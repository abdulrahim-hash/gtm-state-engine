"""Unit and failure-path tests for the public health contract."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from gtm_state_api.health import readiness_check
from gtm_state_api.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Provide a test client that restores dependency overrides."""

    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_liveness_contract(client: TestClient) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "gtm-state-api",
        "version": "0.1.0",
    }


def test_readiness_when_database_is_available(client: TestClient) -> None:
    app.dependency_overrides[readiness_check] = lambda: True

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_hides_database_failure_details(client: TestClient) -> None:
    app.dependency_overrides[readiness_check] = lambda: False

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert "database" not in response.text.lower()
    assert "postgres" not in response.text.lower()


def test_production_disables_interactive_api_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    from gtm_state_api import main
    from gtm_state_api.config import get_settings

    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    production_app = main.create_app()

    assert production_app.docs_url is None
    assert production_app.redoc_url is None
    assert production_app.openapi_url is None

    get_settings.cache_clear()
