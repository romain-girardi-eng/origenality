#!/usr/bin/env python3
"""Section x year grid queries against Adamantius/GIROTA -- cross-check + volumetry."""
import os, re, json, time, urllib.request, urllib.parse, html

import sys

SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCR)
from adam_paths import GRID_DIR, UA, ensure_dirs, ensure_form

OUT = GRID_DIR
ensure_dirs()
URL = "http://www2.classics.unibo.it/adamantius/index.php?page=result"
DELAY = 3.0

# Le formulaire est téléchargé une fois s'il manque, plutôt que supposé présent.
form_html = ensure_form()
sel1 = re.search(r'<select name="sezione1sel">(.*?)</select>', form_html, re.S).group(1)
SECTIONS = [html.unescape(m) for m in re.findall(r'<option value="([^"]+)"', sel1)]

YEARS = list(range(1993, 2007))

def post(sez, anno):
    data = urllib.parse.urlencode({
        "sezione1sel": sez, "sezione2sel": "tutte le sezioni",
        "autore": "", "anno": str(anno), "notizia": "", "abstract": "",
    }).encode()
    req = urllib.request.Request(URL, data=data, headers={"User-Agent": UA})
    for a in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            if a == 3:
                return None
            time.sleep(6 * (a + 1))

results = {}
for sez in SECTIONS:
    for y in YEARS:
        key = "%s||%d" % (sez, y)
        fn = os.path.join(OUT, re.sub(r"[^A-Za-z0-9]+", "_", sez)[:60] + "_%d.html" % y)
        if os.path.exists(fn):
            body = open(fn, encoding="utf-8", errors="replace").read()
        else:
            body = post(sez, y)
            time.sleep(DELAY)
            if body is None:
                results[key] = {"count": None, "ids": [], "error": "fetch_failed"}
                print("FAIL", key, flush=True)
                continue
            open(fn, "w", encoding="utf-8").write(body)
        m = re.search(r"Ho trovato <b>(\d+)</b>", body)
        cnt = int(m.group(1)) if m else None
        ids = [int(x) for x in re.findall(r"schedavis=(\d+)>", body)]
        results[key] = {"count": cnt, "ids": ids, "capped": cnt == 100}
        print(key, cnt, len(ids), flush=True)

json.dump(results, open(os.path.join(SCR, "grid_results.json"), "w"), ensure_ascii=False)
json.dump(SECTIONS, open(os.path.join(SCR, "sections_form.json"), "w"), ensure_ascii=False, indent=1)
print("GRID DONE", len(results))
