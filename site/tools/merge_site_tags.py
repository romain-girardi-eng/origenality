#!/usr/bin/env python3
"""Project record-level tags onto the work clusters produced by merge_dedup."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from tree_paths import data_dir, repository_root  # noqa: E402

ROOT = Path(repository_root(str(HERE)))
DATA = Path(data_dir(str(ROOT)))
DEFAULT_CORPUS = DATA / "site-merged" / "corpus.jsonl"
DEFAULT_SOURCE_TAGS = DATA / "site-tags.jsonl"
DEFAULT_OUT = DATA / "site-merged" / "tags.jsonl"
DEFAULT_REPORT = DATA / "site-merged" / "tag_merge_report.json"
RELEVANCE = {"none": 0, "marginal": 1, "partial": 2, "core": 3}


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def source_keys(cluster: dict) -> list[str]:
    keys = []
    for entry in cluster.get("sources") or []:
        if not isinstance(entry, dict) or not entry.get("source") or entry.get("source_id") is None:
            continue
        keys.append(f"{entry['source']}:{entry['source_id']}")
    return sorted(set(keys))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--source-tags", type=Path, default=DEFAULT_SOURCE_TAGS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)

    source_rows = read_rows(args.source_tags)
    source_tags = {row["notice_id"]: row for row in source_rows}
    if len(source_tags) != len(source_rows):
        raise SystemExit("duplicate notice_id in source tag snapshot")

    output = []
    missing = []
    disagreements = []
    distribution = Counter()
    clusters = read_rows(args.corpus)
    for cluster in clusters:
        keys = source_keys(cluster)
        rows = [source_tags[key] for key in keys if key in source_tags]
        absent = [key for key in keys if key not in source_tags]
        if absent or not rows:
            missing.append({"cluster": cluster.get("origenality_id"), "missing": absent or keys})
            continue
        rows.sort(key=lambda row: (-RELEVANCE.get(row.get("relevance"), -1),
                                   bool(row.get("needs_review")), row["notice_id"]))
        chosen = rows[0]
        signatures = {(row.get("relevance"), tuple(row.get("themes") or []),
                       tuple(row.get("works") or []), tuple(row.get("approaches") or []))
                      for row in rows}
        conflict = len(signatures) > 1
        if conflict:
            disagreements.append({
                "cluster": cluster["origenality_id"],
                "source_tags": [row["notice_id"] for row in rows],
                "relevance": {row["notice_id"]: row.get("relevance") for row in rows},
            })
        result = {
            "notice_id": cluster["origenality_id"],
            "relevance": chosen["relevance"],
            "relevance_none_reason": chosen.get("relevance_none_reason", "not-applicable"),
            "themes": chosen.get("themes") or [],
            "works": chosen.get("works") or ["unspecified"],
            "approaches": chosen.get("approaches") or [],
            "needs_review": bool(chosen.get("needs_review") or conflict),
            "source_tag_ids": [row["notice_id"] for row in rows],
            "source_tag_disagreement": conflict,
            "wave": "public_work_clusters_2026_08_24",
            "vocabulary_version": chosen.get("vocabulary_version"),
        }
        distribution[result["relevance"]] += 1
        output.append(result)

    if missing:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({"missing": missing}, indent=2) + "\n",
                               encoding="utf-8")
        raise SystemExit(f"{len(missing)} work cluster(s) lack a source tag")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                for row in output), encoding="utf-8")
    report = {
        "source_records": len(source_rows),
        "work_clusters": len(clusters),
        "tagged_clusters": len(output),
        "clusters_with_tag_disagreement": len(disagreements),
        "distribution": dict(distribution),
        "disagreements": disagreements,
        "selection_rule": ("highest relevance class; ties are deterministic. Any disagreement "
                           "sets needs_review and remains listed in this report."),
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                     sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "disagreements"},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
