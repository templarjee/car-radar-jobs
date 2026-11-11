"""GitHub Actions scheduled-run freshness gate (OIDC, read-only)."""
from datetime import datetime
from pathlib import Path
import os
from zoneinfo import ZoneInfo

from run_catalog import api


def already_imported(baseline, day):
    return (
        isinstance(baseline, dict)
        and baseline.get("scan_date") == day
        and type(baseline.get("total_unique")) is int
        and baseline["total_unique"] >= 100
    )


def main():
    response = api({"action": "baseline"})
    if response.get("ok") is not True:
        raise RuntimeError("Catalog baseline is unavailable")
    today = datetime.now(ZoneInfo("Europe/Prague")).date().isoformat()
    current = already_imported(response.get("baseline"), today)
    print(f"CATALOG FRESHNESS: today={today}, current={current}", flush=True)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(f"current={str(current).lower()}\n")


if __name__ == "__main__":
    main()
