#!/usr/bin/env python3
"""Regenerate the open-source section of README.md from GitHub's search API.

Lists pull requests the profile owner sent to public repositories they do not
own, drawn as a card per project (assets/oss-*.svg) with every pull request
listed underneath. Closed-without-merge PRs are left out.

The query always carries `is:public`, so work in private organisation
repositories can never appear here, whatever token the script runs with.

If the API is unreachable or returns nothing, the README and images are left
untouched, so a transient outage can never publish an empty section.

Card summaries come from assets/oss-summaries.json when a project has one, and
fall back to the most recent pull request title otherwise.
"""
import base64
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import oss_svg  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
ASSETS = ROOT / "assets"
SUMMARIES = ASSETS / "oss-summaries.json"
USER = os.environ.get("PROFILE_USER", "Hayyan612")

START, END = "<!-- oss:start -->", "<!-- oss:end -->"
QUERY = f"is:pr author:{USER} is:public -user:{USER}"
MAX_PROJECTS = 8
API = "https://api.github.com"
NETWORK_ERRORS = (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, KeyError)


def request(url, raw=False):
    headers = {"accept": "application/vnd.github+json", "user-agent": f"{USER}-profile"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith(API):
        headers["authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return (r.read(), r.headers.get_content_type()) if raw else json.load(r)


def fetch_prs():
    """Return the owner's PRs to public repos they do not own, or None on failure."""
    try:
        data = request(f"{API}/search/issues?" + urllib.parse.urlencode({"q": QUERY, "per_page": 100, "sort": "created"}))
    except NETWORK_ERRORS as e:
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
            "merged": bool(merged_at),
            "merged_at": merged_at,
            "created_at": item["created_at"],
        })
    return prs


def avatar_data_uri(owner):
    """Owner avatar inlined as a data URI; None draws a lettered disc instead."""
    try:
        body, mime = request(f"https://github.com/{owner}.png?size=64", raw=True)
    except NETWORK_ERRORS:
        return None
    if not mime.startswith("image/"):
        return None
    return f"data:{mime};base64,{base64.b64encode(body).decode()}"


def clean_title(title):
    # Drop a conventional-commit prefix ("fix(ui): ") for display.
    title = re.sub(r"^\w+(\([^)]*\))?!?:\s*", "", title)
    return title[:1].upper() + title[1:]


def group_projects(prs):
    summaries = json.loads(SUMMARIES.read_text()) if SUMMARIES.exists() else {}
    by_repo = {}
    for pr in prs:
        by_repo.setdefault(pr["repo"], []).append(pr)

    projects = []
    for repo, repo_prs in by_repo.items():
        owner, name = repo.split("/", 1)
        try:
            stars = request(f"{API}/repos/{repo}")["stargazers_count"]
        except NETWORK_ERRORS:
            stars = None
        # Merged first, then newest, so the chips read as a record rather than a queue.
        repo_prs.sort(key=lambda p: (p["merged"], p["merged_at"] or p["created_at"]), reverse=True)
        latest = max(repo_prs, key=lambda p: p["created_at"])
        projects.append({
            "repo": repo, "owner": owner, "name": name, "stars": stars, "prs": repo_prs,
            "summary": summaries.get(repo) or clean_title(latest["title"]),
            "avatar": avatar_data_uri(owner),
        })

    merged_count = lambda p: sum(pr["merged"] for pr in p["prs"])  # noqa: E731
    projects.sort(key=lambda p: (merged_count(p), p["stars"] or 0), reverse=True)
    return projects[:MAX_PROJECTS]


def pr_table(prs):
    rows = ["| Status | Project | Pull request | Date |", "|---|---|---|---|"]
    ordered = sorted(prs, key=lambda p: (p["merged"], p["merged_at"] or p["created_at"]), reverse=True)
    for pr in ordered:
        status = "Merged" if pr["merged"] else "In review"
        date = (pr["merged_at"] or pr["created_at"])[:10]
        title = clean_title(pr["title"]).replace("|", "\\|")
        rows.append(f"| {status} | [{pr['repo']}](https://github.com/{pr['repo']}) | "
                    f"[#{pr['number']}]({pr['url']}) {title} | {date} |")
    return rows


def render_section(prs):
    search = "https://github.com/search?" + urllib.parse.urlencode({"q": QUERY, "type": "pullrequests"})
    merged = sum(p["merged"] for p in prs)
    return "\n".join([
        START, "",
        "## Open source", "",
        f'<a href="{search}">',
        "  <picture>",
        '    <source media="(prefers-color-scheme: dark)" srcset="assets/oss-dark.svg" />',
        '    <source media="(prefers-color-scheme: light)" srcset="assets/oss-light.svg" />',
        f'    <img alt="Open source: {merged} merged and {len(prs) - merged} in review pull requests" '
        'src="assets/oss-light.svg" width="100%" />',
        "  </picture>",
        "</a>", "",
        "<sub>🟣 merged &nbsp;·&nbsp; 🟢 in review &nbsp;·&nbsp; ★ project stars &nbsp;·&nbsp; refreshed daily</sub>", "",
        "<details>",
        "<summary><b>Every pull request</b></summary>", "",
        *pr_table(prs), "",
        "</details>", "",
        END,
    ])


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

    projects = group_projects(prs)
    merged = sum(p["merged"] for p in prs)
    for theme in oss_svg.THEMES:
        (ASSETS / f"oss-{theme}.svg").write_text(oss_svg.build(theme, projects, merged, len(prs) - merged))
        print(f"wrote assets/oss-{theme}.svg")

    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    README.write_text(head + render_section(prs) + tail)
    print(f"wrote {merged} merged, {len(prs) - merged} in review across {len(projects)} projects")
    return 0


if __name__ == "__main__":
    sys.exit(main())
