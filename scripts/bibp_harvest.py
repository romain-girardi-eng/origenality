#!/usr/bin/env python3
"""BIBP harvester — limited technical sample.

Chain (3 request types, all offered by the site's own UI):
  1. POST /cgi-bin/bibp/recherche.cgi          -> result set + session tokens
  2. GET  /cgi-bin/bibp/recherche.cgi?next=... -> page N of the result set
  3. GET  /cgi-bin/bibp/affiche.cgi?tout=...   -> the FULL notices of that page
     (this is the site's own "afficher tout" button: one request per page,
      instead of one request per notice — the politest available path)

Politeness: 3 s between requests, identifiable academic User-Agent, page size
capped at 99 (the form's own maxlength=2 on `hits`).
No data is invented: every field is parsed from the server's HTML.
"""
import html as htmllib
import json, os, re, sys, time, urllib.parse, urllib.request

UA = "Origenality-Research/1.0 (PhD thesis, Univ. de Geneve; romain.girardi@univ-cotedazur.fr)"
BASE = "https://www4.bibl.ulaval.ca"
SEARCH = BASE + "/cgi-bin/bibp/recherche.cgi"
AFFICHE = BASE + "/cgi-bin/bibp/affiche.cgi"
DELAY = 3.0

# Chemins relatifs au dépôt : un chemin absolu de machine rendait le
# moissonneur injouable ailleurs (critère D4, reproductibilité).
_HERE = os.path.dirname(os.path.abspath(__file__))
_BASE = os.path.dirname(_HERE)
OUT_DIR = os.path.join(_BASE, "data", "raw", "bibp")
os.makedirs(OUT_DIR, exist_ok=True)

_req_count = 0


def get(url):
    global _req_count
    _req_count += 1
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read().decode("iso-8859-1", "replace")


def post_search(terme1, champ1, hits=99, tri="Année"):
    global _req_count
    _req_count += 1
    fields = [
        # Le formulaire de BIBP porte un champ « maintainer » qui voyage avec la
        # requête. L'adresse nominative du responsable de la base y figurait,
        # recopiée du formulaire public : elle est remplacée par l'adresse de
        # contact du projet, qui est celle à laquelle il faut écrire si la
        # moisson dérange.
        ("bd", "bibp"), ("maintainer", "romain.girardi@univ-cotedazur.fr"),
        ("terme1", terme1), ("champ1", champ1), ("op1", "AND"),
        ("terme2", ""), ("champ2", "Tous les champs"), ("op2", "AND"),
        ("terme3", ""), ("champ3", "Tous les champs"), ("op3", "AND"),
        ("terme4", ""), ("champ4", "Tous les champs"),
        ("accents", "non"), ("langue", "Toutes les langues"),
        ("discipline", "Toutes les disciplines"),
        ("hits", str(hits)), ("tri", tri),
    ]
    body = urllib.parse.urlencode(fields, encoding="iso-8859-1", errors="replace").encode("ascii")
    req = urllib.request.Request(SEARCH, data=body, headers={
        "User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "text/html", "Referer": BASE + "/bd/bibp/recherche.html"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read().decode("iso-8859-1", "replace")


def parse_count(h):
    m = re.search(r"<B>(\d+)\s+documents? correspondent", h)
    return int(m.group(1)) if m else None


def tokens(h):
    t = re.search(r"affiche\.cgi\?tout=(aff\d+\.txt)", h)
    n = re.search(r"next=(res\d+\.txt)", h)
    return (t.group(1) if t else None, n.group(1) if n else None)


def clean(s):
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = htmllib.unescape(s)
    return re.sub(r"[ \t\xa0]+", " ", s).strip()


ROW_RE = re.compile(
    r"<TH[^>]*BGCOLOR=\"#CCCCCC\"[^>]*>(.*?)</TH>(.*?)(?=<TR>\s*<TH[^>]*BGCOLOR=\"#CCCCCC\"|</TABLE>)",
    re.S | re.I)
CELL_RE = re.compile(r"<TD[^>]*>(.*?)</TD>", re.S | re.I)


def parse_notices(page_html):
    """Split the 'afficher tout' page into per-notice field dicts."""
    notices = []
    # each notice is one <TABLE ...> whose first TH label is the doc type
    for tbl in re.findall(r"<TABLE width=\"100%\"[^>]*>(.*?)</TABLE>", page_html, re.S | re.I):
        if "Numéro du document" not in tbl:
            continue
        rec, order = {}, []
        for m in ROW_RE.finditer(tbl + "</TABLE>"):
            label = clean(m.group(1))
            cells = [clean(c) for c in CELL_RE.findall(m.group(2))]
            if not label:
                continue
            rec.setdefault(label, []).extend([c for c in cells if c])
            order.append(label)
        if rec.get("Numéro du document"):
            rec["_order"] = order
            notices.append(rec)
    return notices


def split_desc(s):
    return [t.strip() for t in re.split(r"[;\n]", s) if t.strip()]


# Label carrying the title; also tells the document type.
TITLE_LABELS = [("Article", "article"), ("Titre (monographie)", "monograph"),
                ("Livre", "book"), ("Recension", "review"),
                ("Chapitre", "chapter"), ("Thèse", "thesis")]
AUTHOR_LABELS = ["Auteur(s)", "Auteurs"]


def parse_ids(h):
    """Row handles (`no=`) from a results list. NOT the stable notice number."""
    return re.findall(r"affiche\.cgi\?bd=bibp&tri=\w+&no=(\d+)", h)


def normalize(rec, query_label, retrieval_no=None):
    label, doctype = next(((l, d) for l, d in TITLE_LABELS if l in rec), (None, None))
    title = rec.get(label, [None])[0] if label else None
    no = rec.get("Numéro du document", [None])[0]
    authors_raw = []
    for al in AUTHOR_LABELS:
        for cell in rec.get(al, []):
            authors_raw.extend(a.strip() for a in re.split(r"[;\n]", cell) if a.strip())
    ref = (rec.get("Référence") or
           rec.get("Date de publication et pages concernées") or [None])[0]
    year = None
    if ref:
        m = re.search(r"\((\d{4})\)", ref) or re.search(r"\b(1[89]\d{2}|20\d{2})\b", ref)
        if m:
            year = int(m.group(1))
    if year is None and rec.get("Année"):
        digits = re.sub(r"\D", "", rec["Année"][0])[:4]
        year = int(digits) if len(digits) == 4 else None

    # Descriptor cells hold up to two <br>-separated lines:
    #   line 0 = indexing in the document's own language, line 1 = French equivalents.
    descriptors = []
    for label, weight in (("Descripteurs primaires", "primary"),
                          ("Descripteurs secondaires", "secondary")):
        for cell in rec.get(label, []):
            lines = [l for l in cell.split("\n") if l.strip()]
            for li, line in enumerate(lines):
                lang = "original" if li == 0 else "fr"
                for term in split_desc(line):
                    descriptors.append({"term": term, "weight": weight,
                                        "index_language": lang})

    abstract = "\n".join(rec.get("Résumé", [])) or None
    disciplines = []
    for c in rec.get("Disciplines concernées", []):
        disciplines.extend([d.strip() for d in c.split("\n") if d.strip()])

    return {
        "source": "bibp",
        "source_id": no,
        "title": title,
        "authors": authors_raw,
        "year": year,
        "container": (rec.get("Titre du périodique") or rec.get("Éditeur(s)") or [None])[0],
        "language": (rec.get("Langue") or [None])[0],
        "descriptors": descriptors,
        "abstract": abstract,
        "abstract_rights": "bibp-unverified",
        "url": (f"{AFFICHE}?bd=bibp&tri=annee&no={retrieval_no}" if retrieval_no else None),
        # provenance / extra fields kept verbatim from the server
        "bibp_retrieval_no": retrieval_no,
        "doc_type": doctype,
        "reference": ref,
        "disciplines": disciplines,
        "documentaliste": (rec.get("Documentaliste") or [None])[0],
        "collection": (rec.get("Collection") or [None])[0],
        "isbn_issn": (rec.get("ISSN") or rec.get("ISBN") or [None])[0],
        "publisher": (rec.get("Éditeur(s)") or [None])[0],
        "place": (rec.get("Lieu(x) d'édition") or [None])[0],
        "remarks": (rec.get("Remarques") or rec.get("Complément") or [None])[0],
        "query_label": query_label,
        "reuse_notice": ("Il est interdit de reproduire le contenu de ces pages sans "
                         "l'autorisation de la Bibliotheque de l'Universite Laval et de "
                         "monsieur Rene-Michel Roberge (c)1998/2003"),
        "harvested_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def harvest(terme, champ, query_label, max_pages, hits=99):
    h = post_search(terme, champ, hits=hits)
    total = parse_count(h)
    print(f"[search] {query_label}: total={total}", flush=True)
    tout, nxt = tokens(h)
    ids = parse_ids(h)
    out, page = [], 1
    while tout and page <= max_pages:
        time.sleep(DELAY)
        full = get(f"{AFFICHE}?tout={urllib.parse.quote(tout)}&bd=bibp&tri=annee")
        cache = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             f"bibp_raw_page{page}.html")
        with open(cache, "w", encoding="utf-8") as fh:
            fh.write(full)
        notices = parse_notices(full)
        if len(ids) != len(notices):
            print(f"[warn] page {page}: {len(ids)} row handles vs {len(notices)} notices "
                  f"-> retrieval_no left null", flush=True)
            ids = [None] * len(notices)
        out.extend(normalize(n, query_label, ids[i]) for i, n in enumerate(notices))
        print(f"[page {page}] notices parsed = {len(notices)} (cumul {len(out)})", flush=True)
        if page >= max_pages or not nxt:
            break
        page += 1
        time.sleep(DELAY)
        h = get(f"{SEARCH}?bd=bibp&next={urllib.parse.quote(nxt)}&hits={hits}"
                f"&total={total}&tri=annee&page={page}")
        tout, nxt2 = tokens(h)
        ids = parse_ids(h)
        nxt = nxt2 or nxt
    return total, out


if __name__ == "__main__":
    max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    total, recs = harvest("ORIGENE", "Descripteurs primaires (tous les)",
                          "descripteurs_primaires=ORIGENE", max_pages)
    path = os.path.join(OUT_DIR, "records.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    stats = {
        "query_label": "descripteurs_primaires=ORIGENE",
        "total_matching_in_bibp": total,
        "pages_harvested": max_pages,
        "records_written": len(recs),
        "http_requests": _req_count,
        "with_abstract": sum(1 for r in recs if r["abstract"]),
        "with_secondary_desc": sum(1 for r in recs
                                   if any(d["weight"] == "secondary" for d in r["descriptors"])),
    }
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bibp_stats.json"),
              "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
