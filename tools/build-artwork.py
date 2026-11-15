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
    P = 12
    ix_off = 40

    # --- vertical rhythm, measured not guessed
    chip_y = 26                       # chip top, panel relative
    name_top = 66                     # wordmark ink top, panel relative
    name_size = 96
    _, ink_h = text_at_top("AMIT VERMA", ANTON, name_size, 0, 0, 1.2, "#000")
    role_rel = name_top + ink_h + 26  # role baseline
    stack_rel = role_rel + 34         # stack baseline
    stack_bottom = stack_rel + 5      # icons extend a few px below the baseline
    panel_h = stack_bottom + 24       # equal-ish air under the last element
    canvas_pad = 32                   # keep every edge clear so nothing clips
    hero_h = panel_h + canvas_pad * 2

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {HERO_W} {hero_h}" width="{HERO_W}" height="{hero_h}" role="img" aria-label="Amit Verma, senior frontend developer and UI/UX designer. React, Next.js, TypeScript, five years.">']
    parts.append(defs(t, uid))
    parts.append(f'<rect width="{HERO_W}" height="{hero_h}" fill="{t["bg"]}"/>')
    parts.append(blobs(t, uid, HERO_W, hero_h, [
        (90, hero_h - 70, 280, 190, "b1", 21),
        (720, 46, 280, 170, "b2", 26),
        (430, hero_h * 0.55, 240, 140, "b3", 31),
    ]))
    parts.append("".join(
        f'<line x1="{gx}" y1="{canvas_pad}" x2="{gx}" y2="{hero_h - canvas_pad}" stroke="{t["stroke"]}" stroke-opacity="0.22"/>'
        for gx in range(44, HERO_W, 44)
    ))

    hx, hy, hw, hh = P, canvas_pad, HERO_W - P * 2, panel_h
    parts.append(glass_card(hx, hy, hw, hh, t, uid, r=24))

    ix = hx + ix_off

    chip_txt = "AVAILABLE FOR SENIOR ROLES"
    ct_w = text_width(chip_txt, INTER[700], 10.5, 2.3)
    parts.append(f'<rect x="{ix}" y="{hy + chip_y}" width="{ct_w + 42:.1f}" height="24" rx="12" '
                 f'fill="{t["accent"]}" fill-opacity="0.14" stroke="{t["accent"]}" stroke-opacity="0.45" stroke-width="1"/>')
    parts.append(f'<circle cx="{ix + 14}" cy="{hy + chip_y + 12}" r="3.6" fill="{t["accent2"]}">'
                 f'<animate attributeName="opacity" values="1;0.25;1" dur="2.6s" repeatCount="indefinite"/></circle>')
    parts.append(text_paths(chip_txt, INTER[700], 10.5, ix + 26, hy + chip_y + 16, 2.3, t["ink2"])[0])

    nm, _ = text_at_top("AMIT VERMA", ANTON, name_size, ix, hy + name_top, 1.2, t["ink"])
    parts.append(nm)

    role_y = hy + role_rel
    parts.append(text_paths("SENIOR FRONTEND DEVELOPER", INTER[700], 15, ix, role_y, 4.2, t["accent"])[0])
    sep = text_width("SENIOR FRONTEND DEVELOPER", INTER[700], 15, 4.2)
    parts.append(f'<circle cx="{ix + sep + 9}" cy="{role_y - 5}" r="2.6" fill="{t["dim"]}"/>')
    parts.append(text_paths("UI/UX DESIGNER", INTER[700], 15, ix + sep + 20, role_y, 4.2, t["accent2"])[0])

    sy = hy + stack_rel
    x = ix
    for slug, lbl in (("react", "React"), ("nextdotjs", "Next.js"), ("typescript", "TypeScript")):
        parts.append(icon(slug, x, sy - 16, 19, t["brand"][slug]))
        m, w = text_paths(lbl, INTER[600], 14.5, x + 26, sy, 0.2, t["ink2"])
        parts.append(m)
        x += 26 + w + 22

    meta_x = hx + hw - 38
    ysz = 62
    yw = text_width("05", ANTON, ysz, 1)
    parts.append(text_paths("05", ANTON, ysz, meta_x - yw, hy + 34 + ysz * 0.73, 1, t["accent"])[0])
    lab = "YEARS SHIPPING"
    lw = text_width(lab, INTER[700], 10, 2.4)
    parts.append(text_paths(lab, INTER[700], 10, meta_x - lw, hy + 34 + ysz * 0.73 + 17, 2.4, t["dim"])[0])
    handle = "@it-is-amit"
    hw2 = text_width(handle, INTER[600], 12, 0.6)
    parts.append(text_paths(handle, INTER[600], 12, meta_x - hw2, hy + hh - 26, 0.6, t["muted"])[0])

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


# ================================================================ SOCIAL CARDS
# Each link is its own image so it can sit inside its own <a>. A single combined
# image can never be clickable in more than one place.
CARD_W, CARD_H = 424, 104
WIDE_W = 864                    # the full-width slot, drawn at its real size     # wide card, two per row
MINI_W, MINI_H = 277, 104     # mini card, three per row


def social_card(theme, slug, name, handle, full=False):
    """One contact card as a standalone image, ready to wrap in an anchor."""
    t = THEMES[theme]
    uid = "d" if theme == "dark" else "l"
    W = WIDE_W if full else CARD_W
    H = CARD_H
    ink = t["brand"].get(slug, t["accent2"])
    if slug == "link":
        ink = t["accent2"]

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{name}, {handle}">']
    parts.append(defs(t, uid))
    parts.append(f'<rect width="{W}" height="{H}" fill="{t["bg"]}"/>')
    parts.append(blobs(t, uid, W, H, [
        (W * 0.12, H * 0.1, 190, 130, "b1", 23),
        (W * 0.9, H, 190, 140, "b3", 27),
    ]))
    parts.append(glass_card(6, 6, W - 12, H - 12, t, uid, r=18))

    # icon chip
    isz = 34
    bx, by = 22, 20
    parts.append(f'<rect x="{bx}" y="{by}" width="{isz}" height="{isz}" rx="10" fill="{ink}" fill-opacity="0.14" '
                 f'stroke="url(#edge-{uid})" stroke-width="1"/>')
    if slug == "link":
        cx, cy = bx + isz / 2, by + isz / 2
        parts.append(f'<g stroke="{ink}" stroke-width="2" stroke-linecap="round" fill="none">'
                     f'<path d="M{cx - 6.5} {cy + 1} a5 5 0 0 1 0 -7 l3.2 -3.2"/>'
                     f'<path d="M{cx + 6.5} {cy - 1} a5 5 0 0 1 0 7 l-3.2 3.2"/>'
                     f'<path d="M{cx - 4} {cy + 4} l8 -8"/></g>')
    else:
        parts.append(icon(slug, bx + (isz - isz * 0.56) / 2, by + (isz - isz * 0.56) / 2,
                          isz * 0.56, ink))

    # name + handle
    ns = 15.5
    parts.append(text_paths(name, INTER[700], ns, bx + isz + 13, by + 15, 0.2, t["ink"])[0])
    parts.append(text_paths(handle, INTER[500], 12.5,
                            bx + isz + 13, by + 32, 0.1, t["muted"])[0])

    arrow_x = W - 34
    parts.append(f'<path d="M{arrow_x} {H - 36} l7 6 l-7 6" stroke="{t["accent"]}" '
                 f'stroke-width="1.9" fill="none" stroke-linecap="round" stroke-linejoin="round"/>')

    parts.append("</svg>")
    return "\n".join(parts)


SOCIAL_LINKS = [
    ("github", "GitHub", "it-is-amit", "https://github.com/it-is-amit", True),
    ("linkedin", "LinkedIn", "amit-verma", "https://www.linkedin.com/in/amit-verma-2a46971b4/", True),
    ("link", "Portfolio", "portfolio-itisamit.vercel.app", "https://portfolio-itisamit.vercel.app/", False),
    ("instagram", "Instagram", "it_is_amit", "https://www.instagram.com/it_is_amit", False),
    ("gmail", "Email", "amverma1204t", "mailto:amverma1204t@gmail.com", False),
]


if __name__ == "__main__":
    import resvg_py

    for theme in THEMES:
        jobs = [("hero", hero(theme)), ("bento", bento(theme))]
        for slug, name, handle, url, wide in SOCIAL_LINKS:
            jobs.append((f"social-{slug}", social_card(theme, slug, name, handle,
                                                       full=(slug == "gmail"))))

        for name, markup in jobs:
            ET.fromstring(markup)  # fail loudly on malformed SVG
            (OUT / f"{name}-{theme}.svg").write_text(markup, encoding="utf-8")
            png = bytes(resvg_py.svg_to_bytes(svg_string=markup, zoom=2))
            (OUT / f"{name}-{theme}.png").write_bytes(png)
            print(f"{name}-{theme}: svg {len(markup) // 1024:3} KB · png {len(png) // 1024:3} KB")
