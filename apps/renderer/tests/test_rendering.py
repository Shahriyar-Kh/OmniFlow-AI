from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from tbos_renderer.config import Settings, load_brand_config
from tbos_renderer.content_engine.exceptions import ContentNotFoundError
from tbos_renderer.content_engine.repository import ContentRepository
from tbos_renderer.content_engine.schemas import (
    CaptionPack,
    ContentLanguage,
    ContentMetadata,
    ContentType,
    Difficulty,
    FactSensitivity,
    HashtagPack,
    PosterContent,
    ReelContent,
    ReelScene,
)
from tbos_renderer.models import Asset, ContentItem, ContentVersion
from tbos_renderer.rendering.poster import PosterRenderer
from tbos_renderer.rendering.service import RenderingService
from tbos_renderer.rendering.typography import get_font, get_text_dimensions, wrap_text
from tbos_renderer.rendering.video import FfmpegVideoCompositor, VideoResult
from tbos_renderer.rendering.voiceover import (
    EdgeTtsVoiceoverEngine,
    VoiceoverResult,
)


@pytest.fixture
def sample_poster_content() -> PosterContent:
    metadata = ContentMetadata(
        brand="techbuilt-open-school",
        content_type=ContentType.POSTER,
        language=ContentLanguage.ROMAN_URDU,
        content_pillar="Python and Automation",
        topic="What Is a Python Variable?",
        target_audience="Beginner Python learners",
        objective="Store and reuse a value",
        tone="clear, practical",
        difficulty=Difficulty.BEGINNER,
        cta_type="code",
        fact_sensitivity=FactSensitivity.LOW,
        prompt_template_name="poster_educational",
        prompt_template_version=1,
        model_name="gemini-2.5-flash",
        generation_parameters={},
        content_hash="a" * 64,
    )
    return PosterContent(
        metadata=metadata,
        headline="Python Variable: Memory Box",
        subheadline="Values ko store aur manipulate karein",
        teaching_points=[
            "Variable memory mein value point karta hai.",
            "Dynamic typing ki wajah se type specify karna zaroori nahi.",
            "Descriptive variable names readable code banate hain.",
        ],
        cta="Save this post for your coding practice!",
        visual_concept="A labelled memory box holding an integer value",
        captions=CaptionPack(
            instagram="IG: Python variables explained simply.",
            facebook="FB: Learn Python variables easily.",
            tiktok="TT: Python variable quick guide.",
        ),
        hashtags=HashtagPack(instagram=[], facebook=[], tiktok=[]),
        alt_text="Infographic explaining what a Python variable represents.",
    )


@pytest.fixture
def sample_reel_content() -> ReelContent:
    metadata = ContentMetadata(
        brand="techbuilt-open-school",
        content_type=ContentType.REEL,
        language=ContentLanguage.ROMAN_URDU,
        content_pillar="AI Tools and Practical AI",
        topic="What Is an AI Hallucination?",
        target_audience="Students using AI tools",
        objective="Recognize fluent AI errors",
        tone="clear, cautious",
        difficulty=Difficulty.BEGINNER,
        cta_type="save",
        fact_sensitivity=FactSensitivity.LOW,
        prompt_template_name="reel_educational",
        prompt_template_version=1,
        model_name="gemini-2.5-flash",
        generation_parameters={},
        content_hash="b" * 64,
    )
    scenes = [
        ReelScene(
            scene_number=1,
            duration_seconds=5.0,
            narration="Kya AI hamesha sach bolta hai? Bilkul nahi.",
            on_screen_text="AI hamesha sach nahi bolta!",
            visual_direction="Glitch effect on AI bot text",
        ),
        ReelScene(
            scene_number=2,
            duration_seconds=5.0,
            narration="Isko tech world mein AI hallucination kehte hain.",
            on_screen_text="Isay AI Hallucination kehte hain",
            visual_direction="Definition highlight",
        ),
        ReelScene(
            scene_number=3,
            duration_seconds=5.0,
            narration="AI confidence ke saath ghalat facts create karta hai.",
            on_screen_text="Confidence ke saath ghalat facts!",
            visual_direction="Warning icon pulsing",
        ),
        ReelScene(
            scene_number=4,
            duration_seconds=5.0,
            narration="Kyunki models statistics predict karte hain facts nahi.",
            on_screen_text="Predictions, Not Real Understanding",
            visual_direction="Probability bars",
        ),
        ReelScene(
            scene_number=5,
            duration_seconds=5.0,
            narration="Is liye facts ko verify karna bohot zaroori hai.",
            on_screen_text="Har important fact verify karein",
            visual_direction="Checklist checkmarks",
        ),
        ReelScene(
            scene_number=6,
            duration_seconds=5.0,
            narration="TechBuilt Open School ko follow karein practical tech ke liye.",
            on_screen_text="Follow TechBuilt Open School!",
            visual_direction="TBOS brand card with follow button",
        ),
    ]
    return ReelContent(
        metadata=metadata,
        cover_title="AI Hallucination Explained",
        hook="Kya AI hamesha sach bolta hai?",
        target_duration_seconds=30,
        narration=" ".join(s.narration for s in scenes),
        scenes=scenes,
        cta="Follow TechBuilt Open School for practical learning!",
        captions=CaptionPack(
            instagram="IG: Understand AI hallucinations in 30 seconds.",
            facebook="FB: Why AI makes up false facts.",
            tiktok="TT: Watch out for AI hallucinations.",
        ),
        hashtags=HashtagPack(instagram=[], facebook=[], tiktok=[]),
        accessibility_description="Educational reel explaining AI hallucinations.",
    )


# ---------------------------------------------------------------------------
# 1. Typography Tests
# ---------------------------------------------------------------------------


def test_typography_font_and_measurements() -> None:
    font_regular = get_font(24, bold=False)
    font_bold = get_font(32, bold=True)
    assert font_regular is not None
    assert font_bold is not None

    w, h = get_text_dimensions("Hello TBOS", font_regular)
    assert w > 0
    assert h > 0

    assert get_text_dimensions("", font_regular) == (0, 0)


def test_typography_wrap_text() -> None:
    font = get_font(24)
    text = "TechBuilt Open School provides free practical technology education for students."
    lines = wrap_text(text, font, max_width=200)
    assert len(lines) > 1
    assert " ".join(lines) == text

    assert wrap_text("", font, 200) == []
    assert wrap_text("Short", font, 1000) == ["Short"]


# ---------------------------------------------------------------------------
# 2. PosterRenderer Tests
# ---------------------------------------------------------------------------


def test_poster_renderer_image_dimensions(
    settings: Settings, sample_poster_content: PosterContent
) -> None:
    brand = load_brand_config(settings.brand_config_path)
    renderer = PosterRenderer(brand)
    img = renderer.render(sample_poster_content)

    assert isinstance(img, Image.Image)
    assert img.size == (1080, 1080)


def test_poster_renderer_render_to_file(
    tmp_path: Path, settings: Settings, sample_poster_content: PosterContent
) -> None:
    brand = load_brand_config(settings.brand_config_path)
    renderer = PosterRenderer(brand)
    target = tmp_path / "renders" / "poster.png"

    result = renderer.render_to_file(sample_poster_content, target)
    assert target.exists()
    assert result["width"] == 1080
    assert result["height"] == 1080
    assert len(result["sha256"]) == 64
    assert result["mime_type"] == "image/png"


def test_poster_renderer_hybrid_template_and_quiz(
    tmp_path: Path, settings: Settings, sample_poster_content: PosterContent
) -> None:
    from tbos_renderer.content_engine.schemas import PracticeQuestion

    # Test with custom code snippet and practice quiz
    sample_poster_content.code_snippet = "x = 42\nprint(x)"
    sample_poster_content.code_output = "42"
    sample_poster_content.practice_question = PracticeQuestion(
        question="What is x?",
        options=["A) 42", "B) None", "C) Error", "D) 0"],
        answer="A) 42",
        explanation="x is 42",
    )

    # 1. Without template (dynamic luxury canvas)
    empty_templates = tmp_path / "no_templates"
    empty_templates.mkdir()
    renderer_dynamic = PosterRenderer(templates_dir=empty_templates)
    img_dynamic = renderer_dynamic.render(sample_poster_content)
    assert img_dynamic.size == (1080, 1080)

    # 2. With template image
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    template_img = Image.new("RGB", (1080, 1080), color="#0B1120")
    template_img.save(templates_dir / "master_template.png")

    renderer_template = PosterRenderer(templates_dir=templates_dir)
    img_template = renderer_template.render(sample_poster_content)
    assert img_template.size == (1080, 1080)


# ---------------------------------------------------------------------------
# 3. VoiceoverEngine Tests
# ---------------------------------------------------------------------------


def test_voiceover_voice_resolution() -> None:
    engine = EdgeTtsVoiceoverEngine()
    assert engine.resolve_voice(ContentLanguage.ROMAN_URDU) == "ur-PK-UzmaNeural"
    assert engine.resolve_voice(ContentLanguage.SIMPLE_ENGLISH) == "en-US-ChristopherNeural"
    assert engine.resolve_voice("unknown") == "en-US-ChristopherNeural"
    assert engine.resolve_voice("roman_urdu", override="custom-voice") == "custom-voice"


def test_voiceover_probe_duration(tmp_path: Path) -> None:
    engine = EdgeTtsVoiceoverEngine()
    dummy_file = tmp_path / "dummy.mp3"
    dummy_file.write_bytes(b"test audio content")

    with patch("shutil.which", return_value=None):
        duration = engine.probe_duration(dummy_file, fallback_word_count=50)
        assert duration == 20.0


@pytest.mark.asyncio
async def test_voiceover_generate_with_mock(tmp_path: Path) -> None:
    engine = EdgeTtsVoiceoverEngine()
    out_file = tmp_path / "voiceover.mp3"

    mock_comm = MagicMock()

    async def fake_save(path_str: str) -> None:
        Path(path_str).write_bytes(b"fake mp3 audio bytes")

    mock_comm.save = AsyncMock(side_effect=fake_save)

    with patch("edge_tts.Communicate", return_value=mock_comm):
        result = await engine.generate_voiceover(
            text="Yeh aik test narration hai.",
            language=ContentLanguage.ROMAN_URDU,
            output_path=out_file,
        )

    assert out_file.exists()
    assert result.audio_path == str(out_file)
    assert result.duration_seconds > 0
    assert result.voice == "ur-PK-UzmaNeural"
    assert len(result.sha256) == 64


# ---------------------------------------------------------------------------
# 4. VideoCompositor Tests
# ---------------------------------------------------------------------------


def test_video_compositor_scene_slides(
    settings: Settings, sample_reel_content: ReelContent
) -> None:
    brand = load_brand_config(settings.brand_config_path)
    compositor = FfmpegVideoCompositor(brand)

    slide1 = compositor.render_scene_slide(
        scene=sample_reel_content.scenes[0],
        total_scenes=len(sample_reel_content.scenes),
        topic=sample_reel_content.metadata.topic,
        pillar=sample_reel_content.metadata.content_pillar,
        is_final_scene=False,
    )
    assert slide1.size == (1080, 1920)

    slide_final = compositor.render_scene_slide(
        scene=sample_reel_content.scenes[-1],
        total_scenes=len(sample_reel_content.scenes),
        topic=sample_reel_content.metadata.topic,
        pillar=sample_reel_content.metadata.content_pillar,
        is_final_scene=True,
        cta_text=sample_reel_content.cta,
    )
    assert slide_final.size == (1080, 1920)


@pytest.mark.asyncio
async def test_video_compositor_compose_reel(
    tmp_path: Path, settings: Settings, sample_reel_content: ReelContent
) -> None:
    brand = load_brand_config(settings.brand_config_path)
    compositor = FfmpegVideoCompositor(brand)

    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"dummy audio")
    out_video = tmp_path / "reel.mp4"

    mock_process = MagicMock()
    mock_process.returncode = 0

    async def fake_communicate() -> tuple[bytes, bytes]:
        out_video.write_bytes(b"dummy mp4 video bytes")
        return b"", b""

    mock_process.communicate = AsyncMock(side_effect=fake_communicate)

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_process)):
        result = await compositor.compose_reel(
            content=sample_reel_content,
            audio_path=audio_file,
            output_path=out_video,
        )

    assert out_video.exists()
    assert result.video_path == str(out_video)
    assert result.width == 1080
    assert result.height == 1920
    assert result.fps == 30
    assert len(result.sha256) == 64


# ---------------------------------------------------------------------------
# 5. RenderingService Integration Tests
# ---------------------------------------------------------------------------


def setup_db_item_with_version(
    engine: Engine,
    content: PosterContent | ReelContent,
    content_type: str,
) -> tuple[UUID, int]:
    """Helper to insert a ContentItem and ContentVersion into the test database."""
    item_id = uuid4()
    version_id = uuid4()
    with Session(engine) as session, session.begin():
        item = ContentItem(
            id=item_id,
            external_key=f"test:{item_id}",
            content_type=content_type,
            primary_language=content.metadata.language.value,
            content_pillar=content.metadata.content_pillar,
            topic=content.metadata.topic,
            status="QA_PASSED",
            risk_classification="low",
        )
        session.add(item)
        session.flush()

        version = ContentVersion(
            id=version_id,
            content_item_id=item_id,
            version_number=1,
            language=content.metadata.language.value,
            title=content.metadata.topic,
            script_data={"content": content.model_dump(mode="json")},
            lineage={"quality_report": {"score": 90, "passed": True, "qa_engine_version": "1.0"}},
        )
        session.add(version)
    return item_id, 1


@pytest.mark.asyncio
async def test_rendering_service_poster(
    settings: Settings,
    engine: Engine,
    tmp_path: Path,
    sample_poster_content: PosterContent,
) -> None:
    settings.shared_storage_path = tmp_path
    repo = ContentRepository(engine)
    service = RenderingService(settings, repo)

    item_id, version_num = setup_db_item_with_version(engine, sample_poster_content, "poster")

    result = await service.render(item_id, version_number=version_num)
    assert result.content_id == item_id
    assert result.version_number == 1
    assert result.content_type == "poster"
    assert result.status == "RENDERED"
    assert len(result.assets) == 1
    assert result.assets[0].asset_type == "poster"
    assert Path(result.assets[0].local_path).exists()

    with Session(engine) as session:
        stored_assets = session.scalars(select(Asset)).all()
        assert len(stored_assets) == 1
        assert stored_assets[0].asset_type == "poster"
        assert stored_assets[0].mime_type == "image/png"


@pytest.mark.asyncio
async def test_rendering_service_reel(
    settings: Settings,
    engine: Engine,
    tmp_path: Path,
    sample_reel_content: ReelContent,
) -> None:
    settings.shared_storage_path = tmp_path
    repo = ContentRepository(engine)

    mock_vo = MagicMock()

    async def fake_vo(
        text: str, language: Any, output_path: Path, **kwargs: Any
    ) -> VoiceoverResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake audio data")
        return VoiceoverResult(
            audio_path=str(output_path),
            duration_seconds=30.0,
            voice="ur-PK-UzmaNeural",
            sha256="1" * 64,
            size_bytes=15,
        )

    mock_vo.generate_voiceover = AsyncMock(side_effect=fake_vo)

    mock_vc = MagicMock()

    async def fake_vc(content: Any, audio_path: Path, output_path: Path) -> VideoResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake mp4 data")
        return VideoResult(
            video_path=str(output_path),
            duration_seconds=30.0,
            width=1080,
            height=1920,
            fps=30,
            sha256="2" * 64,
            size_bytes=13,
        )

    mock_vc.compose_reel = AsyncMock(side_effect=fake_vc)

    service = RenderingService(
        settings,
        repo,
        voiceover_engine=mock_vo,
        video_compositor=mock_vc,
    )

    item_id, version_num = setup_db_item_with_version(engine, sample_reel_content, "reel")
    result = await service.render(item_id, version_number=version_num)

    assert result.content_id == item_id
    assert result.content_type == "reel"
    assert result.status == "RENDERED"
    assert len(result.assets) == 2
    asset_types = {a.asset_type for a in result.assets}
    assert asset_types == {"audio", "reel"}

    assets = service.list_assets(item_id)
    assert len(assets) == 2

    first_asset = service.get_asset(assets[0].id)
    assert first_asset is not None
    assert first_asset.id == assets[0].id


@pytest.mark.asyncio
async def test_rendering_service_not_found(settings: Settings, engine: Engine) -> None:
    repo = ContentRepository(engine)
    service = RenderingService(settings, repo)

    with pytest.raises(ContentNotFoundError):
        await service.render(uuid4())


# ---------------------------------------------------------------------------
# 6. API Endpoint Tests
# ---------------------------------------------------------------------------


def test_api_render_poster_endpoint(
    client: TestClient,
    engine: Engine,
    sample_poster_content: PosterContent,
) -> None:
    item_id, _ = setup_db_item_with_version(engine, sample_poster_content, "poster")

    unauth_resp = client.post(f"/api/v1/content/{item_id}/render")
    assert unauth_resp.status_code == 401

    headers = {"X-TBOS-API-Key": "test-internal-api-key-32-characters"}
    resp = client.post(f"/api/v1/content/{item_id}/render", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["content_id"] == str(item_id)
    assert data["status"] == "RENDERED"
    assert len(data["assets"]) == 1

    asset_id = data["assets"][0]["id"]

    list_resp = client.get(f"/api/v1/content/{item_id}/assets")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    dl_resp = client.get(f"/api/v1/assets/{asset_id}/download")
    assert dl_resp.status_code == 200
    assert dl_resp.headers["content-type"] == "image/png"


def test_api_render_404_endpoint(client: TestClient) -> None:
    headers = {"X-TBOS-API-Key": "test-internal-api-key-32-characters"}
    resp = client.post(f"/api/v1/content/{uuid4()}/render", headers=headers)
    assert resp.status_code == 404

    dl_resp = client.get(f"/api/v1/assets/{uuid4()}/download")
    assert dl_resp.status_code == 404
