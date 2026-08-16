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


class CorsSettings(BaseModel):
    """Origins the browser-facing frontend (radar-eye-command) is allowed
    to call this API from. Structural, not secret, so it lives in
    configs/settings.yaml like other deployment-shaped config -- unlike
    AuthSettings/DatabaseSettings there's no secret value here to keep out
    of the file. Defaults cover the frontend's own documented local dev
    setup (src/api/instance.ts / src/ws/connection.ts default to
    localhost:8000 for the API; the frontend's `@lovable.dev/vite-tanstack-
    config` dev server pins port 8080 in-sandbox, per its own
    validatePort()) so a fresh checkout works without editing YAML."""

    allowed_origins: list[str] = ["http://localhost:8080", "http://127.0.0.1:8080"]


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
    cors: CorsSettings
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
        cors=CorsSettings(**raw.get("cors", {})),
        auth=auth,
        encryption_key=env.encryption_key,
        log_level=env.log_level,
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()


DEFAULT_LIVE_STREAM_PATH = REPO_ROOT / "configs" / "live_stream.yaml"


class LiveStreamHttpSettings(BaseModel):
    """Where apps.deepstream's ``hlssink2`` writes each camera's HLS
    segments/playlist (ADR-031) -- apps.api serves this directory
    directly over authenticated HTTP (``GET /cameras/{camera_id}/hls/...``,
    ADR-011 "centralized access control": apps.api is the sole
    externally-reachable authenticated door). File-based hand-off, not a
    network proxy: both processes read the *same*
    ``configs/live_stream.yaml`` independently (one file, one source of
    truth for the path), and there is no other cross-process
    communication between them for video besides this shared directory."""

    output_dir: str = "/tmp/radar-eye/hls"


def load_live_stream_http_settings(
    live_stream_path: Path | None = None,
) -> LiveStreamHttpSettings:
    path = live_stream_path or DEFAULT_LIVE_STREAM_PATH
    raw = _load_yaml(path)
    return LiveStreamHttpSettings(output_dir=raw.get("output_dir", "/tmp/radar-eye/hls"))


@lru_cache
def get_live_stream_http_settings() -> LiveStreamHttpSettings:
    return load_live_stream_http_settings()
