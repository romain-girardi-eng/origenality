#!/usr/bin/env python3
"""Les chiffres publiés viennent-ils tous d'un bloc généré ?

    python3 scripts/proofs/probe_published_figures.py

Deux contrôles. D'abord la présence des balises : un bloc généré qui perd ses
balises redevient du texte tapé à la main sans que rien ne le dise. Ensuite la
chasse aux chiffres périmés que l'audit a relevés dans Method — un compte de
grappes et deux pourcentages par langue qui n'étaient plus ceux des données.

Sortie 0 si les balises sont là et qu'aucun chiffre périmé ne subsiste.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

BLOCKS = {
    "site/build-c/index.html": ("FIGURES:population-meta", "FIGURES:population-scope",
                                "FIGURES:population-held"),
    "site/build-c/observatoire.html": ("FIGURES:population-meta", "FIGURES:population-lede",
                                       "FIGURES:population-reservoir",
                                       "FIGURES:population-languages",
                                       "FIGURES:population-themes"),
    "site/build-c/methode.html": ("FIGURES:summary-provenance", "FIGURES:citation-coverage",
                                  "FIGURES:population-stamp", "FIGURES:population-bias",
                                  "FIGURES:population-counted", "FIGURES:population-rule"),
    "site/build-c/credits.html": ("FIGURES:summary-provenance", "FIGURES:population-source"),
    "site/build-c/README.md": ("FIGURES:summary-provenance", "FIGURES:population-reservoirs",
                               "FIGURES:population-screen", "FIGURES:population-weights",
                               "FIGURES:population-untagged"),
}

# Comptes de grappes que Method a publiés et qui n'existent plus. Les
# pourcentages par langue ne sont pas listés ici : ils sont désormais produits
# par `build_summary_figures.py`, et c'est son `--check` qui dit s'ils sont à
# jour — inscrire une valeur en dur ici la figerait à nouveau.
STALE = ("42 246", "42246", "42 205", "42205")

# La population de la vague 1, que le site a affichée jusqu'au 16 août : elle ne
# doit plus apparaître nulle part, ni en prose ni dans une balise de description.
STALE_POPULATION = ("1 400", "1400")
POPULATION_PAGES = ("site/build-c/index.html", "site/build-c/observatoire.html",
                    "site/build-c/methode.html", "site/build-c/credits.html",
                    "site/build-c/README.md")


def main():
    status = 0
    for name, marks in BLOCKS.items():
        text = (ROOT / name).read_text(encoding="utf-8")
        for mark in marks:
            opener, closer = "<!-- %s -->" % mark, "<!-- /%s -->" % mark
            present = opener in text and closer in text
            print("%-30s %-32s %s" % (name, mark, "balisé" if present else "BALISES ABSENTES"))
            if not present:
                status = 1

    coverage = json.loads((ROOT / "data" / "derived" / "citations_coverage.json")
                          .read_text(encoding="utf-8"))
    print("citations_coverage.json : %d grappes, %d mesurées, %.1f %%"
          % (coverage["clusters"], coverage["measured"], 100 * coverage["coverage"]))

    page = (ROOT / "site" / "build-c" / "methode.html").read_text(encoding="utf-8")
    for value in STALE:
        if value in page:
            print("CHIFFRE PÉRIMÉ ENCORE PUBLIÉ : %s" % value)
            status = 1

    for name in POPULATION_PAGES:
        text = (ROOT / name).read_text(encoding="utf-8")
        for value in STALE_POPULATION:
            if value in text:
                print("POPULATION DE LA VAGUE 1 ENCORE PUBLIÉE : %s dans %s" % (value, name))
                status = 1
    if status == 0:
        print("aucun chiffre périmé ne subsiste : ni les comptes de grappes relevés par "
              "l'audit, ni la population de la vague 1")
    return status


if __name__ == "__main__":
    sys.exit(main())
