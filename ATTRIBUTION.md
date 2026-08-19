# Attribution

Origenality holds no bibliographic data of its own. Every record it shows was
harvested from a database that built it, and every one carries the name of that
database and a link back to the record it came from. This file is the table of
those databases, their licences, and the link template that turns a record
identifier into an address. The machine-readable version of the same table sits
in a fenced JSON block inside `DATA_POLICY.md`, and `scripts/check_release.py`
reads it: a summary whose database is not in the table, or whose attribution
does not resolve to a link, blocks the release.

## What you must do when you reuse this

1. **Name the database** for each record you reuse, not just this project. The
   `label` column below is the name to print.
2. **Keep the link** to the source record when you display a summary. A database
   name without a link is a typographic credit, not an attribution.
3. **Semantic Scholar data are ODC-BY 1.0**: attribution is required by the
   licence itself, not by courtesy. If your reuse includes any record whose
   summary or citation count came from Semantic Scholar, the attribution must
   appear wherever you publish it.
4. **Cite Origenality separately** for the federation, the deduplication and the
   classification, which are the parts this project made. See `CITATION.cff`.

## The table

| Key | Label to print | Licence / terms | Link template |
|---|---|---|---|
| `ixtheo-k10plus` | Index Theologicus (IxTheo / K10plus) | CC0 1.0 (K10plus metadata) | `https://ixtheo.de/Record/{id}` |
| `openalex` | OpenAlex | CC0 1.0 | `{id}` — the identifier is itself an address, and it must be on `openalex.org` |
| `crossref` | Crossref | Crossref open metadata policy | `https://doi.org/{id}` |
| `semanticscholar` | Semantic Scholar | **ODC-BY 1.0 — attribution required by the licence** | `https://www.semanticscholar.org/paper/{id}` |
| `isidore` | ISIDORE (Huma-Num) | terms of the aggregator and of each provider | `https://hdl.handle.net/{id}` |
| `thesesfr` | theses.fr | Licence Ouverte / Open Licence (Etalab) | `https://theses.fr/{id}` |
| `k10plus` | K10plus (GBV / BSZ) | CC0 1.0 (K10plus metadata) | `https://opac.k10plus.de/DB=2.1/PPNSET?PPN={id}` |
| `b3kat` | B3Kat (Bibliotheksverbund Bayern / KOBV) | CC0 1.0 (B3Kat metadata) | `https://opacplus.bib-bvb.de/TouchPoint_touchpoint/perma.do?q=+0%3D%22{id}%22+IN+%5B2%5D&v=bvb&l=de` |
| `gnomon-gbd` | Gnomon Bibliographische Datenbank (Eichstätt) | GBD's own terms; the metadata itself is served by B3Kat | `https://www.gbd.digital/Record/{id}` |
| `dnb` | Deutsche Nationalbibliothek | CC0 1.0 | `https://d-nb.info/{id}` |
| `bnf` | Bibliothèque nationale de France | Licence Ouverte / Open Licence (Etalab) | `https://catalogue.bnf.fr/ark:/12148/{id}` |
| `loc` | Library of Congress | CC0 1.0 / public domain (US Government work) | `https://lccn.loc.gov/{id}` |
| `sudoc` | Sudoc — ABES | **Licence Ouverte (Etalab); the licence requires printing “Agence bibliographique de l'Enseignement supérieur”** | `https://www.sudoc.fr/{id}` |
| `sbn` | SBN — Servizio Bibliotecario Nazionale | terms of the ICCU | `https://opac.sbn.it/bid/{id}` |
| `bibp` | BIBP — Université Laval | terms of BIBP (Université Laval) | none — records carry their own address or none |
| `adamantius-girota` | GIROTA / Adamantius | terms of Morcelliana / GIROTA | none — records carry their own address or none |
| `dialnet` | Dialnet | terms of Dialnet (Universidad de La Rioja) | none — records carry their own address or none |
| `generated` | Summary written by Origenality | licence of this repository | none |

A template of `none` does not mean the record has no address. It means the
database publishes no address that can be built from an identifier, so the
record is only publishable when the harvest captured its own URL. Records that
have neither are not published with a summary.

## Summaries, and their removal

Summaries are published because a bibliography without them is much harder to
use. They are published under one condition and one promise: the condition is
that each one names its database and links to its record; the promise is that any
rights holder who asks for one to be removed gets it removed.

The removal is a command, not a negotiation:

```bash
python3 scripts/check_release.py <dump> --withdraw <source> --strip <out.jsonl>
```

The withdrawn database is recorded in the dump itself (`withdrawn_sources`), so
the next build cannot bring the summaries back by accident.

Write to **romain.girardi@univ-cotedazur.fr**, name the database or the record,
and it goes out of the next build. No justification is required.

## Sources not present, and why

Subscription indexes — L'Année philologique, ATLA and the like — are not
harvested. Their terms do not allow redistribution, and a bibliography that
cannot be republished is of no use as a public instrument. Their absence is a
real gap in coverage, thickest before 1980, and `docs/methodology.md` says where
it shows.
