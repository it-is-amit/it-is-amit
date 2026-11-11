#!/usr/bin/env python3
"""Render the GitHub profile hero banner (dark + light) at 2x with real fonts."""
import pathlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONTDIR = pathlib.Path(__file__).parent / "fonts"
OUT = pathlib.Path(__file__).parent.parent / "assets"
SS = 2                      # supersample factor (canvas is 1200x330 CSS -> 2400x680)
W, H = 1200 * SS, 330 * SS

ANTON = FONTDIR / "anton-latin-400-normal.ttf"
INTER = {w: FONTDIR / f"inter-latin-{w}-normal.ttf" for w in (500, 600, 700)}

THEMES = {
    "dark": dict(
        bg=(10, 12, 16), grid=(21, 26, 34), glow=(255, 106, 43), glow_op=0.32,
        eyebrow=(110, 118, 129), name=(245, 247, 250), numeral=(255, 106, 43),
        role=(255, 138, 76), stack=(139, 148, 158), label=(92, 101, 112),
        a1=(255, 106, 43), a2=(255, 176, 103),
    ),
    "light": dict(
        bg=(250, 247, 243), grid=(231, 224, 216), glow=(255, 106, 43), glow_op=0.17,
        eyebrow=(138, 131, 120), name=(15, 17, 21), numeral=(232, 80, 26),
        role=(209, 68, 15), stack=(107, 101, 92), label=(138, 131, 120),
        a1=(232, 80, 26), a2=(255, 148, 72),
    ),
}


def tracked_width(text, font, track):
    return sum(font.getlength(c) for c in text) + track * (len(text) - 1)


def draw_tracked(draw, xy, text, font, fill, track, anchor="left"):
    """Draw text with manual letter-spacing. anchor: 'left' | 'right'. Baseline xy."""
    total = tracked_width(text, font, track)
    x = xy[0] - total if anchor == "right" else xy[0]
    for ch in text:
        draw.text((x, xy[1]), ch, font=font, fill=fill, anchor="ls")
        x += font.getlength(ch) + track
    return total


def fit_font(path, text, target_w, track, start=400):
    """Largest size whose tracked width stays <= target_w."""
    size = start
    while size > 10:
        f = ImageFont.truetype(str(path), size)
        if tracked_width(text, f, track) <= target_w:
            return f
        size -= 2
    return ImageFont.truetype(str(path), 10)


def radial_mask(w, h, cx, cy, rx, ry):
    yy, xx = np.mgrid[0:h, 0:w]
    t = np.sqrt(((xx - cx * w) / (rx * w)) ** 2 + ((yy - cy * h) / (ry * h)) ** 2)
    return np.clip(1 - t, 0, 1)


def accent_gradient(w, h, c1, c2):
    ramp = np.linspace(0, 1, w)
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for i, ch in enumerate((0, 1, 2)):
        arr[:, :, i] = np.interp(ramp, [0, 1], [c1[ch], c2[ch]]).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def rounded_mask(w, h, r):
    m = Image.new("L", (w * 4, h * 4), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * 4 - 1, h * 4 - 1], radius=r * 4, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def build(theme):
    t = THEMES[theme]
    img = Image.new("RGB", (W, H), t["bg"])

    # soft accent glow, top-right
    glow = np.clip(radial_mask(W, H, 0.90, 0.06, 0.86, 1.15), 0, 1) ** 2.4
    base = np.asarray(img).astype(np.float32)
    tint = np.array(t["glow"], dtype=np.float32)
    a = (glow * t["glow_op"])[:, :, None]
    img = Image.fromarray(np.clip(base * (1 - a) + tint * a, 0, 255).astype(np.uint8), "RGB")

    d = ImageDraw.Draw(img)
    S = SS

    # hairline grid
    d.line([(76 * S, 0), (76 * S, H)], fill=t["grid"], width=S)
    d.line([(0, 44 * S), (W, 44 * S)], fill=t["grid"], width=S)
    d.line([(0, H - S), (W, H - S)], fill=t["grid"], width=S)

    # ---- outlined "05" (bottom right) ----
    num_font = ImageFont.truetype(str(INTER[700]), 196 * S)
    box = (1128 * S, 244 * S)
    stroke = Image.new("L", (W, H), 0)
    ImageDraw.Draw(stroke).text(box, "05", font=num_font, fill=255,
                                anchor="rs", stroke_width=int(2.2 * S), stroke_fill=255)
    fillm = Image.new("L", (W, H), 0)
    ImageDraw.Draw(fillm).text(box, "05", font=num_font, fill=255, anchor="rs")
    ring = np.clip(np.asarray(stroke, np.int16) - np.asarray(fillm, np.int16), 0, 255).astype(np.uint8)
    ring = Image.fromarray(ring).point(lambda v: int(v * 0.26))
    img.paste(Image.new("RGB", (W, H), t["numeral"]), (0, 0), ring)

    lab_font = ImageFont.truetype(str(INTER[600]), 14 * S)
    d = ImageDraw.Draw(img)
    draw_tracked(d, (1128 * S, 284 * S), "YEARS SHIPPING", lab_font, t["label"], 6.2 * S, "right")

    # ---- eyebrow ----
    eye = ImageFont.truetype(str(INTER[600]), 14 * S)
    draw_tracked(d, (118 * S, 58 * S), "FRONTEND ENGINEER \u2014 INDIA", eye, t["eyebrow"], 4.8 * S)

    # ---- name ----
    name_font = ImageFont.truetype(str(ANTON), 130 * S)
    draw_tracked(d, (114 * S, 192 * S), "AMIT VERMA", name_font, t["name"], 2 * S)

    # ---- accent bar ----
    bw, bh, br = 118 * S, 6 * S, 3 * S
    img.paste(accent_gradient(bw, bh, t["a1"], t["a2"]), (118 * S, 210 * S),
              rounded_mask(bw, bh, br))
    d = ImageDraw.Draw(img)

    # ---- role + stack ----
    role = ImageFont.truetype(str(INTER[700]), 24 * S)
    draw_tracked(d, (118 * S, 256 * S), "SENIOR FRONTEND DEVELOPER", role, t["role"], 6 * S)

    stack = ImageFont.truetype(str(INTER[500]), 17 * S)
    draw_tracked(d, (118 * S, 298 * S), "REACT.JS \u00b7 NEXT.JS \u00b7 TYPESCRIPT", stack, t["stack"], 2.4 * S)

    # ---- bottom fade hairline ----
    ramp = np.sin(np.linspace(0, np.pi, W)) ** 1.4
    fade = np.tile((ramp * 130).astype(np.uint8)[None, :], (S, 1))
    img.paste(Image.new("RGB", (W, S), t["a1"]), (0, H - S), Image.fromarray(fade, "L"))

    return img


for name in THEMES:
    im = build(name)
    im.save(OUT / f"hero-{name}.png", optimize=True)
    print(name, f"{W}x{H}", (OUT / f"hero-{name}.png").stat().st_size // 1024, "KB")

for p in OUT.glob("*.svg"):
    p.unlink()
