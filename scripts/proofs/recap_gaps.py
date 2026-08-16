#!/usr/bin/env python3
"""Ce que la passe de rattrapage a repris, et ce qu'elle en a fait.

    python3 scripts/proofs/recap_gaps.py <gaps.json d'avant> <tags de la passe>

Le premier fichier est le relevé produit par `semantic/retag_gaps.py` sur le
fichier de tags d'avant la passe : il porte les notices sans classe et le motif
de chacune. Le second est la sortie du tagueur. Le module croise les deux et
imprime, ligne à ligne, la notice, son motif et la classe qu'elle a reçue.

Rien n'est recopié : les deux fichiers sont relus à chaque passe, et un
identifiant présent dans le relevé et absent des tags fait sortir en 1.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    report = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    tags = {}
    for line in Path(argv[1]).read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            tags[str(record.get("notice_id"))] = record

    gaps = report["gaps"]
    missing = [gap["origenality_id"] for gap in gaps
               if str(gap["origenality_id"]) not in tags]
    classes = collections.Counter()
    causes = collections.Counter()

    print("relevé : %d grappes, %d notices affichées sans classe"
          % (report["clusters_without_tag"], report["notices_without_tag"]))
    for gap in gaps:
        record = tags.get(str(gap["origenality_id"]))
        klass = record.get("relevance") if record else "SANS TAG"
        if record:
            classes[klass] += len(gap["notices"])
        causes[gap["cause"]] += len(gap["notices"])
        print("  %-17s %-9s %-14s %s (%s)"
              % (gap["cause"], klass, gap["origenality_id"],
                 (gap["title"] or "")[:60], gap["year"]))

    print("motifs, en notices : " + " · ".join(
        "%s %d" % (cause, count) for cause, count in sorted(causes.items())))
    print("classes reçues, en notices : " + " · ".join(
        "%s %d" % (klass, count) for klass, count in sorted(classes.items())))
    counted = classes["core"] + classes["partial"]
    print("dont comptées (core + partial) : %d · mentionnées : %d · hors compte : %d"
          % (counted, classes["marginal"], classes["none"]))

    if missing:
        print("SANS TAG : " + ", ".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
