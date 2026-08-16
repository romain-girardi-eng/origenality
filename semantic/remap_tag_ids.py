#!/usr/bin/env python3
"""Origenality — report des tags sémantiques d'un corpus fusionné sur le suivant.

`origenality_id` est dérivé du contenu d'une grappe : corriger la fusion
(patronyme du premier auteur, tomes distincts séparés, collisions d'identité
levées) renumérote les grappes touchées. Les tags produits sur l'ancien corpus
seraient alors orphelins. Ce module fait le report, et il le fait sur une
identité qui, elle, ne bouge pas : la liste des couples source/source_id, qui
désigne des notices moissonnées, pas des grappes.

Deux modes.

  --build-map   compare l'ancien et le nouveau corpus, écrit une table
                ancien identifiant → nouveaux identifiants (avec le nombre de
                notices sources partagées, qui sert de vote).
  --apply       réécrit un fichier de tags sous les nouveaux identifiants.

Un ancien identifiant peut viser plusieurs nouveaux : l'ancienne grappe a été
scindée (deux tomes, deux publications homonymes). Le tag, lui, a été produit
sur une seule fiche de métadonnées. On tranche alors par l'empreinte d'entrée
`input_digest`, que `tag_notices.payload_digest` recalcule à l'identique sur la
grappe cible : la grappe dont la fiche redonne la même empreinte est celle qui a
été taguée. Faute de correspondance, le tag va à la grappe qui hérite du plus
grand nombre de notices sources et passe en `needs_review` — on ne fait pas
passer pour mesuré ce qui n'est qu'un choix par défaut.

Deux tags peuvent aussi viser la même nouvelle grappe : deux anciennes grappes
ont fusionné. On garde alors celui dont l'empreinte correspond à la nouvelle
fiche, à défaut le premier dans l'ordre du fichier, et on compte les écartés.

    python3 semantic/remap_tag_ids.py --build-map \\
        --old-corpus <ancien corpus.jsonl ou id<TAB>signature.tsv> \\
        --new-corpus data/merged/corpus.jsonl \\
        --out-map data/merged/id_remap_<date>.json

    python3 semantic/remap_tag_ids.py --apply \\
        --map data/merged/id_remap_<date>.json \\
        --tags semantic/waves/wave2_federated/tags.jsonl \\
        --corpus data/merged/corpus.jsonl \\
        --output semantic/waves/wave2_federated/tags.jsonl
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tag_notices import notice_payload, payload_digest  # noqa: E402
from tags_io import read_tags  # noqa: E402

REMAP_FIELDS = ("remapped_from", "remap_status")


def source_pairs(record):
    return ["%s:%s" % (s.get("source"), s.get("source_id"))
            for s in record.get("sources") or []]


def read_old(path: Path):
    """ancien identifiant → couples source/source_id.

    Accepte le corpus lui-même ou la table `id<TAB>signature` qu'on en tire
    avant de l'écraser (une fusion réécrit `corpus.jsonl` sur place)."""
    table = collections.defaultdict(set)
    if path.suffix == ".tsv":
        for line in path.open(encoding="utf-8"):
            line = line.rstrip("\n")
            if not line:
                continue
            oid, signature = line.split("\t", 1)
            table[oid].update(p for p in signature.split("|") if p)
        return table
    for line in path.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        table[record["origenality_id"]].update(source_pairs(record))
    return table


def build_map(old_path: Path, new_path: Path, out_path: Path):
    old = read_old(old_path)
    pair_to_new = {}
    new_ids = set()
    for line in new_path.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        new_ids.add(record["origenality_id"])
        for pair in source_pairs(record):
            pair_to_new[pair] = record["origenality_id"]

    table = {}
    unresolved = []
    for oid, pairs in old.items():
        votes = collections.Counter()
        for pair in pairs:
            target = pair_to_new.get(pair)
            if target:
                votes[target] += 1
        if not votes:
            unresolved.append(oid)
            continue
        table[oid] = [{"id": target, "shared_sources": count}
                      for target, count in sorted(votes.items(),
                                                  key=lambda kv: (-kv[1], kv[0]))]

    payload = {
        "old_corpus": str(old_path),
        "new_corpus": str(new_path),
        "old_ids": len(old),
        "new_ids": len(new_ids),
        "unchanged_ids": len(set(old) & new_ids),
        "mapped": len(table),
        "unresolved": unresolved,
        "split_clusters": sum(1 for v in table.values() if len(v) > 1),
        "map": table,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    summary = {k: v for k, v in payload.items() if k not in ("map", "unresolved")}
    summary["unresolved"] = len(unresolved)
    return summary


def load_corpus_digests(corpus_path: Path, wanted):
    """identifiant → (empreinte de la fiche d'entrée) pour les grappes visées."""
    digests = {}
    with Path(corpus_path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            oid = record.get("origenality_id")
            if oid in wanted:
                digests[oid] = payload_digest(notice_payload(record))
    return digests


# Proportion de lignes qu'un report doit savoir renuméroter pour avoir le droit
# d'écrire. Le garde « zéro correspondance » de l'itération 7 ne protégeait que
# du cas total : une table erronée qui résout fortuitement un seul identifiant
# sur 1 632 le passait, puis le report en place effaçait les 1 631 autres.
MIN_RESOLVED_SHARE = 0.95


def apply_map(map_path: Path, tags_path: Path, corpus_path: Path, out_path: Path,
              gold: bool = False, force: bool = False):
    table = json.loads(map_path.read_text(encoding="utf-8"))["map"]
    # Une notice, un tag : le DERNIER écrit. Reporter aussi les lignes qu'un
    # retag a périmées les ferait renaître sous le nouvel identifiant.
    rows = read_tags(tags_path, keep_unidentified=False)

    wanted = set()
    for row in rows:
        for entry in table.get(str(row.get("notice_id")), []):
            wanted.add(entry["id"])
    digests = load_corpus_digests(corpus_path, wanted)

    counts = collections.Counter()
    for row in rows:
        old_id = str(row.get("notice_id"))
        targets = table.get(old_id)
        if not targets:
            row["_new_id"] = None
            counts["orphan"] += 1
            continue
        if len(targets) == 1:
            row["_new_id"] = targets[0]["id"]
            counts["identity" if targets[0]["id"] == old_id else "unique"] += 1
            row["_status"] = ("identity" if targets[0]["id"] == old_id
                              else "unique-successor")
            continue
        matching = [t["id"] for t in targets
                    if digests.get(t["id"]) == row.get("input_digest")]
        if len(matching) == 1:
            row["_new_id"] = matching[0]
            row["_status"] = "digest-matched"
            counts["digest"] += 1
        else:
            row["_new_id"] = targets[0]["id"]
            row["_status"] = "majority-fallback"
            counts["fallback"] += 1

    # collisions : deux anciennes grappes fusionnées en une seule
    by_target = collections.defaultdict(list)
    for index, row in enumerate(rows):
        if row.get("_new_id"):
            by_target[row["_new_id"]].append(index)

    keep = set()
    dropped = 0
    for target, indices in by_target.items():
        if len(indices) == 1:
            keep.add(indices[0])
            continue
        exact = [i for i in indices
                 if digests.get(target) == rows[i].get("input_digest")]
        chosen = exact[0] if exact else indices[0]
        keep.add(chosen)
        dropped += len(indices) - 1

    # Garde-fou : un report qui n'a rien à reporter n'écrit rien. Appliqué à un
    # fichier d'une AUTRE numérotation — la vague 1 tague des PPN, pas des
    # identifiants de grappe —, le report trouvait 100 % d'orphelins et
    # réécrivait le fichier vide. Un outil de renumérotation n'a pas le droit
    # d'effacer ce qu'il ne sait pas renuméroter.
    resolved = sum(1 for row in rows if row.get("_new_id"))
    if rows and not resolved:
        raise SystemExit(
            "REFUS : aucune des %d lignes de %s ne se reporte sur %s — ce fichier "
            "n'est pas numéroté comme ce corpus, et il ne sera pas réécrit."
            % (len(rows), tags_path, corpus_path))
    share = resolved / len(rows) if rows else 1.0
    if rows and share < MIN_RESOLVED_SHARE and not force:
        raise SystemExit(
            "REFUS : %d des %d lignes de %s se reportent sur %s, soit %.1f %% "
            "(plancher %.0f %%). Un report qui perd une ligne sur vingt n'est pas "
            "un report : c'est une amputation. Passer --force pour l'assumer."
            % (resolved, len(rows), tags_path, corpus_path,
               100 * share, 100 * MIN_RESOLVED_SHARE))

    # Un report en place écrase le fichier d'entrée. La sauvegarde est écrite
    # AVANT toute écriture, même quand le garde de proportion a été forcé :
    # l'incident de la vague 1 s'est joué sur l'absence de cette copie.
    out_path = Path(out_path)
    tags_path = Path(tags_path)
    backup = None
    if out_path.exists() and out_path.resolve() == tags_path.resolve():
        backup = out_path.with_suffix(out_path.suffix + ".bak")
        backup.write_bytes(out_path.read_bytes())

    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with out_path.open("w", encoding="utf-8") as handle:
        for index, row in enumerate(rows):
            if index not in keep:
                continue
            new_id = row.pop("_new_id")
            status = row.pop("_status", "identity")
            row.pop("remapped_from", None)
            row.pop("remap_status", None)
            if new_id != row.get("notice_id"):
                row["remapped_from"] = row["notice_id"]
                row["remap_status"] = status
                row["notice_id"] = new_id
            # Un report par défaut est un doute, et il doit se voir. Sur un
            # enregistrement étalon, en revanche, `needs_review` décrit le
            # jugement de l'annotateur, pas la solidité du report : on ne le
            # réécrit pas, le statut de report suffit à le dire.
            if status == "majority-fallback" and not gold:
                row["needs_review"] = True
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1

    return {
        "tags_in": len(rows),
        "tags_out": written,
        "resolved_share": round(share, 4),
        "backup": str(backup) if backup else None,
        "dropped_on_merge": dropped,
        "orphans": counts["orphan"],
        "identity": counts["identity"],
        "unique_successor": counts["unique"],
        "digest_matched": counts["digest"],
        "majority_fallback": counts["fallback"],
    }


def main(argv):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--build-map", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--old-corpus", type=Path)
    parser.add_argument("--new-corpus", type=Path)
    parser.add_argument("--out-map", type=Path)
    parser.add_argument("--map", type=Path)
    parser.add_argument("--tags", type=Path)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--gold", action="store_true",
                        help="jeu étalon : ne pas réécrire needs_review sur un report par défaut")
    parser.add_argument("--force", action="store_true",
                        help="écrire malgré un taux de report inférieur au plancher")
    arguments = parser.parse_args(argv)

    if arguments.build_map:
        if not (arguments.old_corpus and arguments.new_corpus and arguments.out_map):
            parser.error("--build-map demande --old-corpus, --new-corpus, --out-map")
        summary = build_map(arguments.old_corpus, arguments.new_corpus,
                            arguments.out_map)
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        return 0

    if arguments.apply:
        if not (arguments.map and arguments.tags and arguments.corpus
                and arguments.output):
            parser.error("--apply demande --map, --tags, --corpus, --output")
        summary = apply_map(arguments.map, arguments.tags, arguments.corpus,
                            arguments.output, gold=arguments.gold,
                            force=arguments.force)
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        return 0

    parser.error("choisir --build-map ou --apply")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
