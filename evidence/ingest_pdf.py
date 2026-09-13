#!/usr/bin/env python3
"""Ingest one scholarly PDF into the private, page-aware evidence store.

The command copies the PDF under a content-derived name, extracts every page
with Poppler, records a visible-folio map supplied by the curator, and appends a
document manifest.  It never guesses printed pagination and never promotes an
image-only extraction to quotable evidence.
"""
from __future__ import annotations

import argparse
import collections
import json
import shutil
import statistics
import subprocess
import sys
from datetime import date
from pathlib import Path

from core import EvidenceError, canonical_text, file_sha256, read_jsonl, sha256_text, write_jsonl


ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / "data" / "evidence" / "private"
DOCUMENTS = ROOT / "data" / "evidence" / "curated" / "documents.jsonl"


def command(*args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, check=True, text=True, capture_output=True)
    except FileNotFoundError as exc:
        raise EvidenceError(f"required command is missing: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise EvidenceError(f"{' '.join(args)} failed: {detail}") from exc


def pdf_page_count(path: Path) -> int:
    output = command("pdfinfo", str(path)).stdout
    for line in output.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise EvidenceError("pdfinfo returned no page count")


def extractor_version() -> str:
    result = command("pdftotext", "-v")
    text = (result.stderr or result.stdout).splitlines()
    return text[0].strip() if text else "pdftotext"


def load_page_map(path: Path | None, page_count: int) -> dict[int, dict]:
    if path is None:
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise EvidenceError("page map must be a JSON array of contiguous ranges")
    mapped: dict[int, dict] = {}
    for index, segment in enumerate(value, 1):
        if not isinstance(segment, dict):
            raise EvidenceError(f"page-map segment {index} is not an object")
        start, end = segment.get("pdf_start"), segment.get("pdf_end")
        printed = segment.get("printed_start")
        confidence = segment.get("confidence")
        method = segment.get("method")
        if not all(isinstance(item, int) for item in (start, end, printed)):
            raise EvidenceError(f"page-map segment {index} needs integer starts and end")
        if start < 1 or end < start or end > page_count:
            raise EvidenceError(f"page-map segment {index} leaves the PDF page range")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise EvidenceError(f"page-map segment {index} has invalid confidence")
        if not isinstance(method, str) or not method:
            raise EvidenceError(f"page-map segment {index} needs an explicit method")
        for physical in range(start, end + 1):
            if physical in mapped:
                raise EvidenceError(f"physical page {physical} is mapped twice")
            mapped[physical] = {
                "printed_page": str(printed + physical - start),
                "printed_page_confidence": float(confidence),
                "printed_page_method": method,
            }
    return mapped


def extract_pages(pdf: Path, page_count: int, page_map: dict[int, dict]) -> tuple[list[dict], dict]:
    output = command("pdftotext", "-layout", "-enc", "UTF-8", str(pdf), "-").stdout
    secondary = command("mutool", "draw", "-F", "txt", "-o", "-", str(pdf)).stdout
    secondary_chunks = secondary.split("\f")
    if secondary_chunks and not secondary_chunks[-1].strip():
        secondary_chunks.pop()
    if len(secondary_chunks) != page_count:
        raise EvidenceError(
            f"mutool returned {len(secondary_chunks)} page chunks for a {page_count}-page PDF"
        )
    chunks = output.split("\f")
    if chunks and not chunks[-1].strip():
        chunks.pop()
    if len(chunks) != page_count:
        raise EvidenceError(
            f"pdftotext returned {len(chunks)} page chunks for a {page_count}-page PDF"
        )
    records: list[dict] = []
    lengths: list[int] = []
    suspicious: collections.Counter[str] = collections.Counter()
    for physical, raw in enumerate(chunks, 1):
        canonical = canonical_text(raw)
        page_suspicious = collections.Counter(
            char for char in canonical
            if 0x80 <= ord(char) <= 0x9F or 0x250 <= ord(char) <= 0x2FF)
        suspicious.update(page_suspicious)
        secondary_replacements = secondary_chunks[physical - 1].count("\ufffd")
        page_status = ("needs-text-review"
                       if sum(page_suspicious.values()) > 5 or secondary_replacements
                       else "native-text")
        lengths.append(len(canonical))
        locator = page_map.get(physical, {})
        records.append({
            "pdf_page": physical,
            "printed_page": locator.get("printed_page"),
            "printed_page_confidence": locator.get("printed_page_confidence", 0.0),
            "printed_page_method": locator.get("printed_page_method"),
            "raw_text": raw,
            "canonical_text": canonical,
            "canonical_text_sha256": sha256_text(canonical),
            "characters": len(canonical),
            "quality_status": page_status,
            "suspicious_glyphs": sum(page_suspicious.values()),
            "secondary_extractor_replacement_glyphs": secondary_replacements,
            "quotable": page_status == "native-text",
        })
    nonempty = sum(length >= 80 for length in lengths)
    median = statistics.median(lengths) if lengths else 0
    ratio = nonempty / max(1, page_count)
    suspicious_total = sum(suspicious.values())
    replacement_glyphs = sum(chunk.count("\ufffd") for chunk in secondary_chunks)
    quotable_pages = sum(record["quotable"] for record in records)
    review_pages = page_count - quotable_pages
    if ratio < 0.8 or median < 200:
        status = "needs-ocr-review"
    elif review_pages:
        status = "mixed-text-review"
    else:
        status = "native-text"
    quality = {
        "status": status,
        "pages": page_count,
        "pages_with_at_least_80_characters": nonempty,
        "nonempty_ratio": round(ratio, 4),
        "median_characters": int(median),
        "suspicious_glyphs": suspicious_total,
        "suspicious_glyph_examples": [
            {"character": char, "count": count, "codepoint": f"U+{ord(char):04X}"}
            for char, count in suspicious.most_common(12)
        ],
        "secondary_extractor": "mutool-draw-text",
        "secondary_extractor_replacement_glyphs": replacement_glyphs,
        "quotable_pages": quotable_pages,
        "pages_needing_text_review": review_pages,
        "quotable": status != "needs-ocr-review" and quotable_pages > 0,
    }
    return records, quality


def existing_documents() -> list[dict]:
    return list(read_jsonl(DOCUMENTS)) if DOCUMENTS.exists() else []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", action="append", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--record-id", action="append", default=[])
    parser.add_argument("--doi")
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--access",
                        choices=("open-access", "institutional-access", "owned-copy", "permission"),
                        required=True)
    parser.add_argument("--license", default="all-rights-reserved")
    parser.add_argument("--license-url")
    parser.add_argument("--rights-holder")
    parser.add_argument("--tdm-basis",
                        choices=("open-license", "research-organisation", "general-tdm",
                                 "permission", "none"), required=True)
    parser.add_argument("--tdm-opt-out",
                        choices=("not-found", "present", "not-applicable", "unchecked"),
                        required=True)
    parser.add_argument("--retention-rule", required=True)
    parser.add_argument("--commercial-use", action="store_true")
    parser.add_argument("--adaptation-allowed", action="store_true")
    parser.add_argument("--third-party-exclusion", action="append", default=[])
    parser.add_argument("--public-quote-policy",
                        choices=("licensed-verbatim", "short-quotation-only", "private-only"),
                        required=True)
    parser.add_argument("--public-quote-clearance", action="store_true",
                        help="explicitly clear the declared public quote policy")
    parser.add_argument("--rights-review-status",
                        choices=("unreviewed", "license-verified", "permission-verified"),
                        default="unreviewed")
    parser.add_argument("--rights-review-note")
    parser.add_argument("--page-map", type=Path,
                        help="JSON ranges verified from visible printed folios")
    parser.add_argument("--replace", action="store_true",
                        help="replace the manifest row for the same content digest")
    args = parser.parse_args(argv)

    pdf = args.pdf.expanduser().resolve()
    if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
        raise EvidenceError(f"not a readable PDF: {pdf}")
    digest = file_sha256(pdf)
    document_id = f"doc:{digest[:20]}"
    count = pdf_page_count(pdf)
    mapping = load_page_map(args.page_map, count)
    pages, quality = extract_pages(pdf, count, mapping)

    pdf_rel = Path("data") / "evidence" / "private" / "pdfs" / f"{document_id[4:]}.pdf"
    pages_rel = (Path("data") / "evidence" / "private" / "extracted" /
                 document_id[4:] / "pages.jsonl")
    pdf_target = ROOT / pdf_rel
    pages_target = ROOT / pages_rel
    pdf_target.parent.mkdir(parents=True, exist_ok=True)
    if not pdf_target.exists():
        shutil.copy2(pdf, pdf_target)
    elif file_sha256(pdf_target) != digest:
        raise EvidenceError(f"content-addressed PDF collision at {pdf_target}")
    write_jsonl(pages_target, pages)

    document = {
        "id": document_id,
        "type": "ScholarlyDocument",
        "title": args.title,
        "authors": args.author,
        "year": args.year,
        "doi": args.doi,
        "bibliographic_record_ids": sorted(set(args.record_id)),
        "source_url": args.source_url,
        "pdf_sha256": digest,
        "pdf_bytes": pdf.stat().st_size,
        "pdf_pages": count,
        "private_pdf_path": pdf_rel.as_posix(),
        "extraction": {
            "method": "pdftotext-layout-page-preserving",
            "tool": extractor_version(),
            "extracted_on": date.today().isoformat(),
            "pages_path": pages_rel.as_posix(),
            "quality": quality,
        },
        "rights": {
            "lawful_access_basis": args.access,
            "license": args.license,
            "license_url": args.license_url,
            "rights_holder": args.rights_holder,
            "tdm_basis": args.tdm_basis,
            "tdm_opt_out": args.tdm_opt_out,
            "retention_rule": args.retention_rule,
            "commercial_use": args.commercial_use,
            "adaptation_allowed": args.adaptation_allowed,
            "third_party_exclusions": args.third_party_exclusion,
            "public_quote_policy": args.public_quote_policy,
            "public_quote_clearance": args.public_quote_clearance,
            "review_status": args.rights_review_status,
            "reviewed_on": (date.today().isoformat()
                            if args.rights_review_status != "unreviewed" else None),
            "review_note": args.rights_review_note,
        },
    }
    documents = existing_documents()
    same = [index for index, item in enumerate(documents) if item.get("id") == document_id]
    if same and not args.replace:
        raise EvidenceError(f"{document_id} is already registered; pass --replace to refresh it")
    if same:
        documents[same[0]] = document
    else:
        documents.append(document)
    write_jsonl(DOCUMENTS, documents)
    print(json.dumps({
        "document_id": document_id,
        "pdf_sha256": digest,
        "pages": count,
        "mapped_printed_pages": len(mapping),
        "quality": quality,
        "manifest": str(DOCUMENTS.relative_to(ROOT)),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvidenceError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        raise SystemExit(2)
