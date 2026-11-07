"""Läs in Lenex-filer (.lef/.lxf), filtrera resultaten och spara dem som CSV/JSON.

Ändra inställningarna i avsnittet INSTÄLLNINGAR nedan och kör:

    python lenex_extract.py                  # läser alla filer i mappen results
    python lenex_extract.py fil1.lxf         # läser en specifik fil (du kan också dra filen på skriptet)

Resultaten sparas i mappen utdata, med filnamn som börjar med namnet på den inlästa filen.

Skriptet tar med alla simmare som deltagit i någon gren. Det finns inga krav på antal KM eller lopp
och inget urval: sådana filter väljer besökaren på hemsidan (index.html).
Endast Pythons standardbibliotek behövs.
"""
import csv
import glob
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

# ======================================================================
# INSTÄLLNINGAR - ändra bara det du behöver
# ======================================================================

# --- Vilka resultat ska med? -------------------------------------------
MIN_STARTANDE_PER_GREN = 5    # grenar med färre startande tas bort
HOPPA_OVER_T_O_M_ALDER = 12   # åldersklasser upp till och med denna ålder tas bort (None = ta med alla)

# --- Visning av listorna i utdata ----------------------------------------
BARA_BASTA_RESULTAT = False   # True = i resultatlistan bara varje simmares bästa resultat
VISA_TOPP = None              # t.ex. 10 för topp 10 (gäller både simmare och resultatlista)

# ----------------------------------------------------------------------
# Fasta val som sällan behöver ändras
# ----------------------------------------------------------------------
INDATA = ["results/*.lef", "results/*.lxf"]   # används om du inte anger filer när du kör skriptet
UTMAPP = "utdata"
DATA_MAPP = "data"           # slimmad data som publiceras med hemsidan
UTFORMAT = ["csv"]
CSV_SEPARATOR = ";"           # fungerar direkt i svensk Excel
SKRIV_BORTTAGNA = True        # sparar även en lista över borttagna resultat med orsak
TA_BORT_STATUS = {"EXH"}      # utom tävlan tas alltid bort
INTE_STARTANDE = {"DNS", "WDR"}
MED_STAFETTER = False
VISA_TOPP_LOPP = VISA_TOPP    # samma topp-gräns för resultatlistan
TAVLINGSNAMN_RENSA = r"\s*&\s*Medleycupen.*$"   # "KM 4 & Medleycupen 4" blir "KM 4"

# ======================================================================
# Här börjar själva koden. Behöver normalt inte ändras.
# ======================================================================

STROKE_SV = {"FREE": "Frisim", "BACK": "Ryggsim", "BREAST": "Bröstsim",
             "FLY": "Fjärilsim", "MEDLEY": "Medley", "IMRELAY": "Lagmedley"}
STROKE_ORDER = list(STROKE_SV)


def alder_klass(alder):
    """Klasserna som används i Lenex-filen och på hemsidan."""
    if not alder or alder <= 12:
        return ""
    if alder >= 20:
        return "20+"
    if alder >= 17:
        return "17-19"
    if alder >= 15:
        return "15-16"
    return "13-14"


def tid_sekunder(s):
    m = re.match(r"^(\d+):(\d+):(\d+)(?:\.(\d+))?$", (s or "").strip())
    if not m:
        return None
    frac = int((m.group(4) or "0").ljust(2, "0")[:2])
    return (int(m.group(1)) * 60 + int(m.group(2))) * 60 + int(m.group(3)) + frac / 100


def tid_text(sek):
    if sek is None:
        return ""
    cs = round(sek * 100)
    h, rest = divmod(cs, 360000)
    m, rest = divmod(rest, 6000)
    s, c = divmod(rest, 100)
    if h:
        return f"{h}:{m:02d}:{s:02d}.{c:02d}"
    if m:
        return f"{m}:{s:02d}.{c:02d}"
    return f"{s}.{c:02d}"


def int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def las_xml(sokvag):
    """Returnerar XML-texten i en .lef/.xml eller i en .lxf/.zip."""
    p = Path(sokvag)
    if p.suffix.lower() in (".lxf", ".zip"):
        with zipfile.ZipFile(p) as z:
            namn = next((n for n in z.namelist() if re.search(r"\.(lef|xml)$", n, re.I)), None)
            if not namn:
                raise ValueError(f"{p.name} innehåller ingen .lef-fil.")
            return z.read(namn)
    return p.read_bytes()


def tavlingsnamn(namn):
    return re.sub(TAVLINGSNAMN_RENSA, "", namn, flags=re.I).strip() if TAVLINGSNAMN_RENSA else namn.strip()


def las_fil(sokvag):
    """Läser alla individuella resultat i filen. Returnerar en lista med dictar."""
    root = ET.fromstring(las_xml(sokvag))
    rader = []
    for meet in root.iter("MEET"):
        tnamn = tavlingsnamn(meet.get("name") or Path(sokvag).stem)
        ses_datum = {}
        events = {}
        for ses in meet.iter("SESSION"):
            for ev in ses.iter("EVENT"):
                ss = ev.find("SWIMSTYLE")
                events[ev.get("eventid")] = {
                    "distans": ss.get("distance") if ss is not None else "",
                    "simsatt": ss.get("stroke") if ss is not None else "",
                    "stafett": int_or_none(ss.get("relaycount") if ss is not None else 1) or 1,
                    "kon": ev.get("gender") or "",
                    "datum": ses.get("date") or "",
                    "bana": ses.get("course") or meet.get("course") or "",
                }
        datum0 = next(iter(events.values()), {}).get("datum", "")
        # Åldersklass och placering per resultat
        klass, placering = {}, {}
        for ev in meet.iter("EVENT"):
            for ag in ev.iter("AGEGROUP"):
                for rk in ag.iter("RANKING"):
                    p = int_or_none(rk.get("place"))
                    klass[rk.get("resultid")] = (int_or_none(ag.get("agemin")), int_or_none(ag.get("agemax")))
                    placering[rk.get("resultid")] = p if p and p > 0 else None
        for club in meet.findall("./CLUBS/CLUB"):
            klubb = club.get("name") or club.get("shortname") or "Okänd klubb"
            for ath in club.findall("./ATHLETES/ATHLETE"):
                fornamn, efternamn = ath.get("firstname") or "", ath.get("lastname") or ""
                fodd = (ath.get("birthdate") or "")[:4]
                kon = ath.get("gender") or ""
                for res in ath.findall("./RESULTS/RESULT"):
                    ev = events.get(res.get("eventid"), {})
                    status = res.get("status") or ""
                    datum = ev.get("datum") or datum0
                    alder = (int(datum[:4]) - int(fodd)) if datum[:4].isdigit() and fodd.isdigit() else None
                    amin, amax = klass.get(res.get("resultid"), (None, None))
                    poang = int_or_none(res.get("points"))
                    sek = tid_sekunder(res.get("swimtime"))
                    rader.append({
                        "fil": Path(sokvag).name,
                        "tavling": tnamn,
                        "datum": datum,
                        "grenid": f"{Path(sokvag).name}|{meet.get('name')}|{res.get('eventid')}",
                        "stafett": ev.get("stafett", 1) > 1,
                        "fornamn": fornamn, "efternamn": efternamn,
                        "namn": f"{fornamn} {efternamn}".strip(),
                        "fodd": fodd, "kon": kon, "klubb": klubb,
                        "distans": ev.get("distans", ""), "simsatt": ev.get("simsatt", ""),
                        "gren": f"{ev.get('distans', '')} {ev.get('simsatt', '')}".strip(),
                        "bana": ev.get("bana", ""),
                        "status": status,
                        "tid_sek": None if (status and status != "EXH") else sek,
                        "poang": poang if (not status or status == "EXH") and poang is not None else 0,
                        "placering": placering.get(res.get("resultid")),
                        "alder": alder, "klass_min": amin, "klass_max": amax,
                        "ak": alder_klass(amin if amin and amin > 0 else alder),
                        "ung": (amax is not None and 0 <= amax <= (HOPPA_OVER_T_O_M_ALDER or -1))
                               or (not (amin and amin > 0) and alder is not None
                                   and 0 < alder <= (HOPPA_OVER_T_O_M_ALDER or -1)),
                    })
    return rader


def filtrera(rader):
    """Returnerar (kvar, borttagna) där borttagna är (rad, orsak)."""
    borta = []

    def ta_bort(r, orsak):
        borta.append((r, orsak))

    # 1. Fasta regler
    steg1 = []
    for r in rader:
        if r["stafett"] and not MED_STAFETTER:
            ta_bort(r, "stafett")
        elif r["status"] in TA_BORT_STATUS:
            ta_bort(r, f"status {r['status']}")
        elif HOPPA_OVER_T_O_M_ALDER is not None and r["ung"]:
            ta_bort(r, f"{HOPPA_OVER_T_O_M_ALDER} år eller yngre")
        else:
            steg1.append(r)

    # 2. Startande per gren (alla åldersklasser räknas ihop)
    startande = {}
    for r in steg1:
        if r["status"] not in INTE_STARTANDE:
            startande[r["grenid"]] = startande.get(r["grenid"], 0) + 1
    steg2 = []
    for r in steg1:
        n = startande.get(r["grenid"], 0)
        if n < MIN_STARTANDE_PER_GREN:
            ta_bort(r, f"färre än {MIN_STARTANDE_PER_GREN} startande i grenen ({n})")
        else:
            steg2.append(r)

    return steg2, borta


def simmare_nyckel(r):
    return f"{r['fornamn']}|{r['efternamn']}|{r['fodd']}|{r['kon']}".lower().strip()


def sammanstall_simmare(rader):
    """En rad per simmare med alla som deltagit på något KM i någon gren. Inga krav på antal KM eller lopp.

    Rangordning efter antal KM och lopp görs på hemsidan, där besökaren kan välja kraven själv.
    """
    per = {}
    for r in rader:
        per.setdefault(simmare_nyckel(r), []).append(r)
    ut = []
    for rs in per.values():
        giltiga = sorted((r for r in rs if r["poang"] > 0), key=lambda r: -r["poang"])
        summa = sum(r["poang"] for r in giltiga)
        senaste = max(rs, key=lambda r: r["datum"])
        ut.append({
            "namn": rs[0]["namn"], "fodd": rs[0]["fodd"], "kon": rs[0]["kon"], "klubb": senaste["klubb"],
            "ak": senaste["ak"],
            "antal_km": len({(r["tavling"], r["datum"]) for r in rs}), "starter": len(rs),
            "hogsta_poang": giltiga[0]["poang"] if giltiga else 0,
            "basta_gren": giltiga[0]["gren"] if giltiga else "",
            "snitt_per_lopp": round(summa / len(giltiga)) if giltiga else 0, "summa_poang": summa,
        })
    ut.sort(key=lambda s: -s["summa_poang"])
    return ut[:VISA_TOPP] if VISA_TOPP else ut


def lopplista(rader):
    """Som fliken Alla lopp."""
    if BARA_BASTA_RESULTAT:
        basta = {}
        for r in rader:
            k = simmare_nyckel(r)
            if k not in basta or r["poang"] > basta[k]["poang"]:
                basta[k] = r
        rader = list(basta.values())
    rader = sorted(rader, key=lambda r: -r["poang"])
    return rader[:VISA_TOPP_LOPP] if VISA_TOPP_LOPP else rader


LOPP_KOLUMNER = [("tavling", "Tävling"), ("datum", "Datum"), ("namn", "Namn"), ("fodd", "Född"), ("kon", "Kön"),
                 ("klubb", "Klubb"), ("ak", "Åldersklass"), ("gren", "Gren"),
                 ("bana", "Bana"), ("tid", "Tid"), ("status", "Status"), ("placering", "Placering"),
                 ("poang", "Poäng")]
SIMMARE_KOLUMNER = [("namn", "Namn"), ("fodd", "Född"), ("kon", "Kön"), ("klubb", "Klubb"), ("ak", "Åldersklass"),
                    ("antal_km", "KM"), ("starter", "Starter"), ("hogsta_poang", "Högsta"),
                    ("basta_gren", "Bästa gren"), ("snitt_per_lopp", "Snitt per lopp"),
                    ("summa_poang", "Summa poäng")]


def lopp_rad(r):
    return {**r, "tid": tid_text(r["tid_sek"])}


def skriv(namn, kolumner, rader):
    ut = Path(UTMAPP)
    ut.mkdir(parents=True, exist_ok=True)
    if "csv" in UTFORMAT:
        with open(ut / f"{namn}.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=CSV_SEPARATOR)
            w.writerow([k[1] for k in kolumner])
            for r in rader:
                w.writerow(["" if r.get(k[0]) is None else r.get(k[0]) for k in kolumner])
    if "json" in UTFORMAT:
        with open(ut / f"{namn}.json", "w", encoding="utf-8") as f:
            json.dump([{k[1]: r.get(k[0]) for k in kolumner} for r in rader], f, ensure_ascii=False, indent=2)
    print(f"  {namn}: {len(rader)} rader -> {ut / namn}.{'/'.join(UTFORMAT)}")


def skriv_webbdata(rader):
    """Skriver den slimmade datan som hemsidan läser, en fil per KM, plus data/index.json.

    Bara det som visas på sidan tas med: namn, födelseår, kön, klubb, gren, tid, poäng och åldersklass.
    Licensnummer, fullständigt födelsedatum, mellantider och allt som filtrerats bort publiceras aldrig.
    """
    per = {}
    for r in rader:
        if r["status"] in INTE_STARTANDE:
            continue
        per.setdefault((r["tavling"], r["datum"], r["bana"]), []).append(r)
    ut = Path(DATA_MAPP)
    ut.mkdir(exist_ok=True)
    for (namn, datum, bana), rs in per.items():
        fil = re.sub(r"[^A-Za-z0-9]+", "_", f"{namn}_{datum}").strip("_") + ".json"
        data = {"version": 1, "meet": {"name": namn, "date": datum, "course": bana},
                "results": [{"first": r["fornamn"], "last": r["efternamn"], "birth": r["fodd"], "gender": r["kon"],
                             "club": r["klubb"], "distance": r["distans"], "stroke": r["simsatt"],
                             "time": None if r["tid_sek"] is None else round(r["tid_sek"] * 100),
                             "status": r["status"], "points": r["poang"], "cls": r["ak"]} for r in rs]}
        with open(ut / fil, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        print(f"  hemsidan: {len(rs)} resultat -> {ut / fil}")
    filer = sorted(p.name for p in ut.glob("*.json") if p.name != "index.json")
    with open(ut / "index.json", "w", encoding="utf-8") as f:
        json.dump(filer, f, ensure_ascii=False)


def main():
    if not sys.argv[1:]:
        Path("results").mkdir(exist_ok=True)   # hela mappen ignoreras av git, så den finns inte i en ny kopia
    monster = sys.argv[1:] or INDATA
    filer = sorted({p for m in monster for p in glob.glob(m)})
    if not filer:
        sys.exit(f"Hittade inga filer för {monster}. Lägg Lenex-filer (.lef/.lxf) i mappen results och kör igen.")
    rader = []
    for f in filer:
        try:
            n = las_fil(f)
            print(f"Läste {f}: {len(n)} resultat")
            rader += n
        except Exception as e:  # noqa: BLE001 - visa felet och gå vidare med övriga filer
            print(f"FEL i {f}: {e}")
    # Samma tävling inläst två gånger (samma namn och datum) räknas bara en gång.
    sedda, unika = set(), []
    for r in rader:
        k = (r["tavling"], r["datum"], r["namn"], r["fodd"], r["grenid"].split("|")[-1], r["tid_sek"], r["status"])
        if k not in sedda:
            sedda.add(k)
            unika.append(r)
    rader = unika

    kvar, borta = filtrera(rader)
    print(f"\n{len(rader)} resultat lästes, {len(kvar)} blev kvar, {len(borta)} togs bort.")
    orsaker = {}
    for _, o in borta:
        orsaker[o] = orsaker.get(o, 0) + 1
    for o, n in sorted(orsaker.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4d}  {o}")

    # Filnamnen baseras på den inlästa filen. Flera filer sparas tillsammans som "samlat".
    bas = Path(filer[0]).stem if len(filer) == 1 else "samlat"
    print("\nSparar:")
    skriv(f"{bas}_resultat", LOPP_KOLUMNER, [lopp_rad(r) for r in lopplista(kvar)])
    skriv(f"{bas}_simmare", SIMMARE_KOLUMNER, sammanstall_simmare(kvar))
    if SKRIV_BORTTAGNA:
        skriv(f"{bas}_borttagna", [("orsak", "Orsak")] + LOPP_KOLUMNER,
              [{**lopp_rad(r), "orsak": o} for r, o in borta])
    # Data till hemsidan: samma resultat som i resultatlistan, utan några krav på antal KM eller lopp.
    skriv_webbdata(kvar)


if __name__ == "__main__":
    main()
