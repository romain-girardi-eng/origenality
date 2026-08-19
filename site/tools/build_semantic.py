#!/usr/bin/env python3
"""Fold the controlled vocabulary and the tag records into one file for the front.

Reads   semantic/vocabulary/*.json                    the four axes, versioned
        semantic/waves/wave2_federated/tags.jsonl     the tag records, one per cluster
        data/merged/corpus.jsonl                      the cluster -> IxTheo PPN table
Writes  site/build-c/assets/semantic.json

The tags no longer come from the first wave. That file, `semantic/pilot/tags_ixtheo.jsonl`,
was overwritten during the seventh iteration and rebuilt from this very asset, so
reading it here made the site the source of its own input and carried a
reconstruction, not a measurement. The federated wave holds a record for every
cluster in scope, and the 1 632 IxTheo notices the site draws are among them: this
script joins them by the cluster's own identifier, read off the corpus, where each
cluster lists the source notices it was built from.

Nothing about the engine that produced the tags travels to the front: the run
identifier, the model field and the free-text justifications stay in the working
data. What the site needs is the vocabulary, the labels in four languages, and,
per publication, its themes, works, approaches and relevance class.

The three counts the pages print — works counted, mentioned only, held aside — used
to be typed into the prose of four pages, so this script refused to write whenever
its own counts disagreed with them. Refusing was the only honest thing it could do
while the numbers were hand-set, and it also meant the site could not follow its
own data. The numbers are now produced by `build_summary_figures.py` inside marked
blocks, exactly as the summary provenance and the citation coverage already were.
So the order is reversed: this script writes the asset, then calls that one, and
the pages come out of the same build as the file they describe. `--no-figures`
leaves the prose alone, and writing anywhere other than the published asset never
touches it.

    python3 site/build-c/tools/build_semantic.py
    python3 site/build-c/tools/build_semantic.py --out /tmp/semantic_next.json
    python3 site/build-c/tools/build_semantic.py --no-figures
"""

import argparse
import collections
import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.abspath(os.path.join(HERE, ".."))

sys.path.insert(0, HERE)
from tree_paths import data_dir, repository_root  # noqa: E402

# La racine se cherche, elle ne se compte pas : l'arbre public a une marche de
# moins que le dépôt de travail (voir `tree_paths`).
ROOT = repository_root(HERE)
DATA = data_dir(ROOT)
VOCAB = os.path.join(ROOT, "semantic", "vocabulary")
TAGS = os.path.join(ROOT, "semantic", "waves", "wave2_federated", "tags.jsonl")
CORPUS = os.path.join(ROOT, "data", "merged", "corpus.jsonl")
GRAPH = os.path.join(DATA, "graph.json")
OUT = os.path.join(BUILD, "assets", "semantic.json")

sys.path.insert(0, os.path.join(ROOT, "semantic"))
from tags_io import read_tags  # noqa: E402
import build_summary_figures  # noqa: E402

LANGS = ("de", "fr", "it")
IXTHEO = "ixtheo-k10plus"
COUNTED = ("core", "partial")

def load(name):
    with open(os.path.join(VOCAB, name), encoding="utf-8") as fh:
        return json.load(fh)


def labels_of(entry):
    out = {}
    for code in LANGS:
        val = (entry.get("labels") or {}).get(code)
        if val and val != entry.get("label"):
            out[code] = val
    return out


def aliases_of(entry):
    """The spellings a reader actually types, kept alongside the label.

    The vocabulary files already carry them — 197 for the works alone
    ("contre celse", "gegen kelsos", "traité des principes") — and the build
    used to drop them, so the map answered "Contra Celsum" with 45 records and
    "Contre Celse" with 7. They are served now, matched as whole phrases in the
    controlled-vocabulary channel of the search.
    """
    seen, out = set(), []
    for alias in entry.get("aliases") or []:
        key = " ".join(str(alias).lower().split())
        if key and key not in seen:
            seen.add(key)
            out.append(alias)
    return out


def ppn_to_cluster(corpus_path, wanted):
    """PPN of an IxTheo notice -> identifier of the cluster it was merged into.

    A cluster can carry several IxTheo notices, and several PPNs then answer with
    the same identifier: that is the deduplication doing its work, and both PPNs
    inherit the tag of the cluster they belong to.
    """
    table = {}
    with open(corpus_path, encoding="utf-8") as fh:
        for line in fh:
            record = json.loads(line)
            for entry in record.get("sources") or []:
                if isinstance(entry, dict) and entry.get("source") == IXTHEO:
                    ppn = str(entry.get("source_id"))
                    if ppn in wanted and ppn not in table:
                        table[ppn] = record.get("origenality_id")
    return table


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tags", default=TAGS)
    parser.add_argument("--corpus", default=CORPUS)
    parser.add_argument("--out", default=OUT)
    parser.add_argument("--no-figures", action="store_true",
                        help="write the asset and leave the prose of the pages alone")
    parser.add_argument("--allow-gaps", action="store_true",
                        help="write even though some publication on display carries no tag")
    args = parser.parse_args()

    themes = load("themes.json")
    works = load("works.json")
    approaches = load("approaches.json")
    relevance = load("relevance.json")

    with open(GRAPH, encoding="utf-8") as fh:
        graph = json.load(fh)
    known = {n["ppn"] for n in graph["nodes"] if n.get("k") == "pub" and n.get("ppn")}

    cluster_of = ppn_to_cluster(args.corpus, known)
    records = read_tags(args.tags, keep_unidentified=False)
    by_cluster = {str(rec.get("notice_id")): rec for rec in records}

    by_ppn = {}
    wave = None
    vocabulary_version = None
    needs_review = 0
    repaired = 0
    review_by_class = {}
    unmapped = 0
    untagged = 0
    for ppn in sorted(known):
        cluster = cluster_of.get(ppn)
        if not cluster:
            unmapped += 1
            continue
        rec = by_cluster.get(str(cluster))
        if rec is None:
            untagged += 1
            continue
        wave = wave or rec.get("wave")
        vocabulary_version = vocabulary_version or rec.get("vocabulary_version")
        entry = {"r": rec.get("relevance", "none")}
        # Pourquoi une notice est tenue hors compte : le champ que le prompt v2 a
        # ajouté (homonyme, autre sujet, métadonnées trop minces, texte d'Origène).
        # Le réservoir n'est plus une masse indistincte, et les pages peuvent dire
        # ce qu'il contient sans que personne ait à le compter à la main.
        if entry["r"] == "none" and rec.get("relevance_none_reason"):
            entry["x"] = rec["relevance_none_reason"]
        for key, name in (("t", "themes"), ("w", "works"), ("a", "approaches")):
            values = [v for v in (rec.get(name) or []) if v]
            if values:
                entry[key] = values
        if rec.get("needs_review"):
            entry["n"] = 1
            needs_review += 1
            klass = entry["r"]
            review_by_class[klass] = review_by_class.get(klass, 0) + 1
            # une valeur réparée à la validation : le front le dit avec le reste
            # plutôt que de laisser croire à une simple hésitation de classe
            if rec.get("repairs"):
                repaired += 1
        by_ppn[ppn] = entry

    classes = collections.Counter(entry["r"] for entry in by_ppn.values())
    aside_reasons = collections.Counter(
        entry["x"] for entry in by_ppn.values()
        if entry["r"] == "none" and entry.get("x"))
    built = (sum(classes[k] for k in COUNTED), classes["marginal"],
             len(known) - sum(classes[k] for k in COUNTED) - classes["marginal"])

    payload = {
        "generated": date.today().isoformat(),
        "source": {
            "wave": wave,
            "vocabulary_version": vocabulary_version,
            "notices_tagged": len(by_ppn),
            "notices_in_graph": len(known),
            "needs_review": needs_review,
            "needs_review_by_class": review_by_class,
            "needs_review_repaired": repaired,
            "notices_without_tag": unmapped + untagged,
            "held_aside_reasons": dict(aside_reasons),
            "counts_in_density": [
                key for key, val in relevance["relevance"].items()
                if val.get("counts_in_density")
            ],
        },
        "domains": {
            key: {
                "label": val["label"],
                "labels": labels_of(val),
                "color": val.get("color", "#8A8272"),
            }
            for key, val in themes["domains"].items()
        },
        "themes": {
            key: {
                "domain": val["domain"],
                "label": val["label"],
                "labels": labels_of(val),
                "aliases": aliases_of(val),
            }
            for key, val in themes["themes"].items()
            if val.get("status", "active") == "active"
        },
        "workCategories": {
            key: {"label": val.get("description", key), "color": val.get("color", "#8A8272")}
            for key, val in works["categories"].items()
        },
        "works": {
            key: {
                "label": val["label"],
                "category": val.get("category", "indirect"),
                "labels": labels_of(val),
                "aliases": aliases_of(val),
            }
            for key, val in works["works"].items()
            if val.get("status", "active") == "active"
        },
        "approaches": {
            key: {"label": val["label"], "labels": labels_of(val), "aliases": aliases_of(val)}
            for key, val in approaches["approaches"].items()
            if val.get("status", "active") == "active"
        },
        "relevance": {
            key: {
                "label": val["label"],
                "labels": labels_of(val),
                "density": bool(val.get("counts_in_density")),
            }
            for key, val in relevance["relevance"].items()
        },
        "byPpn": by_ppn,
    }

    # What must not leave the working repo are FIELDS, so the check reads keys,
    # not the blob. A substring test refused the whole build over the alias
    # "justification" of the soteriology theme — a word of theology, not a
    # field of the tagging run.
    forbidden = ("source_model", "run_id", "justification", "abstract", "api_key")

    def keys_of(node):
        if isinstance(node, dict):
            for key, val in node.items():
                yield key
                yield from keys_of(val)
        elif isinstance(node, list):
            for item in node:
                yield from keys_of(item)

    for key in keys_of(payload):
        if key in forbidden:
            sys.exit("refused: the payload carries a %s field" % key)

    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    print("tags read from %s — %d records"
          % (os.path.relpath(args.tags, ROOT), len(records)))
    print("     %d of the %d publications in the graph joined a tagged cluster"
          % (len(by_ppn), len(known)))
    if unmapped or untagged:
        print("     %d without a cluster, %d in a cluster this wave did not tag"
              % (unmapped, untagged))
    print("     counted %d · mentioned only %d · held aside %d"
          % built)

    # Une publication affichée sans tag tombait dans le réservoir « hors compte »
    # sans avoir été jugée : elle y côtoyait les homonymes et les textes
    # d'Origène, et le lecteur ne pouvait pas les distinguer. Vingt-huit
    # publications y sont restées le temps qu'une correction de fusion les
    # renumérote et qu'aucune vague ne les rattrape. Le build refuse maintenant
    # d'écrire tant qu'il en reste une, et dit par où la reprendre.
    if (unmapped or untagged) and not args.allow_gaps:
        sys.exit(
            "refused: %d publication(s) on display carry no tag.\n"
            "  list them and write the tagger's input with:\n"
            "    python3 semantic/retag_gaps.py --tags %s --out <notices.jsonl> --check\n"
            "  or pass --allow-gaps to publish the gap as a gap."
            % (unmapped + untagged, os.path.relpath(args.tags, ROOT)))

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(blob)
    print("wrote %s — %d publications tagged, %d needing review"
          % (os.path.relpath(args.out, ROOT), len(by_ppn), needs_review))
    print("     %d domains, %d themes, %d works, %d approaches"
          % (len(payload["domains"]), len(payload["themes"]),
             len(payload["works"]), len(payload["approaches"])))

    # Les pages disent ces trois nombres en toutes lettres. Elles les tenaient
    # d'une saisie à la main, et ce script refusait alors d'écrire pour ne pas
    # les rendre fausses en silence. Elles les tiennent maintenant d'un bloc
    # balisé : l'asset est écrit, puis la prose est refaite dans la foulée, et
    # les deux sortent de la même passe. Écrire ailleurs que sur l'asset publié
    # ne touche à aucune page.
    if args.no_figures:
        print("     --no-figures : la prose des pages n'a pas été refaite")
        return 0
    if os.path.abspath(args.out) != os.path.abspath(OUT):
        print("     asset écrit hors du site : la prose des pages n'a pas été refaite")
        return 0
    print()
    return build_summary_figures.main([])


if __name__ == "__main__":
    sys.exit(main())
