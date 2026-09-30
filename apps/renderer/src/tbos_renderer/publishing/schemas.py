from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class PublishResult(BaseModel):
    """Result returned by platform-specific publishers."""

    platform: str
    external_post_id: str
    permalink: str | None = None
    published_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class PublishJobExecutionResult(BaseModel):
    """Result of attempting to execute a publish job."""

    job_id: UUID
    status: str
    platform: str
    published_post_id: UUID | None = None
    external_post_id: str | None = None
    permalink: str | None = None
    error: str | None = None


class HandoffPackageResult(BaseModel):
    """Result of assembling a local TikTok handoff package."""

    content_id: UUID
    version_id: UUID
    bundle_dir: str
    video_path: str
    thumbnail_path: str
    caption_path: str
    timing_path: str
    ready_caption: str
    telegram_message: str


class PublishedPostResponse(BaseModel):
    """API response model for published posts."""

    id: UUID
    publish_job_id: UUID
    platform: str
    external_post_id: str
    permalink: str | None = None
    published_at: datetime
    created_at: datetime
