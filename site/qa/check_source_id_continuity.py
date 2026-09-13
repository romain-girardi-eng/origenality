#!/usr/bin/env python3
"""Continuité des identifiants de source d'une publication à la suivante (règle OR-20).

Un lien vers une notice, dans l'Explorer (`#r=ixtheo-k10plus:011209895`) comme
dans la CLI (`origenality record 011209895`), nomme la notice par l'identifiant
du catalogue dont elle vient, jamais par l'identifiant Origenality : celui-ci est
un condensé de l'identité du regroupement (DOI, ou titre, année et auteur), et une
correction de catalogue peut le changer d'une reconstruction à l'autre. Un tel
lien ne survit donc à une reconstruction que si chaque identifiant de source que
la carte publiée portait figure encore dans les `source_ids` de la nouvelle.

Le contrôle charge le graphe de la publication précédente et vérifie que chacun
de ses identifiants se retrouve :

  - sous la même paire source:identifiant, ce qu'écrit le bouton « Copy link » ;
  - à défaut, sous le seul identifiant, à condition qu'il désigne une notice et
    une seule (la source a été renommée ; un lien nu la retrouve encore).

Le graphe précédent se lit dans un historique git : l'arbre public voisin
(`../origenality-public`, chemin `data/graph.json`) depuis l'arbre de travail,
et, partout ailleurs, le dépôt même où tourne le contrôle, dans sa géométrie
(`data/graph.json` dans un clone public, `site/data/graph.json` dans un clone
de l'arbre de travail). La référence est `--ref` ; par défaut, le commit le
plus récent dont le graphe diffère de celui qu'on contrôle, à défaut `HEAD~1`.
Le contrôle comparait `HEAD` à lui-même dans un clone public, et sortait en 0
avec un avertissement dans le clone du selftest (audit du 13/09, C-2) : il
échoue maintenant quand aucun graphe antérieur ne se lit, sauf
`--allow-no-reference` (premier build). Un historique complet est donc requis :
la CI clone avec `fetch-depth: 0`.

Sortie 1 si un identifiant est perdu ou ne désigne plus une notice unique, ou si
aucune référence ne se lit ; sortie 0 sinon.

    python3 site/build-c/qa/check_source_id_continuity.py
    python3 site/build-c/qa/check_source_id_continuity.py --ref <commit>
    python3 site/build-c/qa/check_source_id_continuity.py --previous chemin/vers/graph.json
    python3 site/build-c/qa/check_source_id_continuity.py --public-tree ../origenality-public
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(BUILD, "tools"))
from tree_paths import data_dir, repository_root  # noqa: E402

ROOT = repository_root(HERE)


def shown(path: str) -> str:
    """a path as printed: relative to the repository, never a machine path"""
    try:
        rel = os.path.relpath(path, ROOT)
    except ValueError:
        return os.path.basename(path)
    return rel if not rel.startswith("..") else os.path.join("..", os.path.basename(os.path.abspath(path)))


def git(tree: str, *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", tree, *arguments], capture_output=True)


def graph_path_in(tree: str) -> str:
    """Le chemin du graphe dans un dépôt, selon sa géométrie."""
    return ("site/data/graph.json" if os.path.isdir(os.path.join(tree, "site", "build-c"))
            else "data/graph.json")


def reference_tree(args) -> str:
    if args.public_tree:
        return os.path.abspath(args.public_tree)
    if os.path.isdir(os.path.join(ROOT, "site", "build-c")):
        sibling = os.path.join(os.path.dirname(ROOT), "origenality-public")
        if git(sibling, "rev-parse", "--is-inside-work-tree").returncode == 0 \
                and not os.path.samefile(sibling, ROOT):
            return sibling
    return ROOT


def blob_id(data: bytes) -> str:
    """L'identifiant git d'un contenu (`git hash-object`)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def default_ref(tree: str, path: str, current: bytes) -> tuple[str | None, str]:
    """Le commit le plus récent dont `path` diffère du graphe contrôlé, sinon HEAD~1."""
    here = blob_id(current)
    log = git(tree, "log", "--format=%H", "--", path)
    for sha in log.stdout.decode().split() if log.returncode == 0 else []:
        blob = git(tree, "rev-parse", "--verify", "-q", "%s:%s" % (sha, path))
        if blob.returncode == 0 and blob.stdout.decode().strip() != here:
            return sha, "the most recent commit whose graph differs"
    if git(tree, "rev-parse", "--verify", "-q", "HEAD~1").returncode == 0:
        return "HEAD~1", "no commit with another graph; HEAD~1"
    return None, "no earlier commit in the history"


def previous_graph(args, current: bytes) -> tuple[dict | None, str]:
    if args.previous:
        with open(args.previous, encoding="utf-8") as fh:
            return json.load(fh), shown(args.previous)
    tree = reference_tree(args)
    path = graph_path_in(tree)
    if git(tree, "rev-parse", "--is-inside-work-tree").returncode != 0:
        return None, "%s is not a git repository" % shown(tree)
    if args.ref:
        ref, how = args.ref, "given with --ref"
    else:
        ref, how = default_ref(tree, path, current)
    if ref is None:
        return None, "%s:%s in %s (%s)" % ("?", path, shown(tree), how)
    label = "%s:%s in %s (%s)" % (ref[:12], path, shown(tree), how)
    out = git(tree, "show", "%s:%s" % (ref, path))
    if out.returncode:
        return None, label
    return json.loads(out.stdout.decode("utf-8")), label


def source_ids(node: dict) -> list[tuple[str, str]]:
    """the (source, id) pairs a published record carries; before 24 August 2026
    a record carried one, as its `ppn` under its first `src`"""
    if node.get("source_ids"):
        return [(e.get("source") or "", str(e["id"])) for e in node["source_ids"] if e.get("id") not in (None, "")]
    if node.get("ppn"):
        return [((node.get("src") or [""])[0], str(node["ppn"]))]
    return []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="source ids of the previous published graph still resolve")
    ap.add_argument("--previous", help="a previous graph.json, instead of the public tree")
    ap.add_argument("--public-tree", help="the public tree to read the previous graph from")
    ap.add_argument("--ref", default=None,
                    help="the commit to compare with (default: the most recent commit whose graph "
                         "differs from the current one, else HEAD~1)")
    ap.add_argument("--allow-no-reference", action="store_true",
                    help="exit 0 when no earlier graph can be read (a first build)")
    args = ap.parse_args(argv)

    new_path = os.path.join(data_dir(ROOT), "graph.json")
    with open(new_path, "rb") as fh:
        current = fh.read()
    old, label = previous_graph(args, current)
    if old is None:
        if args.allow_no_reference:
            print(f"notice: no previous published graph could be read ({label}); "
                  f"continuity not checked (--allow-no-reference)")
            return 0
        print(f"FAIL: no previous published graph could be read ({label}); a clone needs its "
              f"history (fetch-depth 0), or pass --ref, --previous or --allow-no-reference")
        return 1
    new = json.loads(current.decode("utf-8"))

    pairs: set[tuple[str, str]] = set()
    by_id: dict[str, set[str]] = {}
    for node in new["nodes"]:
        if node.get("k") != "pub":
            continue
        for source, ident in source_ids(node):
            pairs.add((source, ident))
            by_id.setdefault(ident, set()).add(node.get("ppn") or node.get("id"))

    total = by_pair = by_bare = 0
    lost, ambiguous = [], []
    for node in old["nodes"]:
        if node.get("k") != "pub":
            continue
        for source, ident in source_ids(node):
            total += 1
            if (source, ident) in pairs:
                by_pair += 1
            elif len(by_id.get(ident, ())) == 1:
                by_bare += 1
            elif ident in by_id:
                ambiguous.append(f"{source}:{ident}")
            else:
                lost.append(f"{source}:{ident}")

    print(f"previous: {label}")
    print(f"current:  {shown(new_path)}")
    print(f"{total} source ids published before: {by_pair} found under the same source, "
          f"{by_bare} under their id alone (source relabelled), {len(ambiguous)} ambiguous, {len(lost)} lost")
    if ambiguous:
        print("  ambiguous (the id names several records and its source is gone): " + ", ".join(ambiguous[:20])
              + (" …" if len(ambiguous) > 20 else ""))
    if lost:
        print("  lost: " + ", ".join(lost[:20]) + (" …" if len(lost) > 20 else ""))
    if lost or ambiguous:
        print("FAIL: a link made on the previous build would no longer open its record")
        return 1
    print("ok: every record link of the previous build still opens its record")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
