#!/usr/bin/env python3
"""Dialnet — pas d'API de recherche (l'OAI-PMH n'accepte pas de mot-clé).
Extraction des pages de résultats web. Politesse 2,5 s."""
import html, json, os, re, time
from common import (BASE, Sink, get, record, q, nfc, RE_ORIG, RE_ES_ALEX,
                    RE_ES_COMMON, RE_ORIGENISM)

OUT = os.path.join(BASE, "dialnet", "records.jsonl")
STATS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats_dialnet.json")
ROOT = "https://dialnet.unirioja.es"
SEARCH = ROOT + "/buscar/documentos?querysDismax.DOCUMENTAL_TODO={}&inicio={}"
QUERIES = ["origeniano", "Orígenes exégesis", "Orígenes de Alejandría",
           "Orígenes alejandrino", "origenismo"]
# Le moteur DisMax de Dialnet ignore les guillemets et lemmatise « origenismo »
# en « orígenes » : 33 447 réponses, quasi toutes le nom commun espagnol
# (« los orígenes de… »). D'où deux garde-fous, documentés dans le REPORT :
MAX_PER_QUERY = 300          # plafond dur par requête
STOP_AFTER_EMPTY_PAGES = 3   # arrêt après N pages consécutives 100 % bruit
AUTOR_ORIGENES = 2259044     # page auteur Dialnet « Orígenes »
DELAY = 10.0  # Dialnet renvoie 503 au-delà de ~10 requêtes rapprochées
PAGE = 20

RE_LI = re.compile(r'<li id="(articulo|tesis|libro|capitulo|colectivo|revista)(\d+)"[^>]*>(.*?)</li>\s*(?=\n|\s*</ul>|\s*<li id=")',
                   re.S)
RE_TOTAL = re.compile(r'(\d[\d\.]*)\s*documentos?\s+encontrad', re.I)
RE_TAG = re.compile(r"<[^>]+>")


def txt(s):
    return html.unescape(RE_TAG.sub(" ", s or "")).replace("\xa0", " ").strip()


def squeeze(s):
    return re.sub(r"\s+", " ", s or "").strip()


def split_items(page):
    """Découpe le <ul id="listadoDeArticulos"> en <li> de premier niveau."""
    m = re.search(r'<ul id="listadoDeArticulos".*?>(.*)</ul>', page, re.S)
    if not m:
        return []
    body = m.group(1)
    items, i = [], 0
    starts = [mm.start() for mm in re.finditer(r'<li id="(?:articulo|tesis|libro|capitulo|colectivo)\d+"', body)]
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(body)
        items.append(body[s:e])
    return items


def parse_item(block, query):
    m = re.match(r'<li id="([a-z]+)(\d+)"', block)
    if not m:
        return None
    kind, code = m.group(1), m.group(2)
    sid = f"{kind}:{code}"
    # le premier <p class="titulo"> du bloc est celui de la notice ;
    # ceux qui suivent appartiennent à <div class="resenadoEn"> (comptes rendus)
    head = block.split('<div class="resenadoEn"', 1)[0]
    mt = re.search(r'<p class="titulo">(.*?)</p>', head, re.S)
    title = squeeze(txt(mt.group(1))) if mt else None
    ma = re.search(r'<p class="autores">(.*?)</p>', head, re.S)
    authors = []
    relation = "about"
    if ma:
        for am in re.finditer(r'<a href="/servlet/autor\?codigo=\d+">(.*?)</a>(\s*\(<abbr[^>]*>(.*?)</abbr>\))?', ma.group(1), re.S):
            nm = squeeze(txt(am.group(1)))
            role = squeeze(txt(am.group(3) or ""))
            if nm:
                authors.append(nm + (f" ({role})" if role else ""))
    ml = re.search(r'<p class="localizacion">(.*?)</p>', head, re.S)
    loc = squeeze(txt(ml.group(1))) if ml else None

    container = None
    if ml:
        mr = re.search(r'<a href="/servlet/revista\?codigo=\d+">(.*?)</a>', ml.group(1), re.S)
        if mr:
            container = squeeze(txt(mr.group(1)))
    year = None
    if loc:
        ys = re.findall(r"\b(1[5-9]\d\d|20[0-2]\d)\b", loc)
        if ys:
            year = int(ys[-1])

    # Origène auteur d'une édition/traduction : « Orígenes » figure comme auteur
    if any(re.fullmatch(r"or[ií]genes(\s*\(.*\))?", a.strip(), re.I) for a in authors):
        relation = "by"

    url = {"articulo": "/servlet/articulo?codigo=", "tesis": "/servlet/tesis?codigo=",
           "libro": "/servlet/libro?codigo=", "capitulo": "/servlet/articulo?codigo=",
           "colectivo": "/servlet/libro?codigo="}.get(kind, "/servlet/articulo?codigo=") + code
    kinds = {"articulo": "articulo_revista", "tesis": "tesis", "libro": "libro",
             "capitulo": "capitulo", "colectivo": "libro_colectivo"}

    t = nfc(title or "")
    if RE_ES_ALEX.search(t) or RE_ORIGENISM.search(t) or relation == "by":
        noise = False
    elif RE_ES_COMMON.search(t) and not RE_ES_ALEX.search(t):
        noise = True          # « los orígenes de … » : pluriel commun espagnol
    elif RE_ORIG.search(t):
        noise = None
    else:
        noise = True

    return record("dialnet", sid, title=title, authors=authors, year=year,
                  language="es", container=container or loc, rtype=kinds.get(kind, kind),
                  url=ROOT + url, abstract=None, abstract_rights=None,
                  relation=relation, noise_guess=noise, query_matched=[query])


def harvest_author(sink, per_query):
    """Page auteur « Orígenes » : les documents dont Origène est l'auteur."""
    url = f"{ROOT}/servlet/autor?codigo={AUTOR_ORIGENES}"
    try:
        page = get(url, timeout=60, tries=8, sleep=45.0).decode("utf-8", "replace")
    except Exception as e:
        print(f"[dialnet] ERREUR page auteur : {e}", flush=True)
        per_query["autor:Orígenes"] = {"erreur": str(e)}
        return
    n = 0
    for b in split_items(page):
        r = parse_item(b, "autor:Orígenes")
        if r:
            r["relation"] = "by"
            r["noise_guess"] = False
            sink.add(r)
            n += 1
    sink.flush()
    per_query["autor:Orígenes"] = {"total_web": n, "recuperes": n}
    print(f"[dialnet] page auteur Orígenes : {n} notices, uniques={len(sink)}", flush=True)


def main():
    sink = Sink(OUT)
    per_query = {}
    if os.environ.get("SKIP_AUTHOR") != "1":
        harvest_author(sink, per_query)
        time.sleep(DELAY)
    for query in QUERIES:
        inicio, total, seen_pages, empty_streak, kept = 1, None, 0, 0, 0
        while True:
            url = SEARCH.format(q(query).replace("%20", "+"), inicio)
            try:
                page = get(url, timeout=60, tries=8, sleep=45.0).decode("utf-8", "replace")
            except Exception as e:
                print(f"[dialnet] ERREUR '{query}' inicio={inicio}: {e}", flush=True)
                break
            if total is None:
                mt = RE_TOTAL.search(page)
                total = int(mt.group(1).replace(".", "")) if mt else 0
            items = split_items(page)
            if not items:
                break
            page_kept = 0
            for b in items:
                r = parse_item(b, query)
                if r:
                    sink.add(r)
                    if r["noise_guess"] is not True:
                        page_kept += 1
            kept += page_kept
            empty_streak = empty_streak + 1 if page_kept == 0 else 0
            seen_pages += len(items)
            sink.flush()
            print(f"[dialnet] '{query}' inicio={inicio} +{len(items)} (retenus {page_kept}) "
                  f"({seen_pages}/{total}) uniques={len(sink)}", flush=True)
            if 'rel="next"' not in page or seen_pages >= total:
                break
            if empty_streak >= STOP_AFTER_EMPTY_PAGES:
                print(f"[dialnet] '{query}' arrêt : {empty_streak} pages consécutives sans pertinent", flush=True)
                break
            if seen_pages >= MAX_PER_QUERY:
                print(f"[dialnet] '{query}' arrêt : plafond {MAX_PER_QUERY}", flush=True)
                break
            inicio += PAGE
            time.sleep(DELAY)
        per_query[query] = {"total_web": total, "recuperes": seen_pages,
                            "retenus_non_bruit": kept,
                            "tronque": bool(total and seen_pages < total)}
        time.sleep(DELAY)

    sink.flush()
    vals = list(sink.seen.values())
    stats = {"per_query": per_query, "unique": len(sink),
             "relation_by": sum(1 for r in vals if r["relation"] == "by"),
             "noise_true": sum(1 for r in vals if r["noise_guess"] is True),
             "noise_false": sum(1 for r in vals if r["noise_guess"] is False),
             "noise_null": sum(1 for r in vals if r["noise_guess"] is None),
             "par_type": {}}
    for r in vals:
        stats["par_type"][r["type"]] = stats["par_type"].get(r["type"], 0) + 1
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    json.dump(stats, open(STATS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
