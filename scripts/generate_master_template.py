from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def generate_luxury_base_template(output_path: Path) -> Path:
    """Generate master base template (1080x1080) with luxury deep navy, gold & cyan accents."""
    width, height = 1080, 1080
    image = Image.new("RGB", (width, height), color="#090E1A")
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 1. Subtle Tech Grid
    grid_spacing = 48
    grid_color = (30, 41, 59, 90)
    for x in range(0, width, grid_spacing):
        draw.line([(x, 0), (x, height)], fill=grid_color, width=1)
    for y in range(0, height, grid_spacing):
        draw.line([(0, y), (width, y)], fill=grid_color, width=1)

    # 2. Glowing Radial Auras
    # Top-right cyan aura
    aura_cx, aura_cy = width - 100, 100
    for r in range(380, 30, -15):
        alpha = int(28 * (1.0 - (r / 380.0)))
        draw.ellipse(
            [aura_cx - r, aura_cy - r, aura_cx + r, aura_cy + r],
            fill=(56, 189, 248, alpha),
        )

    # Top-left gold/amber aura
    gold_cx, gold_cy = 120, 100
    for r in range(280, 30, -20):
        alpha = int(20 * (1.0 - (r / 280.0)))
        draw.ellipse(
            [gold_cx - r, gold_cy - r, gold_cx + r, gold_cy + r],
            fill=(245, 158, 11, alpha),
        )

    # Bottom-right violet aura
    indigo_cx, indigo_cy = width - 100, height - 120
    for r in range(300, 30, -20):
        alpha = int(20 * (1.0 - (r / 300.0)))
        draw.ellipse(
            [indigo_cx - r, indigo_cy - r, indigo_cx + r, indigo_cy + r],
            fill=(99, 102, 241, alpha),
        )

    # Composite overlay onto base
    final_img = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_img.save(output_path, format="PNG", optimize=True)
    return output_path


if __name__ == "__main__":
    target = Path("storage/templates/master_template.png")
    generate_luxury_base_template(target)
    print(f"Master template created at: {target}")

