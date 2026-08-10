"""Full environment pre-flight -- RM-11.SIV operator tooling, decision-tree
entry point.

The first command an operator runs, before any other `scripts/check_*.py`
or `scripts/*.py` tool -- see docs/SIV_OPERATOR_RUNBOOK.md's decision tree.
Validates the machine itself (GPU/driver/CUDA/TensorRT/DeepStream/
GStreamer/PostgreSQL/Python/packages/env vars/model files/disk space/
output directories) so a broken environment is reported once, up front,
with the exact reason, instead of surfacing later as a confusing failure
three tools deep into a session.

Never installs, downloads, builds, or touches the database/model files --
the one exception is the output-directories check, which (like
services/recording/storage.py itself) lazily creates
<storage-root>/{,snapshots,recordings} if missing so it can verify they're
actually writable, not just guess from a parent directory's permissions.
Safe to run repeatedly.

Usage:
    python -m scripts.check_environment [--models-yaml PATH]
        [--storage-root PATH] [--min-free-gb N]

Exit code 0 = every check passed. Exit code 1 = at least one check
failed -- the printed FAIL section names exactly which and why.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from apps.deepstream.app.config import DEFAULT_MODELS_PATH, load_models_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORAGE_ROOT = REPO_ROOT / "storage"
DEFAULT_MIN_FREE_GB = 5.0
_REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"
_REQUIRED_ENV_VARS = ("RADAR_EYE_DB_USER", "RADAR_EYE_DB_PASSWORD", "RADAR_EYE_ENCRYPTION_KEY")
_MIN_PYTHON_VERSION = (3, 10)
_DEEPSTREAM_INSTALL_DIR = Path("/opt/nvidia/deepstream/deepstream")


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    """On pass: a short informational summary (version, count, ...). On
    fail: the exact reason, per this script's contract with the runbook."""


def _run(*args: str) -> tuple[int, str, str]:
    """subprocess.run wrapper -- returns (returncode, stdout, stderr),
    never raises (FileNotFoundError becomes returncode -1)."""
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=15)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return -1, "", f"{args[0]}: command not found"
    except subprocess.TimeoutExpired:
        return -1, "", f"{args[0]}: timed out"


def check_gpu_visible() -> CheckResult:
    code, out, err = _run("nvidia-smi", "-L")
    if code != 0 or not out:
        return CheckResult("GPU", False, err or "nvidia-smi reported no visible GPU")
    return CheckResult("GPU", True, out.splitlines()[0])


def check_nvidia_driver() -> CheckResult:
    code, out, err = _run("nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader")
    if code != 0 or not out:
        return CheckResult("NVIDIA Driver", False, err or "could not query driver_version")
    return CheckResult("NVIDIA Driver", True, out.splitlines()[0])


def check_cuda_version() -> CheckResult:
    code, out, _err = _run("nvcc", "--version")
    if code == 0 and out:
        match = re.search(r"release (\d+\.\d+)", out)
        if match:
            return CheckResult("CUDA", True, match.group(1))

    for version_file, parser in (
        (Path("/usr/local/cuda/version.json"), _parse_cuda_version_json),
        (Path("/usr/local/cuda/version.txt"), lambda text: text.strip()),
    ):
        if version_file.is_file():
            try:
                version = parser(version_file.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 -- fall through to next source
                continue
            if version:
                return CheckResult("CUDA", True, version)

    return CheckResult(
        "CUDA", False, "nvcc not found and no /usr/local/cuda/version.{json,txt} present"
    )


def _parse_cuda_version_json(text: str) -> str | None:
    import json

    data = json.loads(text)
    cuda = data.get("cuda", {})
    return cuda.get("version") if isinstance(cuda, dict) else None


def check_tensorrt_version() -> CheckResult:
    try:
        import tensorrt as trt  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001 -- import-time failures vary by install
        return CheckResult("TensorRT", False, f"import tensorrt failed: {exc}")
    return CheckResult("TensorRT", True, str(trt.__version__))


def check_deepstream_installation() -> CheckResult:
    if not _DEEPSTREAM_INSTALL_DIR.is_dir():
        return CheckResult(
            "DeepStream",
            False,
            f"{_DEEPSTREAM_INSTALL_DIR} does not exist -- DeepStream SDK not installed",
        )
    version_file = _DEEPSTREAM_INSTALL_DIR / "version"
    detail = (
        version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else "installed"
    )
    return CheckResult("DeepStream", True, detail)


def check_gstreamer_installation() -> CheckResult:
    try:
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        Gst.init(None)
        version = Gst.version_string()
    except Exception as exc:  # noqa: BLE001 -- gi/Gst import-time failures vary
        return CheckResult(
            "GStreamer",
            False,
            f"{exc} -- run under the DeepStream/GStreamer interpreter, not a plain venv",
        )
    return CheckResult("GStreamer", True, version)


async def _postgres_reachable() -> tuple[bool, str]:
    from apps.api.app.config import get_settings
    from apps.api.app.db import create_engine

    try:
        settings = get_settings()
    except Exception as exc:  # noqa: BLE001 -- ValidationError etc.
        return False, f"could not load settings: {exc}"

    engine = create_engine(settings)
    try:
        async with engine.begin():
            pass
    except Exception as exc:  # noqa: BLE001 -- any connectivity failure
        return False, str(exc)
    finally:
        await engine.dispose()
    return True, f"{settings.database.host}:{settings.database.port}/{settings.database.name}"


def check_postgresql_connectivity() -> CheckResult:
    import asyncio

    ok, detail = asyncio.run(_postgres_reachable())
    return CheckResult("PostgreSQL", ok, detail)


def check_python_version() -> CheckResult:
    version = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info[:2] < _MIN_PYTHON_VERSION:
        required = ".".join(str(part) for part in _MIN_PYTHON_VERSION)
        return CheckResult("Python version", False, f"{version} < required {required}+")
    return CheckResult("Python version", True, version)


def check_required_packages() -> CheckResult:
    if not _REQUIREMENTS_PATH.is_file():
        return CheckResult("Python packages", False, f"{_REQUIREMENTS_PATH} not found")

    missing: list[str] = []
    for line in _REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-r "):
            continue
        # "sqlalchemy[asyncio]>=2.0" -> "sqlalchemy"; "PyYAML>=6.0" -> "PyYAML"
        name = re.split(r"[\[<>=!~; ]", line, maxsplit=1)[0]
        try:
            importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(name)

    if missing:
        return CheckResult("Python packages", False, f"not installed: {', '.join(missing)}")
    return CheckResult("Python packages", True, f"{_REQUIREMENTS_PATH.name} satisfied")


def check_environment_variables() -> CheckResult:
    from pydantic import ValidationError

    from apps.api.app.config import EnvSettings

    try:
        # Required fields are sourced from the environment / .env at runtime
        # by pydantic-settings -- see apps/api/app/config.py's load_settings.
        EnvSettings()  # type: ignore[call-arg]
    except ValidationError as exc:
        missing = sorted(
            {str(error["loc"][0]) for error in exc.errors() if error["type"] == "missing"}
        )
        if not missing:
            return CheckResult("Environment variables", False, str(exc))
        env_names = ", ".join(f"RADAR_EYE_{field.upper()}" for field in missing)
        return CheckResult(
            "Environment variables", False, f"missing: {env_names} (set directly or via .env)"
        )
    return CheckResult("Environment variables", True, ", ".join(_REQUIRED_ENV_VARS))


def check_model_files(models_yaml: Path) -> list[CheckResult]:
    """Three checks in one pass over configs/models.yaml -- model directory,
    engine file, label file -- since all three key off the same
    ``load_models_settings()`` read and the same per-stage enabled flag."""
    try:
        models = load_models_settings(models_yaml)
    except Exception as exc:  # noqa: BLE001 -- ValidationError / OSError
        reason = f"{models_yaml} failed to load: {exc}"
        return [
            CheckResult("Model directory", False, reason),
            CheckResult("Engine files", False, reason),
            CheckResult("Label files", False, reason),
        ]

    stages = [stage for stage in (models.pgie, models.sgie) if stage.enabled]
    if not stages:
        note = "no stages enabled in configs/models.yaml -- placeholder mode, nothing to validate"
        return [
            CheckResult("Model directory", True, note),
            CheckResult("Engine files", True, note),
            CheckResult("Label files", True, note),
        ]

    missing_dirs = [s.model_file for s in stages if not Path(s.model_file).parent.is_dir()]
    missing_engines = [s.engine_file for s in stages if not Path(s.engine_file).is_file()]
    missing_labels = [s.labels for s in stages if not Path(s.labels).is_file()]

    return [
        CheckResult(
            "Model directory",
            not missing_dirs,
            "exists" if not missing_dirs else f"missing directory for: {', '.join(missing_dirs)}",
        ),
        CheckResult(
            "Engine files",
            not missing_engines,
            "present" if not missing_engines else f"missing: {', '.join(missing_engines)}",
        ),
        CheckResult(
            "Label files",
            not missing_labels,
            "present" if not missing_labels else f"missing: {', '.join(missing_labels)}",
        ),
    ]


def check_disk_space(storage_root: Path, *, min_free_gb: float) -> CheckResult:
    probe_path = storage_root if storage_root.exists() else storage_root.parent
    try:
        _total, _used, free = shutil.disk_usage(probe_path)
    except OSError as exc:
        return CheckResult("Disk space", False, f"could not stat {probe_path}: {exc}")

    free_gb = free / (1024**3)
    if free_gb < min_free_gb:
        return CheckResult(
            "Disk space",
            False,
            f"{free_gb:.1f} GB free at {probe_path}, below the {min_free_gb:.1f} GB minimum "
            "(continuous H.265 recording -- CLAUDE.md Recording Rules)",
        )
    return CheckResult("Disk space", True, f"{free_gb:.1f} GB free at {probe_path}")


def check_writable_output_directories(storage_root: Path) -> CheckResult:
    targets = [storage_root, storage_root / "snapshots", storage_root / "recordings"]
    unwritable: list[str] = []
    for target in targets:
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            unwritable.append(f"{target} ({exc})")
            continue
        if not os.access(target, os.W_OK):
            unwritable.append(str(target))

    if unwritable:
        reason = f"not writable: {', '.join(unwritable)}"
        return CheckResult("Writable output directories", False, reason)
    return CheckResult("Writable output directories", True, ", ".join(str(t) for t in targets))


def run_all_checks(
    *, models_yaml: Path, storage_root: Path, min_free_gb: float
) -> list[CheckResult]:
    return [
        check_python_version(),
        check_required_packages(),
        check_environment_variables(),
        check_gpu_visible(),
        check_nvidia_driver(),
        check_cuda_version(),
        check_tensorrt_version(),
        check_deepstream_installation(),
        check_gstreamer_installation(),
        check_postgresql_connectivity(),
        *check_model_files(models_yaml),
        check_disk_space(storage_root, min_free_gb=min_free_gb),
        check_writable_output_directories(storage_root),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-yaml", type=Path, default=DEFAULT_MODELS_PATH)
    parser.add_argument("--storage-root", type=Path, default=DEFAULT_STORAGE_ROOT)
    parser.add_argument("--min-free-gb", type=float, default=DEFAULT_MIN_FREE_GB)
    args = parser.parse_args()

    results = run_all_checks(
        models_yaml=args.models_yaml,
        storage_root=args.storage_root,
        min_free_gb=args.min_free_gb,
    )

    for result in results:
        mark = "✓" if result.passed else "✗"
        if result.passed:
            print(f"{mark} {result.name}: {result.detail}")
        else:
            print(f"{mark} {result.name}")

    failures = [r for r in results if not r.passed]
    print()
    if not failures:
        print("RESULT: PASS")
        raise SystemExit(0)

    print("FAIL")
    print()
    for result in failures:
        print(f"{result.name}:")
        print(f"  {result.detail}")
        print()
    print("Do not continue to the next SIV step until every check above passes.")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
