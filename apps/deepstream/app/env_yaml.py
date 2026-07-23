"""YAML loading with ``${VAR_NAME}`` environment-variable substitution.

Source: RM-11.SIV Principal Engineer approval, Additional Requirement A.1,
Option B (preferred) -- ``configs/camera.yaml`` must never need to hold a
plaintext credential in the file itself. Kept as a small standalone module
(rather than folded into ``config.py``) because it is only ever used by
``scripts/siv_register_camera.py`` against ``configs/camera.yaml`` -- that
file is a one-time bootstrap input (RM-11.SIV Decision A), never read by
``DeepStreamRuntime``/``apps/deepstream/app/config.py`` at runtime.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class MissingEnvironmentVariableError(RuntimeError):
    """Raised when a ``${VAR_NAME}`` placeholder has no matching environment
    variable set -- fail fast rather than substituting an empty string and
    silently producing e.g. an empty RTSP password."""


def _substitute(raw_text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        value = os.environ.get(name)
        if value is None:
            raise MissingEnvironmentVariableError(
                f"Environment variable '{name}' referenced as '${{{name}}}' is not set"
            )
        return value

    return _VAR_PATTERN.sub(_replace, raw_text)


def load_yaml_with_env_substitution(path: Path) -> dict:
    """Read ``path``, replace every ``${VAR_NAME}`` with the matching
    environment variable (raising if unset), then parse as YAML."""
    raw_text = path.read_text(encoding="utf-8")
    substituted = _substitute(raw_text)
    return yaml.safe_load(substituted) or {}
