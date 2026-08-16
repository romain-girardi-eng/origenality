# Methodology

How the records get from ten catalogues to one map: what is federated, what is
merged, what is classified, and what the density figure counts. Every rule below
is enforced by code in this repository, and the tests that hold it are named.

## 1. Federation

Ten sources are harvested, one script per source in `scripts/`, each of them
rate-limited to one request per second, resumable, and writing a dated raw file.
The harvest of August 2026 brought in 45 685 records. `docs/sources.md` lists the
sources, their access method and their licences.

The harvesters agree on nothing but a shape: a JSON line per record, with the
fields the source happens to publish. Normalisation happens once, in the merge,
so that a catalogue's idiosyncrasies stay legible up to that point and can be
argued with afterwards.

## 2. Deduplication

45 685 records become 42 210 clusters. A cluster is one work; the records that
built it stay listed inside it, with their source and their identifier, and the
values they disagreed about are kept in a `conflicts` field rather than being
silently arbitrated away. Three links can bring two records into one cluster.

**DOI.** Same normalised DOI, same work. The normalisation strips resolvers,
lowercases, URL-decodes and removes trailing punctuation, because
`…/abc%3adef`, `…/abc:def` and `…/abc:def.` were three identifiers for one
article. Two *different* DOIs are only brought together on complete identical
titles long enough to discriminate, and never when they carry different volume
markers: the two Cambridge volumes of one commentary have the same title, two
DOIs, and only their summaries say which is volume 1.

**Fuzzy title.** First 80 characters of the normalised title, plus the first
author's surname, plus the declared type. Groups above six members are left
unmerged. Past that size the key is not a work but a service title of the kind
dozens of distinct records share: *Editorial Board*, *Front Matter*,
*Introduction*, *1*.

**ISBN.** Same ISBN (normalised to ISBN-13, checksum verified) means the same
volume, with three refusals. An ISBN carried by more than six distinct titles is
a series number recopied onto its parts, and unites nothing. A gap of more than
one year between the two records is a reissue that kept the old number, and the
two stay apart — *Geist und Feuer* carries 3894113049 in 1951 and again in 1991,
and merging them would erase the first from every time series. Different volume
markers refuse the link, unless the two titles carry the same work designation:
a book can belong to two numbering systems at once, being volume LXXXIV of a
series and volume 10 of a set of conference proceedings. That exception is
itself bounded — a shared run of words that contains a volume word, or that
stops exactly where two numbers diverge, is a series address and not a work
title, so the two volumes of one conference stay apart even if a cataloguing
error gives them the same ISBN.

Cluster identifiers are deterministic and unique: 42 210 clusters, 42 210
identifiers, the merge refusing to emit a duplicate. Two runs of the merge over
the same input produce byte-identical output.

## 3. Classification

A controlled vocabulary, versioned in `semantic/vocabulary/`, on four axes:

- **themes** — 61 leaves under 16 domains (exegesis and hermeneutics, God and
  the Logos, anthropology and free will, and so on), each with English labels and
  German, French and Italian aliases;
- **works of Origen** — 28 named works plus two reservoirs, so that a study of
  the *Commentary on John* is findable as such;
- **approaches** — ten angles: doctrinal, exegetical, philological,
  comparative, reception, edition or translation, and the rest;
- **relevance** — `core`, `partial`, `marginal`, `none`.

Each record is read against the vocabulary and can only be given values that
exist in it: the validation schema is derived from the vocabulary files, so it
cannot drift from them. A value outside the vocabulary is dropped, the repair is
written into the record, and the record is flagged for review. Records that
cannot be read at all go to a rejects file with their cause; none disappears
quietly. Every record carries the vocabulary version, the prompt version and a
digest of the exact input submitted, so a later run can tell what it is
comparing itself with.

Corrections inside a wave are appended rather than overwritten, and the last
line for a record is the one that counts. At the end of a wave the file is
compacted to one line per record, its superseded lines kept in a history beside
it.

**The relevance classes decide every published figure.** A figure counts `core`
and `partial`, and nothing else. `marginal` records — Origen is mentioned, he is
not the subject — are returned by every search and listed under every count, and
enter no count. `none` records are not published. The rule is the same on every
surface, and a check refuses a build where one screen counts a different
population from another.

<!-- FIGURES:classification -->
Of the 21 104 records classified so far: 4 909 `core`, 1 833 `partial` (the
citable dossier, **6 742**), 1 100 `marginal`, 13 262 `none`. The figures are
counted from the wave files published under `semantic/waves/`, and a record
classified again in a later wave counts once, under its last class.
<!-- /FIGURES:classification -->

**What is not yet established.** A reference set of fifty records tagged by hand
exists, with a written protocol. The agreement between hand and machine on the
one question that matters — does this record enter the count or not — has not
been measured against the current prompt, so no agreement figure is published
anywhere until it has been. The threshold the project holds itself to is nine
out of ten.

## 4. Citation weight

Citation counts come from the bibliometric sources and are measured for 14 772
of the 42 210 clusters (35 %). A count is shown as a percentile inside a cohort
of the same decade, the same document type and the same language, with a minimum
cohort of eight; below that the cohort is widened rather than the rank being
guessed. Ranks are averaged over ties and never reach 0 or 1, because no work is
above all others or below all others.

A count can be carried from one cluster to another only when the two share a
folded title, a first author's surname and a declared type — and, in addition,
when their years agree exactly for a journal piece, within one year for a book.
Three such projections exist in the current data, and a standing check re-derives
each one and fails if any of them no longer holds.

Two things the weight is not. It is not a filter: a record with no citation data
keeps the base size and is excluded from nothing. And it is not part of the
density.

**Coverage is uneven by language** — 88.9 % for Spanish, 39.8 % for German,
35.9 % for English, 24.4 % for Italian, 9.6 % for French — because older and
non-anglophone records are largely absent from the bibliometric sources. Reading
citation weight across languages is unsafe, and the site says so where it shows
it.

## 5. Density

The density of a query is **the number of distinct records carried by the nodes
selected for that query, inside the citable perimeter**. Not a weighting, not a
distance, not a score of originality: a headcount, read as "47 studies in this
neighbourhood".

The path from a query to that number: the thematic index holds only `core` and
`partial` records; the navigation selects at most eight nodes, scoring each on
the query terms found in its title, path, computed summary and labels; the
records of the selected nodes are unioned without duplicates; the density is the
size of that union, published with its denominator.

**No match means no selection.** A query whose terms appear nowhere returns an
empty selection and a density of zero, with a message saying so. It does not
return the largest clusters of the index — which is what it did until 16 August
2026, so that an unrelated query produced the highest density in the whole index.

A density is only comparable with a density computed under the same five
parameters: vocabulary version, prompt version, index relevance threshold,
maximum number of nodes, and selection engine. All five are written into the
files that produce it. A density meant to be cited is produced by the
deterministic engine and says so.

**Not implemented**: recency weighting, semantic radius, vector embeddings,
uncertainty intervals, sensitivity to the threshold, weighting by language or by
source. None of these enters the published figure. Citation coverage is measured
and its bias published, but it does not enter the density either.

## 6. Abstracts

Abstracts are published, each with the name of the database that wrote it and a
link to the record it wrote it for. The link points at the *donor* record — the
one that actually carries the summary — and not at some other record of the same
cluster: 3 755 abstracts in the federated perimeter, checked one by one, none
pointing elsewhere.

A release check refuses a dump where any abstract lacks a named database or a
resolvable link. Resolvable is enforced literally: an http(s) scheme, a real
host, no user information in the authority, a port in range, no loopback or
private address, and no path traversal even under double encoding. Where a
database's identifier is itself an address, the address must belong to that
database's declared hosts.

Rights declarations are recorded per record — including when two records of one
cluster carry the same text under different terms — but they decide nothing.
They exist so that a takedown can be executed quickly and exactly. See
`ATTRIBUTION.md`.

## 7. Reproducibility

The pipeline is standard-library Python, and no credential is stored anywhere in
this repository. The harvesters need none. The classification step needs one, and
reads it from the process environment through a neutral adapter
(`semantic/llm_adapter.py`) that names no vendor and no engine: what the
repository records of a classification run is its wave, its prompt version, its
vocabulary version and a digest of the input, never the name of what read it. Each stage is a script, each script writes a
dated output, and a proof harness replays the chain end to end into a temporary
directory, comparing the replayed merge with the reference by SHA-256 and
failing at the first step whose exit code differs from the one it declares. The
test suite holds 136 cases.

What is not reproducible from this repository alone: the raw harvests and the
merged corpus are not published here, so the chain has to be re-run from the
sources. Running the harvesters over the same sources will not produce the
identical corpus of August 2026 — catalogues change — which is why every figure
in this repository is dated.
