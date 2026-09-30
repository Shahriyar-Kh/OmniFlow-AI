from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from tbos_renderer.content_engine.duplicate_detection import content_hash
from tbos_renderer.content_engine.schemas import (
    CaptionPack,
    ContentMetadata,
    ContentType,
    FactSensitivity,
    HashtagPack,
    PosterContent,
    ReelContent,
    ReelScene,
)


def metadata(content_type: ContentType = ContentType.POSTER) -> ContentMetadata:
    topic = "What Is an API?" if content_type is ContentType.POSTER else "Python List vs Tuple"
    payload = {"topic": topic, "content_type": content_type.value}
    return ContentMetadata(
        brand="TechBuilt Open School",
        content_type=content_type,
        topic=topic,
        content_pillar=(
            "Computer Science Concepts"
            if content_type is ContentType.POSTER
            else "Python and Automation"
        ),
        target_audience="Beginner BS students",
        objective="Teach one clear concept",
        language="roman_urdu",
        tone="clear and practical",
        difficulty="beginner",
        cta_type="save",
        fact_sensitivity=FactSensitivity.LOW,
        prompt_template_name=(
            "poster_content" if content_type is ContentType.POSTER else "reel_script"
        ),
        prompt_template_version=1,
        model_name="fake-model",
        generation_parameters={"temperature": 0.2},
        generation_timestamp=datetime.now(UTC),
        content_hash=content_hash(payload),
    )


def captions() -> CaptionPack:
    return CaptionPack(
        facebook="API software apps ko clear rules ke saath connect karti hai.",
        instagram="API ko apps ke darmiyan bridge ki tarah samjhein.",
        tiktok="API ka simple concept aaj samjhein.",
    )


def hashtags() -> HashtagPack:
    return HashtagPack(
        facebook=["#TechBuiltOpenSchool", "#LearnTech"],
        instagram=["#LearnAPI", "#ComputerScience"],
        tiktok=["#TechTok", "#APIBasics"],
    )


def poster() -> PosterContent:
    return PosterContent(
        metadata=metadata(),
        headline="API Kya Hoti Hai?",
        subheadline="Software apps ka communication bridge",
        teaching_points=[
            "App request bhejti hai",
            "API clear rules follow karti hai",
            "Server response wapas deta hai",
        ],
        cta="Is concept ko save karein",
        visual_concept="Do apps ke darmiyan labelled bridge",
        captions=captions(),
        hashtags=hashtags(),
        alt_text="Do software apps ek API bridge ke zariye connected hain.",
    )


def reel() -> ReelContent:
    scenes = [
        ReelScene(
            scene_number=index,
            duration_seconds=5,
            narration=f"Scene {index} mein aap simple Python concept samjhein.",
            on_screen_text=f"Step {index}",
            visual_direction=f"Python example ka visual number {index}",
        )
        for index in range(1, 7)
    ]
    reel_captions = CaptionPack(
        facebook="Python list aur tuple ka practical farq step by step samjhein.",
        instagram="List ya tuple? Simple example ke saath decision samjhein.",
        tiktok="Python list vs tuple ka quick concept.",
    )
    return ReelContent(
        metadata=metadata(ContentType.REEL),
        cover_title="Python List vs Tuple",
        hook="List aur tuple mein asal farq kya hai?",
        target_duration_seconds=30,
        narration=" ".join(scene.narration for scene in scenes),
        scenes=scenes,
        cta="Example khud code karke dekhein",
        captions=reel_captions,
        hashtags=hashtags(),
        accessibility_description="Six scenes compare a mutable Python list with a fixed tuple.",
    )


def raw_content(content_type: ContentType) -> dict[str, Any]:
    value = poster() if content_type is ContentType.POSTER else reel()
    payload = value.model_dump(mode="json")
    payload.pop("metadata")
    return payload
