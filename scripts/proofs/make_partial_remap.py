#!/usr/bin/env python3
"""Fabrique le cas de report partiel de l'audit 5, pour le contrôle négatif.

Une table de renumérotation qui ne résout qu'un identifiant sur vingt passait le
garde « zéro correspondance » posé à l'itération 7, puis un report en place
gardait cette ligne et supprimait les dix-neuf autres. Ce script écrit les trois
fichiers du scénario ; le harnais lance ensuite le report dessus et attend son
refus.

    python3 scripts/proofs/make_partial_remap.py data/_proofs_tmp/remap
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LINES = 20
RESOLVED = 1


def main(argv):
    if len(argv) != 1:
        print(__doc__)
        return 3
    work = Path(argv[0])
    work.mkdir(parents=True, exist_ok=True)

    tags = work / "tags.jsonl"
    with tags.open("w", encoding="utf-8") as handle:
        for index in range(LINES):
            handle.write(json.dumps(
                {"notice_id": "OLD%02d" % index, "relevance": "core"}) + "\n")

    table = {"map": {"OLD%02d" % index: [{"id": "NEW%02d" % index}]
                     for index in range(RESOLVED)}}
    (work / "map.json").write_text(json.dumps(table, indent=1), encoding="utf-8")

    corpus = work / "corpus.jsonl"
    with corpus.open("w", encoding="utf-8") as handle:
        for index in range(LINES):
            handle.write(json.dumps({"origenality_id": "NEW%02d" % index}) + "\n")

    print("%d tags, une table qui en reporte %d, un corpus de %d grappes"
          % (LINES, RESOLVED, LINES))
    print("écrit dans %s" % work)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
