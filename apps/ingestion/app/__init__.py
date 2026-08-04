"""Camera Ingestion Service (ADR-028, Media Architecture Reset).

A platform service, with a hard scope boundary: it owns RTSP session
management, reconnect logic, credential management, transport health,
and stream publishing (via ``shared.media_transport``). Nothing else.

It must never know about AI, inference, tracking, WebRTC, recording, or
archive. Its entire vocabulary is: "I receive video. I distribute
video." Concretely enforced, not just stated: this package has zero
imports of ``apps.deepstream``, zero imports of DeepStream-specific
GStreamer elements (``nvv4l2decoder``/``nvinfer``/``nvtracker``/
``nvstreammux``), and zero imports of anything WebRTC/signaling-related
-- see ``docs/DEEPSTREAM_PIPELINE_SPEC.md`` Stage 1 and
``docs/CAMERA_RUNTIME_LIFECYCLE.md`` for the architecture this
supersedes.

Holds exactly one upstream RTSP connection per camera, ever -- the
physical camera in this deployment has a low concurrent-RTSP-session
tolerance (empirically confirmed), and every other subsystem subscribes
to this service's locally re-published copy instead of opening its own
connection to the camera.

Built and run as a completely new, standalone subsystem, alongside the
existing ``apps.deepstream``-owned ingestion path -- Phase 1 migrates no
existing code and is wired to zero consumers. Consumers (Live Streaming,
Recording, AI Runtime, AI Streaming, Archive, Health) migrate to it one
at a time in later phases, never simultaneously.
"""
