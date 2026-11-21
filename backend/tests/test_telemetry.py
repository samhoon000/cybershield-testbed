import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.telemetry import TelemetrySender
from conftest import ADMIN_EMAIL, PASSWORD
from test_portal import csrf, login_admin, make_assignment, make_course, register

URL = "http://127.0.0.1:8091/v1/http-events"
KEY = "11" * 32


def test_queue_overflow_drops_new_events():
    sender = TelemetrySender(URL, "northfield-test", bytes.fromhex(KEY), queue_size=2)
    for event in range(10):
        sender.submit(event)
    assert sender.queue.qsize() == 2
    assert [sender.queue.get_nowait(), sender.queue.get_nowait()] == [0, 1]
    assert sender.health.dropped == 8


@pytest.mark.parametrize("statuses", [(503, 429, 200), (503, 503, 503), (401,)])
def test_retries_use_fresh_nonces_and_report_delivery_health(statuses, monkeypatch):
    requests = []
    delays = []
    events = [{"request_id": "same-event"}]

    async def sleep(seconds):
        delays.append(seconds)

    async def respond(request):
        requests.append(request)
        status = statuses[len(requests) - 1]
        return httpx.Response(status, headers={"Retry-After": "99"} if status == 429 else {})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await sender.deliver(client, events)

    monkeypatch.setattr("app.telemetry.asyncio.sleep", sleep)
    sender = TelemetrySender(URL, "northfield-test", bytes.fromhex(KEY))
    success = statuses[-1] == 200
    assert asyncio.run(run()) is success
    assert len(requests) == len(statuses)
    assert len({request.headers["x-telemetry-nonce"] for request in requests}) == len(statuses)
    assert len({request.headers["x-telemetry-signature"] for request in requests}) == len(statuses)
    assert all(json.loads(request.content)["events"] == events for request in requests)
    assert json.loads(requests[-1].content)["delivery"]["retries"] == len(statuses) - 1
    assert sender.health.sent == int(success)
    assert sender.health.dropped == sender.health.failed_batches == int(not success)
    if success:
        assert delays[-1] == 5


def test_portal_actions_emit_only_safe_metadata_during_collector_outage(application, monkeypatch):
    observed = []
    submit = TelemetrySender.submit

    async def outage(self):
        await asyncio.Event().wait()

    def capture(self, event):
        observed.append(event)
        submit(self, event)

    monkeypatch.setattr(TelemetrySender, "run", outage)
    monkeypatch.setattr(TelemetrySender, "submit", capture)
    settings = application.state.settings.model_dump()
    settings.update(telemetry_collector_url=URL, telemetry_app_id="northfield-test", telemetry_hmac_key=KEY)
    portal = create_app(Settings(_env_file=None, **settings))
    with TestClient(portal) as client:
        course = make_course(client)
        assignment, _ = make_assignment(client, course, login_admin(client))
        assert register(client).status_code == 201
        failure = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "bad-secret"})
        login = client.post("/api/auth/login", json={"email": "student1@example.com", "password": PASSWORD})
        enroll = client.post(f"/api/courses/{course}/enroll?token=private-query", headers=csrf(login))
        submission = client.post(f"/api/assignments/{assignment}/submit",
                                 json={"content": "Confidential synthetic answer"}, headers=csrf(login))
        unknown = client.get("/api/private-person@example.com")
        assert client.get("/health").status_code == 200
        assert client.options("/api/auth/login", headers={
            "Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "POST",
        }).status_code == 200

    assert len(observed) == 10
    by_id = {event["request_id"]: event for event in observed}
    for response, route, code, outcome in [
        (failure, "/api/auth/login", 401, "denied"),
        (login, "/api/auth/login", 200, "authenticated"),
        (enroll, "/api/courses/{course_id}/enroll", 201, "authenticated"),
        (submission, "/api/assignments/{assignment_id}/submit", 201, "authenticated"),
        (unknown, "unmatched", 404, "none"),
    ]:
        assert response.status_code == code, response.text
        event = by_id[response.headers["x-request-id"]]
        assert event.keys() == {"request_id", "timestamp", "route", "method", "status", "duration_ms", "auth"}
        assert (event["route"], event["status"], event["auth"]) == (route, code, outcome)
    serialized = json.dumps(observed)
    for private in (PASSWORD, "bad-secret", "private-query", "Confidential synthetic answer",
                    "student1@example.com", "private-person", login.cookies["portal"], login.json()["csrf_token"]):
        assert private not in serialized
