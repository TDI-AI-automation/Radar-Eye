"""Repository-native domain objects produced by the Runtime Adapter.

Source: ADR-027 (DeepStream Runtime Adapter as Anti-Corruption Layer) --
these are exactly the kind of "repository-native domain objects" ADR-027
names as what may leave the Runtime Adapter boundary (``FrameObservation``,
``DetectionObservation`` are named explicitly). No field here holds a
``pyds``/``Gst`` type -- everything is a plain Python primitive.

Phase 1 scope (RM-11 Phase 1 approval): ``class_id``/``label`` are raw
passthrough values from whatever PGIE model is configured (currently a
placeholder, non-weapon model -- see
``apps/deepstream/configs/pgie_placeholder.txt``). Mapping a real detection
onto ``shared.constants.weapon_types.WeaponType`` is real business logic
that requires an approved weapon-detection model (per MODEL_REGISTRY.md)
and is deliberately not done here yet.

Phase 2 scope (RM-11 Phase 2 design review, Decision B): ``secondary_label``
is the equivalent raw passthrough for SGIE (currently a placeholder,
non-uniform classifier -- see
``apps/deepstream/configs/sgie_placeholder.txt``); ``None`` when SGIE hasn't
run on a detection (e.g. it doesn't match the classifier's
``operate-on-class-ids`` filter). Mapping onto
``shared.constants.uniform_classes.UniformClass`` is likewise deferred
until an approved uniform classifier exists.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BoundingBox:
    """Pixel-space bounding box, top-left origin."""

    left: float
    top: float
    width: float
    height: float


@dataclass(frozen=True)
class DetectionObservation:
    """One detected (and, once NvDCF has run, tracked) object in a frame.

    ``track_id`` is ``None`` until the tracker element has assigned one --
    per DEEPSTREAM_PIPELINE_SPEC.md Stage 3 (detector) vs. Stage 4
    (tracker), a detection can structurally exist without a track yet.
    """

    class_id: int
    label: str
    confidence: float
    bbox: BoundingBox
    track_id: int | None
    secondary_label: str | None = None
    """Raw SGIE classifier output label, if SGIE ran on this detection
    (Phase 2). ``None`` if SGIE hasn't processed it yet or doesn't apply."""


@dataclass(frozen=True)
class FrameObservation:
    """One processed frame's full detection/tracking result for one camera.

    ``ingress_timestamp`` is captured as early as possible (streammux input)
    and ``metadata_timestamp`` once parsing completes -- the RM-11 Phase 1
    approval's "end-to-end latency (frame ingress -> metadata available)"
    instrumentation requirement is exactly this pair's delta.
    """

    camera_id: uuid.UUID
    frame_num: int
    ingress_timestamp: datetime
    metadata_timestamp: datetime
    detections: tuple[DetectionObservation, ...]


RawDetection = tuple[int, str, float, tuple[float, float, float, float], int | None, str | None]
"""(class_id, label, confidence, (left, top, width, height), track_id,
secondary_label). Plain-primitive intermediate form -- what RuntimeAdapter's
pyds-touching extraction step reduces each ``NvDsObjectMeta`` to, before
construction crosses into this module (which has no pyds/Gst dependency at
all)."""


def build_frame_observation(
    *,
    camera_id: uuid.UUID,
    frame_num: int,
    ingress_timestamp: datetime,
    metadata_timestamp: datetime,
    raw_detections: list[RawDetection],
) -> FrameObservation:
    """Pure construction -- no ``pyds``/``Gst`` involved, fully unit-testable
    without the DeepStream SDK. The one place RuntimeAdapter's extraction
    step hands off to plain domain objects.

    Takes real wall-clock ``datetime`` values directly (callers capture
    these via ``datetime.now(timezone.utc)`` at the relevant moment) --
    latency *measurement* is a separate concern handled with
    ``time.monotonic()`` elsewhere (see ``instrumentation.py``), never
    derived from these fields. Monotonic clocks have no epoch relationship
    to wall-clock time, so treating one as the other silently produces
    meaningless dates.
    """
    detections = tuple(
        DetectionObservation(
            class_id=class_id,
            label=label,
            confidence=confidence,
            bbox=BoundingBox(left=bbox[0], top=bbox[1], width=bbox[2], height=bbox[3]),
            track_id=track_id,
            secondary_label=secondary_label,
        )
        for class_id, label, confidence, bbox, track_id, secondary_label in raw_detections
    )
    return FrameObservation(
        camera_id=camera_id,
        frame_num=frame_num,
        ingress_timestamp=ingress_timestamp,
        metadata_timestamp=metadata_timestamp,
        detections=detections,
    )
