# Sources

Ten bibliographic sources, all of them open. Counts are the raw records brought
in by the harvest of August 2026, before deduplication; the merged total is
42 210. Attribution labels and link templates are in `ATTRIBUTION.md`.

| Source | Records | What it brings | Access | Licence / terms |
|---|---:|---|---|---|
| OpenAlex | 14 816 | the widest net, with citation counts and abstracts | REST API, no key | CC0 1.0 |
| Crossref | 8 990 | DOI-bearing articles and chapters, publisher metadata | REST API, polite pool | Crossref open metadata policy |
| ISIDORE (Huma-Num) | 7 763 | francophone and open-repository literature | REST API | terms of the aggregator and of each provider |
| Semantic Scholar | 3 607 | citation graph, abstracts | bulk search API, no key | **ODC-BY 1.0 — attribution required** |
| Adamantius / GIROTA | 3 806 | the annual bibliography of the Italian Origen research group | published bulletins, parsed | terms of Morcelliana / GIROTA |
| SBN (ICCU) | 3 471 | Italian national library holdings, monographs above all | OPAC | terms of the ICCU |
| IxTheo / K10plus | 2 116 | theological cataloguing with subject-chain indexing | SRU / MARC | CC0 1.0 (K10plus metadata) |
| Dialnet | 872 | Spanish-language articles and chapters | public search | terms of Dialnet (Universidad de La Rioja) |
| theses.fr | 145 | French doctoral theses, defended and in progress | REST API | Licence Ouverte / Open Licence (Etalab) |
| BIBP (Université Laval) | 99 | francophone biblical periodical indexing | published index | terms of BIBP (Université Laval) |

## Why these, and not others

The selection rule is simple: a source enters if its metadata can be harvested
without a subscription and redistributed with attribution. That rule excludes
the two indexes a patristics scholar would ask about first.

**L'Année philologique** and **ATLA** are subscription indexes. Their coverage of
pre-1980 scholarship and of the smaller national traditions is better than
anything in the table above, and their terms allow neither harvesting nor
redistribution. Their absence is the largest known gap in this corpus, and it is
not evenly spread: it falls hardest on older work, on articles in journals that
never received a DOI, and on languages the bibliometric sources index poorly.

**Google Scholar** is excluded for the same reason in a different form: no API,
no licence to redistribute, and no stable identifier to deduplicate on.

Two projects are neighbours rather than sources. **Clavis Origenis** is the
reference for the works of Origen themselves, and this project's list of works
follows it. **BiblIndex** indexes the biblical citations of the Fathers, which is
the complementary question to this one — who cites what, rather than who has
written about whom.

## Character of each harvest

The sources do not measure the same thing, and mixing them without saying so
would be the main way to lie with this corpus.

**Bibliometric sources** (OpenAlex, Crossref, Semantic Scholar) are broad, carry
citation counts, and are strongly biased towards recent, anglophone,
DOI-bearing articles. They also bring in most of the noise: their queries return
everything that mentions the name, including homonyms and passing references.
7 274 OpenAlex records and 4 111 Crossref records were flagged as probable noise
at harvest, and the thematic classification pushed most of the rest out.

**Catalogues** (IxTheo/K10plus, SBN) are curated. Every record in the IxTheo
harvest is attached by the Tübingen cataloguers to the authority record for
Origen, which is why the classification treats that harvest differently: a
record with no positive signal in its metadata is far more likely to be a
thinly-described study than a false positive.

**Field bibliographies** (Adamantius/GIROTA, BIBP) are the work of specialists
and are the most reliable per record. They are also the smallest, the slowest to
appear, and the hardest to harvest, since they are published as prose bulletins
rather than as data.

**Repositories and thesis registries** (ISIDORE, theses.fr, Dialnet) fill the
francophone and hispanophone gaps the bibliometric sources leave, and carry
abstracts the others do not have.

## Harvest conventions

Every harvester in `scripts/` holds to the same rules: one request per second,
`Retry-After` honoured up to an hour, a resumable cursor so an interrupted run
restarts where it stopped rather than from the beginning, and a raw file written
per source and per date. No harvesting runs in continuous integration — there is
no reason to make ten servers pay for a test suite.
