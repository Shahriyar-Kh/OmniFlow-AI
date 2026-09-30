from __future__ import annotations

import asyncio
from typing import Any

import httpx
from sqlalchemy.engine import Engine

from tbos_renderer.database import ping_database
from tbos_renderer.schemas import ComponentStatus


async def database_status(engine: Engine) -> ComponentStatus:
    try:
        await asyncio.to_thread(ping_database, engine)
        return ComponentStatus(status="ok", required=True)
    except Exception:
        return ComponentStatus(status="unavailable", required=True, detail="Database check failed")


async def http_service_status(
    url: str | None,
    *,
    required: bool,
    enabled: bool = True,
    service_name: str,
) -> ComponentStatus:
    if not enabled or not url:
        return ComponentStatus(status="not_configured", required=required)
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
            response.raise_for_status()
        return ComponentStatus(status="ok", required=required)
    except (httpx.HTTPError, OSError):
        status = "unavailable" if required else "degraded"
        return ComponentStatus(
            status=status,
            required=required,
            detail=f"{service_name} is not reachable",
        )


def safe_component_dump(component: ComponentStatus) -> dict[str, Any]:
    """Return only the explicitly public component fields."""
    return component.model_dump()
