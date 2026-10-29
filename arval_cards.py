"""Parse public listing cards; no network or operational diagnostics."""
from __future__ import annotations

import re
import urllib.parse


START_URL = "https://www.arvalclub.cz/nabidka-vozu/prodej/?"
HOST = "www.arvalclub.cz"
CAR_PATH = re.compile(r"^/cz/[^/]+/[^/]+/(\d+)/?$")
PRICE_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[\s\u00a0\u202f]\d{3})+|\d{4,8})\s*Kč")
KM_RE = re.compile(r"(\d{1,3}(?:[\s\u00a0\u202f]\d{3})+|\d{1,6})\s*km\b", re.I)
DATE_RE = re.compile(r"v\s+provozu\s+od\s*:?\s*(\d{2}/\d{4})", re.I)


def car_records(soup, base_url):
    """One record per stable ID, with full details (no first-12 truncation)."""
    found = {}
    for link in soup.select("a[href]"):
        url = urllib.parse.urljoin(base_url, link.get("href", ""))
        match = CAR_PATH.fullmatch(urllib.parse.urlparse(url).path)
        if not match:
            continue
        car_id = match.group(1)
        if car_id in found:
            continue
        target = link.parent
        for _ in range(10):
            if not target or target.name in ("html", "body"):
                break
            heading = target.find(["h2", "h3"])
            content = target.get_text(" ", strip=True)
            prices = PRICE_RE.findall(content)
            if heading and prices and len(content) < 1800:
                km = KM_RE.search(content)
                first_service = DATE_RE.search(content)
                found[car_id] = {
                    "id": car_id,
                    "title": heading.get_text(" ", strip=True),
                    "price_czk_candidates": list(dict.fromkeys(
                        int(re.sub(r"\D", "", price)) for price in prices
                    ))[:3],
                    "mileage_km": int(re.sub(r"\D", "", km.group(1))) if km else None,
                    "in_service_since": first_service.group(1) if first_service else None,
                    "url": url,
                }
                break
            target = target.parent
    return list(found.values())

