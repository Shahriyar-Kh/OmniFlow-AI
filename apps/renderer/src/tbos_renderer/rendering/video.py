from __future__ import annotations

import asyncio
import hashlib
import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from PIL import Image, ImageDraw

from tbos_renderer.config import BrandConfig
from tbos_renderer.content_engine.schemas import ReelContent, ReelScene
from tbos_renderer.rendering.typography import get_font, get_text_dimensions, wrap_text

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class VideoResult:
    video_path: str
    duration_seconds: float
    width: int
    height: int
    fps: int
    sha256: str
    size_bytes: int
    mime_type: str = "video/mp4"


@runtime_checkable
class VideoCompositorEngine(Protocol):
    async def compose_reel(
        self,
        content: ReelContent,
        audio_path: Path,
        output_path: Path,
    ) -> VideoResult: ...


class FfmpegVideoCompositor:
    """Composites 1080x1920 (9:16) MP4 short reels using scene slide rendering and FFmpeg."""

    def __init__(
        self,
        brand_config: BrandConfig | None = None,
        ffmpeg_bin: str | None = None,
        ffprobe_bin: str | None = None,
    ) -> None:
        self.brand_config = brand_config
        palette = brand_config.brand.palette if brand_config else {}
        self.primary_color = palette.get("primary", "#155EEF")
        self.secondary_color = palette.get("secondary", "#0E9384")
        self.accent_color = palette.get("accent", "#F79009")
        self.bg_color = "#0B0F19"
        self.card_bg = "#161F30"
        self.card_border = "#2A3852"
        self.text_color = "#F8FAFC"
        self.muted_text = "#94A3B8"
        self.ffmpeg_bin = ffmpeg_bin or shutil.which("ffmpeg") or "ffmpeg"
        self.ffprobe_bin = ffprobe_bin or shutil.which("ffprobe") or "ffprobe"

    def render_scene_slide(
        self,
        scene: ReelScene,
        total_scenes: int,
        topic: str,
        pillar: str,
        is_final_scene: bool,
        cta_text: str | None = None,
    ) -> Image.Image:
        """Render a single 1080x1920 scene card image."""
        width = 1080
        height = 1920
        image = Image.new("RGB", (width, height), color=self.bg_color)
        draw = ImageDraw.Draw(image)

        margin_x = 80
        content_width = width - (margin_x * 2)

        # 1. Top Decorative Brand Bar
        draw.rectangle([0, 0, width, 16], fill=self.primary_color)
        draw.rectangle([0, 16, int(width * 0.4), 22], fill=self.accent_color)

        current_y = 90

        # 2. Header: Brand + Topic Pill
        brand_font = get_font(26, bold=True)
        draw.text(
            (margin_x, current_y),
            "TECHBUILT OPEN SCHOOL",
            fill=self.primary_color,
            font=brand_font,
        )

        topic_font = get_font(20, bold=True)
        pill_w, pill_h = get_text_dimensions(pillar.upper(), topic_font, draw)
        pill_pad_x, pill_pad_y = 18, 10
        pill_x = width - margin_x - (pill_w + (pill_pad_x * 2))
        draw.rounded_rectangle(
            [
                pill_x,
                current_y - 6,
                pill_x + pill_w + (pill_pad_x * 2),
                current_y + pill_h + (pill_pad_y * 2),
            ],
            radius=14,
            fill=self.secondary_color,
        )
        draw.text(
            (pill_x + pill_pad_x, current_y + pill_pad_y - 4),
            pillar.upper(),
            fill="#FFFFFF",
            font=topic_font,
        )

        current_y += 80

        # 3. Progress indicator: Segmented Progress Bar
        bar_height = 8
        bar_gap = 12
        segment_width = (content_width - (bar_gap * (total_scenes - 1))) // total_scenes
        for i in range(total_scenes):
            seg_x = margin_x + (i * (segment_width + bar_gap))
            seg_color = self.primary_color if i < scene.scene_number else "#1E293B"
            draw.rounded_rectangle(
                [seg_x, current_y, seg_x + segment_width, current_y + bar_height],
                radius=4,
                fill=seg_color,
            )

        current_y += 40

        # Scene Counter Tag
        scene_tag = f"SCENE {scene.scene_number} OF {total_scenes}"
        tag_font = get_font(20, bold=True)
        draw.text((margin_x, current_y), scene_tag, fill=self.accent_color, font=tag_font)

        # 4. Central Highlight Card: On-Screen Text
        card_start_y = 520
        card_min_height = 680
        card_padding = 60

        text_font = get_font(48, bold=True)
        text_lines = wrap_text(
            scene.on_screen_text, text_font, content_width - (card_padding * 2), draw
        )
        calc_text_h = len(text_lines) * 64
        card_height = max(card_min_height, calc_text_h + (card_padding * 2) + 100)

        card_rect = [margin_x, card_start_y, width - margin_x, card_start_y + card_height]
        draw.rounded_rectangle(
            card_rect, radius=28, fill=self.card_bg, outline=self.card_border, width=3
        )

        # Left accent stripe on card
        draw.rounded_rectangle(
            [margin_x, card_start_y + 40, margin_x + 10, card_start_y + card_height - 40],
            radius=5,
            fill=self.primary_color,
        )

        # Draw on-screen text lines centered vertically inside card
        line_start_y = card_start_y + ((card_height - calc_text_h) // 2)
        for line in text_lines:
            lw, lh = get_text_dimensions(line, text_font, draw)
            text_x = margin_x + ((content_width - lw) // 2)
            draw.text((text_x, line_start_y), line, fill=self.text_color, font=text_font)
            line_start_y += lh + 18

        # 5. Bottom Callout or Action Banner
        if is_final_scene and cta_text:
            cta_y = card_start_y + card_height + 80
            cta_h = 100
            cta_rect = [margin_x, cta_y, width - margin_x, cta_y + cta_h]
            draw.rounded_rectangle(cta_rect, radius=20, fill=self.accent_color)
            cta_font = get_font(30, bold=True)
            cw, ch = get_text_dimensions(cta_text, cta_font, draw)
            draw.text(
                (margin_x + ((content_width - cw) // 2), cta_y + ((cta_h - ch) // 2) - 2),
                cta_text,
                fill="#FFFFFF",
                font=cta_font,
            )
        elif scene.scene_number == 1:
            badge_y = card_start_y + card_height + 80
            badge_text = "SWIPE OR WATCH TO LEARN"
            badge_font = get_font(22, bold=True)
            bw, _ = get_text_dimensions(badge_text, badge_font, draw)
            draw.text(
                (margin_x + ((content_width - bw) // 2), badge_y),
                badge_text,
                fill=self.muted_text,
                font=badge_font,
            )

        # 6. Bottom Watermark
        footer_y = height - 90
        footer_font = get_font(20, bold=False)
        footer_text = "TechBuilt Open School  •  Follow for Practical Tech"
        fw, _ = get_text_dimensions(footer_text, footer_font, draw)
        draw.text(
            ((width - fw) // 2, footer_y),
            footer_text,
            fill=self.muted_text,
            font=footer_font,
        )

        return image

    async def compose_reel(
        self,
        content: ReelContent,
        audio_path: Path,
        output_path: Path,
    ) -> VideoResult:
        """Compose MP4 video from reel scenes and narration audio."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        total_scenes = len(content.scenes)
        total_duration = sum(scene.duration_seconds for scene in content.scenes)

        with tempfile.TemporaryDirectory(prefix="tbos_reel_") as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            scene_files: list[tuple[Path, float]] = []

            # 1. Render image for each scene
            for idx, scene in enumerate(content.scenes, start=1):
                is_final = idx == total_scenes
                img = self.render_scene_slide(
                    scene=scene,
                    total_scenes=total_scenes,
                    topic=content.metadata.topic,
                    pillar=content.metadata.content_pillar,
                    is_final_scene=is_final,
                    cta_text=content.cta if is_final else None,
                )
                scene_img_path = tmp_dir / f"scene_{idx:02d}.png"
                img.save(str(scene_img_path), format="PNG")
                scene_files.append((scene_img_path, scene.duration_seconds))

            # 2. Build FFmpeg concat script
            concat_path = tmp_dir / "concat.txt"
            concat_lines: list[str] = []
            for scene_path, duration in scene_files:
                escaped_path = scene_path.as_posix().replace("'", "'\\''")
                concat_lines.append(f"file '{escaped_path}'")
                concat_lines.append(f"duration {duration:.2f}")

            if scene_files:
                last_path = scene_files[-1][0].as_posix().replace("'", "'\\''")
                concat_lines.append(f"file '{last_path}'")

            concat_path.write_text("\n".join(concat_lines), encoding="utf-8")

            # 3. Execute FFmpeg
            cmd = [
                self.ffmpeg_bin,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_path),
                "-i",
                str(audio_path),
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "22",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "30",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(output_path),
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                err_msg = stderr.decode(errors="replace")
                LOGGER.error("FFmpeg reel composition failed: %s", err_msg)
                raise RuntimeError(
                    f"FFmpeg reel composition failed (code {process.returncode}): {err_msg[:300]}"
                )

        # Compute output metadata
        data = output_path.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()

        return VideoResult(
            video_path=str(output_path),
            duration_seconds=round(total_duration, 2),
            width=1080,
            height=1920,
            fps=30,
            sha256=sha256,
            size_bytes=len(data),
            mime_type="video/mp4",
        )
