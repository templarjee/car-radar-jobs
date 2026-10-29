"""Conservative, deterministic canonical engine identification from Arval cards.

Never alter source labels. Only the displayed power is known; hybrid total vs.
combustion output is not assumed. Version every backfill.
"""
from __future__ import annotations

import re
from decimal import Decimal

# Longer/specific families before shorter generic tokens; allow no separator
# between engine displacement and family (e.g. 1.0TSI / 1.6CRDi).
FAMILIES = (
    ("E-TSI", r"e-?TSI", "petrol"),
    ("TFSI", r"TFSI", "petrol"),
    ("TSI", r"TSI", "petrol"),
    ("TDI", r"TDI", "diesel"),
    ("T-GDI", r"T-?GDI", "petrol"),
    ("CRDI", r"CRDI", "diesel"),
    ("GDI", r"GDI", "petrol"),
    ("BLUEHDI", r"BLUEHDI", "diesel"),
    ("HDI", r"HDI", "diesel"),
    ("DCI", r"DCI", "diesel"),
    ("EcoBoost", r"ECOBOOST", "petrol"),
    ("PURETECH", r"PURETECH", "petrol"),
    ("TCE", r"TCE", "petrol"),
    ("MPI", r"MPI", "petrol"),
    ("CDTI", r"CDTI", "diesel"),
    ("THP", r"THP", "petrol"),
    ("D-4D", r"D-4D", "diesel"),
    ("MULTIJET", r"MULTIJET", "diesel"),
    ("SKYACTIV-G", r"SKYACTIV-G", "petrol"),
    ("SKYACTIV-D", r"SKYACTIV-D", "diesel"),
    ("SKYACTIV-X", r"SKYACTIV-X", "petrol"),
)
FAMILY_PATTERNS = [
    (label, re.compile(r"(?<![A-Za-z])" + pattern + r"(?![A-Za-z])", re.I), fuel)
    for label, pattern, fuel in FAMILIES
]
CAPACITY = re.compile(r"(?<!\d)([0-5][.,]\d{1,2})\s*(?=[A-Za-z]|(?:\s+[A-Za-z])|$)")
HYBRID_TYPES = {"HEV", "PHEV", "MHEV", "hybrid_unspecified"}
FUEL_CLASSES = {
    "benzín": "petrol",
    "nafta": "diesel",
    "elektromobil": "electric",
}


def extract_engine(variant: str | None, power_kw: int | None,
                   powertrain: str | None, fuel_raw: str | None) -> dict:
    original = (variant or "").strip()
    capacity = CAPACITY.search(original)
    litres = float(Decimal(capacity[1].replace(",", "."))) if capacity else None
    # Specific tokens contain generic suffixes (T-GDI/GDI, e-TSI/TSI).
    # Ignore a suffix only at the SAME occurrence; a separate TSI + TDI
    # still represents a real conflict and must never acquire an exact key.
    matches = [(name, fuel, m.span()) for name, regex, fuel in FAMILY_PATTERNS
               for m in regex.finditer(original)]
    families = [(name, fuel) for name, fuel, (start, end) in matches
                if not any(a <= start and end <= b and (a, b) != (start, end)
                           for _, _, (a, b) in matches)]
    distinct = list(dict.fromkeys(name for name, _ in families))
    family = distinct[0] if len(distinct) == 1 else None
    family_fuel = next((fuel for name, fuel in families if name == family), None)
    conflicts = []
    if len(distinct) > 1:
        conflicts.append("multiple_engine_families")
    advertised_fuel = FUEL_CLASSES.get((fuel_raw or "").strip().casefold())
    if family_fuel and advertised_fuel and family_fuel != advertised_fuel:
        conflicts.append("fuel_label_conflicts_engine_family")
    # Legacy catalog badges show kW, but for hybrids the badge may show
    # power of a motor or the whole system. Do not guess which.
    hybrid = powertrain in HYBRID_TYPES
    scope = "hybrid_scope_unverified" if hybrid else "unspecified"
    valid_kw = power_kw if type(power_kw) is int and 1 <= power_kw <= 1000 else None

    # A canonical key requires distinctive engine family + displacement + badge.
    # Avoid equating an unknown engine with a concrete TSI/TDI or hybrid class.
    label_parts = []
    if litres is not None:
        label_parts.append(f"{litres:.1f}")
    if family:
        label_parts.append(family)
    elif hybrid and powertrain != "hybrid_unspecified":
        label_parts.append(powertrain)
    if valid_kw is not None:
        label_parts.append(f"{valid_kw} kW")
    readable = " ".join(label_parts) if len(label_parts) >= 2 else None

    suffix = powertrain if hybrid and powertrain != "hybrid_unspecified" else "unspecified"
    key = (f"{litres:g}|{family}|{valid_kw}|{suffix}"
           if litres is not None and family and valid_kw and not conflicts
           else None)
    if conflicts:
        confidence = "conflict"
    elif family and litres is not None and valid_kw is not None:
        confidence = "medium" if hybrid else "high"
    elif len(label_parts) >= 2 and (family or hybrid):
        confidence = "medium" if not hybrid else "low"
    elif valid_kw is not None or litres is not None or family is not None:
        confidence = "low"
    else:
        confidence = "unknown"
    return {
        "engine_displacement_l": litres,
        "engine_family": family,
        "engine_variant_normalized": readable,
        "engine_variant_key": key,
        "engine_confidence": confidence,
        "engine_power_scope": scope,
        "engine_evidence": {
            "source": "catalog_variant_and_displayed_power",
            "variant_raw": original,
            "displayed_power_kw": valid_kw,
            "fuel_raw": fuel_raw,
            "powertrain_inferred": powertrain,
            "conflicts": conflicts,
        },
    }


