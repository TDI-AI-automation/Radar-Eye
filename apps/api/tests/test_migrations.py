"""Automated migration up/down verification against real PostgreSQL.

Acceptance criterion (docs/IMPLEMENTATION_ROADMAP.md, RM-03): migrations are
reversible. Per the RM-03 design review, migration tests run against a real
PostgreSQL -- never SQLite, since production semantics (JSONB, partial
unique indices, custom ENUM types) differ.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from apps.api.app.config import REPO_ROOT, get_settings
from apps.api.app.db import create_engine

_ALEMBIC_INI = REPO_ROOT / "apps" / "api" / "alembic.ini"

_EXPECTED_TABLES = {
    "cameras",
    "camera_stream_profiles",
    "camera_calibrations",
    "incidents",
    "incident_events",
    "human_review_items",
    "snapshots",
    "recordings",
    "system_events",
    "users",
    "audit_log",
}


def _alembic_config() -> Config:
    return Config(str(_ALEMBIC_INI))


async def _reset_schema(settings) -> None:
    """Drop every table/type this migration owns, so each test starts clean
    regardless of what other test files left behind."""
    engine = create_engine(settings)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "DROP TABLE IF EXISTS snapshots, recordings, incident_events, incidents, "
                "human_review_items, camera_stream_profiles, camera_calibrations, users, "
                "system_events, cameras, audit_log, alembic_version CASCADE"
            )
        )
        await conn.execute(text("DROP TYPE IF EXISTS incident_status, incident_type, threat_level"))
    await engine.dispose()


async def _list_tables(settings) -> set[str]:
    engine = create_engine(settings)
    async with engine.connect() as conn:
        names = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    await engine.dispose()
    return set(names)


@pytest.fixture
def clean_postgres(_default_env: None) -> Iterator[None]:
    """Skip if PostgreSQL is unreachable; otherwise guarantee a clean schema
    before and after the test (docs/... testing strategy -- CI always has a
    real PostgreSQL service; local/agent-driven dev without Docker skips)."""
    settings = get_settings()
    try:
        asyncio.run(_reset_schema(settings))
    except Exception as exc:  # noqa: BLE001 -- any connectivity failure means "skip"
        pytest.skip(f"PostgreSQL is not reachable, skipping migration test: {exc}")

    yield

    asyncio.run(_reset_schema(settings))


class TestMigrations:
    def test_upgrade_creates_all_tables(self, clean_postgres: None) -> None:
        command.upgrade(_alembic_config(), "head")

        tables = asyncio.run(_list_tables(get_settings()))

        assert _EXPECTED_TABLES.issubset(tables)

    def test_downgrade_removes_all_tables(self, clean_postgres: None) -> None:
        command.upgrade(_alembic_config(), "head")
        command.downgrade(_alembic_config(), "base")

        tables = asyncio.run(_list_tables(get_settings()))

        assert _EXPECTED_TABLES.isdisjoint(tables)

    def test_migration_is_reversible_across_multiple_cycles(self, clean_postgres: None) -> None:
        cfg = _alembic_config()

        for _ in range(3):
            command.upgrade(cfg, "head")
            command.downgrade(cfg, "base")

        # No exception across three full up/down cycles is the acceptance
        # criterion itself; confirm the final state is clean.
        tables = asyncio.run(_list_tables(get_settings()))
        assert _EXPECTED_TABLES.isdisjoint(tables)
