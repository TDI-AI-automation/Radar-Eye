"""Performance instrumentation -- RM-11 Phase 1 approval.

Collects: pipeline startup time, PGIE initialization time, inference FPS,
end-to-end latency (frame ingress -> metadata available, reported as a
rolling average -- see ``_LATENCY_WINDOW_SIZE``'s docstring), GPU
utilization, GPU memory utilization, CPU utilization, system memory
utilization.

"Instrumentation shall be lightweight and must not alter pipeline
behavior" (Phase 1 approval): per-frame recording (``record_frame``) is
pure in-memory arithmetic, no I/O. System-level sampling (GPU via
``nvidia-smi`` subprocess, CPU/memory via ``/proc``) is comparatively
expensive and is therefore never called per-frame -- callers (see
``runtime.py``) invoke ``sample_system_metrics()`` on a slow periodic timer
(``DeepStreamSettings.metrics_sample_interval_seconds``), not from any
GStreamer callback or hot path.

No ``pyds``/``gi`` import here -- this module has no DeepStream dependency
at all, so it is fully unit-testable without the SDK.
"""

from __future__ import annotations

import logging
import subprocess
import time
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_FPS_WINDOW_SIZE = 120
"""Rolling window of recent frame intervals used for the FPS estimate."""

_LATENCY_WINDOW_SIZE = 120
"""Rolling window of recent per-frame latencies used for the reported
end-to-end latency figure.

Source: RM-11 Phase 2 Principal Engineer review's required latency-
instrumentation follow-up. A real-hardware diagnostic
(hash(gst_buffer)/id(gst_buffer) compared against buffer PTS at the
ingress and egress probes) confirmed the buffer-identity correlation
mechanism itself is completely reliable -- 15/15 matches, GStreamer's
zero-copy in-place processing (ADR-005) holds through PGIE/tracker/SGIE as
expected. The actual root cause of the Phase 1 vs. Phase 2 latency
figures looking inconsistent (~25ms vs. ~1.6ms) was this class reporting
only the single most-recently-recorded frame's latency rather than a
representative window: true per-frame latency on this hardware ranges from
~120ms during the first few frames after PLAYING (draining the initial
RTSP/decode queue backlog) down to a stable ~2ms once steady-state
streaming begins -- so a single-sample reading is highly sensitive to
exactly when it happens to be taken. Fixed by windowing latency the same
way FPS was already windowed, rather than changing the (confirmed correct)
correlation mechanism itself."""


@dataclass
class PerformanceSnapshot:
    pipeline_startup_seconds: float | None
    pgie_init_seconds: float | None
    inference_fps: float | None
    end_to_end_latency_ms: float | None
    gpu_utilization_pct: float | None
    gpu_memory_used_mb: float | None
    gpu_memory_total_mb: float | None
    cpu_utilization_pct: float | None
    system_memory_used_pct: float | None
    frames_processed: int
    pgie_is_placeholder: bool


@dataclass
class _ProcStatSample:
    idle: int
    total: int


def _read_gpu_metrics() -> tuple[float, float, float] | None:
    """(utilization_pct, memory_used_mb, memory_total_mb) via nvidia-smi, or
    None if unavailable (e.g. no NVIDIA GPU / driver on this machine)."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        first_line = result.stdout.strip().splitlines()[0]
        util_str, used_str, total_str = (part.strip() for part in first_line.split(","))
        return float(util_str), float(used_str), float(total_str)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _read_proc_stat() -> _ProcStatSample | None:
    """Cumulative (idle, total) CPU jiffies since boot, aggregate across
    cores, from /proc/stat's first line. Two samples are needed to compute
    a percentage -- see ``_cpu_utilization_pct``."""
    try:
        with open("/proc/stat", encoding="ascii") as handle:
            first_line = handle.readline()
        values = [int(x) for x in first_line.split()[1:]]
        idle = values[3] + values[4]  # idle + iowait
        total = sum(values)
        return _ProcStatSample(idle=idle, total=total)
    except (OSError, ValueError, IndexError):
        return None


def _cpu_utilization_pct(previous: _ProcStatSample, current: _ProcStatSample) -> float | None:
    total_delta = current.total - previous.total
    if total_delta <= 0:
        return None
    idle_delta = current.idle - previous.idle
    return max(0.0, min(100.0, 100.0 * (1.0 - idle_delta / total_delta)))


def _read_system_memory_used_pct() -> float | None:
    try:
        values: dict[str, int] = {}
        with open("/proc/meminfo", encoding="ascii") as handle:
            for line in handle:
                key, _, rest = line.partition(":")
                if key in ("MemTotal", "MemAvailable"):
                    values[key] = int(rest.strip().split()[0])
        total = values.get("MemTotal")
        available = values.get("MemAvailable")
        if not total or available is None:
            return None
        return max(0.0, min(100.0, 100.0 * (1.0 - available / total)))
    except (OSError, ValueError, IndexError):
        return None


class PerformanceInstrumentation:
    """Owns every metric named in the RM-11 Phase 1 approval."""

    def __init__(self, *, pgie_is_placeholder: bool) -> None:
        self._pgie_is_placeholder = pgie_is_placeholder
        self._build_started_at: float | None = None
        self._playing_at: float | None = None
        self._pgie_init_seconds: float | None = None
        self._frame_timestamps: deque[float] = deque(maxlen=_FPS_WINDOW_SIZE)
        self._latency_samples_ms: deque[float] = deque(maxlen=_LATENCY_WINDOW_SIZE)
        self._frames_processed = 0

        self._prev_proc_stat: _ProcStatSample | None = None
        self._gpu_utilization_pct: float | None = None
        self._gpu_memory_used_mb: float | None = None
        self._gpu_memory_total_mb: float | None = None
        self._cpu_utilization_pct: float | None = None
        self._system_memory_used_pct: float | None = None

    def mark_pipeline_build_start(self) -> None:
        self._build_started_at = time.monotonic()

    def mark_pipeline_playing(self) -> None:
        self._playing_at = time.monotonic()

    def record_frame(self, *, ingress_seconds: float, metadata_seconds: float) -> None:
        """Called once per processed frame from RuntimeAdapter. Pure
        arithmetic -- safe to call at full inference rate."""
        if self._pgie_init_seconds is None and self._playing_at is not None:
            self._pgie_init_seconds = max(0.0, metadata_seconds - self._playing_at)

        self._frame_timestamps.append(metadata_seconds)
        self._latency_samples_ms.append(max(0.0, (metadata_seconds - ingress_seconds) * 1000.0))
        self._frames_processed += 1

    def sample_system_metrics(self) -> None:
        """Expensive (subprocess + file I/O) -- call on a slow periodic
        timer only, never per-frame."""
        gpu = _read_gpu_metrics()
        if gpu is not None:
            self._gpu_utilization_pct, self._gpu_memory_used_mb, self._gpu_memory_total_mb = gpu

        current_stat = _read_proc_stat()
        if current_stat is not None:
            if self._prev_proc_stat is not None:
                self._cpu_utilization_pct = _cpu_utilization_pct(self._prev_proc_stat, current_stat)
            self._prev_proc_stat = current_stat

        self._system_memory_used_pct = _read_system_memory_used_pct()

    def _inference_fps(self) -> float | None:
        if len(self._frame_timestamps) < 2:
            return None
        span = self._frame_timestamps[-1] - self._frame_timestamps[0]
        if span <= 0:
            return None
        return (len(self._frame_timestamps) - 1) / span

    def _average_latency_ms(self) -> float | None:
        """Rolling average over the last _LATENCY_WINDOW_SIZE frames -- see
        that constant's docstring for why a single most-recent sample is
        not representative."""
        if not self._latency_samples_ms:
            return None
        return sum(self._latency_samples_ms) / len(self._latency_samples_ms)

    def snapshot(self) -> PerformanceSnapshot:
        pipeline_startup_seconds = None
        if self._build_started_at is not None and self._playing_at is not None:
            pipeline_startup_seconds = max(0.0, self._playing_at - self._build_started_at)

        return PerformanceSnapshot(
            pipeline_startup_seconds=pipeline_startup_seconds,
            pgie_init_seconds=self._pgie_init_seconds,
            inference_fps=self._inference_fps(),
            end_to_end_latency_ms=self._average_latency_ms(),
            gpu_utilization_pct=self._gpu_utilization_pct,
            gpu_memory_used_mb=self._gpu_memory_used_mb,
            gpu_memory_total_mb=self._gpu_memory_total_mb,
            cpu_utilization_pct=self._cpu_utilization_pct,
            system_memory_used_pct=self._system_memory_used_pct,
            frames_processed=self._frames_processed,
            pgie_is_placeholder=self._pgie_is_placeholder,
        )
