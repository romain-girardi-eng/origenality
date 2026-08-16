#!/usr/bin/env python3
"""Semantic Scholar /paper/search/bulk harvest (no API key).

The bulk endpoint answers a boolean/phrase query over title+abstract, returns up
to 1000 records per request and paginates by opaque token. It is far kinder to
the anonymous pool than /paper/search: one request per 1000 records instead of
one per 100, and it did not 429 on probe.

Politeness: >= 30 s between requests, identifiable academic User-Agent, clean
stop on runtime budget or persistent 429, and the server's own `Retry-After`
honoured whenever it sends one. Nothing invented: server output only.

Resuming: the pagination token is opaque and short-lived on the server, but it
is the only way back to page 2 of a query. It is written to
`data/raw/semanticscholar/s2_bulk_state.json` after every page, together with
the queries already finished, so a run stopped by the runtime budget or by a
persistent 429 starts again where it left off instead of paying for page 1 of
every query a second time. A token the server has since forgotten simply fails,
and the query restarts from its first page — the state is an optimisation, never
a source of truth. `--restart` ignores it.
"""
import argparse, json, os, time, urllib.request, urllib.error, urllib.parse, datetime

# Chemins relatifs au dépôt : un chemin absolu de machine rendait le
# moissonneur injouable ailleurs (critère D4, reproductibilité).
_HERE = os.path.dirname(os.path.abspath(__file__))
_BASE = os.path.dirname(_HERE)
OUT_DIR = os.path.join(_BASE, "data", "raw", "semanticscholar")
HERE = os.path.dirname(os.path.abspath(__file__))
UA = "Origenality-Research/1.0 (PhD thesis, Univ. de Geneve; romain.girardi@univ-cotedazur.fr)"
FIELDS = "title,abstract,year,externalIds,venue,authors,openAccessPdf,publicationTypes,publicationDate"
ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
INTERVAL = 30.0
MAX_RUNTIME = 22 * 60
MAX_CONSEC_429 = 5
MAX_TOTAL = 5000     # runaway guard: a query matching more than this is noise, skip it
MAX_PAGES = 2        # per query (1000 records/page)

# Name variants and high-precision anchors (CONCEPTION.md section 4, recall-first).
# Every query is anchored: a bare OR-list of Origen-derivatives returned 133 215
# hits on probe (2026-08-15), i.e. noise, so those forms are always ANDed.
QUERIES = [
    '"Origen of Alexandria"',
    'Origen + Alexandria',
    'Origen + (patristic | patristics | "Church Fathers" | exegesis)',
    'Origen + (Celsus | Rufinus | Eusebius | Jerome | Hexapla | Philocalia)',
    'Origen + (theology | scripture | biblical | soul | resurrection | allegory)',
    '"Contra Celsum"',
    '"De Principiis" + (Origen | Origenes)',
    '"Peri Archon"',
    'Origenism + (Christian | theology | patristic | Church | controversy)',
    '"Origène"',
    '"Orígenes de Alejandría"',
    'Origeniana',
    '"Origene di Alessandria" | "Origene Alessandrino"',
    'Origenes + (Alexandria | patristic | theology | Christian | Kirchenvater)',
]

log_path = os.path.join(HERE, "s2_bulk.log")


def log(m):
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {m}"
    open(log_path, "a").write(line + "\n")
    print(line, flush=True)


RETRY_AFTER_MAX = 3600.0   # une heure : le serveur peut demander plus de cinq minutes
STATE_PATH = os.path.join(OUT_DIR, "s2_bulk_state.json")


def retry_after(error):
    """Seconds the server asked for in `Retry-After`, or None.

    The header comes in seconds or as an HTTP date. Replaying it instead of our
    own interval is the only polite answer to a 429: the server said when to
    come back, and ignoring it is insisting.
    """
    headers = getattr(error, "headers", None)
    raw = headers.get("Retry-After") if headers is not None else None
    if not raw:
        return None
    raw = str(raw).strip()
    if raw.isdigit():
        return min(float(raw), RETRY_AFTER_MAX)
    try:
        from email.utils import parsedate_to_datetime
        moment = parsedate_to_datetime(raw)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=datetime.timezone.utc)
        delay = (moment - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
        return min(max(delay, 0.0), RETRY_AFTER_MAX)
    except Exception:  # noqa: BLE001
        return None


# Codes que le serveur rend quand le curseur opaque n'est plus valide. Le
# curseur est court-lived : une reprise tardive le présente encore, le serveur
# le refuse, et l'ancienne boucle sortait de la requête en gardant l'état — donc
# en représentant le même curseur mort à chaque relance, sans jamais revenir à
# la page 1. L'état est une optimisation, jamais une source de vérité : quand il
# est démenti, on l'efface.
EXPIRED_TOKEN_STATUS = (400, 422)


def token_expired(status, token):
    """Le serveur vient-il de refuser le curseur qu'on lui a présenté ?"""
    return bool(token) and status in EXPIRED_TOKEN_STATUS


def drop_token(state, query):
    """Oublie le curseur d'une requête : la reprise repart de la page 1."""
    state["token"].pop(query, None)
    state["pages"][query] = 0
    return state


def load_state(restart=False):
    """{"done": [queries], "token": {query: token}, "pages": {query: n}}"""
    empty = {"done": [], "token": {}, "pages": {}}
    if restart or not os.path.exists(STATE_PATH):
        return empty
    try:
        with open(STATE_PATH, encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, ValueError):
        return empty
    for key, default in empty.items():
        state.setdefault(key, default)
    return state


def save_state(state):
    """Written after every page: a run killed mid-query keeps its cursor."""
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_PATH)


def fetch(query, token=None):
    p = {"query": query, "fields": FIELDS}
    if token:
        p["token"] = token
    url = ENDPOINT + "?" + urllib.parse.urlencode(p)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300], retry_after(e)
    except Exception as e:
        return -1, str(e), None


def normalize(p, query):
    ext = p.get("externalIds") or {}
    oap = p.get("openAccessPdf") or {}
    return {
        "source": "semanticscholar",
        "source_id": p.get("paperId"),
        "title": p.get("title"),
        "authors": [a.get("name") for a in (p.get("authors") or []) if a.get("name")],
        "year": p.get("year"),
        "container": p.get("venue"),
        "language": None,
        "descriptors": [],
        "abstract": p.get("abstract"),
        "abstract_rights": "s2-odc-by",
        "url": f"https://www.semanticscholar.org/paper/{p['paperId']}" if p.get("paperId") else None,
        "doi": ext.get("DOI"),
        "external_ids": ext,
        "open_access_pdf": oap.get("url"),
        "open_access_license": oap.get("license"),
        "publication_types": p.get("publicationTypes"),
        "publication_date": p.get("publicationDate"),
        "s2_query": query,
        "s2_endpoint": "search/bulk",
        "harvested_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restart", action="store_true",
                        help="ignore the saved cursor and start every query at page 1")
    arguments = parser.parse_args(argv)
    state = load_state(arguments.restart)

    # keep whatever the first (relevance-search) pass already stored
    rec_path = os.path.join(OUT_DIR, "records.jsonl")
    seen, existing = set(), []
    if os.path.exists(rec_path):
        for line in open(rec_path, encoding="utf-8"):
            r = json.loads(line)
            existing.append(r)
            if r.get("source_id"):
                seen.add(r["source_id"])
    log(f"START bulk; carried over {len(existing)} records from previous pass")

    start = time.time()
    fh = open(rec_path, "a", encoding="utf-8")   # incremental: survives a kill
    n_new, per_query, n_req, n_429, consec = 0, [], 0, 0, 0
    stop = False
    resumed = 0
    purged = 0
    for q in QUERIES:
        if stop or time.time() - start > MAX_RUNTIME:
            log("Runtime budget reached. Clean stop.")
            break
        if q in state["done"]:
            log(f"SKIP q={q!r}: already finished in a previous run")
            continue
        token = state["token"].get(q)
        pages = int(state["pages"].get(q, 0))
        if token:
            resumed += 1
            log(f"RESUME q={q!r} at page {pages + 1} with the stored cursor")
        got_q, total_q, skipped = 0, None, False
        while True:
            if n_req:
                time.sleep(INTERVAL)
            if time.time() - start > MAX_RUNTIME:
                log("Runtime budget reached mid-query. Clean stop.")
                stop = True
                break
            status, payload, asked = fetch(q, token)
            n_req += 1
            if status == 200:
                consec = 0
                total_q = payload.get("total", total_q)
                if total_q and total_q > MAX_TOTAL:
                    log(f"SKIP q={q!r}: total={total_q} > {MAX_TOTAL}, query is too broad")
                    skipped = True
                    state["done"].append(q)
                    save_state(state)
                    break
                data = payload.get("data") or []
                fresh = 0
                for p in data:
                    pid = p.get("paperId")
                    if pid and pid in seen:
                        continue
                    if pid:
                        seen.add(pid)
                    fh.write(json.dumps(normalize(p, q), ensure_ascii=False) + "\n")
                    fresh += 1
                fh.flush()
                os.fsync(fh.fileno())
                n_new += fresh
                got_q += len(data)
                pages += 1
                token = payload.get("token")
                # Le curseur est écrit AVANT la page suivante : un arrêt entre
                # deux requêtes ne coûte pas la reprise de la requête entière.
                state["pages"][q] = pages
                if token:
                    state["token"][q] = token
                else:
                    state["token"].pop(q, None)
                exhausted = not token or not data or pages >= MAX_PAGES
                if exhausted and q not in state["done"]:
                    state["done"].append(q)
                save_state(state)
                log(f"OK q={q!r} page={pages} got={len(data)} new={fresh} total={total_q}")
                if exhausted:
                    break
            elif status in (429, 503):
                n_429 += 1
                consec += 1
                wait = asked if asked is not None else 0.0
                log(f"{status} q={q!r} (consecutive={consec})"
                    + (f", Retry-After={wait:.0f}s honoured" if asked is not None else ""))
                if consec >= MAX_CONSEC_429:
                    log("Persistent throttling. Clean stop.")
                    stop = True
                    break
                if wait:
                    time.sleep(wait)
            elif token_expired(status, token):
                # Curseur périmé : on le jette et on reprend la requête à sa
                # première page, en le disant dans le journal.
                log(f"HTTP {status} q={q!r}: the stored cursor was refused; "
                    f"dropping it and restarting this query at page 1")
                drop_token(state, q)
                save_state(state)
                token, pages, got_q = None, 0, 0
                purged += 1
                continue
            else:
                log(f"HTTP {status} q={q!r}: {str(payload)[:200]}")
                break
        per_query.append({"query": q, "total_reported": total_q,
                          "records_returned": got_q, "pages": pages,
                          "skipped_too_broad": skipped,
                          "resumed_from_stored_token": bool(state["token"].get(q))})
    fh.close()
    save_state(state)

    stats = {
        "endpoint": "graph/v1/paper/search/bulk",
        "requests": n_req, "http_429": n_429,
        "new_records": n_new,
        "records_total_in_file": len(existing) + n_new,
        "unique_paper_ids": len(seen),
        "expired_cursors_purged": purged,
        "per_query": per_query,
        "runtime_s": round(time.time() - start, 1),
        "queries_resumed_from_a_stored_cursor": resumed,
        "state_file": os.path.relpath(STATE_PATH, _BASE),
        "finished_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    json.dump(stats, open(os.path.join(HERE, "s2_bulk_stats.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    log("DONE " + json.dumps({k: v for k, v in stats.items() if k != "per_query"}))


if __name__ == "__main__":
    main()
