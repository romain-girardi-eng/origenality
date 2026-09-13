#!/usr/bin/env python3
"""Write or verify the content-addressed manifest of the public build."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from tree_paths import data_dir, repository_root  # noqa: E402
import build_public_snapshot as snapshot  # noqa: E402

BUILD = HERE.parent
ROOT = Path(repository_root(str(HERE)))
DATA = Path(data_dir(str(ROOT)))
OUT = DATA / "BUILD.json"
FILES = {
    "data/site-records.jsonl": DATA / "site-records.jsonl",
    "data/site-tags.jsonl": DATA / "site-tags.jsonl",
    "data/site-merged/corpus.jsonl": DATA / "site-merged/corpus.jsonl",
    "data/site-merged/tags.jsonl": DATA / "site-merged/tags.jsonl",
    "data/site-merged/merge_report.json": DATA / "site-merged/merge_report.json",
    "data/site-merged/tag_merge_report.json": DATA / "site-merged/tag_merge_report.json",
    "data/corrections.json": DATA / "corrections.json",
    "data/abstract-anomalies.json": DATA / "abstract-anomalies.json",
    "data/citation-counts.json": DATA / "citation-counts.json",
    "data/graph.json": DATA / "graph.json",
    "data/abstracts.json": DATA / "abstracts.json",
    "data/stats.json": DATA / "stats.json",
    "data/evidence.json": DATA / "evidence.json",
    "data/cite.json": DATA / "cite.json",
    "site/assets/semantic.json": BUILD / "assets" / "semantic.json",
    "site/assets/weights.json": BUILD / "assets" / "weights.json",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> int:
    return sum(1 for line in path.open(encoding="utf-8") if line.strip())


def value(generated: str | None = None) -> dict:
    missing = [name for name, path in FILES.items() if not path.is_file()]
    if missing:
        raise SystemExit("missing build input(s): " + ", ".join(missing))
    merge = json.loads((DATA / "site-merged/merge_report.json").read_text())
    tag_report = json.loads((DATA / "site-merged/tag_merge_report.json").read_text())
    anomalies = json.loads((DATA / "abstract-anomalies.json").read_text())
    records = [json.loads(line) for line in
               (DATA / "site-records.jsonl").read_text(encoding="utf-8").splitlines()
               if line.strip()]
    field_coverage = snapshot.coverage(records)
    thresholds = json.loads((DATA / "graph.json").read_text(encoding="utf-8")).get("thresholds") or {}
    partial = field_coverage["records"] - field_coverage["basis_catalogue_record"]
    limitation = None
    if partial:
        # La limite se dit avec ses chiffres, lus dans le snapshot : 478 sujets et
        # 61 contenants avaient été publiés comme s'ils étaient le périmètre (OR-01).
        rest = ("The other record keeps" if partial == 1 else "The other %d keep" % partial)
        limitation = ("%d of %d source records carry their subject headings and container "
                      "from their catalogue record. %s what the graph "
                      "published on 22 August 2026 held: headings used by at least %s records "
                      "and containers used by at least %s. Distinct subject and container "
                      "totals undercount %s."
                      % (field_coverage["basis_catalogue_record"], field_coverage["records"],
                         rest, thresholds.get("subject_min_publications"),
                         thresholds.get("container_min_publications"),
                         "that record" if partial == 1 else "those records"))
    return {
        "field_coverage": field_coverage,
        "limitation": limitation,
        "generated": generated or date.today().isoformat(),
        "status": "replayable-public-build",
        "population_unit": "deduplicated-work-cluster",
        "source_records": rows(DATA / "site-records.jsonl"),
        "work_clusters": merge["merged_clusters"],
        "duplicates_collapsed": merge["dedup_removed"],
        "tagged_clusters": tag_report["tagged_clusters"],
        "tag_disagreements_flagged": tag_report["clusters_with_tag_disagreement"],
        "abstract_anomalies_quarantined": len(anomalies.get("records") or []),
        "files": {
            name: {"sha256": sha(path), "bytes": path.stat().st_size}
            for name, path in FILES.items()
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        if not OUT.exists():
            print("BUILD.json is missing")
            return 1
        current = json.loads(OUT.read_text(encoding="utf-8"))
        expected = value(current.get("generated"))
        if current != expected:
            print("BUILD.json is stale")
            return 1
        print(f"BUILD.json verifies {len(FILES)} files and {expected['work_clusters']} clusters")
        return 0
    expected = value()
    OUT.write_text(json.dumps(expected, ensure_ascii=False, indent=2,
                              sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(FILES)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
