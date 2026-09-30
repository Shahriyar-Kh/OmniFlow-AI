from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from tbos_renderer.api.dependencies import get_settings_from_request
from tbos_renderer.config import Settings

LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])

TEMPLATE_PATHS = [
    Path(__file__).parent.parent / "templates" / "dashboard.html",
    Path("apps/renderer/src/tbos_renderer/templates/dashboard.html"),
    Path("/workspace/apps/renderer/src/tbos_renderer/templates/dashboard.html"),
]


def _load_dashboard_template() -> str:
    for path in TEMPLATE_PATHS:
        if path.exists() and path.stat().st_size > 0:
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError("Dashboard HTML template not found.")


@router.get("/dashboard", response_class=HTMLResponse)
def render_dashboard(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings_from_request)],
) -> HTMLResponse:
    """Serve the local Content Approval and Publishing Dashboard."""
    try:
        html = _load_dashboard_template()
    except FileNotFoundError as exc:
        LOGGER.error("Dashboard template missing: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dashboard template could not be loaded.",
        ) from exc

    key = settings.internal_api_key.get_secret_value()
    rendered_html = html.replace("{{ internal_api_key }}", key)
    return HTMLResponse(content=rendered_html, status_code=200)
