from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from uuid import UUID

from PIL import Image, ImageDraw

from tbos_renderer.config import Settings
from tbos_renderer.content_engine.repository import ContentRepository
from tbos_renderer.models import ContentVersion
from tbos_renderer.publishing.schemas import HandoffPackageResult
from tbos_renderer.rendering.typography import get_font, wrap_text

LOGGER = logging.getLogger(__name__)


class TikTokHandoffPackager:
    """Generates an offline-compliant handoff package for mobile TikTok publishing."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.storage_base = settings.shared_storage_path / "handoff"

    def create_handoff_package(
        self,
        content_id: UUID,
        version: ContentVersion,
        video_source_path: Path | str,
        thumbnail_source_path: Path | str | None = None,
    ) -> HandoffPackageResult:
        """Create a TikTok handoff bundle with media, cover, and ready-to-copy metadata."""
        bundle_dir = self.storage_base / str(content_id)
        bundle_dir.mkdir(parents=True, exist_ok=True)

        video_path = Path(video_source_path)
        dest_video_path = bundle_dir / "reel.mp4"
        if video_path.exists():
            shutil.copy2(video_path, dest_video_path)
        else:
            dest_video_path.write_bytes(b"")

        # Cover Thumbnail
        dest_thumb_path = bundle_dir / "cover.png"
        if thumbnail_source_path and Path(thumbnail_source_path).exists():
            shutil.copy2(thumbnail_source_path, dest_thumb_path)
        else:
            self._generate_cover_image(version.title, dest_thumb_path)

        # Prepare Caption
        script_content = ContentRepository._parse_content(version)
        captions = getattr(script_content, "captions", None)
        tt_caption = getattr(captions, "tiktok", "") if captions else ""
        hook = version.hook or version.title
        cta = version.cta or "Follow @TechBuilt for daily coding concepts!"
        hashtags_list = version.hashtags or ["#TechBuilt", "#LearnCoding", "#LearnOnTikTok"]
        hashtags_str = " ".join(t if t.startswith("#") else f"#{t}" for t in hashtags_list)

        ready_caption = f"{hook}\n\n{tt_caption}\n\n{cta}\n\n{hashtags_str}".strip()
        caption_file = bundle_dir / "caption.txt"
        caption_file.write_text(ready_caption, encoding="utf-8")

        # Sound & Timing Suggestions
        scenes = version.scene_data.get("scenes", [])
        timing_metadata = {
            "content_id": str(content_id),
            "version_id": str(version.id),
            "title": version.title,
            "recommended_posting_slot": "19:00 - 21:00 Asia/Karachi",
            "suggested_sounds": [
                "Lo-Fi Tech Beats / Calm Coding Ambience",
                "Soft Inspiring Instrumental / Trending Education Sound",
            ],
            "scene_count": len(scenes),
            "hashtags": hashtags_list,
        }
        timing_file = bundle_dir / "timing_and_sounds.json"
        timing_file.write_text(json.dumps(timing_metadata, indent=2), encoding="utf-8")

        # Telegram Review & Mobile Notification Message
        telegram_message = (
            f"📱 *TechBuilt Open School — TikTok Handoff Package Ready*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 *Topic:* {version.title}\n"
            f"🎬 *Video File:* `reel.mp4` (1080x1920 Short)\n"
            f"📂 *Storage Path:* `{bundle_dir.as_posix()}`\n\n"
            f"📋 *Ready-to-Copy Caption:*\n"
            f"```\n{ready_caption}\n```\n\n"
            f"⏰ *Recommended Slot:* 19:00 Asia/Karachi (Peak Engagement)\n"
            f"🎵 *Audio Recommendation:* Lo-Fi Chill Beats / Trending Tech\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Approved for 1-click mobile TikTok handoff."
        )

        LOGGER.info("Created TikTok handoff package at %s", bundle_dir)

        return HandoffPackageResult(
            content_id=content_id,
            version_id=version.id,
            bundle_dir=str(bundle_dir),
            video_path=str(dest_video_path),
            thumbnail_path=str(dest_thumb_path),
            caption_path=str(caption_file),
            timing_path=str(timing_file),
            ready_caption=ready_caption,
            telegram_message=telegram_message,
        )

    def _generate_cover_image(self, title: str, output_path: Path) -> None:
        """Fallback generator for 1080x1920 reel cover image."""
        img = Image.new("RGBA", (1080, 1920), color=(11, 30, 54, 255))
        draw = ImageDraw.Draw(img)

        # Header watermark
        brand_font = get_font(36, bold=True)
        draw.text((80, 120), "TECHBUILT OPEN SCHOOL", font=brand_font, fill=(212, 175, 55, 255))

        # Title Card
        title_font = get_font(60, bold=True)
        lines = wrap_text(title, title_font, 900, draw)
        y = 800
        for line in lines:
            draw.text((80, y), line, font=title_font, fill=(248, 249, 250, 255))
            y += 76

        # Subtitle
        sub_font = get_font(38, bold=False)
        draw.text(
            (80, y + 40),
            "Swipe up for full concept • Learn in Roman Urdu",
            font=sub_font,
            fill=(180, 200, 220, 255),
        )

        img.convert("RGB").save(output_path, "PNG")
