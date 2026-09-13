#!/usr/bin/env python3
"""Tests du moissonneur des notices d'autorité (`hydrate_authority_records.py`).

    python3 scripts/test_hydrate_authority.py

Les notices de test sont des réponses réelles des sept interfaces, réduites aux
zones que le moissonneur lit : K10plus (PPN 016546318), DNB (IDN 1388660261),
B3Kat (BV050113439), Library of Congress (LCCN 00379631), Sudoc (PPN 119899515
et 002427141) et BnF (ark:/12148/cb304950124). Aucun test ne touche le réseau.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "pipeline"))

import hydrate_authority_records as h  # noqa: E402

K10PLUS = b"""<?xml version="1.0" encoding="UTF-8"?>
<zs:searchRetrieveResponse xmlns:zs="http://www.loc.gov/zing/srw/"><zs:version>1.1</zs:version>
<zs:numberOfRecords>1</zs:numberOfRecords><zs:records><zs:record>
<zs:recordSchema>marcxml</zs:recordSchema><zs:recordData>
<record xmlns="http://www.loc.gov/MARC21/slim">
  <leader>     cam a22      c 4500</leader>
  <controlfield tag="001">016546318</controlfield>
  <controlfield tag="008">860424s1985    gw |||||      00| ||grc c</controlfield>
  <datafield tag="041" ind1=" " ind2=" "><subfield code="a">grc</subfield><subfield code="a">lat</subfield></datafield>
  <datafield tag="100" ind1="0" ind2=" "><subfield code="a">Origenes</subfield><subfield code="d">185-254</subfield></datafield>
  <datafield tag="245" ind1="1" ind2="0"><subfield code="a">Vier B\xc3\xbccher von den Prinzipien</subfield><subfield code="c">hrsg. von Herwig G\xc3\xb6rgemanns</subfield></datafield>
  <datafield tag="264" ind1=" " ind2="1"><subfield code="a">Darmstadt</subfield><subfield code="c">1985</subfield></datafield>
  <datafield tag="490" ind1="1" ind2=" "><subfield code="a">Texte zur Forschung</subfield><subfield code="v">24</subfield></datafield>
  <datafield tag="650" ind1="0" ind2="7"><subfield code="0">(DE-588)4059758-1</subfield><subfield code="a">Theologie</subfield><subfield code="2">gnd</subfield></datafield>
  <datafield tag="650" ind1=" " ind2="4"><subfield code="a">Literaturverzeichnis/Bibliographie</subfield></datafield>
  <datafield tag="655" ind1=" " ind2="7"><subfield code="a">Quelle</subfield><subfield code="2">gnd-content</subfield></datafield>
  <datafield tag="689" ind1="0" ind2="0"><subfield code="D">s</subfield><subfield code="a">Theologie</subfield></datafield>
  <datafield tag="689" ind1="0" ind2=" "><subfield code="5">DE-101</subfield></datafield>
  <datafield tag="689" ind1="2" ind2="0"><subfield code="D">s</subfield><subfield code="a">Glaube</subfield></datafield>
  <datafield tag="700" ind1="1" ind2=" "><subfield code="a">G\xc3\xb6rgemanns, Herwig</subfield></datafield>
  <datafield tag="830" ind1=" " ind2="0"><subfield code="a">Texte zur Forschung</subfield><subfield code="v">24</subfield></datafield>
</record></zs:recordData></zs:record></zs:records></zs:searchRetrieveResponse>"""

# Une première 773 sans titre (zone codée « 773 18 »), puis la vraie notice
# hôte : la règle IxTheo s'arrêtait à la première et perdait le titre.
DNB = b"""<?xml version="1.0" encoding="UTF-8"?>
<searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/"><version>1.1</version>
<numberOfRecords>1</numberOfRecords><records><record><recordSchema>MARC21-xml</recordSchema><recordData>
<record xmlns="http://www.loc.gov/MARC21/slim" type="Bibliographic">
  <leader>00000naa a2200000uc 4500</leader>
  <controlfield tag="001">1388660261</controlfield>
  <controlfield tag="008">260201s2013    gw |||||o|||| 00||||eng  </controlfield>
  <datafield tag="245" ind1="0" ind2="0"><subfield code="a">Kurzanzeigen</subfield></datafield>
  <datafield tag="600" ind1="0" ind2="7"><subfield code="a">Origenes</subfield><subfield code="d">185-254</subfield><subfield code="2">gnd</subfield></datafield>
  <datafield tag="650" ind1=" " ind2="7"><subfield code="a">Fr\xc3\xbchchristentum</subfield><subfield code="2">gnd</subfield></datafield>
  <datafield tag="650" ind1=" " ind2="7"><subfield code="a">Rezeption</subfield><subfield code="2">gnd</subfield></datafield>
  <datafield tag="773" ind1="1" ind2="8"><subfield code="g">volume:17</subfield><subfield code="g">pages:185-193</subfield></datafield>
  <datafield tag="773" ind1="0" ind2="8"><subfield code="i">Enthalten in</subfield><subfield code="t">Zeitschrift f\xc3\xbcr antikes Christentum</subfield><subfield code="g">17, Heft 1 (2013), 185-193</subfield><subfield code="x">1612-961X</subfield></datafield>
</record></recordData></record></records></searchRetrieveResponse>"""

# Les marques de non-classement (NSB, NSE) encadrent l'article du titre hôte.
B3KAT = """<?xml version="1.0"?>
<zs:searchRetrieveResponse xmlns:zs="http://www.loc.gov/zing/srw/"><zs:version>1.1</zs:version>
<zs:numberOfRecords>1</zs:numberOfRecords><zs:records><zs:record><zs:recordData>
<record xmlns="http://www.loc.gov/MARC21/slim">
  <leader>01105naa a2200301 c 4500</leader>
  <controlfield tag="001">BV050113439</controlfield>
  <controlfield tag="008">240101s2024    xx       |||| 00||| ger d</controlfield>
  <datafield tag="245" ind1="1" ind2="0"><subfield code="a">"Der Logos in uns"</subfield><subfield code="b">Das Wohnen des Logos</subfield></datafield>
  <datafield tag="264" ind1=" " ind2="1"><subfield code="c">2024</subfield></datafield>
  <datafield tag="688" ind1=" " ind2="7"><subfield code="a">Origenes theol. TLG 2042</subfield><subfield code="2">gbd</subfield></datafield>
  <datafield tag="773" ind1="1" ind2="8"><subfield code="g">pages:107-130</subfield></datafield>
  <datafield tag="773" ind1="0" ind2="8"><subfield code="t">Das Johannesevangelium in antik-christlicher Rezeption /</subfield><subfield code="g">Seite 107-130</subfield></datafield>
</record></zs:recordData></zs:record></zs:records></zs:searchRetrieveResponse>""".encode("utf-8")

LOC = b"""<?xml version="1.0" encoding="UTF-8"?><record xmlns="http://www.loc.gov/MARC21/slim">
  <leader>01478cam a2200397 a 4500</leader>
  <controlfield tag="001">12371202</controlfield>
  <controlfield tag="008">010306s2000    ke       b    000 0 eng  </controlfield>
  <datafield ind1=" " ind2=" " tag="010"><subfield code="a">   00379631 </subfield></datafield>
  <datafield ind1="1" ind2=" " tag="100"><subfield code="a">Heisey, Nancy R.</subfield></datafield>
  <datafield ind1="1" ind2="0" tag="245"><subfield code="a">Origen, the Egyptian :</subfield><subfield code="b">a literary and historical consideration of the Egyptian background in Origen's writings on martyrdom /</subfield><subfield code="c">by Nancy R. Heisey.</subfield></datafield>
  <datafield ind1=" " ind2=" " tag="260"><subfield code="a">Nairobi, Kenya :</subfield><subfield code="c">2000.</subfield></datafield>
  <datafield ind1="0" ind2="0" tag="600"><subfield code="a">Origen.</subfield></datafield>
  <datafield ind1=" " ind2="0" tag="650"><subfield code="a">Martyrdom</subfield><subfield code="x">Christianity</subfield><subfield code="x">History of doctrines</subfield></datafield>
  <datafield ind1=" " ind2="0" tag="651"><subfield code="a">Egypt</subfield><subfield code="x">Religion.</subfield></datafield>
</record>"""

SUDOC_ARTICLE = """<?xml version="1.0" encoding="UTF-8"?>
<record>
  <leader>     caa2 22        450 </leader>
  <controlfield tag="001">119899515</controlfield>
  <datafield tag="100" ind1="#" ind2="#"><subfield code="a">20071210d1992    k  y0frey50      ba</subfield></datafield>
  <datafield tag="101" ind1="0" ind2="#"><subfield code="a">ita</subfield></datafield>
  <datafield tag="200" ind1="1" ind2="#"><subfield code="a">L' "omelia sul Levitico 5, 1"</subfield><subfield code="e">Origène e Rufino a confronto</subfield><subfield code="f">Pietro Carlo Porta</subfield></datafield>
  <datafield tag="463" ind1="#" ind2="#"><subfield code="0">039584445</subfield><subfield code="t">Orpheus (Catania)</subfield><subfield code="x">0030-5790</subfield><subfield code="v">13, 1992, fasc. 1, p. 52-76</subfield></datafield>
  <datafield tag="600" ind1="#" ind2="0"><subfield code="a">Origène</subfield><subfield code="f">0185?-0254?</subfield><subfield code="2">rameau</subfield></datafield>
  <datafield tag="600" ind1="#" ind2="0"><subfield code="a">Rufin d'Aquilée</subfield><subfield code="f">034.?-0410?</subfield><subfield code="2">rameau</subfield></datafield>
  <datafield tag="605" ind1="#" ind2="#"><subfield code="a">Bible</subfield><subfield code="i">A.T.</subfield><subfield code="2">rameau</subfield></datafield>
  <datafield tag="700" ind1="#" ind2="1"><subfield code="a">Porta</subfield><subfield code="b">Pietro Carlo</subfield></datafield>
</record>""".encode("utf-8")

SUDOC_BOOK = """<?xml version="1.0" encoding="UTF-8"?>
<record>
  <leader>     cam0 22        450 </leader>
  <controlfield tag="001">002427141</controlfield>
  <datafield tag="100" ind1="#" ind2="#"><subfield code="a">19911205d1990    k  y0frey50      ba</subfield></datafield>
  <datafield tag="200" ind1="1" ind2="#"><subfield code="a">The golden chain</subfield><subfield code="e">studies in the development of platonism and christianity</subfield></datafield>
  <datafield tag="225" ind1="2" ind2="#"><subfield code="a">Collected studies series</subfield><subfield code="v">333</subfield></datafield>
  <datafield tag="410" ind1="#" ind2="#"><subfield code="t">Collected studies series</subfield><subfield code="x">0961-7582</subfield></datafield>
  <datafield tag="600" ind1="#" ind2="0"><subfield code="a">Plotin</subfield><subfield code="f">0205?-0270</subfield></datafield>
  <datafield tag="606" ind1="#" ind2="#"><subfield code="a">Platonisme</subfield><subfield code="2">rameau</subfield></datafield>
  <datafield tag="700" ind1="#" ind2="1"><subfield code="a">Dillon</subfield><subfield code="b">John Myles</subfield></datafield>
</record>""".encode("utf-8")

BNF = """<?xml version="1.0" encoding="UTF-8"?><srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/">
<srw:version>1.2</srw:version><srw:numberOfRecords>1</srw:numberOfRecords><srw:records><srw:record><srw:recordData>
<mxc:record xmlns:mxc="info:lc/xmlns/marcxchange-v2" format="UNIMARC" id="ark:/12148/cb304950124" type="Bibliographic">
<mxc:leader>     cam  22        450 </mxc:leader>
<mxc:controlfield tag="001">FRBNF304950120000000</mxc:controlfield>
<mxc:datafield tag="100" ind1=" " ind2=" "><mxc:subfield code="a">19930517d1903    m  y0frey50      ba</mxc:subfield></mxc:datafield>
<mxc:datafield tag="200" ind1="1" ind2=" "><mxc:subfield code="a">L'enseignement d'Origène sur la prière</mxc:subfield><mxc:subfield code="b">Texte imprimé</mxc:subfield></mxc:datafield>
<mxc:datafield tag="604" ind1=" " ind2=" "><mxc:subfield code="a">Origène</mxc:subfield><mxc:subfield code="t">Sur la prière</mxc:subfield></mxc:datafield>
</mxc:record></srw:recordData></srw:record></srw:records></srw:searchRetrieveResponse>""".encode("utf-8")


def row(source, identifier, title, year):
    return {"source": source, "source_id": identifier, "title": title, "year": year,
            "origenality_id": "%s:%s" % (source, identifier)}


class ParserTest(unittest.TestCase):
    def parse(self, body, source, identifier):
        record = h.select_record(body, source, identifier)
        return h.parse_record(record, h.SOURCES[source]["format"])

    def test_k10plus_headings_chains_and_series(self):
        parsed = self.parse(K10PLUS, "k10plus", "016546318")
        self.assertEqual(parsed["subjects"], ["Theologie", "Literaturverzeichnis/Bibliographie"])
        self.assertEqual(parsed["subject_chains"], ["Theologie", "Glaube"])
        self.assertNotIn("Quelle", parsed["subjects"])       # 655 : forme, pas sujet
        self.assertEqual(parsed["container"]["type"], "series")
        self.assertEqual(parsed["container"]["title"], "Texte zur Forschung")
        self.assertEqual(parsed["container"]["details"], ["24"])
        self.assertEqual((parsed["title"], parsed["year"], parsed["language"]),
                         ("Vier Bücher von den Prinzipien", 1985, "grc"))

    def test_dnb_host_is_the_first_773_that_has_a_title(self):
        parsed = self.parse(DNB, "dnb", "1388660261")
        self.assertEqual(parsed["container"]["type"], "host")
        self.assertEqual(parsed["container"]["title"], "Zeitschrift für antikes Christentum")
        self.assertEqual(parsed["subjects"], ["Origenes", "Frühchristentum", "Rezeption"])
        self.assertEqual(parsed["subject_fields"][0], ["600", "Origenes"])

    def test_b3kat_sort_marks_and_isbd_slash_are_removed(self):
        parsed = self.parse(B3KAT, "gnomon-gbd", "BV050113439")
        self.assertEqual(parsed["container"]["title"],
                         "Das Johannesevangelium in antik-christlicher Rezeption")
        # 688, thésaurus local de la GBD : absent du graphe publié, non retenu.
        self.assertEqual(parsed["subjects"], [])

    def test_a_bnf_response_for_another_ark_is_refused(self):
        with self.assertRaises(h.FetchError) as caught:
            h.select_record(BNF, "bnf", "ark:/12148/cb454216334")
        self.assertEqual(caught.exception.cause, "wrong-record")
        self.assertIn("persistentid+any", h.SOURCES["bnf"]["url"]("ark:/12148/cb1"))

    def test_loc_keeps_the_main_heading_of_each_6xx(self):
        parsed = self.parse(LOC, "loc", "00379631")
        self.assertEqual(parsed["subjects"], ["Origen", "Martyrdom", "Egypt"])
        self.assertIsNone(parsed["container"])
        self.assertTrue(parsed["title"].startswith("Origen, the Egyptian : a literary"))
        self.assertEqual(h.lccn_key("a  51005034"), "a51005034")
        self.assertIn("query=bath.lccn%3Da51005034", h.SOURCES["loc"]["url"]("a  51005034"))

    def test_sudoc_article_host_and_unimarc_names(self):
        parsed = self.parse(SUDOC_ARTICLE, "sudoc", "119899515")
        self.assertEqual(parsed["container"],
                         {"type": "host", "title": "Orpheus (Catania)",
                          "details": ["13, 1992, fasc. 1, p. 52-76"], "issn": "0030-5790"})
        self.assertEqual(parsed["subjects"], ["Origène", "Rufin d'Aquilée", "Bible"])
        self.assertEqual(parsed["authors"], ["Porta, Pietro Carlo"])
        self.assertEqual(parsed["year"], 1992)

    def test_sudoc_series_prefers_the_transcribed_statement(self):
        parsed = self.parse(SUDOC_BOOK, "sudoc", "002427141")
        self.assertEqual(parsed["container"]["type"], "series")
        self.assertEqual(parsed["container"]["title"], "Collected studies series")
        self.assertEqual(parsed["title"],
                         "The golden chain : studies in the development of platonism and christianity")

    def test_bnf_marcxchange_record(self):
        parsed = self.parse(BNF, "bnf", "ark:/12148/cb304950124")
        self.assertEqual(parsed["subjects"], ["Origène"])
        self.assertEqual(parsed["year"], 1903)
        self.assertEqual(parsed["title"], "L'enseignement d'Origène sur la prière")

    def test_responses_without_the_record_are_failures_with_a_cause(self):
        cases = {
            b'<?xml version="1.0"?><error>Les donn\xc3\xa9es sont ind\xc3\xa9finies <ppn>1</ppn></error>':
                "not-found",
            b'<zs:searchRetrieveResponse xmlns:zs="http://www.loc.gov/zing/srw/">'
            b'<zs:numberOfRecords>0</zs:numberOfRecords></zs:searchRetrieveResponse>': "no-record",
            b"<html><body>error": "unparseable-response",
        }
        for body, cause in cases.items():
            with self.assertRaises(h.FetchError) as caught:
                h.select_record(body, "k10plus", "1")
            self.assertEqual(caught.exception.cause, cause)


class IdentityTest(unittest.TestCase):
    def check(self, snapshot_row, body, source):
        record = h.select_record(body, source, snapshot_row["source_id"])
        parsed = h.parse_record(record, h.SOURCES[source]["format"])
        parsed["title_proper"] = h.title_proper(record, h.SOURCES[source]["format"])
        return h.identity_check(snapshot_row, parsed)

    def test_a_truncated_published_title_still_matches(self):
        published = ("Origen, the Egyptian : a literary and historical consideration of the "
                     "Egyptian background in Origen's writings on marty…")
        result = self.check(row("loc", "00379631", published, 2000), LOC, "loc")
        self.assertEqual((result["status"], result["title"], result["year"]),
                         ("verified", "prefix", "match"))

    def test_another_title_is_a_mismatch(self):
        result = self.check(row("loc", "00379631", "Origen and the Bible", 2000), LOC, "loc")
        self.assertEqual((result["status"], result["title"]), ("mismatch", "differs"))

    def test_another_year_is_a_mismatch(self):
        result = self.check(row("k10plus", "016546318", "Vier Bücher von den Prinzipien", 1976),
                            K10PLUS, "k10plus")
        self.assertEqual((result["status"], result["year"]), ("mismatch", "differs"))

    def test_a_snapshot_without_year_is_checked_on_the_title_alone(self):
        result = self.check(row("bnf", "ark:/12148/cb304950124",
                                "L'enseignement d'Origène sur la prière", None), BNF, "bnf")
        self.assertEqual((result["status"], result["year"]), ("verified", "unverifiable-snapshot"))

    def test_word_order_and_articles_do_not_block_a_real_match(self):
        self.assertEqual(h.title_agreement("L'unità delle nazioni : una visione dei Padri",
                                           "L' unità delle nazioni : una visione dei Padri della Chiesa",
                                           "L' unità delle nazioni"), "prefix")
        self.assertEqual(h.title_agreement("Origenes", "Die Welt als Bild", "Die Welt als Bild"),
                         "differs")


class FakeResponse:
    def __init__(self, body, kind="text/xml"):
        self.body, self.headers = body, {"Content-Type": kind}

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FetchAndResumeTest(unittest.TestCase):
    def test_throttle_spaces_requests_to_one_per_interval(self):
        moments, slept = iter([0.0, 0.3, 1.0]), []
        throttle = h.Throttle(1.0, clock=lambda: next(moments), sleep=slept.append)
        throttle.wait()
        throttle.wait()
        self.assertEqual(slept, [0.7])

    def test_503_is_retried_and_404_is_not(self):
        calls, slept = [], []

        def busy_then_ok(request, timeout):
            calls.append(request.full_url)
            if len(calls) == 1:
                raise urllib.error.HTTPError(request.full_url, 503, "busy", {}, None)
            return FakeResponse(K10PLUS)

        throttle = h.Throttle(0, sleep=lambda s: None)
        body = h.fetch("https://example.org/a", throttle, opener=busy_then_ok, sleep=slept.append)
        self.assertEqual((body, len(calls), slept), (K10PLUS, 2, [h.BACKOFF]))
        self.assertIn(h.CONTACT, h.USER_AGENT)

        def missing(request, timeout):
            calls.append(request.full_url)
            raise urllib.error.HTTPError(request.full_url, 404, "missing", {}, None)

        calls.clear()
        with self.assertRaises(h.FetchError) as caught:
            h.fetch("https://example.org/b", throttle, opener=missing, sleep=slept.append)
        self.assertEqual((caught.exception.cause, len(calls)), ("not-found", 1))

    def test_an_html_error_page_is_not_a_record(self):
        throttle = h.Throttle(0, sleep=lambda s: None)
        with self.assertRaises(h.FetchError) as caught:
            h.fetch("https://example.org/c", throttle,
                    opener=lambda r, timeout: FakeResponse(b"<html>", "text/html;charset=UTF-8"))
        self.assertEqual(caught.exception.cause, "not-marcxml")

    def test_written_records_and_other_sources_are_not_requested_again(self):
        rows = [row("k10plus", "1", "a", 1), row("k10plus", "2", "b", 1),
                row("ixtheo-k10plus", "3", "c", 1), row("sudoc", "4", "d", 1),
                row("sudoc", "5", "e", 1)]
        pending = h.pending_rows(rows, {"k10plus:1"})
        self.assertEqual([r["source_id"] for r in pending], ["2", "4", "5"])
        self.assertEqual([r["source_id"] for r in h.pending_rows(rows, set(), limit=1)], ["1", "4"])

    def test_a_cached_response_is_read_without_the_network(self):
        snapshot = [row("sudoc", "119899515",
                        "L' \"omelia sul Levitico 5, 1\" : Origène e Rufino a confronto", 1992),
                    row("sudoc", "002427141", "Another book entirely", 1990)]
        original = h.fetch
        h.fetch = lambda *a, **k: self.fail("network called for a cached record")
        try:
            with tempfile.TemporaryDirectory() as folder:
                out = Path(folder)
                for identifier, body in (("119899515", SUDOC_ARTICLE), ("002427141", SUDOC_BOOK)):
                    path = h.cache_path(out, "sudoc", identifier)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(body)
                harvest = h.Harvest(out, snapshot)
                harvest.run(h.pending_rows(snapshot, set()))
                written = h.read_jsonl(out / "records.jsonl")
                failures = h.read_jsonl(out / "failures.jsonl")
                table = h.summarise(snapshot, written, failures)
                progress = json.loads((out / "progress.json").read_text(encoding="utf-8"))
        finally:
            h.fetch = original
        by_id = {entry["source_id"]: entry for entry in written}
        self.assertEqual(by_id["119899515"]["fetched_from"], "cache")
        self.assertEqual(by_id["119899515"]["identity"]["status"], "verified")
        self.assertEqual(by_id["002427141"]["identity"]["status"], "mismatch")
        self.assertEqual([f["cause"] for f in failures], ["identity-mismatch"])
        self.assertEqual(dict(table["sudoc"]), {
            "requested": 2, "fetched": 2, "parsed": 2, "verified": 1, "with_subjects": 1,
            "with_container": 1, "mismatches": 1, "failures": 0})
        self.assertTrue(progress["done"])


class SnapshotAuthorityTest(unittest.TestCase):
    """Le snapshot ne prend d'une notice relue que ses vedettes et son contenant,
    et seulement si le contrôle d'identité l'a vérifiée."""

    @classmethod
    def setUpClass(cls):
        for tools in (ROOT / "site" / "build-c" / "tools", ROOT / "site" / "tools"):
            if tools.is_dir():
                sys.path.insert(0, str(tools))
        import build_public_snapshot  # noqa: E402
        cls.snapshot = build_public_snapshot

    @staticmethod
    def base(key, **fields):
        source, identifier = key.split(":", 1)
        row = {"origenality_id": key, "source": source, "source_id": identifier,
               "title": "Titel", "year": 2000, "relation": "about", "subjects": ["Priester"],
               "subject_chains": [], "container": None,
               "subjects_container_basis": "public-projection"}
        row.update(fields)
        return row

    @staticmethod
    def fetched(key, status="verified", **fields):
        source, identifier = key.split(":", 1)
        record = {"source": source, "source_id": identifier, "identity": {"status": status},
                  "title": "Ein anderer Titel", "subjects": ["Apostel", "Priester"],
                  "subject_chains": ["Apostel"],
                  "container": {"type": "series", "title": "Adamantiana", "details": ["3"]}}
        record.update(fields)
        return record

    def test_a_verified_record_gives_headings_and_container_but_not_the_title(self):
        rows = [self.base("sudoc:1"), self.base("k10plus:2"), self.base("ixtheo-k10plus:3")]
        authority = {"sudoc:1": self.fetched("sudoc:1"),
                     "ixtheo-k10plus:3": self.fetched("ixtheo-k10plus:3")}
        out = self.snapshot.refresh(rows, {}, {}, {}, authority)
        self.assertEqual(out[0]["subjects_container_basis"], "catalogue-record-refetched")
        self.assertEqual(out[0]["subjects"], ["Apostel", "Priester"])
        self.assertEqual(out[0]["container"], {"title": "Adamantiana", "type": "series"})
        self.assertEqual((out[0]["title"], out[0]["relation"]), ("Titel", "about"))
        self.assertEqual(out[1]["subjects_container_basis"], "public-projection")
        # IxTheo n'est pas un flux d'autorité : la table ne s'y applique pas.
        self.assertEqual(out[2]["subjects"], ["Priester"])

    def test_a_mismatched_record_is_never_loaded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "records.jsonl"
            path.write_text("".join(json.dumps(r) + "\n" for r in (
                self.fetched("sudoc:1"), self.fetched("dnb:2", status="mismatch"))),
                encoding="utf-8")
            self.assertEqual(sorted(self.snapshot.load_authority(path)), ["sudoc:1"])
        self.assertEqual(self.snapshot.load_authority(None), {})

    def test_a_rebuild_without_the_authority_harvest_keeps_the_refetched_rows(self):
        once = self.snapshot.refresh([self.base("loc:7")], {}, {}, {},
                                     {"loc:7": self.fetched("loc:7")})
        self.assertEqual(self.snapshot.refresh(once, {}, {}, {}), once)
        self.assertEqual(self.snapshot.coverage(once)["basis_catalogue_record"], 1)


# Réduite de la notice Sudoc 145827976 (Rome, Eucario Silber, 1489), telle que le
# cache de la relecture la garde : une zone de forme 608, un imprimeur (702 $4 610)
# et un ancien possesseur (702 $4 390).
SUDOC_INCUNABLE = """<?xml version="1.0" encoding="UTF-8"?>
<record>
  <leader>     cam0 22        450 </leader>
  <controlfield tag="001">145827976</controlfield>
  <datafield tag="100" ind1="#" ind2="#"><subfield code="a">20100726d1489    |||y0frey50      ba</subfield></datafield>
  <datafield tag="200" ind1="1" ind2="#"><subfield code="a">Determinationes magistrales contra conclusiones Joannis Pici Mirandulæ</subfield></datafield>
  <datafield tag="210" ind1="#" ind2="#"><subfield code="a">[Roma</subfield><subfield code="c">Eucario Silber</subfield><subfield code="d">15 octobre 1489]</subfield></datafield>
  <datafield tag="606" ind1="#" ind2="#"><subfield code="a">Philosophie médiévale</subfield><subfield code="2">rameau</subfield></datafield>
  <datafield tag="608" ind1="#" ind2="#"><subfield code="a">Ouvrages avant 1800</subfield><subfield code="2">rameau</subfield></datafield>
  <datafield tag="700" ind1="#" ind2="1"><subfield code="a">Garcia</subfield><subfield code="b">Pierre</subfield><subfield code="4">070</subfield></datafield>
  <datafield tag="702" ind1="#" ind2="1"><subfield code="a">Silber</subfield><subfield code="b">Eucario</subfield><subfield code="c">imprimeur-libraire</subfield><subfield code="4">610</subfield></datafield>
  <datafield tag="702" ind1="#" ind2="0"><subfield code="a">Augustus Frederick</subfield><subfield code="c">duc de Sussex</subfield><subfield code="4">390</subfield></datafield>
</record>""".encode("utf-8")

# Réduite de la notice LCCN 11006687 (Oxford, 1667) : l'imprimeur et le libraire
# portent leur rôle en URI id.loc.gov.
LOC_IMPRINT = b"""<?xml version="1.0" encoding="UTF-8"?><record xmlns="http://www.loc.gov/MARC21/slim">
  <leader>01234cam a2200301 i 4500</leader>
  <controlfield tag="001">8226550</controlfield>
  <controlfield tag="008">930304s1667    enk           000 0 eng  </controlfield>
  <datafield ind1="1" ind2=" " tag="100"><subfield code="a">Parker, Samuel,</subfield><subfield code="e">author</subfield><subfield code="4">aut</subfield><subfield code="4">http://id.loc.gov/vocabulary/relators/aut</subfield></datafield>
  <datafield ind1="1" ind2="2" tag="245"><subfield code="a">A free and impartial censure of the Platonick philosophie :</subfield><subfield code="b">with an account of the Origenian hypothesis, concerning the preexistence of souls : in two letters, written to Mr. Nath. Bisbie /</subfield></datafield>
  <datafield ind1="1" ind2=" " tag="700"><subfield code="a">Hall, Henry,</subfield><subfield code="e">printer</subfield><subfield code="4">http://id.loc.gov/vocabulary/relators/prt</subfield></datafield>
  <datafield ind1="1" ind2=" " tag="700"><subfield code="a">Davis, Richard,</subfield><subfield code="e">bookseller</subfield><subfield code="4">http://id.loc.gov/vocabulary/relators/bsl</subfield></datafield>
</record>"""


def tools_on_path():
    for tools in (ROOT / "site" / "build-c" / "tools", ROOT / "site" / "tools"):
        if tools.is_dir():
            sys.path.insert(0, str(tools))
    import build_public_snapshot  # noqa: E402
    return build_public_snapshot


def records_in(body: bytes):
    return h.marc_records(h.ET.fromstring(body))[0]


class FormHeadingAndRoleTest(unittest.TestCase):
    """Audit du 13/09 : la zone de forme UNIMARC 608 comptée comme sujet, et les
    rôles non auctoriaux (imprimeur, ancien possesseur) versés dans les auteurs."""

    def test_a_unimarc_form_heading_is_not_a_subject(self):
        parsed = h.parse_record(records_in(SUDOC_INCUNABLE), "unimarc")
        self.assertEqual(parsed["subjects"], ["Philosophie médiévale"])
        self.assertNotIn("608", {tag for tag, _ in parsed["subject_fields"]})
        self.assertNotIn("608", h.SUBJECT_TAGS["unimarc"])
        self.assertNotIn("655", h.SUBJECT_TAGS["marc21"])

    def test_unimarc_roles_are_read_from_subfield_4(self):
        parsed = h.parse_record(records_in(SUDOC_INCUNABLE), "unimarc")
        self.assertEqual(parsed["author_roles"], [["Garcia, Pierre", ["070"]],
                                                  ["Silber, Eucario", ["610"]],
                                                  ["Augustus Frederick", ["390"]]])

    def test_marc21_roles_read_a_code_given_as_a_uri(self):
        parsed = h.parse_record(records_in(LOC_IMPRINT), "marc21")
        self.assertEqual(parsed["author_roles"], [["Parker, Samuel", ["aut"]],
                                                  ["Hall, Henry", ["prt"]],
                                                  ["Davis, Richard", ["bsl"]]])

    def test_marc21_falls_back_on_the_plain_mention(self):
        body = (b'<record xmlns="http://www.loc.gov/MARC21/slim"><controlfield tag="001">1'
                b'</controlfield><datafield tag="700" ind1="1" ind2=" "><subfield code="a">'
                b'Gensch, Christian</subfield><subfield code="e">DruckerIn</subfield></datafield>'
                b'</record>')
        parsed = h.parse_record(records_in(body), "marc21")
        self.assertEqual(parsed["author_roles"], [["Gensch, Christian", ["druckerin"]]])
        import fields  # noqa: E402
        self.assertTrue(fields.non_authorial(["druckerin"]))
        self.assertFalse(fields.non_authorial(["aut", "prt"]))
        self.assertFalse(fields.non_authorial([""]))
        self.assertFalse(fields.non_authorial([]))

    def test_the_corrected_year_lets_the_record_verify(self):
        """La correction 1514 -> 1489 passe avant le contrôle d'identité."""
        title = "Determinationes magistrales contra conclusiones Joannis Pici Mirandulæ"
        wrong = h.build_entry(row("sudoc", "145827976", title, 1514), SUDOC_INCUNABLE,
                              "2026-09-13T02:01:17+00:00", "cache")
        right = h.build_entry(row("sudoc", "145827976", title, 1489), SUDOC_INCUNABLE,
                              "2026-09-13T02:01:17+00:00", "cache")
        self.assertEqual(wrong["identity"]["status"], "mismatch")
        self.assertEqual(right["identity"]["status"], "verified")
        self.assertIn(["Silber, Eucario", ["610"]], right["author_roles"])


class SnapshotRepairTest(unittest.TestCase):
    """Les quatre réparations du snapshot : auteurs, contenants, liens, date de relecture."""

    @classmethod
    def setUpClass(cls):
        cls.snapshot = tools_on_path()
        cls.attribution = cls.snapshot.load_attribution()

    def incunable(self):
        title = "Determinationes magistrales contra conclusiones Joannis Pici Mirandulæ"
        base = {"origenality_id": "sudoc:145827976", "source": "sudoc",
                "source_id": "145827976", "title": title, "year": 1489,
                "authors": ["Garcia, Pierre", "Silber, Eucario", "Augustus Frederick"],
                "subjects": ["Ouvrages avant 1800"], "subject_chains": [], "container": None,
                "relation": "about", "subjects_container_basis": "public-projection",
                "sources": [{"source": "sudoc", "source_id": "145827976",
                             "url": "https://www.sudoc.fr/145827976"}],
                "url": "https://www.sudoc.fr/145827976"}
        entry = h.build_entry(base, SUDOC_INCUNABLE, "2026-09-13T02:01:17+00:00", "cache")
        return base, entry

    def test_a_printer_and_a_former_owner_leave_the_authors(self):
        base, entry = self.incunable()
        once = self.snapshot.refresh([base], {}, {}, {}, {"sudoc:145827976": entry})
        self.assertEqual(once[0]["authors"], ["Garcia, Pierre"])
        self.assertEqual(once[0]["authors_not_credited"],
                         [{"name": "Silber, Eucario", "roles": ["610"]},
                          {"name": "Augustus Frederick", "roles": ["390"]}])
        self.assertEqual(once[0]["subjects"], ["Philosophie médiévale"])
        self.assertEqual(once[0]["subjects_container_fetched"], "2026-09-13")
        # Sans la moisson, la ligne garde ce que la moisson lui a donné.
        self.assertEqual(self.snapshot.refresh(once, {}, {}, {}), once)

    def test_a_person_with_one_authorial_role_stays(self):
        kept, dropped = self.snapshot.credited_authors(
            {"authors": ["Gensch, Christian", "Huet, Pierre Daniel"]},
            {"gensch, christian": ["aut", "prt"], "huet, pierre daniel": ["wat"]})
        self.assertEqual((kept, dropped), (["Gensch, Christian", "Huet, Pierre Daniel"], []))

    def test_ixtheo_roles_come_from_the_harvest(self):
        rows = [{"origenality_id": "ixtheo-k10plus:1918709939", "source": "ixtheo-k10plus",
                 "source_id": "1918709939", "title": "T", "year": 2020,
                 "authors": ["Iulius Africanus, Sextus", "Aristides, Aelius", "Fürst, Alfons"]}]
        catalogue = {"ixtheo-k10plus:1918709939": {"source_id": "1918709939", "authors": [
            {"name": "Iulius Africanus, Sextus", "role": "aut"},
            {"name": "Aristides, Aelius", "role": "rcp"},
            {"name": "Fürst, Alfons", "role": "edt"}]}}
        out = self.snapshot.refresh(rows, catalogue, {}, {})
        self.assertEqual(out[0]["authors"], ["Iulius Africanus, Sextus", "Fürst, Alfons"])

    def test_container_titles_lose_the_statement_of_responsibility(self):
        clean = self.snapshot.clean_container_title
        cases = {
            "Biblica / a Pontificio Instituto Biblico in lucem editi in Urbe": "Biblica",
            "Jahrbuch für Antike und Christentum / im Auftr. d. Nordrhein-Westfälischen Akademie "
            "der Wissenschaften hrsg. im Franz-Joseph-Dölger-Institut zur Erforschung der "
            "Spätantike der Universität Bonn": "Jahrbuch für Antike und Christentum",
            "Origeniana undecima / edited by Anders-Christian Jacobsen": "Origeniana undecima",
            "Werke mit deutscher Übersetzung / Origenes ; im Auftrag der Berlin-Brandenburgischen "
            "Akademie der Wissenschaften und der Forschungsstelle Origenes der Universität Münster "
            "; herausgegeben von Alfons Fürst und Christoph Markschies":
                "Werke mit deutscher Übersetzung",
            "Studies in early christianity / François Bovon": "Studies in early christianity",
            "In S. Gregorii Nysseni et Origenis scripta et doctrinam nova recensio : cum appendice "
            "de actis synodi V. oecumenicae ; partes quatuor in quatuor volumina divisae / per "
            "Aloisium Vincenzi": "In S. Gregorii Nysseni et Origenis scripta et doctrinam nova "
            "recensio : cum appendice de actis synodi V. oecumenicae ; partes quatuor in quatuor "
            "volumina divisae",
            "Studia patristica. 21. Tenth Conference, 1987 ; 3: Second Century, Tertullian to "
            "Nicea in the West, Clement of Alexandria and Origen, Athanasius / ed. by Elizabeth "
            "A. Livingstone": "Studia patristica. 21. Tenth Conference, 1987 ; 3: Second Century, "
            "Tertullian to Nicea in the West, Clement of Alexandria and Origen, Athanasius",
            # Ce qui n'est pas une mention de responsabilité reste tel quel.
            "Vetera Christianorum / Quaderni": "Vetera Christianorum / Quaderni",
            "[Augustinianum / Studia]": "[Augustinianum / Studia]",
            "Adamantius": "Adamantius",
            # Une collectivité seule reste attachée au titre court qu'elle distingue.
            "Skrifter / Det Norske Videnskaps-Akademi": "Skrifter / Det Norske Videnskaps-Akademi",
            "The classical review / Classical Association": "The classical review",
        }
        for title, expected in cases.items():
            self.assertEqual(clean(title), expected, title)
        twin = "Auctores nostri / Università degli Studi di Foggia, Cattedra di Letteratura Cristiana Antica"
        self.assertEqual(clean(twin), twin)
        self.assertEqual(clean(twin, frozenset({"auctores nostri"})), "Auctores nostri")

    def test_a_free_text_citation_keeps_only_the_host_title(self):
        clean = self.snapshot.clean_container_title
        self.assertEqual(clean(
            "In: Markschies, Christoph / Zachhuber, Johannes (Hrsg.): Die Welt als Bild : "
            "interdisziplinäre Beiträge zur Visualität von Weltbildern. (Arbeiten zur "
            "Kirchengeschichte ; 107) Berlin, S. 69-79"),
            "Die Welt als Bild : interdisziplinäre Beiträge zur Visualität von Weltbildern")
        self.assertIsNone(clean("In: Festschrift für einen Kollegen, Berlin 2004"))

    def test_one_series_counted_three_times_becomes_one_and_volumes_stay_apart(self):
        forms = ["Werke mit deutscher Übersetzung",
                 "Werke mit deutscher Übersetzung / Origenes ; im Auftrag der Berlin-Brandenburgischen "
                 "Akademie der Wissenschaften und der Forschungsstelle Origenes der Universität "
                 "Münster ; herausgegeben von Alfons Fürst und Christoph Markschies",
                 "Werke mit deutscher Übersetzung / Origenes ; im Auftrag der Berlin-Brandenburgischen "
                 "Akademie der Wissenschaften und der Forschungsstelle Origenes der Westfälischen "
                 "Wilhelms-Universität Münster ; herausgegeben von Alfons Fürst und Christoph Markschies",
                 "Studia patristica. 17,2. Eighth Conference, 1979 ; 2 / ed. by Elizabeth A. Livingstone",
                 "Studia patristica. 26. Eleventh Conference, 1991 ; 3: Liturgica, Second Century, "
                 "Alexandria before Nicaea, Athanasius and the Arian Controversy / ed. by Elizabeth "
                 "A. Livingstone"]
        rows = [{"origenality_id": "gnomon-gbd:%d" % n, "source": "gnomon-gbd", "source_id": str(n),
                 "title": "T%d" % n, "container": {"title": form, "type": "series"}}
                for n, form in enumerate(forms)]
        out = self.snapshot.refresh(rows, {}, {}, {})
        titles = {row["container"]["title"] for row in out}
        self.assertEqual(len(titles), 3, titles)
        self.assertEqual(out[1]["container_as_catalogued"], forms[1])
        self.assertNotIn("container_as_catalogued", out[0])

    def test_a_record_link_on_another_database_is_rebuilt_from_its_own_template(self):
        rows = [{"origenality_id": "b3kat:BV003571296", "source": "b3kat", "source_id": "BV003571296",
                 "url": "https://www.gbd.digital/gbd/Record/BV003571296",
                 "sources": [{"source": "b3kat", "source_id": "BV003571296",
                              "url": "https://www.gbd.digital/gbd/Record/BV003571296"}]},
                {"origenality_id": "k10plus:1", "source": "k10plus", "source_id": "1",
                 "url": "https://doi.org/10.1163/x", "sources": [{"source": "k10plus", "source_id": "1"}]},
                {"origenality_id": "gnomon-gbd:BV046495281", "source": "gnomon-gbd",
                 "source_id": "BV046495281", "url": "https://www.gbd.digital/gbd/Record/BV046495281",
                 "sources": [{"source": "gnomon-gbd", "source_id": "BV046495281",
                              "url": "https://www.gbd.digital/gbd/Record/BV046495281"}]}]
        out = self.snapshot.refresh(rows, {}, {}, {}, None, self.attribution)
        self.assertEqual(out[0]["url"], "https://www.gateway-bayern.de/BV003571296")
        self.assertEqual(out[0]["sources"][0]["url"], "https://www.gateway-bayern.de/BV003571296")
        self.assertEqual(out[1]["url"], "https://doi.org/10.1163/x")
        self.assertEqual(out[1]["sources"][0]["url"], "https://opac.k10plus.de/DB=2.1/PPNSET?PPN=1")
        self.assertEqual(out[2]["url"], "https://www.gbd.digital/gbd/Record/BV046495281")
        self.assertEqual(self.attribution["gnomon-gbd"]["url_template"],
                         "https://www.gbd.digital/gbd/Record/{id}")


class SnapshotCheckTest(unittest.TestCase):
    """C-3 : `--check` dit ce qu'il a pu dériver, et ne se fait pas passer pour un
    contrôle de contenu quand il n'a relu aucune notice."""

    @classmethod
    def setUpClass(cls):
        cls.snapshot = tools_on_path()

    def run_tool(self, *arguments):
        import contextlib
        import io
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            status = self.snapshot.main(list(arguments))
        return status, buffer.getvalue()

    def rows_file(self, name, rows):
        folder = ROOT / "data" / "_proofs_tmp" / "tests" / "snapshot_check" / name
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "site-records.jsonl"
        path.write_text(self.snapshot.serialise(rows), encoding="utf-8")
        return folder, path

    def test_zero_rows_derived_fails_unless_structure_only_is_said(self):
        rows = [{"origenality_id": "k10plus:%d" % n, "source": "k10plus", "source_id": str(n),
                 "title": "T%d" % n, "authors": [], "container": None, "subjects": ["S"],
                 "subject_chains": [], "relation": None,
                 "subjects_container_basis": "public-projection"} for n in range(3)]
        folder, path = self.rows_file("structure", rows)
        absent = folder / "absent.jsonl"
        common = ("--records", str(path), "--catalogue", str(absent), "--no-authority")
        self.assertEqual(self.run_tool(*common)[0], 0)
        status, output = self.run_tool(*common, "--check")
        self.assertEqual(status, 1, output)
        self.assertIn("derived again from catalogue records on disk: 0 of 3", output)
        self.assertIn("no row could be derived again", output)
        status, output = self.run_tool(*common, "--check", "--structure-only")
        self.assertEqual(status, 0, output)
        self.assertIn("structure only", output)

    def test_rows_derived_from_the_harvest_are_counted(self):
        rows = [{"origenality_id": "ixtheo-k10plus:1", "source": "ixtheo-k10plus", "source_id": "1",
                 "title": "T", "authors": []}]
        folder, path = self.rows_file("derived", rows)
        catalogue = folder / "ixtheo.jsonl"
        catalogue.write_text(json.dumps({"source_id": "1", "relation": "about", "subjects": ["S"],
                                         "container": None}) + "\n", encoding="utf-8")
        common = ("--records", str(path), "--catalogue", str(catalogue), "--no-authority")
        self.assertEqual(self.run_tool(*common)[0], 0)
        status, output = self.run_tool(*common, "--check")
        self.assertEqual(status, 0, output)
        self.assertIn("derived again from catalogue records on disk: 1 of 1 (IxTheo harvest 1", output)

    def test_duplicate_keys_fail(self):
        row = {"origenality_id": "k10plus:1", "source": "k10plus", "source_id": "1", "title": "T"}
        folder, path = self.rows_file("duplicates", [row, dict(row)])
        status, output = self.run_tool("--records", str(path), "--catalogue",
                                       str(folder / "absent.jsonl"), "--no-authority", "--check",
                                       "--structure-only")
        self.assertEqual(status, 1, output)
        self.assertIn("duplicate record keys: k10plus:1", output)


if __name__ == "__main__":
    unittest.main()
