#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evidence"))

from build_evidence import public_projection, public_quote  # noqa: E402
from core import EvidenceError, anchor, canonical_text, sha256_text, validate_selector  # noqa: E402
from validate_evidence import (GRAPH, map_record_keys, validate_document,  # noqa: E402
                               validate_map_resolution)


def page(text: str) -> dict:
    canonical = canonical_text(text)
    return {
        "pdf_page": 7,
        "printed_page": "91",
        "printed_page_confidence": 0.99,
        "canonical_text": canonical,
        "canonical_text_sha256": sha256_text(canonical),
    }


def document(policy="private-only", clearance=False, review="unreviewed") -> dict:
    return {
        "id": "doc:" + "a" * 20,
        "type": "ScholarlyDocument",
        "title": "A source",
        "authors": ["A. Scholar"],
        "year": 2020,
        "doi": "10.0000/example",
        "bibliographic_record_ids": ["ixtheo:1"],
        "source_url": "https://example.org/source",
        "pdf_sha256": "b" * 64,
        "pdf_bytes": 10,
        "pdf_pages": 1,
        "private_pdf_path": "data/evidence/private/pdfs/" + "a" * 20 + ".pdf",
        "extraction": {
            "method": "pdftotext-layout-page-preserving",
            "tool": "test",
            "extracted_on": "2026-08-24",
            "pages_path": "data/evidence/private/extracted/" + "a" * 20 + "/pages.jsonl",
            "quality": {"status": "native-text", "pages": 1,
                        "pages_with_at_least_80_characters": 1, "nonempty_ratio": 1.0,
                        "median_characters": 100, "suspicious_glyphs": 0,
                        "suspicious_glyph_examples": [], "secondary_extractor": "mutool-draw-text",
                        "secondary_extractor_replacement_glyphs": 0,
                        "quotable_pages": 1, "pages_needing_text_review": 0,
                        "quotable": True},
        },
        "rights": {
            "lawful_access_basis": "owned-copy",
            "license": "all-rights-reserved",
            "license_url": None,
            "rights_holder": None,
            "tdm_basis": "research-organisation",
            "tdm_opt_out": "unchecked",
            "retention_rule": "Retain for source verification.",
            "commercial_use": False,
            "adaptation_allowed": False,
            "third_party_exclusions": [],
            "public_quote_policy": policy,
            "public_quote_clearance": clearance,
            "review_status": review,
            "reviewed_on": None,
            "review_note": None,
        },
    }


def evidence(exact="A scholar makes one bounded claim in this sentence.") -> dict:
    return {
        "id": "evidence:example",
        "quote": exact,
        "language": "en",
        "public_excerpt": "one bounded claim",
        "selectors": [],
    }


def claim(item: dict) -> dict:
    return {
        "id": "claim:example",
        "type": "ScholarPosition",
        "document_id": "doc:" + "a" * 20,
        "bibliographic_record_ids": ["ixtheo:1"],
        "scholar": {"name": "A. Scholar", "orcid": None},
        "statement": "The scholar makes one bounded claim in the selected passage.",
        "statement_language": "en",
        "claim_kind": "interpretation",
        "belief_status": "asserted",
        "scope": "one argument",
        "author_vocabulary": ["bounded claim"],
        "about": [{"kind": "theme", "id": "example"}],
        "relations": [],
        "evidence": [item],
        "curation": {"status": "source-anchored", "anchored_on": "2026-08-24",
                     "human_reviewed": False, "needs_review": True, "review_note": None},
    }


class SelectorTest(unittest.TestCase):

    def test_anchor_resolves_by_quote_and_position(self):
        source = page("Before. A scholar makes one bounded claim in this sentence. After.")
        selector = anchor(source, "A scholar makes one bounded claim in this sentence.")
        self.assertEqual(validate_selector("doc:test", selector, source), [])
        self.assertEqual(selector["printed_page"], "91")

    def test_ambiguous_occurrence_is_explicit(self):
        source = page("same words; same words")
        first = anchor(source, "same words", occurrence=1)
        second = anchor(source, "same words", occurrence=2)
        self.assertNotEqual(first["text_position_selector"], second["text_position_selector"])
        with self.assertRaises(EvidenceError):
            anchor(source, "same words", occurrence=3)

    def test_tampered_quote_fails(self):
        source = page("An exact statement in its source page.")
        selector = anchor(source, "An exact statement in its source page.")
        selector["text_quote_selector"]["exact"] = "A changed statement"
        self.assertTrue(validate_selector("doc:test", selector, source))


class RightsGateTest(unittest.TestCase):

    def test_unreviewed_source_never_publishes_a_quote(self):
        quote, status = public_quote(document(), evidence())
        self.assertIsNone(quote)
        self.assertEqual(status, "withheld-unreviewed")

    def test_short_quote_needs_a_curated_excerpt(self):
        doc = document("short-quotation-only", True, "license-verified")
        item = evidence()
        self.assertEqual(public_quote(doc, item), ("one bounded claim", "short-quotation"))
        item["public_excerpt"] = None
        self.assertEqual(public_quote(doc, item), (None, "withheld-no-cleared-excerpt"))

    def test_explicit_open_license_can_release_the_anchored_quote(self):
        doc = document("licensed-verbatim", True, "license-verified")
        doc["rights"]["license_url"] = "https://creativecommons.org/licenses/by/4.0/"
        exact = evidence()["quote"]
        self.assertEqual(public_quote(doc, evidence()), (exact, "licensed-verbatim"))

    def test_clearance_without_review_is_invalid(self):
        problems = validate_document(document("short-quotation-only", True, "unreviewed"),
                                     check_pdf=False)
        self.assertTrue(any("cannot be unreviewed" in problem for problem in problems))

    def test_public_projection_never_leaks_private_paths(self):
        doc = document()
        value = public_projection({doc["id"]: doc}, [claim(evidence())])
        payload = json.dumps(value)
        self.assertNotIn("private_pdf_path", payload)
        self.assertNotIn("raw_text", payload)
        self.assertIsNone(value["claims"][0]["evidence"][0]["quote"])


class SchemaTest(unittest.TestCase):

    def test_schemas_are_valid_json_and_closed(self):
        for path in sorted((ROOT / "evidence" / "schemas").glob("*.json")):
            value = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(value["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertFalse(value["additionalProperties"])


class MapResolutionTest(unittest.TestCase):
    """OR-50: a document names records on the map, or says why it cannot."""

    def resolved(self, record_id):
        doc = document()
        doc["bibliographic_record_ids"] = [record_id]
        doc["map_resolution"] = {"status": "resolved", "checked_on": "2026-09-13",
                                 "basis": "DOI identical to the catalogue record"}
        return doc

    def test_a_resolved_document_must_name_records_on_the_map(self):
        self.assertEqual(validate_map_resolution(self.resolved("ixtheo-k10plus:1"),
                                                 {"ixtheo-k10plus:1"}), [])
        self.assertTrue(validate_map_resolution(self.resolved("ixtheo:1"), {"ixtheo-k10plus:1"}))

    def test_an_unresolved_document_needs_a_reason(self):
        doc = document()
        doc["map_resolution"] = {"status": "unresolved", "checked_on": "2026-09-13"}
        self.assertTrue(validate_map_resolution(doc, set()))
        doc["map_resolution"]["reason"] = "No record on the map carries this DOI."
        self.assertEqual(validate_map_resolution(doc, set()), [])

    def test_a_document_without_a_status_is_refused(self):
        self.assertTrue(validate_map_resolution(document(), {"ixtheo:1"}))

    def test_an_unresolved_document_and_its_claims_stay_private(self):
        doc = document()
        doc["map_resolution"] = {"status": "unresolved", "checked_on": "2026-09-13",
                                 "reason": "off the map"}
        projection = public_projection({doc["id"]: doc}, [claim(evidence())])
        self.assertEqual(projection["documents"], {})
        self.assertEqual(projection["claims"], [])

    def test_map_keys_answer_to_cluster_and_source_identifiers(self):
        graph = {"nodes": [{"k": "pub", "ppn": "ORabc",
                            "source_ids": [{"source": "ixtheo-k10plus", "id": "1"}]},
                           {"k": "author", "label": "Crouzel, Henri"}]}
        self.assertEqual(map_record_keys(graph), {"ORabc", "ixtheo-k10plus:1"})

    def test_every_published_claim_points_at_a_record_on_the_map(self):
        public = next((path for path in (ROOT / "site" / "data" / "evidence.json",
                                         ROOT / "data" / "evidence.json") if path.is_file()), None)
        if public is None or not GRAPH.is_file():
            self.skipTest("no published evidence projection in this tree")
        keys = map_record_keys(json.loads(GRAPH.read_text(encoding="utf-8")))
        projection = json.loads(public.read_text(encoding="utf-8"))
        for item in list(projection["claims"]) + list(projection["documents"].values()):
            for record_id in item["bibliographic_record_ids"]:
                self.assertIn(record_id, keys, item["id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
