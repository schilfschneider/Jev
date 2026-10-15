"""Google-Maps- und Booking.com-Einträge zu einem Datensatz je Betrieb zusammenführen.

Basis sind die Google-Einträge (mit Bundesland und Bezirk laut Google-Adresse). Jeder Booking-Eintrag
wird dem nächstgelegenen Google-Eintrag mit sehr ähnlichem Namen zugeordnet; Booking-Betriebe ohne
Google-Gegenstück werden als eigene Datensätze übernommen (Bundesland dann aus der PLZ).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from rapidfuzz import fuzz

from .booking import BookingHotel
from .match import distance_km, normalize_name
from .places import GoogleHotel


@dataclass
class Hotel:
    id: str
    name: str
    adresse: str = ""
    plz: str = ""
    ort: str = ""
    bezirk: str = ""
    bundesland: str = ""
    lat: float | None = None
    lon: float | None = None
    website: str = ""
    telefon: str = ""
    typ: str = ""
    sterne: float | None = None
    ausstattung: list[str] = field(default_factory=list)
    google_bewertung: float | None = None      # 1–5
    google_anzahl: int = 0
    google_url: str = ""
    booking_bewertung: float | None = None     # 1–10
    booking_anzahl: int = 0
    booking_url: str = ""
    teilnoten: dict[str, float] = field(default_factory=dict)
    # Mitgliedsabgleich
    mitglied_status: str = ""                  # "Mitglied", "kein Mitglied", "prüfen"
    mitglied_name: str = ""
    mitglied_methode: str = ""
    # Scoring (siehe scoring.py)
    score: float | None = None
    score_google: float | None = None
    score_booking: float | None = None
    vertrauen: str = ""
    klasse: str = ""
    rang_gesamt: int | None = None
    rang_bundesland: int | None = None
    perzentil: float | None = None
    abweichung_quellen: float | None = None

    @property
    def ist_mitglied(self) -> bool:
        return self.mitglied_status == "Mitglied"


def bundesland_aus_plz(plz: str) -> str:
    """Näherung über die PLZ-Leitzone. Die Zonen folgen den Postleitbereichen, nicht exakt den
    Landesgrenzen (z. B. 52xx/53xx teils Oberösterreich, 2xxx teils Burgenland); nur als Rückfallwert."""
    if not plz or not plz[:2].isdigit():
        return ""
    z, zz = plz[0], int(plz[:2])
    if z == "1":
        return "Wien"
    if z in "23":
        return "Niederösterreich"
    if z == "4" or zz in (52, 53):
        return "Oberösterreich"
    if z == "5":
        return "Salzburg"
    if zz >= 67 and z == "6":
        return "Vorarlberg"
    if z == "6" or zz == 99:
        return "Tirol"
    if z == "7":
        return "Burgenland"
    if z == "8":
        return "Steiermark"
    if z == "9":
        return "Kärnten"
    return ""


GOOGLE_TYPEN = {
    "lodging": "Unterkunft", "hotel": "Hotel", "resort_hotel": "Resort", "motel": "Motel", "hostel": "Hostel",
    "bed_and_breakfast": "Frühstückspension", "guest_house": "Pension", "inn": "Gasthof", "farmstay": "Bauernhof",
    "campground": "Campingplatz", "cottage": "Ferienhaus", "private_guest_room": "Privatzimmer",
    "extended_stay_hotel": "Apartmenthotel",
}


def from_google(g: GoogleHotel) -> Hotel:
    return Hotel(
        id=f"g:{g.place_id}", name=g.name, adresse=g.adresse, plz=g.plz, ort=g.ort, bezirk=g.bezirk,
        bundesland=g.bundesland, lat=g.lat, lon=g.lon, website=g.website, telefon=g.telefon, typ=GOOGLE_TYPEN.get(g.typ, g.typ),
        ausstattung=list(g.ausstattung), google_bewertung=g.bewertung, google_anzahl=g.anzahl_bewertungen or 0,
        google_url=g.maps_url,
    )


def add_booking(h: Hotel, b: BookingHotel) -> None:
    h.booking_bewertung, h.booking_anzahl, h.booking_url = b.bewertung, b.anzahl_bewertungen, b.url
    h.sterne = b.sterne if b.sterne else h.sterne
    h.teilnoten = dict(b.teilnoten)
    h.ausstattung = sorted(set(h.ausstattung) | set(b.ausstattung))
    if b.typ:
        h.typ = b.typ  # Booking unterscheidet Hotel/Pension/Apartment feiner als Google
    h.plz, h.ort = h.plz or b.plz, h.ort or b.ort


def from_booking(b: BookingHotel) -> Hotel:
    h = Hotel(id=f"b:{b.booking_id}", name=b.name, adresse=b.adresse, plz=b.plz, ort=b.ort,
              bundesland=bundesland_aus_plz(b.plz), lat=b.lat, lon=b.lon)
    add_booking(h, b)
    return h


def same_property(g: GoogleHotel, b: BookingHotel) -> float:
    """Ähnlichkeit 0–100, wenn beide Einträge nahe beieinander liegen, sonst 0."""
    km = distance_km(g.lat, g.lon, b.lat, b.lon)
    if km is None:
        if not (g.plz and g.plz == b.plz):
            return 0
        km = 0.3  # gleiche PLZ ohne Koordinaten: wie mittlere Entfernung behandeln
    if km > 0.5:
        return 0
    name = fuzz.token_sort_ratio(normalize_name(g.name), normalize_name(b.name))
    # Sehr nah (< 100 m) genügt ein ähnlicher Name, weiter weg muss er nahezu gleich sein.
    need = 75 if km <= 0.1 else 88
    return name if name >= need else 0


def merge(google: list[GoogleHotel], booking: list[BookingHotel]) -> list[Hotel]:
    hotels = {g.place_id: from_google(g) for g in google}
    # Grobes Raster (~1 km) statt Vergleich jeder mit jedem.
    grid: dict[tuple[int, int], list[GoogleHotel]] = {}
    for g in google:
        grid.setdefault((int(g.lat * 100), int(g.lon * 100)), []).append(g)
    taken: set[str] = set()
    extra = []
    for b in booking:
        best, best_score = None, 0.0
        if b.lat is not None and b.lon is not None:
            cy, cx = int(b.lat * 100), int(b.lon * 100)
            near = [g for dy in (-1, 0, 1) for dx in (-1, 0, 1) for g in grid.get((cy + dy, cx + dx), [])]
        else:
            near = [g for g in google if g.plz and g.plz == b.plz]
        for g in near:
            if g.place_id in taken:
                continue
            s = same_property(g, b)
            if s > best_score:
                best, best_score = g, s
        if best:
            taken.add(best.place_id)
            add_booking(hotels[best.place_id], b)
        else:
            extra.append(from_booking(b))
    return list(hotels.values()) + extra


def save(hotels: list[Hotel], path: Path) -> None:
    path.write_text(json.dumps([asdict(h) for h in hotels], ensure_ascii=False, indent=1))


def load(path: Path) -> list[Hotel]:
    return [Hotel(**d) for d in json.loads(path.read_text())]
