#!/usr/bin/env python3
"""Reject incomplete, suspicious or duplicate Arval full-catalog snapshots."""
import json
import sys
from urllib.parse import urlparse
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
    pending = data.get('pending_price_cars', [])
    if not isinstance(pending, list):
        raise ValueError('Pending-price roster must be a list')
    price_ids = {c.get('id') for c in cars}
    pending_ids = [r.get('id') for r in pending]
    if len(pending_ids) != len(set(pending_ids)):
        raise ValueError('Duplicate IDs in pending-price roster')
    if set(pending_ids) & price_ids:
        raise ValueError('Pending-price and priced rosters overlap: ' +
                         str(sorted(set(pending_ids) & price_ids)[:10]))
    for record in pending:
        car_id = record.get('id')
        if not isinstance(car_id, str) or not car_id.isdigit():
            raise ValueError('Invalid pending-price ID: ' + repr(car_id))
        url = urlparse(record.get('url', ''))
        parts = url.path.strip('/').split('/')
        if (record.get('price_status') != 'pending' or not record.get('title')
                or type(record.get('mileage_km')) is not int
                or url.scheme != 'https' or url.netloc != 'www.arvalclub.cz'
                or url.query or url.fragment or not url.path.endswith('/')
                or len(parts) != 4 or parts[0] != 'cz' or parts[-1] != car_id):
            raise ValueError('Malformed pending-price record for Arval ID ' + car_id)
    # A mutable paginated catalog may show an ID as "pending" on one page
    # and as priced on another during the same crawl. Retain the priced
    # observation; pending cards are pagination evidence, not prices.
    evidence_ids = [v for page in pages for v in page.get('pending_price_ids', [])]
    expected_pending = set(evidence_ids) - price_ids
    if set(pending_ids) != expected_pending:
        raise ValueError(
            'Pending-price evidence mismatch: missing=' +
            str(sorted(expected_pending - set(pending_ids))[:10]) +
            ', extra=' + str(sorted(set(pending_ids) - expected_pending)[:10])
        )
    repeated = len(evidence_ids) - len(set(evidence_ids))
    transitioned = len(set(evidence_ids) & price_ids)
    if repeated or transitioned:
        print(f'PENDING PRICE EVIDENCE: {repeated} repeat page appearances; '
              f'{transitioned} IDs also observed with a price', flush=True)
    if (data.get("complete") is not True or data.get("finish_reason") != "end_of_catalog"
            or not pages or len(pages) != status.get("page_count")
            or pages[-1].get("next_url") is not None
            or any(p.get("page") != i or p.get("http_status") != 200
                   or not 1 <= p.get("count", 0) <= 20
                   or p.get("new", 0) < 0
                   or (p.get('new', 0) == 0 and not p.get('pending_price_ids'))
                   or len(set(p.get('pending_price_ids', []))) != len(p.get('pending_price_ids', []))
                   or p.get('count', 0) != p.get('new', 0) + len(p.get('duplicate_ids', [])) + len(p.get('pending_price_ids', []))
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

