#!/usr/bin/env python3
"""Parse Adamantius schedasingola HTML into structured records."""
import os, re, sys, json, html, unicodedata

SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCR)
from adam_paths import HTML_DIR

HTMLDIR = HTML_DIR

FIELD_RE = re.compile(
    r"<i>\s*(Scheda|Codice volume|Sezione|Sottosezione|Autore|Anno|Notizia Bibliografica|Abstract)\s*:\s*</i>\s*</td>\s*<td>(.*?)</td>",
    re.S | re.I)
PDF_RE = re.compile(r'href=(adam_pdf/[^\s>"]+)')


def clean(s):
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = s.replace(" ", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def split_authors(raw):
    """Autore field is a run of 'Initials Surname' groups, space separated.
    e.g. 'P. Sacchi L. Troiani' -> ['P. Sacchi', 'L. Troiani'].
    Keep raw when the pattern does not apply."""
    raw = raw.strip(" ;,")
    if not raw:
        return []
    # split before any initial-block  (A.  /  A.-B.  /  A.B.)
    parts = re.split(r"(?=(?:\b[A-ZÀ-ÖØ-Þ]\.\s*)+(?:[-–]\s*[A-ZÀ-ÖØ-Þ]\.\s*)*[A-ZÀ-ÖØ-Þ])", raw)
    parts = [p.strip(" ,;") for p in parts if p.strip(" ,;")]
    if len(parts) <= 1:
        return [raw]
    return parts


LANG_HINTS = [
    (r"\b(Die|Der|Das|und|zur|zum|über|Untersuchungen|Studien|Beiträge|eines|einer|nach|bei|im)\b", "de"),
    (r"\b(the|The|and|of|in the|Studies|Essays|between|from|according)\b", "en"),
    (r"\b(la|le|les|des|dans|selon|chez|d`après|Études|Étude|sur|pour|une|aux)\b", "fr"),
    (r"\b(di|della|dello|degli|nella|nel|sulla|secondo|Studi|Ricerche|alla|per il|un`)\b", "it"),
    (r"\b(de la|del|los|las|según|Estudios|sobre|en el)\b", "es"),
]


class InterceptedPage(Exception):
    """The response is not an Adamantius page (captive portal / proxy injection)."""


def parse_file(path):
    body = open(path, encoding="utf-8", errors="replace").read()
    # HTTP is unencrypted here: a captive portal can substitute its own page and
    # still return 200 with a plausible size. Refuse anything that is not the site.
    if "<title>ADAMANTIUS</title>" not in body:
        raise InterceptedPage(path)
    d = {}
    for k, v in FIELD_RE.findall(body):
        d[k.strip().lower()] = clean(v)
    if not d.get("codice volume"):
        return None
    scheda = d.get("scheda", "").strip()
    if not scheda.isdigit():
        return None
    pdf = PDF_RE.search(body)
    return {
        "scheda": int(scheda),
        "codice_volume": d.get("codice volume", ""),
        "sezione": d.get("sezione", ""),
        "sottosezione": d.get("sottosezione", ""),
        "autore_raw": d.get("autore", ""),
        "anno": d.get("anno", ""),
        "notizia": d.get("notizia bibliografica", ""),
        "abstract": d.get("abstract", ""),
        "pdf": pdf.group(1) if pdf else None,
    }


def main():
    recs = []
    for fn in sorted(os.listdir(HTMLDIR)):
        if not fn.endswith(".html"):
            continue
        r = parse_file(os.path.join(HTMLDIR, fn))
        if r:
            recs.append(r)
    json.dump(recs, open(os.path.join(SCR, "parsed.json"), "w"), ensure_ascii=False)
    print("parsed", len(recs))
    if recs:
        print(json.dumps(recs[0], ensure_ascii=False, indent=1)[:1200])


if __name__ == "__main__":
    main()
