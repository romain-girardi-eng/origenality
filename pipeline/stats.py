#!/usr/bin/env python3
"""Origenality — statistiques de champ sur le corpus fusionné.

Usage : stats.py [--top N]

Deux règles gouvernent cette sortie.

1. Trois ensembles, jamais deux. `noise_guess` vaut true, false ou null, et
   null ne veut pas dire « pertinent » : il veut dire « non tranché ». Les
   comptes sont donc toujours donnés en trois colonnes étiquetées — sûr
   (false), non classé (null), bruit (true) — et jamais additionnés en un
   « hors bruit » qui ferait passer des milliers de notices non examinées pour
   de la bibliographie origénienne.

2. Harmonisation avant comptage. Les champs de date, de langue et de type
   diffèrent d'une source à l'autre ; ils passent tous par `fields.py`, faute
   de quoi Adamantius disparaît des séries chronologiques (il date par
   `year_bib_parsed`), l'allemand se scinde en `de` et `ge`, et les types
   d'IxTheo, de BIBP et de Semantic Scholar tombent en « ? ».

Les éditions des œuvres d'Origène (relation=by) restent écartées : sources
primaires, pas littérature secondaire.
"""
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fields import norm_lang, norm_type, norm_year, raw_type  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(BASE, "data", "merged", "corpus.jsonl")

BUCKETS = [("sur", "sûr (noise_guess=false)"),
           ("non_classe", "non classé (noise_guess=null)"),
           ("bruit", "bruit (noise_guess=true)")]
SERIES_FROM, SERIES_TO = 2010, 2025


def bucket_of(record):
    flag = record.get("noise_guess")
    if flag is True:
        return "bruit"
    if flag is False:
        return "sur"
    return "non_classe"


class Bucket:
    def __init__(self):
        self.n = 0
        self.lang = Counter()
        self.year = Counter()
        self.lang_year = defaultdict(Counter)
        self.source = Counter()
        self.type = Counter()
        self.raw_unmapped = Counter()


def table(title, buckets, extract, top):
    """Trois colonnes étiquetées, ordonnées par le total des trois."""
    keys = Counter()
    for bucket in buckets.values():
        for key, count in extract(bucket).items():
            keys[key] += count
    print(f"\n{title}")
    print(f"  {'':<28}{'sûr':>9}{'non classé':>12}{'bruit':>9}")
    for key, _ in keys.most_common(top):
        row = "".join("%*d" % (width, extract(buckets[name]).get(key, 0))
                      for (name, _label), width in zip(BUCKETS, (9, 12, 9)))
        print(f"  {str(key):<28}{row}")


def main():
    if "--include-noise" in sys.argv:
        print("note : --include-noise n'a plus d'objet, les trois ensembles "
              "sont toujours rapportés séparément.\n")
    top = 12
    if "--top" in sys.argv:
        top = int(sys.argv[sys.argv.index("--top") + 1])

    buckets = {name: Bucket() for name, _ in BUCKETS}
    total = 0
    editions = 0
    with open(CORPUS) as f:
        for line in f:
            record = json.loads(line)
            total += 1
            if record.get("relation") == "by":
                editions += 1
                continue
            bucket = buckets[bucket_of(record)]
            bucket.n += 1
            lang = norm_lang(record.get("language"))
            bucket.lang[lang] += 1
            year = norm_year(record)
            if year and 1800 <= year <= 2026:
                bucket.year[year] += 1
                bucket.lang_year[lang][year] += 1
            for source in record.get("sources", []):
                bucket.source[source["source"]] += 1
            doctype = norm_type(record)
            bucket.type[doctype] += 1
            if doctype == "other":
                bucket.raw_unmapped[raw_type(record)] += 1

    kept = total - editions
    print(f"Corpus fusionné : {total} notices")
    print(f"Éditions d'Origène écartées (relation=by) : {editions}")
    print(f"Restent {kept} notices, en trois ensembles distincts :")
    for name, label in BUCKETS:
        n = buckets[name].n
        print(f"  {label:<34} {n:>6}  ({100.0 * n / kept:.1f} %)")
    print("  — « sûr » et « non classé » ne s'additionnent pas : le second est "
          "un stock non examiné, pas une bibliographie.")

    table("Par langue :", buckets, lambda b: b.lang, top)
    table("Par source (une notice fusionnée compte pour chaque source) :",
          buckets, lambda b: b.source, top)
    table("Par type harmonisé (« ? » = aucun champ de type dans la notice) :",
          buckets, lambda b: b.type, 8)
    table("Par décennie :", buckets,
          lambda b: Counter((y // 10) * 10 for y in b.year.elements()), 20)

    for name, label in BUCKETS:
        bucket = buckets[name]
        print(f"\nProduction {SERIES_FROM}-{SERIES_TO}, ensemble « {label} », "
              f"top-5 langues :")
        for lang, _ in bucket.lang.most_common(5):
            series = [bucket.lang_year[lang].get(y, 0)
                      for y in range(SERIES_FROM, SERIES_TO + 1)]
            print(f"  {lang:<5}: {series}")

    unmapped = Counter()
    for bucket in buckets.values():
        unmapped.update(bucket.raw_unmapped)
    if unmapped:
        print("\nTypes bruts présents mais non mappés (top 10) — à verser dans "
              "fields.TYPE_MAP si nécessaire :")
        for value, count in unmapped.most_common(10):
            print(f"  {value!r:<40} {count}")


if __name__ == "__main__":
    main()
