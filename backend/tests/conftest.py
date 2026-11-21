from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import make_engine
from app.main import create_app
from app.models import User
from app.security import passwords

PASSWORD = "a local testing password"
ADMIN_EMAIL = "admin@example.com"


@pytest.fixture()
def application(tmp_path):
    settings = Settings(_env_file=None, app_env="test", jwt_secret="local-test-secret-used-only-by-pytest",
                        sqlite_path=tmp_path / "portal.sqlite3", auth_requests_per_minute=8)
    engine = make_engine(settings.sqlite_path)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    engine.dispose()
    app = create_app(settings)
    with app.state.sessions.begin() as db:
        db.add(User(email=ADMIN_EMAIL, full_name="Test Administrator", student_id="ADMIN-01",
                    role="admin", password_hash=passwords.hash(PASSWORD)))
    return app


@pytest.fixture()
def client(application):
    with TestClient(application) as test:
        yield test
