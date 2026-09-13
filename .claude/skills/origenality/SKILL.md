---
name: origenality
description: Use when a question concerns the SCHOLARSHIP on Origen of Alexandria, including whether a topic has already been treated, how thickly, by whom, in what language, or where the literature is thin. Covers originality checks before writing ("has this been done?"), literature surveys, finding studies on a work of Origen (Contra Celsum, De principiis, Commentary on John…) or on a theme (apokatastasis, free will, allegory, prayer), and reading the density of a subfield. Triggers on Origen, Origène, Origenes, Origenality, patristics bibliography, "has anyone written on", "state of the question", "Forschungsstand", and "état de la question". NOT for the text of Origen himself; this maps what has been written ABOUT him.
---

# Origenality: what has been written about Origen, and where it is thin

A bibliographic map of the scholarship on Origen of Alexandria. The current
site exposes 2 490 work clusters from 2 582 source records under eight source
labels; 92 duplicate catalogue records are collapsed. The clusters are
classified against a controlled vocabulary. It answers one question well: **has this
ground been worked, and how thickly?** It is honest about what it cannot
see.

Site: https://origenality.com · source-specific data terms, code MIT.

## Use the CLI

```bash
node cli/origenality.mjs <command> [--json] [--limit N]
```

From a checkout, add `--local .` (a public clone or the working tree, the CLI
finds the data in either). Without it the CLI reads the published data over
HTTPS and caches it for twelve hours; no checkout is needed.

The CLI runs `site/assets/search-core.js`, the very file the website executes,
on the index that file builds, so **the figure you get is the figure a human
sees on the map**. `scripts/check_search_parity.py` fails a release where the
two disagree. `api-spec/openapi.yaml` describes every JSON output.

## The commands

| | |
|---|---|
| `search <query>` | what has been written, counted honestly |
| `gap <query>` | the same, framed as an originality check (always JSON) |
| `record <id>` | one work cluster in full, by cluster ID or source-record ID |
| `vocabulary [themes\|works\|approaches\|domains]` | the controlled vocabulary with its counts |
| `density <theme\|work\|approach\|domain> <key>` | how thick one heading is, by decade; the same count as `search <kind>:<key>` |
| `coverage` | what the corpus cannot answer, in figures |
| `primary` | the primary layer: the texts of Origen, never counted as scholarship |
| `claims [query]` | source-anchored scholar positions and their release-safe evidence |
| `stats` | the harvest, counted: the top-level series count the records kept, `counted` holds the same series on the counted records, `population` says which is which |

Restrictions: `--lang en,de` · `--since 1990` · `--until 2010` apply to
`search`, `gap`, `density` and `vocabulary`; `--limit N` (0 or more) to
`search`, `gap`, `density` and `claims`. A year restriction keeps dated records
only. A command given an option it does not take refuses it.

Exit status: `0` an answer; `1` a failure (network, a record ID that matches
nothing); `2` a usage error (an argument a command does not take, an option
with no command) or a query the engine refused to evaluate. Treat a `2` as a
question to rephrase, never as a zero.

## Naming a field, when you want one publication

A free-text query returns a neighbourhood. When you are after a particular
publication (or a precise slice), name the field instead. The same grammar
works on the site and here.

```
author:crouzel          year:1971   year:1971-1990   year:>2000
lang:fr                 type:book
work:cels               theme:exegesis   domain:…   approach:…
in:adamantius           the journal or volume it sits in
"free will"             those words, in that order
-rufinus                and not this one
```

Conditions are conjunctive and **never widened**: `year:1971` does not mean
thereabouts. So a field query that returns nothing returns nothing on purpose,
and `widened` will be false: that is a real answer, not a failure. Mix a field
with free text freely (`work:cels lang:fr allegory`). A year condition keeps
dated records only. `lang:` takes ISO 639 codes and their MARC forms (`fre`,
`ger`, `arm`) or an English language name (`lang:english`).

Keys for `work:`, `theme:`, `domain:` and `approach:` come from
`vocabulary`; a prefix is enough (`theme:exegesis` catches every theme of that
domain).

A query the grammar cannot honour is refused with exit status 2 and a JSON
reason: `query_not_understood` with `query_errors` (unknown field, empty value,
unclosed quotation mark, invalid or reversed year, unknown language, type or
key), or `no_searchable_term` when every word was shorter than three letters or
a stopword (`PG`, `the`). Fix the query and ask again; do not report a count.

Terms match at word starts, accents ignored: `Origène` finds "d'Origène" and
"Origenes", `Bußlehre` equals `Busslehre`, and Greek or Cyrillic words are
terms like any other.

## Read the answer correctly

This is the part that matters, and it is where a careless agent will mislead
its reader.

**Two figures, not one.** `counted_in_density` are the records judged to be
*about* Origen; `listed` includes those that merely mention him or are held
aside. Quote the first as "studies on", never the second.

**A widened answer is not an answer.** When `widened` is true the engine could
not find enough records carrying every term and dropped to
`widened_to_terms`. The real answer is `carrying_all_terms`, often 0 or 2
where `listed` is in the hundreds. Report the real one.

```
$ node cli/origenality.mjs gap "Origen in Ethiopia"
  "carrying_all_terms": 0,
  "terms_absent_from_corpus": ["ethiopia"],
  "widened": true, "listed": <the records carrying "origen">
```
→ say *no study joins Origen and Ethiopia; "ethiopia" appears in no record*.
Do **not** quote `listed` as a number of studies on the question.

`carrying_all_terms_counted` is the part of `carrying_all_terms` that counts in
the density figures, and `per_term` gives how many records each term reaches:
a term that reaches most of the corpus (often "origen") narrows the answer very
little.

**`terms_absent_from_corpus` names a term found in none of the fields read.**
`searched_fields` lists them: title, authors, every subject heading of the
record, its journal or volume, year, language, theme labels and abstract. A term
in none of them, in any cluster, whatever the filters, is the strongest sign of
thin ground the map gives; report it with the fields searched, never as proof
that nobody has written on the subject. `terms_absent_under_filters` is weaker:
the term exists in the corpus, only not in the slice your filters or options
leave. If the answer carries `terms_not_found_partial_index`, the file of
subject headings could not be read and nothing was called absent: say so and
do not report an absence.

**A heading is not a phrase.** `filed_under_heading` counts records filed under
a controlled-vocabulary heading (a work of Origen, a theme or an approach) in
any of its languages. "Contre Celse" reaches the records filed under *Contra Celsum*
even when none spells it that way. Use `vocabulary works` to get the
exact headings.

**Absence is weaker evidence than presence.** Most clusters carry no abstract
(`coverage` gives the share); those are searched on title, authors, subject
headings, journal or volume and theme labels. A subject can be treated inside a
book whose title and headings never name it. Run `coverage` before concluding
that something has never been done, and say so.

## An originality check, end to end

```bash
node cli/origenality.mjs gap "Origen and Roman law"        # is the ground taken?
node cli/origenality.mjs vocabulary themes | head -40      # the nearest headings
node cli/origenality.mjs density theme cosmos.providence-and-evil
node cli/origenality.mjs coverage                          # what this cannot see
```

Then report: what carries all the terms, what the nearest heading holds, how
that compares with the corpus total, and what the corpus cannot answer.

## Do not

- Quote `listed` when `widened` is true, as if it answered the question.
- Turn a thin result into "unexplored" without running `coverage` and saying
  what the corpus cannot see.
- Invent an identifier, a title or a year. Every record has a `url` back to its
  catalogue: cite it.
- Use this for the *text* of Origen. It maps the secondary literature.
