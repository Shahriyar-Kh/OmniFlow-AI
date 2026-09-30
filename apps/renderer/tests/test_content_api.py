from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from tbos_renderer.content_engine.client import AiClient
from tbos_renderer.content_engine.schemas import (
    AiStatusResponse,
    ContentType,
)

from .conftest import TEST_API_KEY
from .factories import poster, raw_content


def test_topics_endpoints(client: TestClient) -> None:
    res = client.get("/api/v1/topics")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 70
    assert len(data["items"]) == 70

    # Filter topics
    filtered = client.get(
        "/api/v1/topics",
        params={"pillar": "AI Tools and Practical AI", "content_type": "poster"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] > 0

    # Single topic
    item = client.get("/api/v1/topics/ai-prompt-anatomy")
    assert item.status_code == 200
    assert item.json()["id"] == "ai-prompt-anatomy"

    # 404
    missing = client.get("/api/v1/topics/unknown-topic-id")
    assert missing.status_code == 404


def test_weekly_plan_endpoint(client: TestClient) -> None:
    # Missing auth
    unauth = client.post("/api/v1/plans/weekly", json={"week_start": "2026-10-05"})
    assert unauth.status_code == 401

    # Valid auth
    res = client.post(
        "/api/v1/plans/weekly",
        headers={"X-TBOS-API-Key": TEST_API_KEY},
        json={"week_start": "2026-10-05"},
    )
    assert res.status_code == 200
    plan = res.json()
    assert len(plan["items"]) == 7
    assert plan["plan_id"].startswith("weekly-2026-10-05")


def test_content_generation_and_management_lifecycle(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mock AI Client generation so tests run fast without network calls
    mock_ai = AsyncMock(spec=AiClient)
    mock_ai.active_model_name = "mock-gemini-flash"
    mock_ai.last_provider_used = "gemini"
    mock_ai.fallback_occurred = False
    mock_ai.generate_json.return_value = raw_content(ContentType.POSTER)
    mock_ai.status.return_value = AiStatusResponse(
        enabled=True,
        configured=True,
        reachable=True,
        selected_model="mock-gemini-flash",
        model_available=True,
        available_models=["mock-gemini-flash"],
        detail="Mock ready",
    )

    # Attach mock to app state
    client.app.state.content_service.client = mock_ai  # type: ignore[attr-defined]

    # 1. Generate poster
    idempotency_key = f"test-idemp-{uuid4().hex}"
    payload = {
        "brief": {
            "content_type": "poster",
            "topic": "What Is an API?",
            "content_pillar": "Computer Science Concepts",
            "target_audience": "Beginner BS students",
            "objective": "Explain an API with one analogy",
            "language": "roman_urdu",
            "fact_sensitivity": "LOW",
        },
        "idempotency_key": idempotency_key,
    }

    # Missing API key
    unauth = client.post("/api/v1/content/generate", json=payload)
    assert unauth.status_code == 401

    # With API key
    gen_res = client.post(
        "/api/v1/content/generate",
        headers={"X-TBOS-API-Key": TEST_API_KEY},
        json=payload,
    )
    assert gen_res.status_code == 200
    gen_data = gen_res.json()
    assert gen_data["status"] == "QA_PASSED"
    content_id = gen_data["content_id"]
    version_id = gen_data["version_id"]

    # 2. Idempotent replay
    replay = client.post(
        "/api/v1/content/generate",
        headers={"X-TBOS-API-Key": TEST_API_KEY},
        json=payload,
    )
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["content_id"] == content_id

    # 3. Get content
    get_res = client.get(f"/api/v1/content/{content_id}")
    assert get_res.status_code == 200
    assert get_res.json()["version_id"] == version_id

    # 4. List content
    list_res = client.get("/api/v1/content")
    assert list_res.status_code == 200
    assert list_res.json()["total"] >= 1

    # 5. List versions
    v_res = client.get(f"/api/v1/content/{content_id}/versions")
    assert v_res.status_code == 200
    assert len(v_res.json()) == 1

    # 6. Specific version
    v1_res = client.get(f"/api/v1/content/{content_id}/versions/1")
    assert v1_res.status_code == 200
    assert v1_res.json()["version_number"] == 1

    # 7. Rerun QA
    qa_res = client.post(
        f"/api/v1/content/{content_id}/qa",
        headers={"X-TBOS-API-Key": TEST_API_KEY},
    )
    assert qa_res.status_code == 200
    assert qa_res.json()["quality_report"]["passed"] is True

    # 8. Regenerate version
    mock_ai.generate_json.return_value = raw_content(ContentType.POSTER)
    regen_res = client.post(
        f"/api/v1/content/{content_id}/regenerate",
        headers={"X-TBOS-API-Key": TEST_API_KEY},
        json={"idempotency_key": f"regen-{uuid4().hex}", "reason": "Improve points"},
    )
    assert regen_res.status_code == 200
    assert regen_res.json()["version_number"] == 2

    # 9. Manual Revision
    rev_payload = {
        "idempotency_key": f"rev-{uuid4().hex}",
        "reason": "Correct typo",
        "content": poster().model_dump(mode="json"),
    }
    rev_res = client.post(
        f"/api/v1/content/{content_id}/revisions",
        headers={"X-TBOS-API-Key": TEST_API_KEY},
        json=rev_payload,
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["version_number"] == 3


def test_ai_status_and_smoke_test(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_ai = AsyncMock(spec=AiClient)
    mock_ai.active_model_name = "gemini-2.5-flash"
    mock_ai.last_provider_used = "gemini"
    mock_ai.fallback_occurred = False
    mock_ai.status.return_value = AiStatusResponse(
        enabled=True,
        configured=True,
        reachable=True,
        selected_model="gemini-2.5-flash",
        model_available=True,
        available_models=["gemini-2.5-flash"],
        detail="Primary Gemini ready",
    )
    mock_ai.generate_json.return_value = {
        "concept": "API",
        "roman_urdu": "API software applications ko connect karne ke liye use hoti hai.",
    }

    client.app.state.content_service.client = mock_ai  # type: ignore[attr-defined]

    # Status endpoint
    status_res = client.get("/api/v1/ai/status")
    assert status_res.status_code == 200
    assert status_res.json()["reachable"] is True
    assert status_res.json()["selected_model"] == "gemini-2.5-flash"

    # Smoke test endpoint
    smoke_res = client.post(
        "/api/v1/ai/smoke-test",
        headers={"X-TBOS-API-Key": TEST_API_KEY},
    )
    assert smoke_res.status_code == 200
    assert smoke_res.json()["success"] is True
    assert smoke_res.json()["roman_urdu_detected"] is True
