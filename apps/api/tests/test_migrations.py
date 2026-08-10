"""Automated migration up/down verification against real PostgreSQL.

Acceptance criterion (docs/IMPLEMENTATION_ROADMAP.md, RM-03): migrations are
reversible. Per the RM-03 design review, migration tests run against a real
PostgreSQL -- never SQLite, since production semantics (JSONB, partial
unique indices, custom ENUM types) differ.

Runs against the guarded test database (``test_database_url`` fixture,
root conftest.py) -- never ``get_settings()``. This file used to call
``get_settings()`` directly and run raw ``DROP TABLE ... CASCADE`` plus
``alembic downgrade base`` against whatever it returned -- the real
development database, since ``get_settings()`` never resolves to the test
database on its own. That ran against real application data for real,
more than once.

No monkeypatching: ``alembic/env.py`` only calls ``get_settings()`` if
nothing already set ``sqlalchemy.url`` on its ``Config`` object, so
``_alembic_config()`` below sets that URL directly before any
``alembic.command`` call -- the same mechanism a real deployment's own
``alembic.ini``/CLI invocation would use, not a test-only branch.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from apps.api.app.config import REPO_ROOT

_ALEMBIC_INI = REPO_ROOT / "apps" / "api" / "alembic.ini"

_EXPECTED_TABLES = {
    "cameras",
    "camera_stream_profiles",
    "camera_calibrations",
    "camera_media_endpoints",
    "camera_subsystem_health",
    "incidents",
    "incident_events",
    "human_review_items",
    "snapshots",
    "recordings",
    "system_events",
    "users",
    "audit_log",
}


def _alembic_config(database_url: str) -> Config:
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


async def _reset_schema(database_url: str) -> None:
    """Drop every table/type this migration owns, so each test starts clean
    regardless of what other test files left behind."""
    engine = create_async_engine(database_url, future=True)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "DROP TABLE IF EXISTS snapshots, recordings, incident_events, incidents, "
                "human_review_items, camera_stream_profiles, camera_calibrations, "
                "camera_media_endpoints, camera_subsystem_health, users, "
                "system_events, cameras, audit_log, alembic_version CASCADE"
            )
        )
        await conn.execute(text("DROP TYPE IF EXISTS incident_status, incident_type, threat_level"))
    await engine.dispose()


async def _list_tables(database_url: str) -> set[str]:
    engine = create_async_engine(database_url, future=True)
    async with engine.connect() as conn:
        names = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    await engine.dispose()
    return set(names)


@pytest.fixture
def clean_postgres(test_database_url: str) -> Iterator[None]:
    """Skip if the test PostgreSQL database is unreachable; otherwise
    guarantee a clean schema before and after the test."""
    try:
        asyncio.run(_reset_schema(test_database_url))
    except Exception as exc:  # noqa: BLE001 -- any connectivity failure means "skip"
        pytest.skip(f"Test PostgreSQL database is not reachable, skipping migration test: {exc}")

    yield

    asyncio.run(_reset_schema(test_database_url))


class TestMigrations:
    def test_upgrade_creates_all_tables(self, clean_postgres: None, test_database_url: str) -> None:
        command.upgrade(_alembic_config(test_database_url), "head")

        tables = asyncio.run(_list_tables(test_database_url))

        assert _EXPECTED_TABLES.issubset(tables)

    def test_downgrade_removes_all_tables(
        self, clean_postgres: None, test_database_url: str
    ) -> None:
        cfg = _alembic_config(test_database_url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")

        tables = asyncio.run(_list_tables(test_database_url))

        assert _EXPECTED_TABLES.isdisjoint(tables)

    def test_migration_is_reversible_across_multiple_cycles(
        self, clean_postgres: None, test_database_url: str
    ) -> None:
        cfg = _alembic_config(test_database_url)

        for _ in range(3):
            command.upgrade(cfg, "head")
            command.downgrade(cfg, "base")

        # No exception across three full up/down cycles is the acceptance
        # criterion itself; confirm the final state is clean.
        tables = asyncio.run(_list_tables(test_database_url))
        assert _EXPECTED_TABLES.isdisjoint(tables)
