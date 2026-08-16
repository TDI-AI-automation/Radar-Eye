"""Lists cameras registered in the database -- RM-11.SIV operator tooling.

Confirms scripts/siv_register_camera.py actually wrote what the operator
expects, without ever printing decrypted credentials -- the RTSP URL is
shown host/port/path only, with any embedded username:password masked.

Usage:
    python -m scripts.show_registered_cameras
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit, urlunsplit

from apps.api.app.config import Settings, get_settings
from apps.api.app.db import create_engine, create_session_factory
from apps.api.app.repositories.camera import CameraRepository, CameraStreamProfileRepository
from apps.api.app.security.encryption import get_credential_encryption_provider

_COLUMNS = ("camera_id", "name", "status", "transport", "rtsp_host", "created_at")


def _mask_rtsp_url(url: str) -> str:
    """Host/port/path only -- never the decrypted username/password, even
    though this script already had to decrypt to get this far. Operators
    running this to sanity-check a bootstrap should not see credentials
    echoed back into a terminal that might be logged/shared."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<unparseable>"
    netloc = parts.hostname or ""
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


async def show_registered_cameras(settings: Settings | None = None) -> list[dict]:
    settings = settings or get_settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    encryption = get_credential_encryption_provider(settings)

    rows: list[dict] = []
    try:
        async with session_factory() as session:
            camera_repo = CameraRepository(session)
            profile_repo = CameraStreamProfileRepository(session)

            cameras = await camera_repo.list()
            profiles = {p.camera_id: p for p in await profile_repo.list()}

            for camera in cameras:
                profile = profiles.get(camera.id)
                rtsp_host = "<no stream profile>"
                transport = "-"
                if profile is not None:
                    decrypted = encryption.decrypt(profile.rtsp_url_encrypted)
                    rtsp_host = _mask_rtsp_url(decrypted)
                    transport = profile.transport
                rows.append(
                    {
                        "camera_id": str(camera.id),
                        "name": camera.name,
                        "status": camera.status,
                        "transport": transport,
                        "rtsp_host": rtsp_host,
                        "created_at": camera.created_at.isoformat(),
                    }
                )
    finally:
        await engine.dispose()

    return rows


def _print_table(rows: list[dict]) -> None:
    if not rows:
        print("No cameras registered.")
        print("Run: python -m scripts.siv_register_camera")
        return

    widths = {col: max(len(col), *(len(row[col]) for row in rows)) for col in _COLUMNS}
    header = "  ".join(col.ljust(widths[col]) for col in _COLUMNS)
    print(header)
    print("  ".join("-" * widths[col] for col in _COLUMNS))
    for row in rows:
        print("  ".join(row[col].ljust(widths[col]) for col in _COLUMNS))


def main() -> None:
    try:
        rows = asyncio.run(show_registered_cameras())
    except Exception as exc:  # noqa: BLE001 -- operator CLI: report and exit, don't traceback-dump
        raise SystemExit(f"error: could not query the database: {exc}") from exc

    _print_table(rows)


if __name__ == "__main__":
    main()
