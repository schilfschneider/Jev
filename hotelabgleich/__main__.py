"""Kommandozeile: python -m hotelabgleich <schritt> ...

  google      Hotelbetriebe eines Bundeslands (oder ganz Österreichs) über die Google Places API sammeln
  booking     Unterkünfte in Österreich über die Booking.com Demand API laden (oder CSV übernehmen)
  mitglieder  ÖHV-Mitgliederliste von meinhotel.at lesen (oder CSV übernehmen)
  abgleich    Google-Betriebe mit Mitgliedern abgleichen, Excel-Bericht zur Mitgliedsquote
  ranking     Google + Booking zusammenführen, Mitglieder abgleichen, Gästescore berechnen,
              Ranking-Excel und interaktives Dashboard (HTML) schreiben
  demo        Ranking mit erfundenen Beispieldaten erzeugen (ohne API-Zugänge)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import booking, dashboard, demo, match, members, merge, places, report, scoring


def slug(name: str) -> str:
    return name.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")


def build_ranking(google, bookings, mlist, use_typesafe: bool, log=print) -> list[merge.Hotel]:
    hotels = merge.merge(google, bookings)
    with_booking = sum(h.booking_anzahl > 0 and h.id.startswith("g:") for h in hotels)
    log(f"{len(hotels)} Betriebe nach Zusammenführung ({with_booking} mit Google und Booking)")
    for r in match.match_all(hotels, mlist, use_typesafe=use_typesafe, log=log):
        h = r.hotel
        h.mitglied_status, h.mitglied_methode = r.status, r.methode
        h.mitglied_name = r.member.name if r.member and r.status != "kein Mitglied" else ""
    return scoring.score_all(hotels)


def write_outputs(hotels, out_dir: Path, quellen: str, demo_mode: bool = False) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    merge.save(hotels, out_dir / "hotels_scored.json")
    report.write_ranking(hotels, scoring.compare(hotels), out_dir / "oehv_ranking.xlsx", quellen)
    dashboard.write(hotels, out_dir / "oehv_ranking.html", quellen, demo=demo_mode)
    cmp = scoring.compare(hotels)["gesamt"]
    print(f"Ø Score Mitglieder {cmp['mitglieder']['mittel']} (n={cmp['mitglieder']['n']}) vs. andere "
          f"{cmp['andere']['mittel']} (n={cmp['andere']['n']}) → {out_dir}/oehv_ranking.html, oehv_ranking.xlsx")


def main() -> None:
    ap = argparse.ArgumentParser(prog="hotelabgleich", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("google")
    g.add_argument("--bundesland", default="Salzburg", choices=[*sorted(places.BUNDESLAENDER), "alle"])
    g.add_argument("--query", default="Hotel")
    g.add_argument("--typ", default="lodging", help="Places-Typ, z. B. lodging oder hotel")
    g.add_argument("--out", type=Path, help="Standard: data/google_<bundesland>.json bzw. data/google_oesterreich.json")

    b = sub.add_parser("booking")
    b.add_argument("--csv", type=Path, help="Booking-Daten als CSV statt Demand API (Spalten siehe README)")
    b.add_argument("--teilnoten", action="store_true", help="Teilnoten abrufen (nur mit Freischaltung im Partnervertrag)")
    b.add_argument("--out", type=Path, default=Path("data/booking.json"))

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

    r = sub.add_parser("ranking")
    r.add_argument("--google", type=Path, nargs="*", default=[Path("data/google_oesterreich.json")])
    r.add_argument("--booking", type=Path, help=".json oder .csv (optional)")
    r.add_argument("--mitglieder", type=Path, default=Path("data/mitglieder.json"), help=".json oder .csv")
    r.add_argument("--ohne-typesafe", action="store_true", help="Unklare Mitgliedsfälle nicht mit Jev bewerten")
    r.add_argument("--out-dir", type=Path, default=Path("data"))

    d = sub.add_parser("demo")
    d.add_argument("--anzahl", type=int, default=600)
    d.add_argument("--out-dir", type=Path, default=Path("data/demo"))

    args = ap.parse_args()

    if args.cmd == "google":
        client = places.PlacesClient()
        lands = sorted(places.BUNDESLAENDER) if args.bundesland == "alle" else [args.bundesland]
        hotels = []
        for land in lands:
            found = places.collect(client, land, args.query, args.typ)
            print(f"{len(found)} Betriebe in {land}")
            hotels += found
        out = args.out or Path(f"data/google_{'oesterreich' if args.bundesland == 'alle' else slug(args.bundesland)}.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        places.save(hotels, out)
        print(f"{len(hotels)} Betriebe → {out} ({client.requests_sent} neue API-Anfragen)")

    elif args.cmd == "booking":
        found = booking.load_csv(args.csv) if args.csv else booking.collect(booking.DemandClient(), with_subscores=args.teilnoten)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        booking.save(found, args.out)
        print(f"{len(found)} Booking.com-Unterkünfte → {args.out}")

    elif args.cmd == "ranking":
        google = [h for p in args.google for h in places.load(p)]
        bookings = booking.load(args.booking) if args.booking else []
        hotels = build_ranking(google, bookings, members.load(args.mitglieder), not args.ohne_typesafe)
        quellen = "Google Places API" + (", Booking.com Demand API" if bookings else "") + ", meinhotel.at"
        write_outputs(hotels, args.out_dir, quellen)

    elif args.cmd == "demo":
        google, bookings, mlist = demo.generate(args.anzahl)
        hotels = build_ranking(google, bookings, mlist, use_typesafe=False)
        write_outputs(hotels, args.out_dir, "erfundene Demo-Daten", demo_mode=True)

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
