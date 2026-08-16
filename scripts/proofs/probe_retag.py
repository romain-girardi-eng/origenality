#!/usr/bin/env python3
"""Un tag corrigé arrive-t-il jusqu'à l'arbre publié ?

Audit 4, finding A4-4 : le tagueur écrit en ajout, l'arbre prenait la première
ligne de chaque notice — une notice retaguée gardait donc son ancien thème pour
toujours. Le sondage pose le cas de bout en bout, sur un fichier minuscule :

  1. une notice taguée « god.logos », puis retaguée « anthropology.free-will » ;
  2. l'arbre est reconstruit sur le fichier tel quel (deux lignes) ;
  3. l'arbre doit porter le NOUVEAU thème et pas l'ancien ;
  4. le compactage de fin de vague ramène le fichier à une ligne, et l'historique
     à côté reçoit la seule ligne périmée — pas l'état courant, qui y serait
     recopié à chaque passe.

    python3 scripts/proofs/probe_retag.py --work data/_proofs_tmp/retag

Sortie 0 si l'arbre a suivi la correction, 1 sinon.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "semantic"))

import tags_io  # noqa: E402

OLD_THEME = "god.logos"
NEW_THEME = "anthropology.free-will"
NOTICE = "ORPROOF000001"


def tag(theme: str, digest: str) -> dict:
    return {
        "notice_id": NOTICE, "input_digest": digest,
        "relevance": "core", "relevance_none_reason": "not-applicable",
        "relevance_floor_applied": False,
        "works": ["unspecified"], "themes": [theme], "approaches": ["doctrinal"],
        "confidence": 0.9, "justification": "cas de contrôle du harnais",
        "needs_review": False, "wave": "proof",
        "prompt_version": "tag-notice-v2",
    }


def themes_in_tree(tree: dict) -> set:
    """Feuilles de thème que l'arbre attribue à la notice de contrôle.

    Une feuille est un nœud dont le `node_id` porte un identifiant à deux
    niveaux (« themes:anthropology.free-will ») ; les domaines n'en ont qu'un.
    """
    found = set()

    def walk(node):
        node_id = str(node.get("node_id") or "")
        leaf = node_id.split(":", 1)[1] if ":" in node_id else ""
        if "." in leaf and NOTICE in (node.get("notice_ids") or []):
            found.add(leaf)
        for child in node.get("nodes") or []:
            walk(child)

    for axis in tree.get("axes") or []:
        if axis.get("axis") == "themes":
            walk(axis["root"])
    return found


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", default=str(ROOT / "data" / "_proofs_tmp" / "retag"))
    arguments = parser.parse_args(argv)

    work = Path(arguments.work)
    work.mkdir(parents=True, exist_ok=True)
    tags = work / "tags.jsonl"
    notices = work / "notices.jsonl"
    tree_path = work / "topic_tree.json"

    notices.write_text(json.dumps(
        {"notice_id": NOTICE, "title": "Contra Celsum, notice de contrôle",
         "year": 2020, "language": "fr"}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    with tags.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(tag(OLD_THEME, "aaaa1111"), ensure_ascii=False) + "\n")
        handle.write(json.dumps(tag(NEW_THEME, "bbbb2222"), ensure_ascii=False) + "\n")

    print("fichier de tags : 2 lignes, une seule notice (%s)" % NOTICE)
    print("  ligne 1 : %s" % OLD_THEME)
    print("  ligne 2 : %s  (la correction)" % NEW_THEME)

    command = [sys.executable, str(ROOT / "semantic" / "tree" / "build_topic_tree.py"),
               "--tags", str(tags), "--notices", str(notices),
               "--output", str(tree_path), "--wave", "proof"]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        return 1

    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    leaves = themes_in_tree(tree)
    print("thèmes portés par l'arbre : %s" % (sorted(leaves) or "aucun"))
    status = 0
    if NEW_THEME not in leaves:
        print("ÉCHEC : l'arbre ne porte pas le thème corrigé %s" % NEW_THEME)
        status = 1
    if OLD_THEME in leaves:
        print("ÉCHEC : l'arbre porte encore l'ancien thème %s" % OLD_THEME)
        status = 1
    if status == 0:
        print("l'arbre porte le thème corrigé, et lui seul")

    report = tags_io.compact(tags)
    lines = len(tags.read_text(encoding="utf-8").splitlines())
    history = work / "tags.history.jsonl"
    history_lines = len(history.read_text(encoding="utf-8").splitlines()) if history.exists() else 0
    print("compactage de fin de vague : %d ligne(s) gardée(s), %d périmée(s), "
          "historique %d ligne(s) — la seule ligne périmée, pas l'état courant"
          % (lines, report["superseded"], history_lines))
    if lines != 1 or report["superseded"] != 1 or history_lines != 1:
        print("ÉCHEC : le compactage n'a pas fait ce qu'il annonce")
        status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
