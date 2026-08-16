"""Semantic tagging of bibliographic notices against the controlled vocabulary.

Reads a JSONL of notices, writes a JSONL of tag records — one per notice —
whose every value comes from `vocabulary/`. Nothing is free text except a
one-line justification.

    python3 tag_notices.py --input ../data/raw/ixtheo/records.jsonl \\
        --output pilot/tags_ixtheo.jsonl --wave semantic_tags_ixtheo_2026_08

Properties that matter for reproducibility:

* deterministic notice identifiers, so two runs address the same objects;
* resume by default: a notice already tagged in the same wave is skipped;
* every record carries wave, run_id, source_model, prompt and vocabulary
  versions, and a digest of the exact payload submitted;
* refusals and transport errors are kept in a separate rejects file rather
  than silently dropped;
* `--dry-run` writes the prompts that would be sent and calls nothing.

The endpoint is reached through `llm_adapter`, which reads its address, its
credential and its model identifier from the environment. No provider and no
model name appears in this file.
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import hashlib
import json
import os
import re
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm_adapter  # noqa: E402
from tags_io import compact  # noqa: E402
from vocabulary_io import Vocabulary, load_vocabulary, tag_record_schema  # noqa: E402

PROMPT_VERSION = "tag-notice-v2.1"
ABSTRACT_CHARS = 1200
DEFAULT_REVIEW_THRESHOLD = 0.6

# Sources whose whole perimeter is curated against an authority record for
# Origen: a cataloguer has already decided the notice belongs to the dossier.
# Inside such a perimeter the floor of relevance is "marginal", never "none".
CURATED_SOURCES = {"ixtheo-k10plus", "bibp"}
CURATED_ADAMANTIUS_SECTIONS = ("12.", "13.")
RELEVANCE_ORDER = ["none", "marginal", "partial", "core"]


def _none_reasons() -> frozenset[str]:
    """Liste fermée des motifs de `none`, lue dans le schéma publié.

    La lire plutôt que la recopier évite qu'elle diverge : le schéma est la
    seule déclaration, ici comme dans le prompt envoyé au moteur.
    """
    path = Path(__file__).resolve().parent / "vocabulary" / "tag_record.schema.json"
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
        values = schema["properties"]["relevance_none_reason"]["enum"]
    except (OSError, KeyError, ValueError):
        return frozenset({"not-applicable", "homonym", "text-by-origen",
                          "insufficient-metadata", "other-subject"})
    return frozenset(str(v) for v in values)


NONE_REASONS = _none_reasons()

SYSTEM_PROMPT_HEAD = """You are a cataloguer for a bibliography of scholarship on Origen of Alexandria.

You receive the metadata of one bibliographic notice and assign tags from a closed
vocabulary. You never write prose, never propose a new tag, and never state a fact
that is not in the metadata you were given.

Rules that override everything else:
1. Judge from the metadata alone: title, subject headings, container, abstract when
   present. You have not read the publication. Do not use outside knowledge to decide
   what the publication argues; use it only to recognise a name or a title.
2. Never invent. If the metadata does not positively show that Origen of Alexandria is
   discussed, answer relevance "none" and needs_review true.
2bis. Exception when the field curated_scope is present. It says that a cataloguer has
   already tied this notice to the authority record for Origen, inside a perimeter built
   for him. The notice then belongs to the dossier even when the title does not name him:
   he is one witness among others in a study of patristic doctrine, of an ancient
   controversy, of a later reader. In that case the floor is relevance "marginal", never
   "none". "none" stays available for two cases only: a homonym (rule 3), or a text
   written by Origen and catalogued as such (rule 4).
2ter. Inside a curated perimeter, the line between "partial" and "marginal" is drawn on
   one test, and on nothing else: does the metadata show that Origen holds at least one
   identifiable part of the publication — a named chapter or section, a subject chain or
   a heading that files part of the work under him, an abstract that says he is treated
   there? If yes, answer "partial". If the metadata shows only that a cataloguer filed
   the notice under him, with no part of the work identifiably his, answer "marginal".
   Do not weigh how important Origen looks, and do not guess at a proportion; ask only
   whether a part is identifiable. A collective volume of Origen studies — proceedings of
   a colloquium on Origen, a Festschrift on him, a companion — is "core": the whole
   volume is the identifiable part.
3. Beware of homonyms: the Spanish common nouns origen and origenes, the phrase
   "origenes de", and the distinct figure Origenes Platonicus are not this Origen.
4. A text written by Origen, catalogued as such, is not a study of Origen. Answer
   relevance "none" with relevance_none_reason "text-by-origen". This holds for an old
   edition of his works — a sixteenth or seventeenth-century Opera, a reprint of one —
   whatever its historical value: printing a text is not studying it, and rule 2bis does
   not lift it, since "text-by-origen" is one of the two reasons that survive the floor.
   One exception, and it goes no higher than "marginal": when the metadata itself shows
   substantial scholarly matter around the text — a critical apparatus, a named editor's
   introduction or commentary, a series of critical editions such as Sources
   Chrétiennes, Die griechischen christlichen Schriftsteller, Corpus Christianorum —
   answer "marginal" with approach "edition". The scholarly matter must be visible in the
   metadata; the mere word "edition" in a title is not it.
5. Assign a work of Origen only when the metadata names it or clearly implies it.
   Otherwise the single value "unspecified".
6. Assign between one and five theme leaves, most central first. Prefer the leaf that
   the subject headings support; when only the general subject is known, choose the
   leaf closest to it rather than several vague ones.
6bis. A notice that presents Origen as a whole — an encyclopaedia or dictionary entry,
   a handbook or companion chapter, an introduction, a general portrait, a notice whose
   only subject is "Origen" — takes context.general-presentation. Do not put it under
   exegesis.hermeneutic-theory, which is for theory of interpretation proper: senses of
   scripture, allegory as a method, hermeneutic rules. Keep
   scholarship.research-surveys for research reports, status quaestionis and
   bibliographies, that is for writing about the scholarship rather than about Origen.
7. Assign one or two approaches. "review" is for book reviews, "edition" for editions
   and translations, "survey" for handbooks, bibliographies and collective volumes.
8. confidence is your confidence in the whole record: 0.9 and above when the metadata
   states it, 0.6 to 0.9 for a clear inference, below 0.6 when you are guessing.
   Set needs_review true whenever confidence is below 0.6, the metadata is too thin,
   or you hesitated between two relevance values — and in that case take the lower one.
9. justification: one English line naming the metadata elements that decided the case
   (for instance: title names Contra Celsum; headings Apologetik, Celsus). No new facts.
10. relevance_none_reason: "not-applicable" whenever relevance is not "none". When it is
   "none", say which case: "homonym", "text-by-origen", "insufficient-metadata" when the
   metadata is too thin to decide, "other-subject" when the notice is plainly about
   something else.

Answer with a single JSON object and nothing else.
"""


# ---------------------------------------------------------------------------
# vocabulary rendering
# ---------------------------------------------------------------------------

def render_vocabulary(vocab: Vocabulary) -> str:
    lines: list[str] = []
    lines.append("RELEVANCE (choose exactly one):")
    for identifier, entry in vocab.relevance.items():
        lines.append(f"  {identifier}: {entry['label']} — {entry['description']}")

    lines.append("")
    lines.append("WORKS OF ORIGEN (choose one to four; 'unspecified' alone when none applies):")
    for identifier in vocab.work_ids:
        entry = vocab.works[identifier]
        lines.append(f"  {identifier}: {entry['label']}")

    lines.append("")
    lines.append("THEMES (choose one to five leaf identifiers, most central first):")
    grouped = vocab.themes_by_domain()
    for domain_id, domain in vocab.domains.items():
        leaves = grouped.get(domain_id, [])
        if not leaves:
            continue
        lines.append(f"  [{domain['label']}]")
        for identifier in leaves:
            lines.append(f"    {identifier}: {vocab.themes[identifier]['label']}")

    lines.append("")
    lines.append("APPROACHES (choose one or two):")
    for identifier in vocab.approach_ids:
        entry = vocab.approaches[identifier]
        lines.append(f"  {identifier}: {entry['label']} — {entry['description']}")
    return "\n".join(lines)


def system_prompt(vocab: Vocabulary) -> str:
    return SYSTEM_PROMPT_HEAD + "\n" + render_vocabulary(vocab)


# ---------------------------------------------------------------------------
# notices
# ---------------------------------------------------------------------------

def record_sources(record: dict[str, Any]) -> list[str]:
    """Source names of a notice, in both shapes the project uses.

    A raw harvest record carries a flat `source`; a merged cluster carries a
    `sources` list of {source, source_id}.
    """
    names: list[str] = []
    for entry in record.get("sources") or []:
        if isinstance(entry, dict):
            name = str(entry.get("source") or "").strip()
        else:
            name = str(entry).strip()
        if name and name not in names:
            names.append(name)
    flat = str(record.get("source") or "").strip()
    if flat and flat not in names:
        names.append(flat)
    return names


def curated_scope(record: dict[str, Any]) -> str:
    """Non-empty when the notice comes from a perimeter curated by authority.

    Three perimeters qualify: the IxTheo notices attached to the authority
    record for Origen, the Bibliographie de Bible et Patristique, and sections
    12 and 13 of the Adamantius repertorio (Origen; Origenism and the fortune
    of Origen). The returned string is what the tagger reads.
    """
    sources = set(record_sources(record))
    reasons: list[str] = []
    if sources & CURATED_SOURCES:
        reasons.append("catalogued under the authority record for Origen")
    if "adamantius-girota" in sources:
        for section in record.get("sections") or []:
            name = section.get("sezione") if isinstance(section, dict) else str(section)
            if str(name or "").strip().startswith(CURATED_ADAMANTIUS_SECTIONS):
                reasons.append(f"repertorio section {str(name).strip()}")
                break
    return "; ".join(reasons)


def notice_identifier(record: dict[str, Any]) -> str:
    stable = str(record.get("origenality_id") or "").strip()
    if stable:
        return stable
    source = str(record.get("source") or "unknown")
    source_id = str(record.get("source_id") or record.get("id") or "").strip()
    if source_id:
        return f"{source}:{source_id}"
    authors = record.get("authors") or []
    first = ""
    if authors and isinstance(authors[0], dict):
        first = str(authors[0].get("name") or "")
    elif authors:
        first = str(authors[0])
    basis = "|".join([str(record.get("title") or ""), first, str(record.get("year") or "")])
    return f"{source}:sha1:{hashlib.sha1(basis.encode('utf-8')).hexdigest()[:16]}"


def author_names(record: dict[str, Any], limit: int = 6) -> list[str]:
    names: list[str] = []
    for author in record.get("authors") or []:
        if isinstance(author, dict):
            name = str(author.get("name") or "").strip()
            role = str(author.get("role") or "").strip()
            if name:
                names.append(f"{name} ({role})" if role and role != "aut" else name)
        elif isinstance(author, str) and author.strip():
            names.append(author.strip())
        if len(names) >= limit:
            break
    return names


ORIGEN_AUTHOR_FORMS = {
    "origenes", "origene", "origen", "origenes adamantius", "origenes alexandrinus",
    "origen of alexandria", "origene di alessandria", "origene alessandrino",
    "origenes von alexandrien", "origenes alexandrinus adamantius", "origenes adamantios",
}
ORIGEN_GND = "118590235"


def text_by_origen(record: dict[str, Any]) -> bool:
    """True when the catalogue presents the notice as a work OF Origen.

    Two signals, and no third. `relation` says it outright when the harvest
    carries the field. When it does not — an OpenAlex record of a sixteenth-
    century Opera, say — Origen standing in the author list says the same
    thing: nobody credits him as author of a study about him. `relation` of
    "both", an edition bound with studies, is not this case and is left alone.
    """
    relation = str(record.get("relation") or "").strip().lower()
    if relation == "by":
        return True
    if relation:
        return False
    for author in record.get("authors") or []:
        if isinstance(author, dict):
            if str(author.get("gnd") or "") == ORIGEN_GND:
                return True
            name = str(author.get("name") or "")
        else:
            name = str(author or "")
        folded = unicodedata.normalize("NFD", name).lower()
        folded = "".join(c for c in folded if unicodedata.category(c) != "Mn")
        folded = " ".join(w for w in re.split(r"[^a-z]+", folded) if w and w != "ca")
        if folded in ORIGEN_AUTHOR_FORMS:
            return True
    return False


def subject_terms(record: dict[str, Any]) -> list[str]:
    """Every controlled term a source attached to the notice, deduplicated.

    The federated corpus carries five vocabularies under five names: IxTheo
    subject headings, Adamantius sections, OpenAlex topics, bibp descriptors
    and theses.fr Rameau headings. They are merged here because the tagger
    reads them all the same way, as evidence of what the notice is about.
    """
    terms: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, dict):
            value = value.get("term") or value.get("sezione") or value.get("display_name")
        text = str(value or "").strip()
        if text and text not in terms:
            terms.append(text)

    for key in ("subjects", "topics", "descriptors", "subjects_rameau", "disciplines"):
        for value in record.get(key) or []:
            add(value)
    for section in record.get("sections") or []:
        add(section)
    return terms[:30]


def notice_payload(record: dict[str, Any]) -> dict[str, Any]:
    container = record.get("container") or {}
    abstract = record.get("abstract")
    payload = {
        "title": record.get("title"),
        "authors": author_names(record),
        "year": record.get("year"),
        "language": record.get("language") or (record.get("languages") or [None])[0],
        "format": record.get("format") or record.get("type"),
        "container": container.get("title") if isinstance(container, dict) else container,
        "publisher": record.get("publisher"),
        "subjects": subject_terms(record),
        "subject_chains": (record.get("subject_chains") or [])[:25],
        "abstract": (abstract[:ABSTRACT_CHARS] if isinstance(abstract, str) else None),
        "catalogued_relation": record.get("relation"),
        "catalogued_as_text_by_origen": True if text_by_origen(record) else None,
        "curated_scope": curated_scope(record),
    }
    return {key: value for key, value in payload.items() if value not in (None, [], "")}


def user_prompt(payload: dict[str, Any]) -> str:
    return (
        "Notice metadata (JSON). Fields absent from the object are unknown; "
        "do not guess them.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True)
    )


def payload_digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]


def read_notices(
    path: Path,
    relations: set[str] | None,
    exclude_relations: set[str] | None = None,
    skip_noise: bool = False,
) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                yield {"__malformed__": True, "__line__": line_number}
                continue
            relation = str(record.get("relation") or "")
            if relations and relation not in relations:
                continue
            if exclude_relations and relation in exclude_relations:
                continue
            # Le pré-tri mécanique est calculé notice par notice, à la moisson,
            # sur le titre et le sujet d'OpenAlex ou de Crossref. Une grappe en
            # hérite d'une seule de ses notices donatrices, et cette notice-là
            # peut être la moins bien décrite : « Wort und Eucharistie bei
            # Origenes » est sorti du dossier parce que le sujet principal de
            # son jumeau OpenAlex portait le mot « education ». Quand la même
            # grappe porte aussi une notice d'un périmètre curaté, un
            # catalogueur l'a déjà rattachée à la fiche d'autorité d'Origène :
            # ce jugement-là vaut mieux qu'un pré-tri sur un mot du sujet, et
            # il l'emporte. Le bruit espagnol n'y gagne rien — « denominaciones
            # de origen » n'est catalogué ni à IxTheo sous Origène ni à la
            # Bibliographie de Bible et Patristique.
            if skip_noise and record.get("noise_guess") is True and not curated_scope(record):
                continue
            yield record


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

@dataclass
class Validation:
    values: dict[str, Any] = field(default_factory=dict)
    repairs: list[str] = field(default_factory=list)
    error: str = ""


def validate(
    answer: dict[str, Any],
    vocab: Vocabulary,
    review_threshold: float,
    curated: str = "",
    by_origen: bool = False,
) -> Validation:
    result = Validation()

    relevance = str(answer.get("relevance") or "").strip()
    if relevance not in vocab.relevance:
        result.error = f"relevance not in vocabulary: {relevance!r}"
        return result

    none_reason = str(answer.get("relevance_none_reason") or "").strip() or "not-applicable"
    if relevance != "none":
        none_reason = "not-applicable"
    elif none_reason not in NONE_REASONS:
        # Un motif inventé — « unclear », « no-info » — passait sans contrôle et
        # ressortait dans les sorties comme une valeur du vocabulaire. Le motif
        # est une énumération fermée : hors de la liste, la ligne est rejetée,
        # comme l'est une relevance hors vocabulaire.
        result.error = f"relevance_none_reason not in the closed list: {none_reason!r}"
        return result

    # Floor of the curated perimeter, applied here as well as in the prompt so
    # that the rule holds whatever the model answers. Two reasons survive the
    # floor, exactly the two the pilot notes reserve: a homonym, and a text
    # written by Origen and catalogued as such.
    lifted = False
    if (
        curated
        and relevance == "none"
        and none_reason not in {"homonym", "text-by-origen"}
        and "marginal" in vocab.relevance
    ):
        relevance = "marginal"
        lifted = True

    # Ceiling on a text by Origen. When the catalogue itself says the notice is
    # a work of his rather than a work about him, printing that text is not
    # studying it: the notice cannot count in the density, whatever apparatus
    # travels with it. The prompt says so (rule 4); the ceiling holds here as
    # well, so that the rule does not depend on the answer. `both` — an edition
    # bound with studies — is untouched, and so is `about`.
    capped = False
    if (
        by_origen
        and relevance in {"core", "partial"}
        and "marginal" in vocab.relevance
    ):
        relevance = "marginal"
        capped = True
        result.repairs.append("relevance capped at marginal: catalogued as a text by Origen")

    def clean(axis: str, allowed: list[str], maximum: int) -> list[str]:
        raw = answer.get(axis)
        raw = raw if isinstance(raw, list) else ([raw] if isinstance(raw, str) else [])
        kept: list[str] = []
        for value in raw:
            value = str(value).strip()
            if value in allowed and value not in kept:
                kept.append(value)
            elif value:
                result.repairs.append(f"dropped {axis}:{value}")
        return kept[:maximum]

    works = clean("works", vocab.work_ids, 4)
    themes = clean("themes", vocab.theme_ids, 5)
    approaches = clean("approaches", vocab.approach_ids, 2)

    if not works:
        works = ["unspecified"]
        result.repairs.append("works defaulted to unspecified")
    if len(works) > 1 and "unspecified" in works:
        works = [w for w in works if w != "unspecified"]
        result.repairs.append("unspecified removed from a non-empty work list")
    if not approaches:
        result.error = "no approach survived validation"
        return result
    if not themes:
        if relevance == "none":
            # Une notice hors dossier n'a pas de thème. Lui en imposer un
            # faisait de `general-presentation` un remplissage : 4 700 de ses
            # 5 184 emplois portaient sur des notices `none`. La liste vide est
            # désormais la réponse juste, et le vocabulaire le dit (cardinalité
            # 0..5).
            themes = []
        elif relevance == "marginal":
            themes = ["context.biography"]
            result.repairs.append("themes defaulted for a marginal notice")
        else:
            result.error = "no theme survived validation"
            return result

    raw_confidence = answer.get("confidence")
    out_of_range = False
    try:
        confidence = float(raw_confidence)
    except (TypeError, ValueError):
        confidence = 0.0
        result.repairs.append("confidence unreadable, set to 0")
    else:
        # Une confiance hors [0, 1] — 2, -1, 95 — était ramenée en silence dans
        # la plage et ressortait en 1.0 sans marque : le moteur n'avait pas
        # répondu sur l'échelle demandée, et la ligne le taisait.
        if not 0.0 <= confidence <= 1.0:
            out_of_range = True
            result.repairs.append(
                f"confidence out of [0,1] ({raw_confidence!r}), clamped and flagged")
    confidence = min(1.0, max(0.0, confidence))

    needs_review = bool(answer.get("needs_review")) or confidence < review_threshold
    if result.repairs or out_of_range:
        needs_review = True

    justification = str(answer.get("justification") or "").strip().replace("\n", " ")[:300]
    if not justification:
        justification = "no justification returned"
        needs_review = True

    result.values = {
        "relevance": relevance,
        "relevance_none_reason": none_reason,
        "relevance_floor_applied": lifted,
        "relevance_ceiling_applied": capped,
        "works": works,
        "themes": themes,
        "approaches": approaches,
        "confidence": round(confidence, 3),
        "justification": justification,
        "needs_review": needs_review,
    }
    return result


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------

class Writer:
    """Append-only JSONL writer, flushed on every record."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._handle = self.path.open("a", encoding="utf-8")

    def write(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            self._handle.write(line + "\n")
            self._handle.flush()
            os.fsync(self._handle.fileno())

    def close(self) -> None:
        with self._lock:
            self._handle.close()


def already_tagged(path: Path, wave: str, prompt_version: str = "",
                   vocabulary_version: str = "") -> set[tuple[str, str]]:
    """Notices déjà traitées dans cette vague, SOUS LA MÊME RÈGLE ET SUR LA MÊME
    FICHE.

    Reprendre sur le seul identifiant faisait passer pour acquis un tag produit
    par un autre prompt ou un autre vocabulaire : changer la règle et relancer
    ne retaguait rien. La clé de saut comprend donc la version du prompt, celle
    du vocabulaire, et l'empreinte de la fiche soumise — `input_digest`, que
    chaque ligne écrit déjà. Sans elle, corriger un titre ou verser un résumé
    sous le même identifiant laissait le vieux tag en place indéfiniment : la
    notice avait changé, le tag non, et rien ne le disait.

    La valeur rendue est un ensemble de couples (identifiant, empreinte) : c'est
    la clé complète, comparée telle quelle à ce que la notice donne aujourd'hui.
    """
    done: set[tuple[str, str]] = set()
    if not path.exists():
        return done
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("wave") != wave or not record.get("notice_id"):
                continue
            if prompt_version and record.get("prompt_version") != prompt_version:
                continue
            if vocabulary_version and record.get("vocabulary_version") != vocabulary_version:
                continue
            done.add((str(record["notice_id"]), str(record.get("input_digest") or "")))
    return done


def already_rejected(path: Path | None, wave: str, prompt_version: str = "",
                     vocabulary_version: str = "") -> set[tuple[str, str]]:
    """Notices déjà refusées dans cette vague, sous la même règle et la même fiche.

    Un rejet est un résultat : la notice a été soumise et sa réponse n'a pas
    passé la validation. Ne pas l'inscrire dans l'état de reprise faisait
    resoumettre les mêmes notices à chaque relance, pour le même refus. Mais un
    refus ne vaut que pour la règle et la fiche qui l'ont produit : un rejet
    écrit sous un autre prompt, un autre vocabulaire ou une autre version de la
    notice ne dit rien de la soumission d'aujourd'hui, et le retenir gèlerait la
    notice hors du corpus tagué.

    Les rejets anciens, écrits avant que le fichier ne porte ces champs, sont
    lus comme des refus inconditionnels — leur empreinte vide ne peut coïncider
    avec aucune fiche, donc la notice repart, ce qui est le bon défaut.
    """
    seen: set[tuple[str, str]] = set()
    if not path or not path.exists():
        return seen
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not record.get("notice_id") or record.get("wave", wave) != wave:
                continue
            if prompt_version and record.get("prompt_version", prompt_version) != prompt_version:
                continue
            if vocabulary_version and record.get(
                    "vocabulary_version", vocabulary_version) != vocabulary_version:
                continue
            seen.add((str(record["notice_id"]), str(record.get("input_digest") or "")))
    return seen


def resume_key(record: dict[str, Any]) -> tuple[str, str]:
    """Clé de reprise d'une notice : son identifiant ET l'empreinte de sa fiche."""
    return (notice_identifier(record), payload_digest(notice_payload(record)))


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

@dataclass
class Counters:
    tagged: int = 0
    rejected: int = 0
    skipped: int = 0
    needs_review: int = 0
    repaired: int = 0
    curated: int = 0
    floor_applied: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0


def tag_one(
    record: dict[str, Any],
    vocab: Vocabulary,
    schema: dict[str, Any],
    system: str,
    review_threshold: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, llm_adapter.LLMResult | None]:
    """Returns (tag_values, rejection, llm_result)."""
    notice_id = notice_identifier(record)
    payload = notice_payload(record)
    digest = payload_digest(payload)
    curated = str(payload.get("curated_scope") or "")
    if not payload.get("title"):
        return None, {"notice_id": notice_id, "input_digest": digest,
                      "stage": "input", "error": "no title"}, None

    try:
        result = llm_adapter.complete(
            system,
            user_prompt(payload),
            schema=schema,
            schema_name="origenality_tag_record",
        )
    except llm_adapter.LLMCallFailed as exc:
        return None, {"notice_id": notice_id, "input_digest": digest,
                      "stage": "call", "error": str(exc)[:400]}, None

    try:
        answer = llm_adapter.extract_json(result.content)
    except (json.JSONDecodeError, ValueError) as exc:
        return (
            None,
            {
                "notice_id": notice_id,
                "input_digest": digest,
                "stage": "parse",
                "error": str(exc)[:200],
                "raw": result.content[:600],
            },
            result,
        )

    validation = validate(
        answer, vocab, review_threshold, curated=curated,
        by_origen=bool(payload.get("catalogued_as_text_by_origen")),
    )
    if validation.error:
        return (
            None,
            {
                "notice_id": notice_id,
                "input_digest": digest,
                "stage": "validate",
                "error": validation.error,
                "raw": json.dumps(answer, ensure_ascii=False)[:600],
            },
            result,
        )

    values = dict(validation.values)
    values["notice_id"] = notice_id
    values["input_digest"] = digest
    values["curated_scope"] = bool(curated)
    # L'adaptateur peut dégrader schema → json → off. Une ligne obtenue sans le
    # schéma n'a pas été contrainte de la même façon qu'une ligne obtenue sous
    # lui : le mode effectivement retenu est donc écrit par ligne, et non
    # seulement dans le rapport de run.
    values["output_mode"] = result.structured_mode
    if validation.repairs:
        values["repairs"] = validation.repairs
    return values, None, result


def main(argv: list[str]) -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, help="JSONL of notices")
    parser.add_argument("--output", type=Path, help="JSONL of tag records")
    parser.add_argument("--rejects", type=Path, help="JSONL of rejects (default: <output>.rejects.jsonl)")
    parser.add_argument("--stats", type=Path, help="JSON run report (default: <output>.stats.json)")
    parser.add_argument("--vocabulary", type=Path, default=here / "vocabulary")
    parser.add_argument("--wave", default="semantic_tags_" + datetime.now(timezone.utc).strftime("%Y_%m"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--relations", default="about,both", help="comma-separated; empty string keeps all")
    parser.add_argument("--exclude-relations", default="", help="comma-separated relations to drop")
    parser.add_argument("--skip-noise", action="store_true", help="drop clusters whose noise_guess is true")
    parser.add_argument(
        "--source-order",
        default="",
        help="comma-separated source names; notices are tagged in that order, the rest last",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--review-threshold", type=float, default=DEFAULT_REVIEW_THRESHOLD)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="write prompts, call nothing")
    parser.add_argument("--dry-run-out", type=Path, help="where the prompts go (default: <output>.prompts.jsonl)")
    parser.add_argument("--print-schema", action="store_true", help="print the resolved schema and exit")
    parser.add_argument("--print-system-prompt", action="store_true")
    arguments = parser.parse_args(argv)

    vocab = load_vocabulary(arguments.vocabulary)
    schema = tag_record_schema(vocab)
    system = system_prompt(vocab)

    if arguments.print_schema:
        print(json.dumps(schema, ensure_ascii=False, indent=2))
        return 0
    if arguments.print_system_prompt:
        print(system)
        return 0
    if not arguments.input or not arguments.output:
        parser.error("--input and --output are required unless --print-schema/--print-system-prompt")

    rejects_path = arguments.rejects or arguments.output.with_suffix(".rejects.jsonl")
    stats_path = arguments.stats or arguments.output.with_suffix(".stats.json")
    relations = {r.strip() for r in arguments.relations.split(",") if r.strip()} or None
    run_id = arguments.run_id or f"{arguments.wave}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    excluded = {r.strip() for r in arguments.exclude_relations.split(",") if r.strip()} or None
    selector = dict(
        relations=relations, exclude_relations=excluded, skip_noise=arguments.skip_noise
    )
    notices = [n for n in read_notices(arguments.input, **selector) if not n.get("__malformed__")]
    malformed = sum(1 for _ in read_notices(arguments.input, **selector) if _.get("__malformed__"))

    order = [s.strip() for s in arguments.source_order.split(",") if s.strip()]
    if order:
        rank = {name: index for index, name in enumerate(order)}

        def priority(record: dict[str, Any]) -> tuple[int, str]:
            ranks = [rank[s] for s in record_sources(record) if s in rank]
            return (min(ranks) if ranks else len(order), notice_identifier(record))

        notices.sort(key=priority)

    if arguments.offset:
        notices = notices[arguments.offset :]
    if arguments.limit:
        notices = notices[: arguments.limit]

    # Une même entrée peut porter deux fois le même identifiant — c'était le cas
    # tant que `origenality_id` n'était pas une clé. Le tagueur soumettait alors
    # la notice deux fois et écrivait deux lignes sous le même identifiant. On
    # ne garde que la première occurrence, et on dit combien ont été écartées.
    unique_notices = []
    seen_input: set[str] = set()
    duplicate_inputs = 0
    for record in notices:
        identifier = notice_identifier(record)
        if identifier in seen_input:
            duplicate_inputs += 1
            continue
        seen_input.add(identifier)
        unique_notices.append(record)
    notices = unique_notices

    if arguments.no_resume:
        done: set[tuple[str, str]] = set()
        refused: set[tuple[str, str]] = set()
    else:
        done = already_tagged(arguments.output, arguments.wave,
                              PROMPT_VERSION, vocab.version_string)
        refused = already_rejected(rejects_path, arguments.wave,
                                   PROMPT_VERSION, vocab.version_string)
    keys = {notice_identifier(n): resume_key(n) for n in notices}
    pending = [n for n in notices
               if keys[notice_identifier(n)] not in done
               and keys[notice_identifier(n)] not in refused]
    current = set(keys.values())
    # Une notice déjà taguée dont la fiche a changé n'est pas « déjà faite » :
    # elle repart, et on le dit plutôt que de la compter dans les acquis.
    known = done | refused
    known_ids = {identifier for identifier, _ in known}
    stale = sum(1 for identifier, key in keys.items()
                if key not in known and identifier in known_ids)

    print(f"notices selected: {len(notices)} | already tagged in wave: {len(done & current)} "
          f"| already rejected in wave: {len(refused & current)} | to do: {len(pending)}")
    if stale:
        print(f"notices retagged because their input changed since the last run: {stale}")
    if duplicate_inputs:
        print(f"duplicate notice identifiers in the input, skipped: {duplicate_inputs}")
    if malformed:
        print(f"malformed input lines skipped: {malformed}")

    if arguments.dry_run:
        target = arguments.dry_run_out or arguments.output.with_suffix(".prompts.jsonl")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            for record in pending:
                payload = notice_payload(record)
                handle.write(
                    json.dumps(
                        {
                            "notice_id": notice_identifier(record),
                            "input_digest": payload_digest(payload),
                            "prompt_version": PROMPT_VERSION,
                            "vocabulary_version": vocab.version_string,
                            "system": system,
                            "user": user_prompt(payload),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        schema_path = target.with_name(target.stem + ".schema.json")
        schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
        approx = sum(len(system) + len(user_prompt(notice_payload(r))) for r in pending) // 4
        print(f"dry run: {len(pending)} prompts -> {target}")
        print(f"resolved schema -> {schema_path}")
        print(f"approximate prompt tokens if run: {approx:,} (about {approx // max(len(pending), 1):,} per notice)")
        return 0

    if not llm_adapter.is_configured():
        print("no endpoint configured: set ORIGENALITY_LLM_BASE_URL, ORIGENALITY_LLM_API_KEY, ORIGENALITY_LLM_MODEL")
        print("(or run with --dry-run)")
        return 2

    description = llm_adapter.describe()
    print(f"endpoint host: {description['endpoint_host']} | model: {description['model']} | structured: {description['structured_mode']}")

    writer = Writer(arguments.output)
    rejects = Writer(rejects_path)
    counters = Counters()
    started = time.time()
    now = datetime.now(timezone.utc).isoformat()

    def worker(record: dict[str, Any]) -> None:
        values, rejection, result = tag_one(record, vocab, schema, system, arguments.review_threshold)
        if result is not None:
            counters.prompt_tokens += result.usage.prompt_tokens
            counters.completion_tokens += result.usage.completion_tokens
            counters.latency_ms += result.latency_ms
        if rejection is not None:
            # Un refus n'est valable que pour la règle et la fiche qui l'ont
            # produit : sans ces trois champs, la reprise ne peut pas savoir
            # qu'il est périmé.
            rejection.update({"wave": arguments.wave, "run_id": run_id,
                              "rejected_at": now,
                              "prompt_version": PROMPT_VERSION,
                              "vocabulary_version": vocab.version_string})
            rejects.write(rejection)
            counters.rejected += 1
            return
        assert values is not None
        values.update(
            {
                "wave": arguments.wave,
                "run_id": run_id,
                "source_model": llm_adapter.model_id(),
                "auto_generated": True,
                "tagged_at": datetime.now(timezone.utc).isoformat(),
                "vocabulary_version": vocab.version_string,
                "prompt_version": PROMPT_VERSION,
            }
        )
        writer.write(values)
        counters.tagged += 1
        if values["needs_review"]:
            counters.needs_review += 1
        if values.get("repairs"):
            counters.repaired += 1
        if values.get("curated_scope"):
            counters.curated += 1
        if values.get("relevance_floor_applied"):
            counters.floor_applied += 1

    try:
        with futures.ThreadPoolExecutor(max_workers=max(1, arguments.concurrency)) as pool:
            submitted = {pool.submit(worker, record): resume_key(record) for record in pending}
            for index, future in enumerate(futures.as_completed(submitted), start=1):
                try:
                    future.result()
                except Exception as exc:  # a worker must never kill the run
                    rejects.write(
                        {
                            "notice_id": submitted[future][0],
                            "input_digest": submitted[future][1],
                            "stage": "worker",
                            "error": f"{type(exc).__name__}: {exc}"[:400],
                            "wave": arguments.wave,
                            "run_id": run_id,
                            "prompt_version": PROMPT_VERSION,
                            "vocabulary_version": vocab.version_string,
                        }
                    )
                    counters.rejected += 1
                if index % 25 == 0 or index == len(pending):
                    elapsed = time.time() - started
                    rate = index / elapsed if elapsed else 0
                    print(
                        f"[{index}/{len(pending)}] tagged={counters.tagged} rejected={counters.rejected} "
                        f"review={counters.needs_review} {rate:.2f}/s",
                        flush=True,
                    )
    except KeyboardInterrupt:
        print("interrupted; partial output kept, rerun to resume")
    finally:
        writer.close()
        rejects.close()

    # Fin de vague : le fichier de tags redevient « une ligne par notice ».
    # L'écriture en ajout est ce qui fait survivre un run à une interruption ;
    # elle laisse en revanche derrière elle des lignes que des reprises ont
    # périmées, et l'aval n'a pas à trancher entre elles. L'historique complet
    # part dans <output>.history.jsonl : rien n'est perdu, rien n'est ambigu.
    compaction = compact(arguments.output)
    if compaction.get("superseded"):
        print("compacted %(lines_in)d lines -> %(lines_out)d records "
              "(%(superseded)d superseded, kept in the history file)" % compaction)

    elapsed = time.time() - started
    report = {
        "wave": arguments.wave,
        "run_id": run_id,
        "input": str(arguments.input),
        "output": str(arguments.output),
        "rejects": str(rejects_path),
        "relations": sorted(relations) if relations else "all",
        "exclude_relations": sorted(excluded) if excluded else [],
        "skip_noise": bool(arguments.skip_noise),
        "source_order": order,
        "notices_selected": len(notices),
        "duplicate_input_ids_skipped": duplicate_inputs,
        "notices_attempted": len(pending),
        "tagged": counters.tagged,
        "rejected": counters.rejected,
        "needs_review": counters.needs_review,
        "records_repaired": counters.repaired,
        "curated_perimeter": counters.curated,
        "relevance_floor_applied": counters.floor_applied,
        "prompt_tokens": counters.prompt_tokens,
        "completion_tokens": counters.completion_tokens,
        "wall_seconds": round(elapsed, 1),
        "mean_latency_ms": round(counters.latency_ms / max(counters.tagged + counters.rejected, 1)),
        "concurrency": arguments.concurrency,
        "review_threshold": arguments.review_threshold,
        "prompt_version": PROMPT_VERSION,
        "vocabulary_version": vocab.version_string,
        "source_model": llm_adapter.model_id(),
        "compaction": compaction,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if counters.tagged else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
