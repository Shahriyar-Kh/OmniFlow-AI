from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from tbos_renderer.api.dependencies import get_content_service
from tbos_renderer.content_engine.schemas import (
    ContentType,
    FactSensitivity,
    Topic,
    TopicListResponse,
)
from tbos_renderer.content_engine.service import ContentEngineService

router = APIRouter(prefix="/api/v1/topics", tags=["topics"])


@router.get("", response_model=TopicListResponse)
def list_topics(
    pillar: str | None = None,
    content_type: ContentType | None = None,
    audience: str | None = None,
    difficulty: str | None = None,
    fact_sensitivity: Annotated[FactSensitivity | None, Query()] = None,
    service: Annotated[ContentEngineService, Depends(get_content_service)] = None,  # type: ignore[assignment]
) -> TopicListResponse:
    items = service.topics.filter(
        pillar=pillar,
        content_type=content_type,
        audience=audience,
        difficulty=difficulty,
        max_sensitivity=fact_sensitivity,
    )
    return TopicListResponse(items=items, total=len(items))


@router.get("/{topic_id}", response_model=Topic)
def get_topic(
    topic_id: str,
    service: Annotated[ContentEngineService, Depends(get_content_service)],
) -> Topic:
    topic = service.topics.get(topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic was not found.")
    return topic
