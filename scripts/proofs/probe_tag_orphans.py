#!/usr/bin/env python3
"""Après une refonte de la fusion, les tags visent-ils encore des grappes ?

    python3 scripts/proofs/probe_tag_orphans.py [--corpus <corpus.jsonl>]

Renuméroter les grappes rend orphelin tout tag qui n'a pas été reporté. Le
sondage confronte au corpus les fichiers qui portent des `origenality_id` : les
tags de la vague fédérée, l'étalon, et l'arbre construit sur eux. Zéro orphelin
attendu partout.

La vague 1 (`semantic/pilot/tags_ixtheo.jsonl`) est hors de ce contrôle : elle
tague des PPN K10plus, pas des grappes, et elle est archivée comme historique.

Sortie 0 s'il n'y a aucun orphelin, 1 sinon.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "semantic"))

from tags_io import read_tags, superseded_count  # noqa: E402

TAG_FILES = ("semantic/waves/wave2_federated/tags.jsonl",
             "semantic/pilot/gold_50.jsonl")
TREES = ("semantic/tree/topic_tree_federated.json",)


def tree_notice_ids(path: Path) -> set:
    tree = json.loads(path.read_text(encoding="utf-8"))
    found = set()

    def walk(node):
        found.update(node.get("notice_ids") or [])
        for child in node.get("nodes") or []:
            walk(child)

    for axis in tree.get("axes") or []:
        walk(axis["root"])
    return found


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=str(ROOT / "data" / "merged" / "corpus.jsonl"))
    arguments = parser.parse_args(argv)

    known = set()
    with open(arguments.corpus, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                known.add(json.loads(line)["origenality_id"])
    print("grappes du corpus : %d" % len(known))

    status = 0
    for name in TAG_FILES:
        path = ROOT / name
        records = read_tags(path, keep_unidentified=False)
        ids = {str(record["notice_id"]) for record in records}
        orphans = sorted(ids - known)
        print("%-46s %6d tags · %6d notices · %d périmées · %d orphelins"
              % (name, len(records), len(ids), superseded_count(path), len(orphans)))
        for orphan in orphans[:8]:
            print("      orphelin : %s" % orphan)
        if orphans:
            status = 1

    for name in TREES:
        ids = tree_notice_ids(ROOT / name)
        orphans = sorted(ids - known)
        print("%-46s %6d notices indexées · %d orphelins" % (name, len(ids), len(orphans)))
        for orphan in orphans[:8]:
            print("      orphelin : %s" % orphan)
        if orphans:
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
