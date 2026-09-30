from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from tbos_renderer.api import dashboard
from tbos_renderer.config import Settings
from tbos_renderer.models import ContentItem, ContentVersion


@pytest.fixture
def sample_poster(engine: Engine) -> tuple[ContentItem, ContentVersion]:
    with Session(engine) as session, session.begin():
        item = ContentItem(
            external_key=f"test-dash-{uuid4().hex[:12]}",
            content_type="poster",
            primary_language="roman_urdu",
            content_pillar="Computer Science Concepts",
            topic="What Is an API?",
            status="RENDERED",
            risk_classification="low",
        )
        session.add(item)
        session.flush()

        version = ContentVersion(
            content_item_id=item.id,
            version_number=1,
            language="roman_urdu",
            title="What Is an API?",
            hook="API ko restaurant waiter samajhein!",
            cta="Follow TechBuilt!",
            caption="API explained easily.",
            hashtags=["#API", "#TechBuilt"],
            script_data={},
            lineage={},
        )
        session.add(version)
        session.flush()
        item_id, version_id = item.id, version.id

    with Session(engine) as session:
        return session.get(ContentItem, item_id), session.get(ContentVersion, version_id)  # type: ignore[return-value]


def test_dashboard_endpoint_serves_html(client: TestClient, settings: Settings) -> None:
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    text = resp.text
    assert "TECHBUILT" in text
    assert "OPEN SCHOOL" in text
    assert "Trigger Publishing" in text
    assert "Editorial Approval & Media Dashboard" in text
    expected_key = settings.internal_api_key.get_secret_value()
    assert expected_key in text


def test_dashboard_template_missing_raises_500(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        dashboard,
        "TEMPLATE_PATHS",
        [Path("/non/existent/path/dashboard.html")],
    )
    resp = client.get("/dashboard")
    assert resp.status_code == 500
    assert "Dashboard template" in resp.json()["detail"]


def test_storage_static_file_serving(
    client: TestClient,
    settings: Settings,
) -> None:
    render_dir = settings.shared_storage_path / "renders" / "test_item" / "v1"
    render_dir.mkdir(parents=True, exist_ok=True)
    test_poster = render_dir / "poster.png"
    test_poster.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    resp = client.get("/storage/renders/test_item/v1/poster.png")
    assert resp.status_code == 200
    assert "image/png" in resp.headers["content-type"]
    assert resp.content.startswith(b"\x89PNG")


def test_dashboard_approval_actions(
    client: TestClient,
    settings: Settings,
    sample_poster: tuple[ContentItem, ContentVersion],
) -> None:
    item, version = sample_poster
    headers = {"X-TBOS-API-Key": settings.internal_api_key.get_secret_value()}

    approve_payload = {
        "decision": "approved",
        "reviewer_reference": "web_admin",
        "notes": "Approved via Web Dashboard",
    }
    resp = client.post(f"/api/v1/content/{item.id}/approval", json=approve_payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["approval"]["decision"] == "approved"
    assert data["approval"]["reviewer_reference"] == "web_admin"
    assert len(data["publish_jobs"]) == 3

    reject_payload = {
        "decision": "rejected",
        "reviewer_reference": "web_admin",
        "notes": "Adjust audio level on scene 2",
    }
    resp_rej = client.post(
        f"/api/v1/content/{item.id}/approval", json=reject_payload, headers=headers
    )
    assert resp_rej.status_code == 200
    data_rej = resp_rej.json()
    assert data_rej["approval"]["decision"] == "rejected"
    assert data_rej["approval"]["notes"] == "Adjust audio level on scene 2"
