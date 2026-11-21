from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Assignment, Session, User, now
from app.security import passwords
from conftest import ADMIN_EMAIL, PASSWORD

COURSE = {
    "title": "Introduction to Data", "description": "Build a foundation in data analysis.",
    "category": "Data Science", "instructor": "Helen Li", "duration": 8, "status": "open",
}


def register(client, number=1, **changes):
    payload = {
        "full_name": "Jordan Lee", "email": f"student{number}@example.com", "student_id": f"NF-10{number}",
        "password": PASSWORD, "confirm_password": PASSWORD,
    }
    return client.post("/api/auth/register", json={**payload, **changes})


def csrf(response):
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def login_admin(client):
    response = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return csrf(response)


def make_course(client, **changes):
    response = client.post("/api/courses", json={**COURSE, **changes}, headers=login_admin(client))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def make_assignment(client, course, headers):
    payload = {"title": "Case study", "description": "Evaluate the case and describe your findings.",
               "course_id": course, "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat()}
    response = client.post("/api/assignments", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"], payload


def test_health(client):
    response = client.get("/health")
    assert response.json() == {"status": "ok"}
    assert response.headers["x-content-type-options"] == "nosniff"


def test_registration_and_case_insensitive_uniqueness(client, application):
    response = register(client, email="Student1@example.com", student_id="nf-101")
    assert response.status_code == 201, response.text
    assert response.json()["user"]["role"] == "student"
    assert response.json()["user"]["student_id"] == "NF-101"
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()
    assert client.get("/api/auth/me").json()["user"]["email"] == "student1@example.com"
    with application.state.sessions() as db:
        user = db.scalar(select(User).where(User.email == "student1@example.com"))
        assert user.password_hash != PASSWORD and passwords.verify(user.password_hash, PASSWORD)
    assert register(client, 2, email="STUDENT1@example.com").status_code == 409
    assert register(client, 2, student_id="NF-101").status_code == 409


def test_login_logout_and_revocation(client):
    assert register(client).status_code == 201
    response = client.post("/api/auth/login", json={"email": "student1@example.com", "password": PASSWORD})
    assert response.status_code == 200
    token = client.cookies.get("portal")
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers=csrf(response)).status_code == 204
    assert client.get("/api/auth/me", headers={"Cookie": f"portal={token}"}).status_code == 401


def test_session_expiration(client, application):
    assert register(client).status_code == 201
    with application.state.sessions.begin() as db:
        session = db.scalar(select(Session))
        session.expires_at = now() - timedelta(seconds=1)
    assert client.get("/api/auth/me").status_code == 401


def test_invalid_credentials_and_events(client):
    bad = {"email": ADMIN_EMAIL, "password": "incorrect"}
    first = client.post("/api/auth/login", json=bad)
    second = client.post("/api/auth/login", json={**bad, "email": "missing@example.com"})
    assert first.json() == second.json() == {"detail": "Invalid email or password"}
    assert first.status_code == second.status_code == 401
    login_admin(client)
    failures = client.get("/api/activity?event_type=login_failed").json()
    assert len(failures) == 2
    assert all(event["user_id"] is None and event["outcome"] == "denied" for event in failures)
    assert first.headers["x-request-id"] in [event["request_id"] for event in failures]


def test_validation_does_not_echo_secrets(client):
    response = register(client, password="confidential mismatched input")
    assert response.status_code == 422
    assert "confidential" not in response.text
    assert register(client, role="admin").status_code == 422
    assert register(client, email="invalid").status_code == 422
    assert register(client, student_id="!!!!").status_code == 422


def test_authentication_and_role_boundaries(client, application):
    assert client.get("/api/courses").status_code == 401
    assert client.get("/api/dashboard/stats").status_code == 401
    student = register(client)
    assert student.status_code == 201
    assert client.get("/api/students").status_code == 403
    assert client.post("/api/courses", json=COURSE, headers=csrf(student)).status_code == 403
    assert client.post("/api/assignments", json={}, headers=csrf(student)).status_code == 403
    with TestClient(application) as admin:
        headers = login_admin(admin)
        assert admin.get("/api/students").json()[0]["id"] == student.json()["user"]["id"]
        assert admin.post("/api/courses/1/enroll", headers=headers).status_code == 403
        events = admin.get("/api/activity").json()
        assert {"authentication_failed", "authorization_failed"} <= {event["event_type"] for event in events}


def test_course_crud_listing_enrollment_and_progress(client, application):
    course = make_course(client)
    closed = make_course(client, title="Design Basics", category="Design", status="closed")
    headers = login_admin(client)
    assert client.put(f"/api/courses/{course}", json={**COURSE, "title": "Applied Data"}, headers=headers).status_code == 200
    assert client.get("/api/courses", params={"search": "applied", "category": "Data Science"}).json()["total"] == 1
    assert client.get("/api/courses?search=%25").json()["total"] == 0
    assert client.get("/api/courses?page=2&page_size=1").json()["total"] == 2
    with TestClient(application) as student:
        session = register(student)
        student_headers = csrf(session)
        assert student.get("/api/courses/enrolled").json() == []
        assert student.post(f"/api/courses/{closed}/enroll", headers=student_headers).status_code == 409
        result = student.post(f"/api/courses/{course}/enroll", headers=student_headers)
        assert result.status_code == 201, result.text
        assert student.post(f"/api/courses/{course}/enroll", headers=student_headers).status_code == 409
        assert student.get("/api/courses/enrolled").json()[0]["id"] == course
        assert student.post(f"/api/courses/{course}/access", headers=student_headers).status_code == 204
        assert student.put(f"/api/courses/{course}/progress", json={"progress": 101}, headers=student_headers).status_code == 422
        assert student.put(f"/api/courses/{course}/progress", json={"progress": 100}, headers=student_headers).status_code == 200
        dashboard = student.get("/api/dashboard/stats").json()
        assert (dashboard["enrolled"], dashboard["completed"], dashboard["progress"]) == (1, 1, 100)
        activity = student.get("/api/activity?event_type=course_enrolled").json()
        assert activity[0]["request_id"] == result.headers["x-request-id"]
        assert client.delete(f"/api/courses/{course}", headers=headers).status_code == 204
        assert student.get("/api/courses/enrolled").json() == []


def test_assignment_workflows_visibility_and_deadlines(client, application):
    course = make_course(client)
    admin_headers = login_admin(client)
    assignment, payload = make_assignment(client, course, admin_headers)
    route = f"/api/assignments/{assignment}"
    assert client.put(route, json={**payload, "title": "Updated case study"}, headers=admin_headers).status_code == 200
    with TestClient(application) as student, TestClient(application) as other:
        student_headers = csrf(register(student))
        other_headers = csrf(register(other, 2))
        assert student.get(route).status_code == 404
        assert student.post(f"/api/courses/{course}/enroll", headers=student_headers).status_code == 201
        assert other.post(f"/api/courses/{course}/enroll", headers=other_headers).status_code == 201
        assert student.get(route).json()["title"] == "Updated case study"
        assert student.get("/api/dashboard/stats").json()["pending"] == 1
        assert student.post(route + "/submit", json={"content": "  "}, headers=student_headers).status_code == 422
        for content in ["My submission", "My revised submission"]:
            response = student.post(route + "/submit", json={"content": content}, headers=student_headers)
            assert response.status_code == 201, response.text
        assert len(student.get(route + "/submissions").json()) == 2
        assert other.get(route + "/submissions").json() == []
        assert student.get("/api/dashboard/stats").json()["submission_stats"][0]["value"] == 1
        assert client.get(route + "/submissions").json()[0]["student_name"] == "Jordan Lee"
        with application.state.sessions.begin() as db:
            db.get(Assignment, assignment).deadline = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        assert student.post(route + "/submit", json={"content": "Late work"}, headers=student_headers).status_code == 409


def test_profile_ownership(client, application):
    first = register(client)
    with TestClient(application) as other:
        second = register(other, 2, full_name="Other Student")
        path = f"/api/students/{second.json()['user']['id']}"
        assert client.get(path).status_code == 404
        fields = {"full_name": "Jordan Updated", "academic_year": 2, "department": "Computing"}
        assert client.put("/api/students/me", json={**fields, "id": second.json()["user"]["id"]},
                          headers=csrf(first)).status_code == 422
        assert client.put("/api/students/me", json=fields, headers=csrf(first)).status_code == 200
        assert client.get("/api/students/me").json()["full_name"] == "Jordan Updated"
        assert other.get("/api/students/me").json()["full_name"] == "Other Student"
        assert not other.get("/api/activity?event_type=profile_updated").json()


def test_authentication_rate_limit(client):
    payload = {"email": ADMIN_EMAIL, "password": "incorrect"}
    for _ in range(8):
        assert client.post("/api/auth/login", json=payload).status_code == 401
    denied = client.post("/api/auth/login", json=payload, headers={"X-Forwarded-For": "192.0.2.1"})
    assert denied.status_code == 429
    assert denied.headers["retry-after"] == "60"


def test_restricted_origin_csrf_and_body_size(client):
    session = register(client)
    fields = {"full_name": "Test Student", "academic_year": None, "department": ""}
    assert client.put("/api/students/me", json=fields).status_code == 403
    assert client.put("/api/students/me", json=fields,
                      headers={**csrf(session), "Origin": "https://unrelated.example.com"}).status_code == 403
    assert client.put("/api/students/me", json=fields,
                      headers={**csrf(session), "Origin": "http://127.0.0.1:5173"}).status_code == 200
    response = client.post("/api/auth/login", content=b"x" * 131073)
    assert response.status_code == 413
    assert response.headers["x-request-id"]


def test_production_cookie_and_headers(application):
    from app.main import create_app

    settings = application.state.settings.model_copy(update={
        "app_env": "production", "allowed_origins": "https://portal.example.com",
    })
    with TestClient(create_app(settings), base_url="https://portal.example.com") as secure:
        response = secure.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert cookie.startswith("__Host-portal=") and "Secure" in cookie and "HttpOnly" in cookie
        assert secure.get("/api/auth/me").status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
