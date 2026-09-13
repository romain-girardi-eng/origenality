#!/usr/bin/env python3
"""Put the language codes of the primary layer on the map's scheme.

`data/primary-layer.jsonl` holds the editions, translations and manuscript
witnesses of Origen's own works, with the `language` each catalogue wrote.  The
map moved to ISO 639-1 (`pipeline/fields.norm_lang`); this layer kept the raw
MARC codes, so Latin was counted twice, as `lat` and as `la` (audit of 13
September, OR-48).  This tool normalises every `language` with the same function
and recounts `by_language` in the summary, keeping its convention: the ten most
frequent values, `null` for a record that carries no code.  Nothing else in
either file is touched.

    python3 site/build-c/tools/build_primary_layer.py
    python3 site/build-c/tools/build_primary_layer.py --check
"""
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
sys.path.insert(0, str(ROOT / "pipeline"))
from fields import norm_lang  # noqa: E402

LAYER = DATA / "primary-layer.jsonl"
SUMMARY = DATA / "primary-layer-summary.json"
TOP = 10


def normalised(value):
    if value is None:
        return None
    code = norm_lang(value)
    return None if code == "?" else code


def rebuild(layer_text: str, summary: dict) -> tuple[str, dict]:
    rows = [json.loads(line) for line in layer_text.splitlines() if line.strip()]
    lines = []
    for row in rows:
        row["language"] = normalised(row.get("language"))
        lines.append(json.dumps(row, ensure_ascii=False))
    counts = Counter("null" if row["language"] is None else row["language"] for row in rows)
    updated = dict(summary)
    updated["by_language"] = dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP])
    if updated.get("records") != len(rows):
        raise SystemExit("primary-layer-summary.json counts %s records, the layer holds %d"
                         % (updated.get("records"), len(rows)))
    return "\n".join(lines) + "\n", updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    layer_text = LAYER.read_text(encoding="utf-8")
    summary_text = SUMMARY.read_text(encoding="utf-8")
    wanted_layer, summary = rebuild(layer_text, json.loads(summary_text))
    wanted_summary = json.dumps(summary, ensure_ascii=False, indent=1) + "\n"
    if args.check:
        stale = [path.name for path, current, wanted in
                 ((LAYER, layer_text, wanted_layer), (SUMMARY, summary_text, wanted_summary))
                 if current != wanted]
        if stale:
            print("stale: " + ", ".join(stale))
            return 1
        print("primary layer languages are normalised")
        return 0
    LAYER.write_text(wanted_layer, encoding="utf-8")
    SUMMARY.write_text(wanted_summary, encoding="utf-8")
    print(json.dumps(summary["by_language"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
