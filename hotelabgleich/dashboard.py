"""Interaktives Ranking als eigenständige HTML-Datei (ohne Server, Daten eingebettet).

Suche nach Name/Ort, Filter nach Bundesland, Ort, Typ, Sterne, Ausstattung und ÖHV-Mitgliedschaft;
Ranking beste/schwächste Betriebe; Vergleich Mitglieder vs. Nicht-Mitglieder für die aktuelle Auswahl.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import scoring
from .merge import Hotel

FIELDS = [
    "id", "name", "ort", "plz", "bezirk", "bundesland", "typ", "sterne", "ausstattung", "google_bewertung",
    "google_anzahl", "google_url", "booking_bewertung", "booking_anzahl", "booking_url", "teilnoten",
    "mitglied_status", "mitglied_name", "score", "score_google", "score_booking", "vertrauen", "klasse",
    "rang_gesamt", "rang_bundesland", "perzentil", "abweichung_quellen", "website",
]


def payload(hotels: list[Hotel], quellen: str, demo: bool = False) -> dict:
    rows = []
    for h in hotels:
        d = {k: getattr(h, k) for k in FIELDS}
        rows.append({k: v for k, v in d.items() if v not in (None, "", [], {})})
    return {
        "stand": f"{date.today():%d.%m.%Y}",
        "quellen": quellen,
        "demo": demo,
        "hotels": rows,
        "vergleich": scoring.compare(hotels),
        "modell": {
            "prior": scoring.PRIOR_REVIEWS,
            "gewichte": scoring.SOURCE_WEIGHT,
            "klassen": scoring.KLASSEN,
            "abweichung": scoring.ABWEICHUNG_HINWEIS,
        },
    }


def render(hotels: list[Hotel], quellen: str, demo: bool = False, standalone: bool = True) -> str:
    data = json.dumps(payload(hotels, quellen, demo), ensure_ascii=False).replace("</", "<\\/")
    body = TEMPLATE.replace("__DATA__", data)
    if standalone:
        return f'<!doctype html>\n<html lang="de">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n{body}\n</html>\n'
    return body


def write(hotels: list[Hotel], path: Path, quellen: str, demo: bool = False, standalone: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(hotels, quellen, demo, standalone), encoding="utf-8")


TEMPLATE = r"""<title>ÖHV Hotel-Ranking</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&display=swap">
<style>
/* Layout: Kopfband in ÖHV-Blau, darunter Filterleiste über Ergebnisliste; Vergleichspanel rechts, schmal untereinander. */
:root {
  --blau: #007eab; --blau-dunkel: #005b7a; --blau-hell: #dbedf3; --gelb: #eda10a; --gruen: #008058;
  --bg: #f6f9fb; --surface: #ffffff; --fg: #12242c; --muted: #5b6e77; --line: #d9e4ea; --chip: #eaf3f7; --head: #007eab; --link: #007eab;
  --k-exz: #008058; --k-sg: #4f9f6a; --k-gut: #007eab; --k-bef: #c98a08; --k-krit: #c4501a;
  --display: "Barlow Condensed", "Arial Narrow", Arial, sans-serif;
  --body: Arial, "Helvetica Neue", Helvetica, sans-serif;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #0b1a20; --surface: #11252d; --fg: #e4eef2; --muted: #9ab0b9; --line: #23414c; --chip: #183540;
  --blau-hell: #163844; --head: #e4eef2; --link: #6cc0de; --k-exz: #3fb37f; --k-sg: #7cc48e; --k-gut: #49a4c3; --k-bef: #eda10a; --k-krit: #f0784a; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #0b1a20; --surface: #11252d; --fg: #e4eef2; --muted: #9ab0b9; --line: #23414c; --chip: #183540;
  --blau-hell: #163844; --head: #e4eef2; --link: #6cc0de; --k-exz: #3fb37f; --k-sg: #7cc48e; --k-gut: #49a4c3; --k-bef: #eda10a; --k-krit: #f0784a; color-scheme: dark }
* { box-sizing: border-box }
body { margin: 0; background: var(--bg); color: var(--fg); font: 14px/1.5 var(--body) }
.wrap { max-width: 1280px; margin: 0 auto; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)) }
header.band { background: var(--blau); color: #fff }
header.band .wrap { padding-block: 22px 18px; display: flex; flex-wrap: wrap; gap: 8px 24px; align-items: end; justify-content: space-between }
h1, h2, h3 { font-family: var(--display); font-weight: 700; text-wrap: balance; margin: 0; line-height: 1.1 }
h1 { font-size: 2.4rem; letter-spacing: .01em }
h2 { font-size: 1.5rem; color: var(--head) }
h3 { font-size: 1.15rem }
.claim { font-family: var(--display); color: var(--gelb); font-size: 1.15rem; font-weight: 600 }
.meta { font-size: .8rem; opacity: .9 }
.demo-note { background: var(--gelb); color: #1d1400; font-weight: 700; font-size: .85rem }
.demo-note .wrap { padding-block: 6px }
main .wrap { padding-block: 20px 40px; display: grid; gap: 20px }
.kpis { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px }
@media (max-width: 760px) { .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)) } .kpi:last-child { grid-column: 1 / -1 } }
.kpi { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; display: grid; gap: 2px }
.kpi .lbl { font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted) }
.kpi .val { font-family: var(--display); font-size: 1.9rem; font-weight: 700; font-variant-numeric: tabular-nums }
.kpi .sub { font-size: .78rem; color: var(--muted) }
.pos { color: var(--k-exz) } .neg { color: var(--k-krit) }
.filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; align-items: end }
.filters label { display: grid; gap: 3px; font-size: .72rem; text-transform: uppercase; letter-spacing: .05em; color: var(--muted) }
input, select, button { font: inherit; color: var(--fg); background: var(--surface); border: 1px solid var(--line); border-radius: 4px; padding: 0 9px; height: 36px; min-width: 0 }
input:focus-visible, select:focus-visible, button:focus-visible, a:focus-visible { outline: 2px solid var(--gelb); outline-offset: 1px }
.chips { display: flex; flex-wrap: wrap; gap: 6px }
.chip { border-radius: 999px; padding: 4px 10px; font-size: .8rem; background: var(--chip); border: 1px solid transparent; cursor: pointer }
.chip[aria-pressed="true"] { background: var(--blau); color: #fff }
.seg { display: inline-flex; border: 1px solid var(--line); border-radius: 4px; overflow: hidden }
.seg button { border: 0; border-radius: 0; cursor: pointer; padding: 7px 10px }
.seg button[aria-pressed="true"] { background: var(--blau); color: #fff }
.grid2 { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 20px; align-items: start }
@media (max-width: 980px) { .grid2 { grid-template-columns: minmax(0, 1fr) } }
.panel { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 16px; display: grid; gap: 12px; min-width: 0 }
.tablebox { overflow-x: auto }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums }
th { text-align: left; font-size: .7rem; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); font-weight: 700; padding: 6px 8px; border-bottom: 2px solid var(--blau); white-space: nowrap }
td { padding: 7px 8px; border-bottom: 1px solid var(--line); vertical-align: top }
td.num, th.num { text-align: right }
td.num .hsub, .pill + .hsub { white-space: nowrap }
.hname { font-weight: 700 }
.hsub { font-size: .78rem; color: var(--muted) }
.bar { position: relative; height: 8px; background: var(--chip); border-radius: 4px; width: 90px; margin-top: 4px }
.bar i { position: absolute; inset: 0 auto 0 0; border-radius: 4px }
.pill { display: inline-block; font-size: .72rem; font-weight: 700; padding: 1px 8px; border-radius: 999px; color: #fff; white-space: nowrap }
.badge { display: inline-block; font-size: .7rem; font-weight: 700; padding: 1px 6px; border-radius: 3px; background: var(--blau-hell); color: var(--fg); border: 1px solid var(--blau) }
.badge.pruefen { border-color: var(--gelb) }
.warn { color: var(--k-bef); font-size: .75rem }
a { color: var(--link) }
.more { justify-self: start; cursor: pointer }
.dist { display: grid; gap: 8px }
.dist .row { display: grid; grid-template-columns: 96px 1fr; gap: 8px; align-items: center; font-size: .8rem }
.dist .bars { display: grid; gap: 2px }
.dist .b { height: 9px; border-radius: 2px; min-width: 1px }
.legend { display: flex; gap: 14px; font-size: .78rem; color: var(--muted) }
.legend span::before { content: ""; display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; background: var(--c) }
.prose { max-width: 70ch; display: grid; gap: 8px }
.prose p, .prose li { margin: 0 }
.prose ul { margin: 0; padding-left: 18px; display: grid; gap: 4px }
details summary { cursor: pointer; font-family: var(--display); font-size: 1.3rem; font-weight: 700; color: var(--head) }
.small { font-size: .78rem; color: var(--muted) }
@media (prefers-reduced-motion: no-preference) { .bar i, .dist .b { transition: width .25s ease } }
</style>

<header class="band"><div class="wrap">
  <div><h1>ÖHV Hotel-Ranking</h1><div class="claim">Für eine starke Hotellerie.</div></div>
  <div class="meta" id="meta"></div>
</div></header>
<div class="demo-note" id="demoNote" hidden><div class="wrap">Demo-Daten: erfundene Betriebe zur Ansicht der Funktionen, keine echten Bewertungen.</div></div>

<main><div class="wrap">
  <section class="kpis" id="kpis" aria-label="Kennzahlen der Auswahl"></section>

  <section class="panel" aria-label="Suche und Filter">
    <div class="filters">
      <label>Suche<input id="q" type="search" placeholder="Name oder Ort"></label>
      <label>Bundesland<select id="bl"><option value="">Alle</option></select></label>
      <label>Ort<input id="ort" list="orte" placeholder="Alle Orte"><datalist id="orte"></datalist></label>
      <label>Typ<select id="typ"><option value="">Alle</option></select></label>
      <label>Sterne<select id="sterne"><option value="">Alle</option><option value="5">5</option><option value="4">4</option><option value="3">3</option><option value="2">1–2</option><option value="0">ohne Angabe</option></select></label>
      <label>Klasse<select id="klasse"><option value="">Alle</option></select></label>
      <label>Mind. Vertrauen<select id="vertrauen"><option value="">Alle</option><option value="mittel">mittel (≥ 50 Bew.)</option><option value="hoch">hoch (≥ 200 Bew.)</option></select></label>
      <label>Sortierung<select id="sort"><option value="best">Beste zuerst</option><option value="worst">Schwächste zuerst</option><option value="reviews">Meiste Bewertungen</option><option value="name">Name A–Z</option></select></label>
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center">
      <div class="seg" role="group" aria-label="ÖHV-Mitgliedschaft" id="mseg">
        <button type="button" data-m="" aria-pressed="true">Alle Betriebe</button>
        <button type="button" data-m="Mitglied" aria-pressed="false">ÖHV-Mitglieder</button>
        <button type="button" data-m="kein Mitglied" aria-pressed="false">Nicht-Mitglieder</button>
      </div>
      <button type="button" id="reset">Filter zurücksetzen</button>
    </div>
    <div><div class="small" style="margin-bottom:6px">Ausstattung (alle gewählten müssen zutreffen)</div><div class="chips" id="amen"></div></div>
  </section>

  <div class="grid2">
    <section class="panel" aria-label="Ranking">
      <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:baseline">
        <h2>Ranking</h2><span class="small" id="count"></span>
      </div>
      <div class="tablebox"><table>
        <thead><tr><th class="num">Rang</th><th>Betrieb</th><th>Score</th><th>Klasse</th><th class="num">Google</th><th class="num">Booking</th><th>ÖHV</th></tr></thead>
        <tbody id="rows"></tbody>
      </table></div>
      <button type="button" class="more" id="more" hidden>Weitere 100 anzeigen</button>
    </section>

    <aside class="panel" aria-label="Vergleich Mitglieder und Nicht-Mitglieder">
      <h2>Mitglieder im Vergleich</h2>
      <div class="small">Bezogen auf die aktuelle Auswahl. Ohne Betriebe, deren Mitgliedschaft noch geprüft wird.</div>
      <div id="cmp"></div>
      <h3>Verteilung nach Klasse</h3>
      <div class="legend"><span style="--c:var(--blau)">ÖHV-Mitglieder</span><span style="--c:var(--muted)">Andere</span></div>
      <div class="dist" id="dist"></div>
      <h3>Nach Bundesland</h3>
      <div class="tablebox"><table><thead><tr><th>Land</th><th class="num">Ø Mitgl.</th><th class="num">Ø Andere</th><th class="num">Diff.</th></tr></thead><tbody id="cmpbl"></tbody></table></div>
    </aside>
  </div>

  <section class="panel">
    <details>
      <summary>Methodik und Hintergrund</summary>
      <div class="prose" id="method"></div>
    </details>
  </section>
</div></main>

<script type="application/json" id="data">__DATA__</script>
<script>
(function () {
  const D = JSON.parse(document.getElementById("data").textContent);
  const H = D.hotels;
  const KL = D.modell.klassen.map(k => k[1]);
  const KC = { "Exzellent": "var(--k-exz)", "Sehr gut": "var(--k-sg)", "Gut": "var(--k-gut)", "Befriedigend": "var(--k-bef)", "Kritisch": "var(--k-krit)" };
  const $ = id => document.getElementById(id);
  const fmt = (v, d = 1) => v == null ? "–" : v.toLocaleString("de-AT", { minimumFractionDigits: d, maximumFractionDigits: d });
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const mean = a => a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;
  const signed = v => v == null ? "–" : Math.abs(v) < 0.05 ? "±0,0" : (v > 0 ? "+" : "") + fmt(v);
  const median = a => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

  $("meta").textContent = `Stand ${D.stand} · ${H.length.toLocaleString("de-AT")} Betriebe · Quellen: ${D.quellen}`;
  $("demoNote").hidden = !D.demo;

  const uniq = k => [...new Set(H.map(h => h[k]).filter(Boolean))].sort((a, b) => a.localeCompare(b, "de"));
  uniq("bundesland").forEach(v => $("bl").add(new Option(v, v)));
  uniq("typ").forEach(v => $("typ").add(new Option(v, v)));
  KL.forEach(v => $("klasse").add(new Option(v, v)));
  const amenCount = {};
  H.forEach(h => (h.ausstattung || []).forEach(a => amenCount[a] = (amenCount[a] || 0) + 1));
  const amens = Object.entries(amenCount).sort((a, b) => b[1] - a[1]).slice(0, 18).map(e => e[0]);
  const chosen = new Set();
  amens.forEach(a => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "chip"; b.textContent = a; b.setAttribute("aria-pressed", "false");
    b.onclick = () => { chosen.has(a) ? chosen.delete(a) : chosen.add(a); b.setAttribute("aria-pressed", chosen.has(a)); update(); };
    $("amen").appendChild(b);
  });
  let mFilter = "", shown = 100;
  $("mseg").querySelectorAll("button").forEach(b => b.onclick = () => {
    mFilter = b.dataset.m;
    $("mseg").querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", x === b));
    update();
  });
  function fillOrte() {
    const bl = $("bl").value;
    $("orte").innerHTML = [...new Set(H.filter(h => !bl || h.bundesland === bl).map(h => h.ort).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b, "de")).map(o => `<option value="${esc(o)}">`).join("");
  }
  fillOrte();

  function filtered(ignoreMember) {
    const q = $("q").value.trim().toLowerCase(), bl = $("bl").value, ort = $("ort").value.trim().toLowerCase();
    const typ = $("typ").value, st = $("sterne").value, kl = $("klasse").value, vt = $("vertrauen").value;
    return H.filter(h => {
      if (h.score == null) return false;
      if (q && !(`${h.name} ${h.ort || ""} ${h.plz || ""}`.toLowerCase().includes(q))) return false;
      if (bl && h.bundesland !== bl) return false;
      if (ort && (h.ort || "").toLowerCase() !== ort) return false;
      if (typ && h.typ !== typ) return false;
      if (st) { const s = Math.floor(h.sterne || 0); if (st === "2" ? !(s >= 1 && s <= 2) : s !== +st) return false; }
      if (kl && h.klasse !== kl) return false;
      if (vt === "mittel" && h.vertrauen === "gering") return false;
      if (vt === "hoch" && h.vertrauen !== "hoch") return false;
      for (const a of chosen) if (!(h.ausstattung || []).includes(a)) return false;
      if (!ignoreMember && mFilter && h.mitglied_status !== mFilter) return false;
      return true;
    });
  }
  const sorters = {
    best: (a, b) => b.score - a.score || (b.google_anzahl || 0) + (b.booking_anzahl || 0) - (a.google_anzahl || 0) - (a.booking_anzahl || 0),
    worst: (a, b) => a.score - b.score,
    reviews: (a, b) => (b.google_anzahl || 0) + (b.booking_anzahl || 0) - (a.google_anzahl || 0) - (a.booking_anzahl || 0),
    name: (a, b) => a.name.localeCompare(b.name, "de"),
  };

  function row(h, i) {
    const stars = h.sterne ? " · " + "★".repeat(Math.floor(h.sterne)) + (h.sterne % 1 ? " S" : "") : "";
    const g = h.google_bewertung ? `${fmt(h.google_bewertung)}<div class="hsub">${(h.google_anzahl || 0).toLocaleString("de-AT")} Bew.</div>` : "–";
    const bk = h.booking_bewertung ? `${fmt(h.booking_bewertung)}<div class="hsub">${(h.booking_anzahl || 0).toLocaleString("de-AT")} Bew.</div>` : "–";
    const mem = h.mitglied_status === "Mitglied" ? `<span class="badge" title="${esc(h.mitglied_name)}">Mitglied</span>`
      : h.mitglied_status === "prüfen" ? `<span class="badge pruefen">prüfen</span>` : "";
    const links = [h.google_url && `<a href="${esc(h.google_url)}" target="_blank" rel="noopener">Google</a>`, h.booking_url && `<a href="${esc(h.booking_url)}" target="_blank" rel="noopener">Booking</a>`].filter(Boolean).join(" · ");
    const dev = h.abweichung_quellen >= D.modell.abweichung ? `<div class="warn">Google und Booking weichen ${fmt(h.abweichung_quellen, 0)} Punkte ab</div>` : "";
    const sub = Object.entries(h.teilnoten || {}).map(([k, v]) => `${k} ${fmt(v)}`).join(" · ");
    return `<tr>
      <td class="num">${i}<div class="hsub">${h.bundesland ? "Land " + (h.rang_bundesland ?? "–") : ""}</div></td>
      <td><div class="hname">${esc(h.name)}</div><div class="hsub">${esc([h.plz, h.ort].filter(Boolean).join(" "))}${h.bundesland ? ", " + esc(h.bundesland) : ""}${esc(stars)}${h.typ ? " · " + esc(h.typ) : ""}</div>${sub ? `<div class="hsub">${esc(sub)}</div>` : ""}${dev}${links ? `<div class="hsub">${links}</div>` : ""}</td>
      <td><strong>${fmt(h.score)}</strong><div class="bar"><i style="width:${h.score}%;background:${KC[h.klasse]}"></i></div><div class="hsub">Vertrauen ${esc(h.vertrauen)}</div></td>
      <td><span class="pill" style="background:${KC[h.klasse]}">${esc(h.klasse)}</span><div class="hsub">Top ${Math.max(1, Math.ceil(100 - h.perzentil))} %</div></td>
      <td class="num">${g}</td><td class="num">${bk}</td><td>${mem}</td></tr>`;
  }

  function kpi(lbl, val, sub, cls) {
    return `<div class="kpi"><span class="lbl">${lbl}</span><span class="val ${cls || ""}">${val}</span><span class="sub">${sub}</span></div>`;
  }

  function update(keepShown) {
    if (!keepShown) shown = 100;
    const list = filtered(false).sort(sorters[$("sort").value]);
    $("count").textContent = `${list.length.toLocaleString("de-AT")} Betriebe`;
    $("rows").innerHTML = list.slice(0, shown).map((h, i) => row(h, i + 1)).join("") ||
      `<tr><td colspan="7">Keine Betriebe für diese Auswahl. Filter lockern oder zurücksetzen.</td></tr>`;
    $("more").hidden = list.length <= shown;

    // Vergleich: gleiche Auswahl, aber unabhängig vom Mitglieds-Schalter.
    const pool = filtered(true).filter(h => h.mitglied_status === "Mitglied" || h.mitglied_status === "kein Mitglied");
    const M = pool.filter(h => h.mitglied_status === "Mitglied"), A = pool.filter(h => h.mitglied_status !== "Mitglied");
    const mm = mean(M.map(h => h.score)), ma = mean(A.map(h => h.score)), diff = mm != null && ma != null ? mm - ma : null;
    const top = [...pool].sort(sorters.best), k = Math.max(1, Math.floor(top.length / 10));
    const shareTop = top.length ? 100 * top.slice(0, k).filter(h => h.mitglied_status === "Mitglied").length / k : null;
    const shareAll = pool.length ? 100 * M.length / pool.length : null;

    $("kpis").innerHTML =
      kpi("Betriebe in Auswahl", list.length.toLocaleString("de-AT"), "mit Score") +
      kpi("Ø Score Auswahl", fmt(mean(list.map(h => h.score))), "Median " + fmt(median(list.map(h => h.score)))) +
      kpi("Ø ÖHV-Mitglieder", fmt(mm), `${M.length.toLocaleString("de-AT")} Betriebe`) +
      kpi("Ø Nicht-Mitglieder", fmt(ma), `${A.length.toLocaleString("de-AT")} Betriebe`) +
      kpi("Unterschied", signed(diff), "Score-Punkte, Mitglieder minus andere", diff > 0 ? "pos" : diff < 0 ? "neg" : "");

    const V = D.vergleich, p = V.gesamt.p_wert;
    $("cmp").innerHTML = `<div class="prose small">
      <p>Mitgliedsanteil in der Auswahl: <strong>${fmt(shareAll)} %</strong>, unter den besten 10 %: <strong>${fmt(shareTop)} %</strong>.</p>
      <p>Gesamtbestand: Mitglieder ${fmt(V.gesamt.mitglieder.mittel)} vs. andere ${fmt(V.gesamt.andere.mittel)}
      (${signed(V.gesamt.differenz)} Punkte${p == null ? "" : p < 0.05 ? ", statistisch signifikant, p = " + p.toExponential(1) : ", nicht signifikant, p = " + fmt(p, 2)}).
      Strukturbereinigt, also verglichen mit Betrieben im selben Bundesland, mit gleicher Sternezahl und ähnlicher Größe: <strong>${signed(V.bereinigt.differenz)} Punkte</strong>.</p></div>`;

    const cnt = (arr, kl) => arr.length ? 100 * arr.filter(h => h.klasse === kl).length / arr.length : 0;
    $("dist").innerHTML = KL.map(kl => {
      const a = cnt(M, kl), b = cnt(A, kl);
      return `<div class="row"><span>${kl}</span><div class="bars">
        <div class="b" style="width:${a}%;background:var(--blau)" title="Mitglieder ${fmt(a)} %"></div>
        <div class="b" style="width:${b}%;background:var(--muted)" title="Andere ${fmt(b)} %"></div></div></div>`;
    }).join("") + `<div class="small">Balkenlänge = Anteil der jeweiligen Gruppe in dieser Klasse.</div>`;

    const lands = [...new Set(pool.map(h => h.bundesland).filter(Boolean))].sort((a, b) => a.localeCompare(b, "de"));
    $("cmpbl").innerHTML = lands.map(l => {
      const m = mean(M.filter(h => h.bundesland === l).map(h => h.score)), a = mean(A.filter(h => h.bundesland === l).map(h => h.score));
      const d = m != null && a != null ? m - a : null;
      return `<tr><td>${esc(l)}</td><td class="num">${fmt(m)}</td><td class="num">${fmt(a)}</td><td class="num ${d >= 0.05 ? "pos" : d <= -0.05 ? "neg" : ""}">${signed(d)}</td></tr>`;
    }).join("");
  }

  ["q", "bl", "ort", "typ", "sterne", "klasse", "vertrauen", "sort"].forEach(id => $(id).addEventListener("input", () => { if (id === "bl") { $("ort").value = ""; fillOrte(); } update(); }));
  $("more").onclick = () => { shown += 100; update(true); };
  $("reset").onclick = () => {
    ["q", "bl", "ort", "typ", "sterne", "klasse", "vertrauen"].forEach(id => $(id).value = "");
    $("sort").value = "best"; chosen.clear(); $("amen").querySelectorAll(".chip").forEach(c => c.setAttribute("aria-pressed", "false"));
    mFilter = ""; $("mseg").querySelectorAll("button").forEach((x, i) => x.setAttribute("aria-pressed", i === 0)); fillOrte(); update();
  };

  const M = D.modell;
  $("method").innerHTML = `
    <h3>So entsteht der ÖHV-Gästescore (0–100)</h3>
    <ul>
      <li><strong>Normierung:</strong> Google-Sterne (1–5) und Booking.com-Noten (1–10) werden auf 0–100 umgerechnet. Google 4,5 entspricht 87,5 Punkten, Booking 8,5 entspricht 83,3 Punkten.</li>
      <li><strong>Glättung nach Bewertungsanzahl:</strong> Jede Quelle wird mit ${M.prior} fiktiven Durchschnittsbewertungen gemischt (Bayes-Mittel). Ein Haus mit 5,0 aus drei Bewertungen überholt so kein Haus mit 4,8 aus 2.000.</li>
      <li><strong>Zusammenführung:</strong> Google und Booking zählen grundsätzlich gleich (${M.gewichte.google * 100} : ${M.gewichte.booking * 100}), eine Quelle mit mehr Bewertungen erhält mehr Gewicht.</li>
      <li><strong>Klassen:</strong> ${M.klassen.map(k => `${k[1]} ab ${k[0]}`).join(", ")}. Feste Schwellen machen Ergebnisse über die Zeit vergleichbar; Rang und Perzentil zeigen die relative Position.</li>
      <li><strong>Vertrauen:</strong> hoch ab 200, mittel ab 50 Bewertungen über beide Plattformen. Weichen Google und Booking um mehr als ${M.abweichung} Punkte ab, erscheint ein Hinweis.</li>
    </ul>
    <h3>Vergleich ÖHV-Mitglieder vs. Nicht-Mitglieder</h3>
    <p>Der einfache Mittelwertvergleich ist verzerrt, wenn unter den Mitgliedern mehr größere 4- und 5-Sterne-Häuser sind, die generell besser bewertet werden. Der <strong>strukturbereinigte Unterschied</strong> vergleicht deshalb nur Betriebe im selben Bundesland, mit gleicher Sternezahl und ähnlicher Bewertungsanzahl (als Näherung für die Größe). Die Signifikanz prüft der Mann-Whitney-U-Test. Ein Unterschied zeigt einen Zusammenhang, keinen Beleg, dass die Mitgliedschaft ihn verursacht.</p>
    <h3>Hintergrund</h3>
    <ul>
      <li><strong>Datenquellen:</strong> Google Places API und Booking.com Demand API, beide offizielle Schnittstellen. Die Websites selbst werden nicht ausgelesen, weil die Nutzungsbedingungen beider Plattformen das verbieten. Die Booking-Teilnoten (Sauberkeit, Personal, Lage …) setzen eine Freischaltung im Partnervertrag voraus (<a href="https://developers.booking.com/demand/docs/open-api/demand-api/accommodations/accommodations/reviews/scores" target="_blank" rel="noopener">Booking.com Demand API</a>).</li>
      <li><strong>Sterne:</strong> In Österreich vergibt der Fachverband Hotellerie der WKO die Sterne nach den Kriterien der Hotelstars Union. Die Sterne auf Booking.com stammen teils aus dieser Klassifizierung, teils aus Angaben der Betriebe; sie werden hier nur als Filter verwendet und fließen nicht in den Score ein.</li>
      <li><strong>ÖHV-Mitgliedschaft:</strong> Die Zuordnung erfolgt über den Abgleich mit meinhotel.at (gleiche Website-Domain, Name und Lage). Unklare Fälle sind als „prüfen“ markiert und zählen im Vergleich nicht mit.</li>
      <li><strong>Grenzen:</strong> Online-Bewertungen bilden die Gästesicht ab, nicht Wirtschaftlichkeit oder Qualität in allen Dimensionen. Kleine Betriebe mit wenigen Bewertungen sind unsicherer eingestuft.</li>
      <li><strong>Nutzung:</strong> Google- und Booking-Inhalte unterliegen den Bedingungen der jeweiligen Plattform. Nur zur internen Auswertung verwenden, regelmäßig neu abrufen und vor einer Veröffentlichung rechtlich prüfen lassen.</li>
    </ul>`;

  update();
})();
</script>
"""
