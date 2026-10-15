"""ÖHV-Gästescore: eigenes Rating je Betrieb aus Google- und Booking-Bewertungen, Ranking und Vergleich
ÖHV-Mitglieder vs. Nicht-Mitglieder.

Modell
1. Normieren auf 0–100: Google (Sterne 1–5) → (x − 1) / 4 · 100, Booking (Note 1–10) → (x − 1) / 9 · 100.
2. Glätten (Bayes-Mittel): Wenige Bewertungen sind wenig aussagekräftig. Jede Quelle wird mit
   ``PRIOR_REVIEWS`` fiktiven Durchschnittsbewertungen gemischt: (n · x + m · Ø) / (n + m).
   Ein Haus mit 5,0 aus 3 Google-Bewertungen landet so nahe am Durchschnitt, eines mit 4,8 aus 2.000
   bleibt bei 4,8.
3. Zusammenführen: gewichteter Mittelwert der geglätteten Quellenwerte; Gewicht = Quellengewicht ·
   n / (n + m), d. h. eine Quelle mit vielen Bewertungen zählt mehr.
4. Einstufen: Klasse nach festen Schwellen (vergleichbar über Zeit), dazu Rang und Perzentil.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict

from .merge import Hotel

PRIOR_REVIEWS = 25
SOURCE_WEIGHT = {"google": 0.5, "booking": 0.5}
KLASSEN = [(90, "Exzellent"), (82, "Sehr gut"), (72, "Gut"), (60, "Befriedigend"), (0, "Kritisch")]
VERTRAUEN = [(200, "hoch"), (50, "mittel"), (1, "gering")]
ABWEICHUNG_HINWEIS = 15  # Punkte Unterschied Google vs. Booking, ab dem ein Hinweis erscheint


def norm_google(x: float) -> float:
    return (x - 1) / 4 * 100


def norm_booking(x: float) -> float:
    return (x - 1) / 9 * 100


def _sources(h: Hotel) -> dict[str, tuple[float, int]]:
    out = {}
    if h.google_bewertung and h.google_anzahl > 0:
        out["google"] = (norm_google(h.google_bewertung), h.google_anzahl)
    if h.booking_bewertung and h.booking_anzahl > 0:
        out["booking"] = (norm_booking(h.booking_bewertung), h.booking_anzahl)
    return out


def priors(hotels: list[Hotel]) -> dict[str, float]:
    """Durchschnitt je Quelle über alle Betriebe des Datensatzes (Fallback 80 = Google 4,2 / Booking 8,2)."""
    vals = defaultdict(list)
    for h in hotels:
        for src, (x, _) in _sources(h).items():
            vals[src].append(x)
    return {src: statistics.fmean(vals[src]) if vals[src] else 80.0 for src in SOURCE_WEIGHT}


def score_hotel(h: Hotel, prior: dict[str, float], m: int = PRIOR_REVIEWS) -> None:
    src = _sources(h)
    adj = {s: (n * x + m * prior[s]) / (n + m) for s, (x, n) in src.items()}
    h.score_google, h.score_booking = adj.get("google"), adj.get("booking")
    if not adj:
        h.score, h.vertrauen, h.klasse = None, "", "ohne Bewertungen"
        return
    w = {s: SOURCE_WEIGHT[s] * n / (n + m) for s, (_, n) in src.items()}
    h.score = round(sum(w[s] * adj[s] for s in adj) / sum(w.values()), 1)
    total = sum(n for _, n in src.values())
    h.vertrauen = next(label for limit, label in VERTRAUEN if total >= limit)
    h.klasse = next(label for limit, label in KLASSEN if h.score >= limit)
    h.abweichung_quellen = round(abs(adj["google"] - adj["booking"]), 1) if len(adj) == 2 else None


def score_all(hotels: list[Hotel]) -> list[Hotel]:
    prior = priors(hotels)
    for h in hotels:
        score_hotel(h, prior)
    rank(hotels)
    return hotels


def _sort_key(h: Hotel):
    return (-h.score, -(h.google_anzahl + h.booking_anzahl), h.name)


def rank(hotels: list[Hotel]) -> None:
    scored = sorted((h for h in hotels if h.score is not None), key=_sort_key)
    n = len(scored)
    for i, h in enumerate(scored, 1):
        h.rang_gesamt = i
        h.perzentil = round(100 * (n - i) / (n - 1), 1) if n > 1 else 100.0
    by_land = defaultdict(list)
    for h in scored:
        by_land[h.bundesland].append(h)
    for group in by_land.values():
        for i, h in enumerate(group, 1):
            h.rang_bundesland = i


# --- Vergleich Mitglieder vs. Nicht-Mitglieder --------------------------------------------------


def mann_whitney_p(a: list[float], b: list[float]) -> float | None:
    """Zweiseitiger p-Wert des Mann-Whitney-U-Tests (Normalapproximation mit Bindungskorrektur)."""
    n1, n2 = len(a), len(b)
    if n1 < 3 or n2 < 3:
        return None
    allv = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    ranks, ties, i = [0.0] * len(allv), 0.0, 0
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1][0] == allv[i][0]:
            j += 1
        for k in range(i, j + 1):
            ranks[k] = (i + j) / 2 + 1
        t = j - i + 1
        ties += t**3 - t
        i = j + 1
    r1 = sum(r for r, (_, g) in zip(ranks, allv) if g == 0)
    u = r1 - n1 * (n1 + 1) / 2
    n = n1 + n2
    sigma = math.sqrt(n1 * n2 / 12 * ((n + 1) - ties / (n * (n - 1))))
    if sigma == 0:
        return 1.0
    z = (u - n1 * n2 / 2) / sigma
    return math.erfc(abs(z) / math.sqrt(2))


def _group_stats(members: list[float], others: list[float]) -> dict:
    def s(v):
        return {"n": len(v), "mittel": round(statistics.fmean(v), 1) if v else None,
                "median": round(statistics.median(v), 1) if v else None}

    m, o = s(members), s(others)
    diff = round(m["mittel"] - o["mittel"], 1) if members and others else None
    return {"mitglieder": m, "andere": o, "differenz": diff, "p_wert": mann_whitney_p(members, others)}


def groessenklasse(h: Hotel) -> str:
    """Anzahl Bewertungen als Näherung für die Betriebsgröße (Zimmerzahl liegt nicht vor)."""
    n = h.google_anzahl + h.booking_anzahl
    return "klein (< 200 Bew.)" if n < 200 else "mittel (200–999 Bew.)" if n < 1000 else "groß (≥ 1.000 Bew.)"


def sterne_label(h: Hotel) -> str:
    return f"{int(h.sterne)} Sterne" if h.sterne else "ohne Angabe"


def compare(hotels: list[Hotel]) -> dict:
    """Mitglieder vs. Nicht-Mitglieder: gesamt, je Bundesland/Sterne/Größe und strukturbereinigt.

    Nur Betriebe mit Score und eindeutigem Abgleich ("prüfen" bleibt außen vor).
    """
    pool = [h for h in hotels if h.score is not None and h.mitglied_status in ("Mitglied", "kein Mitglied")]

    def split(group):
        return [h.score for h in group if h.ist_mitglied], [h.score for h in group if not h.ist_mitglied]

    out = {"gesamt": _group_stats(*split(pool))}
    for key, fn in (("bundesland", lambda h: h.bundesland or "(ohne Angabe)"), ("sterne", sterne_label), ("groesse", groessenklasse)):
        groups = defaultdict(list)
        for h in pool:
            groups[fn(h)].append(h)
        out[key] = {k: _group_stats(*split(g)) for k, g in sorted(groups.items())}

    # Strukturbereinigt: Differenz innerhalb gleicher Zellen (Bundesland × Sterne × Größe),
    # gewichtet mit der Zahl der Mitglieder je Zelle. Beantwortet: Schneiden Mitglieder besser ab als
    # vergleichbare Nicht-Mitglieder – nicht nur, weil unter ihnen mehr große 4- und 5-Sterne-Häuser sind?
    cells = defaultdict(list)
    for h in pool:
        cells[(h.bundesland, sterne_label(h), groessenklasse(h))].append(h)
    num = den = 0.0
    for g in cells.values():
        ms, os_ = split(g)
        if ms and os_:
            num += len(ms) * (statistics.fmean(ms) - statistics.fmean(os_))
            den += len(ms)
    out["bereinigt"] = {"differenz": round(num / den, 1) if den else None, "mitglieder_in_vergleich": int(den)}

    scored = sorted(pool, key=_sort_key)
    k = max(1, len(scored) // 10)
    n_m = sum(h.ist_mitglied for h in pool)
    out["anteile"] = {
        "mitglieder_gesamt": round(100 * n_m / len(pool), 1) if pool else None,
        "mitglieder_top10": round(100 * sum(h.ist_mitglied for h in scored[:k]) / k, 1) if pool else None,
        "mitglieder_flop10": round(100 * sum(h.ist_mitglied for h in scored[-k:]) / k, 1) if pool else None,
    }
    klassen = defaultdict(lambda: [0, 0])
    for h in pool:
        klassen[h.klasse][0 if h.ist_mitglied else 1] += 1
    out["klassen"] = {label: {"mitglieder": klassen[label][0], "andere": klassen[label][1]} for _, label in KLASSEN}
    return out
