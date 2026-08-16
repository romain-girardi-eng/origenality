#!/usr/bin/env python3
"""Lecture d'un fichier de tags : une notice, un tag — le dernier écrit.

Le tagueur écrit en ajout : un enregistrement corrigé se pose à la fin du
fichier sans effacer le précédent, ce qui est la seule façon de survivre à une
interruption. En aval, en revanche, deux lignes pour une même notice ne sont pas
deux tags : c'est un tag et son brouillon. Prendre la PREMIÈRE — ce que faisait
l'arbre — publiait définitivement le thème qu'une reprise venait de corriger.

Ce module donne la règle, une fois, à tous les consommateurs : la dernière ligne
d'une notice l'emporte, et l'ordre de sortie est celui de la première apparition
de la notice, pour qu'un retag ne renumérote pas l'index entier.

    from tags_io import read_tags, compact
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator


def iter_lines(path) -> Iterator[tuple[int, dict[str, Any]]]:
    """(numéro de ligne, enregistrement) — les lignes illisibles sont sautées."""
    with Path(path).open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield number, json.loads(line)
            except ValueError:
                continue


def read_tags(path, keep_unidentified: bool = True) -> list[dict[str, Any]]:
    """Un enregistrement par `notice_id` : le dernier écrit, à sa première place.

    Les lignes sans `notice_id` sont rendues telles quelles quand
    `keep_unidentified`, pour que les contrôles de schéma les voient aussi.
    """
    order: list[str] = []
    latest: dict[str, dict[str, Any]] = {}
    loose: list[tuple[int, dict[str, Any]]] = []
    for number, record in iter_lines(path):
        notice = record.get("notice_id")
        if notice in (None, ""):
            if keep_unidentified:
                loose.append((number, record))
            continue
        key = str(notice)
        if key not in latest:
            order.append(key)
        latest[key] = record
    records = [latest[key] for key in order]
    records.extend(record for _number, record in loose)
    return records


def superseded_count(path) -> int:
    """Lignes rendues caduques par une écriture plus récente."""
    seen: dict[str, int] = {}
    total = 0
    for _number, record in iter_lines(path):
        notice = record.get("notice_id")
        if notice in (None, ""):
            continue
        key = str(notice)
        total += 1
        seen[key] = seen.get(key, 0) + 1
    return total - len(seen)


def compact(path, history_path=None) -> dict[str, int]:
    """Réécrit le fichier avec une ligne par notice, l'historique à côté.

    Appelé en fin de vague. L'historique n'est pas un doublon décoratif : c'est
    la trace de ce qui a été corrigé, et le fichier compacté ne la porte plus.
    Sans ligne caduque, rien n'est réécrit et aucun historique n'est créé.

    Il ne reçoit que les lignes périmées : compaction après compaction, il se lit
    comme un journal des corrections, sans que l'état courant y soit recopié à
    chaque passe.
    """
    path = Path(path)
    if not path.exists():
        return {"lines_in": 0, "lines_out": 0, "superseded": 0}
    lines_in = sum(1 for _number, _record in iter_lines(path))
    records = read_tags(path)
    superseded = lines_in - len(records)
    if superseded <= 0:
        return {"lines_in": lines_in, "lines_out": lines_in, "superseded": 0}

    # L'historique ne reçoit QUE les lignes périmées. Y verser le fichier entier
    # — ce que faisait la version précédente — produisait A, B, B, C après deux
    # compactions : une pile d'instantanés où l'état courant revient à chaque
    # passe, et dont on ne peut plus lire la suite des corrections. Ce qui est
    # conservé ici est exactement ce que le fichier compacté perd.
    last_line = {}
    for number, record in iter_lines(path):
        notice = record.get("notice_id")
        if notice not in (None, ""):
            last_line[str(notice)] = number

    history = Path(history_path) if history_path else path.with_suffix(".history.jsonl")
    with history.open("a", encoding="utf-8") as handle:
        for number, record in iter_lines(path):
            notice = record.get("notice_id")
            if notice in (None, "") or last_line.get(str(notice)) == number:
                continue
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    temporary = path.with_suffix(path.suffix + ".compact")
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    temporary.replace(path)
    return {"lines_in": lines_in, "lines_out": len(records),
            "superseded": superseded, "history": str(history)}
