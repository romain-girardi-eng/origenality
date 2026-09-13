#!/usr/bin/env python3
"""Tests des contrôles de release : langues et poids, pages servies, empreintes.

    python3 scripts/test_release_gates.py
    python3 -m unittest discover -s scripts -p test_release_gates.py

Chaque contrôle est rejoué sur un arbre fabriqué ici, dans les deux
géométries quand la géométrie compte (`site/build-c/` et `site/data/` dans le
dépôt de travail, `site/` et `data/` dans l'arbre public). Le contrôle doit
échouer sur le défaut que l'audit du 13/09 a trouvé en ligne, et passer sur
l'arbre corrigé.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import qa_checks  # noqa: E402
import stamp_assets  # noqa: E402


def scratch(name: str) -> Path:
    """Un répertoire neuf sous data/_proofs_tmp/tests, jamais sous /tmp."""
    directory = ROOT / "data" / "_proofs_tmp" / "tests" / "release_gates" / name
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True)
    return directory


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def quietly(function, *args):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        status = function(*args)
    return status, buffer.getvalue()


def langs(*codes: str) -> str:
    rows = ",\n".join("    { code: '%s', label: '%s', col: '#000000' }" % (code, code)
                      for code in codes)
    return "(function () {\n  var LANGS = [\n%s\n  ];\n})();\n" % rows


def site_tree(name, private=True, explorer=None, observatory=None,
              languages=None, relevance=None, weights=None):
    """Un arbre minimal : pages, graph.json, semantic.json, weights.json."""
    root = scratch(name)
    pages = root / "site" / "build-c" if private else root / "site"
    data = root / "site" / "data" if private else root / "data"
    write(pages / "index.html", "<!doctype html><title>Explorer</title>\n")
    languages = languages or ["en"] * 6 + ["de"] * 3 + ["la"]
    nodes, by_ppn = [], {}
    for number, code in enumerate(languages):
        ppn = "OR%04d" % number
        nodes.append({"id": "p:" + ppn, "k": "pub", "ppn": ppn, "lang": code})
        by_ppn[ppn] = {"r": (relevance or {}).get(code, "core")}
    nodes.append({"id": "s:allegory", "k": "subject"})
    write(data / "graph.json", json.dumps({"nodes": nodes, "edges": []}))
    write(pages / "assets" / "semantic.json", json.dumps({"byPpn": by_ppn}))
    identifiers = weights if weights is not None else sorted(by_ppn)
    write(pages / "assets" / "weights.json", json.dumps(
        {"total": len(identifiers), "w": {key: {"w": 0.5} for key in identifiers}}))
    write(pages / "assets" / "explorer.js", explorer or langs("en", "de", "oth"))
    write(pages / "assets" / "observatory.js", observatory or explorer or langs("en", "de", "oth"))
    return root


class SiteCodesTest(unittest.TestCase):
    """OR-04 : la légende des langues et les poids lus contre les données."""

    def test_codes_that_match_the_data_pass_in_both_geometries(self):
        for private in (True, False):
            root = site_tree("codes-ok-%s" % private, private=private)
            status, output = quietly(qa_checks.check_site_codes, root)
            self.assertEqual(status, 0, output)
            self.assertIn("en 6, de 3, hors légende 1", output)

    def test_marc_codes_against_iso_data_fail(self):
        """Le cas en ligne : eng/ger dans le script, en/de dans graph.json."""
        root = site_tree("codes-marc", explorer=langs("eng", "ger", "oth"))
        status, output = quietly(qa_checks.check_site_codes, root)
        self.assertEqual(status, 1)
        self.assertIn("« eng » ne compte aucune notice", output)
        self.assertIn("tombent hors des langues nommées", output)

    def test_only_the_counted_population_counts(self):
        """Une langue dont toutes les notices sont marginales compte zéro."""
        root = site_tree("codes-marginal", relevance={"de": "marginal"})
        status, output = quietly(qa_checks.check_site_codes, root)
        self.assertEqual(status, 1)
        self.assertIn("« de » ne compte aucune notice", output)

    def test_a_population_mostly_outside_the_legend_fails(self):
        root = site_tree("codes-other", languages=["en", "de"] + ["la"] * 8)
        status, output = quietly(qa_checks.check_site_codes, root)
        self.assertEqual(status, 1)
        self.assertIn("8 notices comptées sur 10", output)

    def test_the_two_screens_must_name_the_same_languages(self):
        root = site_tree("codes-screens", explorer=langs("en", "de", "oth"),
                         observatory=langs("en", "oth"))
        status, output = quietly(qa_checks.check_site_codes, root)
        self.assertEqual(status, 1)
        self.assertIn("ne nomment pas les mêmes langues", output)

    def test_weights_must_carry_the_graph_identifiers(self):
        identifiers = ["OR%04d" % number for number in range(9)] + ["ORstale"]
        root = site_tree("codes-weights", weights=identifiers)
        status, output = quietly(qa_checks.check_site_codes, root)
        self.assertEqual(status, 1)
        self.assertIn("sans poids : 1, ex. OR0009", output)
        self.assertIn("inconnus du graphe : 1, ex. ORstale", output)

    def test_a_missing_legend_fails(self):
        root = site_tree("codes-nolegend", explorer="(function () {})();\n")
        status, output = quietly(qa_checks.check_site_codes, root)
        self.assertEqual(status, 1)
        self.assertIn("aucun tableau LANGS lisible", output)


GOOD_PAGE = """<!doctype html>
<html lang="en"><head><title>Method</title>
<script type="application/ld+json">{"@type": "WebPage"}</script>
<link rel="stylesheet" href="assets/base.css">
</head><body><details open><summary>Pages</summary></details>
<script src="assets/chrome.js"></script></body></html>
"""

GOOD_404 = """<!doctype html>
<html lang="en"><head><title>Page not found</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/site/assets/base.css">
</head><body><a href="/site/methode.html">Method</a> <a href="#main">skip</a></body></html>
"""


def page_tree(name, page=GOOD_PAGE, not_found=GOOD_404, private=False):
    root = scratch(name)
    pages = root / "site" / "build-c" if private else root / "site"
    write(root / "index.html", '<!doctype html><title>x</title><a href="/site/welcome">x</a>\n')
    write(pages / "index.html", page)
    if not_found is not None:
        write(root / "404.html", not_found)
    return root


class ServedPagesTest(unittest.TestCase):
    """OR-33, OR-42 : les pages sous la politique du site, et une vraie 404."""

    def test_pages_without_inline_code_pass(self):
        for private in (True, False):
            root = page_tree("pages-ok-%s" % private, private=private)
            status, output = quietly(qa_checks.check_served_pages, root)
            self.assertEqual(status, 0, output)

    def test_the_shipped_not_found_page_passes(self):
        root = page_tree("pages-shipped", not_found=(ROOT / "404.html").read_text(encoding="utf-8"))
        status, output = quietly(qa_checks.check_served_pages, root)
        self.assertEqual(status, 0, output)

    def test_an_inline_script_fails(self):
        """Le cas de la page racine : une redirection par script en ligne."""
        page = GOOD_PAGE.replace("</body>", '<script>location.replace("/site/welcome");</script></body>')
        root = page_tree("pages-inline", page=page)
        status, output = quietly(qa_checks.check_served_pages, root)
        self.assertEqual(status, 1)
        self.assertIn("script en ligne", output)

    def test_an_event_handler_or_a_javascript_url_fails(self):
        for label, markup in (("handler", '<button onclick="go()">Go</button>'),
                              ("url", '<a href="javascript:go()">Go</a>')):
            page = GOOD_PAGE.replace("<body>", "<body>" + markup)
            root = page_tree("pages-" + label, page=page)
            status, output = quietly(qa_checks.check_served_pages, root)
            self.assertEqual(status, 1, label)
            self.assertIn("exécute du code dans le balisage", output)

    def test_a_missing_not_found_page_fails(self):
        root = page_tree("pages-no404", not_found=None)
        status, output = quietly(qa_checks.check_served_pages, root)
        self.assertEqual(status, 1)
        self.assertIn("404.html absent", output)

    def test_a_not_found_page_must_be_absolute_and_unindexed(self):
        for label, markup, expected in (
                ("relative", GOOD_404.replace("/site/assets/base.css", "assets/base.css"), "est relatif"),
                ("indexed", GOOD_404.replace('<meta name="robots" content="noindex">', ""), "noindex"),
                ("canonical", GOOD_404.replace("</head>", '<link rel="canonical" href="https://example.org/">'
                                                          "</head>"), "canonique")):
            root = page_tree("pages-404-" + label, not_found=markup)
            status, output = quietly(qa_checks.check_served_pages, root)
            self.assertEqual(status, 1, label)
            self.assertIn(expected, output)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:8]


def asset_tree(name, private=True):
    """Pages, une feuille, et une chaîne de modules avec une dépendance partagée."""
    root = scratch(name)
    pages = root / "site" / "build-c" if private else root / "site"
    assets = pages / "assets"
    write(assets / "vendor" / "three.js", "export const A = 1;\n")
    write(assets / "vendor" / "addon.js", "import {\n  A\n} from './three.js';\nexport const B = A;\n")
    write(assets / "field.js", "import * as THREE from './vendor/three.js';\n"
                               "import { B } from './vendor/addon.js';\nexport const F = B;\n")
    write(assets / "app.js", "import { F } from './field.js';\n"
                             "const later = () => import('./field.js?v=00000000');\n"
                             "const text = 'Abstract from ' + F;\n")
    write(assets / "chrome.js", "document.documentElement.dataset.ready = '1';\n")
    write(assets / "base.css", "body { margin: 0; }\n")
    # Une copie de conflit d'iCloud n'est ni lue ni tamponnée.
    write(assets / "app 2.js", "import { gone } from './missing.js';\n")
    write(pages / "index.html", '<link rel="stylesheet" href="assets/base.css">\n'
                                '<script src="assets/chrome.js?v=deadbeef"></script>\n'
                                '<script type="module" src="assets/app.js"></script>\n')
    write(root / "404.html", '<link rel="stylesheet" href="/site/assets/base.css">\n')
    return root, pages


class SelftestScriptTest(unittest.TestCase):
    """Ce que le selftest rejoue dans un clone : les contrôles ajoutés le 13/09, et un
    serveur attendu plutôt que deviné."""

    @classmethod
    def setUpClass(cls):
        cls.script = (ROOT / "scripts" / "selftest_public.sh").read_text(encoding="utf-8")

    def test_the_new_gates_are_replayed(self):
        for gate in ("build_public_snapshot.py\" --check", "build_primary_layer.py\" --check",
                     "build_cite_data.py\" --check", "qa/check_crossings.py", "qa/check_source_id_continuity.py"):
            self.assertIn(gate, self.script)

    def test_the_local_server_is_polled_not_slept_on(self):
        serve = self.script.index("python3 -m http.server")
        first_page = self.script.index("for page in index.html")
        between = self.script[serve:first_page]
        self.assertNotRegex(between, r"\n\s*sleep \d")
        self.assertIn("urllib.request.urlopen", between)

    def test_the_data_layer_is_served_from_the_geometry_of_the_clone(self):
        # site/data dans l'arbre de travail : data/graph.json en dur y répondait 404
        self.assertIn("DATA=site/data", self.script)
        self.assertIn('"$DATA/graph.json"', self.script)
        self.assertNotIn("for asset in data/graph.json", self.script)

    def test_the_claims_command_must_find_a_position(self):
        self.assertIn('["matched"]', self.script)
        self.assertRegex(self.script, r'\[ "\$\{claims:-0\}" -gt 0 \]')


class StampAssetsTest(unittest.TestCase):
    """OR-66 : empreintes dans les deux géométries, imports de modules compris."""

    def stamp(self, root, *extra):
        return quietly(stamp_assets.main, ["--root", str(root), *extra])

    def test_both_geometries_are_found_and_stamped(self):
        for private in (True, False):
            root, pages = asset_tree("stamp-geometry-%s" % private, private=private)
            self.assertEqual(stamp_assets.pages_dir(root), pages)
            status, output = self.stamp(root, "--check")
            self.assertEqual(status, 1, output)
            self.assertIn("app.js: empreintes absentes ou périmées", output)
            self.assertEqual(self.stamp(root)[0], 0)
            status, output = self.stamp(root, "--check")
            self.assertEqual(status, 0, output)
            self.assertIn("empreintes à jour", output)

    def test_modules_are_stamped_leaves_first_under_one_url(self):
        root, pages = asset_tree("stamp-modules")
        self.assertEqual(self.stamp(root)[0], 0)
        assets = pages / "assets"
        three = sha((assets / "vendor" / "three.js").read_bytes())
        addon = (assets / "vendor" / "addon.js").read_text(encoding="utf-8")
        field = (assets / "field.js").read_text(encoding="utf-8")
        app = (assets / "app.js").read_text(encoding="utf-8")
        # Les deux importeurs de three.js le demandent sous la même empreinte.
        self.assertIn("from './three.js?v=%s'" % three, addon)
        self.assertIn("from './vendor/three.js?v=%s'" % three, field)
        addon_stamp = sha((assets / "vendor" / "addon.js").read_bytes())
        self.assertIn("from './vendor/addon.js?v=%s'" % addon_stamp, field)
        field_stamp = sha((assets / "field.js").read_bytes())
        self.assertIn("from './field.js?v=%s'" % field_stamp, app)
        self.assertIn("import('./field.js?v=%s')" % field_stamp, app)
        self.assertIn("'Abstract from '", app)
        index = (pages / "index.html").read_text(encoding="utf-8")
        self.assertIn("assets/app.js?v=%s" % sha((assets / "app.js").read_bytes()), index)
        self.assertIn("assets/chrome.js?v=%s" % sha((assets / "chrome.js").read_bytes()), index)
        not_found = (root / "404.html").read_text(encoding="utf-8")
        self.assertIn("/site/assets/base.css?v=%s" % sha((assets / "base.css").read_bytes()), not_found)
        self.assertEqual((assets / "app 2.js").read_text(encoding="utf-8"),
                         "import { gone } from './missing.js';\n")
        self.assertIn("0 fichier(s) tamponné(s)", self.stamp(root)[1])

    def test_a_changed_leaf_moves_every_parent_stamp(self):
        root, pages = asset_tree("stamp-cascade")
        self.assertEqual(self.stamp(root)[0], 0)
        write(pages / "assets" / "vendor" / "three.js", "export const A = 2;\n")
        status, output = self.stamp(root, "--check")
        self.assertEqual(status, 1)
        for name in ("vendor/addon.js", "field.js", "app.js", "index.html"):
            self.assertIn(name + ": empreintes absentes ou périmées", output)
        self.assertNotIn("chrome.js:", output)
        self.assertEqual(self.stamp(root)[0], 0)
        self.assertEqual(self.stamp(root, "--check")[0], 0)

    def test_a_missing_module_is_reported(self):
        root, pages = asset_tree("stamp-missing")
        write(pages / "assets" / "app.js", "import { F } from './nowhere.js';\n")
        status, output = self.stamp(root, "--check")
        self.assertEqual(status, 1)
        self.assertIn("./nowhere.js introuvable", output)


# ---------------------------------------------------------------------------
# Audit du 13/09 : références de continuité, node, liens de notice, images
# ---------------------------------------------------------------------------

import os  # noqa: E402
import struct  # noqa: E402
import subprocess  # noqa: E402
import urllib.error  # noqa: E402
import zlib  # noqa: E402

import check_record_links  # noqa: E402
import strip_image_metadata  # noqa: E402

TOOLS = next(path for path in (ROOT / "site" / "build-c" / "tools", ROOT / "site" / "tools")
             if path.is_dir())
QA = TOOLS.parent / "qa"


def git(directory: Path, *arguments: str) -> None:
    subprocess.run(["git", "-c", "user.name=Origenality tests", "-c", "user.email=noreply@example.com",
                    "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *arguments],
                   cwd=directory, check=True, capture_output=True, text=True)


def graph_of(*pairs) -> str:
    nodes = [{"k": "pub", "ppn": "OR%d" % n, "src": [source],
              "source_ids": [{"source": source, "id": ident}]}
             for n, (source, ident) in enumerate(pairs)]
    return json.dumps({"nodes": nodes, "edges": []})


class ContinuityReferenceTest(unittest.TestCase):
    """C-2 : dans un clone public, le contrôle comparait HEAD à lui-même et passait."""

    def clone(self, name: str) -> Path:
        root = scratch("continuity-" + name)
        write(root / "CITATION.cff", "cff-version: 1.2.0\n")
        write(root / "README.md", "# clone\n")
        (root / "site" / "qa").mkdir(parents=True)
        (root / "site" / "tools").mkdir(parents=True)
        shutil.copy2(QA / "check_source_id_continuity.py", root / "site" / "qa")
        shutil.copy2(TOOLS / "tree_paths.py", root / "site" / "tools")
        git(root, "init", "-q")
        return root

    def commit(self, root: Path, graph: str, message: str) -> None:
        write(root / "data" / "graph.json", graph)
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", message)

    def check(self, root: Path, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(root / "site" / "qa" / "check_source_id_continuity.py"),
                               *arguments], cwd=root, capture_output=True, text=True,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))

    def test_a_clone_without_an_earlier_graph_fails_unless_told(self):
        root = self.clone("first")
        self.commit(root, graph_of(("k10plus", "1")), "first release")
        answer = self.check(root)
        self.assertEqual(answer.returncode, 1, answer.stdout)
        self.assertIn("FAIL: no previous published graph", answer.stdout)
        answer = self.check(root, "--allow-no-reference")
        self.assertEqual(answer.returncode, 0, answer.stdout)

    def test_the_previous_release_is_read_from_the_history_and_a_lost_id_fails(self):
        root = self.clone("mutated")
        self.commit(root, graph_of(("k10plus", "1"), ("sudoc", "2")), "release one")
        self.commit(root, graph_of(("k10plus", "1")), "release two loses sudoc:2")
        answer = self.check(root)
        self.assertEqual(answer.returncode, 1, answer.stdout)
        self.assertIn("lost: sudoc:2", answer.stdout)
        self.assertIn("the most recent commit whose graph differs", answer.stdout)
        # Une troisième publication qui garde tout ce que la deuxième portait passe.
        self.commit(root, graph_of(("k10plus", "1"), ("b3kat", "BV3")), "release three")
        answer = self.check(root)
        self.assertEqual(answer.returncode, 0, answer.stdout)
        # Une référence nommée l'emporte sur le défaut.
        first = subprocess.run(["git", "rev-list", "--max-parents=0", "HEAD"], cwd=root,
                               capture_output=True, text=True).stdout.strip()
        answer = self.check(root, "--ref", first)
        self.assertEqual(answer.returncode, 1, answer.stdout)
        self.assertIn("lost: sudoc:2", answer.stdout)


class CrossingsNodeTest(unittest.TestCase):
    """C-8 : sans node, le contrôle des croisements sortait en 0 et sautait 1 553 liens."""

    def run_without_node(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(QA / "check_crossings.py"), *arguments],
                              cwd=ROOT, capture_output=True, text=True,
                              env=dict(os.environ, PATH=str(scratch("no-node")),
                                       PYTHONDONTWRITEBYTECODE="1"))

    def test_a_missing_node_fails(self):
        answer = self.run_without_node()
        self.assertEqual(answer.returncode, 1, answer.stdout + answer.stderr)
        self.assertIn("node absent", answer.stdout)

    def test_no_node_recounts_and_says_so(self):
        answer = self.run_without_node("--no-node")
        self.assertEqual(answer.returncode, 0, answer.stdout + answer.stderr)
        self.assertIn("--no-node", answer.stdout)


class SelftestNodeAndStructureTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.script = (ROOT / "scripts" / "selftest_public.sh").read_text(encoding="utf-8")

    def test_a_missing_node_is_a_failure(self):
        self.assertNotIn("tests node non lancés", self.script)
        self.assertNotIn("parité de la recherche non contrôlée", self.script)
        self.assertIn('command -v node >/dev/null 2>&1 || fail', self.script)

    def test_the_snapshot_check_in_a_clone_is_named_structure_only(self):
        self.assertIn("--check --structure-only", self.script)
        self.assertIn("structure, not content", self.script)
        self.assertNotIn("--allow-no-reference", self.script)

    def test_the_workflow_keeps_the_history_for_the_continuity_check(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("fetch-depth: 0", workflow)
        self.assertNotIn("sitemap check dates each page", workflow)


class BackfillHostTest(unittest.TestCase):
    """D-P2-4 : 130 notices B3Kat liaient une notice de la Gnomon, et le contrôle passait."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(TOOLS))
        import backfill_record_urls  # noqa: E402
        cls.backfill = backfill_record_urls

    def graph(self, name: str, url: str) -> Path:
        path = scratch("backfill-" + name) / "graph.json"
        path.write_text(json.dumps({"nodes": [{"k": "pub", "src": ["b3kat"], "ppn": "BV003571296",
                                               "url": url, "source_ids": [
                                                   {"source": "b3kat", "id": "BV003571296", "url": url}]}]}),
                        encoding="utf-8")
        return path

    def test_a_link_on_another_database_fails_the_check(self):
        path = self.graph("gbd", "https://www.gbd.digital/gbd/Record/BV003571296")
        status, _ = quietly(self.backfill.main, ["--check", "--graph", str(path)])
        self.assertEqual(status, 1)
        status, _ = quietly(self.backfill.main, ["--graph", str(path)])
        self.assertEqual(status, 0)
        repaired = json.loads(path.read_text(encoding="utf-8"))["nodes"][0]
        self.assertEqual(repaired["url"], "https://www.gateway-bayern.de/BV003571296")
        self.assertEqual(quietly(self.backfill.main, ["--check", "--graph", str(path)])[0], 0)

    def test_the_templates_are_read_from_the_data_policy(self):
        self.assertNotIn("TEMPLATES = {", (TOOLS / "backfill_record_urls.py").read_text(encoding="utf-8"))
        self.assertEqual(self.backfill.record_url("gnomon-gbd", "BV046495281"),
                         "https://www.gbd.digital/gbd/Record/BV046495281")


class FakeAnswer:
    def __init__(self, body: bytes, status: int = 200, url: str = ""):
        self.body, self.status, self.url = body, status, url

    def read(self, size=-1):
        return self.body

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class RecordLinksTest(unittest.TestCase):
    """Le contrôle réseau des liens de notice, rejoué sans réseau."""

    def test_a_link_must_follow_its_declared_pattern(self):
        pattern = "https://www.gbd.digital/gbd/Record/{id}"
        self.assertTrue(check_record_links.follows_pattern(
            "https://www.gbd.digital/gbd/Record/BV1", "BV1", pattern))
        self.assertFalse(check_record_links.follows_pattern(
            "https://www.gbd.digital/Record/BV1", "BV1", pattern))
        self.assertTrue(check_record_links.follows_pattern("https://doi.org/10.1/x", "BV1", pattern))

    def test_the_sample_takes_at_most_n_links_per_source_in_graph_order(self):
        graph = json.loads(graph_of(*[("sudoc", str(n)) for n in range(7)] + [("loc", "9")]))
        for node in graph["nodes"]:
            entry = node["source_ids"][0]
            entry["url"] = "https://example.org/%s/%s" % (entry["source"], entry["id"])
        picked = check_record_links.sample(graph, 5)
        self.assertEqual([ident for ident, _ in picked["sudoc"]], ["0", "1", "2", "3", "4"])
        self.assertEqual(len(picked["loc"]), 1)

    def test_status_errors_and_error_pages_do_not_resolve(self):
        throttle = check_record_links.Throttle(interval=0)

        def missing(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

        self.assertEqual(check_record_links.probe("https://a.example/1", throttle, missing),
                         (False, "HTTP 404"))
        error_page = lambda request, timeout: FakeAnswer(b"<title>Seite nicht gefunden</title>")
        self.assertFalse(check_record_links.probe("https://a.example/2", throttle, error_page)[0])
        record = lambda request, timeout: FakeAnswer(b"<title>Gateway Bayern</title>BV1",
                                                     url="https://a.example/2")
        self.assertEqual(check_record_links.probe("https://a.example/2", throttle, record),
                         (True, "HTTP 200"))

    def test_one_request_per_interval_per_host(self):
        now, slept = [100.0], []
        throttle = check_record_links.Throttle(interval=1.0, clock=lambda: now[0],
                                               sleep=lambda s: slept.append(s))
        throttle.wait("a.example")
        throttle.wait("b.example")
        now[0] += 0.25
        throttle.wait("a.example")
        self.assertEqual(slept, [0.75])

    def test_the_run_reports_each_failing_link(self):
        folder = scratch("record-links")
        graph = json.loads(graph_of(("b3kat", "BV1"), ("gnomon-gbd", "BV2")))
        graph["nodes"][0]["source_ids"][0]["url"] = "https://www.gateway-bayern.de/BV1"
        graph["nodes"][1]["source_ids"][0]["url"] = "https://www.gbd.digital/Record/BV2"
        write(folder / "graph.json", json.dumps(graph))
        write(folder / "META.json", json.dumps({"sources_present": [
            {"source": "b3kat", "record_url_pattern": "https://www.gateway-bayern.de/{id}"},
            {"source": "gnomon-gbd", "record_url_pattern": "https://www.gbd.digital/Record/{id}"}]}))

        def opener(request, timeout):
            if "gbd.digital" in request.full_url:
                raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)
            return FakeAnswer(b"<title>Gateway Bayern</title>", url=request.full_url)

        status, output = quietly(lambda: check_record_links.main(
            ["--graph", str(folder / "graph.json"), "--meta", str(folder / "META.json"),
             "--report", str(folder / "report.json")], opener=opener,
            throttle=check_record_links.Throttle(interval=0)))
        self.assertEqual(status, 1, output)
        self.assertIn("NOT RESOLVING gnomon-gbd:BV2", output)
        report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["b3kat"]["resolving"], 1)


def png_image(rows, width, extra=()):
    """Un PNG RGB 8 bits dont chaque ligne porte son filtre : [(filtre, octets), …]."""
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    header = struct.pack(">IIBBBBB", width, len(rows), 8, 2, 0, 0, 0)
    raw = b"".join(bytes([kind]) + bytes(line) for kind, line in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + b"".join(chunk(k, b) for k, b in extra)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def jpeg_image(extra=(), scan=b"\x12\x34\x56"):
    def segment(marker, body):
        return bytes([0xFF, marker]) + struct.pack(">H", len(body) + 2) + body
    return (b"\xff\xd8" + segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
            + b"".join(segment(m, b) for m, b in extra) + segment(0xDB, b"\x00" + bytes(64))
            + segment(0xC0, b"\x08\x00\x01\x00\x02\x01\x01\x11\x00")
            + segment(0xDA, b"\x01\x01\x00\x00\x3f\x00") + scan + b"\xff\xd9")


class StripImageMetadataTest(unittest.TestCase):
    """D-P0 : ce qui porte des métadonnées dans une image, et une image rendue à l'identique."""

    def test_png_filters_are_undone_before_the_pixels_are_compared(self):
        image = png_image([(1, [10, 20, 30, 5, 5, 5]), (2, [1, 1, 1, 1, 1, 1])], 2)
        width, height, pixels = strip_image_metadata.png_pixels(image)
        self.assertEqual((width, height), (2, 2))
        self.assertEqual(list(pixels), [10, 20, 30, 15, 25, 35, 11, 21, 31, 16, 26, 36])

    def test_a_png_loses_its_text_and_credential_chunks_and_keeps_its_pixels(self):
        rows = [(4, [9, 8, 7, 6, 5, 4]), (3, [1, 2, 3, 4, 5, 6])]
        image = png_image(rows, 2, extra=[(b"tEXt", b"Comment\x00made somewhere"),
                                          (b"caBX", b"manifest"), (b"pHYs", bytes(9))])
        self.assertEqual(strip_image_metadata.carriers(image, "a.png"), ["caBX", "tEXt"])
        stripped = strip_image_metadata.strip(image, "a.png")
        self.assertEqual(strip_image_metadata.carriers(stripped, "a.png"), [])
        self.assertIn(b"pHYs", stripped)
        self.assertEqual(strip_image_metadata.same_rendering(image, stripped, "a.png")[0], True)
        other = png_image([(4, [9, 8, 7, 6, 5, 4]), (3, [1, 2, 3, 4, 5, 7])], 2)
        self.assertFalse(strip_image_metadata.same_rendering(image, other, "a.png")[0])

    def test_a_jpeg_keeps_its_colour_profile_and_its_entropy_coded_data(self):
        icc = b"ICC_PROFILE\x00\x01\x01" + bytes(20)
        image = jpeg_image(extra=[(0xE1, b"Exif\x00\x00" + bytes(10)), (0xE2, icc),
                                  (0xED, b"Photoshop 3.0\x00"), (0xFE, b"a comment"),
                                  (0xEB, b"JP\x00\x00jumb")])
        self.assertEqual(strip_image_metadata.carriers(image, "b.jpg"),
                         ["APP1 Exif", "APP11 JP", "APP13 Photoshop 3.0", "COM"])
        stripped = strip_image_metadata.strip(image, "b.jpg")
        self.assertEqual(strip_image_metadata.carriers(stripped, "b.jpg"), [])
        self.assertIn(b"ICC_PROFILE", stripped)
        self.assertTrue(stripped.endswith(b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\x12\x34\x56\xff\xd9"))
        self.assertTrue(strip_image_metadata.same_rendering(image, stripped, "b.jpg")[0])

    def test_a_webp_loses_exif_and_xmp_and_their_flags(self):
        def chunk(kind, body):
            return kind + struct.pack("<I", len(body)) + body + (b"\x00" if len(body) & 1 else b"")
        body = b"WEBP" + chunk(b"VP8X", bytes([0x0C]) + bytes(9)) + chunk(b"VP8L", b"\x2f" + bytes(4)) \
            + chunk(b"EXIF", b"II*\x00") + chunk(b"XMP ", b"<x:xmpmeta/>")
        image = b"RIFF" + struct.pack("<I", len(body)) + body
        self.assertEqual(strip_image_metadata.carriers(image, "c.webp"), ["EXIF", "XMP"])
        stripped = strip_image_metadata.strip(image, "c.webp")
        self.assertEqual(strip_image_metadata.carriers(stripped, "c.webp"), [])
        self.assertEqual(stripped[20] & 0x0C, 0)

    def test_the_shipped_images_carry_no_metadata(self):
        for path in sorted((TOOLS.parent / "assets" / "marks").iterdir()):
            if path.suffix.lower() in strip_image_metadata.IMAGE_SUFFIXES:
                self.assertEqual(strip_image_metadata.carriers(path.read_bytes(), path.name), [], path.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
