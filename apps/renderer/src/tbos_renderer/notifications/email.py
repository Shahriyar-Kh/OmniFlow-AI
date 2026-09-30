from __future__ import annotations

import asyncio
import html
import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

from tbos_renderer.config import Settings
from tbos_renderer.models import ContentItem, ContentVersion

LOGGER = logging.getLogger(__name__)


def _send_smtp_sync(
    host: str,
    port: int,
    user: str | None,
    password: str | None,
    message: EmailMessage,
    timeout: float = 30.0,
) -> None:
    """Synchronous worker that connects, authenticates, and sends an EmailMessage via SMTP."""
    context = ssl.create_default_context()
    if port == 465:
        # SSL direct connection
        with smtplib.SMTP_SSL(host, port, context=context, timeout=timeout) as server:
            if user and password:
                server.login(user, password)
            server.send_message(message)
    else:
        # STARTTLS connection (standard for port 587 and others)
        with smtplib.SMTP(host, port, timeout=timeout) as server:
            server.ehlo()
            try:
                server.starttls(context=context)
                server.ehlo()
            except smtplib.SMTPNotSupportedError:
                LOGGER.warning(
                    "SMTP server on %s:%s does not support STARTTLS; proceeding plaintext.",
                    host,
                    port,
                )
            if user and password:
                server.login(user, password)
            server.send_message(message)


class EmailNotificationService:
    """Delivers editorial alerts to reviewers via configurable SMTP."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_enabled(self) -> bool:
        """Check whether email notifications are globally enabled and properly configured."""
        return bool(
            self.settings.feature_email_notifications_enabled
            and self.settings.smtp_host
            and self.settings.notification_email
        )

    def build_review_email(
        self,
        content_item: ContentItem,
        content_version: ContentVersion,
    ) -> EmailMessage:
        """Construct a multi-part (Plain-text + Responsive HTML) EmailMessage."""
        content_type = (content_item.content_type or "poster").lower()
        is_poster = content_type == "poster"
        format_label = "Poster (1080x1350)" if is_poster else "Reel Short (9:16)"
        badge_emoji = "📸" if is_poster else "🎬"

        title = content_version.title or content_item.topic
        hook = content_version.hook or "No hook provided"
        version_num = content_version.version_number
        pillar = content_item.content_pillar or "TechBuilt Curriculum"

        # Extract captions
        script_content = content_version.script_data.get("content", {})
        captions: dict[str, Any] = script_content.get("captions", {})
        ig_caption = captions.get("instagram") or content_version.caption or "N/A"
        fb_caption = captions.get("facebook") or content_version.caption or "N/A"
        tt_caption = captions.get("tiktok") or content_version.caption or "N/A"

        # Extract QA score if available
        quality_report = content_version.lineage.get("quality_report", {})
        qa_score = quality_report.get("total_score")
        qa_score_str = f"{qa_score}/100" if qa_score is not None else "Passed"

        hashtags_list = content_version.hashtags or []
        hashtags_str = " ".join(
            t if t.startswith("#") else f"#{t}" for t in hashtags_list
        ) or "#TechBuiltOpenSchool #LearnToCode"

        dashboard_url = self.settings.dashboard_public_url

        from_email = (
            self.settings.smtp_from
            or self.settings.smtp_user
            or "TechBuilt Open School <noreply@tbos.local>"
        )
        to_email = self.settings.notification_email or "admin@tbos.local"

        msg = EmailMessage()
        msg["Subject"] = f"[TBOS Review Alert] New {format_label}: {title}"
        msg["From"] = from_email
        msg["To"] = to_email

        # 1. Plain text fallback
        text_body = f"""TechBuilt Open School — Content Review Alert
=====================================================

A new educational content item has been rendered and is waiting for your review.

• Format: {format_label}
• Topic: {title}
• Pillar: {pillar}
• Version: v{version_num}
• QA Score: {qa_score_str}

Hook:
{hook}

Captions Preview:
• Instagram: {ig_caption}
• Facebook:  {fb_caption}
• TikTok:    {tt_caption}

Hashtags:
{hashtags_str}

Content ID: {content_item.id}
Version ID: {content_version.id}

-----------------------------------------------------
ACTION REQUIRED:
Please review and Approve or Reject this item on the dashboard:
{dashboard_url}

⚠️ Note: Human approval is strictly required before public publishing.
=====================================================
"""
        msg.set_content(text_body)

        # 2. Rich HTML alternative
        safe_title = html.escape(title)
        safe_pillar = html.escape(pillar)
        safe_hook = html.escape(hook)
        safe_ig = html.escape(ig_caption)
        safe_fb = html.escape(fb_caption)
        safe_tt = html.escape(tt_caption)
        safe_hashtags = html.escape(hashtags_str)
        safe_dashboard_url = html.escape(dashboard_url)
        content_id_str = str(content_item.id)

        badge_bg = "#3b82f6" if is_poster else "#8b5cf6"
        badge_text = "POSTER" if is_poster else "REEL SHORT"

        html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Content Review Alert</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background-color: #0f172a;
      color: #e2e8f0;
      margin: 0;
      padding: 24px;
    }}
    .container {{
      max-width: 640px;
      margin: 0 auto;
      background-color: #1e293b;
      border: 1px solid #334155;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
    }}
    .header {{
      background: linear-gradient(135deg, #1e1b4b, #312e81);
      padding: 24px;
      border-bottom: 1px solid #4338ca;
    }}
    .brand {{
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: #a5b4fc;
      font-weight: 700;
      margin: 0 0 8px 0;
    }}
    .title {{
      font-size: 22px;
      color: #ffffff;
      font-weight: 800;
      margin: 0 0 12px 0;
      line-height: 1.3;
    }}
    .badge {{
      display: inline-block;
      font-size: 11px;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 9999px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      background-color: {badge_bg};
      color: #ffffff;
    }}
    .content {{
      padding: 24px;
    }}
    .meta-grid {{
      display: table;
      width: 100%;
      margin-bottom: 20px;
      font-size: 13px;
    }}
    .meta-row {{
      display: table-row;
    }}
    .meta-label {{
      display: table-cell;
      padding: 6px 12px 6px 0;
      color: #94a3b8;
      font-weight: 600;
      width: 100px;
    }}
    .meta-val {{
      display: table-cell;
      padding: 6px 0;
      color: #f1f5f9;
    }}
    .hook-box {{
      background-color: #0f172a;
      border-left: 4px solid #38bdf8;
      padding: 14px 16px;
      border-radius: 4px;
      margin-bottom: 20px;
    }}
    .hook-title {{
      font-size: 12px;
      font-weight: 700;
      color: #38bdf8;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 4px;
    }}
    .hook-text {{
      font-size: 15px;
      color: #f8fafc;
      font-style: italic;
      line-height: 1.4;
    }}
    .captions-block {{
      margin-bottom: 24px;
    }}
    .caption-tab {{
      background-color: #0f172a;
      border: 1px solid #334155;
      border-radius: 6px;
      padding: 12px;
      margin-bottom: 10px;
      font-size: 13px;
      line-height: 1.5;
    }}
    .platform-name {{
      font-weight: 700;
      color: #cbd5e1;
      margin-bottom: 4px;
      display: flex;
      align-items: center;
    }}
    .btn-container {{
      text-align: center;
      margin: 32px 0 24px 0;
    }}
    .btn {{
      display: inline-block;
      background: linear-gradient(135deg, #2563eb, #1d4ed8);
      color: #ffffff !important;
      text-decoration: none;
      font-weight: 700;
      font-size: 16px;
      padding: 14px 32px;
      border-radius: 8px;
      box-shadow: 0 4px 14px 0 rgba(37, 99, 235, 0.4);
    }}
    .notice {{
      background-color: #1e1b4b;
      border: 1px solid #3730a3;
      border-radius: 8px;
      padding: 14px;
      font-size: 12px;
      color: #c7d2fe;
      line-height: 1.5;
      text-align: center;
    }}
    .footer {{
      padding: 18px 24px;
      background-color: #0f172a;
      border-top: 1px solid #1e293b;
      font-size: 11px;
      color: #64748b;
      text-align: center;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="brand">TechBuilt Open School</div>
      <div class="title">{safe_title}</div>
      <div>
        <span class="badge">{badge_emoji} {badge_text}</span>
        <span style="font-size: 12px; color: #94a3b8; margin-left: 8px;">
          Version v{version_num} &bull; QA: {qa_score_str}
        </span>
      </div>
    </div>
    <div class="content">
      <div class="meta-grid">
        <div class="meta-row">
          <div class="meta-label">Curriculum:</div>
          <div class="meta-val">{safe_pillar}</div>
        </div>
        <div class="meta-row">
          <div class="meta-label">Content ID:</div>
          <div class="meta-val"><code style="color: #93c5fd;">{content_id_str}</code></div>
        </div>
      </div>

      <div class="hook-box">
        <div class="hook-title">Roman Urdu Hook</div>
        <div class="hook-text">&ldquo;{safe_hook}&rdquo;</div>
      </div>

      <div class="captions-block">
        <div style="font-size: 13px; font-weight: 700; color: #94a3b8; margin-bottom: 8px;">
          MULTI-PLATFORM CAPTIONS
        </div>
        <div class="caption-tab">
          <div class="platform-name">📷 Instagram</div>
          <div style="color: #e2e8f0;">{safe_ig}</div>
        </div>
        <div class="caption-tab">
          <div class="platform-name">📘 Facebook</div>
          <div style="color: #e2e8f0;">{safe_fb}</div>
        </div>
        <div class="caption-tab">
          <div class="platform-name">🎵 TikTok</div>
          <div style="color: #e2e8f0;">{safe_tt}</div>
        </div>
      </div>

      <div style="font-size: 12px; color: #64748b; margin-bottom: 24px;">
        <strong>Hashtags:</strong> {safe_hashtags}
      </div>

      <div class="btn-container">
        <a href="{safe_dashboard_url}" class="btn" target="_blank">
          &rarr; Open Approval Dashboard
        </a>
      </div>

      <div class="notice">
        ⚠️ <strong>Human Approval Required:</strong> In accordance with security rules,
        human approval is required before publishing to social platforms.
      </div>
    </div>
    <div class="footer">
      TechBuilt Open School Local Automation &bull; Zero Monthly Software Cost
    </div>
  </div>
</body>
</html>
"""
        msg.add_alternative(html_body, subtype="html")
        return msg

    async def send_review_alert(
        self,
        content_item: ContentItem,
        content_version: ContentVersion,
    ) -> bool:
        """Format and deliver an editorial review notification to the configured reviewer."""
        if not self.is_enabled():
            LOGGER.info(
                "Email notifications disabled or unconfigured; skipping alert for %s.",
                content_item.id,
            )
            return False

        try:
            msg = self.build_review_email(content_item, content_version)
            host = self.settings.smtp_host
            assert host is not None
            port = self.settings.smtp_port
            user = self.settings.smtp_user
            password = (
                self.settings.smtp_password.get_secret_value()
                if self.settings.smtp_password
                else None
            )

            await asyncio.to_thread(
                _send_smtp_sync,
                host=host,
                port=port,
                user=user,
                password=password,
                message=msg,
                timeout=30.0,
            )
            LOGGER.info(
                "Review alert email delivered successfully for content %s to %s",
                content_item.id,
                self.settings.notification_email,
            )
            return True
        except Exception as exc:
            LOGGER.error(
                "Failed to deliver review alert email for content %s: %s",
                content_item.id,
                exc,
                exc_info=True,
            )
            return False
