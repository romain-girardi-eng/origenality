#!/usr/bin/env python3
"""Ce que l'export des références et l'index de recherche lisent : `data/cite.json`.

L'Explorateur écrit les références d'une vue (BibTeX, RIS, CSL-JSON) avec
`assets/cite.js`. `graph.json` ne garde un contenant que lorsque cinq notices
le partagent, et n'en donne jamais le type (revue ou volume hôte, collection) :
l'export lisait donc `site-merged/corpus.jsonl` entier, environ 4 Mo, au premier
usage. Ce fichier n'en garde que les champs que `cite.js` écrit et que le corpus
porte : contenant (titre et type), éditeur, DOI, ISBN.

Il porte aussi, depuis l'audit du 13 septembre 2026 (S-P1), ce que la recherche
lit de chaque notice et que le graphe tait : `graph.json` ne garde une vedette
que si trois notices la partagent et un contenant que si cinq le partagent, si
bien que `search-core.js` déclarait « absent du corpus » un mot porté par une
vedette (« Antisemitismus », « Homerus », « Geistesgeschichte »). Chaque notice
reçoit donc toutes ses vedettes-matière (`s`) et son contenant tel que la carte
le classe (`in`), lus comme `pipeline/build_site_data.py` les lit
(`record_subjects`, `clean_headings`, `record_container`) et nommés par la forme
de surface que le graphe retient (la plus fréquente, puis la plus longue). La
page et la CLI passent ce fichier au même `buildIndex`.

Clé : l'identifiant Origenality (`origenality_id`), celui que la page donne à
une notice (`ppn` dans l'index de `search-core.js`) et sous lequel `cite.js`
cherche le contenant. Le contenant de l'export est lu comme `cite.js` le lit dans
le corpus (`containersFromCorpus`) : une chaîne est un titre sans type, un objet
garde `host` ou `series` et rien d'autre. `in` n'est écrit que lorsqu'il diffère
de `c`. Une notice sans aucun de ces champs n'y figure pas. Sortie déterministe
(clés triées, JSON compact), pour que `--check` compare octet pour octet.

Garde-fou : chaque vedette et chaque contenant que `graph.json` relie à une
notice doit figurer parmi ceux que ce fichier lui donne, sous le même libellé ;
sinon le script s'arrête, écriture comme `--check`.

    python3 site/build-c/tools/build_cite_data.py          # écrit data/cite.json
    python3 site/build-c/tools/build_cite_data.py --check  # sortie 1 si le fichier n'est plus à jour

Place dans la reconstruction : après `pipeline/build_site_data.py`, qui écrit
le corpus fusionné que ce fichier réduit et le graphe qu'il complète.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tree_paths import data_dir, repository_root  # noqa: E402

ROOT = repository_root(HERE)
DATA = data_dir(ROOT)
CORPUS = os.path.join(DATA, "site-merged", "corpus.jsonl")
GRAPH = os.path.join(DATA, "graph.json")
OUT = os.path.join(DATA, "cite.json")
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from build_site_data import clean_headings, norm_key, record_container, record_subjects  # noqa: E402

SCHEMA = "origenality-cite/2"

# clé courte dans le fichier -> champ du corpus
FIELDS = {"c": "container title", "ct": "container type: host or series",
          "pb": "publisher", "doi": "DOI", "isbn": "ISBN",
          "s": "every subject heading of the record, as the map names it",
          "in": "container title as the map files it, when it differs from c"}
TYPES = ("host", "series")


def present(value) -> bool:
    return isinstance(value, str) and value.strip() != ""


def preferred(labels: Counter) -> str:
    """La forme de surface que `build_graph` retient : la plus fréquente, puis la
    plus longue (elle porte diacritiques et casse), puis l'ordre alphabétique."""
    return sorted(labels.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))[0][0]


def heading_keys(record: dict) -> list[tuple[str, str]]:
    """(clé, forme) de chaque vedette d'une notice, dans l'ordre, sans doublon de clé."""
    out, seen = [], set()
    for heading in clean_headings(record_subjects(record)):
        key = norm_key(heading)
        if key and key not in seen:
            seen.add(key)
            out.append((key, heading))
    return out


def entry(record: dict, subject_label: dict, container_label: dict) -> dict:
    out = {}
    container = record.get("container")
    if present(container):
        out["c"] = container
    elif isinstance(container, dict) and container.get("title") not in (None, ""):
        out["c"] = str(container["title"])
        if container.get("type") in TYPES:
            out["ct"] = container["type"]
    for key, field in (("pb", "publisher"), ("doi", "doi"), ("isbn", "isbn")):
        if present(record.get(field)):
            out[key] = record[field]
    headings = [subject_label[key] for key, _ in heading_keys(record)]
    if headings:
        out["s"] = headings
    filed = record_container(record)
    if filed:
        label = container_label[norm_key(filed[0])]
        if label != out.get("c"):
            out["in"] = label
    return out


def value() -> dict:
    rows = []
    with open(CORPUS, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    subject_forms: dict[str, Counter] = defaultdict(Counter)
    container_forms: dict[str, Counter] = defaultdict(Counter)
    for record in rows:
        for key, heading in heading_keys(record):
            subject_forms[key][heading] += 1
        filed = record_container(record)
        if filed:
            container_forms[norm_key(filed[0])][filed[0]] += 1
    subject_label = {key: preferred(forms) for key, forms in subject_forms.items()}
    container_label = {key: preferred(forms) for key, forms in container_forms.items()}
    by_id, records = {}, 0
    for record in rows:
        identifier = record.get("origenality_id")
        if not identifier:
            continue
        records += 1
        fields = entry(record, subject_label, container_label)
        if fields:
            by_id[identifier] = fields
    verify_against_graph(by_id)
    return {"schema": SCHEMA, "source": "data/site-merged/corpus.jsonl",
            "records": records, "fields": FIELDS, "byPpn": by_id}


def verify_against_graph(by_id: dict) -> None:
    """Chaque vedette et chaque contenant du graphe est parmi ceux du fichier."""
    with open(GRAPH, encoding="utf-8") as handle:
        graph = json.load(handle)
    nodes = graph.get("nodes") or []
    missing = []
    for edge in graph.get("edges") or []:
        if edge.get("r") not in ("sub", "in"):
            continue
        pub, target = nodes[edge["s"]], nodes[edge["t"]]
        row = by_id.get(pub.get("ppn"), {})
        if edge["r"] == "sub":
            ok = target.get("label") in (row.get("s") or [])
        else:
            ok = target.get("label") == row.get("in", row.get("c"))
        if not ok:
            missing.append((pub.get("ppn"), edge["r"], target.get("label")))
    if missing:
        sys.exit("graph.json relie %d vedettes ou contenants que cite.json ne donne pas, "
                 "dont %r : la lecture des vedettes a divergé de build_site_data.py"
                 % (len(missing), missing[:3]))


def render(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def headed(data: dict) -> int:
    return sum(1 for row in data["byPpn"].values() if row.get("s"))


def shown(path: str) -> str:
    return os.path.relpath(path, ROOT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write or verify data/cite.json.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    data = value()
    text = render(data)
    size = len(text.encode("utf-8"))
    if args.check:
        if not os.path.exists(OUT):
            print("%s is missing" % shown(OUT))
            return 1
        with open(OUT, encoding="utf-8") as handle:
            if handle.read() != text:
                print("%s is stale: run build_cite_data.py" % shown(OUT))
                return 1
        print("%s is current: %d records, %d with a field, %d with subject headings, %d bytes"
              % (shown(OUT), data["records"], len(data["byPpn"]), headed(data), size))
        return 0
    with open(OUT, "w", encoding="utf-8") as handle:
        handle.write(text)
    print("wrote %s: %d records, %d with a field, %d with subject headings, %d bytes"
          % (shown(OUT), data["records"], len(data["byPpn"]), headed(data), size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
