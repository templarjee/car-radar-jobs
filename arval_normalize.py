#!/usr/bin/env python3
"""Deterministic Arval public-card normalizer. Keep source fields untouched."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
from urllib.parse import urlparse
from arval_engine import extract_engine

LINK = re.compile(r"^/cz/(?P<brand>[^/]+)/(?P<model>[^/]+)/(?P<id>\d+)/?$")
MILEAGE = re.compile(r"(\d{1,3}(?:[\s\u00a0\u202f]\d{3})+|\d{1,6})\s*km\s*\|\s*v provozu od:\s*(\d{2}/\d{4})", re.I)
POWER = re.compile(r"(\d{2,3})\s*kW\s*\((\d{2,3})\s*PS\)", re.I)
GEARBOX = re.compile(r"Převodovka\s+(automatick\w*|manuáln\w*)", re.I)
FUEL = re.compile(r"Detail vozu\s+(Benzín|Nafta|Elektromobil|Hybridní vozidlo|LPG|CNG)", re.I)
DISCOUNT = re.compile(r"\bSleva\s+(\d{1,2})\s*%", re.I)
AWD = re.compile(r"\b(?:AWD|4WD|4x4|4MOTION|quattro|xDrive)\b", re.I)

def normalize(car, captured_at_utc=None):
    raw = car.get("listing_text") or ""
    link = LINK.fullmatch(urlparse(car.get("url") or "").path)
    if not link or link["id"] != str(car.get("id")):
        raise ValueError("Invalid URL/ID in car record: " + str(car.get("id")))
    title = (car.get("title") or "").strip()
    km_match = MILEAGE.search(raw)
    variant = None
    if km_match:
        prefix = raw[:km_match.start()].strip()
        if title:
            offset = prefix.find(title)
            if offset >= 0:
                variant = prefix[offset + len(title):].strip() or None
        else:
            # Some Arval records have a missing make/model heading. Preserve
            # the visible variant as an honest fallback; never guess the make.
            prefix = re.sub(r"^(?:Sleva \d{1,2} %\s*)?(?:Málo najeto\s*)?(?:Brzy bude pryč\s*)?(?:Operativní leasing\s*)?", "", prefix).strip()
            if not prefix:
                raise ValueError("No recoverable vehicle title for ID " + str(car.get("id")))
            title = prefix
    if not title:
        raise ValueError("No vehicle title for ID " + str(car.get("id")))
    p = POWER.search(raw)
    g = GEARBOX.search(raw)
    f = FUEL.search(raw)
    discount = DISCOUNT.search(raw)
    candidates = car.get("price_czk_candidates") or []
    if not candidates or any(type(n) is not int or n <= 0 for n in candidates):
        raise ValueError("No valid prices for ID " + str(car.get("id")))
    offer = "operating_lease" if re.search(r"Operativní leasing|Kč\s*[/]?měsíčně", raw, re.I) else "sale"
    name = ((variant or "") + " " + (f.group(1) if f else "")).upper()
    if re.search(r"(?:^|[^A-Z])(?:PHEV|PLUG[ -]?IN)\b", name):
        powertrain, confidence = "PHEV", "high"
    elif re.search(r"(?:^|[^A-Z])(?:MHEV|MILD[ -]?HYBRID|M[.]HYB)\b", name):
        powertrain, confidence = "MHEV", "high"
    elif re.search(r"(?:^|[^A-Z])(?:HEV|HYBRID|HYB)\b", name):
        powertrain, confidence = "HEV", "medium" if re.search(r"(?:^|[^A-Z])HYB\b", name) else "high"
    elif f and f.group(1).lower() == "elektromobil":
        powertrain, confidence = "EV", "high"
    elif f and f.group(1).lower() == "hybridní vozidlo":
        powertrain, confidence = "hybrid_unspecified", "low"
    else:
        powertrain, confidence = "unknown", "unknown"
    engine_attributes = extract_engine(variant, int(p[1]) if p else None, powertrain, f.group(1) if f else None)
    return {
        "arval_id": str(car["id"]),
        "source": "arvalclub_public_catalog",
        "source_url": car["url"],
        "captured_at_utc": captured_at_utc,
        "brand_slug": link["brand"],
        "model_slug": link["model"],
        "title": title,
        "variant_raw": variant,
        "engine_liter_hint": engine_attributes["engine_displacement_l"],
        **engine_attributes,
        "powertrain": powertrain,
        "powertrain_confidence": confidence,
        "fuel_raw": f.group(1) if f else None,
        "gearbox": ("automatic" if g[1].lower().startswith("automat") else "manual") if g else "unknown",
        "drive": "AWD" if variant and AWD.search(variant) else "unknown",
        "power_kw_raw": int(p[1]) if p else None,
        "power_ps_raw": int(p[2]) if p else None,
        "mileage_km": car.get("mileage_km"),
        "first_in_service_month": car.get("in_service_since"),
        "offer_type": offer,
        "amount_czk": candidates[-1],
        "amount_unit": "CZK_per_month" if offer == "operating_lease" else "CZK_purchase",
        "previous_displayed_amount_czk": candidates[-2] if len(candidates) > 1 else None,
        "advertised_discount_pct": int(discount[1]) if discount else None,
        "flags": {
            "low_mileage_badge": "Málo najeto" in raw,
            "leaving_soon_badge": "Brzy bude pryč" in raw,
        },
        "raw_price_candidates": list(candidates),
        "listing_text": raw,
    }

def normalize_snapshot(data):
    cars = data.get("cars")
    if not data.get("complete") or not isinstance(cars, list):
        raise ValueError("Refusing to normalize incomplete catalog")
    records = [normalize(c, data.get("captured_at_utc")) for c in cars]
    if len({v["arval_id"] for v in records}) != len(records):
        raise ValueError("Duplicate Arval IDs")
    return {
        "source_snapshot_time": data.get("captured_at_utc"),
        "normalizer_version": 3,
        "total": len(records),
        "notes": ["Preserve source raw data; inferred fields may remain unknown.",
                  "Raw fuel label can conflict with inferred hybrid engine.",
                  "Displayed asking price is not a guaranteed transaction price."],
        "vehicles": records,
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("snapshot", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    data = json.loads(args.snapshot.read_text(encoding="utf-8"))
    normalized = normalize_snapshot(data)
    output = args.output or args.snapshot.with_name(args.snapshot.stem + "-normalized.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    from collections import Counter
    for key in ("offer_type", "powertrain", "gearbox", "drive"):
        print(key + ": " + str(dict(Counter(v[key] for v in normalized["vehicles"]))), flush=True)
    print(f"Normalized {normalized['total']} records to {output}", flush=True)

if __name__ == "__main__":
    main()


