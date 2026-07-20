"""Root conftest.py — ensures the repository root is on sys.path.

This makes ``shared``, ``apps``, and ``services`` importable from any test
subtree without requiring editable installs.  Developer tooling (RM-DEV)
will formalise the packaging approach; for now this matches the import
pattern established by RM-01.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Insert the repository root as the first entry so project packages take
# precedence over any same-named installed packages.
_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
