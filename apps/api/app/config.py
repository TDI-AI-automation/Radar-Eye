"""Application settings.

Structural, non-secret configuration is read from ``configs/settings.yaml``.
Secret and deployment-environment-specific values (database credentials, log
level) come only from environment variables and are never written to that
file.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SETTINGS_PATH = REPO_ROOT / "configs" / "settings.yaml"


class DatabaseSettings(BaseModel):
    """Database connection details.

    ``host``/``port``/``name`` come from configs/settings.yaml.
    ``user``/``password`` are environment-only and are merged in by
    load_settings() -- they never appear in the YAML file.
    """

    host: str
    port: int
    name: str
    user: str
    password: SecretStr

    @property
    def url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:"
            f"{self.password.get_secret_value()}@{self.host}:{self.port}/{self.name}"
        )


class RecordingSettings(BaseModel):
    retention_days: int


class ThreatEngineSettings(BaseModel):
    enabled: bool


class AuthSettings(BaseModel):
    """JWT signing/expiry configuration (RM-12, docs/RM-12_ARCHITECTURE.md
    §3.2). ``jwt_secret`` is environment-only, like ``encryption_key`` --
    never written to configs/settings.yaml. TTLs have safe defaults so a
    fresh checkout without explicit env overrides still works."""

    jwt_secret: SecretStr
    access_token_ttl_seconds: int = 900
    """15 minutes -- short-lived by design; a compromised access token has
    a small blast-radius window. Refresh tokens are what carry a session
    forward, not a long-lived access token."""
    refresh_token_ttl_seconds: int = 604800
    """7 days."""


class EnvSettings(BaseSettings):
    """Values that must come from the environment, never from settings.yaml."""

    model_config = SettingsConfigDict(
        env_prefix="RADAR_EYE_",
        env_file=".env",
        extra="ignore",
    )

    db_user: str
    db_password: SecretStr
    encryption_key: SecretStr
    jwt_secret: SecretStr
    log_level: str = "INFO"


class Settings(BaseModel):
    environment: str
    database: DatabaseSettings
    recording: RecordingSettings
    threat_engine: ThreatEngineSettings
    auth: AuthSettings
    encryption_key: SecretStr
    log_level: str

    @property
    def database_url(self) -> str:
        return self.database.url


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_settings(settings_path: Path | None = None) -> Settings:
    """Load settings.yaml and overlay environment-only secrets.

    Called fresh (uncached) so tests can exercise different environment
    variable combinations. Application code should use get_settings()
    instead, which caches the result for the lifetime of the process.
    """
    path = settings_path or DEFAULT_SETTINGS_PATH
    raw = _load_yaml(path)
    # Required fields are sourced from RADAR_EYE_* env vars / .env at runtime
    # by pydantic-settings -- mypy has no way to see that without the fields
    # becoming Optional, so the zero-arg call is a known false positive.
    env = EnvSettings()  # type: ignore[call-arg]

    db_section = raw.get("database", {})
    database = DatabaseSettings(
        host=db_section["host"],
        port=db_section["port"],
        name=db_section["name"],
        user=env.db_user,
        password=env.db_password,
    )

    auth_section = raw.get("auth", {})
    auth = AuthSettings(jwt_secret=env.jwt_secret, **auth_section)

    return Settings(
        environment=raw.get("environment", "development"),
        database=database,
        recording=RecordingSettings(**raw.get("recording", {})),
        threat_engine=ThreatEngineSettings(**raw.get("threat_engine", {})),
        auth=auth,
        encryption_key=env.encryption_key,
        log_level=env.log_level,
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()
