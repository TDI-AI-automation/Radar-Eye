"""RM-11.SIV validation-only tooling.

Nothing in this package is imported by production orchestration code
(``runtime.py``, ``runtime_adapter.py``, ``threat_runtime_adapter.py``,
``pipeline/builder.py``) -- the dependency runs the other way: this
package's watchdog/dashboard read the shared ``HeartbeatRegistry`` and
``PerformanceInstrumentation`` snapshot that those modules already expose,
plus ``configs/validation.yaml``. See ``apps/deepstream/app/pipeline_trace.py``
(not in this package, since it *is* called from production modules -- an
optional, off-by-default instrumentation hook, same pattern as
``heartbeat_registry.py``).
"""

from __future__ import annotations
