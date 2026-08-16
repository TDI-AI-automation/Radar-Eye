"""RTSP URL generator -- Camera Management workflow.

An operator picks a brand plus IP/credentials/port/stream; the backend
builds the RTSP URL. The operator never types one -- see
shared.schemas.camera.CameraCreateRequestSchema's docstring. Only the
generated URL is ever stored (encrypted, apps.api.app.security.
encryption.CredentialEncryptionProvider); this module never touches
persistence itself.

Extensibility: every brand supported today builds a URL the same way
(``rtsp://[user:pass@]ip:port/path``), just with a different default port
and stream path, so one concrete ``RtspUrlAdapter`` is instantiated once
per brand rather than five near-identical subclasses pretending to differ.
``build()`` is still a method, not a bare function, specifically so a
future brand whose URL scheme genuinely differs (e.g. query-string auth
instead of userinfo) can subclass ``RtspUrlAdapter`` and override it --
adding that one adapter and one ``_ADAPTERS`` entry, without touching any
caller of ``generate_rtsp_url()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from shared.schemas.camera import CameraBrand


@dataclass
class RtspUrlAdapter:
    label: str
    default_port: int
    default_stream_path: str

    def build(
        self,
        *,
        ip_address: str,
        port: int,
        username: str | None,
        password: str | None,
        stream_path: str,
    ) -> str:
        auth = ""
        if username and password:
            auth = f"{quote(username, safe='')}:{quote(password, safe='')}@"
        path = stream_path if stream_path.startswith("/") else f"/{stream_path}"
        return f"rtsp://{auth}{ip_address}:{port}{path}"


_ADAPTERS: dict[CameraBrand, RtspUrlAdapter] = {
    "HIKVISION": RtspUrlAdapter("Hikvision", 554, "/Streaming/Channels/101"),
    "DAHUA": RtspUrlAdapter("Dahua", 554, "/cam/realmonitor?channel=1&subtype=0"),
    "UNIVIEW": RtspUrlAdapter("Uniview", 554, "/media/video1"),
    "AXIS": RtspUrlAdapter("Axis", 554, "/axis-media/media.amp"),
    "HANWHA": RtspUrlAdapter("Hanwha", 554, "/profile2/media.smp"),
}
"""The standard/default RTSP path convention documented by each brand --
not verified against every model/firmware revision (this machine has no
Dahua/Uniview/Axis/Hanwha hardware to validate against, unlike the
Hikvision path, which matches configs/camera.yaml's real, hardware-tested
value). ``port``/``stream_path`` stay operator-editable per camera
specifically so a firmware that differs from the default isn't a dead
end."""


def supported_brands() -> list[CameraBrand]:
    return list(_ADAPTERS.keys())


def brand_label(brand: CameraBrand) -> str:
    return _ADAPTERS[brand].label


def default_port_for_brand(brand: CameraBrand) -> int:
    return _ADAPTERS[brand].default_port


def default_stream_path_for_brand(brand: CameraBrand) -> str:
    return _ADAPTERS[brand].default_stream_path


def generate_rtsp_url(
    *,
    brand: CameraBrand,
    ip_address: str,
    port: int | None = None,
    username: str | None = None,
    password: str | None = None,
    stream_path: str | None = None,
) -> str:
    """Builds the RTSP URL for one camera. ``port``/``stream_path``
    fall back to the brand's own default when not given -- the only two
    fields ``CameraCreateRequestSchema ``/``CameraUpdateRequestSchema``
    let an operator omit."""
    adapter = _ADAPTERS[brand]
    return adapter.build(
        ip_address=ip_address,
        port=port if port is not None else adapter.default_port,
        username=username,
        password=password,
        stream_path=stream_path if stream_path else adapter.default_stream_path,
    )
