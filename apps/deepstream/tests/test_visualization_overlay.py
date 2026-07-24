"""Tests for overlay.py -- RM-11.SIV visualization subsystem.

Pure Python, SDK-free -- no gi/Gst/pyds/DeepStream dependency, no hardware
needed. This is the highest-coverage unit-test target in the visualization
feature; every color/text decision the OSD renderer makes is exercised
here, not against real GStreamer buffers.
"""

from __future__ import annotations

import pytest

from apps.deepstream.app.config import ColorSchemeSettings, VisualizationSettings
from apps.deepstream.app.visualization.overlay import (
    compose_frame_text,
    compose_object_text,
    parse_color,
    resolve_color,
)


class TestParseColor:
    def test_six_digit_hex_defaults_to_opaque(self) -> None:
        assert parse_color("#FF0000") == (1.0, 0.0, 0.0, 1.0)

    def test_eight_digit_hex_carries_alpha(self) -> None:
        assert parse_color("#00FF0080") == pytest.approx((0.0, 1.0, 0.0, 128 / 255))

    def test_leading_hash_is_optional(self) -> None:
        assert parse_color("0000FF") == (0.0, 0.0, 1.0, 1.0)

    def test_wrong_length_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid color"):
            parse_color("#ABC")


class TestResolveColor:
    def test_known_class_uses_its_configured_color(self) -> None:
        scheme = ColorSchemeSettings(person="#00FF00FF")

        color = resolve_color(
            class_label="person", threat_level=None, color_scheme=scheme, draw_threat=True
        )

        assert color == (0.0, 1.0, 0.0, 1.0)

    def test_unknown_class_falls_back_to_default(self) -> None:
        scheme = ColorSchemeSettings(default="#FFFFFFFF")

        color = resolve_color(
            class_label="unknown_class", threat_level=None, color_scheme=scheme, draw_threat=True
        )

        assert color == (1.0, 1.0, 1.0, 1.0)

    def test_high_threat_overrides_class_color_when_draw_threat_enabled(self) -> None:
        scheme = ColorSchemeSettings(person="#00FF00FF", threat_high="#FF0000FF")

        color = resolve_color(
            class_label="person", threat_level="HIGH", color_scheme=scheme, draw_threat=True
        )

        assert color == (1.0, 0.0, 0.0, 1.0)

    def test_threat_override_suppressed_when_draw_threat_disabled(self) -> None:
        scheme = ColorSchemeSettings(person="#00FF00FF", threat_high="#FF0000FF")

        color = resolve_color(
            class_label="person", threat_level="HIGH", color_scheme=scheme, draw_threat=False
        )

        assert color == (0.0, 1.0, 0.0, 1.0)

    def test_threat_level_with_no_configured_override_falls_back_to_class_color(self) -> None:
        """ALLY/OBSERVE/HUMAN_REVIEW have no color_scheme entry -- must not
        be invented one, just fall through to the class-based color."""
        scheme = ColorSchemeSettings(person="#00FF00FF")

        color = resolve_color(
            class_label="person", threat_level="OBSERVE", color_scheme=scheme, draw_threat=True
        )

        assert color == (0.0, 1.0, 0.0, 1.0)


class TestComposeObjectText:
    def test_all_toggles_off_produces_empty_string(self) -> None:
        settings = VisualizationSettings(
            draw_labels=False,
            draw_tracker=False,
            draw_sgie=False,
            draw_threat=False,
            draw_zone=False,
            draw_distance=False,
        )

        text = compose_object_text(
            class_label="person",
            confidence=0.9,
            track_id=42,
            secondary_label="Civilian",
            zone="zone_1",
            distance_meters=12.3,
            threat_level="HIGH",
            settings=settings,
        )

        assert text == ""

    def test_all_toggles_on_includes_every_line(self) -> None:
        settings = VisualizationSettings()

        text = compose_object_text(
            class_label="person",
            confidence=0.9,
            track_id=42,
            secondary_label="Civilian",
            zone="zone_1",
            distance_meters=12.3,
            threat_level="HIGH",
            settings=settings,
        )

        lines = text.splitlines()
        assert "person (0.90)" in lines
        assert "ID #42" in lines
        assert "Civilian" in lines
        assert "Threat: HIGH" in lines
        assert "Zone: zone_1" in lines
        assert "12.3m" in lines

    def test_missing_optional_fields_omit_their_lines_even_when_toggle_is_on(self) -> None:
        settings = VisualizationSettings()

        text = compose_object_text(
            class_label="person",
            confidence=0.9,
            track_id=None,
            secondary_label=None,
            zone=None,
            distance_meters=None,
            threat_level=None,
            settings=settings,
        )

        assert text == "person (0.90)"

    def test_individual_toggle_off_omits_only_that_line(self) -> None:
        settings = VisualizationSettings(draw_sgie=False)

        text = compose_object_text(
            class_label="person",
            confidence=0.9,
            track_id=42,
            secondary_label="Civilian",
            zone=None,
            distance_meters=None,
            threat_level=None,
            settings=settings,
        )

        assert "Civilian" not in text
        assert "ID #42" in text


class TestComposeFrameText:
    def test_all_toggles_off_produces_empty_string(self) -> None:
        settings = VisualizationSettings(
            draw_camera_name=False,
            draw_timestamp=False,
            draw_fps=False,
            draw_latency=False,
            draw_gpu=False,
            draw_system_status=False,
        )

        text = compose_frame_text(
            camera_name="north-gate-01",
            timestamp="2026-07-23T14:00:00Z",
            fps=24.8,
            latency_ms=4.8,
            gpu_percent=21.0,
            system_status="OK",
            settings=settings,
        )

        assert text == ""

    def test_all_toggles_on_includes_every_line(self) -> None:
        settings = VisualizationSettings(draw_system_status=True)

        text = compose_frame_text(
            camera_name="north-gate-01",
            timestamp="2026-07-23T14:00:00Z",
            fps=24.8,
            latency_ms=4.8,
            gpu_percent=21.0,
            system_status="OK",
            settings=settings,
        )

        lines = text.splitlines()
        assert "north-gate-01" in lines
        assert "2026-07-23T14:00:00Z" in lines
        assert "FPS: 24.8" in lines
        assert "Latency: 4.8ms" in lines
        assert "GPU: 21%" in lines
        assert "OK" in lines

    def test_missing_optional_fields_omit_their_lines(self) -> None:
        settings = VisualizationSettings()

        text = compose_frame_text(
            camera_name="north-gate-01",
            timestamp=None,
            fps=None,
            latency_ms=None,
            gpu_percent=None,
            system_status=None,
            settings=settings,
        )

        assert text == "north-gate-01"
