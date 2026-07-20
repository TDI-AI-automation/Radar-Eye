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
