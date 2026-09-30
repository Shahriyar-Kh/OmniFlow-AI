from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssetResponse(StrictModel):
    id: UUID
    content_version_id: UUID
    asset_type: str
    local_path: str
    mime_type: str | None = None
    sha256: str | None = None
    temporary_public_url: str | None = None
    public_url_expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class RenderRequest(StrictModel):
    version_number: int | None = None
    force: bool = False


class RenderResultResponse(StrictModel):
    content_id: UUID
    version_id: UUID
    version_number: int
    content_type: str
    assets: list[AssetResponse]
    status: str
