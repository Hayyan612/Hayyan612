#!/usr/bin/env python3
"""Regenerate the open-source section of README.md from GitHub's search API.

Lists pull requests the profile owner sent to public repositories they do not
own: merged ones first, then the ones still in review. Closed-without-merge PRs
are left out.

The query always carries `is:public`, so work in private organisation
repositories can never appear here, whatever token the script runs with.

If the API is unreachable or returns nothing, the README is left untouched, so a
transient outage can never publish an empty section.
"""
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
USER = os.environ.get("PROFILE_USER", "Hayyan612")

START, END = "<!-- oss:start -->", "<!-- oss:end -->"
MAX_MERGED, MAX_OPEN = 10, 6
API = "https://api.github.com"


def get(path):
    headers = {"accept": "application/vnd.github+json", "user-agent": f"{USER}-profile"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(API + path, headers=headers), timeout=30) as r:
        return json.load(r)


def fetch_prs():
    """Return the owner's PRs to public repos they do not own, or None on failure."""
    q = f"is:pr author:{USER} is:public -user:{USER}"
    try:
        data = get("/search/issues?" + urllib.parse.urlencode({"q": q, "per_page": 100, "sort": "created"}))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        print(f"search failed ({type(e).__name__}), leaving README unchanged")
        return None

    prs = []
    for item in data.get("items", []):
        merged_at = (item.get("pull_request") or {}).get("merged_at")
        if item["state"] == "closed" and not merged_at:
            continue
        prs.append({
            "repo": item["repository_url"].split("/repos/", 1)[1],
            "number": item["number"],
            "title": item["title"],
            "url": item["html_url"],
            "merged_at": merged_at,
            "created_at": item["created_at"],
        })
    return prs


def stars(repos):
    """Star counts per repo; a failed lookup just omits the count."""
    out = {}
    for repo in repos:
        try:
            out[repo] = get(f"/repos/{repo}")["stargazers_count"]
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, KeyError):
            pass
    return out


def short(n):
    return f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)


def clean_title(title):
    # Drop a conventional-commit prefix ("fix(ui): ") and keep table cells intact.
    title = re.sub(r"^\w+(\([^)]*\))?!?:\s*", "", title)
    return (title[:1].upper() + title[1:]).replace("|", "\\|")


def rows(prs, date_key, star_counts):
    out = []
    for pr in prs:
        count = star_counts.get(pr["repo"])
        project = f"[{pr['repo']}](https://github.com/{pr['repo']})"
        if count is not None:
            project += f" ★ {short(count)}"
        link = f"[#{pr['number']}]({pr['url']}) {clean_title(pr['title'])}"
        out.append(f"| {project} | {link} | {pr[date_key][:10]} |")
    return out


def render(prs):
    merged = sorted((p for p in prs if p["merged_at"]), key=lambda p: p["merged_at"], reverse=True)[:MAX_MERGED]
    in_review = sorted((p for p in prs if not p["merged_at"]), key=lambda p: p["created_at"], reverse=True)[:MAX_OPEN]
    star_counts = stars(sorted({p["repo"] for p in merged + in_review}))

    lines = [START, "", "## Open source", "",
             "Pull requests I have sent to other people's projects, refreshed daily from GitHub.", ""]
    if merged:
        lines += ["**Merged**", "", "| Project | Pull request | Merged |", "|---|---|---|",
                  *rows(merged, "merged_at", star_counts), ""]
    if in_review:
        lines += ["**In review**", "", "| Project | Pull request | Opened |", "|---|---|---|",
                  *rows(in_review, "created_at", star_counts), ""]
    lines.append(END)
    return "\n".join(lines)


def main():
    text = README.read_text()
    if START not in text or END not in text:
        print(f"markers {START} / {END} not found in README.md")
        return 1

    prs = fetch_prs()
    if not prs:
        # An empty result is far more likely to be a broken response than a
        # history that vanished, so refuse to publish it.
        print("no pull requests found, leaving README unchanged")
        return 0

    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    README.write_text(head + render(prs) + tail)
    print(f"wrote {sum(1 for p in prs if p['merged_at'])} merged, "
          f"{sum(1 for p in prs if not p['merged_at'])} in review")
    return 0


if __name__ == "__main__":
    sys.exit(main())
