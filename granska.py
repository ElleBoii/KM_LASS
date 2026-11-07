"""Granska resultaten i data/*.json: skapar en lättläst HTML-rapport i mappen granskning.

Kör:  python granska.py
Du får välja vilken fil som ska granskas (eller Alla) genom att skriva en siffra och trycka Enter.
Hoppa över frågan och granska allt med:  python granska.py --alla
Rapporten öppnas i webbläsaren.

Rapporten innehåller:
  1. Översikt per KM
  2. Alla grenar med antal startande
  3. Rangordning per gren (tid, poäng, åldersklass)
  4. Alla simmare med sina lopp
  5. Kontroller som hittar misstänkta fel i datan

Den läser bara data/*.json, alltså exakt det som publiceras på hemsidan.
"""
import html
import json
import sys
import webbrowser
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path("data")
UT = Path("granskning")   # egen mapp, skild från utdata, och ignorerad av git
MIN_STARTANDE = 5   # samma gräns som i lenex_extract.py, används bara för kontrollen

STROKE_SV = {"FREE": "Frisim", "BACK": "Ryggsim", "BREAST": "Bröstsim", "FLY": "Fjärilsim",
             "MEDLEY": "Medley", "IMRELAY": "Lagmedley"}
STROKE_ORDER = list(STROKE_SV)
KLASS_ORDER = ["13-14", "15-16", "17-19", "20+"]
KON_SV = {"F": "Damer", "M": "Herrar"}
STATUS_SV = {"DSQ": "Disk", "DNS": "Ej start", "DNF": "Ej mål", "WDR": "Struken", "EXH": "Utom tävlan"}

esc = lambda s: html.escape(str(s if s is not None else ""))


def tid(h):
    if h is None:
        return ""
    cs = int(h)
    m, rest = divmod(cs, 6000)
    s, c = divmod(rest, 100)
    return f"{m}:{s:02d}.{c:02d}" if m else f"{s}.{c:02d}"


def gren_namn(r):
    return f"{r['distance']} m {STROKE_SV.get(r['stroke'], r['stroke'])}"


def gren_sort(r):
    st = STROKE_ORDER.index(r["stroke"]) if r["stroke"] in STROKE_ORDER else 99
    return (st, int(r["distance"] or 0))


def nyckel(r):
    return (r["first"], r["last"], r["birth"], r["gender"])


def namn(r):
    return f"{r['first']} {r['last']}"


def tabell(rubriker, rader, hogerjust=()):
    h = "".join(f'<th class="{"n" if i in hogerjust else ""}">{esc(t)}</th>' for i, t in enumerate(rubriker))
    b = "".join("<tr>" + "".join(f'<td class="{"n" if i in hogerjust else ""}">{c}</td>'
                                 for i, c in enumerate(rad)) + "</tr>" for rad in rader)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>"


def las_data():
    idx = DATA / "index.json"
    if not idx.exists():
        sys.exit("Hittar inte data/index.json. Kör först: python lenex_extract.py")
    meets = []
    for f in json.loads(idx.read_text(encoding="utf-8")):
        d = json.loads((DATA / f).read_text(encoding="utf-8"))
        d["fil"] = f
        meets.append(d)
    if not meets:
        sys.exit("data/index.json är tom.")
    return sorted(meets, key=lambda m: m["meet"]["date"])


def valj(meets):
    """Frågar användaren vilka filer som ska granskas. Sista siffran är alltid "Alla"."""
    if "--alla" in sys.argv:
        return meets
    alla = len(meets) + 1
    print("Vilka filer ska granskas?")
    for i, m in enumerate(meets, 1):
        print(f"  {i}. {m['fil']}  ({m['meet']['name']}, {m['meet']['date']}, {len(m['results'])} resultat)")
    print(f"  {alla}. Alla")
    while True:
        try:
            svar = input(f"Skriv en siffra (1-{alla}) och tryck Enter: ").strip()
        except EOFError:   # ingen som kan svara (t.ex. körs utan terminal): granska allt
            print("Ingen inmatning möjlig, granskar alla.")
            return meets
        if svar.isdigit() and 1 <= int(svar) <= alla:
            n = int(svar)
            return meets if n == alla else [meets[n - 1]]
        print(f"  \"{svar}\" är inte giltigt. Välj en siffra mellan 1 och {alla}.")


def oversikt(meets):
    rader = []
    for m in meets:
        rs = m["results"]
        status = Counter(r["status"] for r in rs if r["status"])
        rader.append([esc(m["meet"]["name"]), esc(m["meet"]["date"]), esc(m["meet"]["course"]), len(rs),
                      len({nyckel(r) for r in rs}), len({(r["distance"], r["stroke"], r["gender"]) for r in rs}),
                      esc(", ".join(f"{STATUS_SV.get(k, k)}: {v}" for k, v in status.items()) or "–"), esc(m["fil"])])
    return tabell(["KM", "Datum", "Bana", "Resultat", "Simmare", "Grenar", "Status", "Fil"], rader, {3, 4, 5})


def grenar(m):
    """Grupperar efter (gren, kön)."""
    g = defaultdict(list)
    for r in m["results"]:
        g[(r["distance"], r["stroke"], r["gender"])].append(r)
    return sorted(g.items(), key=lambda kv: (gren_sort(kv[1][0]), kv[0][2]))


def grenoversikt(m):
    rader = []
    for (dist, stroke, kon), rs in grenar(m):
        klass = Counter(r["cls"] for r in rs)
        rader.append([esc(gren_namn(rs[0])), KON_SV.get(kon, kon), len(rs), len({nyckel(r) for r in rs}),
                      esc("  ".join(f"{k}: {klass[k]}" for k in KLASS_ORDER if klass[k])),
                      sum(1 for r in rs if r["status"] == "DSQ")])
    return tabell(["Gren", "Kön", "Resultat", "Startande", "Per åldersklass", "Diskade"], rader, {2, 3, 5})


def grenlistor(m):
    ut = []
    for (dist, stroke, kon), rs in grenar(m):
        rs = sorted(rs, key=lambda r: (-r["points"], r["time"] if r["time"] is not None else 10**9))
        rader = []
        for i, r in enumerate(rs, 1):
            status = STATUS_SV.get(r["status"], r["status"])
            rader.append([i, esc(namn(r)), esc(r["birth"]), esc(r["cls"]), esc(r["club"]),
                          esc(status) if r["status"] else tid(r["time"]), r["points"] if r["points"] else "–"])
        ut.append(f'<div class="event"><h4>{esc(gren_namn(rs[0]))}, {KON_SV.get(kon, kon)} '
                  f'<span class="muted">({len(rs)} resultat)</span></h4>'
                  + tabell(["#", "Namn", "Född", "Klass", "Klubb", "Tid", "Poäng"], rader, {0, 5, 6}) + "</div>")
    return "".join(ut)


def simmarlista(meets):
    per = defaultdict(list)
    for m in meets:
        for r in m["results"]:
            per[nyckel(r)].append((m["meet"]["name"], r))
    rader = []
    for k, rs in sorted(per.items(), key=lambda kv: (kv[0][1].lower(), kv[0][0].lower())):
        rs.sort(key=lambda x: gren_sort(x[1]))
        lopp = "<br>".join(
            f"{esc(km)}: {esc(gren_namn(r))} "
            + (esc(STATUS_SV.get(r['status'], r['status'])) if r["status"] else f"{tid(r['time'])} ({r['points']} p)")
            for km, r in rs)
        r0 = rs[-1][1]
        rader.append([esc(f"{k[0]} {k[1]}"), esc(k[2]), esc(KON_SV.get(k[3], k[3])), esc(r0["club"]),
                      esc(r0["cls"]), len({km for km, _ in rs}), lopp])
    return tabell(["Namn", "Född", "Kön", "Klubb", "Klass", "KM", "Lopp"], rader, {5}), len(rader)


def kontroller(meets):
    """Returnerar en lista (rubrik, [detaljer]) för varje kontroll."""
    fel = defaultdict(list)
    namn_varianter = defaultdict(set)
    for m in meets:
        km, ar = m["meet"]["name"], int(m["meet"]["date"][:4])
        sedda = Counter()
        for (dist, stroke, kon), rs in grenar(m):
            if len(rs) < MIN_STARTANDE:
                fel["Grenar med färre än %d resultat" % MIN_STARTANDE].append(f"{km}: {gren_namn(rs[0])} {KON_SV.get(kon, kon)} ({len(rs)})")
        for r in rs_all(m):
            namn_varianter[(r["first"].lower(), r["last"].lower())].add((r["birth"], r["gender"]))
            sedda[(nyckel(r), r["distance"], r["stroke"])] += 1
            alder = ar - int(r["birth"]) if str(r["birth"]).isdigit() else None
            if r["status"] == "" and r["points"] == 0:
                fel["Resultat med tid men 0 poäng"].append(f"{km}: {namn(r)}, {gren_namn(r)}")
            if r["status"] == "" and r["time"] is None:
                fel["Resultat utan tid och utan status"].append(f"{km}: {namn(r)}, {gren_namn(r)}")
            if r["status"] == "EXH":
                fel["Resultat utom tävlan (ska normalt vara borttagna)"].append(f"{km}: {namn(r)}, {gren_namn(r)}")
            if not r["cls"]:
                fel["Resultat utan åldersklass"].append(f"{km}: {namn(r)}, {gren_namn(r)}")
            if alder is not None and alder <= 12:
                fel["Simmare som är 12 år eller yngre enligt födelseår"].append(f"{km}: {namn(r)} född {r['birth']}")
            if not r["club"] or r["club"] == "Okänd klubb":
                fel["Resultat utan klubb"].append(f"{km}: {namn(r)}")
        for (k, d, s), n in sedda.items():
            if n > 1:
                fel["Samma simmare två gånger i samma gren och KM"].append(f"{km}: {k[0]} {k[1]}, {d} m {s} ({n} gånger)")
    for (f, l), v in namn_varianter.items():
        if len(v) > 1:
            fel["Samma namn med olika födelseår eller kön (kan vara olika personer eller felstavning)"].append(
                f"{f.title()} {l.title()}: " + ", ".join(f"{b}/{g}" for b, g in sorted(v)))
    return fel


def rs_all(m):
    return m["results"]


CSS = """
:root{color-scheme:light}
body{font:13px/1.45 system-ui,Segoe UI,Arial,sans-serif;color:#0f2230;margin:0;background:#f3f6f8}
main{max-width:1100px;margin:0 auto;padding:24px 16px 60px}
h1{font-size:26px;margin:0 0 4px} h2{font-size:19px;margin:34px 0 8px;padding-top:10px;border-top:3px solid #0a6b93}
h3{font-size:16px;margin:22px 0 6px} h4{font-size:14px;margin:0 0 4px}
.muted{color:#5b6f7d;font-weight:400} .sub{color:#5b6f7d;margin:0 0 14px}
table{border-collapse:collapse;width:100%;background:#fff;margin:4px 0 14px}
th,td{padding:4px 8px;border-bottom:1px solid #d7e0e6;text-align:left;vertical-align:top}
th{background:#e8f0f4;font-size:11px;text-transform:uppercase;letter-spacing:.05em}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.event{break-inside:avoid;margin-bottom:12px}
.ok{background:#e4f3ea;border-left:4px solid #2f7d4f;padding:8px 12px;margin:6px 0}
.warn{background:#fbf1c9;border-left:4px solid #e2b714;padding:8px 12px;margin:8px 0}
.warn ul{margin:4px 0 0 18px;padding:0}
nav a{margin-right:14px}
@media print{body{background:#fff;font-size:10.5px} main{padding:0} h2{break-before:page} h2:first-of-type{break-before:auto}
 tr{break-inside:avoid} nav{display:none}}
"""


def bygg(meets):
    total = sum(len(m["results"]) for m in meets)
    ant_sim = len({nyckel(r) for m in meets for r in m["results"]})
    delar = [f"<h1>Granskning av resultatdata</h1>",
             f'<p class="sub">{len(meets)} KM, {total} resultat, {ant_sim} simmare. Granskade filer: '
             f'{esc(", ".join(m["fil"] for m in meets))}. Läst från data/, alltså exakt det som publiceras på hemsidan.</p>',
             '<nav><a href="#o">Översikt</a><a href="#g">Grenar</a><a href="#r">Rangordning</a>'
             '<a href="#s">Simmare</a><a href="#k">Kontroller</a></nav>',
             '<h2 id="o">1. Översikt per KM</h2>', oversikt(meets),
             '<h2 id="g">2. Grenar och antal startande</h2>']
    for m in meets:
        delar += [f'<h3>{esc(m["meet"]["name"])} <span class="muted">{esc(m["meet"]["date"])}</span></h3>', grenoversikt(m)]
    delar.append('<h2 id="r">3. Rangordning per gren</h2>')
    for m in meets:
        delar += [f'<h3>{esc(m["meet"]["name"])}</h3>', grenlistor(m)]
    tab, n = simmarlista(meets)
    delar += [f'<h2 id="s">4. Alla simmare ({n})</h2>', tab, '<h2 id="k">5. Kontroller</h2>']
    fel = kontroller(meets)
    if not fel:
        delar.append('<div class="ok">Inga avvikelser hittades.</div>')
    for rubrik, rader in fel.items():
        delar.append(f'<div class="warn"><strong>{esc(rubrik)}: {len(rader)}</strong><ul>'
                     + "".join(f"<li>{esc(x)}</li>" for x in rader[:50])
                     + (f"<li>… och {len(rader) - 50} till</li>" if len(rader) > 50 else "") + "</ul></div>")
    return (f'<!doctype html><html lang="sv"><head><meta charset="utf-8"><title>Granskning</title>'
            f'<style>{CSS}</style></head><body><main>' + "\n".join(delar) + "</main></body></html>"), fel


def main():
    meets = valj(las_data())
    UT.mkdir(exist_ok=True)
    sida, fel = bygg(meets)
    html_fil = UT / "rapport.html"
    html_fil.write_text(sida, encoding="utf-8")
    print(f"Rapport: {html_fil}")
    print("\nKontroller:", "inga avvikelser" if not fel else f"{sum(len(v) for v in fel.values())} avvikelser")
    for rubrik, rader in fel.items():
        print(f"  {len(rader):3d}  {rubrik}")
    if "--nopen" not in sys.argv:
        webbrowser.open(html_fil.resolve().as_uri())


if __name__ == "__main__":
    main()
