#!/usr/bin/env node
/* Regression tests for site/assets/search-core.js and for the CLI options.
 *
 *   node scripts/test_search_core.mjs
 *
 * No framework and no dependency; exits 1 on the first run that has a failure.
 * The core tests run on a small synthetic map, so they state the rule and do
 * not move when the corpus grows. The CLI tests read this checkout (either
 * geometry) and check exit statuses, not figures.
 */
import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const CORE = [join(ROOT, 'site/build-c/assets/search-core.js'), join(ROOT, 'site/assets/search-core.js')]
  .find((p) => existsSync(p));
const C = require(CORE);

let passed = 0;
const failures = [];
function check(name, ok, detail) {
  if (ok) passed++;
  else failures.push(detail === undefined ? name : `${name}: ${JSON.stringify(detail)}`);
}
function eq(name, got, want) {
  check(name, JSON.stringify(got) === JSON.stringify(want), { got, want });
}

/* ------------------------------------------------------------------ fixture */

const SEM = {
  domains: {
    exegesis: { label: 'Exegesis and hermeneutics', labels: { fr: 'Exégèse et herméneutique' } },
    prayer: { label: 'Prayer and martyrdom', labels: { de: 'Gebet und Martyrium' } },
  },
  themes: {
    'exegesis.allegory': { domain: 'exegesis', label: 'Allegory and the spiritual senses',
      labels: { de: 'Allegorese' }, aliases: ['allegory'] },
    'prayer.martyrdom': { domain: 'prayer', label: 'Martyrdom', labels: {}, aliases: [] },
  },
  works: {
    cels: { label: 'Contra Celsum', labels: {}, aliases: ['contre celse', 'gegen kelsos'] },
    unspecified: { label: 'No specific work / Origen in general' },
  },
  approaches: { philological: { label: 'Philological and text-critical', labels: {}, aliases: [] } },
  byPpn: {
    P1: { r: 'core', t: ['exegesis.allegory'], w: ['cels'], a: ['philological'] },
    P2: { r: 'core', t: [], w: ['unspecified'], a: [] },
    P3: { r: 'partial', t: ['prayer.martyrdom', 'nope.unknown'], w: [], a: ['unknown'] },
    P4: { r: 'core', t: [], w: ['unspecified'], a: [] },
    P5: { r: 'marginal', t: [], w: [], a: [] },
    P6: { r: 'core', t: [], w: [], a: [] },
    P7: { r: 'core', t: [], w: ['cels'], a: [] },
    P9: { r: 'core', t: [], w: [], a: [] },
  },
};
const pub = (ppn, title, year, lang, type) => ({ k: 'pub', ppn, title, year, lang, type, url: `https://example.org/${ppn}` });
const GRAPH = {
  nodes: [
    pub('P1', "Bibliographie critique d'Origène", 1971, 'fr', 'book'),                        // 0
    pub('P2', 'Jerome and the Hexapla', 1990, 'en', 'article'),                               // 1
    pub('P3', 'Rome and Alexandria', 2001, 'en', 'article'),                                  // 2
    pub('P4', 'Die Sündenvergebung bei Origenes: ein Beitrag zur altchristlichen Bußlehre', 1955, 'de', 'book'), // 3
    pub('P5', 'Ωριγένους Φιλοσοφούμενα', null, 'grc', 'book'),                               // 4
    pub('P6', "Samaritaine et samaritains dans l'Église", 1985, 'fr', 'book'),               // 5
    pub('P7', 'Contra Celsum in Armenian', 1980, 'arm', 'chapter'),                           // 6
    { k: 'author', label: 'Crouzel, Henri', title: 'an author node that carries a title' },   // 7
    pub('P8', '', 2010, 'de', 'article'),                                                     // 8 untitled pub
    { k: 'subject', label: 'allegory' },                                                      // 9
    { k: 'container', label: 'Adamantius' },                                                  // 10
    pub('P9', 'Origen on the free', 2015, 'en', 'article'),                                   // 11
    { k: 'author', label: 'Will, Robert' },                                                   // 12
  ],
  edges: [
    { s: 0, t: 7, r: 'aut' }, { s: 0, t: 9, r: 'sub' }, { s: 2, t: 10, r: 'in' },
    { s: 1, t: 7, r: 'aut' }, { s: 11, t: 12, r: 'aut' },
  ],
};
const ABS = { byPpn: { P3: { t: 'A study of the Roman church and its bishops.', s: 'openalex' } } };
// data/cite.json, version 2: every heading and container of a record, the
// ones graph.json keeps (P1 'allegory', P3 'Adamantius') and those it drops
const CITE = { schema: 'origenality-cite/2', byPpn: {
  P1: { s: ['allegory', 'Antisemitismus'] },
  P3: { c: 'Adamantius', ct: 'series' },
  P6: { c: 'Rare journal', s: ['Homerus', 'Geistesgeschichte 30-300'] },
} };

const IDX = C.buildIndex(GRAPH, SEM, ABS, CITE);
const R = IDX.records;
const byPpn = (ppn) => R.find((p) => p.ppn === ppn);
const ids = (r) => [...r.matched].map((i) => R[i].ppn).sort();
const hits = (r) => r.order.filter((i) => !r.vocabOnly.has(i)).map((i) => R[i].ppn);
const kinds = (r) => r.errors.map((e) => e.kind);

/* ------------------------------------------------------------------ index (OR-12, OR-26, OR-58) */

eq('the index holds every node of kind pub, untitled included, and nothing else',
  R.map((p) => p.ppn), ['P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8', 'P9']);
check('i is the position in records', R.every((p, i) => p.i === i));
eq("the 'unspecified' sentinel is not a work of the index", byPpn('P2').works, []);
eq('unknown theme and approach keys are dropped', [byPpn('P3').themes, byPpn('P3').approaches],
  [['prayer.martyrdom'], []]);
check("the sentinel is not a key a query may name", !IDX.keys.works.includes('unspecified'));
check('the sentinel label is not in the heading index', !/specific work/.test(R.map((p) => p.vocab).join(' ')));
eq('domains follow the themes', byPpn('P1').domains, ['exegesis']);
check('legacy aliases rel/appr/doms are kept', byPpn('P1').appr === byPpn('P1').approaches
  && byPpn('P1').doms === byPpn('P1').domains && byPpn('P1').rel === 'core');
eq('rawlang carries the stored code', byPpn('P7').rawlang, 'arm');
check('the abstract is in the free-text index', /roman church/.test(byPpn('P3').hay));

/* ------------------------------------------------------------------ normalisation (OR-03, OR-15) */

eq('an apostrophe ends a word', C.norm("d'Origène"), 'd origene');
eq('the typographic apostrophe too', C.norm('d’Origène'), 'd origene');
eq('ß folds to ss', C.norm('Bußlehre'), 'busslehre');
eq('œ, æ, ø, ł fold', C.norm('Œuvre Æther Søren Łódź'), 'oeuvre aether soren lodz');
eq('Greek keeps its letters, final sigma folds', C.norm('Ὠριγένης'), 'ωριγενησ');
eq('an elided article is dropped as a short word', C.tokens("d'Origène"), ['origene']);
eq('a Greek word is a token', C.tokens('Ωριγένους'), ['ωριγενουσ']);
eq('a Cyrillic word is a token', C.tokens('Ориген'), ['ориген']);
eq('ß does not cut a word', C.tokens('großen'), ['grossen']);

/* ------------------------------------------------------------------ word starts, elisions (OR-03) */

eq("'Origène' finds d'Origène (and Origenes, at a word start)", ids(C.search(IDX, 'Origène')), ['P1', 'P4']);
eq("the elided form answers like the bare word", ids(C.search(IDX, 'd’Origène')), ['P1', 'P4']);
check("'Origen' reaches Origène and Origenes", ['P1', 'P4', 'P9'].every((p) => ids(C.search(IDX, 'origen')).includes(p)));
eq("a phrase with an elision matches either apostrophe",
  [ids(C.search(IDX, '"l\'Église"')), ids(C.search(IDX, '"l’Église"'))], [['P6'], ['P6']]);
eq('Rome does not answer Jerome', ids(C.search(IDX, 'rome')), ['P3']);

/* ------------------------------------------------------------------ phrases (OR-14) */

eq('a quoted phrase does not match inside a word', ids(C.search(IDX, '"rome"')), ['P3']);
eq('a quoted phrase is bounded at its end', ids(C.search(IDX, '"rom"')), []);
eq('a phrase does not run from the title into the author', ids(C.search(IDX, '"free will"')), []);
eq('the same words unquoted are a conjunction', hits(C.search(IDX, 'free will')), ['P9']);
eq('curly and guillemet quotation marks open a phrase',
  [C.search(IDX, '“free will”').phrases, C.search(IDX, '« Contre Celse »').phrases],
  [['free will'], ['contre celse']]);
eq('a negated phrase excludes', ids(C.search(IDX, 'origen -"on the free"')), ['P1', 'P4']);

/* ------------------------------------------------------------------ non-Latin input (OR-15) */

eq('a Greek query reaches a Greek title', ids(C.search(IDX, 'Ωριγένους')), ['P5']);
eq('Bußlehre and Busslehre reach Bußlehre', [ids(C.search(IDX, 'Bußlehre')), ids(C.search(IDX, 'Busslehre'))],
  [['P4'], ['P4']]);
{
  const r = C.search(IDX, 'Ориген');
  eq('an absent Cyrillic term is named', r.absentTerms, ['ориген']);
}
{
  const r = C.search(IDX, 'PG');
  eq('a query that normalises to nothing says so', [r.normalisedEmpty, r.droppedTerms, r.matched.size], [true, ['pg'], 0]);
  eq('stopwords alone normalise to nothing', C.search(IDX, 'the and').normalisedEmpty, true);
  eq('a blank query is blank, not empty', [C.search(IDX, '  ').blank, C.search(IDX, '  ').normalisedEmpty], [true, false]);
  eq('queryIsBlank', ['', '  ', 'l:fr', 'PG', 'foo:bar'].map(C.queryIsBlank), [true, true, false, false, false]);
}

/* ------------------------------------------------------------------ absence (OR-02) */

{
  const r = C.search(IDX, 'year:2026 rome allegory');
  eq('a term present in the corpus is not absent because a filter hides it', r.absentTerms, []);
  eq('it is reported apart', r.absentUnderFilters, ['rome', 'allegory']);
  const k = C.search(IDX, 'rome', { keep: (p) => p.lang === 'de' });
  eq('the same under keep', [k.absentTerms, k.absentUnderFilters], [[], ['rome']]);
  eq('a term in no record is absent', C.search(IDX, 'Ethiopia').absentTerms, ['ethiopia']);
  eq('a term found only in a heading is not absent', C.search(IDX, 'Kelsos Ethiopia').absentTerms, ['ethiopia']);
  eq('no filter, nothing absent under filters', C.search(IDX, 'Ethiopia').absentUnderFilters, []);
}

/* ------------------------------------------------------------------ widening (OR-13) */

{
  const r = C.search(IDX, 'samaritaine samaritains');
  eq('a thin answer carrying every term is not widened', [r.fullHit, r.widened, r.hitDepth], [1, false, 2]);
  const w = C.search(IDX, 'origen rome');
  eq('a real widening is flagged', [w.fullHit, w.widened, w.hitDepth], [0, true, 1]);
  const t = C.search(IDX, 'origen rome');
  eq('per-term reach', t.termHits, [3, 1]);
}

/* ------------------------------------------------------------------ years (OR-23) */

check('year:<2000 leaves the undated record out', !ids(C.search(IDX, 'year:<2000')).includes('P5'));
check('-year:<2000 leaves it out too', !ids(C.search(IDX, '-year:<2000')).includes('P5'));
eq('year bounds', [ids(C.search(IDX, 'year:<=1971')), ids(C.search(IDX, 'year:>2001')), ids(C.search(IDX, 'year:1980-1990'))],
  [['P1', 'P4'], ['P8', 'P9'], ['P2', 'P6', 'P7']]);

/* ------------------------------------------------------------------ headings (OR-53, OR-56) */

{
  const plain = C.search(IDX, 'Contre Celse');
  const french = C.search(IDX, 'Contre Celse ?');
  eq('an alias reaches its work', plain.vocabHit, 2);
  eq('trailing French punctuation keeps the heading', [french.vocabHit, french.heading, french.widened],
    [plain.vocabHit, 'Contre Celse', plain.widened]);
  eq('so does a trailing full stop', C.search(IDX, 'Contre Celse.').vocabHit, 2);
  const fr = C.search(IDX, 'Contre Celse', { keep: (p) => p.lang === 'fr' });
  eq('the heading count follows keep', [fr.vocabHit, fr.vocabHitAll], [1, 2]);
  eq('the sentinel label is no heading', C.search(IDX, 'No specific work').vocabHit, 0);
}

/* ------------------------------------------------------------------ malformed queries (OR-16) */

eq('unknown field', kinds(C.search(IDX, 'foo:bar')), ['unknown_field']);
eq('unknown field names are listed', C.search(IDX, 'foo:bar title:x').unknownFields, ['foo', 'title']);
check('an invalid query is not evaluated', C.search(IDX, 'foo:bar origen').matched.size === 0
  && C.search(IDX, 'foo:bar origen').invalid);
eq('empty field', kinds(C.search(IDX, 'author:')), ['empty_value']);
eq('empty quoted field', kinds(C.search(IDX, 'author:""')), ['empty_value']);
eq('empty phrase', kinds(C.search(IDX, '""')), ['empty_value']);
eq('unclosed quotation mark', kinds(C.search(IDX, '"free will')), ['unclosed_quote']);
eq('unclosed quotation mark in a field', kinds(C.search(IDX, 'author:"de lubac')), ['unclosed_quote']);
eq('invalid year', kinds(C.search(IDX, 'year:abc')), ['invalid_year']);
eq('five-digit year', kinds(C.search(IDX, 'year:19710')), ['invalid_year']);
eq('open range', kinds(C.search(IDX, 'year:1971-')), ['invalid_year']);
eq('reversed range', kinds(C.search(IDX, 'year:2000-1990')), ['reversed_year_range']);
eq('unknown language', kinds(C.search(IDX, 'lang:xx')), ['unknown_language']);
eq('unknown type', kinds(C.search(IDX, 'type:bok')), ['unknown_type']);
eq('unknown key', kinds(C.search(IDX, 'work:unspecified')), ['unknown_key']);
eq('a colon followed by a space is prose', kinds(C.search(IDX, 'Origen: Contra Celsum')), []);
check('every error carries a message', C.search(IDX, 'foo:bar year:abc').errors.every((e) => e.message && e.token));

/* ------------------------------------------------------------------ languages (OR-57) */

eq('Armenian: hy, arm, hye', ['lang:hy', 'lang:arm', 'lang:hye'].map((q) => ids(C.search(IDX, q))),
  [['P7'], ['P7'], ['P7']]);
eq('MARC aliases', ['lang:fre', 'lang:fra', 'lang:ger', 'lang:deu', 'lang:eng', 'l:fr'].map((q) => ids(C.search(IDX, q)).length),
  [2, 2, 2, 2, 3, 2]);
eq('a language name resolves', [C.resolveLanguage('English'), C.resolveLanguage('français'), C.resolveLanguage('xx')],
  ['en', 'fr', null]);

/* ------------------------------------------------------------------ fields */

eq('approach: reaches the approach', ids(C.search(IDX, 'approach:philo')), ['P1']);
eq('domain: reaches the domain', ids(C.search(IDX, 'domain:prayer')), ['P3']);
eq('author: at a word start', ids(C.search(IDX, 'author:crouz')), ['P1', 'P2']);
eq('in: reaches the container', ids(C.search(IDX, 'in:adamantius')), ['P3']);
{
  const legacy = [{ i: 0, hay: '', appr: ['philological'], doms: ['exegesis'], lang: 'oth', rawlang: 'la' }];
  eq('the older records array still answers approach:, domain:, lang:',
    ['approach:philo', 'domain:exe', 'lang:la'].map((q) => C.search(legacy, q).matched.size), [1, 1, 1]);
}

/* ------------------------------------------------------------------ order (OR-61) */

eq('a field-only query reads newest first, undated last',
  C.search(IDX, 'type:book').order.map((i) => R[i].ppn), ['P6', 'P1', 'P4', 'P5']);
eq('ties on score and year break on title',
  C.compareHits({ i: 1, year: 1990, title: 'B' }, { i: 0, year: 1990, title: 'A' }, null) > 0, true);
{
  const r = C.search(IDX, 'origen samaritains', { widenFloor: 1 });
  check('score comes before year', r.order.length > 0 && r.scores[r.order[0]] >= r.scores[r.order[r.order.length - 1]]);
}

/* ------------------------------------------------------------------ counted figures (F1 fields) */

{
  const r = C.search(IDX, 'origen');
  eq('fullHitCounted leaves out records outside the density', [r.fullHit, r.fullHitCounted], [3, 3]);
  eq('a field-only query counts too', [C.search(IDX, 'type:book').fullHit, C.search(IDX, 'type:book').fullHitCounted], [4, 3]);
  // P5 is classed marginal: it carries the term and enters no count
  const greek = C.search(IDX, 'Ωριγένους');
  eq('per-term counted reach leaves out records outside the density', [greek.termHits, greek.termHitsCounted], [[1], [0]]);
  eq('per-term counted reach runs parallel to the terms', C.search(IDX, 'origen rome').termHitsCounted, [3, 1]);
  // the heading figure a surface prints is a count: a record filed under the
  // heading and classed marginal is listed, and left out of it
  const SEM2 = { ...SEM, byPpn: { ...SEM.byPpn, P7: { ...SEM.byPpn.P7, r: 'marginal' } } };
  const IDX2 = C.buildIndex(GRAPH, SEM2, ABS, CITE);
  const cc = C.search(IDX2, 'Contre Celse');
  eq('the counted heading figure leaves out a marginal record', [cc.vocabHit, cc.vocabHitCounted], [2, 1]);
  const ccFr = C.search(IDX2, 'Contre Celse', { keep: (p) => p.lang === 'fr' });
  eq('the counted heading figure follows keep', [ccFr.vocabHit, ccFr.vocabHitCounted], [1, 1]);
  eq('no heading, no counted heading figure', C.search(IDX, 'type:book').vocabHitCounted, 0);
}

/* ------------------------------------------------------------------ every heading (S-P1) */
// graph.json keeps a heading only when three records share it: an index built
// on it alone named "antisemitismus" absent from a corpus whose record carries it.

{
  const partial = C.buildIndex(GRAPH, SEM, ABS);
  eq('without cite.json the index is partial, with it complete', [partial.fields, IDX.fields], ['partial', 'complete']);
  const p = C.search(partial, 'Antisemitismus');
  eq('a partial index names no term absent, and says which it did not find', [p.absentTerms, p.absentFromPartialIndex, p.fields],
    [[], ['antisemitismus'], 'partial']);
  const c = C.search(IDX, 'Antisemitismus');
  eq('a heading no other record shares is searched', [ids(c), c.absentTerms, c.absentFromPartialIndex], [['P1'], [], []]);
  eq('so is a heading of the subject chains, dates and all', ids(C.search(IDX, 'Geistesgeschichte')), ['P6']);
  eq('a term absent from the complete index is named', C.search(IDX, 'Ethiopia').absentTerms, ['ethiopia']);
  eq('in: reaches a container graph.json does not keep', ids(C.search(IDX, 'in:rare')), ['P6']);
  eq('the graph headings stay', byPpn('P1').subjects, ['allegory', 'Antisemitismus']);
  const later = C.applyCite(C.buildIndex(GRAPH, SEM, ABS), CITE);
  check('building then reading cite.json gives the index built with it, record by record',
    later.records.every((q, k) => q.hay === R[k].hay && JSON.stringify(q.subjects) === JSON.stringify(R[k].subjects)
      && q.container === R[k].container) && later.fields === 'complete');
  const v1 = C.applyCite(C.buildIndex(GRAPH, SEM, ABS), { schema: 'origenality-cite/1', byPpn: { P1: { c: 'X' } } });
  eq('a version 1 file leaves the index partial, graph headings kept', [v1.fields, v1.records[0].subjects], ['partial', ['allegory']]);
  eq('the fields searched, in words', C.searchedFields(IDX).slice(2, 4), ['subject headings', 'journal or volume']);
  check('a partial index says what it holds, with the graph thresholds',
    C.searchedFields(C.buildIndex({ ...GRAPH, thresholds: { subject_min_publications: 3, container_min_publications: 5 } }, SEM, ABS))
      .includes('subject headings shared by 3 or more records'));
}

/* ------------------------------------------------------------------ CLI options (OR-17, OR-18) */

const CLI = join(ROOT, 'cli/origenality.mjs');
function cli(...args) {
  const out = spawnSync(process.execPath, [CLI, ...args], { encoding: 'utf8', timeout: 120000 });
  return { status: out.status, stdout: out.stdout, stderr: out.stderr };
}
const local = ['--local', ROOT];
const status2 = [
  ['search', 'allegory', '--limit', '-1'],
  ['search', 'allegory', '--limit', 'abc'],
  ['search', 'allegory', '--limit'],
  ['search', 'allegory', '--since', 'abc'],
  ['search', 'allegory', '--since', '2000', '--until', '1990'],
  ['search', 'allegory', '--lang'],
  ['search', 'allegory', '--lang', 'xx'],
  ['search', 'allegory', '--frobnicate'],
  ['stats', '--since', '2000'],
  ['record'],
  ['density'],
  ['density', 'themes'],
  ['density', 'kinds', 'x'],
  ['density', 'theme', 'nope'],
  ['density', 'themes', 'nope'],
  ['vocabulary', 'foo'],
  ['frobnicate'],
  ['search', 'year:abc'],
  ['search', 'PG'],
  ['gap', 'foo:bar allegory'],
  // C-9: an argument a command does not take, an option with no command
  ['coverage', 'extra'],
  ['stats', 'extra'],
  ['--json'],
  ['--limit', '3'],
];
for (const args of status2) {
  const res = cli(...args, ...local);
  check(`exit 2: ${args.join(' ')}`, res.status === 2, { status: res.status, stderr: res.stderr.slice(0, 200) });
  check(`a message on stderr: ${args.join(' ')}`, res.stderr.trim().length > 0);
}
{
  eq('--help alone, and no argument at all, print the usage with status 0', [cli('--help').status, cli().status], [0, 0]);
  check('the stats help says what population each part counts', /"counted"/.test(cli('--help').stdout) && /"population"/.test(cli('--help').stdout));
}
{
  const res = cli('search', 'allegory', '--local');
  check('--local with no path is an error, never a network read', res.status === 2, res.stderr);
  const none = cli('search', 'allegory', '--local', join(ROOT, 'no-such-directory'));
  check('--local on a missing directory is an error', none.status === 2, none.stderr);
}
{
  const res = cli('search', 'year:abc', '--json', ...local);
  const body = JSON.parse(res.stdout);
  eq('a refused query in JSON', [body.error, body.query_errors[0].kind], ['query_not_understood', 'invalid_year']);
  const empty = JSON.parse(cli('gap', 'PG', ...local).stdout);
  eq('a query with no term in JSON', [empty.error, empty.dropped_terms], ['no_searchable_term', ['pg']]);
}
{
  const json = (...a) => JSON.parse(cli(...a, '--json', ...local).stdout);
  const byOption = json('search', 'allegory', '--lang', 'FR');
  const byGrammar = json('search', 'allegory lang:FR');
  eq('--lang takes what lang: takes', [byOption.listed, byOption.counted_in_density],
    [byGrammar.listed, byGrammar.counted_in_density]);
  const zero = json('search', 'allegory', '--limit', '0');
  eq('--limit 0 returns no record and keeps the figures', [zero.results.length, zero.listed > 0], [0, true]);
  for (const [kind, key, extra] of [['work', 'cels', []], ['theme', 'exegesis', []],
    ['theme', 'exegesis.allegory', ['--since', '2000']], ['work', 'cels', ['--lang', 'de']]]) {
    const d = json('density', kind, key, ...extra);
    const s = json('search', `${kind}:${key}`, ...extra);
    eq(`density ${kind} ${key} ${extra.join(' ')} agrees with search`,
      [d.listed, d.counted_in_density, d.corpus_density_total],
      [s.listed, s.counted_in_density, s.corpus_density_total]);
  }
  const law = json('gap', 'Origen and Roman law');
  const lead = law.carrying_all_terms_counted
    ? String(law.carrying_all_terms_counted).replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + ' counted work'
    : 'No counted work';
  check('gap leads with the counted records carrying every term', law.answer.startsWith(lead), law.answer);
  eq('gap reports each term\'s counted reach', Object.keys(law.per_term_counted), law.query_terms);
  // S-P1: three words of subject headings graph.json drops, once named absent
  for (const word of ['Antisemitismus', 'Homerus', 'Geistesgeschichte']) {
    const g = json('gap', `Origen ${word}`);
    check(`gap "Origen ${word}": the heading word is found, not named absent`,
      !g.terms_absent_from_corpus.includes(C.norm(word)) && g.per_term[C.norm(word)] > 0 && !g.terms_not_found_partial_index,
      { absent: g.terms_absent_from_corpus, per_term: g.per_term });
  }
  const cov = json('coverage');
  check('coverage counts every record with a heading, and names the fields searched',
    cov.with_subjects > 0 && Array.isArray(cov.searched_fields) && cov.searched_fields.includes('subject headings')
    && cov.caveat.includes('subject headings'), cov);
  const dc = json('density', 'work', 'cels');
  const sc = json('search', 'work:cels');
  eq('density carries the reliability figures of search',
    [dc.review_flagged, dc.with_abstract, dc.no_year, dc.top_source],
    [sc.reliability.review_flagged, sc.reliability.with_abstract, sc.reliability.no_year, sc.reliability.top_source]);
  check('the reliability figures describe the counted records', sc.reliability.counted === sc.counted_in_density
    && sc.reliability.review_flagged <= sc.reliability.counted, sc.reliability);
  const since = json('density', 'theme', 'exegesis.allegory', '--since', '2000');
  check('density honours --since in its decades', Object.keys(since.by_decade).every((d) => Number(d) >= 2000),
    since.by_decade);
}

/* ------------------------------------------------------------------ report */

if (failures.length) {
  console.error(failures.map((f) => `  x ${f}`).join('\n'));
  console.error(`\n${failures.length} failed, ${passed} passed`);
  process.exit(1);
}
console.log(`${passed} checks passed`);
