#!/usr/bin/env python3
"""Push a completed Arval snapshot to private Supabase through GitHub Actions OIDC.

No Supabase credentials, personal passwords or long-lived secrets in GitHub.
The Edge Function verifies signed short-lived GitHub identity and handles writes.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

AUDIENCE = "arval-car-radar-supabase-ingest"
ENDPOINT = "https://umplaiqonphkrtfslsxj.supabase.co/functions/v1/ingest-arval"


def prepare(snapshot: Path) -> dict:
    if snapshot.parent.name != "data" or not snapshot.name.startswith("arval-baseline-"):
        raise ValueError("Expected data/arval-baseline-YYYY-MM-DD.json")
    day = snapshot.stem.removeprefix("arval-baseline-")
    if len(day) != 10:
        raise ValueError("Invalid snapshot date")
    raw = json.loads(snapshot.read_text(encoding="utf-8"))
    captured = datetime.fromisoformat(raw["captured_at_utc"])
    if captured.tzinfo is None or captured.astimezone(ZoneInfo("Europe/Prague")).date().isoformat() != day:
        raise ValueError("Snapshot date does not match actual capture date in Prague")
    normalized_path = snapshot.parent / "normalized" / snapshot.name
    norm = json.loads(normalized_path.read_text(encoding="utf-8"))
    if (raw.get("complete") is not True or raw.get("finish_reason") != "end_of_catalog"
            or norm.get("source_snapshot_time") != raw.get("captured_at_utc")
            or norm.get("total") != raw.get("total_unique")
            or norm.get("normalizer_version") != 3
            or len(norm.get("vehicles", [])) != raw.get("total_unique")
            or len(raw.get("pages", [])) < 1):
        raise ValueError("Source and normalized snapshots are not complete/matching")
    return {
        "scan_date": day,
        "captured_at_utc": raw["captured_at_utc"],
        "complete": True,
        "total_unique": raw["total_unique"],
        "page_count": len(raw["pages"]),
        "normalizer_version": 3,
        "snapshot_path": snapshot.as_posix(),
        "vehicles": norm["vehicles"],
    }


def get_github_oidc() -> str:
    endpoint = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")
    bearer = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not endpoint or not bearer:
        raise RuntimeError("GitHub Actions OIDC is required; do not run this from a personal machine")
    sep = "&" if "?" in endpoint else "?"
    url = endpoint + sep + urlencode({"audience": AUDIENCE})
    request = Request(url, headers={"Authorization": "Bearer " + bearer}, method="GET")
    with urlopen(request, timeout=20) as response:
        result = json.loads(response.read(100000))
    if not isinstance(result.get("value"), str):
        raise RuntimeError("GitHub Actions OIDC token was not issued")
    return result["value"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--auth-probe", action="store_true")
    args = parser.parse_args()
    payload = prepare(args.snapshot)
    print("Prepared", payload["scan_date"], payload["total_unique"],
          "records", payload["page_count"], "catalog pages", flush=True)
    if args.dry_run:
        print("Dry run: no network request", flush=True)
        return
    token = get_github_oidc()
    if args.auth_probe:
        from urllib.error import HTTPError
        probe = Request(
            ENDPOINT, data=b'{}', method="POST",
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        )
        try:
            with urlopen(probe, timeout=25) as response:
                raise RuntimeError("Invalid payload should not be accepted")
        except HTTPError as error:
            if error.code != 422:
                raise RuntimeError(f"Authentication probe failed: HTTP {error.code}") from None
            print("GitHub OIDC authentication verified (HTTP 422 for intentionally invalid data)", flush=True)
        return
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > 2_000_000:
        raise ValueError("Import payload exceeds endpoint limit")
    request = Request(
        ENDPOINT, data=encoded, method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    # Never log tokens or the source payload.
    with urlopen(request, timeout=120) as response:
        result = json.loads(response.read(50000))
    if (not result.get("ok") or result.get("vehicles") != payload["total_unique"]
            or result.get("observations") != payload["total_unique"]):
        raise RuntimeError("Import returned unexpected counts")
    print("SQL import verified:", result, flush=True)


if __name__ == "__main__":
    main()

