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

# ---------------------------------------------------------------------------
# Le schéma d'un enregistrement
# ---------------------------------------------------------------------------
#
# Une seule fonction rend les deux schémas : celui qu'on envoie au moteur et
# celui qu'on publie. Ils étaient auparavant écrits deux fois — un fichier
# statique d'un côté, une fabrique en mémoire de l'autre —, reliés par les
# seuls marqueurs `x-enum-source`. Les énumérations ne pouvaient donc pas
# diverger, mais tout le reste si, et le reste divergeait : `uniqueItems`, les
# bornes de `confidence` et la longueur de `justification` n'existaient que du
# côté publié, de sorte que le moteur travaillait sous un contrat plus lâche
# que celui contre lequel on relisait ses réponses.

SCHEMA_VERSION = "1.3.0"
SCHEMA_ID = f"https://origenality.org/schemas/tag_record-{SCHEMA_VERSION}.json"

SCHEMA_DESCRIPTION = (
    "One line of the tagging output. This file is GENERATED by "
    "semantic/build_tag_schema.py from vocabulary_io.tag_record_schema(vocab, full=True): "
    "the same function renders the schema sent to the tagger, so neither can drift from "
    "the other. Do not edit by hand — change the code or the vocabulary and regenerate. "
    "The enum values of relevance, works, themes and approaches are not written out here: "
    "they are injected from the four vocabulary files, so that the schema can never drift "
    "from the vocabulary. tag_notices.py --print-schema prints the resolved schema actually "
    "sent to the model. Two families of properties are written by the pipeline and never by "
    "the tagger: the record of what validation had to repair (repairs, "
    "relevance_floor_applied, relevance_ceiling_applied, output_mode) and the record of an "
    "identifier change after a re-merge of the corpus (remapped_from, remap_status). They "
    "are declared here because additionalProperties is false and a strict schema that its "
    "own outputs violate is not a schema."
)

# Où le schéma va chercher ses énumérations. Le marqueur reste dans le fichier
# publié : il dit que la liste des valeurs est ailleurs, et empêche qu'on la
# corrige ici plutôt que dans le vocabulaire.
ENUM_SOURCES = {
    "relevance": "vocabulary/relevance.json#/relevance",
    "works": "vocabulary/works.json#/works",
    "themes": "vocabulary/themes.json#/themes",
    "approaches": "vocabulary/approaches.json#/approaches",
}

# Les champs que le classeur a à produire. Bornes de listes, unicité et bornes
# numériques sont ici, une fois, pour les deux schémas.
def _answer_properties() -> dict[str, Any]:
    return {
        'relevance': {
            "type": "string",
            "x-enum-source": "vocabulary/relevance.json#/relevance",
            "description": "Exactly one value."
        },
        'relevance_none_reason': {
            "type": "string",
            "enum": [
                "not-applicable",
                "homonym",
                "text-by-origen",
                "insufficient-metadata",
                "other-subject"
            ],
            "description": "Why relevance is \"none\". \"not-applicable\" whenever relevance is not \"none\". A homonym and a text by Origen keep \"none\" inside a curated perimeter; the other reasons do not."
        },
        'works': {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "uniqueItems": True,
            "items": {
                "type": "string",
                "x-enum-source": "vocabulary/works.json#/works"
            },
            "description": "Works of Origen the publication bears on, at most four — a longer list is truncated to its first four. Use [\"unspecified\"] alone when none is identifiable."
        },
        'themes': {
            "type": "array",
            "minItems": 0,
            "maxItems": 5,
            "uniqueItems": True,
            "items": {
                "type": "string",
                "x-enum-source": "vocabulary/themes.json#/themes"
            },
            "description": "Leaf theme identifiers, most central first. Empty when relevance is \"none\": a notice out of the dossier has no theme, and imposing one made general-presentation a filler."
        },
        'approaches': {
            "type": "array",
            "minItems": 1,
            "maxItems": 2,
            "uniqueItems": True,
            "items": {
                "type": "string",
                "x-enum-source": "vocabulary/approaches.json#/approaches"
            }
        },
        'confidence': {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Self-reported confidence of the tagging as a whole. 0.9 and above: the metadata states it. 0.6 to 0.9: clear inference. Below 0.6: uncertain, and needs_review must be true."
        },
        'justification': {
            "type": "string",
            "maxLength": 300,
            "description": "One line, in English, naming the elements of the notice that carried the decision. No new facts."
        },
        'needs_review': {
            "type": "boolean",
            "description": "True whenever confidence is below the review threshold, the metadata is too thin, or the tagger hesitated between two relevance values."
        },
    }


# Les champs que le pipeline écrit lui-même : provenance, réparations,
# renumérotation. Le classeur ne les voit jamais.
def _provenance_properties() -> dict[str, Any]:
    return {
        'notice_id': {
            "type": "string",
            "description": "Deterministic identifier of the notice: <source>:<source_id> when both exist, otherwise a sha1 over the normalised title, first author and year."
        },
        'wave': {
            "type": "string",
            "description": "Provenance wave, e.g. semantic_tags_ixtheo_2026_08."
        },
        'run_id': {
            "type": "string",
            "description": "Identifier of the individual run inside the wave."
        },
        'source_model': {
            "type": "string",
            "description": "Opaque identifier of the tagger, read from the environment at run time. Never hard-coded. The value manual-gold marks records annotated by hand."
        },
        'auto_generated': {
            "type": "boolean",
            "description": "False only for hand-annotated gold records."
        },
        'tagged_at': {
            "type": "string",
            "description": "UTC timestamp, ISO 8601."
        },
        'vocabulary_version': {
            "type": "string",
            "description": "Concatenated versions of the four vocabulary files, e.g. works=1.0.0;themes=1.0.0;approaches=1.0.0;relevance=1.0.0."
        },
        'prompt_version': {
            "type": "string",
            "description": "Version tag of the prompt template used."
        },
        'prompt_digest': {
            "type": "string",
            "description": "sha1 of the system prompt actually sent, rendered vocabulary included. The version tag is bumped by hand and therefore forgotten; the digest is not. Absent from records written before the field existed: its absence never invalidates a record, only a digest that is present and different does."
        },
        'input_digest': {
            "type": "string",
            "description": "sha1 of the exact notice payload sent to the tagger. Two runs with the same digest and the same prompt_version are comparable."
        },
        'gold': {
            "type": "boolean",
            "description": "True on records of the hand-annotated calibration set."
        },
        'annotator': {
            "type": "string",
            "description": "Present on gold records only."
        },
        'curated_scope': {
            "type": "boolean",
            "description": "True when the notice comes from a perimeter curated against the authority record for Origen: IxTheo, BIBP, or sections 12 and 13 of the Adamantius repertorio. Inside such a perimeter the floor of relevance is \"marginal\"."
        },
        'relevance_floor_applied': {
            "type": "boolean",
            "description": "True when the curated-perimeter floor lifted a \"none\" to \"marginal\" after the answer. A policy, recorded as such, not a judgement of the tagger."
        },
        'themes_not_applicable': {
            "type": "boolean",
            "description": "Hand-tagged records only: the notice is out of the dossier and its themes are a filler the vocabulary imposes, to be excluded from theme agreement."
        },
        'repairs': {
            "type": "array",
            "items": {
                "type": "string"
            },
            "description": "Written by validation, never by the tagger: one line per correction applied to the answer (a value dropped as outside the vocabulary, a confidence outside [0,1] clamped and flagged, a ceiling applied). A non-empty list forces needs_review."
        },
        'relevance_ceiling_applied': {
            "type": "boolean",
            "description": "True when the deterministic ceiling brought a notice catalogued as a text by Origen down to \"marginal\". A policy, recorded as such."
        },
        'output_mode': {
            "type": "string",
            "enum": [
                "schema",
                "json",
                "off"
            ],
            "description": "How the answer was actually obtained for this line: under the resolved schema, under a plain JSON instruction, or with no output constraint at all. Recorded per line because the adapter may fall back, and a line obtained without the schema is not evidence of the same rigour as one obtained under it."
        },
        'remapped_from': {
            "type": "string",
            "description": "Former origenality_id of this notice, when a re-merge of the corpus renumbered its cluster. Written by semantic/remap_tag_ids.py."
        },
        'remap_status': {
            "type": "string",
            "enum": [
                "identity",
                "unique-successor",
                "digest-matched",
                "majority-fallback"
            ],
            "description": "How the new identifier was chosen. majority-fallback means the former cluster was split and the input digest did not settle which half was tagged: the line is kept, attributed to the larger half, and flagged needs_review."
        },
        'gold_version': {
            "type": "string",
            "description": "Version of the annotation rules the gold record was produced under — the prompt version and the theme vocabulary the annotator applied, e.g. v2.1. A gold set mixing versions measures nothing: report.py refuses to compare a run to gold records annotated under other rules."
        },
        'gold_batch': {
            "type": "string",
            "description": "Which batch of the gold set the record belongs to (ixtheo_30, federated_20…)."
        },
        'revision': {
            "type": "string",
            "description": "What changed at the last re-annotation of this gold record, in one line: which rule or vocabulary version moved it and how. Free text, kept so that a gold value can be argued with rather than merely trusted."
        },
        'notice_id_pilot': {
            "type": "string",
            "description": "Identifier the notice carried in the pilot, when it differs from the identifier of the merged corpus."
        },
    }


ANSWER_REQUIRED = [
    "relevance", "relevance_none_reason", "works", "themes", "approaches",
    "confidence", "justification", "needs_review",
]
RECORD_REQUIRED = ["notice_id"] + ANSWER_REQUIRED + [
    "wave", "run_id", "source_model", "auto_generated", "tagged_at",
    "vocabulary_version", "prompt_version",
]


def resolve(schema: dict[str, Any], vocab: Vocabulary) -> dict[str, Any]:
    """Remplace les marqueurs `x-enum-source` par les valeurs du vocabulaire.

    Le contrôle a posteriori doit porter sur le schéma du contrôle a priori :
    la résolution est donc faite ici, une fois, et non redite par chaque
    consommateur.
    """
    enums = {
        ENUM_SOURCES["relevance"]: vocab.relevance_ids,
        ENUM_SOURCES["works"]: vocab.work_ids,
        ENUM_SOURCES["themes"]: vocab.theme_ids,
        ENUM_SOURCES["approaches"]: vocab.approach_ids,
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


def tag_record_schema(vocab: Vocabulary, full: bool = False) -> dict[str, Any]:
    """Le schéma d'un enregistrement, rendu depuis le vocabulaire du dépôt.

    `full=False` rend le schéma de la RÉPONSE, énumérations résolues : les seuls
    champs que le classeur a à produire, et c'est celui qu'on envoie au moteur.
    `full=True` rend le document PUBLIÉ — les mêmes champs plus ceux que le
    pipeline écrit lui-même, marqueurs `x-enum-source` en place —, et c'est lui
    qu'écrit `build_tag_schema.py`. Le second contient le premier : un schéma
    que ses propres sorties violent n'est pas un schéma.
    """
    answer = _answer_properties()
    if not full:
        return resolve({
            "type": "object",
            "additionalProperties": False,
            "required": list(ANSWER_REQUIRED),
            "properties": answer,
        }, vocab)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "Origenality Tag Record",
        "description": SCHEMA_DESCRIPTION,
        "version": SCHEMA_VERSION,
        "generated_by": "semantic/build_tag_schema.py — do not edit by hand",
        "vocabulary_version": vocab.version_string,
        "type": "object",
        "additionalProperties": False,
        "required": list(RECORD_REQUIRED),
        # L'identifiant d'abord, puis la réponse, puis la provenance : l'ordre
        # de lecture du document publié, tenu ici pour qu'une régénération se
        # relise en diff plutôt qu'en remaniement.
        "properties": _ordered_properties(answer),
    }


def _ordered_properties(answer: dict[str, Any]) -> dict[str, Any]:
    provenance = _provenance_properties()
    ordered = {"notice_id": provenance.pop("notice_id")}
    ordered.update(answer)
    ordered.update(provenance)
    return ordered
