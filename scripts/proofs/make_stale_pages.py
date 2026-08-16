#!/usr/bin/env python3
"""Une copie des pages du site dont un chiffre publié a été retouché à la main.

    python3 scripts/proofs/make_stale_pages.py <répertoire>

Le contrôle négatif du garde-fou des chiffres. `build_semantic.py` refusait
autrefois d'écrire quand ses comptes différaient de ceux tapés dans les pages ;
il écrit maintenant, puis fait réécrire les pages par `build_summary_figures.py`.
Le garde-fou a changé de place : ce n'est plus l'écriture qui est refusée, c'est
`--check` qui doit sortir en 1 dès qu'une page ne porte plus le texte que le
générateur produirait.

Encore faut-il que ce refus arrive vraiment. On copie donc le répertoire du site,
on change UN chiffre dans un bloc balisé, et le harnais attend un code 1 sur la
copie. Le site publié n'est pas touché.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
# Le prototype s'appelle `build-c` dans le dépôt de travail et `site` dans
# l'arbre public : on prend celui qui existe.
BUILD = next((path for path in (ROOT / "site" / "build-c", ROOT / "site")
              if (path / "index.html").exists()), ROOT / "site" / "build-c")

# Le bloc retouché et la retouche : un compte de la population, dans l'en-tête
# de l'Explorer, remplacé par un nombre qu'aucune donnée ne donne.
BLOCK = "FIGURES:population-scope"
FAKE = "9 999"


def main(argv):
    if len(argv) != 1:
        return "usage: make_stale_pages.py <répertoire>"
    target = Path(argv[0])
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(BUILD, target, ignore=shutil.ignore_patterns("screenshots"))

    page = target / "index.html"
    text = page.read_text(encoding="utf-8")
    pattern = re.compile(
        r"(<!-- %s -->.*?<b>)([^<]+)(</b>)" % re.escape(BLOCK), re.DOTALL)
    updated, count = pattern.subn(lambda m: m.group(1) + FAKE + m.group(3), text)
    if count != 1:
        return ("REFUS : le bloc « %s » n'a pas été trouvé une fois et une seule dans %s"
                % (BLOCK, page))
    page.write_text(updated, encoding="utf-8")
    print("copie du site dans %s" % target)
    print("un compte du bloc « %s » remplacé par %s dans index.html" % (BLOCK, FAKE))
    print("le contrôle des chiffres doit maintenant sortir en 1 sur cette copie")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
