"""Live Monitoring's permanent video delivery path (WebRTC).

Single subsystem boundary, mirroring ``visualization/manager.py``'s own
"nothing outside this package touches internal collaborators" rule:
``apps/deepstream/app/runtime.py`` only ever calls ``LiveStreamManager``
(``manager.py``) -- ``add_camera``/``remove_camera``/``start``/``stop``/
``handle_offer``.

Live Monitoring architecture reset -- transport-only subsystem. Live
Streaming is a decode-free, encode-free passthrough of the camera's own
original H.264 bitstream: it never decodes, never runs inference, never
draws overlays, never touches analytics. This is what "every media
representation exists exactly once" (``docs/DEEPSTREAM_PIPELINE_SPEC.md``)
means for this subsystem -- the encoded H.264 already produced once by
each camera's shared ``h264parse`` (``pipeline/frame_distributor.py``'s
bitstream tee) is the only thing this package ever forwards; it is never
decoded and re-encoded here.

Stage B topology (current) -- one input, always raw:

    BitstreamPublisher -- appsrc -- input-selector -- rtph264pay -- webrtcbin

The bitstream is delivered via ``BitstreamPublisher``
(``media_publisher/bitstream.py``) -- ``consumer.py``'s
``BitstreamAppsrcBridge`` is the one consumer this feature registers.
``input-selector`` is built with a single input already, so that a future
second (annotated) input can be added later as a purely additive change --
requesting a new sink pad and linking a new upstream branch -- without
ever touching ``rtph264pay``/``webrtcbin``/the peer connection already
negotiated with the browser. That second input, and the runtime-driven
switch between them, is explicitly out of this stage's scope.

Browser contract (permanent invariant): the browser never knows whether
it is receiving raw, AI-annotated, recording, or snapshot media -- it
only ever receives "Camera Video," forever. Source selection is entirely
a backend/transport concern; frontend-facing terminology never uses
"raw," "annotated," "AI," or "recording" (``VideoProvider``'s own status
vocabulary is ``connecting``/``playing``/``error``, nothing
source-specific). One ``RTCPeerConnection``, one ``RTCRtpTransceiver``,
one ``<video>`` element per camera, built once, never rebuilt or
renegotiated for a source switch.
"""
