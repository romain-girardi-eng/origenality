#!/usr/bin/env python3
"""Chemins de travail de la chaîne Adamantius, relatifs au dépôt.

Les trois étapes — moisson des fiches, grille section × année, analyse — se
passaient des fichiers par un répertoire absolu propre à une machine — un
chemin temporaire du poste de travail — ou par des entrées qu'aucun script ne produisait
(`scripts/adam_html`, `scripts/form.html`). La chaîne ne repartait donc pas
ailleurs. Tout passe désormais par un seul répertoire de travail, sous le
dépôt, redéfinissable par `ORIGENALITY_ADAM_WORK` :

    data/raw/adamantius/work/
        html/          une page schedasingola par fiche  (adam_fetch.py)
        grid/          une page de résultats par section × année (adam_grid.py)
        form.html      le formulaire de recherche, d'où sortent les sections

`form.html` n'est pas un fichier à fournir à la main : `ensure_form()` le
télécharge s'il manque, depuis la page de recherche du site, et le garde.

Le contenu de ce répertoire est du cache de moisson : il se reconstruit, il
n'est pas versionné.
"""
import os
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.environ.get(
    "ORIGENALITY_ADAM_WORK",
    os.path.join(BASE, "data", "raw", "adamantius", "work"))

HTML_DIR = os.path.join(WORK, "html")
GRID_DIR = os.path.join(WORK, "grid")
FORM_PATH = os.path.join(WORK, "form.html")
LOG_PATH = os.path.join(WORK, "adam_fetch.log")

SITE = "http://www2.classics.unibo.it/adamantius/"
FORM_URL = SITE + "index.php?page=ricerca"
UA = ("OrigenalityBot/1.0 (academic research, PhD thesis; "
      "romain.girardi@univ-cotedazur.fr)")


def ensure_dirs():
    for path in (WORK, HTML_DIR, GRID_DIR):
        os.makedirs(path, exist_ok=True)


def ensure_form(url=FORM_URL, timeout=60):
    """Renvoie le HTML du formulaire de recherche, en le téléchargeant une fois.

    Le fichier était supposé présent et ne l'était jamais sur une machine
    neuve : deux scripts s'arrêtaient sur une FileNotFoundError sans dire quoi
    faire."""
    ensure_dirs()
    if os.path.exists(FORM_PATH) and os.path.getsize(FORM_PATH) > 500:
        with open(FORM_PATH, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", "replace")
    with open(FORM_PATH, "w", encoding="utf-8") as handle:
        handle.write(body)
    return body
