from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from tbos_renderer.api.dependencies import get_content_service, require_internal_api_key
from tbos_renderer.content_engine.schemas import AiSmokeTestResponse, AiStatusResponse
from tbos_renderer.content_engine.service import ContentEngineService

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.get("/status", response_model=AiStatusResponse)
async def ai_status(
    service: Annotated[ContentEngineService, Depends(get_content_service)],
) -> AiStatusResponse:
    return await service.client.status()


@router.post(
    "/smoke-test",
    response_model=AiSmokeTestResponse,
    dependencies=[Depends(require_internal_api_key)],
)
async def ai_smoke_test(
    service: Annotated[ContentEngineService, Depends(get_content_service)],
) -> AiSmokeTestResponse:
    return await service.smoke_test()
