#!/usr/bin/env node
/* Origenality: the references the Explorer writes, checked without a browser.
 *
 *     node scripts/test_cite_export.mjs
 *
 * cite.js is required as the page loads it. Fixtures check the escaping, the
 * fields each type receives and the fields never written without data; then the
 * whole build is exported from the data layer the page reads (graph.json,
 * semantic.json, abstracts.json, site-merged/corpus.jsonl) and every file is read
 * back by the small parsers below and compared with the records. Exits 1 when a
 * check fails. Works in both geometries: working tree (site/build-c/, site/data/)
 * and public clone (site/, data/).
 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const PAGES = fs.existsSync(path.join(ROOT, 'site/build-c/assets/cite.js'))
  ? path.join(ROOT, 'site/build-c') : path.join(ROOT, 'site');
const DATA = fs.existsSync(path.join(ROOT, 'site/data/graph.json'))
  ? path.join(ROOT, 'site/data') : path.join(ROOT, 'data');
const require = createRequire(import.meta.url);
const C = require(path.join(PAGES, 'assets/cite.js'));
const CORE = require(path.join(PAGES, 'assets/search-core.js'));

let failures = 0, passes = 0;
function check(name, ok, detail) {
  if (ok) { passes++; return; }
  failures++;
  console.log('FAIL ' + name + (detail !== undefined ? ' :: ' + JSON.stringify(detail).slice(0, 600) : ''));
}
function group(name, body) {
  try { body(); } catch (err) { check(name + ' could not run', false, err.stack || err.message); }
}
const oneLine = (s) => String(s == null ? '' : s).replace(/[\u0000-\u001f\u007f\u2028\u2029]+/g, ' ').trim();

/* ------------------------------------------------------------ parsers */
// BibTeX as cite.js writes it: optional % lines, then entries of the form
// @type{key,\n  name = {value},\n ... \n}\n. Braces are counted raw, as BibTeX
// itself counts them, so an unescaped brace breaks the parse.
const UNBIB = {
  '\\textbackslash{}': '\\', '\\textbraceleft{}': '{', '\\textbraceright{}': '}', '\\textasciitilde{}': '~',
  '\\textasciicircum{}': '^', '\\%': '%', '\\&': '&', '\\#': '#', '\\$': '$', '\\_': '_'
};
function unbib(s) {
  return s.replace(/\\textbackslash\{\}|\\textbraceleft\{\}|\\textbraceright\{\}|\\textasciitilde\{\}|\\textasciicircum\{\}|\\[%&#$_]/g,
    (m) => UNBIB[m]);
}
function parseBib(text) {
  const out = [];
  let i = 0;
  const fail = (msg) => { throw new Error('BibTeX ' + msg + ' at offset ' + i + ': ' + JSON.stringify(text.slice(i, i + 80))); };
  for (;;) {
    const at = text.indexOf('@', i);
    const between = text.slice(i, at < 0 ? text.length : at);
    if (between.split('\n').some((l) => l.trim() && !l.startsWith('%'))) fail('text outside an entry');
    if (at < 0) break;
    const head = /^@([a-z]+)\{([A-Za-z0-9_]+),\n/.exec(text.slice(at));
    if (!head) { i = at; fail('entry head'); }
    i = at + head[0].length;
    const fields = {};
    for (;;) {
      const m = /^ {2}([a-z]+) = \{/.exec(text.slice(i));
      if (!m) fail('field head');
      i += m[0].length;
      const start = i;
      let depth = 1;
      while (depth) {
        const ch = text[i];
        if (ch === undefined) fail('unbalanced braces');
        if (ch === '\n') fail('line break inside a value');
        if (ch === '{') depth++;
        else if (ch === '}') depth--;
        i++;
      }
      if (m[1] in fields) fail('field written twice: ' + m[1]);
      fields[m[1]] = text.slice(start, i - 1);
      if (text.startsWith(',\n', i)) { i += 2; continue; }
      if (text.startsWith('\n}\n', i)) { i += 3; break; }
      fail('field end');
    }
    out.push({ type: head[1], key: head[2], fields });
  }
  return out;
}
// names are separated by " and " at brace depth 0, as BibTeX reads them
function bibAuthors(value) {
  const names = [];
  let depth = 0, from = 0;
  for (let i = 0; i < value.length; i++) {
    if (value[i] === '{') depth++;
    else if (value[i] === '}') depth--;
    else if (depth === 0 && value.startsWith(' and ', i)) { names.push(value.slice(from, i)); from = i + 5; i += 4; }
  }
  names.push(value.slice(from));
  return names.map((n) => {
    if (/^\{[^{}]*(\\text[a-z]+\{\}[^{}]*)*\}$/.test(n)) return unbib(n.slice(1, -1));
    return unbib(n.replace(/\{and\}/g, 'and'));
  });
}
// RIS: CR LF lines, TAG + two spaces + hyphen + space, TY first, ER last.
function parseRIS(text) {
  const fail = (msg) => { throw new Error('RIS ' + msg); };
  if (/[^\r]\n/.test(text)) fail('bare line feed');
  if (!text.endsWith('ER  - \r\n')) fail('the file does not end on ER');
  const records = [];
  let cur = null;
  text.split('\r\n').forEach((line, n) => {
    if (line === '') { if (cur) fail('blank line inside a record, line ' + n); return; }
    const m = /^([A-Z][A-Z0-9]) {2}- (.*)$/.exec(line);
    if (!m) fail('malformed line ' + n + ': ' + JSON.stringify(line));
    if (m[1] === 'TY') { if (cur) fail('TY inside a record, line ' + n); cur = { TY: m[2], tags: {} }; return; }
    if (!cur) fail('tag outside a record, line ' + n);
    if (m[1] === 'ER') { if (m[2] !== '') fail('ER with a value'); records.push(cur); cur = null; return; }
    (cur.tags[m[1]] = cur.tags[m[1]] || []).push(m[2]);
  });
  if (cur) fail('record without ER');
  return records;
}
// The CSL item shape cite.js documents, checked against the CSL 1.0.2 schema's
// type list and its name and date variable forms.
const CSL_TYPES = new Set(('article article-journal article-magazine article-newspaper bill book broadcast chapter ' +
  'classic collection dataset document entry entry-dictionary entry-encyclopedia event figure graphic hearing ' +
  'interview legal_case legislation manuscript map motion_picture musical_score pamphlet paper-conference patent ' +
  'performance periodical personal_communication post post-weblog regulation report review review-book software ' +
  'song speech standard thesis treaty webpage').split(' '));
const CSL_STRINGS = new Set(['title', 'container-title', 'collection-title', 'publisher', 'ISBN', 'DOI', 'URL',
  'language', 'keyword', 'abstract', 'note']);
const nonEmpty = (v) => typeof v === 'string' && v.length > 0;
function cslProblems(item) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) return ['not an object'];
  const p = [];
  if (!nonEmpty(item.id)) p.push('id');
  if (!CSL_TYPES.has(item.type)) p.push('type ' + item.type);
  for (const [k, v] of Object.entries(item)) {
    if (k === 'id' || k === 'type') continue;
    if (CSL_STRINGS.has(k)) { if (!nonEmpty(v)) p.push(k + ' is not a non-empty string'); continue; }
    if (k === 'author') {
      const ok = Array.isArray(v) && v.length && v.every((n) => n && typeof n === 'object' && (
        (Object.keys(n).join() === 'literal' && nonEmpty(n.literal)) ||
        (Object.keys(n).every((x) => x === 'family' || x === 'given') && nonEmpty(n.family) &&
          (n.given === undefined || nonEmpty(n.given)))));
      if (!ok) p.push('author');
      continue;
    }
    if (k === 'issued') {
      const dp = v && v['date-parts'];
      const ok = Object.keys(v || {}).join() === 'date-parts' && Array.isArray(dp) && dp.length >= 1 && dp.length <= 2 &&
        dp.every((d) => Array.isArray(d) && d.length >= 1 && d.length <= 3 && d.every(Number.isInteger));
      if (!ok) p.push('issued');
      continue;
    }
    p.push('key outside the documented shape: ' + k);
  }
  return p;
}
function kev(s) {
  const out = {};
  s.split('&').forEach((pair) => {
    const [k, v] = pair.split('=').map(decodeURIComponent);
    (out[k] = out[k] || []).push(v);
  });
  return out;
}

/* ------------------------------------------------------------ fixtures */
const host = (title) => ({ title, type: 'host' });
const series = (title) => ({ title, type: 'series' });
const NASTY = 'Braces {x} back\\slash 100 % R&D #1 $5 a_b ~t ^c "quoted" d’Origène Ἀδαμάντιος';
const fixtures = [
  { ppn: 'ORfix01', title: NASTY, authors: ['Doe, J. {Jr.}', 'Rufinus', 'Society and Church', 'Lévy, Ç\\x'],
    year: 1999, type: 'article', lang: 'fr', publisher: 'P & Q_%', isbn: '978-3-16-148410-0', doi: '10.1000/x{y}\\z',
    sourceIds: [{ source: 'ixtheo-k10plus', id: '1', url: 'https://ixtheo.de/Record/1?a=1&b=%20#x' }], rel: 'core' },
  { ppn: 'ORfix02', title: 'Bare', authors: [], year: null, type: 'book', sourceIds: [], rel: 'marginal' },
  { ppn: 'ORfix03', title: 'Origenes', authors: ['Hefele, Karl Joseph'], year: 1851, type: 'chapter',
    sourceIds: [{ source: 'ixtheo-k10plus', id: '3', url: 'https://ixtheo.de/Record/3' }], rel: 'partial' },
  { ppn: 'ORfix04', title: 'Monograph', authors: ['Crouzel, Henri'], year: 1962, type: 'book', publisher: 'Aubier',
    sourceIds: [{ source: 'sudoc', id: '4', url: 'https://www.sudoc.fr/4' }], rel: 'none' },
  { ppn: 'ORfix05', title: 'Hosted book', authors: ['Camplani, Alberto'], year: 2009, type: 'book',
    sourceIds: [{ source: 'k10plus', id: '5' }], url: 'https://opac.k10plus.de/5', src: 'k10plus', rel: 'core' },
  { ppn: 'ORfix06', title: 'A review', authors: ['Doe, Jane'], year: 2001, type: 'review',
    sourceIds: [{ source: 'ixtheo-k10plus', id: '6', url: 'https://ixtheo.de/Record/6' }], rel: 'core' },
  { ppn: 'ORfix07', title: 'Thesis typed oddly', authors: [], year: 2010, type: 'thesis', sourceIds: [], rel: 'core' },
  { ppn: 'ORfix08', title: 'Adamantius', authors: [], year: null, type: 'other', sourceIds: [], rel: 'core' },
];
const containers = {
  ORfix01: host('Revue {des} études & notes'), ORfix03: host('Kirchenlexikon'), ORfix04: series('Théologie 34'),
  ORfix05: host('Adamantius (Testo stampato)'), ORfix06: host('Journal of Reviews')
};
const byPpn = (list, ppn) => list[fixtures.findIndex((f) => f.ppn === ppn)];
// the record id the page's links use (explorer.js recordKey): the first source
// id when it has a number, the Origenality ID otherwise
const idOf = (p) => {
  const s = (p.sourceIds || [])[0];
  return s && s.source && s.id != null && s.id !== '' ? s.source + ':' + s.id : p.ppn;
};

group('escaping', () => {
  const e = C.entryFromRecord(fixtures[0], { containers, sourceName: () => 'IxTheo' });
  e.key = 'doe1999braces';
  const bib = C.toBibTeX([e], { header: ['Origenality, a view @ home', 'second line'] });
  const [b] = parseBib(bib);
  check('a header line never opens an entry', !/^%.*@/m.test(bib), bib.split('\n').slice(0, 3));
  check('the title reads back after escaping', unbib(b.fields.title) === oneLine(NASTY), unbib(b.fields.title));
  check('accents and Greek stay as written, UTF-8', b.fields.title.includes('d’Origène Ἀδαμάντιος')
    && Buffer.from(bib, 'utf8').toString('utf8') === bib);
  check('LaTeX specials are escaped', /\\textbraceleft\{\}x\\textbraceright\{\}/.test(b.fields.title) && /100 \\% R\\&D \\#1 \\\$5 a\\_b \\textasciitilde\{\}t \\textasciicircum\{\}c/.test(b.fields.title)
    && /back\\textbackslash\{\}slash/.test(b.fields.title), b.fields.title);
  check('quotes are left as they are', b.fields.title.includes('"quoted"'));
  check('the journal reads back', unbib(b.fields.journal) === 'Revue {des} études & notes', b.fields.journal);
  check('the publisher reads back', unbib(b.fields.publisher) === 'P & Q_%');
  eq('authors read back, a single form braced whole, "and" protected', bibAuthors(b.fields.author),
    ['Doe, J. {Jr.}', 'Rufinus', 'Society and Church', 'Lévy, Ç\\x']);
  check('a name without a comma is one braced group', b.fields.author.includes('{Rufinus}') && b.fields.author.includes('{Society and Church}'), b.fields.author);
  check('url is raw, braces and backslash percent-encoded', b.fields.url === 'https://ixtheo.de/Record/1?a=1&b=%20#x'
    && b.fields.doi === '10.1000/x%7By%7D%5Cz', [b.fields.url, b.fields.doi]);
  const ris = parseRIS(C.toRIS([e]))[0];
  check('RIS keeps the text unescaped on one line', ris.tags.TI[0] === oneLine(NASTY) && ris.tags.AU.length === 4);
  const csl = JSON.parse(C.toCSL([e]))[0];
  check('CSL keeps the text unescaped', csl.title === oneLine(NASTY) && csl.DOI === '10.1000/x{y}\\z');
  eq('CSL names: family and given, or a literal', csl.author, [{ family: 'Doe', given: 'J. {Jr.}' }, { literal: 'Rufinus' },
    { literal: 'Society and Church' }, { family: 'Lévy', given: 'Ç\\x' }]);
  const tabbed = C.entryFromRecord({ ppn: 'x', title: 'a\tb\nc\r\n  d\u2028e', authors: [], type: 'book', sourceIds: [] }, {});
  tabbed.key = 't';
  check('a run of control characters becomes one space, spaces stay', parseBib(C.toBibTeX([tabbed]))[0].fields.title === 'a b c   d e'
    && parseRIS(C.toRIS([tabbed]))[0].tags.TI[0] === 'a b c   d e', parseBib(C.toBibTeX([tabbed]))[0].fields.title);
  const loc = C.entryFromRecord({ ppn: 'x', title: 'T', authors: [], type: 'book',
    sourceIds: [{ source: 'loc', id: 'a  21000197', url: 'https://lccn.loc.gov/a%20%2021000197' }] }, { sourceName: () => 'Library of Congress' });
  loc.key = 'l';
  check('a record id keeps its inner spaces in the note', JSON.parse(C.toCSL([loc]))[0].note.startsWith('Origenality loc:a  21000197, '));
});

function eq(name, got, want) {
  const a = JSON.stringify(got), b = JSON.stringify(want);
  check(name, a === b, a === b ? undefined : { got, want });
}

group('types and fields', () => {
  const entries = fixtures.map((f) => C.entryFromRecord(f, { containers, sourceName: (k) => ({ 'ixtheo-k10plus': 'IxTheo', sudoc: 'Sudoc', k10plus: 'K10plus' })[k] || k }));
  C.assignKeys(entries);
  const bib = parseBib(C.toBibTeX(entries));
  const ris = parseRIS(C.toRIS(entries));
  const csl = JSON.parse(C.toCSL(entries));
  eq('BibTeX types from the record type', bib.map((b) => b.type), ['article', 'book', 'incollection', 'book', 'book', 'article', 'misc', 'misc']);
  eq('RIS types from the record type', ris.map((r) => r.TY), ['JOUR', 'BOOK', 'CHAP', 'BOOK', 'BOOK', 'JOUR', 'GEN', 'GEN']);
  eq('CSL types from the record type', csl.map((r) => r.type), ['article-journal', 'book', 'chapter', 'book', 'book', 'article-journal', 'document', 'document']);
  const bare = byPpn(bib, 'ORfix02');
  eq('a record with a title only writes title, keyword and note', Object.keys(bare.fields), ['title', 'keywords', 'note']);
  eq('RIS: the same, and nothing else', Object.keys(byPpn(ris, 'ORfix02').tags), ['ID', 'TI', 'KW', 'N1']);
  eq('CSL: the same, and nothing else', Object.keys(byPpn(csl, 'ORfix02')), ['id', 'type', 'title', 'keyword', 'note']);
  const chap = byPpn(bib, 'ORfix03');
  check('a chapter with a host writes booktitle', chap.fields.booktitle === 'Kirchenlexikon' && !('journal' in chap.fields));
  check('RIS chapter host is T2, CSL container-title', byPpn(ris, 'ORfix03').tags.T2[0] === 'Kirchenlexikon' && byPpn(csl, 'ORfix03')['container-title'] === 'Kirchenlexikon');
  const mono = byPpn(bib, 'ORfix04');
  check('a book in a series writes series', unbib(mono.fields.series) === 'Théologie 34' && byPpn(ris, 'ORfix04').tags.T3[0] === 'Théologie 34'
    && byPpn(csl, 'ORfix04')['collection-title'] === 'Théologie 34');
  check('a record held aside is kept and marked', mono.fields.keywords === 'origenality:held-aside');
  check('a record mentioned only is kept and marked', bare.fields.keywords === 'origenality:mentioned-only' && byPpn(csl, 'ORfix02').keyword === 'origenality:mentioned-only');
  const hosted = byPpn(bib, 'ORfix05');
  check('a book with a host says so in the note, in no other field', /^In Adamantius \(Testo stampato\)\. /.test(hosted.fields.note)
    && !('series' in hosted.fields) && !('booktitle' in hosted.fields) && !('journal' in hosted.fields), hosted.fields);
  check('without a URL on the source id, the record URL is used', hosted.fields.url === 'https://opac.k10plus.de/5'
    && hosted.fields.note.includes('Origenality k10plus:5, K10plus record https://opac.k10plus.de/5.'), hosted.fields.note);
  const rev = byPpn(bib, 'ORfix06');
  check('a review is an article whose note opens "Review."', rev.type === 'article' && rev.fields.journal === 'Journal of Reviews'
    && /^Review\. /.test(rev.fields.note) && /^Review\. /.test(byPpn(ris, 'ORfix06').tags.N1[0]));
  const art = byPpn(bib, 'ORfix01');
  check('every note names the record and says what the data lacks', unbib(art.fields.note) ===
    'Origenality ixtheo-k10plus:1, IxTheo record https://ixtheo.de/Record/1?a=1&b=%20#x. Volume, issue and pages are not carried by Origenality.', unbib(art.fields.note));
  check('no volume, number or pages field, in any entry', bib.every((b) => !Object.keys(b.fields).some((k) => /volume|number|pages|issue/.test(k)))
    && ris.every((r) => !['VL', 'IS', 'SP', 'EP'].some((t) => t in r.tags)));
  csl.forEach((it) => eq('CSL item ' + it.id + ' has the documented shape', cslProblems(it), []));
  // abstracts: only when asked, and with their credit
  const plain = C.entryFromRecord(fixtures[2], { containers });
  const withAb = C.entryFromRecord(fixtures[2], { containers, abstract: { text: 'Ein Text.', credit: 'Abstract from Index Theologicus (IxTheo / K10plus)', url: 'https://ixtheo.de/Record/3' } });
  plain.key = 'a'; withAb.key = 'b';
  check('no abstract unless asked', !/abstract/i.test(C.toBibTeX([plain])) && !/^AB/m.test(C.toRIS([plain])) && !('abstract' in JSON.parse(C.toCSL([plain]))[0]));
  const ab = parseBib(C.toBibTeX([withAb]))[0];
  check('an abstract carries the database that wrote it and the link to its record', ab.fields.abstract === 'Ein Text.'
    && unbib(ab.fields.note).endsWith(' Abstract from Index Theologicus (IxTheo / K10plus), https://ixtheo.de/Record/3.'), ab.fields.note);
  const risAb = parseRIS(C.toRIS([withAb]))[0];
  check('RIS: AB and the credit in N1', risAb.tags.AB[0] === 'Ein Text.' && risAb.tags.N1[0].includes('Abstract from Index Theologicus'));
  // COinS
  const coinsChap = kev(C.toCOinS(entries[2]));
  check('COinS of a chapter: bookitem, atitle and btitle', coinsChap.ctx_ver[0] === 'Z39.88-2004' && coinsChap['rft.genre'][0] === 'bookitem'
    && coinsChap['rft.btitle'][0] === 'Kirchenlexikon' && coinsChap['rft.au'][0] === 'Hefele, Karl Joseph', coinsChap);
  const coinsArt = kev(C.toCOinS(entries[0]));
  check('COinS of an article: journal format, jtitle, every author, DOI', coinsArt['rft_val_fmt'][0] === 'info:ofi/fmt:kev:mtx:journal'
    && coinsArt['rft.jtitle'][0] === 'Revue {des} études & notes' && coinsArt['rft.au'].length === 4
    && coinsArt.rft_id.includes('info:doi/10.1000/x{y}\\z'), coinsArt);
  check('COinS writes no field the record lacks', Object.keys(kev(C.toCOinS(entries[1]))).sort().join() === 'ctx_ver,rft.btitle,rft.genre,rft_val_fmt');
  check('file names are plain and carry the build', C.fileName('“Contre Celse”', '20260913-2490', 'bibtex') === 'origenality-contre-celse-20260913-2490.bib'
    && C.fileName('record ixtheo-k10plus:16382584X', '20260913-2490', 'csl') === 'origenality-record-ixtheo-k10plus-16382584x-20260913-2490.json');
});

group('keys', () => {
  const twin = (ppn, id) => ({ ppn, title: 'De principiis', authors: ['Görgemanns, Herwig'], year: 1976, type: 'book',
    sourceIds: [{ source: 'dnb', id, url: 'https://d-nb.info/' + id }], rel: 'core' });
  const a = [twin('ORa', '2'), twin('ORb', '1'), twin('ORc', '3')].map((r) => C.entryFromRecord(r, {}));
  C.assignKeys(a);
  eq('twins get a, b, c in the order of their record id', a.map((e) => e.key), ['gorgemanns1976principiisb', 'gorgemanns1976principiisa', 'gorgemanns1976principiisc']);
  const b = [twin('ORc', '3'), twin('ORa', '2'), twin('ORb', '1')].map((r) => C.entryFromRecord(r, {}));
  C.assignKeys(b);
  const sorted = (list) => list.map((e) => e.recordId + '=' + e.key).sort();
  eq('the suffix does not depend on the order of the list', sorted(b), sorted(a));
  const dup = a.map((e) => Object.assign({}, e, { key: 'same' }));
  const keys = parseBib(C.toBibTeX(dup)).map((x) => x.key);
  check('a file never holds a key twice, whatever keys it is given', new Set(keys).size === keys.length, keys);
  const noAuthor = C.entryFromRecord({ ppn: 'x', title: 'The Hexapla and its readers', authors: [], year: null, type: 'book', sourceIds: [] }, {});
  check('without author or year the key is the first title word, nd, the second', C.baseKey(noAuthor) === 'hexaplandits', C.baseKey(noAuthor));
});

/* ------------------------------------------------------------ the build */
group('the build', () => {
  const graph = JSON.parse(fs.readFileSync(path.join(DATA, 'graph.json'), 'utf8'));
  const sem = JSON.parse(fs.readFileSync(path.join(PAGES, 'assets/semantic.json'), 'utf8'));
  const abs = JSON.parse(fs.readFileSync(path.join(DATA, 'abstracts.json'), 'utf8'));
  const corpusText = fs.readFileSync(path.join(DATA, 'site-merged/corpus.jsonl'), 'utf8');
  const rows = corpusText.split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l));
  const IDX = CORE.buildIndex(graph, sem, abs);
  const cmap = C.containersFromCorpus(corpusText);
  const withContainer = rows.filter((r) => r.container && r.container.title);
  check('every container of the record file is read', Object.keys(cmap).length === withContainer.length, { read: Object.keys(cmap).length, rows: withContainer.length });
  const rowById = Object.fromEntries(rows.map((r) => [r.origenality_id, r]));
  check('the record file covers every record of the graph', IDX.records.every((p) => rowById[p.ppn]));

  const entries = IDX.records.map((p) => C.entryFromRecord(p, { containers: cmap, sourceName: (k) => k }));
  C.assignKeys(entries);
  const keyOf = Object.fromEntries(entries.map((e) => [e.recordId, e.key]));
  check('one key per record over the build', new Set(entries.map((e) => e.key)).size === entries.length && Object.keys(keyOf).length === entries.length);
  check('keys are plain letters and digits', entries.every((e) => /^[a-z0-9_]+$/.test(e.key)), entries.filter((e) => !/^[a-z0-9_]+$/.test(e.key)).slice(0, 3).map((e) => e.key));
  const shuffled = IDX.records.slice().reverse().map((p) => C.entryFromRecord(p, { containers: cmap }));
  C.assignKeys(shuffled);
  check('keys are the same whatever the order of the build', shuffled.every((e) => keyOf[e.recordId] === e.key));

  const bibText = C.toBibTeX(entries, { header: ['Origenality, the whole corpus'] });
  const bib = parseBib(bibText), ris = parseRIS(C.toRIS(entries)), csl = JSON.parse(C.toCSL(entries));
  check('every record is one entry in each format', bib.length === entries.length && ris.length === entries.length && csl.length === entries.length,
    { bib: bib.length, ris: ris.length, csl: csl.length, records: entries.length });
  check('BibTeX keys are unique', new Set(bib.map((b) => b.key)).size === bib.length);
  check('RIS: every record ends on ER', (C.toRIS(entries).match(/\r\nER {2}- \r\n/g) || []).length === entries.length);
  const cslBad = csl.map((it) => [it.id, cslProblems(it)]).filter((x) => x[1].length);
  check('CSL-JSON: every item has the documented shape', cslBad.length === 0, cslBad.slice(0, 3));

  // each entry, read back, is its record: every field there is data for, and no other
  const wrong = [];
  IDX.records.forEach((p, i) => {
    const b = bib[i].fields, r = ris[i].tags, j = csl[i], row = rowById[p.ppn];
    const c = cmap[p.ppn] || null;
    const role = c ? (c.type === 'series' ? 'series' : (['article', 'review', 'chapter'].includes(p.type) ? 'host' : 'note')) : null;
    const expect = {
      author: p.authors.length > 0, title: !!p.title, year: p.year != null, publisher: !!p.publisher, isbn: !!p.isbn,
      doi: !!p.doi, url: !!((p.sourceIds || []).some((s) => s.url) || p.url), language: !!p.lang,
      keywords: !p.dens, journal: role === 'host' && p.type !== 'chapter', booktitle: role === 'host' && p.type === 'chapter',
      series: role === 'series', note: true
    };
    const emitted = new Set(Object.keys(b));
    Object.entries(expect).forEach(([k, want]) => { if (emitted.has(k) !== want) wrong.push([p.ppn, 'bibtex ' + k, want]); });
    emitted.forEach((k) => { if (!(k in expect)) wrong.push([p.ppn, 'bibtex unexpected ' + k]); });
    if (b.title !== undefined && unbib(b.title) !== oneLine(p.title)) wrong.push([p.ppn, 'title']);
    if (b.author !== undefined && JSON.stringify(bibAuthors(b.author)) !== JSON.stringify(p.authors.map(oneLine))) wrong.push([p.ppn, 'author', b.author]);
    if (b.year !== undefined && b.year !== String(p.year)) wrong.push([p.ppn, 'year']);
    if (b.publisher !== undefined && unbib(b.publisher) !== oneLine(p.publisher)) wrong.push([p.ppn, 'publisher']);
    if (b.isbn !== undefined && unbib(b.isbn) !== oneLine(p.isbn)) wrong.push([p.ppn, 'isbn']);
    if (b.doi !== undefined && b.doi !== oneLine(p.doi)) wrong.push([p.ppn, 'doi']);
    const cTitle = b.journal || b.booktitle || b.series;
    if (cTitle !== undefined && unbib(cTitle) !== oneLine(c.title)) wrong.push([p.ppn, 'container']);
    if (role === 'host' && row.container.title !== c.title) wrong.push([p.ppn, 'container is not the record file\'s']);
    if (!b.note.includes('Origenality ' + idOf(p))) wrong.push([p.ppn, 'note id']);
    // RIS and CSL say the same
    if ((r.AU || []).length !== p.authors.length || (r.TI || [])[0] !== oneLine(p.title)) wrong.push([p.ppn, 'ris']);
    if ((r.PY || [undefined])[0] !== (p.year != null ? String(p.year) : undefined)) wrong.push([p.ppn, 'ris year']);
    if (!!j.ISBN !== !!p.isbn || !!j.DOI !== !!p.doi || !!j.publisher !== !!p.publisher || !!j.issued !== (p.year != null)) wrong.push([p.ppn, 'csl']);
  });
  check('each entry, read back, holds its record and nothing the record lacks', wrong.length === 0, { count: wrong.length, first: wrong.slice(0, 5) });
  check('no volume, issue or pages anywhere in the build', !/^ {2}(volume|number|pages|issue) = /m.test(bibText)
    && !/\r\n(VL|IS|SP|EP) {2}- /.test(C.toRIS(entries)));

  const chapters = IDX.records.filter((p) => p.type === 'chapter' && cmap[p.ppn]);
  const known = chapters[0];
  const kb = bib[IDX.records.indexOf(known)];
  check('a chapter with a known book title exports it as booktitle', !!known && kb.type === 'incollection' && unbib(kb.fields.booktitle) === oneLine(cmap[known.ppn].title),
    known && { ppn: known.ppn, fields: kb.fields });
  check('every chapter the record file places in a book exports its booktitle',
    bib.filter((x) => x.type === 'incollection' && x.fields.booktitle).length === chapters.filter((p) => cmap[p.ppn].type !== 'series').length);

  // a view: work:cels, as the panel lists it
  const r = CORE.search(IDX, 'work:cels');
  const view = r.order.map((i) => IDX.records[i]);
  const viewEntries = view.map((p) => Object.assign(C.entryFromRecord(p, { containers: cmap }), { key: keyOf[idOf(p)] }));
  const vb = parseBib(C.toBibTeX(viewEntries));
  check('work:cels exports exactly the records the view lists', vb.length === r.matched.size && vb.length > 0, { exported: vb.length, listed: r.matched.size });
  check('a record keeps its whole-build key in a view', vb.every((x, i) => x.key === keyOf[viewEntries[i].recordId]));
  const mentioned = view.filter((p) => !p.dens);
  check('records mentioned only stay in the export, marked', mentioned.length === 0 ||
    vb.filter((x) => /origenality:(mentioned-only|held-aside)/.test(x.fields.keywords || '')).length === mentioned.length);

  // abstracts, credited as the page credits them
  const withAb = IDX.records.filter((p) => p.ab && p.ab.t && p.ab.k !== 'generated' && p.ab.u).slice(0, 25);
  const abBib = parseBib(C.toBibTeX(withAb.map((p) => {
    const label = (abs.sources[p.ab.s] || {}).label || p.ab.s;
    return Object.assign(C.entryFromRecord(p, { containers: cmap, abstract: { text: p.ab.t, credit: 'Abstract from ' + label, url: p.ab.u } }), { key: '' });
  })));
  check('an exported abstract is the page abstract with its credit and link', withAb.length > 0 && abBib.every((x, i) => {
    const p = withAb[i];
    const label = (abs.sources[p.ab.s] || {}).label || p.ab.s;
    return unbib(x.fields.abstract) === oneLine(p.ab.t) && unbib(x.fields.note).endsWith('Abstract from ' + oneLine(label) + ', ' + p.ab.u + '.');
  }));
  // COinS on the real records
  const coinsBad = entries.filter((e) => {
    const k = kev(C.toCOinS(e));
    return k.ctx_ver[0] !== 'Z39.88-2004' || (e.authors.length && (k['rft.au'] || k['rft.creator'] || []).length !== e.authors.length);
  });
  check('every record has a readable COinS with all its authors', coinsBad.length === 0, coinsBad.slice(0, 2).map((e) => e.recordId));
});

/* ------------------------------------------------------------ cite.json */
// The light file the Explorer's export reads (site/build-c/tools/build_cite_data.py):
// what cite.js takes from it is what it takes from the record file.
group('cite.json', () => {
  const file = path.join(DATA, 'cite.json');
  check('cite.json is in the data layer', fs.existsSync(file));
  const json = JSON.parse(fs.readFileSync(file, 'utf8'));
  const corpusText = fs.readFileSync(path.join(DATA, 'site-merged/corpus.jsonl'), 'utf8');
  const rows = corpusText.split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l));
  check('cite.json counts the records of the record file', json.records === rows.length, { file: json.records, corpus: rows.length });
  const d = C.citeData(json);
  const sorted = (m) => JSON.stringify(Object.keys(m).sort().map((k) => [k, m[k]]));
  check('cite.json holds the containers of the record file, with their types', sorted(d.containers) === sorted(C.containersFromCorpus(corpusText)));
  const want = {};
  rows.forEach((r) => {
    const f = {};
    [['publisher', 'publisher'], ['doi', 'doi'], ['isbn', 'isbn']].forEach(([k, field]) => {
      if (typeof r[field] === 'string' && r[field].trim()) f[k] = r[field];
    });
    if (Object.keys(f).length) want[r.origenality_id] = f;
  });
  check('cite.json holds the publisher, DOI and ISBN of the record file, and nothing else', sorted(d.fields) === sorted(want));
  const graph = JSON.parse(fs.readFileSync(path.join(DATA, 'graph.json'), 'utf8'));
  const ids = new Set(graph.nodes.filter((n) => n.k === 'pub').map((n) => n.ppn));
  const stray = Object.keys(json.byPpn).filter((id) => !ids.has(id));
  check('cite.json is keyed by the Origenality IDs of graph.json', stray.length === 0, stray.slice(0, 3));
  check('a record cite.json does not name has no container once the file is read',
    C.entryFromRecord({ ppn: 'ORnone', title: 't', container: 'Shared' }, { containers: d.containers }).container === null);
  const e = C.entryFromRecord({ ppn: 'ORx', title: 't', publisher: 'Graph press', isbn: '111', doi: '' },
    { containers: {}, fields: { ORx: { publisher: 'File press', doi: '10.1/x' } } });
  check('a field from cite.json is written, and the record fills what the file lacks',
    e.publisher === 'File press' && e.doi === '10.1/x' && e.isbn === '111', e);
  let refused = 0;
  [null, {}, { byPpn: {} }, { schema: 'origenality-cite/3', byPpn: {} }].forEach((bad) => {
    try { C.citeData(bad); } catch (err) { refused++; }
  });
  check('a file of another shape is refused, so the page falls back to the record file', refused === 4, refused);
  check('the version 1 and version 2 files are both read', !!C.citeData({ schema: 'origenality-cite/1', byPpn: {} })
    && !!C.citeData({ schema: 'origenality-cite/2', byPpn: { ORx: { c: 'J', s: ['A'], in: 'J.' } } }).containers.ORx);
});

console.log((failures ? 'FAILED ' : 'ok ') + passes + ' passed, ' + failures + ' failed');
process.exit(failures ? 1 : 0);
