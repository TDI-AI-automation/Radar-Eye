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
    nvv4l2h264enc -- h264parse -- output tee --+-- queue(leaky) -- fakesink
                                                |     (permanent drain)
                                                +-- queue(leaky) -- rtph264pay
                                                      -- webrtcbin
                                                      (per browser connection)

The output tee (``branch.py``'s ``build()``) exists so the encode chain
always has a live downstream peer, even when no browser is connected --
the chain starts receiving real buffers the moment the camera is added,
long before any browser necessarily connects, and a src pad with no peer
at all fails every push (unlike an inactive input-selector branch, which
discards internally without attempting one); once that happens
repeatedly the streaming thread stops delivering buffers, and linking a
real consumer later does not wake it back up. The drain branch is
permanent and never released; the transport branch (queue onward)
requests/releases its own tee pad per browser connection, so
attaching/detaching a browser never disturbs the drain or the chain
upstream of the tee.

*Every* tee branch gets its own leaky queue immediately downstream,
including the transport branch (``_build_webrtc_transport``'s own
docstring has the hardware-confirmed story) -- not just the drain.
``webrtcbin``'s own internal send path can stall (a dead/unresponsive
browser peer, most commonly an old connection mid-reconnect) without any
error ever reaching this branch; without a queue there, that stall
propagates synchronously back through the tee's own push call into the
*shared* ``sgie_tee`` this tee forks off of, freezing PGIE/tracker/SGIE
for every camera, not just this one's video delivery. The queue makes
that impossible: the tee's push into it always succeeds immediately
(buffer or drop), so nothing downstream of it -- however stuck -- can
ever apply backpressure past that point.

Browser contract (permanent invariant): the browser never knows this is
AI-annotated video specifically -- it only ever receives "Camera Video,"
forever. Frontend-facing terminology never uses "raw," "annotated," or
"AI" (``VideoProvider``'s own status vocabulary is
``connecting``/``playing``/``error``, nothing source-specific). One
``RTCPeerConnection``, one ``RTCRtpTransceiver``, one ``<video>`` element
per camera, built once per browser connection.
"""
