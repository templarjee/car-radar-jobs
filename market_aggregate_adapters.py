"""Public model-year aggregate parser; no other source adapters."""
from __future__ import annotations

from dataclasses import dataclass, asdict, replace

from datetime import date

from html import unescape

from urllib.parse import urlparse

import re

from bs4 import BeautifulSoup

NUMBER = r"(\d(?:[\d \u00a0\u202f]{0,15}\d)?)"

DATE = r"(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})"

class SourceParseError(ValueError):
    pass

class SourceZeroResults(SourceParseError):
    """An identified, dated source explicitly reports zero offers."""

def text_of(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for elem in soup(["script", "style", "noscript", "svg"]):
        elem.decompose()
    return " ".join(soup.stripped_strings).replace("\u00a0", " ").replace("\u202f", " ")

def czk(raw: str) -> int:
    digits = re.sub(r"\D", "", raw)
    if not digits:
        raise SourceParseError("Missing CZK amount")
    amount = int(digits)
    if amount < 10_000 or amount > 20_000_000:
        raise SourceParseError("Out-of-range market amount")
    return amount

def date_from(groups) -> date:
    day, month, year = (int(x) for x in groups)
    return date(year, month, day)

@dataclass(frozen=True)
class AggregateStat:
    provider: str
    url: str
    brand: str
    model: str
    coverage: str          # model_year | motor_multi_year | ambiguous_fuel_motor_year
    year: int | None
    first_year: int | None
    last_year: int | None
    motor_kw: int | None
    engine_liters: float | None
    powertrain: str | None  # HEV | PHEV | gasoline | unknown_hybrid | None
    drive: str | None
    sample_n: int | None
    metric: str
    central_czk: int
    p25_czk: int | None
    p75_czk: int | None
    underlying_date: str | None
    notes: str

    def as_dict(self):
        return asdict(self)

def _assert_source(url: str, expected_host: str, path_regex: str):
    p = urlparse(url)
    if p.scheme != "https" or p.hostname != expected_host or not re.fullmatch(path_regex, p.path):
        raise SourceParseError("Source URL not on explicit host/path allowlist")

def parse_autohledac_year(html: str, url: str) -> AggregateStat:
    _assert_source(url, "autohledac.cz",
                   r"/znacky/([a-z][a-z0-9-]{1,23})/([a-z0-9][a-z0-9-]{1,39})/(20\d{2})/?")
    p = urlparse(url).path.strip("/").split("/")
    brand, model, year = p[1], p[2], int(p[3])
    text = text_of(html)
    shown_brand = r"(?:Škoda|Skoda)" if brand=="skoda" else re.escape(brand)
    # A dynamic cohort is only accepted when BOTH title and dated body name the
    # exact requested brand, model and year; a 404/captcha cannot pass.
    # URL identity and display spelling differ for these documented names only.
    # Both exact header and dated body still have to match the same year/model.
    aliases = {("kia", "ceed"): r"Cee['’´]?d",
               ("hyundai", "santa-fe"): r"Santa\s+Fe"}
    exact_model = aliases.get((brand, model), re.escape(model))
    header = re.search(
        rf"(?i)\b{shown_brand}\s+{exact_model}\s+{year}\s*:\s*cena\s+a\s+bazar\b", text)
    if not header:
        # A rearranged title or challenge page must be a hard failure.
        raise SourceParseError("Missing exact brand/model/year title")
    empty = re.search(
        rf"K\s*{DATE}\s*je\s+v\s+české\s+inzerci\s+0\s+nabídek\s+"
        rf"{shown_brand}\s+{exact_model}\s+{year}\s+z\s+\d+\s+inzertních\s+serverů", text, re.I)
    if empty:
        date_from(empty.groups()[:3])
        raise SourceZeroResults("Dated exact model-year statement reports zero offers")
    expr = (
        rf"K\s*{DATE}\s*je\s+v\s+české\s+inzerci\s+{NUMBER}\s+nabídek\s+"
        rf"{shown_brand}\s+{exact_model}\s+{year}\s+z\s+{NUMBER}\s+inzertních\s+serverů\.\s+"
        rf"Mediánová\s+cena\s+je\s+{NUMBER}\s*Kč"
    )
    m = re.search(expr, text, re.I)
    if not m:
        raise SourceParseError("Missing dated model-year median/count statement")
    source_date = date_from(m.groups()[0:3]).isoformat()
    count, sites = int(czk_count(m.group(4))), int(czk_count(m.group(5)))
    price = czk(m.group(6))
    if count < 1 or sites < 1 or sites > 100:
        raise SourceParseError("Invalid number of offers/sites")
    return AggregateStat("AutoHledac",url,brand,model,"model_year",year,None,None,None,None,None,
                         None,count,"median",price,None,None,source_date,
                         "Model/year pooled across engines, drivetrain, mileage and trim. May contain duplicates across providers.")

def czk_count(raw: str) -> int:
    return int(re.sub(r"\D", "", raw))
