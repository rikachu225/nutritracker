"""
NutriTracker Icon Generator
Generates 192x192 and 512x512 PNG app icons using Pillow.

Design: Dark background with centered accent-colored circle and "N" lettermark.

Usage:
    pip install Pillow
    python generate_icons.py
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math

PROJECT_ROOT = Path(__file__).resolve().parent
ICONS_DIR = PROJECT_ROOT / "frontend" / "assets" / "icons"

BG_COLOR = (10, 10, 10)          # #0a0a0a
ACCENT_COLOR = (110, 231, 183)   # #6ee7b7
ACCENT_DIM = (110, 231, 183, 30) # low-opacity accent for outer ring


def draw_leaf(draw, cx, cy, size):
    """Draw a simplified leaf shape using polygon points."""
    # Leaf is a pointed oval / almond shape
    points = []
    steps = 60
    # Top half (right side)
    for i in range(steps + 1):
        t = i / steps  # 0 to 1
        # Parametric leaf: y goes from -size to +size, x bulges out
        y = cy - size + (2 * size * t)
        # Width peaks at ~35% from top
        bulge = math.sin(math.pi * t) * (size * 0.45)
        # Skew: wider near top-middle
        skew = math.sin(math.pi * (t ** 0.7))
        x = cx + bulge * skew * 0.9
        points.append((x, y))
    # Bottom half (left side, reverse)
    for i in range(steps, -1, -1):
        t = i / steps
        y = cy - size + (2 * size * t)
        bulge = math.sin(math.pi * t) * (size * 0.45)
        skew = math.sin(math.pi * (t ** 0.7))
        x = cx - bulge * skew * 0.9
        points.append((x, y))

    draw.polygon(points, fill=ACCENT_COLOR)


def draw_leaf_veins(draw, cx, cy, size, line_width):
    """Draw the center vein and side branches."""
    top_y = cy - size + int(size * 0.15)
    bot_y = cy + size - int(size * 0.12)

    # Center vein
    draw.line([(cx, top_y), (cx, bot_y)], fill=BG_COLOR, width=line_width)

    # Side branches (alternating left/right)
    branch_positions = [0.28, 0.40, 0.52, 0.64, 0.76]
    branch_len = size * 0.28
    for i, frac in enumerate(branch_positions):
        y = cy - size + (2 * size * frac)
        direction = 1 if i % 2 == 0 else -1
        # Angle branches upward slightly
        end_x = cx + direction * branch_len
        end_y = y - branch_len * 0.4
        draw.line(
            [(cx, y), (int(end_x), int(end_y))],
            fill=BG_COLOR,
            width=max(1, line_width - 1),
        )


def generate_icon(size: int, filename: str):
    """Generate a single icon PNG at the given size."""
    img = Image.new("RGBA", (size, size), BG_COLOR + (255,))
    draw = ImageDraw.Draw(img)

    cx, cy = size // 2, size // 2
    radius_outer = int(size * 0.34)
    radius_inner = int(size * 0.25)

    # Outer ring (subtle)
    ring_box = [cx - radius_outer, cy - radius_outer, cx + radius_outer, cy + radius_outer]
    draw.ellipse(ring_box, outline=ACCENT_DIM, width=max(2, size // 80))

    # Inner filled circle (very subtle background)
    inner_box = [cx - radius_inner, cy - radius_inner, cx + radius_inner, cy + radius_inner]
    dim_fill = (110, 231, 183, 25)
    draw.ellipse(inner_box, fill=dim_fill)

    # Leaf
    leaf_size = int(size * 0.23)
    draw_leaf(draw, cx, cy, leaf_size)

    # Leaf veins
    vein_width = max(2, size // 100)
    draw_leaf_veins(draw, cx, cy, leaf_size, vein_width)

    # Rounded corner mask
    corner_radius = size // 6
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(
        [0, 0, size - 1, size - 1],
        radius=corner_radius,
        fill=255,
    )
    img.putalpha(mask)

    # Save
    output_path = ICONS_DIR / filename
    img.save(str(output_path), "PNG")
    print(f"Generated: {output_path} ({size}x{size})")


def generate_fallback_icon(size: int, filename: str):
    """Fallback: simple circle with 'N' lettermark if leaf drawing fails."""
    img = Image.new("RGBA", (size, size), BG_COLOR + (255,))
    draw = ImageDraw.Draw(img)

    cx, cy = size // 2, size // 2
    circle_r = int(size * 0.32)

    # Accent circle
    draw.ellipse(
        [cx - circle_r, cy - circle_r, cx + circle_r, cy + circle_r],
        fill=ACCENT_COLOR,
    )

    # "N" in center
    font_size = int(size * 0.36)
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except (IOError, OSError):
            font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), "N", font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = cx - tw // 2 - bbox[0]
    ty = cy - th // 2 - bbox[1]
    draw.text((tx, ty), "N", fill=BG_COLOR, font=font)

    # Rounded corner mask
    corner_radius = size // 6
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(
        [0, 0, size - 1, size - 1],
        radius=corner_radius,
        fill=255,
    )
    img.putalpha(mask)

    output_path = ICONS_DIR / filename
    img.save(str(output_path), "PNG")
    print(f"Generated (fallback): {output_path} ({size}x{size})")


def main():
    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    sizes = [
        (192, "icon-192.png"),
        (512, "icon-512.png"),
    ]

    for size, filename in sizes:
        try:
            generate_icon(size, filename)
        except Exception as e:
            print(f"Leaf icon failed for {size}x{size}: {e}")
            print("Falling back to lettermark icon...")
            generate_fallback_icon(size, filename)


if __name__ == "__main__":
    main()
