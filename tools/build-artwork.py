#!/usr/bin/env python3
"""
Build the GitHub profile artwork as hand-authored SVG with text converted to outlines.

Three constraints drive every decision here:

1. FONTS. GitHub's image proxy strips external resources, so a webfont never loads
   and the type silently falls back to a system font. Glyphs are converted to
   <path> outlines so typography renders identically everywhere.

2. SIZE. GitHub renders README images at roughly 860 to 900px, so artwork is
   authored at 880px. Matching the render width avoids fractional resampling,
   which is what smears thin text strokes.

3. SURVIVABILITY. GitHub's proxy rasterises SVG at a resolution it chooses, and
   some browser/display-scaling combinations get that wrong and blur it. The
   build therefore also emits 2x PNGs, and the README references those.

Palette: cool indigo and glacier blue on near-black, with a violet secondary.
No orange. Gradients stay inside one temperature family so nothing clashes.

Outputs (dark + light variants):
  assets/hero-{dark,light}    glass header: wordmark, role, stack, availability
  assets/bento-{dark,light}   tech stack grid plus client work
  assets/social-{dark,light}  bento cards for GitHub, LinkedIn, Portfolio,
                              Instagram and Email
  plus 2x PNG for each

Motion is SMIL <animate> only. No JS, no third party services, no external images.
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
INTER = {w: FONTS / f"inter-latin-{w}-normal.ttf" for w in (500, 600, 700, 800)}

# ---------------------------------------------------------------- brand colours
BRAND = {
    "react": "#61DAFB", "nextdotjs": "#EDEDED", "typescript": "#3178C6",
    "javascript": "#F7DF1E", "tailwindcss": "#38BDF8", "tanstack": "#FF4154",
    "redux": "#764ABC", "framer": "#0055FF", "figma": "#F24E1E",
    "github": "#EDEDED", "gmail": "#EA4335", "firebase": "#FFCA28",
    "mongodb": "#47A248", "postgresql": "#4169E1", "git": "#F05032",
    "postman": "#FF6C37", "vercel": "#EDEDED", "netlify": "#00C7B7",
    "instagram": "#FF4D8D", "linkedin": "#4C9AFF", "python": "#3776AB",
    "bootstrap": "#8B6BE0", "adobexd": "#FF61F6", "photoshop": "#31A8FF",
    "premiere": "#9999FF",
}
BRAND_LIGHT = dict(
    BRAND, nextdotjs="#111111", github="#111111", vercel="#111111",
    javascript="#B58A00", tanstack="#D92B38", framer="#0055FF",
    instagram="#D6246E", nextdotjs_light="#111111",
)

# Cool, cohesive palette. One family: indigo to glacier, violet as support.
THEMES = {
    "dark": dict(
        bg="#0A0B14",
        tile="#12141F",          # solid base under frosted tiles
        glass="#141726",         # frosted fill
        chip="#181B29",
        stroke="#252A3D",
        ink="#F3F5FA", ink2="#D2D8E6", muted="#98A1B8", dim="#6B7488",
        accent="#7C8CFF",        # indigo
        accent2="#4FD1FF",       # glacier
        violet="#A78BFA",
        brand=BRAND,
        blob1="#4C56D6", blob2="#2AA6D8", blob3="#8B5CF6",
        blob_op=0.55,
    ),
    "light": dict(
        bg="#F7F8FC",
        tile="#FFFFFF", glass="#FFFFFF", chip="#F1F3FA",
        stroke="#E2E6F0",
        ink="#0D1020", ink2="#333A4D", muted="#5C6478", dim="#8A90A3",
        accent="#4F5BD5", accent2="#1B9AD6", violet="#7C5CE0",
        brand=BRAND_LIGHT,
        blob1="#B9C2FF", blob2="#A8E4FA", blob3="#D5C7FF",
        blob_op=0.85,
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


def _round_path(d: str, nd: int = 2) -> str:
    """Trim coordinate precision without destroying curve data.

    nd=0 collapses sub-pixel curve control points and visibly smudges glyphs at
    these sizes; two decimals keeps the outlines intact for a modest size cost.
    """
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
    return (f'<g fill="{fill}"><path d="{_round_path(pen.getCommands())}"/></g>',
            text_width(text, path, size, track))


def wrap(text, path, size, max_w, track=0.0):
    """Greedy word wrap against measured width, so no string can overrun its box."""
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and text_width(trial, path, size, track) > max_w:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def text_bbox(text, path, size, track=0.0):
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
    return bp.bounds


def text_at_top(text, path, size, x, top, track=0.0, fill="currentColor"):
    """Place display type so the top of its ink lands exactly on `top`."""
    b = text_bbox(text, path, size, track)
    baseline = top - b[1] if b else top + size
    markup, _ = text_paths(text, path, size, x, baseline, track, fill)
    return markup, baseline + (b[3] if b else size)


# ---------------------------------------------------------------- icons
_icon_cache: dict = {}


def icon(slug, x, y, size, color, opacity=1.0):
    """Simple Icons glyph (24x24) as a filled path at (x, y)."""
    if slug not in _icon_cache:
        root = ET.parse(ICONS / f"{slug}.svg").getroot()
        _icon_cache[slug] = root.find("{http://www.w3.org/2000/svg}path").get("d")
    s = size / 24.0
    op = f' opacity="{opacity}"' if opacity != 1 else ""
    return (f'<g transform="translate({x:.1f} {y:.1f}) scale({s:.4f})"{op}>'
            f'<path d="{_icon_cache[slug]}" fill="{color}"/></g>')


def adobe_icon(app, x, y, size, bg, fg="#FFFFFF"):
    """The three Adobe marks are no longer in Simple Icons, so draw them here
    as the two-letter app tile Adobe actually uses."""
    letters = {"adobexd": "Xd", "photoshop": "Ps", "premiere": "Pr"}[app]
    r = size * 0.22
    parts = [f'<rect x="{x:.1f}" y="{y:.1f}" width="{size}" height="{size}" rx="{r:.1f}" fill="{bg}"/>']
    fs = size * 0.42 if app != "adobexd" else size * 0.40
    tw = text_width(letters, INTER[700], fs, -0.2)
    m, _ = text_paths(letters, INTER[700], fs, x + (size - tw) / 2, y + size * 0.69, -0.2, fg)
    parts.append(m)
    return "".join(parts)


def any_icon(slug, x, y, size, color, t):
    if slug in ("adobexd", "photoshop", "premiere"):
        return adobe_icon(slug, x, y, size, t["brand"][slug])
    return icon(slug, x, y, size, color)


# ---------------------------------------------------------------- chrome
def defs(t, uid):
    dark = uid.startswith("d")
    return f"""  <defs>
    <linearGradient id="ac-{uid}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{t['accent']}"/><stop offset="1" stop-color="{t['accent2']}"/>
    </linearGradient>
    <linearGradient id="hair-{uid}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{t['accent']}" stop-opacity="0"/>
      <stop offset="0.25" stop-color="{t['accent']}" stop-opacity="{0.55 if dark else 0.4}"/>
      <stop offset="0.75" stop-color="{t['accent2']}" stop-opacity="{0.55 if dark else 0.4}"/>
      <stop offset="1" stop-color="{t['accent2']}" stop-opacity="0"/>
    </linearGradient>
    <radialGradient id="b1-{uid}" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="{t['blob1']}" stop-opacity="{t['blob_op']}"/>
      <stop offset="0.6" stop-color="{t['blob1']}" stop-opacity="{t['blob_op'] * 0.28:.2f}"/>
      <stop offset="1" stop-color="{t['blob1']}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="b2-{uid}" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="{t['blob2']}" stop-opacity="{t['blob_op'] * 0.85:.2f}"/>
      <stop offset="0.6" stop-color="{t['blob2']}" stop-opacity="{t['blob_op'] * 0.2:.2f}"/>
      <stop offset="1" stop-color="{t['blob2']}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="b3-{uid}" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="{t['blob3']}" stop-opacity="{t['blob_op'] * 0.7:.2f}"/>
      <stop offset="0.65" stop-color="{t['blob3']}" stop-opacity="{t['blob_op'] * 0.15:.2f}"/>
      <stop offset="1" stop-color="{t['blob3']}" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="glass-{uid}" x1="0" y1="0" x2="0.6" y2="1">
      <stop offset="0" stop-color="{t['glass']}" stop-opacity="{0.92 if dark else 1}"/>
      <stop offset="1" stop-color="{t['glass']}" stop-opacity="{0.72 if dark else 1}"/>
    </linearGradient>
    <linearGradient id="edge-{uid}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{t['ink']}" stop-opacity="{0.16 if dark else 0.7}"/>
      <stop offset="0.5" stop-color="{t['stroke']}" stop-opacity="{0.5 if dark else 0.5}"/>
      <stop offset="1" stop-color="{t['ink']}" stop-opacity="{0.05 if dark else 0.4}"/>
    </linearGradient>
    <filter id="blur-{uid}" x="-40%" y="-40%" width="180%" height="180%">
      <feGaussianBlur stdDeviation="26"/>
    </filter>
  </defs>"""


def blobs(t, uid, w, h, spec):
    """Blurred gradient blobs. Ambient, slow drift, never flashing."""
    out = []
    for i, (cx, cy, rx, ry, grad, dur) in enumerate(spec):
        out.append(
            f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="url(#{grad}-{uid})">'
            f'<animate attributeName="cy" values="{cy};{cy + 8};{cy}" dur="{dur}s" repeatCount="indefinite"/>'
            f'</ellipse>'
        )
    return "".join(out)


def glass_card(x, y, w, h, t, uid, r=20, tint=None):
    """Frosted tile: gradient fill, soft top highlight, hairline edge."""
    fill = tint or f"url(#glass-{uid})"
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" fill="{fill}"/>'
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" fill="none" '
        f'stroke="url(#edge-{uid})" stroke-width="1.1"/>'
    )


# ================================================================ HERO
HERO_W, HERO_H = 880, 356


def hero(theme):
    t = THEMES[theme]
    uid = "d" if theme == "dark" else "l"
    P = 44

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {HERO_W} {HERO_H}" width="{HERO_W}" height="{HERO_H}" role="img" aria-label="Amit Verma, senior frontend developer and UI/UX designer. React, Next.js, TypeScript.">']
    parts.append(defs(t, uid))
    parts.append(f'<rect width="{HERO_W}" height="{HERO_H}" fill="{t["bg"]}"/>')
    parts.append(blobs(t, uid, HERO_W, HERO_H, [
        (112, 300, 300, 210, "b1", 21),
        (700, 40, 300, 180, "b2", 26),
        (452, 160, 250, 150, "b3", 31),
    ]))

    # faint grid, adds the SaaS blueprint feel without noise
    grid = "".join(
        f'<line x1="{gx}" y1="0" x2="{gx}" y2="{HERO_H}" stroke="{t["stroke"]}" stroke-opacity="0.28"/>'
        for gx in range(0, HERO_W, 44)
    )
    parts.append(grid)

    # ---------------------------------------------- glass header panel
    hx, hy, hw, hh = P, 26, HERO_W - P * 2, HERO_H - 50
    parts.append(glass_card(hx, hy, hw, hh, t, uid, r=24))
    # top sheen
    parts.append(f'<rect x="{hx + 1}" y="{hy + 1}" width="{hw - 2}" height="1.4" fill="url(#ac-{uid})" opacity="0.75"/>')

    ix = hx + 38

    # availability chip
    chip_txt = "AVAILABLE FOR SENIOR ROLES"
    ct_w = text_width(chip_txt, INTER[700], 10.5, 2.3)
    parts.append(f'<rect x="{ix}" y="{hy + 26}" width="{ct_w + 42:.1f}" height="24" rx="12" '
                 f'fill="{t["accent"]}" fill-opacity="0.14" stroke="{t["accent"]}" stroke-opacity="0.45" stroke-width="1"/>')
    parts.append(f'<circle cx="{ix + 14}" cy="{hy + 38}" r="3.6" fill="{t["accent2"]}">'
                 f'<animate attributeName="opacity" values="1;0.25;1" dur="2.6s" repeatCount="indefinite"/></circle>')
    parts.append(text_paths(chip_txt, INTER[700], 10.5, ix + 26, hy + 42, 2.3, t["ink2"])[0])

    # wordmark
    name_size = 96
    nm, name_bottom = text_at_top("AMIT VERMA", ANTON, name_size, ix, hy + 66, 1.2, t["ink"])
    parts.append(nm)

    # role line, accent gradient text via a rect mask-free approach: two tone words
    role_y = name_bottom + 26
    parts.append(text_paths("SENIOR FRONTEND DEVELOPER", INTER[700], 15, ix, role_y, 4.2, t["accent"])[0])
    sep = text_width("SENIOR FRONTEND DEVELOPER", INTER[700], 15, 4.2)
    parts.append(f'<circle cx="{ix + sep + 9}" cy="{role_y - 5}" r="2.6" fill="{t["dim"]}"/>')
    parts.append(text_paths("UI/UX DESIGNER", INTER[700], 15, ix + sep + 20, role_y, 4.2, t["accent2"])[0])

    # stack row with icons
    sy = role_y + 34
    x = ix
    for slug, lbl in (("react", "React"), ("nextdotjs", "Next.js"), ("typescript", "TypeScript")):
        parts.append(icon(slug, x, sy - 16, 19, t["brand"][slug]))
        m, w = text_paths(lbl, INTER[600], 14.5, x + 26, sy, 0.2, t["ink2"])
        parts.append(m)
        x += 26 + w + 22

    # ---------------------------------------------- contact pill + meta right side
    meta_x = hx + hw - 34
    yrs = "05"
    ysz = 62
    yw = text_width(yrs, ANTON, ysz, 1)
    parts.append(text_paths(yrs, ANTON, ysz, meta_x - yw, hy + 96, 1, t["accent"])[0])
    lab = "YEARS SHIPPING"
    lw = text_width(lab, INTER[700], 10, 2.4)
    parts.append(text_paths(lab, INTER[700], 10, meta_x - lw, hy + 114, 2.4, t["dim"])[0])

    handle = "@it-is-amit"
    hw2 = text_width(handle, INTER[600], 12, 0.6)
    parts.append(text_paths(handle, INTER[600], 12, meta_x - hw2, hy + 148, 0.6, t["muted"])[0])

    parts.append("</svg>")
    return "\n".join(parts)


# ================================================================ BENTO
PAD = 12
BENTO_W = 880
INNER = BENTO_W - PAD * 2


def label(text, x, y, t, color=None, size=12, track=2.8):
    return text_paths(text, INTER[700], size, x, y, track, color or t["dim"])[0]


def tech_tile(slug, lbl, x, y, t, uid, w, h):
    """Frosted tile: brand mark above a readable label."""
    parts = [
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="14" fill="{t["chip"]}"/>',
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="14" fill="none" '
        f'stroke="url(#edge-{uid})" stroke-width="1"/>',
    ]
    isize = min(24, w * 0.2)
    parts.append(any_icon(slug, x + 14, y + 12, isize, t["brand"][slug], t))
    parts.append(text_paths(lbl, INTER[600], 13, x + 14, y + h - 13, 0.1, t["ink2"])[0])
    return "".join(parts)


def bento(theme):
    t = THEMES[theme]
    uid = "d" if theme == "dark" else "l"
    a = t["accent"]

    COLS, ROWS = 8, 3
    gap = 10
    ipad = 22
    tw = (INNER - ipad * 2 - gap * (COLS - 1)) / COLS
    th = 64
    grid_h = ROWS * th + (ROWS - 1) * gap
    STACK_H = grid_h + ipad * 2

    TOP_Y = 40
    WORK_Y = TOP_Y + STACK_H + 62
    WORK_H = 262
    H = WORK_Y + WORK_H + PAD

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {BENTO_W} {H}" width="{BENTO_W}" height="{H}" role="img" aria-label="Tech stack and three selected client projects.">']
    parts.append(defs(t, uid))
    parts.append(f'<rect width="{BENTO_W}" height="{H}" fill="{t["bg"]}"/>')
    parts.append(blobs(t, uid, BENTO_W, H, [
        (60, 120, 260, 200, "b1", 24),
        (830, 380, 240, 220, "b2", 29),
    ]))

    # ---------------------------------------------- 01 stack
    parts.append(label("01  STACK", PAD, TOP_Y - 14, t))
    parts.append(glass_card(PAD, TOP_Y, INNER, STACK_H, t, uid, r=22))

    tiles = [
        ("react", "React.js"), ("nextdotjs", "Next.js"), ("typescript", "TypeScript"),
        ("javascript", "JavaScript"), ("tailwindcss", "Tailwind"), ("bootstrap", "Bootstrap"),
        ("redux", "Redux"), ("tanstack", "TanStack"),
        ("framer", "Framer"), ("figma", "Figma"), ("adobexd", "Adobe XD"),
        ("photoshop", "Photoshop"),
        ("python", "Python"), ("postgresql", "PostgreSQL"), ("mongodb", "MongoDB"),
        ("firebase", "Firebase"),
        ("premiere", "Premiere Pro"), ("postman", "Postman"), ("github", "GitHub"),
        ("vercel", "Vercel"), ("git", "Git"), ("netlify", "Netlify"),
        ("postman", "Postman"), ("vercel", "Vercel"),
    ]
    # 8 x 3 = 24 slots; trim the accidental duplicates to exactly fill the grid
    tiles = tiles[:16] + [("premiere", "Premiere Pro"), ("postman", "Postman"),
                          ("github", "GitHub"), ("vercel", "Vercel"),
                          ("git", "Git"), ("netlify", "Netlify"),
                          ("figma", "Figma"), ("python", "Python")]
    seen, final = set(), []
    for slug, lbl in tiles:
        if lbl in seen:
            continue
        seen.add(lbl)
        final.append((slug, lbl))
    tiles = final

    for i, (slug, lbl) in enumerate(tiles[:COLS * ROWS]):
        r, c = divmod(i, COLS)
        x = PAD + ipad + c * (tw + gap)
        y = TOP_Y + ipad + r * (th + gap)
        parts.append(tech_tile(slug, lbl, x, y, t, uid, tw, th))

    # ---------------------------------------------- 02 selected work
    parts.append(label("02  SELECTED WORK", PAD, WORK_Y - 16, t))
    note = "CLIENT PROJECTS, NAMES WITHHELD"
    nw = text_width(note, INTER[700], 10.5, 2.2)
    parts.append(label(note, BENTO_W - PAD - nw, WORK_Y - 16, t, size=10.5, track=2.2))

    projects = [
        ("Fleet management dashboard",
         "Live vehicle status, reporting and role-based access across 45+ screens.",
         "50K users", ["tanstack", "typescript", "firebase"]),
        ("School site and admin panel",
         "Public site plus a CMS for exams, results, admissions and achievements.",
         "30K users", ["nextdotjs", "typescript"]),
        ("Industrial monitoring platform",
         "Billing, inventory and plant ops for wastewater treatment sites.",
         "In production", ["react", "postgresql"]),
    ]

    cw = (INNER - gap * 2) / 3
    for i, (name, desc, scale, stack) in enumerate(projects):
        cx = PAD + i * (cw + gap)
        parts.append(glass_card(cx, WORK_Y, cw, WORK_H, t, uid, r=20))

        bw = text_width(scale, INTER[700], 10.5, 0.5) + 20
        parts.append(f'<rect x="{cx + cw - 18 - bw:.1f}" y="{WORK_Y + 18}" width="{bw:.1f}" height="22" rx="11" '
                     f'fill="{a}" fill-opacity="0.16" stroke="{a}" stroke-opacity="0.45" stroke-width="1"/>')
        parts.append(text_paths(scale, INTER[700], 10.5, cx + cw - 18 - bw + 10, WORK_Y + 33, 0.5, a)[0])

        parts.append(text_paths(f"0{i+1}", INTER[700], 11, cx + 18, WORK_Y + 34, 1.1, t["dim"])[0])

        lines = wrap(name, INTER[600], 19, cw - 36, -0.2)
        for j, ln in enumerate(lines):
            parts.append(text_paths(ln, INTER[600], 19, cx + 18, WORK_Y + 78 + j * 24, -0.2, t["ink"])[0])

        dy = WORK_Y + 78 + len(lines) * 24 + 16
        for j, ln in enumerate(wrap(desc, INTER[500], 13.5, cw - 36, 0.1)):
            parts.append(text_paths(ln, INTER[500], 13.5, cx + 18, dy + j * 20, 0.1, t["muted"])[0])

        ix = cx + 18
        for slug in stack:
            parts.append(icon(slug, ix, WORK_Y + WORK_H - 36, 19, t["brand"][slug]))
            ix += 27

    parts.append("</svg>")
    return "\n".join(parts)


# ================================================================ SOCIAL
SOCIAL_W = 880
SOCIAL_H = 220


def social(theme):
    """Bento cards: 2 wide on the top row, 3 on the bottom."""
    t = THEMES[theme]
    uid = "d" if theme == "dark" else "l"
    P = 12
    gap = 12
    inner = SOCIAL_W - P * 2

    items = [
        ("github", "GitHub", "it-is-amit", "github.com/it-is-amit"),
        ("linkedin", "LinkedIn", "amit-verma", "in/amit-verma"),
        ("link", "Portfolio", "coming soon", "amitverma.dev"),
        ("instagram", "Instagram", "it_is_amit", "instagram.com/it_is_amit"),
        ("gmail", "Email", "amverma1204t", "gmail.com"),
    ]

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SOCIAL_W} {SOCIAL_H}" width="{SOCIAL_W}" height="{SOCIAL_H}" role="img" aria-label="Contact cards for GitHub, LinkedIn, Portfolio, Instagram and Email.">']
    parts.append(defs(t, uid))
    parts.append(f'<rect width="{SOCIAL_W}" height="{SOCIAL_H}" fill="{t["bg"]}"/>')
    parts.append(blobs(t, uid, SOCIAL_W, SOCIAL_H, [
        (150, 40, 240, 150, "b1", 23),
        (740, 200, 240, 160, "b3", 27),
    ]))

    top_h, top_y = 100, 8
    bot_y, bot_h = top_y + top_h + gap, 100
    top_w = (inner - gap) / 2
    bot_w = (inner - gap * 2) / 3

    for i, (slug, name, handle, url) in enumerate(items):
        if i < 2:
            x, y, w, h = P + i * (top_w + gap), top_y, top_w, top_h
        else:
            j = i - 2
            x, y, w, h = P + j * (bot_w + gap), bot_y, bot_w, bot_h

        parts.append(glass_card(x, y, w, h, t, uid, r=18))

        # icon tile
        isz = 34 if i < 2 else 28
        bx, by = x + 18, y + 18
        parts.append(f'<rect x="{bx}" y="{by}" width="{isz}" height="{isz}" rx="10" '
                     f'fill="{t["brand"][slug] if slug != "link" else t["accent2"]}" fill-opacity="0.14" '
                     f'stroke="url(#edge-{uid})" stroke-width="1"/>')
        if slug == "link":
            # a clean chain-link glyph, there is no Simple Icons mark for "portfolio"
            cx, cy = bx + isz / 2, by + isz / 2
            parts.append(f'<g stroke="{t["accent2"]}" stroke-width="2" stroke-linecap="round" fill="none">'
                         f'<path d="M{cx - 6.5} {cy + 1} a5 5 0 0 1 0 -7 l3.2 -3.2"/>'
                         f'<path d="M{cx + 6.5} {cy - 1} a5 5 0 0 1 0 7 l-3.2 3.2"/>'
                         f'<path d="M{cx - 4} {cy + 4} l8 -8"/></g>')
        else:
            parts.append(icon(slug, bx + (isz - isz * 0.56) / 2, by + (isz - isz * 0.56) / 2,
                              isz * 0.56, t["brand"][slug]))

        # label + handle
        size_name = 15 if i < 2 else 13.5
        parts.append(text_paths(name, INTER[700], size_name, bx + isz + 12, by + 15, 0.2, t["ink"])[0])
        parts.append(text_paths(handle, INTER[500], 12 if i < 2 else 11,
                                bx + isz + 12, by + 31, 0.1, t["muted"])[0])

        # url strip on the wide cards
        if i < 2:
            parts.append(text_paths(url, INTER[500], 11.5, x + 18, y + h - 18, 0.1, t["dim"])[0])
            ar_x = x + w - 30
            parts.append(f'<path d="M{ar_x} {y + h - 24} l7 6 l-7 6" stroke="{t["accent"]}" '
                         f'stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>')

    parts.append("</svg>")
    return "\n".join(parts)


if __name__ == "__main__":
    import resvg_py

    for theme in THEMES:
        for name, builder in (("hero", hero), ("bento", bento), ("social", social)):
            markup = builder(theme)
            ET.fromstring(markup)  # fail loudly on malformed SVG
            svg_path = OUT / f"{name}-{theme}.svg"
            svg_path.write_text(markup, encoding="utf-8")
            png = bytes(resvg_py.svg_to_bytes(svg_string=markup, zoom=2))
            (OUT / f"{name}-{theme}.png").write_bytes(png)
            print(f"{name}-{theme}: svg {len(markup) // 1024:3} KB · png {len(png) // 1024:3} KB")
