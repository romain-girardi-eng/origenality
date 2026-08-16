#!/usr/bin/env python3
"""ISIDORE — 2e passe : contournement de la profondeur maximale.

L'API plafonne à 1 000 notices par requête (au-delà de l'offset 1000 elle
renvoie indéfiniment la même page — vérifié : replies=200&page=5/6/7 et
replies=500&page=2/3 renvoient le même premier et le même dernier @uri).
Le filtre `&date=AAAA` (alias `&year=`) fonctionne : on tranche chaque
requête par année, chaque tranche restant sous le plafond.
"""
import json, os, time
from common import BASE, Sink, get_json, q
from harvest_isidore import API, REPLIES, CAP, QUERIES, parse, as_list, OUT

STATS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats_isidore.json")
YEARS = list(range(1800, 2027))
DEPTH_LIMIT = 1000


def fetch_query(sink, query, extra="", label=None):
    """Pagine une requête (éventuellement filtrée par année). Renvoie (total, recus)."""
    label = label or query
    page, got, total = 1, 0, 0
    seen_first = None
    while True:
        if len(sink) >= CAP:
            return total, got
        url = API.format(q(query), REPLIES, page) + extra
        try:
            d = get_json(url, timeout=120)
        except Exception as e:
            print(f"[isidore-y] ERREUR {label} p{page}: {e}", flush=True)
            return total, got
        rep = d.get("response", {}).get("replies", {})
        total = int(rep.get("meta", {}).get("@items", 0))
        replies = as_list((rep.get("content") or {}).get("reply"))
        if not replies:
            return total, got
        first = replies[0].get("@uri")
        if seen_first is not None and first == seen_first:
            return total, got            # plateau de profondeur atteint
        seen_first = first
        for r in replies:
            if len(sink) >= CAP:
                break
            sink.add(parse(r, label))
        got += len(replies)
        if got >= total or got >= DEPTH_LIMIT:
            return total, got
        page += 1
        time.sleep(0.35)


def main():
    sink = Sink(OUT)
    start = len(sink)
    print(f"[isidore-y] reprise : {start} notices déjà sur disque", flush=True)
    detail = {}
    for query in QUERIES:
        # d'abord la requête nue (les 1 000 premières, déjà largement en base)
        tot, got = fetch_query(sink, query)
        detail[query] = {"total_api": tot, "recuperes_sans_tranche": got, "par_annee": {}}
        sink.flush()
        print(f"[isidore-y] '{query}' nu : {got}/{tot} uniques={len(sink)}", flush=True)
        if tot <= DEPTH_LIMIT:
            continue
        for y in YEARS:
            if len(sink) >= CAP:
                print(f"[isidore-y] CAP {CAP} atteint", flush=True)
                break
            t, g = fetch_query(sink, query, extra=f"&date={y}", label=f"{query} [{y}]")
            if g:
                detail[query]["par_annee"][str(y)] = {"total": t, "recuperes": g}
            if y % 10 == 0:
                sink.flush()
                print(f"[isidore-y] '{query}' année {y} : {g}/{t} uniques={len(sink)}", flush=True)
            time.sleep(0.25)
        sink.flush()
        print(f"[isidore-y] '{query}' TERMINE uniques={len(sink)}", flush=True)
        if len(sink) >= CAP:
            break

    sink.flush()
    vals = list(sink.seen.values())
    stats = {
        "methode": "pagination directe (plafond API = 1 000 notices/requête) "
                   "+ tranchage par année via &date=AAAA",
        "plafond_profondeur_api": DEPTH_LIMIT,
        "cap_global": CAP,
        "detail": detail,
        "unique": len(sink),
        "ajout_2e_passe": len(sink) - start,
        "noise_true": sum(1 for r in vals if r["noise_guess"] is True),
        "noise_false": sum(1 for r in vals if r["noise_guess"] is False),
        "noise_null": sum(1 for r in vals if r["noise_guess"] is None),
        "with_abstract": sum(1 for r in vals if r["abstract"]),
    }
    json.dump(stats, open(STATS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in stats.items() if k != "detail"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
