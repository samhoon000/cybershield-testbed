from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from secrets import compare_digest, token_urlsafe
from threading import BoundedSemaphore, Lock
from time import monotonic
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete
from sqlalchemy.orm import Session as DatabaseSession

from .activity import record
from .models import Session, User, now
from .protection import subject_for

passwords = PasswordHasher()
DUMMY_HASH = passwords.hash(token_urlsafe(32))
password_slots = BoundedSemaphore(3)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class AuthRateLimit:
    """Bounded, process-local admission limit for credential endpoints."""

    def __init__(self, limit: int):
        self.limit = limit
        self.entries: OrderedDict[str, tuple[float, int]] = OrderedDict()
        self.lock = Lock()

    def allow(self, peer: str) -> bool:
        current_time = monotonic()
        with self.lock:
            while self.entries:
                oldest = next(iter(self.entries))
                if current_time - self.entries[oldest][0] < 60:
                    break
                self.entries.popitem(last=False)
            if peer not in self.entries:
                if len(self.entries) >= 10000:
                    return False
                self.entries[peer] = (current_time, 0)
            started, count = self.entries[peer]
            if count >= self.limit:
                return False
            self.entries[peer] = (started, count + 1)
            return True


def db_session(request: Request):
    with request.app.state.sessions() as db:
        yield db


def cookie_name(request: Request) -> str:
    return "__Host-portal" if request.app.state.settings.app_env == "production" else "portal"


def set_session_cookie(request: Request, response: Response, value: str, max_age: int):
    settings = request.app.state.settings
    cross_site = settings.session_cross_site
    attributes = {"partitioned": True} if cross_site else {}
    response.set_cookie(cookie_name(request), value, max_age=max_age, expires=0 if max_age == 0 else None,
                        secure=settings.app_env == "production", httponly=True, path="/",
                        samesite="none" if cross_site else "lax", **attributes)


def issue_session(request: Request, response: Response, db: DatabaseSession, user: User) -> str:
    settings = request.app.state.settings
    sid = str(uuid4())
    csrf = token_urlsafe(32)
    current = datetime.now(UTC)
    lifetime = timedelta(minutes=settings.session_minutes)
    expires = current + lifetime
    db.execute(delete(Session).where(Session.expires_at <= now()))
    db.add(Session(id=sid, user_id=user.id, expires_at=expires.replace(tzinfo=None)))
    token = jwt.encode(
        {"sub": str(user.id), "jti": sid, "csrf": csrf, "iat": current, "exp": expires, "aud": "northfield-portal"},
        settings.jwt_secret.get_secret_value(), algorithm="HS256",
    )
    set_session_cookie(request, response, token, max_age=int(lifetime.total_seconds()))
    return csrf


def credentials_match(user: User | None, password: str) -> bool:
    try:
        valid = passwords.verify(user.password_hash if user else DUMMY_HASH, password)
    except (InvalidHashError, VerificationError):
        return False
    return user is not None and valid


def deny(request: Request, db: DatabaseSession, code: int, message: str, user_id: int | None = None):
    request.state.auth_outcome = "denied"
    record(db, request, "authentication_failed" if code == 401 else "authorization_failed",
           user_id=user_id, outcome="denied")
    db.commit()
    raise HTTPException(code, message)


def require_user(request: Request, db: DatabaseSession = Depends(db_session)) -> User:
    settings = request.app.state.settings
    token = request.cookies.get(cookie_name(request))
    if not token:
        # The frontend probes /me before presenting the login screen.
        if request.url.path == "/api/auth/me":
            request.state.auth_outcome = "anonymous"
            raise HTTPException(401, "Sign in to continue")
        deny(request, db, 401, "Sign in to continue")
    try:
        claims = jwt.decode(token, settings.jwt_secret.get_secret_value(), algorithms=["HS256"],
                            audience="northfield-portal", options={"require": ["exp", "iat", "sub", "jti", "csrf"]})
    except jwt.InvalidTokenError:
        deny(request, db, 401, "Session expired or invalid")
    session = db.get(Session, claims["jti"])
    if not session or session.expires_at <= now() or str(session.user_id) != claims["sub"]:
        deny(request, db, 401, "Session expired or invalid")
    user = db.get(User, session.user_id)
    if not user:
        deny(request, db, 401, "Session expired or invalid")

    request.state.user_id = user.id
    request.state.auth_outcome = "authenticated"
    request.state.session_id = session.id
    request.state.csrf = claims["csrf"]
    if request.method not in SAFE_METHODS:
        supplied = request.headers.get("x-csrf-token", "").encode()
        if not compare_digest(supplied, claims["csrf"].encode()):
            deny(request, db, 403, "Invalid request token", user.id)
    key = request.app.state.subject_key
    if key and user.role == "student":
        subject = subject_for(key, settings.telemetry_app_id, user)
        request.state.telemetry_subject = subject
        if protection := request.app.state.protection:
            protection.enforce(request, subject)
    return user


def require_role(role: str):
    def authorize(request: Request, user: User = Depends(require_user),
                  db: DatabaseSession = Depends(db_session)) -> User:
        if user.role != role:
            deny(request, db, 403, "You do not have access to this action", user.id)
        return user
    return authorize


student_only = require_role("student")
admin_only = require_role("admin")
