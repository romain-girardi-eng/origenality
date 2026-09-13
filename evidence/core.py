#!/usr/bin/env python3
"""Shared primitives for Origenality's full-text evidence layer.

The bibliographic graph says that a work exists.  This module supports the
separate, stricter layer that says what a scholar argues and where the source
supports that representation.  Every quote is anchored to a content-addressed
PDF page by both a text-position selector and a text-quote selector.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Iterator


HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class EvidenceError(ValueError):
    """A fail-closed evidence or provenance error."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_text(text: str) -> str:
    """Stable selector text derived from a PDF page.

    Layout extraction inserts line breaks and discretionary hyphens.  Selectors
    operate on NFC text with line-end word breaks repaired and whitespace
    collapsed.  The raw extraction remains beside it in the private page file.
    """
    text = unicodedata.normalize("NFC", text).replace("\u00ad", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?<=\w)-\n\s*(?=\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def read_jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvidenceError(f"{path}:{number}: malformed JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise EvidenceError(f"{path}:{number}: a JSONL row must be an object")
            yield value


def write_jsonl(path: Path, records: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def load_documents(path: Path) -> dict[str, dict]:
    documents: dict[str, dict] = {}
    for record in read_jsonl(path):
        identifier = record.get("id")
        if not isinstance(identifier, str) or not identifier.startswith("doc:"):
            raise EvidenceError(f"{path}: document without a stable doc: identifier")
        if identifier in documents:
            raise EvidenceError(f"{path}: duplicate document {identifier}")
        documents[identifier] = record
    return documents


def load_pages(root: Path, document: dict) -> dict[int, dict]:
    relative = document.get("extraction", {}).get("pages_path")
    if not isinstance(relative, str) or not relative:
        raise EvidenceError(f"{document.get('id')}: missing extraction.pages_path")
    path = (root / relative).resolve()
    private_root = (root / "data" / "evidence" / "private").resolve()
    if private_root not in path.parents:
        raise EvidenceError(f"{document.get('id')}: pages_path leaves the private evidence root")
    pages: dict[int, dict] = {}
    for record in read_jsonl(path):
        page = record.get("pdf_page")
        if not isinstance(page, int) or page < 1:
            raise EvidenceError(f"{path}: invalid pdf_page {page!r}")
        if page in pages:
            raise EvidenceError(f"{path}: duplicate physical page {page}")
        pages[page] = record
    return pages


def anchor(page: dict, quote: str, occurrence: int = 1, context: int = 48) -> dict:
    """Return W3C-style quote and position selectors for an exact page span."""
    exact = canonical_text(quote)
    if not exact:
        raise EvidenceError("an empty quote cannot be anchored")
    page_text = page.get("canonical_text")
    if not isinstance(page_text, str):
        raise EvidenceError("page has no canonical_text")
    starts = [match.start() for match in re.finditer(re.escape(exact), page_text)]
    if occurrence < 1 or occurrence > len(starts):
        raise EvidenceError(
            f"quote occurrence {occurrence} does not resolve; found {len(starts)} exact match(es)"
        )
    start = starts[occurrence - 1]
    end = start + len(exact)
    return {
        "pdf_page": page["pdf_page"],
        "printed_page": page.get("printed_page"),
        "printed_page_confidence": page.get("printed_page_confidence", 0.0),
        "page_text_sha256": page.get("canonical_text_sha256"),
        "text_quote_selector": {
            "type": "TextQuoteSelector",
            "exact": exact,
            "prefix": page_text[max(0, start - context):start],
            "suffix": page_text[end:end + context],
        },
        "text_position_selector": {
            "type": "TextPositionSelector",
            "start": start,
            "end": end,
        },
    }


def validate_selector(document_id: str, selector: dict, page: dict) -> list[str]:
    problems: list[str] = []
    page_number = selector.get("pdf_page")
    if page_number != page.get("pdf_page"):
        problems.append(f"{document_id}: selector/page physical index mismatch")
    if selector.get("printed_page") != page.get("printed_page"):
        problems.append(f"{document_id} p{page_number}: printed-page locator mismatch")
    confidence = selector.get("printed_page_confidence")
    if not isinstance(confidence, (int, float)) or confidence < 0.9:
        problems.append(f"{document_id} p{page_number}: printed-page confidence below 0.90")
    expected_page_hash = page.get("canonical_text_sha256")
    if selector.get("page_text_sha256") != expected_page_hash:
        problems.append(f"{document_id} p{page_number}: page hash mismatch")

    quote_selector = selector.get("text_quote_selector") or {}
    position_selector = selector.get("text_position_selector") or {}
    exact = quote_selector.get("exact")
    start, end = position_selector.get("start"), position_selector.get("end")
    text = page.get("canonical_text", "")
    if not isinstance(exact, str) or not exact:
        problems.append(f"{document_id} p{page_number}: empty TextQuoteSelector")
    elif not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start:
        problems.append(f"{document_id} p{page_number}: invalid TextPositionSelector")
    elif text[start:end] != exact:
        problems.append(f"{document_id} p{page_number}: quote does not resolve at the stored position")
    else:
        prefix = quote_selector.get("prefix", "")
        suffix = quote_selector.get("suffix", "")
        if prefix and text[max(0, start - len(prefix)):start] != prefix:
            problems.append(f"{document_id} p{page_number}: quote prefix mismatch")
        if suffix and text[end:end + len(suffix)] != suffix:
            problems.append(f"{document_id} p{page_number}: quote suffix mismatch")
    return problems

