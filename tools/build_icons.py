#!/usr/bin/env python3
"""Generate deterministic PNG and Windows ICO assets from the app icon geometry."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
GREEN = "#2F6F5E"
WHITE = "#FFFFFF"


def main() -> int:
    assets = Path(__file__).resolve().parents[1] / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((40, 40, 984, 984), radius=210, fill=GREEN)
    draw.ellipse((180, 122, 844, 786), fill=WHITE)
    draw.polygon(((205, 585), (819, 585), (512, 938)), fill=WHITE)
    draw.ellipse((322, 264, 702, 644), fill=GREEN)
    draw.line(
        ((406, 452), (478, 524), (626, 364)),
        fill=WHITE,
        width=54,
        joint="curve",
    )
    image.save(assets / "app-icon.png", optimize=True)
    image.save(
        assets / "app-icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
