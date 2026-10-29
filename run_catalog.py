"""Collect, validate and optionally import; raw data never leaves the runner as an artifact."""
import argparse
from urllib.error import HTTPError
import json
from pathlib import Path
from arval_db_sync import get_github_oidc, ENDPOINT
from urllib.request import Request, urlopen
from arval_full_snapshot import run
from arval_normalize import normalize_snapshot
from validate_arval_snapshot import validate


def api(payload):
    # A fresh token is requested for every call; never print it or HTTP bodies.
    req = Request(ENDPOINT, data=json.dumps(payload).encode(), method="POST", headers={
        "Authorization": "Bearer " + get_github_oidc(), "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=120) as response:
            return json.load(response)
    except HTTPError as error:
        # The server returns only fixed aggregate/error codes, never payloads or tokens.
        body = json.loads(error.read(4096))
        raise RuntimeError(f"Ingest HTTP {error.code}: {body.get('error')}, reason={body.get('reason')}") from None


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--mode", choices=["dry-run", "import", "saved-import"], required=True)
    args = cli.parse_args()
    baseline = api({"action": "baseline"})
    if not baseline.get("ok") or not baseline.get("baseline"):
        raise RuntimeError("No verified production baseline")
    Path("baseline.json").write_text(json.dumps(baseline["baseline"]))
    if args.mode != "saved-import":
        run()
    path = validate()
    data = json.loads(path.read_text())
    normalized = path.parent / "normalized" / path.name
    normalized.parent.mkdir(parents=True, exist_ok=True)
    normalized.write_text(json.dumps(normalize_snapshot(data), ensure_ascii=False))
    from arval_db_sync import prepare
    payload = prepare(path)
    if args.mode == "dry-run":
        print(f"Dry crawl validated: {payload['total_unique']} vehicles, {payload['page_count']} pages; no writes")
        return
    result = api(payload)
    if (result.get("ok") is not True or result.get("scan_date") != payload["scan_date"] or
        result.get("vehicles") != payload["total_unique"] or
        result.get("observations") != payload["total_unique"]):
        raise RuntimeError("Production import verification failed")
    print(json.dumps({k: result[k] for k in ("ok", "scan_date", "vehicles", "observations")}))


if __name__ == "__main__":
    main()
