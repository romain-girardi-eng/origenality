#!/usr/bin/env python3
"""Le plan du site et le fichier `llms.txt`, écrits depuis le dépôt lui-même.

Deux fichiers que les moteurs et les agents lisent avant les pages, et qui
portent tous deux des chiffres et des dates. Ils sont donc produits plutôt que
tapés. La date `lastmod` de chaque document de `sitemap.xml` est celle où son
contenu a changé : `data/sitemap-dates.json` garde, par adresse, l'empreinte
SHA-256 du fichier et sa date ; une empreinte inchangée garde sa date, une
empreinte nouvelle prend la date du jour. La date de construction ne sert plus
à tout dater (audit du 13/09, OR-69), et aucun historique git n'entre dans le
calcul, puisque les deux arbres n'ont pas le même. Les chiffres de `llms.txt`
sont recomptés depuis `META.json` et `build_summary_figures`, comme ceux des
pages. Un fichier écrit à la main aurait vieilli le jour où la
population a bougé, sans que rien ne s'en aperçoive.

    python3 scripts/build_seo_assets.py
    python3 scripts/build_seo_assets.py --check   # sort en 1 si un fichier est périmé
                                                  # ou si un document a changé sans nouvelle date

Bibliothèque standard seule, comme le reste du dépôt. `--check` est le contrôle
à passer avant une publication.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "site" / "build-c" if (ROOT / "site" / "build-c").is_dir() else ROOT / "site"
SITE_PREFIX = BUILD.relative_to(ROOT).as_posix()
sys.path.insert(0, str(BUILD / "tools"))

import build_summary_figures as figures  # noqa: E402

SITE = "https://origenality.com"
REPO = "https://github.com/romain-girardi-eng/origenality"

# Les pages, dans l'ordre de la navigation, avec l'adresse que Cloudflare
# Pages sert réellement : il retire l'extension et redirige `.html` vers elle.
PAGES = (
    (f"{SITE_PREFIX}/welcome.html", "/site/welcome", "1.0",
     "the door: what the map is, and the one step that opens it."),
    (f"{SITE_PREFIX}/index.html", "/site/", "0.9",
     "the map of the field, a free-text bar and four questions that lead to a "
     "neighbourhood of the scholarship."),
    (f"{SITE_PREFIX}/observatoire.html", "/site/observatoire", "0.8",
     "the harvest counted by decade, language, format, theme and work of "
     "Origen, with what those counts cannot say."),
    (f"{SITE_PREFIX}/methode.html", "/site/methode", "0.9",
     "how the corpus is built, how summaries are credited and removed, what "
     "the controlled vocabulary holds, and what the density figure measures."),
    (f"{SITE_PREFIX}/credits.html", "/site/credits", "0.6",
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
    ("/data/stats.json", "the counts by year, decade, format, language, subject and container: "
     "under `counted`, the population every figure on the site counts (core and partial "
     "records); at the top level, every kept work cluster, as its `population` key says"),
    ("/data/abstracts.json", "the summaries shown in the Explorer, each with the "
     "database that wrote it and a link to its record"),
    ("/data/META.json", "the harvest itself: source, harvest date, the date subject headings "
     "and containers were read again (`refetched`), scope, fields published"),
    ("/api-spec/openapi.yaml", "the JSON the command line prints, described command by command"),
)

META = Path(figures.DATA) / "META.json"
PRIMARY_SUMMARY = Path(figures.DATA) / "primary-layer-summary.json"
SITEMAP_DATES = Path(figures.DATA) / "sitemap-dates.json"


def content_date(address: str, path: Path, dates: dict, today: str) -> tuple[str, bool]:
    """(lastmod, changed) d'un document, lus sur son contenu et non sur la construction.

    Les pages et les documents sont copiés octet pour octet d'un arbre à l'autre,
    donc leur empreinte est la même des deux côtés : la table voyage avec la
    couche de données et le contrôle passe dans les deux arbres.
    """
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    known = dates.get(address) or {}
    if known.get("sha256") == digest and known.get("lastmod"):
        return known["lastmod"], False
    dates[address] = {"sha256": digest, "lastmod": today}
    return today, True


def sitemap(dates: dict | None = None, today: str | None = None) -> str:
    dates = dates if dates is not None else load_dates()
    today = today or dt.date.today().isoformat()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for source, address, priority, _ in PAGES + DOCS:
        lastmod, _changed = content_date(address, ROOT / source, dates, today)
        lines += ["  <url>",
                  "    <loc>%s%s</loc>" % (SITE, address),
                  "    <lastmod>%s</lastmod>" % lastmod,
                  "    <priority>%s</priority>" % priority,
                  "  </url>"]
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def load_dates() -> dict:
    return (json.loads(SITEMAP_DATES.read_text(encoding="utf-8"))
            if SITEMAP_DATES.exists() else {})


def dates_text(dates: dict) -> str:
    return json.dumps(dict(sorted(dates.items())), ensure_ascii=False, indent=1) + "\n"


def ordinal(number: int) -> str:
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return "%d%s" % (number, suffix)


def llms() -> str:
    values = figures.population(BUILD)
    classified = figures.classification()
    corpus = figures.corpus_figures(BUILD)
    summaries = figures.figures()
    meta = json.loads(META.read_text(encoding="utf-8"))
    primary = json.loads(PRIMARY_SUMMARY.read_text(encoding="utf-8"))
    n = figures.spaced
    labels = [figures.english_label(entry.get("label") or entry["source"])
              for entry in meta.get("sources_present") or []]
    first_century = (primary["year_min"] - 1) // 100 + 1

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
        title = {"/site/welcome": "Home", "/site/": "Explorer",
                 "/site/observatoire": "Observatory",
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

    # Rendue au générateur : la section avait été tapée dans le fichier le 22 août,
    # et la régénération suivante l'avait effacée (OR-09, OR-32).
    out += ["## For programs", "",
            "- `cli/origenality.mjs`: the map as a command line. `search` and `gap` answer "
            "\"has this been written about, and how thickly\"; `record`, `vocabulary`, "
            "`density`, `coverage` and `stats` give the rest. It reads the published data "
            "over HTTPS, so it needs no checkout: "
            "`node cli/origenality.mjs gap \"Origen and Roman law\"`.",
            "- It runs `site/assets/search-core.js`, the same file the website executes, so "
            "a program and a reader are never shown two different figures. "
            "`scripts/check_search_parity.py` fails a release where they diverge.",
            "- Read the answer with care: `counted_in_density` are the records judged to be "
            "about Origen and `listed` includes those that only mention him; when `widened` "
            "is true the engine relaxed the query and the real answer is "
            "`carrying_all_terms`, not `listed`; `terms_absent_from_corpus` names a word "
            "found in none of the %s records, in any field `searched_fields` lists (title, "
            "authors, every subject heading, journal or volume, year, language, theme labels, "
            "abstract): the strongest sign of thin ground this map gives, and still no proof "
            "that the subject is untreated. Run `coverage` before saying so: %s of records "
            "carry an abstract, so absence of a hit is weaker evidence than presence of one."
            % (n(values["kept"]), "%.1f%%" % summaries["share"]),
            "- A query may name its field rather than describe a project: `author:crouzel`, "
            "`year:1971-1990`, `lang:fr`, `type:book`, `work:cels`, `theme:exegesis`, "
            "`in:adamantius`, `\"free will\"` for an exact phrase, `-rufinus` to exclude. "
            "These are conditions, conjunctive and never widened, so a field query returning "
            "nothing is a real answer. Same grammar in the browser and on the command line.",
            "- A second layer holds the texts rather than the studies: %s editions, "
            "translations and manuscript witnesses of Origen's own works, from the %s century "
            "onward, served as `data/primary-layer.jsonl` with a summary at "
            "`data/primary-layer-summary.json` and through `origenality primary`. It is never "
            "counted in a density figure, and it should never be quoted as scholarship."
            % (n(corpus["primary_records"]), ordinal(first_century)),
            "- `.claude/skills/origenality/SKILL.md` states those reading rules for an agent.",
            ""]

    out += ["## Key facts", "",
            "- The published map draws %s source labels, each queried through an authority "
            "record for Origen rather than through the string of his name (GND 118590235 and "
            "its national equivalents): %s. Asking by authority number is what keeps the "
            "Spanish \"orígenes\", the Italian \"origini\" and the French \"origines\" out of "
            "a corpus about Origen." % (figures.number_word(len(labels)), "; ".join(labels)),
            "- The harvest returned %s catalogue records about Origen, merged into %s work "
            "clusters (%s %s collapsed). %s of them are counted in every figure on the site, "
            "%s %s him only and %s %s held outside the count; the last two are returned by a "
            "search and enter no figure.%s"
            % (n(values["harvested"]), n(values["kept"]), n(values["duplicates"]),
               figures.noun(values["duplicates"], "duplicate", "duplicates"),
               n(values["counted"]), n(values["mentioned"]),
               figures.verb(values["mentioned"], "mentions", "mention"),
               n(values["aside"]), figures.verb(values["aside"]),
               (" " + figures.refetch_sentence(values, "those records"))
               if figures.refetch_sentence(values, "those records") else ""),
            "- The working corpus behind the classification is wider: ten open "
            "sources merged into %s clusters, of which %s have been classified "
            "against the vocabulary and %s are about Origen or give him a section "
            "of the argument. It adds no record to the published map; where one of its "
            "sources summarises a publication the map holds, the summary is attached to "
            "that record and credited to the database that wrote it."
            % (n(CLUSTERS), n(classified["classified"]), n(classified["counted"])),
            "- The density figure is a count of records inside a named node of the "
            "vocabulary. It measures how much has been written in a neighbourhood, "
            "not whether a project is original: a thin area may be unexplored, or "
            "empty for a reason, or written in a language these catalogues index "
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
    dates = load_dates()
    before = dates_text(dates)
    for name, build in TARGETS:
        path = ROOT / name
        wanted = sitemap(dates) if build is sitemap else build()
        if path.exists() and path.read_text(encoding="utf-8") == wanted:
            print("%-14s à jour" % name)
            continue
        stale.append(name)
        if args.check:
            print("%-14s PÉRIMÉ" % name)
            continue
        path.write_text(wanted, encoding="utf-8")
        print("%-14s écrit (%d octets)" % (name, len(wanted.encode("utf-8"))))
    # Un document dont l'empreinte a changé sans que la table ait suivi : en
    # contrôle, c'est une date périmée, jamais une date réécrite en silence.
    if dates_text(dates) != before:
        stale.append(SITEMAP_DATES.name)
        if args.check:
            print("%-14s PÉRIMÉ (un document a changé depuis sa date)" % SITEMAP_DATES.name)
        else:
            SITEMAP_DATES.write_text(dates_text(dates), encoding="utf-8")
            print("%-14s écrit" % SITEMAP_DATES.name)
    llms_text = (ROOT / "llms.txt").read_text(encoding="utf-8") if (ROOT / "llms.txt").exists() else ""
    meta = json.loads(META.read_text(encoding="utf-8"))
    count_phrase = "draws %s source labels" % figures.number_word(len(meta.get("sources_present") or []))
    for required in ("## For programs", count_phrase):
        if required not in llms_text:
            stale.append("llms.txt")
            print("llms.txt       ne dit pas « %s »" % required)

    if args.check and stale:
        print("\n%s à régénérer : python3 scripts/build_seo_assets.py"
              % ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
