#!/usr/bin/env python3
"""francophone/ contient deux sources : on garde un fichier par source
(records_thesesfr.jsonl, records_isidore.jsonl) et on produit leur union
dans records.jsonl (le champ `source` distingue les notices)."""
import json, os
from common import BASE

D = os.path.join(BASE, "francophone")
parts = ["records_thesesfr.jsonl", "records_isidore.jsonl"]
out = os.path.join(D, "records.jsonl")
n = {}
with open(out + ".tmp", "w", encoding="utf-8") as f:
    for p in parts:
        fp = os.path.join(D, p)
        if not os.path.exists(fp):
            continue
        c = 0
        for line in open(fp, encoding="utf-8"):
            if line.strip():
                f.write(line)
                c += 1
        n[p] = c
os.replace(out + ".tmp", out)
print(json.dumps({"parts": n, "total": sum(n.values()), "out": out}, ensure_ascii=False, indent=2))
