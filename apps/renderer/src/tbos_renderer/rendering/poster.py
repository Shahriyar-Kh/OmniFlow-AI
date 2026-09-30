from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from tbos_renderer.config import BrandConfig
from tbos_renderer.content_engine.schemas import PosterContent
from tbos_renderer.rendering.typography import get_font, get_text_dimensions, wrap_text


class PosterRenderer:
    """Deterministic Pillow-based renderer for 1080x1350 educational posters."""

    def __init__(self, brand_config: BrandConfig | None = None) -> None:
        self.brand_config = brand_config
        palette = brand_config.brand.palette if brand_config else {}
        self.bg_color = palette.get("background", "#F8FAFC")
        self.primary_color = palette.get("primary", "#155EEF")
        self.secondary_color = palette.get("secondary", "#0E9384")
        self.accent_color = palette.get("accent", "#F79009")
        self.text_color = palette.get("text", "#101828")
        self.card_bg = "#FFFFFF"
        self.card_border = "#E2E8F0"
        self.muted_text = "#475467"

    def render(self, content: PosterContent) -> Image.Image:
        width = 1080
        height = 1350
        image = Image.new("RGB", (width, height), color=self.bg_color)
        draw = ImageDraw.Draw(image)

        # Top decorative brand stripe
        draw.rectangle([0, 0, width, 14], fill=self.primary_color)
        draw.rectangle([0, 14, int(width * 0.35), 20], fill=self.accent_color)

        current_y = 60
        margin_x = 70
        content_width = width - (margin_x * 2)

        # 1. Header: Brand Tracker + Pillar Pill Badge
        brand_font = get_font(22, bold=True)
        draw.text(
            (margin_x, current_y),
            "TECHBUILT OPEN SCHOOL",
            fill=self.primary_color,
            font=brand_font,
        )

        pillar_text = content.metadata.content_pillar.upper()
        pillar_font = get_font(18, bold=True)
        pill_w, pill_h = get_text_dimensions(pillar_text, pillar_font, draw)
        pill_pad_x, pill_pad_y = 16, 8
        pill_x = width - margin_x - (pill_w + (pill_pad_x * 2))
        pill_rect = [
            pill_x,
            current_y - 4,
            pill_x + pill_w + (pill_pad_x * 2),
            current_y + pill_h + (pill_pad_y * 2),
        ]
        draw.rounded_rectangle(pill_rect, radius=12, fill=self.secondary_color)
        draw.text(
            (pill_x + pill_pad_x, current_y + pill_pad_y - 2),
            pillar_text,
            fill="#FFFFFF",
            font=pillar_font,
        )

        current_y += 70

        # 2. Hero Headline
        headline_font = get_font(46, bold=True)
        headline_lines = wrap_text(content.headline, headline_font, content_width, draw)
        for line in headline_lines:
            draw.text((margin_x, current_y), line, fill=self.text_color, font=headline_font)
            _, h = get_text_dimensions(line, headline_font, draw)
            current_y += h + 14

        # Subheadline (if provided)
        if content.subheadline:
            current_y += 6
            sub_font = get_font(26, bold=False)
            sub_lines = wrap_text(content.subheadline, sub_font, content_width, draw)
            for line in sub_lines:
                draw.text((margin_x, current_y), line, fill=self.muted_text, font=sub_font)
                _, h = get_text_dimensions(line, sub_font, draw)
                current_y += h + 8

        current_y += 24

        # 3. Teaching Points Container Card
        card_start_y = current_y
        card_padding = 32
        point_font = get_font(25, bold=False)
        badge_font = get_font(20, bold=True)

        # Pre-calculate points height
        inner_width = content_width - (card_padding * 2) - 60  # minus badge width & gap
        point_line_blocks: list[list[str]] = []
        for point in content.teaching_points:
            lines = wrap_text(point, point_font, inner_width, draw)
            point_line_blocks.append(lines)

        estimated_points_height = sum(max(len(block) * 36, 44) + 24 for block in point_line_blocks)
        card_height = estimated_points_height + (card_padding * 2)

        # Draw card container
        card_rect = [margin_x, card_start_y, width - margin_x, card_start_y + card_height]
        draw.rounded_rectangle(
            card_rect, radius=20, fill=self.card_bg, outline=self.card_border, width=2
        )

        # Draw points inside card
        point_y = card_start_y + card_padding
        for idx, block in enumerate(point_line_blocks, start=1):
            badge_radius = 18
            badge_cx = margin_x + card_padding + badge_radius
            badge_cy = point_y + badge_radius + 2

            # Badge circle
            draw.ellipse(
                [
                    badge_cx - badge_radius,
                    badge_cy - badge_radius,
                    badge_cx + badge_radius,
                    badge_cy + badge_radius,
                ],
                fill=self.primary_color,
            )
            idx_str = str(idx)
            bw, bh = get_text_dimensions(idx_str, badge_font, draw)
            draw.text(
                (badge_cx - (bw // 2), badge_cy - (bh // 2) - 2),
                idx_str,
                fill="#FFFFFF",
                font=badge_font,
            )

            # Point lines
            text_x = margin_x + card_padding + 52
            line_y = point_y
            for line in block:
                draw.text((text_x, line_y), line, fill=self.text_color, font=point_font)
                _, lh = get_text_dimensions(line, point_font, draw)
                line_y += lh + 10

            point_y = max(line_y + 12, point_y + 56)

        current_y = card_start_y + card_height + 30

        # 4. CTA Banner
        cta_height = 80
        cta_rect = [margin_x, current_y, width - margin_x, current_y + cta_height]
        draw.rounded_rectangle(cta_rect, radius=16, fill=self.primary_color)

        cta_font = get_font(26, bold=True)
        cta_w, cta_h = get_text_dimensions(content.cta, cta_font, draw)
        cta_x = margin_x + ((content_width - cta_w) // 2)
        draw.text(
            (cta_x, current_y + ((cta_height - cta_h) // 2) - 2),
            content.cta,
            fill="#FFFFFF",
            font=cta_font,
        )

        # 5. Footer Watermark
        footer_y = height - 60
        footer_font = get_font(18, bold=False)
        footer_text = "TechBuilt Open School  •  Free Practical Tech Education"
        fw, _ = get_text_dimensions(footer_text, footer_font, draw)
        draw.text(
            ((width - fw) // 2, footer_y),
            footer_text,
            fill=self.muted_text,
            font=footer_font,
        )

        return image

    def render_to_file(self, content: PosterContent, output_path: Path) -> dict[str, Any]:
        image = self.render(content)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        data = buffer.getvalue()
        output_path.write_bytes(data)

        sha256 = hashlib.sha256(data).hexdigest()
        return {
            "local_path": str(output_path),
            "width": image.width,
            "height": image.height,
            "size_bytes": len(data),
            "sha256": sha256,
            "mime_type": "image/png",
        }
