"""RM-12 Phase 6 -- consolidated contract-verification pass.

Systematically cross-checks every REST endpoint and WebSocket channel
listed in docs/FRONTEND_BACKEND_CONTRACTS.md against the real, running
application -- not just "the tests happened to write per phase" (per
docs/RM-12_IMPLEMENTATION_PLAN.md's Phase 6, mirroring the same kind of
final verification pass docs/RM-11_SIV_ENGINEERING_REVIEW.md did for
RM-11). Two endpoints and one WS channel are intentionally, explicitly
absent -- asserted absent here, not just implicitly missing, so a future
change can't silently "fix" this list without also resolving
docs/OPEN_QUESTIONS.md Q-014/Q-015.
"""

from __future__ import annotations

import pytest

from apps.api.app.main import create_app


def _all_route_paths(app) -> set[str]:
    """FastAPI wraps ``include_router()``-registered routes in a lazy
    ``_IncludedRouter`` whose sub-routes only surface via
    ``.original_router.routes`` -- ``app.routes`` alone (as of fastapi
    0.139) does not flatten them."""
    paths: set[str] = set()
    for route in app.routes:
        if hasattr(route, "path"):
            paths.add(route.path)
        elif hasattr(route, "original_router"):
            for sub_route in route.original_router.routes:
                if hasattr(sub_route, "path"):
                    paths.add(sub_route.path)
    return paths


# (method, path) exactly as docs/FRONTEND_BACKEND_CONTRACTS.md lists them,
# deduplicated across sections (several routes are reused by multiple
# frontend screens -- e.g. GET /cameras appears in Live Monitoring,
# Tactical Map, and Camera Management).
IMPLEMENTED_REST_ROUTES: set[tuple[str, str]] = {
    ("get", "/cameras"),
    ("post", "/cameras"),
    ("delete", "/cameras/{camera_id}"),
    ("get", "/cameras/brands"),
    ("patch", "/cameras/{camera_id}/lifecycle"),
    ("get", "/threats/active"),
    ("get", "/incidents/open"),
    ("get", "/incidents"),
    ("get", "/incidents/{incident_id}"),
    ("patch", "/incidents/{incident_id}"),
    ("get", "/incidents/{incident_id}/events"),
    ("get", "/incidents/{incident_id}/evidence"),
    ("get", "/cameras/{camera_id}"),
    ("patch", "/cameras/{camera_id}"),
    ("get", "/cameras/{camera_id}/health"),
    ("get", "/cameras/{camera_id}/calibration"),
    ("post", "/cameras/{camera_id}/webrtc/offer"),
    ("get", "/analytics/threats"),
    ("get", "/analytics/incidents"),
    ("get", "/analytics/cameras"),
    ("get", "/analytics/system"),
    ("get", "/health/system"),
    ("get", "/health/gpu"),
    ("get", "/health/storage"),
    ("get", "/health/recording"),
    ("get", "/health/cameras"),
    ("get", "/users"),
    ("patch", "/users/{user_id}"),
    ("get", "/reviews"),
    ("get", "/reviews/{review_id}"),
    ("patch", "/reviews/{review_id}"),
    ("post", "/reviews/{review_id}/confirm-military"),
    ("post", "/reviews/{review_id}/confirm-civilian"),
    ("post", "/reviews/{review_id}/escalate"),
    ("post", "/reviews/{review_id}/dismiss"),
    ("get", "/calibration/cameras"),
    ("post", "/calibration/start"),
    ("post", "/calibration/validate"),
    ("get", "/calibration/results"),
    ("get", "/calibration/{camera_id}"),
    ("get", "/evidence"),
    ("get", "/evidence/{evidence_id}"),
    ("get", "/recordings"),
    ("get", "/recordings/{recording_id}"),
    ("get", "/recordings/{recording_id}/download"),
    ("get", "/snapshots/{snapshot_id}"),
    ("get", "/snapshots/{snapshot_id}/download"),
}

DESCOPED_REST_ROUTES: set[tuple[str, str]] = {
    ("get", "/config"),  # docs/OPEN_QUESTIONS.md Q-014
    ("patch", "/config"),  # docs/OPEN_QUESTIONS.md Q-014
}

IMPLEMENTED_WS_CHANNELS: set[str] = {
    "/ws/threats",
    "/ws/incidents",
    "/ws/camera-health",
    "/ws/reviews",
    "/ws/alarms",
}

DESCOPED_WS_CHANNELS: set[str] = {"/ws/tracking"}  # docs/OPEN_QUESTIONS.md Q-015


@pytest.fixture
def _openapi_paths(_default_env: None) -> dict[str, set[str]]:
    app = create_app()
    schema = app.openapi()
    return {path: set(methods.keys()) for path, methods in schema["paths"].items()}


class TestRestContractCoverage:
    def test_every_implemented_route_exists_in_the_app(
        self, _openapi_paths: dict[str, set[str]]
    ) -> None:
        missing = [
            (method, path)
            for method, path in IMPLEMENTED_REST_ROUTES
            if method not in _openapi_paths.get(path, set())
        ]
        assert missing == []

    def test_descoped_routes_are_not_accidentally_implemented(
        self, _openapi_paths: dict[str, set[str]]
    ) -> None:
        present = [
            (method, path)
            for method, path in DESCOPED_REST_ROUTES
            if method in _openapi_paths.get(path, set())
        ]
        assert present == [], (
            "A descoped route (docs/OPEN_QUESTIONS.md) now exists -- update "
            "IMPLEMENTED_REST_ROUTES/DESCOPED_REST_ROUTES and close the open question."
        )

    def test_no_undocumented_extra_routes(self, _openapi_paths: dict[str, set[str]]) -> None:
        """Every (method, path) the app actually serves must be accounted
        for -- either as an implemented contract route or an explicit,
        pre-existing exception (docs, health-check infra, or RM-09's
        already-shipped health routes, none of which are RM-12's to
        re-litigate)."""
        pre_existing_exceptions = {
            ("get", "/openapi.json"),
            ("get", "/docs"),
            ("get", "/docs/oauth2-redirect"),
            ("get", "/redoc"),
            ("post", "/auth/login"),
            ("post", "/auth/refresh"),
        }
        documented = IMPLEMENTED_REST_ROUTES | pre_existing_exceptions
        actual = {(method, path) for path, methods in _openapi_paths.items() for method in methods}
        undocumented = actual - documented
        assert undocumented == set()


class TestWebSocketContractCoverage:
    def test_every_implemented_channel_is_registered(self, _default_env: None) -> None:
        app = create_app()
        registered_paths = _all_route_paths(app)
        missing = IMPLEMENTED_WS_CHANNELS - registered_paths
        assert missing == set()

    def test_descoped_channels_are_not_accidentally_implemented(self, _default_env: None) -> None:
        app = create_app()
        registered_paths = _all_route_paths(app)
        present = DESCOPED_WS_CHANNELS & registered_paths
        assert present == set(), (
            "A descoped WS channel (docs/OPEN_QUESTIONS.md) now exists -- update "
            "IMPLEMENTED_WS_CHANNELS/DESCOPED_WS_CHANNELS and close the open question."
        )
