"""Build the traversable topic index from the tag records.

Output: one JSON document holding two trees over the same notices —

  themes  root -> 16 domains -> 60 leaves -> notice identifiers
  works   root -> work categories -> works of Origen -> notice identifiers

Node shape follows the TreeNode used for hierarchical navigation: node_id,
title, path, summary, concept_tags, entity_tags, nodes[]. Two fields are added
because the objects indexed here are notices rather than passages: notice_ids
(the notices attached to this node itself) and stats (aggregated over the
subtree).

Summaries are computed, not generated: counts, year range, language mix,
dominant approaches. Nothing in this file calls a model, so the index is a
deterministic function of the tag records and the vocabulary.

    python3 build_topic_tree.py --tags ../pilot/tags_ixtheo.jsonl \\
        --notices ../../data/raw/ixtheo/records.jsonl --output topic_tree.json
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tags_io import read_tags  # noqa: E402
from vocabulary_io import load_vocabulary  # noqa: E402

RELEVANCE_ORDER = ["none", "marginal", "partial", "core"]

LANGUAGE_LABELS = {
    "ger": "German", "eng": "English", "fre": "French", "ita": "Italian",
    "spa": "Spanish", "lat": "Latin", "dut": "Dutch", "por": "Portuguese",
    "pol": "Polish", "rus": "Russian", "gre": "Greek", "grc": "Ancient Greek",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def notice_index(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path or not path.exists():
        return {}
    index: dict[str, dict[str, Any]] = {}
    for record in read_jsonl(path):
        # A merged cluster is addressed by its stable identifier, a raw harvest
        # record by source:source_id. Both are indexed so one tree builder
        # serves both kinds of input.
        stable = str(record.get("origenality_id") or "").strip()
        if stable:
            index[stable] = record
        source = str(record.get("source") or "unknown")
        source_id = str(record.get("source_id") or record.get("id") or "").strip()
        if source_id:
            index[f"{source}:{source_id}"] = record
    return index


def surname(author: Any) -> str:
    name = author.get("name") if isinstance(author, dict) else str(author or "")
    name = str(name or "").strip()
    if "," in name:
        return name.split(",", 1)[0].strip()
    return name.split(" ")[-1].strip() if name else ""


def describe(entries: list[dict[str, Any]], label: str) -> str:
    """Deterministic one-line summary of a set of tagged notices."""
    if not entries:
        return f"{label}: no notice at this level."
    years = sorted(y for y in (entry.get("year") for entry in entries) if isinstance(y, int))
    languages = collections.Counter(
        LANGUAGE_LABELS.get(str(entry.get("language") or ""), str(entry.get("language") or "unknown"))
        for entry in entries
    )
    approaches = collections.Counter(a for entry in entries for a in entry.get("approaches", []))
    works = collections.Counter(
        w for entry in entries for w in entry.get("works", []) if w != "unspecified"
    )
    parts = [f"{len(entries)} notices"]
    if years:
        parts.append(f"{years[0]}-{years[-1]}")
    if languages:
        parts.append(
            "languages: " + ", ".join(f"{name} {count}" for name, count in languages.most_common(3))
        )
    if approaches:
        parts.append("approaches: " + ", ".join(name for name, _ in approaches.most_common(2)))
    if works:
        parts.append("works: " + ", ".join(name for name, _ in works.most_common(3)))
    return f"{label} — " + "; ".join(parts) + "."


def stats_of(entries: list[dict[str, Any]]) -> dict[str, Any]:
    years = sorted(y for y in (entry.get("year") for entry in entries) if isinstance(y, int))
    return {
        "n_notices": len(entries),
        "year_min": years[0] if years else None,
        "year_max": years[-1] if years else None,
        "languages": dict(
            collections.Counter(str(entry.get("language") or "unknown") for entry in entries).most_common()
        ),
        "relevance": dict(
            collections.Counter(str(entry.get("relevance") or "") for entry in entries).most_common()
        ),
        "needs_review": sum(1 for entry in entries if entry.get("needs_review")),
        "mean_confidence": (
            round(sum(float(entry.get("confidence") or 0) for entry in entries) / len(entries), 3)
            if entries
            else None
        ),
    }


def entity_tags(entries: list[dict[str, Any]], limit: int = 8) -> list[str]:
    authors = collections.Counter(
        name for entry in entries for name in entry.get("author_surnames", []) if name
    )
    works = collections.Counter(
        w for entry in entries for w in entry.get("works", []) if w != "unspecified"
    )
    tags = [name for name, _ in works.most_common(4)]
    tags += [name for name, _ in authors.most_common(limit - len(tags))]
    return tags


def build_tree(
    entries: list[dict[str, Any]],
    axis: str,
    groups: list[tuple[str, str, str, list[tuple[str, str, list[str]]], list[str]]],
) -> dict[str, Any]:
    """groups: [(group_id, group_title, group_summary_label, leaves, group_tags)]

    where leaves is [(leaf_id, leaf_title, leaf_concept_tags)] and group_tags
    holds the domain's own labels in the languages of the vocabulary. Those
    labels used to be dropped: a domain node carried only the English titles of
    its leaves, so a query written in French found the leaves that happen to
    carry a French alias and never the domain itself.
    """
    by_leaf: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for entry in entries:
        for value in entry.get(f"_{axis}", []):
            by_leaf[value].append(entry)

    group_nodes: list[dict[str, Any]] = []
    for group_id, group_title, group_label, leaves, group_tags in groups:
        leaf_nodes: list[dict[str, Any]] = []
        group_entries: dict[str, dict[str, Any]] = {}
        for leaf_id, leaf_title, concept_tags in leaves:
            leaf_entries = by_leaf.get(leaf_id, [])
            for entry in leaf_entries:
                group_entries[entry["notice_id"]] = entry
            leaf_nodes.append(
                {
                    "node_id": f"{axis}:{leaf_id}",
                    "title": leaf_title,
                    "path": f"{group_title} > {leaf_title}",
                    "summary": describe(leaf_entries, leaf_title),
                    "concept_tags": concept_tags,
                    "entity_tags": entity_tags(leaf_entries),
                    "notice_ids": sorted(entry["notice_id"] for entry in leaf_entries),
                    "stats": stats_of(leaf_entries),
                    "nodes": [],
                }
            )
        collected = list(group_entries.values())
        group_nodes.append(
            {
                "node_id": f"{axis}:{group_id}",
                "title": group_title,
                "path": group_title,
                "summary": describe(collected, group_label),
                "concept_tags": list(group_tags) + [leaf[1] for leaf in leaves],
                "entity_tags": entity_tags(collected),
                "notice_ids": sorted(group_entries),
                "stats": stats_of(collected),
                "nodes": sorted(leaf_nodes, key=lambda node: -node["stats"]["n_notices"]),
            }
        )
    return {
        "axis": axis,
        "root": {
            "node_id": f"{axis}:root",
            "title": "Themes" if axis == "themes" else "Works of Origen",
            "path": "",
            "summary": describe(entries, "All notices"),
            "concept_tags": [],
            "entity_tags": [],
            "notice_ids": sorted(entry["notice_id"] for entry in entries),
            "stats": stats_of(entries),
            "nodes": sorted(group_nodes, key=lambda node: -node["stats"]["n_notices"]),
        },
    }


def main(argv: list[str]) -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tags", type=Path, required=True)
    parser.add_argument("--notices", type=Path, help="original notices, for year, language and authors")
    parser.add_argument("--output", type=Path, default=here / "topic_tree.json")
    parser.add_argument("--vocabulary", type=Path, default=here.parent / "vocabulary")
    parser.add_argument(
        "--min-relevance",
        default="partial",
        choices=RELEVANCE_ORDER,
        help="notices below this relevance are excluded from the index (default: partial)",
    )
    parser.add_argument("--wave", default=None, help="keep only this wave")
    arguments = parser.parse_args(argv)

    vocab = load_vocabulary(arguments.vocabulary)
    notices = notice_index(arguments.notices)
    threshold = RELEVANCE_ORDER.index(arguments.min_relevance)

    entries: list[dict[str, Any]] = []
    excluded = collections.Counter()
    # Une notice, un tag : le DERNIER écrit. Le tagueur écrit en ajout, donc un
    # retag se pose en fin de fichier ; garder la première ligne publiait
    # l'ancien thème pour toujours (audit 4, finding A4-4).
    for tag in read_tags(arguments.tags, keep_unidentified=False):
        if arguments.wave and tag.get("wave") != arguments.wave:
            continue
        notice_id = str(tag.get("notice_id") or "")
        if not notice_id:
            continue
        relevance = str(tag.get("relevance") or "none")
        if relevance not in RELEVANCE_ORDER or RELEVANCE_ORDER.index(relevance) < threshold:
            excluded[relevance] += 1
            continue
        record = notices.get(notice_id, {})
        entries.append(
            {
                "notice_id": notice_id,
                "relevance": relevance,
                "works": list(tag.get("works") or []),
                "_themes": list(tag.get("themes") or []),
                "_works": list(tag.get("works") or []),
                "approaches": list(tag.get("approaches") or []),
                "confidence": tag.get("confidence"),
                "needs_review": bool(tag.get("needs_review")),
                "title": record.get("title"),
                "year": record.get("year"),
                "language": record.get("language"),
                "author_surnames": [s for s in (surname(a) for a in (record.get("authors") or [])) if s][:3],
            }
        )

    theme_groups = []
    grouped = vocab.themes_by_domain()
    for domain_id, domain in vocab.domains.items():
        leaves = []
        for leaf_id in grouped.get(domain_id, []):
            entry = vocab.themes[leaf_id]
            concept_tags = [entry["label"]] + list(entry.get("aliases") or [])[:8]
            concept_tags += [str(v) for v in (entry.get("labels") or {}).values()]
            leaves.append((leaf_id, entry["label"], concept_tags))
        domain_tags = [domain["label"]] + [
            str(v) for v in (domain.get("labels") or {}).values()]
        theme_groups.append((domain_id, domain["label"], domain["label"], leaves,
                             domain_tags))

    work_groups = []
    for category_id, category in vocab.work_categories.items():
        leaves = []
        for work_id in vocab.work_ids:
            entry = vocab.works[work_id]
            if entry.get("category") != category_id:
                continue
            concept_tags = [entry["label"]] + list(entry.get("aliases") or [])[:8]
            leaves.append((work_id, entry["label"], concept_tags))
        if leaves:
            category_tags = [category["description"]] + [
                str(v) for v in (category.get("labels") or {}).values()]
            work_groups.append((category_id, category["description"],
                                category["description"], leaves, category_tags))

    document = {
        "index_id": "origenality-topic-tree",
        "version": "1.0.0",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "vocabulary_version": vocab.version_string,
        "source_tags": str(arguments.tags),
        "min_relevance": arguments.min_relevance,
        "counts": {
            "notices_indexed": len(entries),
            "excluded_by_relevance": dict(excluded),
            "needs_review": sum(1 for entry in entries if entry["needs_review"]),
        },
        "axes": [
            build_tree(entries, "themes", theme_groups),
            build_tree(entries, "works", work_groups),
        ],
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(document, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"notices indexed: {len(entries)} | excluded: {dict(excluded)}")
    print(f"tree written: {arguments.output}")
    for axis in document["axes"]:
        top = sorted(axis["root"]["nodes"], key=lambda node: -node["stats"]["n_notices"])[:5]
        print(f"  {axis['axis']}: " + ", ".join(f"{n['title']} ({n['stats']['n_notices']})" for n in top))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
