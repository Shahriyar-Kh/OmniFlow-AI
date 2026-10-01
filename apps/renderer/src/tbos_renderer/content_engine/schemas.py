from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ContentType(StrEnum):
    POSTER = "poster"
    REEL = "reel"


class ContentLanguage(StrEnum):
    ROMAN_URDU = "roman_urdu"
    SIMPLE_ENGLISH = "simple_english"


class Difficulty(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"


class FactSensitivity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class IssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"
    CRITICAL = "critical"


class SourceReference(StrictModel):
    fact_id: UUID | None = None
    title: str = Field(min_length=2, max_length=300)
    url: str = Field(min_length=8, max_length=2000)
    publisher: str | None = Field(default=None, max_length=200)
    reviewed: bool = False


class FactRecord(StrictModel):
    id: UUID
    statement: str = Field(min_length=3, max_length=2000)
    sensitivity: FactSensitivity
    source: SourceReference | None = None
    expires_at: datetime | None = None


class ContentBrief(StrictModel):
    brand: str = "TechBuilt Open School"
    content_type: ContentType
    topic: str = Field(min_length=3, max_length=250)
    content_pillar: str = Field(min_length=3, max_length=120)
    target_audience: str = Field(min_length=3, max_length=180)
    objective: str = Field(min_length=3, max_length=300)
    language: ContentLanguage = ContentLanguage.ROMAN_URDU
    tone: str = Field(default="clear, encouraging, practical, honest", max_length=200)
    difficulty: Difficulty = Difficulty.BEGINNER
    cta_type: str = Field(default="learn_more", max_length=80)
    scheduled_date: date | None = None
    fact_sensitivity: FactSensitivity = FactSensitivity.LOW
    sources: list[SourceReference] = Field(default_factory=list, max_length=10)


class ContentGenerationRequest(StrictModel):
    brief: ContentBrief
    idempotency_key: str = Field(min_length=12, max_length=180)
    notes: str | None = Field(default=None, max_length=1000)


class PlatformCaption(StrictModel):
    platform: Literal["facebook", "instagram", "tiktok"]
    text: str = Field(min_length=3, max_length=2200)


class CaptionPack(StrictModel):
    facebook: str = Field(min_length=3, max_length=2200)
    instagram: str = Field(min_length=3, max_length=2200)
    tiktok: str = Field(min_length=3, max_length=300)

    @model_validator(mode="after")
    def captions_are_distinct(self) -> CaptionPack:
        if len({self.facebook.casefold(), self.instagram.casefold(), self.tiktok.casefold()}) < 3:
            raise ValueError("platform captions must be distinct")
        return self


class HashtagPack(StrictModel):
    facebook: list[str] = Field(default_factory=list, max_length=15)
    instagram: list[str] = Field(default_factory=list, max_length=5)
    tiktok: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def hashtags_are_valid(self) -> HashtagPack:
        for values in (self.facebook, self.instagram, self.tiktok):
            if any(not value.startswith("#") or " " in value for value in values):
                raise ValueError("hashtags must start with # and contain no spaces")
        return self


class ContentMetadata(StrictModel):
    brand: str
    content_type: ContentType
    topic: str
    content_pillar: str
    target_audience: str
    objective: str
    language: ContentLanguage
    tone: str
    difficulty: Difficulty
    cta_type: str
    scheduled_date: date | None = None
    fact_sensitivity: FactSensitivity
    sources_used: list[SourceReference] = Field(default_factory=list)
    prompt_template_name: str
    prompt_template_version: int = Field(ge=1)
    model_name: str
    generation_parameters: dict[str, int | float | str | bool]
    generation_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    quality_score: int = Field(default=0, ge=0, le=100)


class PracticeQuestion(StrictModel):
    question: str = Field(min_length=5, max_length=240)
    options: list[str] = Field(min_length=2, max_length=4)
    answer: str = Field(min_length=1, max_length=80)
    explanation: str | None = Field(default=None, max_length=200)


class PosterContent(StrictModel):
    metadata: ContentMetadata
    headline: str = Field(min_length=3, max_length=55)
    subheadline: str | None = Field(default=None, max_length=90)
    code_snippet: str | None = Field(default=None, max_length=800)
    code_output: str | None = Field(default=None, max_length=300)
    teaching_points: list[str] = Field(min_length=3, max_length=5)
    practice_question: PracticeQuestion | None = Field(default=None)
    cta: str = Field(min_length=3, max_length=60)
    visual_concept: str = Field(min_length=3, max_length=500)
    captions: CaptionPack
    hashtags: HashtagPack
    alt_text: str = Field(min_length=10, max_length=500)

    @model_validator(mode="after")
    def teaching_points_are_concise(self) -> PosterContent:
        if any(len(point) > 130 for point in self.teaching_points):
            raise ValueError("teaching points must be at most 130 characters")
        return self


class ReelScene(StrictModel):
    scene_number: int = Field(ge=1, le=8)
    duration_seconds: float = Field(gt=0, le=10)
    narration: str = Field(min_length=2, max_length=450)
    on_screen_text: str = Field(min_length=1, max_length=90)
    visual_direction: str = Field(min_length=3, max_length=500)


class ReelContent(StrictModel):
    metadata: ContentMetadata
    cover_title: str = Field(min_length=3, max_length=55)
    hook: str = Field(min_length=3, max_length=140)
    target_duration_seconds: int = Field(ge=30, le=45)
    narration: str = Field(min_length=30, max_length=1200)
    scenes: list[ReelScene] = Field(min_length=6, max_length=8)
    cta: str = Field(min_length=3, max_length=100)
    captions: CaptionPack
    hashtags: HashtagPack
    accessibility_description: str = Field(min_length=10, max_length=600)

    @model_validator(mode="after")
    def scene_timing_matches_target(self) -> ReelContent:
        numbers = [scene.scene_number for scene in self.scenes]
        if numbers != list(range(1, len(self.scenes) + 1)):
            raise ValueError("scene numbers must be consecutive and start at one")
        duration = sum(scene.duration_seconds for scene in self.scenes)
        if abs(duration - self.target_duration_seconds) > 2:
            raise ValueError("scene durations must be within two seconds of the target")
        return self


GeneratedContent = Annotated[PosterContent | ReelContent, Field(discriminator=None)]


class QualityIssue(StrictModel):
    code: str
    category: str
    severity: IssueSeverity
    message: str
    field: str | None = None
    suggested_fix: str | None = None


class ContentQualityReport(StrictModel):
    score: int = Field(ge=0, le=100)
    passed: bool
    blocking_issues: list[QualityIssue] = Field(default_factory=list)
    warnings: list[QualityIssue] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True
    fact_review_required: bool = False
    suggested_fixes: list[str] = Field(default_factory=list)
    qa_engine_version: str


class ContentGenerationResult(StrictModel):
    content_id: UUID
    version_id: UUID
    version_number: int
    status: Literal["DRAFTED", "QA_PASSED", "FAILED"]
    content: PosterContent | ReelContent
    quality_report: ContentQualityReport
    idempotent_replay: bool = False


class ContentVersionResponse(StrictModel):
    content_id: UUID
    version_id: UUID
    version_number: int
    status: str
    origin: str
    content: PosterContent | ReelContent
    quality_report: ContentQualityReport
    created_at: datetime


class ContentSummary(StrictModel):
    id: UUID
    external_key: str
    content_type: ContentType
    language: ContentLanguage
    pillar: str
    topic: str
    status: str
    scheduled_at: datetime | None
    current_version: int | None


class ContentListResponse(StrictModel):
    items: list[ContentSummary]
    page: int
    page_size: int
    total: int


class RegenerationRequest(StrictModel):
    idempotency_key: str = Field(min_length=12, max_length=180)
    reason: str = Field(min_length=3, max_length=500)


class ManualContentRevisionRequest(StrictModel):
    idempotency_key: str = Field(min_length=12, max_length=180)
    reason: str = Field(min_length=3, max_length=500)
    content: PosterContent | ReelContent


class WeeklyPlanRequest(StrictModel):
    week_start: date
    language: ContentLanguage = ContentLanguage.ROMAN_URDU
    regenerate: bool = False
    pillar: str | None = None
    audience: str | None = None
    difficulty: Difficulty | None = None
    max_fact_sensitivity: FactSensitivity = FactSensitivity.MEDIUM

    @model_validator(mode="after")
    def week_starts_monday(self) -> WeeklyPlanRequest:
        if self.week_start.weekday() != 0:
            raise ValueError("week_start must be a Monday")
        return self


class WeeklyPlanItem(StrictModel):
    slot: str
    scheduled_at: datetime
    content_type: ContentType
    topic_id: str
    title: str
    pillar: str
    target_audience: str
    difficulty: Difficulty
    fact_sensitivity: FactSensitivity
    cta_type: str


class WeeklyPlan(StrictModel):
    plan_id: str
    week_start: date
    timezone: str
    items: list[WeeklyPlanItem]
    idempotent_replay: bool = False

    @model_validator(mode="after")
    def correct_mix(self) -> WeeklyPlan:
        posters = sum(item.content_type is ContentType.POSTER for item in self.items)
        reels = sum(item.content_type is ContentType.REEL for item in self.items)
        if (posters, reels) != (4, 3):
            raise ValueError("weekly plan must contain four posters and three reels")
        if len({item.topic_id for item in self.items}) != 7:
            raise ValueError("weekly plan topics must be unique")
        return self


class Topic(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    title: str
    pillar: str
    formats: list[ContentType]
    target_audience: str
    difficulty: Difficulty
    learning_objective: str
    fact_sensitivity: FactSensitivity
    cta_type: str
    prerequisites: list[str] = Field(default_factory=list)
    active: bool = True


class TopicListResponse(StrictModel):
    items: list[Topic]
    total: int


class AiStatusResponse(StrictModel):
    enabled: bool
    configured: bool
    reachable: bool
    selected_model: str
    model_available: bool
    available_models: list[str] = Field(default_factory=list)
    detail: str


class AiSmokeTestResponse(StrictModel):
    success: bool
    model: str
    roman_urdu_detected: bool
    structured_json_valid: bool
    sample: dict[str, str]


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"


class ApprovalRequest(StrictModel):
    decision: ApprovalDecision
    reviewer_reference: str = Field(min_length=1, max_length=160)
    notes: str | None = None
    version_number: int | None = None


class ApprovalResponse(StrictModel):
    id: UUID
    content_version_id: UUID
    decision: str
    reviewer_reference: str
    notes: str | None = None
    decided_at: datetime | None = None
    created_at: datetime


class PublishJobResponse(StrictModel):
    id: UUID
    content_version_id: UUID
    platform: str
    state: str
    idempotency_key: str
    retry_count: int
    scheduled_at: datetime | None = None
    request_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ApprovalResultResponse(StrictModel):
    content_id: UUID
    version_id: UUID
    version_number: int
    status: str
    approval: ApprovalResponse
    publish_jobs: list[PublishJobResponse] = Field(default_factory=list)
