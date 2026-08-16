#!/usr/bin/env python3
"""Écrit un dump synthétique dont aucune attribution ne se résout en lien.

    python3 scripts/proofs/make_unresolvable_dump.py data/_proofs_tmp/faux_liens.jsonl

Sert de contrôle négatif au harnais : `check_release.py` doit le REFUSER
(sortie 2). Cinq notices, cinq façons de rater un lien — base connue sans
adresse ni identifiant, résumé en liste, pseudo-adresse « http-not-a-url »,
« http:// » sans hôte, identifiant qui remonte l'arborescence.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROWS = [
    {"origenality_id": "ORSYNTH1", "abstract": "Un résumé sans lien vers sa notice.",
     "source": "bibp", "source_id": ""},
    {"origenality_id": "ORSYNTH2", "Abstract": ["Un résumé", "en liste."],
     "abstract_source": "bibp"},
    {"origenality_id": "ORSYNTH3", "abstract": "Une pseudo-adresse.",
     "abstract_source": "ixtheo-k10plus", "abstract_url": "http-not-a-url"},
    {"origenality_id": "ORSYNTH4", "abstract": "Un schéma sans hôte.",
     "abstract_source": "ixtheo-k10plus", "abstract_url": "http://"},
    {"origenality_id": "ORSYNTH5", "abstract": "Un identifiant qui remonte.",
     "source": "ixtheo-k10plus", "source_id": "../../not-a-record"},
]


def main(argv):
    if len(argv) != 1:
        print("usage: make_unresolvable_dump.py <sortie.jsonl>", file=sys.stderr)
        return 2
    path = Path(argv[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in ROWS:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("%d notices écrites, aucune attribuable" % len(ROWS))
    for row in ROWS:
        print("   %s  %s" % (row["origenality_id"],
                             row.get("abstract_url") or row.get("source_id") or "(rien)"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
