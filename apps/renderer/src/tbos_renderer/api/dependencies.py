from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from tbos_renderer.config import Settings
from tbos_renderer.content_engine.repository import ContentRepository
from tbos_renderer.content_engine.service import ContentEngineService
from tbos_renderer.publishing.service import PublishingService
from tbos_renderer.rendering.service import RenderingService


def get_settings_from_request(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_repository(request: Request) -> ContentRepository:
    return request.app.state.content_repository  # type: ignore[no-any-return]


def get_content_service(request: Request) -> ContentEngineService:
    return request.app.state.content_service  # type: ignore[no-any-return]


def get_rendering_service(request: Request) -> RenderingService:
    return request.app.state.rendering_service  # type: ignore[no-any-return]


def get_publishing_service(request: Request) -> PublishingService:
    return request.app.state.publishing_service  # type: ignore[no-any-return]


def require_internal_api_key(
    request: Request,
    supplied: Annotated[str | None, Header(alias="X-TBOS-API-Key")] = None,
) -> None:
    expected = get_settings_from_request(request).internal_api_key.get_secret_value()
    valid = bool(supplied and expected and secrets.compare_digest(supplied, expected))
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid internal API key is required.",
            headers={"WWW-Authenticate": "TBOS-API-Key"},
        )
