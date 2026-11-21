"""Staging-only enforcement using locally cached, signed policy snapshots."""

import asyncio
import hashlib
import hmac
import logging
import math
import re
import sqlite3
import time
from collections import OrderedDict
from contextlib import closing
from threading import Lock
from typing import get_args
from uuid import uuid4

import httpx
from fastapi import HTTPException

from .policy_wire import MAX_BYTES, Receipt, Route, Snapshot, Sync, sign

ROUTES = set(get_args(Route))
LOG = logging.getLogger(__name__)


class StagingProtection:
    def __init__(self, settings, clock=time.time, monotonic=time.monotonic):
        self.app = settings.telemetry_app_id
        self.url = settings.protection_url
        self.policy_key = bytes.fromhex(settings.protection_hmac_key.get_secret_value())
        self.subject_key = bytes.fromhex(settings.protection_subject_key.get_secret_value())
        self.watermark = settings.sqlite_path.with_suffix(".policy-state.sqlite3")
        self.kill_switch = settings.sqlite_path.with_suffix(".policy-disabled")
        self.clock = clock
        self.monotonic = monotonic
        self.lock = Lock()
        self.snapshot: Snapshot | None = None
        self.rules = {}
        self.buckets = {}
        self.receipts = OrderedDict()
        self.valid_until = 0.0
        self.disabled_revision = 0
        self.sync_errors = 0

    def subject(self, user):
        scope = f"northfield-subject-v1\n{self.app}\nstaging\n{user.id}\n{user.created_at.isoformat()}"
        return "s1_" + hmac.new(self.subject_key, scope.encode(), hashlib.sha256).hexdigest()

    def receipt(self, snapshot, outcome, rule_id=None, request_id=None):
        item = Receipt(id=str(uuid4()), policy_id=snapshot.id, revision=snapshot.revision, outcome=outcome,
                       rule_id=rule_id, request_id=request_id, timestamp=int(self.clock()))
        self.receipts[item.id] = item
        if len(self.receipts) > 128:
            self.receipts.popitem(last=False)

    def locally_disabled(self, snapshot):
        try:
            disabled = self.kill_switch.exists()
        except OSError:
            disabled = True
        if disabled and self.disabled_revision != snapshot.revision:
            self.disabled_revision = snapshot.revision
            self.receipt(snapshot, "disabled")
        return self.disabled_revision == snapshot.revision

    def install(self, snapshot):
        now = int(self.clock())
        if snapshot.app != self.app or snapshot.environment != "staging" or not snapshot.created <= now < snapshot.expires:
            return False
        with self.lock:
            if self.snapshot and snapshot.revision <= self.snapshot.revision:
                return False
        with closing(sqlite3.connect(self.watermark, timeout=2)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS watermark(app TEXT PRIMARY KEY, revision INTEGER NOT NULL)")
            row = db.execute("SELECT revision FROM watermark WHERE app=?", (self.app,)).fetchone()
            if row and snapshot.revision <= row[0]:
                return False
            db.execute("""
                INSERT INTO watermark VALUES (?, ?) ON CONFLICT(app) DO UPDATE SET revision=excluded.revision
            """, (self.app, snapshot.revision))
        with self.lock:
            if self.snapshot and self.snapshot.revision >= snapshot.revision:
                return False
            self.snapshot = snapshot
            self.valid_until = self.monotonic() + max(0, snapshot.expires - self.clock())
            elapsed, wall = self.monotonic(), self.clock()
            self.rules = {(rule.subject, rule.method, rule.route): (rule, elapsed + max(0, rule.expires - wall))
                          for rule in snapshot.rules}
            self.buckets = {rule.id: self.buckets[rule.id] for rule in snapshot.rules if rule.id in self.buckets}
            if snapshot.enabled and not self.locally_disabled(snapshot):
                self.receipt(snapshot, "applied")
            elif not snapshot.enabled:
                self.disabled_revision = snapshot.revision
                self.receipt(snapshot, "disabled")
        return True

    def enforce(self, request, subject):
        if request.method != "POST":
            return
        route = getattr(request.scope.get("route"), "path_format", "")
        if route not in ROUTES:
            route = "/api" + route
        if route not in ROUTES:
            return
        now, elapsed = self.clock(), self.monotonic()
        with self.lock:
            snapshot = self.snapshot
            if not snapshot or not snapshot.enabled:
                return
            if now >= snapshot.expires or elapsed >= self.valid_until:
                self.rules.clear()
                return
            if self.locally_disabled(snapshot):
                return
            scope = (subject, request.method, route)
            entry = self.rules.get(scope)
            if not entry:
                return
            rule, cutoff = entry
            if now >= rule.expires or elapsed >= cutoff:
                self.rules.pop(scope, None)
                return
            identifier = request.state.request_id
            if rule.action == "block":
                self.receipt(snapshot, "blocked", rule.id, identifier)
                raise HTTPException(403, "This action is temporarily unavailable.")
            started, used = self.buckets.get(rule.id, (elapsed, 0))
            if elapsed - started >= 60:
                started, used = elapsed, 0
            if used >= rule.requests_per_minute:
                wait = max(1, min(math.ceil(60 - (elapsed - started)), math.ceil(rule.expires - now),
                                  math.ceil(cutoff - elapsed)))
                self.receipt(snapshot, "rate_limited", rule.id, identifier)
                raise HTTPException(429, "Too many requests. Try again later.", headers={"Retry-After": str(wait)})
            self.buckets[rule.id] = started, used + 1

    async def poll(self, client):
        with self.lock:
            if self.snapshot and self.snapshot.enabled and self.clock() < self.snapshot.expires:
                self.locally_disabled(self.snapshot)
            receipts = list(self.receipts.values())[:16]
        sync = Sync(version=1, app=self.app, environment="staging", nonce=str(uuid4()),
                    timestamp=int(self.clock()), receipts=receipts, errors=self.sync_errors)
        body = sync.model_dump_json().encode()
        async with asyncio.timeout(4):
            async with client.stream("POST", self.url, content=body, headers={
                "content-type": "application/json",
                "x-policy-signature": sign(self.policy_key, "sync", sync.nonce, body),
            }) as response:
                response.raise_for_status()
                values = response.headers.get_list("x-policy-signature")
                reply = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(reply) + len(chunk) > MAX_BYTES:
                        raise ValueError("Policy response is oversized")
                    reply.extend(chunk)
                if len(values) != 1 or not re.fullmatch(r"[0-9a-f]{64}", values[0]) or not hmac.compare_digest(
                    values[0], sign(self.policy_key, "snapshot", sync.nonce, bytes(reply))
                ):
                    raise ValueError("Policy response signature is invalid")
        snapshot = Snapshot.model_validate_json(reply)
        if snapshot.app != self.app or not snapshot.created <= int(self.clock()) < snapshot.expires:
            raise ValueError("Policy application or validity mismatch")
        with self.lock:
            previous = self.snapshot
            if previous and (snapshot.revision < previous.revision or
                             (snapshot.revision == previous.revision and snapshot != previous)):
                raise ValueError("Policy revision rollback or conflict")
        await asyncio.to_thread(self.install, snapshot)
        with self.lock:
            for item in receipts:
                self.receipts.pop(item.id, None)

    async def sync_once(self, client):
        try:
            await self.poll(client)
        except (httpx.HTTPError, TimeoutError, ValueError, OSError, sqlite3.Error) as error:
            with self.lock:
                self.snapshot = None
                self.rules.clear()
                self.sync_errors = min(self.sync_errors + 1, 2**53 - 1)
            LOG.warning("Staging policy sync unavailable: %s", type(error).__name__)
            return False
        return True

    async def run(self):
        async with httpx.AsyncClient(timeout=4, follow_redirects=False, trust_env=False) as client:
            while True:
                await self.sync_once(client)
                await asyncio.sleep(2)
