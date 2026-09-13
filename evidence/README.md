# Full-text evidence layer

The bibliographic map and the evidence graph answer different questions. The
map records that a study exists and where it sits in the field. The evidence
graph records a scholar's stated position, the passage that supports the
representation, and the activity that produced the locator. A claim without a
resolving passage does not enter this layer.

## Model

`ScholarPosition` is a first-class node. It is never collapsed into a fact
about Origen. Contradictory positions can therefore coexist, each attributed to
its author and source. The private JSON-LD projection types the proposition set
with CRMinf and carries PROV-O provenance. Relations between positions use the
Citation Typing Ontology. Documents, editions and PDF instances remain distinct
so that a quotation never floats free of the version that supplied it.

The implementation follows six public specifications:

- [PROV-O](https://www.w3.org/TR/prov-o/) for entities, activities and agents;
- [Web Annotation](https://www.w3.org/TR/annotation-model/) for quote and
  position selectors;
- [CRMinf 1.2.1](https://cidoc-crm.org/crminf/ModelVersion/crminf-1.2.1) for
  attributed propositions and argumentation;
- [LRMoo 1.0](https://cidoc-crm.org/node/8951) for work, expression,
  manifestation and item distinctions;
- [SHACL 1.0](https://www.w3.org/TR/shacl/) as the target RDF validation layer;
- [CiTO 2.8.2](https://sparontologies.github.io/cito/current/cito.html) for
  agreement, critique, extension and qualification links.

JSON Schema is the executable validation format in this repository. SHACL is a
planned RDF export, not a second source of truth.

## Storage boundary

The following files never leave the private repository:

```text
data/evidence/private/pdfs/          acquired PDF instances
data/evidence/private/extracted/     page-preserving text and page hashes
data/evidence/private/knowledge-graph.jsonld
data/evidence/curated/claims.jsonl   full verbatim evidence
```

The build emits `site/data/evidence.json`. It contains the claim statement,
source, printed locator and content hashes. It includes verbatim text only when
the document carries an explicit, reviewed release basis. Open access without a
named licence does not clear long quotation.

This boundary reflects the warning in the Web Annotation model that a
`TextQuoteSelector` can disclose protected content. A private record keeps both
the quote and its position. The public record keeps a position and page hash
when the text itself is not cleared.

## Ingest a PDF

The page map is a list of ranges established from visible folios. Physical page
numbers are one-based PDF positions; printed pages are the numbers on the work.
The command never infers the second from the first.

```json
[
  {
    "pdf_start": 2,
    "pdf_end": 54,
    "printed_start": 237,
    "confidence": 1.0,
    "method": "visible-folio-verified"
  }
]
```

```bash
python3 evidence/ingest_pdf.py article.pdf \
  --title "Article title" --author "Author name" --year 2020 \
  --record-id "ixtheo:record" --doi "10.x/example" \
  --source-url "https://publisher.example/article" \
  --access open-access --license "CC BY 4.0" \
  --license-url "https://creativecommons.org/licenses/by/4.0/" \
  --tdm-basis open-license --tdm-opt-out not-applicable \
  --retention-rule "Retain with the evidence record." \
  --public-quote-policy licensed-verbatim \
  --rights-review-status license-verified --public-quote-clearance \
  --page-map page-map.json
```

The extractor requires Poppler's `pdfinfo` and `pdftotext`, plus MuPDF's
`mutool` as an independent encoding check. A sparse result is marked
`needs-ocr-review`. Replacement glyphs or suspicious characters are recorded
per page; a mixed document can still support a claim on a clean page, while the
affected pages remain blocked. OCR is a separate review workflow because a
plausible transcription is not a verbatim source.

## Anchor, validate and build

```bash
python3 evidence/anchor_quote.py \
  --document-id doc:... --pdf-page 12 --quote-file quote.txt --language en

python3 evidence/validate_evidence.py
python3 evidence/build_evidence.py
python3 -m unittest evidence/tests/test_evidence.py
```

The validator checks the PDF digest, page digest, printed-page confidence,
position selector, quote selector, author vocabulary and publication rights.
Any mismatch blocks both projections.

## Rights gate

The public build is fail-closed. `public_quote_clearance` remains false until a
licence or permission has been checked. A downloadable PDF is not, by itself, a
licence to republish it. For sources under ordinary copyright, the public graph
can publish a curator-written statement, DOI or catalogue URL, printed page,
position and hashes; any short quotation is separately selected and reviewed.

This is a risk-control workflow, not legal advice. The project records the
lawful access basis, licence, rights holder, text-and-data-mining basis, opt-out,
retention rule, commercial status, adaptation permission and exclusions for
third-party material before extraction begins.
