from __future__ import annotations

import smtplib
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session
from tbos_renderer.config import Settings
from tbos_renderer.models import ContentItem, ContentVersion
from tbos_renderer.notifications.email import EmailNotificationService
from tbos_renderer.rendering.service import RenderingService

from .factories import poster as make_poster
from .factories import reel as make_reel


@pytest.fixture
def email_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_user": "user@example.com",
            "smtp_password": SecretStr("secret-smtp-pass"),
            "smtp_from": "TechBuilt Alert <alerts@example.com>",
            "notification_email": "reviewer@example.com",
            "dashboard_public_url": "http://localhost:8080/dashboard",
            "feature_email_notifications_enabled": True,
        }
    )


@pytest.fixture
def sample_poster_entities(engine) -> tuple[ContentItem, ContentVersion]:
    poster_obj = make_poster()
    poster_data = poster_obj.model_dump(mode="json")
    poster_data["captions"] = {
        "instagram": "Instagram caption for API concept.",
        "facebook": "Facebook caption for API concept.",
        "tiktok": "TikTok caption for API concept.",
    }
    with Session(engine) as session:
        item = ContentItem(
            external_key="poster-email-test-001",
            content_type="poster",
            primary_language="roman_urdu",
            content_pillar="Computer Science Concepts",
            topic="What Is an API?",
            status="RENDERED",
        )
        session.add(item)
        session.flush()

        version = ContentVersion(
            content_item_id=item.id,
            version_number=1,
            language="roman_urdu",
            title="What Is an API? (Khana Order Karne Jaisa)",
            hook="API restaurant ke waiter ki tarah hoti hai!",
            cta="Follow for more coding tips!",
            caption="API ek waiter ki tarah hai jo kitchen se order lati hai.",
            hashtags=["API", "Coding", "LearnPython"],
            scene_data={"teaching_points": ["Point 1", "Point 2"]},
            script_data={"content": poster_data},
            lineage={"quality_report": {"total_score": 92}},
        )
        session.add(version)
        session.commit()

        session.refresh(item)
        session.refresh(version)
        session.expunge(item)
        session.expunge(version)
        return item, version


@pytest.fixture
def sample_reel_entities(engine) -> tuple[ContentItem, ContentVersion]:
    reel_obj = make_reel()
    reel_data = reel_obj.model_dump(mode="json")
    reel_data["captions"] = {
        "instagram": "IG reel caption.",
        "facebook": "FB reel caption.",
        "tiktok": "TT reel caption.",
    }
    with Session(engine) as session:
        item = ContentItem(
            external_key="reel-email-test-002",
            content_type="reel",
            primary_language="roman_urdu",
            content_pillar="Python and Automation",
            topic="Python List vs Tuple",
            status="RENDERED",
        )
        session.add(item)
        session.flush()

        version = ContentVersion(
            content_item_id=item.id,
            version_number=2,
            language="roman_urdu",
            title="Python List vs Tuple in 30 Seconds",
            hook="List mutable hai, Tuple immutable!",
            cta="Save this reel for exams!",
            caption="Quick guide to Python data types.",
            hashtags=["Python", "TechBuilt"],
            scene_data={"scenes": []},
            script_data={"content": reel_data},
            lineage={"quality_report": {"total_score": 88}},
        )
        session.add(version)
        session.commit()

        session.refresh(item)
        session.refresh(version)
        session.expunge(item)
        session.expunge(version)
        return item, version


def test_build_review_email_poster(email_settings: Settings, sample_poster_entities) -> None:
    item, version = sample_poster_entities
    service = EmailNotificationService(email_settings)

    msg = service.build_review_email(item, version)

    assert "[TBOS Review Alert]" in msg["Subject"]
    assert "Poster (1080x1350)" in msg["Subject"]
    assert "What Is an API?" in msg["Subject"]
    assert msg["To"] == "reviewer@example.com"
    assert msg["From"] == "TechBuilt Alert <alerts@example.com>"

    # Check plain text content
    text_part = msg.get_payload(0)
    content_str = text_part.get_content()
    assert "What Is an API? (Khana Order Karne Jaisa)" in content_str
    assert "API restaurant ke waiter ki tarah hoti hai!" in content_str
    assert "http://localhost:8080/dashboard" in content_str
    assert "Instagram caption for API concept." in content_str
    assert "#API #Coding #LearnPython" in content_str
    assert "92/100" in content_str

    # Check HTML alternative
    html_part = msg.get_payload(1)
    html_content = html_part.get_content()
    assert "POSTER" in html_content
    assert "Open Approval Dashboard" in html_content
    assert "http://localhost:8080/dashboard" in html_content


def test_build_review_email_reel(email_settings: Settings, sample_reel_entities) -> None:
    item, version = sample_reel_entities
    service = EmailNotificationService(email_settings)

    msg = service.build_review_email(item, version)

    assert "Reel Short (9:16)" in msg["Subject"]
    assert "Python List vs Tuple" in msg["Subject"]

    html_part = msg.get_payload(1)
    html_content = html_part.get_content()
    assert "REEL SHORT" in html_content
    assert "List mutable hai, Tuple immutable!" in html_content


@pytest.mark.asyncio
async def test_send_review_alert_success(email_settings: Settings, sample_poster_entities) -> None:
    item, version = sample_poster_entities
    service = EmailNotificationService(email_settings)

    with patch("tbos_renderer.notifications.email.smtplib.SMTP") as mock_smtp:
        mock_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_instance

        success = await service.send_review_alert(item, version)

        assert success is True
        mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=30.0)
        mock_instance.starttls.assert_called_once()
        mock_instance.login.assert_called_once_with("user@example.com", "secret-smtp-pass")
        mock_instance.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_send_review_alert_ssl_port_465(
    email_settings: Settings, sample_poster_entities
) -> None:
    item, version = sample_poster_entities
    ssl_settings = email_settings.model_copy(update={"smtp_port": 465})
    service = EmailNotificationService(ssl_settings)

    with patch("tbos_renderer.notifications.email.smtplib.SMTP_SSL") as mock_ssl:
        mock_instance = MagicMock()
        mock_ssl.return_value.__enter__.return_value = mock_instance

        success = await service.send_review_alert(item, version)

        assert success is True
        mock_ssl.assert_called_once()
        mock_instance.login.assert_called_once_with("user@example.com", "secret-smtp-pass")
        mock_instance.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_send_review_alert_disabled(email_settings: Settings, sample_poster_entities) -> None:
    item, version = sample_poster_entities
    disabled_settings = email_settings.model_copy(
        update={"feature_email_notifications_enabled": False}
    )
    service = EmailNotificationService(disabled_settings)

    with patch("tbos_renderer.notifications.email.smtplib.SMTP") as mock_smtp:
        success = await service.send_review_alert(item, version)
        assert success is False
        mock_smtp.assert_not_called()


@pytest.mark.asyncio
async def test_send_review_alert_smtp_failure(
    email_settings: Settings, sample_poster_entities
) -> None:
    item, version = sample_poster_entities
    service = EmailNotificationService(email_settings)

    with patch("tbos_renderer.notifications.email.smtplib.SMTP") as mock_smtp:
        mock_smtp.side_effect = smtplib.SMTPConnectError(421, b"Connection refused")

        success = await service.send_review_alert(item, version)
        assert success is False


def test_api_notify_review_endpoint_success(
    client: TestClient, sample_poster_entities, email_settings: Settings
) -> None:
    item, _ = sample_poster_entities
    client.app.state.settings = email_settings
    client.app.state.email_service = EmailNotificationService(email_settings)

    with patch.object(
        EmailNotificationService, "send_review_alert", new_callable=AsyncMock
    ) as mock_send:
        mock_send.return_value = True

        response = client.post(
            f"/api/v1/content/{item.id}/notify-review",
            headers={"X-TBOS-API-Key": email_settings.internal_api_key.get_secret_value()},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["content_id"] == str(item.id)
        assert data["recipient"] == "reviewer@example.com"
        mock_send.assert_awaited_once()


def test_api_notify_review_endpoint_unauthorized(
    client: TestClient, sample_poster_entities: tuple[ContentItem, ContentVersion]
) -> None:
    item, _ = sample_poster_entities
    response = client.post(f"/api/v1/content/{item.id}/notify-review")
    assert response.status_code == 401


def test_api_notify_review_endpoint_not_found(client: TestClient, email_settings: Settings) -> None:
    client.app.state.settings = email_settings
    client.app.state.email_service = EmailNotificationService(email_settings)

    random_id = uuid4()
    response = client.post(
        f"/api/v1/content/{random_id}/notify-review",
        headers={"X-TBOS-API-Key": email_settings.internal_api_key.get_secret_value()},
    )
    assert response.status_code == 404


def test_api_notify_review_disabled(
    client: TestClient, sample_poster_entities, email_settings: Settings
) -> None:
    item, _ = sample_poster_entities
    disabled = email_settings.model_copy(update={"feature_email_notifications_enabled": False})
    client.app.state.settings = disabled
    client.app.state.email_service = EmailNotificationService(disabled)

    response = client.post(
        f"/api/v1/content/{item.id}/notify-review",
        headers={"X-TBOS-API-Key": disabled.internal_api_key.get_secret_value()},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "Email notifications disabled" in data["message"]


@pytest.mark.asyncio
async def test_rendering_service_triggers_email(
    email_settings: Settings, engine, sample_poster_entities
) -> None:
    from tbos_renderer.content_engine.repository import ContentRepository

    item, _ = sample_poster_entities
    repo = ContentRepository(engine)
    mock_notifier = MagicMock(spec=EmailNotificationService)
    mock_notifier.is_enabled.return_value = True
    mock_notifier.send_review_alert = AsyncMock(return_value=True)

    rendering_service = RenderingService(
        email_settings,
        repo,
        email_notifier=mock_notifier,
    )

    with patch.object(
        rendering_service.poster_renderer,
        "render_to_file",
        return_value={"sha256": "a" * 64, "width": 1080, "height": 1350},
    ):
        result = await rendering_service.render(item.id, version_number=1)

        assert result.status == "RENDERED"
        mock_notifier.send_review_alert.assert_awaited_once()
