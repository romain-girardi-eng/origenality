#!/usr/bin/env python3
"""Semantic Scholar polite harvest (no API key).
Rules: max 1 request / 30 s, hard stop after 30 min, stop if 429s persist,
`Retry-After` honoured when the server sends one.
Writes records.jsonl + a run log. No fabricated data: only what the server returns.

Resumable. The run used to restart at offset zero with an empty `seen` set and
append to the same file, so a second run rewrote everything it had already
written. State now lives in work/_state.json next to the output — the offset to
request next, the paper ids already written, and the length of records.jsonl at
that offset. On restart the file is truncated back to that length, the saved
offset is requested again, and known ids are skipped: no duplicate, no gap.

All paths are relative to the repository; nothing is written outside it.
"""
import json, os, sys, time, urllib.request, urllib.error, urllib.parse, datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_BASE = os.path.dirname(_HERE)
OUT_DIR = os.path.join(_BASE, "data", "raw", "semanticscholar")
SCRATCH = os.path.join(OUT_DIR, "work")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(SCRATCH, exist_ok=True)

UA = "Origenality-Research/1.0 (PhD thesis, Univ. de Geneve; romain.girardi@univ-cotedazur.fr)"
QUERY = "Origen of Alexandria"
FIELDS = "title,abstract,year,externalIds,venue,authors,openAccessPdf,publicationTypes,publicationDate"
LIMIT = 100
MIN_INTERVAL = 30.0
MAX_RUNTIME = 30 * 60
MAX_CONSEC_429 = 6

log_path = os.path.join(SCRATCH, "s2_run.log")
rec_path = os.path.join(OUT_DIR, "records.jsonl")
stats_path = os.path.join(SCRATCH, "s2_stats.json")
state_path = os.path.join(SCRATCH, "_state.json")


def load_state():
    if os.path.exists(state_path):
        with open(state_path, encoding="utf-8") as f:
            return json.load(f)
    return {"offset": 0, "seen": [], "committed_bytes": 0, "written": 0}


def save_state(state):
    tmp = state_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, state_path)


RETRY_AFTER_MAX = 3600.0   # une heure : le serveur peut demander plus de cinq minutes


def retry_after(error, fallback):
    """Delay the server asked for, in seconds, or `fallback`."""
    headers = getattr(error, "headers", None)
    raw = headers.get("Retry-After") if headers is not None else None
    if not raw:
        return fallback
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
        return fallback


def log(msg):
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}"
    with open(log_path, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def fetch(offset):
    url = ("https://api.semanticscholar.org/graph/v1/paper/search"
           f"?query={urllib.parse.quote(QUERY)}&fields={FIELDS}&limit={LIMIT}&offset={offset}")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        return e.code, {"__error__": body, "__retry_after__": retry_after(e, None)}
    except Exception as e:
        return -1, str(e)


def normalize(p):
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
        "doi": ext.get("DOI"),
        "external_ids": ext,
        "open_access_pdf": oap.get("url"),
        "open_access_license": oap.get("license"),
        "publication_types": p.get("publicationTypes"),
        "publication_date": p.get("publicationDate"),
        "url": f"https://www.semanticscholar.org/paper/{p.get('paperId')}" if p.get("paperId") else None,
    }


def main():
    start = time.time()
    state = load_state()
    offset = int(state.get("offset") or 0)
    total_reported = None
    n_written = int(state.get("written") or 0)
    n_req = 0
    n_429 = 0
    consec_429 = 0
    seen = set(state.get("seen") or [])
    events = []
    # anything written past the last committed offset belongs to a page whose
    # state was never saved: drop it rather than let it be appended twice
    committed = int(state.get("committed_bytes") or 0)
    if os.path.exists(rec_path) and os.path.getsize(rec_path) > committed:
        with open(rec_path, "r+b") as trunc:
            trunc.truncate(committed)
    fh = open(rec_path, "a")
    log(f"RESUME offset={offset} known_ids={len(seen)} bytes={committed}")
    log(f"START query={QUERY!r} limit={LIMIT} interval={MIN_INTERVAL}s max_runtime={MAX_RUNTIME}s")
    while time.time() - start < MAX_RUNTIME:
        t0 = time.time()
        status, payload = fetch(offset)
        n_req += 1
        if status == 200:
            consec_429 = 0
            total_reported = payload.get("total", total_reported)
            data = payload.get("data") or []
            new = 0
            for p in data:
                pid = p.get("paperId")
                if pid and pid in seen:
                    continue
                if pid:
                    seen.add(pid)
                fh.write(json.dumps(normalize(p), ensure_ascii=False) + "\n")
                new += 1
            fh.flush()
            os.fsync(fh.fileno())
            n_written += new
            nxt = payload.get("next")
            log(f"OK offset={offset} got={len(data)} new={new} total={total_reported} next={nxt}")
            events.append({"req": n_req, "offset": offset, "status": 200, "got": len(data)})
            if not data or nxt is None:
                log("No more results (next is null or empty page). Stopping.")
                state.update({"offset": offset, "seen": sorted(seen),
                              "committed_bytes": fh.tell(), "written": n_written,
                              "done": True})
                save_state(state)
                break
            offset = nxt
            state.update({"offset": offset, "seen": sorted(seen),
                          "committed_bytes": fh.tell(), "written": n_written})
            save_state(state)
        elif status == 429:
            n_429 += 1
            consec_429 += 1
            log(f"429 at offset={offset} (consecutive={consec_429})")
            events.append({"req": n_req, "offset": offset, "status": 429})
            if consec_429 >= MAX_CONSEC_429:
                log(f"Persistent 429 ({consec_429} in a row). Clean stop.")
                break
        else:
            log(f"HTTP {status} at offset={offset}: {str(payload)[:200]}")
            events.append({"req": n_req, "offset": offset, "status": status})
            consec_429 = 0
            if status == 400:
                log("400 (likely offset+limit cap reached). Stopping.")
                break
        # politeness: the server's own Retry-After first, then our backoff
        asked = None
        if isinstance(payload, dict):
            asked = payload.get("__retry_after__")
        wait = asked if asked else MIN_INTERVAL * (1 + consec_429)
        elapsed = time.time() - t0
        sleep_for = max(0, wait - elapsed)
        if time.time() - start + sleep_for >= MAX_RUNTIME:
            log("Runtime budget reached during backoff. Clean stop.")
            break
        time.sleep(sleep_for)
    fh.close()
    stats = {
        "query": QUERY, "requests": n_req, "http_429": n_429,
        "records_written": n_written, "unique_paper_ids": len(seen),
        "total_reported_by_api": total_reported, "last_offset": offset,
        "runtime_s": round(time.time() - start, 1), "events": events,
        "finished_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    with open(stats_path, "w") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    log(f"DONE {json.dumps({k: v for k, v in stats.items() if k != 'events'})}")


if __name__ == "__main__":
    main()
