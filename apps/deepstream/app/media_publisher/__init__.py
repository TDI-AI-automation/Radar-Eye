"""Media Publisher -- RM-12 Camera Runtime Step 7.

Completes the separation between Tier 1 (raw media) and Tier 2 (AI
annotated media) started by Step 2's Frame Distributor: this package makes
each tier's frame resource genuinely reachable by a registered consumer,
without implementing any transport.

- ``interfaces``: ``Tier1FrameConsumer``/``Tier2FrameConsumer`` -- the
  contracts a real consumer (recording, streaming, preview -- all future
  work) implements.
- ``registry``: ``ConsumerRegistry`` -- thread-safe per-camera consumer
  bookkeeping with failure-isolated dispatch, shared by both tiers.
- ``base``: ``_TieredPublisher`` -- the attach/detach/register/unregister/
  shutdown lifecycle shared by both tiers (every pipeline mutation
  scheduled through ``AsyncBridge.schedule_on_mainloop``, matching Step 3's
  discipline).
- ``tier1``: ``Tier1Publisher`` -- attaches to the per-camera Tier 1 tee's
  already-existing raw branch (Step 2). No pipeline topology change: the
  branch always exists once a camera's source bin does -- Tier1Publisher
  only attaches/detaches a probe on it.
- ``tier2``: ``Tier2Publisher`` -- owns the per-camera branches downstream
  of the shared ``nvstreamdemux`` (this step's own topology addition, see
  ``pipeline/builder.py``), built when a camera is added and torn down when
  it's removed.
- ``media_publisher``: ``MediaPublisher`` -- thin facade owning one
  ``Tier1Publisher`` and one ``Tier2Publisher``, with one unified
  ``shutdown()``.

Publishers are consumers only: nothing here ever calls into Runtime
Supervisor, Desired State synchronization, or Telemetry, and a failing
consumer is isolated (logged, never re-raised into the pipeline) rather
than allowed to affect Camera Runtime.

No submodule is re-exported here -- callers import
``apps.deepstream.app.media_publisher.tier1``/``.tier2``/etc. directly,
matching every other subsystem package in ``apps/deepstream/app``.
"""
