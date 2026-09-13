#!/usr/bin/env python3
"""Build private JSON-LD and a rights-filtered public evidence projection."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from core import EvidenceError, load_documents, read_jsonl
from validate_evidence import CLAIMS, DOCUMENTS, ROOT, run


PRIVATE_GRAPH = ROOT / "data" / "evidence" / "private" / "knowledge-graph.jsonld"
PUBLIC_DATA = ROOT / "site" / "data" / "evidence.json"

CONTEXT = {
    "schema": "https://schema.org/",
    "prov": "http://www.w3.org/ns/prov#",
    "oa": "http://www.w3.org/ns/oa#",
    "cito": "http://purl.org/spar/cito/",
    "crminf": "http://www.cidoc-crm.org/crminf/",
    "lrmoo": "http://iflastandards.info/ns/lrm/lrmoo/",
    "norg": "https://origenality.com/ns/",
}


def public_quote(document: dict, evidence: dict) -> tuple[str | None, str]:
    rights = document["rights"]
    if not rights.get("public_quote_clearance"):
        return None, "withheld-unreviewed"
    policy = rights.get("public_quote_policy")
    if policy == "licensed-verbatim":
        return evidence.get("quote"), "licensed-verbatim"
    if policy == "short-quotation-only":
        excerpt = evidence.get("public_excerpt")
        return (excerpt, "short-quotation") if excerpt else (None, "withheld-no-cleared-excerpt")
    return None, "private-only"


def public_selector(selector: dict, include_quote: bool) -> dict:
    value = {
        "pdf_page": selector["pdf_page"],
        "printed_page": selector["printed_page"],
        "printed_page_confidence": selector["printed_page_confidence"],
        "page_text_sha256": selector["page_text_sha256"],
        "text_position_selector": selector["text_position_selector"],
    }
    if include_quote:
        value["text_quote_selector"] = selector["text_quote_selector"]
    return value


def private_jsonld(documents: dict[str, dict], claims: list[dict]) -> dict:
    graph: list[dict] = []
    for document in documents.values():
        graph.append({
            "@id": document["id"],
            "@type": ["schema:CreativeWork", "norg:ScholarlyDocument"],
            "schema:name": document["title"],
            "schema:author": document["authors"],
            "schema:datePublished": document["year"],
            "schema:identifier": document.get("doi") or document["bibliographic_record_ids"],
            "schema:url": document["source_url"],
            "norg:pdfSha256": document["pdf_sha256"],
            "norg:rights": document["rights"],
        })
    for claim in claims:
        graph.append({
            "@id": claim["id"],
            "@type": ["norg:ScholarPosition", "crminf:I4_Proposition_Set"],
            "schema:author": claim["scholar"],
            "norg:statement": claim["statement"],
            "norg:statementLanguage": claim["statement_language"],
            "norg:claimKind": claim["claim_kind"],
            "norg:beliefStatus": claim["belief_status"],
            "norg:scope": claim["scope"],
            "norg:authorVocabulary": claim["author_vocabulary"],
            "norg:about": claim["about"],
            "norg:relations": claim["relations"],
            "prov:wasDerivedFrom": {"@id": claim["document_id"]},
            "oa:hasBody": claim["evidence"],
            "norg:curation": claim["curation"],
        })
    return {"@context": CONTEXT, "generated": date.today().isoformat(), "@graph": graph}


def on_the_map(document: dict) -> bool:
    """A document whose record link is unresolved stays in the private registry."""
    return (document.get("map_resolution") or {}).get("status") != "unresolved"


def public_projection(documents: dict[str, dict], claims: list[dict]) -> dict:
    withheld = sorted(identifier for identifier, document in documents.items()
                      if not on_the_map(document))
    documents = {identifier: document for identifier, document in documents.items()
                 if on_the_map(document)}
    claims = [claim for claim in claims if claim["document_id"] in documents]
    public_documents = {}
    for identifier, document in documents.items():
        rights = document["rights"]
        public_documents[identifier] = {
            "id": identifier,
            "title": document["title"],
            "authors": document["authors"],
            "year": document["year"],
            "doi": document.get("doi"),
            "bibliographic_record_ids": document["bibliographic_record_ids"],
            "source_url": document["source_url"],
            "license": rights.get("license"),
            "license_url": rights.get("license_url"),
            "public_quote_policy": rights.get("public_quote_policy"),
        }

    public_claims = []
    for claim in claims:
        document = documents[claim["document_id"]]
        evidence_rows = []
        for evidence in claim["evidence"]:
            quote, release = public_quote(document, evidence)
            evidence_rows.append({
                "id": evidence["id"],
                "quote": quote,
                "quote_release": release,
                "language": evidence["language"],
                "selectors": [public_selector(selector, include_quote=quote is not None)
                              for selector in evidence["selectors"]],
            })
        public_claims.append({
            "id": claim["id"],
            "type": claim["type"],
            "document_id": claim["document_id"],
            "bibliographic_record_ids": claim["bibliographic_record_ids"],
            "scholar": claim["scholar"],
            "statement": claim["statement"],
            "statement_language": claim["statement_language"],
            "claim_kind": claim["claim_kind"],
            "belief_status": claim["belief_status"],
            "scope": claim["scope"],
            "author_vocabulary": claim["author_vocabulary"],
            "about": claim["about"],
            "relations": claim["relations"],
            "evidence": evidence_rows,
            "human_reviewed": claim["curation"]["human_reviewed"],
            "needs_review": claim["curation"]["needs_review"],
        })
    return {
        "schema_version": "evidence-1.0.0",
        "generated": date.today().isoformat(),
        "documents": public_documents,
        "claims": public_claims,
        "policy": {
            "long_quotes_private_by_default": True,
            "statement": ("A public quote is emitted only after an explicit rights clearance; "
                          "the private graph retains the complete source-anchored evidence."),
        },
    }


def dump(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=Path, default=DOCUMENTS)
    parser.add_argument("--claims", type=Path, default=CLAIMS)
    parser.add_argument("--private-out", type=Path, default=PRIVATE_GRAPH)
    parser.add_argument("--public-out", type=Path, default=PUBLIC_DATA)
    args = parser.parse_args(argv)
    problems, summary = run(args.documents, args.claims, check_pdf=True)
    if problems:
        for problem in problems:
            print(f"ERROR {problem}", file=sys.stderr)
        raise EvidenceError(f"evidence validation failed with {len(problems)} problem(s)")
    documents = load_documents(args.documents)
    claims = list(read_jsonl(args.claims))
    dump(args.private_out, private_jsonld(documents, claims))
    dump(args.public_out, public_projection(documents, claims))
    print(json.dumps({**summary,
                      "private_graph": str(args.private_out.relative_to(ROOT)),
                      "public_projection": str(args.public_out.relative_to(ROOT))}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvidenceError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        raise SystemExit(2)
