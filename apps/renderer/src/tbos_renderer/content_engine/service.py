from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import TypeAdapter

from tbos_renderer.config import Settings, load_brand_config, load_schedule_config
from tbos_renderer.content_engine.client import AiClient, CompositeAiClient
from tbos_renderer.content_engine.duplicate_detection import content_hash
from tbos_renderer.content_engine.facts import retrieve_approved_facts
from tbos_renderer.content_engine.planner import TopicLibrary, WeeklyPlanner
from tbos_renderer.content_engine.prompts import (
    PromptLibrary,
    delimit_untrusted,
    validate_untrusted_input,
)
from tbos_renderer.content_engine.qa import evaluate_content
from tbos_renderer.content_engine.repair import build_repair_prompt, generate_with_repair
from tbos_renderer.content_engine.repository import ContentRepository
from tbos_renderer.content_engine.schemas import (
    AiSmokeTestResponse,
    ContentGenerationRequest,
    ContentGenerationResult,
    ContentMetadata,
    ContentQualityReport,
    ContentType,
    ContentVersionResponse,
    PosterContent,
    ReelContent,
    RegenerationRequest,
    WeeklyPlan,
    WeeklyPlanRequest,
)


class ContentEngineService:
    def __init__(
        self,
        settings: Settings,
        repository: ContentRepository,
        *,
        client: AiClient | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.client = client or CompositeAiClient(settings)
        self.prompts = PromptLibrary(settings.prompt_templates_path)
        self.topics = TopicLibrary(settings.topic_library_path)
        self.planner = WeeklyPlanner(
            self.topics, load_schedule_config(settings.schedule_config_path)
        )

    def weekly_plan(self, request: WeeklyPlanRequest) -> WeeklyPlan:
        recent = self.repository.recent_topic_ids()
        plan = self.planner.create(request, recent)
        return self.repository.persist_plan(plan, regenerate=request.regenerate)

    async def generate(self, request: ContentGenerationRequest) -> ContentGenerationResult:
        replay = self.repository.find_generation(request.idempotency_key)
        if replay:
            return replay
        validate_untrusted_input(request.brief.topic, request.notes)
        template_name = (
            "poster_content" if request.brief.content_type is ContentType.POSTER else "reel_script"
        )
        definition = self.prompts.load(template_name)
        brand = load_brand_config(self.settings.brand_config_path).brand
        with self.repository.session() as session:
            facts = retrieve_approved_facts(session)
        sources = [fact.source for fact in facts if fact.source is not None]
        context = {
            "brand": brand.model_dump(mode="json"),
            "brief": request.brief.model_dump(mode="json"),
            "topic": delimit_untrusted(request.brief.topic),
            "notes": delimit_untrusted(request.notes or ""),
            "approved_facts": [fact.model_dump(mode="json") for fact in facts],
            "output_schema": (
                PosterContent.model_json_schema()
                if request.brief.content_type is ContentType.POSTER
                else ReelContent.model_json_schema()
            ),
        }
        prompt = self.prompts.render(definition, context)
        schema_type: type[PosterContent] | type[ReelContent] = (
            PosterContent if request.brief.content_type is ContentType.POSTER else ReelContent
        )
        report_holder: dict[str, Any] = {}

        def validate(raw: dict[str, Any]) -> PosterContent | ReelContent:
            raw_without_metadata = {key: value for key, value in raw.items() if key != "metadata"}
            digest = content_hash(raw_without_metadata)
            metadata = ContentMetadata(
                brand=brand.name,
                content_type=request.brief.content_type,
                topic=request.brief.topic,
                content_pillar=request.brief.content_pillar,
                target_audience=request.brief.target_audience,
                objective=request.brief.objective,
                language=request.brief.language,
                tone=request.brief.tone,
                difficulty=request.brief.difficulty,
                cta_type=request.brief.cta_type,
                scheduled_date=request.brief.scheduled_date,
                fact_sensitivity=request.brief.fact_sensitivity,
                sources_used=sources,
                prompt_template_name=definition.name,
                prompt_template_version=definition.version,
                model_name=self.client.active_model_name,
                generation_parameters={
                    "temperature": self.settings.ollama_temperature,
                    "context_length": self.settings.ollama_context_length,
                    "provider": self.client.last_provider_used,
                    "fallback_occurred": self.client.fallback_occurred,
                },
                generation_timestamp=datetime.now(UTC),
                content_hash=digest,
            )
            payload = {**raw_without_metadata, "metadata": metadata.model_dump(mode="json")}
            parsed = schema_type.model_validate(payload)
            report = evaluate_content(parsed)
            report_holder["report"] = report
            if not report.passed:
                messages = [issue.message for issue in [*report.blocking_issues, *report.warnings]]
                raise ValueError("; ".join(messages) or "Content did not meet the QA threshold.")
            parsed.metadata.quality_score = report.score
            return parsed

        content, _repairs = await generate_with_repair(
            self.client,
            prompt,
            schema=schema_type.model_json_schema(),
            validator=validate,
            repair_prompt=build_repair_prompt,
        )
        report = report_holder["report"]
        return self.repository.store_generation(request, content, report)

    async def regenerate(
        self, content_id: UUID, request: RegenerationRequest
    ) -> ContentGenerationResult:
        item = self.repository.get_item(content_id)
        generation_request = ContentGenerationRequest.model_validate(
            {
                "brief": {
                    "content_type": item.content_type,
                    "topic": item.topic,
                    "content_pillar": item.content_pillar,
                    "target_audience": "Beginner technology learners",
                    "objective": f"Teach one clear concept about {item.topic}",
                    "language": item.primary_language,
                    "fact_sensitivity": item.risk_classification.upper(),
                },
                "idempotency_key": request.idempotency_key,
                "notes": request.reason,
            }
        )
        generated = await self._generate_without_initial_persistence(generation_request)
        return self.repository.add_version(
            content_id,
            request.idempotency_key,
            generated.content,
            generated.quality_report,
            origin="ai_regeneration",
            reason=request.reason,
        )

    async def _generate_without_initial_persistence(
        self, request: ContentGenerationRequest
    ) -> ContentGenerationResult:
        original = self.repository.store_generation
        captured: dict[str, Any] = {}

        def capture(
            request: ContentGenerationRequest,
            content: PosterContent | ReelContent,
            report: ContentQualityReport,
            *,
            origin: str = "ai_generation",
            reason: str | None = None,
            **_kwargs: Any,
        ) -> ContentGenerationResult:
            captured["content"] = content
            captured["report"] = report
            return ContentGenerationResult(
                content_id=UUID(int=0),
                version_id=UUID(int=0),
                version_number=0,
                status="QA_PASSED" if report.passed else "DRAFTED",
                content=content,
                quality_report=report,
            )

        self.repository.store_generation = capture  # type: ignore[method-assign]
        try:
            return await self.generate(request)
        finally:
            self.repository.store_generation = original  # type: ignore[method-assign]

    def rerun_qa(self, content_id: UUID) -> ContentVersionResponse:
        versions = self.repository.list_versions(content_id)
        if not versions:
            raise ValueError("Content item has no versions.")
        latest = versions[-1]
        latest.quality_report = evaluate_content(latest.content)
        return latest

    async def smoke_test(self) -> AiSmokeTestResponse:
        prompt = (
            'Return strict JSON with exactly two string fields: "concept" and "roman_urdu". '
            'Use concept "API" and explain it in one short Roman Urdu sentence.'
        )
        result = await self.client.generate_json(
            prompt,
            schema={
                "type": "object",
                "properties": {
                    "concept": {"type": "string"},
                    "roman_urdu": {"type": "string"},
                },
                "required": ["concept", "roman_urdu"],
                "additionalProperties": False,
            },
        )
        adapter = TypeAdapter(dict[str, str])
        sample = adapter.validate_python(result)
        text = sample.get("roman_urdu", "").casefold()
        urdu_markers = ("aap", "hai", "mein", "ko", "karein", "ki", "ka")
        detected = any(marker in text.split() for marker in urdu_markers)
        return AiSmokeTestResponse(
            success=detected,
            model=self.client.active_model_name,
            roman_urdu_detected=detected,
            structured_json_valid=True,
            sample=sample,
        )
