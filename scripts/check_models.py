"""Pre-flight check for configs/models.yaml -- RM-11.SIV operator tooling.

Validates configs/models.yaml without starting the pipeline: resolves each
enabled stage through the real ModelConfigResolver (the same code
scripts/run_siv.py uses), which fails fast naming the exact key if a
referenced model/labels file doesn't exist, and prints the rendered nvinfer
config so the operator can inspect exactly what will be loaded.

Pure Python/file-IO -- does not need gi/pyds/DeepStream/GPU, so it runs
under any Python with this repo's dependencies installed, before the
DeepStream environment itself needs to be touched.

Usage:
    python -m scripts.check_models [--models-yaml PATH] [--show-config]

Exit code 0 = every enabled stage resolved successfully. Exit code 1 = at
least one stage failed (missing file, or configs/models.yaml itself is
invalid) -- the printed error names the exact configs/models.yaml key.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pydantic import ValidationError

from apps.deepstream.app.config import DEFAULT_MODELS_PATH, load_models_settings
from apps.deepstream.app.models_config import ModelConfigError, ModelConfigResolver


def _print_stage_summary(name: str, stage) -> None:  # noqa: ANN001 -- ModelStageSettings
    print(f"[{name}]")
    print(f"  enabled:    {stage.enabled}")
    if not stage.enabled:
        print("  -> placeholder config will be used (RM-11 Phase 1/2 stock model)")
        return
    print(f"  model_file: {stage.model_file}")
    print(f"  engine_file:{stage.engine_file}")
    print(f"  labels:     {stage.labels}")
    print(
        f"  batch_size: {stage.batch_size}  precision: {stage.precision}  "
        f"unique_id: {stage.unique_id}"
    )
    if stage.custom_lib_path:
        print(f"  custom_lib_path: {stage.custom_lib_path}")
        print(f"  parse_bbox_func_name: {stage.parse_bbox_func_name}")


def check_models(models_yaml_path: Path, *, show_config: bool) -> bool:
    """Returns True if every enabled stage resolved successfully."""
    print(f"Reading {models_yaml_path}")
    try:
        models = load_models_settings(models_yaml_path)
    except ValidationError as exc:
        print(f"FAIL: configs/models.yaml failed to parse:\n{exc}")
        return False
    except OSError as exc:
        print(f"FAIL: could not read {models_yaml_path}: {exc}")
        return False

    print()
    _print_stage_summary("pgie", models.pgie)
    print()
    _print_stage_summary("sgie", models.sgie)
    print()

    resolver = ModelConfigResolver()
    ok = True
    for stage_name, resolve in (("pgie", resolver.resolve_pgie), ("sgie", resolver.resolve_sgie)):
        try:
            resolved = resolve(models)
        except ModelConfigError as exc:
            print(f"FAIL [{stage_name}]: {exc}")
            ok = False
            continue

        kind = "placeholder" if resolved.is_placeholder else "resolved (custom model)"
        print(f"PASS [{stage_name}]: {kind} -> {resolved.config_file_path}")
        if show_config:
            print("-" * 64)
            print(resolved.config_file_path.read_text(encoding="utf-8"))
            print("-" * 64)

    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-yaml", type=Path, default=DEFAULT_MODELS_PATH)
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Print the full rendered nvinfer config for each resolved stage.",
    )
    args = parser.parse_args()

    ok = check_models(args.models_yaml, show_config=args.show_config)
    print()
    print("RESULT: PASS" if ok else "RESULT: FAIL")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
