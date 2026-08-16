#!/usr/bin/env python3
"""Origenality — les notices que le site affiche et qu'aucune vague n'a taguées.

Une vague tague des grappes. Le site, lui, affiche des notices, et il les
rattache à leur grappe au moment du build. Entre les deux, la fusion bouge :
une grappe se scinde et l'un des deux morceaux hérite d'un identifiant neuf,
un pré-tri mécanique écarte une notice, un filtre de relation en laisse une
autre dehors. Le tag ne suit pas, et la notice paraît sur le site sans classe.
Elle tombe alors dans le réservoir « hors compte » sans que personne l'ait
jugée : c'est un artefact de tuyauterie, pas une décision.

Ce module produit la liste de ces notices et le fichier d'entrée qui les
renvoie au tagueur. Il ne décide rien lui-même et n'appelle rien : il compare
trois pièces — le graphe du site, le corpus fusionné, un ou plusieurs fichiers
de tags — et écrit ce qui manque.

    python3 semantic/retag_gaps.py \\
        --tags semantic/waves/wave2_federated/tags.jsonl \\
        --out semantic/waves/wave4_gap28/notices.jsonl \\
        --report semantic/waves/wave4_gap28/gaps.json

    python3 semantic/retag_gaps.py --tags ... --check   # sort 1 s'il reste un trou

Le motif est établi par élimination, dans cet ordre, et il est écrit par
grappe dans le rapport :

  noise_guess        la grappe porte le pré-tri mécanique ; une vague lancée
                     avec --skip-noise ne l'a jamais vue ;
  relation-<valeur>  sa relation à Origène n'est pas dans le filtre habituel
                     (« about,both ») — un texte d'Origène, par exemple ;
  identifiant-neuf   son identifiant n'existait pas dans la table d'identifiants
                     fournie par --old-ids : la fusion l'a créé après la vague ;
  hors-selection     rien de tout cela : la grappe existait sous le même
                     identifiant et la vague ne l'a pas retenue.

`--old-ids` est facultatif ; sans lui, les deux derniers motifs se confondent
en « hors-selection ».

La sortie `--out` est un JSONL de grappes recopiées du corpus, prêt pour :

    python3 semantic/tag_notices.py --input <out> --output <tags de la vague> \\
        --relations "" --wave <nom de la vague>

`--relations ""` garde tout : la liste vient d'être établie par ce module, il
n'y a plus rien à filtrer, et refiltrer ici rejouerait exactement l'exclusion
qu'on répare.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tags_io import read_tags  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# La couche de données du site est sous `site/data/` dans le dépôt de travail et
# sous `data/` dans l'arbre public, où c'est ce que demandent les `fetch()` des
# pages. Le défaut suit l'arbre où il tourne plutôt que d'en supposer un.
DEFAULT_GRAPH = next(
    (path for path in (ROOT / "site" / "data" / "graph.json",
                       ROOT / "data" / "graph.json") if path.exists()),
    ROOT / "site" / "data" / "graph.json")
DEFAULT_CORPUS = ROOT / "data" / "merged" / "corpus.jsonl"
SITE_SOURCE = "ixtheo-k10plus"
KEPT_RELATIONS = ("about", "both")


def graph_notices(path: Path, source: str) -> tuple[set[str], dict[str, dict]]:
    """Identifiants de notice que le site affiche, et le nœud de chacune."""
    graph = json.loads(Path(path).read_text(encoding="utf-8"))
    nodes = {}
    for node in graph.get("nodes") or []:
        if node.get("k") == "pub" and node.get("ppn"):
            nodes[str(node["ppn"])] = node
    return set(nodes), nodes


def tagged_ids(paths: list[Path]) -> set[str]:
    done: set[str] = set()
    for path in paths:
        if not Path(path).exists():
            continue
        for record in read_tags(path, keep_unidentified=False):
            done.add(str(record.get("notice_id")))
    return done


def read_old_ids(path: Path | None) -> set[str] | None:
    """Identifiants d'un état antérieur du corpus, lus dans une table `id<TAB>signature`."""
    if not path:
        return None
    ids = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            ids.add(line.split("\t", 1)[0])
    return ids


def cause_of(record: dict, old_ids: set[str] | None) -> str:
    if record.get("noise_guess") is True:
        return "noise_guess"
    relation = str(record.get("relation") or "")
    if relation not in KEPT_RELATIONS:
        return "relation-%s" % (relation or "vide")
    if old_ids is not None and str(record.get("origenality_id")) not in old_ids:
        return "identifiant-neuf"
    return "hors-selection"


def authors_of(record: dict, limit: int = 3) -> list[str]:
    names = []
    for author in (record.get("authors") or [])[:limit]:
        name = author.get("name") if isinstance(author, dict) else str(author)
        if name:
            names.append(str(name))
    return names


def collect(corpus: Path, wanted: set[str], done: set[str], source: str,
            old_ids: set[str] | None) -> list[dict]:
    """Grappes du corpus qui portent une notice affichée et n'ont pas de tag."""
    gaps = []
    with Path(corpus).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            shown = [str(entry.get("source_id"))
                     for entry in record.get("sources") or []
                     if isinstance(entry, dict) and entry.get("source") == source
                     and str(entry.get("source_id")) in wanted]
            if not shown:
                continue
            if str(record.get("origenality_id")) in done:
                continue
            gaps.append({
                "origenality_id": record.get("origenality_id"),
                "notices": sorted(shown),
                "cause": cause_of(record, old_ids),
                "noise_rule": record.get("noise_rule"),
                "relation": record.get("relation") or "",
                "title": record.get("title"),
                "authors": authors_of(record),
                "year": record.get("year"),
                "sources": sorted({str(e.get("source")) for e in record.get("sources") or []
                                   if isinstance(e, dict)}),
                "record": record,
            })
    return gaps


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--tags", type=Path, action="append", default=[],
                        help="fichier de tags ; répétable")
    parser.add_argument("--source", default=SITE_SOURCE,
                        help="source dont le site affiche les notices")
    parser.add_argument("--old-ids", type=Path,
                        help="table id<TAB>signature d'un état antérieur, pour distinguer "
                             "un identifiant créé depuis la vague d'une notice non retenue")
    parser.add_argument("--out", type=Path, help="JSONL des grappes à retaguer")
    parser.add_argument("--report", type=Path, help="JSON du relevé, motifs compris")
    parser.add_argument("--check", action="store_true",
                        help="sort 1 s'il reste une notice affichée sans tag")
    arguments = parser.parse_args(argv)

    if not arguments.tags:
        parser.error("--tags est requis (au moins un fichier de tags)")

    # Le relevé rapproche le graphe du site du corpus fusionné, qui n'est pas
    # publié : un clone qui lance la commande doit lire une phrase, pas une
    # trace d'appels sur un fichier absent.
    for label, path in (("graphe du site", arguments.graph),
                        ("corpus fusionné", arguments.corpus)):
        if not path.exists():
            try:
                shown = path.resolve().relative_to(ROOT)
            except ValueError:
                shown = path
            print("%s absent : %s" % (label, shown), file=sys.stderr)
            print("Le corpus fusionné n'est pas publié : le reconstruire avec les "
                  "moissonneurs puis pipeline/merge_dedup.py.", file=sys.stderr)
            return 2

    wanted, nodes = graph_notices(arguments.graph, arguments.source)
    done = tagged_ids(arguments.tags)
    old_ids = read_old_ids(arguments.old_ids)
    gaps = collect(arguments.corpus, wanted, done, arguments.source, old_ids)

    notices = sum(len(gap["notices"]) for gap in gaps)
    causes = collections.Counter(gap["cause"] for gap in gaps)
    notices_by_cause = collections.Counter()
    for gap in gaps:
        notices_by_cause[gap["cause"]] += len(gap["notices"])

    print("notices affichées par le site : %d — sans tag : %d, en %d grappes"
          % (len(wanted), notices, len(gaps)))
    for cause, count in sorted(causes.items()):
        print("  %-18s %2d grappes, %2d notices" % (cause, count, notices_by_cause[cause]))
    for gap in sorted(gaps, key=lambda g: (g["cause"], g["title"] or "")):
        print("  %-18s %s  %s — %s (%s)"
              % (gap["cause"], gap["origenality_id"], ",".join(gap["notices"]),
                 (gap["title"] or "")[:64], gap["year"]))

    if arguments.out:
        arguments.out.parent.mkdir(parents=True, exist_ok=True)
        with arguments.out.open("w", encoding="utf-8") as handle:
            for gap in gaps:
                handle.write(json.dumps(gap["record"], ensure_ascii=False) + "\n")
        print("écrit %s — %d grappes" % (arguments.out, len(gaps)))

    if arguments.report:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "graph": str(arguments.graph),
            "corpus": str(arguments.corpus),
            "tags": [str(path) for path in arguments.tags],
            "old_ids": str(arguments.old_ids) if arguments.old_ids else None,
            "source": arguments.source,
            "notices_shown": len(wanted),
            "notices_without_tag": notices,
            "clusters_without_tag": len(gaps),
            "clusters_by_cause": dict(causes),
            "notices_by_cause": dict(notices_by_cause),
            "gaps": [{key: value for key, value in gap.items() if key != "record"}
                     for gap in sorted(gaps, key=lambda g: (g["cause"], g["title"] or ""))],
        }
        arguments.report.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print("écrit %s" % arguments.report)

    if arguments.check and gaps:
        print("il reste %d notice(s) affichée(s) sans tag" % notices)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
