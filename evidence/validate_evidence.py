#!/usr/bin/env python3
"""Validate source integrity, locators, rights gates, and claim evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core import (EvidenceError, HEX_64, canonical_text, file_sha256, load_documents,
                  load_pages, read_jsonl, validate_selector)


ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS = ROOT / "data" / "evidence" / "curated" / "documents.jsonl"
CLAIMS = ROOT / "data" / "evidence" / "curated" / "claims.jsonl"
GRAPH = next((path for path in (ROOT / "site" / "data" / "graph.json", ROOT / "data" / "graph.json")
              if path.is_file()), ROOT / "site" / "data" / "graph.json")


def map_record_keys(graph: dict) -> set[str]:
    """Every identifier a map record answers to: cluster key and `source:id` pairs."""
    keys: set[str] = set()
    for node in graph.get("nodes") or []:
        if node.get("k") != "pub":
            continue
        if node.get("ppn"):
            keys.add(str(node["ppn"]))
        for entry in node.get("source_ids") or []:
            if entry.get("source") and entry.get("id") is not None:
                keys.add(f"{entry['source']}:{entry['id']}")
    return keys


def validate_map_resolution(document: dict, keys: set[str]) -> list[str]:
    """A document either points at records on the map, or says why it cannot.

    The identifiers were typed at ingest and nothing compared them with the map:
    six of seven claims pointed at DOIs no map record carries (OR-50). A document
    marked `resolved` must name only keys the map holds; a document marked
    `unresolved` must give its reason, and stays out of the public projection.
    """
    identifier = document.get("id", "(unknown)")
    resolution = document.get("map_resolution") or {}
    status = resolution.get("status")
    record_ids = document.get("bibliographic_record_ids") or []
    if status == "unresolved":
        if not resolution.get("reason"):
            return [f"{identifier}: an unresolved record link needs a reason"]
        return []
    if status != "resolved":
        return [f"{identifier}: map_resolution.status must be resolved or unresolved"]
    if not record_ids:
        return [f"{identifier}: a resolved document names no map record"]
    missing = [value for value in record_ids if value not in keys]
    return [f"{identifier}: record {value} is not on the map" for value in missing]


def validate_document(document: dict, check_pdf: bool = True) -> list[str]:
    problems: list[str] = []
    identifier = document.get("id", "(unknown)")
    digest = document.get("pdf_sha256")
    if not isinstance(digest, str) or not HEX_64.fullmatch(digest):
        problems.append(f"{identifier}: invalid PDF digest")
    quality = document.get("extraction", {}).get("quality", {})
    if quality.get("quotable_pages", 0) + quality.get("pages_needing_text_review", 0) \
            != quality.get("pages"):
        problems.append(f"{identifier}: page-level quality counts do not cover the PDF")
    rights = document.get("rights") or {}
    required_rights = {
        "lawful_access_basis", "license", "license_url", "rights_holder", "tdm_basis",
        "tdm_opt_out", "retention_rule", "commercial_use", "adaptation_allowed",
        "third_party_exclusions", "public_quote_policy", "public_quote_clearance",
        "review_status",
    }
    missing = required_rights - set(rights)
    if missing:
        problems.append(f"{identifier}: missing rights fields {sorted(missing)}")
    if rights.get("public_quote_clearance") and rights.get("review_status") == "unreviewed":
        problems.append(f"{identifier}: public quote clearance cannot be unreviewed")
    if rights.get("public_quote_policy") == "licensed-verbatim" and not rights.get("license_url"):
        problems.append(f"{identifier}: licensed verbatim publication needs a license URL")

    private_path = document.get("private_pdf_path")
    if check_pdf and isinstance(private_path, str):
        pdf = (ROOT / private_path).resolve()
        private_root = (ROOT / "data" / "evidence" / "private").resolve()
        if private_root not in pdf.parents or not pdf.is_file():
            problems.append(f"{identifier}: private PDF is missing or outside the private root")
        elif file_sha256(pdf) != digest:
            problems.append(f"{identifier}: private PDF digest changed")
    return problems


def validate_claim(claim: dict, documents: dict[str, dict], pages_cache: dict) -> list[str]:
    problems: list[str] = []
    identifier = claim.get("id", "(unknown claim)")
    document_id = claim.get("document_id")
    document = documents.get(document_id)
    if document is None:
        return [f"{identifier}: unknown source document {document_id}"]
    if claim.get("bibliographic_record_ids") != document.get("bibliographic_record_ids"):
        problems.append(f"{identifier}: bibliographic IDs diverge from the source document")
    if claim.get("type") != "ScholarPosition":
        problems.append(f"{identifier}: type must be ScholarPosition")
    if not claim.get("statement") or len(claim["statement"].strip()) < 20:
        problems.append(f"{identifier}: claim statement is too thin")
    vocabulary = claim.get("author_vocabulary") or []
    if not vocabulary:
        problems.append(f"{identifier}: author_vocabulary is empty")
    evidence = claim.get("evidence") or []
    if not evidence:
        problems.append(f"{identifier}: a claim without evidence cannot enter the graph")
        return problems

    if document_id not in pages_cache:
        pages_cache[document_id] = load_pages(ROOT, document)
    pages = pages_cache[document_id]
    evidence_text = " ".join(item.get("quote", "") for item in evidence)
    folded = canonical_text(evidence_text).casefold()
    for term in vocabulary:
        if canonical_text(term).casefold() not in folded:
            problems.append(f"{identifier}: author term {term!r} is absent from its evidence")

    evidence_ids: set[str] = set()
    for item in evidence:
        evidence_id = item.get("id")
        if not isinstance(evidence_id, str) or evidence_id in evidence_ids:
            problems.append(f"{identifier}: missing or duplicate evidence ID {evidence_id!r}")
        evidence_ids.add(evidence_id)
        quote = canonical_text(item.get("quote", ""))
        selectors = item.get("selectors") or []
        selected_parts: list[str] = []
        for selector in selectors:
            page_number = selector.get("pdf_page")
            page = pages.get(page_number)
            if page is None:
                problems.append(f"{identifier}: source has no physical page {page_number}")
                continue
            if not page.get("quotable"):
                problems.append(f"{identifier}: physical page {page_number} needs text review")
            problems.extend(validate_selector(document_id, selector, page))
            exact = (selector.get("text_quote_selector") or {}).get("exact")
            if isinstance(exact, str):
                selected_parts.append(exact)
        if canonical_text(" ".join(selected_parts)) != quote:
            problems.append(f"{identifier}/{evidence_id}: quote differs from selector exact text")
        excerpt = item.get("public_excerpt")
        if excerpt is not None and canonical_text(excerpt) not in quote:
            problems.append(f"{identifier}/{evidence_id}: public excerpt is not part of the quote")

    curation = claim.get("curation") or {}
    if curation.get("status") == "human-verified" and not curation.get("human_reviewed"):
        problems.append(f"{identifier}: human-verified status without human review")
    return problems


def run(documents_path: Path = DOCUMENTS, claims_path: Path = CLAIMS,
        check_pdf: bool = True, graph_path: Path | None = GRAPH) -> tuple[list[str], dict]:
    documents = load_documents(documents_path)
    claims = list(read_jsonl(claims_path)) if claims_path.exists() else []
    problems: list[str] = []
    keys = (map_record_keys(json.loads(graph_path.read_text(encoding="utf-8")))
            if graph_path is not None and graph_path.is_file() else None)
    for document in documents.values():
        problems.extend(validate_document(document, check_pdf=check_pdf))
        if keys is not None:
            problems.extend(validate_map_resolution(document, keys))
    claim_ids: set[str] = set()
    pages_cache: dict = {}
    for claim in claims:
        identifier = claim.get("id")
        if not isinstance(identifier, str) or identifier in claim_ids:
            problems.append(f"duplicate or missing claim ID {identifier!r}")
        claim_ids.add(identifier)
        problems.extend(validate_claim(claim, documents, pages_cache))
    summary = {
        "documents": len(documents),
        "claims": len(claims),
        "evidence_spans": sum(len(claim.get("evidence") or []) for claim in claims),
        "problems": len(problems),
    }
    return problems, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=Path, default=DOCUMENTS)
    parser.add_argument("--claims", type=Path, default=CLAIMS)
    parser.add_argument("--skip-pdf-digest", action="store_true")
    args = parser.parse_args(argv)
    problems, summary = run(args.documents, args.claims, check_pdf=not args.skip_pdf_digest)
    print(json.dumps(summary, indent=2))
    for problem in problems:
        print(f"ERROR {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvidenceError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        raise SystemExit(2)
