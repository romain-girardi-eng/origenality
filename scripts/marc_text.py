#!/usr/bin/env python3
"""Origenality — nettoyage des artefacts d'export MARC dans les textes K10plus.

Les résumés de la zone 520 arrivent de K10plus avec des dégâts d'encodage qui
ne sont pas du texte : un `?` de substitution là où l'original portait un tiret,
une apostrophe typographique ou des guillemets, et un `0` de délimiteur de
sous-zone resté collé à la phrase précédente — « … die Freiheit des Menschen
stehen.0Alfons Fürst beschreibt … ». Affichés tels quels, ils se lisent comme
des fautes de la source.

Le nettoyage se fait à l'ingestion, jamais au rendu : une donnée réparée à
l'affichage reste fausse dans le fichier, et chaque consommateur devrait
refaire le travail.

Règles, toutes conservatrices — on ne corrige que ce qui ne peut pas être du
texte légitime :

  marc-delimiter    « stehen.0Alfons », « Augustine.00In » : un ou deux zéros
                    entre une fin de phrase et le début d'une autre. Il faut un
                    MOT avant le point (deux minuscules au moins) et une
                    capitale suivie d'une minuscule après : « v.0Alpha » est un
                    numéro de version, pas une phrase, et reste intact.
  year-range        « (185?253/54) » : un `?` entre deux MILLÉSIMES est un
                    tiret. Trois conditions, toutes exigées : les deux nombres
                    tombent dans les bornes d'un millésime (100-2099), leur
                    écart est croissant et inférieur à deux siècles, et rien
                    n'annonce une référence juste avant. Une cote « Ms. 123?456 »
                    échoue aux deux dernières et garde son point d'interrogation.
  genitive          « God?s will » : un `?` entre une lettre et « s » suivi
                    d'une espace est une apostrophe.
  quotes            « Als ?das Wunder der christlichen Welt? gepriesen » : une
                    paire dont la seconde moitié est suivie d'une minuscule.
                    Un vrai point d'interrogation est suivi d'une capitale ;
                    la règle ne le touche pas.
  dash              « bleiben ? das war », « panton ? and » : un `?` isolé
                    entre deux espaces, après une minuscule ET avant une
                    minuscule. L'allemand et l'anglais ne mettent jamais
                    d'espace avant un point d'interrogation — le français, si :
                    les textes déclarés français sont exclus de cette règle et
                    de la précédente. La minuscule qui suit est ce qui
                    distingue l'incise du vrai point d'interrogation : une
                    phrase interrogative est suivie d'une capitale, et
                    « Wer war Origenes ? Adamantius … » reste intact.
  soft-hyphen       le tiret conditionnel U+00AD, invisible et coupant les mots
                    à la recherche, est retiré.

`normalise_marc_text` renvoie le texte réparé et la liste des règles
appliquées : rien n'est corrigé en silence.
"""
from __future__ import annotations

import re

SOFT_HYPHEN = "­"

# Un `0` de délimiteur ne recolle une phrase que s'il y a une phrase des deux
# côtés : au moins deux minuscules avant le point — « stehen », « Augustine » —,
# et une capitale suivie d'une minuscule après. Une initiale isolée n'est pas un
# mot : « v.0Alpha » est un numéro de version, et il reste intact.
RULES = (
    ("marc-delimiter",
     re.compile(r"(?<=[a-zäöüßéèàçñ][a-zäöüßéèàçñ])\.0{1,2}"
                r"(?=[A-ZÄÖÜÉ][a-zäöüßéèàçñ])"), ". "),
    ("genitive", re.compile(r"(?<=[A-Za-zÄÖÜäöü])\?(?=s\s)"), "’"),
)

# Un `?` entre deux nombres n'est un tiret que si les deux nombres sont des
# millésimes plausibles ET si le contexte n'annonce pas une référence. Une cote
# « Ms. 123?456 » a la forme d'un intervalle sans en être un : deux gardes
# indépendants la retiennent — l'écart de 333 ans, et le mot de cote qui
# précède.
#
# La borne basse est 100, pas 1000 : le corpus porte les dates d'Origène
# (« Alexandria (185?253/54) », la seule réparation `year-range` réelle des
# quatre du fonds). Fixer le plancher au premier millénaire reviendrait à
# n'accepter aucune date patristique — dans un corpus de patristique.
YEAR_RANGE = re.compile(r"(?<![\d/.-])(\d{3,4})\?(\d{3,4})(?![\d])")
YEAR_MIN, YEAR_MAX = 100, 2099
MAX_YEAR_SPAN = 200
REFERENCE_CUE = re.compile(
    r"\b(?:ms|mss|cod|codd|cote|inv|sign|nr|no|n|vol|bd|t|tome|fasc|heft|col|"
    r"p|pp|s|ff|abb|fig|taf)\.?\s*$", re.IGNORECASE)

QUOTES = re.compile(r"(?<=\s)\?([A-Za-zÄÖÜäöü][^?]{0,200}?[A-Za-zÄÖÜäöü])\?(?=\s+[a-zäöüß])")
DASH = re.compile(r"(?<=[a-zäöüß])\s\?\s(?=[a-zäöüß])")


def _year_range(match) -> str:
    """Remplace le `?` par un tiret, ou laisse le texte tel quel."""
    first, second = int(match.group(1)), int(match.group(2))
    if not (YEAR_MIN <= first <= YEAR_MAX and YEAR_MIN <= second <= YEAR_MAX):
        return match.group(0)
    if not 0 < second - first <= MAX_YEAR_SPAN:
        return match.group(0)
    before = match.string[:match.start()]
    if REFERENCE_CUE.search(before):
        return match.group(0)
    return "%d–%d" % (first, second)


def normalise_marc_text(text, language=None):
    """Renvoie (texte réparé, règles appliquées). Laisse tout le reste intact."""
    if not isinstance(text, str) or not text:
        return text, []
    applied = []
    cleaned = text

    if SOFT_HYPHEN in cleaned:
        cleaned = cleaned.replace(SOFT_HYPHEN, "")
        applied.append("soft-hyphen")

    for name, pattern, replacement in RULES:
        repaired, count = pattern.subn(replacement, cleaned)
        if count:
            cleaned = repaired
            applied.append(name)

    repaired = YEAR_RANGE.sub(_year_range, cleaned)
    if repaired != cleaned:
        cleaned = repaired
        applied.append("year-range")

    # Le français met une espace insécable avant le point d'interrogation : les
    # deux règles qui lisent « ? » entouré d'espaces comme un artefact ne
    # peuvent pas s'y appliquer.
    if str(language or "").lower()[:3] not in {"fre", "fra", "fr"}:
        repaired, count = QUOTES.subn("“\\1”", cleaned)
        if count:
            cleaned = repaired
            applied.append("quotes")
        repaired, count = DASH.subn(" – ", cleaned)
        if count:
            cleaned = repaired
            applied.append("dash")

    return cleaned, applied


def normalise_record(record, fields=("abstract", "title")):
    """Applique le nettoyage aux champs textuels d'une notice, en place.

    Renvoie la liste des règles appliquées, préfixées du champ."""
    applied = []
    language = record.get("language")
    for name in fields:
        value = record.get(name)
        cleaned, rules = normalise_marc_text(value, language)
        if rules:
            record[name] = cleaned
            applied.extend(f"{name}:{rule}" for rule in rules)
    if applied:
        record["marc_normalised"] = sorted(set(applied))
    return applied


def main(argv):
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description=("Applique le nettoyage MARC à un fichier de notices déjà "
                     "moissonné, sans y retourner sur le réseau."),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)

    records = []
    changed = 0
    counts = {}
    for line in arguments.path.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        applied = normalise_record(record)
        if applied:
            changed += 1
            for rule in applied:
                counts[rule] = counts.get(rule, 0) + 1
        records.append(record)

    if not arguments.dry_run:
        temporary = arguments.path.with_suffix(arguments.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        temporary.replace(arguments.path)

    print(json.dumps({"path": str(arguments.path), "records": len(records),
                      "records_changed": changed, "rules": counts,
                      "dry_run": bool(arguments.dry_run)},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
