"""Overlay color/text decision logic -- RM-11.SIV visualization subsystem.

Pure Python: no ``gi``/``Gst``/``pyds``/DeepStream imports anywhere in this
module. Every color and every line of on-screen text is decided here, from
plain inputs, and returned as plain outputs (an RGBA float tuple, a
string) -- ``osd_renderer.py`` calls these functions and writes their
results onto DeepStream's own display-metadata fields; it makes no color
or formatting decisions itself. This split mirrors this codebase's existing
``observations.py`` (pure) vs. ``runtime_adapter.py`` (``pyds``-touching)
pattern.
"""

from __future__ import annotations

from apps.deepstream.app.config import ColorSchemeSettings, VisualizationSettings

_THREAT_LEVEL_COLOR_ATTR = {
    "HIGH": "threat_high",
    "MEDIUM": "threat_medium",
    "LOW": "threat_low",
}
"""Only these three ThreatLevel values have a configured override color
(HIGH=solid red / MEDIUM=yellow / LOW=green, per the visualization
requirement) -- ALLY/OBSERVE/HUMAN_REVIEW fall through to the class-based
color instead of being invented a color that was never asked for."""


def parse_color(hex_color: str) -> tuple[float, float, float, float]:
    """Parse ``"#RRGGBB"`` or ``"#RRGGBBAA"`` into normalized (r, g, b, a)
    floats in [0, 1] -- the format ``NvOSD_ColorParams`` (pyds) expects.
    Alpha defaults to fully opaque (1.0) when only 6 hex digits are given."""
    value = hex_color.lstrip("#")
    if len(value) not in (6, 8):
        raise ValueError(f"invalid color {hex_color!r}: expected #RRGGBB or #RRGGBBAA")
    r = int(value[0:2], 16) / 255.0
    g = int(value[2:4], 16) / 255.0
    b = int(value[4:6], 16) / 255.0
    a = int(value[6:8], 16) / 255.0 if len(value) == 8 else 1.0
    return (r, g, b, a)


def resolve_color(
    *,
    class_label: str,
    threat_level: str | None,
    color_scheme: ColorSchemeSettings,
    draw_threat: bool,
) -> tuple[float, float, float, float]:
    """Base color comes from ``class_label`` (the real PGIE label set --
    fire/metal/ranged_metal/non_metal/person -- falling back to
    ``color_scheme.default`` for anything else). A known threat level
    overrides it when ``draw_threat`` is on, since threat is the
    operationally important signal once available."""
    if draw_threat and threat_level is not None:
        attr = _THREAT_LEVEL_COLOR_ATTR.get(threat_level)
        if attr is not None:
            return parse_color(getattr(color_scheme, attr))
    class_color = getattr(color_scheme, class_label, None) or color_scheme.default
    return parse_color(class_color)


def compose_object_text(
    *,
    class_label: str,
    confidence: float,
    track_id: int | None,
    secondary_label: str | None,
    zone: str | None,
    distance_meters: float | None,
    threat_level: str | None,
    settings: VisualizationSettings,
) -> str:
    """Multi-line per-object overlay text -- one line per concern, each
    independently gated by its own ``draw_*`` toggle."""
    lines: list[str] = []
    if settings.draw_labels:
        lines.append(f"{class_label} ({confidence:.2f})")
    if settings.draw_tracker and track_id is not None:
        lines.append(f"ID #{track_id}")
    if settings.draw_sgie and secondary_label is not None:
        lines.append(secondary_label)
    if settings.draw_threat and threat_level is not None:
        lines.append(f"Threat: {threat_level}")
    if settings.draw_zone and zone is not None:
        lines.append(f"Zone: {zone}")
    if settings.draw_distance and distance_meters is not None:
        lines.append(f"{distance_meters:.1f}m")
    return "\n".join(lines)


def compose_frame_text(
    *,
    camera_name: str | None,
    timestamp: str | None,
    fps: float | None,
    latency_ms: float | None,
    gpu_percent: float | None,
    system_status: str | None,
    settings: VisualizationSettings,
) -> str:
    """Multi-line frame-global overlay text (camera name / timestamp /
    FPS / latency / GPU / system status) -- one line per concern, each
    independently gated by its own ``draw_*`` toggle."""
    lines: list[str] = []
    if settings.draw_camera_name and camera_name is not None:
        lines.append(camera_name)
    if settings.draw_timestamp and timestamp is not None:
        lines.append(timestamp)
    if settings.draw_fps and fps is not None:
        lines.append(f"FPS: {fps:.1f}")
    if settings.draw_latency and latency_ms is not None:
        lines.append(f"Latency: {latency_ms:.1f}ms")
    if settings.draw_gpu and gpu_percent is not None:
        lines.append(f"GPU: {gpu_percent:.0f}%")
    if settings.draw_system_status and system_status is not None:
        lines.append(system_status)
    return "\n".join(lines)
