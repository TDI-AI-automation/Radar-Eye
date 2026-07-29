"""Local dev/test user bootstrap script -- RM-12 has no seed/first-user step
(see docs/IMPLEMENTATION_STATUS.md's RM-12 entry: users are only ever
created via ``PATCH /users/{user_id}``-adjacent admin flows or directly in
the ``users`` table -- nothing creates the *first* one). This script fills
that gap for local development only: it is not part of any approved
architecture document and must never be run against a production database.

Idempotent: re-running with the same ``--username`` updates that user's
password/role in place rather than creating a duplicate (mirrors
``scripts/siv_register_camera.py``'s upsert pattern).

``ensure_test_user()`` below is the non-destructive counterpart run.py
calls on every launcher startup (create-if-missing only, never resets an
existing password/role) -- see its own docstring for why that's a
separate function rather than reusing this module's CLI behavior as-is.

Usage:
    python -m scripts.create_test_user
    python -m scripts.create_test_user --username myuser --password mypass --role operator
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from apps.api.app.config import get_settings
from apps.api.app.db import create_engine, create_session_factory
from apps.api.app.models.user import KNOWN_ROLES, ROLE_ADMIN, User
from apps.api.app.repositories.user import UserRepository
from apps.api.app.security.auth import hash_password

logger = logging.getLogger(__name__)

DEFAULT_USERNAME = "testadmin"
DEFAULT_PASSWORD = "TestPass123!"  # noqa: S105 -- local dev/test credential, not a secret


async def create_test_user(username: str, password: str, role: str) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    try:
        async with session_factory() as session:
            repo = UserRepository(session)
            user = await repo.get_by_username(username)
            if user is None:
                await repo.add(
                    User(username=username, password_hash=hash_password(password), role=role)
                )
                logger.info("Created new user '%s' (role=%s)", username, role)
            else:
                user.password_hash = hash_password(password)
                user.role = role
                await session.flush()
                logger.info("Updated existing user '%s' (role=%s)", username, role)

            await session.commit()
    finally:
        await engine.dispose()

    print(f"username: {username}")
    print(f"password: {password}")
    print(f"role:     {role}")


async def ensure_test_user(
    username: str = DEFAULT_USERNAME, password: str = DEFAULT_PASSWORD, role: str = ROLE_ADMIN
) -> bool:
    """Create-if-missing only -- never touches an existing user's
    password or role. Distinct from ``create_test_user()`` above (which
    is this module's own CLI-facing, explicit-reset convenience,
    documented and unchanged): this is what ``run.py`` calls on every
    startup so a launcher run can never silently invalidate a password an
    operator is already relying on, or reset one they changed by hand.

    Returns ``True`` if the user was created just now, ``False`` if it
    already existed (left untouched either way).
    """
    settings = get_settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            repo = UserRepository(session)
            if await repo.get_by_username(username) is not None:
                return False
            await repo.add(
                User(username=username, password_hash=hash_password(password), role=role)
            )
            await session.commit()
            return True
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--role", default=ROLE_ADMIN, choices=KNOWN_ROLES)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    asyncio.run(create_test_user(args.username, args.password, args.role))


if __name__ == "__main__":
    main()
