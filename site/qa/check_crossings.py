#!/usr/bin/env python3
"""Croisements de l'Observatoire : recomptage indépendant, sortie du CLI, page.

La page (`assets/observatory.js`) et la ligne de commande (`origenality
crossings`) appellent la même fonction de `assets/observatory-core.js`. Ce
contrôle recompte les trois vues en Python, sans rien reprendre de ce fichier,
sur `graph.json` et `semantic.json`, et compare le résultat à la sortie du CLI
pour chaque vue. Il vérifie aussi que la page charge le noyau avant son script
et l'appelle, que les langues du noyau sont celles de la légende de
l'Observatoire, et qu'aucun texte des croisements ne parle de lacune,
d'originalité ou de terrain non étudié : une densité est un compte.

Chaque compte non nul que la grammaire de l'Explorateur sait nommer est un lien
vers la vue qui liste les mêmes notices (`crossingLinks` dans le noyau). Pour
chaque lien, le contrôle recompte la case en Python et fait tourner la requête du
lien dans `search-core.js` : la case, le recomptage et le compte que
l'Explorateur affiche doivent être le même nombre, et l'adresse doit porter la
requête. Il dit aussi combien de comptes non nuls restent sans lien.

    python3 site/build-c/qa/check_crossings.py

Sortie 0 quand tout concorde, 1 sinon. Sans node, la comparaison au CLI n'est
pas faite et le script le dit ; les contrôles statiques tournent quand même.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote_plus

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(BUILD, "tools"))
from tree_paths import data_dir, repository_root  # noqa: E402

ROOT = repository_root(HERE)
GRAPH = os.path.join(data_dir(ROOT), "graph.json")
SEMANTIC = os.path.join(BUILD, "assets", "semantic.json")
CORE = os.path.join(BUILD, "assets", "observatory-core.js")
PAGE_JS = os.path.join(BUILD, "assets", "observatory.js")
PAGE = os.path.join(BUILD, "observatoire.html")
CLI = os.path.join(ROOT, "cli", "origenality.mjs")

COUNTED = ("core", "partial")
LANGUAGES = ("en", "de", "it", "fr", "es")
OTHER = "oth"
ZERO_LANGUAGES = ("en", "de", "fr", "it")
FIRST_DECADE = 1950
PERIODS = ((1980, 1999), (2010, None))
DRIFT_FLOOR, WORK_FLOOR, THICK_WORK, LEAF_FLOOR = 10, 15, 50, 30
VIEWS = ("theme-decade", "work-domain", "domain-lang")
WORDS = re.compile(r"\bgaps?\b|\boriginal|\bunstudied", re.I)


def unique(items):
    out = []
    for item in items or []:
        if item not in out:
            out.append(item)
    return out


def share(n, total):
    return math.floor(n * 1000 / total + 0.5) / 10 if total else 0


def records(graph, sem):
    tags = sem["byPpn"]
    out = []
    for node in graph["nodes"]:
        if node.get("k") != "pub" or not node.get("ppn"):
            continue
        rec = tags.get(node["ppn"])
        if not rec or rec["r"] not in COUNTED:
            continue
        year = node.get("year")
        themes = unique(t for t in rec.get("t") or [] if t in sem["themes"])
        out.append({
            "year": year if isinstance(year, (int, float)) and not isinstance(year, bool) else None,
            "lang": node.get("lang") if node.get("lang") in LANGUAGES else OTHER,
            "sources": unique(node.get("src") or []),
            "themes": themes,
            "domains": unique(sem["themes"][t]["domain"] for t in themes),
            "works": unique(w for w in rec.get("w") or [] if w != "unspecified" and w in sem["works"]),
        })
    return out


def decade(year):
    if year is None:
        return "undated"
    if year < FIRST_DECADE:
        return "before-%d" % FIRST_DECADE
    return str(int(year // 10 * 10))


def leaves_of(sem, domain):
    return [t for t, v in sem["themes"].items() if v["domain"] == domain]


def count(recs, test):
    return sum(1 for r in recs if test(r))


def theme_decade(recs, sem):
    dated = [r["year"] for r in recs if r["year"] is not None]
    latest = max(dated) if dated else None
    last = max([FIRST_DECADE] + [int(y // 10 * 10) for y in dated if y >= FIRST_DECADE])
    columns = ["before-%d" % FIRST_DECADE] + [str(d) for d in range(FIRST_DECADE, last + 1, 10)] + ["undated"]
    periods = []
    for start, end in PERIODS:
        end = latest if end is None else end
        periods.append({"from": start, "to": end,
                        "records": count(recs, lambda r: r["year"] is not None and start <= r["year"] <= end)})

    def row(key, label, field):
        mine = [r for r in recs if key in r[field]]
        a = count(mine, lambda r: r["year"] is not None and periods[0]["from"] <= r["year"] <= periods[0]["to"])
        b = count(mine, lambda r: r["year"] is not None and periods[1]["from"] <= r["year"] <= periods[1]["to"])
        drift = None if a < DRIFT_FLOOR and b < DRIFT_FLOOR else {
            "from": a, "to": b, "from_share": share(a, periods[0]["records"]),
            "to_share": share(b, periods[1]["records"])}
        return {"key": key, "label": label, "total": len(mine),
                "cells": [count(mine, lambda r, c=c: decade(r["year"]) == c) for c in columns],
                "drift": drift}

    rows = []
    for domain, value in sem["domains"].items():
        entry = row(domain, value["label"], "domains")
        entry["leaves"] = [row(t, sem["themes"][t]["label"], "themes") for t in leaves_of(sem, domain)]
        rows.append(entry)
    sources = {}
    for r in recs:
        for s in r["sources"]:
            sources.setdefault(s, []).append(r)
    envelope = [{"source": s, "total": len(mine),
                 "cells": [count(mine, lambda r, c=c: decade(r["year"]) == c) for c in columns]}
                for s, mine in sorted(sources.items(), key=lambda kv: (-len(kv[1]), kv[0]))]
    hist = {}
    for r in recs:
        hist[str(len(r["themes"]))] = hist.get(str(len(r["themes"])), 0) + 1
    return {"view": "theme-decade", "counted": len(recs), "columns": columns, "latest_year": latest,
            "periods": periods, "drift_floor": DRIFT_FLOOR, "rows": rows,
            "column_totals": [count(recs, lambda r, c=c: decade(r["year"]) == c) for c in columns],
            "envelope": envelope, "themes_per_record": hist}


def work_domain(recs, sem):
    domains = list(sem["domains"])
    totals = {}
    for r in recs:
        for w in r["works"]:
            totals[w] = totals.get(w, 0) + 1
    works = sorted((w for w, n in totals.items() if n >= WORK_FLOOR), key=lambda w: (-totals[w], w))
    rows = [{"key": w, "label": sem["works"][w]["label"], "total": totals[w],
             "cells": [count(recs, lambda r, w=w, d=d: w in r["works"] and d in r["domains"]) for d in domains]}
            for w in works]
    return {"view": "work-domain", "counted": len(recs),
            "without_work": count(recs, lambda r: not r["works"]),
            "work_floor": WORK_FLOOR, "thick_floor": THICK_WORK,
            "columns": [{"key": d, "label": sem["domains"][d]["label"]} for d in domains],
            "rows": rows, "cells": len(rows) * len(domains),
            "empty_cells": sum(1 for r in rows for n in r["cells"] if not n),
            "thin": [{"key": r["key"], "label": r["label"], "total": r["total"],
                      "empty": [d for d, n in zip(domains, r["cells"]) if not n]}
                     for r in rows if r["total"] > THICK_WORK and not all(r["cells"])]}


def domain_language(recs, sem):
    cols = list(LANGUAGES) + [OTHER]

    def row(key, label, field):
        mine = [r for r in recs if key in r[field]]
        cells = [count(mine, lambda r, c=c: r["lang"] == c) for c in cols]
        return {"key": key, "label": label, "total": len(mine), "cells": cells,
                "shares": [share(n, len(mine)) for n in cells]}

    rows, zero = [], []
    for domain, value in sem["domains"].items():
        entry = row(domain, value["label"], "domains")
        entry["leaves"] = []
        for t in leaves_of(sem, domain):
            leaf = row(t, sem["themes"][t]["label"], "themes")
            entry["leaves"].append(leaf)
            missing = [c for c in ZERO_LANGUAGES if not leaf["cells"][cols.index(c)]]
            if leaf["total"] >= LEAF_FLOOR and missing:
                zero.append({"key": t, "label": leaf["label"], "total": leaf["total"], "languages": missing})
        rows.append(entry)
    baseline = [count(recs, lambda r, c=c: r["lang"] == c) for c in cols]
    return {"view": "domain-lang", "counted": len(recs), "columns": cols, "baseline": baseline,
            "baseline_shares": [share(n, len(recs)) for n in baseline], "rows": rows,
            "leaf_floor": LEAF_FLOOR, "zero_languages": list(ZERO_LANGUAGES), "zero": zero}


def first_difference(a, b, path="$"):
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                return "%s.%s: présent d'un seul côté" % (path, key)
            found = first_difference(a[key], b[key], "%s.%s" % (path, key))
            if found:
                return found
        return None
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return "%s: %d éléments contre %d" % (path, len(a), len(b))
        for i, (x, y) in enumerate(zip(a, b)):
            found = first_difference(x, y, "%s[%d]" % (path, i))
            if found:
                return found
        return None
    return None if a == b else "%s: %r contre %r" % (path, a, b)


# Les liens du noyau, et ce que l'Explorateur compte pour chacun : une requête de
# champs sans mot libre ni rubrique, dont le titre du panneau est le nombre de
# notices comptées qu'elle liste (explorer.js, headlineRecords).
LINKS_JS = r"""
const [build, data] = process.argv.slice(1);
const fs = require('fs'), path = require('path');
const C = require(path.join(build, 'assets', 'search-core.js'));
const X = require(path.join(build, 'assets', 'observatory-core.js'));
const read = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const graph = read(path.join(data, 'graph.json'));
const sem = read(path.join(build, 'assets', 'semantic.json'));
const absFile = path.join(data, 'abstracts.json');
const index = C.buildIndex(graph, sem, fs.existsSync(absFile) ? read(absFile) : null);
const out = [];
for (const view of X.VIEWS) {
  const v = X.crossing(view, graph, sem);
  for (const l of X.crossingLinks(v, sem)) {
    const r = C.search(index, l.query);
    const plain = !r.invalid && !r.normalisedEmpty && !r.terms.length && !r.vocabOnly.size;
    let explorer = null;
    if (plain) { explorer = 0; r.matched.forEach((i) => { if (index.records[i].dens) explorer++; }); }
    out.push({ view, row: l.row, col: l.col, n: l.n, query: l.query, href: X.explorerHref(l.query), explorer });
  }
}
process.stdout.write(JSON.stringify(out));
"""


def link_problems(recs, expected) -> list[str]:
    problems = []
    if shutil.which("node") is None:
        # Seulement sous --no-node : main() refuse sinon.
        print("node absent (--no-node) : liens vers l'Explorateur non recomptés")
        return problems
    run = subprocess.run(["node", "-e", LINKS_JS, BUILD, data_dir(ROOT)], capture_output=True, text=True, cwd=ROOT)
    if run.returncode != 0:
        return ["liens : node sort en %d, %s" % (run.returncode, run.stderr.strip()[-300:])]
    links = json.loads(run.stdout)
    periods = expected["theme-decade"]["periods"]
    fields = {"domain": "domains", "theme": "themes", "work": "works"}

    def row_test(kind, key):
        if kind == "all":
            return lambda r: True
        return lambda r: key in r[fields[kind]]

    def column_test(view, col):
        if col == "total":
            return lambda r: True
        if view == "theme-decade":
            if col in ("period-a", "period-b"):
                p = periods[0 if col == "period-a" else 1]
                return lambda r: r["year"] is not None and p["from"] <= r["year"] <= p["to"]
            if col == "undated":
                return None
            return lambda r: decade(r["year"]) == col
        if view == "work-domain":
            return lambda r: col in r["domains"]
        return lambda r: r["lang"] == col

    per_view = {}
    for link in links:
        where = "%s, %s %s, %s" % (link["view"], link["row"][0], link["row"][1] or "(pied)", link["col"])
        per_view[link["view"]] = per_view.get(link["view"], 0) + 1
        test = column_test(link["view"], link["col"])
        if test is None:
            problems.append("%s : lien sur une colonne qu'aucune requête ne nomme" % where)
            continue
        rows = row_test(*link["row"])
        n = count(recs, lambda r: rows(r) and test(r))
        if link["n"] != n:
            problems.append("%s : la case vaut %d, le recomptage %d" % (where, link["n"], n))
        if link["explorer"] != n:
            problems.append("%s : l'Explorateur compte %s pour « %s », le recomptage %d"
                            % (where, link["explorer"], link["query"], n))
        address = link["href"].split("#q=", 1)
        if len(address) != 2 or unquote_plus(address[1]) != link["query"]:
            problems.append("%s : l'adresse %s ne porte pas la requête « %s »" % (where, link["href"], link["query"]))

    td = expected["theme-decade"]
    at = td["columns"].index("undated")
    undated = sum(1 for d in td["rows"] for r in [d] + d["leaves"] if r["cells"][at]) + (1 if td["column_totals"][at] else 0)
    sources = sum(1 for s in td["envelope"] for n in [s["total"]] + s["cells"] if n)
    print("liens vers l'Explorateur : %s ; chaque case recomptée et relue dans search-core.js"
          % ", ".join("%s %d" % (v, per_view.get(v, 0)) for v in VIEWS))
    print("comptes non nuls sans lien : %d dans la colonne sans année, %d dans la table des sources"
          % (undated, sources))
    return problems


def static_problems() -> list[str]:
    problems = []
    page = open(PAGE, encoding="utf-8").read()
    core_tag = page.find('src="assets/observatory-core.js')
    page_tag = page.find('src="assets/observatory.js')
    if core_tag < 0 or page_tag < 0 or core_tag > page_tag:
        problems.append("observatoire.html ne charge pas observatory-core.js avant observatory.js")
    script = open(PAGE_JS, encoding="utf-8").read()
    for view in VIEWS:
        if "core.crossing('%s'" % view not in script:
            problems.append("observatory.js n'appelle pas le noyau pour %s" % view)
    if "core.crossingLinks(" not in script:
        problems.append("observatory.js ne lit pas les liens du noyau (crossingLinks)")
    legend = re.search(r"var LANGS = \[(.*?)\];", script, re.S)
    legend_codes = re.findall(r"code:\s*'([a-z]+)'", legend.group(1)) if legend else []
    core = open(CORE, encoding="utf-8").read()
    core_codes = re.search(r"var LANGUAGES = \[(.*?)\];", core)
    core_codes = re.findall(r"'([a-z]+)'", core_codes.group(1)) if core_codes else []
    if [c for c in legend_codes if c != OTHER] != core_codes:
        problems.append("langues du noyau %s, légende de l'Observatoire %s" % (core_codes, legend_codes))
    region = re.search(r"/\* crossings \*/(.*?)/\* /crossings \*/", script, re.S)
    section = re.search(r'<section id="crossings">(.*?)</section>', page, re.S)
    if not region or not section:
        problems.append("bornes des croisements introuvables dans observatory.js ou observatoire.html")
    for name, text in (("observatory-core.js", core), ("observatory.js (croisements)", region and region.group(1)),
                       ("observatoire.html (croisements)", section and section.group(1))):
        for match in WORDS.finditer(text or ""):
            problems.append("%s porte « %s » : un compte n'est pas un verdict" % (name, match.group(0)))
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0] if __doc__ else None)
    parser.add_argument("--no-node", action="store_true",
                        help="recount without node: no CLI comparison and no link check")
    args = parser.parse_args(argv)
    if shutil.which("node") is None and not args.no_node:
        # Le contrôle sortait en 0 sans node, en sautant la comparaison au CLI et la
        # relecture de chaque lien vers l'Explorateur (audit du 13/09, C-8).
        print("ÉCHEC : node absent, donc ni la sortie du CLI ni les liens vers l'Explorateur "
              "ne sont contrôlés ; installer node, ou passer --no-node pour le seul recomptage")
        return 1
    with open(GRAPH, encoding="utf-8") as handle:
        graph = json.load(handle)
    with open(SEMANTIC, encoding="utf-8") as handle:
        sem = json.load(handle)
    recs = records(graph, sem)
    expected = {"theme-decade": theme_decade(recs, sem), "work-domain": work_domain(recs, sem),
                "domain-lang": domain_language(recs, sem)}
    problems = static_problems()
    judaism = next(r for r in expected["theme-decade"]["rows"] if r["key"] == "judaism") \
        if "judaism" in sem["domains"] else None
    print("notices comptées : %d" % len(recs))
    if judaism:
        print("judaism par décennie : %s" % ", ".join(
            "%s %d" % (c, n) for c, n in zip(expected["theme-decade"]["columns"], judaism["cells"])))
    wd = expected["work-domain"]
    print("œuvres en ligne : %d, cases vides %d sur %d" % (len(wd["rows"]), wd["empty_cells"], wd["cells"]))

    if shutil.which("node") is None:
        print("node absent (--no-node) : sortie du CLI non comparée")
    else:
        for view in VIEWS:
            run = subprocess.run(["node", CLI, "crossings", view, "--local", ROOT],
                                 capture_output=True, text=True, cwd=ROOT)
            if run.returncode != 0:
                problems.append("CLI crossings %s : sortie %d, %s" % (view, run.returncode, run.stderr.strip()[-300:]))
                continue
            found = first_difference(json.loads(run.stdout), expected[view])
            if found:
                problems.append("CLI crossings %s et recomptage : %s" % (view, found))
            else:
                print("CLI crossings %-12s = recomptage indépendant" % view)
    problems.extend(link_problems(recs, expected))
    for line in problems:
        print("   CROISEMENTS EN DÉFAUT  %s" % line)
    print("croisements en défaut : %d" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
