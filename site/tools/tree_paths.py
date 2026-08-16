#!/usr/bin/env python3
"""Où sont les fichiers, dans un arbre de travail comme dans un clone public.

Les outils du site vivaient sous `site/build-c/tools/` et comptaient les marches
jusqu'à la racine du dépôt. La passe de publication supprime une marche — le
prototype perd son nom, `site/build-c/` devient `site/` — et une racine comptée
en marches désigne alors le répertoire AU-DESSUS du dépôt : l'outil cherche ses
données dehors, et l'audit 6 l'a fait sortir en 1 sur un clone propre.

On cherche donc la racine vers le haut, à ses documents, et la couche de données
au nom qu'elle porte de ce côté-ci (`site/data/` dans le dépôt de travail,
`data/` dans l'arbre public, où c'est ce que demandent les `fetch()` des pages).
Un outil n'a plus à savoir dans quelle géométrie il tourne.
"""
from __future__ import annotations

import os

MARKERS = ("CITATION.cff", "README.md")


def repository_root(start: str) -> str:
    """Le premier répertoire, en remontant, qui porte les documents de racine."""
    current = os.path.abspath(start)
    while True:
        if all(os.path.exists(os.path.join(current, name)) for name in MARKERS):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            # Aucun marqueur trouvé : on rend ce qu'un compte de marches aurait
            # rendu, pour que l'erreur qui suit nomme un chemin plutôt qu'une
            # exception de remontée.
            return os.path.abspath(os.path.join(start, "..", ".."))
        current = parent


def data_dir(root: str) -> str:
    """La couche de données du site, sous le nom qu'elle porte dans cet arbre."""
    for candidate in (os.path.join(root, "site", "data"), os.path.join(root, "data")):
        if os.path.exists(os.path.join(candidate, "graph.json")):
            return candidate
    return os.path.join(root, "site", "data")
