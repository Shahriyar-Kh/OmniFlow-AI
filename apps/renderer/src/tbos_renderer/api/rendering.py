from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from tbos_renderer.api.dependencies import (
    get_rendering_service,
    require_internal_api_key,
)
from tbos_renderer.content_engine.exceptions import ContentNotFoundError
from tbos_renderer.rendering.schemas import (
    AssetResponse,
    RenderRequest,
    RenderResultResponse,
)
from tbos_renderer.rendering.service import RenderingService

router = APIRouter(prefix="/api/v1", tags=["rendering"])


@router.post(
    "/content/{content_id}/render",
    response_model=RenderResultResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_internal_api_key)],
)
async def render_content(
    content_id: UUID,
    payload: RenderRequest | None = None,
    service: Annotated[RenderingService, Depends(get_rendering_service)] = None,  # type: ignore[assignment]
) -> RenderResultResponse:
    """Render poster or reel media assets for the given content item."""
    version_num = payload.version_number if payload else None
    force = payload.force if payload else False
    try:
        return await service.render(content_id, version_number=version_num, force=force)
    except ContentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rendering failed: {exc}",
        ) from exc


@router.get(
    "/content/{content_id}/assets",
    response_model=list[AssetResponse],
)
async def list_content_assets(
    content_id: UUID,
    version_number: int | None = Query(default=None),
    service: Annotated[RenderingService, Depends(get_rendering_service)] = None,  # type: ignore[assignment]
) -> list[AssetResponse]:
    """List all rendered media assets for a content item."""
    return service.list_assets(content_id, version_number=version_number)


@router.get(
    "/assets/{asset_id}/download",
)
async def download_asset(
    asset_id: UUID,
    service: Annotated[RenderingService, Depends(get_rendering_service)] = None,  # type: ignore[assignment]
) -> FileResponse:
    """Download or stream a rendered media asset file."""
    asset = service.get_asset(asset_id)
    if not asset or not os.path.exists(asset.local_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset file not found.",
        )
    return FileResponse(
        path=asset.local_path,
        media_type=asset.mime_type or "application/octet-stream",
        filename=Path(asset.local_path).name,
    )
