from __future__ import annotations

from collections.abc import Iterator

import pytest

from services.calibration import service as calibration_service

# _default_env, db_engine, db_session are defined once in the repository
# root conftest.py -- see that module's docstring for why.


@pytest.fixture(autouse=True)
def _clear_calibration_cache() -> Iterator[None]:
    """CalibrationService's homography cache is module-level/process-wide
    by design (RM-11 Phase 2 design review, Decision A) -- reset it between
    tests so no test observes another's cached state."""
    calibration_service.clear_cache()
    yield
    calibration_service.clear_cache()
