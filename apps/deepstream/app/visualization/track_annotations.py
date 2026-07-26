"""Track-keyed calibration/threat-engine annotations for the visualization
overlay -- RM-11.SIV visualization subsystem.

Bounding box, track ID, PGIE class, confidence, and SGIE classification are
all synchronously available in the annotate probe (already on ``obj_meta``/
``NvDsClassifierMeta`` by the time SGIE has run). Threat level, zone, and
distance are not -- they require ``CalibrationService.estimate()`` (an
async DB call) and ``ThreatEngine.ingest()``, run by
``ThreatEngineRuntimeAdapter`` on the asyncio side. By the time that result
exists, the GStreamer buffer that produced it has likely already left the
pipeline. This registry is the thread-safe hand-off point: written from the
asyncio side once those results exist, read from the GStreamer-thread OSD
probe by ``(camera_id, track_id)``.

Same proven pattern as ``apps/deepstream/app/heartbeat_registry.py``'s
``HeartbeatRegistry``: a ``threading.Lock``-protected private dict, write
side mutates under the lock, read side returns a fresh frozen dataclass
snapshot copied out from under the lock -- never a live reference.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

TrackKey = tuple[uuid.UUID, int]


@dataclass(frozen=True)
class TrackAnnotation:
    """One track's most recently known calibration/threat-engine state."""

    camera_id: uuid.UUID
    track_id: int
    zone: str | None
    distance_meters: float | None
    threat_level: str | None
    rule_id: str | None
    last_updated_monotonic: float


@dataclass
class _TrackState:
    zone: str | None = None
    distance_meters: float | None = None
    threat_level: str | None = None
    rule_id: str | None = None
    last_updated_monotonic: float = field(default_factory=time.monotonic)


class TrackAnnotationRegistry:
    """Thread-safe, TTL-evicting store of per-track overlay annotations.

    ``get()`` treats an entry older than ``ttl_seconds`` as absent (soft
    expiry -- correctness never depends on a background sweep running).
    ``update()`` additionally sweeps the whole dict under the lock on every
    call, evicting expired entries -- since ``update()`` runs once per
    detection per frame on live traffic, this bounds memory to currently
    (or very recently) live tracks without a timer or extra thread.
    """

    def __init__(self, *, ttl_seconds: float) -> None:
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._tracks: dict[TrackKey, _TrackState] = {}

    def update(
        self,
        camera_id: uuid.UUID,
        track_id: int,
        *,
        zone: str | None = None,
        distance_meters: float | None = None,
        threat_level: str | None = None,
        rule_id: str | None = None,
        now: float | None = None,
    ) -> None:
        """Record one unit of new annotation data for a track. Only
        fields passed as not-None are updated -- a caller that only just
        learned ``zone``/``distance_meters`` (calibration resolved, threat
        engine hasn't run yet) doesn't clobber a ``threat_level`` written
        moments earlier for the same track. ``now`` mirrors ``get()``'s
        injectable clock reading -- defaults to the real monotonic clock;
        tests use it to exercise TTL eviction deterministically."""
        now = now if now is not None else time.monotonic()
        with self._lock:
            self._evict_expired_locked(now)
            key = (camera_id, track_id)
            state = self._tracks.setdefault(key, _TrackState())
            if zone is not None:
                state.zone = zone
            if distance_meters is not None:
                state.distance_meters = distance_meters
            if threat_level is not None:
                state.threat_level = threat_level
            if rule_id is not None:
                state.rule_id = rule_id
            state.last_updated_monotonic = now

    def get(
        self, camera_id: uuid.UUID, track_id: int, *, now: float | None = None
    ) -> TrackAnnotation | None:
        """Current annotation for a track, or ``None`` if never recorded or
        stale (older than ``ttl_seconds``) -- absence is correct, honest
        overlay behavior, never a fabricated value."""
        now = now if now is not None else time.monotonic()
        with self._lock:
            state = self._tracks.get((camera_id, track_id))
        if state is None:
            return None
        if now - state.last_updated_monotonic > self._ttl_seconds:
            return None
        return TrackAnnotation(
            camera_id=camera_id,
            track_id=track_id,
            zone=state.zone,
            distance_meters=state.distance_meters,
            threat_level=state.threat_level,
            rule_id=state.rule_id,
            last_updated_monotonic=state.last_updated_monotonic,
        )

    def size(self) -> int:
        with self._lock:
            return len(self._tracks)

    def active_tracks(self, *, now: float | None = None) -> list[TrackKey]:
        now = now if now is not None else time.monotonic()
        with self._lock:
            return [
                key
                for key, state in self._tracks.items()
                if now - state.last_updated_monotonic <= self._ttl_seconds
            ]

    def expired_tracks(self, *, now: float | None = None) -> list[TrackKey]:
        now = now if now is not None else time.monotonic()
        with self._lock:
            return [
                key
                for key, state in self._tracks.items()
                if now - state.last_updated_monotonic > self._ttl_seconds
            ]

    def _evict_expired_locked(self, now: float) -> None:
        """Caller must already hold ``self._lock``."""
        expired = [
            key
            for key, state in self._tracks.items()
            if now - state.last_updated_monotonic > self._ttl_seconds
        ]
        for key in expired:
            del self._tracks[key]
