from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from tbos_renderer.content_engine.repository import ContentRepository
from tbos_renderer.content_engine.schemas import (
    ApprovalDecision,
    ApprovalRequest,
    CaptionPack,
    ContentLanguage,
    ContentMetadata,
    ContentType,
    Difficulty,
    FactSensitivity,
    HashtagPack,
    PosterContent,
)
from tbos_renderer.models import Approval, ContentItem, ContentStatus, ContentVersion, PublishJob


@pytest.fixture
def sample_poster(engine: Engine) -> tuple[ContentItem, ContentVersion]:
    with Session(engine) as session, session.begin():
        item = ContentItem(
            external_key=f"test-approval-{uuid4().hex[:12]}",
            content_type="poster",
            primary_language="roman_urdu",
            content_pillar="Computer Science Concepts",
            topic="What Is an API?",
            status="RENDERED",
            risk_classification="low",
        )
        session.add(item)
        session.flush()

        metadata = ContentMetadata(
            brand="techbuilt-open-school",
            content_type=ContentType.POSTER,
            language=ContentLanguage.ROMAN_URDU,
            content_pillar="Computer Science Concepts",
            topic="What Is an API?",
            target_audience="Beginner BS students",
            objective="Explain an API with one everyday analogy",
            tone="clear, practical",
            difficulty=Difficulty.BEGINNER,
            cta_type="save",
            fact_sensitivity=FactSensitivity.LOW,
            prompt_template_name="poster_educational",
            prompt_template_version=1,
            model_name="gemini-2.5-flash",
            generation_parameters={},
            content_hash="c" * 64,
        )
        content = PosterContent(
            metadata=metadata,
            headline="What Is an API? (Waiter Analogy)",
            subheadline="Software components ke darmiyan bridge",
            teaching_points=[
                "API ek waiter ki tarah request kitchen tak le jata hai.",
                "Client aur server direct communicate nahi karte.",
                "Security aur standard format ensure karta hai.",
            ],
            cta="Follow TechBuilt for daily concepts!",
            visual_concept="Waiter carrying menu between customer and kitchen",
            captions=CaptionPack(
                instagram="IG: APIs explained simply.",
                facebook="FB: APIs explained easily.",
                tiktok="TT: API quick analogy.",
            ),
            hashtags=HashtagPack(
                instagram=["#API", "#TechBuilt"],
                facebook=["#API", "#ComputerScience"],
                tiktok=["#API", "#LearnCoding"],
            ),
            alt_text="Infographic explaining APIs using a restaurant analogy.",
        )
        version = ContentVersion(
            content_item_id=item.id,
            version_number=1,
            language="roman_urdu",
            title="What Is an API? (Waiter Analogy)",
            hook="Kya aapko pata hai API waiter jaisa hota hai?",
            cta="Follow TechBuilt for daily concepts!",
            caption="API explained simply with the waiter analogy.",
            hashtags=["#API", "#TechBuilt"],
            scene_data={},
            script_data={"content": content.model_dump(mode="json")},
            lineage={"model": "gemini-2.5-flash"},
        )
        session.add(version)
        session.flush()

        item_id = item.id
        version_id = version.id

    with Session(engine) as session:
        return session.get(ContentItem, item_id), session.get(ContentVersion, version_id)  # type: ignore[return-value]


def test_repository_approve_success(
    engine: Engine, sample_poster: tuple[ContentItem, ContentVersion]
) -> None:
    item, version = sample_poster
    repo = ContentRepository(engine)

    req = ApprovalRequest(
        decision=ApprovalDecision.APPROVED,
        reviewer_reference="telegram:987654321 (@admin_editor)",
        notes="Looks great for publishing!",
    )
    result = repo.record_approval(item.id, req)

    assert result.content_id == item.id
    assert result.version_id == version.id
    assert result.status == ContentStatus.APPROVED.value
    assert result.approval.decision == "approved"
    assert result.approval.reviewer_reference == "telegram:987654321 (@admin_editor)"
    assert len(result.publish_jobs) == 3

    platforms = {j.platform for j in result.publish_jobs}
    assert platforms == {"facebook", "instagram", "tiktok_handoff"}

    # Verify database persistence
    with Session(engine) as session:
        db_item = session.get(ContentItem, item.id)
        assert db_item is not None
        assert db_item.status == "APPROVED"

        approvals = session.scalars(
            select(Approval).where(Approval.content_version_id == version.id)
        ).all()
        assert len(approvals) == 1
        assert approvals[0].decision == "approved"

        jobs = session.scalars(
            select(PublishJob).where(PublishJob.content_version_id == version.id)
        ).all()
        assert len(jobs) == 3
        # Check idempotency keys are unique
        keys = [j.idempotency_key for j in jobs]
        assert len(set(keys)) == 3


def test_repository_reject_changes_requested(
    engine: Engine, sample_poster: tuple[ContentItem, ContentVersion]
) -> None:
    item, version = sample_poster
    repo = ContentRepository(engine)

    req = ApprovalRequest(
        decision=ApprovalDecision.CHANGES_REQUESTED,
        reviewer_reference="telegram:987654321 (@admin_editor)",
        notes="Clarify point 2: explain JSON response format",
    )
    result = repo.record_approval(item.id, req)

    assert result.status == ContentStatus.CHANGES_REQUESTED.value
    assert result.approval.decision == "changes_requested"
    assert len(result.publish_jobs) == 0

    with Session(engine) as session:
        db_item = session.get(ContentItem, item.id)
        assert db_item is not None
        assert db_item.status == "CHANGES_REQUESTED"

        jobs = session.scalars(
            select(PublishJob).where(PublishJob.content_version_id == version.id)
        ).all()
        assert len(jobs) == 0


def test_api_approval_endpoints(
    client: TestClient, engine: Engine, sample_poster: tuple[ContentItem, ContentVersion]
) -> None:
    item, version = sample_poster
    headers = {"X-TBOS-API-Key": "test-internal-api-key-32-characters"}

    # Unauthenticated request fails
    unauth = client.post(
        f"/api/v1/content/{item.id}/approval",
        json={
            "decision": "approved",
            "reviewer_reference": "telegram:123",
        },
    )
    assert unauth.status_code == 401

    # Authenticated approval succeeds
    resp = client.post(
        f"/api/v1/content/{item.id}/approval",
        headers=headers,
        json={
            "decision": "approved",
            "reviewer_reference": "telegram:123456 (@reviewer)",
            "notes": "Quality score 95/100, verified.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "APPROVED"
    assert len(data["publish_jobs"]) == 3

    # Query approvals list
    list_resp = client.get(f"/api/v1/content/{item.id}/approvals")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["decision"] == "approved"

    # Query publish jobs list
    jobs_resp = client.get(f"/api/v1/content/{item.id}/publish-jobs")
    assert jobs_resp.status_code == 200
    assert len(jobs_resp.json()) == 3
