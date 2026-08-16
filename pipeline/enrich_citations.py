#!/usr/bin/env python3
"""Origenality — projection des comptes de citations sur tout le corpus fusionné.

Le problème que ce module traite est celui de la maquette C : la jointure entre
les bases à identifiant pérenne et les catalogues de bibliothèque échoue parce
que les jeux de DOI ne se recouvrent pas. Une notice IxTheo de 1977 sans DOI
n'existe dans aucune base bibliométrique ; aucune jointure ne la fera
apparaître. La réponse n'est donc pas de forcer la jointure, mais de sortir un
enregistrement pour **chaque** grappe du corpus, mesurée ou non, et de publier
le taux de mesure par source.

Ce que produit le module, une ligne par grappe dans `data/derived/citations.jsonl` :

    origenality_id   identifiant stable de la grappe
    ixtheo_ppn       PPN K10plus quand une source IxTheo est dans la grappe
    doi              DOI de la grappe quand elle en porte un
    cited_by_count   entier, ou null si aucune source ne le donne
    source           source du compte, ou null
    measured         true quand cited_by_count est un entier
    cohort           {decade, type, lang} après harmonisation
    cohort_level     granularité effectivement retenue pour le rang
    cohort_size      nombre de grappes mesurées dans cette cohorte
    cohort_rank      rang percentile parmi les grappes mesurées de la cohorte

Le rang n'est calculé que sur les grappes mesurées : une grappe non mesurée n'a
pas un rang nul, elle n'a pas de rang. Confondre les deux reviendrait à déclarer
qu'un livre allemand de 1935 n'a jamais été cité, alors que personne ne l'a
compté.

    python3 pipeline/enrich_citations.py
    python3 pipeline/enrich_citations.py --corpus data/merged/corpus.jsonl \\
        --output data/derived/citations.jsonl --min-cohort 8
"""
from __future__ import annotations

import argparse
import bisect
import collections
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fields  # noqa: E402
from merge_dedup import first_author_key  # noqa: E402

# Champs qui portent un compte de citations, dans l'ordre de préférence. La
# liste est ouverte : une moisson ultérieure qui ramènerait le compte de
# Semantic Scholar n'aura qu'à ajouter son nom ici.
COUNT_FIELDS = ("cited_by_count", "citationCount", "citation_count")

# Sources bibliométriques, dans l'ordre où on leur attribue le compte quand la
# provenance ne le dit pas.
BIBLIOMETRIC_SOURCES = ("openalex", "semanticscholar", "crossref")


def decade_of(year):
    return f"{(year // 10) * 10}s" if isinstance(year, int) else "?"


def cluster_sources(cluster):
    names = []
    for entry in cluster.get("sources") or []:
        name = entry.get("source") if isinstance(entry, dict) else str(entry)
        if name and name not in names:
            names.append(name)
    return names


def ixtheo_ppn(cluster):
    for entry in cluster.get("sources") or []:
        if isinstance(entry, dict) and entry.get("source") == "ixtheo-k10plus":
            return str(entry.get("source_id") or "") or None
    return None


def count_and_source(cluster):
    """Compte de citations de la grappe et source qui le porte.

    La provenance par champ écrite par la fusion est la réponse la plus sûre ;
    à défaut on retombe sur la première source bibliométrique de la grappe.
    """
    provenance = cluster.get("provenance") or {}
    for field in COUNT_FIELDS:
        value = cluster.get(field)
        if value is None:
            continue
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        origin = provenance.get(field) or {}
        source = origin.get("source") if isinstance(origin, dict) else None
        if not source:
            present = cluster_sources(cluster)
            source = next((s for s in BIBLIOMETRIC_SOURCES if s in present), None)
        return count, source
    return None, None


TITLE_MIN = 20


def fold_title(text):
    decomposed = unicodedata.normalize("NFD", text or "")
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    squashed = re.sub(r"[^a-z0-9 ]", " ", stripped.lower())
    return re.sub(r"\s+", " ", squashed).strip()


# Un type inconnu ("?") ou fourre-tout ("other") ne prouve rien : il peut
# recouvrir aussi bien la monographie que sa recension. Le report l'écarte.
PROJECTABLE_TYPES = ("article", "book", "chapter", "review", "dissertation")

# Écart d'année toléré, PAR TYPE.
#
# Un article et une recension sont des pièces de périodique : le titre revient
# d'un fascicule à l'autre, chaque année, sous la même signature. « Bulletin de
# patrologie » de Matthieu Cassin paraît dans la Revue des sciences
# philosophiques et théologiques millésime après millésime ; une tolérance d'un
# an suffisait à verser le compte du fascicule 2022 au fascicule 2020/2021, avec
# son rang de cohorte. Pour ces types, l'année doit coïncider exactement.
#
# Un livre, un chapitre ou une thèse n'ont pas cette périodicité, mais ils ont
# l'inverse : deux bases datent le même volume de l'année d'impression et de
# l'année de dépôt, ou de l'année de la thèse et de celle de sa publication.
# L'écart d'un an y reste nécessaire, et il n'y a pas de série annuelle à
# confondre.
YEAR_GAP_BY_TYPE = {
    "article": 0,
    "review": 0,
    "book": 1,
    "chapter": 1,
    "dissertation": 1,
}
DEFAULT_YEAR_GAP = 0


def project_by_title(rows, keys, years, gap_by_type=None):
    """Second passe conservatrice : report d'un compte sur un travail identique.

    La fusion ne rapproche deux notices que sur un faisceau d'indices ; deux
    grappes peuvent donc porter le même travail sans avoir été réunies, l'une
    mesurée, l'autre non. Reporter le chiffre sur le TITRE SEUL, comme le
    faisait la première version, attribue au livre les citations de sa
    recension : *Alexandria in Late Antiquity* de Christopher Haas et la
    recension que *Choice* en a publiée portent le même titre, et la
    monographie recevait ainsi les 244 citations de la recension, avec son rang
    de cohorte.

    La clé de report est donc un triplet, et il faut qu'il soit complet :

      - titre normalisé identique, d'au moins vingt caractères ;
      - patronyme du premier auteur identique et non vide — une notice sans
        auteur ne reçoit et ne donne rien ;
      - type de document identique et déclaré : une recension ne verse jamais
        son compte à un livre, et un type absent ou « other » interdit le
        report au lieu de le supposer ;

    puis, en plus : cible unique, comptes concordants s'il y en a plusieurs, et
    années toutes deux connues et distantes d'au plus l'écart toléré POUR CE
    TYPE (`YEAR_GAP_BY_TYPE` : zéro pour les pièces de périodique, un an pour le
    livre, le chapitre et la thèse) — une année absente n'est jamais tenue pour
    compatible.

    Le compte reporté reste marqué `count_method: title-projection` : ce n'est
    pas une fusion, les grappes restent distinctes, seul le chiffre voyage, et
    il voyage marqué.
    """
    gaps = YEAR_GAP_BY_TYPE if gap_by_type is None else gap_by_type
    measured = collections.defaultdict(set)
    measured_year = {}
    for index, row in enumerate(rows):
        key = keys[index]
        if key is None:
            continue
        if row["measured"]:
            measured[key].add(row["cited_by_count"])
            measured_year.setdefault(key, years[index])

    projected = 0
    for index, row in enumerate(rows):
        if row["measured"]:
            continue
        key = keys[index]
        if key is None:
            continue
        candidates = measured.get(key)
        if not candidates or len(candidates) > 1:
            continue
        left, right = years[index], measured_year.get(key)
        if not isinstance(left, int) or not isinstance(right, int):
            continue
        if abs(left - right) > gaps.get(key[2], DEFAULT_YEAR_GAP):
            continue
        row["cited_by_count"] = next(iter(candidates))
        row["measured"] = True
        row["source"] = "openalex"
        row["count_method"] = "title-projection"
        projected += 1
    return projected


def projection_key(cluster, title, doc_type):
    """Clé de report : titre + patronyme du premier auteur + type déclaré.

    Renvoie None dès qu'une des trois pièces manque — sans elles, deux travaux
    différents se ressemblent trop.
    """
    if not title or len(title) < TITLE_MIN:
        return None
    if doc_type not in PROJECTABLE_TYPES:
        return None
    author = first_author_key(cluster.get("authors") or [])
    if not author:
        return None
    return (title, author, doc_type)


def percentile_ranks(counts):
    """Rang percentile moyen, à égalité partagée, pour une cohorte mesurée.

    Renvoie une fonction compte -> rang dans ]0, 1[. Le rang d'un compte est la
    position moyenne des grappes qui le portent, divisée par l'effectif : les
    ex æquo reçoivent le même rang, et ni 0 ni 1 ne sont atteints, puisque
    aucune grappe n'est au-dessus de zéro autre ni au-dessous de zéro autre.
    Le rang dit la position, pas la valeur.
    """
    ordered = sorted(counts)
    total = len(ordered)

    def rank(value):
        lower = bisect.bisect_left(ordered, value)
        upper = bisect.bisect_right(ordered, value)
        return round((lower + upper) / (2 * total), 4)

    return rank


def build(corpus_path, output_path, coverage_path, min_cohort, project_titles=True):
    rows = []
    keys = []
    years = []
    for line in corpus_path.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        cluster = json.loads(line)
        count, source = count_and_source(cluster)
        year = fields.norm_year(cluster)
        doc_type = fields.norm_type(cluster)
        keys.append(projection_key(cluster, fold_title(cluster.get("title")),
                                   doc_type))
        years.append(year)
        rows.append(
            {
                "origenality_id": cluster.get("origenality_id"),
                "ixtheo_ppn": ixtheo_ppn(cluster),
                "doi": cluster.get("doi"),
                "cited_by_count": count,
                "source": source,
                "measured": count is not None,
                "count_method": "cluster" if count is not None else None,
                "referenced_works_count": cluster.get("referenced_works_count"),
                "noise_guess": cluster.get("noise_guess"),
                "sources": cluster_sources(cluster),
                "cohort": {
                    "decade": decade_of(year),
                    "type": doc_type,
                    "lang": fields.norm_lang(
                        cluster.get("language") or cluster.get("languages")
                    ),
                },
            }
        )

    projected = project_by_title(rows, keys, years) if project_titles else 0

    # Cohortes emboîtées : on descend jusqu'à ce qu'une cohorte compte assez de
    # grappes mesurées pour qu'un rang veuille dire quelque chose.
    levels = [
        ("decade+type+lang", lambda c: (c["decade"], c["type"], c["lang"])),
        ("decade+type", lambda c: (c["decade"], c["type"])),
        ("decade", lambda c: (c["decade"],)),
        ("all", lambda c: ("all",)),
    ]
    pools = []
    for name, key in levels:
        table = collections.defaultdict(list)
        for row in rows:
            if row["measured"]:
                table[key(row["cohort"])].append(row["cited_by_count"])
        pools.append((name, key, table))

    rankers = {}
    for name, _, table in pools:
        rankers[name] = {k: percentile_ranks(v) for k, v in table.items()}

    for row in rows:
        row["cohort_level"] = None
        row["cohort_size"] = 0
        row["cohort_rank"] = None
        if not row["measured"]:
            continue
        for name, key, table in pools:
            bucket = key(row["cohort"])
            members = table.get(bucket, [])
            if len(members) >= min_cohort or name == "all":
                row["cohort_level"] = name
                row["cohort_size"] = len(members)
                row["cohort_rank"] = rankers[name][bucket](row["cited_by_count"])
                break

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    coverage = coverage_report(rows, min_cohort)
    coverage["title_projections"] = projected
    coverage["title_projection_year_gap_by_type"] = dict(YEAR_GAP_BY_TYPE)
    coverage_path.write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return rows, coverage


def coverage_report(rows, min_cohort):
    per_source = collections.defaultdict(lambda: {"clusters": 0, "measured": 0})
    per_decade = collections.defaultdict(lambda: {"clusters": 0, "measured": 0})
    per_lang = collections.defaultdict(lambda: {"clusters": 0, "measured": 0})
    per_type = collections.defaultdict(lambda: {"clusters": 0, "measured": 0})
    levels = collections.Counter()
    with_doi = {"clusters": 0, "measured": 0}
    without_doi = {"clusters": 0, "measured": 0}

    for row in rows:
        measured = 1 if row["measured"] else 0
        for name in row["sources"]:
            per_source[name]["clusters"] += 1
            per_source[name]["measured"] += measured
        per_decade[row["cohort"]["decade"]]["clusters"] += 1
        per_decade[row["cohort"]["decade"]]["measured"] += measured
        per_lang[row["cohort"]["lang"]]["clusters"] += 1
        per_lang[row["cohort"]["lang"]]["measured"] += measured
        per_type[row["cohort"]["type"]]["clusters"] += 1
        per_type[row["cohort"]["type"]]["measured"] += measured
        bucket = with_doi if row["doi"] else without_doi
        bucket["clusters"] += 1
        bucket["measured"] += measured
        if row["cohort_level"]:
            levels[row["cohort_level"]] += 1

    def rate(table):
        out = {}
        for key, value in sorted(
            table.items(), key=lambda kv: -kv[1]["clusters"]
        ):
            share = value["measured"] / value["clusters"] if value["clusters"] else 0
            out[key] = {**value, "coverage": round(share, 4)}
        return out

    measured = sum(1 for r in rows if r["measured"])
    return {
        "clusters": len(rows),
        "measured": measured,
        "coverage": round(measured / len(rows), 4) if rows else 0,
        "min_cohort": min_cohort,
        "count_source": dict(
            collections.Counter(r["source"] for r in rows if r["measured"]).most_common()
        ),
        "count_method": dict(
            collections.Counter(r["count_method"] for r in rows if r["measured"]).most_common()
        ),
        "cohort_levels": dict(levels.most_common()),
        "by_source": rate(per_source),
        "by_doi": {"with_doi": rate({"with_doi": with_doi})["with_doi"],
                   "without_doi": rate({"without_doi": without_doi})["without_doi"]},
        "by_decade": rate(per_decade),
        "by_language": rate(per_lang),
        "by_type": rate(per_type),
    }


def main(argv):
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--corpus", type=Path, default=root / "data/merged/corpus.jsonl")
    parser.add_argument("--output", type=Path, default=root / "data/derived/citations.jsonl")
    parser.add_argument(
        "--coverage", type=Path, default=root / "data/derived/citations_coverage.json"
    )
    parser.add_argument(
        "--min-cohort",
        type=int,
        default=8,
        help="grappes mesurées requises pour qu'une cohorte serve au rang",
    )
    parser.add_argument(
        "--no-title-projection",
        action="store_true",
        help="s'en tenir aux comptes portés par la grappe elle-même",
    )
    arguments = parser.parse_args(argv)

    rows, coverage = build(
        arguments.corpus,
        arguments.output,
        arguments.coverage,
        arguments.min_cohort,
        project_titles=not arguments.no_title_projection,
    )
    print(f"grappes : {coverage['clusters']:,}")
    print(f"mesurées : {coverage['measured']:,} ({coverage['coverage']:.1%})")
    print(f"dont reports par titre : {coverage['title_projections']:,}")
    print("couverture par source :")
    for name, value in coverage["by_source"].items():
        print(f"  {name:<20} {value['measured']:>6,}/{value['clusters']:>6,}  {value['coverage']:.1%}")
    print(f"-> {arguments.output}")
    print(f"-> {arguments.coverage}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
