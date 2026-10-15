# ÖHV Hotel-Ranking und Mitgliederabgleich

Sammelt Beherbergungsbetriebe in ganz Österreich aus **Google Maps** (Google Places API) und **Booking.com**
(Demand API), führt beide Quellen je Betrieb zusammen, gleicht mit der ÖHV-Mitgliederliste von
**meinhotel.at** ab und berechnet einen eigenen **ÖHV-Gästescore** (0–100). Ergebnis:

| Ausgabe | Inhalt |
| --- | --- |
| `oehv_ranking.html` | Interaktives Dashboard: Suche nach Name/Ort, Filter nach Bundesland, Ort, Typ, Sterne, Klasse, Ausstattung und ÖHV-Mitgliedschaft; Ranking beste/schwächste Betriebe; Vergleich Mitglieder vs. Nicht-Mitglieder für die jeweilige Auswahl |
| `oehv_ranking.xlsx` | Vergleich (gesamt, je Bundesland/Sterne/Größe, strukturbereinigt), vollständiges Ranking, Methodik |
| `hotels_scored.json` | Alle Betriebe mit Quellenwerten, Score, Rang und Mitgliedsstatus |
| `oehv_abgleich_<land>.xlsx` | Bisheriger Bericht zur Mitgliedsquote je Bezirk und Akquise-Potenzial |

## Schnellstart ohne Zugänge

```bash
pip install -r requirements.txt
python -m hotelabgleich demo          # erfundene Betriebe → data/demo/oehv_ranking.html
```

## Echter Lauf

```bash
# 1. Google Maps: alle Bundesländer (braucht GOOGLE_MAPS_API_KEY)
python -m hotelabgleich google --bundesland alle         # → data/google_oesterreich.json

# 2. Booking.com: Demand API (Partnerzugang) …
python -m hotelabgleich booking [--teilnoten]            # → data/booking.json
#    … oder CSV aus einer lizenzierten Quelle
python -m hotelabgleich booking --csv booking.csv

# 3. ÖHV-Mitglieder von meinhotel.at (oder CSV-Export der Mitgliederverwaltung)
python -m hotelabgleich mitglieder                       # → data/mitglieder.json

# 4. Zusammenführen, abgleichen, bewerten, Dashboard + Excel schreiben
python -m hotelabgleich ranking --booking data/booking.json
```

Booking-CSV: Spalten `name; plz; ort; adresse; lat; lon; sterne; bewertung; anzahl_bewertungen; typ; ausstattung; url`,
Ausstattung mit `|` getrennt, optional Teilnoten `sauberkeit; personal; lage; preis-leistung; komfort; wlan` (Skala 1–10).

## ÖHV-Gästescore

1. **Normieren auf 0–100:** Google (1–5) → (x − 1) / 4 · 100, Booking (1–10) → (x − 1) / 9 · 100.
2. **Glätten (Bayes-Mittel):** jede Quelle mit 25 fiktiven Durchschnittsbewertungen gemischt, damit 5,0 aus drei
   Bewertungen nicht vor 4,8 aus 2.000 landet.
3. **Zusammenführen:** gewichteter Mittelwert, Gewicht je Quelle = 50 % · n / (n + 25).
4. **Einstufen:** Exzellent ≥ 90, Sehr gut ≥ 82, Gut ≥ 72, Befriedigend ≥ 60, sonst Kritisch; dazu Rang gesamt,
   Rang im Bundesland, Perzentil, Vertrauen (hoch ≥ 200, mittel ≥ 50 Bewertungen) und ein Hinweis, wenn Google und
   Booking um mehr als 15 Punkte abweichen.

Alle Parameter stehen oben in `hotelabgleich/scoring.py`.

**Vergleich Mitglieder vs. Nicht-Mitglieder:** Mittelwert, Median, Mann-Whitney-U-Test, Anteil der Mitglieder unter
den besten/schwächsten 10 % sowie ein **strukturbereinigter Unterschied**: Verglichen werden nur Betriebe im selben
Bundesland, mit gleicher Sternezahl und ähnlicher Größe (Anzahl Bewertungen als Näherung). So zeigt die Auswertung,
ob Mitglieder besser abschneiden als *vergleichbare* Häuser – nicht nur, weil unter ihnen mehr große 4- und
5-Sterne-Betriebe sind. Betriebe mit Mitgliedsstatus „prüfen“ zählen nicht mit.

## Zusammenführung und Mitgliederabgleich

- **Google ↔ Booking:** gleicher Betrieb, wenn < 100 m entfernt und Name ≥ 75 % ähnlich, oder < 500 m und ≥ 88 %.
  Booking-Betriebe ohne Google-Gegenstück bleiben eigene Einträge (Bundesland dann aus der PLZ).
- **ÖHV-Mitglied:** gleiche Website-Domain, oder fast gleicher Name bei gleicher PLZ bzw. < 500 m → Mitglied.
  Kein ähnlicher Name in der Nähe, oder alle namensähnlichen Mitglieder haben eine andere Website → kein Mitglied.
  Unklare Fälle bewertet optional das TypeSafe-Modell **Jev** (`TYPESAFE_API_KEY`), sonst bleiben sie auf „prüfen“.

## Zugänge

| Variable | Wofür |
| --- | --- |
| `GOOGLE_MAPS_API_KEY` | Google Places API (New), Text Search. Ausstattungsfelder (Hunde, Kinder, Frühstück, Parken, Barrierefreiheit) fallen in die höchste Preisstufe. Antworten werden unter `data/cache/` zwischengespeichert. |
| `BOOKING_API_TOKEN`, `BOOKING_AFFILIATE_ID` | Booking.com Demand API (Partnerprogramm). `BOOKING_API_BASE` optional, z. B. Sandbox `https://demandapi-sandbox.booking.com/3.1/`. Teilnoten nur mit Freischaltung der Reviews-Endpunkte im Partnervertrag. |
| `TYPESAFE_API_KEY` | Optional, für unklare Mitgliedsfälle. |

**Ungetestet:** Der Booking-Anschluss folgt der öffentlichen Dokumentation der Demand API 3.1, war aber aus der
Entwicklungsumgebung nicht erreichbar. Beim ersten Lauf gegen die Sandbox prüfen. Dasselbe gilt für den Crawler
von meinhotel.at.

## Rechtliches

Die Websites von Google Maps und Booking.com werden bewusst **nicht** ausgelesen: Beide Plattformen verbieten
automatisiertes Auslesen in ihren Nutzungsbedingungen, Bewertungssammlungen können zudem als Datenbank geschützt
sein. Auch über die offiziellen Schnittstellen gelten Einschränkungen (u. a. Speicherdauer von Google-Inhalten,
Verwendungszweck laut Booking-Partnervertrag). Daten nur intern auswerten, regelmäßig neu abrufen und vor einer
Veröffentlichung von Rankings rechtlich prüfen lassen.

## Tests

```bash
python -m pytest
```
