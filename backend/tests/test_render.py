import sys
from secrets import token_urlsafe

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.bootstrap import initialize
from app.config import Settings
from app.db import make_engine, make_sessions
from app.main import create_app
from app.models import Assignment, Course, User

FRONTEND = "https://frontend.example.com"
BACKEND = "https://api.example.net"
UNLISTED = "https://other.example.com"


def test_production_bootstrap_is_repeatable_and_rebuilds_fresh_sqlite(tmp_path):
    settings = Settings(
        _env_file=None, app_env="production", jwt_secret=token_urlsafe(48),
        allowed_origins=FRONTEND, sqlite_path=tmp_path / "first.sqlite3",
        seed_demo_data=True, demo_admin_email="demo-admin@example.com", demo_admin_password=token_urlsafe(32),
        demo_student_email="demo-student@example.com", demo_student_password=token_urlsafe(32),
    )
    initialize(settings)
    engine = make_engine(settings.sqlite_path)
    sessions = make_sessions(engine)
    with sessions.begin() as db:
        student = db.scalar(select(User).where(User.email == settings.demo_student_email))
        student.department = "User edit"
    initialize(settings)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 19
        assert db.scalar(select(func.count()).select_from(Course)) == 12
        assert db.scalar(select(func.count()).select_from(Assignment)) == 24
        assert db.scalar(select(User.department).where(User.email == settings.demo_student_email)) == "User edit"
    engine.dispose()

    reset = settings.model_copy(update={"sqlite_path": tmp_path / "after-reset.sqlite3"})
    initialize(reset)
    with TestClient(create_app(reset), base_url=BACKEND) as client:
        assert client.get("/health").status_code == 200
        response = client.post("/api/auth/login", json={"email": settings.demo_admin_email,
                                                       "password": settings.demo_admin_password.get_secret_value()})
        assert response.status_code == 200
        assert response.json()["user"]["role"] == "admin"
        assert len(client.get("/api/students").json()) == 18


@pytest.mark.skipif(sys.version_info < (3, 14), reason="Cross-site CHIPS needs Python 3.14+")
def test_partitioned_cookie_cors_and_csrf(application):
    settings = application.state.settings.model_copy(update={
        "app_env": "production", "allowed_origins": FRONTEND, "session_cross_site": True,
    })
    with TestClient(create_app(settings), base_url=BACKEND) as client:
        preflight_headers = {
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
        }
        preflight = client.options("/api/auth/logout", headers={**preflight_headers, "Origin": FRONTEND})
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == FRONTEND
        assert preflight.headers["access-control-allow-credentials"] == "true"
        unlisted = client.options("/api/auth/logout", headers={**preflight_headers, "Origin": UNLISTED})
        assert unlisted.status_code == 400
        assert "access-control-allow-origin" not in unlisted.headers

        password = token_urlsafe(32)
        signup = client.post("/api/auth/register", headers={"Origin": FRONTEND}, json={
            "full_name": "Render Test Student", "email": "render-student@example.com",
            "student_id": "NF-RENDER", "password": password, "confirm_password": password,
        })
        assert signup.status_code == 201
        cookie = signup.headers["set-cookie"].lower()
        assert cookie.startswith("__host-portal=")
        assert all(flag in cookie for flag in ("partitioned", "samesite=none", "secure", "httponly", "path=/"))
        assert "domain=" not in cookie
        assert client.get("/api/auth/me", headers={"Origin": FRONTEND}).status_code == 200
        csrf = signup.json()["csrf_token"]
        assert client.post("/api/auth/logout", headers={"Origin": FRONTEND}).status_code == 403
        assert client.post("/api/auth/logout", headers={"Origin": UNLISTED, "X-CSRF-Token": csrf}).status_code == 403
        logout = client.post("/api/auth/logout", headers={"Origin": FRONTEND, "X-CSRF-Token": csrf})
        assert logout.status_code == 204
        logout_cookie = logout.headers["set-cookie"].lower()
        assert "partitioned" in logout_cookie and "max-age=0" in logout_cookie
        assert client.get("/api/auth/me", headers={"Origin": FRONTEND}).status_code == 401
