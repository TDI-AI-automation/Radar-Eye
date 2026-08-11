"""Live Monitoring's permanent video delivery path (WebRTC).

Single subsystem boundary, mirroring ``visualization/manager.py``'s own
"nothing outside this package touches internal collaborators" rule:
``apps/deepstream/app/runtime.py`` only ever calls ``LiveStreamManager``
(``manager.py``) -- ``add_camera``/``remove_camera``/``start``/``stop``/
``handle_offer``.

AI-annotated-only video output (ADR-030). This package taps the AI
pipeline's own SGIE tee, encodes what PGIE/NvDCF/SGIE/OSD already
produced, and delivers it to the browser over WebRTC -- it never decodes
a second time, never re-runs inference, and cannot affect the Inference
Path. There is no raw/non-AI channel: DeepStream is the sole producer of
the one video representation the browser ever receives (see
``docs/DEEPSTREAM_PIPELINE_SPEC.md`` Stage 5.5). Radar Eye has no product
requirement to view camera video independent of AI processing -- if
DeepStream is unavailable, browser video is unavailable, an accepted
trade-off (ADR-030's Consequences).

Topology:

    SGIE tee -- queue -- nvvideoconvert -- nvdsosd -- nvvideoconvert --
    nvv4l2h264enc -- h264parse -- rtph264pay -- webrtcbin

Browser contract (permanent invariant): the browser never knows this is
AI-annotated video specifically -- it only ever receives "Camera Video,"
forever. Frontend-facing terminology never uses "raw," "annotated," or
"AI" (``VideoProvider``'s own status vocabulary is
``connecting``/``playing``/``error``, nothing source-specific). One
``RTCPeerConnection``, one ``RTCRtpTransceiver``, one ``<video>`` element
per camera, built once per browser connection.
"""
