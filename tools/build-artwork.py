#!/usr/bin/env python3
"""
Build the GitHub profile artwork as hand-authored SVG with text converted to outlines.

Why outlines: GitHub serves README images from a proxy that strips most external
resources, so a webfont <link> will not load. Converting glyphs to <path> makes the
typography render identically on every device with no font dependency at all.

Outputs (dark + light variants):
  assets/hero-{dark,light}.svg        big condensed name + role, animated accent
  assets/bento-{dark,light}.svg       bento grid: about / stack / now / work
  assets/divider.svg                  hairline rule with section label

Animated with SMIL <animate> + CSS @keyframes inside the SVG (both are allowed in
GitHub's image sandbox; JS is not). All motion is opt-out friendly: the accent
animations are ambient (slow, low contrast), nothing flashes.
"""
import gzip
import pathlib
import re

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib.models import normalizeValue  # noqa: F401  (kept for future)

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONTS = ROOT / "tools" / "fonts"
OUT = ROOT / "assets"
OUT.mkdir(exist_ok=True)

ANTON = FONTS / "anton-latin-400-normal.ttf"
INTER = {w: FONTS / f"inter-latin-{w}-normal.ttf" for w in (500, 600, 700)}

# ---------------------------------------------------------------- theme tokens
THEMES = {
    "dark": dict(
        bg="#0B0D11", tile="#12161D", tile_hi="#171C25", stroke="#232A35",
        ink="#F2F5F9", ink2="#C9D1D9", muted="#8B949E", dim="#5A646F",
        chip="#181E27", accent="#FF6A2B", accent2="#FFB067", paper="#0B0D11",
    ),
    "light": dict(
        bg="#FAF7F3", tile="#FFFFFF", tile_hi="#F4EFE8", stroke="#E4DDD3",
        ink="#101318", ink2="#3A3630", muted="#6B655C", dim="#8A8378",
        chip="#F7F3ED", accent="#E8501A", accent2="#FF9448", paper="#FAF7F3",
    ),
}

# ---------------------------------------------------------------- font plumbing
_cache: dict = {}


def _font(path: pathlib.Path):
    if path not in _cache:
        _cache[path] = (TTFont(str(path)), TTFont(str(path)).getGlyphSet())
    return _cache[path]


_NUM = re.compile(r"-?\d+\.?\d*")


def _round_path(d: str, nd: int = 0) -> str:
    """Trim coordinate precision — SVG path decimals are the bulk of the file size."""
    def fmt(m):
        v = round(float(m.group()), nd)
        return f"{v:g}" if v != int(v) else str(int(v))
    return _NUM.sub(fmt, d)


def text_inner(text, path, size, x, y, track=0.0, extra=""):
    """A single <path> containing every glyph of `text`, positioned at baseline (x, y).

    The translate/scale/flip transform is baked into the outline coordinates, so a run
    of text costs one <path> instead of one per character — a much smaller file.
    """
    from fontTools.pens.transformPen import TransformPen

    tt, gs = _font(path)
    upm = tt["head"].unitsPerEm
    sc = size / upm
    cmap = tt.getBestCmap()
    hmtx = tt["hmtx"]

    pen = SVGPathPen(gs)
    dx = 0.0
    for ch in text:
        name = cmap.get(ord(ch))
        if name is None:
            dx += size * 0.28 + track
            continue
        # fresh TransformPen per glyph: scale, flip y, then place at the run offset
        gs[name].draw(TransformPen(pen, (sc, 0, 0, -sc, x + dx, y)))
        dx += hmtx[name][0] * sc + track

    width = dx - track if text else 0.0
    return f'<path d="{_round_path(pen.getCommands())}" {extra}/>', width


def text_paths(text, path, size, x, y, track=0.0, fill="currentColor", extra=""):
    """Text as a single outlined <path> wrapped in a <g> that carries the fill."""
    inner, width = text_inner(text, path, size, x, y, track, extra)
    return f'<g fill="{fill}">{inner}</g>', width


def text_width(text, path, size, track=0.0):
    """Advance width of a text run, with no path construction."""
    tt, _ = _font(path)
    sc = size / tt["head"].unitsPerEm
    cmap = tt.getBestCmap()
    hmtx = tt["hmtx"]
    w = 0.0
    for ch in text:
        name = cmap.get(ord(ch))
        w += (hmtx[name][0] * sc if name else size * 0.28) + track
    return w - track if text else 0.0


def fit(path, text, target_w, track_ratio=0.0, start=400):
    """Largest size whose tracked width fits target_w."""
    size = start
    while size > 4:
        if text_width(text, path, size, track_ratio * size) <= target_w:
            return size
        size -= 1
    return size


# ---------------------------------------------------------------- SVG helpers
def defs(t, uid):
    a = t["accent"]
    return f"""  <defs>
    <linearGradient id="g-accent-{uid}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{t['accent2']}"/>
    </linearGradient>
    <radialGradient id="g-glow-{uid}" cx="0.86" cy="0.02" r="0.82">
      <stop offset="0" stop-color="{a}" stop-opacity="{'0.34' if uid.startswith('d') else '0.18'}"/>
      <stop offset="0.5" stop-color="{a}" stop-opacity="{'0.07' if uid.startswith('d') else '0.04'}"/>
      <stop offset="1" stop-color="{a}" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="g-fade-{uid}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{a}" stop-opacity="0"/>
      <stop offset="0.5" stop-color="{a}" stop-opacity="0.55"/>
      <stop offset="1" stop-color="{a}" stop-opacity="0"/>
    </linearGradient>
    <filter id="f-soft-{uid}" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="18"/>
    </filter>
  </defs>"""


# ================================================================ HERO
HERO_W, HERO_H = 1200, 330


def hero(theme: str) -> str:
    t = THEMES[theme]
    uid = "d" if theme == "dark" else "l"
    a = t["accent"]

    eyebrow = "FRONTEND DEVELOPER + UI/UX DESIGNER"
    eye_markup, _ = text_paths(eyebrow, INTER[600], 14, 116, 58, 4.6, t["dim"])

    name_text = "AMIT VERMA"
    name_size = 132
    name_markup, name_w = text_paths(name_text, ANTON, name_size, 112, 192, 2, t["ink"])

    role_markup, _ = text_paths("SENIOR FRONTEND DEVELOPER", INTER[700], 24, 116, 256, 5.6, t["accent"])
    stack_markup, _ = text_paths("REACT.JS · NEXT.JS · TYPESCRIPT", INTER[500], 17, 116, 298, 2.2, t["muted"])

    # outlined year numeral, right side
    num = "05"
    n_size = 190
    n_w = text_width(num, INTER[700], n_size, 2)
    n_markup, _ = text_paths(num, INTER[700], n_size, HERO_W - 68 - n_w, 244, 2, "none",
                             extra=f'stroke="{a}" stroke-opacity="0.26" stroke-width="2"')
    lab_w = text_width("YEARS SHIPPING", INTER[600], 13, 5.6)
    lab_markup, _ = text_paths("YEARS SHIPPING", INTER[600], 13, HERO_W - 68 - lab_w, 286, 5.6, t["dim"])

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {HERO_W} {HERO_H}" width="{HERO_W}" height="{HERO_H}" role="img" aria-label="Amit Verma — Senior Frontend Developer and UI/UX Designer. React.js, Next.js, TypeScript. Five years.">
{defs(t, uid)}
  <rect width="{HERO_W}" height="{HERO_H}" fill="{t['bg']}"/>

  <!-- drifting accent glow -->
  <g opacity="1">
    <ellipse cx="1050" cy="40" rx="430" ry="330" fill="url(#g-glow-{uid})">
      <animate attributeName="cx" values="1010;1090;1010" dur="19s" repeatCount="indefinite"/>
      <animate attributeName="cy" values="30;70;30" dur="23s" repeatCount="indefinite"/>
    </ellipse>
  </g>

  <!-- hairline frame -->
  <g stroke="{t['stroke']}" stroke-width="1">
    <line x1="72" y1="0" x2="72" y2="{HERO_H}"/>
    <line x1="0" y1="44" x2="{HERO_W}" y2="44"/>
  </g>

  {n_markup}
  {lab_markup}

  {eye_markup}
  {name_markup}

  <!-- accent rule with a sweeping highlight -->
  <g>
    <rect x="112" y="212" width="112" height="5" rx="2.5" fill="url(#g-accent-{uid})"/>
    <rect x="112" y="212" width="34" height="5" rx="2.5" fill="{t['ink']}" opacity="0.85">
      <animate attributeName="x" values="112;190;112" dur="7s" repeatCount="indefinite" keySplines="0.4 0 0.6 1;0.4 0 0.6 1" calcMode="spline"/>
      <animate attributeName="opacity" values="0;0.85;0" dur="7s" repeatCount="indefinite"/>
    </rect>
  </g>

  {role_markup}
  {stack_markup}

  <!-- bottom hairline -->
  <rect x="0" y="{HERO_H - 2}" width="{HERO_W}" height="2" fill="url(#g-fade-{uid})"/>
</svg>
"""


# ================================================================ BENTO
# Deliberately roomy: three tiles, large type, generous padding. The earlier
# 4-tile + 6-card grid read as congested at GitHub's ~860px render width.
PAD = 52
GUT = 20
BENTO_W = 1160
INNER = BENTO_W - PAD * 2
COL = (INNER - GUT * 2) / 3

TOP_Y = 92
TOP_H = 286
WORK_LABEL_Y = TOP_Y + TOP_H + 58
WORK_Y = WORK_LABEL_Y + 26
WORK_H = 214
BENTO_H = int(WORK_Y + WORK_H + PAD)


def card(x, y, w, h, t, r=18, fill=None):
    f = fill or t["tile"]
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" '
            f'fill="{f}" stroke="{t["stroke"]}" stroke-width="1.25"/>')


def label(text, x, y, t, color=None, size=13, track=3.4):
    return text_paths(text, INTER[600], size, x, y, track, color or t["dim"])


def chip(x, y, lbl, t, size=14):
    tw = text_width(lbl, INTER[500], size, 0.4)
    pad, h = 15, 32
    w = tw + pad * 2
    box = (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h}" rx="{h/2:.1f}" '
           f'fill="{t["chip"]}" stroke="{t["stroke"]}" stroke-width="1"/>')
    tx, _ = text_paths(lbl, INTER[500], size, x + pad, y + 21, 0.4, t["ink2"])
    return box + tx, w


def bento(theme: str) -> str:
    t = THEMES[theme]
    uid = "d" if theme == "dark" else "l"
    a = t["accent"]

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {BENTO_W} {BENTO_H}" width="{BENTO_W}" height="{BENTO_H}" role="img" aria-label="Profile card for Amit Verma: about, tech stack and selected client work.">']
    parts.append(defs(t, uid))
    parts.append(f'<rect width="{BENTO_W}" height="{BENTO_H}" fill="{t["bg"]}"/>')

    # ------------------------------------------------ 01 about (2 cols)
    parts.append(label("01 — ABOUT", PAD, 62, t)[0])
    x, y, w = PAD, TOP_Y, COL * 2 + GUT
    parts.append(card(x, y, w, TOP_H, t))

    for i, line in enumerate(["I build interfaces that are", "designed, not just coded."]):
        parts.append(text_paths(line, INTER[600], 30, x + 38, y + 66 + i * 39, -0.2, t["ink"])[0])

    for i, line in enumerate([
        "Five years in frontend, four of them in React, Next.js and",
        "TypeScript. I started out as a UI/UX designer, so hierarchy,",
        "motion and the pixel still lead every decision I make.",
    ]):
        parts.append(text_paths(line, INTER[500], 16, x + 38, y + 140 + i * 26, 0.1, t["muted"])[0])

    # stat row, hairline separated
    stats = [("05", "YEARS"), ("4+", "REACT / NEXT"), ("50K", "MAX USERS")]
    sw = (w - 76) / 3
    base = y + TOP_H - 44
    parts.append(f'<line x1="{x+38}" y1="{base-40}" x2="{x+w-38}" y2="{base-40}" stroke="{t["stroke"]}" stroke-width="1"/>')
    for i, (big, small) in enumerate(stats):
        sx = x + 38 + i * sw
        parts.append(text_paths(big, INTER[700], 30, sx, base, -0.3, a)[0])
        parts.append(text_paths(small, INTER[600], 11, sx, base + 20, 1.8, t["dim"])[0])

    # ------------------------------------------------ 02 stack (1 col)
    sx0 = PAD + (COL + GUT) * 2
    parts.append(card(sx0, y, COL, TOP_H, t))
    parts.append(label("02 — STACK", sx0 + 32, y + 50, t)[0])

    rows = [["React.js", "Next.js"], ["TypeScript", "JavaScript"],
            ["Tailwind CSS", "TanStack"], ["Redux Toolkit", "Framer Motion"]]
    cy = y + 72
    for row in rows:
        cx = sx0 + 32
        for lbl in row:
            m, cw = chip(cx, cy, lbl, t)
            parts.append(m)
            cx += cw + 8
        cy += 42

    # ------------------------------------------------ 03 selected work
    parts.append(label("03 — SELECTED WORK", PAD, WORK_LABEL_Y, t)[0])
    note = "CLIENT PROJECTS · NAMES WITHHELD"
    nw = text_width(note, INTER[600], 11, 2.6)
    parts.append(label(note, BENTO_W - PAD - nw, WORK_LABEL_Y, t, size=11, track=2.6)[0])

    projects = [
        ("Fleet management dashboard",
         ["Operations dashboard for a fleet: live", "vehicle status, reporting, access control."],
         "TanStack Query · Firebase", "50K users"),
        ("School site + admin panel",
         ["Public site plus an admin CMS for exams,", "results, admissions and achievements."],
         "Next.js · SEO", "30K users"),
        ("Industrial monitoring platform",
         ["Billing, inventory and plant management", "for wastewater treatment sites."],
         "React · REST APIs", "In production"),
    ]

    cw3 = (INNER - GUT * 2) / 3
    for i, (name, desc, meta, scale) in enumerate(projects):
        cx = PAD + i * (cw3 + GUT)
        parts.append(card(cx, WORK_Y, cw3, WORK_H, t, r=16))
        parts.append(text_paths(f"0{i+1}", INTER[600], 12, cx + 30, WORK_Y + 44, 1.2, a)[0])
        scw = text_width(scale, INTER[600], 12, 0.4)
        parts.append(text_paths(scale, INTER[600], 12, cx + cw3 - 30 - scw, WORK_Y + 44, 0.4, a)[0])
        parts.append(text_paths(name, INTER[600], 19, cx + 30, WORK_Y + 94, -0.2, t["ink"])[0])
        for j, line in enumerate(desc):
            parts.append(text_paths(line, INTER[500], 14, cx + 30, WORK_Y + 126 + j * 22, 0.1, t["muted"])[0])
        parts.append(text_paths(meta, INTER[500], 12, cx + 30, WORK_Y + WORK_H - 30, 0.3, t["dim"])[0])

    parts.append("</svg>")
    return "\n".join(parts)


# ================================================================ DIVIDER
def divider(theme: str, label: str | None = None) -> str:
    t = THEMES[theme]
    uid = "d" if theme == "dark" else "l"
    w, h = 1200, 40
    line = (
        f'<line x1="0" y1="20" x2="{w}" y2="20" stroke="{t["stroke"]}" stroke-width="1"/>'
    )
    lab = ""
    if label:
        lab, lab_w = text_paths(label, INTER[600], 12, 0, 0, 4.0, t["dim"])
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
  <rect width="{w}" height="{h}" fill="none"/>
  {line}
</svg>
"""


if __name__ == "__main__":
    for theme in THEMES:
        for name, builder in (("hero", hero), ("bento", bento)):
            markup = builder(theme)
            path = OUT / f"{name}-{theme}.svg"
            path.write_text(markup, encoding="utf-8")
            gz = len(gzip.compress(markup.encode(), 9))
            print(f"{path.name:18} {path.stat().st_size // 1024:4} KB raw · {gz // 1024:4} KB gzip")
