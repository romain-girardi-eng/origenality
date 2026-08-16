#!/usr/bin/env python3
"""Récapitulatif du harnais — mesuré sur les fichiers, jamais récité.

    python3 scripts/proofs/recap.py --merge <dir> --sans-isbn <dir> --release <json>

L'ancien harnais imprimait un récapitulatif constant : les mêmes lignes, les
mêmes chiffres, quelles que soient les données et quels que soient les échecs.
Celui-ci relit les artefacts que la passe vient de produire et échoue si l'un
manque. Un récapitulatif qui ne peut pas mentir est un récapitulatif qui plante
quand la passe a planté.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "semantic"))

from tags_io import read_tags, superseded_count  # noqa: E402


def spaced(number) -> str:
    return f"{number:,}".replace(",", " ")


def published_counted() -> int:
    """Le nombre de travaux comptés que l'asset publié porte aujourd'hui."""
    asset = json.loads((ROOT / "site" / "build-c" / "assets" / "semantic.json")
                       .read_text(encoding="utf-8"))
    classes = collections.Counter(entry["r"] for entry in asset["byPpn"].values())
    return classes["core"] + classes["partial"]


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merge", required=True)
    parser.add_argument("--sans-isbn", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--semantic-next",
                        help="asset sémantique construit sur la vague fédérée")
    arguments = parser.parse_args(argv)

    merge = json.loads((Path(arguments.merge) / "merge_report.json")
                       .read_text(encoding="utf-8"))
    without = json.loads((Path(arguments.sans_isbn) / "merge_report.json")
                         .read_text(encoding="utf-8"))
    release = json.loads(Path(arguments.release).read_text(encoding="utf-8"))
    coverage = json.loads((ROOT / "data" / "derived" / "citations_coverage.json")
                          .read_text(encoding="utf-8"))
    abstracts = json.loads((ROOT / "site" / "data" / "abstracts.json")
                           .read_text(encoding="utf-8"))
    tags = ROOT / "semantic" / "waves" / "wave2_federated" / "tags.jsonl"
    tag_records = read_tags(tags, keep_unidentified=False)
    per_source = collections.Counter(entry["s"] for entry in abstracts["byPpn"].values())
    linked = sum(1 for entry in abstracts["byPpn"].values() if entry.get("u"))

    print("A4-1  fusion rejouée dans %s ; corpus de référence non réécrit ; "
          "deux fusions comparées par SHA-256" % arguments.merge)
    print("A4-2  grappes %s (identifiants uniques %s) · liens ISBN %d · "
          "refusés : série %d, tomaison %d, écart d'années %d"
          % (spaced(merge["merged_clusters"]), spaced(merge["unique_ids"]),
             merge["isbn_links"], merge["isbn_series_ignored"],
             merge["isbn_blocked_volume_marker"], merge["isbn_blocked_year_gap"]))
    print("A4-2  sans le lien ISBN : %s grappes, %d liens — l'écart mesure ce que "
          "l'ISBN recolle" % (spaced(without["merged_clusters"]), without["isbn_links"]))
    print("A4-3  résumés publiés %d, dont %d avec lien vers la notice donatrice ; "
          "bases : %s" % (len(abstracts["byPpn"]), linked,
                          ", ".join("%s %d" % (key, value)
                                    for key, value in per_source.most_common())))
    print("A4-4  vague fédérée : %s tags, %d ligne(s) périmée(s) restantes"
          % (spaced(len(tag_records)), superseded_count(tags)))
    print("A4-5  contrôle de publication : %s notices, %s résumés, %s attribués, "
          "%d violation(s)" % (spaced(release["records"]), spaced(release["abstracts"]),
                               spaced(release["attributed"]), release["violations"]))
    print("A5-1  refus de tomaison sur la fusion rejouée : %d ; le lien ISBN unit "
          "%d paires" % (merge["isbn_blocked_volume_marker"], merge["isbn_links"]))
    if arguments.semantic_next and Path(arguments.semantic_next).exists():
        built = json.loads(Path(arguments.semantic_next).read_text(encoding="utf-8"))
        classes = collections.Counter(entry["r"] for entry in built["byPpn"].values())
        counted = classes["core"] + classes["partial"]
        # Hors compte = tout ce que le site ne compte pas : les notices classées
        # hors dossier ET celles qu'aucun tag n'atteint. Ne compter que les
        # premières donnerait 5 là où les pages disent 33.
        in_graph = (built.get("source") or {}).get("notices_in_graph", len(built["byPpn"]))
        aside = in_graph - counted - classes["marginal"]
        published = published_counted()
        print("A5-4  vague fédérée sur les notices du site : %s comptées, %d mentionnées, "
              "%d hors compte — l'asset publié en porte %s%s"
              % (spaced(counted), classes["marginal"], aside, spaced(published),
                 "" if published == counted else " (ÉCART)"))
    else:
        print("A5-4  l'asset sémantique de la vague fédérée n'a pas été construit")
    print("A4-7  citations : %s grappes, %s mesurées (%.1f %%), %d report(s) par titre"
          % (spaced(coverage["clusters"]), spaced(coverage["measured"]),
             100 * coverage["coverage"], coverage["title_projections"]))

    if release["violations"]:
        print("ÉCHEC : le corpus porte des résumés non attribuables")
        return 1
    if merge["unique_ids"] != merge["merged_clusters"]:
        print("ÉCHEC : origenality_id n'est pas une clé")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
