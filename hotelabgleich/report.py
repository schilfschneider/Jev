"""Excel-Bericht im ÖHV-Design (Arial, ÖHV-Blau als Tabellenkopf)."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .match import NOUL_MATCH, NOUL_NO_MATCH, Result

BLAU, BLAU_HELL, GELB = "007EAB", "DBEDF3", "EDA10A"
HEAD_FONT = Font(name="Arial", bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor=BLAU)
BODY_FONT = Font(name="Arial", size=10)
TITLE_FONT = Font(name="Arial", bold=True, size=16, color=BLAU)
STATUS_FILL = {
    "Mitglied": PatternFill("solid", fgColor=BLAU_HELL),
    "prüfen": PatternFill("solid", fgColor="FCECC4"),
}

COLUMNS = [
    ("Status", 14), ("Betrieb (Google Maps)", 38), ("Bezirk", 16), ("PLZ", 7), ("Ort", 20),
    ("Adresse", 42), ("Website", 32), ("Telefon", 18), ("Google-Bewertung", 10), ("Anzahl Bewertungen", 11),
    ("Typ", 14), ("ÖHV-Mitglied (Treffer)", 36), ("Methode", 26), ("Jev-Wahrscheinlichkeit", 12),
    ("Mitglieds-Quelle", 36), ("Google-Maps-Link", 30),
]


def _row(r: Result) -> list:
    h, m = r.hotel, r.member
    return [
        r.status, h.name, h.bezirk, h.plz, h.ort, h.adresse, h.website, h.telefon, h.bewertung,
        h.anzahl_bewertungen, h.typ, m.name if m else "", r.methode,
        None if r.wahrscheinlichkeit is None else round(r.wahrscheinlichkeit, 3), m.quelle if m else "", h.maps_url,
    ]


def _table(ws, results: list[Result]) -> None:
    for c, (title, width) in enumerate(COLUMNS, 1):
        cell = ws.cell(1, c, title)
        cell.font, cell.fill = HEAD_FONT, HEAD_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(c)].width = width
    for i, r in enumerate(results, 2):
        for c, v in enumerate(_row(r), 1):
            cell = ws.cell(i, c, v)
            cell.font = BODY_FONT
            if r.status in STATUS_FILL:
                cell.fill = STATUS_FILL[r.status]
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions


def write(results: list[Result], members_total: int, bundesland: str, path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Übersicht"
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 34, 14
    for col in "CDE":
        ws.column_dimensions[col].width = 14

    counts = Counter(r.status for r in results)
    total = len(results)
    ws["A1"] = f"ÖHV-Mitgliederabgleich {bundesland}"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"Stand {date.today():%d.%m.%Y} · Quellen: Google Places API, ÖHV-Mitgliederliste (meinhotel.at)"
    ws["A2"].font = Font(name="Arial", italic=True, size=9)

    rows = [
        ("Beherbergungsbetriebe auf Google Maps", total),
        ("davon ÖHV-Mitglied", counts["Mitglied"]),
        ("davon kein Mitglied (Potenzial)", counts["kein Mitglied"]),
        ("davon manuell zu prüfen", counts["prüfen"]),
        ("Mitgliedsquote (bestätigt)", counts["Mitglied"] / total if total else 0),
        ("Einträge in der Mitgliederliste (gesamt, alle Bundesländer)", members_total),
    ]
    for i, (label, val) in enumerate(rows, 4):
        ws.cell(i, 1, label).font = BODY_FONT
        cell = ws.cell(i, 2, val)
        cell.font = Font(name="Arial", bold=True, color=BLAU)
        if isinstance(val, float):
            cell.number_format = "0.0 %"

    start = 4 + len(rows) + 2
    for c, t in enumerate(["Bezirk", "Betriebe", "Mitglieder", "Potenzial", "Quote"], 1):
        cell = ws.cell(start, c, t)
        cell.font, cell.fill = HEAD_FONT, HEAD_FILL
    by_bezirk: dict[str, Counter] = defaultdict(Counter)
    for r in results:
        by_bezirk[r.hotel.bezirk or "(ohne Angabe)"][r.status] += 1
    for i, (bezirk, c) in enumerate(sorted(by_bezirk.items(), key=lambda kv: -sum(kv[1].values())), start + 1):
        n = sum(c.values())
        vals = [bezirk, n, c["Mitglied"], c["kein Mitglied"], c["Mitglied"] / n]
        for col, v in enumerate(vals, 1):
            cell = ws.cell(i, col, v)
            cell.font = BODY_FONT
        ws.cell(i, 5).number_format = "0.0 %"

    order = {"Mitglied": 0, "prüfen": 1, "kein Mitglied": 2}
    _table(wb.create_sheet("Alle Betriebe"), sorted(results, key=lambda r: (order[r.status], r.hotel.bezirk, r.hotel.name)))
    potenzial = sorted((r for r in results if r.status == "kein Mitglied"), key=lambda r: -(r.hotel.anzahl_bewertungen or 0))
    _table(wb.create_sheet("Potenzial (Nicht-Mitglieder)"), potenzial)
    _table(wb.create_sheet("Manuell prüfen"), [r for r in results if r.status == "prüfen"])

    m = wb.create_sheet("Methodik")
    m.column_dimensions["A"].width = 120
    text = [
        "Methodik",
        "1. Google Places API (Text Search, Typ „lodging“, Suchbegriff „Hotel“): Das Bundesland wird in Kacheln zerlegt, "
        "volle Kacheln (60 Treffer) werden geviertelt. Nur Einträge mit Bundesland laut Google-Adresse, ohne dauerhaft geschlossene.",
        "2. Mitgliederliste: Hotelseiten von meinhotel.at (strukturierte Daten) bzw. CSV-Export der Mitgliederverwaltung.",
        "3. Zuordnung per Regel: gleiche Website-Domain, oder Namensähnlichkeit ≥ 90 % bei gleicher PLZ bzw. < 500 m Entfernung.",
        f"4. Unklare Fälle: TypeSafe-Modell Jev beurteilt je Kandidat, ob es derselbe Betrieb ist (Mitglied ab {NOUL_MATCH:.0%}, "
        f"ausgeschlossen unter {NOUL_NO_MATCH:.0%}, dazwischen manuelle Prüfung).",
        "",
        "Einschränkungen",
        "• Google Maps erfasst auch Pensionen, Apartments und Ferienwohnungen (Spalte „Typ“). Für Akquise-Listen ggf. nach Typ filtern.",
        "• Ein Mitglied kann mehreren Google-Einträgen zugeordnet sein (z. B. Hotel und Restaurant mit eigenem Eintrag).",
        "• Google-Daten sind nutzergeneriert; Bewertungszahl und Website sind Anhaltspunkte, keine geprüften Betriebsdaten.",
        "• Bewertungen und Kontaktdaten aus Google Maps unterliegen den Google-Maps-Nutzungsbedingungen (nur interne Auswertung, keine Weitergabe).",
    ]
    for i, t in enumerate(text, 1):
        cell = m.cell(i, 1, t)
        cell.font = Font(name="Arial", bold=t in ("Methodik", "Einschränkungen"), color=BLAU if t in ("Methodik", "Einschränkungen") else None)
        cell.alignment = Alignment(wrap_text=True)

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
