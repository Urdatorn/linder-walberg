"""The background of the macOS disk image (make dmg in dict/src): the lexicon on the
left and, beside it, how to install it, in Swedish. A link to the dictionaries folder
cannot go in the image: each user has their own (~/Library/Dictionaries), and
/Library/Dictionaries need not exist; Ordbok's File menu opens the user's own.
Writes dict/src/dmg/background.png and background@2x.png (Finder window 640x400;
the icon sits at (150, 215), as the Makefile places it):

    python dict/dmg_background.py
"""

from __future__ import annotations

import io
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONTS = HERE.parent / "app/src/fonts"
# PAPER a shade darker than the icon's own paper (#f6f2e9), so that the icon reads as one
PAPER, INK, FAINT, RED = "#e6dcc6", "#2b2620", "#7a7166", "#9b1c1c"


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Gentium from the web app's woff2, unpacked for Pillow."""
    f = TTFont(FONTS / name)
    f.flavor = None
    buf = io.BytesIO()
    f.save(buf)
    buf.seek(0)
    return ImageFont.truetype(buf, size)


def draw(scale: int) -> Image.Image:
    s = lambda v: round(v * scale)
    im = Image.new("RGB", (s(640), s(400)), PAPER)
    d = ImageDraw.Draw(im)
    title = font("gentium-normal-700-latin.woff2", s(26))
    text = font("gentium-normal-400-latin.woff2", s(17))
    d.text((s(320), s(52)), "Svenskt-grekiskt lexikon", font=title, fill=INK, anchor="mm")
    d.text((s(320), s(82)), "Linder & Walberg 1862", font=text, fill=FAINT, anchor="mm")
    steps = ["Öppna programmet Ordbok.",
             "Välj Arkiv › Öppna ordboksmappen.",
             "Dra lexikonet härifrån till den mappen.",
             "Starta om Ordbok och kryssa i lexikonet",
             "under Ordbok › Inställningar."]
    num = font("gentium-normal-700-latin.woff2", s(17))
    y = s(150)
    for k, line in enumerate(steps):
        if k < 4:
            d.text((s(282), y), f"{k + 1}.", font=num, fill=RED, anchor="ra")
        d.text((s(292), y), line, font=text, fill=INK, anchor="la")
        y += s(30) if k < 3 else s(24)
    return im


def main() -> None:
    out = HERE / "src/dmg"
    out.mkdir(exist_ok=True)
    draw(1).save(out / "background.png")
    draw(2).save(out / "background@2x.png")
    print("written", out / "background.png", out / "background@2x.png")


if __name__ == "__main__":
    main()
