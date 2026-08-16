#!/usr/bin/env python3
"""La documentation dit-elle encore le contraire de la décision en vigueur ?

    python3 scripts/proofs/probe_docs.py

Le régime des résumés est « attribution et retrait à la demande » : chaque
résumé affiché nomme sa base et porte un lien résoluble vers sa notice, et les
droits déclarés ne conditionnent rien. Deux phrases résiduelles disaient encore
l'inverse (CONCEPTION.md, ARCHITECTURE.md), et le README du front promettait
16 étiquettes sur 16 à 375 px là où il en reconnaît 14 plus bas.

Sortie 0 quand aucune contradiction ne subsiste.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# (fichier, motif interdit, ce que le motif décrivait)
FORBIDDEN = [
    ("CONCEPTION.md", r"indexé en interne", "résumés d'éditeur réservés à l'usage interne"),
    ("ARCHITECTURE.md", r"champ abstract non autorisé", "gate par droits sur le champ abstract"),
    ("site/build-c/README.md", r"16 of 16 domains are still named at 375",
     "16/16 étiquettes à 375 px"),
]

# (fichier, motif attendu)
REQUIRED = [
    ("CONCEPTION.md", r"nomme la base qui l'a écrit"),
    ("ARCHITECTURE.md", r"n'est pas attribuable"),
    ("ARCHITECTURE.md", r"PUBLISH_DENYLIST\.md"),
    ("site/build-c/README.md", r"14 of the 16 domains are named at 375"),
    ("PUBLISH_DENYLIST.md", r"docs/qa"),
    ("PUBLISH_DENYLIST.md", r"data/_proofs_tmp"),
    ("PUBLISH_DENYLIST.md", r"s2_bulk_state\.json"),
    (".gitignore", r"data/_proofs_tmp/"),
]


def main():
    status = 0
    for name, pattern, described in FORBIDDEN:
        text = (ROOT / name).read_text(encoding="utf-8")
        found = [number for number, line in enumerate(text.splitlines(), 1)
                 if re.search(pattern, line)]
        print("%-28s résidu « %s » : %s" % (name, described,
                                            "lignes %s" % found if found else "aucun"))
        if found:
            status = 1
    for name, pattern in REQUIRED:
        text = (ROOT / name).read_text(encoding="utf-8")
        present = re.search(pattern, text) is not None
        print("%-28s attendu /%s/ : %s" % (name, pattern, "présent" if present else "ABSENT"))
        if not present:
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
