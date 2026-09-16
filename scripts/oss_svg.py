"""Draw the open-source contributions grid as a self-contained SVG.

Everything the image needs is inlined, avatars included as data URIs: GitHub
serves README images through Camo as <img>, where an SVG cannot load anything
external. Animation uses SMIL for the same reason the infrastructure diagram
does, since CSS keyframes inside an <img> SVG do not reliably run there. Nothing
starts hidden: a renderer that ignores animation must still show the whole grid.
"""
from xml.sax.saxutils import escape

FONT = "-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"

# GitHub's own pull request colours, so the states read the way they do on github.com.
THEMES = {
    "light": dict(bg="#ffffff", card="#f6f8fa", stroke="#d0d7de", text="#1f2328", muted="#59636e",
                  link="#0969da", accent="#1a4f8a", merged="#8250df", open="#1a7f37", chip="#eaeef2"),
    "dark":  dict(bg="#0d1117", card="#161b22", stroke="#30363d", text="#e6edf3", muted="#8b949e",
                  link="#4493f8", accent="#58a6ff", merged="#a371f7", open="#3fb950", chip="#21262d"),
}

W, PAD, GAP = 820, 16, 16
HEADER_H, CARD_H = 64, 104
CARD_W = (W - 2 * PAD - GAP) // 2

# Octicons (MIT), 16px grid.
STAR = ("M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 "
        "4.192a.751.751 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 "
        "6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z")
MERGE = ("M5.45 5.154A4.25 4.25 0 0 0 9.25 7.5h1.378a2.251 2.251 0 1 1 0 1.5H9.25A5.734 5.734 0 0 1 5 "
         "7.123v3.505a2.25 2.25 0 1 1-1.5 0V5.372a2.25 2.25 0 1 1 1.95-.218ZM4.25 13.5a.75.75 0 1 0 "
         "0-1.5.75.75 0 0 0 0 1.5Zm8.5-4.5a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5ZM5 3.25a.75.75 0 1 0 0 .005V3.25Z")
PULL = ("M1.5 3.25a2.25 2.25 0 1 1 3 2.122v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.25 2.25 0 0 1 1.5 "
        "3.25Zm5.677-.177L9.573.677A.25.25 0 0 1 10 .854V2.5h1A2.5 2.5 0 0 1 13.5 5v5.628a2.251 2.251 0 "
        "1 1-1.5 0V5a1 1 0 0 0-1-1h-1v1.646a.25.25 0 0 1-.427.177L7.177 3.427a.25.25 0 0 1 0-.354ZM3.75 "
        "2.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm0 9.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm8.25.75a.75.75 "
        "0 1 0 1.5 0 .75.75 0 0 0-1.5 0Z")


def text_width(s, size):
    """Rough rendered width of s in the system UI font; good enough to lay out and truncate."""
    narrow, wide = set("il.,:;'|!()[] "), set("mwMW@")
    units = sum(0.3 if c in narrow else 0.85 if c in wide else 0.66 if c.isupper() else 0.54 for c in s)
    return units * size


def fit(s, size, max_w):
    if text_width(s, size) <= max_w:
        return s
    while s and text_width(s + "…", size) > max_w:
        s = s[:-1]
    return s.rstrip() + "…"


def short_count(n):
    return f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)


def header(t, merged, in_review, projects):
    stats = [(merged, "merged", t["merged"]), (in_review, "in review", t["open"]), (projects, "projects", t["accent"])]
    out = [f'<text x="{PAD}" y="30" font-family="{FONT}" font-size="13" font-weight="700" '
           f'fill="{t["accent"]}" letter-spacing="1.4">OPEN SOURCE</text>',
           f'<text x="{PAD}" y="50" font-family="{FONT}" font-size="12" fill="{t["muted"]}">'
           f'Pull requests to other people\'s projects</text>']
    x = W - PAD
    for value, label, colour in reversed(stats):
        label_w = text_width(label, 12)
        value_w = text_width(str(value), 22)
        x -= label_w
        out.append(f'<text x="{x:.0f}" y="44" font-family="{FONT}" font-size="12" fill="{t["muted"]}">{label}</text>')
        x -= value_w + 6
        out.append(f'<text x="{x:.0f}" y="44" font-family="{FONT}" font-size="22" font-weight="700" '
                   f'fill="{colour}">{value}</text>')
        x -= 28
    return "\n  ".join(out)


def avatar(x, y, size, owner, data_uri, t, idx):
    clip = f"av{idx}"
    if data_uri:
        return (f'<clipPath id="{clip}"><circle cx="{x + size / 2}" cy="{y + size / 2}" r="{size / 2}"/></clipPath>'
                f'<image href="{data_uri}" x="{x}" y="{y}" width="{size}" height="{size}" clip-path="url(#{clip})"/>'
                f'<circle cx="{x + size / 2}" cy="{y + size / 2}" r="{size / 2 - 0.5}" fill="none" stroke="{t["stroke"]}"/>')
    # No avatar available: a lettered disc keeps the layout intact.
    return (f'<circle cx="{x + size / 2}" cy="{y + size / 2}" r="{size / 2}" fill="{t["chip"]}"/>'
            f'<text x="{x + size / 2}" y="{y + size / 2 + 4}" text-anchor="middle" font-family="{FONT}" '
            f'font-size="12" font-weight="700" fill="{t["muted"]}">{escape(owner[:1].upper())}</text>')


def chip(x, y, number, merged, t):
    label = f"#{number}"
    w = text_width(label, 11) + 30
    colour = t["merged"] if merged else t["open"]
    icon = MERGE if merged else PULL
    return w, (f'<rect x="{x:.0f}" y="{y}" width="{w:.0f}" height="20" rx="10" fill="{t["chip"]}"/>'
               f'<path d="{icon}" fill="{colour}" transform="translate({x + 7:.0f},{y + 4}) scale(0.75)"/>'
               f'<text x="{x + 23:.0f}" y="{y + 14}" font-family="{FONT}" font-size="11" fill="{t["text"]}">{label}</text>')


def card(x, y, project, t, idx):
    has_open = any(not p["merged"] for p in project["prs"])
    all_merged = not has_open
    dot = t["merged"] if all_merged else t["open"]
    inner = x + 14
    parts = ['<g>',
             f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{CARD_H}" rx="10" fill="{t["card"]}" stroke="{t["stroke"]}"/>',
             avatar(inner, y + 14, 26, project["owner"], project.get("avatar"), t, idx)]

    name_x = inner + 36
    stars = f"{short_count(project['stars'])}" if project.get("stars") is not None else ""
    stars_w = text_width(stars, 12) + 18 if stars else 0
    name = fit(project["name"], 15, CARD_W - (name_x - x) - stars_w - 34)
    parts.append(f'<circle cx="{name_x + 4}" cy="{y + 27}" r="4" fill="{dot}">'
                 + ('<animate attributeName="opacity" values="1;0.35;1" dur="2.4s" repeatCount="indefinite"/>'
                    if has_open else '') + '</circle>')
    parts.append(f'<text x="{name_x + 14}" y="{y + 32}" font-family="{FONT}" font-size="15" font-weight="600" '
                 f'fill="{t["link"]}">{escape(name)}</text>')
    if stars:
        sx = x + CARD_W - 14 - text_width(stars, 12)
        parts.append(f'<path d="{STAR}" fill="{t["muted"]}" transform="translate({sx - 16:.0f},{y + 20}) scale(0.8)"/>'
                     f'<text x="{sx:.0f}" y="{y + 31}" font-family="{FONT}" font-size="12" fill="{t["muted"]}">{stars}</text>')

    summary = fit(project["summary"], 12.5, CARD_W - (name_x - x) - 14)
    parts.append(f'<text x="{name_x}" y="{y + 55}" font-family="{FONT}" font-size="12.5" fill="{t["text"]}">'
                 f'{escape(summary)}</text>')

    cx, limit = name_x, x + CARD_W - 14
    prs = project["prs"]
    for i, pr in enumerate(prs):
        remaining = len(prs) - i
        w, svg = chip(cx, y + 70, pr["number"], pr["merged"], t)
        more_w = text_width(f"+{remaining}", 11) + 16
        if cx + w > limit or (remaining > 1 and cx + w + more_w > limit):
            parts.append(f'<text x="{cx + 2:.0f}" y="{y + 84}" font-family="{FONT}" font-size="11" '
                         f'fill="{t["muted"]}">+{remaining}</text>')
            break
        parts.append(svg)
        cx += w + 6
    parts.append("</g>")
    return "\n  ".join(parts)


def more_card(x, y, t, idx):
    return ('<g>'
            f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{CARD_H}" rx="10" fill="none" stroke="{t["stroke"]}" '
            f'stroke-dasharray="5 4"/>'
            f'<text x="{x + CARD_W / 2}" y="{y + 48}" text-anchor="middle" font-family="{FONT}" font-size="14" '
            f'font-weight="600" fill="{t["text"]}">Every pull request</text>'
            f'<text x="{x + CARD_W / 2}" y="{y + 68}" text-anchor="middle" font-family="{FONT}" font-size="12" '
            f'fill="{t["muted"]}">listed with links below the grid</text></g>')


def build(theme, projects, merged, in_review):
    t = THEMES[theme]
    cells = len(projects) + (len(projects) % 2)
    rows = cells // 2
    h = HEADER_H + rows * CARD_H + (rows - 1) * GAP + PAD
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" role="img" '
           f'aria-label="Open source: {merged} merged and {in_review} in review pull requests across {len(projects)} projects">',
           f'<rect width="{W}" height="{h}" fill="{t["bg"]}"/>',
           header(t, merged, in_review, len(projects))]
    for i in range(cells):
        x = PAD + (i % 2) * (CARD_W + GAP)
        y = HEADER_H + (i // 2) * (CARD_H + GAP)
        out.append(card(x, y, projects[i], t, i) if i < len(projects) else more_card(x, y, t, i))
    out.append("</svg>")
    return "\n  ".join(out)
