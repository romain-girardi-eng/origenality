#!/usr/bin/env python3
"""SBN / OPAC ICCU — passerelle JSON non documentée `opacmobilegw/search.json`.

Paramètres découverts par sondage (les autres renvoient {"error":…}) :
  any=      recherche toutes zones      author=  zone auteur
  title=    zone titre                  rows=    taille de page (300 accepté)
  start=    offset                      -> numFound, briefRecords[], facetRecords[]
Politesse : 1 s.
"""
import json, os, re, time
from common import (BASE, Sink, get_json, record, q, nfc, RE_ORIG)

OUT = os.path.join(BASE, "sbn", "records.jsonl")
STATS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats_sbn.json")
API = "https://opac.sbn.it/opacmobilegw/search.json?{}={}&rows={}&start={}"
ROWS = 300
DELAY = 1.0

# (champ, valeur, relation forcée)
SEARCHES = [
    ("author", "Origenes", "by"),        # Origène AUTEUR : éditions, traductions
    ("any", "Origene Alessandria", None),
    ("any", "Origeniana", None),
    ("title", "Origeniana", None),
    ("any", "Origenes", None),           # toutes zones : ~3 039
]

RE_YEAR = re.compile(r"\b(1[4-9]\d\d|20[0-2]\d)\b")
RE_ORIG_AUTHOR = re.compile(r"^\s*orig[eé]n[eé]?s?\b", re.IGNORECASE)


def parse(br, label, forced_rel):
    cid = br.get("codiceIdentificativo")
    if not cid:
        return None
    bid = cid.replace("IT\\ICCU\\", "").replace("\\", "")
    titolo = br.get("titolo")
    autore = br.get("autorePrincipale")
    pubb = br.get("pubblicazione")
    year = None
    if pubb:
        ys = RE_YEAR.findall(pubb)
        if ys:
            year = int(ys[0])

    authors = []
    if autore:
        authors.append(autore)
    for n in (br.get("nomi") or []):
        s = re.sub(r"^\s*\[[^\]]*\]\s*", "", str(n)).strip()
        if s and s not in authors:
            authors.append(s)

    # relation : « by » quand Origène est l'auteur de la notice (édition/traduction)
    relation = "by" if (autore and RE_ORIG_AUTHOR.match(nfc(autore))) else "about"
    if forced_rel == "by" and relation != "by":
        relation = "by" if not autore else relation

    t = nfc(titolo or "")
    if relation == "by":
        noise = False
    elif RE_ORIG.search(t):
        noise = False
    elif RE_ORIG.search(" ".join(str(x) for x in authors)):
        noise = None
    else:
        noise = True

    rtype = " / ".join(filter(None, [br.get("livello"), br.get("tipo")])) or None
    return record("sbn", bid, title=titolo, authors=authors, year=year,
                  language=None, container=pubb, rtype=rtype,
                  url=f"https://opac.sbn.it/risultati-ricerca-avanzata/-/opac-adv/detail/{bid}",
                  abstract=None, abstract_rights=None,
                  relation=relation, noise_guess=noise, query_matched=[label])


def main():
    sink = Sink(OUT)
    per_query = {}
    for field, value, forced in SEARCHES:
        label = f"{field}:{value}"
        start, total, got = 0, None, 0
        while True:
            try:
                d = get_json(API.format(field, q(value), ROWS, start), timeout=90)
            except Exception as e:
                print(f"[sbn] ERREUR {label} start={start}: {e}", flush=True)
                break
            if "error" in d:
                print(f"[sbn] ERREUR API {label}: {d['error']}", flush=True)
                break
            total = d.get("numFound", 0)
            recs = d.get("briefRecords") or []
            if not recs:
                break
            for br in recs:
                r = parse(br, label, forced)
                if r:
                    sink.add(r)
            got += len(recs)
            sink.flush()
            print(f"[sbn] {label} {got}/{total} uniques={len(sink)}", flush=True)
            if got >= total:
                break
            start += ROWS
            time.sleep(DELAY)
        per_query[label] = {"numFound": total, "recuperes": got}
        time.sleep(DELAY)

    sink.flush()
    vals = list(sink.seen.values())
    stats = {"per_query": per_query, "unique": len(sink),
             "relation_by": sum(1 for r in vals if r["relation"] == "by"),
             "relation_about": sum(1 for r in vals if r["relation"] == "about"),
             "noise_true": sum(1 for r in vals if r["noise_guess"] is True),
             "noise_false": sum(1 for r in vals if r["noise_guess"] is False),
             "noise_null": sum(1 for r in vals if r["noise_guess"] is None),
             "avec_annee": sum(1 for r in vals if r["year"])}
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    json.dump(stats, open(STATS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
