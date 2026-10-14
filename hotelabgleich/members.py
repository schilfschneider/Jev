"""ÖHV-Mitgliederliste laden: aus meinhotel.at (Sitemap + strukturierte Daten) oder aus einer CSV.

Hinweis: Der Aufbau von meinhotel.at war beim Erstellen nicht einsehbar (Domain aus der
Arbeitsumgebung gesperrt). Der Crawler setzt daher auf zwei verbreitete Standards – eine
XML-Sitemap und schema.org-Daten (JSON-LD) auf den Hotelseiten – und muss beim ersten echten
Lauf überprüft werden. Der CSV-Import ist der verlässliche Weg, z. B. mit einem Export aus der
ÖHV-Mitgliederverwaltung.
"""

from __future__ import annotations

import csv
import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urljoin

import requests

BASE_URL = "https://www.meinhotel.at/"
HOTEL_TYPES = {"Hotel", "LodgingBusiness", "Resort", "BedAndBreakfast", "Hostel", "Motel"}
USER_AGENT = "OEHV-Mitgliederabgleich/1.0"


@dataclass
class Member:
    name: str
    plz: str = ""
    ort: str = ""
    strasse: str = ""
    website: str = ""
    lat: float | None = None
    lon: float | None = None
    quelle: str = ""


def load_csv(path: Path) -> list[Member]:
    """CSV mit Spalten name, plz, ort, strasse, website, lat, lon (nur ``name`` ist Pflicht).

    Trennzeichen ``;`` oder ``,`` wird automatisch erkannt (Excel-Export).
    """
    text = path.read_text(encoding="utf-8-sig")
    dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=";,")
    members = []
    for row in csv.DictReader(text.splitlines(), dialect=dialect):
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}

        def num(key: str) -> float | None:
            try:
                return float(row.get(key, "").replace(",", "."))
            except ValueError:
                return None

        if row.get("name"):
            members.append(
                Member(
                    name=row["name"],
                    plz=row.get("plz", ""),
                    ort=row.get("ort", ""),
                    strasse=row.get("strasse", ""),
                    website=row.get("website", ""),
                    lat=num("lat"),
                    lon=num("lon"),
                    quelle=str(path),
                )
            )
    return members


def _get(session: requests.Session, url: str) -> str:
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return r.text


def _sitemap_urls(session: requests.Session, url: str, depth: int = 0) -> list[str]:
    root = ET.fromstring(_get(session, url).encode())
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    if root.tag.endswith("sitemapindex") and depth < 3:
        urls = []
        for loc in root.findall("s:sitemap/s:loc", ns):
            urls += _sitemap_urls(session, loc.text.strip(), depth + 1)
        return urls
    return [loc.text.strip() for loc in root.findall("s:url/s:loc", ns)]


def _jsonld_hotels(html: str):
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data])
        for item in items:
            types = item.get("@type", [])
            types = {types} if isinstance(types, str) else set(types)
            if types & HOTEL_TYPES:
                yield item


def parse_member_page(html: str, url: str) -> Member | None:
    for item in _jsonld_hotels(html):
        addr = item.get("address") or {}
        if isinstance(addr, list):
            addr = addr[0] if addr else {}
        geo = item.get("geo") or {}
        same_as = item.get("sameAs") or []
        website = item.get("url", "")
        # Auf einem Portal zeigt "url" oft auf die Portalseite selbst; die Hotel-Website steht dann in sameAs.
        if "meinhotel.at" in website:
            website = next((s for s in ([same_as] if isinstance(same_as, str) else same_as) if "meinhotel.at" not in s), "")
        try:
            lat, lon = float(geo.get("latitude")), float(geo.get("longitude"))
        except (TypeError, ValueError):
            lat = lon = None
        return Member(
            name=item.get("name", "").strip(),
            plz=str(addr.get("postalCode", "")).strip(),
            ort=addr.get("addressLocality", "").strip(),
            strasse=addr.get("streetAddress", "").strip(),
            website=website,
            lat=lat,
            lon=lon,
            quelle=url,
        )
    return None


def crawl_meinhotel(url_filter: str = "", delay: float = 1.0, limit: int | None = None, log=print) -> list[Member]:
    """Hotelseiten aus der Sitemap von meinhotel.at lesen. Höflich: eine Anfrage pro ``delay`` Sekunden."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    robots = _get(session, urljoin(BASE_URL, "robots.txt"))
    sitemaps = re.findall(r"(?im)^sitemap:\s*(\S+)", robots) or [urljoin(BASE_URL, "sitemap.xml")]
    urls = [u for sm in sitemaps for u in _sitemap_urls(session, sm)]
    urls = [u for u in dict.fromkeys(urls) if url_filter in u][:limit]
    log(f"{len(urls)} Seiten aus der Sitemap")
    members, skipped = [], 0
    for i, url in enumerate(urls, 1):
        try:
            m = parse_member_page(_get(session, url), url)
        except requests.RequestException as e:
            log(f"  Fehler {url}: {e}")
            m = None
        if m and m.name:
            members.append(m)
        else:
            skipped += 1
        if i % 50 == 0:
            log(f"  {i}/{len(urls)} gelesen, {len(members)} Hotels")
        time.sleep(delay)
    log(f"{len(members)} Mitgliedsbetriebe erkannt, {skipped} Seiten ohne Hoteldaten")
    return members


def save(members: list[Member], path: Path) -> None:
    path.write_text(json.dumps([asdict(m) for m in members], ensure_ascii=False, indent=1))


def load(path: Path) -> list[Member]:
    if path.suffix.lower() == ".csv":
        return load_csv(path)
    return [Member(**d) for d in json.loads(path.read_text())]
