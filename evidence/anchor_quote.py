#!/usr/bin/env python3
"""Resolve a curator-supplied quote against one extracted PDF page.

The output is an evidence object ready to place in a claim record.  A quote
that is absent or ambiguous is refused; the curator must select an occurrence
explicitly rather than trusting a fuzzy match.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core import EvidenceError, anchor, load_documents, load_pages, sha256_text


ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS = ROOT / "data" / "evidence" / "curated" / "documents.jsonl"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--pdf-page", type=int, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--quote")
    group.add_argument("--quote-file", type=Path)
    parser.add_argument("--language", required=True)
    parser.add_argument("--occurrence", type=int, default=1)
    parser.add_argument("--public-excerpt")
    args = parser.parse_args(argv)

    documents = load_documents(DOCUMENTS)
    document = documents.get(args.document_id)
    if document is None:
        raise EvidenceError(f"unknown document {args.document_id}")
    pages = load_pages(ROOT, document)
    page = pages.get(args.pdf_page)
    if page is None:
        raise EvidenceError(f"{args.document_id}: no extracted page {args.pdf_page}")
    quote = (args.quote_file.read_text(encoding="utf-8")
             if args.quote_file is not None else args.quote)
    selector = anchor(page, quote, occurrence=args.occurrence)
    exact = selector["text_quote_selector"]["exact"]
    public_excerpt = args.public_excerpt
    if public_excerpt is not None and public_excerpt not in exact:
        raise EvidenceError("public excerpt is not an exact substring of the anchored quote")
    payload = {
        "id": f"evidence:{sha256_text(args.document_id + exact)[:20]}",
        "quote": exact,
        "language": args.language,
        "public_excerpt": public_excerpt,
        "selectors": [selector],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvidenceError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        raise SystemExit(2)

