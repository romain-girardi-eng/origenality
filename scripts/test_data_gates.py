#!/usr/bin/env python3
"""Tests des garde-fous de données : attribution des résumés, périmètre, rangs.

    python3 scripts/test_data_gates.py          # ou -m unittest

Trois pièces sont contrôlées ici, celles dont une erreur silencieuse coûterait
cher : la résolution de la base d'origine d'un résumé et son attribution, la
détection du périmètre curaté qui commande le plancher de pertinence, et le
rang percentile qui ordonne les grappes mesurées.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "semantic"))

import check_release  # noqa: E402
import harvest_crossref  # noqa: E402
import harvest_openalex  # noqa: E402
import marc_text  # noqa: E402
import s2_bulk  # noqa: E402
import s2_harvest  # noqa: E402
import merge_dedup  # noqa: E402
import enrich_citations  # noqa: E402
import qa_checks  # noqa: E402
import remap_tag_ids  # noqa: E402
import retag_gaps  # noqa: E402
import tag_notices  # noqa: E402
import tags_io  # noqa: E402
import build_tag_schema  # noqa: E402
import build_openalex  # noqa: E402
import validate_tags  # noqa: E402
from vocabulary_io import load_vocabulary, resolve, tag_record_schema  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts" / "harvest_p1"))
import common as harvest_common  # noqa: E402


class AttributionTest(unittest.TestCase):
    """Le régime est l'attribution : un résumé publié doit nommer sa base."""

    @classmethod
    def setUpClass(cls):
        cls.policy = check_release.load_policy(check_release.DEFAULT_POLICY)

    def status(self, record):
        return check_release.decide(record, self.policy)[0]

    def test_every_harvested_source_can_be_credited(self):
        harvested = {
            "ixtheo-k10plus", "openalex", "crossref", "semanticscholar",
            "bibp", "adamantius-girota", "isidore", "thesesfr", "dialnet", "sbn",
        }
        missing = harvested - set(self.policy["attribution"])
        self.assertEqual(missing, set(), "bases sans ligne d'attribution : %s" % missing)
        for key, entry in self.policy["attribution"].items():
            self.assertTrue(entry["label"].strip(), "libellé vide pour %s" % key)

    def test_the_provenance_of_the_abstract_names_the_source(self):
        record = {
            "abstract": "x",
            "sources": [{"source": "ixtheo-k10plus"}, {"source": "openalex"}],
            "provenance": {"abstract": {"source": "openalex",
                                       "source_id": "https://openalex.org/W1"}},
        }
        self.assertEqual(check_release.abstract_source(record), "openalex")
        self.assertEqual(self.status(record), "attributed")

    def test_a_single_source_harvest_needs_no_provenance(self):
        self.assertEqual(check_release.abstract_source({"source": "bibp", "abstract": "x"}), "bibp")

    def test_a_merged_record_without_abstract_provenance_is_not_attributable(self):
        record = {
            "abstract": "x",
            "sources": [{"source": "ixtheo-k10plus"}, {"source": "openalex"}],
        }
        self.assertIsNone(check_release.abstract_source(record))
        self.assertEqual(self.status(record), "no_source")

    def test_an_unlisted_source_is_refused_for_lack_of_a_credit(self):
        self.assertEqual(self.status({"abstract": "x", "source": "une base jamais vue"}),
                         "unknown_source")

    def test_declared_rights_no_longer_decide_anything(self):
        """Persée, « all rights reserved », droits absents : tous publiables."""
        for rights in ("Copyright PERSEE 2003-2024.", "All rights reserved", None):
            record = {"abstract": "x", "source": "isidore", "source_id": "10670/1.ab",
                      "abstract_rights": rights}
            self.assertEqual(self.status(record), "attributed")

    def test_a_dump_whose_abstracts_are_all_credited_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / "dump.jsonl"
            dump.write_text(
                json.dumps({"origenality_id": "OR1", "abstract": "x",
                            "abstract_source": "isidore",
                            "abstract_url": "https://hdl.handle.net/10670/1.ab",
                            "abstract_rights": "Copyright PERSEE 2003-2024."})
                + "\n"
                + json.dumps({"origenality_id": "OR2", "abstract": "y",
                              "abstract_source": "openalex",
                              "source_id": "https://openalex.org/W2",
                              "abstract_rights": "openalex-inverted"})
                + "\n",
                encoding="utf-8",
            )
            report = check_release.check(dump, self.policy, 0, None, 10)
            self.assertEqual(report["violations"], 0)
            self.assertEqual(report["attributed"], 2)

    def test_an_abstract_without_a_source_is_still_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / "dump.jsonl"
            dump.write_text(json.dumps({"origenality_id": "OR3", "abstract": "x"}) + "\n",
                            encoding="utf-8")
            report = check_release.check(dump, self.policy, 0, None, 10)
            self.assertEqual(report["no_source"], 1)
            self.assertEqual(report["violations"], 1)

    def test_rights_are_recorded_without_being_judged(self):
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / "dump.jsonl"
            dump.write_text(
                json.dumps({"origenality_id": "OR4", "abstract": "x", "source": "bibp",
                            "abstract_url": "https://www.bibl.ulaval.ca/bibp/4"}) + "\n",
                encoding="utf-8",
            )
            report = check_release.check(dump, self.policy, 0, None, 10)
            self.assertEqual(report["violations"], 0)
            self.assertEqual(report["rights_unrecorded"], 1)
            self.assertEqual(report["by_source"], {"bibp": 1})

    def test_withdrawal_removes_the_targeted_abstracts_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / "dump.jsonl"
            clean = Path(directory) / "clean.jsonl"
            dump.write_text(
                json.dumps({"origenality_id": "OR5", "abstract": "x", "source": "bibp",
                            "abstract_url": "https://www.bibl.ulaval.ca/bibp/5"}) + "\n"
                + json.dumps({"origenality_id": "OR6", "abstract": "y", "source": "openalex",
                              "source_id": "https://openalex.org/W6"}) + "\n",
                encoding="utf-8",
            )
            report = check_release.check(dump, self.policy, 0, clean, 10, withdraw="bibp")
            self.assertEqual(report["withdrawn"], 1)
            kept, removed = {}, {}
            for line in clean.read_text(encoding="utf-8").splitlines():
                record = json.loads(line)
                (removed if "abstract_withheld" in record else kept)[record["origenality_id"]] = record
            self.assertIn("OR6", kept)
            self.assertNotIn("abstract", removed["OR5"])
            self.assertIn("bibp", removed["OR5"]["abstract_withheld"])

    def test_stripping_without_a_withdrawal_keeps_every_abstract(self):
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / "dump.jsonl"
            copy = Path(directory) / "copy.jsonl"
            dump.write_text(
                json.dumps({"origenality_id": "OR7", "abstract": "x", "source": "bibp",
                            "abstract_url": "https://www.bibl.ulaval.ca/bibp/7"}) + "\n",
                encoding="utf-8",
            )
            report = check_release.check(dump, self.policy, 0, copy, 10)
            self.assertEqual(report["withdrawn"], 0)
            self.assertEqual(json.loads(copy.read_text(encoding="utf-8"))["abstract"], "x")


class AttributionResolvabilityTest(unittest.TestCase):
    """Un crédit sans lien n'est pas une attribution (audit 3, finding 3)."""

    @classmethod
    def setUpClass(cls):
        cls.policy = check_release.load_policy(check_release.DEFAULT_POLICY)

    def status(self, record):
        return check_release.decide(record, self.policy)[0]

    def test_a_named_source_without_any_link_is_refused(self):
        """Contrôle négatif : BIBP n'a pas de gabarit d'URL de notice."""
        record = {"abstract": "x", "source": "bibp", "source_id": "42"}
        self.assertEqual(self.status(record), "unresolvable")

    def test_an_explicit_abstract_url_is_enough(self):
        record = {"abstract": "x", "source": "bibp", "source_id": "42",
                  "abstract_url": "https://www.bibl.ulaval.ca/bibp/42"}
        status, source, link = check_release.decide(record, self.policy)
        self.assertEqual(status, "attributed")
        self.assertEqual(link, "https://www.bibl.ulaval.ca/bibp/42")

    def test_an_identifier_resolved_by_the_template_is_enough(self):
        record = {"abstract": "x", "source": "ixtheo-k10plus", "source_id": "883455439"}
        status, _source, link = check_release.decide(record, self.policy)
        self.assertEqual(status, "attributed")
        self.assertEqual(link, "https://ixtheo.de/Record/883455439")

    def test_an_identifier_of_another_base_never_builds_the_link(self):
        """Le `source_id` d'une grappe ne vaut pas pour le résumé d'une autre base."""
        record = {
            "abstract": "x",
            "source_id": "883455439",
            "sources": [{"source": "ixtheo-k10plus"}, {"source": "bibp"}],
            "provenance": {"abstract": {"source": "bibp", "source_id": None}},
        }
        self.assertEqual(self.status(record), "unresolvable")

    def test_an_abstract_in_a_list_is_a_summary_not_an_absence(self):
        record = {"abstract": ["Premier paragraphe.", "Second paragraphe."],
                  "source": "bibp", "source_id": "42"}
        self.assertEqual(check_release.abstract_text(record),
                         "Premier paragraphe.\n\nSecond paragraphe.")
        self.assertEqual(self.status(record), "unresolvable")

    def test_an_empty_list_is_not_a_summary(self):
        self.assertIsNone(check_release.abstract_text({"abstract": []}))
        self.assertIsNone(check_release.abstract_text({"abstract": [{"p": "x"}]}))

    def test_the_abstract_key_is_read_whatever_its_case(self):
        record = {"Abstract": "x", "source": "bibp", "source_id": "42"}
        self.assertEqual(check_release.abstract_text(record), "x")

    def test_a_dump_of_lists_and_odd_cases_is_still_controlled(self):
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / "dump.jsonl"
            dump.write_text(
                json.dumps({"origenality_id": "OR8",
                            "Abstract": ["a", "b"],
                            "abstract_source": "bibp"}) + "\n"
                + json.dumps({"origenality_id": "OR9", "abstract": ["c"],
                              "abstract_source": "bibp",
                              "abstract_url": "https://www.bibl.ulaval.ca/bibp/9"}) + "\n",
                encoding="utf-8")
            report = check_release.check(dump, self.policy, 0, None, 10)
            self.assertEqual(report["abstracts"], 2)
            self.assertEqual(report["unresolvable"], 1)
            self.assertEqual(report["violations"], 1)
            self.assertIn("OR8", report["examples"][0]["id"])

    def test_a_withdrawal_removes_the_abstract_whatever_the_key_case(self):
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / "dump.jsonl"
            clean = Path(directory) / "clean.jsonl"
            dump.write_text(
                json.dumps({"origenality_id": "ORA", "Abstract": "x",
                            "abstract_source": "bibp",
                            "abstract_url": "https://www.bibl.ulaval.ca/bibp/a"}) + "\n",
                encoding="utf-8")
            report = check_release.check(dump, self.policy, 0, clean, 10, withdraw="bibp")
            self.assertEqual(report["withdrawn"], 1)
            written = json.loads(clean.read_text(encoding="utf-8"))
            self.assertNotIn("Abstract", written)
            self.assertIn("abstract_withheld", written)

    def test_every_credited_base_declares_a_licence(self):
        for key, entry in self.policy["attribution"].items():
            self.assertTrue(str(entry.get("license") or "").strip(),
                            "base sans licence déclarée : %s" % key)


class CuratedScopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vocab = load_vocabulary(ROOT / "semantic/vocabulary")

    def test_ixtheo_and_bibp_are_curated(self):
        self.assertTrue(tag_notices.curated_scope({"sources": [{"source": "ixtheo-k10plus"}]}))
        self.assertTrue(tag_notices.curated_scope({"source": "bibp"}))

    def test_adamantius_is_curated_only_in_sections_12_and_13(self):
        record = {"sources": [{"source": "adamantius-girota"}], "sections": [{"sezione": "12. Origene"}]}
        self.assertTrue(tag_notices.curated_scope(record))
        record["sections"] = [{"sezione": "13. L`origenismo e la fortuna di Origene"}]
        self.assertTrue(tag_notices.curated_scope(record))
        record["sections"] = [{"sezione": "7. Filone Alessandrino"}]
        self.assertFalse(tag_notices.curated_scope(record))

    def test_other_sources_are_not_curated(self):
        self.assertFalse(tag_notices.curated_scope({"sources": [{"source": "openalex"}]}))
        self.assertFalse(tag_notices.curated_scope({"sources": [{"source": "crossref"}]}))

    def _selected(self, records):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "notices.jsonl"
            path.write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
                encoding="utf-8")
            return [r["title"] for r in tag_notices.read_notices(
                path, {"about", "both"}, skip_noise=True)]

    def test_skip_noise_keeps_a_cluster_of_a_curated_perimeter(self):
        """Le pré-tri mécanique ne l'emporte pas sur la fiche d'autorité.

        Cas réel : « Wort und Eucharistie bei Origenes », notice IxTheo, sortie
        du dossier parce que le sujet principal de son jumeau OpenAlex portait
        le mot « education ».
        """
        kept = self._selected([
            {"title": "Wort und Eucharistie bei Origenes", "relation": "about",
             "noise_guess": True, "noise_rule": "topic-hors-champ",
             "sources": [{"source": "ixtheo-k10plus", "source_id": "42385500X"},
                         {"source": "openalex", "source_id": "W1"}]},
        ])
        self.assertEqual(kept, ["Wort und Eucharistie bei Origenes"])

    def test_skip_noise_still_drops_noise_outside_a_curated_perimeter(self):
        """Contrôle négatif : le bruit espagnol reste écarté."""
        kept = self._selected([
            {"title": "Denominaciones de origen y calidad", "relation": "about",
             "noise_guess": True, "sources": [{"source": "openalex", "source_id": "W2"}]},
            {"title": "Los orígenes del megacolon", "relation": "about",
             "noise_guess": True, "sources": [{"source": "crossref", "source_id": "10.1/x"}]},
        ])
        self.assertEqual(kept, [])

    def answer(self, relevance, reason="not-applicable"):
        return {
            "relevance": relevance,
            "relevance_none_reason": reason,
            "works": ["unspecified"],
            "themes": ["context.biography"],
            "approaches": ["historical"],
            "confidence": 0.8,
            "justification": "test",
            "needs_review": False,
        }

    def test_the_floor_lifts_none_to_marginal_inside_a_curated_perimeter(self):
        result = tag_notices.validate(self.answer("none"), self.vocab, 0.6, curated="ixtheo")
        self.assertEqual(result.values["relevance"], "marginal")
        self.assertTrue(result.values["relevance_floor_applied"])

    def test_the_floor_spares_homonyms_and_texts_by_origen(self):
        for reason in ("homonym", "text-by-origen"):
            result = tag_notices.validate(self.answer("none", reason), self.vocab, 0.6, curated="ixtheo")
            self.assertEqual(result.values["relevance"], "none")
            self.assertFalse(result.values["relevance_floor_applied"])

    def test_a_text_by_origen_cannot_count_in_the_density(self):
        """Rule 4 of prompt v2.1: printing a text is not studying it."""
        for answered in ("core", "partial"):
            result = tag_notices.validate(self.answer(answered), self.vocab, 0.6,
                                          curated="ixtheo", by_origen=True)
            self.assertEqual(result.values["relevance"], "marginal")
            self.assertTrue(result.values["relevance_ceiling_applied"])
            self.assertTrue(result.values["needs_review"])

    def test_the_ceiling_spares_an_edition_bound_with_studies(self):
        record = {"relation": "both", "authors": [{"name": "Origenes"}]}
        self.assertFalse(tag_notices.text_by_origen(record))
        result = tag_notices.validate(self.answer("core"), self.vocab, 0.6,
                                      curated="ixtheo", by_origen=False)
        self.assertEqual(result.values["relevance"], "core")
        self.assertFalse(result.values["relevance_ceiling_applied"])

    def test_a_text_by_origen_is_recognised_without_a_relation_field(self):
        """The Badius Opera comes from a harvest that carries no relation."""
        self.assertTrue(tag_notices.text_by_origen(
            {"authors": [{"name": "ca. ca. Or\u00edgenes"}, {"name": "Josse Badius"}]}))
        self.assertTrue(tag_notices.text_by_origen({"relation": "by"}))
        self.assertFalse(tag_notices.text_by_origen({"authors": [{"name": "Alfons F\u00fcrst"}]}))
        self.assertFalse(tag_notices.text_by_origen(
            {"relation": "about", "authors": [{"name": "Origenes"}]}))

    def test_the_floor_does_not_apply_outside_a_curated_perimeter(self):
        result = tag_notices.validate(self.answer("none"), self.vocab, 0.6, curated="")
        self.assertEqual(result.values["relevance"], "none")

    def test_the_new_leaf_is_in_the_vocabulary(self):
        self.assertIn("context.general-presentation", self.vocab.theme_ids)
        self.assertEqual(self.vocab.versions["themes"], "1.1.0")

    def test_the_identifier_prefers_the_stable_cluster_id(self):
        self.assertEqual(
            tag_notices.notice_identifier({"origenality_id": "OR123", "source": "openalex", "source_id": "W1"}),
            "OR123",
        )
        self.assertEqual(
            tag_notices.notice_identifier({"source": "ixtheo-k10plus", "source_id": "011209895"}),
            "ixtheo-k10plus:011209895",
        )


class CitationTest(unittest.TestCase):
    def test_percentile_rank_orders_and_shares_ties(self):
        rank = enrich_citations.percentile_ranks([0, 0, 5, 10])
        self.assertLess(rank(0), rank(5))
        self.assertLess(rank(5), rank(10))
        self.assertEqual(rank(0), 0.25)  # deux ex æquo au bas de quatre
        self.assertEqual(rank(10), 0.875)  # rang moyen du plus cité, jamais 1
        self.assertTrue(0 < rank(0) < rank(10) < 1)

    def test_the_count_carries_its_source(self):
        cluster = {
            "cited_by_count": 12,
            "provenance": {"cited_by_count": {"source": "openalex"}},
            "sources": [{"source": "ixtheo-k10plus"}, {"source": "openalex"}],
        }
        self.assertEqual(enrich_citations.count_and_source(cluster), (12, "openalex"))

    def test_an_unmeasured_cluster_has_no_count_and_no_rank(self):
        cluster = {"sources": [{"source": "ixtheo-k10plus"}]}
        self.assertEqual(enrich_citations.count_and_source(cluster), (None, None))

    def test_title_projection_is_marked_and_refuses_ambiguity(self):
        rows = [
            {"measured": True, "cited_by_count": 7, "source": "openalex", "count_method": "cluster"},
            {"measured": False, "cited_by_count": None, "source": None, "count_method": None},
            {"measured": False, "cited_by_count": None, "source": None, "count_method": None},
        ]
        key = ("origen and the alexandrian school of exegesis", "crouzel", "article")
        keys = [key, key, None]
        years = [1990, 1990, 1990]
        moved = enrich_citations.project_by_title(rows, keys, years)
        self.assertEqual(moved, 1)
        self.assertEqual(rows[1]["count_method"], "title-projection")
        self.assertFalse(rows[2]["measured"])

    def test_title_projection_refuses_a_year_gap(self):
        rows = [
            {"measured": True, "cited_by_count": 7, "source": "openalex", "count_method": "cluster"},
            {"measured": False, "cited_by_count": None, "source": None, "count_method": None},
        ]
        key = ("origen and the alexandrian school of exegesis", "crouzel", "article")
        self.assertEqual(enrich_citations.project_by_title(rows, [key, key], [1990, 2005]), 0)

    def test_title_projection_refuses_a_missing_year(self):
        """Une année absente n'est pas une année compatible."""
        rows = [
            {"measured": True, "cited_by_count": 7, "source": "openalex", "count_method": "cluster"},
            {"measured": False, "cited_by_count": None, "source": None, "count_method": None},
        ]
        key = ("origen and the alexandrian school of exegesis", "crouzel", "article")
        self.assertEqual(enrich_citations.project_by_title(rows, [key, key], [1990, None]), 0)

    def _one_projection(self, doc_type, left_year, right_year):
        rows = [
            {"measured": True, "cited_by_count": 7, "source": "openalex",
             "count_method": "cluster"},
            {"measured": False, "cited_by_count": None, "source": None,
             "count_method": None},
        ]
        key = ("origen and the alexandrian school of exegesis", "crouzel", doc_type)
        return enrich_citations.project_by_title(
            rows, [key, key], [left_year, right_year])

    def test_a_serial_piece_demands_the_exact_year(self):
        """Le fascicule 2020/2021 ne reçoit plus le compte du fascicule 2022."""
        self.assertEqual(self._one_projection("article", 2022, 2021), 0)
        self.assertEqual(self._one_projection("review", 2022, 2021), 0)
        self.assertEqual(self._one_projection("article", 2021, 2021), 1)

    def test_a_book_still_tolerates_one_year(self):
        """Année d'impression contre année de dépôt : l'écart d'un an reste."""
        for doc_type in ("book", "chapter", "dissertation"):
            self.assertEqual(self._one_projection(doc_type, 1994, 1995), 1, doc_type)
            self.assertEqual(self._one_projection(doc_type, 1994, 1996), 0, doc_type)

    def test_the_year_rule_is_declared_for_every_projectable_type(self):
        self.assertEqual(set(enrich_citations.YEAR_GAP_BY_TYPE),
                         set(enrich_citations.PROJECTABLE_TYPES))

    def test_a_review_never_lends_its_count_to_the_book(self):
        """Le cas Haas : même titre, même auteur, types différents."""
        book = {"title": "Alexandria in Late Antiquity. Topography and Social Conflict",
                "authors": ["Haas C."], "type": "book"}
        review = {"title": "Alexandria in late antiquity: topography and social conflict",
                  "authors": ["Haas C."], "type": "book-review"}
        title = enrich_citations.fold_title
        book_key = enrich_citations.projection_key(book, title(book["title"]), "book")
        review_key = enrich_citations.projection_key(review, title(review["title"]), "review")
        self.assertIsNotNone(book_key)
        self.assertIsNotNone(review_key)
        self.assertNotEqual(book_key, review_key)

    def test_a_notice_without_author_or_type_projects_nothing(self):
        title = "alexandria in late antiquity topography and social conflict"
        self.assertIsNone(enrich_citations.projection_key({"authors": None}, title, "book"))
        self.assertIsNone(
            enrich_citations.projection_key({"authors": ["Haas C."]}, title, "?"))
        self.assertIsNone(
            enrich_citations.projection_key({"authors": ["Haas C."]}, title, "other"))


class MergeIdentityTest(unittest.TestCase):
    """`origenality_id` doit être une clé, et la fusion ne doit ni confondre
    deux tomes ni scinder un auteur selon la forme de son nom."""

    def test_first_author_key_reads_the_surname_in_every_form(self):
        for form in ("Bovon, François", "Bovon F.", "François Bovon"):
            self.assertEqual(merge_dedup.first_author_key([form]), "bovon", form)
        for form in ("van den Hoek, Annewies", "Hoek A. van den", "Annewies van den Hoek"):
            self.assertEqual(merge_dedup.first_author_key([form]), "hoek", form)
        for form in ("Reydams-Schils G.", "Gretchen Reydams-Schils"):
            self.assertEqual(merge_dedup.first_author_key([form]), "reydams", form)
        self.assertEqual(merge_dedup.first_author_key([{"name": "Haas, Christopher"}]), "haas")
        self.assertEqual(merge_dedup.first_author_key([]), "")

    def test_two_doi_of_the_same_registrant_are_two_publications(self):
        left = "10.1017/cbo9780511996917"
        right = "10.1017/cbo9780511996924"
        self.assertEqual(merge_dedup.doi_prefix(left), merge_dedup.doi_prefix(right))
        self.assertNotEqual(merge_dedup.doi_prefix(left), merge_dedup.doi_prefix("10.2307/1234"))

    def test_a_volume_marker_hidden_in_an_abstract_is_seen(self):
        first = {"title": "The Commentary of Origen on S. John's Gospel",
                 "abstract": "Volume 1 includes an introductory discussion."}
        second = {"title": "The Commentary of Origen on S. John's Gospel",
                  "abstract": "Volume 2 includes Books 19, 20, 28 and 32."}
        self.assertNotEqual(merge_dedup.text_volume_signature(first),
                            merge_dedup.text_volume_signature(second))

    def test_two_clusters_of_the_same_identity_get_distinct_signatures(self):
        left = {"sources": [{"source": "sbn", "source_id": "A"}]}
        right = {"sources": [{"source": "sbn", "source_id": "B"}]}
        self.assertEqual(merge_dedup.cluster_identity(left), "s:sbn:A")
        self.assertNotEqual(merge_dedup.cluster_signature(left),
                            merge_dedup.cluster_signature(right))


class IsbnIdentityTest(unittest.TestCase):
    """L'ISBN est le troisième lien d'identité (audit 3, finding 1)."""

    def test_isbn10_and_isbn13_of_the_same_volume_give_one_key(self):
        self.assertEqual(merge_dedup.norm_isbn("3451221098"), "9783451221095")
        self.assertEqual(merge_dedup.norm_isbn("978-3-451-22109-5"), "9783451221095")
        self.assertEqual(merge_dedup.norm_isbn(" 3-451-22109-8 "), "9783451221095")

    def test_a_wrong_check_digit_is_not_an_isbn(self):
        self.assertIsNone(merge_dedup.norm_isbn("3451221099"))
        self.assertIsNone(merge_dedup.norm_isbn("9783451221096"))

    def test_an_issn_is_not_an_isbn(self):
        self.assertIsNone(merge_dedup.norm_isbn("0022-1953"))
        self.assertIsNone(merge_dedup.norm_isbn("1234"))

    def test_isbn_are_read_from_every_field_and_shape(self):
        self.assertEqual(
            merge_dedup.record_isbns({"isbn": ["3451221098", "3-451-22209-4"]}),
            {"9783451221095", "9783451222092"})
        self.assertEqual(
            merge_dedup.record_isbns({"isbn_issn": "978-88-7228-811-5"}),
            {"9788872288115"})

    def test_the_volume_marker_still_separates_two_tomes(self):
        left = merge_dedup.text_volume_signature({"title": "Studia patristica, vol. LXXXIV"})
        right = merge_dedup.text_volume_signature({"title": "Papers, vol. 10"})
        self.assertEqual((left, right), ((84,), (10,)))
        self.assertNotEqual(left, right)

    def test_a_marker_on_one_side_only_does_not_block(self):
        """Le catalogue n'écrit « Bd. 4 » que sur une des trois saisies."""
        left = merge_dedup.text_volume_signature(
            {"title": "Commentarii in Epistulam ad Romanos : 4 Liber septimus"})
        right = merge_dedup.text_volume_signature(
            {"title": "Commentarii in epistulam ad Romanos. Bd. 4 Liber septimus"})
        self.assertEqual(left, ())
        self.assertEqual(right, (4,))
        self.assertFalse(left and right and left != right)


class UrlValidationTest(unittest.TestCase):
    """Une attribution résoluble doit l'être vraiment (audit 4, finding 5)."""

    @classmethod
    def setUpClass(cls):
        cls.policy = check_release.load_policy(check_release.DEFAULT_POLICY)

    def test_a_string_that_starts_with_http_is_not_an_address(self):
        for value in ("http-not-a-url", "http://", "https://", "httpfoo",
                      "http:///Record/1", "https://a b.de/x", ""):
            self.assertFalse(check_release.is_resolvable_url(value), value)

    def test_a_host_without_a_dot_is_refused(self):
        self.assertFalse(check_release.is_resolvable_url("http://localhost/Record/1"))

    def test_a_path_that_climbs_the_tree_is_refused(self):
        self.assertFalse(check_release.is_resolvable_url("https://ixtheo.de/Record/../../x"))
        self.assertFalse(check_release.is_resolvable_url("https://ixtheo.de/Record/%2e%2e/x"))

    def test_a_real_address_passes(self):
        for value in ("https://ixtheo.de/Record/1011064553",
                      "http://www.bibl.ulaval.ca/bibp/42",
                      "https://hdl.handle.net/10670/1.ab"):
            self.assertTrue(check_release.is_resolvable_url(value), value)

    def test_an_identifier_never_climbs_the_tree(self):
        for value in ("../../not-a-record", "/etc/passwd", "", None, "a b",
                      "javascript:alert(1)", "file:///etc/passwd"):
            self.assertFalse(check_release.is_safe_identifier(value), repr(value))
        for value in ("1011064553", "10670/1.ab", "W2741809807",
                      "https://openalex.org/W1"):
            self.assertTrue(check_release.is_safe_identifier(value), value)

    def test_a_full_address_is_not_interpolated_into_another_one(self):
        """Le gabarit d'IxTheo préfixe : une URL complète n'y entre pas."""
        entry = self.policy["attribution"]["ixtheo-k10plus"]
        record = {"abstract": "x", "source": "ixtheo-k10plus",
                  "source_id": "https://evil.example/x"}
        self.assertIsNone(check_release.attribution_link(record, "ixtheo-k10plus", entry))

    def test_a_base_whose_identifier_is_the_address_still_resolves(self):
        """OpenAlex : le gabarit est « {id} », l'identifiant EST l'adresse."""
        entry = self.policy["attribution"]["openalex"]
        record = {"abstract": "x", "source": "openalex",
                  "source_id": "https://openalex.org/W1"}
        self.assertEqual(
            check_release.attribution_link(record, "openalex", entry),
            "https://openalex.org/W1")

    def test_the_three_strings_named_by_the_audit_are_refused_end_to_end(self):
        entry = self.policy["attribution"]["ixtheo-k10plus"]
        cases = [
            {"abstract": "x", "source": "ixtheo-k10plus", "abstract_url": "http-not-a-url"},
            {"abstract": "x", "source": "ixtheo-k10plus", "abstract_url": "http://"},
            {"abstract": "x", "source": "ixtheo-k10plus", "source_id": "../../not-a-record"},
        ]
        for record in cases:
            self.assertIsNone(
                check_release.attribution_link(record, "ixtheo-k10plus", entry), record)
            self.assertEqual(check_release.decide(record, self.policy)[0], "unresolvable")


class S2TokenTest(unittest.TestCase):
    """Un curseur refusé est purgé, la requête repart page 1 (finding 6)."""

    def test_a_400_on_a_paginated_request_means_the_cursor_died(self):
        self.assertTrue(s2_bulk.token_expired(400, "opaque-cursor"))
        self.assertTrue(s2_bulk.token_expired(422, "opaque-cursor"))

    def test_a_400_without_a_cursor_is_not_a_cursor_problem(self):
        """Sans curseur présenté, l'erreur vient de la requête : on ne boucle pas."""
        self.assertFalse(s2_bulk.token_expired(400, None))
        self.assertFalse(s2_bulk.token_expired(400, ""))

    def test_other_statuses_leave_the_cursor_alone(self):
        for status in (200, 429, 500, 503):
            self.assertFalse(s2_bulk.token_expired(status, "opaque-cursor"))

    def test_purging_sends_the_query_back_to_page_one(self):
        state = {"done": [], "token": {"q1": "dead", "q2": "alive"},
                 "pages": {"q1": 7, "q2": 3}}
        s2_bulk.drop_token(state, "q1")
        self.assertNotIn("q1", state["token"])
        self.assertEqual(state["pages"]["q1"], 0)
        self.assertEqual(state["token"]["q2"], "alive")
        self.assertEqual(state["pages"]["q2"], 3)

    def test_a_simulated_expired_cursor_run(self):
        """Réponse simulée : 400 sur le curseur, puis 200 sur la page 1."""
        answers = [(400, {"error": "invalid token"}, None),
                   (200, {"total": 1, "data": [{"paperId": "P1"}], "token": None}, None)]
        calls = []

        def fake_fetch(query, token=None):
            calls.append(token)
            return answers[len(calls) - 1]

        state = {"done": [], "token": {"q": "dead"}, "pages": {"q": 5}}
        token = state["token"]["q"]
        purged = 0
        for _attempt in range(2):
            status, payload, _asked = fake_fetch("q", token)
            if s2_bulk.token_expired(status, token):
                s2_bulk.drop_token(state, "q")
                token = None
                purged += 1
                continue
            self.assertEqual(status, 200)
            self.assertEqual(payload["data"][0]["paperId"], "P1")
            break
        self.assertEqual(calls, ["dead", None])
        self.assertEqual(purged, 1)
        self.assertEqual(state["pages"]["q"], 0)


class IsbnLinkTest(unittest.TestCase):
    """Ce que le lien ISBN unit, et ce qu'il refuse d'unir (audit 4, finding 2).

    `isbn_group_pairs` est une fonction pure : les cas se posent ici sur des
    tables minuscules, sans corpus ni fichier, y compris ceux que le corpus réel
    ne contient pas — le garde de série n'était jamais exercé.
    """

    @staticmethod
    def decide(rows):
        """rows = [(titre, tomaison, année)] ; tous partagent le même ISBN."""
        titles = [merge_dedup.norm_title(title) for title, _marks, _year in rows]
        volsigs = [marks for _title, marks, _year in rows]
        years = [year for _title, _marks, year in rows]
        return merge_dedup.isbn_group_pairs(
            list(range(len(rows))), titles, volsigs, years)

    def test_two_editions_forty_years_apart_stay_apart(self):
        """Le cas réel : 3894113049 sur « Geist und Feuer » en 1951 et en 1991."""
        pairs, refusals = self.decide([
            ("Geist und Feuer", (), 1951),
            ("Geist und Feuer : ein Aufbau aus seinen Schriften", (), 1991),
        ])
        self.assertEqual(pairs, [])
        self.assertEqual(refusals["year_gap"], 1)

    def test_one_year_of_drift_is_the_same_printing(self):
        """Dépôt légal et parution : une année d'écart n'est pas une réédition."""
        pairs, refusals = self.decide([
            ("Origenes und die Freiheit", (), 2015),
            ("Origenes und die Freiheit", (), 2016),
        ])
        self.assertEqual(pairs, [(0, 1)])
        self.assertEqual(refusals["year_gap"], 0)

    def test_a_missing_year_does_not_block(self):
        """Une année absente n'est pas la preuve d'une autre édition."""
        pairs, _refusals = self.decide([
            ("Origenes und die Freiheit", (), None),
            ("Origenes und die Freiheit", (), 2016),
        ])
        self.assertEqual(pairs, [(0, 1)])

    def test_an_isbn_worn_by_eight_titles_is_a_series_and_links_nothing(self):
        """Le garde de série, jamais exercé par le corpus : cas synthétique."""
        rows = [("Corpus Christianorum : tome %d, texte propre %d" % (n, n),
                 (n,), 2000 + n) for n in range(1, 9)]
        pairs, refusals = self.decide(rows)
        self.assertEqual(len(rows), 8)
        self.assertEqual(pairs, [])
        self.assertEqual(refusals["series"], 1)
        # le refus porte sur le groupe entier, pas paire par paire
        self.assertEqual(refusals["year_gap"], 0)
        self.assertEqual(refusals["volume_marker"], 0)

    def test_two_tomes_of_one_series_stay_apart(self):
        pairs, refusals = self.decide([
            ("Lexicon Gregorianum : Band I", (1,), 1999),
            ("Lexicon Gregorianum : Band II", (2,), 1999),
        ])
        self.assertEqual(pairs, [])
        self.assertEqual(refusals["volume_marker"], 1)

    def test_one_volume_under_two_numberings_is_one_volume(self):
        """Les paires ixtheo :47/:627 et :48/:628, instruites.

        Même ISBN, même année, même éditeur ; les numéros divergent parce que le
        volume appartient à deux hiérarchies — la série Studia Patristica et le
        jeu des actes d'Oxford 2015. La désignation d'ouvrage, elle, est la même
        suite de mots des deux côtés.
        """
        pairs, refusals = self.decide([
            ("Evagrius between Origen, the Cappadocians, and Neoplatonism : "
             "studia patristica, vol. LXXXIV", (84,), 2017),
            ("Papers presented at the Seventeenth International Conference on "
             "Patristic Studies held in Oxford 2015 : Volume 10 Evagrius "
             "between Origen, the Cappadocians, and Neoplatonism", (10,), 2017),
        ])
        self.assertEqual(pairs, [(0, 1)])
        self.assertEqual(refusals["volume_marker"], 0)

    def test_a_shared_collection_name_is_not_a_shared_designation(self):
        """« studia patristica » seul ne lève pas le garde de tomaison."""
        self.assertFalse(merge_dedup.same_designation(
            merge_dedup.norm_title("Studia patristica, vol. LXXXIV"),
            merge_dedup.norm_title("Studia patristica, vol. XCIV")))


class LastWriteWinsTest(unittest.TestCase):
    """Un retag remplace l'ancien tag partout en aval (audit 4, finding 4)."""

    def write(self, rows):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".jsonl", delete=False, encoding="utf-8")
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return Path(handle.name)

    def test_the_last_line_of_a_notice_is_the_one_that_counts(self):
        path = self.write([
            {"notice_id": "OR1", "themes": ["ancien"], "wave": "w"},
            {"notice_id": "OR2", "themes": ["autre"], "wave": "w"},
            {"notice_id": "OR1", "themes": ["corrigé"], "wave": "w"},
        ])
        records = tags_io.read_tags(path)
        self.assertEqual([r["notice_id"] for r in records], ["OR1", "OR2"])
        self.assertEqual(records[0]["themes"], ["corrigé"])
        self.assertEqual(tags_io.superseded_count(path), 1)

    def test_a_retag_does_not_reorder_the_index(self):
        """L'ordre de sortie est celui de la PREMIÈRE apparition."""
        path = self.write([
            {"notice_id": "A"}, {"notice_id": "B"}, {"notice_id": "C"},
            {"notice_id": "A", "v": 2},
        ])
        self.assertEqual([r["notice_id"] for r in tags_io.read_tags(path)],
                         ["A", "B", "C"])

    def test_compaction_keeps_the_history_and_leaves_one_line_per_notice(self):
        path = self.write([
            {"notice_id": "OR1", "themes": ["ancien"]},
            {"notice_id": "OR1", "themes": ["corrigé"]},
        ])
        history = path.with_suffix(".history.jsonl")
        self.addCleanup(lambda: history.unlink(missing_ok=True))
        report = tags_io.compact(path)
        self.assertEqual(report["lines_in"], 2)
        self.assertEqual(report["lines_out"], 1)
        self.assertEqual(report["superseded"], 1)
        kept = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(kept, [{"notice_id": "OR1", "themes": ["corrigé"]}])
        # l'historique ne reçoit que la ligne périmée : recopier aussi la ligne
        # courante y empilait des états au lieu d'y écrire un journal (audit 5)
        archived = [json.loads(line)
                    for line in history.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(archived, [{"notice_id": "OR1", "themes": ["ancien"]}])

    def test_compaction_of_a_clean_file_changes_nothing(self):
        path = self.write([{"notice_id": "OR1"}, {"notice_id": "OR2"}])
        before = path.read_text(encoding="utf-8")
        report = tags_io.compact(path)
        self.assertEqual(report["superseded"], 0)
        self.assertEqual(path.read_text(encoding="utf-8"), before)
        self.assertFalse(path.with_suffix(".history.jsonl").exists())


class AbstractRightsConflictTest(unittest.TestCase):
    """Les droits concurrents se relèvent même à texte identique (finding 7)."""

    def test_three_bases_on_one_text_keep_their_three_labels(self):
        merged = merge_dedup.merge_records([
            {"source": "ixtheo-k10plus", "source_id": "883455439",
             "abstract": "Un même texte.", "abstract_rights": "editor-unverified"},
            {"source": "openalex", "source_id": "W1",
             "abstract": "Un même texte.", "abstract_rights": "openalex-inverted"},
            {"source": "crossref", "source_id": "10.1017/x",
             "abstract": "Un même texte.", "abstract_rights": "crossref-jats"},
        ])
        self.assertEqual(merged["abstract_rights"], "editor-unverified")
        self.assertEqual(merged.get("conflicts", {}).get("abstract"), None)
        got = {(c["source"], c["value"])
               for c in merged["conflicts"]["abstract_rights"]}
        self.assertEqual(got, {("openalex", "openalex-inverted"),
                               ("crossref", "crossref-jats")})

    def test_one_label_shared_by_all_is_not_a_conflict(self):
        merged = merge_dedup.merge_records([
            {"source": "openalex", "source_id": "W1", "abstract": "t",
             "abstract_rights": "openalex-inverted"},
            {"source": "crossref", "source_id": "10.1/x", "abstract": "t",
             "abstract_rights": "openalex-inverted"},
        ])
        self.assertNotIn("abstract_rights", merged.get("conflicts", {}))

    def test_the_abstract_link_comes_from_the_donor_notice(self):
        merged = merge_dedup.merge_records([
            {"source": "ixtheo-k10plus", "source_id": "1", "url": "https://ixtheo.de/Record/1"},
            {"source": "isidore", "source_id": "10670/1.ab", "abstract": "t",
             "url": "https://example.org/isidore/ab"},
        ])
        self.assertEqual(merged["url"], "https://ixtheo.de/Record/1")
        self.assertEqual(merged["abstract_url"], "https://example.org/isidore/ab")
        self.assertEqual(merged["provenance"]["abstract_url"]["source"], "isidore")


class ResumeTest(unittest.TestCase):
    """La reprise saute une notice inchangée et RETAGUE une notice modifiée."""

    NOTICE = {"source": "ixtheo-k10plus", "source_id": "883455439",
              "title": "Contra Celsum", "relation": "about"}

    def written(self, directory, notice, wave="w", prompt="tag-notice-v2.1",
                vocabulary="v1"):
        path = Path(directory) / "tags.jsonl"
        path.write_text(json.dumps({
            "notice_id": tag_notices.notice_identifier(notice),
            "input_digest": tag_notices.payload_digest(
                tag_notices.notice_payload(notice)),
            "wave": wave, "prompt_version": prompt,
            "vocabulary_version": vocabulary,
        }) + "\n", encoding="utf-8")
        return path

    def test_an_unchanged_notice_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.written(directory, self.NOTICE)
            done = tag_notices.already_tagged(path, "w", "tag-notice-v2.1", "v1")
            self.assertIn(tag_notices.resume_key(self.NOTICE), done)

    def test_a_corrected_title_under_the_same_id_is_retagged(self):
        """Le cas de l'audit : même identifiant, fiche différente."""
        with tempfile.TemporaryDirectory() as directory:
            path = self.written(directory, self.NOTICE)
            done = tag_notices.already_tagged(path, "w", "tag-notice-v2.1", "v1")
            corrected = dict(self.NOTICE, title="Contra Celsum, livres I-II")
            self.assertEqual(tag_notices.notice_identifier(corrected),
                             tag_notices.notice_identifier(self.NOTICE))
            self.assertNotIn(tag_notices.resume_key(corrected), done)

    def test_an_abstract_added_under_the_same_id_is_retagged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.written(directory, self.NOTICE)
            done = tag_notices.already_tagged(path, "w", "tag-notice-v2.1", "v1")
            enriched = dict(self.NOTICE, abstract="Un résumé versé après coup.")
            self.assertNotIn(tag_notices.resume_key(enriched), done)

    def test_another_prompt_or_vocabulary_does_not_count_as_done(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.written(directory, self.NOTICE, prompt="tag-notice-v1")
            self.assertEqual(
                tag_notices.already_tagged(path, "w", "tag-notice-v2.1", "v1"), set())

    def test_a_reject_is_compared_to_the_versions_and_to_the_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rejects.jsonl"
            path.write_text(json.dumps({
                "notice_id": tag_notices.notice_identifier(self.NOTICE),
                "input_digest": tag_notices.payload_digest(
                    tag_notices.notice_payload(self.NOTICE)),
                "wave": "w", "prompt_version": "tag-notice-v1",
                "vocabulary_version": "v1", "stage": "validate",
            }) + "\n", encoding="utf-8")
            self.assertEqual(
                tag_notices.already_rejected(path, "w", "tag-notice-v2.1", "v1"), set())
            self.assertIn(
                tag_notices.resume_key(self.NOTICE),
                tag_notices.already_rejected(path, "w", "tag-notice-v1", "v1"))

    def test_an_old_reject_without_a_digest_sends_the_notice_back(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rejects.jsonl"
            path.write_text(json.dumps({
                "notice_id": tag_notices.notice_identifier(self.NOTICE),
                "wave": "w", "stage": "call",
            }) + "\n", encoding="utf-8")
            refused = tag_notices.already_rejected(path, "w", "tag-notice-v2.1", "v1")
            self.assertNotIn(tag_notices.resume_key(self.NOTICE), refused)


class TagValidationTest(unittest.TestCase):
    """Le validateur ne borne plus en silence et ne prend plus un motif inventé."""

    @classmethod
    def setUpClass(cls):
        cls.vocab = load_vocabulary(ROOT / "semantic" / "vocabulary")

    def answer(self, **overrides):
        base = {"relevance": "core", "relevance_none_reason": "not-applicable",
                "works": ["unspecified"], "themes": ["exegesis.allegory"],
                "approaches": ["exegetical"], "confidence": 0.8,
                "justification": "title names Origen", "needs_review": False}
        base.update(overrides)
        return base

    def test_an_invented_none_reason_is_rejected(self):
        result = tag_notices.validate(
            self.answer(relevance="none", relevance_none_reason="unclear"),
            self.vocab, 0.6)
        self.assertTrue(result.error)
        self.assertFalse(result.values)

    def test_a_confidence_out_of_range_is_flagged_not_silently_clamped(self):
        result = tag_notices.validate(self.answer(confidence=2), self.vocab, 0.6)
        self.assertFalse(result.error)
        self.assertEqual(result.values["confidence"], 1.0)
        self.assertTrue(result.values["needs_review"])
        self.assertTrue(any("out of [0,1]" in r for r in result.repairs))

    def test_a_notice_out_of_the_dossier_carries_no_theme(self):
        result = tag_notices.validate(
            self.answer(relevance="none", relevance_none_reason="homonym", themes=[]),
            self.vocab, 0.6)
        self.assertFalse(result.error)
        self.assertEqual(result.values["themes"], [])

    def test_a_relevant_notice_still_needs_a_theme(self):
        result = tag_notices.validate(self.answer(themes=[]), self.vocab, 0.6)
        self.assertTrue(result.error)


class NavigationTest(unittest.TestCase):
    """Sans correspondance, la sélection est vide : pas de densité de consolation."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "semantic" / "tree"))
        import navigate  # noqa: PLC0415
        cls.navigate = navigate
        cls.nodes = [
            {"node_id": "themes:anthropology", "title": "Human being, soul and freedom",
             "path": "Human being, soul and freedom", "summary": "",
             "concept_tags": ["L'homme, l'âme et la liberté"], "entity_tags": [],
             "depth": 1, "n_notices": 900, "notice_ids": ["a"]},
            {"node_id": "themes:exegesis", "title": "Exegesis and hermeneutics",
             "path": "Exegesis and hermeneutics", "summary": "",
             "concept_tags": [], "entity_tags": [], "depth": 1,
             "n_notices": 2000, "notice_ids": ["b"]},
        ]

    def test_no_match_selects_nothing(self):
        self.assertEqual(self.navigate.heuristic_select("zzzzyyyyxxxx", self.nodes, 8), [])
        self.assertEqual(
            self.navigate.heuristic_select("quantum chromodynamics", self.nodes, 8), [])

    def test_a_french_query_reaches_the_domain_by_its_french_label(self):
        chosen = self.navigate.heuristic_select("Origène et la liberté", self.nodes, 8)
        self.assertEqual([n["node_id"] for n in chosen], ["themes:anthropology"])

    def test_a_non_latin_query_yields_terms(self):
        self.assertTrue(self.navigate.query_terms("自由意志"))
        self.assertTrue(self.navigate.query_terms("Willensfreiheit"))


class MarcTextTest(unittest.TestCase):
    """Les artefacts d'export MARC sont réparés, un vrai point d'interrogation non."""

    def test_the_subfield_delimiter_left_glued_is_removed(self):
        out, rules = marc_text.normalise_marc_text(
            "die Freiheit des Menschen stehen.0Alfons Fürst beschreibt")
        self.assertIn("stehen. Alfons", out)
        self.assertIn("marc-delimiter", rules)

    def test_a_substitution_mark_between_digits_is_a_dash(self):
        out, rules = marc_text.normalise_marc_text("Alexandria (185?253/54)")
        self.assertIn("185–253", out)
        self.assertIn("year-range", rules)

    def test_a_genuine_question_mark_survives(self):
        out, rules = marc_text.normalise_marc_text(
            "Origenes simplex vel duplex? Das Origenes-Problem")
        self.assertEqual(out, "Origenes simplex vel duplex? Das Origenes-Problem")
        self.assertEqual(rules, [])

    def test_french_keeps_its_space_before_the_question_mark(self):
        out, rules = marc_text.normalise_marc_text("Que dire ? Il faut voir", "fre")
        self.assertEqual(rules, [])
        self.assertEqual(out, "Que dire ? Il faut voir")


class HarvestPolitenessTest(unittest.TestCase):
    """Le serveur dit quand revenir, et une reprise ne repaie pas la page 1."""

    class Throttled:
        def __init__(self, value):
            self.headers = {"Retry-After": value} if value is not None else {}

    def test_every_harvester_waits_up_to_an_hour(self):
        """Le plafond de 300 s n'honorait pas une valeur supérieure."""
        for module in (s2_bulk, s2_harvest, harvest_crossref, harvest_openalex,
                       harvest_common):
            self.assertEqual(module.RETRY_AFTER_MAX, 3600.0, module.__name__)

    def test_the_asked_delay_is_replayed_and_capped(self):
        self.assertEqual(s2_bulk.retry_after(self.Throttled("900")), 900.0)
        self.assertEqual(s2_bulk.retry_after(self.Throttled("7200")), 3600.0)
        self.assertIsNone(s2_bulk.retry_after(self.Throttled(None)))

    def test_an_http_date_is_read_as_a_delay(self):
        import datetime as dt
        from email.utils import format_datetime
        moment = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=600)
        delay = s2_bulk.retry_after(self.Throttled(format_datetime(moment)))
        self.assertTrue(590 <= delay <= 601, delay)

    def test_the_pagination_cursor_survives_a_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "s2_bulk_state.json"
            original = s2_bulk.STATE_PATH
            try:
                s2_bulk.STATE_PATH = str(path)
                state = s2_bulk.load_state()
                self.assertEqual(state, {"done": [], "token": {}, "pages": {}})
                state["token"]['"Peri Archon"'] = "opaque-cursor"
                state["pages"]['"Peri Archon"'] = 1
                state["done"].append('"Contra Celsum"')
                s2_bulk.save_state(state)
                self.assertEqual(s2_bulk.load_state(), state)
                self.assertEqual(s2_bulk.load_state(restart=True),
                                 {"done": [], "token": {}, "pages": {}})
            finally:
                s2_bulk.STATE_PATH = original

    def test_a_corrupt_state_file_is_not_fatal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "s2_bulk_state.json"
            path.write_text("{ pas du json", encoding="utf-8")
            original = s2_bulk.STATE_PATH
            try:
                s2_bulk.STATE_PATH = str(path)
                self.assertEqual(s2_bulk.load_state(),
                                 {"done": [], "token": {}, "pages": {}})
            finally:
                s2_bulk.STATE_PATH = original


class MarcFalsePositiveTest(unittest.TestCase):
    """Motifs légitimes que les règles MARC ne doivent PAS réécrire.

    L'audit 3 (finding 14) note que les règles reconnaissent un motif, non un
    contexte : chiffre–point d'interrogation–chiffre, ou « .0 » suivi d'une
    capitale. Ces six cas sont ceux où le motif existe dans un texte correct.
    """

    def unchanged(self, text, language=None):
        out, rules = marc_text.normalise_marc_text(text, language)
        self.assertEqual(out, text, "texte réécrit : %r -> %r" % (text, out))
        self.assertEqual(rules, [], "règles appliquées à tort : %s" % rules)

    def test_a_version_number_before_a_capital_is_left_alone(self):
        self.unchanged("Publié avec TEI 2.0 Alpha en annexe")

    def test_a_shelfmark_with_a_query_between_digits_keeps_its_question(self):
        """« Ms. 1?2 » — la cote dont un chiffre est douteux, pas un millésime."""
        self.unchanged("Cote Vat. gr. Ms. 1?2, à vérifier sur place")

    def test_an_uncertain_volume_number_keeps_its_question_mark(self):
        self.unchanged("Erschienen in vol. 3?4, die Angabe schwankt")
        self.unchanged("Erschienen in vol. 3? oder 4, die Angabe schwankt")

    def test_a_year_range_is_still_repaired(self):
        """La règle resserrée ne perd pas le cas réel du corpus."""
        out, rules = marc_text.normalise_marc_text("Alexandria (185?253/54)")
        self.assertIn("185–253", out)
        self.assertEqual(rules, ["year-range"])

    def test_an_unpaired_question_mark_is_not_a_pair_of_quotes(self):
        self.unchanged("Origenes simplex vel duplex? Ein ?altes Problem")

    def test_a_question_mark_opening_a_capitalised_clause_survives(self):
        self.unchanged("Wer war Origenes ? Adamantius nennt ihn so")

    def test_a_decimal_figure_before_a_capital_is_left_alone(self):
        self.unchanged("Der Anteil steigt auf 12.0 Prozent")

    # --- audit 4, finding 8 : les deux motifs encore réécrits -----------------

    def test_a_shelfmark_of_three_digits_keeps_its_question_mark(self):
        """« Ms. 123?456 » : deux gardes, l'écart et le mot de cote."""
        self.unchanged("Ms. 123?456")
        self.unchanged("Cote Vat. gr. Ms. 123?456, à vérifier sur place")

    def test_a_version_number_glued_to_a_capital_keeps_its_zero(self):
        """« v.0Alpha » : une initiale n'est pas un mot, donc pas une phrase."""
        self.unchanged("v.0Alpha")
        self.unchanged("Fichier v.0Alpha du 3 mars")
        self.unchanged("Nr.0Alfons")

    def test_two_numbers_too_far_apart_are_not_a_year_range(self):
        self.unchanged("Die Nummern 100?1900 sind vergeben")

    def test_a_descending_pair_is_not_a_year_range(self):
        self.unchanged("Die Nummern 1990?1950 stimmen nicht")

    def test_a_number_out_of_the_year_bounds_is_not_a_year(self):
        self.unchanged("Die Nummern 2500?2600 sind vergeben")

    def test_the_four_real_repairs_of_the_corpus_still_fire(self):
        """Les quatre notices réparées du fonds, motif par motif."""
        cases = [
            ("Freiheit des Menschen stehen.0Alfons Fürst beschreibt", "marc-delimiter"),
            ("Origenes aus Alexandria (185?253/54)", "year-range"),
            ("God?s will and human freedom", "genitive"),
            ("Als ?das Wunder der christlichen Welt? gepriesen worden", "quotes"),
            ("Grieche bleiben ? das war sein Programm", "dash"),
        ]
        for text, rule in cases:
            out, rules = marc_text.normalise_marc_text(text)
            self.assertIn(rule, rules, "règle perdue sur %r" % text)
            self.assertNotEqual(out, text)


# ---------------------------------------------------------------------------
# Itération 8 — les gardes-fous de l'audit 5
# ---------------------------------------------------------------------------

def scratch(prefix):
    """Répertoire de travail sous data/_proofs_tmp/tests, jamais sous /tmp.

    Les bacs à sable d'audit n'ont pas toujours de répertoire temporaire, et dix-neuf
    tests y tombaient en erreur sans qu'aucune assertion soit en cause. Le répertoire
    de travail du harnais, lui, existe partout où le dépôt existe.
    """
    base = ROOT / "data" / "_proofs_tmp" / "tests"
    base.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=str(base)))


class SeriesDesignationTest(unittest.TestCase):
    """A5-1 : un long préfixe d'actes de colloque n'est pas une désignation d'ouvrage."""

    # les deux notices réelles, ixtheo :627 (volume 10) et :628 (volume 20)
    VOL10 = ("Papers presented at the Seventeenth International Conference on Patristic "
             "Studies held in Oxford 2015 : Volume 10 Evagrius between Origen, the "
             "Cappadocians, and Neoplatonism")
    VOL20 = ("Papers presented at the Seventeenth International Conference on Patristic "
             "Studies held in Oxford 2015 : Volume 20 From Tertullian to Tyconius")
    SP84 = ("Evagrius between Origen, the Cappadocians, and Neoplatonism : "
            "studia patristica, vol. LXXXIV")

    def designation(self, left, right):
        return merge_dedup.same_designation(merge_dedup.norm_title(left),
                                            merge_dedup.norm_title(right))

    def test_two_volumes_of_one_conference_are_not_one_work(self):
        self.assertFalse(self.designation(self.VOL10, self.VOL20))

    def test_the_shared_run_of_those_two_is_long_enough_to_have_passed(self):
        """Le contournement de l'auditeur : cent quatre caractères communs."""
        run, _left, _right = merge_dedup.longest_common_run(
            merge_dedup.norm_title(self.VOL10).split(),
            merge_dedup.norm_title(self.VOL20).split())
        self.assertGreater(len(" ".join(run)), 100)

    def test_the_same_volume_under_two_numberings_still_unites(self):
        """La paire ixtheo :47/:627, admise à l'itération 7, n'est pas perdue."""
        self.assertTrue(self.designation(self.SP84, self.VOL10))

    def test_a_shared_isbn_does_not_merge_the_two_conference_volumes(self):
        """Le scénario complet : un ISBN de série recopié sur les volumes 10 et 20."""
        titles = [merge_dedup.norm_title(self.VOL10), merge_dedup.norm_title(self.VOL20)]
        volsigs = [merge_dedup.volume_signature(self.VOL10),
                   merge_dedup.volume_signature(self.VOL20)]
        pairs, refusals = merge_dedup.isbn_group_pairs(
            [0, 1], titles, volsigs, [2017, 2017])
        self.assertEqual(pairs, [])
        self.assertEqual(refusals["volume_marker"], 1)

    def test_a_run_that_carries_a_volume_word_is_refused(self):
        self.assertFalse(self.designation(
            "Corpus Christianorum series latina volume 1",
            "Corpus Christianorum series latina volume 2"))


class OpenAlexHostTest(unittest.TestCase):
    """A5-2 : un identifiant qui EST une adresse doit rester chez lui."""

    ENTRY = {"label": "OpenAlex", "url_template": "{id}", "hosts": ["openalex.org"]}

    def link(self, identifier):
        record = {"source": "openalex", "source_id": identifier, "abstract": "x"}
        return check_release.attribution_link(record, "openalex", self.ENTRY)

    def test_an_openalex_address_is_attributed(self):
        self.assertEqual(self.link("https://openalex.org/W1"), "https://openalex.org/W1")

    def test_a_subdomain_of_the_declared_host_is_attributed(self):
        self.assertTrue(self.link("https://api.openalex.org/works/W1"))

    def test_a_third_party_host_is_refused(self):
        self.assertIsNone(self.link("https://evil.example/W1"))

    def test_userinfo_does_not_smuggle_the_declared_host(self):
        self.assertIsNone(self.link("https://openalex.org@evil.example/W1"))
        self.assertIsNone(self.link("https://evil.example@openalex.org/W1"))

    def test_a_template_that_is_an_identifier_needs_a_host_list(self):
        """Une table qui oublie la liste d'hôtes est refusée au chargement."""
        directory = scratch("policy")
        policy = directory / "DATA_POLICY.md"
        policy.write_text(
            "```json\n" + json.dumps({
                "attribution": {"openalex": {"label": "OpenAlex", "url_template": "{id}"}}
            }) + "\n```\n", encoding="utf-8")
        with self.assertRaises(check_release.PolicyError):
            check_release.load_policy(policy)

    def test_the_project_policy_declares_the_host_list(self):
        policy = check_release.load_policy(check_release.DEFAULT_POLICY)
        self.assertIn("openalex.org", policy["attribution"]["openalex"]["hosts"])


class UrlHardeningTest(unittest.TestCase):
    """A5-5 : les contournements que l'audit 5 a fait passer."""

    def test_the_addresses_the_audit_slipped_through_are_refused(self):
        for value in ("https://user:pass@example.com/x",
                      "https://example.com\\@evil.example/x",
                      "https://example.com:99999/x",
                      "https://example.com:0/x",
                      "http://127.0.0.1/x",
                      "http://localhost/x",
                      "http://10.0.0.5/x",
                      "https://example.com/%252E%252E/x"):
            self.assertFalse(check_release.is_resolvable_url(value), value)

    def test_a_quadruply_encoded_traversal_is_refused(self):
        """Audit 6 : `%2525252E` ne rend son point qu'au quatrième décodage."""
        self.assertFalse(check_release.is_resolvable_url(
            "https://example.com/%2525252E%2525252E/x"))
        self.assertFalse(check_release.is_safe_identifier("%2525252E%2525252E"))
        self.assertFalse(check_release.is_safe_identifier("%25255C"))
        self.assertEqual(check_release._fully_unquoted("%2525252E"), ".")

    def test_the_identifiers_of_the_corpus_stay_safe(self):
        for value in ("011209895", "W2000000000",
                      "10.1017/S0022046900001234", "oai:HAL:hal-01234v1"):
            self.assertTrue(check_release.is_safe_identifier(value), value)

    def test_the_addresses_of_the_corpus_still_resolve(self):
        for value in ("https://ixtheo.de/Record/011209895",
                      "https://doi.org/10.1017/S0022046900001234",
                      "https://hdl.handle.net/10670/1.abcdef",
                      "https://openalex.org/W2000000000",
                      "https://example.com:443/x"):
            self.assertTrue(check_release.is_resolvable_url(value), value)


class RemapGuardTest(unittest.TestCase):
    """A5-3 : un report qui ne reporte presque rien n'écrit rien."""

    def build(self, resolved):
        directory = scratch("remap")
        tags = directory / "tags.jsonl"
        with tags.open("w", encoding="utf-8") as handle:
            for index in range(20):
                handle.write(json.dumps({"notice_id": "OLD%02d" % index,
                                         "relevance": "core"}) + "\n")
        table = {"map": {"OLD%02d" % index: [{"id": "NEW%02d" % index}]
                         for index in range(resolved)}}
        map_path = directory / "map.json"
        map_path.write_text(json.dumps(table), encoding="utf-8")
        corpus = directory / "corpus.jsonl"
        with corpus.open("w", encoding="utf-8") as handle:
            for index in range(20):
                handle.write(json.dumps({"origenality_id": "NEW%02d" % index}) + "\n")
        return directory, map_path, tags, corpus

    def test_one_lucky_match_out_of_twenty_does_not_authorise_a_rewrite(self):
        directory, map_path, tags, corpus = self.build(resolved=1)
        before = tags.read_bytes()
        with self.assertRaises(SystemExit) as raised:
            remap_tag_ids.apply_map(map_path, tags, corpus, tags)
        self.assertIn("REFUS", str(raised.exception))
        self.assertEqual(tags.read_bytes(), before)

    def test_force_assumes_the_loss_and_leaves_a_backup(self):
        directory, map_path, tags, corpus = self.build(resolved=1)
        before = tags.read_bytes()
        summary = remap_tag_ids.apply_map(map_path, tags, corpus, tags, force=True)
        self.assertEqual(summary["tags_out"], 1)
        backup = tags.with_suffix(tags.suffix + ".bak")
        self.assertTrue(backup.exists())
        self.assertEqual(backup.read_bytes(), before)

    def test_a_complete_table_passes(self):
        directory, map_path, tags, corpus = self.build(resolved=20)
        summary = remap_tag_ids.apply_map(map_path, tags, corpus, tags)
        self.assertEqual(summary["tags_out"], 20)
        self.assertEqual(summary["resolved_share"], 1.0)


class TagHistoryTest(unittest.TestCase):
    """A5-8 : l'historique est un journal des corrections, pas une pile d'états."""

    def test_two_compactions_do_not_duplicate_the_intermediate_state(self):
        directory = scratch("history")
        tags = directory / "tags.jsonl"
        history = directory / "tags.history.jsonl"

        def append(state):
            with tags.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"notice_id": "OR1", "state": state}) + "\n")

        append("A")
        append("B")
        tags_io.compact(tags, history)
        append("C")
        tags_io.compact(tags, history)

        states = [json.loads(line)["state"]
                  for line in history.read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(states, ["A", "B"])
        current = [json.loads(line)["state"]
                   for line in tags.read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(current, ["C"])


class ProjectionGateTest(unittest.TestCase):
    """A5-9 : un report par titre qui ne tient pas fait échouer la QA."""

    def build(self, receiver_year):
        directory = scratch("projections")
        corpus = directory / "corpus.jsonl"
        rows = [
            {"origenality_id": "ORDONOR", "title": "The letter to Africanus reconsidered",
             "authors": ["Martens, Peter"], "type": "article", "year": 2015},
            {"origenality_id": "ORRECEIVER", "title": "The letter to Africanus reconsidered",
             "authors": ["Martens, Peter"], "type": "article", "year": receiver_year},
        ]
        with corpus.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
        citations = directory / "citations.jsonl"
        cohort = {"decade": "2010s", "type": "article", "lang": "eng"}
        with citations.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps({"origenality_id": "ORDONOR", "cited_by_count": 4,
                                     "measured": True, "count_method": "cluster",
                                     "cohort": cohort, "cohort_rank": 0.5}) + "\n")
            handle.write(json.dumps({"origenality_id": "ORRECEIVER", "cited_by_count": 4,
                                     "measured": True, "count_method": "title-projection",
                                     "cohort": cohort, "cohort_rank": 0.5}) + "\n")
        return citations, corpus

    def test_a_projection_across_two_years_of_a_journal_piece_fails_the_check(self):
        citations, corpus = self.build(receiver_year=2017)
        self.assertEqual(qa_checks.check_projections(citations, corpus), 1)

    def test_a_projection_within_the_same_year_passes(self):
        citations, corpus = self.build(receiver_year=2015)
        self.assertEqual(qa_checks.check_projections(citations, corpus), 0)


# Le constructeur sémantique est sous `site/build-c/tools/` dans le dépôt de
# travail et sous `site/tools/` dans l'arbre public : la passe de publication
# renomme le prototype. Le test cherche donc les deux, et se déclare sauté s'il
# ne trouve ni l'un ni l'autre plutôt que d'échouer sur une géométrie légitime.
BUILD_SEMANTIC = next(
    (path for path in (ROOT / "site" / "build-c" / "tools" / "build_semantic.py",
                       ROOT / "site" / "tools" / "build_semantic.py")
     if path.exists()), None)


@unittest.skipIf(BUILD_SEMANTIC is None, "build_semantic.py absent de cet arbre")
class SiteSemanticInputTest(unittest.TestCase):
    """A5-4 : le constructeur du site ne lit plus la vague 1 reconstruite."""

    SOURCE = BUILD_SEMANTIC.read_text(encoding="utf-8") if BUILD_SEMANTIC else ""

    def test_the_archived_first_wave_is_no_longer_an_input(self):
        """Le chemin de la vague 1 n'est plus construit : il n'est plus que cité."""
        code = "\n".join(line for line in self.SOURCE.splitlines()
                         if "os.path.join" in line or "TAGS" in line)
        self.assertNotIn("pilot", code)
        self.assertNotIn("tags_ixtheo", code)

    def test_the_federated_wave_is_the_input(self):
        self.assertIn("wave2_federated", self.SOURCE)

    @unittest.skipUnless((ROOT / "data" / "merged" / "corpus.jsonl").exists(),
                         "les données de travail ne sont pas dans cet arbre")
    def test_the_build_refuses_a_population_where_a_record_carries_no_tag(self):
        """Itération 8ter : le réservoir ne se remplit plus d'un trou de tuyauterie.

        Contrôle négatif joué sur le fichier de tags amputé de la passe de
        rattrapage : le build sort en 1 et nomme le module qui répare.
        """
        tags = ROOT / "semantic" / "waves" / "wave2_federated" / "tags.jsonl"
        lines = tags.read_text(encoding="utf-8").splitlines()
        with tempfile.TemporaryDirectory() as folder:
            amputated = Path(folder) / "tags.jsonl"
            amputated.write_text("\n".join(lines[:21080]) + "\n", encoding="utf-8")
            command = [sys.executable, str(BUILD_SEMANTIC), "--tags", str(amputated),
                       "--out", str(Path(folder) / "semantic.json")]
            refused = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
            self.assertIn("retag_gaps.py", refused.stdout + refused.stderr)
            self.assertFalse((Path(folder) / "semantic.json").exists())
            allowed = subprocess.run(command + ["--allow-gaps"], capture_output=True, text=True)
            self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)

    def test_the_pages_are_no_longer_read_for_their_counts(self):
        """Itération 8bis : le constructeur n'interroge plus la prose des pages.

        Il lisait `index.html` pour comparer ses comptes à ceux qui y étaient
        tapés, et refusait d'écrire en cas d'écart. Les comptes sortent
        maintenant d'un bloc généré, et la page n'est plus une entrée.
        """
        self.assertNotIn("index.html", self.SOURCE)
        self.assertNotIn("accept-new-counts", self.SOURCE)


SUMMARY_FIGURES = next(
    (path for path in (ROOT / "site" / "build-c" / "tools" / "build_summary_figures.py",
                       ROOT / "site" / "tools" / "build_summary_figures.py")
     if path.exists()), None)

# Les chiffres se REGÉNÈRENT dans le dépôt de travail, où sont le corpus fusionné
# et la couche de données du site. L'arbre public reçoit les pages déjà écrites :
# on y contrôle que les blocs sont balisés, pas qu'ils peuvent être reconstruits
# depuis des données qui n'y sont pas.
WORKING_DATA = ((ROOT / "site" / "data" / "abstracts.json").exists()
                and (ROOT / "data" / "merged" / "corpus.jsonl").exists())


@unittest.skipIf(SUMMARY_FIGURES is None, "build_summary_figures.py absent de cet arbre")
class PublishedFiguresTest(unittest.TestCase):
    """Itération 8bis : aucun chiffre publié n'est tapé à la main."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SUMMARY_FIGURES.parent))
        import build_summary_figures  # noqa: E402
        cls.module = build_summary_figures
        cls.build = SUMMARY_FIGURES.parent.parent

    def test_every_declared_block_is_marked_in_its_page(self):
        for name, page, _builder in self.module.POPULATION_BLOCKS:
            text = (self.build / page).read_text(encoding="utf-8")
            opener, closer = self.module.marks(name)
            self.assertIn(opener, text, "%s sans balise ouvrante dans %s" % (name, page))
            self.assertIn(closer, text, "%s sans balise fermante dans %s" % (name, page))

    @unittest.skipUnless(WORKING_DATA, "les données de travail ne sont pas dans cet arbre")
    def test_the_pages_are_up_to_date(self):
        self.assertEqual(self.module.main(["--check", "--build", str(self.build)]), 0)

    @unittest.skipUnless(WORKING_DATA, "les données de travail ne sont pas dans cet arbre")
    def test_a_hand_edited_figure_is_caught(self):
        """Contrôle négatif : un chiffre retouché sur une copie fait sortir en 1."""
        sys.path.insert(0, str(ROOT / "scripts" / "proofs"))
        import make_stale_pages  # noqa: E402
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / "pages"
            self.assertEqual(make_stale_pages.main([str(copy)]), 0)
            self.assertEqual(self.module.main(["--check", "--build", str(copy)]), 1)


class RetagGapsTest(unittest.TestCase):
    """Itération 8ter : une notice affichée sans tag est un trou, et il se voit."""

    def build(self, folder, corpus, tags, graph_ppns):
        base = Path(folder)
        (base / "graph.json").write_text(json.dumps(
            {"nodes": [{"k": "pub", "ppn": ppn} for ppn in graph_ppns]}), encoding="utf-8")
        (base / "corpus.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in corpus) + "\n",
            encoding="utf-8")
        (base / "tags.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in tags),
            encoding="utf-8")
        return base

    def cluster(self, oid, ppn, **extra):
        record = {"origenality_id": oid, "title": "T " + oid, "relation": "about",
                  "sources": [{"source": "ixtheo-k10plus", "source_id": ppn}]}
        record.update(extra)
        return record

    def run_it(self, base, extra=()):
        return retag_gaps.main([
            "--graph", str(base / "graph.json"),
            "--corpus", str(base / "corpus.jsonl"),
            "--tags", str(base / "tags.jsonl"),
            "--out", str(base / "notices.jsonl"),
            "--report", str(base / "gaps.json"), *extra])

    def test_a_tagged_population_leaves_no_gap(self):
        with tempfile.TemporaryDirectory() as folder:
            base = self.build(folder, [self.cluster("OR1", "p1")],
                              [{"notice_id": "OR1", "relevance": "core"}], ["p1"])
            self.assertEqual(self.run_it(base, ["--check"]), 0)
            report = json.loads((base / "gaps.json").read_text(encoding="utf-8"))
            self.assertEqual(report["notices_without_tag"], 0)

    def test_an_untagged_notice_is_reported_and_written_out(self):
        with tempfile.TemporaryDirectory() as folder:
            base = self.build(folder,
                              [self.cluster("OR1", "p1"), self.cluster("OR2", "p2")],
                              [{"notice_id": "OR1", "relevance": "core"}], ["p1", "p2"])
            self.assertEqual(self.run_it(base, ["--check"]), 1)
            report = json.loads((base / "gaps.json").read_text(encoding="utf-8"))
            self.assertEqual(report["notices_without_tag"], 1)
            written = [json.loads(line) for line
                       in (base / "notices.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([r["origenality_id"] for r in written], ["OR2"])

    def test_the_last_line_of_a_retag_closes_the_gap(self):
        """Le relevé lit les tags en dernier-écrit-gagne, comme l'arbre et le site."""
        with tempfile.TemporaryDirectory() as folder:
            base = self.build(folder, [self.cluster("OR1", "p1")],
                              [{"notice_id": "OR0", "relevance": "none"},
                               {"notice_id": "OR1", "relevance": "marginal"}], ["p1"])
            self.assertEqual(self.run_it(base, ["--check"]), 0)

    def test_the_three_causes_are_told_apart(self):
        with tempfile.TemporaryDirectory() as folder:
            corpus = [self.cluster("ORa", "pa", noise_guess=True),
                      self.cluster("ORb", "pb", relation="by"),
                      self.cluster("ORc", "pc")]
            base = self.build(folder, corpus, [], ["pa", "pb", "pc"])
            (base / "old.tsv").write_text("ORa\tixtheo-k10plus:pa\nORb\tixtheo-k10plus:pb\n",
                                          encoding="utf-8")
            self.assertEqual(self.run_it(base, ["--old-ids", str(base / "old.tsv")]), 0)
            report = json.loads((base / "gaps.json").read_text(encoding="utf-8"))
            self.assertEqual(report["clusters_by_cause"],
                             {"noise_guess": 1, "relation-by": 1, "identifiant-neuf": 1})

    def test_a_cluster_carrying_several_notices_counts_them_all(self):
        with tempfile.TemporaryDirectory() as folder:
            record = self.cluster("OR1", "p1")
            record["sources"].append({"source": "ixtheo-k10plus", "source_id": "p2"})
            base = self.build(folder, [record], [], ["p1", "p2"])
            self.assertEqual(self.run_it(base), 0)
            report = json.loads((base / "gaps.json").read_text(encoding="utf-8"))
            self.assertEqual(report["clusters_without_tag"], 1)
            self.assertEqual(report["notices_without_tag"], 2)


# ---------------------------------------------------------------------------
# Corrections portées depuis le dépôt frère (2026-08-20)
# ---------------------------------------------------------------------------

class MalformedLineTest(unittest.TestCase):
    """Une ligne illisible est comptée et rendue, jamais avalée.

    C'était le seul endroit d'un dispositif fondé sur « rien ne disparaît » où
    quelque chose disparaissait : `iter_lines` sautait la ligne en silence, et
    un fichier tronqué par une interruption passait pour un fichier propre.
    """

    def written(self, lines):
        directory = scratch("malformed")
        path = directory / "tags.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_a_truncated_line_is_counted_and_named(self):
        path = self.written([
            json.dumps({"notice_id": "OR1", "themes": ["a"]}),
            '{"notice_id": "OR2", "themes": ["b"',
            json.dumps({"notice_id": "OR3", "themes": ["c"]}),
        ])
        self.assertEqual(tags_io.malformed_lines(path), [2])
        self.assertEqual([r["notice_id"] for r in tags_io.read_tags(path)], ["OR1", "OR3"])

    def test_a_json_line_that_is_not_an_object_is_malformed_too(self):
        """`.get` sur une liste casserait plus loin, là où on ne saurait plus où."""
        path = self.written([json.dumps({"notice_id": "OR1"}), json.dumps([1, 2]),
                             json.dumps("texte")])
        self.assertEqual(tags_io.malformed_lines(path), [2, 3])

    def test_a_clean_file_reports_nothing(self):
        path = self.written([json.dumps({"notice_id": "OR1"}),
                             json.dumps({"notice_id": "OR2"})])
        self.assertEqual(tags_io.malformed_lines(path), [])
        self.assertEqual(tags_io.compact(path)["malformed"], [])

    def test_compaction_reports_the_broken_line_instead_of_erasing_it(self):
        path = self.written([
            json.dumps({"notice_id": "OR1", "v": 1}),
            '{"notice_id": "OR1", "v"',
            json.dumps({"notice_id": "OR1", "v": 2}),
        ])
        report = tags_io.compact(path)
        self.assertEqual(report["malformed"], [2])
        self.assertEqual(report["superseded"], 1)

    def test_the_waves_of_this_repository_carry_none(self):
        """La correction est sûre parce qu'elle ne change rien d'observable ici."""
        for path in sorted((ROOT / "semantic" / "waves").glob("*/tags.jsonl")):
            self.assertEqual(tags_io.malformed_lines(path), [], str(path))


class PromptDigestTest(unittest.TestCase):
    """La reprise ne fait plus confiance à `prompt_version` seul.

    Retoucher la consigne sans bumper la version mélangeait deux règles dans une
    même vague sans laisser de trace. Le contrôle est ADDITIF : les
    enregistrements écrits avant que le champ n'existe restent valides.
    """

    NOTICE = {"source": "ixtheo-k10plus", "source_id": "883455439",
              "title": "Contra Celsum", "relation": "about"}

    def written(self, **extra):
        directory = scratch("digest")
        path = directory / "tags.jsonl"
        row = {
            "notice_id": tag_notices.notice_identifier(self.NOTICE),
            "input_digest": tag_notices.payload_digest(
                tag_notices.notice_payload(self.NOTICE)),
            "wave": "w", "prompt_version": "tag-notice-v2.1",
            "vocabulary_version": "v1",
        }
        row.update(extra)
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")
        return path

    def test_the_digest_follows_the_rendered_vocabulary_not_the_version_tag(self):
        vocab = load_vocabulary(ROOT / "semantic" / "vocabulary")
        first = tag_notices.prompt_digest(tag_notices.system_prompt(vocab))
        self.assertEqual(first, tag_notices.prompt_digest(tag_notices.system_prompt(vocab)))
        altered = tag_notices.system_prompt(vocab) + "\nune règle de plus."
        self.assertNotEqual(first, tag_notices.prompt_digest(altered))

    def test_a_record_written_under_another_prompt_is_not_done(self):
        path = self.written(prompt_digest="aaaaaaaaaaaaaaaa")
        done = tag_notices.already_tagged(path, "w", "tag-notice-v2.1", "v1",
                                          "bbbbbbbbbbbbbbbb")
        self.assertEqual(done, set())

    def test_the_same_digest_still_counts_as_done(self):
        path = self.written(prompt_digest="aaaaaaaaaaaaaaaa")
        done = tag_notices.already_tagged(path, "w", "tag-notice-v2.1", "v1",
                                          "aaaaaaaaaaaaaaaa")
        self.assertIn(tag_notices.resume_key(self.NOTICE), done)

    def test_a_legacy_record_without_a_digest_is_not_invalidated(self):
        """Additif : 21 104 lignes existantes n'en portent pas."""
        path = self.written()
        done = tag_notices.already_tagged(path, "w", "tag-notice-v2.1", "v1",
                                          "bbbbbbbbbbbbbbbb")
        self.assertIn(tag_notices.resume_key(self.NOTICE), done)

    def test_a_reject_follows_the_same_rule(self):
        directory = scratch("digest-rejets")
        path = directory / "rejects.jsonl"
        base = {"notice_id": tag_notices.notice_identifier(self.NOTICE),
                "input_digest": tag_notices.payload_digest(
                    tag_notices.notice_payload(self.NOTICE)),
                "wave": "w", "prompt_version": "tag-notice-v2.1",
                "vocabulary_version": "v1", "stage": "validate"}
        path.write_text(json.dumps(dict(base, prompt_digest="aaaaaaaaaaaaaaaa")) + "\n",
                        encoding="utf-8")
        self.assertEqual(
            tag_notices.already_rejected(path, "w", "tag-notice-v2.1", "v1", "cccccccccccccccc"),
            set())
        path.write_text(json.dumps(base) + "\n", encoding="utf-8")
        self.assertIn(
            tag_notices.resume_key(self.NOTICE),
            tag_notices.already_rejected(path, "w", "tag-notice-v2.1", "v1", "cccccccccccccccc"))

    def test_the_field_is_declared_by_the_schema(self):
        """`additionalProperties: false` : un champ non déclaré invaliderait la ligne."""
        vocab = load_vocabulary(ROOT / "semantic" / "vocabulary")
        schema = tag_record_schema(vocab, full=True)
        self.assertIn("prompt_digest", schema["properties"])
        self.assertNotIn("prompt_digest", schema["required"])


class SchemaGenerationTest(unittest.TestCase):
    """Une seule fonction rend le schéma du moteur et le schéma publié.

    Les marqueurs `x-enum-source` tenaient les énumérations ensemble ; le reste
    divergeait, et de fait `uniqueItems` et les bornes de `confidence`
    n'existaient que du côté publié.
    """

    @classmethod
    def setUpClass(cls):
        cls.vocab = load_vocabulary(ROOT / "semantic" / "vocabulary")

    def test_the_published_file_is_up_to_date(self):
        self.assertEqual(
            build_tag_schema.main(["--check", "--out",
                                   str(ROOT / "semantic" / "vocabulary" / "tag_record.schema.json")]),
            0)

    def test_the_engine_schema_carries_the_same_constraints_as_the_published_one(self):
        engine = tag_record_schema(self.vocab)
        published = resolve(tag_record_schema(self.vocab, full=True), self.vocab)
        for name in engine["properties"]:
            self.assertEqual(engine["properties"][name], published["properties"][name], name)

    def test_the_constraints_that_used_to_exist_on_one_side_only(self):
        engine = tag_record_schema(self.vocab)
        for axis in ("works", "themes", "approaches"):
            self.assertTrue(engine["properties"][axis]["uniqueItems"], axis)
        self.assertEqual(engine["properties"]["confidence"]["minimum"], 0)
        self.assertEqual(engine["properties"]["confidence"]["maximum"], 1)
        self.assertEqual(engine["properties"]["justification"]["maxLength"], 300)

    def test_the_enums_come_from_the_vocabulary_and_not_from_the_file(self):
        engine = tag_record_schema(self.vocab)
        self.assertEqual(engine["properties"]["themes"]["items"]["enum"], self.vocab.theme_ids)
        self.assertNotIn("x-enum-source", engine["properties"]["themes"]["items"])
        published = tag_record_schema(self.vocab, full=True)
        self.assertIn("x-enum-source", published["properties"]["themes"]["items"])

    def test_a_stale_published_file_is_named_and_fails(self):
        directory = scratch("schema-perime")
        vocabulary = directory / "vocabulary"
        vocabulary.mkdir(parents=True)
        for name in ("works.json", "themes.json", "approaches.json", "relevance.json"):
            (vocabulary / name).write_text(
                (ROOT / "semantic" / "vocabulary" / name).read_text(encoding="utf-8"),
                encoding="utf-8")
        stale = tag_record_schema(self.vocab, full=True)
        stale["properties"]["confidence"].pop("maximum")
        (vocabulary / "tag_record.schema.json").write_text(
            json.dumps(stale, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        tags = directory / "tags.jsonl"
        tags.write_text("", encoding="utf-8")
        report = directory / "report.json"
        code = validate_tags.main([str(tags), "--vocabulary", str(vocabulary),
                                   "--report", str(report)])
        self.assertEqual(code, 1)
        self.assertIn("OBSOLÈTE", json.loads(report.read_text(encoding="utf-8"))["schema_state"])


class VocabularyStatusTest(unittest.TestCase):
    """`status` était déclaré et lu par personne : une valeur retirée restait assignable.

    Le contrôle ne change pas la validation. Aujourd'hui toutes les valeurs sont
    actives et il passe ; il parlera le jour où l'une sera retirée.
    """

    def test_the_repository_assigns_no_retired_value(self):
        self.assertEqual(qa_checks.check_vocabulary(), 0)

    def test_a_retired_value_still_assigned_fails_the_check(self):
        directory = scratch("statut")
        vocabulary = directory / "vocabulary"
        vocabulary.mkdir(parents=True)
        for name in ("works.json", "approaches.json", "relevance.json"):
            (vocabulary / name).write_text(
                (ROOT / "semantic" / "vocabulary" / name).read_text(encoding="utf-8"),
                encoding="utf-8")
        themes = json.loads(
            (ROOT / "semantic" / "vocabulary" / "themes.json").read_text(encoding="utf-8"))
        retired = sorted(themes["themes"])[0]
        themes["themes"][retired]["status"] = "retired"
        (vocabulary / "themes.json").write_text(
            json.dumps(themes, ensure_ascii=False), encoding="utf-8")

        waves = directory / "waves" / "wave"
        waves.mkdir(parents=True)
        (waves / "tags.jsonl").write_text(
            json.dumps({"notice_id": "OR1", "themes": [retired],
                        "relevance": "core", "works": ["unspecified"],
                        "approaches": ["exegetical"]}) + "\n", encoding="utf-8")

        self.assertEqual(
            qa_checks.check_vocabulary(directory / "waves", vocabulary), 1)
        # la même valeur restée active ne dit rien
        themes["themes"][retired]["status"] = "active"
        (vocabulary / "themes.json").write_text(
            json.dumps(themes, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(
            qa_checks.check_vocabulary(directory / "waves", vocabulary), 0)


class HarvestStemBoundaryTest(unittest.TestCase):
    """Les radicaux de la moisson mordent sur les flexions, jamais sur un autre mot.

    Le dépôt frère avait un motif sans borne à droite : « The Reception of Paulo
    Freire » passait pour une étude de réception paulinienne. Ici la borne
    manquante d'`ES_ORIGINS` est délibérée — elle sert à attraper « orígenes
    históricos », « orígenes doctrinales » —, et la poser ferait perdre au filtre
    de bruit des titres espagnols qu'il attrape aujourd'hui. Ce test fixe les
    deux sens pour qu'une correction de confort ne les défasse pas.
    """

    def keeps(self, title, language="es"):
        return build_openalex.classify(title, "", language, "", [])

    def test_the_spanish_common_noun_is_still_caught_with_its_inflections(self):
        for title in ("Origenes historicos de Cataluña",
                      "Los origenes doctrinales del franquismo",
                      "El origen historico del retorno cooperativo"):
            self.assertEqual(self.keeps(title)[0], True, title)

    def test_a_patristic_indicator_wins_over_the_spanish_noun(self):
        self.assertEqual(self.keeps("Orígenes de Alejandría y el Contra Celsum")[0], False)

    def test_the_noun_filter_only_fires_on_spanish_portuguese_catalan(self):
        self.assertIsNone(self.keeps("Origenes der Christ und Origenes der Platoniker",
                                     language="de")[0])

    def test_no_patristic_stem_bites_into_an_unrelated_word(self):
        """« aborígenes » est le faux ami de la racine ; aucun motif ne doit l'attraper."""
        for title in ("Los aborigenes de la Patagonia", "Aborígenes australianos"):
            self.assertIsNone(build_openalex.PATRISTIC_TXT.search(build_openalex.fold(title)),
                              title)
            self.assertFalse(harvest_common.has_orig_strict(title), title)


# --------------------------------------------------------------------------
# Couche de données reconstruite (audit du 13 septembre 2026)
# --------------------------------------------------------------------------

TOOLS_DIR = (ROOT / "site" / "build-c" / "tools" if (ROOT / "site" / "build-c" / "tools").is_dir()
             else ROOT / "site" / "tools")


def site_data_dir() -> Path:
    sys.path.insert(0, str(TOOLS_DIR))
    from tree_paths import data_dir  # noqa: E402
    return Path(data_dir(str(ROOT)))


def read_json_lines(path: Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


class SnapshotFieldCoverageTest(unittest.TestCase):
    """OR-01, OR-07, OR-44, OR-46 : le snapshot d'entrée ne se reconstruit plus sur
    les arêtes du graphe, qui n'existent qu'au-dessus des seuils (3 et 5) ; une
    reconstruction qui ferait chuter la couverture d'un champ est refusée."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(TOOLS_DIR))
        import build_public_snapshot  # noqa: E402
        import build_site_data  # noqa: E402
        cls.snapshot = build_public_snapshot
        cls.site = build_site_data
        cls.data = site_data_dir()

    @staticmethod
    def row(key, **fields):
        source, identifier = key.split(":", 1)
        base = {"origenality_id": key, "source": source, "source_id": identifier,
                "sources": [{"source": source, "source_id": identifier}],
                "title": "Titel " + identifier, "authors": ["Autor, A"], "year": 1977,
                "subjects": [], "container": None, "published_snapshot": True}
        base.update(fields)
        return base

    def test_a_heading_and_a_container_used_once_survive_the_snapshot_and_the_stats(self):
        rows = [self.row("ixtheo-k10plus:011209895", container="Regensburger Studien"),
                self.row("k10plus:1", subjects=["Priester"])]
        catalogue = {"ixtheo-k10plus:011209895": {
            "source_id": "011209895", "relation": "about", "subjects": ["Origenes", "Apostel"],
            "subject_chains": ["Priester"],
            "container": {"type": "series", "title": "Regensburger Studien zur Theologie"}}}
        refreshed = self.snapshot.refresh(rows, catalogue, {}, {})
        self.assertEqual(refreshed[0]["subjects_container_basis"], "catalogue-record")
        self.assertEqual(refreshed[0]["container"],
                         {"title": "Regensburger Studien zur Theologie", "type": "series"})
        self.assertEqual(refreshed[0]["relation"], "about")
        self.assertEqual(refreshed[1]["subjects_container_basis"], "public-projection")
        stats = self.site.build_stats(refreshed, 3, 5)
        self.assertEqual(stats["totals"]["distinct_subjects"], 2)
        self.assertEqual(stats["totals"]["distinct_containers"], 1)
        self.assertEqual(stats["top_containers"][0]["type"], "series")

    def test_a_rebuild_without_the_harvest_keeps_what_the_harvest_gave(self):
        catalogue = {"ixtheo-k10plus:1": {"source_id": "1", "relation": "both",
                                          "subjects": ["Apostel"],
                                          "container": {"title": "Adamantius", "type": "host"}}}
        once = self.snapshot.refresh([self.row("ixtheo-k10plus:1")], catalogue, {}, {})
        self.assertEqual(self.snapshot.refresh(once, {}, {}, {}), once)

    def test_the_release_graph_gives_back_relation_and_container_type(self):
        graph = {"nodes": [{"k": "pub", "src": ["k10plus"], "ppn": "7", "rel": "both"},
                           {"k": "container", "label": "Adamantiana", "ctype": "series"}],
                 "edges": [{"s": 0, "t": 1, "r": "in"}]}
        refreshed = self.snapshot.refresh([self.row("k10plus:7", container="Adamantiana")], {},
                                          self.snapshot.release_projection(graph), {})
        self.assertEqual(refreshed[0]["relation"], "both")
        self.assertEqual(refreshed[0]["container"], {"title": "Adamantiana", "type": "series"})

    def test_a_rebuild_that_loses_coverage_is_refused(self):
        before = {"container": 1439, "subjects": 1975, "distinct_headings": 1548}
        self.assertEqual(self.snapshot.coverage_drops(before, dict(before)), [])
        self.assertEqual(len(self.snapshot.coverage_drops(
            before, {"container": 749, "subjects": 1975, "distinct_headings": 478})), 2)

    def test_the_shipped_snapshot_is_current_and_matches_its_manifest(self):
        rows = read_json_lines(self.data / "site-records.jsonl")
        manifest = json.loads((self.data / "BUILD.json").read_text(encoding="utf-8"))
        self.assertEqual(self.snapshot.coverage(rows), manifest["field_coverage"])
        # Un clone n'a ni la moisson IxTheo ni la relecture : le contrôle n'y vérifie que
        # la structure, et doit le dire (C-3). L'arbre de travail contrôle le contenu.
        harvests = self.snapshot.IXTHEO_RAW.is_file() or self.snapshot.AUTHORITY_RAW.is_file()
        import contextlib
        import io
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            status = self.snapshot.main(["--check"] if harvests else ["--check", "--structure-only"])
        self.assertEqual(status, 0, buffer.getvalue())
        self.assertIn("derived again" if harvests else "structure only", buffer.getvalue())

    def test_the_shipped_totals_are_counted_without_the_graph_thresholds(self):
        stats = json.loads((self.data / "stats.json").read_text(encoding="utf-8"))
        graph = json.loads((self.data / "graph.json").read_text(encoding="utf-8"))
        kinds, totals = graph["counts"]["nodes_by_kind"], stats["totals"]
        # Signature de la reconstruction par arêtes : autant de sujets et de
        # contenants distincts que de nœuds du graphe (478 et 61 le 24 août).
        self.assertGreater(totals["distinct_subjects"], 2 * kinds["subject"])
        self.assertGreater(totals["distinct_containers"], 2 * kinds["container"])
        self.assertIn("series", {n.get("ctype") for n in graph["nodes"] if n["k"] == "container"})
        self.assertTrue(any(n.get("rel") for n in graph["nodes"] if n["k"] == "pub"))

    def test_the_merge_keeps_the_headings_and_containers_of_the_snapshot(self):
        rows = read_json_lines(self.data / "site-records.jsonl")
        headings = {self.site.norm_key(heading) for row in rows
                    for heading in self.site.clean_headings(self.site.record_subjects(row))}
        containers = {self.site.norm_key(found[0]) for row in rows
                      for found in [self.site.record_container(row)] if found}
        totals = json.loads((self.data / "stats.json").read_text(encoding="utf-8"))["totals"]
        self.assertLessEqual(totals["distinct_subjects"], len(headings))
        self.assertGreaterEqual(totals["distinct_subjects"], MERGE_COVERAGE_FLOOR * len(headings))
        self.assertGreaterEqual(totals["distinct_containers"], MERGE_COVERAGE_FLOOR * len(containers))


# La fusion garde la valeur de la source prioritaire et range les autres en
# conflits : quelques vedettes d'un doublon sortent du compte, jamais une part
# qui se voie.
MERGE_COVERAGE_FLOOR = 0.95


class GeneratedFiguresTest(unittest.TestCase):
    """OR-36, OR-37, OR-38, OR-45, OR-49, OR-71, OR-72, OR-09, OR-32, OR-39."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(TOOLS_DIR))
        import build_summary_figures  # noqa: E402
        cls.f = build_summary_figures
        cls.build = Path(build_summary_figures.BUILD)
        cls.values = build_summary_figures.population(cls.build)
        cls.corpus = build_summary_figures.corpus_figures(cls.build)
        cls.meta = json.loads((Path(build_summary_figures.DATA) / "META.json")
                              .read_text(encoding="utf-8"))

    def test_a_count_of_one_takes_the_singular(self):
        import re
        values = dict(self.values, aside=1, mentioned=1, aside_classed=1, aside_untagged=0,
                      duplicates=1)
        corpus = dict(self.corpus, multi_source=1, tag_disagreements=1, with_publisher=1,
                      primary_before_1001=1, primary_set_aside=1, primary_undated=1)
        f = self.f
        text = " ".join([f.observatory_lede_block(values), f.observatory_reservoir_block(values),
                         f.method_bias_block(values), f.method_counted_block(values),
                         f.method_merge_block(values), f.method_dedup_block(values, corpus),
                         f.identifier_coverage_block(corpus), f.primary_dates_block(corpus),
                         f.primary_undated_block(corpus)])
        for wrong in (r"\b1 records\b", r"\b1 are\b", r"\b1 mention\b", r"\b1 clusters\b",
                      r"\b1 duplicates\b", r"\b1 name\b", r"\b1 records predate\b",
                      r"\b1 records carry\b", r"One implausible dates"):
            self.assertIsNone(re.search(wrong, text), wrong)

    def test_harvested_names_the_catalogue_records_on_every_page(self):
        import re
        pattern = re.compile(r"(\d[\d  ]*)\s+(?:catalogue\s+|source\s+)?records\s+harvested"
                             r"|of\s+the\s+(\d[\d  ]*)\s+harvested|harvest\s+of\s+(\d[\d  ]*)")
        found = []
        for page in ("index.html", "observatoire.html", "methode.html", "credits.html"):
            text = (self.build / page).read_text(encoding="utf-8")
            for match in pattern.finditer(text):
                number = next(group for group in match.groups() if group)
                found.append((page, int(re.sub(r"\D", "", number))))
        self.assertTrue(found)
        self.assertEqual({number for _, number in found}, {self.meta["records_harvested_total"]},
                         found)

    def test_every_source_row_is_generated_and_sums_to_the_harvest(self):
        import re
        by_source = self.meta["sources_harvested"]
        self.assertEqual(sum(by_source.values()), self.meta["records_harvested_total"])
        for page, skipped in (("methode.html", ()), ("credits.html", ("ixtheo-k10plus",))):
            text = (self.build / page).read_text(encoding="utf-8")
            shown = {match.group(1): int(re.sub(r"\D", "", match.group(2))) for match in
                     re.finditer(r"<!-- FIGURES:source-count-([a-z0-9-]+) -->([\d  ]+)<!--", text)}
            self.assertEqual(shown, {key: value for key, value in by_source.items()
                                     if key not in skipped}, page)

    def test_a_summary_is_credited_to_its_own_catalogue_or_to_another_base(self):
        values = self.f.figures()
        self.assertEqual(values["written_by_the_catalogue"] + values["written_elsewhere"],
                         values["with_abstract"])
        self.assertFalse(set(values["own_labels"]) & set(values["other_labels"]))

    def test_english_pages_put_no_space_before_a_colon(self):
        import re
        for page in ("methode.html", "credits.html", "observatoire.html", "index.html",
                     "welcome.html"):
            text = (self.build / page).read_text(encoding="utf-8")
            text = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", text,
                          flags=re.S)
            text = re.sub(r"<[^>]+>", " ", text)
            self.assertIsNone(re.search(r"\w\s+:\s", text), page)

    def test_the_published_figure_blocks_are_current(self):
        result = subprocess.run([sys.executable, str(TOOLS_DIR / "build_summary_figures.py"),
                                 "--check"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr[-800:])

    def test_the_citation_data_is_current(self):
        """F5 : data/cite.json est ce que build_cite_data.py écrirait du corpus fusionné."""
        result = subprocess.run([sys.executable, str(TOOLS_DIR / "build_cite_data.py"), "--check"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout[-800:] + result.stderr[-800:])

    def test_llms_names_the_sources_from_the_data_and_keeps_the_section_for_programs(self):
        text = (ROOT / "llms.txt").read_text(encoding="utf-8")
        self.assertIn("## For programs", text)
        self.assertNotIn("one catalogue", text)
        labels = self.meta["sources_present"]
        self.assertIn("draws %s source labels" % self.f.number_word(len(labels)), text)
        for entry in labels:
            self.assertIn(self.f.english_label(entry["label"]), text)


class LanguageCodeTest(unittest.TestCase):
    """OR-47, OR-48, OR-57 : un seul schéma de codes, un libellé pour chacun."""

    def test_every_code_the_normaliser_returns_has_a_label(self):
        import build_site_data  # noqa: E402
        import fields  # noqa: E402
        codes = set(fields.ISO2_TO_ISO1.values()) | set(fields.LANG_NAMES.values())
        for code in codes:
            self.assertIn(code, build_site_data.LANG_LABELS, code)
            self.assertNotEqual(build_site_data.LANG_LABELS[code][0], code)
        for key in build_site_data.LANG_LABELS:
            self.assertFalse(fields.ISO2_TO_ISO1.get(key, key) != key, key)

    def test_armenian_reaches_its_iso_639_1_code(self):
        import fields  # noqa: E402
        self.assertEqual(fields.norm_lang("arm"), "hy")
        self.assertEqual(fields.norm_lang("hye"), "hy")

    def test_the_shipped_layers_carry_no_raw_code(self):
        sys.path.insert(0, str(TOOLS_DIR))
        import build_primary_layer  # noqa: E402
        import fields  # noqa: E402
        data = site_data_dir()
        raw_codes = {key for key, value in fields.ISO2_TO_ISO1.items() if key != value}
        stats = json.loads((data / "stats.json").read_text(encoding="utf-8"))
        for entry in stats["by_language"]:
            self.assertNotEqual(entry["label_en"], entry["code"])
        graph = json.loads((data / "graph.json").read_text(encoding="utf-8"))
        self.assertFalse({n.get("lang") for n in graph["nodes"] if n["k"] == "pub"} & raw_codes)
        layer = read_json_lines(data / "primary-layer.jsonl")
        self.assertFalse({row.get("language") for row in layer} & raw_codes)
        self.assertEqual(build_primary_layer.main(["--check"]), 0)


class MetaProvenanceTest(unittest.TestCase):
    """OR-08, OR-35, OR-36, OR-51."""

    def test_a_tags_file_outside_the_repository_publishes_no_path(self):
        import build_site_data  # noqa: E402
        outside = build_site_data.published_tags_path(
            "/tmp/origenality-harvest/classify/build/tags_combine.jsonl", str(ROOT))
        self.assertEqual(outside, "tags_combine.jsonl")
        inside = build_site_data.published_tags_path(
            str(ROOT / "site" / "data" / "site-merged" / "tags.jsonl"), str(ROOT))
        self.assertEqual(inside, "data/site-merged/tags.jsonl")

    def test_the_editions_set_aside_come_from_the_primary_layer(self):
        data = site_data_dir()
        meta = json.loads((data / "META.json").read_text(encoding="utf-8"))
        summary = json.loads((data / "primary-layer-summary.json").read_text(encoding="utf-8"))
        manifest = json.loads((data / "BUILD.json").read_text(encoding="utf-8"))
        self.assertGreater(meta["excluded"]["relation_by"], 0)
        self.assertEqual(meta["excluded"]["relation_by"], summary["records"])
        self.assertEqual(meta["records_harvested_total"], sum(meta["sources_harvested"].values()))
        self.assertEqual(meta["records_harvested_total"], manifest["source_records"])
        self.assertEqual(meta["records"], manifest["work_clusters"])
        self.assertNotIn("..", meta.get("tags") or "")


class PopulationCaptureTest(unittest.TestCase):
    """Une capture sans la bande des trois ensembles de l'Observatoire ne passe plus en silence."""

    def test_a_capture_without_the_band_of_sets_is_refused(self):
        import importlib.util
        # site/build-c/qa dans l'arbre de travail, site/qa dans un clone public
        path = TOOLS_DIR.parent / "qa" / "check_one_population.py"
        spec = importlib.util.spec_from_file_location("check_one_population", path)
        check = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(check)
        captures = sorted((TOOLS_DIR.parent / "qa").glob("measured_*.json"))
        measured = json.loads(captures[-1].read_text(encoding="utf-8"))
        exp = check.expected(*check.load())
        problems = []
        check.compare(exp, measured, problems)
        self.assertEqual(problems, [])
        measured["observatory_sets"] = []
        problems = []
        check.compare(exp, measured, problems)
        self.assertTrue(any("three sets" in problem for problem in problems), problems)


class SitemapDatesTest(unittest.TestCase):
    """OR-69 : la date d'un document suit son contenu, pas la construction."""

    def test_an_unchanged_document_keeps_its_date_when_the_build_moves(self):
        import build_seo_assets  # noqa: E402
        scratch = ROOT / "data" / "_proofs_tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            path = Path(folder) / "doc.md"
            path.write_text("stable", encoding="utf-8")
            dates: dict = {}
            date_of = build_seo_assets.content_date
            self.assertEqual(date_of("/doc.md", path, dates, "2026-08-16"), ("2026-08-16", True))
            self.assertEqual(date_of("/doc.md", path, dates, "2026-09-13"), ("2026-08-16", False))
            path.write_text("changed", encoding="utf-8")
            self.assertEqual(date_of("/doc.md", path, dates, "2026-09-13"), ("2026-09-13", True))


class PagesAuditTest(unittest.TestCase):
    """Audit du 13/09, lot pages : OR-06, OR-10, OR-40, OR-41, OR-73, OR-74, OR-76,
    OR-77, le JSON-LD de la page de méthode et les croisements de l'Observatoire."""

    @classmethod
    def setUpClass(cls):
        cls.build = TOOLS_DIR.parent
        cls.assets = cls.build / "assets"
        cls.data = site_data_dir()

    def read(self, name):
        return (self.build / name).read_text(encoding="utf-8")

    @staticmethod
    def blocks(css, query):
        """Le contenu des @media dont la condition contient `query`."""
        out, start = [], 0
        while True:
            start = css.find("@media", start)
            if start < 0:
                return out
            brace = css.find("{", start)
            depth, end = 1, brace + 1
            while depth:
                depth += {"{": 1, "}": -1}.get(css[end], 0)
                end += 1
            if query in css[start:brace]:
                out.append(css[brace + 1:end - 1])
            start = end

    @staticmethod
    def rgb(colour):
        return tuple(int(colour[k:k + 2], 16) for k in (1, 3, 5))

    def contrast(self, fg, bg):
        def luminance(value):
            channels = [c / 255 for c in (self.rgb(value) if isinstance(value, str) else value)]
            lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
            return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
        high, low = sorted((luminance(fg), luminance(bg)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    def test_the_observatory_names_languages_by_the_codes_of_the_data(self):
        """OR-06 : la page lisait eng/ger quand graph.json porte en/de, tout tombait dans « autre »."""
        import collections
        import re
        script = self.read("assets/observatory.js")
        legend = re.search(r"var LANGS = \[(.*?)\];", script, re.S).group(1)
        named = [code for code in re.findall(r"code:\s*'([a-z]+)'", legend) if code != "oth"]
        graph = json.loads((self.data / "graph.json").read_text(encoding="utf-8"))
        tags = json.loads((self.assets / "semantic.json").read_text(encoding="utf-8"))["byPpn"]
        counted = [node for node in graph["nodes"] if node.get("k") == "pub"
                   and (tags.get(node.get("ppn")) or {}).get("r") in ("core", "partial")]
        languages = collections.Counter(node.get("lang") for node in counted)
        for code in named:
            self.assertGreater(languages.get(code, 0), 0, code)
        other = sum(number for code, number in languages.items() if code not in named)
        self.assertLess(other / len(counted), 0.25, other)

    def test_source_counts_on_the_observatory_come_from_meta(self):
        """OR-10, OR-39 : « one source, IxTheo », puis « Eight source labels » à côté de « Seven catalogues »."""
        import re
        script = self.read("assets/observatory.js")
        for stale in ("IxTheo", "one source", "build of"):
            self.assertNotIn(stale, script)
        self.assertIn("meta.sources_present", script)
        page = re.sub(r"<!-- (FIGURES:[\w-]+) -->.*?<!-- /\1 -->", " ", self.read("observatoire.html"),
                      flags=re.S)
        numbers = r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|sixteen|\d+"
        self.assertIsNone(re.search(r"\b(%s)\s+(source labels|catalogues|domains)\b" % numbers, page, re.I))

    def test_the_method_json_ld_agrees_with_the_data(self):
        """Le JSON-LD disait 1677/2026 quand stats.json commence en 1514."""
        import re
        sys.path.insert(0, str(TOOLS_DIR))
        import build_summary_figures  # noqa: E402
        page = self.read("methode.html")
        block = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S).group(1)
        dataset = next(item for item in json.loads(block)["@graph"] if item.get("@type") == "Dataset")
        # La couverture est celle des notices comptées : 1514, l'année (fausse) d'une notice
        # marginale, ouvrait la couverture quand les notices comptées commencent en 1639.
        totals = json.loads((self.data / "stats.json").read_text(encoding="utf-8"))["counted"]["totals"]
        meta = json.loads((self.data / "META.json").read_text(encoding="utf-8"))
        self.assertEqual(dataset["temporalCoverage"], "%s/%s" % (totals["year_min"], totals["year_max"]))
        self.assertIn("under %s source labels"
                      % build_summary_figures.number_word(len(meta["sources_present"])),
                      dataset["description"])

    def test_the_landing_plate_and_canvas_share_one_framing(self):
        """OR-40, OR-73 : la plaque fixe et le canevas lisaient deux cadrages, choisis par la largeur seule."""
        script = self.read("assets/landing.js")
        css = self.read("assets/landing.css")
        self.assertIn("getPropertyValue('--focus-x')", script)
        self.assertIn("getPropertyValue('--focus-y')", script)
        self.assertNotRegex(script, r"focus:\s*narrow\s*\?")
        portrait = "".join(self.blocks(css, "(max-aspect-ratio:1/1)"))
        self.assertRegex(portrait, r"--focus-x:\.24;--focus-y:\.34")
        framing = css[css.index("@supports (height:1svh)"):]
        # les unités cqh et cqw ont été mesurées à une hauteur nulle dans Chrome
        self.assertNotRegex(framing, r"\dcq[hw]")
        self.assertIn("var(--focus-x)", framing)
        self.assertIn("var(--focus-y)", framing)
        self.assertIn("@media (min-width:761px) and (min-aspect-ratio:1/1)", css)

    def test_the_landing_requests_three_only_when_motion_is_allowed(self):
        """OR-74 : l'import statique téléchargeait three.js avant le garde du mouvement réduit."""
        import re
        script = self.read("assets/landing.js")
        self.assertIsNone(re.search(r"^\s*import\s.*\sfrom\s", script, re.M))
        guard = script.index("|| reduce ||")
        # l'import porte l'empreinte de stamp_assets.py (?v=…), qui marque aussi
        # les imports de modules (OR-66)
        dynamic = re.search(r"import\('\./particle-image\.js(?:\?v=[0-9a-f]+)?'\)", script)
        self.assertIsNotNone(dynamic)
        self.assertLess(guard, dynamic.start())
        welcome = self.read("welcome.html")
        self.assertNotIn("modulepreload", welcome)
        self.assertNotIn("three.module", welcome)

    def test_touch_targets_follow_the_pointer_not_the_width(self):
        """OR-41 : 28 px en tête, 20 px en pied, 24 px sur le tableau à 768 px tactile."""
        base = "".join(self.blocks(self.read("assets/base.css"), "(pointer:coarse)"))
        self.assertRegex(base, r"\.nav-wide a\{[^}]*min-height:44px")
        self.assertRegex(base, r"\.wordmark\{[^}]*min-height:44px")
        pages = "".join(self.blocks(self.read("assets/pages.css"), "(pointer:coarse)"))
        self.assertRegex(pages, r"\.foot a\{[^}]*min-height:44px")
        self.assertRegex(pages, r"\.data-table summary\{[^}]*min-height:44px")
        observatory = self.read("assets/observatory.css")
        self.assertRegex(observatory, r'\.cross-tabs \[role="tab"\]\{[^}]*min-height:44px')
        self.assertRegex("".join(self.blocks(observatory, "(pointer:coarse)")),
                         r"\.cross-toggle\{[^}]*min-height:44px")

    def test_small_grey_text_holds_four_and_a_half_to_one_on_the_whole_gradient(self):
        """OR-76 : --stone tombait à 4,45:1 sur --ground-deep, le bas du dégradé des pages."""
        import re
        tokens = dict(re.findall(r"--([a-z0-9-]+):(#[0-9A-Fa-f]{6})", self.read("assets/base.css")))
        for ground in ("ground-deep", "ground", "ground-lift"):
            for ink in ("stone", "ink-2"):
                self.assertGreaterEqual(self.contrast(tokens[ink], tokens[ground]), 4.5, (ink, ground))
        tint = float(re.search(r"--tint-max:([\d.]+)", self.read("assets/observatory.css")).group(1))
        shaded = tuple(round(d * (1 - tint) + a * tint)
                       for d, a in zip(self.rgb(tokens["ground-deep"]), self.rgb(tokens["accent"])))
        self.assertGreaterEqual(self.contrast(tokens["ink"], shaded), 4.5)

    def test_decade_labels_stay_legible_on_a_phone(self):
        """OR-77 : les années de l'axe tombaient à 9,28 px sous 760 px."""
        import re
        phone = "".join(self.blocks(self.read("assets/observatory.css"), "(max-width:760px)"))
        size = re.search(r"\.obs \.cols \.c \.lb\{font-size:([\d.]+)rem", phone)
        self.assertIsNotNone(size)
        self.assertGreaterEqual(float(size.group(1)) * 16, 11)
        self.assertIn("lb-minor", self.read("assets/observatory.js"))

    def test_the_crossings_agree_with_an_independent_recount_and_the_cli(self):
        """F7 : la page et le CLI lisent observatory-core.js ; un recomptage Python les contrôle."""
        import shutil
        if shutil.which("node") is None:
            self.skipTest("node absent")
        result = subprocess.run([sys.executable, str(self.build / "qa" / "check_crossings.py")],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout[-1500:])



class AuditDataRepairTest(unittest.TestCase):
    """Audit du 13/09 : deux populations nommées dans stats.json, la date de relecture,
    la phrase de fusion, l'incunable daté par sa notice, les imprimeurs, les formes et
    les contenants."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(TOOLS_DIR))
        import build_public_snapshot  # noqa: E402
        import build_site_data  # noqa: E402
        import build_summary_figures  # noqa: E402
        cls.f = build_summary_figures
        cls.snapshot = build_public_snapshot
        cls.site = build_site_data
        cls.data = Path(site_data_dir())
        cls.build = Path(build_summary_figures.BUILD)
        read = lambda path: json.loads(path.read_text(encoding="utf-8"))
        cls.stats = read(cls.data / "stats.json")
        cls.meta = read(cls.data / "META.json")
        cls.graph = read(cls.data / "graph.json")
        cls.tags = read(cls.build / "assets" / "semantic.json")["byPpn"]
        cls.rows = [json.loads(line) for line in
                    (cls.data / "site-records.jsonl").read_text(encoding="utf-8").splitlines()
                    if line.strip()]

    def pubs(self):
        return [node for node in self.graph["nodes"] if node.get("k") == "pub"]

    def test_stats_json_carries_the_counted_population_under_its_own_key(self):
        import collections
        pubs = self.pubs()
        counted = [node for node in pubs
                   if (self.tags.get(node.get("ppn")) or {}).get("r") in ("core", "partial")]
        self.assertIn("population", self.stats)
        self.assertEqual(self.stats["totals"]["records"], len(pubs))
        self.assertEqual(self.stats["counted"]["totals"]["records"], len(counted))
        languages = collections.Counter(node.get("lang") or "none" for node in counted)
        for entry in self.stats["counted"]["by_language"]:
            self.assertEqual(entry["count"], languages[entry["code"]], entry["code"])
        years = [node["year"] for node in counted if isinstance(node.get("year"), int)]
        self.assertEqual(self.stats["counted"]["totals"]["year_min"], min(years))

    def test_meta_publishes_the_day_the_headings_were_read_again(self):
        dates = [row["subjects_container_fetched"] for row in self.rows
                 if row.get("subjects_container_basis") == "catalogue-record-refetched"]
        self.assertEqual(self.meta["refetched"], max(dates))
        self.assertEqual(self.meta["refetched_records"], len(dates))
        scratch_root = ROOT / "data" / "_proofs_tmp" / "tests"
        scratch_root.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(dir=str(scratch_root)))
        path = folder / "site-records.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in [
            {"subjects_container_basis": "catalogue-record-refetched", "subjects_container_fetched": "2026-09-12"},
            {"subjects_container_basis": "catalogue-record-refetched", "subjects_container_fetched": "2026-09-13"},
            {"subjects_container_basis": "catalogue-record"}]), encoding="utf-8")
        found = self.site.refetch_provenance(str(path))
        self.assertEqual((found["refetched"], found["refetched_records"]), ("2026-09-13", 2))
        path.write_text(json.dumps({"subjects_container_basis": "catalogue-record"}) + "\n", encoding="utf-8")
        self.assertEqual(self.site.refetch_provenance(str(path)), {})
        self.assertEqual(self.site.refetch_provenance(str(folder / "absent.jsonl")), {})

    def test_the_second_reading_is_dated_wherever_the_harvest_is(self):
        english = self.f.english_date(self.meta["refetched"])
        for path in (self.build / "methode.html", self.build / "credits.html", ROOT / "README.md",
                     ROOT / "llms.txt"):
            self.assertIn("were read again from their own catalogues on " + english,
                          path.read_text(encoding="utf-8"), path.name)
        self.assertIn("relues dans leur catalogue le " + self.f.french_date(self.meta["refetched"]),
                      (self.data / "README.md").read_text(encoding="utf-8"))
        credits = (self.build / "credits.html").read_text(encoding="utf-8")
        self.assertIn(self.f.english_date(self.meta["harvested"]) + ".</td>", credits)

    def test_the_merge_sentence_gives_both_counts(self):
        clusters = [json.loads(line) for line in (self.data / "site-merged" / "corpus.jsonl")
                    .read_text(encoding="utf-8").splitlines() if line.strip()]
        several = sum(1 for cluster in clusters if len(cluster.get("sources") or []) > 1)
        across = sum(1 for cluster in clusters
                     if len({entry.get("source") for entry in cluster["sources"]}) > 1)
        page = " ".join((self.build / "methode.html").read_text(encoding="utf-8").split())
        self.assertIn("%s clusters merge several records, and %s of those join records from more "
                      "than one source label" % (self.f.spaced(several), self.f.spaced(across)), page)
        self.assertNotIn("multi-source clusters", page)

    def test_the_incunable_is_dated_by_its_catalogue_record(self):
        row = next(row for row in self.rows if row["origenality_id"] == "sudoc:145827976")
        self.assertEqual(row["year"], 1489)
        self.assertEqual(row["curated_correction"]["basis"], "https://www.sudoc.fr/145827976")
        node = next(node for node in self.pubs()
                    if any(entry["id"] == "145827976" for entry in node["source_ids"]))
        self.assertEqual(node["year"], 1489)

    def test_no_printer_or_former_owner_is_an_author(self):
        authors = {node["label"] for node in self.graph["nodes"] if node.get("k") == "author"}
        for name in ("Silber, Eucario", "Augustus Frederick", "Hall, Henry", "Tournes, Samuel de",
                     "Luchtmans, Samuel", "Hovius, Henri", "Chantelauze, Régis de"):
            self.assertNotIn(name, authors)
        for row in self.rows:
            dropped = {entry["name"] for entry in row.get("authors_not_credited") or []}
            self.assertFalse(dropped & set(row.get("authors") or []), row["origenality_id"])

    def test_no_form_heading_counts_as_a_subject(self):
        forms = {"Thèses et écrits académiques", "Actes de congrès", "Ouvrages avant 1800"}
        for row in self.rows:
            if row.get("source") in ("sudoc", "bnf"):
                self.assertFalse(forms & set(row.get("subjects") or []), row["origenality_id"])

    def test_container_titles_carry_no_editor_and_cleaning_them_again_changes_nothing(self):
        known = set()
        for row in self.rows:
            container = row.get("container")
            if isinstance(container, dict):
                known.add(container["title"].casefold())
            if row.get("container_as_catalogued"):
                known.add(row["container_as_catalogued"].casefold())
        for row in self.rows:
            container = row.get("container")
            if not isinstance(container, dict):
                continue
            title = container["title"]
            self.assertEqual(self.snapshot.clean_container_title(title, frozenset(known)), title)
            self.assertFalse(title.startswith("In:"), title)
            _, statement = self.snapshot.split_responsibility(title)
            if statement is not None:
                self.assertIn(self.snapshot.responsibility_kind(statement), (None, "corporate"), title)

    def test_llms_describes_stats_json_by_population(self):
        text = (ROOT / "llms.txt").read_text(encoding="utf-8")
        self.assertNotIn("the counts the Observatory draws", text)
        line = next(line for line in text.splitlines() if "stats.json" in line)
        self.assertIn("`counted`", line)

    def test_record_links_follow_the_corrected_templates(self):
        policy = check_release.load_policy(ROOT / "DATA_POLICY.md")["attribution"]
        self.assertEqual(policy["gnomon-gbd"]["url_template"], "https://www.gbd.digital/gbd/Record/{id}")
        self.assertEqual(policy["b3kat"]["url_template"], "https://www.gateway-bayern.de/{id}")
        for node in self.pubs():
            for entry in node["source_ids"]:
                if entry["source"] == "b3kat":
                    self.assertTrue(entry["url"].startswith("https://www.gateway-bayern.de/"), entry)


if __name__ == "__main__":
    unittest.main(verbosity=2)
