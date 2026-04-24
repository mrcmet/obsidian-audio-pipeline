#!/usr/bin/env python3
"""
generate_icons.py — Generates icon.png and icon_active.png for the tray app.

Run once to produce the assets:
    python assets/generate_icons.py

Requires only Pillow (PIL).
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw

_OUT_DIR = Path(__file__).parent.resolve()
_SIZE = 64


def _draw_microphone(draw: ImageDraw.ImageDraw, color: str = "white") -> None:
    """Draw a simple geometric microphone centred in a 64×64 canvas."""
    # Mic body: rounded rectangle in the upper-centre
    body_x0, body_y0 = 24, 10
    body_x1, body_y1 = 40, 36
    radius = 8
    draw.rounded_rectangle([body_x0, body_y0, body_x1, body_y1], radius=radius, fill=color)

    # Stand arm: vertical line below body
    draw.rectangle([30, 36, 34, 46], fill=color)

    # Base: horizontal bar
    draw.rectangle([22, 46, 42, 50], fill=color)

    # Stand foot: small rectangle centred under base
    draw.rectangle([30, 50, 34, 54], fill=color)


def make_icon() -> Image.Image:
    img = Image.new("RGBA", (_SIZE, _SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background circle
    margin = 2
    draw.ellipse([margin, margin, _SIZE - margin, _SIZE - margin], fill="#1a7a6e")

    _draw_microphone(draw)
    return img


def make_icon_active() -> Image.Image:
    img = make_icon()
    draw = ImageDraw.Draw(img)

    # Green activity indicator in bottom-right corner
    indicator_radius = 8
    cx = _SIZE - indicator_radius - 2
    cy = _SIZE - indicator_radius - 2
    draw.ellipse(
        [cx - indicator_radius, cy - indicator_radius,
         cx + indicator_radius, cy + indicator_radius],
        fill="#00cc44",
        outline="white",
        width=1,
    )
    return img


def main() -> None:
    icon_path = _OUT_DIR / "icon.png"
    icon_active_path = _OUT_DIR / "icon_active.png"

    make_icon().save(icon_path)
    print(f"Written: {icon_path}")

    make_icon_active().save(icon_active_path)
    print(f"Written: {icon_active_path}")


if __name__ == "__main__":
    main()
