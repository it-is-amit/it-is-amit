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
        ink="#F2F5F9", muted="#8B949E", dim="#5A646F", accent="#FF6A2B",
        accent2="#FFB067", paper="#0B0D11",
    ),
    "light": dict(
        bg="#FAF7F3", tile="#FFFFFF", tile_hi="#F4EFE8", stroke="#E4DDD3",
        ink="#101318", muted="#6B655C", dim="#8A8378", accent="#E8501A",
        accent2="#FF9448", paper="#FAF7F3",
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
PAD = 44            # outer padding
GUT = 16            # gutter
COLS = 4
BENTO_W = 1200
INNER = BENTO_W - PAD * 2
COL_W = (INNER - GUT * (COLS - 1)) / COLS

HEADER_H = 140
ROW1_Y = HEADER_H
ROW1_H = 252
ROW2_Y = ROW1_Y + ROW1_H + GUT
CARD_H, CARD_GAP = 86, 14
ROW2_H = 62 + CARD_H * 2 + CARD_GAP + 26
BENTO_H = int(ROW2_Y + ROW2_H + PAD)


def tile(x, y, w, h, t, r=16, fill=None, stroke=True):
    f = fill or t["tile"]
    s = f' stroke="{t["stroke"]}" stroke-width="1.25"' if stroke else ""
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" fill="{f}"{s}/>'


def chip(x, y, label, t, size=13):
    """Outlined pill with label; returns (markup, width)."""
    tw = text_width(label, INTER[600], size, 0.5)
    w, h, padx = tw + 26, 27, 13
    box = (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h}" rx="{h/2:.1f}" '
           f'fill="none" stroke="{t["stroke"]}" stroke-width="1.2"/>')
    tx, _ = text_paths(label, INTER[600], size, x + padx, y + 18, 0.5, t["muted"])
    return box + tx, w


def micro_label(text, x, y, t, color=None, size=12, track=3.6):
    m, w = text_paths(text, INTER[600], size, x, y, track, color or t["dim"])
    return m, w


def bento(theme: str) -> str:
    t = THEMES[theme]
    uid = "d" if theme == "dark" else "l"
    a = t["accent"]

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {BENTO_W} {BENTO_H}" width="{BENTO_W}" height="{BENTO_H}" role="img" aria-label="Bento profile card for Amit Verma: about, tech stack, current work and selected anonymised client projects.">']
    parts.append(defs(t, uid))
    parts.append(f'<rect width="{BENTO_W}" height="{BENTO_H}" fill="{t["bg"]}"/>')

    # ---------------------------------------------------------- header
    eye, _ = micro_label("AMIT VERMA — GITHUB PROFILE", PAD, 40, t, size=12, track=4.2)
    parts.append(eye)

    avail_label = "OPEN TO SENIOR FRONTEND ROLES"
    av_w = text_width(avail_label, INTER[600], 12, 3.4)
    av, _ = text_paths(avail_label, INTER[600], 12, BENTO_W - PAD - av_w, 40, 3.4, t["muted"])
    parts.append(av)
    parts.append(
        f'<circle cx="{BENTO_W - PAD - av_w - 16}" cy="36" r="4" fill="{a}">'
        f'<animate attributeName="opacity" values="1;0.2;1" dur="2.8s" repeatCount="indefinite"/></circle>'
    )

    title_txt = "DESIGN-MINDED FRONTEND ENGINEER"
    t_size = fit(ANTON, title_txt, INNER - 8, 0.012, start=92)
    title, _ = text_paths(title_txt, ANTON, t_size, PAD, HEADER_H - 22, 0.012 * t_size, t["ink"])
    parts.append(title)

    # ---------------------------------------------------------- 01 about (2 cols)
    left_w = COL_W * 2 + GUT
    x, y = PAD, ROW1_Y
    parts.append(tile(x, y, left_w, ROW1_H, t))
    lb, _ = micro_label("01 — ABOUT", x + 26, y + 38, t)
    parts.append(lb)

    for i, line in enumerate(["I build interfaces that are", "designed, not just coded."]):
        parts.append(text_paths(line, INTER[600], 22, x + 26, y + 82 + i * 29, 0.1, t["ink"])[0])

    for i, line in enumerate([
        "5 years in frontend, 4+ of them in React, Next.js and TypeScript.",
        "Started out in UI/UX, so hierarchy and motion still lead my work.",
    ]):
        parts.append(text_paths(line, INTER[500], 14, x + 26, y + 152 + i * 23, 0.2, t["muted"])[0])

    # stat strip
    stats = [("5", "YEARS"), ("4+", "REACT / NEXT"), ("50K", "MAX USERS")]
    sx = x + 26
    base = y + ROW1_H - 24
    for big, small in stats:
        bm, bw = text_paths(big, ANTON, 30, sx, base, 0.5, a)
        sm, sw = text_paths(small, INTER[600], 10, sx, base + 14, 1.6, t["dim"])
        parts += [bm, sm]
        sx += max(bw, sw) + 44

    # ---------------------------------------------------------- 02 stack (2 cols)
    rx = PAD + left_w + GUT
    right_w = INNER - left_w - GUT
    stack_h = 128
    parts.append(tile(rx, ROW1_Y, right_w, stack_h, t))
    lb, _ = micro_label("02 — STACK", rx + 24, ROW1_Y + 34, t)
    parts.append(lb)

    rows = [
        ["React.js", "Next.js", "TypeScript", "JavaScript"],
        ["Tailwind CSS", "TanStack Query", "Redux Toolkit", "Framer Motion"],
    ]
    cy = ROW1_Y + 48
    for row in rows:
        cx = rx + 24
        for label in row:
            m, w = chip(cx, cy, label, t)
            parts.append(m)
            cx += w + 8
        cy += 35

    # ---------------------------------------------------------- 03 now
    now_y = ROW1_Y + stack_h + GUT
    now_h = ROW1_H - stack_h - GUT
    parts.append(tile(rx, now_y, right_w, now_h, t))
    lb, _ = micro_label("03 — NOW", rx + 24, now_y + 32, t)
    parts.append(lb)
    parts.append(text_paths("Leading frontend on product dashboards.", INTER[500], 15,
                            rx + 24, now_y + 58, 0.2, t["muted"])[0])
    parts.append(text_paths("Based in Rajasthan, India · remote-friendly.", INTER[500], 15,
                            rx + 24, now_y + 82, 0.2, t["dim"])[0])

    # ---------------------------------------------------------- 04 selected work
    wx, wy, ww = PAD, ROW2_Y, INNER
    parts.append(tile(wx, wy, ww, ROW2_H, t))
    lb, _ = micro_label("04 — SELECTED WORK · CLIENT PROJECTS, ANONYMISED", wx + 26, wy + 38, t)
    parts.append(lb)

    projects = [
        ("Fleet management dashboard", "TanStack Query · Firebase auth", "50K users"),
        ("Industrial monitoring platform", "React · billing + inventory", "in production"),
        ("School site + admin panel", "Next.js · SEO · admin CMS", "30K users"),
        ("E-commerce storefront", "Next.js · SSR/SSG · responsive", "5K+ users"),
        ("Social platform", "reusable component architecture", "5K users"),
        ("AI astrology platform", "UI/UX overhaul + frontend", "5K users"),
    ]

    cols = 3
    card_w = (ww - 52 - CARD_GAP * (cols - 1)) / cols
    cy0 = wy + 58
    for i, (name, meta, scale) in enumerate(projects):
        r, c = divmod(i, cols)
        cx = wx + 26 + c * (card_w + CARD_GAP)
        cy = cy0 + r * (CARD_H + CARD_GAP)
        parts.append(tile(cx, cy, card_w, CARD_H, t, r=12, fill=t["tile_hi"], stroke=True))
        idx, _ = text_paths(f"0{i+1}", INTER[600], 10, cx + 16, cy + 24, 1.2, a)
        parts.append(idx)
        nm, _ = text_paths(name, INTER[600], 15, cx + 16, cy + 48, 0, t["ink"])
        parts.append(nm)
        mt, _ = text_paths(meta, INTER[500], 11, cx + 16, cy + 66, 0.2, t["dim"])
        parts.append(mt)
        scw = text_width(scale, INTER[600], 11, 0.6)
        sc, _ = text_paths(scale, INTER[600], 11, cx + card_w - 16 - scw, cy + 24, 0.6, a)
        parts.append(sc)

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
