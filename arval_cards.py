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


def pending_price_records(soup, base_url):
    """Recognize explicit source placeholders, never arbitrary missing prices."""
    found = {}
    for card in soup.select('.cars-list > div > .content-container'):
        price = card.select_one('.prices .price')
        heading = card.find(['h2', 'h3'])
        content = card.get_text(' ', strip=True)
        km = KM_RE.search(content)
        if (not price or price.get_text(' ', strip=True) != 'Cenu připravujeme'
                or not heading or not km or PRICE_RE.search(content)):
            continue
        urls = {}
        for link in card.select('a[href]'):
            url = urllib.parse.urljoin(base_url, link['href'])
            parsed = urllib.parse.urlparse(url)
            match = CAR_PATH.fullmatch(parsed.path)
            if parsed.scheme == 'https' and parsed.hostname == HOST and match:
                # Strip harmless tracking parameters; downstream evidence needs
                # a canonical, stable vehicle URL for the same Arval ID.
                urls[match[1]] = urllib.parse.urlunparse(
                    (parsed.scheme, parsed.netloc, parsed.path.rstrip('/') + '/', '', '', '')
                )
        if len(urls) == 1:
            car_id, url = next(iter(urls.items()))
            found[car_id] = {'id': car_id, 'url': url,
                             'title': heading.get_text(' ', strip=True),
                             'mileage_km': int(re.sub(r'\D', '', km[1])),
                             'price_status': 'pending'}
    return list(found.values())


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
        # Never climb out of a card into neighbouring listing prices:
        # this could invent a price for a "Cenu pripravujeme" vehicle.
        card = link.find_parent(class_='content-container')
        target = card if card is not None else link.parent
        for _ in range(1 if card is not None else 10):
            if not target or target.name in ("html", "body"):
                break
            if target.get('class') and 'cars-list' in target.get('class', []):
                break
            explicit = target.select_one('.prices .price')
            if explicit and explicit.get_text(' ', strip=True) == 'Cenu připravujeme':
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

