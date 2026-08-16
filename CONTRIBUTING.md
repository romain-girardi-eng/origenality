# Contributing

The most useful contribution is a correction to the data. The second most useful
is a source.

## Corrections

Open an issue naming the record — its cluster identifier, or its title and year
— and saying what is wrong:

- **two works merged into one.** Give both, and what distinguishes them: a volume
  number, a different year, a reissue.
- **one work split in two.** Give both identifiers.
- **a misclassification.** Which theme, work or approach it should carry, or that
  it should not be in the citable dossier at all.
- **a wrong link or a wrong attribution** on a summary.

Corrections to the data are applied at the next build; the fix normally goes into
a merge rule or a vocabulary entry rather than into the record, so that it also
catches the cases nobody has reported.

## Sources

A source is worth adding if its metadata can be harvested without a subscription
and republished with attribution. Say which source, what it covers that the ten
in `docs/sources.md` do not, and how it is accessed. Coverage of pre-1980
scholarship and of languages other than English is where the corpus is thinnest.

## Code

Python 3.11, standard library only — no dependency is added without a reason
that survives being written down. Every harvester holds to one request per
second and is resumable. Every change to a merge, classification or publication
rule comes with a test in `scripts/test_data_gates.py` that fails without it,
and the suite runs in under a second:

```bash
python3 scripts/test_data_gates.py
python3 scripts/qa_checks.py all
```

Two rules that are not negotiable. No credential, address or token is committed,
in any form, including in a test fixture. And no figure is written by hand into
a page or a document: figures are generated from the data by a script that also
checks them, because a number typed once is a number wrong later.

## Scope

This is a map of what has been written on Origen, not a critical bibliography and
not a judgement of quality. Proposals that would turn a density into a ranking,
or a citation count into a measure of worth, are outside what the project will
do.
