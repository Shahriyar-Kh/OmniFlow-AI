from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from tbos_renderer.schemas import ComponentStatus, SystemStatusResponse


def test_liveness_is_process_only(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_readiness_success(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["database"]["status"] == "ok"
    assert response.json()["ollama"]["status"] == "not_configured"


def test_readiness_database_failure(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tbos_renderer.main.database_status",
        AsyncMock(
            return_value=ComponentStatus(
                status="unavailable", required=True, detail="Database check failed"
            )
        ),
    )
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_system_status_matches_schema(client: TestClient) -> None:
    response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    parsed = SystemStatusResponse.model_validate(response.json())
    assert parsed.environment == "test"
    assert parsed.database.status == "ok"


def test_correlation_id_propagates(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Correlation-ID": "test-correlation-42"})
    assert response.headers["X-Correlation-ID"] == "test-correlation-42"
    assert response.json()["correlation_id"] == "test-correlation-42"


def test_public_config_never_contains_secrets(client: TestClient) -> None:
    response = client.get("/api/v1/config/public")
    assert response.status_code == 200
    body = response.text.lower()
    assert "database_url" not in body
    assert "password" not in body
    assert "token" not in body
    assert "secret" not in body
    assert response.json()["brand_slug"] == "techbuilt-open-school"


def test_openapi_enabled_for_test_environment(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 200
