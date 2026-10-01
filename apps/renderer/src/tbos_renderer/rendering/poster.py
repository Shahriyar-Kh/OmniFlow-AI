from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from tbos_renderer.config import BrandConfig
from tbos_renderer.content_engine.schemas import PosterContent, PracticeQuestion
from tbos_renderer.rendering.typography import get_font, get_text_dimensions, wrap_text


class PosterRenderer:
    """Deterministic Pillow-based hybrid renderer for luxury 1080x1080 educational posters."""

    def __init__(
        self,
        brand_config: BrandConfig | None = None,
        templates_dir: Path | str | None = None,
    ) -> None:
        self.brand_config = brand_config
        self.templates_dir = Path(templates_dir) if templates_dir else Path("storage/templates")

        palette = brand_config.brand.palette if brand_config else {}
        self.bg_color = palette.get("background", "#090E1A")
        self.primary_color = palette.get("primary", "#38BDF8")  # Vibrant Cyan
        self.gold_color = palette.get("accent", "#F59E0B")      # Warm Amber/Gold
        self.emerald_color = palette.get("secondary", "#10B981") # Python Emerald
        self.text_primary = "#F8FAFC"                           # Slate 50
        self.text_secondary = "#94A3B8"                         # Slate 400
        self.card_bg = "#0F172A"                                # Dark Slate Container
        self.card_border = "#1E293B"                            # Border Slate
        self.code_bg = "#030712"                                # Code Editor BG
        self.output_bg = "#09101D"                              # Terminal Output BG

    def _load_base_canvas(self, template_name: str | None = None) -> Image.Image:
        """Load luxury master base template if present, or generate dynamically."""
        width, height = 1080, 1080
        template_file: Path | None = None

        if self.templates_dir and self.templates_dir.exists():
            if template_name:
                candidate = self.templates_dir / template_name
                if candidate.is_file():
                    template_file = candidate
            if not template_file:
                template_candidates = (
                    "master_template.png",
                    "luxury_base.png",
                    "base_template.png",
                    "template.png",
                )
                for fname in template_candidates:
                    candidate = self.templates_dir / fname
                    if candidate.is_file():
                        template_file = candidate
                        break
            if not template_file:
                pngs = list(self.templates_dir.glob("*.png"))
                if pngs:
                    template_file = pngs[0]

        if template_file and template_file.is_file():
            try:
                with Image.open(template_file) as loaded:
                    return loaded.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
            except Exception:
                pass

        return self._create_dynamic_canvas(width, height)

    def _create_dynamic_canvas(self, width: int, height: int) -> Image.Image:
        """Generate high-end dark luxury canvas with subtle tech grid and glowing radial auras."""
        image = Image.new("RGB", (width, height), color=self.bg_color)
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Subtle Tech Grid
        grid_spacing = 48
        grid_color = (30, 41, 59, 70)
        for x in range(0, width, grid_spacing):
            draw.line([(x, 0), (x, height)], fill=grid_color, width=1)
        for y in range(0, height, grid_spacing):
            draw.line([(0, y), (width, y)], fill=grid_color, width=1)

        # Glowing Radial Auras
        # Top-right cyan aura
        aura_cx, aura_cy = width - 80, 80
        for r in range(320, 20, -20):
            alpha = int(24 * (1.0 - (r / 320.0)))
            draw.ellipse(
                [aura_cx - r, aura_cy - r, aura_cx + r, aura_cy + r],
                fill=(56, 189, 248, alpha),
            )

        # Top-left gold aura
        gold_cx, gold_cy = 100, 80
        for r in range(240, 20, -20):
            alpha = int(18 * (1.0 - (r / 240.0)))
            draw.ellipse(
                [gold_cx - r, gold_cy - r, gold_cx + r, gold_cy + r],
                fill=(245, 158, 11, alpha),
            )

        # Bottom-right violet aura
        indigo_cx, indigo_cy = width - 100, height - 100
        for r in range(260, 20, -20):
            alpha = int(18 * (1.0 - (r / 260.0)))
            draw.ellipse(
                [indigo_cx - r, indigo_cy - r, indigo_cx + r, indigo_cy + r],
                fill=(99, 102, 241, alpha),
            )

        # Top accent dual-color stripe
        draw.rectangle([0, 0, width, 6], fill=(56, 189, 248, 255))
        draw.rectangle([0, 6, int(width * 0.38), 10], fill=(245, 158, 11, 255))

        return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")

    def _draw_bookmark_icon(
        self, draw: ImageDraw.ImageDraw, x: int, y: int, color: str = "#0B1120"
    ) -> None:
        """Draw clean vector bookmark ribbon icon without external font/emoji dependencies."""
        w, h = 12, 16
        notch = 4
        points = [
            (x, y),
            (x + w, y),
            (x + w, y + h),
            (x + (w // 2), y + h - notch),
            (x, y + h),
        ]
        draw.polygon(points, fill=color)

    def render(self, content: PosterContent) -> Image.Image:
        """Render complete 1080x1080 square educational poster."""
        width = 1080
        height = 1080
        image = self._load_base_canvas()
        draw = ImageDraw.Draw(image)

        margin_x = 64
        content_width = width - (margin_x * 2)

        # -------------------------------------------------------------------
        # 1. Header Bar: Academy Brand + Pillar Badge
        # -------------------------------------------------------------------
        current_y = 38
        brand_font = get_font(20, bold=True)
        draw.text(
            (margin_x, current_y),
            "TECHBUILT OPEN SCHOOL",
            fill=self.primary_color,
            font=brand_font,
        )

        pillar_text = content.metadata.content_pillar.upper()
        pillar_font = get_font(14, bold=True)
        pill_w, pill_h = get_text_dimensions(pillar_text, pillar_font, draw)
        pill_pad_x, pill_pad_y = 14, 6
        pill_x = width - margin_x - (pill_w + (pill_pad_x * 2))
        pill_rect = [
            pill_x,
            current_y - 2,
            pill_x + pill_w + (pill_pad_x * 2),
            current_y + pill_h + (pill_pad_y * 2),
        ]
        draw.rounded_rectangle(pill_rect, radius=8, fill="#1E293B", outline="#334155", width=1)
        draw.text(
            (pill_x + pill_pad_x, current_y + pill_pad_y - 1),
            pillar_text,
            fill="#38BDF8",
            font=pillar_font,
        )

        current_y += 46

        # -------------------------------------------------------------------
        # 2. Headline & Subheadline
        # -------------------------------------------------------------------
        headline_font = get_font(38, bold=True)
        headline_lines = wrap_text(content.headline, headline_font, content_width, draw)
        for line in headline_lines[:2]:
            draw.text((margin_x, current_y), line, fill=self.text_primary, font=headline_font)
            _, h = get_text_dimensions(line, headline_font, draw)
            current_y += h + 8

        if content.subheadline:
            sub_font = get_font(20, bold=False)
            sub_lines = wrap_text(content.subheadline, sub_font, content_width, draw)
            for line in sub_lines[:1]:
                draw.text((margin_x, current_y), line, fill=self.gold_color, font=sub_font)
                _, h = get_text_dimensions(line, sub_font, draw)
                current_y += h + 6

        current_y += 12

        # -------------------------------------------------------------------
        # 3. macOS / IDE Code Block Hero (with Terminal Output)
        # -------------------------------------------------------------------
        if content.code_snippet:
            ide_y = current_y
            raw_lines = [ln.rstrip() for ln in content.code_snippet.strip().splitlines()][:6]
            has_output = bool(content.code_output)

            # Window header (32px) + code lines (~26px each) + output block (~68px) + padding
            code_line_height = 24
            code_area_h = max(len(raw_lines) * code_line_height + 20, 70)
            output_area_h = 60 if has_output else 0
            ide_total_h = 36 + code_area_h + output_area_h + 16

            # Container card
            draw.rounded_rectangle(
                [margin_x, ide_y, width - margin_x, ide_y + ide_total_h],
                radius=14,
                fill=self.card_bg,
                outline=self.card_border,
                width=2,
            )

            # macOS top bar
            bar_h = 34
            draw.rectangle(
                [margin_x, ide_y, width - margin_x, ide_y + bar_h],
                fill="#161F30",
            )
            draw.line(
                [(margin_x, ide_y + bar_h), (width - margin_x, ide_y + bar_h)],
                fill=self.card_border,
                width=1,
            )

            # Colored window dots (macOS style)
            dots = [
                (margin_x + 18, ide_y + 17, "#EF4444"),  # Red
                (margin_x + 36, ide_y + 17, "#F59E0B"),  # Yellow
                (margin_x + 54, ide_y + 17, "#10B981"),  # Green
            ]
            for cx, cy, dot_color in dots:
                draw.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=dot_color)

            # Tab / Editor title
            tab_font = get_font(13, monospace=True, bold=True)
            draw.text(
                (margin_x + 76, ide_y + 10),
                "main.py",
                fill="#94A3B8",
                font=tab_font,
            )

            # Environment badge
            env_font = get_font(11, monospace=True, bold=True)
            env_label = "Python 3.13"
            ew, eh = get_text_dimensions(env_label, env_font, draw)
            env_x = width - margin_x - ew - 20
            draw.rounded_rectangle(
                [env_x - 8, ide_y + 8, env_x + ew + 8, ide_y + eh + 12],
                radius=4,
                fill="#0B132B",
                outline="#38BDF8",
                width=1,
            )
            draw.text((env_x, ide_y + 10), env_label, fill="#38BDF8", font=env_font)

            # Code lines inside editor
            code_font = get_font(17, monospace=True, bold=False)
            line_y = ide_y + bar_h + 12
            for line in raw_lines:
                draw.text((margin_x + 22, line_y), line, fill="#E2E8F0", font=code_font)
                line_y += code_line_height

            # Dedicated Terminal Output Container
            if has_output and content.code_output:
                out_y = line_y + 8
                out_rect = [
                    margin_x + 14,
                    out_y,
                    width - margin_x - 14,
                    out_y + output_area_h - 8,
                ]
                draw.rounded_rectangle(
                    out_rect, radius=8, fill=self.output_bg, outline="#1E293B", width=1
                )

                # Output marker badge
                out_badge_font = get_font(11, monospace=True, bold=True)
                draw.text(
                    (margin_x + 24, out_y + 8),
                    "OUTPUT >>",
                    fill=self.emerald_color,
                    font=out_badge_font,
                )

                out_text_font = get_font(15, monospace=True, bold=False)
                out_line = content.code_output.strip().splitlines()[0]
                draw.text(
                    (margin_x + 102, out_y + 6),
                    out_line,
                    fill="#38BDF8",
                    font=out_text_font,
                )

            current_y = ide_y + ide_total_h + 16

        # -------------------------------------------------------------------
        # 4. Takeaway Points (Core Insights)
        # -------------------------------------------------------------------
        point_font = get_font(18, bold=False)
        accent_colors = ["#38BDF8", "#F59E0B", "#10B981"]

        takeaways = content.teaching_points[:3]
        for idx, point in enumerate(takeaways):
            card_h = 52
            p_rect = [margin_x, current_y, width - margin_x, current_y + card_h]
            draw.rounded_rectangle(
                p_rect, radius=10, fill=self.card_bg, outline=self.card_border, width=1
            )

            # Accent vertical bar on the left
            acc_color = accent_colors[idx % len(accent_colors)]
            draw.rounded_rectangle(
                [margin_x, current_y, margin_x + 5, current_y + card_h],
                radius=4,
                fill=acc_color,
            )

            # Number badge: 01, 02, 03
            num_str = f"0{idx + 1}"
            num_font = get_font(14, bold=True)
            draw.text(
                (margin_x + 18, current_y + 18),
                num_str,
                fill=acc_color,
                font=num_font,
            )

            # Point text
            wrapped_pt = wrap_text(point, point_font, content_width - 80, draw)
            first_line = wrapped_pt[0] if wrapped_pt else point
            draw.text(
                (margin_x + 52, current_y + 16),
                first_line,
                fill=self.text_primary,
                font=point_font,
            )

            current_y += card_h + 8

        # -------------------------------------------------------------------
        # 5. Viral Practice Question (Interactive MCQ)
        # -------------------------------------------------------------------
        if content.practice_question:
            current_y += 6
            pq: PracticeQuestion = content.practice_question
            quiz_total_h = 175

            quiz_rect = [margin_x, current_y, width - margin_x, current_y + quiz_total_h]
            draw.rounded_rectangle(
                quiz_rect, radius=14, fill="#0F172A", outline="#F59E0B", width=2
            )

            # Header strip inside quiz card
            draw.rectangle(
                [margin_x + 2, current_y + 2, width - margin_x - 2, current_y + 32],
                fill="#17223B",
            )
            quiz_tag_font = get_font(12, bold=True)
            draw.text(
                (margin_x + 16, current_y + 8),
                "PRACTICE MCQ  •  TEST YOUR KNOWLEDGE",
                fill=self.gold_color,
                font=quiz_tag_font,
            )

            # Question text
            q_font = get_font(17, bold=True)
            q_lines = wrap_text(pq.question, q_font, content_width - 40, draw)
            q_text = q_lines[0] if q_lines else pq.question
            draw.text(
                (margin_x + 16, current_y + 42),
                q_text,
                fill=self.text_primary,
                font=q_font,
            )

            # 2x2 Options Grid
            opt_y = current_y + 72
            opt_w = (content_width - 50) // 2
            opt_h = 32
            opt_font = get_font(14, bold=False)

            opts = pq.options[:4]
            labels = ["A", "B", "C", "D"]
            for o_idx, opt_text in enumerate(opts):
                col = o_idx % 2
                row = o_idx // 2
                ox = margin_x + 16 + (col * (opt_w + 16))
                oy = opt_y + (row * (opt_h + 8))

                draw.rounded_rectangle(
                    [ox, oy, ox + opt_w, oy + opt_h],
                    radius=6,
                    fill="#1E293B",
                    outline="#334155",
                    width=1,
                )
                formatted_opt = (
                    f"{labels[o_idx]}) {opt_text}"
                    if not opt_text.startswith(f"{labels[o_idx]}")
                    else opt_text
                )
                draw.text(
                    (ox + 12, oy + 7),
                    formatted_opt,
                    fill="#E2E8F0",
                    font=opt_font,
                )

            # Comment CTA strip
            cta_y = current_y + 146
            cta_font = get_font(13, bold=True)
            cta_text = ">> COMMENT YOUR ANSWER (A, B, C, D) BELOW <<"
            cw, ch = get_text_dimensions(cta_text, cta_font, draw)
            draw.text(
                (margin_x + ((content_width - cw) // 2), cta_y),
                cta_text,
                fill=self.primary_color,
                font=cta_font,
            )

        # -------------------------------------------------------------------
        # 6. Footer & Save CTA
        # -------------------------------------------------------------------
        footer_y = height - 52
        footer_font = get_font(13, bold=False)
        footer_text = "TechBuilt Open School  •  Free Practical Education"
        draw.text(
            (margin_x, footer_y + 10),
            footer_text,
            fill=self.text_secondary,
            font=footer_font,
        )

        # Save for Practice Button with Ribbon Bookmark Icon
        btn_font = get_font(13, bold=True)
        btn_label = "SAVE FOR PRACTICE"
        bw, bh = get_text_dimensions(btn_label, btn_font, draw)
        btn_pad_x = 22
        btn_w = bw + (btn_pad_x * 2) + 20
        btn_h = 36
        btn_x = width - margin_x - btn_w
        btn_rect = [btn_x, footer_y + 2, btn_x + btn_w, footer_y + 2 + btn_h]

        draw.rounded_rectangle(btn_rect, radius=8, fill=self.primary_color)
        self._draw_bookmark_icon(draw, btn_x + 14, footer_y + 11, color="#090E1A")
        draw.text(
            (btn_x + 34, footer_y + 11),
            btn_label,
            fill="#090E1A",
            font=btn_font,
        )

        return image

    def render_to_file(self, content: PosterContent, output_path: Path) -> dict[str, Any]:
        """Render poster image to a PNG file and compute integrity metadata."""
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
