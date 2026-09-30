from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from tbos_renderer.api.dependencies import get_content_service, require_internal_api_key
from tbos_renderer.content_engine.schemas import WeeklyPlan, WeeklyPlanRequest
from tbos_renderer.content_engine.service import ContentEngineService

router = APIRouter(prefix="/api/v1/plans", tags=["plans"])


@router.post(
    "/weekly",
    response_model=WeeklyPlan,
    dependencies=[Depends(require_internal_api_key)],
)
def create_weekly_plan(
    request: WeeklyPlanRequest,
    service: Annotated[ContentEngineService, Depends(get_content_service)],
) -> WeeklyPlan:
    return service.weekly_plan(request)
