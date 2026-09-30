from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from tbos_renderer.api.dependencies import (
    get_email_service,
    get_repository,
    require_internal_api_key,
)
from tbos_renderer.content_engine.repository import ContentRepository
from tbos_renderer.models import ContentItem, ContentVersion
from tbos_renderer.notifications.email import EmailNotificationService

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["notifications"])


class ReviewAlertResponse(BaseModel):
    success: bool
    content_id: UUID
    recipient: str | None = None
    message: str


class TestEmailRequest(BaseModel):
    recipient: str | None = Field(default=None, description="Optional override recipient email")


class TestEmailResponse(BaseModel):
    success: bool
    recipient: str
    message: str


@router.post(
    "/content/{content_id}/notify-review",
    response_model=ReviewAlertResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_internal_api_key)],
)
async def trigger_review_email_notification(
    content_id: UUID,
    version_number: int | None = Query(default=None),
    repository: Annotated[ContentRepository, Depends(get_repository)] = None,  # type: ignore[assignment]
    email_service: Annotated[EmailNotificationService, Depends(get_email_service)] = None,  # type: ignore[assignment]
) -> ReviewAlertResponse:
    """Send an editorial review alert email for the given content item."""
    with repository.session() as session:
        item = session.get(ContentItem, content_id)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Content item {content_id} not found.",
            )

        if version_number is not None:
            version = session.scalar(
                select(ContentVersion).where(
                    ContentVersion.content_item_id == content_id,
                    ContentVersion.version_number == version_number,
                )
            )
        else:
            version = session.scalar(
                select(ContentVersion)
                .where(ContentVersion.content_item_id == content_id)
                .order_by(ContentVersion.version_number.desc())
            )

        if version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Content version for item {content_id} was not found.",
            )

        session.expunge(item)
        session.expunge(version)

    sent = await email_service.send_review_alert(item, version)
    recipient = email_service.settings.notification_email

    if not sent:
        if not email_service.is_enabled():
            return ReviewAlertResponse(
                success=False,
                content_id=content_id,
                recipient=recipient,
                message="Email notifications disabled or SMTP not configured.",
            )
        return ReviewAlertResponse(
            success=False,
            content_id=content_id,
            recipient=recipient,
            message="Failed to deliver review notification email via SMTP.",
        )

    return ReviewAlertResponse(
        success=True,
        content_id=content_id,
        recipient=recipient,
        message=f"Review notification email delivered to {recipient}.",
    )
