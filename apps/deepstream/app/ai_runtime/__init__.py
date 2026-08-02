"""AI Runtime -- the subsystem that turns DeepStream/pyds metadata into
threat decisions.

RM-12 Camera Runtime Step 6 gave this its own explicit package (a pure
reorganization of RM-11's existing ``runtime_adapter.py``/
``threat_runtime_adapter.py``/``observations.py`` -- no behavior changed):

- ``observations``: the shared, pyds-free data contract between the two
  modules below (``FrameObservation``, ``DetectionObservation``, etc.).
- ``detection``: ``RuntimeAdapter``, the ADR-027 anti-corruption layer --
  the only code in the repository permitted to import ``pyds``/touch
  ``NvDsBatchMeta``. Produces ``observations.FrameObservation`` values.
- ``threat_bridge``: ``ThreatEngineRuntimeAdapter``, which consumes those
  ``FrameObservation`` values and orchestrates Calibration/ThreatEngine/
  Incident/Alarm. Never touches ``pyds``, ``Gst``, or ``GLib``.

Kept as two modules (not merged) because they own genuinely different
responsibilities on either side of the ADR-027 boundary; kept in one
package because that boundary, and the shared ``observations`` contract
crossing it, is easiest to see and preserve when they sit together.

No submodule is re-exported here -- callers import
``apps.deepstream.app.ai_runtime.detection``/``.threat_bridge``/
``.observations`` directly, matching every other subsystem package in
``apps/deepstream/app`` (``ingestion``, ``pipeline``, ``visualization``).
"""
