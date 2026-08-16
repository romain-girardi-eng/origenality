#!/usr/bin/env python3
"""Les quatre cas d'ISBN que l'audit 4 a nommés, tranchés sur le corpus.

    python3 scripts/proofs/probe_isbn_cases.py [--corpus <corpus.jsonl>]

  3894113049   « Geist und Feuer », 1951 chez O. Müller et 1991 chez
               Johannes-Verlag : DEUX grappes attendues. Un numéro repris par une
               réédition quarante ans plus tard ne désigne pas le même livre, et
               les fusionner effaçait la publication de 1951 de toute série
               temporelle.
  3451221098   le volume 4 du commentaire aux Romains chez Herder, catalogué
               trois fois sous trois libellés : UNE grappe attendue.
  ixtheo :47 / :627 et :48 / :628
               deux volumes de Studia Patristica, chacun catalogué sous deux
               numérotations — la série (« vol. LXXXIV ») et le jeu des actes
               d'Oxford 2015 (« Volume 10 »). Même ISBN, même année, même
               éditeur, même désignation d'ouvrage : UNE grappe attendue par
               paire.

Sortie 0 si les quatre attentes tiennent, 1 sinon.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

from merge_dedup import ISBN_FIELDS, norm_isbn  # noqa: E402

REISSUE = "3894113049"
ONE_VOLUME = "3451221098"
PAIRS = (("1011064553", "1566831350"), ("1011124106", "1566836638"))


def cluster_isbns(record) -> set:
    codes = set()
    values = [record.get(field) for field in ISBN_FIELDS]
    for field, entries in (record.get("conflicts") or {}).items():
        if field in ISBN_FIELDS:
            values.extend(entry.get("value") for entry in entries)
    for value in values:
        if value is None:
            continue
        for item in (value if isinstance(value, list) else [value]):
            code = norm_isbn(item)
            if code:
                codes.add(code)
    return codes


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=str(ROOT / "data" / "merged" / "corpus.jsonl"))
    arguments = parser.parse_args(argv)

    wanted = {norm_isbn(REISSUE), norm_isbn(ONE_VOLUME)}
    by_code = collections.defaultdict(list)
    cluster_of_source = {}
    for line in open(arguments.corpus, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        for entry in record.get("sources") or []:
            if entry.get("source") == "ixtheo-k10plus":
                cluster_of_source[str(entry.get("source_id"))] = record
        for code in cluster_isbns(record) & wanted:
            by_code[code].append(record)

    status = 0

    def describe(record):
        return "%s  %s  %s" % (record["origenality_id"], record.get("year") or "????",
                               (record.get("title") or "")[:56])

    code = norm_isbn(REISSUE)
    clusters = by_code[code]
    print("-- %s (ISBN-10 %s) : deux éditions, deux grappes attendues"
          % (code, REISSUE))
    for record in sorted(clusters, key=lambda r: r.get("year") or 0):
        print("   %s" % describe(record))
    print("   grappes : %d" % len(clusters))
    if len(clusters) != 2:
        print("   ÉCHEC : %d grappe(s) au lieu de 2" % len(clusters))
        status = 1

    code = norm_isbn(ONE_VOLUME)
    clusters = by_code[code]
    print("-- %s (ISBN-10 %s) : un volume, une grappe attendue" % (code, ONE_VOLUME))
    for record in clusters:
        print("   %s" % describe(record))
        print("      notices sources : %s"
              % [(entry["source"], entry["source_id"]) for entry in record["sources"]])
    if len(clusters) != 1:
        print("   ÉCHEC : %d grappe(s) au lieu de 1" % len(clusters))
        status = 1

    for left, right in PAIRS:
        first, second = cluster_of_source.get(left), cluster_of_source.get(right)
        print("-- ixtheo %s / %s : un volume sous deux numérotations" % (left, right))
        for identifier, record in ((left, first), (right, second)):
            print("   %s -> %s" % (identifier, describe(record) if record else "ABSENT"))
        if first is None or second is None:
            print("   ÉCHEC : notice absente du corpus")
            status = 1
        elif first["origenality_id"] != second["origenality_id"]:
            print("   ÉCHEC : deux grappes distinctes")
            status = 1
        else:
            print("   une seule grappe : %s" % first["origenality_id"])
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
