from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query

from tbos_renderer.api.dependencies import (
    get_content_service,
    get_repository,
    require_internal_api_key,
)
from tbos_renderer.content_engine.repository import ContentRepository
from tbos_renderer.content_engine.schemas import (
    ApprovalRequest,
    ApprovalResponse,
    ApprovalResultResponse,
    ContentGenerationRequest,
    ContentGenerationResult,
    ContentLanguage,
    ContentListResponse,
    ContentType,
    ContentVersionResponse,
    ManualContentRevisionRequest,
    PublishJobResponse,
    RegenerationRequest,
)
from tbos_renderer.content_engine.service import ContentEngineService

router = APIRouter(prefix="/api/v1/content", tags=["content"])


@router.get("", response_model=ContentListResponse)
def list_content(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    content_type: ContentType | None = None,
    pillar: str | None = None,
    status: str | None = None,
    scheduled_date: date | None = None,
    language: ContentLanguage | None = None,
    repository: Annotated[ContentRepository, Depends(get_repository)] = None,  # type: ignore[assignment]
) -> ContentListResponse:
    return repository.list_content(
        page=page,
        page_size=page_size,
        content_type=content_type,
        pillar=pillar,
        status=status,
        scheduled_date=scheduled_date,
        language=language,
    )


@router.get("/{content_id}", response_model=ContentVersionResponse)
def get_content(
    content_id: UUID,
    repository: Annotated[ContentRepository, Depends(get_repository)],
) -> ContentVersionResponse:
    versions = repository.list_versions(content_id)
    if not versions:
        raise ValueError("Content item has no generated versions.")
    return versions[-1]


@router.get("/{content_id}/versions", response_model=list[ContentVersionResponse])
def list_versions(
    content_id: UUID,
    repository: Annotated[ContentRepository, Depends(get_repository)],
) -> list[ContentVersionResponse]:
    return repository.list_versions(content_id)


@router.get("/{content_id}/versions/{version_number}", response_model=ContentVersionResponse)
def get_version(
    content_id: UUID,
    version_number: int,
    repository: Annotated[ContentRepository, Depends(get_repository)],
) -> ContentVersionResponse:
    return repository.get_version(content_id, version_number)


@router.post(
    "/generate",
    response_model=ContentGenerationResult,
    dependencies=[Depends(require_internal_api_key)],
)
async def generate_content(
    request: Annotated[
        ContentGenerationRequest,
        Body(
            openapi_examples={
                "poster": {
                    "summary": "Beginner poster",
                    "value": {
                        "brief": {
                            "content_type": "poster",
                            "topic": "What Is an API?",
                            "content_pillar": "Computer Science Concepts",
                            "target_audience": "Beginner BS students",
                            "objective": "Explain an API with one everyday analogy",
                            "language": "roman_urdu",
                            "fact_sensitivity": "LOW",
                        },
                        "idempotency_key": "poster-api-example-001",
                    },
                },
                "reel": {
                    "summary": "Beginner reel",
                    "value": {
                        "brief": {
                            "content_type": "reel",
                            "topic": "Python List vs Tuple",
                            "content_pillar": "Python and Automation",
                            "target_audience": "Beginner Python learners",
                            "objective": "Explain when to use a list or tuple",
                            "language": "roman_urdu",
                            "fact_sensitivity": "LOW",
                        },
                        "idempotency_key": "reel-list-tuple-example-001",
                    },
                },
            }
        ),
    ],
    service: Annotated[ContentEngineService, Depends(get_content_service)],
) -> ContentGenerationResult:
    return await service.generate(request)


@router.post(
    "/{content_id}/regenerate",
    response_model=ContentGenerationResult,
    dependencies=[Depends(require_internal_api_key)],
)
async def regenerate_content(
    content_id: UUID,
    request: RegenerationRequest,
    service: Annotated[ContentEngineService, Depends(get_content_service)],
) -> ContentGenerationResult:
    return await service.regenerate(content_id, request)


@router.post(
    "/{content_id}/qa",
    response_model=ContentVersionResponse,
    dependencies=[Depends(require_internal_api_key)],
)
def rerun_qa(
    content_id: UUID,
    service: Annotated[ContentEngineService, Depends(get_content_service)],
) -> ContentVersionResponse:
    return service.rerun_qa(content_id)


@router.post(
    "/{content_id}/revisions",
    response_model=ContentGenerationResult,
    dependencies=[Depends(require_internal_api_key)],
)
def manual_revision(
    content_id: UUID,
    request: ManualContentRevisionRequest,
    repository: Annotated[ContentRepository, Depends(get_repository)],
) -> ContentGenerationResult:
    return repository.store_manual_revision(content_id, request)


@router.post(
    "/{content_id}/approval",
    response_model=ApprovalResultResponse,
    dependencies=[Depends(require_internal_api_key)],
)
def record_content_approval(
    content_id: UUID,
    request: ApprovalRequest,
    repository: Annotated[ContentRepository, Depends(get_repository)],
) -> ApprovalResultResponse:
    """Record an editorial approval or rejection decision and provision publish jobs."""
    return repository.record_approval(content_id, request)


@router.get(
    "/{content_id}/approvals",
    response_model=list[ApprovalResponse],
)
def list_content_approvals(
    content_id: UUID,
    repository: Annotated[ContentRepository, Depends(get_repository)],
) -> list[ApprovalResponse]:
    """List approval audit records for a content item."""
    return repository.list_approvals(content_id)


@router.get(
    "/{content_id}/publish-jobs",
    response_model=list[PublishJobResponse],
)
def list_content_publish_jobs(
    content_id: UUID,
    repository: Annotated[ContentRepository, Depends(get_repository)],
) -> list[PublishJobResponse]:
    """List generated publishing jobs for a content item."""
    return repository.list_publish_jobs(content_id=content_id)
