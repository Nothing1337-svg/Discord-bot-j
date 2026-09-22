import io
from functools import lru_cache

import regex
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .config import ROOT
from .i18n import tr


@lru_cache
def fonts(size):
    result = []
    for name in ("NotoSans-Bold.ttf", "NotoEmoji-Regular.ttf"):
        path = ROOT / "assets" / "fonts" / name
        with TTFont(path) as font:
            cmap = set(font.getBestCmap())
        result.append((ImageFont.truetype(str(path), size), cmap))
    return result


def draw_text(draw, xy, text, size, fill, max_width):
    """Keep grapheme clusters together; unsupported clusters become a visible '?' marker."""
    x, y = xy
    end = x + max_width
    for cluster in regex.findall(r"\X", text):
        chars = {ord(c) for c in cluster if c not in "\ufe0f\ufe0e\u200d"}
        font = next((font for font, cmap in fonts(size) if chars <= cmap), None)
        if font is None:
            cluster, font = "?", fonts(size)[0][0]
        width = draw.textlength(cluster, font=font)
        if x + width > end:
            break
        draw.text((x, y), cluster, font=font, fill=fill)
        x += width


def create_background(path):
    image = Image.new("RGB", (960, 540))
    draw = ImageDraw.Draw(image)
    for y in range(540):
        draw.line((0, y, 960, y), fill=(13 + y // 35, 19 + y // 24, 42 + y // 13))
    draw.ellipse((610, -240, 1160, 310), outline=(69, 94, 132), width=2)
    draw.ellipse((510, -340, 1260, 410), outline=(39, 65, 106), width=2)
    image.save(path)


def render(count, language="ru", background=None, title="COMMUNITY • LIVE"):
    if background is None:
        background = ROOT / "assets" / "background.png"
    with Image.open(background) as original:
        image = ImageOps.fit(original.convert("RGB"), (960, 540))
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    panel = ImageDraw.Draw(overlay)
    panel.rounded_rectangle((42, 36, 918, 504), radius=32, fill=(7, 15, 31, 205))
    image = Image.alpha_composite(image.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(image)
    draw.ellipse((80, 79, 93, 92), fill="#54e5b1")
    draw_text(draw, (109, 65), title, 22, "#b7c6da", 720)
    draw_text(draw, (78, 146), tr(language, "voice"), 30, "#f1f5fb", 800)
    draw_text(draw, (72, 191), str(count), 152, "#ffffff", 810)
    draw.line((80, 407, 880, 407), fill="#314661", width=2)
    draw_text(draw, (80, 433), tr(language, "subtitle"), 22, "#a7bad1", 800)
    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG")
    return output.getvalue()
