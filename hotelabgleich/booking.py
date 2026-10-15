"""Booking.com-Unterkünfte in Österreich laden: über die offizielle Demand API oder aus einer CSV.

Die Booking.com-Website selbst wird bewusst nicht ausgelesen: Die Nutzungsbedingungen verbieten
automatisiertes Auslesen, und die Bewertungsdaten sind als Datenbank geschützt. Der rechtssichere
Weg ist die Demand API (Zugang über das Booking.com-Partnerprogramm, Affiliate-ID + API-Token).

Verwendete Endpunkte (Demand API 3.1, https://developers.booking.com/demand/docs):
  POST accommodations/details    Name, Lage, Sterne, Bewertung, Anzahl Bewertungen, Ausstattung
  POST accommodations/constants  Klartext zu Ausstattungs- und Unterkunftstyp-IDs
  POST common/locations/cities   Ortsnamen zu Orts-IDs
  POST accommodations/reviews/scores  Teilnoten (Sauberkeit, Personal …), nur wenn der
                                       Partnervertrag die Reviews-Endpunkte freischaltet

Die Antwortstruktur wurde aus der Dokumentation übernommen, aber nicht gegen einen echten Zugang
getestet; der Parser liest deshalb defensiv. Beim ersten Lauf zuerst gegen die Sandbox prüfen
(``BOOKING_API_BASE=https://demandapi-sandbox.booking.com/3.1/``).
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests

API_BASE_ENV, TOKEN_ENV, AFFILIATE_ENV = "BOOKING_API_BASE", "BOOKING_API_TOKEN", "BOOKING_AFFILIATE_ID"
DEFAULT_BASE = "https://demandapi.booking.com/3.1/"
SUBSCORE_KEYS = {
    "cleanliness": "Sauberkeit", "comfort": "Komfort", "facilities": "Ausstattung", "free_wifi": "WLAN",
    "location": "Lage", "staff": "Personal", "value_for_money": "Preis-Leistung",
}


@dataclass
class BookingHotel:
    booking_id: str
    name: str
    adresse: str = ""
    plz: str = ""
    ort: str = ""
    lat: float | None = None
    lon: float | None = None
    sterne: float | None = None
    bewertung: float | None = None       # Booking-Skala 1–10
    anzahl_bewertungen: int = 0
    typ: str = ""
    ausstattung: list[str] = field(default_factory=list)
    teilnoten: dict[str, float] = field(default_factory=dict)
    url: str = ""


def _text(v, lang: str = "de") -> str:
    """Mehrsprachige Felder kommen als {"de": "...", "en-gb": "..."} oder als einfacher Text."""
    if isinstance(v, dict):
        return str(v.get(lang) or v.get("en-gb") or next(iter(v.values()), ""))
    return "" if v is None else str(v)


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def from_api(item: dict, cities: dict[str, str], facilities: dict[str, str], types: dict[str, str]) -> BookingHotel:
    loc = item.get("location") or {}
    coords = loc.get("coordinates") or {}
    rating = item.get("rating") or {}
    facs = []
    for f in item.get("facilities") or []:
        fid = str(f.get("id") if isinstance(f, dict) else f)
        if fid in facilities:
            facs.append(facilities[fid])
    return BookingHotel(
        booking_id=str(item.get("id", "")),
        name=_text(item.get("name")).strip(),
        adresse=_text(loc.get("address")).strip(),
        plz=str(loc.get("postal_code") or "").strip(),
        ort=cities.get(str(loc.get("city")), ""),
        lat=_num(coords.get("latitude")),
        lon=_num(coords.get("longitude")),
        sterne=_num(rating.get("stars")),
        bewertung=_num(rating.get("review_score")),
        anzahl_bewertungen=int(rating.get("number_of_reviews") or 0),
        typ=types.get(str(item.get("accommodation_type")), ""),
        ausstattung=sorted(set(facs)),
        url=str(item.get("url") or ""),
    )


def parse_subscores(data) -> dict[str, float]:
    """Teilnoten aus beliebig verschachtelter Antwort holen: Schlüssel wie ``cleanliness`` mit Zahl oder {score: …}."""
    found: dict[str, float] = {}

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in SUBSCORE_KEYS:
                    val = _num(v.get("score") if isinstance(v, dict) else v)
                    if val is not None:
                        found.setdefault(SUBSCORE_KEYS[k], val)
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(data)
    return found


class DemandClient:
    def __init__(self, cache_dir: Path = Path("data/cache/booking")):
        self.base = os.environ.get(API_BASE_ENV, DEFAULT_BASE).rstrip("/") + "/"
        self.token = os.environ.get(TOKEN_ENV, "").strip()
        self.affiliate = os.environ.get(AFFILIATE_ENV, "").strip()
        if not (self.token and self.affiliate):
            raise SystemExit(f"Kein Booking.com-Zugang: {TOKEN_ENV} und {AFFILIATE_ENV} setzen (Partnerprogramm).")
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.requests_sent = 0

    def post(self, path: str, body: dict) -> dict:
        key = hashlib.sha256(json.dumps([path, body], sort_keys=True).encode()).hexdigest()[:24]
        cached = self.cache_dir / f"{key}.json"
        if cached.exists():
            return json.loads(cached.read_text())
        headers = {"Authorization": f"Bearer {self.token}", "X-Affiliate-Id": self.affiliate}
        for attempt in range(5):
            r = requests.post(self.base + path, json=body, headers=headers, timeout=60)
            if r.status_code in (429, 500, 503):
                time.sleep(2**attempt)
                continue
            break
        r.raise_for_status()
        self.requests_sent += 1
        data = r.json()
        cached.write_text(json.dumps(data))
        return data

    def paged(self, path: str, body: dict):
        while True:
            data = self.post(path, body)
            yield from data.get("data") or []
            token = data.get("next_page")
            if not token:
                return
            body = {**body, "page": token}


def _id_names(entries) -> dict[str, str]:
    """Konstanten kommen als Liste [{id, name}] oder als Dict {id: {name}}."""
    if isinstance(entries, dict):
        entries = [{"id": k, **(v if isinstance(v, dict) else {"name": v})} for k, v in entries.items()]
    return {str(e.get("id")): _text(e.get("name")) for e in entries or [] if isinstance(e, dict)}


def collect(client: DemandClient, country: str = "at", with_subscores: bool = False, log=print) -> list[BookingHotel]:
    const = client.post("accommodations/constants", {"languages": ["de"]}).get("data") or {}
    facilities = _id_names(const.get("facilities"))
    types = _id_names(const.get("accommodation_types"))
    cities = {str(c.get("id")): _text(c.get("name")) for c in client.paged("common/locations/cities", {"country": country, "languages": ["de"]})}
    log(f"  {len(cities)} Orte, {len(facilities)} Ausstattungsmerkmale")
    body = {"country": country, "extras": ["facilities"], "languages": ["de"], "rows": 100}
    hotels = [from_api(item, cities, facilities, types) for item in client.paged("accommodations/details", body)]
    log(f"  {len(hotels)} Unterkünfte")
    if with_subscores:
        for i in range(0, len(hotels), 100):
            chunk = hotels[i : i + 100]
            data = client.post("accommodations/reviews/scores", {"accommodations": [int(h.booking_id) for h in chunk]})
            by_id = {str(d.get("id")): d for d in data.get("data") or [] if isinstance(d, dict)}
            for h in chunk:
                h.teilnoten = parse_subscores(by_id.get(h.booking_id, {}))
    return hotels


def load_csv(path: Path) -> list[BookingHotel]:
    """CSV mit Spalten name; plz; ort; adresse; lat; lon; sterne; bewertung; anzahl_bewertungen; typ; ausstattung; url.

    ``ausstattung`` als Liste mit ``|`` getrennt (z. B. ``Pool|Spa|Restaurant``). Teilnoten optional als
    Spalten ``sauberkeit``, ``personal``, ``lage``, ``preis-leistung`` … (Booking-Skala 1–10).
    """
    text = path.read_text(encoding="utf-8-sig")
    dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=";,")
    sub_cols = {v.lower(): v for v in SUBSCORE_KEYS.values()}
    out = []
    for i, row in enumerate(csv.DictReader(text.splitlines(), dialect=dialect)):
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        if not row.get("name"):
            continue
        out.append(
            BookingHotel(
                booking_id=row.get("booking_id") or f"csv{i}",
                name=row["name"], adresse=row.get("adresse", ""), plz=row.get("plz", ""), ort=row.get("ort", ""),
                lat=_num(row.get("lat")), lon=_num(row.get("lon")), sterne=_num(row.get("sterne")),
                bewertung=_num(row.get("bewertung")), anzahl_bewertungen=int(_num(row.get("anzahl_bewertungen")) or 0),
                typ=row.get("typ", ""), ausstattung=[a.strip() for a in row.get("ausstattung", "").split("|") if a.strip()],
                teilnoten={label: v for col, label in sub_cols.items() if (v := _num(row.get(col))) is not None},
                url=row.get("url", ""),
            )
        )
    return out


def save(hotels: list[BookingHotel], path: Path) -> None:
    path.write_text(json.dumps([asdict(h) for h in hotels], ensure_ascii=False, indent=1))


def load(path: Path) -> list[BookingHotel]:
    if path.suffix.lower() == ".csv":
        return load_csv(path)
    return [BookingHotel(**d) for d in json.loads(path.read_text())]
