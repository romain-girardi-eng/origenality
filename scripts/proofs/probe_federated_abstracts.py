#!/usr/bin/env python3
"""Le lien affiché sous un résumé mène-t-il à la notice qui l'a écrit ?

Rejeu du sondage de l'audit 4 (finding A4-3) : le vrai `build_abstracts()` est
exécuté en mémoire sur les publications retenues par le périmètre fédéré, et
chaque lien produit est confronté à la notice DONATRICE du résumé, celle que la
provenance désigne.

    python3 scripts/proofs/probe_federated_abstracts.py [--corpus <corpus.jsonl>]

Trois compteurs, tous attendus à zéro :

  wrong_notice_link   le lien pointe vers une notice qui n'a pas écrit le résumé
  missing_u           aucun lien, alors qu'un gabarit ou une adresse existait
  bad_scheme          le lien n'est pas une adresse http(s)

Sortie 0 si les trois sont nuls, 1 sinon. Les cas restants sont nommés un par
un : un chiffre sans les cas ne vaut rien.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "scripts"))

import build_site_data  # noqa: E402
import check_release  # noqa: E402


def expected_link(record, source, entry):
    """Le lien que la notice donatrice justifie, calculé indépendamment.

    On ne réutilise pas `attribution_link` : un sondage qui appelle la fonction
    qu'il contrôle ne contrôle rien. La provenance du résumé donne la base et
    l'identifiant ; le gabarit de cette base donne l'adresse.
    """
    provenance = record.get("provenance") or {}
    donor = provenance.get("abstract") if isinstance(provenance, dict) else None
    donor_id = None
    if isinstance(donor, dict) and donor.get("source") == source:
        donor_id = donor.get("source_id")
    elif record.get("source") == source:
        donor_id = record.get("source_id")

    explicit = record.get("abstract_url")
    if isinstance(explicit, str) and explicit.strip().startswith("http"):
        return explicit.strip(), donor_id
    template = entry.get("url_template")
    if template and donor_id not in (None, ""):
        return template.replace("{id}", str(donor_id)), donor_id
    return None, donor_id


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=str(ROOT / "data" / "merged" / "corpus.jsonl"))
    parser.add_argument("--tags",
                        default=str(ROOT / "semantic" / "waves" / "wave2_federated" / "tags.jsonl"))
    parser.add_argument("--max-shown", type=int, default=8)
    arguments = parser.parse_args(argv)

    policy = check_release.load_policy(ROOT / "DATA_POLICY.md")
    attribution = policy["attribution"]

    relevance = build_site_data.load_relevance(arguments.tags)
    pubs = []
    with open(arguments.corpus, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            key = build_site_data.record_id(record)
            if build_site_data.is_publication(record, relevance.get(key), True):
                pubs.append(record)

    abstracts = build_site_data.build_abstracts(pubs, None, policy)
    entries = abstracts["byPpn"]
    by_key = {}
    for record in pubs:
        key = record.get("source_id") or build_site_data.record_id(record)
        by_key.setdefault(key, record)

    wrong, missing, bad_scheme, checked = [], [], [], 0
    for key, entry in entries.items():
        record = by_key.get(key)
        if record is None:
            continue
        checked += 1
        source = entry["s"]
        wanted, donor_id = expected_link(record, source, attribution.get(source, {}))
        got = entry.get("u")
        if got is None:
            if wanted is not None:
                missing.append((key, source, wanted))
            continue
        parsed = urlparse(got)
        if parsed.scheme not in ("http", "https") or "." not in (parsed.hostname or ""):
            bad_scheme.append((key, source, got))
        if wanted is not None and got != wanted:
            wrong.append((key, source, got, wanted, donor_id))

    print("corpus                  : %s" % Path(arguments.corpus).name)
    print("pubs                    : %d" % len(pubs))
    print("abstract_entries        : %d" % len(entries))
    print("liens contrôlés         : %d" % checked)
    print("same_expected_link      : %d" % (checked - len(wrong) - len(missing)))
    print("wrong_notice_link       : %d" % len(wrong))
    print("missing_u               : %d" % len(missing))
    print("bad_scheme              : %d" % len(bad_scheme))
    for label, rows in (("wrong_notice_link", wrong),
                        ("missing_u", missing),
                        ("bad_scheme", bad_scheme)):
        for row in rows[:arguments.max_shown]:
            print("   %s  %s" % (label, json.dumps(row, ensure_ascii=False)))
    return 1 if (wrong or missing or bad_scheme) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
