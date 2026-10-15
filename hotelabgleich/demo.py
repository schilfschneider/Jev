"""Erfundener Beispieldatensatz, um Abgleich, Scoring und Dashboard ohne API-Zugänge auszuprobieren.

Betriebsnamen sind aus Silben zusammengesetzte Fantasienamen, Websites enden auf ``.example``; Orte und
Bundesländer sind echt, Bewertungen und Mitgliedschaften zufällig erzeugt. Die Ergebnisse sagen nichts über reale Betriebe aus.
"""

from __future__ import annotations

import random

from .booking import BookingHotel
from .members import Member
from .places import GoogleHotel

ORTE = {
    "Wien": [("Wien", "1010", 48.208, 16.373)],
    "Niederösterreich": [("Baden", "2500", 48.006, 16.234), ("Krems an der Donau", "3500", 48.410, 15.600), ("Semmering", "2680", 47.633, 15.830)],
    "Oberösterreich": [("Linz", "4020", 48.306, 14.286), ("Bad Ischl", "4820", 47.711, 13.620), ("St. Wolfgang im Salzkammergut", "5360", 47.739, 13.448)],
    "Salzburg": [("Salzburg", "5020", 47.800, 13.045), ("Zell am See", "5700", 47.325, 12.795), ("Bad Gastein", "5640", 47.115, 13.134), ("Saalbach", "5753", 47.390, 12.637)],
    "Tirol": [("Innsbruck", "6020", 47.269, 11.404), ("Kitzbühel", "6370", 47.446, 12.392), ("Sölden", "6450", 46.966, 11.007), ("Mayrhofen", "6290", 47.167, 11.865), ("Seefeld in Tirol", "6100", 47.330, 11.190)],
    "Vorarlberg": [("Bregenz", "6900", 47.503, 9.747), ("Lech", "6764", 47.208, 10.142)],
    "Kärnten": [("Velden am Wörthersee", "9220", 46.613, 14.040), ("Villach", "9500", 46.610, 13.850), ("Bad Kleinkirchheim", "9546", 46.810, 13.800)],
    "Steiermark": [("Graz", "8010", 47.070, 15.440), ("Schladming", "8970", 47.394, 13.687), ("Bad Waltersdorf", "8271", 47.170, 16.000)],
    "Burgenland": [("Bad Tatzmannsdorf", "7431", 47.330, 16.230), ("Rust", "7071", 47.800, 16.670), ("Podersdorf am See", "7141", 47.850, 16.840)],
}
SILBEN = (["Al", "Ber", "Kor", "Lin", "Mar", "Sel", "Tan", "Wol", "Rie", "Gun", "Hal", "Fen", "Quir", "Zel"],
          ["ma", "ve", "ro", "ti", "ka", "lu", "ne", "so", "", ""],
          ["dor", "ling", "bach", "stein", "hof", "au", "eck", "horn", "see", "wald", "berg", "tal"])


def fantasy_name(rnd: random.Random, used: set[str]) -> str:
    while True:
        name = "".join(rnd.choice(part) for part in SILBEN)
        if name not in used:
            used.add(name)
            return name
TYPEN = ["Hotel", "Hotel", "Hotel", "Pension", "Apartment", "Gasthof"]
AUSSTATTUNG = ["Spa", "Pool", "Restaurant", "Fitnesscenter", "Familienzimmer", "Ladestation E-Auto", "Tagungsraum",
               "Skiraum", "Sauna", "Bar", "Shuttle", "Garten"]


def generate(n: int = 600, seed: int = 7) -> tuple[list[GoogleHotel], list[BookingHotel], list[Member]]:
    rnd = random.Random(seed)
    google, booking, members = [], [], []
    lands = list(ORTE)
    used: set[str] = set()
    weights = [18, 10, 11, 20, 24, 6, 9, 12, 4]  # grob nach Bettenangebot gewichtet, nur für die Demo
    for i in range(1, n + 1):
        land = rnd.choices(lands, weights)[0]
        ort, plz, lat, lon = rnd.choice(ORTE[land])
        lat, lon = lat + rnd.uniform(-0.02, 0.02), lon + rnd.uniform(-0.03, 0.03)
        typ = rnd.choice(TYPEN)
        sterne = rnd.choices([None, 2, 3, 4, 5], [10, 8, 40, 33, 9])[0] if typ in ("Hotel", "Gasthof") else rnd.choice([None, 2, 3])
        size = rnd.lognormvariate(5.3 + 0.35 * (sterne or 2.5) - 1.0, 0.9)
        member = rnd.random() < (0.12 + 0.07 * (sterne or 2))
        quality = rnd.gauss(0, 1) + 0.25 * ((sterne or 3) - 3) + (0.1 if member else 0)
        # „Apartment“ ist im Abgleich bewusst kein Füllwort; als gemeinsames Namenswort würde es jede
        # Ferienwohnung in der Nähe zum Kandidaten machen.
        prefix = "" if typ == "Apartment" else f"{typ} "
        name = f"{prefix}{fantasy_name(rnd, used)} {fantasy_name(rnd, used)}"
        site = f"https://www.demo-{i:03d}.example"
        amen = sorted(rnd.sample(AUSSTATTUNG, rnd.randint(1, 3 + int(sterne or 1))))
        on_google, on_booking = rnd.random() < 0.9, rnd.random() < 0.8
        if on_google:
            google.append(GoogleHotel(
                place_id=f"demo{i}", name=name, adresse=f"Demoweg {i}, {plz} {ort}", plz=plz, ort=ort, bezirk="",
                bundesland=land, lat=lat, lon=lon, website=site, telefon="", typ="lodging", status="OPERATIONAL",
                bewertung=round(min(5, max(2.5, 4.35 + 0.3 * quality + rnd.gauss(0, 0.12))), 1),
                anzahl_bewertungen=int(size * rnd.uniform(0.5, 1.5)), maps_url="",
                ausstattung=[a for a in ("Frühstück", "Parkplatz", "Hunde erlaubt") if rnd.random() < 0.5],
            ))
        if on_booking:
            booking.append(BookingHotel(
                booking_id=str(i), name=f"{name} ****" if sterne == 4 else name,
                adresse=f"Demoweg {i}", plz=plz, ort=ort, lat=lat + rnd.uniform(-0.0003, 0.0003), lon=lon,
                sterne=sterne, bewertung=round(min(10, max(5.5, 8.6 + 0.55 * quality + rnd.gauss(0, 0.2))), 1),
                anzahl_bewertungen=int(size * rnd.uniform(0.8, 2.5)), typ=typ, ausstattung=amen,
                teilnoten={k: round(min(10, max(5, 8.6 + 0.5 * quality + rnd.gauss(0, 0.35))), 1)
                           for k in ("Sauberkeit", "Personal", "Lage", "Preis-Leistung")},
            ))
        if member:
            members.append(Member(name=f"{name} GmbH", plz=plz, ort=ort, website=site if rnd.random() < 0.7 else "",
                                  lat=lat, lon=lon, quelle="demo"))
    return google, booking, members
