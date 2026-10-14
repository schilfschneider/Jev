"""Kommandozeile: python -m hotelabgleich <schritt> ...

  google      Hotelbetriebe eines Bundeslands über die Google Places API sammeln
  mitglieder  ÖHV-Mitgliederliste von meinhotel.at lesen (oder CSV übernehmen)
  abgleich    Beide Listen abgleichen und Excel-Bericht schreiben
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import match, members, places, report


def main() -> None:
    ap = argparse.ArgumentParser(prog="hotelabgleich", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("google")
    g.add_argument("--bundesland", default="Salzburg", choices=sorted(places.BUNDESLAENDER))
    g.add_argument("--query", default="Hotel")
    g.add_argument("--typ", default="lodging", help="Places-Typ, z. B. lodging oder hotel")
    g.add_argument("--out", type=Path, default=Path("data/google_salzburg.json"))

    m = sub.add_parser("mitglieder")
    src = m.add_mutually_exclusive_group()
    src.add_argument("--csv", type=Path, help="Mitgliederliste als CSV statt Crawl von meinhotel.at")
    src.add_argument("--url-filter", default="", help="Nur Sitemap-URLs, die diesen Text enthalten")
    m.add_argument("--limit", type=int, help="Nur die ersten N Seiten (Testlauf)")
    m.add_argument("--delay", type=float, default=1.0)
    m.add_argument("--out", type=Path, default=Path("data/mitglieder.json"))

    a = sub.add_parser("abgleich")
    a.add_argument("--google", type=Path, default=Path("data/google_salzburg.json"))
    a.add_argument("--mitglieder", type=Path, default=Path("data/mitglieder.json"), help=".json oder .csv")
    a.add_argument("--bundesland", default="Salzburg")
    a.add_argument("--ohne-typesafe", action="store_true", help="Unklare Fälle nicht mit Jev bewerten")
    a.add_argument("--out", type=Path, default=Path("data/oehv_abgleich_salzburg.xlsx"))

    args = ap.parse_args()

    if args.cmd == "google":
        client = places.PlacesClient()
        hotels = places.collect(client, args.bundesland, args.query, args.typ)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        places.save(hotels, args.out)
        print(f"{len(hotels)} Betriebe in {args.bundesland} → {args.out} ({client.requests_sent} neue API-Anfragen)")

    elif args.cmd == "mitglieder":
        found = members.load_csv(args.csv) if args.csv else members.crawl_meinhotel(args.url_filter, args.delay, args.limit)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        members.save(found, args.out)
        print(f"{len(found)} Mitglieder → {args.out}")

    elif args.cmd == "abgleich":
        hotels = places.load(args.google)
        mlist = members.load(args.mitglieder)
        results = match.match_all(hotels, mlist, use_typesafe=not args.ohne_typesafe)
        report.write(results, len(mlist), args.bundesland, args.out)
        stats = {s: sum(r.status == s for r in results) for s in ("Mitglied", "kein Mitglied", "prüfen")}
        print(f"{len(results)} Betriebe: {stats} → {args.out}")


if __name__ == "__main__":
    main()
