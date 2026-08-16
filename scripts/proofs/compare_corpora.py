#!/usr/bin/env python3
"""Compare deux corpus par SHA-256 et rend 1 s'ils diffèrent.

    python3 scripts/proofs/compare_corpora.py <a.jsonl> <b.jsonl>

Sert au harnais de preuves : la fusion rejouée dans un répertoire temporaire
doit reproduire, octet pour octet, le corpus de référence. La comparaison porte
sur le contenu, pas sur le chemin — c'est la seule façon de prouver qu'une
fusion est déterministe sans réécrire le corpus qu'elle prétend reproduire.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            sha.update(block)
    return sha.hexdigest()


def shown(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv):
    if len(argv) != 2:
        print("usage: compare_corpora.py <a.jsonl> <b.jsonl>", file=sys.stderr)
        return 2
    left, right = Path(argv[0]), Path(argv[1])
    for path in (left, right):
        if not path.is_file():
            print("fichier absent : %s" % shown(path))
            return 3
    a, b = digest(left), digest(right)
    print("%s  %s" % (a, shown(left)))
    print("%s  %s" % (b, shown(right)))
    if a == b:
        print("identiques (SHA-256)")
        return 0
    print("DIFFÉRENTS — la preuve ne tient pas")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
