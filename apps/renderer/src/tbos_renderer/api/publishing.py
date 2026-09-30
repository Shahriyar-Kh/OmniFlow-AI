from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from tbos_renderer.api.dependencies import get_publishing_service, require_internal_api_key
from tbos_renderer.publishing.schemas import (
    HandoffPackageResult,
    PublishedPostResponse,
    PublishJobExecutionResult,
)
from tbos_renderer.publishing.service import PublishingService

router = APIRouter(prefix="/api/v1/publishing", tags=["publishing"])


@router.post(
    "/jobs/{job_id}/execute",
    response_model=PublishJobExecutionResult,
    dependencies=[Depends(require_internal_api_key)],
)
async def execute_publish_job(
    job_id: UUID,
    service: Annotated[PublishingService, Depends(get_publishing_service)],
) -> PublishJobExecutionResult:
    """Execute a single publishing job with idempotency and retry handling."""
    try:
        return await service.execute_publish_job(job_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Publishing execution failed: {exc}",
        ) from exc


@router.post(
    "/process-pending",
    response_model=list[PublishJobExecutionResult],
    dependencies=[Depends(require_internal_api_key)],
)
async def process_pending_publish_jobs(
    service: Annotated[PublishingService, Depends(get_publishing_service)],
) -> list[PublishJobExecutionResult]:
    """Process all pending and due retry publishing jobs."""
    return await service.process_pending_jobs()


@router.post(
    "/tiktok-handoff/{content_id}",
    response_model=HandoffPackageResult,
    dependencies=[Depends(require_internal_api_key)],
)
def create_tiktok_handoff(
    content_id: UUID,
    service: Annotated[PublishingService, Depends(get_publishing_service)],
) -> HandoffPackageResult:
    """Generate a local TikTok handoff package with ready-to-copy metadata."""
    try:
        return service.create_tiktok_handoff_for_content(content_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/published",
    response_model=list[PublishedPostResponse],
)
def list_published_posts(
    platform: str | None = Query(default=None),
    service: Annotated[PublishingService, Depends(get_publishing_service)] = None,  # type: ignore[assignment]
) -> list[PublishedPostResponse]:
    """List all successfully published social posts."""
    return service.list_published_posts(platform=platform)
