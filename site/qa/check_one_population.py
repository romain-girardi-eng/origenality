#!/usr/bin/env python3
"""One population per screen — the check, run against the data rather than the page.

The rule the site states: every figure it prints counts the records classed
`core` or `partial`. A record where Origen is merely mentioned, and one held as
not about him, are returned by a search and listed in a panel, and they enter no
figure.

This script recomputes, from `site/data/graph.json` and
`site/build-c/assets/semantic.json`, the numbers each surface should be printing,
then compares them with the numbers actually read off the running pages, stored
in `measured_<date>.json` next to this file. It exits non-zero on the first
disagreement, so a later change that reintroduces a second population fails here
before anybody has to notice it by eye.

    python3 site/build-c/qa/check_one_population.py
    python3 site/build-c/qa/check_one_population.py --measured qa/measured_2026-08-17.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(BUILD, "tools"))
from tree_paths import data_dir, repository_root  # noqa: E402

# La géométrie change d'un arbre à l'autre — `site/build-c/qa/` ici, `site/qa/`
# dans un clone public — et une racine comptée en marches désigne alors le
# répertoire au-dessus du dépôt. On la cherche (voir `tools/tree_paths.py`).
ROOT = repository_root(HERE)
GRAPH = os.path.join(data_dir(ROOT), "graph.json")
SEMANTIC = os.path.join(BUILD, "assets", "semantic.json")

COUNTED_CLASSES = ("core", "partial")
LANGS = [("eng", "English"), ("ger", "German"), ("ita", "Italian"),
         ("fre", "French"), ("spa", "Spanish"), ("oth", "Other or none")]
LANG_CODES = {code for code, _ in LANGS if code != "oth"}


def nf(n: int) -> str:
    """the site's thousands separator: a space, as in its own prose"""
    return f"{n:,}".replace(",", " ").replace(" ", " ")


def load():
    with open(GRAPH, encoding="utf-8") as fh:
        graph = json.load(fh)
    with open(SEMANTIC, encoding="utf-8") as fh:
        semantic = json.load(fh)
    tags = semantic["byPpn"]
    counted, mentioned, aside = [], [], []
    for node in graph["nodes"]:
        if node.get("k") != "pub" or not node.get("ppn"):
            continue
        rec = tags.get(node["ppn"])
        if rec and rec["r"] in COUNTED_CLASSES:
            counted.append((node, rec))
        elif rec and rec["r"] == "marginal":
            mentioned.append((node, rec))
        else:
            aside.append((node, rec))
    return semantic, counted, mentioned, aside


def lang_of(node) -> str:
    code = node.get("lang")
    return code if code in LANG_CODES else "oth"


def expected(semantic, counted, mentioned, aside):
    exp = {}
    exp["counted"] = len(counted)
    exp["mentioned"] = len(mentioned)
    exp["aside"] = len(aside)

    by_lang = {}
    by_fmt = {}
    by_decade = {}
    dated = 0
    for node, _ in counted:
        by_lang[lang_of(node)] = by_lang.get(lang_of(node), 0) + 1
        fmt = node.get("type") or "Not coded"
        by_fmt[fmt] = by_fmt.get(fmt, 0) + 1
        year = node.get("year")
        if year and year >= 1900:
            dated += 1
            decade = year // 10 * 10
            row = by_decade.setdefault(decade, {})
            row[lang_of(node)] = row.get(lang_of(node), 0) + 1
            row["all"] = row.get("all", 0) + 1
    exp["by_language"] = by_lang
    exp["by_format"] = by_fmt
    exp["by_decade"] = by_decade
    exp["dated_1900_on"] = dated

    approaches = {}
    works = {}
    for _, rec in counted:
        for key in rec.get("a", []):
            approaches[key] = approaches.get(key, 0) + 1
        for key in rec.get("w", []):
            if key != "unspecified":
                works[key] = works.get(key, 0) + 1
    exp["by_approach"] = {semantic["approaches"][k]["label"]: v
                          for k, v in approaches.items() if k in semantic["approaches"]}
    exp["by_work"] = {semantic["works"][k]["label"]: v
                      for k, v in works.items() if k in semantic["works"]}

    review = {}
    repaired = (semantic.get("source") or {}).get("needs_review_repaired")
    for rec in semantic["byPpn"].values():
        if rec.get("n"):
            review[rec["r"]] = review.get(rec["r"], 0) + 1
    exp["needs_review"] = review
    exp["needs_review_repaired"] = repaired
    return exp


def num(text: str) -> int:
    return int("".join(ch for ch in text if ch.isdigit()))


def compare(exp, measured, problems):
    def want(label, got, wanted):
        if got != wanted:
            problems.append(f"{label}: page says {got!r}, data says {wanted!r}")

    # the header of the Explorer
    scope = measured["explorer_scope"]
    for value in (exp["counted"], exp["mentioned"], exp["aside"]):
        if nf(value) not in scope:
            problems.append(f"explorer header does not carry {nf(value)}: {scope!r}")

    # the band of three sets, which is where the two populations used to part:
    # it was drawn on the tagged records alone and printed 5 held aside under a
    # header that said 33
    sets = [value for value, _label in measured.get("observatory_sets") or []]
    if sets:
        for value in (exp["counted"], exp["mentioned"], exp["aside"]):
            if nf(value) not in sets:
                problems.append(f"the band of three sets does not carry {nf(value)}: {sets!r}")

    # the sentence under the legend, which repeats the three counts in words
    held = measured.get("explorer_held")
    if held:
        for value in (exp["counted"], exp["mentioned"], exp["aside"]):
            if nf(value) not in held:
                problems.append(f"the note under the legend does not carry {nf(value)}: {held!r}")

    # the legend, and the fourth question, on the same numbers as the Observatory
    legend = {label: num(value) for label, value in measured["explorer_legend"]}
    chips = {label: num(value) for label, value in measured["wizard"]["lang"]["chips"]}
    bars = {label: num(value) for label, value in measured["observatory_lang"]}
    for code, label in LANGS:
        wanted = exp["by_language"].get(code, 0)
        if not wanted:
            continue
        want(f"legend / {label}", legend.get(label), wanted)
        want(f"question 4 / {label}", chips.get(label), wanted)
        want(f"Observatory language bar / {label}", bars.get(label), wanted)

    # formats
    fmt = {label: num(value) for label, value in measured["observatory_fmt"]}
    for label, value in sorted(exp["by_format"].items(), key=lambda kv: -kv[1])[:7]:
        want(f"Observatory format / {label}", fmt.get(label), value)

    # the decade table, cell by cell
    head = measured["observatory_decade_head"]
    for row in measured["observatory_decades"]:
        decade = num(row[0])
        wanted_row = exp["by_decade"].get(decade, {})
        for column, cell in zip(head[1:], row[1:]):
            code = next((c for c, label in LANGS if label == column), "all")
            want(f"decade table / {decade}s / {column}",
                 num(cell), wanted_row.get(code, 0))

    # the angles of the second question
    appr = {label: num(value) for label, value in measured["wizard"]["approach"]["chips"]}
    for label, value in exp["by_approach"].items():
        want(f"question 2 / {label}", appr.get(label), value)

    # the works of the first question
    works = {label: num(value) for label, value in measured["wizard"]["work"]["chips"]}
    for label, value in exp["by_work"].items():
        want(f"question 1 / {label}", works.get(label), value)

    # What the flag for review actually covers. The note gives three numbers —
    # held aside, mentioned only, inside the count — and the last one is the sum
    # of the two counted classes, so it is compared as such rather than class by
    # class: looking for each class separately passed on a substring the note
    # happened to hold, which is not a check.
    note = measured["observatory_review"]
    review = exp["needs_review"]
    wanted = {
        "held aside": review.get("none", 0),
        "mentioned only": review.get("marginal", 0),
        "inside the count": sum(review.get(key, 0) for key in COUNTED_CLASSES),
        "repaired": exp["needs_review_repaired"],
    }
    for label, value in wanted.items():
        if str(value) not in note:
            problems.append(f"review note does not carry {value} for {label}: {note!r}")

    # and the line that says what the other records are
    note = measured["observatory_timenote"]
    for value in (exp["mentioned"], exp["aside"], exp["mentioned"] + exp["aside"]):
        if nf(value) not in note:
            problems.append(f"the decade note does not say that {nf(value)} records are outside it")
    if "not about" not in note:
        problems.append("the decade note does not name the records held aside")


# The files whose rendering the archived capture read. If one of them is newer
# than the capture, the capture no longer describes the page that would render
# now, and the second half of this check is out of date even when it passes.
RENDERED_FILES = [
    "index.html", "observatoire.html", "methode.html", "credits.html",
    os.path.join("assets", "explorer.js"), os.path.join("assets", "observatory.js"),
    os.path.join("assets", "semantic.json"),
]


def describe_capture(path: str, measured: dict) -> None:
    """Say, in the output, when the page figures were read and from what.

    This script compares live data with numbers read off the rendered pages and
    stored. That second half is only as fresh as its capture, so the capture
    says where and when it was taken — `qa/capture_population.sh` renders the
    pages without a screen and writes the line — and this reports it rather than
    letting a stored file pass for a browser run of today.
    """
    stamp = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
    print(f"\npage figures: read off the rendered pages and stored in "
          f"{os.path.basename(path)}, last written {stamp}")
    if measured.get("_measured"):
        print(f"             capture: {measured['_measured']}")
    newer = []
    for name in RENDERED_FILES:
        candidate = os.path.join(BUILD, name)
        if os.path.exists(candidate) and os.path.getmtime(candidate) > os.path.getmtime(path):
            when = datetime.fromtimestamp(os.path.getmtime(candidate)).strftime("%Y-%m-%d %H:%M")
            newer.append(f"{name} ({when})")
    if newer:
        print("             changed since that capture, so the pages may now render "
              "other numbers: " + ", ".join(newer))
    else:
        print("             no page or asset it measured has changed since")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--measured", default=os.path.join(HERE, "measured_2026-08-17.json"))
    parser.add_argument("--print-expected", action="store_true")
    args = parser.parse_args()

    semantic, counted, mentioned, aside = load()
    exp = expected(semantic, counted, mentioned, aside)

    print(f"counted (core + partial): {exp['counted']}")
    print(f"mentioned only:           {exp['mentioned']}")
    print(f"held as not about Origen: {exp['aside']}")
    print(f"counted and dated 1900 on: {exp['dated_1900_on']}")
    if args.print_expected:
        print(json.dumps(exp, ensure_ascii=False, indent=1))

    if not os.path.exists(args.measured):
        print(f"\nno measured file at {args.measured}: nothing to compare", file=sys.stderr)
        return 1
    with open(args.measured, encoding="utf-8") as fh:
        measured = json.load(fh)
    describe_capture(args.measured, measured)

    problems: list[str] = []
    compare(exp, measured, problems)
    print()
    if problems:
        for line in problems:
            print("MISMATCH  " + line)
        print(f"\n{len(problems)} disagreements between the pages and the data")
        return 2
    print("every figure read off the pages matches the counted population")
    return 0


if __name__ == "__main__":
    sys.exit(main())
