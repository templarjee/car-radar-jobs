"""Daily catalog SLO watchdog via the public GitHub Actions audit trail.

No access to private database credentials or raw snapshots. A green workflow
without a successful 'Validate and import' checkpoint is NOT counted.
"""
import json
import os
import sys
from datetime import datetime
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

REPO = "templarjee/car-radar-jobs"
API = "https://api.github.com/repos/" + REPO
WORKFLOWS = ("arval-scheduled.yml", "arval-recovery.yml")
CHECKPOINT = "Validate and import complete catalog"


def request(path, method="GET", payload=None):
    token = os.environ["GITHUB_TOKEN"]
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(API + path, method=method, data=data, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    })
    with urlopen(req, timeout=25) as response:
        return json.load(response)


def local_day(timestamp):
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(
        ZoneInfo("Europe/Prague")).date().isoformat()


def verified_import(jobs):
    return any(
        job.get("name") == "collect"
        and job.get("status") == "completed"
        and job.get("conclusion") == "success"
        and any(step.get("name") == CHECKPOINT
                and step.get("status") == "completed"
                and step.get("conclusion") == "success"
                for step in job.get("steps", []))
        for job in jobs
    )


def has_successful_import(day):
    for workflow in WORKFLOWS:
        runs = request(f"/actions/workflows/{workflow}/runs?per_page=50").get(
            "workflow_runs", [])
        for run in runs:
            if (run.get("status") != "completed"
                    or run.get("conclusion") != "success"
                    or run.get("head_branch") != "main"
                    or local_day(run["run_started_at"]) != day):
                continue
            jobs = request(f"/actions/runs/{run['id']}/jobs?per_page=30").get(
                "jobs", [])
            if verified_import(jobs):
                return True
    return False


def alert_missing(day):
    title = f"[Catalog SLO] Missing verified Arval import {day}"
    issues = request("/issues?state=open&per_page=100")
    if not any(issue.get("title") == title and "pull_request" not in issue
               for issue in issues):
        request("/issues", "POST", {
            "title": title,
            "body": (
                f"No successful Arval full-catalog production import was verified for "
                f"**{day}** (Europe/Prague). This is a real daily-history risk.\n\n"
                "Investigate the scheduled catalog runner and source snapshot gate:\n"
                f"https://github.com/{REPO}/actions/workflows/arval-scheduled.yml\n\n"
                "Audit criteria: successful main-branch workflow **and** successful "
                "'Validate and import complete catalog' step. A green smoke, skipped "
                "backup import or dry-run does not count. Do not backfill made-up prices."
            ),
        })
    print(f"CATALOG SLO FAILURE: no verified import for {day}", flush=True)
    return 1


def main():
    day = datetime.now(ZoneInfo("Europe/Prague")).date().isoformat()
    if has_successful_import(day):
        print(f"CATALOG SLO OK: verified production import for {day}", flush=True)
        return 0
    return alert_missing(day)


if __name__ == "__main__":
    sys.exit(main())
