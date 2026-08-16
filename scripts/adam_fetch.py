#!/usr/bin/env python3
"""Sweep Adamantius/GIROTA schedasingola pages by id. Resumable, polite.

Politeness is enforced globally, not per worker. Eight workers each pausing
2.5 s still hit the site about three times a second; the site is a small
university server with no published rate limit, and three requests a second is
not a rate one takes without asking. A single token bucket, shared by every
worker, now caps the whole sweep at one request per second.

Pages land in the shared work directory (scripts/adam_paths.py), under the
repository, so the next stage finds them on any machine.
"""
import os, sys, time, threading, urllib.request, urllib.error, random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adam_paths import HTML_DIR, LOG_PATH, UA, ensure_dirs

BASE = "http://www2.classics.unibo.it/adamantius/index.php?page=schedasingola&schedavis=%d"
OUT = HTML_DIR
LOG = LOG_PATH
RATE = 1.0           # requests per second, for the whole sweep
WORKERS = 8
LO, HI = 1, 5100

ensure_dirs()
lock = threading.Lock()
fails = []

_rate_lock = threading.Lock()
_next_slot = [0.0]


def take_slot():
    """One request per second, all workers together."""
    while True:
        with _rate_lock:
            now = time.time()
            slot = max(now, _next_slot[0])
            _next_slot[0] = slot + 1.0 / RATE
        wait = slot - time.time()
        if wait <= 0:
            return
        time.sleep(wait)

def log(msg):
    with lock:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

def fetch(i):
    path = os.path.join(OUT, "%05d.html" % i)
    if os.path.exists(path) and os.path.getsize(path) > 2000:
        return "cached"
    url = BASE % i
    for attempt in range(4):
        take_slot()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45) as r:
                data = r.read()
            if len(data) < 1000:
                raise ValueError("short body %d" % len(data))
            with open(path, "wb") as f:
                f.write(data)
            return "ok"
        except Exception as e:
            if attempt == 3:
                log("FAIL %d %r" % (i, e))
                with lock:
                    fails.append(i)
                return "fail"
            time.sleep(5 * (attempt + 1))
    return "fail"

def worker(ids, wid):
    for n, i in enumerate(ids):
        st = fetch(i)
        if n % 100 == 0:
            log("w%d progress id=%d (%d/%d)" % (wid, i, n, len(ids)))

def main():
    allids = list(range(LO, HI + 1))
    chunks = [allids[w::WORKERS] for w in range(WORKERS)]
    ts = [threading.Thread(target=worker, args=(c, w)) for w, c in enumerate(chunks)]
    t0 = time.time()
    for t in ts: t.start()
    for t in ts: t.join()
    log("DONE in %.0fs, fails=%s" % (time.time() - t0, sorted(fails)))
    print("DONE fails=%d" % len(fails))

if __name__ == "__main__":
    main()
