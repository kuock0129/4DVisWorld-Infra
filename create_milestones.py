#!/usr/bin/env python3
"""Create GitHub milestones + issues from ROADMAP.md using the gh CLI.

Usage:
    python create_milestones.py --repo vinesmsuic/visualworld-infra --dry-run
    python create_milestones.py --repo vinesmsuic/visualworld-infra

Requires: gh CLI authenticated with write access to the repo.
Safe to re-run: existing milestones and issues with the same title are skipped.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

LABELS = {
    "milestone:M0": "c5def5", "milestone:M1": "c5def5", "milestone:M2": "c5def5",
    "milestone:M3": "c5def5", "milestone:M4": "c5def5", "milestone:M5": "c5def5",
    "stretch": "fef2c0",
}


def gh(args, dry_run=False, capture=True):
    cmd = ["gh", *args]
    if dry_run:
        print("DRY:", " ".join(cmd))
        return ""
    res = subprocess.run(cmd, capture_output=capture, text=True)
    if res.returncode != 0:
        sys.exit(f"gh failed: {' '.join(cmd)}\n{res.stderr}")
    return res.stdout


def parse_roadmap(text):
    # Due dates from the summary table: | M0 | Title | window | 2026-11-15 | owner |
    due = {m: d for m, d in re.findall(r"^\|\s*(M\d)\s*\|[^|]*\|[^|]*\|\s*(\d{4}-\d{2}-\d{2})\s*\|", text, re.M)}
    milestones = []
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        header, _, body = block.partition("\n")
        m = re.match(r"(M\d)\s+—\s+(.*)", header.strip())
        if not m:
            continue
        key, title = m.groups()
        goal = re.search(r"\*\*Goal:\*\*\s*(.*)", body)
        done = re.search(r"\*\*Done when:\*\*\s*(.*)", body)
        tasks = re.findall(r"^- \[ \] (.*)$", body, re.M)
        milestones.append({
            "key": key,
            "title": f"{key} — {title}",
            "due": due.get(key),
            "description": f"{goal.group(1) if goal else ''}\n\nDone when: {done.group(1) if done else ''}".strip(),
            "tasks": tasks,
        })
    return milestones


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--roadmap", default="ROADMAP.md")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    milestones = parse_roadmap(Path(a.roadmap).read_text(encoding="utf-8"))
    if not milestones:
        sys.exit("No milestones found in roadmap.")

    for name, color in LABELS.items():
        gh(["label", "create", name, "--color", color, "--force", "--repo", a.repo], a.dry_run)

    existing_ms = set()
    existing_issues = set()
    if not a.dry_run:
        existing_ms = set(json.loads(gh(["api", f"repos/{a.repo}/milestones?state=all&per_page=100",
                                         "--jq", "[.[].title]"]) or "[]"))
        existing_issues = set(json.loads(gh(["issue", "list", "--repo", a.repo, "--state", "all",
                                             "--limit", "1000", "--json", "title", "--jq", "[.[].title]"]) or "[]"))

    for ms in milestones:
        if ms["title"] in existing_ms:
            print(f"skip milestone (exists): {ms['title']}")
        else:
            args = ["api", f"repos/{a.repo}/milestones", "-f", f"title={ms['title']}",
                    "-f", f"description={ms['description']}"]
            if ms["due"]:
                # 23:59 PST = 07:59 UTC next day; GitHub stores the date part.
                args += ["-f", f"due_on={ms['due']}T23:59:00-08:00"]
            gh(args, a.dry_run)
            print(f"created milestone: {ms['title']}")

        for task in ms["tasks"]:
            stretch = "(stretch)" in task
            title = re.sub(r"\s*\(stretch\)", "", task).strip()
            title = f"[{ms['key']}] {title}"
            if title in existing_issues:
                print(f"  skip issue (exists): {title}")
                continue
            body = f"Part of **{ms['title']}**.\n\n{ms['description']}\n\nSee `ROADMAP.md`."
            labels = f"milestone:{ms['key']}" + (",stretch" if stretch else "")
            gh(["issue", "create", "--repo", a.repo, "--title", title, "--body", body,
                "--milestone", ms["title"], "--label", labels], a.dry_run)
            print(f"  created issue: {title}")


if __name__ == "__main__":
    main()
