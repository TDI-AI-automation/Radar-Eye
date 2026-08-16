"""Live Monitoring's permanent video delivery path (HLS, ADR-031).

Single subsystem boundary, mirroring ``visualization/manager.py``'s own
"nothing outside this package touches internal collaborators" rule:
``apps/deepstream/app/runtime.py`` only ever calls ``LiveStreamManager``
(``manager.py``) -- ``add_camera``/``remove_camera``/``start``/``stop``.
There is no signaling, no per-browser-connection state, and no dynamic
GStreamer branch creation/destruction of any kind: each camera's
``CameraHlsBranch`` is built exactly once (when the camera is added) and
torn down exactly once (when it's removed), fully independent of whether
any browser is ever watching.

AI-annotated-only video output (ADR-030, unchanged by ADR-031). This
package taps the AI pipeline's own SGIE tee, encodes what
PGIE/NvDCF/SGIE/OSD already produced, and writes it to disk as an HLS
(HTTP Live Streaming) segment sequence + playlist -- it never decodes a
second time, never re-runs inference, and cannot affect the Inference
Path. There is no raw/non-AI channel: DeepStream is the sole producer of
the one video representation the browser ever receives (see
``docs/DEEPSTREAM_PIPELINE_SPEC.md`` Stage 5.5).

Topology:

    SGIE tee -- queue -- nvvideoconvert -- nvdsosd -- nvvideoconvert --
    nvv4l2h264enc -- h264parse -- hlssink2 (writes segment*.ts + playlist.m3u8)

No output tee, no drain branch, no per-connection sub-branch: unlike the
WebRTC design this replaces (ADR-030 era), there is exactly one
consumer -- ``hlssink2`` -- and it is permanent, so the encode chain
always has a live downstream peer for the branch's entire lifetime with
no dynamic linking ever required. ``hlssink2`` is a plain file sink from
GStreamer's point of view; it has no concept of "a browser connected" at
all.

Browser delivery (ADR-031): ``apps.api`` serves the HLS files
``hlssink2`` writes under ``configs/live_stream.yaml``'s ``output_dir``
directly over authenticated HTTP (``GET /cameras/{camera_id}/hls/...`` --
see ``apps/api/app/routers/cameras.py``). Any number of browsers read the
same files independently; DeepStream is completely unaware of how many
browsers (if any) are watching, and a browser refresh/reconnect/multi-tab
open never reaches this process at all -- it only ever talks to
``apps.api``. If DeepStream crashes, the last-written HLS files simply
stop updating (playback stalls, does not error) until DeepStream
restarts and resumes writing; there is still no product requirement to
view video with no AI running (ADR-030's accepted trade-off, unchanged).

Browser contract (permanent invariant): the browser never knows this is
AI-annotated video specifically -- it only ever receives "Camera Video,"
forever. Frontend-facing terminology never uses "raw," "annotated," or
"AI" (``VideoProvider``'s own status vocabulary is
``connecting``/``playing``/``error``, nothing source-specific).
"""
