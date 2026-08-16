#!/usr/bin/env python3
"""Rassemble, pour le périmètre du site, le meilleur résumé disponible.

IxTheo ne porte un résumé que sur 8 % de ses notices : le catalogue décrit, il
ne résume pas. Les mêmes publications sont pourtant souvent résumées ailleurs —
OpenAlex, Crossref, Semantic Scholar, la BIBP, le repertorio Adamantius. La
fusion `data/merged/corpus.jsonl` a déjà rapproché ces notices ; ce script en
tire les résumés et les rapporte au PPN qui identifie la publication côté site.

Trois jointures, de la plus sûre à la plus lâche, appliquées dans cet ordre et
jamais l'une par-dessus l'autre :

1. **PPN** — la grappe fusionnée contient la notice IxTheo. C'est la jointure
   du pipeline, faite en amont sur DOI, titre et auteur.
2. **DOI** — même identifiant d'objet numérique, normalisé par `norm_doi`.
3. **Titre + année** — titre normalisé identique et années à un an près. Un
   titre de moins de 25 caractères ne joint pas : « Origen » ou « Introduction »
   rapprocheraient n'importe quoi. Un titre normalisé qui désigne plusieurs
   publications distinctes est écarté plutôt qu'arbitré.

Chaque résumé retenu garde la base qui l'a écrit et un lien vers la notice
d'origine : c'est le régime d'attribution de `DATA_POLICY.md`, dont la table
des bases est lue ici même — aucune deuxième copie de ces libellés.

Sortie : `data/derived/abstracts_enrichment.jsonl`, une ligne par PPN.

    python3 site/build-c/tools/enrich_abstracts.py
    python3 site/build-c/tools/enrich_abstracts.py --report
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tree_paths import repository_root  # noqa: E402

ROOT = repository_root(HERE)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from merge_dedup import norm_doi, norm_title  # noqa: E402
from fields import norm_year  # noqa: E402
import check_release  # noqa: E402

IXTHEO = os.path.join(ROOT, "data", "raw", "ixtheo", "records.jsonl")
CORPUS = os.path.join(ROOT, "data", "merged", "corpus.jsonl")
RAW_DIR = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "derived", "abstracts_enrichment.jsonl")
POLICY = os.path.join(ROOT, "DATA_POLICY.md")

TITLE_JOIN_MIN = 25
YEAR_TOLERANCE = 1


def read_jsonl(path):
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def source_urls():
    """(base, identifiant) → URL de notice, telle que la moisson l'a reçue.

    Les gabarits d'URL de `DATA_POLICY.md` ne couvrent pas toutes les bases :
    la BIBP numérote ses notices autrement que ses enregistrements, ISIDORE
    renvoie au dépôt d'origine plutôt qu'à lui-même. Là où l'URL a été
    moissonnée, elle vaut mieux qu'un gabarit.
    """
    urls = {}
    for name in sorted(os.listdir(RAW_DIR)):
        path = os.path.join(RAW_DIR, name, "records.jsonl")
        if not os.path.isfile(path):
            continue
        for record in read_jsonl(path):
            key = (record.get("source"), record.get("source_id"))
            if not key[0] or not key[1]:
                continue
            url = record.get("url") or record.get("ixtheo_url")
            if isinstance(url, str) and url.startswith("http"):
                urls.setdefault(key, url)
    return urls


def notice_url(source, source_id, harvested, attribution):
    if not source_id:
        return None
    direct = harvested.get((source, source_id))
    if direct:
        return direct
    template = (attribution.get(source) or {}).get("url_template")
    if not template:
        return None
    return template.replace("{id}", str(source_id))


def abstract_of(cluster, harvested, attribution):
    """Résumé d'une grappe fusionnée, avec sa base et le lien vers sa notice."""
    text = cluster.get("abstract")
    if not isinstance(text, str) or not text.strip():
        return None
    source = check_release.abstract_source(cluster)
    if not source or source not in attribution:
        return None
    provenance = (cluster.get("provenance") or {}).get("abstract") or {}
    source_id = provenance.get("source_id")
    if not source_id:
        for entry in cluster.get("sources") or []:
            if isinstance(entry, dict) and entry.get("source") == source:
                source_id = entry.get("source_id")
                break
    return {
        "text": " ".join(text.split()),
        "source": source,
        "source_label": attribution[source]["label"],
        "url": notice_url(source, source_id, harvested, attribution),
        "rights": cluster.get("abstract_rights"),
    }


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--ixtheo", default=IXTHEO)
    parser.add_argument("--corpus", default=CORPUS)
    parser.add_argument("--out", default=OUT)
    args = parser.parse_args()

    policy = check_release.load_policy(Path(POLICY))
    attribution = policy["attribution"]
    harvested = source_urls()

    # ---- côté site : les notices IxTheo, celles qui portent déjà un résumé
    notices = []
    own = 0
    for record in read_jsonl(args.ixtheo):
        ppn = record.get("source_id")
        if not ppn:
            continue
        has_own = isinstance(record.get("abstract"), str) and record["abstract"].strip()
        own += bool(has_own)
        notices.append({
            "ppn": ppn,
            "doi": norm_doi(record.get("doi")),
            "title": norm_title(record.get("title") or ""),
            "year": norm_year(record),
            "has_own": bool(has_own),
        })

    by_ppn = {n["ppn"]: n for n in notices}
    wanted_doi = collections.defaultdict(list)
    wanted_title = collections.defaultdict(list)
    for notice in notices:
        if notice["has_own"]:
            continue
        if notice["doi"]:
            wanted_doi[notice["doi"]].append(notice["ppn"])
        if len(notice["title"]) >= TITLE_JOIN_MIN:
            wanted_title[notice["title"]].append(notice["ppn"])

    # ---- côté corpus fédéré : une passe, trois index
    found = {}                                   # ppn → résumé retenu
    method = {}                                  # ppn → jointure appliquée
    by_doi = {}
    by_title = collections.defaultdict(list)

    for cluster in read_jsonl(args.corpus):
        payload = abstract_of(cluster, harvested, attribution)
        if not payload:
            continue

        ppns = [
            entry.get("source_id")
            for entry in cluster.get("sources") or []
            if isinstance(entry, dict) and entry.get("source") == "ixtheo-k10plus"
        ]
        for ppn in ppns:
            if ppn in by_ppn and not by_ppn[ppn]["has_own"] and ppn not in found:
                found[ppn] = payload
                method[ppn] = "ppn"

        doi = norm_doi(cluster.get("doi"))
        if doi and doi in wanted_doi:
            by_doi.setdefault(doi, payload)

        title = norm_title(cluster.get("title") or "")
        if len(title) >= TITLE_JOIN_MIN and title in wanted_title:
            by_title[title].append((norm_year(cluster), payload))

    for doi, ppns in wanted_doi.items():
        payload = by_doi.get(doi)
        if not payload:
            continue
        for ppn in ppns:
            if ppn not in found:
                found[ppn] = payload
                method[ppn] = "doi"

    ambiguous = 0
    for title, ppns in wanted_title.items():
        candidates = by_title.get(title)
        if not candidates:
            continue
        if len(ppns) > 1:
            ambiguous += 1
            continue
        ppn = ppns[0]
        if ppn in found:
            continue
        year = by_ppn[ppn]["year"]
        for candidate_year, payload in candidates:
            close = (
                year is None
                or candidate_year is None
                or abs(candidate_year - year) <= YEAR_TOLERANCE
            )
            if close:
                found[ppn] = payload
                method[ppn] = "title-year"
                break

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        for ppn, payload in sorted(found.items()):
            row = dict(payload)
            row["ppn"] = ppn
            row["join"] = method[ppn]
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    total = len(notices)
    covered = own + len(found)
    by_method = collections.Counter(method.values())
    by_source = collections.Counter(p["source"] for p in found.values())
    print(f"→ {os.path.relpath(args.out, ROOT)}")
    print(f"   {total} notices IxTheo ; {own} résumés propres ({100*own/total:.1f} %)")
    print(f"   {len(found)} résumés joints depuis le corpus fédéré "
          f"({dict(by_method)}, {ambiguous} titres écartés pour homonymie)")
    print(f"   couverture : {covered}/{total} = {100*covered/total:.1f} %")
    for source, count in by_source.most_common():
        print(f"      {source:<20} {count:>5}")


if __name__ == "__main__":
    main()
