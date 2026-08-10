"""Camera bootstrap script -- RM-11.SIV Decision A.

Reads ``configs/camera.yaml`` (env-var substituted -- see
``apps/deepstream/app/env_yaml.py``), encrypts the RTSP credentials via
``CredentialEncryptionProvider``, and upserts the ``cameras`` /
``camera_stream_profiles`` database rows that ``CameraRegistry`` loads at
pipeline startup (``apps/deepstream/app/ingestion/camera_registry.py``) --
the exact same production path RM-12's eventual registration API will use.
``DeepStreamRuntime`` never reads ``camera.yaml`` directly (see the RM-11.SIV
design review's Decision A) -- this script is the only thing that does.

Idempotent: re-running with the same ``camera_id`` slug updates the existing
camera's stream profile in place rather than creating a duplicate.

Usage:
    python -m scripts.siv_register_camera [--camera-yaml PATH]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from apps.api.app.config import Settings, get_settings
from apps.api.app.db import create_engine, create_session_factory
from apps.api.app.models.camera import Camera, CameraStreamProfile
from apps.api.app.repositories.camera import CameraRepository, CameraStreamProfileRepository
from apps.api.app.security.encryption import get_credential_encryption_provider
from apps.deepstream.app.camera_yaml import build_rtsp_url, require_keys
from apps.deepstream.app.env_yaml import load_yaml_with_env_substitution

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CAMERA_YAML = REPO_ROOT / "configs" / "camera.yaml"


async def register_camera(camera_yaml_path: Path, settings: Settings | None = None) -> None:
    raw = load_yaml_with_env_substitution(camera_yaml_path)
    require_keys(raw)
    camera_slug = raw["camera_id"]
    rtsp_url = build_rtsp_url(raw)
    transport = raw.get("transport", "tcp")

    settings = settings or get_settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    encryption = get_credential_encryption_provider(settings)

    try:
        async with session_factory() as session:
            camera_repo = CameraRepository(session)
            profile_repo = CameraStreamProfileRepository(session)

            cameras = await camera_repo.list()
            camera = next((c for c in cameras if c.name == camera_slug), None)
            if camera is None:
                camera = await camera_repo.add(
                    Camera(name=camera_slug, location=None, status="DISCONNECTED")
                )
                logger.info("Created new camera %s (%s)", camera.id, camera_slug)
            else:
                logger.info("Reusing existing camera %s (%s)", camera.id, camera_slug)

            encrypted_url = encryption.encrypt(rtsp_url)
            profiles = await profile_repo.list()
            profile = next((p for p in profiles if p.camera_id == camera.id), None)
            if profile is None:
                await profile_repo.add(
                    CameraStreamProfile(
                        camera_id=camera.id,
                        rtsp_url_encrypted=encrypted_url,
                        transport=transport,
                    )
                )
                logger.info("Created new stream profile for camera %s", camera.id)
            else:
                profile.rtsp_url_encrypted = encrypted_url
                profile.transport = transport
                await session.flush()
                logger.info("Updated existing stream profile for camera %s", camera.id)

            await session.commit()
            camera_id = camera.id
    finally:
        await engine.dispose()

    logger.info("Registered camera '%s' (id=%s) for RM-11.SIV", camera_slug, camera_id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera-yaml", type=Path, default=DEFAULT_CAMERA_YAML)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    if not args.camera_yaml.is_file():
        raise SystemExit(
            f"{args.camera_yaml} not found -- copy configs/camera.yaml.example to "
            f"configs/camera.yaml and fill in your camera's details first."
        )
    asyncio.run(register_camera(args.camera_yaml))


if __name__ == "__main__":
    main()
