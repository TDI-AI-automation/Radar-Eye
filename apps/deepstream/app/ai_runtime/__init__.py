"""AI Runtime -- the subsystem that turns DeepStream/pyds metadata into
``ObservationEvent`` (ADR-029). A pure CV engine: it publishes observations,
never a decision -- no threat, incident, alert, or hardware-action logic
lives here.

- ``observations``: the shared, pyds-free data contract this package
  produces (``FrameObservation``, ``DetectionObservation``, etc.).
- ``detection``: ``RuntimeAdapter``, the ADR-027 anti-corruption layer --
  the only code in the repository permitted to import ``pyds``/touch
  ``NvDsBatchMeta``. Produces ``observations.FrameObservation`` values and
  publishes them as ``ObservationEvent`` on the Event Bus -- AI Runtime's
  only outward product besides AI Streaming.

Per ADR-029, this package has no compile-time dependency on
``services.threat_engine``, ``services.calibration``, or
``services.incident_service`` -- that orchestration (formerly
``ThreatEngineRuntimeAdapter`` in a since-removed ``threat_bridge`` module,
RM-11 Phase 2) has been removed; downstream services consume
``ObservationEvent`` instead.

No submodule is re-exported here -- callers import
``apps.deepstream.app.ai_runtime.detection``/``.observations`` directly,
matching every other subsystem package in ``apps/deepstream/app``
(``ingestion``, ``pipeline``, ``visualization``).
"""
