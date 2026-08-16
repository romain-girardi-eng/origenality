#!/usr/bin/env python3
"""Extrait du rapport de fusion les compteurs du lien ISBN.

    python3 scripts/proofs/probe_merge_report.py <merge_report.json>

Sortie 0 si le rapport est cohérent avec lui-même : autant d'identifiants
uniques que de grappes, et des compteurs de refus tous présents.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

KEYS = ("input_records", "merged_clusters", "unique_ids", "fuzzy_links",
        "isbn_links", "isbn_series_ignored", "isbn_blocked_volume_marker",
        "isbn_blocked_year_gap", "distinct_isbn", "clusters_with_conflicts")


def main(argv):
    if len(argv) != 1:
        print("usage: probe_merge_report.py <merge_report.json>", file=sys.stderr)
        return 2
    report = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    missing = [key for key in KEYS if key not in report]
    print(json.dumps({key: report.get(key) for key in KEYS},
                     ensure_ascii=False, indent=1))
    if missing:
        print("compteurs absents du rapport : %s" % missing)
        return 1
    if report["unique_ids"] != report["merged_clusters"]:
        print("les identifiants ne couvrent pas les grappes")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
