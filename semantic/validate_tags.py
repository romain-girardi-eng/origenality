#!/usr/bin/env python3
"""Origenality — contrôle d'un fichier de tags contre le schéma publié.

Le schéma se dit strict (`additionalProperties: false`) ; il fallait pouvoir le
vérifier autrement qu'en le lisant. Ce module valide chaque ligne de
`tags.jsonl` contre `vocabulary/tag_record.schema.json`, énumérations des quatre
axes résolues depuis les fichiers de vocabulaire — la même résolution que celle
envoyée au moteur, pour qu'un contrôle a posteriori porte sur le même schéma
que le contrôle a priori.

Le validateur ne couvre que les mots-clés que le schéma emploie : type,
required, additionalProperties, properties, items, enum, minItems, maxItems,
uniqueItems, minimum, maximum, maxLength. Il ne prétend pas à la conformité
JSON Schema générale ; il prétend à un verdict exact sur ce schéma-ci, sans
dépendance.

    python3 semantic/validate_tags.py semantic/waves/wave2_federated/tags.jsonl
    python3 semantic/validate_tags.py <fichier> --report docs/qa/…json
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tags_io import read_tags, superseded_count  # noqa: E402
from vocabulary_io import load_vocabulary  # noqa: E402

TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "number": (int, float),
    "integer": int,
}


def resolve(schema: dict, vocab) -> dict:
    """Injecte les énumérations des axes là où le schéma les annonce par
    `x-enum-source`, comme le fait le schéma envoyé au moteur."""
    enums = {
        "vocabulary/relevance.json#/relevance": vocab.relevance_ids,
        "vocabulary/works.json#/works": vocab.work_ids,
        "vocabulary/themes.json#/themes": vocab.theme_ids,
        "vocabulary/approaches.json#/approaches": vocab.approach_ids,
    }

    def walk(node):
        if isinstance(node, dict):
            node = {k: walk(v) for k, v in node.items()}
            source = node.pop("x-enum-source", None)
            if source and source in enums:
                node["enum"] = list(enums[source])
            return node
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def check(value, schema, path, errors):
    expected = schema.get("type")
    if expected:
        python_type = TYPES.get(expected)
        if expected == "number" and isinstance(value, bool):
            errors.append(f"{path}: boolean where a number is required")
            return
        if expected == "boolean" and not isinstance(value, bool):
            errors.append(f"{path}: {type(value).__name__} where a boolean is required")
            return
        if python_type and not isinstance(value, python_type):
            errors.append(f"{path}: {type(value).__name__} where {expected} is required")
            return

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} outside the enumeration")

    if isinstance(value, str):
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: {len(value)} characters, maximum {schema['maxLength']}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} below the minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} above the maximum {schema['maximum']}")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: {len(value)} items, minimum {schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: {len(value)} items, maximum {schema['maxItems']}")
        if schema.get("uniqueItems") and len(value) != len({json.dumps(v, sort_keys=True) for v in value}):
            errors.append(f"{path}: repeated items")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                check(item, item_schema, f"{path}[{index}]", errors)

    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        for name in schema.get("required") or []:
            if name not in value:
                errors.append(f"{path}: required property {name!r} missing")
        if schema.get("additionalProperties") is False:
            for name in value:
                if name not in properties:
                    errors.append(f"{path}: property {name!r} not declared by the schema")
        for name, item in value.items():
            if name in properties:
                check(item, properties[name], f"{path}.{name}" if path else name, errors)


def relative_to_root(path):
    root = Path(__file__).resolve().parent.parent
    try:
        return str(Path(path).resolve().relative_to(root))
    except ValueError:
        return str(path)


def main(argv):
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tags", type=Path)
    parser.add_argument("--schema", type=Path,
                        default=here / "vocabulary" / "tag_record.schema.json")
    parser.add_argument("--vocabulary", type=Path, default=here / "vocabulary")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--max-shown", type=int, default=12)
    arguments = parser.parse_args(argv)

    vocab = load_vocabulary(arguments.vocabulary)
    schema = resolve(json.loads(arguments.schema.read_text(encoding="utf-8")), vocab)

    # Le contrôle porte sur ce que l'aval publiera, c'est-à-dire la DERNIÈRE
    # ligne de chaque notice ; les lignes qu'un retag a rendues caduques sont
    # comptées à part, jamais validées ni comptées comme fautes.
    superseded = superseded_count(arguments.tags)
    records = read_tags(arguments.tags)
    lines = 0
    invalid = 0
    reasons = collections.Counter()
    shown = []
    for number, record in enumerate(records, start=1):
        lines += 1
        errors = []
        check(record, schema, "", errors)
        if errors:
            invalid += 1
            for message in errors:
                reasons[message.split(":", 1)[-1].strip()[:80]] += 1
            if len(shown) < arguments.max_shown:
                shown.append({"record": number, "notice_id": record.get("notice_id"),
                              "errors": errors})

    summary = {
        "tags": str(arguments.tags),
        # Chemin relatif à la racine : une sortie de contrôle archivée ne doit
        # pas exposer l'arborescence de la machine qui l'a produite.
        "schema": relative_to_root(arguments.schema),
        "schema_version": json.loads(
            arguments.schema.read_text(encoding="utf-8")).get("version"),
        "lines": lines,
        "superseded_lines": superseded,
        "invalid": invalid,
        "reasons": dict(reasons.most_common(20)),
        "examples": shown,
    }
    if arguments.report:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(
            json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "examples"},
                     ensure_ascii=False, indent=1))
    for example in shown:
        print(f"  record {example['record']} ({example['notice_id']}): "
              f"{'; '.join(example['errors'][:3])}")
    return 1 if invalid else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
