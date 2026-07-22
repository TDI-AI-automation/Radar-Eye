"""Frame-level pipeline trace -- RM-11.SIV "Pipeline Trace" requirement.

Traces one physical frame's complete execution through every stage
(FRAME RECEIVED -> OBJECT DETECTED -> TRACK UPDATED -> SECONDARY
CLASSIFICATION -> FRAME OBSERVATION CREATED -> CALIBRATION RESULT ->
THREAT ASSESSMENT -> INCIDENT CREATED -> ALARM GENERATED -> EVENT
PUBLISHED), not isolated per-subsystem diagnostics -- that's what the
``radar_eye.stage.*`` loggers (``stage_logging.py``) are for. Named
``pipeline_trace.py`` rather than ``stage_trace.py`` for exactly that
reason (RM-11.SIV approval, "PIPELINE TRACE" section).

Controlled entirely by ``configs/validation.yaml``'s ``frame_trace.enabled``
(default ``False``). Every ``PipelineTracer`` method starts with a single
boolean check before doing any work -- when disabled, tracing a frame costs
one attribute read, not a string format or a log call, so it is safe to
call at full inference frame rate from either the GStreamer streaming
thread (``RuntimeAdapter.extract_frame_observations``) or the asyncio loop
(``ThreatEngineRuntimeAdapter``). Call sites additionally guard with
``if tracer.enabled:`` before building any arguments (e.g. formatting a
bounding box), so the disabled path never even constructs the call.
"""

from __future__ import annotations

import logging
import uuid

TRACE_LOGGER_NAME = "radar_eye.trace"


def get_trace_logger() -> logging.Logger:
    return logging.getLogger(TRACE_LOGGER_NAME)


class PipelineTracer:
    def __init__(self, *, enabled: bool) -> None:
        self._enabled = enabled
        self._logger = get_trace_logger()
        if enabled:
            self._logger.setLevel(logging.DEBUG)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @staticmethod
    def frame_id(camera_id: uuid.UUID, frame_num: int) -> str:
        return f"{camera_id}:{frame_num}"

    @staticmethod
    def track_id_key(camera_id: uuid.UUID, track_id: int) -> str:
        """Correlation id for stages reached after a frame's own identity
        is no longer directly at hand (e.g. incident/alarm, which act on an
        EscalationSignal keyed by track, not frame_num)."""
        return f"{camera_id}:track={track_id}"

    def _emit(self, correlation_id: str, stage: str, detail: str = "") -> None:
        if not self._enabled:
            return
        if detail:
            self._logger.debug("[%s] %s %s", correlation_id, stage, detail)
        else:
            self._logger.debug("[%s] %s", correlation_id, stage)

    def frame_received(self, correlation_id: str) -> None:
        self._emit(correlation_id, "FRAME RECEIVED")

    def object_detected(
        self, correlation_id: str, *, class_label: str, confidence: float, bbox: object
    ) -> None:
        self._emit(
            correlation_id,
            "OBJECT DETECTED",
            f"class={class_label} conf={confidence:.2f} bbox={bbox}",
        )

    def track_updated(self, correlation_id: str, *, track_id: int) -> None:
        self._emit(correlation_id, "TRACK UPDATED", f"track_id={track_id}")

    def secondary_classification(self, correlation_id: str, *, label: str) -> None:
        self._emit(correlation_id, "SECONDARY CLASSIFICATION", f"label={label}")

    def frame_observation_created(self, correlation_id: str, *, detection_count: int) -> None:
        self._emit(correlation_id, "FRAME OBSERVATION CREATED", f"detections={detection_count}")

    def calibration_result(self, correlation_id: str, *, zone: str, distance_meters: float) -> None:
        self._emit(
            correlation_id, "CALIBRATION RESULT", f"zone={zone} distance={distance_meters:.1f}m"
        )

    def threat_assessment(
        self, correlation_id: str, *, threat_level: str, rule_id: str | None = None
    ) -> None:
        detail = f"level={threat_level}"
        if rule_id:
            detail += f" rule={rule_id}"
        self._emit(correlation_id, "THREAT ASSESSMENT", detail)

    def incident_created(self, correlation_id: str, *, incident_id: uuid.UUID) -> None:
        self._emit(correlation_id, "INCIDENT CREATED", f"incident_id={incident_id}")

    def alarm_generated(self, correlation_id: str) -> None:
        self._emit(correlation_id, "ALARM GENERATED")

    def event_published(self, correlation_id: str, *, event_type: str) -> None:
        self._emit(correlation_id, "EVENT PUBLISHED", event_type)
