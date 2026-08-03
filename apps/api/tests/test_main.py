from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.app.main import create_app


def test_app_instantiates() -> None:
    app = create_app()

    with TestClient(app):
        pass

    assert isinstance(app, FastAPI)


def test_default_docs_endpoints_are_enabled() -> None:
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200


def test_cors_preflight_allows_the_default_frontend_origin() -> None:
    """CORSMiddleware must be registered and configured with
    settings.cors.allowed_origins -- regression coverage for a real
    incident where this middleware existed only as an uncommitted local
    change (confirmed via `git log --all -S"CORSMiddleware"` returning no
    commits) for the whole life of this feature, so no test ever
    protected it and it was one `git clean`/fresh-checkout away from
    silently vanishing. Exercises the real preflight (OPTIONS) request a
    browser sends before POST /cameras, not just a GET, since that's the
    exact request shape the operator-reported regression involved."""
    app = create_app()

    with TestClient(app) as client:
        response = client.options(
            "/cameras",
            headers={
                "Origin": "http://localhost:8080",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8080"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_rejects_an_unlisted_origin() -> None:
    """The flip side of the above -- CORS must not be wide open (a
    misconfigured `allow_origins=["*"]` would also make the preflight
    test above pass, silently hiding a real security regression)."""
    app = create_app()

    with TestClient(app) as client:
        response = client.options(
            "/cameras",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert "access-control-allow-origin" not in response.headers
