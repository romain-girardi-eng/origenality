#!/usr/bin/env python3
"""ISIDORE (Huma-Num) — API resource/search. CAP global 8 000 notices uniques."""
import json, os, time
from common import (BASE, Sink, get_json, record, q, has_orig, nfc, RE_ORIG)

OUT = os.path.join(BASE, "francophone", "records_isidore.jsonl")
STATS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats_isidore.json")
API = "https://api.isidore.science/resource/search?q={}&output=json&replies={}&page={}"
REPLIES = 100
CAP = 8000
# du plus précis au plus large : le cap se remplit d'abord avec le pertinent
QUERIES = ["origénien", "origénisme", "Origène d'Alexandrie", "Origène"]

# Valeur portée par `abstract_rights` quand la notice a un résumé mais que
# la base ne déclare aucun `dc:rights`. Elle n'autorise ni n'interdit rien :
# elle dit d'où vient le résumé et que la source s'est tue sur ses droits.
RIGHTS_UNSTATED = "isidore-unstated"

# domaines/sources manifestement hors SHS-antiquité (jugement sur le champ `topic`)
OFF_TOPIC = ("/sdv", "/spi", "/sde", "/sdu", "/info", "/math", "/phys", "/chim", "/nlin", "/stat", "/qfin")


def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def text_of(x):
    """ISIDORE renvoie tantôt une string, tantôt {'$': ...}, tantôt une liste."""
    for v in as_list(x):
        if isinstance(v, str) and v.strip():
            return v.strip()
    for v in as_list(x):
        if isinstance(v, dict):
            s = v.get("$")
            if isinstance(s, str) and s.strip():
                return s.strip()
    return None


def parse(reply, query):
    uri = reply.get("@uri")
    iso = reply.get("isidore") or {}
    title = text_of(iso.get("title"))
    url = text_of(iso.get("url"))

    authors = []
    ec = iso.get("enrichedCreators") or {}
    for c in as_list(ec.get("creator")):
        if isinstance(c, dict):
            nm = c.get("@normalizedAuthor") or c.get("@origin")
            if not nm:
                ln, fn = c.get("lastname"), c.get("firstname")
                nm = " ".join(filter(None, [ln, fn]))
            if nm:
                authors.append(nm)
    if not authors:
        for c in as_list((iso.get("creators") or {}).get("creator")):
            s = text_of(c) if not isinstance(c, str) else c
            if s:
                authors.append(s)

    year = None
    dt = iso.get("date")
    if isinstance(dt, dict):
        y = dt.get("year") or (dt.get("@origin") or "")[:4]
        if isinstance(y, str) and y[:4].isdigit():
            year = int(y[:4])
    elif isinstance(dt, str) and dt[:4].isdigit():
        year = int(dt[:4])

    # ISIDORE expose la langue sous `dc:language` (ISO 639-2 le plus souvent)
    lang = None
    lg = iso.get("dc:language") or iso.get("languages") or iso.get("language")
    if isinstance(lg, dict):
        lang = text_of(lg.get("language")) or lg.get("@origin") or text_of(lg)
    elif isinstance(lg, list):
        lang = text_of(lg)
    else:
        lang = lg if isinstance(lg, str) else None

    src = iso.get("source") or {}
    container = text_of(src.get("name")) if isinstance(src, dict) else None
    topic = ""
    if isinstance(src, dict):
        t = src.get("topic")
        topic = " ".join([x for x in as_list(t) if isinstance(x, str)]) or (text_of(t) or "")

    tp = iso.get("types") or {}
    rtype = text_of(tp.get("type")) if isinstance(tp, dict) else text_of(tp)
    abstract = text_of(iso.get("abstract"))

    # Droits déclarés par la source moissonnée (dc:rights). ISIDORE laisse le
    # champ vide sur une petite minorité de notices ; un résumé sans mention de
    # droits n'en est pas pour autant sans provenance, et le silence de la base
    # doit être consigné comme tel plutôt que laissé à `null` — sinon la
    # traçabilité perd la seule information disponible, à savoir qu'on a
    # demandé et que la source n'a rien déclaré.
    rights = iso.get("dc:rights")
    if isinstance(rights, list):
        rights = " ; ".join(x if isinstance(x, str) else (text_of(x) or "") for x in rights).strip(" ;")
    elif isinstance(rights, dict):
        rights = text_of(rights)
    if not isinstance(rights, str) or not rights.strip():
        rights = RIGHTS_UNSTATED if (abstract or "").strip() else None

    subjects = []
    sj = iso.get("enrichedSubjects") or iso.get("subjects") or {}
    for s in as_list(sj.get("subject") if isinstance(sj, dict) else sj):
        v = text_of(s) if not isinstance(s, str) else s
        if v:
            subjects.append(v)

    # noise_guess
    if has_orig(title):
        noise = False
    elif any(o in (topic or "").lower() for o in OFF_TOPIC):
        noise = True
    elif has_orig(abstract) or has_orig(*subjects):
        noise = None
    else:
        noise = True   # racine absente de tout le métadonné disponible

    return record("isidore", uri, title=title, authors=authors, year=year,
                  language=lang, container=container, rtype=rtype, url=url,
                  abstract=abstract,
                  abstract_rights=rights,
                  relation="about", noise_guess=noise, query_matched=[query])


def main():
    sink = Sink(OUT)
    per_query = {}
    for query in QUERIES:
        page, got, total = 1, 0, None
        while True:
            if len(sink) >= CAP:
                print(f"[isidore] CAP {CAP} atteint, arrêt", flush=True)
                break
            try:
                d = get_json(API.format(q(query), REPLIES, page))
            except Exception as e:
                print(f"[isidore] ERREUR page {page} q='{query}': {e}", flush=True)
                break
            rep = d.get("response", {}).get("replies", {})
            meta = rep.get("meta", {})
            total = int(meta.get("@items", 0))
            content = rep.get("content") or {}
            replies = as_list(content.get("reply"))
            if not replies:
                break
            for r in replies:
                if len(sink) >= CAP:
                    break
                sink.add(parse(r, query))
            got += len(replies)
            if page % 5 == 0:
                sink.flush()
                print(f"[isidore] '{query}' page {page} got={got}/{total} uniques={len(sink)}", flush=True)
            if got >= total:
                break
            page += 1
            time.sleep(0.4)
        sink.flush()
        per_query[query] = {"total_api": total, "recuperes": got}
        print(f"[isidore] '{query}' TERMINE total_api={total} recuperes={got} uniques={len(sink)}", flush=True)
        if len(sink) >= CAP:
            break

    sink.flush()
    vals = list(sink.seen.values())
    stats = {"per_query": per_query, "unique": len(sink), "cap": CAP,
             "noise_true": sum(1 for r in vals if r["noise_guess"] is True),
             "noise_false": sum(1 for r in vals if r["noise_guess"] is False),
             "noise_null": sum(1 for r in vals if r["noise_guess"] is None),
             "with_abstract": sum(1 for r in vals if r["abstract"])}
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    json.dump(stats, open(STATS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
