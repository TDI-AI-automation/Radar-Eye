"""configs/camera.yaml parsing helpers shared by scripts/siv_register_camera.py
and scripts/check_rtsp.py -- RM-11.SIV Decision A.

Kept separate from env_yaml.py (generic env-substituted YAML loading, no
camera-specific knowledge) and from siv_register_camera.py (DB-writing,
should not be imported just to build a URL for a read-only connectivity
check).
"""

from __future__ import annotations

REQUIRED_KEYS = ("camera_id", "rtsp_url")


class CameraYamlError(ValueError):
    """configs/camera.yaml is missing a required key."""


def build_rtsp_url(raw: dict) -> str:
    """``camera_stream_profiles.rtsp_url_encrypted`` is the single encrypted
    field ``CameraRegistry`` decrypts and hands straight to ``rtspsrc``'s
    ``location`` property (``ingestion/source.py``) -- there is no separate
    username/password column in the schema. ``rtspsrc`` itself supports
    embedded credentials (``rtsp://user:pass@host/...``), so that is where
    ``camera.yaml``'s ``username``/``password`` actually end up, rather than
    as new, otherwise-unused database columns.

    Raises CameraYamlError naming the missing key if rtsp_url is absent --
    fail fast, same philosophy as ModelConfigResolver's file-existence
    checks (RM-11.SIV Decision C).
    """
    if "rtsp_url" not in raw:
        raise CameraYamlError("configs/camera.yaml: missing required key 'rtsp_url'")
    url = raw["rtsp_url"]
    username = raw.get("username")
    password = raw.get("password")
    if username and password and "@" not in url:
        scheme, _, rest = url.partition("://")
        url = f"{scheme}://{username}:{password}@{rest}"
    return url


def require_keys(raw: dict, *, keys: tuple[str, ...] = REQUIRED_KEYS) -> None:
    missing = [key for key in keys if key not in raw]
    if missing:
        raise CameraYamlError(f"configs/camera.yaml: missing required key(s): {', '.join(missing)}")
