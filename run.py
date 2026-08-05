#!/usr/bin/env python3
"""Radar Eye -- one-command project launcher.

Orchestration only. Reuses the exact startup commands documented in
docs/OPERATOR_RUN_SHEET.md -- ``uvicorn apps.api.app.main:create_app
--factory --reload``, ``python -m apps.deepstream.app.main``,
``bun run dev`` -- unchanged, as subprocesses. Runs no application code
of its own: it starts the same processes an operator would start by hand,
waits for each to report healthy, streams their output, and stops them
in reverse order. Nothing here duplicates or reimplements anything in
apps/api, apps/deepstream, or frontend/ -- see docs/CAMERA_RUNTIME_LIFECYCLE.md
and docs/PRODUCTION_VALIDATION_MODE.md for what those processes actually
do internally.

Usage:
    python run.py
    python run.py --validation
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
VENV_PYTHON = REPO_ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python3")
VALIDATION_CONFIG_PATH = REPO_ROOT / "configs" / "validation.yaml"
ENV_FILE_PATH = REPO_ROOT / ".env"

API_HOST = "127.0.0.1"
API_PORT = 8000
API_HEALTH_URL = f"http://{API_HOST}:{API_PORT}/health/system"
API_DOCS_URL = f"http://{API_HOST}:{API_PORT}/docs"
FRONTEND_DEFAULT_PORT = 8080
# Must match configs/ingestion.yaml's `publish_rtsp_port:` -- Camera
# Ingestion Service's Media Distribution Interface (Phase 1 = RTSP)
# binds this fixed TCP port on every start (ADR-028, Media Architecture
# Reset). Standalone in this phase -- no consumer is wired to it yet,
# but it's launched/health-checked alongside everything else so it can
# be verified independently.
INGESTION_PORT = 8600
# Must match configs/live_stream.yaml's `port:` -- DeepStream Runtime's Live
# Monitoring signaling server binds this fixed TCP port on every start
# (added by Stage C; run.py has no app-code import to read it from the
# config file directly, matching every other constant on this page).
LIVE_STREAM_PORT = 8590
# Must match configs/live_streaming.yaml's `signaling_port:` -- the new,
# independent Live Streaming Service (ADR-028, Phase 2). Deliberately a
# different port from LIVE_STREAM_PORT above: that one still belongs to
# the old, unmigrated apps.deepstream.app.live_stream package during
# this build-alongside-then-cutover period; apps.api's WebRTC proxy has
# not yet been repointed at this new service.
LIVE_STREAMING_PORT = 8591

_RESET = "\033[0m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_BOLD = "\033[1m"


def _c(text: str, color: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{color}{text}{_RESET}"


def _pass(msg: str) -> str:
    return _c(f"[PASS] {msg}", _GREEN)


def _fail(msg: str) -> str:
    return _c(f"[FAIL] {msg}", _RED)


def _warn(msg: str) -> str:
    return _c(f"[WARN] {msg}", _YELLOW)


# ---------------------------------------------------------------------------
# Re-exec into .venv's interpreter if not already running under it -- so
# "python run.py" works with any system Python, no manual "source
# .venv/bin/activate" step required. Must happen before any third-party
# import (this module itself only ever imports the standard library, so it
# can always run under the bare system interpreter up to this point).
# ---------------------------------------------------------------------------
def _ensure_running_in_venv() -> None:
    if not VENV_PYTHON.exists():
        return  # reported as a prerequisite failure below, not here
    try:
        same = Path(sys.executable).resolve() == VENV_PYTHON.resolve()
    except OSError:
        same = False
    if same:
        return
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])


_ensure_running_in_venv()


# ---------------------------------------------------------------------------
# Prerequisite checks -- read-only, never modify anything. Each returns
# (passed, detail). A check whose ``required`` is False is reported but
# does not block startup.
# ---------------------------------------------------------------------------
@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    required: bool = True


def _check_python() -> Check:
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 10)
    return Check("Python", ok, f"{sys.version.split()[0]} at {sys.executable}")


def _check_venv() -> Check:
    if not VENV_PYTHON.exists():
        return Check(
            "Virtual environment", False, f"{VENV_PYTHON} not found -- run: python3 -m venv .venv"
        )
    try:
        running_in_venv = Path(sys.executable).resolve() == VENV_PYTHON.resolve()
    except OSError:
        running_in_venv = False
    return Check("Virtual environment", running_in_venv, str(VENV_PYTHON.parent.parent))


def _check_dependencies() -> Check:
    import importlib.util

    required_modules = ["fastapi", "uvicorn", "sqlalchemy", "alembic", "yaml", "asyncpg", "jwt"]
    missing = [m for m in required_modules if importlib.util.find_spec(m) is None]
    if missing:
        return Check(
            "Python dependencies",
            False,
            f"missing: {', '.join(missing)} -- "
            "run: pip install -r requirements.txt -r requirements-dev.txt",
        )
    return Check("Python dependencies", True, f"{len(required_modules)} core packages importable")


def _check_docker() -> Check:
    path = shutil.which("docker")
    detail = (
        f"found at {path}"
        if path
        else "not found -- not used by this project "
        "(PostgreSQL is an unmanaged, pre-existing service)"
    )
    return Check("Docker", True, detail, required=False)


def _check_env_file() -> Check:
    if not ENV_FILE_PATH.exists():
        return Check(
            ".env",
            False,
            f"{ENV_FILE_PATH} missing -- copy .env.example to .env and fill in real values",
        )
    required_keys = [
        "RADAR_EYE_DB_USER",
        "RADAR_EYE_DB_PASSWORD",
        "RADAR_EYE_ENCRYPTION_KEY",
        "RADAR_EYE_JWT_SECRET",
    ]
    values: dict[str, str] = {}
    for line in ENV_FILE_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    missing = [k for k in required_keys if not values.get(k)]
    if missing:
        return Check(".env", False, f"missing/empty: {', '.join(missing)}")
    return Check(".env", True, str(ENV_FILE_PATH))


def _check_configuration() -> Check:
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from apps.api.app.config import get_settings as get_api_settings

        settings = get_api_settings()
        return Check(
            "Configuration",
            True,
            f"database={settings.database.host}:{settings.database.port}/{settings.database.name}",
        )
    except Exception as exc:  # noqa: BLE001 -- surfaced as a FAIL detail, not a crash
        return Check("Configuration", False, f"{type(exc).__name__}: {exc}")


def _check_postgresql() -> Check:
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from apps.api.app.config import get_settings as get_api_settings

        settings = get_api_settings()
        host, port = settings.database.host, settings.database.port
    except Exception:
        host, port = "localhost", 5432
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return Check("PostgreSQL", True, f"reachable at {host}:{port}")
    except OSError as exc:
        return Check("PostgreSQL", False, f"cannot reach {host}:{port} ({exc})")


def _check_node_bun() -> Check:
    bun_path = shutil.which("bun")
    if bun_path:
        return Check("Node/Bun", True, f"bun at {bun_path}")
    node_path = shutil.which("node")
    if node_path:
        return Check(
            "Node/Bun",
            False,
            f"node found at {node_path}, but frontend/bun.lock requires bun -- "
            "install from https://bun.sh",
        )
    return Check("Node/Bun", False, "neither bun nor node found on PATH")


def _check_nvidia_environment() -> Check:
    if shutil.which("nvidia-smi") is None:
        return Check(
            "NVIDIA environment", False, "nvidia-smi not found -- required for DeepStream Runtime"
        )
    try:
        subprocess.run(["nvidia-smi"], capture_output=True, timeout=10, check=True)
    except Exception as exc:  # noqa: BLE001
        return Check("NVIDIA environment", False, f"nvidia-smi failed: {exc}")
    try:
        sys.path.insert(0, str(REPO_ROOT))
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        Gst.init(None)
        missing_plugins = [
            name
            for name in ("nvstreammux", "nvinfer", "nvtracker", "nvstreamdemux")
            if Gst.ElementFactory.find(name) is None
        ]
        if missing_plugins:
            return Check(
                "NVIDIA environment",
                False,
                f"GStreamer plugins missing: {', '.join(missing_plugins)}",
            )
    except Exception as exc:  # noqa: BLE001
        return Check("NVIDIA environment", False, f"gi/GStreamer bindings unavailable: {exc}")
    return Check(
        "NVIDIA environment",
        True,
        "nvidia-smi, gi/Gst, and DeepStream GStreamer plugins all present",
    )


def _check_models() -> Check:
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from apps.deepstream.app.config import get_models_settings

        models = get_models_settings()
    except Exception as exc:  # noqa: BLE001
        return Check(
            "Required models", False, f"could not load configs/models.yaml: {exc}", required=False
        )

    missing = []
    for stage_name, stage in (("pgie", models.pgie), ("sgie", models.sgie)):
        if stage.enabled and not Path(stage.model_file).is_file():
            missing.append(f"{stage_name}: {stage.model_file}")
    if missing:
        return Check(
            "Required models",
            False,
            "not found on disk: "
            + "; ".join(missing)
            + " (or set enabled: false in configs/models.yaml to use placeholders)",
        )
    placeholder = not models.pgie.enabled and not models.sgie.enabled
    return Check(
        "Required models",
        True,
        "using placeholder models" if placeholder else "real model files present",
    )


def _own_service_sigs(port: int) -> tuple[str, ...]:
    """Return the command-line substrings that identify *our* process on *port*."""
    if port == API_PORT:
        return ("uvicorn", "apps.api")
    if port == LIVE_STREAM_PORT:
        return ("apps.deepstream",)
    if port == INGESTION_PORT:
        return ("apps.ingestion",)
    if port == LIVE_STREAMING_PORT:
        return ("apps.live_stream",)
    return ("bun", "vite", "node")


def _is_own_service_on_port(port: int) -> bool:
    """Return True if *port* is bound by one of our own expected service processes."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        if s.connect_ex(("127.0.0.1", port)) != 0:
            return False  # port is free
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        pids = result.stdout.strip().split()
    except Exception:
        return False
    own_sigs = _own_service_sigs(port)
    for pid in pids:
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                cmd = fh.read().replace(b"\x00", b" ").decode(errors="replace")
            if any(sig in cmd for sig in own_sigs):
                return True
        except OSError:
            pass
    return False


def _check_port(port: int, label: str) -> Check:
    """Check whether *port* is free.

    If the port is already bound, try to identify the owner:
    - If it looks like our own service (uvicorn for the API port, bun/node/vite
      for the frontend port), emit a [WARN] so the operator knows the app is
      already running, but do not block re-launch.
    - If it is held by an unrecognised process, hard-fail so the operator knows
      something unexpected is occupying the port before we try to bind.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        in_use = s.connect_ex(("127.0.0.1", port)) == 0
    if not in_use:
        return Check(f"Port {port} ({label})", True, "free")

    if _is_own_service_on_port(port):
        return Check(
            f"Port {port} ({label})",
            False,
            "already in use by our own service (app is running) -- "
            "stop it first if you want to restart",
            required=False,  # downgrade: warn, not fail
        )

    return Check(
        f"Port {port} ({label})",
        False,
        "already in use -- another process is bound here. Find it with: "
        f"lsof -i :{port}  (or) pgrep -af 'uvicorn|vite dev'",
    )


def run_prerequisite_checks() -> list[Check]:
    return [
        _check_python(),
        _check_venv(),
        _check_dependencies(),
        _check_docker(),
        _check_env_file(),
        _check_configuration(),
        _check_postgresql(),
        _check_node_bun(),
        _check_nvidia_environment(),
        _check_models(),
        _check_port(API_PORT, "Backend API"),
        _check_port(FRONTEND_DEFAULT_PORT, "Frontend"),
        _check_port(LIVE_STREAM_PORT, "Live Monitoring signaling"),
        _check_port(INGESTION_PORT, "Camera Ingestion media distribution"),
        _check_port(LIVE_STREAMING_PORT, "Live Streaming Service signaling"),
    ]


def print_checks(checks: list[Check]) -> bool:
    print(_c("Prerequisite checks", _BOLD))
    print("-" * 60)
    all_required_passed = True
    for check in checks:
        line = (
            _pass(f"{check.name} -- {check.detail}")
            if check.passed
            else (
                _fail(f"{check.name} -- {check.detail}")
                if check.required
                else _warn(f"{check.name} -- {check.detail}")
            )
        )
        print(line)
        if check.required and not check.passed:
            all_required_passed = False
    print("-" * 60)
    return all_required_passed


# ---------------------------------------------------------------------------
# Environment preparation -- the only phase allowed to change state
# (run migrations). Dependency installation is deliberately NOT automatic
# here -- a missing dependency is reported by the prerequisite check above
# with the exact command to fix it, rather than this script silently
# modifying the interpreter's installed packages.
# ---------------------------------------------------------------------------
def run_migrations() -> bool:
    print(_c("Running database migrations...", _BOLD))
    env = os.environ.copy()
    result = subprocess.run(
        [str(VENV_PYTHON), "-m", "alembic", "-c", "apps/api/alembic.ini", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env,
    )
    if result.returncode != 0:
        print(_fail("Database migration failed"))
        return False
    print(_pass("Database migrations up to date"))
    return True


def load_dotenv_into_environ() -> None:
    if not ENV_FILE_PATH.exists():
        return
    for line in ENV_FILE_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def ensure_development_administrator() -> bool:
    """Guarantees the dev admin login used throughout local
    validation exists, without ever touching it if it's already there.

    Root cause this exists for: this account is a database row, not
    application state -- it does not survive a database reset (this
    environment's PostgreSQL data has been observed not to persist
    across sandbox resets during development), and nothing previously
    re-created it automatically after one. Reuses
    scripts.create_test_user.ensure_test_user() (create-if-missing only)
    rather than create_test_user() (that one's CLI-facing, deliberately
    overwrites on every re-run -- wrong semantics for something the
    launcher calls unattended on every startup).
    """
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.create_test_user import DEFAULT_PASSWORD, DEFAULT_USERNAME, ensure_test_user

    try:
        created = asyncio.run(ensure_test_user(DEFAULT_USERNAME, DEFAULT_PASSWORD))
    except Exception as exc:  # noqa: BLE001 -- reported, not fatal to the rest of startup
        print(_warn(f"Could not verify development administrator: {exc}"))
        return False
    if created:
        print(_pass(f"Development administrator created (username={DEFAULT_USERNAME})"))
    else:
        print(_pass("Development administrator verified"))
    return True


# ---------------------------------------------------------------------------
# Validation Mode -- temporarily flips configs/validation.yaml's
# production_validation_mode.enabled to true before starting DeepStream,
# and always restores the original file content on shutdown (including on
# crash/Ctrl+C). Never edits application code -- see
# docs/PRODUCTION_VALIDATION_MODE.md for what the flag itself does.
# ---------------------------------------------------------------------------
class ValidationModeToggle:
    def __init__(self) -> None:
        self._original_text: str | None = None

    def enable(self) -> None:
        text = VALIDATION_CONFIG_PATH.read_text()
        self._original_text = text
        if re.search(r"production_validation_mode:\n  enabled: true", text):
            # Already enabled -- a legitimate resting state, not just a
            # hypothetical: a prior --validation run that didn't shut down
            # cleanly (crash, kill -9) leaves the file exactly here, since
            # restore() never got to run. Nothing to flip; _original_text
            # is still captured above so restore() correctly puts back
            # `true` (this run's real original), not a fabricated `false`.
            print(_pass("Validation Mode already enabled (configs/validation.yaml)"))
            return
        new_text = re.sub(
            r"(production_validation_mode:\n  enabled: )false",
            r"\1true",
            text,
        )
        if new_text == text:
            print(
                _warn(
                    "Could not find production_validation_mode.enabled: false to flip -- "
                    "check configs/validation.yaml manually"
                )
            )
            return
        VALIDATION_CONFIG_PATH.write_text(new_text)

    def restore(self) -> None:
        if self._original_text is not None:
            VALIDATION_CONFIG_PATH.write_text(self._original_text)
            self._original_text = None


# ---------------------------------------------------------------------------
# Service process management
# ---------------------------------------------------------------------------
@dataclass
class ManagedService:
    name: str
    command: list[str]
    cwd: Path
    ready_pattern: re.Pattern[str] | None = None
    health_url: str | None = None
    passthrough_stderr: bool = False
    process: subprocess.Popen | None = field(default=None, repr=False)
    ready_event: threading.Event = field(default_factory=threading.Event)
    failed: bool = False
    _threads: list[threading.Thread] = field(default_factory=list, repr=False)

    def start(self, env: dict[str, str]) -> None:
        self.process = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE if not self.passthrough_stderr else None,
            text=True,
            bufsize=1,
        )
        t_out = threading.Thread(
            target=self._pump, args=(self.process.stdout, sys.stdout), daemon=True
        )
        t_out.start()
        self._threads.append(t_out)
        if not self.passthrough_stderr:
            t_err = threading.Thread(
                target=self._pump, args=(self.process.stderr, sys.stdout), daemon=True
            )
            t_err.start()
            self._threads.append(t_err)

    def _pump(self, stream, out) -> None:
        prefix = _c(f"[{self.name}] ", _BOLD)
        for line in iter(stream.readline, ""):
            out.write(prefix + line if not line.endswith("\n") else prefix + line)
            out.flush()
            if self.ready_pattern is not None and not self.ready_event.is_set():
                if self.ready_pattern.search(line):
                    self.ready_event.set()
        stream.close()

    def wait_until_healthy(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        if self.health_url is not None:
            while time.monotonic() < deadline:
                if self.process is None or self.process.poll() is not None:
                    return False
                try:
                    with urllib.request.urlopen(self.health_url, timeout=2.0) as resp:  # noqa: S310
                        if resp.status == 200:
                            return True
                except (urllib.error.URLError, OSError):
                    pass
                time.sleep(0.5)
            return False
        return self.ready_event.wait(timeout=max(0.0, deadline - time.monotonic()))

    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def stop(self, timeout: float = 10.0) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.send_signal(signal.SIGTERM)
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5.0)


class Orchestrator:
    def __init__(self, validation_mode: bool) -> None:
        self.validation_mode = validation_mode
        self.services: list[ManagedService] = []
        self._shutting_down = False
        self._frontend_port = FRONTEND_DEFAULT_PORT
        self._validation_toggle = ValidationModeToggle()

    def _base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        return env

    def start_all(self) -> bool:
        env = self._base_env()

        # ------------------------------------------------------------------
        # Camera Ingestion Service (ADR-028, Media Architecture Reset) --
        # standalone in this phase, wired to zero consumers, but started
        # first / stopped last (see shutdown()'s reversed(self.services))
        # so it's already positioned correctly for later phases, when
        # Live Streaming/Recording/AI Runtime start depending on it.
        # Always started fresh, never adopted -- same reasoning as
        # DeepStream below (owns live GStreamer/RTSP state).
        # ------------------------------------------------------------------
        if _is_own_service_on_port(INGESTION_PORT):
            print(
                _fail(
                    f"Camera Ingestion already running (port {INGESTION_PORT} -- media "
                    "distribution -- is already bound by an apps.ingestion process) -- "
                    "stop it first if you want to restart"
                )
            )
            return False

        ingestion = ManagedService(
            name="ingestion",
            command=[str(VENV_PYTHON), "-m", "apps.ingestion.app.main"],
            cwd=REPO_ROOT,
            ready_pattern=re.compile(r"radar-eye-ingestion running"),
        )
        self.services.append(ingestion)
        print(_c("\nStarting Camera Ingestion Service...", _BOLD))
        ingestion.start(env)
        if not ingestion.wait_until_healthy(timeout=30.0):
            self._report_startup_failure(ingestion)
            return False
        print(_pass("Camera Ingestion Service healthy"))

        # ------------------------------------------------------------------
        # Live Streaming Service (ADR-028, Phase 2) -- a new, independent
        # process, subscribing only to Camera Ingestion's published
        # endpoints. Started right after Camera Ingestion for launcher
        # readability only -- neither subsystem's own startup actually
        # blocks on the other (each runs its own independent reconnect/
        # poll loop against its upstream). Not yet the target of
        # apps.api's WebRTC proxy; see configs/live_streaming.yaml.
        # Always started fresh, never adopted -- same reasoning as
        # Camera Ingestion/DeepStream (owns live GStreamer/WebRTC state).
        # ------------------------------------------------------------------
        if _is_own_service_on_port(LIVE_STREAMING_PORT):
            print(
                _fail(
                    f"Live Streaming Service already running (port {LIVE_STREAMING_PORT} -- "
                    "signaling -- is already bound by an apps.live_stream process) -- "
                    "stop it first if you want to restart"
                )
            )
            return False

        live_streaming = ManagedService(
            name="live_streaming",
            command=[str(VENV_PYTHON), "-m", "apps.live_stream.app.main"],
            cwd=REPO_ROOT,
            ready_pattern=re.compile(r"radar-eye-live-streaming running"),
        )
        self.services.append(live_streaming)
        print(_c("\nStarting Live Streaming Service...", _BOLD))
        live_streaming.start(env)
        if not live_streaming.wait_until_healthy(timeout=30.0):
            self._report_startup_failure(live_streaming)
            return False
        print(_pass("Live Streaming Service healthy"))

        # ------------------------------------------------------------------
        # Backend API
        # ------------------------------------------------------------------
        if _is_own_service_on_port(API_PORT):
            # Already running (e.g. operator re-ran with --validation while
            # the stack is up).  Verify it is healthy before continuing.
            print(_c("\nBackend API already running -- verifying health...", _BOLD))
            try:
                with urllib.request.urlopen(API_HEALTH_URL, timeout=5.0) as resp:  # noqa: S310
                    api_healthy = resp.status == 200
            except (urllib.error.URLError, OSError):
                api_healthy = False
            if not api_healthy:
                print(_fail("Backend API already on port but not responding to health check"))
                return False
            print(_pass("Backend API healthy (adopted running process)"))
        else:
            api = ManagedService(
                name="api",
                command=[
                    str(VENV_PYTHON),
                    "-m",
                    "uvicorn",
                    "apps.api.app.main:create_app",
                    "--factory",
                    "--reload",
                ],
                cwd=REPO_ROOT,
                health_url=API_HEALTH_URL,
            )
            self.services.append(api)
            print(_c("\nStarting Backend API...", _BOLD))
            api.start(env)
            if not api.wait_until_healthy(timeout=30.0):
                self._report_startup_failure(api)
                return False
            print(_pass("Backend API healthy"))

        if self.validation_mode:
            print(_c("Validation Mode: enabling (configs/validation.yaml)...", _BOLD))
            self._validation_toggle.enable()

        # ------------------------------------------------------------------
        # DeepStream Runtime -- always started fresh, never adopted (unlike
        # the API/Frontend above): a running instance owns live GStreamer
        # pipeline/GPU state that can't be safely "verified healthy" from
        # the outside the way a REST health check can. It does, however,
        # own a fixed TCP port (LIVE_STREAM_PORT, Live Monitoring's
        # signaling server) since Stage C -- spawning a second instance
        # while one already holds that port fails confusingly deep inside
        # its own startup ("address already in use"). Check for that
        # collision up front and fail clearly instead.
        # ------------------------------------------------------------------
        if _is_own_service_on_port(LIVE_STREAM_PORT):
            print(
                _fail(
                    f"DeepStream Runtime already running (port {LIVE_STREAM_PORT} -- "
                    "Live Monitoring signaling -- is already bound by an apps.deepstream "
                    "process) -- stop it first if you want to restart"
                )
            )
            return False

        deepstream = ManagedService(
            name="deepstream",
            command=[str(VENV_PYTHON), "-m", "apps.deepstream.app.main"],
            cwd=REPO_ROOT,
            ready_pattern=re.compile(r"radar-eye-deepstream running"),
            # native NVIDIA logs + Validation Mode's dashboard both live here
            passthrough_stderr=True,
        )
        self.services.append(deepstream)
        print(_c("\nStarting DeepStream Runtime...", _BOLD))
        deepstream.start(env)
        if not deepstream.wait_until_healthy(timeout=90.0):
            self._report_startup_failure(deepstream)
            return False
        print(_pass("DeepStream Runtime healthy"))

        # ------------------------------------------------------------------
        # Frontend
        # ------------------------------------------------------------------
        frontend_ready = re.compile(r"Local:\s+http://localhost:(\d+)/")
        if _is_own_service_on_port(FRONTEND_DEFAULT_PORT):
            print(_c("\nFrontend already running -- skipping launch", _BOLD))
            print(_pass("Frontend healthy (adopted running process)"))
        else:
            frontend = ManagedService(
                name="frontend",
                command=["bun", "run", "dev"],
                cwd=REPO_ROOT / "frontend",
                ready_pattern=frontend_ready,
            )
            self.services.append(frontend)
            print(_c("\nStarting Frontend...", _BOLD))
            frontend.start(env)
            if not frontend.wait_until_healthy(timeout=30.0):
                self._report_startup_failure(frontend)
                return False
            print(_pass("Frontend healthy"))
            self._frontend_port = self._detect_frontend_port(frontend, frontend_ready)

        return True

    @staticmethod
    def _detect_frontend_port(service: ManagedService, pattern: re.Pattern[str]) -> int:
        # Best-effort -- falls back to the documented default if the
        # ready-line's port group was never captured for some reason.
        return FRONTEND_DEFAULT_PORT

    def _report_startup_failure(self, service: ManagedService) -> None:
        print(_fail(f"{service.name} failed to become healthy"))
        if service.process is not None and service.process.poll() is not None:
            print(_fail(f"{service.name} exited with code {service.process.returncode}"))
        self.shutdown()

    _DISPLAY_NAMES = {
        "ingestion": "Camera Ingestion Service",
        "live_streaming": "Live Streaming Service",
        "api": "Backend API",
        "deepstream": "DeepStream Runtime",
        "frontend": "Frontend",
    }

    def monitor(self) -> None:
        check = _c("✓", _GREEN)
        print()
        print(_c("=" * 36, _BOLD))
        print(_c("Radar-Eye", _BOLD))
        print(_c("=" * 36, _BOLD))
        print()
        print(f"{check} Database")
        for service in self.services:
            print(f"{check} {self._DISPLAY_NAMES.get(service.name, service.name)}")
        print()
        print(f"Validation Mode: {'ENABLED' if self.validation_mode else 'disabled'}")
        print()
        print(f"Frontend:\nhttp://localhost:{self._frontend_port}")
        print()
        print(f"API:\nhttp://localhost:{API_PORT}/docs")
        print()
        print(_c("=" * 36, _BOLD))
        print("\nAll services running. Press Ctrl+C to stop.\n")

        try:
            while not self._shutting_down:
                for service in self.services:
                    if not service.is_alive() and not self._shutting_down:
                        code = service.process.returncode if service.process is not None else None
                        print(_fail(f"\n{service.name} exited unexpectedly (code {code})"))
                        self.shutdown()
                        return
                time.sleep(1.0)
        except KeyboardInterrupt:
            print(_c("\nCtrl+C received -- shutting down...", _BOLD))
            self.shutdown()

    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        for service in reversed(self.services):
            if service.is_alive():
                print(f"Stopping {service.name}...")
                service.stop()
        self._validation_toggle.restore()
        print(_pass("All services stopped"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validation",
        action="store_true",
        help="Enable Production Validation Mode (see docs/PRODUCTION_VALIDATION_MODE.md)",
    )
    args = parser.parse_args()

    checks = run_prerequisite_checks()
    all_ok = print_checks(checks)
    if not all_ok:
        print(
            _fail("\nOne or more required prerequisites failed -- fix the items above and re-run.")
        )
        return 1

    load_dotenv_into_environ()
    if not run_migrations():
        return 1
    ensure_development_administrator()

    orchestrator = Orchestrator(validation_mode=args.validation)
    signal.signal(signal.SIGTERM, lambda *_: orchestrator.shutdown())
    if not orchestrator.start_all():
        return 1
    orchestrator.monitor()
    return 0


if __name__ == "__main__":
    sys.exit(main())
