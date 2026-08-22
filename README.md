# Origenality

A bibliographic map of Origen studies: what has been written on Origen of
Alexandria, where the scholarship is dense, and where it is thin.

Site: https://origenality.com · Source: https://github.com/romain-girardi-eng/origenality

## The problem

Anyone starting a piece of work on Origen faces the same question, and no
instrument answers it: has this been done? The bibliographies that exist are
either closed (subscription indexes), partial (one language, one library), or
frozen at their date of publication. Cross-searching five catalogues by hand
gives a pile of records with no way of knowing how much of it is the same work
listed five times, and no way of seeing what the pile leaves out.

Origenality federates the open bibliographic sources on Origen, deduplicates
them into one record per work, classifies each record by theme, by work of Origen
and by approach, and renders the result as a map you can read at a glance and
query in plain language. The measure it gives is a density — how many studies
already sit in a given neighbourhood — not a verdict on originality. An empty
region may be a gap worth filling or a dead end others have already walked away
from; the map says which regions are empty, and that is all it says.

## Where it stands

**Data.** Ten open sources harvested: 45 685 raw records, merged into **42 210
clusters** (3 475 duplicates collapsed). 24 802 of those clusters carry an
abstract, each one attributed to the database that wrote it and linked back to
its record.

<!-- FIGURES:classification -->
**Classification.** 21 104 clusters have been read against a controlled
vocabulary of themes, works, approaches and relevance. Of those, 4 909 are about
Origen and 1 833 give him a section of the argument: **6 742 records form the
citable dossier**. 1 100 mention him only; 13 262 are noise the harvest brought
in and the classification pushed out. Every published figure counts the first two
classes and nothing else.
<!-- /FIGURES:classification -->

**Site (v0).** The explorer published so far draws the IxTheo/K10plus harvest
alone: <!-- FIGURES:population-root -->**2 582 records, of which 2 294 are counted**, 287 mentioned only, 1 held outside the count.<!-- /FIGURES:population-root -->
It is static — no request leaves the page — and it carries an observatory
of the field by decade, language, format, theme and work of Origen.

**Citation weight.** Citation counts are measured for 14 772 of the 42 210
clusters (35 %). They are shown as a percentile inside a cohort of the same
decade, type and language, so that a 1960s German monograph is not crushed by a
2015 English article. The weight is a visual cue, never a filter: no record is
excluded from a search or a count because it has no citation data.

## Limits

- **Citation coverage is uneven by language**: 88.9 % for Spanish, 39.8 % for
  German, 35.9 % for English, 24.4 % for Italian, 9.6 % for French. The cause is
  the absence of older and non-anglophone records from the bibliometric sources,
  not a failure of the join. Any reading of citation weight across languages is
  therefore unsafe, and the site says so on the page that shows it.
- **The classification is machine-assisted and its agreement with hand tagging
  is not currently published.** A reference set of fifty records tagged by hand
  exists; the measurement against the current prompt has not been run, and no
  agreement figure is stated anywhere until it has been.
- **Subscription indexes are absent** (they cannot be harvested and would not be
  redistributable), so the coverage of pre-1980 and of some national traditions
  is thinner than the counts suggest.
- **One harvest, one date.** The figures above describe the August 2026 harvest.
  There is no incremental update yet.
- The federated corpus is not what the published site draws: v0 shows the
  catalogue harvest only, while the classification and the citation work run on
  all ten sources.

## Reproducing it

Python 3.11 or later, standard library only. No key, no service, no build step.
Every command below is run from the root of the clone.

What a fresh clone runs as it stands, on the files it ships with:

```bash
python3 scripts/test_data_gates.py                    # the test suite
python3 site/tools/build_summary_figures.py --check   # every published figure recounted
python3 site/qa/check_one_population.py               # one population on every screen
python3 scripts/build_seo_assets.py --check           # sitemap and llms.txt still current
python3 -m http.server 8020                           # then open /site/welcome.html
bash scripts/selftest_public.sh                       # all of the above, in a throwaway clone
```

What needs a harvest first, because the raw harvests and the merged corpus are
not in this repository — they are large, and several sources ask that their
dumps not be redistributed:

```bash
python3 scripts/harvest_openalex.py                       # one harvester per source, in scripts/
python3 pipeline/merge_dedup.py --out-dir data/merged     # federate and deduplicate
python3 pipeline/enrich_citations.py                      # citation counts and cohorts
python3 pipeline/build_site_data.py --tags <tags.jsonl>   # the site data layer
python3 scripts/qa_checks.py all                          # the standing checks on the merged corpus
```

The harvesters are rate-limited and resumable, and running them rebuilds the
corpus from the sources themselves.

`docs/methodology.md` describes the federation, the deduplication rules, the
classification and the density measure. `docs/sources.md` lists the sources with
their licences. `docs/seo-geo.md` says what the site declares to search engines
and to AI crawlers, and how to check it after a deployment.
`api-spec/openapi.yaml` is the contract the site consumes; the implementation
that serves it is separate from this repository.

## Asking it from a program

The map answers one question — has this ground been worked, and how thickly —
and the command line answers it the same way the website does, because both run
`site/assets/search-core.js`.

```bash
node cli/origenality.mjs gap "Origen and Roman law"     # is this ground taken?
node cli/origenality.mjs search "Contre Celse"          # aliases reach their work
node cli/origenality.mjs density work cels              # how thick, by decade
node cli/origenality.mjs coverage                       # what it cannot answer
```

No checkout is needed: the data is fetched from origenality.com and cached for
twelve hours. Add `--local .` to read this tree instead, `--json` for a
machine, `--lang`, `--since`, `--until` to narrow.

A free-text query returns a neighbourhood; naming a field returns a
publication. The same grammar answers in the browser and here:

```
author:crouzel   year:1971-1990   lang:fre   type:book
work:cels        theme:exegesis   in:adamantius
"free will"      -rufinus
```

These are conditions, not scores: they are conjunctive and never widened, so
`year:1971` does not mean thereabouts.

Two figures come back, never one. `counted_in_density` are the records judged to
be about Origen; `listed` includes those that merely mention him. And when
`widened` is true the query was relaxed to fewer terms — the answer to the
question asked is `carrying_all_terms`, which is often 0 where `listed` is in
the hundreds. `scripts/check_search_parity.py` keeps the two front ends honest.

## Citing it

See `CITATION.cff`. In a footnote:

> Romain Girardi, *Origenality: a bibliographic map of Origen studies*, 2026.

Cite the underlying databases as well when you cite a record: the attribution
template for each is in `ATTRIBUTION.md`, and Semantic Scholar in particular
requires attribution under ODC-BY.

## Contact, corrections, takedown

romain.girardi@univ-cotedazur.fr

Abstracts are published with the name of the database that wrote them and a link
to the record it wrote them for. A publisher, a database or an author who asks
for a summary to be removed or replaced gets it removed or replaced, without
discussion and without having to explain. Write to the address above, name the
source or the record, and the change goes into the next build; the takedown is
scripted, not manual (`scripts/check_release.py --withdraw`).

Corrections to the data are as welcome as takedowns: a merged pair that is not
the same work, a work split in two, a misclassified record. Name the record and
say what is wrong with it.

## Licence

Code: MIT (`LICENSE`). Data: see `DATA_POLICY.md` — they are published under
attribution and takedown on request, and the licence of each source is stated
in `ATTRIBUTION.md`. The metadata come from ten databases under distinct
regimes, so no single licence is asserted over the whole, and `CITATION.cff`
therefore declares none.
