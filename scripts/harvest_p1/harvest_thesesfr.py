#!/usr/bin/env python3
"""theses.fr — API v1 publique (Licence Ouverte). Moisson exhaustive."""
import json, os, sys, time
from common import (BASE, Sink, get_json, record, q, has_orig, has_orig_strict,
                    nfc, RE_OFF_DOMAIN, RE_ORIG)

OUT = os.path.join(BASE, "francophone", "records_thesesfr.jsonl")
QUERIES = ["Origène", "Origène d'Alexandrie", "origénien", "origénisme", "Origen"]
API = "https://theses.fr/api/v1/theses/recherche/?q={}&nombre={}&debut={}"
DETAIL = "https://theses.fr/api/v1/theses/these/{}"
PAGE = 100
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "thesesfr_detail_cache.json")


def load_cache():
    if os.path.exists(CACHE):
        return json.load(open(CACHE, encoding="utf-8"))
    return {}


def main():
    sink = Sink(OUT)
    cache = load_cache()
    hits_per_query = {}
    raw = {}   # nnt -> (these, [queries])
    for query in QUERIES:
        debut, total = 0, None
        while True:
            d = get_json(API.format(q(query), PAGE, debut))
            total = d.get("totalHits", 0)
            batch = d.get("theses", [])
            for t in batch:
                nnt = t.get("nnt") or t.get("id")
                if not nnt:
                    continue
                if nnt not in raw:
                    raw[nnt] = [t, []]
                raw[nnt][1].append(query)
            debut += len(batch)
            if not batch or debut >= total:
                break
            time.sleep(0.5)
        hits_per_query[query] = total
        print(f"[thesesfr] '{query}' totalHits={total} cumul_uniques={len(raw)}", flush=True)
        time.sleep(0.5)

    n = 0
    for nnt, (t, queries) in raw.items():
        det = cache.get(nnt)
        if det is None:
            try:
                det = get_json(DETAIL.format(nnt))
            except Exception as e:
                det = {"_error": str(e)}
            cache[nnt] = det
            n += 1
            if n % 20 == 0:
                json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
                sink.flush()
                print(f"[thesesfr] details {n}", flush=True)
            time.sleep(0.35)

        title = t.get("titrePrincipal") or (det.get("titres") or {}).get("fr")
        title_en = t.get("titreEN")
        authors = [f"{a.get('nom','')} {a.get('prenom','')}".strip()
                   for a in (t.get("auteurs") or [])]
        directeurs = [f"{a.get('nom','')} {a.get('prenom','')}".strip()
                      for a in (t.get("directeurs") or [])]
        date = t.get("dateSoutenance") or ""
        year = None
        if date and len(date) >= 4:
            year = int(date[-4:]) if date[-4:].isdigit() else None
        resumes = det.get("resumes") or {}
        abstract = resumes.get("fr") or resumes.get("en") or None
        lang = "fr" if resumes.get("fr") else ("en" if resumes.get("en") else "fr")
        subjects = [s.get("libelle") for s in (t.get("sujets") or [])]
        rameau = [s.get("libelle") for s in (t.get("sujetsRameau") or [])]
        disc = t.get("discipline") or ""

        # noise_guess — theses.fr fait du stemming : « origine/origen » ramène
        # des milliers de thèses sans rapport. Règles :
        #   racine dans titre / sujets / Rameau        -> False (pertinent)
        #   racine seulement dans le résumé            -> None  (douteux, conservé)
        #   racine nulle part + discipline hors SHS-A. -> True  (bruit évident)
        strong = has_orig_strict(title, title_en, *subjects, *rameau)
        in_abstract = has_orig_strict(abstract)
        if strong:
            noise = False
        elif in_abstract:
            noise = None
        elif RE_OFF_DOMAIN.search(nfc(disc)) or not in_abstract:
            noise = True
        else:
            noise = None

        url = f"https://theses.fr/{nnt}"
        rec = record(
            "thesesfr", nnt, title=title, authors=authors, year=year,
            language=lang,
            container=(t.get("etabSoutenanceN") or None),
            rtype="these",
            url=url, abstract=abstract,
            abstract_rights="theses.fr — Licence Ouverte / Open Licence (Etalab)" if abstract else None,
            relation="about", noise_guess=noise, query_matched=queries)
        rec["discipline"] = disc or None
        rec["directeurs"] = directeurs
        rec["subjects"] = [s for s in subjects if s]
        rec["subjects_rameau"] = [s for s in rameau if s]
        rec["title_en"] = title_en
        rec["status"] = t.get("status")
        sink.add(rec)

    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    sink.flush()
    stats = {"per_query": hits_per_query, "unique": len(sink),
             "noise_true": sum(1 for r in sink.seen.values() if r["noise_guess"] is True),
             "noise_false": sum(1 for r in sink.seen.values() if r["noise_guess"] is False),
             "noise_null": sum(1 for r in sink.seen.values() if r["noise_guess"] is None),
             "with_abstract": sum(1 for r in sink.seen.values() if r["abstract"])}
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    json.dump(stats, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "stats_thesesfr.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
