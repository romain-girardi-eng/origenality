#!/usr/bin/env python3
"""Phase 1 — moissonne les PPN du perimetre Origene sur ixtheo.de (vue RSS).

Deux requetes d'autorite :
  about : (topic_id:"149112637")
  by    : (author_id:"149112637" OR author2_id:"149112637" OR author_corporate_id:"149112637")

Mur PoW SHA-256 resolu via ixsess. Throttling 6-8 s entre requetes, backoff 60 s.
Sauvegarde incrementale dans ppn_list.json apres chaque page.
"""
import json, os, random, re, sys, time
import urllib.parse
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ixsess

# Chemins relatifs au dépôt : un chemin absolu de machine rendait le
# moissonneur injouable ailleurs (critère D4, reproductibilité).
_HERE = os.path.dirname(os.path.abspath(__file__))
_BASE = os.path.dirname(_HERE)
OUT_DIR = os.path.join(_BASE, "data", "raw", "ixtheo")
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "harvest_state.json")
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "harvest.log")

QUERIES = {
    "about": '(topic_id:"149112637")',
    # forme canonique reprise telle quelle du lien de la page AuthorityRecord/149112637
    # (author3_id inclus — c'est lui qui manquait dans le plan initial)
    "by": '(author_id:"149112637" OR author2_id:"149112637" OR author_corporate_id:"149112637" OR author3_id:"149112637")',
}
LIMIT = 500
NS = {"dc": "http://purl.org/dc/elements/1.1/",
      "opensearch": "http://a9.com/-/spec/opensearch/1.1/"}


def log(msg):
    line = "%s  %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def load_state():
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return {"pages": {}, "totals": {}}


def save_state(st):
    with open(STATE, "w") as f:
        json.dump(st, f)


def fetch_page(query, page, attempt=0):
    url = ("https://ixtheo.de/Search/Results?lookfor=%s&type=AllFields&view=rss&limit=%d"
           % (urllib.parse.quote(query), LIMIT))
    if page > 1:
        url += "&page=%d" % page
    try:
        st, hd, body = ixsess.get(url)
    except Exception as e:
        log("  EXC %s" % e)
        st, body = 0, ""
    if st != 200 or "<rss" not in body[:400]:
        if attempt < 5:
            wait = 60 * (attempt + 1)
            log("  HTTP %d — backoff %ds (tentative %d)" % (st, wait, attempt + 1))
            time.sleep(wait)
            return fetch_page(query, page, attempt + 1)
        raise RuntimeError("echec page %d apres 5 tentatives (status %s)" % (page, st))
    return body


def parse_items(body):
    root = ET.fromstring(body.encode("utf-8"))
    chan = root.find("channel")
    tot_el = chan.find("opensearch:totalResults", NS)
    total = int(tot_el.text) if tot_el is not None else None
    out = []
    for it in chan.findall("item"):
        link = it.findtext("link") or ""
        m = re.search(r"/Record/([^/?#]+)", link)
        if not m:
            continue
        fmt = it.findtext("dc:format", default=None, namespaces=NS)
        out.append({"ppn": m.group(1),
                    "rss_title": (it.findtext("title") or "").strip(),
                    "rss_format": fmt,
                    "rss_year": it.findtext("dc:date", default=None, namespaces=NS)})
    return total, out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    st = load_state()
    for rel, query in QUERIES.items():
        page = 1
        while True:
            key = "%s:%d" % (rel, page)
            if key in st["pages"]:
                log("page %s deja en cache (%d items)" % (key, len(st["pages"][key])))
            else:
                log("GET %s page %d" % (rel, page))
                body = fetch_page(query, page)
                total, items = parse_items(body)
                st["pages"][key] = items
                if total is not None:
                    st["totals"][rel] = total
                save_state(st)
                log("  -> %d items (total annonce %s)" % (len(items), st["totals"].get(rel)))
                time.sleep(random.uniform(6.0, 8.0))
            total = st["totals"].get(rel, 0)
            got = sum(len(v) for k, v in st["pages"].items() if k.startswith(rel + ":"))
            if got >= total or not st["pages"][key]:
                break
            page += 1

    # fusion
    merged = {}
    for key, items in st["pages"].items():
        rel = key.split(":")[0]
        for it in items:
            e = merged.setdefault(it["ppn"], {"ppn": it["ppn"], "relations": set(),
                                              "rss_title": it["rss_title"],
                                              "rss_format": it["rss_format"],
                                              "rss_year": it["rss_year"]})
            e["relations"].add(rel)
    out = []
    for ppn, e in sorted(merged.items()):
        rels = sorted(e["relations"])
        e["relation"] = "both" if len(rels) == 2 else rels[0]
        e.pop("relations")
        out.append(e)
    payload = {
        "harvested_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "authority": {"ixtheo": "149112637", "gnd": "118590235",
                      "url": "https://ixtheo.de/AuthorityRecord/149112637"},
        "queries": QUERIES,
        "totals_announced": st["totals"],
        "counts_collected": {
            "about": sum(1 for e in out if e["relation"] in ("about", "both")),
            "by": sum(1 for e in out if e["relation"] in ("by", "both")),
            "both": sum(1 for e in out if e["relation"] == "both"),
            "unique_ppn": len(out),
        },
        "ppns": out,
    }
    with open(os.path.join(OUT_DIR, "ppn_list.json"), "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    log("ECRIT ppn_list.json — %s" % json.dumps(payload["counts_collected"]))


if __name__ == "__main__":
    main()
