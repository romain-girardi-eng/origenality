#!/usr/bin/env python3
"""`origenality_id` est-il une clé ? (une par grappe, aucune en double)

    python3 scripts/proofs/probe_ids.py [--corpus <corpus.jsonl>]

Sortie 0 si le nombre d'identifiants distincts égale le nombre de grappes.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=str(ROOT / "data" / "merged" / "corpus.jsonl"))
    arguments = parser.parse_args(argv)

    counts = collections.Counter()
    with open(arguments.corpus, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                counts[json.loads(line)["origenality_id"]] += 1
    duplicates = {key: value for key, value in counts.items() if value > 1}
    print("grappes                : %d" % sum(counts.values()))
    print("identifiants distincts : %d" % len(counts))
    print("identifiants en double : %d" % len(duplicates))
    for key, value in list(duplicates.items())[:10]:
        print("   %s  x%d" % (key, value))
    return 1 if duplicates else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
