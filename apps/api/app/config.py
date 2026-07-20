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


class EnvSettings(BaseSettings):
    """Values that must come from the environment, never from settings.yaml."""

    model_config = SettingsConfigDict(
        env_prefix="RADAR_EYE_",
        env_file=".env",
        extra="ignore",
    )

    db_user: str
    db_password: SecretStr
    log_level: str = "INFO"


class Settings(BaseModel):
    environment: str
    database: DatabaseSettings
    recording: RecordingSettings
    threat_engine: ThreatEngineSettings
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
    env = EnvSettings()

    db_section = raw.get("database", {})
    database = DatabaseSettings(
        host=db_section["host"],
        port=db_section["port"],
        name=db_section["name"],
        user=env.db_user,
        password=env.db_password,
    )

    return Settings(
        environment=raw.get("environment", "development"),
        database=database,
        recording=RecordingSettings(**raw.get("recording", {})),
        threat_engine=ThreatEngineSettings(**raw.get("threat_engine", {})),
        log_level=env.log_level,
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()
