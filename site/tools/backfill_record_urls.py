#!/usr/bin/env python3
"""Give every catalogue record a resolvable source URL, on its own database.

The graph keeps a source label and that source's record identifier.  A missing
URL is therefore a build defect, not missing information, and so is a URL on
another database than the record's own: the 130 B3Kat records linked to the
Gnomon database, under an address that did not open them (audit of 13
September).  This post-build gate reads the record templates from the
attribution table of DATA_POLICY.md, the only copy, with the one identifier
shape handled explicitly: BnF already supplies an ARK, while the other
catalogues supply the local identifier only.  A DOI link is accepted as the
record's link.

    python3 site/build-c/tools/backfill_record_urls.py            # repair
    python3 site/build-c/tools/backfill_record_urls.py --check    # exit 1 on a gap
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from tree_paths import data_dir, repository_root  # noqa: E402

ROOT = Path(repository_root(str(HERE)))
DATA = Path(data_dir(str(ROOT)))
GRAPH = DATA / "graph.json"

import build_public_snapshot as snapshot  # noqa: E402  (templates and host rule, shared)


def record_url(source: str, identifier: str, attribution: dict | None = None) -> str | None:
    return snapshot.own_record_url(source, identifier,
                                   attribution if attribution is not None
                                   else snapshot.load_attribution())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--graph", type=Path, default=GRAPH)
    parser.add_argument("--policy", type=Path, default=snapshot.POLICY)
    args = parser.parse_args(argv)
    attribution = snapshot.load_attribution(args.policy)
    data = json.loads(args.graph.read_text(encoding="utf-8"))
    repaired = 0
    misplaced = []
    unresolved = []
    for node in data.get("nodes") or []:
        if node.get("k") != "pub":
            continue
        for entry in node.get("source_ids") or []:
            expected = record_url(entry.get("source"), entry.get("id"), attribution)
            url = entry.get("url")
            if url and not snapshot.misdirected(url, expected):
                continue
            if url and expected:
                misplaced.append((entry.get("source"), entry.get("id"), url))
            if expected:
                entry["url"] = expected
                repaired += 1
            elif not url:
                unresolved.append((entry.get("source"), entry.get("id")))
        sources = node.get("src") or []
        source = sources[0] if len(sources) == 1 else None
        identifier = node.get("ppn")
        expected = record_url(source, identifier, attribution) if source and identifier else None
        if node.get("url") and not snapshot.misdirected(node["url"], expected):
            continue
        if node.get("url") and expected:
            misplaced.append((source, identifier, node["url"]))
        if expected:
            node["url"] = expected
            repaired += 1
        elif not node.get("url"):
            unresolved.append((source, identifier))
    if unresolved:
        for source, identifier in unresolved[:20]:
            print(f"UNRESOLVED {source}:{identifier}", file=sys.stderr)
        print(f"{len(unresolved)} publication URL(s) remain unresolved", file=sys.stderr)
        return 1
    if args.check:
        for source, identifier, url in misplaced[:20]:
            print(f"ON ANOTHER DATABASE {source}:{identifier} -> {url}", file=sys.stderr)
        print(f"all publication nodes carry a source URL on their own database "
              f"({repaired} would be repaired, {len(misplaced)} of them on another database)")
        return 1 if repaired else 0
    args.graph.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n",
                          encoding="utf-8")
    print(f"repaired {repaired} source URL(s) in {args.graph.name}, "
          f"{len(misplaced)} of them on another database")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
