"""Loader for the controlled vocabulary.

Single point of access to the four axis files, so that the tagger, the tree
builder and the navigator can never disagree about what an identifier means.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_DIR = Path(__file__).resolve().parent / "vocabulary"

AXIS_FILES = {
    "works": ("works.json", "works"),
    "themes": ("themes.json", "themes"),
    "approaches": ("approaches.json", "approaches"),
    "relevance": ("relevance.json", "relevance"),
}


def fold(text: str) -> str:
    """Lower-case, strip accents, collapse whitespace. Used by every matcher."""
    decomposed = unicodedata.normalize("NFD", text or "")
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", stripped.lower()).strip()


@dataclass(frozen=True)
class Vocabulary:
    root: Path
    works: dict[str, dict[str, Any]]
    themes: dict[str, dict[str, Any]]
    domains: dict[str, dict[str, Any]]
    approaches: dict[str, dict[str, Any]]
    relevance: dict[str, dict[str, Any]]
    work_categories: dict[str, dict[str, Any]]
    versions: dict[str, str]

    # -- enums -------------------------------------------------------------
    @property
    def work_ids(self) -> list[str]:
        return sorted(self.works)

    @property
    def theme_ids(self) -> list[str]:
        return sorted(self.themes)

    @property
    def approach_ids(self) -> list[str]:
        return sorted(self.approaches)

    @property
    def relevance_ids(self) -> list[str]:
        return list(self.relevance)

    @property
    def version_string(self) -> str:
        return ";".join(f"{axis}={self.versions[axis]}" for axis in sorted(self.versions))

    # -- helpers -----------------------------------------------------------
    def domain_of(self, theme_id: str) -> str:
        return str(self.themes.get(theme_id, {}).get("domain", ""))

    def themes_by_domain(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {domain: [] for domain in self.domains}
        for theme_id in self.theme_ids:
            grouped.setdefault(self.domain_of(theme_id), []).append(theme_id)
        return grouped

    def label(self, axis: str, identifier: str) -> str:
        table = getattr(self, axis)
        return str(table.get(identifier, {}).get("label", identifier))

    def alias_index(self, axis: str) -> dict[str, list[str]]:
        """Folded alias or label -> identifiers. Feeds the deterministic fallback."""
        table = getattr(self, axis)
        index: dict[str, list[str]] = {}
        for identifier, entry in table.items():
            terms = [entry.get("label", "")]
            terms += list(entry.get("aliases") or [])
            terms += [str(v) for v in (entry.get("labels") or {}).values()]
            terms += list(entry.get("ix_headings") or [])
            for term in terms:
                key = fold(str(term))
                if len(key) < 4:
                    continue
                index.setdefault(key, [])
                if identifier not in index[key]:
                    index[key].append(identifier)
        return index


def load_vocabulary(root: Path | str | None = None) -> Vocabulary:
    directory = Path(root) if root else DEFAULT_DIR
    loaded: dict[str, Any] = {}
    versions: dict[str, str] = {}
    for axis, (filename, key) in AXIS_FILES.items():
        path = directory / filename
        data = json.loads(path.read_text(encoding="utf-8"))
        loaded[axis] = data[key]
        versions[axis] = str(data.get("version", "0"))
    themes_doc = json.loads((directory / "themes.json").read_text(encoding="utf-8"))
    works_doc = json.loads((directory / "works.json").read_text(encoding="utf-8"))
    return Vocabulary(
        root=directory,
        works=loaded["works"],
        themes=loaded["themes"],
        domains=themes_doc["domains"],
        approaches=loaded["approaches"],
        relevance=loaded["relevance"],
        work_categories=works_doc["categories"],
        versions=versions,
    )


def tag_record_schema(vocab: Vocabulary) -> dict[str, Any]:
    """Strict JSON schema for one tag record, enums resolved from the vocabulary.

    Only the fields the tagger has to produce are included; provenance fields
    are added by the writer, never by the model.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "relevance",
            "relevance_none_reason",
            "works",
            "themes",
            "approaches",
            "confidence",
            "justification",
            "needs_review",
        ],
        "properties": {
            "relevance": {"type": "string", "enum": vocab.relevance_ids},
            # Why "none" was chosen, so that the curated-perimeter floor can be
            # applied outside the model: a homonym and a text by Origen keep
            # "none" inside a curated perimeter, thin metadata does not.
            "relevance_none_reason": {
                "type": "string",
                "enum": [
                    "not-applicable",
                    "homonym",
                    "text-by-origen",
                    "insufficient-metadata",
                    "other-subject",
                ],
            },
            "works": {
                "type": "array",
                "minItems": 1,
                "maxItems": 4,
                "items": {"type": "string", "enum": vocab.work_ids},
            },
            # 0 thème est la réponse juste quand relevance vaut "none" : une
            # notice hors dossier n'a pas de thème, et lui en imposer un a fait
            # de general-presentation un remplissage.
            "themes": {
                "type": "array",
                "minItems": 0,
                "maxItems": 5,
                "items": {"type": "string", "enum": vocab.theme_ids},
            },
            "approaches": {
                "type": "array",
                "minItems": 1,
                "maxItems": 2,
                "items": {"type": "string", "enum": vocab.approach_ids},
            },
            "confidence": {"type": "number"},
            "justification": {"type": "string"},
            "needs_review": {"type": "boolean"},
        },
    }
