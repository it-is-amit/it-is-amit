#!/usr/bin/env python3
"""
Build the GitHub profile artwork as hand-authored SVG with text converted to outlines.

Two constraints drive every decision here:

1. FONTS. GitHub's image proxy strips external resources, so a webfont <link> never
   loads and the type silently falls back to a system font. Converting glyphs to
   <path> outlines makes the typography render identically everywhere.

2. SIZE. GitHub renders README images at roughly 860-900px in the content column,
   so a 1160px canvas shrinks every font by ~25% and small text becomes unreadable.
   All artwork is therefore authored at 900px — one canvas pixel is one screen pixel.

Outputs (dark + light variants):
  assets/hero-{dark,light}.svg    name, role, accent, contact pills
  assets/bento-{dark,light}.svg   stack + selected work

Motion is SMIL <animate> only. No JS, no third-party services, no external images.
"""
import gzip
import pathlib
import re
import xml.etree.ElementTree as ET

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONTS = ROOT / "tools" / "fonts"
ICONS = ROOT / "tools" / "icons"
OUT = ROOT / "assets"
OUT.mkdir(exist_ok=True)

ANTON = FONTS / "anton-latin-400-normal.ttf"
INTER = {w: FONTS / f"inter-latin-{w}-normal.ttf" for w in (500, 600, 700)}

# ---------------------------------------------------------------- brand colours
BRAND = {
    "react": "#61DAFB", "nextdotjs": "#EDEDED", "typescript": "#3178C6",
    "javascript": "#F7DF1E", "tailwindcss": "#38BDF8", "tanstack": "#FF4154",
    "redux": "#764ABC", "framer": "#0055FF", "figma": "#F24E1E",
    "github": "#EDEDED", "gmail": "#EA4335", "firebase": "#FFCA28",
    "mongodb": "#47A248", "postgresql": "#4169E1", "git": "#F05032",
    "postman": "#FF6C37", "vercel": "#EDEDED", "netlify": "#00C7B7",
}
# light theme needs darker variants for the near-white brand marks
BRAND_LIGHT = dict(BRAND, nextdotjs="#111111", github="#111111", vercel="#111111",
                   javascript="#C9A227", tanstack="#D92B38", framer="#0055FF")

THEMES = {
    "dark": dict(
        bg="#0A0C10", tile="#12151C", chip="#1A1F28", stroke="#252B36",
        ink="#F4F6F9", ink2="#D3DAE3", muted="#9BA5B1", dim="#68727E",
        accent="#FF6A2B", accent2="#FFB067", brand=BRAND,
    ),
    "light": dict(
        bg="#FAF7F3", tile="#FFFFFF", chip="#F5F0E9", stroke="#E5DED4",
        ink="#0E1116", ink2="#33302B", muted="#635E56", dim="#8A8378",
        accent="#E8502A", accent2="#FF9A4D", brand=BRAND_LIGHT,
    ),
}

# ---------------------------------------------------------------- font plumbing
_cache: dict = {}
_NUM = re.compile(r"-?\d+\.?\d*")


def _font(path):
    if path not in _cache:
        tt = TTFont(str(path))
        _cache[path] = (tt, tt.getGlyphSet())
    return _cache[path]


def _round_path(d: str, nd: int = 0) -> str:
    def fmt(m):
        v = round(float(m.group()), nd)
        return f"{v:g}" if v != int(v) else str(int(v))
    return _NUM.sub(fmt, d)


def text_width(text, path, size, track=0.0):
    tt, _ = _font(path)
    sc = size / tt["head"].unitsPerEm
    cmap, hmtx = tt.getBestCmap(), tt["hmtx"]
    w = 0.0
    for ch in text:
        name = cmap.get(ord(ch))
        w += (hmtx[name][0] * sc if name else size * 0.28) + track
    return w - track if text else 0.0


def text_paths(text, path, size, x, y, track=0.0, fill="currentColor"):
    """A whole text run as ONE <path>, transform baked into the outline coords."""
    tt, gs = _font(path)
    sc = size / tt["head"].unitsPerEm
    cmap, hmtx = tt.getBestCmap(), tt["hmtx"]
    pen = SVGPathPen(gs)
    dx = 0.0
    for ch in text:
        name = cmap.get(ord(ch))
        if name is None:
            dx += size * 0.28 + track
            continue
        gs[name].draw(TransformPen(pen, (sc, 0, 0, -sc, x + dx, y)))
        dx += hmtx[name][0] * sc + track
    return f'<g fill="{fill}"><path d="{_round_path(pen.getCommands())}"/></g>', text_width(text, path, size, track)


def text_bbox(text, path, size, track=0.0):
    """True ink bounds of a text run at the origin, in the same order as text_paths."""
    from fontTools.pens.boundsPen import BoundsPen

    tt, gs = _font(path)
    sc = size / tt["head"].unitsPerEm
    cmap, hmtx = tt.getBestCmap(), tt["hmtx"]
    bp = BoundsPen(gs)
    dx = 0.0
    for ch in text:
        name = cmap.get(ord(ch))
        if name is None:
            dx += size * 0.28 + track
            continue
        gs[name].draw(TransformPen(bp, (sc, 0, 0, -sc, dx, 0)))
        dx += hmtx[name][0] * sc + track
    return bp.bounds  # (xMin, yMin, xMax, yMax) with y already flipped


def text_at_top(text, path, size, x, top, track=0.0, fill="currentColor"):
    """Place display type so the top of its ink lands exactly on `top`.

    Returns (markup, ink_bottom) so callers can flow the next element beneath the
    real outline bounds instead of guessing at a baseline offset.
    """
    b = text_bbox(text, path, size, track)
    # y is flipped, so ink top is yMin (negative offset above baseline) and the
    # ink bottom is yMax
    baseline = top - b[1] if b else top + size
    markup, _ = text_paths(text, path, size, x, baseline, track, fill)
    ink_bottom = baseline + (b[3] if b else size)
    return markup, ink_bottom


def fit(text, path, target_w, track=0.0, start=200):
    size = start
    while size > 6 and text_width(text, path, size, track * size) > target_w:
        size -= 1
    return size


# ---------------------------------------------------------------- icons
_icon_cache: dict = {}


def icon(slug, x, y, size, color):
    """Simple Icons glyph (24x24) as a filled path at (x, y)."""
    if slug not in _icon_cache:
        root = ET.parse(ICONS / f"{slug}.svg").getroot()
        path = root.find("{http://www.w3.org/2000/svg}path")
        _icon_cache[slug] = path.get("d")
    s = size / 24.0
    return (f'<g transform="translate({x:.1f} {y:.1f}) scale({s:.4f})">'
            f'<path d="{_icon_cache[slug]}" fill="{color}"/></g>')


def defs(t, uid):
    a = t["accent"]
    dark = uid.startswith("d")
    return f"""  <defs>
    <linearGradient id="ac-{uid}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{t['accent2']}"/>
    </linearGradient>
    <radialGradient id="glow-{uid}" cx="0.82" cy="0.0" r="0.9">
      <stop offset="0" stop-color="{a}" stop-opacity="{0.38 if dark else 0.20}"/>
      <stop offset="0.45" stop-color="{a}" stop-opacity="{0.09 if dark else 0.05}"/>
      <stop offset="1" stop-color="{a}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="glow2-{uid}" cx="0.06" cy="1.0" r="0.7">
      <stop offset="0" stop-color="#7C5CFF" stop-opacity="{0.20 if dark else 0.10}"/>
      <stop offset="1" stop-color="#7C5CFF" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="fade-{uid}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{a}" stop-opacity="0"/>
      <stop offset="0.5" stop-color="{a}" stop-opacity="0.6"/>
      <stop offset="1" stop-color="{a}" stop-opacity="0"/>
    </linearGradient>
  </defs>"""


# ================================================================ HERO
HERO_W, HERO_H = 900, 348


def hero(theme):
    t = THEMES[theme]
    uid = "d" if theme == "dark" else "l"
    a = t["accent"]
    P = 48

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {HERO_W} {HERO_H}" width="{HERO_W}" height="{HERO_H}" role="img" aria-label="Amit Verma, senior frontend developer and UI/UX designer. React, Next.js, TypeScript. Five years.">']
    parts.append(defs(t, uid))
    parts.append(f'<rect width="{HERO_W}" height="{HERO_H}" fill="{t["bg"]}"/>')
    parts.append(f'<rect width="{HERO_W}" height="{HERO_H}" fill="url(#glow-{uid})"/>')
    parts.append(f'<rect width="{HERO_W}" height="{HERO_H}" fill="url(#glow2-{uid})"/>')

    # eyebrow with a live dot
    eb = "FRONTEND DEVELOPER  ·  UI/UX DESIGNER"
    parts.append(text_paths(eb, INTER[600], 13, P + 16, 36, 3.2, t["muted"])[0])
    parts.append(f'<circle cx="{P + 2}" cy="32" r="5" fill="{a}">'
                 f'<animate attributeName="opacity" values="1;0.2;1" dur="2.4s" repeatCount="indefinite"/></circle>')

    # name — bigger than before, tight tracking
    name_size = fit("AMIT VERMA", ANTON, 700, 0.01, start=118)
    nm, name_bottom = text_at_top("AMIT VERMA", ANTON, name_size, P - 2, 58, 0.01 * name_size, t["ink"])
    parts.append(nm)
    role_y = name_bottom + 34

    # role in accent
    parts.append(text_paths("SENIOR FRONTEND DEVELOPER", INTER[700], 21, P, role_y, 4.4, a)[0])
    stack_y = role_y + 30

    # stack line with real brand icons
    stack = [("react", "React"), ("nextdotjs", "Next.js"), ("typescript", "TypeScript")]
    x = P
    for slug, lbl in stack:
        parts.append(icon(slug, x, stack_y - 17, 21, t["brand"][slug]))
        m, w = text_paths(lbl, INTER[600], 16, x + 29, stack_y, 0.2, t["ink2"])
        parts.append(m)
        x += 28 + w + 26
        if slug != stack[-1][0]:
            parts.append(f'<circle cx="{x - 14:.1f}" cy="{stack_y - 7}" r="2" fill="{t["dim"]}"/>')

    parts.append(text_paths("5 years building product UIs for 5K–50K users", INTER[500], 14, P, stack_y + 36, 0.2, t["muted"])[0])

    # contact pills
    pills = [("github", "GitHub", "it-is-amit"), ("linkedin", "LinkedIn", "amit-verma"),
             ("gmail", "Email", "amverma1204t")]
    px = P
    py = HERO_H - 36
    for slug, lbl, handle in pills:
        tw = text_width(f"{lbl}", INTER[600], 13, 0.3) + text_width(handle, INTER[500], 13, 0) + 54
        parts.append(f'<rect x="{px:.1f}" y="{py - 15}" width="{tw:.1f}" height="30" rx="15" '
                     f'fill="{t["chip"]}" stroke="{t["stroke"]}" stroke-width="1"/>')
        col = t["brand"].get(slug if slug != "linkedin" else "github", t["ink2"])
        if slug == "linkedin":
            col = "#0A66C2" if theme == "light" else "#4A9EFF"
        parts.append(icon(slug, px + 14, py - 9, 17, col))
        m, w = text_paths(lbl, INTER[600], 13, px + 39, py + 5, 0.3, t["ink"])
        parts.append(m)
        m2, w2 = text_paths(handle, INTER[500], 13, px + 39 + w + 6, py + 5, 0, t["dim"])
        parts.append(m2)
        px += tw + 10

    parts.append(f'<rect x="0" y="{HERO_H - 2}" width="{HERO_W}" height="2" fill="url(#fade-{uid})"/>')
    parts.append("</svg>")
    return "\n".join(parts)


# ================================================================ BENTO
PAD, GUT = 10, 14
BENTO_W = 900
INNER = BENTO_W - PAD * 2


def card(x, y, w, h, t, r=18, fill=None):
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" '
            f'fill="{fill or t["tile"]}" stroke="{t["stroke"]}" stroke-width="1.25"/>')


def label(text, x, y, t, color=None, size=12, track=3.2):
    return text_paths(text, INTER[600], size, x, y, track, color or t["dim"])[0]


def tech_tile(slug, lbl, x, y, t):
    """Icon tile: brand mark + label, both large enough to actually read."""
    w, h = 132, 60
    parts = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{t["chip"]}" '
             f'stroke="{t["stroke"]}" stroke-width="1"/>']
    parts.append(icon(slug, x + 14, y + 14, 24, t["brand"][slug]))
    m, _ = text_paths(lbl, INTER[600], 15, x + 14, y + 52, 0.1, t["ink2"])
    parts.append(m)
    return "".join(parts), w, h


def bento(theme):
    t = THEMES[theme]
    uid = "d" if theme == "dark" else "l"
    a = t["accent"]
    P = 0

    # --- geometry
    TOP_Y = 42
    STACK_H = 190
    WORK_Y = TOP_Y + STACK_H + 62
    WORK_H = 268
    H = WORK_Y + WORK_H + PAD

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {BENTO_W} {H}" width="{BENTO_W}" height="{H}" role="img" aria-label="Tech stack and three selected client projects for Amit Verma.">']
    parts.append(defs(t, uid))
    parts.append(f'<rect width="{BENTO_W}" height="{H}" fill="{t["bg"]}"/>')

    # ------------------------------------------------ 01 stack
    parts.append(label("01 — STACK", PAD, TOP_Y - 16, t))
    parts.append(card(PAD, TOP_Y, INNER, STACK_H, t))

    tiles = [("react", "React.js"), ("nextdotjs", "Next.js"), ("typescript", "TypeScript"),
             ("javascript", "JavaScript"), ("tailwindcss", "Tailwind"), ("tanstack", "TanStack"),
             ("redux", "Redux"), ("framer", "Framer"), ("figma", "Figma"),
             ("postgresql", "PostgreSQL"), ("mongodb", "MongoDB"), ("firebase", "Firebase")]
    tw, th, gap = 132, 60, 12.8
    grid_w = 6 * tw + 5 * gap  # 792 + 64 = 856 <= 880
    gx0 = PAD + (INNER - grid_w) / 2
    for i, (slug, lbl) in enumerate(tiles):
        r, c = divmod(i, 6)
        x = gx0 + c * (tw + gap)
        y = TOP_Y + 24 + r * (th + 12)
        markup, _, _ = tech_tile(slug, lbl, x, y, t)
        parts.append(markup)

    # ------------------------------------------------ 02 selected work
    parts.append(label("02 — SELECTED WORK", PAD, WORK_Y - 18, t))
    note = "CLIENT PROJECTS · NAMES WITHHELD"
    nw = text_width(note, INTER[600], 11, 2.6)
    parts.append(label(note, BENTO_W - PAD - nw, WORK_Y - 18, t, size=11, track=2.6))

    projects = [
        ("Fleet management dashboard",
         ["Live vehicle status, reporting and", "role-based access across 45+ screens."],
         "50K users", ["tanstack", "typescript", "firebase"]),
        ("School site + admin panel",
         ["Public site plus a CMS for exams,", "results, admissions and achievements."],
         "30K users", ["nextdotjs", "typescript"]),
        ("Industrial monitoring platform",
         ["Billing, inventory and plant ops for", "wastewater treatment sites."],
         "In production", ["react", "postgresql"]),
    ]

    cw = (INNER - GUT * 2) / 3
    for i, (name, desc, scale, stack) in enumerate(projects):
        cx = PAD + i * (cw + GUT)
        parts.append(card(cx, WORK_Y, cw, WORK_H, t, r=18))

        # scale badge — accent filled, top right
        bw = text_width(scale, INTER[700], 12, 0.4) + 22
        parts.append(f'<rect x="{cx + cw - 20 - bw:.1f}" y="{WORK_Y + 20}" width="{bw:.1f}" height="24" rx="12" '
                     f'fill="{a}" fill-opacity="0.16" stroke="{a}" stroke-opacity="0.5" stroke-width="1"/>')
        parts.append(label(scale, cx + cw - 20 - bw + 11, WORK_Y + 36, t, color=a, size=12, track=0.4))

        parts.append(text_paths(f"0{i+1}", INTER[600], 12, cx + 20, WORK_Y + 37, 1.2, t["dim"])[0])

        # title, wrapped by hand onto two lines at a readable size
        words, line, lines = name.split(), "", []
        for wd in words:
            trial = f"{line} {wd}".strip()
            if text_width(trial, INTER[600], 21, -0.2) > cw - 40:
                lines.append(line)
                line = wd
            else:
                line = trial
        lines.append(line)
        for j, ln in enumerate(lines):
            parts.append(text_paths(ln, INTER[600], 21, cx + 20, WORK_Y + 84 + j * 26, -0.2, t["ink"])[0])

        dy = WORK_Y + 84 + len(lines) * 26 + 14
        for j, ln in enumerate(desc):
            parts.append(text_paths(ln, INTER[500], 14, cx + 20, dy + j * 21, 0.1, t["muted"])[0])

        # mini stack icons along the bottom
        ix = cx + 20
        for slug in stack:
            parts.append(icon(slug, ix, WORK_Y + WORK_H - 40, 22, t["brand"][slug]))
            ix += 32

    parts.append("</svg>")
    return "\n".join(parts)


if __name__ == "__main__":
    for theme in THEMES:
        for name, builder in (("hero", hero), ("bento", bento)):
            markup = builder(theme)
            path = OUT / f"{name}-{theme}.svg"
            path.write_text(markup, encoding="utf-8")
            ET.fromstring(markup)  # fail loudly on malformed SVG
            gz = len(gzip.compress(markup.encode(), 9))
            print(f"{path.name:18} {path.stat().st_size // 1024:4} KB raw · {gz // 1024:4} KB gzip")
