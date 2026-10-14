# ÖHV-Mitgliederabgleich: Hotelbetriebe laut Google Maps × meinhotel.at

Erfasst alle Beherbergungsbetriebe eines Bundeslands (zuerst **Salzburg**) über die Google Places API, gleicht
sie mit der ÖHV-Mitgliederliste von meinhotel.at ab und erstellt einen Excel-Bericht:

| Blatt | Inhalt |
| --- | --- |
| Übersicht | Anzahl Betriebe, Mitglieder, Potenzial, Mitgliedsquote gesamt und je Bezirk |
| Alle Betriebe | Vollständige Liste mit Status und zugeordnetem Mitglied |
| Potenzial (Nicht-Mitglieder) | Betriebe ohne Mitgliedschaft, sortiert nach Anzahl Google-Bewertungen (Indikator für Größe/Bekanntheit) |
| Manuell prüfen | Fälle, die weder Regeln noch das Modell sicher zuordnen konnten |
| Methodik | Vorgehen und Einschränkungen |

## Ablauf

```bash
pip install -r requirements.txt

# 1. Google-Maps-Betriebe sammeln (braucht GOOGLE_MAPS_API_KEY)
python -m hotelabgleich google --bundesland Salzburg

# 2. Mitgliederliste: Crawl von meinhotel.at …
python -m hotelabgleich mitglieder --limit 20      # Testlauf, dann ohne --limit
#    … oder Export aus der Mitgliederverwaltung (Spalten: name; plz; ort; strasse; website; lat; lon)
python -m hotelabgleich mitglieder --csv mitglieder.csv

# 3. Abgleich + Bericht (nutzt TYPESAFE_API_KEY, falls gesetzt)
python -m hotelabgleich abgleich
# → data/oehv_abgleich_salzburg.xlsx
```

## Wie der Abgleich entscheidet

1. **Kandidaten** je Google-Betrieb: Mitglieder mit gleicher Website-Domain, gleicher PLZ oder < 2 km Entfernung.
2. **Regeln:** gleiche Domain → Mitglied. Nahezu gleicher Name (≥ 90 %, ohne Füllwörter wie „Hotel“, „GmbH“,
   Sterne) und gleiche PLZ bzw. < 500 m → Mitglied. Kein ähnlicher Name in der Umgebung → kein Mitglied.
3. **Unklare Fälle** (z. B. „Alpenrose Apartments“ neben „Hotel Alpenrose“): Das TypeSafe-Modell **Jev**
   beantwortet je Kandidat die Ja/Nein-Frage, ob es derselbe Hotelbetrieb ist. Ab 85 % gilt die Zuordnung,
   unter 15 % ist sie ausgeschlossen, dazwischen bleibt der Fall zur manuellen Prüfung. Die Schwellen sind
   Startwerte und sollten an einer Stichprobe bekannter Fälle überprüft werden.

## Zugänge

| Variable | Wofür |
| --- | --- |
| `GOOGLE_MAPS_API_KEY` | Google Places API (New), Text Search. Abgefragte Felder wie Website und Telefon fallen in eine höhere Preisstufe; Antworten werden unter `data/cache/` zwischengespeichert, Wiederholungen kosten nichts. |
| `TYPESAFE_API_KEY` | Optional, für die Bewertung unklarer Fälle durch Jev. |

Die Google-Daten unterliegen den Nutzungsbedingungen der Google Maps Platform: nur für die interne Auswertung,
nicht weitergeben oder veröffentlichen.

## Tests

```bash
python -m pytest
```
