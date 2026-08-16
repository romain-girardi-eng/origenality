#!/usr/bin/env python3
"""Build records.jsonl, sections.json and REPORT.md from the fetched Adamantius pages."""
import os, re, json, html, unicodedata, collections, datetime

SCR = os.path.dirname(os.path.abspath(__file__))
# Chemins relatifs au dépôt : un chemin absolu de machine rendait le
# moissonneur injouable ailleurs (critère D4, reproductibilité).
_HERE = os.path.dirname(os.path.abspath(__file__))
_BASE = os.path.dirname(_HERE)
OUTDIR = os.path.join(_BASE, "data", "raw", "adamantius")
os.makedirs(OUTDIR, exist_ok=True)

import sys
sys.path.insert(0, SCR)
from adam_authors import split_authors
from adam_parse import parse_file, HTMLDIR
from adam_lang import guess_language

# ---------------------------------------------------------------- reference
JOURNAL = re.compile(
    r"(?:,\s*|=\s*|[?!.]\s+)((?:in\s+)?[`'\"]?[A-ZÀ-Þ][^,]*?[`'\"]?,?\s*\d+(?:[/,]\d+)?\s*"
    r"\(\s*\d{4}(?:[-/]\d{2,4})?\s*\)\s*,?\s*[\dIVXL]+(?:\s*[-–]\s*[\dIVXL]+)?)\s*\.?\s*$")
MONO = re.compile(r",\s*([^,]+,\s*[^,]*\b\d{4}\b[^,]*(?:,\s*[^,]*\d{4})?,\s*(?:pp?\.|coll?\.)\s*[^,]*?)\s*\.?\s*$")
INVOL = re.compile(r",\s*([^,]+,\s*[^,]*\b\d{4}\b\s*,\s*[\dIVXL]+\s*[-–]\s*[\dIVXL]+)\s*\.?\s*$")
PLACEYEAR = re.compile(r",\s*([^,]+,\s*[^,]*\b(?:19|20)\d{2}\b)\s*\.?\s*$")
PAGES = re.compile(r",\s*((?:pp?\.\s*)?[\dIVXL]+\s*[-–]\s*[\dIVXL]+)\s*\.?\s*$")
REF_PATS = [("journal", JOURNAL), ("monograph", MONO), ("in_volume", INVOL),
            ("place_year", PLACEYEAR), ("pages_only", PAGES)]


TRAILNOTE = re.compile(r"\s*\((?:con bibl\.|pro manuscripto|[^()]{0,40}(?:bibl|rist|repr|réimpr|trad|reprint)[^()]{0,40})\)\s*\.?\s*$", re.I)
INANCHOR = re.compile(r",\s+in\s+(?=[`'\"A-ZÀ-Þ])")


def split_notice(notizia, autore_raw):
    """Strip the leading author prefix, then peel a trailing reference.
    Returns (title, reference, note, method). Never invents text: every piece
    returned is a verbatim substring of the notice."""
    body = notizia.strip()
    if autore_raw:
        a = autore_raw.strip().rstrip(",")
        if body.startswith(a):
            body = body[len(a):].lstrip(" ,")
        else:
            # the notice often separates the same names with dashes or commas
            # ('Hengel M.-Schwemer A.M.' vs the Autore field 'Hengel M. Schwemer A.M.')
            pat = r"\s*[-–,]?\s*".join(re.escape(t) for t in a.split())
            m = re.match(pat + r"\s*(?:\([^)]{0,24}\))?\s*[,.]\s*", body)
            if m and m.end() < len(body):
                body = body[m.end():]
    note = None
    mn = TRAILNOTE.search(body)
    if mn:
        note = mn.group(0).strip(" .")
        body = body[:mn.start()].rstrip(" ,.")
    ref, method = None, "none"
    for name, pat in REF_PATS:
        m = pat.search(body)
        if m:
            head = body[:m.start(1)].rstrip(" ,=")
            if not head.strip():      # peeling would leave no title -> keep the notice whole
                continue
            ref = m.group(1).strip(" ,")
            body = head
            method = name
            break
    # an in-volume/monograph tail usually belongs to a ", in <volume>, ..." block:
    # pull that block into the reference so the title stops at the article title.
    if method in ("in_volume", "monograph", "pages_only", "place_year"):
        anchors = list(INANCHOR.finditer(body))
        if anchors:
            a = anchors[-1]
            ref = (body[a.end():].strip(" ,") + ", " + ref).strip(" ,")
            body = body[:a.start()]
            method += "_anchored"
    return body.strip(" ,"), ref, note, method


# ---------------------------------------------------------------- dedup key
def norm_key(s):
    s = unicodedata.normalize("NFKD", s or "").lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    raws = []
    missing = []
    for i in range(1, 5101):
        p = os.path.join(HTMLDIR, "%05d.html" % i)
        if not os.path.exists(p):
            missing.append(i)
            continue
        r = parse_file(p)
        if r:
            raws.append(r)
    print("pages present=%d  parsed_records=%d  missing_pages=%d" % (5100 - len(missing), len(raws), len(missing)))

    # ---- dedup
    merged = collections.OrderedDict()
    for r in sorted(raws, key=lambda x: x["scheda"]):
        key = norm_key(r["notizia"])
        if not key:
            key = "scheda-%d" % r["scheda"]
        if key not in merged:
            merged[key] = {"first": r, "schede": [], "sections": [], "vols": [],
                           "years": [], "abstracts": []}
        m = merged[key]
        m["schede"].append(r["scheda"])
        sec = {"sezione": r["sezione"], "sottosezione": r["sottosezione"]}
        if sec not in m["sections"]:
            m["sections"].append(sec)
        if r["codice_volume"] not in m["vols"]:
            m["vols"].append(r["codice_volume"])
        if r["anno"] and r["anno"] not in m["years"]:
            m["years"].append(r["anno"])
        if r["abstract"] and r["abstract"] not in m["abstracts"]:
            m["abstracts"].append(r["abstract"])

    records, methods = [], collections.Counter()
    for key, m in merged.items():
        r = m["first"]
        title, ref, note, method = split_notice(r["notizia"], r["autore_raw"])
        methods[method] += 1
        abstract = m["abstracts"][0] if m["abstracts"] else None
        lang = guess_language(title)
        vol_years = sorted({v.split("-")[-1] for v in m["vols"] if "-" in v})
        rec = {
            "source": "adamantius-girota",
            "source_id": "adamantius-girota-%d" % r["scheda"],
            "sections": m["sections"],
            "year_bib": r["anno"] or None,
            "year_bib_parsed": [int(y) for y in re.findall(r"\b(?:1[89]|20)\d{2}\b", r["anno"] or "")],
            "authors": split_authors(r["autore_raw"]),
            "title": title or None,
            "reference": ref,
            "reference_note": note,
            "language": lang,
            "abstract": abstract,
            "abstract_rights": "girota-unverified",
            # provenance / non-lossy extras
            "authors_raw": r["autore_raw"] or None,
            "notice_full": r["notizia"],
            "reference_split_method": method,
            "scheda_ids": sorted(m["schede"]),
            "volume_codes": sorted(m["vols"]),
            "volume_years": vol_years,
            "years_seen": sorted(m["years"]),
            "pdf": r["pdf"],
            "url": "http://www2.classics.unibo.it/adamantius/index.php?page=schedasingola&schedavis=%d" % r["scheda"],
        }
        records.append(rec)

    records.sort(key=lambda x: x["scheda_ids"][0])
    with open(os.path.join(OUTDIR, "records.jsonl"), "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("records written:", len(records), "| dedup removed:", len(raws) - len(records))
    print("reference split:", dict(methods))

    json.dump({"raws": len(raws), "records": len(records), "missing": missing,
               "methods": dict(methods)},
              open(os.path.join(SCR, "build_stats.json"), "w"), ensure_ascii=False)
    json.dump(records, open(os.path.join(SCR, "records_mem.json"), "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
