#!/usr/bin/env python3
"""Phase 2 — hydrate les PPN via le SRU K10plus (MARCXML), sans le mur PoW.

Endpoint : https://sru.k10plus.de/opac-de-627
Requetes groupees (pica.ppn=A or pica.ppn=B ...) par paquets de 50.
Sauvegarde incrementale : records.jsonl reecrit depuis un cache JSON par PPN.
Les PPN sans reponse SRU sont journalises dans failed_ppns.json.
"""
import json, os, sys, time
import urllib.request, urllib.parse, urllib.error
import xml.etree.ElementTree as ET

# Chemins relatifs au dépôt : un chemin absolu de machine rendait le
# moissonneur injouable ailleurs (critère D4, reproductibilité).
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import marc_text  # noqa: E402
_BASE = os.path.dirname(_HERE)
OUT_DIR = os.path.join(_BASE, "data", "raw", "ixtheo")
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "sru_cache.jsonl")
LOG = os.path.join(HERE, "hydrate.log")

SRU = "https://sru.k10plus.de/opac-de-627"
MARC = "{http://www.loc.gov/MARC21/slim}"
ZS = "{http://www.loc.gov/zing/srw/}"
BATCH = 50
SLEEP = 0.5


def log(msg):
    line = "%s  %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


# ---------- MARC helpers ----------
def subs(field, codes):
    out = []
    for sf in field.findall(MARC + "subfield"):
        if sf.get("code") in codes and sf.text:
            out.append(sf.text.strip())
    return out


def first(field, code):
    v = subs(field, code)
    return v[0] if v else None


def fields(rec, tag):
    return [f for f in rec.findall(MARC + "datafield") if f.get("tag") == tag]


def ctrl(rec, tag):
    for f in rec.findall(MARC + "controlfield"):
        if f.get("tag") == tag:
            return f.text or ""
    return ""


def clean(s):
    if not s:
        return s
    return s.strip().rstrip(" /:;,.").strip() or None


def parse_record(rec):
    ppn = ctrl(rec, "001").strip()

    # --- titre ---
    title = None
    for f in fields(rec, "245"):
        a = first(f, "a")
        b = first(f, "b")
        n = " ".join(subs(f, "np"))
        parts = [p for p in (clean(a), clean(n), clean(b)) if p]
        if parts:
            title = parts[0] if len(parts) == 1 else parts[0] + " : " + " ; ".join(parts[1:])
        break

    # --- auteurs (100/110/111 principal, 700/710/711 secondaires) ---
    authors = []
    for tag in ("100", "110", "111", "700", "710", "711"):
        for f in fields(rec, tag):
            name = clean(first(f, "a"))
            if not name:
                continue
            kind = ("person" if tag in ("100", "700")
                    else "meeting" if tag in ("111", "711") else "corporate")
            entry = {"name": name, "role": first(f, "4") or first(f, "e"), "type": kind}
            gnd = None
            for v in subs(f, "0"):
                if v.startswith("(DE-588)"):
                    gnd = v[len("(DE-588)"):]
            if gnd:
                entry["gnd"] = gnd
            entry["primary"] = tag.startswith("1")
            if entry not in authors:
                authors.append(entry)

    # --- annee ---
    year = None
    for tag in ("264", "260"):
        for f in fields(rec, tag):
            c = first(f, "c")
            if c:
                d = "".join(ch for ch in c if ch.isdigit())
                if len(d) >= 4:
                    year = int(d[:4])
                    break
        if year:
            break
    if year is None:
        d = ctrl(rec, "008")[7:11]
        if d.isdigit():
            year = int(d)

    # --- langue ---
    langs = []
    for f in fields(rec, "041"):
        langs += subs(f, "a")
    if not langs:
        l = ctrl(rec, "008")[35:38].strip()
        if l and l not in ("", "|||", "und"):
            langs = [l]
    language = langs[0] if langs else None

    # --- editeur / lieu ---
    publisher = place = None
    for tag in ("264", "260"):
        for f in fields(rec, tag):
            publisher = publisher or clean(first(f, "b"))
            place = place or clean(first(f, "a"))
        if publisher:
            break

    # --- contenant : 773 (revue / collectif) puis 490/830 (collection) ---
    container = None
    for f in fields(rec, "773"):
        t = clean(first(f, "t")) or clean(first(f, "a"))
        g = subs(f, "g")
        issn = None
        host_ppn = None
        for x in subs(f, "x"):
            issn = issn or x
        for w in subs(f, "w"):
            if w.startswith("(DE-627)"):
                host_ppn = w[len("(DE-627)"):]
        if t or g:
            container = {"type": "host", "title": t, "details": g or None,
                         "issn": issn, "host_ppn": host_ppn}
            break
    if container is None:
        for tag in ("490", "830"):
            for f in fields(rec, tag):
                t = clean(first(f, "a"))
                if t:
                    container = {"type": "series", "title": t,
                                 "details": subs(f, "v") or None,
                                 "issn": first(f, "x"), "host_ppn": None}
                    break
            if container:
                break

    # --- DOI / ISBN ---
    doi = None
    for f in fields(rec, "024"):
        if (first(f, "2") or "").lower() == "doi":
            doi = clean(first(f, "a"))
            break
    isbns = []
    for f in fields(rec, "020"):
        v = clean(first(f, "a"))
        if v:
            isbns.append(v)

    # --- abstract (520) ---
    abstract = None
    for f in fields(rec, "520"):
        a = " ".join(subs(f, "a"))
        if a and len(a) > len(abstract or ""):
            abstract = a.strip()

    # --- vedettes matiere (650 / 689) : le coeur de l'indexation IxTheo ---
    subjects = []
    for f in fields(rec, "650"):
        v = clean(first(f, "a"))
        if v and v not in subjects:
            subjects.append(v)
    chains = []
    for f in fields(rec, "689"):
        v = clean(first(f, "a"))
        if v and v not in chains:
            chains.append(v)

    # --- format de repli depuis le leader ---
    ldr = rec.findtext(MARC + "leader") or ""
    marc_type = ldr[6:8] if len(ldr) > 7 else None

    return {"ppn": ppn, "title": title, "authors": authors, "year": year,
            "language": language, "languages": langs or None, "container": container,
            "publisher": publisher, "place": place, "doi": doi,
            "isbn": isbns or None, "abstract": abstract,
            "subjects": subjects or None, "subject_chains": chains or None,
            "marc_type": marc_type}


# ---------- SRU ----------
def sru_batch(ppns, attempt=0):
    q = " or ".join("pica.ppn=%s" % p for p in ppns)
    url = ("%s?version=1.1&operation=searchRetrieve&query=%s&recordSchema=marcxml"
           "&maximumRecords=%d" % (SRU, urllib.parse.quote(q), len(ppns) + 10))
    req = urllib.request.Request(url, headers={
        "User-Agent": "Origenality research harvester (academic; romain.girardi@univ-cotedazur.fr)"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            body = r.read().decode("utf-8", "replace")
    except Exception as e:
        if attempt < 4:
            wait = 10 * (attempt + 1)
            log("  SRU erreur %s — attente %ds" % (e, wait))
            time.sleep(wait)
            return sru_batch(ppns, attempt + 1)
        raise
    root = ET.fromstring(body.encode("utf-8"))
    out = []
    for rd in root.iter(ZS + "recordData"):
        rec = rd.find(MARC + "record")
        if rec is not None:
            out.append(parse_record(rec))
    return out


def main():
    with open(os.path.join(OUT_DIR, "ppn_list.json")) as f:
        plist = json.load(f)
    rel_of = {e["ppn"]: e["relation"] for e in plist["ppns"]}
    rss_of = {e["ppn"]: e for e in plist["ppns"]}
    all_ppns = list(rel_of.keys())

    done = {}
    if os.path.exists(CACHE):
        with open(CACHE) as f:
            for line in f:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    done[r["ppn"]] = r
        log("cache : %d notices deja hydratees" % len(done))

    todo = [p for p in all_ppns if p not in done]
    log("a hydrater : %d / %d" % (len(todo), len(all_ppns)))

    t0 = time.time()
    with open(CACHE, "a") as cf:
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            recs = sru_batch(chunk)
            got = {r["ppn"] for r in recs}
            for r in recs:
                done[r["ppn"]] = r
                cf.write(json.dumps(r, ensure_ascii=False) + "\n")
            cf.flush()
            log("lot %d-%d : %d/%d notices" % (i, i + len(chunk), len(got), len(chunk)))
            time.sleep(SLEEP)
    log("hydratation terminee en %.0f s" % (time.time() - t0))

    # ---------- ecriture records.jsonl ----------
    missing = []
    n = 0
    with open(os.path.join(OUT_DIR, "records.jsonl"), "w") as out:
        for ppn in all_ppns:
            rss = rss_of[ppn]
            r = done.get(ppn)
            if r is None:
                # notice locale IxTheo, absente du SRU K10plus (numberOfRecords=0).
                # On ne conserve que ce que le flux RSS d'IxTheo a effectivement renvoye.
                missing.append(ppn)
                r = {"title": None, "authors": [], "year": None, "language": None,
                     "languages": None, "container": None, "publisher": None,
                     "place": None, "doi": None, "isbn": None, "abstract": None,
                     "subjects": None, "subject_chains": None, "marc_type": None}
                hydration = "rss-only"
            else:
                hydration = "sru-marcxml"
            rec = {
                "source": "ixtheo-k10plus",
                "source_id": ppn,
                "relation": rel_of[ppn],
                "title": r["title"] or rss.get("rss_title") or None,
                "authors": r["authors"],
                "year": r["year"] if r["year"] is not None else (
                    int(rss["rss_year"]) if (rss.get("rss_year") or "").isdigit() else None),
                "language": r["language"],
                "languages": r["languages"],
                "container": r["container"],
                "publisher": r["publisher"],
                "place": r["place"],
                "doi": r["doi"],
                "isbn": r["isbn"],
                "format": rss.get("rss_format"),
                "marc_type": r["marc_type"],
                "subjects": r["subjects"],
                "subject_chains": r["subject_chains"],
                "abstract": r["abstract"],
                "abstract_rights": "editor-unverified",
                "ixtheo_url": "https://ixtheo.de/Record/%s" % ppn,
                "raw_marc_kept": False,
                "hydration": hydration,
            }
            # Artefacts d'export MARC (« ? » de substitution, délimiteur de
            # sous-zone resté collé, tiret conditionnel) : nettoyés ici, à
            # l'ingestion, et jamais au rendu.
            marc_text.normalise_record(rec)
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    with open(os.path.join(HERE, "failed_ppns.json"), "w") as f:
        json.dump({"count": len(missing), "ppns": missing}, f, indent=1)
    log("ECRIT records.jsonl : %d notices, %d PPN sans reponse SRU" % (n, len(missing)))


if __name__ == "__main__":
    main()
