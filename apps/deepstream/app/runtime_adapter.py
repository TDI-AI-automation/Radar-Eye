"""Runtime Adapter -- the ADR-027 anti-corruption layer.

Source: RM-07/RM-09/RM-10 design notes, which already named this component
("the Threat Engine Runtime Adapter, deferred until RM-11") and the RM-11
design review, which confirmed it belongs here. Full scope (per-frame
Calibration/Threat Engine/Incident/Alarm wiring) is Phase 2 -- see
DEEPSTREAM_PIPELINE_SPEC.md's Implementation Order. Phase 0 owns camera
connection-state transitions and the events DEEPSTREAM_PIPELINE_SPEC.md's
"Failure Handling" section assigns to camera/ingestion failures
(CameraDisconnectedEvent, SystemEvent). Phase 1 adds metadata extraction:
converting PGIE/NvDCF output into ``FrameObservation``/``DetectionObservation``
(see ``observations.py``) -- per ADR-027, this module is the *only* place
in the repository allowed to import ``pyds`` or touch ``NvDsBatchMeta``/
``NvDsFrameMeta``/``NvDsObjectMeta``; nothing DeepStream-specific leaves it.

Async methods (``on_camera_connected``, ``on_frame_observation``, etc.) must
only ever be invoked on the application asyncio loop -- GStreamer callbacks
reach this class exclusively through ``AsyncBridge.schedule()`` (RM-11
design review, Decision A), never directly.

``extract_frame_observations`` is the one deliberate exception: it is a
plain, synchronous, non-async method. GStreamer pad-probe callbacks run on a
GStreamer streaming thread and a buffer's metadata is only guaranteed valid
for the probe's own (synchronous) duration -- deferring extraction into an
async task scheduled for "later" would risk reading metadata after the
buffer has already been recycled. So extraction happens synchronously,
in-probe (still confined to this module, satisfying ADR-027), producing
plain ``FrameObservation`` values *before* anything crosses into the async
world via ``AsyncBridge.schedule(adapter.on_frame_observation(...))``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from apps.deepstream.app.heartbeat_registry import HeartbeatRegistry
from apps.deepstream.app.instrumentation import PerformanceInstrumentation
from apps.deepstream.app.observations import FrameObservation, RawDetection, build_frame_observation
from apps.deepstream.app.pipeline_trace import PipelineTracer
from apps.deepstream.app.stage_logging import get_audit_logger, get_stage_logger
from shared.events.bus import EventBus
from shared.events.payloads import CameraDisconnectedPayload, SystemEventPayload
from shared.events.types import CameraDisconnectedEvent, SystemEvent
from shared.schemas.camera import CameraConnectionStatus

logger = logging.getLogger(__name__)
_camera_logger = get_stage_logger("camera")
_runtime_adapter_logger = get_stage_logger("runtime_adapter")
_audit_logger = get_audit_logger()

_SOURCE_COMPONENT = "deepstream"
_DEFAULT_STATUS: CameraConnectionStatus = "DISCONNECTED"
_OBSERVATION_LOG_INTERVAL = 150
"""Log one summary line per this many frame observations -- avoids
per-frame log spam at inference frame rate while still surfacing progress."""


class RuntimeAdapter:
    """Bridges DeepStream pipeline lifecycle events onto the internal event
    bus and tracks per-camera connection status for the heartbeat scheduler."""

    def __init__(
        self,
        bus: EventBus,
        *,
        instrumentation: PerformanceInstrumentation | None = None,
        heartbeat: HeartbeatRegistry | None = None,
        tracer: PipelineTracer | None = None,
    ) -> None:
        self._bus = bus
        self._instrumentation = instrumentation
        self._heartbeat = heartbeat
        """RM-11.SIV Unified Heartbeat -- optional, see threat_runtime_adapter.py's
        identical pattern."""
        self._tracer = tracer or PipelineTracer(enabled=False)
        self._status: dict[uuid.UUID, CameraConnectionStatus] = {}
        self._observation_count = 0
        self.last_observation: FrameObservation | None = None
        """Most recently processed frame observation -- exposed for tests
        and manual inspection; not otherwise consumed in Phase 1 (no
        downstream service integration yet -- see Phase 1's Out of Scope)."""

    def _beat(self, component: str, *, reason: str | None = None) -> None:
        if self._heartbeat is not None:
            self._heartbeat.beat(component, reason=reason)

    def status_for(self, camera_id: uuid.UUID) -> CameraConnectionStatus:
        """Synchronous, non-blocking read -- safe for HeartbeatScheduler's
        status_provider (called from the asyncio loop, same as everything
        else here; no cross-thread access)."""
        return self._status.get(camera_id, _DEFAULT_STATUS)

    async def on_camera_connected(self, camera_id: uuid.UUID) -> None:
        self._status[camera_id] = "CONNECTED"
        self._beat("camera")
        _camera_logger.info("Camera %s connected", camera_id)
        _audit_logger.info("Camera Connected: camera=%s", camera_id)
        await self._bus.publish(
            SystemEvent(
                event_type="SystemEvent",
                source=_SOURCE_COMPONENT,
                payload=SystemEventPayload(
                    severity="INFO",
                    source_component=_SOURCE_COMPONENT,
                    message=f"Camera {camera_id} connected",
                ),
            )
        )

    async def on_camera_reconnecting(self, camera_id: uuid.UUID) -> None:
        self._status[camera_id] = "RECONNECTING"

    async def on_camera_disconnected(self, camera_id: uuid.UUID, reason: str) -> None:
        """DEEPSTREAM_PIPELINE_SPEC.md 'Failure Handling' -> 'Camera Failure':
        generate CameraDisconnectedEvent."""
        self._status[camera_id] = "DISCONNECTED"
        _camera_logger.warning("Camera %s disconnected: %s", camera_id, reason)
        _audit_logger.warning("Camera Disconnected: camera=%s reason=%s", camera_id, reason)
        await self._bus.publish(
            CameraDisconnectedEvent(
                event_type="CameraDisconnectedEvent",
                source=_SOURCE_COMPONENT,
                payload=CameraDisconnectedPayload(camera_id=camera_id, reason=reason),
            )
        )

    async def on_pipeline_error(
        self, message: str, *, severity: Literal["ERROR", "CRITICAL"] = "ERROR"
    ) -> None:
        """Generic infrastructure failure not tied to one camera (e.g. a
        pipeline-level GStreamer error). Component-specific failures (model,
        calibration -- DEEPSTREAM_PIPELINE_SPEC.md's 'Failure Handling')
        arrive in Phase 1/2 once those stages exist."""
        get_stage_logger("system").error("DeepStream pipeline error: %s", message)
        await self._bus.publish(
            SystemEvent(
                event_type="SystemEvent",
                source=_SOURCE_COMPONENT,
                payload=SystemEventPayload(
                    severity=severity,
                    source_component=_SOURCE_COMPONENT,
                    message=message,
                ),
            )
        )

    # -- Phase 1: metadata extraction (the ADR-027 boundary) -----------------

    def extract_frame_observations(
        self,
        gst_buffer: Any,
        *,
        camera_id_for_pad_index: dict[int, uuid.UUID],
        ingress_timestamp: datetime,
    ) -> list[FrameObservation]:
        """Parse ``NvDsBatchMeta`` off ``gst_buffer`` into plain
        ``FrameObservation`` values -- one per frame in the batch whose
        ``pad_index`` maps to a known camera.

        ``ingress_timestamp`` is a real wall-clock value the caller captured
        at the pipeline's ingress point; ``metadata_timestamp`` is captured
        here, now, the same way. Latency *measurement* (which needs a
        monotonic clock, not wall-clock) is a separate concern handled by
        the caller via ``PerformanceInstrumentation`` -- see ``runtime.py``.

        Synchronous and the only method in the repository that imports
        ``pyds`` (ADR-027). Must be called from the same GStreamer streaming
        thread that owns ``gst_buffer``, before the pad probe that invoked it
        returns -- see the module docstring for why this cannot be deferred
        onto the asyncio loop.
        """
        import pyds  # noqa: PLC0415 -- deferred: provided by the DeepStream SDK, not pip

        batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
        if batch_meta is None:
            return []

        metadata_timestamp = datetime.now(timezone.utc)
        observations: list[FrameObservation] = []
        l_frame = batch_meta.frame_meta_list
        while l_frame is not None:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
            camera_id = camera_id_for_pad_index.get(frame_meta.pad_index)
            if camera_id is not None:
                observation = build_frame_observation(
                    camera_id=camera_id,
                    frame_num=frame_meta.frame_num,
                    ingress_timestamp=ingress_timestamp,
                    metadata_timestamp=metadata_timestamp,
                    raw_detections=self._extract_raw_detections(frame_meta),
                )
                observations.append(observation)
                if self._tracer.enabled:
                    self._trace_observation(observation)
            l_frame = l_frame.next
        return observations

    def _trace_observation(self, observation: FrameObservation) -> None:
        """RM-11.SIV frame trace -- only called when tracer.enabled is
        already True (see the call site), so this method's own cost never
        applies to the default (disabled) path."""
        correlation_id = self._tracer.frame_id(observation.camera_id, observation.frame_num)
        self._tracer.frame_received(correlation_id)
        for detection in observation.detections:
            self._tracer.object_detected(
                correlation_id,
                class_label=detection.label,
                confidence=detection.confidence,
                bbox=detection.bbox,
            )
            if detection.track_id is not None:
                self._tracer.track_updated(correlation_id, track_id=detection.track_id)
            if detection.secondary_label is not None:
                self._tracer.secondary_classification(
                    correlation_id, label=detection.secondary_label
                )
        self._tracer.frame_observation_created(
            correlation_id, detection_count=len(observation.detections)
        )

    @staticmethod
    def _extract_raw_detections(frame_meta: Any) -> list[RawDetection]:
        """The only place ``NvDsObjectMeta`` fields are actually read.
        Reduces each to a plain-primitive ``RawDetection`` tuple immediately
        -- everything past this point (``build_frame_observation``,
        ``observations.py``) is pure Python with no pyds dependency."""
        import pyds  # noqa: PLC0415

        untracked_id = getattr(pyds, "UNTRACKED_OBJECT_ID", None)
        raw: list[RawDetection] = []
        l_obj = frame_meta.obj_meta_list
        while l_obj is not None:
            obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
            rect = obj_meta.rect_params
            track_id = obj_meta.object_id
            raw.append(
                (
                    obj_meta.class_id,
                    obj_meta.obj_label,
                    obj_meta.confidence,
                    (rect.left, rect.top, rect.width, rect.height),
                    None if track_id == untracked_id else int(track_id),
                    RuntimeAdapter._extract_secondary_label(obj_meta),
                )
            )
            l_obj = l_obj.next
        return raw

    @staticmethod
    def _extract_secondary_label(obj_meta: Any) -> str | None:
        """Raw SGIE classifier output (Phase 2), if any -- the first result
        label of the first classifier that ran on this detection. Returns
        ``None`` if SGIE hasn't classified this object (e.g. it doesn't
        match the classifier's ``operate-on-class-ids`` filter)."""
        import pyds  # noqa: PLC0415

        l_classifier = obj_meta.classifier_meta_list
        if l_classifier is None:
            return None
        classifier_meta = pyds.NvDsClassifierMeta.cast(l_classifier.data)
        l_label = classifier_meta.label_info_list
        if l_label is None:
            return None
        label_info = pyds.NvDsLabelInfo.cast(l_label.data)
        return str(label_info.result_label)

    async def on_frame_observation(
        self,
        observation: FrameObservation,
        *,
        ingress_monotonic_seconds: float,
        metadata_monotonic_seconds: float,
    ) -> None:
        """Records the observation for instrumentation. No business events
        are published here -- ThreatAssessmentEvent construction needs
        uniform classification (SGIE) and a distance zone (Calibration),
        both explicitly out of Phase 1's scope (deferred to Phase 2).

        Takes monotonic timing values as explicit separate arguments rather
        than deriving them from ``observation``'s wall-clock timestamp
        fields -- see ``build_frame_observation``'s docstring for why those
        two clocks must never be conflated.
        """
        self.last_observation = observation
        self._observation_count += 1
        self._beat("runtime_adapter")

        if self._instrumentation is not None:
            self._instrumentation.record_frame(
                ingress_seconds=ingress_monotonic_seconds,
                metadata_seconds=metadata_monotonic_seconds,
            )

        if self._observation_count % _OBSERVATION_LOG_INTERVAL == 1:
            _runtime_adapter_logger.info(
                "Frame observation: camera=%s frame_num=%d detections=%d (observation #%d)",
                observation.camera_id,
                observation.frame_num,
                len(observation.detections),
                self._observation_count,
            )
