from pathlib import Path
import re
import sys
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .telemetry import PATH
from .policy_wire import APP as PROTECTION_APP, SYNC_PATH

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["development", "test", "production"] = "development"
    jwt_secret: SecretStr
    session_minutes: int = Field(30, ge=5, le=60)
    session_cross_site: bool = False
    sqlite_path: Path = ROOT / "portal.sqlite3"
    allowed_origins: str = "http://127.0.0.1:5173,http://127.0.0.1:8000"
    auth_requests_per_minute: int = Field(12, ge=1, le=100)
    max_body_bytes: int = Field(131072, ge=16384, le=1048576)
    seed_demo_data: bool = False
    demo_admin_email: str = ""
    demo_admin_password: SecretStr = SecretStr("")
    demo_student_email: str = ""
    demo_student_password: SecretStr = SecretStr("")
    telemetry_collector_url: str = ""
    telemetry_app_id: str = ""
    telemetry_hmac_key: SecretStr = SecretStr("")
    protection_url: str = ""
    protection_hmac_key: SecretStr = SecretStr("")
    protection_subject_key: SecretStr = SecretStr("")

    @property
    def origins(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.allowed_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_security(self):
        if len(self.jwt_secret.get_secret_value().encode()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 bytes")
        for origin in self.origins:
            parts = urlsplit(origin)
            if (parts.scheme not in {"http", "https"} or not parts.hostname or "*" in origin
                    or parts.username is not None or parts.path or parts.query or parts.fragment):
                raise ValueError("ALLOWED_ORIGINS must contain explicit HTTP(S) origins")
        if self.app_env == "production" and (
            not self.origins or any(not origin.startswith("https://") for origin in self.origins)
        ):
            raise ValueError("Production requires HTTPS origins")
        if self.session_cross_site and (self.app_env != "production" or sys.version_info < (3, 14)):
            raise ValueError("SESSION_CROSS_SITE requires APP_ENV=production and Python 3.14+")
        if not self.sqlite_path.is_absolute():
            self.sqlite_path = ROOT / self.sqlite_path
        key = self.telemetry_hmac_key.get_secret_value()
        if any((self.telemetry_collector_url, self.telemetry_app_id, key)):
            parts = urlsplit(self.telemetry_collector_url)
            loopback = parts.hostname in {"localhost", "127.0.0.1", "::1"}
            secure = parts.scheme == "https" or (
                self.app_env != "production" and loopback and parts.scheme == "http"
            )
            if (not secure or not parts.hostname or parts.username is not None or parts.path != PATH
                    or parts.port == 0 or any(char.isspace() for char in self.telemetry_collector_url)
                    or "?" in self.telemetry_collector_url or "#" in self.telemetry_collector_url
                    or not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", self.telemetry_app_id)
                    or not re.fullmatch(r"[0-9a-f]{64}", key)):
                raise ValueError("Telemetry requires a collector URL, application ID, and 64-digit hex HMAC key")
        policy_key = self.protection_hmac_key.get_secret_value()
        subject_key = self.protection_subject_key.get_secret_value()
        if any((self.protection_url, policy_key, subject_key)):
            target = urlsplit(self.protection_url)
            if (self.app_env == "production" or not self.telemetry_collector_url
                    or not re.fullmatch(PROTECTION_APP, self.telemetry_app_id)
                    or target.scheme != "http" or target.hostname != "127.0.0.1"
                    or target.username is not None or not target.port or target.path != SYNC_PATH
                    or self.protection_url != f"http://127.0.0.1:{target.port}{SYNC_PATH}"
                    or not all(re.fullmatch(r"[0-9a-f]{64}", value) for value in (policy_key, subject_key))
                    or len({policy_key, subject_key, key, self.jwt_secret.get_secret_value()}) != 4):
                raise ValueError("Policy enforcement requires an isolated staging app and independent local keys")
        return self
