"""Live Streaming Service (ADR-028, Phase 2) -- a new, independent
process. Not moved from ``apps/deepstream/app/live_stream/``: built
fresh, importing only ``shared/`` (the Media Distribution Interface's
``build_source_element()``, the generic ``WebRtcBranch``/
``WebRtcSignalingServer``, ``AsyncBridge``, ``ReconnectPolicy``) plus
``apps.api``'s repository layer (the same shared DB-facing surface
every subsystem in this architecture already uses for Desired/Observed
State, not a subsystem-owned import).

Owns: endpoint subscription (which cameras Camera Ingestion currently
publishes, read from ``camera_media_endpoints`` where
``subsystem="ingestion"``), its own local RTSP client per camera
(``build_source_element()`` -- its own ``rtspsrc``/``rtph264depay``/
``h264parse``, never Camera Ingestion's), WebRTC, signaling, peer
connection lifecycle, browser sessions.

Never imports ``apps.ingestion`` or ``apps.deepstream`` -- it does not
know cameras, camera credentials, or the physical RTSP session exist.
It only knows ``MediaEndpoint``: an opaque ``camera_id`` plus a local
address to subscribe to. Camera Ingestion could restart, change its
publish transport, or be replaced entirely, and this package would
never need to change.
"""

from __future__ import annotations
