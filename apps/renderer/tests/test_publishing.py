from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from tbos_renderer.config import Settings
from tbos_renderer.content_engine.repository import ContentRepository
from tbos_renderer.content_engine.schemas import (
    CaptionPack,
    ContentLanguage,
    ContentMetadata,
    ContentType,
    Difficulty,
    FactSensitivity,
    HashtagPack,
    ReelContent,
    ReelScene,
)
from tbos_renderer.models import (
    Asset,
    ContentItem,
    ContentStatus,
    ContentVersion,
    PublishedPost,
    PublishJob,
)
from tbos_renderer.publishing.meta import (
    MetaContainerProcessingError,
    MetaGraphPublisher,
    MetaPublishingError,
    MetaRateLimitError,
)
from tbos_renderer.publishing.schemas import (
    HandoffPackageResult,
    PublishResult,
)
from tbos_renderer.publishing.service import PublishingService
from tbos_renderer.publishing.tiktok import TikTokHandoffPackager

# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def publishing_settings(tmp_path: Path, settings: Settings) -> Settings:
    storage = tmp_path / "storage"
    storage.mkdir(parents=True, exist_ok=True)
    return settings.model_copy(
        update={
            "shared_storage_path": storage,
            "meta_app_id": "test_app_id",
            "meta_app_secret": SecretStr("test_app_secret"),
            "meta_page_id": "100200300",
            "meta_instagram_account_id": "400500600",
            "meta_access_token": SecretStr("EAAG_test_meta_access_token"),
            "meta_api_version": "v22.0",
            "meta_api_base_url": "https://graph.facebook.com",
            "telegram_bot_token": SecretStr("123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"),
            "telegram_approval_chat_id": "-1001234567890",
        }
    )


@pytest.fixture
def sample_approved_content(
    engine: Engine, tmp_path: Path
) -> tuple[ContentItem, ContentVersion, Asset, Asset]:
    """Sets up an approved content item with rendered media assets on disk."""
    dummy_poster = tmp_path / "renders" / "poster.png"
    dummy_poster.parent.mkdir(parents=True, exist_ok=True)
    dummy_poster.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    dummy_reel = tmp_path / "renders" / "reel.mp4"
    dummy_reel.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)

    dummy_thumb = tmp_path / "renders" / "thumb.png"
    dummy_thumb.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    with Session(engine) as session, session.begin():
        item = ContentItem(
            external_key=f"test-pub-{uuid4().hex[:12]}",
            content_type="reel",
            primary_language="roman_urdu",
            content_pillar="AI Tools and Practical AI",
            topic="What Is an AI Hallucination?",
            status="APPROVED",
            risk_classification="low",
        )
        session.add(item)
        session.flush()

        metadata = ContentMetadata(
            brand="techbuilt-open-school",
            content_type=ContentType.REEL,
            language=ContentLanguage.ROMAN_URDU,
            content_pillar="AI Tools and Practical AI",
            topic="What Is an AI Hallucination?",
            target_audience="Beginner Python students",
            objective="Explain hallucinations simply",
            tone="clear, cautious",
            difficulty=Difficulty.BEGINNER,
            cta_type="save",
            fact_sensitivity=FactSensitivity.LOW,
            prompt_template_name="reel_educational",
            prompt_template_version=1,
            model_name="gemini-2.5-flash",
            generation_parameters={},
            content_hash="d" * 64,
        )

        scenes = [
            ReelScene(
                scene_number=i,
                duration_seconds=5.0,
                narration=f"Scene {i} narration explaining AI hallucination concept clearly.",
                on_screen_text=f"Scene {i}: AI Concept",
                visual_direction=f"Scene {i} animation visual",
            )
            for i in range(1, 7)
        ]

        reel_content = ReelContent(
            metadata=metadata,
            cover_title="AI Hallucination",
            hook="AI par andha aitbaar mat karein!",
            target_duration_seconds=30,
            narration=" ".join(s.narration for s in scenes),
            scenes=scenes,
            cta="Follow TechBuilt for daily AI concepts!",
            captions=CaptionPack(
                instagram="IG: Understand AI hallucinations in 30 seconds.",
                facebook="FB: Why AI produces confident false facts.",
                tiktok="TT: Watch out for AI hallucinations.",
            ),
            hashtags=HashtagPack(
                instagram=["#AI", "#TechBuilt"],
                facebook=["#AI", "#ArtificialIntelligence"],
                tiktok=["#AI", "#LearnOnTikTok"],
            ),
            accessibility_description="AI hallucinations explained with 6 scenes.",
        )

        version = ContentVersion(
            content_item_id=item.id,
            version_number=1,
            language="roman_urdu",
            title="What Is an AI Hallucination?",
            hook="AI par andha aitbaar mat karein!",
            cta="Follow TechBuilt for daily AI concepts!",
            caption="AI hallucinations explained simply.",
            hashtags=["#AI", "#TechBuilt", "#LearnAI"],
            scene_data={"scenes": [s.model_dump() for s in scenes]},
            script_data={"content": reel_content.model_dump(mode="json")},
            lineage={"model": "gemini-2.5-flash"},
        )
        session.add(version)
        session.flush()

        reel_asset = Asset(
            content_version_id=version.id,
            asset_type="reel",
            local_path=str(dummy_reel),
            mime_type="video/mp4",
            sha256="e" * 64,
            temporary_public_url="https://cdn.example.com/assets/reel.mp4",
        )
        thumb_asset = Asset(
            content_version_id=version.id,
            asset_type="thumbnail",
            local_path=str(dummy_thumb),
            mime_type="image/png",
            sha256="f" * 64,
        )
        session.add_all([reel_asset, thumb_asset])
        session.flush()

        item_id = item.id
        version_id = version.id
        reel_asset_id = reel_asset.id
        thumb_asset_id = thumb_asset.id

    with Session(engine) as session:
        return (
            session.get(ContentItem, item_id),  # type: ignore[return-value]
            session.get(ContentVersion, version_id),  # type: ignore[return-value]
            session.get(Asset, reel_asset_id),  # type: ignore[return-value]
            session.get(Asset, thumb_asset_id),  # type: ignore[return-value]
        )


# ---------------------------------------------------------------------------
# 1. MetaGraphPublisher Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_meta_publisher_resolve_token_error(publishing_settings: Settings) -> None:
    settings_no_token = publishing_settings.model_copy(update={"meta_access_token": None})
    publisher = MetaGraphPublisher(settings_no_token)
    with pytest.raises(MetaPublishingError, match="META_ACCESS_TOKEN is not configured"):
        publisher._resolve_access_token()


@pytest.mark.asyncio
async def test_meta_publisher_default_client(publishing_settings: Settings) -> None:
    publisher = MetaGraphPublisher(publishing_settings)
    client = await publisher._get_client()
    assert isinstance(client, httpx.AsyncClient)
    await client.aclose()


@pytest.mark.asyncio
async def test_meta_publisher_facebook_missing_page_id(
    publishing_settings: Settings, tmp_path: Path
) -> None:
    settings_no_page = publishing_settings.model_copy(update={"meta_page_id": None})
    publisher = MetaGraphPublisher(settings_no_page)
    dummy_file = tmp_path / "image.png"
    dummy_file.write_bytes(b"dummy")
    with pytest.raises(MetaPublishingError, match="META_PAGE_ID is not configured"):
        await publisher.publish_facebook(dummy_file, caption="Test")


@pytest.mark.asyncio
async def test_meta_publisher_facebook_missing_file(publishing_settings: Settings) -> None:
    publisher = MetaGraphPublisher(publishing_settings)
    with pytest.raises(FileNotFoundError, match="Media file not found"):
        await publisher.publish_facebook("nonexistent.png", caption="Test")


@pytest.mark.asyncio
async def test_meta_publisher_publish_facebook_photo_success(
    publishing_settings: Settings, tmp_path: Path
) -> None:
    dummy_photo = tmp_path / "photo.png"
    dummy_photo.write_bytes(b"\x89PNG\r\n\x1a\n")

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "/100200300/photos" in str(request.url)
        assert request.headers.get("Authorization") == "Bearer EAAG_test_meta_access_token"
        return httpx.Response(200, json={"id": "photo_12345", "post_id": "100200300_98765"})

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)
    publisher = MetaGraphPublisher(publishing_settings, http_client=client)

    result = await publisher.publish_facebook(
        dummy_photo, caption="Learn Python easily!", is_video=False
    )

    assert result.platform == "facebook"
    assert result.external_post_id == "100200300_98765"
    assert result.permalink == "https://www.facebook.com/100200300_98765"
    assert result.published_at is not None
    assert result.metadata["is_video"] is False


@pytest.mark.asyncio
async def test_meta_publisher_publish_facebook_video_success(
    publishing_settings: Settings, tmp_path: Path
) -> None:
    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_bytes(b"\x00\x00\x00\x18ftyp")

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "/100200300/videos" in str(request.url)
        return httpx.Response(200, json={"id": "video_999888"})

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)
    publisher = MetaGraphPublisher(publishing_settings, http_client=client)

    result = await publisher.publish_facebook(
        dummy_video, caption="AI Hallucination Reel", is_video=True
    )

    assert result.platform == "facebook"
    assert result.external_post_id == "video_999888"
    assert "videos/video_999888" in result.permalink
    assert result.metadata["is_video"] is True


@pytest.mark.asyncio
async def test_meta_publisher_instagram_missing_account(publishing_settings: Settings) -> None:
    settings_no_ig = publishing_settings.model_copy(update={"meta_instagram_account_id": None})
    publisher = MetaGraphPublisher(settings_no_ig)
    with pytest.raises(MetaPublishingError, match="META_INSTAGRAM_ACCOUNT_ID is not configured"):
        await publisher.publish_instagram("https://example.com/img.png", caption="Test")


@pytest.mark.asyncio
async def test_meta_publisher_publish_instagram_reel_success(
    publishing_settings: Settings,
) -> None:
    calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        url_str = str(request.url)

        if url_str.endswith("/400500600/media") and request.method == "POST":
            return httpx.Response(200, json={"id": "container_reel_001"})
        elif "/container_reel_001" in url_str and request.method == "GET":
            return httpx.Response(200, json={"status_code": "FINISHED", "id": "container_reel_001"})
        elif url_str.endswith("/400500600/media_publish") and request.method == "POST":
            return httpx.Response(200, json={"id": "ig_media_reel_999"})
        elif "/ig_media_reel_999" in url_str and request.method == "GET":
            return httpx.Response(
                200, json={"permalink": "https://www.instagram.com/reel/Cxyz999/"}
            )
        return httpx.Response(404, json={"error": f"Not Found: {url_str}"})

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)
    publisher = MetaGraphPublisher(publishing_settings, http_client=client)

    result = await publisher.publish_instagram(
        media_url="https://cdn.example.com/reel.mp4",
        caption="Reel Caption",
        is_video=True,
        poll_interval_seconds=0.01,
    )

    assert result.platform == "instagram"
    assert result.external_post_id == "ig_media_reel_999"
    assert result.permalink == "https://www.instagram.com/reel/Cxyz999/"
    assert result.metadata["container_id"] == "container_reel_001"
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_meta_publisher_instagram_container_error(publishing_settings: Settings) -> None:
    def mock_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if url_str.endswith("/media") and request.method == "POST":
            return httpx.Response(200, json={"id": "container_fail"})
        elif "/container_fail" in url_str:
            return httpx.Response(200, json={"status_code": "ERROR"})
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)
    publisher = MetaGraphPublisher(publishing_settings, http_client=client)

    with pytest.raises(MetaContainerProcessingError, match="failed with status: ERROR"):
        await publisher.publish_instagram(
            media_url="https://example.com/bad.png",
            caption="Fail",
            poll_interval_seconds=0.01,
        )


@pytest.mark.asyncio
async def test_meta_publisher_retry_on_429_success(publishing_settings: Settings) -> None:
    attempts = 0

    def mock_handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, json={"error": "Rate limit exceeded"})
        return httpx.Response(200, json={"id": "photo_recovered", "post_id": "post_recovered"})

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)
    publisher = MetaGraphPublisher(
        publishing_settings, http_client=client, max_retries=3, initial_backoff=0.01
    )

    dummy_file = Path("dummy.png")
    dummy_file.write_bytes(b"dummy")
    try:
        result = await publisher.publish_facebook(dummy_file, caption="Retry test")
        assert result.external_post_id == "post_recovered"
        assert attempts == 2
    finally:
        dummy_file.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_meta_publisher_retry_on_500_server_error(publishing_settings: Settings) -> None:
    attempts = 0

    def mock_handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(500, text="Internal Server Error")
        return httpx.Response(200, json={"id": "photo_500_recovered", "post_id": "post_500"})

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)
    publisher = MetaGraphPublisher(
        publishing_settings, http_client=client, max_retries=3, initial_backoff=0.01
    )

    dummy = Path("dummy_500.png")
    dummy.write_bytes(b"dummy")
    try:
        result = await publisher.publish_facebook(dummy, caption="500 test")
        assert result.external_post_id == "post_500"
        assert attempts == 2
    finally:
        dummy.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_meta_publisher_retry_exhausted_rate_limit(publishing_settings: Settings) -> None:
    def mock_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "Too many requests"})

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)
    publisher = MetaGraphPublisher(
        publishing_settings, http_client=client, max_retries=2, initial_backoff=0.01
    )

    dummy = Path("dummy_rate.png")
    dummy.write_bytes(b"dummy")
    try:
        with pytest.raises(MetaRateLimitError, match="rate limit exceeded"):
            await publisher.publish_facebook(dummy, caption="Rate limit test")
    finally:
        dummy.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_meta_publisher_api_returned_error(publishing_settings: Settings) -> None:
    def mock_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {"message": "Invalid OAuth token", "code": 190, "type": "OAuthException"}
            },
        )

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)
    publisher = MetaGraphPublisher(publishing_settings, http_client=client, max_retries=1)

    dummy = Path("dummy_oauth.png")
    dummy.write_bytes(b"dummy")
    try:
        with pytest.raises(MetaPublishingError, match="Invalid OAuth token"):
            await publisher.publish_facebook(dummy, caption="OAuth test")
    finally:
        dummy.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 2. TikTokHandoffPackager Tests
# ---------------------------------------------------------------------------


def test_tiktok_handoff_packager_creates_bundle(
    publishing_settings: Settings,
    sample_approved_content: tuple[ContentItem, ContentVersion, Asset, Asset],
) -> None:
    item, version, reel_asset, thumb_asset = sample_approved_content
    packager = TikTokHandoffPackager(publishing_settings)

    result = packager.create_handoff_package(
        content_id=item.id,
        version=version,
        video_source_path=reel_asset.local_path,
        thumbnail_source_path=thumb_asset.local_path,
    )

    assert isinstance(result, HandoffPackageResult)
    assert result.content_id == item.id
    assert result.version_id == version.id

    bundle_dir = Path(result.bundle_dir)
    assert bundle_dir.exists()
    assert (bundle_dir / "reel.mp4").exists()
    assert (bundle_dir / "cover.png").exists()
    assert (bundle_dir / "caption.txt").exists()
    assert (bundle_dir / "timing_and_sounds.json").exists()

    caption_text = (bundle_dir / "caption.txt").read_text(encoding="utf-8")
    assert version.hook in caption_text
    assert "#AI" in caption_text

    timing_data = json.loads((bundle_dir / "timing_and_sounds.json").read_text(encoding="utf-8"))
    assert timing_data["title"] == version.title
    assert "recommended_posting_slot" in timing_data

    assert "TikTok Handoff Package Ready" in result.telegram_message
    assert result.ready_caption in result.telegram_message


def test_tiktok_handoff_packager_fallback_cover(
    publishing_settings: Settings,
    sample_approved_content: tuple[ContentItem, ContentVersion, Asset, Asset],
) -> None:
    item, version, reel_asset, _ = sample_approved_content
    packager = TikTokHandoffPackager(publishing_settings)

    # Calling without thumbnail source triggers deterministic cover generator
    result = packager.create_handoff_package(
        content_id=item.id,
        version=version,
        video_source_path=reel_asset.local_path,
        thumbnail_source_path=None,
    )

    cover_path = Path(result.thumbnail_path)
    assert cover_path.exists()
    assert cover_path.stat().st_size > 0


# ---------------------------------------------------------------------------
# 3. PublishingService Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def publishing_service(
    engine: Engine,
    publishing_settings: Settings,
) -> tuple[PublishingService, ContentRepository]:
    repo = ContentRepository(engine)
    meta_mock = MagicMock(spec=MetaGraphPublisher)
    tiktok_packager = TikTokHandoffPackager(publishing_settings)
    service = PublishingService(
        settings=publishing_settings,
        repository=repo,
        meta_publisher=meta_mock,
        tiktok_packager=tiktok_packager,
    )
    return service, repo


@pytest.mark.asyncio
async def test_publishing_service_execute_nonexistent_job(
    publishing_service: tuple[PublishingService, ContentRepository],
) -> None:
    service, _ = publishing_service
    with pytest.raises(ValueError, match="not found"):
        await service.execute_publish_job(uuid4())


@pytest.mark.asyncio
async def test_publishing_service_full_lifecycle_success(
    engine: Engine,
    publishing_service: tuple[PublishingService, ContentRepository],
    sample_approved_content: tuple[ContentItem, ContentVersion, Asset, Asset],
) -> None:
    service, repo = publishing_service
    item, version, _, _ = sample_approved_content

    # Create 3 publish jobs in DB (as created by approval workflow)
    with Session(engine) as session, session.begin():
        fb_job = PublishJob(
            content_version_id=version.id,
            platform="facebook",
            state="pending",
            idempotency_key=f"fb-{uuid4()}",
        )
        ig_job = PublishJob(
            content_version_id=version.id,
            platform="instagram",
            state="pending",
            idempotency_key=f"ig-{uuid4()}",
        )
        tt_job = PublishJob(
            content_version_id=version.id,
            platform="tiktok_handoff",
            state="pending",
            idempotency_key=f"tt-{uuid4()}",
        )
        session.add_all([fb_job, ig_job, tt_job])
        session.flush()
        fb_id, ig_id, tt_id = fb_job.id, ig_job.id, tt_job.id

    # Configure mock meta publisher
    service.meta_publisher.publish_facebook = AsyncMock(  # type: ignore[method-assign]
        return_value=PublishResult(
            platform="facebook",
            external_post_id="fb_post_1001",
            permalink="https://www.facebook.com/fb_post_1001",
            published_at=datetime.now(UTC),
        )
    )
    service.meta_publisher.publish_instagram = AsyncMock(  # type: ignore[method-assign]
        return_value=PublishResult(
            platform="instagram",
            external_post_id="ig_post_2002",
            permalink="https://www.instagram.com/p/ig_post_2002",
            published_at=datetime.now(UTC),
        )
    )

    # 1. Execute Facebook Job
    res_fb = await service.execute_publish_job(fb_id)
    assert res_fb.status == "succeeded"
    assert res_fb.platform == "facebook"
    assert res_fb.external_post_id == "fb_post_1001"

    # Verify idempotency: executing fb_id again returns existing without re-dispatching
    service.meta_publisher.publish_facebook.reset_mock()
    res_fb_idem = await service.execute_publish_job(fb_id)
    assert res_fb_idem.status == "succeeded"
    assert res_fb_idem.external_post_id == "fb_post_1001"
    service.meta_publisher.publish_facebook.assert_not_called()

    # 2. Execute Instagram Job
    res_ig = await service.execute_publish_job(ig_id)
    assert res_ig.status == "succeeded"
    assert res_ig.platform == "instagram"

    # At this point, 2 of 3 jobs succeeded; content item status should still be PUBLISHING
    with Session(engine) as session:
        cur_item = session.get(ContentItem, item.id)
        assert cur_item is not None
        assert cur_item.status == ContentStatus.PUBLISHING.value

    # 3. Execute TikTok Handoff Job
    res_tt = await service.execute_publish_job(tt_id)
    assert res_tt.status == "succeeded"
    assert res_tt.platform == "tiktok_handoff"

    # All jobs succeeded! Content item status must now be PUBLISHED
    with Session(engine) as session:
        cur_item = session.get(ContentItem, item.id)
        assert cur_item is not None
        assert cur_item.status == ContentStatus.PUBLISHED.value

        # Verify published_posts table has 3 rows
        published = session.scalars(select(PublishedPost)).all()
        assert len(published) == 3
        platforms = {p.platform for p in published}
        assert platforms == {"facebook", "instagram", "tiktok_handoff"}


@pytest.mark.asyncio
async def test_publishing_service_job_failure_and_retry(
    engine: Engine,
    publishing_service: tuple[PublishingService, ContentRepository],
    sample_approved_content: tuple[ContentItem, ContentVersion, Asset, Asset],
) -> None:
    service, repo = publishing_service
    _, version, _, _ = sample_approved_content

    with Session(engine) as session, session.begin():
        job = PublishJob(
            content_version_id=version.id,
            platform="facebook",
            state="pending",
            idempotency_key=f"fail-{uuid4()}",
        )
        session.add(job)
        session.flush()
        job_id = job.id

    # Mock failure
    service.meta_publisher.publish_facebook = AsyncMock(  # type: ignore[method-assign]
        side_effect=Exception("Transient network outage")
    )

    # First attempt: should go to retry_wait
    res = await service.execute_publish_job(job_id)
    assert res.status == "retry_wait"
    assert "Transient network outage" in (res.error or "")

    with Session(engine) as session:
        db_job = session.get(PublishJob, job_id)
        assert db_job is not None
        assert db_job.state == "retry_wait"
        assert db_job.retry_count == 1
        assert db_job.next_retry_at is not None

    # Exhaust retries to reach 'failed'
    service.max_job_retries = 2
    res2 = await service.execute_publish_job(job_id)
    assert res2.status == "failed"

    with Session(engine) as session:
        db_job = session.get(PublishJob, job_id)
        assert db_job is not None
        assert db_job.state == "failed"
        assert db_job.retry_count == 2


@pytest.mark.asyncio
async def test_publishing_service_process_pending_jobs(
    engine: Engine,
    publishing_service: tuple[PublishingService, ContentRepository],
    sample_approved_content: tuple[ContentItem, ContentVersion, Asset, Asset],
) -> None:
    service, _ = publishing_service
    _, version, _, _ = sample_approved_content

    with Session(engine) as session, session.begin():
        job1 = PublishJob(
            content_version_id=version.id,
            platform="tiktok_handoff",
            state="pending",
            idempotency_key=f"p1-{uuid4()}",
        )
        job2 = PublishJob(
            content_version_id=version.id,
            platform="tiktok_handoff",
            state="pending",
            idempotency_key=f"p2-{uuid4()}",
        )
        session.add_all([job1, job2])

    results = await service.process_pending_jobs()
    assert len(results) >= 2
    assert all(r.status == "succeeded" for r in results)


def test_publishing_service_list_published_posts(
    engine: Engine,
    publishing_service: tuple[PublishingService, ContentRepository],
) -> None:
    service, _ = publishing_service
    with Session(engine) as session, session.begin():
        job_id = uuid4()
        post = PublishedPost(
            publish_job_id=job_id,
            platform="facebook",
            external_post_id="fb_123",
            permalink="https://facebook.com/fb_123",
            published_at=datetime.now(UTC),
        )
        session.add(post)

    posts = service.list_published_posts()
    assert len(posts) >= 1
    assert posts[0].platform == "facebook"

    fb_posts = service.list_published_posts(platform="facebook")
    assert len(fb_posts) >= 1

    ig_posts = service.list_published_posts(platform="instagram")
    assert len(ig_posts) == 0


def test_publishing_service_tiktok_handoff_helper(
    publishing_service: tuple[PublishingService, ContentRepository],
    sample_approved_content: tuple[ContentItem, ContentVersion, Asset, Asset],
) -> None:
    service, _ = publishing_service
    item, _, _, _ = sample_approved_content

    result = service.create_tiktok_handoff_for_content(item.id)
    assert result.content_id == item.id
    assert Path(result.bundle_dir).exists()

    with pytest.raises(ValueError, match="not found"):
        service.create_tiktok_handoff_for_content(uuid4())


# ---------------------------------------------------------------------------
# 4. API Endpoint Integration Tests
# ---------------------------------------------------------------------------


def test_api_publishing_auth_required(client: TestClient) -> None:
    resp = client.post("/api/v1/publishing/process-pending")
    assert resp.status_code == 401


def test_api_publishing_execute_job_not_found(client: TestClient) -> None:
    headers = {"X-TBOS-API-Key": "test-internal-api-key-32-characters"}
    fake_id = str(uuid4())
    resp = client.post(f"/api/v1/publishing/jobs/{fake_id}/execute", headers=headers)
    assert resp.status_code == 404


def test_api_publishing_process_pending(client: TestClient) -> None:
    headers = {"X-TBOS-API-Key": "test-internal-api-key-32-characters"}
    resp = client.post("/api/v1/publishing/process-pending", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_api_publishing_tiktok_handoff_endpoint(
    client: TestClient,
    sample_approved_content: tuple[ContentItem, ContentVersion, Asset, Asset],
) -> None:
    headers = {"X-TBOS-API-Key": "test-internal-api-key-32-characters"}
    item, _, _, _ = sample_approved_content

    resp = client.post(f"/api/v1/publishing/tiktok-handoff/{item.id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["content_id"] == str(item.id)
    assert "bundle_dir" in data

    # Non-existent content returns 404
    resp_404 = client.post(f"/api/v1/publishing/tiktok-handoff/{uuid4()}", headers=headers)
    assert resp_404.status_code == 404


def test_api_publishing_list_published(client: TestClient) -> None:
    resp = client.get("/api/v1/publishing/published")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    resp_fb = client.get("/api/v1/publishing/published?platform=facebook")
    assert resp_fb.status_code == 200
    assert isinstance(resp_fb.json(), list)
