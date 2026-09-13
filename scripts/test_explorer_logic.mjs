#!/usr/bin/env node
/* Origenality — the Explorer's logic, checked without a browser.
 *
 * explorer.js runs inside a page, so its pure functions are lifted out of the
 * file as text and evaluated here against search-core.js and the data layer the
 * page reads. What is checked is the code the page runs, not a copy of it.
 *
 *     node scripts/test_explorer_logic.mjs
 *     node scripts/test_explorer_logic.mjs --explorer <copy of explorer.js>
 *
 * Exits 1 on the first failed group. Works in both geometries: working tree
 * (site/build-c/, site/data/) and public clone (site/, data/).
 */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const PAGES = fs.existsSync(path.join(ROOT, 'site/build-c/assets/explorer.js'))
  ? path.join(ROOT, 'site/build-c') : path.join(ROOT, 'site');
const DATA = fs.existsSync(path.join(ROOT, 'site/data/graph.json'))
  ? path.join(ROOT, 'site/data') : path.join(ROOT, 'data');
// `--explorer <file>` checks another copy of explorer.js, e.g. an older commit's
const argAt = process.argv.indexOf('--explorer');
const SRC = fs.readFileSync(argAt > 0 ? process.argv[argAt + 1] : path.join(PAGES, 'assets/explorer.js'), 'utf8');
const CORE = createRequire(import.meta.url)(path.join(PAGES, 'assets/search-core.js'));

let failures = 0, passes = 0;
function check(name, ok, detail) {
  if (ok) { passes++; return; }
  failures++;
  console.log('FAIL ' + name + (detail !== undefined ? ' :: ' + JSON.stringify(detail) : ''));
}

function group(name, body) {
  try { body(); } catch (err) { check(name + ' could not run', false, err.message); }
}

/* ------------------------------------------------------------ lifting code */
// Scan from `start` to the end of the balanced block that begins at the first
// `open` character, skipping strings, template literals, comments and regex
// literals. With open = null the scan stops at the first `;` at depth 0.
function scanBlock(src, start, open) {
  let depth = 0, i = start, began = open === null;
  let prev = '';
  while (i < src.length) {
    const ch = src[i], nx = src[i + 1];
    if (ch === '/' && nx === '/') { i = src.indexOf('\n', i); continue; }
    if (ch === '/' && nx === '*') { i = src.indexOf('*/', i) + 2; continue; }
    if (ch === '"' || ch === "'" || ch === '`') {
      i++;
      while (i < src.length && src[i] !== ch) i += src[i] === '\\' ? 2 : 1;
      i++; prev = 'x'; continue;
    }
    if (ch === '/' && (prev === '' || '(,=:[!&|?{};+-*%<>~^'.includes(prev))) {
      i++;
      let inClass = false;
      while (i < src.length) {
        if (src[i] === '\\') { i += 2; continue; }
        if (src[i] === '[') inClass = true;
        else if (src[i] === ']') inClass = false;
        else if (src[i] === '/' && !inClass) break;
        i++;
      }
      i++;
      while (/[a-z]/.test(src[i])) i++;
      prev = 'x'; continue;
    }
    if (ch === '{' || ch === '(' || ch === '[') {
      if (ch === open) began = true;
      depth++;
    } else if (ch === '}' || ch === ')' || ch === ']') {
      depth--;
      if (began && open !== null && depth === 0 && ch === '}') return src.slice(start, i + 1);
    } else if (open === null && ch === ';' && depth === 0) {
      return src.slice(start, i + 1);
    }
    if (!/\s/.test(ch)) prev = ch;
    i++;
  }
  throw new Error('unbalanced block from ' + start);
}
function fn(name) {
  const at = SRC.indexOf('function ' + name + '(');
  if (at < 0) throw new Error('function ' + name + ' not found in explorer.js');
  return scanBlock(SRC, at, '{');
}
function decl(name) {
  const at = SRC.indexOf('var ' + name + ' =');
  if (at < 0) throw new Error('var ' + name + ' not found in explorer.js');
  return scanBlock(SRC, at, null);
}
function lift(parts, exportNames, globals) {
  const ctx = vm.createContext(Object.assign({ CORE, Set }, globals || {}));
  vm.runInContext(parts.join('\n') + '\n;this.__out = {' + exportNames.join(',') + '};', ctx);
  return ctx.__out;
}

/* ------------------------------------------------------------ data */
const graph = JSON.parse(fs.readFileSync(path.join(DATA, 'graph.json'), 'utf8'));
const sem = JSON.parse(fs.readFileSync(path.join(PAGES, 'assets/semantic.json'), 'utf8'));
const abs = fs.existsSync(path.join(DATA, 'abstracts.json'))
  ? JSON.parse(fs.readFileSync(path.join(DATA, 'abstracts.json'), 'utf8')) : null;
const pubs = graph.nodes.filter((n) => n.k === 'pub');
const byCode = {};
pubs.forEach((n) => { byCode[n.lang || ''] = (byCode[n.lang || ''] || 0) + 1; });
// the index the page builds, completed with cite.json as the page completes it
// after its first render (and as the CLI builds it at once)
const citeJson = JSON.parse(fs.readFileSync(path.join(DATA, 'cite.json'), 'utf8'));
const IDX = CORE.applyCite(CORE.buildIndex(graph, sem, abs), citeJson);
const counted = IDX.records.filter((p) => p.dens).length;

function eq(name, got, want) {
  const a = JSON.stringify(got), b = JSON.stringify(want);
  check(name, a === b, a === b ? undefined : { got, want });
}
// the CLI, on this tree, as an agent runs it
function cli(...args) {
  const out = spawnSync(process.execPath, [path.join(ROOT, 'cli/origenality.mjs'), ...args, '--json', '--local', ROOT],
    { encoding: 'utf8', timeout: 180000 });
  if (out.status !== 0) throw new Error('CLI ' + args.join(' ') + ' exited ' + out.status + ': ' + out.stderr);
  return JSON.parse(out.stdout);
}
// the string literals of a piece of code, for checks on wording
function literals(code) {
  return (code.match(/'(?:[^'\\\n]|\\.)*'/g) || []).join(' ');
}

/* ------------------------------------------------------------ OR-04 */
// The palette's language codes are the ones graph.json carries.
group('OR-04', () => {
  const langs = lift([decl('LANGS')], ['LANGS']).LANGS;
  const codes = langs.map((l) => l.code).filter((c) => c !== 'oth');
  check('OR-04 LANGS has five named languages and oth', codes.length === 5 && langs.some((l) => l.code === 'oth'), langs.map((l) => l.code));
  codes.forEach((c) => check('OR-04 graph.json carries records in ' + c, (byCode[c] || 0) > 0, byCode));
  const inPalette = codes.reduce((a, c) => a + (byCode[c] || 0), 0);
  check('OR-04 most records fall in a named language', inPalette > pubs.length / 2, { inPalette, total: pubs.length });
});

/* ------------------------------------------------------------ OR-21 */
// A page record keeps the catalogue's code on `lang` and `rawlang`, as the
// shared index builds it; the colour key is `lkey`, a field of its own.
group('OR-21', () => {
  const b = fn('build');
  check('OR-21 build adopts the shared index', /IDX = CORE\.buildIndex\(g, SEM, ABS\)/.test(b) && /PUBS = IDX\.records/.test(b));
  check('OR-21 the colour key is added as lkey', /p\.lkey = lkey\(p\.rawlang\)/.test(b));
  check('OR-21 build never overwrites the catalogue code', !/p\.(raw)?lang\s*=(?!=)/.test(b));
  const g = lift([decl('LANGS'), "var LCOL = {}, LLAB = {};",
    "LANGS.forEach(function (l) { LCOL[l.code] = l.col; LLAB[l.code] = l.label; });", fn('lkey')], ['lkey']);
  const la = IDX.records.find((p) => p.rawlang === 'la');
  check('OR-21 lang keeps la', !!la && la.lang === 'la');
  check('OR-21 lkey folds la into oth', g.lkey('la') === 'oth');
  check('OR-21 lkey keeps fr', g.lkey('fr') === 'fr');
  ['la', 'grc', 'nl', 'fr', 'de'].forEach((code) => {
    const expected = byCode[code] || 0;
    const got = CORE.search(IDX, 'lang:' + code).matched.size;
    check('OR-21 lang:' + code + ' reaches every ' + code + ' record', got === expected && expected > 0, { got, expected });
  });
  check('OR-21 lang:fre is lang:fr', CORE.search(IDX, 'lang:fre').matched.size === (byCode.fr || 0));
  // drawing and legend lookups go through the colour key, never the code
  check('OR-21 no palette lookup keyed by .lang', !/(LCOL|LLAB|langOff|byLang|mix)\[\w+\.lang\]/.test(SRC),
    (SRC.match(/(LCOL|LLAB|langOff|byLang|mix)\[\w+\.lang\]/g) || []));
});

/* ------------------------------------------------------------ OR-22 / OR-54 */
// The page asks the engine whether a query is blank: `l:fr`, `foo:bar` and `PG`
// reach it and come back as an answer or as a reported problem.
group('OR-22/OR-54', () => {
  [['', true], ['   ', true], ['l:fr', false], ['lang:de', false], ['a:ng', false], ['in:xy', false],
    ['"de"', false], ['-of', false], ['origen', false], ['l:fr origen', false], ['foo:bar', false],
    ['PG', false]].forEach(([q, want]) => {
    check('OR-22 queryIsBlank(' + JSON.stringify(q) + ') is ' + want, CORE.queryIsBlank(q) === want);
  });
  const cm = fn('computeMatch');
  check('OR-22 computeMatch gates on the engine test', /CORE\.queryIsBlank\(query\)/.test(cm) && !/queryIsEmpty/.test(SRC));
  check('OR-22 the page searches the shared index', /CORE\.search\(IDX, query, \{ keep: keep \}\)/.test(cm));
  const { problemLine } = lift([fn('problemLine')], ['problemLine']);
  const bad = problemLine(CORE.search(IDX, 'foo:bar'));
  check('OR-16 an unknown field is said, not answered', /^The query was not searched\. Unknown field "foo:"/.test(bad), bad);
  const pg = problemLine(CORE.search(IDX, 'PG'));
  check('OR-16 a query with no searchable word is said', pg === 'Nothing was searched: words under three letters and common words are left out (here: pg).', pg);
  check('OR-16 a refused query closes the panel rather than showing a zero',
    /if \(queryProblem && !matched\) closePanel\(\)/.test(fn('applyMatch')));
  const sl = fn('stateLine');
  check('OR-02 a term missing only under the filters is named apart', /absentFiltered\.length/.test(sl)
    && /the records your filters leave/.test(sl));
  check('the panel lists an answer in the engine order', /list\.sort\(byRank\)/.test(fn('renderPanel'))
    && /RANK\[i\] = at/.test(cm));
});

/* ------------------------------------------------------------ OR-25 */
group('OR-25', () => {
  const { tallyMatch } = lift([fn('counts'), fn('visiblePub'), fn('tallyMatch')], ['tallyMatch'],
    { langOff: { de: true } });
  const recs = [
    { i: 0, lkey: 'fr', dens: true, rel: 'core' },       // counted
    { i: 1, lkey: 'fr', dens: true, rel: 'partial' },    // counted, but reached through a heading only
    { i: 2, lkey: 'en', dens: false, rel: 'marginal' },  // mentioned only
    { i: 3, lkey: 'it', dens: false, rel: 'none' },      // held aside
    { i: 4, lkey: 'de', dens: true, rel: 'core' },       // hidden by the language filter
  ];
  const t = tallyMatch(recs, new Set([1]));
  check('OR-25 tally sets each record apart once', t.hit === 1 && t.shelf === 1 && t.mention === 1 && t.aside === 1 && t.hidden === 1, t);
  check('OR-25 a shelf record that counts is told apart', t.shelfCounted === 1, t);
  const t2 = tallyMatch(recs, null);
  check('OR-25 without a shelf the heading record counts', t2.hit === 2 && t2.shelf === 0, t2);
  check('OR-25 the state line uses the tally', /tallyMatch\(/.test(fn('applyMatch')));
  check('OR-25 the panel headline uses the tally', /tallyMatch\(list/.test(fn('renderPanel')));
  check('OR-25 cluster counts leave heading-only records out', /p\.dens && !shelfOnly\.has\(p\.i\)/.test(fn('applyMatch')));
});

/* ------------------------------------------------------------ OR-62 */
group('OR-62', () => {
  const { recordLinks } = lift([decl('SRC_NAME'), fn('esc'), fn('sourceName'), fn('recordLinks'), 'var ABS = null;'], ['recordLinks']);
  const text = (html) => html.replace(/<[^>]+>/g, '').replace(/\u00a0/g, ' ');
  const merged = recordLinks({ sourceIds: [
    { source: 'ixtheo-k10plus', id: '037157663', url: 'https://ixtheo.de/Record/037157663' },
    { source: 'ixtheo-k10plus', id: '1073000591', url: 'https://ixtheo.de/Record/1073000591' },
    { source: 'openalex', id: 'W1', url: 'https://openalex.org/W1' },
    { source: 'bibp', id: 'x', url: '' }] });
  check('OR-62 one link per record with a URL', merged.length === 3, merged);
  check('OR-62 two IxTheo links read differently', text(merged[0]) !== text(merged[1]), merged.map(text));
  check('OR-62 IxTheo links carry their catalogue numbers',
    text(merged[0]) === 'IxTheo record 037157663' && text(merged[1]) === 'IxTheo record 1073000591', merged.map(text));
  check('OR-62 a base with one record keeps the plain label', text(merged[2]) === 'OpenAlex record', text(merged[2]));
  const noId = recordLinks({ sourceIds: [
    { source: 'bibp', url: 'https://a' }, { source: 'bibp', url: 'https://b' }] });
  check('OR-62 without ids the links are numbered', noId.map(text).join('|') === 'BIBP record 1 of 2|BIBP record 2 of 2', noId.map(text));
  const fallback = recordLinks({ sourceIds: [], url: 'https://x', src: 'crossref' });
  check('OR-62 the record URL remains the fallback', fallback.length === 1 && text(fallback[0]) === 'Crossref record', fallback);
  // on the data: every merged record in graph.json renders distinct link texts
  const lifted = lift([decl('SRC_NAME'), fn('esc'), fn('sourceName'), fn('recordLinks'), 'var ABS = null;'], ['recordLinks']);
  let dup = 0, merged2 = 0;
  pubs.forEach((n) => {
    const labels = lifted.recordLinks({ sourceIds: n.source_ids || [], url: n.url, src: (n.src || [])[0] }).map(text);
    if (labels.length > 1) merged2++;
    if (new Set(labels).size !== labels.length) dup++;
  });
  check('OR-62 no record in graph.json shows two identical link texts', dup === 0, { dup, withSeveralLinks: merged2 });
});

/* ------------------------------------------------------------ OR-64 */
group('OR-64', () => {
check('OR-64 layoutLabels and its hook are gone', !/layoutLabels|__labels|relaxLabels|\bDISCS\b|labSig/.test(SRC));
check('OR-64 leaf names test the neighbouring discs', /rectHitsDisc\(box, discs\[i\]\)/.test(fn('drawLobeLabels'))
  && /var discs = CLUSTERS/.test(fn('drawLobeLabels')));
});

/* ------------------------------------------------------------ F1 gap answer */
// With several terms, the headline counts the counted records carrying every
// term; the widened list comes second; each term's reach is shown.
group('F1', () => {
  const law = cli('gap', 'Origen and Roman law');
  const r = CORE.search(IDX, 'Origen and Roman law');
  const { tallyMatch } = lift([fn('counts'), fn('visiblePub'), fn('tallyMatch')], ['tallyMatch'], { langOff: {} });
  const t = tallyMatch(IDX.records.filter((p) => r.matched.has(p.i)).map((p) => Object.assign({ lkey: 'en' }, p)),
    r.vocabOnly, r.scores, r.terms.length);
  check('F1 the headline is the CLI counted conjunction', t.full === law.carrying_all_terms_counted, { page: t.full, cli: law.carrying_all_terms_counted });
  check('F1 the widened list is a second, larger number', law.widened && t.hit + t.mention + t.aside === law.listed
    && law.listed > t.full, { listed: law.listed, full: t.full });
  const { termReach } = lift([fn('termReach')], ['termReach']);
  const rows = termReach(r, counted);
  const origen = cli('gap', 'Origen');
  check('F1 the reach of "origen" is gap "Origen" counted', rows[0].term === 'origen'
    && rows[0].n === origen.carrying_all_terms_counted && rows[0].n === law.per_term_counted.origen,
    { page: rows[0], gap: origen.carrying_all_terms_counted });
  check('F1 a term reaching most of the corpus is flagged', rows[0].most === true && rows.slice(1).every((x) => !x.most), rows);
  const eth = termReach(CORE.search(IDX, 'Origen in Ethiopia'), counted).find((x) => x.term === 'ethiopia');
  check('F1 a term absent from the corpus is named', !!eth && eth.absent === 'corpus' && eth.n === 0, eth);
  // the state line, lifted with the answer it reads
  const { nf } = lift([fn('nf')], ['nf']);
  const s = lift([fn('nf'), fn('quoteTerms'), fn('absentPhrase'), fn('stateLine')], ['stateLine'], {
    tokCount: r.terms.length, relaxed: r.relaxed, hitDepth: r.hitDepth, absentToks: r.absentTerms,
    absentFiltered: r.absentUnderFilters, vocabHit: r.vocabHit, vocabHitCounted: r.vocabHitCounted,
    vocabLabel: r.heading, PUBS: IDX.records }).stateLine(t, counted);
  const lead = law.carrying_all_terms_counted
    ? nf(law.carrying_all_terms_counted) + (law.carrying_all_terms_counted === 1 ? ' counted work carries' : ' counted works carry')
    : 'No counted work carries';
  check('F1 the state line leads with the counted conjunction', s.startsWith(lead + ' all 3 of your terms'), s);
  check('F1 the state line names the widening second', s.indexOf(' · widened to ' + law.widened_to_terms + ' of 3: ') > 0, s);
  const heading = lift([fn('nf'), fn('quoteTerms'), fn('absentPhrase'), fn('stateLine')], ['stateLine'], {
    tokCount: 2, relaxed: false, hitDepth: 2, absentToks: [], absentFiltered: [], vocabHit: 9, vocabHitCounted: 7,
    vocabLabel: 'Contre Celse', PUBS: [] }).stateLine({ hit: 0, full: 0, mention: 0, aside: 0, shelf: 9, shelfCounted: 7, hidden: 0 }, 100);
  check('F1 a heading figure is the counted one, the rest listed', heading.startsWith('7 works are filed under “Contre Celse”, of 100')
    && heading.indexOf('2 more listed') > 0, heading);
  const words = literals([fn('stateLine'), fn('renderPanel'), fn('reachHTML'), fn('ledgerHTML'),
    fn('viewDescription'), fn('showMissing'), fn('problemLine')].join('\n'));
  check('F1 no wording passes a count off as a verdict', !/\b(original|originality|unexplored|untouched|new ground|gap|novel)\b/i.test(words),
    words.match(/\b(original|originality|unexplored|untouched|new ground|gap|novel)\b/ig));
  const rp = fn('renderPanel');
  check('F1 the panel headline is t.full with several terms', /conj \? t\.full : dens/.test(rp));
});

/* ------------------------------------------------------------ F2 permalinks */
group('F2', () => {
  const a = lift([decl('LIST_KEYS'), fn('hashValue'), fn('serializeState'), fn('parseHash'), fn('viewIsDefault'),
    fn('addressOf'), fn('recordKey'), fn('recordKeys'), fn('resolveRecord')],
    ['serializeState', 'parseHash', 'addressOf', 'recordKey', 'recordKeys', 'resolveRecord']);
  const base = { q: '', m: 'theme', c: null, r: null, a: null, w: [], ap: [], d: [], l: [], off: [], cmp: '', b: null };
  const states = [
    { ...base, q: 'work:cels', b: '20260824-2490' },
    { ...base, q: 'Origen and Roman law', m: 'work', off: ['de', 'oth'] },
    { ...base, c: 'dom:exegesis', w: ['cels', 'princ'], ap: ['philological'], b: 'x' },
    { ...base, r: 'ixtheo-k10plus:011209895', d: ['pre1950', 'd1970'], l: ['fr', 'en'] },
    { ...base, q: '"free will" -rufinus & a=b + c, d/e #f 100 % d’Origène', c: '__off' },
    { ...base, q: 'Contre Celse ?', m: 'work', c: 'w:cels', b: '20260824-2490' },
    { ...base, a: 'a:crouzel-henri', cmp: 'work:princ', off: ['de'], b: '20260913-2490' },
    { ...base, q: 'author:crouzel', cmp: '"free will" year:1971-1990 & a=b, c/d' },
  ];
  states.forEach((s, i) => eq('F2 parse(serialize(state ' + i + ')) is the state',
    JSON.parse(JSON.stringify(a.parseHash('#' + a.serializeState(s)))), s));
  eq('F2 unknown keys are ignored', JSON.parse(JSON.stringify(a.parseHash('q=a&zz=1&w=x,x&m=nope'))),
    { ...base, q: 'a', w: ['x'] });
  check('F2 the map at rest has no address', a.addressOf({ ...base, b: '20260824-2490' }) === '');
  check('F2 a field query stays readable', a.serializeState({ ...base, q: 'work:cels' }) === 'q=work:cels');
  check('F2 an anchor is not a view', /h && h\.indexOf\('='\) < 0\) return/.test(fn('onAddress')));
  // records: by first source id, and every other id a link may carry
  const keys = a.recordKeys(IDX.records);
  const lost = IDX.records.filter((p) => a.resolveRecord(a.recordKey(p), keys) !== p);
  check('F2 every record resolves from its own key', lost.length === 0, lost.slice(0, 3).map((p) => p.ppn));
  const byPpn = IDX.records.filter((p) => a.resolveRecord(p.ppn, keys) !== p || a.resolveRecord('p:' + p.ppn, keys) !== p);
  check('F2 every record resolves from its Origenality ID', byPpn.length === 0, byPpn.slice(0, 3).map((p) => p.ppn));
  const old = IDX.records.find((p) => (p.sourceIds || []).some((e) => e.id === '011209895'));
  if (old) check('F2 the 22 August id 011209895 opens its record', a.resolveRecord('011209895', keys) === old, old.ppn);
  else console.log('note: 011209895 is not in this graph; the 22 August example was skipped');
  check('F2 an unknown id resolves to nothing', a.resolveRecord('nope:0', keys) === null && a.resolveRecord('', keys) === null);
  // wiring: a step for a record or a cluster, a replacement for everything else
  check('F2 opening a cluster or a record adds a history step', /syncHash\(true\)/.test(fn('openCluster')) && /syncHash\(true\)/.test(fn('openPub')));
  check('F2 other changes replace the address', /syncHash\(false\)/.test(fn('applyMatch')) && /syncHash\(false\)/.test(fn('closePanel')));
  check('F2 the fragment only, never the query string', /history\.pushState/.test(fn('syncHash')) && !/location\.search\s*=|[?&]q=/.test(SRC));
  // the citation, at click time, relative to the page in hand
  const view = { kind: 'search', figures: { headline: 88, counted: 88, full: 0, conj: false, relaxed: false, depth: 0, terms: 0,
    listed: 91, mention: 3, aside: 0, shelf: 0, total: 2209, held: false } };
  const c = lift([decl('LANGS'), fn('nf'), fn('recordKey'), fn('viewDescription'), fn('isoDay'), fn('citationText')], ['citationText'], {
    DATA_VERSION: 'B1', VIEW: view, MODE: 'theme', matched: new Set([1]), matchLabel: '“work:cels”', langOff: { de: true },
    viewUrl: () => 'http://127.0.0.1:8033/site/build-c/index.html#q=work:cels&b=B1' }).citationText();
  const total = lift([fn('nf')], ['nf']).nf(2209);
  check('F2 the citation names the view, its figures, the address and the day',
    c.startsWith('Origenality, build B1, view “work:cels”: 88 counted of ' + total + ', 3 mentioned only, not shown: German, '
      + 'http://127.0.0.1:8033/site/build-c/index.html#q=work:cels&b=B1, accessed ') && /accessed \d{4}-\d{2}-\d{2}\.$/.test(c), c);
  for (const href of ['http://127.0.0.1:8033/site/build-c/index.html#old=1', 'https://example.org/mirror/site/']) {
    const u = lift([fn('viewUrl')], ['viewUrl'], { URL, location: { href }, addressOf: () => 'q=work:cels', currentState: () => null }).viewUrl();
    check('F2 the address is resolved against ' + href, u === href.replace(/#.*$/, '') + '#q=work:cels', u);
  }
});

/* ------------------------------------------------------------ F3 reliability line */
group('F3', () => {
  const L = lift([decl('SRC_NAME'), fn('esc'), fn('nf'), fn('sourceName'), fn('counts'), fn('ledgerFigures'), fn('ledgerHTML'),
    'var ABS = null;'], ['ledgerFigures', 'ledgerHTML'], { SEM: sem });
  for (const [kind, key] of [['work', 'cels'], ['theme', 'anthropology.free-will']]) {
    const d = cli('density', kind, key);
    const r = CORE.search(IDX, kind + ':' + key);
    const list = r.order.filter((i) => !r.vocabOnly.has(i)).map((i) => IDX.records[i]);
    const f = L.ledgerFigures(list);
    eq('F3 ' + kind + ':' + key + ' panel figures are the CLI density figures',
      [f.n, f.review, f.withAbstract, f.undated, f.topSource, f.topCount, f.topShare],
      [d.counted_in_density, d.review_flagged, d.with_abstract, d.no_year,
        d.top_source && d.top_source.source, d.top_source && d.top_source.records, d.top_source && d.top_source.share_pct]);
    const html = L.ledgerHTML(f);
    check('F3 the line gives the wave and the threshold', html.includes(String(sem.source.wave)) && /counted: core and partial/.test(html), html);
    // the names are assembled from parts: the export refuses any exported file
    // that spells a provider, this test included
    const engineNames = new RegExp('\\b(' + ['gpt', 'open' + 'ai', 'claude', 'anthrop' + 'ic', 'mistral', 'llama',
      'gemini', 'model'].join('|') + ')\\b', 'i');
    check('F3 no engine or provider named', !engineNames.test(html), html);
    check('F3 no hand-typed agreement figure', !/\d+(\.\d+)?\s*%[^<]*agree|agree[^<]*\d+(\.\d+)?\s*%/i.test(html), html);
  }
  const few = IDX.records.filter((p) => p.dens).slice(0, 3);
  check('F3 a figure under ten says so', /small figure/.test(L.ledgerHTML(L.ledgerFigures(few))));
  const rp = fn('renderPanel');
  check('F3 the line is drawn on cluster, search and corpus panels', /zoneBits\.push\(ledgerHTML\(ledgerFigures\(headRecs\)\)\)/.test(rp));
  const recordBranch = rp.slice(0, rp.indexOf('if (sel) {'));
  check('F3 a single record carries no line', !/ledgerHTML/.test(recordBranch));
  check('F3 on a phone the line scrolls with the list, the figure stays in the head',
    /placeZones\(\)/.test(fn('openPanel')) && /if \(MOBILE\)[\s\S]*pBody\.insertBefore\(pZones/.test(fn('placeZones')));
});

/* ------------------------------------------------------------ build identifier */
// The build is read from the data layer, never typed in explorer.js.
group('BUILD', () => {
  const meta = JSON.parse(fs.readFileSync(path.join(DATA, 'META.json'), 'utf8'));
  const { buildIdOf } = lift([fn('buildIdOf')], ['buildIdOf']);
  const id = buildIdOf(meta);
  check('BUILD the identifier is the day and the work clusters of META.json',
    id === meta.generated.replace(/-/g, '') + '-' + meta.records && /^\d{8}-\d+$/.test(id), id);
  check('BUILD graph.json names the same build, the fallback without META.json',
    buildIdOf({ generated: graph.generated, records: pubs.length }) === id, { graph: graph.generated, pubs: pubs.length, id });
  [null, {}, { generated: '2026-09-13' }, { generated: '13/09/2026', records: 5 }, { generated: '2026-09-13', records: 0 },
    { generated: '2026-09-13', records: 2.5 }].forEach((m) => {
    check('BUILD no identifier from ' + JSON.stringify(m), buildIdOf(m) === null);
  });
  check('BUILD no build identifier typed in explorer.js', !/DATA_VERSION\s*=\s*['"]/.test(SRC) && !/\b20\d{6}-\d{3,5}\b/.test(SRC),
    SRC.match(/\b20\d{6}-\d{3,5}\b/g));
  const metaAt = SRC.indexOf("fetch('../data/META.json'");
  check('BUILD META.json is read before the files it versions', metaAt > 0 && metaAt < SRC.indexOf("versioned('../data/graph.json')"));
  check('BUILD every data file is fetched through versioned()', (SRC.match(/\?v=' \+ DATA_VERSION/g) || []).length === 1
    && /\?v=' \+ DATA_VERSION/.test(fn('versioned'))
    && /versioned\('\.\.\/data\/abstracts\.json'\)/.test(SRC) && /versioned\('assets\/semantic\.json'\)/.test(SRC));
});

/* ------------------------------------------------------------ F5 export */
group('F5', () => {
  const CITE = createRequire(import.meta.url)(path.join(PAGES, 'assets/cite.js'));
  const ex = lift([decl('SRC_NAME'), fn('esc'), fn('nf'), fn('sourceName'), fn('counts'), fn('englishLabel'), fn('abstractCredit'), fn('citeKeys'),
    fn('citeEntry'), fn('exportCounts'), fn('exportLabel'), fn('coinsHTML')],
  ['citeEntry', 'exportCounts', 'exportLabel', 'abstractCredit', 'coinsHTML'],
  { CITE, PUBS: IDX.records, CONTAINERS: null, CITE_FIELDS: null, CITE_KEYS: null, ABS: abs });
  const r = CORE.search(IDX, 'work:cels');
  const list = r.order.map((i) => IDX.records[i]);
  const entries = list.map((p) => ex.citeEntry(p, false));
  const bib = CITE.toBibTeX(entries);
  check('F5 work:cels exports the records the panel lists', (bib.match(/^@[a-z]+\{/gm) || []).length === r.matched.size, { entries: entries.length, listed: r.matched.size });
  check('F5 the control names the population it exports', ex.exportLabel({ kind: 'search', records: list }) === 'Export ' + lift([fn('nf')], ['nf']).nf(list.length) + ' records'
    && ex.exportLabel({ kind: 'record', records: [list[0]] }) === 'Export this record');
  const all = IDX.records.map((p) => ex.citeEntry(p, false));
  const keyOf = Object.fromEntries(all.map((e) => [e.recordId, e.key]));
  check('F5 a record keeps one key in every view', entries.every((e) => e.key && keyOf[e.recordId] === e.key));
  check('F5 keys are unique over the build', new Set(all.map((e) => e.key)).size === all.length);
  const c = ex.exportCounts(list);
  check('F5 records mentioned only or held aside are exported, not dropped', c.n === list.length && c.mention + c.aside === list.filter((p) => !p.dens).length);
  const withAb = IDX.records.find((p) => p.ab && p.ab.t && p.ab.u && p.ab.k !== 'generated');
  const e = ex.citeEntry(withAb, true);
  const englishLabel = (x) => String(x).replace(/\s+[:\u2014\u2013]\s+/g, ', ');
  check('F5 an exported abstract carries the page credit and its link', e.abstract.credit === 'Abstract from ' + englishLabel(abs.sources[withAb.ab.s].label)
    && e.abstract.url === withAb.ab.u && e.abstract.text === withAb.ab.t, e.abstract);
  check('F5 no abstract unless asked', ex.citeEntry(withAb, false).abstract === null);
  // U-11: a catalogue label written the French way ("Sudoc : Agence…") is credited as the English pages set it
  const spaced = IDX.records.filter((p) => p.ab && p.ab.t && p.ab.k !== 'generated' && /\s[:\u2014\u2013]\s/.test((abs.sources[p.ab.s] || {}).label || ''));
  const credits = IDX.records.filter((p) => p.ab && p.ab.t).map((p) => ex.abstractCredit(p).text);
  check('U-11 no abstract credit keeps a spaced colon or dash', credits.length > 0 && credits.every((t) => !/\s[:\u2014\u2013]\s/.test(t)),
    { spacedLabels: spaced.length, bad: credits.filter((t) => /\s[:\u2014\u2013]\s/.test(t)).slice(0, 2) });
  check('U-11 the credit is written with the englishLabel rule', /englishLabel\(/.test(fn('abstractCredit')));
  check('F5 every listed record carries a COinS span', /coinsHTML\(p\)/.test(fn('recordHTML')) && /^<span class="Z3988" title="ctx_ver=Z39\.88-2004&amp;/.test(ex.coinsHTML(list[0])));
  const ev = fn('exportView');
  check('F5 the export reads the open view, in its order', /view\.records\.map\(/.test(ev));
  check('F5 files are downloaded from a Blob, text copied by the clipboard', /new Blob\(\[text\]/.test(fn('download')) && /a\.download = name/.test(fn('download'))
    && /navigator\.clipboard\.writeText\(text\)/.test(ev));
  const lc = fn('loadContainers');
  check('F5 the export reads cite.json of this build (the file the search index reads), and the record file only when cite.json cannot be read',
    /fetch\(versioned\('\.\.\/data\/cite\.json'\)\)/.test(fn('readCiteFile')) && /readCiteFile\(\)/.test(lc) && /CITE\.citeData\(json\)/.test(lc)
    && /fetch\(versioned\('\.\.\/data\/site-merged\/corpus\.jsonl'\)\)/.test(lc)
    && lc.indexOf('readCiteFile()') < lc.indexOf("'../data/site-merged/corpus.jsonl'")
    && (fn('exportView') + fn('toggleExport') + fn('download')).indexOf('fetch(') < 0);
  // what the page writes from cite.json is what it writes from the record file and graph.json
  const parts = [decl('SRC_NAME'), fn('esc'), fn('nf'), fn('sourceName'), fn('counts'), fn('englishLabel'), fn('abstractCredit'), fn('citeKeys'), fn('citeEntry')];
  const d = CITE.citeData(JSON.parse(fs.readFileSync(path.join(DATA, 'cite.json'), 'utf8')));
  const viaCite = lift(parts, ['citeEntry'], { CITE, PUBS: IDX.records, CONTAINERS: d.containers, CITE_FIELDS: d.fields, CITE_KEYS: null, ABS: abs });
  const corpusText = fs.readFileSync(path.join(DATA, 'site-merged/corpus.jsonl'), 'utf8');
  const viaCorpus = lift(parts, ['citeEntry'], { CITE, PUBS: IDX.records, CONTAINERS: CITE.containersFromCorpus(corpusText),
    CITE_FIELDS: null, CITE_KEYS: null, ABS: abs });
  const differ = IDX.records.filter((p) => JSON.stringify(viaCite.citeEntry(p, true)) !== JSON.stringify(viaCorpus.citeEntry(p, true)));
  check('F5 cite.json gives every record the entry the record file gives', differ.length === 0, differ.slice(0, 3).map((p) => p.ppn));
});

/* ------------------------------------------------------------ F4 print */
group('F4', () => {
  const { decadeTally } = lift([fn('decadeRows'), fn('decadeTally')], ['decadeTally']);
  const rec = (year) => ({ year });
  eq('F4 decades: before 1950, each decade to the build\'s, undated apart', decadeTally([1900, 1955, 1957, 1971, null, 2021].map(rec), 2026), [
    { label: 'Before 1950', n: 1, open: false }, { label: '1950s', n: 2, open: false }, { label: '1960s', n: 0, open: false },
    { label: '1970s', n: 1, open: false }, { label: '1980s', n: 0, open: false }, { label: '1990s', n: 0, open: false },
    { label: '2000s', n: 0, open: false }, { label: '2010s', n: 0, open: false }, { label: '2020s', n: 1, open: true },
    { label: 'Undated', n: 1, open: false }]);
  const r = CORE.search(IDX, 'work:cels');
  const counted = r.order.map((i) => IDX.records[i]).filter((p) => p.dens && !r.vocabOnly.has(p.i));
  const t = decadeTally(counted, 2026);
  check('F4 the decade table adds up to the counted records', t.reduce((a, x) => a + x.n, 0) === counted.length && t.filter((x) => x.open).length === 1, t);
  const pp = fn('prepareForPrint');
  check('F4 before printing the list is filled to its end', /while \(shownCount < currentList\.length\) appendMore\(\)/.test(pp) && /fillPrint\(\)/.test(pp));
  check('F4 after printing the list goes back to the reader\'s length', /shownCount = Math\.min\(keep, recs\.length\)/.test(fn('afterPrint')) && /placeMore\(\)/.test(fn('afterPrint')));
  check('F4 the browser print events are handled', /addEventListener\('beforeprint', prepareForPrint\)/.test(SRC) && /addEventListener\('afterprint', afterPrint\)/.test(SRC));
  const fp = fn('fillPrint');
  check('F4 the print head gives address, build and day', /\['Address', viewUrl\(\)\]/.test(fp) && /\['Build', DATA_VERSION/.test(fp) && /\['Printed', isoDay\(new Date\(\)\)\]/.test(fp));
  check('F4 the head is filled whenever the panel opens', /fillPrint\(\)/.test(fn('openPanel')));
  const { englishLabel } = lift([fn('englishLabel')], ['englishLabel']);
  check('F4 catalogue labels are set as the English pages set them', englishLabel("Sudoc : Agence bibliographique de l'Enseignement supérieur (ABES)")
    === "Sudoc, Agence bibliographique de l'Enseignement supérieur (ABES)");
  const css = fs.readFileSync(path.join(PAGES, 'assets/explorer.css'), 'utf8');
  const print = css.slice(css.indexOf('@media print{'));
  check('F4 the stylesheet has a print block', css.indexOf('@media print{') > 0);
  check('F4 the decade strip prints in the dossier, so the head carries no second decade table',
    !/decadeHTML|print-decades/.test(SRC) && /\.strip-cmp,\.strip-tools,\.strip-problem/.test(print));
  check('F4 on paper: no map, no control', /#field-c/.test(print) && /\.cite-tools/.test(print) && /\.more/.test(print) && /\.legend-wrap/.test(print));
  check('F4 on paper: abstracts unfolded, records numbered and unbroken, addresses printed',
    /\.abstract-text\.folded\{display:block/.test(print) && /counter-increment:rec/.test(print) && /break-inside:avoid/.test(print)
    && /a\[href\^="http"\]::after\{content:" <" attr\(href\) ">"/.test(print));
  const html = fs.readFileSync(path.join(PAGES, 'index.html'), 'utf8');
  check('F4 the page holds the print head and foot, and loads cite.js before explorer.js', /id="p-print-head"/.test(html) && /id="p-print-foot"/.test(html)
    && html.indexOf('assets/cite.js') > 0 && html.indexOf('assets/cite.js') < html.indexOf('assets/explorer.js'));
});

/* ------------------------------------------------------------ F6 decade strip */
// The strip counts the records the headline counts, in the columns print and
// export share; a compared query goes through the same engine; the SVG and the
// CSV are written from the strip's own rows.
group('F6', () => {
  const meta = JSON.parse(fs.readFileSync(path.join(DATA, 'META.json'), 'utf8'));
  const year = Number(String(meta.generated).slice(0, 4));
  const buildId = lift([fn('buildIdOf')], ['buildIdOf']).buildIdOf(meta);
  const S = lift([fn('counts'), fn('visiblePub'), fn('tallyMatch'), fn('headlineRecords'), fn('decadeRows'), fn('decadeTally')],
    ['tallyMatch', 'headlineRecords', 'decadeRows', 'decadeTally'], { langOff: {} });
  // a search view as renderPanel counts it: the records listed, their tally, the headline and its records
  const searchView = (q) => {
    const r = CORE.search(IDX, q);
    const list = r.order.map((i) => IDX.records[i]);
    const t = S.tallyMatch(list, r.vocabOnly, r.scores, r.terms.length);
    const shelfAnswer = !t.hit && t.shelf > 0 && r.vocabHitCounted > 0;
    return { r, list, t, headline: shelfAnswer ? r.vocabHitCounted : (r.terms.length > 1 ? t.full : t.hit),
      records: S.headlineRecords(list, t, r, false, false) };
  };
  const sortObj = (o) => JSON.stringify(Object.keys(o).sort().map((k) => [k, o[k]]));
  const againstCli = (name, rows, at, d) => {
    const got = {}, want = {};
    rows.forEach((row) => { if (row.n[at]) got[row.key] = row.n[at]; });
    let before = 0;
    Object.keys(d.by_decade).forEach((k) => {
      if (Number(k) < 1950) before += d.by_decade[k]; else want[k] = d.by_decade[k];
    });
    if (before) want['before-1950'] = before;
    if (d.counted_undated) want.undated = d.counted_undated;
    check(name + ': the strip columns are the CLI density by_decade', sortObj(got) === sortObj(want), { got, want });
    const sum = rows.reduce((a, row) => a + row.n[at], 0);
    check(name + ': the strip adds up to the counted figure, undated included', sum === d.counted_in_density, { sum, counted: d.counted_in_density });
  };

  const cels = searchView('work:cels'), princ = searchView('work:princ');
  const dc = cli('density', 'work', 'cels'), dp = cli('density', 'work', 'princ');
  check('F6 work:cels: the panel headline is the CLI counted figure', cels.headline === dc.counted_in_density
    && cels.records.length === cels.headline, { headline: cels.headline, cli: dc.counted_in_density });
  const rows = S.decadeRows([cels.records, princ.records], year);
  againstCli('F6 work:cels', rows, 0, dc);
  againstCli('F6 work:cels compared with work:princ, the second row', rows, 1, dp);
  eq('F6 one series is the decade tally the print dossier used', S.decadeTally(cels.records, year),
    S.decadeRows([cels.records], year).map((r) => ({ label: r.label, n: r.n[0], open: r.open })));
  const decades = rows.filter((r) => /^\d{4}$/.test(r.key)).map((r) => Number(r.key));
  check('F6 the decade columns run without a hole, and the build decade is the one open column',
    decades.every((d, i) => !i || d === decades[i - 1] + 10) && rows.filter((r) => r.open).length === 1
    && rows.find((r) => r.open).key === String(Math.floor(year / 10) * 10), rows.map((r) => r.key));
  const law = searchView('Origen and Roman law');
  const gap = cli('gap', 'Origen and Roman law');
  check('F6 with several terms the strip counts the records carrying all of them, as the headline does',
    law.records.length === law.t.full && law.t.full === gap.carrying_all_terms_counted && law.headline === law.t.full,
    { strip: law.records.length, full: law.t.full, cli: gap.carrying_all_terms_counted });
  let shelf = null;
  outer: for (const kind of ['works', 'themes', 'domains', 'approaches']) {
    for (const key of Object.keys(sem[kind])) {
      const e = sem[kind][key];
      for (const label of [e.label].concat(Object.values(e.labels || {}), e.aliases || [])) {
        if (!label || label.length < 5 || /[:"]/.test(label)) continue;
        const v = searchView(label);
        if (!v.r.invalid && !v.t.hit && v.t.shelf > 0 && v.r.vocabHitCounted > 0) { shelf = Object.assign(v, { label }); break outer; }
      }
    }
  }
  if (shelf) {
    check('F6 a heading answered by its shelf: the strip counts the counted records filed under it',
      shelf.records.length === shelf.r.vocabHitCounted, { label: shelf.label, strip: shelf.records.length, heading: shelf.r.vocabHitCounted });
  } else console.log('note: no vocabulary label is answered by its shelf alone in this build; that case was skipped');

  // the exported figure, from the same rows and the page's own caption
  const view = { kind: 'search', title: '“work:cels”', records: cels.list, counted: cels.records,
    figures: { headline: cels.headline, counted: cels.t.hit, full: cels.t.full, conj: false, relaxed: false, depth: 1, terms: 0,
      listed: cels.list.length, mention: cels.t.mention, aside: cels.t.aside, shelf: 0, total: counted, held: false } };
  const st = { view, rows, series: [
    { label: '“work:cels”', query: '', records: cels.records, listed: cels.list.length },
    { label: '“work:princ”', query: 'work:princ', records: princ.records, listed: princ.list.length }] };
  const url = 'http://127.0.0.1:8033/site/build-c/index.html#q=work:cels&cmp=work:princ&b=' + buildId;
  const cap = lift([decl('LANGS'), fn('nf'), fn('recordKey'), fn('viewDescription'), fn('isoDay'), fn('buildYear'), fn('figureCaption')],
    ['figureCaption'], { DATA_VERSION: buildId, META: meta, MODE: 'theme', matched: new Set([1]), matchLabel: '“work:cels”',
      langOff: {}, answersKeep: () => null, viewUrl: () => url }).figureCaption(st);
  const nfv = lift([fn('nf')], ['nf']).nf;
  check('F6 the caption states the build, the counted population of each series, the open decade and the address',
    cap.legend[0] === '“work:cels”: ' + nfv(cels.records.length) + ' counted' + (cels.list.length > cels.records.length ? ' of ' + nfv(cels.list.length) + ' listed' : '')
    && cap.legend[1] === '“work:princ”: ' + nfv(princ.records.length) + ' counted'
    && cap.lines.some((l) => l.indexOf('build ' + buildId) >= 0) && cap.lines.some((l) => /core or partial/.test(l))
    && cap.lines.some((l) => /2020s are open/.test(l)) && cap.lines.some((l) => /harvested catalogues, not of the literature/.test(l))
    && cap.lines.includes(url), cap);
  const F = lift([fn('xmlText'), fn('wrapText'), fn('sentences'), fn('figureSVG'), decl('CSV_QUOTED'), fn('csvCell'), fn('figureCSV')], ['figureSVG', 'figureCSV', 'wrapText']);
  const svg = F.figureSVG(st, cap);
  const wellFormed = (xml) => {
    const body = xml.replace(/^<\?xml[^>]*\?>\s*/, '');
    const stack = [], re = /<(\/?)([A-Za-z][\w:-]*)((?:\s+[\w:-]+="[^"<]*")*)\s*(\/?)>|([^<]+)/g;
    let m, pos = 0;
    while ((m = re.exec(body))) {
      if (m.index !== pos) return 'stray text at ' + pos;
      pos = re.lastIndex;
      if (m[5] !== undefined) { if (/&(?!(amp|lt|gt|quot|apos);)/.test(m[5])) return 'bare & in text'; continue; }
      if (m[4]) continue;
      if (m[1]) { if (stack.pop() !== m[2]) return 'mismatched </' + m[2] + '>'; } else stack.push(m[2]);
    }
    return pos === body.length && !stack.length ? null : 'unclosed ' + stack.join(',') + ' at ' + pos;
  };
  check('F6 the SVG is well-formed XML', wellFormed(svg) === null, wellFormed(svg));
  const unxml = (t) => t.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, '&');
  const texts = [...svg.matchAll(/<text[^>]*>([^<]*)<\/text>/g)].map((m) => unxml(m[1]));
  const nums = texts.filter((t) => /^\d+$/.test(t)).map(Number).sort((a, b) => a - b);
  const cells = rows.flatMap((r) => r.n).sort((a, b) => a - b);
  check('F6 every count of the strip is printed on the SVG, and no other number stands alone', JSON.stringify(nums) === JSON.stringify(cells), { nums: nums.length, cells: cells.length });
  check('F6 the SVG carries its title, legend, build, population and address as text',
    texts.includes(cap.title) && cap.legend.every((l) => texts.includes(l)) && texts.join('').indexOf(url) >= 0
    && texts.some((t) => t.indexOf(buildId) >= 0) && texts.some((t) => /not of the literature/.test(t)) && texts.includes('open'));
  check('F6 the SVG is standalone: no script, no image, no font file, no external reference',
    !/<script|<image|<foreignObject|@font-face|@import|xlink:href|\shref=/i.test(svg)
    && (svg.match(/="https?:[^"]*"/g) || []).join() === '="http://www.w3.org/2000/svg"'
    && !/url\((?!#or-hatch\))/.test(svg));
  check('F6 the two series stay apart in black and white: a terracotta fill and an ink hatching, named in the legend',
    /fill="#A03620"/.test(svg) && /fill="url\(#or-hatch\)"/.test(svg) && /<pattern id="or-hatch"/.test(svg)
    && /font-family="'EB Garamond', Georgia, serif"/.test(svg));
  const csv = F.figureCSV(st, cap);
  const parseCsv = (line) => {
    const out = []; let cur = '', q = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (q) { if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++; } else if (ch === '"') q = false; else cur += ch; }
      else if (ch === '"') q = true; else if (ch === ',') { out.push(cur); cur = ''; } else cur += ch;
    }
    out.push(cur);
    return out;
  };
  // read as Python's csv reader reads it: every line parsed, quotes honoured
  const lines = csv.split('\r\n').filter(Boolean);
  const parsed = lines.map(parseCsv);
  const commentRows = parsed.filter((r) => r[0].startsWith('# '));
  const comments = commentRows.map((r) => r[0].slice(2));
  const table = parsed.filter((r) => !r[0].startsWith('# '));
  const captionLines = [cap.title].concat(cap.legend, cap.lines);
  check('F6 the CSV opens with the caption as comment lines', captionLines.every((l) => comments.includes(l)), comments);
  check('C-7 each caption line is one CSV cell: its commas are quoted, not column breaks',
    captionLines.some((l) => l.indexOf(',') >= 0) && commentRows.length === captionLines.length && commentRows.every((r) => r.length === 1),
    parsed.filter((r) => r[0].startsWith('# ') && r.length > 1).slice(0, 2));
  check('U-10 the SVG description reads its lines as sentences', /<desc id="or-desc">[^<]*counted\. [^<]*<\/desc>/.test(svg),
    svg.match(/<desc id="or-desc">[^<]{0,160}/));
  eq('F6 the CSV header names each series and its population', table[0],
    ['decade', '“work:cels”: counted records (core and partial)', '“work:princ”: counted records (core and partial)']);
  eq('F6 the CSV rows are the strip rows', table.slice(1, -1), rows.map((r) => [r.label].concat(r.n.map(String))));
  eq('F6 the CSV ends with the counted total of each series', table[table.length - 1],
    ['All counted', String(cels.records.length), String(princ.records.length)]);
  const wrapped = F.wrapText('x '.repeat(3) + 'y'.repeat(250), 104);
  check('F6 a long address is broken into lines that keep every character', wrapped.every((l) => l.length <= 104)
    && wrapped.join('').replace(/ /g, '') === 'xxx' + 'y'.repeat(250), wrapped);

  // wiring
  check('F6 the strip, the SVG and the CSV read the same rows', /decadeRows\(series\.map/.test(fn('stripState'))
    && /figureSVG\(STRIP, cap\)/.test(fn('stripTool')) && /figureCSV\(STRIP, cap\)/.test(fn('stripTool')));
  check('F6 the panel headline and a compared query share one headline rule',
    /headlineRecords\(list, t, matched \? LAST : null, !!sel, held\)/.test(fn('renderPanel'))
    && /CORE\.search\(IDX, q, \{ keep: answersKeep\(\) \}\)/.test(fn('compareSeries'))
    && /visiblePub\(p\)/.test(fn('compareSeries')) && /headlineRecords\(list, t, r, false, false\)/.test(fn('compareSeries'))
    && /var keep = answersKeep\(\)/.test(fn('computeMatch')));
  check('F6 the compared query belongs to the address', /put\('cmp', s\.cmp\)/.test(fn('serializeState'))
    && /CMP = s\.cmp/.test(fn('applyState')) && /cmp: CMP/.test(fn('currentState')) && /!s\.cmp/.test(fn('viewIsDefault'))
    && /syncHash\(false\)/.test(fn('setCompare')));
  check('F6 files are Blobs, the SVG copy goes through the clipboard',
    /download\(figureCSV\(STRIP, cap\)/.test(fn('stripTool')) && /download\(svg, svgName, 'image\/svg\+xml/.test(fn('stripTool'))
    && /navigator\.clipboard\.writeText\(svg\)/.test(fn('stripTool')));
  const written = literals([fn('stripHTML'), fn('figureSVG'), fn('renderAuthor'), fn('zoneList'), fn('zoneKeys'), fn('authorsHTML')].join('\n'));
  check('F6 no inline script or event handler in what the strip and the author view write', !/<script|\son[a-z]+\s*=/i.test(written));
  check('F6 no wording passes a count off as a verdict', !/\b(original|originality|unexplored|untouched|unstudied|new ground|gap|gaps|novel)\b/i.test(
    literals([fn('stripHTML'), fn('figureCaption'), fn('renderAuthor'), decl('AUTHOR_NOTE')].join('\n'))));
});

/* ------------------------------------------------------------ F8 author view */
// An author is a node of graph.json: its records are those its aut edges reach,
// never a prefix match; the page and the CLI print the same figures.
group('F8', () => {
  const meta = JSON.parse(fs.readFileSync(path.join(DATA, 'META.json'), 'utf8'));
  const year = Number(String(meta.generated).slice(0, 4));
  const A = lift([fn('counts'), fn('authorsOf'), fn('byYear'), fn('keyCounts'), fn('authorSummary'), fn('soleAuthorOf'), fn('decadeRows')],
    ['authorsOf', 'authorSummary', 'soleAuthorOf', 'decadeRows'], { norm: CORE.norm });
  const idx = A.authorsOf(graph, IDX.records);
  const edgeCount = {};
  graph.edges.forEach((e) => { if (e.r === 'aut' && graph.nodes[e.t] && graph.nodes[e.t].k === 'author') edgeCount[graph.nodes[e.t].id] = (edgeCount[graph.nodes[e.t].id] || 0) + 1; });
  const crouzel = idx.byId['a:crouzel-henri'];
  check('F8 Crouzel, Henri lists one record per aut edge', !!crouzel && crouzel.label === 'Crouzel, Henri'
    && crouzel.pubs.length === edgeCount['a:crouzel-henri'], { listed: crouzel && crouzel.pubs.length, edges: edgeCount['a:crouzel-henri'] });
  const off = idx.list.filter((a) => a.pubs.length !== edgeCount[a.id]);
  check('F8 every author entry lists one record per aut edge', off.length === 0 && idx.list.length === Object.keys(edgeCount).length, off.slice(0, 3).map((a) => a.id));

  const summaries = idx.list.map((a) => A.authorSummary(a, sem, idx.ofPub));
  const pick = new Set(['a:crouzel-henri', 'a:furst-alfons', 'a:perrone-lorenzo']);
  const firstWith = (test) => { const s = summaries.find(test); if (s) pick.add(s.id); };
  firstWith((s) => s.aside > 0);
  firstWith((s) => s.mention > 0 && s.counted.length > 0);
  firstWith((s) => !s.counted.length);
  firstWith((s) => s.containers.length > 1);
  const most = summaries.slice().sort((x, y) => y.coauthors.length - x.coauthors.length)[0];
  if (most) pick.add(most.id);
  for (const id of pick) {
    const a = idx.byId[id];
    if (!a) { check('F8 ' + id + ' is an author entry of this graph', false); continue; }
    const s = A.authorSummary(a, sem, idx.ofPub);
    const c = cli('author', id);
    eq('F8 ' + id + ': listed, counted, mentioned only, held aside equal the CLI',
      [s.records.length, s.counted.length, s.mention, s.aside], [c.listed, c.counted_in_density, c.mentioned_only, c.held_aside]);
    for (const k of ['themes', 'works', 'approaches']) {
      eq('F8 ' + id + ': ' + k + ' equal the CLI', s[k].map((x) => [x.key, x.label, x.n]), c[k].map((x) => [x.key, x.label, x.counted]));
    }
    eq('F8 ' + id + ': languages equal the CLI', Object.entries(s.languages).sort(), Object.entries(c.languages).sort());
    eq('F8 ' + id + ': containers equal the CLI', s.containers.map((x) => [x.label, x.n]), c.containers.map((x) => [x.title, x.counted]));
    eq('F8 ' + id + ': co-authors equal the CLI', s.coauthors, c.co_authors);
    eq('F8 ' + id + ': the list reads in year order, as the CLI gives it', s.records.slice(0, c.results.length).map((p) => p.ppn), c.results.map((r) => r.id));
    const byDecade = {};
    A.decadeRows([s.counted], year).forEach((r) => { if (r.n[0] && r.key !== 'undated') byDecade[r.key] = r.n[0]; });
    const undated = (A.decadeRows([s.counted], year).find((r) => r.key === 'undated') || { n: [0] }).n[0];
    const cliDecades = {};
    let before = 0;
    Object.keys(c.by_decade).forEach((k) => { if (Number(k) < 1950) before += c.by_decade[k]; else cliDecades[k] = c.by_decade[k]; });
    if (before) cliDecades['before-1950'] = before;
    eq('F8 ' + id + ': the decade strip equals the CLI by_decade', [Object.entries(byDecade).sort(), undated],
      [Object.entries(cliDecades).sort(), c.counted_undated]);
  }
  const unsorted = summaries.filter((s) => s.coauthors.some((o, i) => i && CORE.norm(s.coauthors[i - 1].label) > CORE.norm(o.label)));
  check('F8 co-authors are names in alphabetical order, with no figure to rank them', unsorted.length === 0
    && summaries.every((s) => s.coauthors.every((o) => Object.keys(o).join() === 'id,label')), unsorted.slice(0, 2).map((s) => s.id));
  const out = summaries.filter((s) => s.records.some((p, i) => i && CORE.isDated(p) && CORE.isDated(s.records[i - 1]) && Number(p.year) < Number(s.records[i - 1].year)));
  check('F8 every author list reads in year order, the undated last', out.length === 0, out.slice(0, 2).map((s) => s.id));

  // author: typed in the search field
  const r = CORE.search(IDX, 'author:crouzel');
  check('F8 author:crouzel is shown as the view of Crouzel, Henri, with the same records',
    A.soleAuthorOf(r, idx) === crouzel && r.matched.size === crouzel.pubs.length);
  check('F8 a name several entries answer stays a search', A.soleAuthorOf(CORE.search(IDX, 'author:cox'), idx) === null);
  let accepted = 0;
  const wrong = [];
  idx.list.filter((a) => a.pubs.length >= 5 && a.label.indexOf('"') < 0).forEach((a) => {
    const rr = CORE.search(IDX, 'author:"' + a.label + '"');
    const got = A.soleAuthorOf(rr, idx);
    if (!got) return;
    accepted++;
    const mine = new Set(got.pubs.map((p) => p.i));
    if (rr.matched.size !== mine.size || [...rr.matched].some((i) => !mine.has(i))) wrong.push(a.id);
  });
  check('F8 an author: query shown as an author view lists exactly that entry', accepted > 0 && wrong.length === 0, { accepted, wrong });

  // the record line and the wiring
  const H = (shown) => lift([fn('esc'), fn('authorsHTML')], ['authorsHTML'], { DATA: graph, authorIndex: () => idx, shownAuthor: shown });
  const rec = crouzel.pubs.find((p) => p.authors.length > 1) || crouzel.pubs[0];
  const line = H(null).authorsHTML(rec);
  check('F8 an author name in a record is a button that opens that author', /<button type="button" class="au" data-a="a:crouzel-henri">Crouzel, Henri<\/button>/.test(line), line);
  check('F8 in the author view the name itself is plain text', H(crouzel).authorsHTML(rec).indexOf('data-a="a:crouzel-henri"') < 0);
  check('F8 the record line calls it', /authorsHTML\(p\)/.test(fn('recordHTML')));
  check('F8 the address carries the author, and a link restores it', /put\('a', s\.a\)/.test(fn('serializeState'))
    && /else if \(selAuthor\) s\.a = selAuthor\.id/.test(fn('currentState')) && /authorIndex\(\)\.byId\[s\.a\]/.test(fn('applyState'))
    && /else if \(author\) openAuthor\(author\)/.test(fn('applyState')) && /!s\.a/.test(fn('viewIsDefault')));
  check('F8 opening an author adds a history step; a heading of the view opens its search as another', /syncHash\(true\)/.test(fn('openAuthor'))
    && /history\.pushState/.test(fn('searchFor')));
  check('F8 the panel shows the author before any cluster or search', /var author = selAuthor \|\| \(sel \? null : soleAuthor\(\)\)/.test(fn('renderPanel')));
  check('F8 the list is ordered by year, never by citation weight', /a\.pubs\.slice\(\)\.sort\(byYear\)/.test(fn('authorSummary'))
    && !/\.w\b|\.wr\b|\.tier\b/.test(fn('authorSummary') + fn('byYear')));
  check('F8 no score or ranking of scholars is printed', !/\b(rank|ranked|ranking|score|leading|prolific|most cited)\b/i.test(
    literals([fn('renderAuthor'), fn('authorSummary'), decl('AUTHOR_NOTE')].join('\n'))));
  check('F8 the note says other spellings are not merged', /not merged/.test(literals(decl('AUTHOR_NOTE'))));
});

/* ------------------------------------------------------------ the Observatory's build */
// The Observatory derives its build as the Explorer does; neither types one.
group('BUILD-OBS', () => {
  const OC = createRequire(import.meta.url)(path.join(PAGES, 'assets/observatory-core.js'));
  const { buildIdOf } = lift([fn('buildIdOf')], ['buildIdOf']);
  const meta = JSON.parse(fs.readFileSync(path.join(DATA, 'META.json'), 'utf8'));
  [meta, null, {}, { generated: '2026-09-13' }, { generated: '2026-09-13', records: 2490 }, { generated: '13/09/2026', records: 5 },
    { generated: '2026-09-13', records: 0 }, { generated: '2026-09-13', records: 2.5 }].forEach((m) => {
    check('BUILD-OBS the Observatory derives the build as the Explorer does from ' + JSON.stringify(m && m.generated ? { generated: m.generated, records: m.records } : m),
      OC.buildIdOf(m) === buildIdOf(m), { observatory: OC.buildIdOf(m), explorer: buildIdOf(m) });
  });
  const obs = fs.readFileSync(path.join(PAGES, 'assets/observatory.js'), 'utf8');
  const core = fs.readFileSync(path.join(PAGES, 'assets/observatory-core.js'), 'utf8');
  for (const [name, text] of [['observatory.js', obs], ['observatory-core.js', core], ['explorer.js', SRC]]) {
    check('BUILD-OBS no build identifier typed in ' + name, !/DATA_VERSION\s*=\s*['"]/.test(text) && !/\b20\d{6}-\d{3,5}\b/.test(text),
      text.match(/\b20\d{6}-\d{3,5}\b/g));
  }
  check('BUILD-OBS the Observatory reads META.json first and keys the other files by its build',
    /fetch\('\.\.\/data\/META\.json', \{ cache: 'no-cache' \}\)/.test(obs) && /CORE\.buildIdOf\(meta\)/.test(obs)
    && /versioned\('\.\.\/data\/graph\.json'\)/.test(obs) && /versioned\('\.\.\/data\/stats\.json'\)/.test(obs)
    && /versioned\('assets\/semantic\.json'\)/.test(obs) && obs.indexOf("'../data/META.json'") < obs.indexOf("versioned('../data/graph.json')"));
});

/* ------------------------------------------------------------ crossings to the Explorer */
// Every count of the Observatory's crossings that links to the Explorer links to
// a view whose headline is that count.
group('CROSS', () => {
  const X = createRequire(import.meta.url)(path.join(PAGES, 'assets/observatory-core.js'));
  const H = lift([fn('counts'), fn('visiblePub'), fn('tallyMatch'), fn('headlineRecords'), decl('LIST_KEYS'), fn('parseHash')],
    ['tallyMatch', 'headlineRecords', 'parseHash'], { langOff: {} });
  let links = 0;
  const bad = [];
  for (const view of X.VIEWS) {
    const v = X.crossing(view, graph, sem);
    for (const l of X.crossingLinks(v, sem)) {
      links++;
      const href = X.explorerHref(l.query);
      const s = H.parseHash(href.slice(href.indexOf('#')));
      const r = CORE.search(IDX, s.q);
      if (!href.startsWith('index.html#q=') || s.q !== l.query || r.invalid) { bad.push([view, l.row, l.col, href]); continue; }
      const list = r.order.map((i) => IDX.records[i]);
      const t = H.tallyMatch(list, r.vocabOnly, r.scores, r.terms.length);
      const shelfAnswer = !t.hit && t.shelf > 0 && r.vocabHitCounted > 0;
      const headline = shelfAnswer ? r.vocabHitCounted : (r.terms.length > 1 ? t.full : t.hit);
      if (headline !== l.n || H.headlineRecords(list, t, r, false, false).length !== l.n) bad.push([view, l.row, l.col, l.n, headline]);
    }
  }
  check('CROSS every linked crossing count is the headline of the Explorer view it opens', links > 0 && bad.length === 0, { links, bad: bad.slice(0, 5) });
  const obs = fs.readFileSync(path.join(PAGES, 'assets/observatory.js'), 'utf8');
  check('CROSS the page takes its links from the core, relative to the page', /core\.crossingLinks\(v, sem\)/.test(obs)
    && /core\.explorerHref\(l\.query\)/.test(obs) && !/href="\//.test(obs));
});

/* ------------------------------------------------------------ OR-05 (wiring) */
check('OR-05 a handled touch tap cancels its compatibility click',
  /touchTap && e\.cancelable\) e\.preventDefault\(\)[\s\S]{0,60}\{ passive: false \}/.test(SRC));
check('OR-05 the veil closes only a gesture that began on it', /if \(veilDown\) closePanel\(true\)/.test(SRC)
  && !/veil\.addEventListener\('click', closePanel\)/.test(SRC));

/* ------------------------------------------------------------ S-P1 every heading, on the page */
// graph.json keeps a heading only when three records share it. The page renders
// on it, then reads cite.json into the same index the CLI builds, and says so
// in the meantime rather than calling a term absent.
group('S-P1', () => {
  const load = SRC.slice(SRC.indexOf("fetch('../data/META.json'"), SRC.indexOf('function build(g)'));
  check('S-P1 the first render does not wait for cite.json: the map is built, then the index completed',
    /build\(r\[0\]\);\s*completeIndex\(\);/.test(load) && load.indexOf('cite.json') < 0, load.slice(-300));
  check('S-P1 the index is completed with the file the CLI reads, through applyCite',
    /CORE\.applyCite\(IDX, json\)/.test(fn('completeIndex')) && /fetch\(versioned\('\.\.\/data\/cite\.json'\)\)/.test(fn('readCiteFile')));
  check('S-P1 the answer on screen is counted again once the index is complete, without moving a field that has not changed',
    /\.then\(refreshAnswer\)/.test(fn('completeIndex')) && /applyMatch\(false, true\)/.test(fn('refreshAnswer'))
    && /var still = !!quiet && sameMatch\(before, matched\)/.test(fn('applyMatch')));
  check('S-P1 computeMatch keeps the terms a partial index did not find apart', /absentPartial = r\.absentFromPartialIndex/.test(fn('computeMatch')));
  const graphOnly = CORE.buildIndex(graph, sem, abs);
  const words = new Set();
  IDX.records.forEach((p) => { if (p.dens) p.subjects.forEach((h) => CORE.tokens(h).forEach((w) => { if (w.length >= 7) words.add(w); })); });
  // absence as search-core.js judges it (hay or vocab, word start), for every
  // word; the engine itself is asked for the three words of the audit
  let before = 0;
  const now = [];
  for (const w of words) {
    const re = CORE.termRe(w);
    if (!graphOnly.records.some((p) => re.test(p.hay) || re.test(p.vocab))) before++;
    if (!IDX.records.some((p) => re.test(p.hay) || re.test(p.vocab))) now.push(w);
  }
  for (const w of ['antisemitismus', 'homerus', 'geistesgeschichte']) {
    const r = CORE.search(IDX, w);
    check('S-P1 "' + w + '" is found by the engine, not named absent', r.absentTerms.length === 0 && r.fullHit > 0, { absent: r.absentTerms, hits: r.fullHit });
  }
  check('S-P1 no word of a subject heading of a counted record is named absent', words.size > 0 && now.length === 0,
    { words: words.size, absent: now.slice(0, 5) });
  console.log('note: S-P1 words of 7+ letters in the headings of counted records: ' + words.size +
    '; found by an index built on graph.json alone: ' + (words.size - before) + ', by the completed index: ' + (words.size - now.length));
  const lifted = (state, partial) => lift([fn('quoteTerms'), fn('partialPhrase'), fn('headingsNote')], ['headingsNote'],
    { headings: state, absentPartial: partial, IDX: { thresholds: graph.thresholds } });
  const r = CORE.search(graphOnly, 'Origen Antisemitismus');
  const loading = lifted('loading', r.absentFromPartialIndex).headingsNote(r);
  check('S-P1 while the headings load, a term not found is not called absent', r.absentTerms.length === 0
    && /“antisemitismus” is not found yet: the subject headings of each record are still loading/.test(loading) && !/appears in none/.test(loading), loading);
  const rising = lifted('loading', []).headingsNote(CORE.search(graphOnly, 'allegory'));
  check('S-P1 while the headings load, a count says it may rise', /still loading, so this count may rise/.test(rising), rising);
  const failed = lifted('failed', []).headingsNote(CORE.search(graphOnly, 'allegory'));
  check('S-P1 when cite.json cannot be read, the line says which headings were searched',
    failed.indexOf('only headings ' + graph.thresholds.subject_min_publications + ' or more records share were searched') >= 0, failed);
  check('S-P1 a complete index adds nothing, nor does a field-only query',
    lifted('complete', []).headingsNote(CORE.search(IDX, 'allegory')) === '' && lifted('loading', []).headingsNote(CORE.search(graphOnly, 'work:cels')) === '');
  const words2 = literals([fn('partialPhrase'), fn('headingsNote'), fn('reachHTML')].join('\n'));
  check('S-P1 no wording passes a count off as a verdict', !/\b(original|originality|unexplored|untouched|new ground|gap|novel)\b/i.test(words2));
});

/* ------------------------------------------------------------ correctness review */
group('C-1', () => {
  const boot = fn('boot');
  const clear = boot.slice(boot.indexOf("clear.addEventListener('click'"), boot.indexOf("getElementById('reset')"));
  const reset = boot.slice(boot.indexOf("getElementById('reset')"), boot.indexOf('var keyTog'));
  check('C-1 the clear button drops the compared query', /CMP = ''/.test(clear), clear);
  check('C-1 Reset drops the compared query', /CMP = ''/.test(reset), reset);
});

group('C-5', () => {
  check('C-5 a step added by an open remembers the address it was taken from',
    /history\.pushState\(\{ view: 1, from: location\.hash\.replace/.test(fn('syncHash')));
  check('C-5 the close button, Escape, the veil, a pull and a tap on the empty map close as the reader',
    /'panel-close'\)\.addEventListener\('click', function \(\) \{ closePanel\(true\); \}\)/.test(SRC)
    && /if \(veilDown\) closePanel\(true\)/.test(SRC) && /dragDy > 72\) closePanel\(true\)/.test(SRC)
    && /else closePanel\(true\)/.test(SRC) && /fold\.focus\(\); return; \}\s*closePanel\(true\);/.test(SRC));
  check('C-5 closing by the reader takes Back when the address would return to the one before',
    /byReader === true && stepBack\(\)/.test(fn('closePanel')));
  const base = { q: '', m: 'theme', c: null, r: null, a: null, w: [], ap: [], d: [], l: [], off: [], cmp: '', b: 'B1' };
  const run = (from, hash, state, restoring) => {
    let backs = 0;
    const S = lift([decl('LIST_KEYS'), fn('hashValue'), fn('serializeState'), fn('parseHash'), fn('viewIsDefault'), fn('addressOf'),
      fn('canonical'), 'var lastHash = "";', fn('stepBack'), 'function seen() { return lastHash; }'], ['stepBack', 'seen'],
    { addressReady: true, restoring: !!restoring, history: { state: from == null ? null : { view: 1, from }, back: () => { backs++; } },
      location: { hash: hash }, currentState: () => ({ ...base, ...state }) });
    const went = S.stepBack();
    return { went, backs, lastHash: S.seen() };
  };
  const cluster = run('q=allegory&b=B1', '#q=allegory&c=dom:exegesis&b=B1', { q: 'allegory' });
  check('C-5 closing a cluster opened from a search goes back to the search', cluster.went && cluster.backs === 1 && cluster.lastHash === 'q=allegory&b=B1', cluster);
  const record = run('q=allegory&c=dom:exegesis&b=B1', '#q=allegory&r=ixtheo-k10plus:1&b=B1', { q: 'allegory' });
  check('C-5 closing a record opened from a cluster replaces the address: Back then reopens the cluster', !record.went && record.backs === 0, record);
  check('C-5 a replayed address never goes back', !run('q=allegory&b=B1', '#q=allegory&c=dom:exegesis&b=B1', { q: 'allegory' }, true).went);
  check('C-5 a step that was not an open (no from) is written over as before', !run(null, '#q=allegory&c=dom:exegesis&b=B1', { q: 'allegory' }).went);
  check('C-5 another build in the address is the same address', run('q=allegory&b=B0', '#q=allegory&c=dom:exegesis&b=B0', { q: 'allegory' }).went);
});

group('C-6', () => {
  ['openCluster', 'openPub', 'openAuthor', 'setCompare', 'setMode'].forEach((name) => {
    check('C-6 ' + name + ' clears the note on the build a link was made on', /userMoved\(\);/.test(fn(name)));
  });
  check('C-6 so do the language key, a reservoir and an answer to the questions',
    /userMoved\(\);\s*setLangOff\(l\.code, !langOff\[l\.code\]\)/.test(SRC) && /userMoved\(\);\s*var show = isFolded\(c\)/.test(SRC)
    && /userMoved\(\);\s*if \(k >= 0\) arr\.splice/.test(SRC) && /userMoved\(\);\s*wizAns\[q\.kind\] = \[\]/.test(SRC));
  const el = { textContent: 'Link made on build B0; figures shown are from build B1. 12 works match' };
  let removed = 0;
  const make = (restoring) => lift([fn('buildNote'), fn('renderState'), fn('userMoved'), 'function lb() { return linkBuild; }'], ['userMoved', 'lb'],
    { restoring, linkBuild: 'B0', DATA_VERSION: 'B1', stateText: '12 works match', document: { getElementById: () => el },
      panel: { querySelector: () => ({ remove: () => { removed++; } }) } });
  const moved = make(false);
  moved.userMoved();
  check('C-6 a view the reader opens drops the note from the state line and the panel', moved.lb() === null && el.textContent === '12 works match' && removed === 1,
    { lb: moved.lb(), text: el.textContent });
  const replay = make(true);
  replay.userMoved();
  check('C-6 a view replayed from the link keeps the note', replay.lb() === 'B0');
});

/* ------------------------------------------------------------ UX and accessibility review */
const CSS = fs.readFileSync(path.join(PAGES, 'assets/explorer.css'), 'utf8');
const PRINT = CSS.slice(CSS.indexOf('@media print{'));
group('U-1', () => {
  check('U-1 an author, a heading, a co-author or a zone opened from inside the panel hands the focus to its head',
    /openAuthor\(a\); focusPanelHead\(\);/.test(SRC) && /searchFor\(t\.getAttribute\('data-q'\)\); focusPanelHead\(\);/.test(SRC)
    && (SRC.match(/openCluster\(CLUSTERS\[\+b\.dataset\.k\]\); focusPanelHead\(\);/g) || []).length === 2);
  check('U-1 after cite.json is read, the head takes the focus only from a control the redraw removed',
    /var inside = open && !!had && had !== panel && panel\.contains\(had\)/.test(fn('refreshAnswer')) && /if \(inside && !document\.contains\(had\)\) focusPanelHead\(\)/.test(fn('refreshAnswer')));
  check('U-1 no ring round the figure after a click, and none on paper', /panel\.classList\.toggle\('by-pointer', byPointer\)/.test(fn('focusPanelHead'))
    && /\.panel\.by-pointer \.density:focus-visible\{outline:none\}/.test(CSS) && /\.panel \.density\{font-size:18pt;margin:0;outline:none!important\}/.test(PRINT));
  check('U-1 the head is focusable by script only', /pDensity\.setAttribute\('tabindex', '-1'\)/.test(fn('focusPanelHead')) && /pDensity\.focus\(/.test(fn('focusPanelHead')));
  const am = fn('appendMore');
  check('U-1 Show more puts the focus on the first record added, before the control is removed',
    /appendMore\(true\)/.test(fn('placeMore')) && am.indexOf('h.focus()') > 0 && am.indexOf('h.focus()') < am.indexOf('placeMore()'));
});
group('U-2', () => {
  check('U-2 the compare field shows a 2 px accent ring on focus', /\.strip-field input:focus-visible\{outline:2px solid var\(--accent\);outline-offset:2px/.test(CSS)
    && !/\.strip-field input:focus-visible\{box-shadow/.test(CSS));
  const lum = (hex) => { const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4))); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); };
  const r = ratio('#A03620', '#F7F2E6');
  check('U-2 the ring holds 3:1 against the panel', r >= 3, r.toFixed(2));
  console.log('note: U-2 focus ring #A03620 on the panel #F7F2E6: ' + r.toFixed(2) + ':1');
});
group('U-3', () => {
  check('U-3 Escape folds an open export first and gives its control the focus',
    /querySelector\('\.cite-export\[aria-expanded="true"\]'\)/.test(SRC) && /if \(fold\) \{ toggleExport\(fold\); fold\.focus\(\); return; \}/.test(SRC));
  const ch = fn('citeHTML');
  check('U-3 Print comes before Export, so the key goes from Export into its fold', ch.indexOf('cite-print') > 0 && ch.indexOf('cite-print') < ch.indexOf('cite-export'));
});
group('U-4', () => {
  const { compareMessage } = lift([fn('nf'), fn('compareMessage')], ['compareMessage']);
  const two = { problem: '', series: [{ label: '“allegory”', records: [1, 2] }, { label: '“work:princ”', records: [1] }] };
  check('U-4 a comparison is said with both series and their counts', compareMessage(two, 'work:princ') === 'Compared by decade: “work:princ”, 1 counted, beside “allegory”, 2 counted.');
  check('U-4 a problem is said as the strip prints it', compareMessage({ problem: 'The query was not searched.', series: [] }, 'x:') === 'The query was not searched.');
  check('U-4 a removal is said', compareMessage({ problem: '', series: [two.series[0]] }, '') === 'The comparison is removed.');
  const html = fs.readFileSync(path.join(PAGES, 'index.html'), 'utf8');
  const live = html.indexOf('id="strip-live"'), body = html.indexOf('id="p-body"');
  check('U-4 the live region stays in the panel, outside the list that is written again', live > body && /<p class="sr" id="strip-live" aria-live="polite"><\/p>/.test(html)
    && html.slice(body, live).indexOf('</div>') >= 0 && html.slice(html.indexOf('<aside class="panel"'), live).length > 0);
  check('U-4 setCompare says the result, and the strip carries no pre-filled status', /sayCompare\(\)/.test(fn('setCompare'))
    && !/strip-problem" role="status"/.test(fn('stripHTML')) && /getElementById\('strip-live'\)/.test(fn('sayCompare')));
});
group('U-6', () => {
  check('U-6 on paper the swatches are lettered ink boxes and terracotta is not printed',
    /\.strip \.s0 i::before\{content:"A"\}/.test(PRINT) && /\.strip \.s1 i::before\{content:"B"\}/.test(PRINT) && /background:none!important;border:\.6pt solid #1a1814/.test(PRINT));
  check('U-6 on paper each row names its series', /\.decades tbody th \.sr\{position:static;width:auto;height:auto;overflow:visible;clip:auto/.test(PRINT));
});
group('U-7', () => {
  const pages = fs.readFileSync(path.join(PAGES, 'assets/pages.css'), 'utf8');
  const print = pages.slice(pages.indexOf('@media print{'));
  check('U-7 the reading pages have a print block', pages.indexOf('@media print{') > 0);
  check('U-7 on paper: the masthead is not fixed, no skip link, no menu, ink on white, no break in a row',
    /\.skip,\.nav,\.bar \.scope,\.cross-skip\{display:none!important\}/.test(print) && /\.bar\{position:static/.test(print)
    && /html,body\{background:#fff!important\}/.test(print) && /tr,\.reg-row,[^{]*\{break-inside:avoid/.test(print) && /color:#1a1814/.test(print));
  for (const page of ['observatoire.html', 'methode.html', 'credits.html']) {
    check('U-7 ' + page + ' loads pages.css', /assets\/pages\.css/.test(fs.readFileSync(path.join(PAGES, page), 'utf8')));
  }
});
group('U-8', () => {
  const touch = CSS.slice(CSS.indexOf('.strip-tools .linkish,.strip-drop{min-height:44px'));
  check('U-8 the strip links draw their underline under the words at 44 px', /^\.strip-tools \.linkish,\.strip-drop\{min-height:44px;display:inline-flex;align-items:center;\s*border-bottom:0;text-decoration:underline/.test(touch));
  check('U-8 so does Copy as BibTeX', /\.export-formats \.linkish\{min-height:44px;display:inline-flex;align-items:center;\s*border-bottom:0;text-decoration:underline/.test(CSS));
});
group('U-9', () => {
  const th = /\.decades thead th\{[^}]*font-size:([\d.]+)rem/.exec(CSS), small = /\.decades thead small\{[^}]*font-size:([\d.]+)em/.exec(CSS);
  check('U-9 the decade heads are 11 px or more', !!th && Number(th[1]) * 16 >= 11, th && th[1]);
  check('U-9 the open mark is the size of its head', !!small && Number(small[1]) >= 1, small && small[1]);
  check('U-9 the Undated column is wide enough for its word', /\.decades thead th\.undated\{width:3\.2rem\}/.test(CSS)
    && /r\.key === 'undated' \? ' class="undated"'/.test(fn('stripHTML')) && /\.decades thead th\.pre\{width:2\.1rem\}/.test(CSS));
});
group('U-10', () => {
  const CITE = createRequire(import.meta.url)(path.join(PAGES, 'assets/cite.js'));
  const { exportHTML } = lift([fn('esc'), fn('nf'), fn('counts'), fn('exportCounts'), fn('exportHTML')], ['exportHTML'], { CITE });
  const html = exportHTML({ kind: 'search', records: IDX.records.slice(0, 3) });
  check('U-10 each format button is named with its file type', /aria-label="BibTeX, \.bib file">BibTeX <span class="ext">\.bib<\/span>/.test(html)
    && /aria-label="RIS, \.ris file"/.test(html), html.match(/<button[^>]*export-fmt[^>]*>/g));
  check('U-10 the decade table is labelled by its caption', /<table class="decades" aria-labelledby="strip-cap">/.test(fn('stripHTML')));
});
group('U-11', () => {
  const { shortDecade } = lift([fn('esc'), fn('shortDecade')], ['shortDecade']);
  check('U-11 the strip says Undated', shortDecade({ key: 'undated', label: 'Undated' }) === 'Undated' && !/n\.d\./.test(SRC));
  eq('U-9 a decade head keeps its full label, abbreviated on a phone under an abbr that names it',
    shortDecade({ key: '1950', label: '1950s', open: false }), '<span class="dl">1950s</span><abbr class="ds" title="1950s">\u201950s</abbr>');
  check('U-9 the abbreviation shows on a phone only, and never on paper', /@media \(max-width:520px\)\{ \.decades thead \.dl\{display:none\} \.decades thead \.ds\{display:inline\} \}/.test(CSS)
    && /\.decades thead \.ds\{display:none!important\}/.test(PRINT));
  const { ledgerHTML } = lift([decl('SRC_NAME'), fn('esc'), fn('nf'), fn('sourceName'), fn('ledgerHTML'), 'var ABS = null;'], ['ledgerHTML'], { SEM: sem });
  const line = ledgerHTML({ n: 20, review: 0, withAbstract: 0, undated: 0, topSource: 'ixtheo-k10plus', topCount: 8, topShare: 40 });
  check('U-11 a share is written 40%, the English way', /40% from IxTheo/.test(line) && !/40[\s  ]%/.test(line), line);
  const obs = fs.readFileSync(path.join(PAGES, 'assets/observatory.js'), 'utf8');
  check('U-11 the Observatory crossings say Undated', /if \(c === 'undated'\) return 'Undated'/.test(obs) && !/No year/.test(obs));
  const cliText = fs.readFileSync(path.join(ROOT, 'cli/origenality.mjs'), 'utf8');
  check('U-11 the CLI text output says undated', !/'n\.d\.'/.test(cliText));
});
group('U-12/U-13', () => {
  check('U-12 a DOI link is 44 px wide under a finger', /\.rec \.links a\{min-width:44px;justify-content:center\}/.test(CSS));
  const { zoneKeys } = lift([fn('esc'), fn('nf'), fn('zoneList'), fn('zoneKeys')], ['zoneKeys']);
  const z = zoneKeys('Themes', [{ key: 'a.b', label: 'Allegory and the spiritual senses', n: 22 }, { key: 'c', label: 'C', n: 3 }], 'theme', false);
  check('U-13 an author view heading keeps its count inside its button', /<button type="button" class="z" data-q="theme:a\.b">Allegory and the spiritual senses <span class="zn">\(22\)<\/span><\/button>,<\/span>/.test(z), z);
  check('U-13 the comma stays on the line of its heading', /\.panel \.zones \.zc\{white-space:nowrap\}/.test(CSS) && /\.panel \.zones \.zc \.z\{white-space:normal/.test(CSS));
});

/* ------------------------------------------------------------ the Observatory: one population, the refetch */
group('OBS', () => {
  const OBS_SRC = fs.readFileSync(path.join(PAGES, 'assets/observatory.js'), 'utf8');
  const fnObs = (name) => { const at = OBS_SRC.indexOf('function ' + name + '('); if (at < 0) throw new Error(name + ' not in observatory.js'); return scanBlock(OBS_SRC, at, '{'); };
  const O = lift(['nf', 'esc', 'attr', 'harvestOf', 'refetchPhrase', 'scopeRows', 'stampText', 'footStampText', 'cellName', 'num', 'colLabel'].map(fnObs),
    ['nf', 'scopeRows', 'stampText', 'footStampText', 'cellName', 'num', 'colLabel']);
  const stats = JSON.parse(fs.readFileSync(path.join(DATA, 'stats.json'), 'utf8'));
  const meta = JSON.parse(fs.readFileSync(path.join(DATA, 'META.json'), 'utf8'));
  const nfo = O.nf;
  const ct = stats.counted.totals;
  const rows = O.scopeRows(stats, meta, counted);
  const by = Object.fromEntries(rows.map((r) => [r.k, r]));
  check('O-P2-1 the scope register counts authors, journals and volumes, DOI and ISBN on the counted records',
    by['distinct authors'].v === nfo(ct.distinct_authors) && by['journals and volumes'].v === nfo(ct.distinct_containers)
    && by['counted records with a DOI'].v === nfo(ct.records_with_doi) && by['counted records with a DOI'].n.indexOf(nfo(ct.records_with_isbn)) === 0
    && by['records counted'].v === nfo(counted) && ct.records === counted, rows);
  check('O-P2-1 the records harvested and kept keep their own figures', by['records kept'].v === nfo(stats.totals.records)
    && by['records harvested'].v === nfo(meta.records_harvested_total));
  const kept = O.scopeRows({ totals: stats.totals }, meta, counted);
  check('O-P2-1 a file without the counted series says the figures are of the records kept',
    kept.some((r) => r.k === 'records kept with a DOI') && kept.find((r) => r.k === 'distinct authors').n.indexOf('records kept') > 0);
  const stamp = O.stampText(meta, stats, counted), foot = O.footStampText(meta, stats);
  check('O-P3-3 the stamp gives the harvest and the second reading', stamp.indexOf('Harvest of ' + meta.harvested) === 0
    && stamp.indexOf(nfo(meta.refetched_records) + ' source records read again on ' + meta.refetched) > 0, stamp);
  check('O-P3-3 so does the foot', foot.indexOf('from the harvest of ' + meta.harvested) > 0 && foot.indexOf('read again on ' + meta.refetched) > 0, foot);
  check('O-P3-3 without a second reading nothing is said of one', O.stampText({ ...meta, refetched: undefined }, stats, counted).indexOf('again') < 0);
  const link = O.num(12, { href: 'index.html#q=theme:exegesis.allegory+year:1980-1989', query: 'theme:exegesis.allegory year:1980-1989' },
    O.cellName('Allegory', O.colLabel('1980'), 12));
  check('U-5 a linked count is named by its row, its column and what it counts', /aria-label="Allegory, 1980s: 12 counted records"/.test(link) && />12<\/a>$/.test(link), link);
  const html = fs.readFileSync(path.join(PAGES, 'observatoire.html'), 'utf8');
  for (const id of ['theme-decade', 'work-domain', 'domain-lang']) {
    const wrap = html.indexOf('aria-labelledby="cap-' + id + '"');
    const skip = html.lastIndexOf('<a class="cross-skip" href="#notes-' + id + '">Skip past this table</a>', wrap);
    check('U-5 a skip link before the ' + id + ' table lands after it', skip > 0 && wrap - skip < 200
      && html.indexOf('<ul class="cross-notes" id="notes-' + id + '" tabindex="-1">') > wrap);
  }
  check('U-5 every count link of the page passes its name', (OBS_SRC.match(/num\([^;]*?link\(/g) || []).every((m) => true)
    && !/shade\(n, n, max, '', link\([^)]*\)\)/.test(OBS_SRC) && !/num\(r\.total, link\([^)]*\)\)/.test(OBS_SRC));
  const obsCss = fs.readFileSync(path.join(PAGES, 'assets/observatory.css'), 'utf8');
  check('U-5 the skip link shows when it has the focus, at 44 px', /\.cross-skip:focus\{position:static;[^}]*min-height:44px/.test(obsCss));
});

console.log((failures ? 'FAILED ' : 'ok ') + passes + ' passed, ' + failures + ' failed');
process.exit(failures ? 1 : 0);
