#!/usr/bin/env python3
"""Origenality — mesures de contrôle rejouables sur les données produites.

Chaque sous-commande mesure une propriété que l'audit a mise en cause, sur les
fichiers du dépôt, sans argument implicite : lancée depuis la racine du projet,
elle rend le même chiffre que celui archivé dans `docs/qa/`. Aucun réseau,
bibliothèque standard seule.

    python3 scripts/qa_checks.py isbn
    python3 scripts/qa_checks.py isbn --corpus <autre corpus.jsonl>
    python3 scripts/qa_checks.py abstract-rights
    python3 scripts/qa_checks.py projections
    python3 scripts/qa_checks.py all

Sortie 0 quand la propriété tient, 1 sinon. `isbn` tolère les ISBN séparés par
le garde de tomaison et les nomme au lieu de les taire.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

from merge_dedup import (  # noqa: E402
    ISBN_FIELDS, MAX_ISBN_YEAR_GAP, norm_isbn, text_volume_signature, value_key,
)
from fields import norm_year  # noqa: E402

DEFAULT_CORPUS = ROOT / "data" / "merged" / "corpus.jsonl"
DEFAULT_CITATIONS = ROOT / "data" / "derived" / "citations.jsonl"


def shown(path: Path) -> str:
    """Chemin relatif à la racine du projet : un chemin de machine n'a rien à
    faire dans une preuve qu'un tiers doit rejouer chez lui."""
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if line:
                yield number, json.loads(line)


def cluster_isbns(record) -> set:
    """Tous les ISBN d'une grappe, y compris ceux relégués dans `conflicts`.

    Ne lire que le champ retenu manquerait les ISBN concurrents des autres
    notices de la grappe, et la mesure serait plus indulgente qu'elle ne doit.
    """
    codes = set()
    values = []
    for field in ISBN_FIELDS:
        values.append(record.get(field))
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


def split_reason(clusters) -> str:
    """Pourquoi un même ISBN se retrouve dans plusieurs grappes.

    Deux séparations sont légitimes et se nomment : une tomaison divergente
    (chaque grappe porte son propre numéro de volume), et une réédition (les
    années s'écartent de plus que ce que le lien ISBN tolère — un numéro repris
    quarante ans plus tard ne désigne plus le même livre). Toute autre
    séparation est une sous-fusion, et la mesure doit échouer.
    """
    marks = [entry["volume"] for entry in clusters.values() if entry["volume"]]
    if len(marks) == len(clusters) and len(set(marks)) == len(marks):
        return "tomaison"
    years = sorted(entry["year"] for entry in clusters.values()
                   if entry["year"] is not None)
    if len(years) == len(clusters) and all(
            b - a > MAX_ISBN_YEAR_GAP for a, b in zip(years, years[1:])):
        return "réédition"
    return "non expliquée"


def check_isbn(corpus: Path) -> int:
    by_code = collections.defaultdict(dict)
    for _number, record in read_jsonl(corpus):
        for code in cluster_isbns(record):
            by_code[code][record["origenality_id"]] = {
                "volume": text_volume_signature(record),
                "year": norm_year(record),
                "title": (record.get("title") or "")[:58],
            }

    split = {code: clusters for code, clusters in by_code.items() if len(clusters) > 1}
    by_reason = collections.defaultdict(dict)
    for code, clusters in split.items():
        by_reason[split_reason(clusters)][code] = clusters
    offending = by_reason["non expliquée"]

    print("corpus                                  : %s" % shown(corpus))
    print("ISBN normalisés distincts               : %d" % len(by_code))
    print("ISBN présents dans plusieurs grappes    : %d" % len(split))
    for reason in ("tomaison", "réédition"):
        print("  dont séparés — %-24s : %d" % (reason, len(by_reason[reason])))
        for code, clusters in sorted(by_reason[reason].items()):
            for oid, entry in sorted(clusters.items()):
                print("      %s  %s  %s  tomaison %s  %s"
                      % (code, oid, entry["year"] or "????",
                         entry["volume"] or "()", entry["title"]))
    print("  sous-fusions non expliquées           : %d" % len(offending))
    for code, clusters in sorted(offending.items()):
        for oid, entry in sorted(clusters.items()):
            print("      %s  %s  %s  %s"
                  % (code, oid, entry["year"] or "????", entry["title"]))
    return 1 if offending else 0


def check_abstract_rights(corpus: Path) -> int:
    """Un même résumé sous plusieurs libellés de droits doit porter le conflit."""
    raw = {}
    for path in sorted(glob.glob(str(ROOT / "data" / "raw" / "*" / "records.jsonl"))):
        for _number, record in read_jsonl(Path(path)):
            raw[(record.get("source"), str(record.get("source_id")))] = record

    same_text, recorded, any_conflict = 0, 0, 0
    for _number, cluster in read_jsonl(corpus):
        rows = [raw.get((entry.get("source"), str(entry.get("source_id"))))
                for entry in cluster.get("sources") or []]
        rows = [row for row in rows if row and row.get("abstract")]
        groups = collections.defaultdict(set)
        for row in rows:
            groups[value_key(row["abstract"])].add(value_key(row.get("abstract_rights")))
        carried = bool((cluster.get("conflicts") or {}).get("abstract_rights"))
        if carried:
            any_conflict += 1
        if any(len(values) > 1 for values in groups.values()):
            same_text += 1
            if carried:
                recorded += 1

    print("corpus                                            : %s" % shown(corpus))
    print("grappes où UN MÊME texte porte plusieurs droits    : %d" % same_text)
    print("  dont conflicts.abstract_rights enregistré        : %d" % recorded)
    print("grappes portant conflicts.abstract_rights (toutes) : %d" % any_conflict)
    return 0 if same_text == recorded else 1


def check_projections(citations: Path, corpus: Path) -> int:
    """Les reports de compte par titre, chacun réinstruit sur le corpus.

    Imprimer les reports n'était pas les contrôler : la fonction rendait zéro
    quoi qu'elle affiche, et un report erroné entrait sans faire échouer la QA.
    Elle refait ici le raisonnement du report, à partir du corpus : pour chaque
    grappe qui a reçu un compte, on retrouve la clé de report (titre replié +
    patronyme du premier auteur + type), on cherche les grappes MESURÉES qui
    portent la même clé, et on vérifie deux choses — même type déclaré, et écart
    d'années dans la limite du type (zéro pour une pièce de périodique, un an
    pour un livre). Un report sans donneur retrouvable est une anomalie au même
    titre : la sortie est non nulle.
    """
    from enrich_citations import (  # noqa: E402  (import tardif : dépend de ROOT)
        DEFAULT_YEAR_GAP, YEAR_GAP_BY_TYPE, fold_title, projection_key,
    )
    from fields import norm_type  # noqa: E402

    rows = {row["origenality_id"]: row for _number, row in read_jsonl(citations)}
    projected = [row for row in rows.values()
                 if row.get("count_method") == "title-projection"]

    keys, years, types = {}, {}, {}
    for _number, cluster in read_jsonl(corpus):
        oid = cluster.get("origenality_id")
        doc_type = norm_type(cluster)
        key = projection_key(cluster, fold_title(cluster.get("title")), doc_type)
        if key is not None:
            keys[oid] = key
        years[oid] = norm_year(cluster)
        types[oid] = doc_type

    donors = collections.defaultdict(list)
    for oid, key in keys.items():
        row = rows.get(oid)
        if row and row.get("count_method") == "cluster" and row.get("measured"):
            donors[key].append(oid)

    print("table de citations              : %s" % shown(citations))
    print("corpus                          : %s" % shown(corpus))
    print("reports par titre               : %d" % len(projected))

    problems = []
    for row in sorted(projected, key=lambda r: r["origenality_id"]):
        oid = row["origenality_id"]
        key = keys.get(oid)
        candidates = donors.get(key, []) if key else []
        gap_max = YEAR_GAP_BY_TYPE.get(types.get(oid), DEFAULT_YEAR_GAP)
        gaps = [abs(years[oid] - years[donor])
                for donor in candidates
                if isinstance(years.get(oid), int) and isinstance(years.get(donor), int)]
        best = min(gaps) if gaps else None
        print("   %s  %s  compte %s  rang %s  donneurs %d  écart %s (max %d)"
              % (oid, row["cohort"], row["cited_by_count"], row["cohort_rank"],
                 len(candidates), "n/d" if best is None else best, gap_max))
        if not candidates:
            problems.append("%s : aucun donneur mesuré ne porte sa clé de report" % oid)
            continue
        if any(types.get(donor) != types.get(oid) for donor in candidates):
            problems.append("%s : un donneur n'a pas le même type déclaré" % oid)
        if best is None:
            problems.append("%s : année inconnue d'un côté, l'écart n'est pas mesurable" % oid)
        elif best > gap_max:
            problems.append("%s : écart d'années %d, au-delà de %d pour un %s"
                            % (oid, best, gap_max, types.get(oid)))

    serial = [row for row in projected if row["cohort"]["type"] in ("article", "review")]
    print("dont pièces de périodique       : %d "
          "(l'année doit y être exacte, jamais ±1)" % len(serial))
    for line in problems:
        print("   REPORT REFUSÉ  %s" % line)
    print("reports en défaut               : %d" % len(problems))
    return 1 if problems else 0


def main(argv):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("check", choices=("isbn", "abstract-rights", "projections", "all"))
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--citations", type=Path, default=DEFAULT_CITATIONS)
    arguments = parser.parse_args(argv)

    # Ces mesures portent sur le corpus fusionné, qui n'est pas dans le dépôt
    # public : il est volumineux et plusieurs bases demandent que leur dump ne
    # soit pas redistribué. Un clone qui lance la commande doit lire une phrase,
    # pas une trace d'appels sur un fichier absent.
    if not arguments.corpus.exists():
        print("corpus fusionné absent : %s" % shown(arguments.corpus), file=sys.stderr)
        print("Les moissons brutes et le corpus fusionné ne sont pas publiés. Les "
              "reconstruire avec les moissonneurs de scripts/, puis "
              "pipeline/merge_dedup.py --out-dir data/merged.", file=sys.stderr)
        return 1

    status = 0
    if arguments.check in ("isbn", "all"):
        status |= check_isbn(arguments.corpus)
    if arguments.check in ("abstract-rights", "all"):
        if arguments.check == "all":
            print()
        status |= check_abstract_rights(arguments.corpus)
    if arguments.check in ("projections", "all"):
        if arguments.check == "all":
            print()
        status |= check_projections(arguments.citations, arguments.corpus)
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
