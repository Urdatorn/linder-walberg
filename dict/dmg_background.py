"""The background of the macOS disk image (make dmg in dict/src): the lexicon on the
left, an arrow, the Dictionaries folder on the right, and what to do, in Swedish.
Writes dict/src/dmg/background.png and background@2x.png (Finder window 640x400;
the icons sit at (160, 205) and (480, 205), as the Makefile places them):

    python dict/dmg_background.py
"""

from __future__ import annotations

import io
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONTS = HERE.parent / "app/src/fonts"
PAPER, INK, FAINT, RED = "#f6f2e9", "#2b2620", "#7a7166", "#9b1c1c"


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
    # the arrow between the two icons
    y = s(205)
    d.line((s(250), y, s(380), y), fill=RED, width=s(4))
    d.polygon([(s(392), y), (s(374), y - s(11)), (s(374), y + s(11))], fill=RED)
    d.text((s(320), s(318)), "Dra lexikonet till mappen Dictionaries.", font=text, fill=INK, anchor="mm")
    d.text((s(320), s(346)), "Öppna sedan programmet Ordbok och välj lexikonet där.", font=text, fill=FAINT, anchor="mm")
    return im


def main() -> None:
    out = HERE / "src/dmg"
    out.mkdir(exist_ok=True)
    draw(1).save(out / "background.png")
    draw(2).save(out / "background@2x.png")
    print("written", out / "background.png", out / "background@2x.png")


if __name__ == "__main__":
    main()
