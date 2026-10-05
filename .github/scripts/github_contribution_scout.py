"""Find recent beginner-friendly GitHub issues and write a local CSV queue.

This read-only scout searches the public GitHub Issues API. It does not create
GitHub comments, issues, pull requests, commits, or pushes.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path


SEARCHES = [
    ("Python automation", "language:Python automation"),
    ("Python data and dashboards", "language:Python (dashboard OR analytics)"),
    ("Java beginner tasks", "language:Java"),
    ("SQL and data", "language:SQL data"),
    ("IT support tools", "language:Python (helpdesk OR support)"),
]

FIELDS = ["Score", "Topic", "Repository", "Title", "UpdatedUTC", "DaysSinceUpdate", "Comments", "Labels", "IssueURL", "RepositoryURL", "Summary"]


def find_candidates(top: int) -> list[dict]:
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=45)).date()
    candidates: dict[str, dict] = {}
    for topic, terms in SEARCHES:
        query = f'is:issue is:open label:"good first issue" updated:>={cutoff.isoformat()} {terms}'
        params = urllib.parse.urlencode({"q": query, "sort": "updated", "order": "desc", "per_page": 30})
        request = urllib.request.Request(
            f"https://api.github.com/search/issues?{params}",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "Harpreet-GitHub-Contribution-Scout", "X-GitHub-Api-Version": "2022-11-28"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                items = json.loads(response.read().decode("utf-8")).get("items", [])
        except Exception as exc:
            print(f"Search failed for {topic}: {exc}")
            continue

        for issue in items:
            if issue.get("pull_request"):
                continue
            issue_url = issue.get("html_url")
            repo = issue.get("repository_url", "").removeprefix("https://api.github.com/repos/")
            if not issue_url or not repo:
                continue
            labels = [label.get("name", "") for label in issue.get("labels", [])]
            updated = dt.datetime.fromisoformat(issue["updated_at"].replace("Z", "+00:00")).astimezone(dt.timezone.utc)
            days_old = max(0, int((dt.datetime.now(dt.timezone.utc) - updated).total_seconds() // 86400))
            comments = int(issue.get("comments", 0))
            title = issue.get("title", "")
            score = 4 + (3 if days_old <= 7 else 2 if days_old <= 21 else 0)
            score += int(0 < comments <= 20)
            score += int(any(word in title.lower() for word in ("documentation", "docs", "typo", "example")))
            summary = " ".join((issue.get("body") or "").split())
            if len(summary) > 420:
                summary = summary[:420].rstrip() + "…"
            candidates[issue_url] = {
                "Score": score, "Topic": topic, "Repository": repo, "Title": title,
                "UpdatedUTC": updated.strftime("%Y-%m-%d %H:%M"), "DaysSinceUpdate": days_old,
                "Comments": comments, "Labels": ", ".join(labels), "IssueURL": issue_url,
                "RepositoryURL": f"https://github.com/{repo}", "Summary": summary,
            }
    return sorted(candidates.values(), key=lambda item: (item["Score"], item["UpdatedUTC"]), reverse=True)[:top]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("github-contribution-queue.csv"))
    args = parser.parse_args()
    items = find_candidates(args.top)
    if not items:
        print("No matching current issues found; no queue file was written.")
        return
    temporary = args.output.with_suffix(".tmp")
    with temporary.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(items)
    temporary.replace(args.output)
    print(f"Wrote {len(items)} candidates to {args.output}")


if __name__ == "__main__":
    main()
