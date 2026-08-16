#!/usr/bin/env python3
"""Le plan du site et le fichier `llms.txt`, écrits depuis le dépôt lui-même.

Deux fichiers que les moteurs et les agents lisent avant les pages, et qui
portent tous deux des chiffres et des dates. Ils sont donc produits plutôt que
tapés : les dates de `sitemap.xml` viennent du dernier commit de chaque fichier,
et les chiffres de `llms.txt` sont recomptés par `build_summary_figures`, comme
ceux des pages. Un fichier écrit à la main aurait vieilli le jour où la
population a bougé, sans que rien ne s'en aperçoive.

    python3 scripts/build_seo_assets.py
    python3 scripts/build_seo_assets.py --check   # sort en 1 si un fichier est périmé

Bibliothèque standard seule, comme le reste du dépôt. `--check` est le contrôle
à passer avant une publication.
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "site"
sys.path.insert(0, str(BUILD / "tools"))

import build_summary_figures as figures  # noqa: E402

SITE = "https://origenality.com"
REPO = "https://github.com/romain-girardi-eng/origenality"

# Les quatre pages, dans l'ordre de la navigation, avec l'adresse que Cloudflare
# Pages sert réellement : il retire l'extension et redirige `.html` vers elle.
PAGES = (
    ("site/index.html", "/site/", "1.0",
     "the map of the field, a free-text bar and four questions that lead to a "
     "neighbourhood of the scholarship."),
    ("site/observatoire.html", "/site/observatoire", "0.8",
     "the harvest counted by decade, language, format, theme and work of "
     "Origen, with what those counts cannot say."),
    ("site/methode.html", "/site/methode", "0.9",
     "how the corpus is built, how summaries are credited and removed, what "
     "the controlled vocabulary holds, and what the density figure measures."),
    ("site/credits.html", "/site/credits", "0.6",
     "the sources behind the map, their licences, the required attributions "
     "and the removal procedure."),
)

# Le corpus fusionné n'est pas livré dans cet arbre — il est lourd, et plusieurs
# sources demandent que leur dump ne soit pas redistribué —, donc sa taille ne
# peut pas se recompter ici. Elle est reprise du README, § « Where it stands »,
# où elle est écrite par la passe de fusion.
CLUSTERS = 42210

DOCS = (
    ("README.md", "/README.md", "0.5",
     "The repository read me: the problem, the state of the data, the limits, "
     "and the commands that reproduce it."),
    ("docs/methodology.md", "/docs/methodology.md", "0.7",
     "Federation, deduplication rules, classification and the density figure, "
     "each rule named with the code that enforces it."),
    ("docs/sources.md", "/docs/sources.md", "0.5",
     "The ten harvested sources, their access method and their licences."),
    ("DATA_POLICY.md", "/DATA_POLICY.md", "0.5",
     "What is published and under what regime: metadata, summaries, tags "
     "(in French)."),
    ("ATTRIBUTION.md", "/ATTRIBUTION.md", "0.4",
     "The attribution template required by each source."),
)

DATA = (
    ("/data/graph.json", "the map layer: one entry per record, with its cluster, "
     "its tags and its link back to the catalogue"),
    ("/data/stats.json", "the counts the Observatory draws"),
    ("/data/abstracts.json", "the summaries shown in the Explorer, each with the "
     "database that wrote it and a link to its record"),
    ("/data/META.json", "the harvest itself: source, date, scope, fields published"),
    ("/api-spec/openapi.yaml", "the contract the site consumes"),
)


def git_date(path: Path) -> str:
    """Date de dernière modification : le commit, ou le fichier s'il a bougé depuis."""
    relative = str(path.relative_to(ROOT))
    try:
        dirty = subprocess.run(["git", "status", "--porcelain", "--", relative],
                               cwd=ROOT, capture_output=True, text=True, check=True)
        if dirty.stdout.strip():
            raise FileNotFoundError
        committed = subprocess.run(["git", "log", "-1", "--format=%cI", "--", relative],
                                   cwd=ROOT, capture_output=True, text=True, check=True)
        stamp = committed.stdout.strip()
        if stamp:
            return stamp[:10]
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass
    return dt.date.fromtimestamp(path.stat().st_mtime).isoformat()


def sitemap() -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for source, address, priority, _ in PAGES + DOCS:
        lines += ["  <url>",
                  "    <loc>%s%s</loc>" % (SITE, address),
                  "    <lastmod>%s</lastmod>" % git_date(ROOT / source),
                  "    <priority>%s</priority>" % priority,
                  "  </url>"]
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def llms() -> str:
    values = figures.population(BUILD)
    classified = figures.classification()
    n = figures.spaced

    out = ["# Origenality", "",
           "> A bibliographic map of the scholarship on Origen of Alexandria. It "
           "federates open bibliographic sources, merges them into one record per "
           "work, classifies each record against a controlled vocabulary of themes, "
           "works of Origen and approaches, and draws the result as a map that says "
           "where the scholarship is dense and where it is thin. Written and "
           "maintained by Romain Girardi, doctoral candidate, Université Côte d'Azur "
           "and University of Geneva. The site is static: no request leaves the page.",
           ""]

    out += ["## Pages", ""]
    for _, address, _, note in PAGES:
        title = {"/site/": "Explorer", "/site/observatoire": "Observatory",
                 "/site/methode": "Method", "/site/credits": "Credits"}[address]
        out.append("- [%s](%s%s): %s" % (title, SITE, address, note))
    out.append("")

    out += ["## Documentation", ""]
    titles = {"/README.md": "Read me", "/docs/methodology.md": "Methodology",
              "/docs/sources.md": "Sources", "/DATA_POLICY.md": "Data policy",
              "/ATTRIBUTION.md": "Attribution"}
    for _, address, _, note in DOCS:
        out.append("- [%s](%s%s): %s" % (titles[address], SITE, address, note))
    out.append("- [Source code](%s): the harvesters, the merge, the classification "
               "and the site, under the MIT licence." % REPO)
    out.append("")

    out += ["## Data files", ""]
    for address, note in DATA:
        out.append("- [%s](%s%s): %s" % (address.rsplit("/", 1)[-1], SITE, address, note))
    out.append("")

    out += ["## Key facts", "",
            "- The published map draws one catalogue: the Index Theologicus "
            "(IxTheo, Tübingen) hydrated from K10plus, harvested through the "
            "authority record for Origen (GND 118590235) on 15 August 2026.",
            "- That harvest returned %s publications about Origen. %s of them are "
            "counted in every figure on the site, %s mention him only and %s are "
            "held outside the count; the last two are returned by a search and "
            "enter no figure."
            % (n(values["harvest"]), n(values["counted"]),
               n(values["mentioned"]), n(values["aside"])),
            "- The working corpus behind the classification is wider: ten open "
            "sources merged into %s clusters, of which %s have been classified "
            "against the vocabulary and %s are about Origen or give him a section "
            "of the argument. No record of that wider corpus is on the published "
            "map yet."
            % (n(CLUSTERS), n(classified["classified"]), n(classified["counted"])),
            "- The density figure is a count of records inside a named node of the "
            "vocabulary. It measures how much has been written in a neighbourhood, "
            "not whether a project is original: a thin area may be unexplored, or "
            "empty for a reason, or written in a language this catalogue indexes "
            "thinly.",
            "- Citation weight is drawn as a percentile inside a cohort of the same "
            "decade, document type and language. It never filters a search and "
            "never enters a count.",
            "- The classification is machine-assisted and checked against a "
            "hand-tagged reference set. No agreement figure is published until it "
            "has been measured under the current instructions.",
            "- Every summary displayed names the database that wrote it and links "
            "to the record there.",
            ""]

    out += ["## Citing and contact", "",
            "- Cite as: Romain Girardi, *Origenality: a bibliographic map of Origen "
            "studies*, 2026. The machine-readable form is in `CITATION.cff`; cite "
            "the underlying databases as well, following `ATTRIBUTION.md`.",
            "- Corrections, and removal of any summary, at "
            "romain.girardi@univ-cotedazur.fr. A publisher, a database or an author "
            "who asks for a summary to be removed gets it removed, without having "
            "to explain.",
            ""]
    return "\n".join(out)


def llms_full() -> str:
    head = ["# Origenality: the full documentation",
            "",
            "The read me and the methodology of the project, concatenated for "
            "reading in one pass. The map itself, its figures and its licences are "
            "at %s." % SITE,
            "", "---", ""]
    body = []
    for name in ("README.md", "docs/methodology.md"):
        body += ["<!-- %s -->" % name, "", (ROOT / name).read_text(encoding="utf-8").strip(),
                 "", "---", ""]
    return "\n".join(head + body).rstrip() + "\n"


TARGETS = (("sitemap.xml", sitemap), ("llms.txt", llms), ("llms-full.txt", llms_full))


def main(argv) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="ne rien écrire, sortir en 1 si un fichier est périmé")
    args = parser.parse_args(argv)

    stale = []
    for name, build in TARGETS:
        path = ROOT / name
        wanted = build()
        if path.exists() and path.read_text(encoding="utf-8") == wanted:
            print("%-14s à jour" % name)
            continue
        stale.append(name)
        if args.check:
            print("%-14s PÉRIMÉ" % name)
            continue
        path.write_text(wanted, encoding="utf-8")
        print("%-14s écrit (%d octets)" % (name, len(wanted.encode("utf-8"))))

    if args.check and stale:
        print("\n%s à régénérer : python3 scripts/build_seo_assets.py"
              % ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
