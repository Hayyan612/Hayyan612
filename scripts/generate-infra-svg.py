#!/usr/bin/env python3
"""Regenerate the infrastructure diagram, using live counts when available.

Reads DOKPLOY_URL and DOKPLOY_API_KEY from the environment. If either is absent
or the API call fails, the last committed counts in assets/infra-data.json are
reused, so a transient outage can never publish a diagram claiming zero services.

Only aggregate counts leave the API. Service names, hostnames and IDs are never
written into the SVG.
"""
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "assets" / "infra-data.json"

SERVICE_KEYS = ("applications", "postgres", "mysql", "mariadb", "mongo", "redis", "compose")


def fetch_live():
    """Return (services, projects) from Dokploy, or None if unavailable."""
    base, key = os.environ.get("DOKPLOY_URL"), os.environ.get("DOKPLOY_API_KEY")
    if not base or not key:
        print("no credentials in env, using committed counts")
        return None

    req = urllib.request.Request(
        base.rstrip("/") + "/api/project.all",
        headers={"x-api-key": key, "accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.load(r)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        # Never fail the build on an infra hiccup; fall back to committed values.
        print(f"dokploy unreachable ({type(e).__name__}), using committed counts")
        return None

    projects = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(projects, list):
        print("unexpected API shape, using committed counts")
        return None

    total = 0
    for p in projects:
        counts = p.get("totalServiceCounts") or {}
        total += sum(int(counts.get(k, 0) or 0) for k in SERVICE_KEYS)

    # A zero reading is far more likely to be a broken response than a real
    # teardown of every service, so refuse to publish it.
    if total == 0:
        print("live count was zero, refusing to publish; using committed counts")
        return None
    return total, len(projects)


def load_committed():
    d = json.loads(DATA.read_text())
    return d["services"], d["projects"], d["servers"]


THEMES = {
    "light": dict(bg="#ffffff", edge="#d0d7de", text="#1f2328", muted="#59636e",
                  card="#f6f8fa", stroke="#d0d7de", accent="#1a4f8a", pulse="#12c4d7"),
    "dark":  dict(bg="#0d1117", edge="#30363d", text="#e6edf3", muted="#8b949e",
                  card="#161b22", stroke="#30363d", accent="#58a6ff", pulse="#12c4d7"),
}
W, H = 900, 340
FONT = "-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"


def box(x, y, w, h, label, sub, t):
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{t["card"]}" '
           f'stroke="{t["stroke"]}" stroke-width="1"/>',
           f'<text x="{x+w/2}" y="{y+(22 if sub else h/2+4)}" text-anchor="middle" '
           f'font-family="{FONT}" font-size="13" font-weight="600" fill="{t["text"]}">{label}</text>']
    if sub:
        out.append(f'<text x="{x+w/2}" y="{y+40}" text-anchor="middle" font-family="{FONT}" '
                   f'font-size="10.5" fill="{t["muted"]}">{sub}</text>')
    return "\n  ".join(out)


def link(x1, y1, x2, y2, t, delay=0.0, dur=2.6):
    # SMIL, not CSS keyframes: GitHub serves images through Camo as <img>,
    # where CSS animations inside an SVG do not reliably run. SMIL does.
    d = f"M {x1} {y1} L {x2} {y2}"
    return (f'<path d="{d}" stroke="{t["edge"]}" stroke-width="1.5" fill="none"/>\n'
            f'  <circle r="3" fill="{t["pulse"]}" opacity="0">\n'
            f'    <animateMotion dur="{dur}s" begin="{delay}s" repeatCount="indefinite" path="{d}"/>\n'
            f'    <animate attributeName="opacity" dur="{dur}s" begin="{delay}s" '
            f'repeatCount="indefinite" values="0;1;1;0" keyTimes="0;0.15;0.85;1"/>\n'
            f'  </circle>')


def build(theme, services, projects, servers):
    t = THEMES[theme]
    server_word = "server" if servers == 1 else "servers"
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'role="img" aria-label="Self-hosted estate: {services} services across {servers} {server_word}">',
         f'<rect width="{W}" height="{H}" fill="{t["bg"]}"/>',
         f'<text x="{W/2}" y="26" text-anchor="middle" font-family="{FONT}" font-size="13" '
         f'font-weight="700" fill="{t["accent"]}" letter-spacing="1.4">SELF-HOSTED ESTATE</text>',
         f'<text x="{W/2}" y="44" text-anchor="middle" font-family="{FONT}" font-size="10.5" '
         f'fill="{t["muted"]}">{services} services across {servers} Linux {server_word}, '
         f'{projects} projects, no managed platform</text>',
         box(360, 62, 180, 46, "Cloudflare", "DNS · CDN · TLS · email auth", t),
         link(450, 108, 450, 136, t, 0.0, 1.5),
         box(360, 136, 180, 46, "Traefik", "routing · automatic TLS", t),
         link(400, 182, 190, 218, t, 0.2),
         link(450, 182, 450, 218, t, 0.35),
         link(500, 182, 710, 218, t, 0.5),
         box(60, 218, 260, 54, "Product services", "API · web console · identity · Postgres", t),
         box(340, 218, 220, 54, "Object storage", "S3-compatible", t),
         box(580, 218, 260, 54, "Internal tools", "PM · wiki · vault · support · finance · HR", t),
         link(450, 272, 450, 300, t, 1.1, 2.0),
         f'<text x="{W/2}" y="316" text-anchor="middle" font-family="{FONT}" font-size="11" '
         f'fill="{t["muted"]}">nightly offsite backups</text>',
         '</svg>']
    return "\n  ".join(p)


def main():
    services, projects, servers = load_committed()
    live = fetch_live()
    if live:
        services, projects = live
        d = json.loads(DATA.read_text())
        d.update(services=services, projects=projects)
        DATA.write_text(json.dumps(d, indent=2) + "\n")
        print(f"live: {services} services across {projects} projects")
    else:
        print(f"committed: {services} services across {projects} projects")

    for name in THEMES:
        (ROOT / "assets" / f"infra-{name}.svg").write_text(build(name, services, projects, servers))
        print(f"wrote assets/infra-{name}.svg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
