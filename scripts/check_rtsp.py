"""Pre-flight RTSP connectivity check for configs/camera.yaml -- RM-11.SIV
operator tooling.

Reads configs/camera.yaml directly (env-var substituted, same as
scripts/siv_register_camera.py) and attempts a real RTSP connection --
rtspsrc ! rtph264depay ! h264parse ! fakesink, the same negotiation
DeepStreamPipeline's source bin performs (apps/deepstream/app/ingestion/
source.py) minus the Jetson-specific hardware decoder, which this check
doesn't need. Reports PLAYING reached / first buffer received, or the
specific error, well before a full scripts/run_siv.py run would surface it.

Requires the DeepStream/GStreamer Python environment (gi + Gst) -- run
under the same interpreter as scripts/run_siv.py, not the repo's own
pytest/miniconda environment. Does NOT require a database -- it reads
configs/camera.yaml directly, not the registered DB row (see
scripts/show_registered_cameras.py for checking what was actually
registered).

Usage:
    python -m scripts.check_rtsp [--camera-yaml PATH] [--timeout SECONDS]
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

from apps.deepstream.app.camera_yaml import CameraYamlError, build_rtsp_url, require_keys
from apps.deepstream.app.env_yaml import (
    MissingEnvironmentVariableError,
    load_yaml_with_env_substitution,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CAMERA_YAML = REPO_ROOT / "configs" / "camera.yaml"
DEFAULT_TIMEOUT_SECONDS = 15.0


def _import_gst():  # noqa: ANN202 -- returns the gi.repository.Gst module
    try:
        import gi
    except ImportError as exc:
        raise SystemExit(
            "error: 'gi' (PyGObject) is not importable under this Python interpreter.\n"
            "check_rtsp.py needs the same DeepStream/GStreamer environment as "
            "scripts/run_siv.py -- run it with that interpreter, not the repo's "
            "pytest/miniconda one."
        ) from exc
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst

    Gst.init(None)
    return Gst


def check_rtsp(camera_yaml_path: Path, *, timeout_seconds: float) -> bool:
    print(f"Reading {camera_yaml_path}")
    try:
        raw = load_yaml_with_env_substitution(camera_yaml_path)
        require_keys(raw)
        url = build_rtsp_url(raw)
    except MissingEnvironmentVariableError as exc:
        print(f"FAIL: {exc}")
        return False
    except CameraYamlError as exc:
        print(f"FAIL: {exc}")
        return False

    transport = raw.get("transport", "tcp")
    latency_ms = raw.get("latency_ms", 200)
    # Never print credentials -- mask the URL for display only.
    display_url = url
    if "@" in url:
        scheme, _, rest = url.partition("://")
        _creds, _, host_part = rest.partition("@")
        display_url = f"{scheme}://***:***@{host_part}"
    print(f"Connecting to {display_url} (transport={transport}, timeout={timeout_seconds}s)")

    Gst = _import_gst()

    pipeline = Gst.parse_launch(
        f'rtspsrc location="{url}" protocols={transport} latency={latency_ms} name=src ! '
        "rtph264depay ! h264parse ! fakesink name=sink sync=0"
    )

    result = {"reached_playing": False, "error": None, "caps": None}
    done = threading.Event()

    def _on_message(_bus, message) -> None:  # noqa: ANN001
        if message.type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            result["error"] = f"{err} ({debug})"
            done.set()
        elif message.type == Gst.MessageType.EOS:
            result["error"] = "Stream ended (EOS) before PLAYING was confirmed"
            done.set()
        elif message.type == Gst.MessageType.STATE_CHANGED and message.src == pipeline:
            _old, new, _pending = message.parse_state_changed()
            if new == Gst.State.PLAYING:
                result["reached_playing"] = True
                done.set()

    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", _on_message)

    from gi.repository import GLib

    loop = GLib.MainLoop()
    loop_thread = threading.Thread(target=loop.run, daemon=True)
    loop_thread.start()

    pipeline.set_state(Gst.State.PLAYING)
    start = time.monotonic()
    done.wait(timeout=timeout_seconds)
    elapsed = time.monotonic() - start

    pipeline.set_state(Gst.State.NULL)
    loop.quit()

    if result["reached_playing"]:
        print(f"PASS: reached PLAYING in {elapsed:.1f}s")
        return True
    if result["error"]:
        print(f"FAIL: {result['error']}")
        return False
    print(f"FAIL: timed out after {timeout_seconds}s without reaching PLAYING or an error")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera-yaml", type=Path, default=DEFAULT_CAMERA_YAML)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args()

    if not args.camera_yaml.is_file():
        print(
            f"error: {args.camera_yaml} not found -- copy configs/camera.yaml.example to "
            f"configs/camera.yaml and fill in your camera's details first.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    ok = check_rtsp(args.camera_yaml, timeout_seconds=args.timeout)
    print()
    print("RESULT: PASS" if ok else "RESULT: FAIL")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
