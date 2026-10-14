"""Google-Maps-Betriebe den ÖHV-Mitgliedern zuordnen.

Stufe 1 (Code): Kandidaten über gleiche Website-Domain, gleiche PLZ oder < 2 km Distanz finden
und eindeutige Fälle per Regel entscheiden.
Stufe 2 (TypeSafe/Jev, optional): Für unklare Fälle fragt je Betrieb eine Noul-Frage pro Kandidat,
ob beide Einträge derselbe Hotelbetrieb sind. Ohne API-Key bleiben diese Fälle zur manuellen Prüfung.
"""

from __future__ import annotations

import math
import os
import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urlparse

from rapidfuzz import fuzz

from .members import Member
from .places import GoogleHotel

# Wörter, die in fast jedem Hotelnamen vorkommen und den Namensvergleich verfälschen.
STOPWORDS = {
    "hotel", "hotels", "gasthof", "gasthaus", "pension", "resort", "spa", "wellness", "wellnesshotel",
    "boutique", "boutiquehotel", "alpin", "gmbh", "co", "kg", "og", "e", "u", "und", "the", "das", "der",
    "die", "am", "an", "im", "in", "zum", "zur", "superior", "sterne", "stern", "s", "garni", "family",
}

NOUL_MATCH = 0.85      # ab dieser Wahrscheinlichkeit gilt die Zuordnung als bestätigt
NOUL_NO_MATCH = 0.15   # darunter gilt sie als ausgeschlossen; dazwischen manuelle Prüfung


def normalize_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name.lower())
    s = s.replace("ß", "ss")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\d\s*\*|\*+", " ", s)
    words = re.findall(r"[a-z0-9]+", s)
    return " ".join(w for w in words if w not in STOPWORDS)


def domain(url: str) -> str:
    if not url:
        return ""
    host = urlparse(url if "//" in url else f"//{url}").hostname or ""
    return host.removeprefix("www.").lower()


def distance_km(lat1, lon1, lat2, lon2) -> float | None:
    if None in (lat1, lon1, lat2, lon2):
        return None
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))


@dataclass
class Candidate:
    member: Member
    name_score: float   # Teilmengen-Ähnlichkeit: "Alpenrose" ~ "Alpenrose Apartments" = 100
    name_exact: float   # Ähnlichkeit des ganzen Namens: zusätzliche Wörter senken den Wert
    km: float | None
    same_domain: bool
    same_plz: bool


@dataclass
class Result:
    hotel: GoogleHotel
    status: str  # "Mitglied", "kein Mitglied", "prüfen"
    member: Member | None = None
    methode: str = ""
    wahrscheinlichkeit: float | None = None
    kandidaten: list[Candidate] = field(default_factory=list)


def candidates(hotel: GoogleHotel, members: list[Member], radius_km: float = 2.0) -> list[Candidate]:
    hname, hdom = normalize_name(hotel.name), domain(hotel.website)
    out = []
    for m in members:
        same_domain = bool(hdom) and hdom == domain(m.website)
        same_plz = bool(hotel.plz) and hotel.plz == m.plz
        km = distance_km(hotel.lat, hotel.lon, m.lat, m.lon)
        if not (same_domain or same_plz or (km is not None and km <= radius_km)):
            continue
        mname = normalize_name(m.name)
        out.append(Candidate(m, fuzz.token_set_ratio(hname, mname), fuzz.token_sort_ratio(hname, mname), km, same_domain, same_plz))
    return sorted(out, key=lambda c: (c.same_domain, c.name_score), reverse=True)[:5]


def decide_by_rules(hotel: GoogleHotel, cands: list[Candidate]) -> Result:
    if not cands:
        return Result(hotel, "kein Mitglied", methode="kein Kandidat in Nähe/PLZ/Domain")
    best = max(cands, key=lambda c: (c.same_domain, c.name_exact))
    near = best.same_plz or (best.km is not None and best.km <= 0.5)
    if best.same_domain:
        return Result(hotel, "Mitglied", best.member, "gleiche Website-Domain", kandidaten=cands)
    if best.name_exact >= 90 and near:
        return Result(hotel, "Mitglied", best.member, f"Name {best.name_exact:.0f} % + Lage", kandidaten=cands)
    if all(c.name_score < 50 for c in cands):
        return Result(hotel, "kein Mitglied", methode="Namen in der Umgebung abweichend", kandidaten=cands)
    return Result(hotel, "prüfen", best.member, "Regeln nicht eindeutig", kandidaten=cands)


def _state(hotel: GoogleHotel, cands: list[Candidate]) -> dict:
    return {
        "google_maps_eintrag": {
            "name": hotel.name, "adresse": hotel.adresse, "website": hotel.website, "telefon": hotel.telefon,
        },
        "kandidaten": [
            {
                "name": c.member.name,
                "adresse": " ".join(x for x in (c.member.strasse, c.member.plz, c.member.ort) if x),
                "website": c.member.website,
                "entfernung_km": None if c.km is None else round(c.km, 2),
            }
            for c in cands
        ],
    }


def judge_with_typesafe(results: list[Result], log=print) -> None:
    """Unklare Fälle mit Jev entscheiden: je Kandidat eine unabhängige Noul-Frage in einem Request."""
    open_cases = [r for r in results if r.status == "prüfen"]
    if not open_cases:
        return
    if not os.environ.get("TYPESAFE_API_KEY", "").strip():
        log(f"{len(open_cases)} unklare Fälle – kein TYPESAFE_API_KEY gesetzt, bleiben zur manuellen Prüfung.")
        return
    from typesafe_sdk import Noul, TypeSafeClient, TypeSafeError

    with TypeSafeClient() as client:
        for i, r in enumerate(open_cases, 1):
            questions = {
                f"k{j}": Noul(
                    instructions=(
                        f"Do `google_maps_eintrag` and `kandidaten[{j}]` describe the same hotel business "
                        "(the same property under the same operation), judging by name, address and website? "
                        "A different hotel in the same village, a sister property of the same owner, or a "
                        "restaurant/apartment house that only shares a name part is not the same business."
                    ),
                    criteria={
                        "true": "Same hotel business; differences are only spelling, legal-form suffixes, star ratings or formatting.",
                        "false": "A different business, or the entries cannot be the same property.",
                    },
                )
                for j in range(len(r.kandidaten))
            }
            try:
                answer = client.system_one(_state(r.hotel, r.kandidaten), questions)
            except TypeSafeError as e:
                log(f"  TypeSafe-Fehler bei {r.hotel.name}: {e}")
                continue
            probs = [answer.nouls[f"k{j}"].noul for j in range(len(r.kandidaten))]
            j = max(range(len(probs)), key=probs.__getitem__)
            r.wahrscheinlichkeit = probs[j]
            if probs[j] >= NOUL_MATCH and sum(p >= NOUL_MATCH for p in probs) == 1:
                r.status, r.member, r.methode = "Mitglied", r.kandidaten[j].member, "Jev bestätigt"
            elif max(probs) <= NOUL_NO_MATCH:
                r.status, r.member, r.methode = "kein Mitglied", None, "Jev: kein Kandidat passt"
            else:
                r.member, r.methode = r.kandidaten[j].member, "Jev unsicher"
            if i % 25 == 0:
                log(f"  {i}/{len(open_cases)} unklare Fälle bewertet")


def match_all(hotels: list[GoogleHotel], members: list[Member], use_typesafe: bool = True, log=print) -> list[Result]:
    results = [decide_by_rules(h, candidates(h, members)) for h in hotels]
    if use_typesafe:
        judge_with_typesafe(results, log)
    return results
