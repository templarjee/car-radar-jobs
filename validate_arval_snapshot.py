#!/usr/bin/env python3
"""Reject incomplete, suspicious or duplicate Arval full-catalog snapshots."""
import json
import sys
from pathlib import Path
from arval_normalize import normalize

STATUS = Path("arval_snapshot_status.json")


def validate():
    if not STATUS.is_file():
        raise ValueError("Missing crawler status file")
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    if status.get("complete") is not True or status.get("finish_reason") != "end_of_catalog":
        raise ValueError("Crawler did not reach catalog end")
    path = Path(status["path"])
    if not path.exists() or not path.name.startswith("arval-baseline-"):
        raise ValueError("Validated snapshot path missing or invalid")
    data = json.loads(path.read_text(encoding="utf-8"))
    cars = data.get("cars", [])
    pages = data.get("pages", [])
    if (data.get("complete") is not True or data.get("finish_reason") != "end_of_catalog"
            or not pages or len(pages) != status.get("page_count")
            or pages[-1].get("next_url") is not None
            or any(p.get("page") != i or p.get("http_status") != 200
                   or not 1 <= p.get("count", 0) <= 20
                   or p.get("new", 0) < 1
                   for i, p in enumerate(pages, 1))
            or sum(p["new"] for p in pages) != len(cars)
            or data.get("total_unique") != len(cars)):
        raise ValueError("Inconsistent page/completeness evidence")
    ids = [car.get("id") for car in cars]
    if len(cars) < 100:
        raise ValueError("Suspiciously few vehicles: " + str(len(cars)))
    if len(cars) != status["total_unique"] or len(ids) != len(set(ids)):
        raise ValueError("Snapshot count/duplicate IDs validation failed")
    for car in cars:
        if not normalize(car).get("title"):
            raise ValueError("Unrecoverable vehicle title for Arval ID " + str(car.get("id")))
        if car.get("mileage_km") is None:
            raise ValueError("Missing mileage for Arval ID " + str(car.get("id")))
    baseline_path = Path("baseline.json")
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text())
        count = baseline.get("total_unique")
        if type(count) is not int or count < 100 or len(cars) < count * 0.65:
            raise ValueError("Production baseline comparison failed")
    historic = sorted(Path("data").glob("arval-baseline-*.json"))
    earlier = [candidate for candidate in historic if candidate != path]
    if earlier:
        previous = json.loads(earlier[-1].read_text(encoding="utf-8"))
        count = int(previous.get("total_unique", 0))
        if count > 0 and len(cars) < count * 0.65:
            raise ValueError(
                "Current " + str(len(cars)) + " vehicles <65% of previous "
                + str(count) + "; manual review needed"
            )
    print("VALIDATED " + str(len(cars)) + " unique listing records", flush=True)
    print("Prices are listing candidates; mix of purchase and operating lease offers", flush=True)
    return path


if __name__ == "__main__":
    try:
        validate()
    except Exception as exc:
        print("SNAPSHOT REJECTED: " + str(exc), file=sys.stderr)
        sys.exit(1)

