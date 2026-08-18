# The site

Five pages on one cream field: the landing, the Explorer, the Observatory, the
Method and the Credits. The landing is the door. The Explorer is the map: a
warm cream ground, one search bar high in the middle, a light map of coloured
clusters, plain names, one dark rounded button.

No CDN, no external request, fonts self hosted, every path relative so the whole
folder can be served under a path prefix such as `/origenality`.

```
python3 -m http.server 8020                    # from the root of the clone
open http://localhost:8020/site/welcome.html
```

Paths below are given from the root of the clone, where the pages sit under
`site/` and their data layer under `data/`. The working repository keeps one
step more — `site/build-c/` for the pages, `site/data/` for the layer — and the
publication pass removes it; the tools find the root by looking for it rather
than by counting steps, so the same command works on either side.

## Pages

| File | What it is |
|---|---|
| `welcome.html` | the landing: the portrait, one sentence, Explore |
| `index.html` | the Explorer: the map, the free bar, the four questions |
| `observatoire.html` | the Observatory: the harvest counted, with its three sets |
| `methode.html` | the Method: corpus, rights, vocabulary, what the density figure is |
| `credits.html` | the Credits: sources, licences, required attributions, origin |

## What the map shows

- **A cluster is a name from the controlled vocabulary**, not a raw catalogue
  heading. Two ways of grouping, one switch in the corner:
  - **by theme** — the sixteen domains of `semantic/vocabulary/themes.json`,
    each cloud built of its own leaves;
  - **by work of Origen** — the works of `semantic/vocabulary/works.json` that
    the harvest actually names, each cloud built of the theme domains that
    study them.
- **Three ranks, always.** Domain → leaf → publication in theme mode, work →
  domain → publication in work mode. At the resting scale a hairline holds each
  domain together and a lighter one holds each of its leaves, so the two ranks
  are visible before anything is clicked. Every cloud on screen carries its
  name. The leaf names come in grey as soon as the reader zooms past the
  resting scale, the titles at twice it.
- **Names are placed by repulsion.** A name looks for a free slot on a ring that
  grows outward from its own cloud: under it first, then over it, then beside
  it. It pushes away from the names already set, from the clouds and from the
  furniture of the page. Whatever is left over goes through one relaxation
  pass where every name pushes the others and is pulled back toward its cloud.
  A name that had to move keeps a hairline back to what it names. Nothing is
  dropped on a wide screen: 16 of 16 domains at 1440, 28 of 28 works, no
  overlap anywhere. A narrow screen leaves a cloud to the tap rather than pile
  two names on one spot; the field is drawn smaller there for the same reason,
  and 14 of the 16 domains are named at 375 — the last two answer to a tap, as
  the known weak points below say.
- **Labels are English, aliases are not.** The hover card and the panel carry the
  German, French and Italian labels of the vocabulary, so a reader who knows the
  field under its German headings recognises the cluster.
- **A publication with several tags is filed under the first one** and stays
  findable under the others: the free bar reads every theme, work and angle it
  carries, and any of them can bring it back.
- **Reservoirs, never a bin, and folded.** `Not about Origen` holds the records
  <!-- FIGURES:population-reservoirs -->the classifier keeps outside the count (5); `No single work` holds the studies that bear on none (1 007 counted, in work mode).<!-- /FIGURES:population-reservoirs --> They are folded under the field as named,
  counted chips: one click draws a reservoir on the map and opens its records, a
  second folds it away. Left open, `No single work` would be the widest cloud in
  work mode and the twenty-eight named works would read as an afterthought.
  Nothing is deleted, and nothing is hidden either.
- **One population per screen.** The legend, the question chips, the panel
  headline, the Observatory bars and the decade columns all count one and the
  <!-- FIGURES:population-screen -->same set of 1 402 records, those where Origen is the subject or holds an identifiable section of the argument. The 225 that mention him only and the 5 held outside the count stay in the index and answer a search; neither enters a figure. Where a surface returns more than it counts, it says so and gives the second number rather than folding it into the first. The three sides print the same values (English 518, German 376, Italian 197, French 155, `Doctrinal and systematic 517`, and so on down the list), which is the point: one number per thing, on every page.<!-- /FIGURES:population-screen -->
- **Colour is the language of publication**, six values, each at 3:1 or better
  against the cream. Colour is a mark and never a word: no text on the site is
  set in a language colour, and the legend pairs a coloured dot with a label in
  ink, so nothing depends on telling six hues apart.
- **Nothing overlaps.** Publications are packed as discs by relaxation until no
  pair intersects; leaves are packed inside the cluster the same way; clusters
  are then separated with a gap that follows their own size. The three ranks of
  names give way to each other in order: a leaf name never lands on the name of
  a cloud, and a title never lands on either.
- **The keyboard walks the whole map.** Arrows move from cluster to cluster and
  say the name and the count out loud, Enter opens one, focus moves into the
  panel, Escape closes it and hands focus back to whatever opened it. A closed
  panel is `inert` and hidden, so nothing inside it can be reached by Tab.
- **The field is drawn when it changes.** The loop runs while a movement is
  running and stops when it ends; a map at rest asks for no frames at all.

## Node size: the academic weight

`tools/build_weights.py` writes `assets/weights.json`. Two objective measures,
no hand coded judgement anywhere:

| term | what it is |
|---|---|
| citation percentile | `cited_by_count` (carried by `data/merged/corpus.jsonl`) ranked **inside the work's own cohort**: same decade, same document type, same language. A cohort holding fewer than 8 works widens to decade plus language, then decade, then the whole corpus. |
| structural percentile | percentile of a plain PageRank (damping 0.85, 45 iterations) over `graph.json` itself, publication to author, subject and container. |
| **weight** | the mean of the two, in [0, 1]. |

A work with **no citation figure keeps the structural percentile alone** and is
never pushed below the base size; its notice reads `no citation data`. Coverage
<!-- FIGURES:population-weights -->today: 220 of 1 632 works (13.5 %), joined on the catalogue number and then on the DOI — never on the title, which used to carry the citations of a review over to the book it reviewed.<!-- /FIGURES:population-weights --> The weight is quantised into five tiers rather than
drawn as a continuum, so the eye reads rank instead of noise. It is drawn, and
only drawn: it never filters, and it never enters the density.

No reading or download figures anywhere: our sources do not hold them, and
simulating them would be an invention.

## The two ways in

**The bar.** Free text, read as a conjunction as far as the corpus allows: the
page keeps the most demanding threshold (all your terms, then one fewer, and so
on) that still leaves at least ten works, and says which one it used, for
instance `10 works match, on 2 of your 4 terms`. Stop words in five languages
are dropped. The haystack is title, authors, catalogue headings, container,
year, language, and the vocabulary labels in four languages.

**Four questions**, optional, each one narrowing the map as it is answered. Every
option is read from the vocabulary, the same file the clusters are named from:

1. *Which works of Origen?* — the works axis, with the count each yields.
2. *Which angle of approach?* — the ten approaches.
3. *Which period of scholarship?* — decades, computed from the harvest.
4. *Which languages do you read?* — the six colours of the legend.

Answers combine as `AND` between questions, `OR` inside one. The graph answers
with a single movement, 780 ms, no bounce, `prefers-reduced-motion` honoured. The
panel then gives the count, what else the answer returned without counting it,
where the works concentrate, the adjacent zones, and the sources with their
links. A record links back to the base that holds it, under that base's name,
and shows its publisher, DOI and ISBN when the record carries them.

## Generated files

```
python3 site/tools/build_semantic.py     # assets/semantic.json, then the prose figures
python3 site/tools/build_weights.py      # assets/weights.json
python3 site/tools/enrich_abstracts.py   # data/derived/abstracts_enrichment.jsonl
python3 pipeline/build_site_data.py      # data/*.json, abstracts.json included
```

`build_semantic.py` folds `semantic/vocabulary/*.json` and the tag records of the
federated wave, `semantic/waves/wave2_federated/tags.jsonl`, into one file for the
front: the four axes with their labels in four languages, and per publication its
themes, works, angles and relevance class. The wave tags clusters, the front draws
catalogue records, so the two are joined through `data/merged/corpus.jsonl`, where
each cluster lists the notices it was built from. The script refuses to write a
payload carrying a run identifier, an engine field, a free-text justification or
an abstract. It used to refuse to write at all when its counts differed from the
three the pages printed in prose — the only honest answer while those three were
typed by hand, and a wall the data could not get past. It now writes the asset and
calls `build_summary_figures.py`, which rewrites every published figure inside its
marked block: the population and its three sets, the provenance of the summaries,
the coverage of the citations. `--check` reads the pages against the data and
exits 1 on the first one that has gone stale.

`enrich_abstracts.py` looks for a summary of each catalogued publication in the
federated corpus, joining on catalogue number, on DOI, or on title and year, and
keeps with each one the database that wrote it and the link to its record. The
Explorer shows the summary in the notice, credits it on the line below, and
indexes its words in the search field. 
<!-- FIGURES:summary-provenance -->
381 of the 1 632 records carry one — 166 written by IxTheo itself, 215 by another database.
<!-- /FIGURES:summary-provenance -->

## The shape of the screen

The field takes the proportions of the screen it is drawn on. Turning a phone or
dragging a window edge recomputes the arrangement once the movement stops
(220 ms of quiet), and the clouds travel to their new places in one movement of
620 ms — or in none at all when the reader asks for reduced motion.

## Known weak points

- At 375 px the field is small and the names compete for it. Theme mode seats
  fourteen of the sixteen domains, work mode thirteen of the twenty-eight works;
  the rest answer to a tap. Two names were traded for a fix that mattered more:
  the hint and the Reset button used to be positioned by a hard-coded offset and
  sat on top of the legend at that width. The block is now measured, the controls
  clear it, and nothing overlaps.
- Citation coverage is thin, and lower than it was once the title join was
  dropped — the share is generated above. Every uncovered work is marked, but the
  size signal is thinner than it looks.
- <!-- FIGURES:population-untagged -->Every record on display carries a class. Twenty-eight did not, until a gap pass
  tagged them: their cluster had been split or joined by the deduplication after the
  second wave had run, or a mechanical pre-sort had set them aside. The build now
  refuses to write this asset while a record on display carries none.<!-- /FIGURES:population-untagged -->

## Files

```
index.html               the Explorer
observatoire.html        the Observatory
methode.html             the Method
credits.html             the Credits
assets/base.css          fonts, tokens, masthead, focus — loaded by every page
assets/explorer.css      the map
assets/pages.css         the reading pages
assets/explorer.js       packing, layout, matching, panel, keyboard path
assets/observatory.js    the figures
assets/semantic.json     generated, see tools/
assets/weights.json      generated, see tools/
assets/fonts/            EB Garamond (display, polytonic) + Literata (text), OFL
assets/marks/favicon.svg the hexaplaric mark
tools/                   the generators: the asset, the weights, the published figures
screenshots/it1/         desktop 1440 and mobile 375, iteration 1
screenshots/it2/         the same pass after the naming and the folded reservoirs
screenshots/it3/         summaries displayed, credited, and withdrawable
screenshots/it4/         one population per screen, the keyboard path, the folded data table
screenshots/it8bis/      the same pass on the second wave, with the counts it gives
qa/                      the prose scorer's output, one file per pass
```

Data is read from `../data/graph.json`, `../data/stats.json`, `../data/META.json`
and `../data/abstracts.json`, unmodified. The Observatory reads the graph as well
as the statistics: year, language and format are counted record by record on the
counted population rather than on the whole harvest, so that the page never puts
two populations on one screen.
