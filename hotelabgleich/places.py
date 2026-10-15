"""Hotelbetriebe eines Bundeslands über die Google Places API (New) erfassen.

Die Text Search liefert höchstens 60 Treffer je Abfrage (3 Seiten à 20). Deshalb wird das
Bundesland als Rechteck in Kacheln zerlegt; eine Kachel mit vollen 60 Treffern wird geviertelt,
bis jede Kachel vollständig abgefragt ist. Treffer außerhalb des Bundeslands werden anhand der
Adresskomponente ``administrative_area_level_1`` verworfen.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
API_KEY_ENV = "GOOGLE_MAPS_API_KEY"
MAX_RESULTS_PER_QUERY = 60

# Rechteck (Süd, West, Nord, Ost), großzügig um die Landesgrenze gelegt. Überlappungen sind gewollt:
# Treffer werden über die Google-Adresse (administrative_area_level_1) dem Bundesland zugeordnet.
BUNDESLAENDER = {
    "Burgenland": (46.83, 15.99, 48.12, 17.17),
    "Kärnten": (46.37, 12.65, 47.13, 15.07),
    "Niederösterreich": (47.42, 14.45, 49.02, 17.07),
    "Oberösterreich": (47.46, 12.73, 48.78, 14.99),
    "Salzburg": (46.93, 12.07, 48.06, 14.00),
    "Steiermark": (46.61, 13.56, 47.83, 16.17),
    "Tirol": (46.62, 10.10, 47.75, 12.97),
    "Vorarlberg": (46.84, 9.53, 47.60, 10.24),
    "Wien": (48.11, 16.18, 48.33, 16.58),
}

# Ausstattungsmerkmale, die die Places API (New) für Beherbergungsbetriebe liefern kann.
# Diese Felder fallen in die höchste Preisstufe (Enterprise + Atmosphere).
AMENITY_FIELDS = ["allowsDogs", "goodForChildren", "servesBreakfast", "parkingOptions", "accessibilityOptions"]
AMENITY_LABELS = {
    "allowsDogs": "Hunde erlaubt",
    "goodForChildren": "Kinderfreundlich",
    "servesBreakfast": "Frühstück",
    "parkingOptions": "Parkplatz",
    "accessibilityOptions": "Barrierefrei",
}

FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.addressComponents",
        "places.location",
        "places.websiteUri",
        "places.nationalPhoneNumber",
        "places.rating",
        "places.userRatingCount",
        "places.primaryType",
        "places.types",
        "places.businessStatus",
        "places.googleMapsUri",
        *(f"places.{f}" for f in AMENITY_FIELDS),
        "nextPageToken",
    ]
)


@dataclass
class GoogleHotel:
    place_id: str
    name: str
    adresse: str
    plz: str
    ort: str
    bezirk: str
    bundesland: str
    lat: float
    lon: float
    website: str
    telefon: str
    bewertung: float | None
    anzahl_bewertungen: int
    typ: str
    status: str
    maps_url: str
    ausstattung: list[str] = field(default_factory=list)

    @classmethod
    def from_api(cls, p: dict) -> "GoogleHotel":
        comps = {t: c for c in p.get("addressComponents", []) for t in c.get("types", [])}

        def comp(kind: str) -> str:
            return comps.get(kind, {}).get("longText", "")

        loc = p.get("location", {})
        return cls(
            place_id=p["id"],
            name=p.get("displayName", {}).get("text", ""),
            adresse=p.get("formattedAddress", ""),
            plz=comp("postal_code"),
            ort=comp("locality") or comp("postal_town"),
            bezirk=comp("administrative_area_level_2"),
            bundesland=comp("administrative_area_level_1"),
            lat=loc.get("latitude", 0.0),
            lon=loc.get("longitude", 0.0),
            website=p.get("websiteUri", ""),
            telefon=p.get("nationalPhoneNumber", ""),
            bewertung=p.get("rating"),
            anzahl_bewertungen=p.get("userRatingCount", 0),
            typ=p.get("primaryType", ""),
            status=p.get("businessStatus", ""),
            maps_url=p.get("googleMapsUri", ""),
            ausstattung=amenities(p),
        )


def amenities(p: dict) -> list[str]:
    out = []
    for f in AMENITY_FIELDS:
        v = p.get(f)
        # parkingOptions/accessibilityOptions sind Objekte mit Einzel-Flags; ein wahres Flag genügt.
        if v is True or (isinstance(v, dict) and any(v.values())):
            out.append(AMENITY_LABELS[f])
    return out


class PlacesClient:
    def __init__(self, api_key: str | None = None, cache_dir: Path = Path("data/cache/places")):
        self.api_key = api_key or os.environ.get(API_KEY_ENV, "").strip()
        if not self.api_key:
            raise SystemExit(f"Kein Google-API-Key: Umgebungsvariable {API_KEY_ENV} setzen.")
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.requests_sent = 0

    def _post(self, body: dict) -> dict:
        key = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:24]
        cached = self.cache_dir / f"{key}.json"
        if cached.exists():
            return json.loads(cached.read_text())
        headers = {"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": FIELD_MASK}
        for attempt in range(5):
            r = requests.post(SEARCH_URL, json=body, headers=headers, timeout=30)
            if r.status_code in (429, 500, 503):
                time.sleep(2**attempt)
                continue
            r.raise_for_status()
            break
        else:
            r.raise_for_status()
        self.requests_sent += 1
        data = r.json()
        cached.write_text(json.dumps(data))
        return data

    def search_rect(self, query: str, rect: tuple[float, float, float, float], included_type: str) -> list[dict]:
        south, west, north, east = rect
        body = {
            "textQuery": query,
            "includedType": included_type,
            "languageCode": "de",
            "regionCode": "at",
            "pageSize": 20,
            "locationRestriction": {
                "rectangle": {
                    "low": {"latitude": south, "longitude": west},
                    "high": {"latitude": north, "longitude": east},
                }
            },
        }
        places: list[dict] = []
        while True:
            data = self._post(body)
            places.extend(data.get("places", []))
            token = data.get("nextPageToken")
            if not token:
                return places
            body = {**body, "pageToken": token}


def split(rect: tuple[float, float, float, float]) -> list[tuple[float, float, float, float]]:
    s, w, n, e = rect
    mlat, mlon = (s + n) / 2, (w + e) / 2
    return [(s, w, mlat, mlon), (s, mlon, mlat, e), (mlat, w, n, mlon), (mlat, mlon, n, e)]


def collect(
    client: PlacesClient,
    bundesland: str,
    query: str = "Hotel",
    included_type: str = "lodging",
    max_depth: int = 7,
    log=print,
) -> list[GoogleHotel]:
    """Alle Treffer im Bundesland sammeln, Kacheln bei Sättigung rekursiv teilen."""
    found: dict[str, dict] = {}
    stack = [(BUNDESLAENDER[bundesland], 0)]
    while stack:
        rect, depth = stack.pop()
        places = client.search_rect(query, rect, included_type)
        for p in places:
            found[p["id"]] = p
        saturated = len(places) >= MAX_RESULTS_PER_QUERY
        log(f"  Kachel Tiefe {depth}: {len(places):>2} Treffer{' → teilen' if saturated and depth < max_depth else ''}")
        if saturated and depth < max_depth:
            stack.extend((r, depth + 1) for r in split(rect))
        elif saturated:
            log("  WARNUNG: maximale Teilungstiefe erreicht, Kachel evtl. unvollständig")
    hotels = [GoogleHotel.from_api(p) for p in found.values()]
    return [h for h in hotels if h.bundesland == bundesland and h.status != "CLOSED_PERMANENTLY"]


def save(hotels: list[GoogleHotel], path: Path) -> None:
    path.write_text(json.dumps([asdict(h) for h in hotels], ensure_ascii=False, indent=1))


def load(path: Path) -> list[GoogleHotel]:
    return [GoogleHotel(**d) for d in json.loads(path.read_text())]
