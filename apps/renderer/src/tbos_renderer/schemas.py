from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ComponentStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "unavailable", "degraded", "not_configured"]
    required: bool
    detail: str | None = None


class LiveResponse(BaseModel):
    status: Literal["alive"]
    service: str
    version: str
    timestamp: datetime
    correlation_id: str


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    database: ComponentStatus
    ollama: ComponentStatus
    timestamp: datetime
    correlation_id: str


class SystemStatusResponse(BaseModel):
    service: str
    version: str
    environment: str
    database: ComponentStatus
    n8n: ComponentStatus
    ollama: ComponentStatus
    timestamp: datetime
    correlation_id: str


class WeeklyTargetsResponse(BaseModel):
    poster: int = Field(ge=0)
    reel: int = Field(ge=0)


class FeatureFlagsResponse(BaseModel):
    telegram: bool
    meta: bool
    r2: bool
    ollama: bool
    email: bool = False


class PublicConfigResponse(BaseModel):
    brand_name: str
    brand_slug: str
    timezone: str
    enabled_content_types: list[Literal["poster", "reel"]]
    weekly_targets: WeeklyTargetsResponse
    default_language_style: str
    feature_flags: FeatureFlagsResponse


class ErrorResponse(BaseModel):
    error: str
    message: str
    correlation_id: str
