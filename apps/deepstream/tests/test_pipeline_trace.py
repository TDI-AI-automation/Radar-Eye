"""Tests for pipeline_trace.py -- RM-11.SIV Pipeline Trace requirement."""

from __future__ import annotations

import logging
import uuid

import pytest

from apps.deepstream.app.pipeline_trace import PipelineTracer, get_trace_logger

_CAMERA = uuid.uuid4()


class TestDisabledIsZeroOverhead:
    def test_no_log_record_emitted_when_disabled(self, caplog: pytest.LogCaptureFixture) -> None:
        tracer = PipelineTracer(enabled=False)
        with caplog.at_level(logging.DEBUG, logger="radar_eye.trace"):
            tracer.frame_received(tracer.frame_id(_CAMERA, 1))
            tracer.object_detected(
                tracer.frame_id(_CAMERA, 1), class_label="weapon", confidence=0.9, bbox="bbox"
            )

        assert caplog.records == []

    def test_enabled_property_reflects_constructor_arg(self) -> None:
        assert PipelineTracer(enabled=False).enabled is False
        assert PipelineTracer(enabled=True).enabled is True


class TestEnabledEmitsExpectedLines:
    def test_frame_received(self, caplog: pytest.LogCaptureFixture) -> None:
        tracer = PipelineTracer(enabled=True)
        with caplog.at_level(logging.DEBUG, logger="radar_eye.trace"):
            tracer.frame_received(tracer.frame_id(_CAMERA, 42))

        assert len(caplog.records) == 1
        message = caplog.records[0].getMessage()
        assert f"{_CAMERA}:42" in message
        assert "FRAME RECEIVED" in message

    def test_object_detected_includes_detail(self, caplog: pytest.LogCaptureFixture) -> None:
        tracer = PipelineTracer(enabled=True)
        with caplog.at_level(logging.DEBUG, logger="radar_eye.trace"):
            tracer.object_detected(
                tracer.frame_id(_CAMERA, 1),
                class_label="weapon",
                confidence=0.873,
                bbox=(1, 2, 3, 4),
            )

        message = caplog.records[0].getMessage()
        assert "OBJECT DETECTED" in message
        assert "class=weapon" in message
        assert "conf=0.87" in message

    def test_incident_created_uses_track_correlation_id(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        tracer = PipelineTracer(enabled=True)
        incident_id = uuid.uuid4()
        with caplog.at_level(logging.DEBUG, logger="radar_eye.trace"):
            tracer.incident_created(tracer.track_id_key(_CAMERA, 7), incident_id=incident_id)

        message = caplog.records[0].getMessage()
        assert f"{_CAMERA}:track=7" in message
        assert "INCIDENT CREATED" in message
        assert str(incident_id) in message

    def test_get_trace_logger_name(self) -> None:
        assert get_trace_logger().name == "radar_eye.trace"
