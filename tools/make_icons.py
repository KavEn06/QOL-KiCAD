"""Regenerate the toolbar icons in icons/ (needs Pillow)."""

import os

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icons")
S = 96  # drawn large, then scaled down for smooth edges


def trim(d, fg, hi):
    d.line([(14, 62), (82, 62)], fill=fg, width=7)
    d.line([(62, 82), (62, 40)], fill=fg, width=7)
    d.line([(62, 34), (62, 12)], fill=hi, width=5)
    d.line([(50, 12), (74, 32)], fill=hi, width=4)
    d.line([(74, 12), (50, 32)], fill=hi, width=4)


def clean(d, fg, hi):
    d.line([(16, 20), (16, 78), (80, 78), (80, 20), (58, 20)], fill=fg, width=7, joint="curve")
    d.line([(16, 20), (36, 20)], fill=fg, width=7)
    d.ellipse([(38, 11), (56, 29)], outline=hi, width=5)


def fillet(d, fg, hi):
    d.line([(14, 18), (52, 18)], fill=fg, width=7)
    d.line([(80, 46), (80, 84)], fill=fg, width=7)
    d.arc([(24, 18), (80, 74)], 270, 360, fill=hi, width=7)


def generate(d, fg, hi):
    d.rounded_rectangle([(12, 20), (84, 76)], radius=16, outline=fg, width=7)
    d.line([(48, 34), (48, 62)], fill=hi, width=6)
    d.line([(34, 48), (62, 48)], fill=hi, width=6)


def import_dxf(d, fg, hi):
    d.rounded_rectangle([(40, 34), (86, 84)], radius=10, outline=fg, width=7)
    d.line([(10, 14), (44, 48)], fill=hi, width=7)
    d.polygon([(50, 54), (26, 46), (42, 30)], fill=hi)


def live_follow(d, fg, hi):
    d.line([(12, 80), (40, 30), (84, 44)], fill=fg, width=7, joint="curve")
    d.ellipse([(28, 18), (52, 42)], fill=hi)
    d.line([(58, 14), (72, 14), (72, 28)], fill=hi, width=5)
    d.line([(72, 14), (56, 30)], fill=hi, width=5)


def sketch(d, fg, hi):
    d.line([(12, 84), (12, 40), (40, 40)], fill=fg, width=7, joint="curve")
    d.arc([(12, 12), (68, 68)], 0, 90, fill=fg, width=7)
    d.line([(12, 84), (40, 84)], fill=fg, width=7)
    d.line([(52, 78), (82, 30)], fill=hi, width=9)
    d.polygon([(44, 90), (48, 72), (60, 80)], fill=hi)


for name, draw in list(globals().items()):
    if not callable(draw) or name in ("Image", "ImageDraw"):
        continue
    for suffix, fg, hi in (("", (60, 60, 60, 255), (210, 60, 40, 255)), ("_dark", (225, 225, 225, 255), (255, 140, 90, 255))):
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        draw(ImageDraw.Draw(img), fg, hi)
        for size in (24, 48):
            img.resize((size, size), Image.LANCZOS).save(os.path.join(OUT, f"{name}{suffix}_{size}.png"))
