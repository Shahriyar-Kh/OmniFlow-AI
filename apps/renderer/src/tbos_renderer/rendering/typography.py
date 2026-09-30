from __future__ import annotations

import os

from PIL import ImageDraw, ImageFont

FONT_CANDIDATES_REGULAR = [
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

FONT_CANDIDATES_BOLD = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a TrueType font with the requested size and weight, or fallback to default."""
    candidates = FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES_REGULAR
    for path_str in candidates:
        if os.path.exists(path_str):
            try:
                return ImageFont.truetype(path_str, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def get_text_dimensions(
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    draw: ImageDraw.ImageDraw | None = None,
) -> tuple[int, int]:
    """Calculate width and height of rendered text."""
    if not text:
        return 0, 0
    bbox = draw.textbbox((0, 0), text, font=font) if draw is not None else font.getbbox(text)
    width = int(bbox[2] - bbox[0])
    height = int(bbox[3] - bbox[1])
    return width, height


def wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    draw: ImageDraw.ImageDraw | None = None,
) -> list[str]:
    """Wrap text to fit within max_width pixels."""
    if not text:
        return []
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current_line: list[str] = []

    for word in words:
        trial = " ".join([*current_line, word])
        width, _ = get_text_dimensions(trial, font, draw)
        if width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                lines.append(word)

    if current_line:
        lines.append(" ".join(current_line))

    return lines
