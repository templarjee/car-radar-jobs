#!/usr/bin/env python3
"""One-time, read-only personal baseline of Arval Club's public car inventory.

Follows only the site's own "Dalších 20 nabídek" links; verifies robots.txt;
fetches max 50 pages, sequentially, 4 seconds apart. Does not access vehicle
detail pages, log in, bypass restrictions, or perform repeated monitoring.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from arval_cards import car_records

START = "https://www.arvalclub.cz/nabidka-vozu/prodej/?"
HOST = "www.arvalclub.cz"
AGENT = "PriceRadarPersonalResearch/0.1 (one-time private reference)"
MAX_PAGES = 50
DELAY = 4.0
LIMIT_BYTES = 4_000_000
RESULT = Path("arval_snapshot_status.json")
PARTIAL = Path("arval_snapshot_partial.json")
ARCHIVE = Path("data") / (
    "arval-baseline-" + datetime.now(ZoneInfo("Europe/Prague")).strftime("%Y-%m-%d") + ".json"
)


def approved(url):
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or u.hostname != HOST:
        return False
    if u.path in ("/nabidka-vozu/prodej/", "/nabidka-vozu/"):
        if not u.query:
            return True
        q = urllib.parse.parse_qs(u.query)
        return (
            set(q) == {"pg"} and len(q["pg"]) == 1
            and q["pg"][0].isdigit()
            and 1 <= int(q["pg"][0]) <= MAX_PAGES
        )
    if u.path != "/pages.script.php":
        return False
    q = urllib.parse.parse_qs(u.query)
    return (
        q.get("action") == ["cars-pos"]
        and len(q.get("pos", [])) == 1
        and q["pos"][0].isdigit()
        and 0 < int(q["pos"][0]) <= MAX_PAGES * 20
    )


def check_robots():
    url = "https://" + HOST + "/robots.txt"
    req = urllib.request.Request(url, headers={"User-Agent": AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            body = response.read(500_000).decode("utf-8", errors="replace")
            status = response.status
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(body.splitlines())
        return parser, {"status": status, "interpretation": "robots_parsed"}
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 410):
            return None, {"status": exc.code, "interpretation": "robots_absent"}
        raise RuntimeError("robots.txt HTTP " + str(exc.code) + ": stop")
    except Exception as exc:
        raise RuntimeError("robots.txt cannot be checked: " + str(exc))


def download(url):
    if not approved(url):
        raise ValueError("Unexpected URL: " + url)
    request = urllib.request.Request(url, headers={
        "User-Agent": AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "cs-CZ,cs;q=0.9",
    })
    with urllib.request.urlopen(request, timeout=25) as response:
        if response.status != 200:
            raise ValueError("HTTP " + str(response.status))
        ctype = response.headers.get("Content-Type", "").lower()
        if "html" not in ctype:
            raise ValueError("Non-HTML response")
        redirected = response.geturl()
        if not approved(redirected):
            raise ValueError("Unexpected redirect")
        data = response.read(LIMIT_BYTES + 1)
        if len(data) > LIMIT_BYTES:
            raise ValueError("Oversized HTML response")
    return BeautifulSoup(data.decode("utf-8", errors="replace"), "html.parser"), redirected


def page_next(soup, current):
    for link in soup.select("a[href]"):
        if "dalších" not in link.get_text(" ", strip=True).lower():
            continue
        url = urllib.parse.urljoin(current, link["href"])
        if approved(url) and url != current:
            return url
    return None


def enrich_records(soup, records):
    """Capture enough text for future matching, without reading detail pages."""
    by_id = {r["id"]: r for r in records}
    for link in soup.select("a[href]"):
        u = urllib.parse.urlparse(urllib.parse.urljoin(START, link["href"]))
        last = u.path.strip("/").split("/")[-1]
        if last not in by_id or "listing_text" in by_id[last]:
            continue
        target = link.parent
        for _ in range(10):
            if target is None or target.name in ("html", "body"):
                break
            body = target.get_text(" ", strip=True)
            if target.find(["h2", "h3"]) and "Kč" in body and len(body) < 1800:
                by_id[last]["listing_text"] = body[:600]
                break
            target = target.parent
    return records


def run():
    started = datetime.now(timezone.utc).isoformat()
    pages, cars, seen, current = [], {}, set(), START
    robots_info = {}
    reason = "not_started"
    try:
        robots, robots_info = check_robots()
        print("robots.txt:", robots_info, flush=True)
        for number in range(1, MAX_PAGES + 1):
            if current in seen:
                reason = "url_loop"
                break
            if robots and not robots.can_fetch(AGENT, current):
                reason = "robots_disallowed"
                break
            seen.add(current)
            if number > 1:
                time.sleep(DELAY)
            soup, final = download(current)
            found = enrich_records(soup, car_records(soup, final))
            incoming = {r["id"]: r for r in found}
            repeated = sorted(set(incoming) & set(cars))
            new = {key: val for key, val in incoming.items() if key not in cars}
            cars.update(new)
            next_url = page_next(soup, final)
            pages.append({
                "page": number, "url": current, "http_status": 200,
                "count": len(found), "new": len(new),
                "duplicate_ids": repeated, "next_url": next_url,
            })
            print(
                f"Page {number}: {len(found)} rows, {len(new)} new, "
                f"{len(repeated)} dupes, total={len(cars)}, next={next_url}",
                flush=True,
            )
            if not incoming:
                reason = "empty_page"
                break
            if next_url is None:
                reason = "end_of_catalog"
                break
            if next_url in seen:
                reason = "url_loop"
                break
            if not new:
                reason = "no_new_car_ids"
                break
            current = next_url
        else:
            reason = "page_limit"
    except Exception as exc:
        reason = "error"
        robots_info["error"] = f"{type(exc).__name__}: {str(exc)[:250]}"
        print("STOP:", robots_info["error"], flush=True)

    complete = reason == "end_of_catalog" and len(cars) > 0
    data = {
        "source": START,
        "captured_at_utc": started,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "complete": complete,
        "finish_reason": reason,
        "robots": robots_info,
        "pages": pages,
        "total_unique": len(cars),
        "cars": sorted(cars.values(), key=lambda c: int(c["id"])),
        "notes": [
            "Only unauthenticated public sale-listing data.",
            "Current price is last displayed price candidate, not checked against detail pages.",
            "The 10% benefit through Ceska sporitelna is not included or verified.",
            "All cars are an instantaneous snapshot, not evidence of their market value.",
        ],
    }
    filename = ARCHIVE if complete else PARTIAL
    filename.parent.mkdir(parents=True, exist_ok=True)
    filename.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    RESULT.write_text(json.dumps({
        "complete": complete, "finish_reason": reason,
        "page_count": len(pages), "total_unique": len(cars),
        "path": str(filename), "robots": robots_info,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"END {reason} | {len(pages)} pages | {len(cars)} unique cars | {filename}", flush=True)


if __name__ == "__main__":
    run()

