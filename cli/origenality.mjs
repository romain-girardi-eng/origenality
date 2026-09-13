#!/usr/bin/env node
/* origenality: the bibliographic map of Origen scholarship, for agents.
 *
 * The map answers one question a human can read off the screen: has this been
 * written about, and how thickly? This exposes the same answer to a program,
 * computed by the SAME code the page runs (site/assets/search-core.js), on the
 * index that same file builds, so a reader and an agent are never shown two
 * different bibliographies.
 *
 * It reads the published data files over HTTPS and caches them, so it works
 * from anywhere with no checkout; --local reads a checkout instead, in either
 * geometry: a public clone (data/, site/) or the working tree (site/data/,
 * site/build-c/).
 *
 * Exit status: 0 an answer, 1 a failure (network, missing record), 2 a usage
 * error or a query that could not be evaluated.
 *
 * Romain Girardi, 2026. MIT.
 */
import { createRequire } from 'node:module';
import { mkdirSync, readFileSync, writeFileSync, existsSync, statSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { homedir } from 'node:os';

const HERE = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

const SITE = 'https://origenality.com';
// [layer, path inside the layer]. The 'data' layer is data/ in a public clone
// and site/data/ in the working tree; the 'site' layer is site/ or site/build-c/.
const FILES = {
  graph: ['data', 'graph.json'],
  semantic: ['site', 'assets/semantic.json'],
  abstracts: ['data', 'abstracts.json'],
  // every subject heading and container of a record, which graph.json keeps
  // only when several records share one: the search reads them from here
  cite: ['data', 'cite.json'],
  primary: ['data', 'primary-layer-summary.json'],
  stats: ['data', 'stats.json'],
  evidence: ['data', 'evidence.json'],
};
const CACHE = join(process.env.XDG_CACHE_HOME || join(homedir(), '.cache'), 'origenality');
const MAX_AGE_MS = 12 * 60 * 60 * 1000;

class UsageError extends Error {}
const usage = (message) => { throw new UsageError(message); };

/* ------------------------------------------------------------------ loading */

function layout(root) {
  return existsSync(join(root, 'site/build-c/assets/search-core.js'))
    ? { data: 'site/data', site: 'site/build-c' }
    : { data: 'data', site: 'site' };
}

async function load(name, opts) {
  const [layer, file] = FILES[name];
  if (opts.local) {
    const path = join(opts.local, layout(opts.local)[layer], file);
    if (!existsSync(path)) {
      usage(`--local ${opts.local}: ${file} is in neither data/ nor site/data/ (or site/assets/).`);
    }
    return JSON.parse(readFileSync(path, 'utf8'));
  }
  const remote = `${layer}/${file}`;
  const path = join(CACHE, name + '.json');
  if (!opts.refresh && existsSync(path) && Date.now() - statSync(path).mtimeMs < MAX_AGE_MS) {
    return JSON.parse(readFileSync(path, 'utf8'));
  }
  const res = await fetch(`${SITE}/${remote}`, { headers: { 'user-agent': 'origenality-cli' } });
  if (!res.ok) throw new Error(`${remote}: HTTP ${res.status}`);
  const text = await res.text();
  mkdirSync(CACHE, { recursive: true });
  writeFileSync(path, text);
  return JSON.parse(text);
}

function core(opts) {
  // the very file the page loads, resolved as a path, never as a package name
  const candidates = opts.local
    ? [join(opts.local, layout(opts.local).site, 'assets/search-core.js')]
    : [join(HERE, '..', 'site/assets/search-core.js'), join(HERE, '..', 'site/build-c/assets/search-core.js')];
  return require(resolve(candidates.find((p) => existsSync(p)) || candidates[0]));
}

function crossingsCore(opts) {
  // the file the Observatory loads, found the way search-core.js is found
  const candidates = opts.local
    ? [join(opts.local, layout(opts.local).site, 'assets/observatory-core.js')]
    : [join(HERE, '..', 'site/assets/observatory-core.js'), join(HERE, '..', 'site/build-c/assets/observatory-core.js')];
  return require(resolve(candidates.find((p) => existsSync(p)) || candidates[0]));
}

/* ------------------------------------------------------------------ output */

function record(p, score) {
  return {
    id: p.ppn, source_ids: p.sourceIds, title: p.title, year: p.year, lang: p.lang, type: p.type,
    authors: p.authors, container: p.container || undefined,
    themes: p.themes, works: p.works,
    counts_in_density: p.dens,
    url: p.url || undefined, doi: p.doi || undefined,
    abstract: p.abstract ? p.abstract.slice(0, 600) : undefined,
    abstract_source: p.abstractSource || undefined,
    terms_matched: score,
  };
}

/* What a headline figure rests on (Method, section 4), computed on the counted
   records that figure counts: the same tally the Explorer prints under it. */
function reliability(recs, C) {
  const bySource = {};
  recs.forEach((p) => { if (p.src) bySource[p.src] = (bySource[p.src] || 0) + 1; });
  const top = Object.keys(bySource).sort((a, b) => (bySource[b] - bySource[a]) || (a < b ? -1 : 1))[0];
  return {
    counted: recs.length,
    review_flagged: recs.filter((p) => p.review).length,
    with_abstract: recs.filter((p) => p.abstract).length,
    no_year: recs.filter((p) => !C.isDated(p)).length,
    top_source: top
      ? { source: top, records: bySource[top], share_pct: Math.round((bySource[top] * 100) / recs.length) }
      : null,
  };
}

function verdict(r, records, scope, limit, C) {
  const hits = r.order.filter((i) => !r.vocabOnly.has(i));
  const shelf = r.order.filter((i) => r.vocabOnly.has(i));
  const perTerm = {}, perTermCounted = {};
  r.terms.forEach((t, k) => { perTerm[t] = r.termHits[k]; perTermCounted[t] = r.termHitsCounted[k]; });
  // the headline: with several terms, the counted records carrying every one
  const k = r.terms.length;
  const headline = hits.filter((i) => records[i].dens && (k < 2 || r.scores[i] >= k));
  const excluded = [...r.exclude, ...r.excludePhrases];
  return {
    query_terms: r.terms,
    dropped_terms: r.droppedTerms,
    terms_absent_from_corpus: r.absentTerms,
    terms_absent_under_filters: r.absentUnderFilters,
    // only when cite.json could not be read: the index then lacks most headings
    terms_not_found_partial_index: r.fields === 'partial' ? r.absentFromPartialIndex : undefined,
    searched_fields: scope.searchedFields,
    per_term: perTerm,
    per_term_counted: perTermCounted,
    carrying_all_terms: r.fullHit,
    carrying_all_terms_counted: r.fullHitCounted,
    widened: r.widened,
    widened_to_terms: r.widened ? r.hitDepth : undefined,
    listed: hits.length,
    counted_in_density: hits.filter((i) => records[i].dens).length,
    corpus_density_total: scope.records.filter((p) => p.dens).length,
    filed_under_heading: r.vocabHit || undefined,
    filed_under_heading_counted: r.vocabHit ? r.vocabHitCounted : undefined,
    heading: r.vocabHit ? r.heading : undefined,
    reliability: reliability(headline.map((i) => records[i]), C),
    filters: r.filters.length
      ? r.filters.map((f) => ({ field: f.field, value: f.value, negated: f.neg })) : undefined,
    phrases: r.phrases.length ? r.phrases : undefined,
    excluded: excluded.length ? excluded : undefined,
    restricted_to: scope.echo,
    results: hits.slice(0, limit).map((i) => record(records[i], r.scores[i])),
    shelf_only: shelf.slice(0, limit).map((i) => record(records[i], 0)),
  };
}

const n = (x) => String(x).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
const count = (x, one, many) => `${n(x)} ${x === 1 ? one : many}`;
const quoted = (terms) => terms.map((t) => `"${t}"`).join(', ');

function absence(v) {
  const bits = [];
  const a = v.terms_absent_from_corpus, f = v.terms_absent_under_filters;
  if (a.length) bits.push(`${quoted(a)} ${a.length === 1 ? 'appears' : 'appear'} in none of the records`);
  if (f.length) bits.push(`${quoted(f)} ${f.length === 1 ? 'appears' : 'appear'} in none of the records your filters leave`);
  const p = v.terms_not_found_partial_index || [];
  if (p.length) {
    bits.push(`${quoted(p)} ${p.length === 1 ? 'is' : 'are'} not in the fields read, and the subject headings `
      + 'file could not be read, so nothing is called absent');
  }
  return bits.join('; ');
}

function sentence(v) {
  const k = v.query_terms.length;
  const total = n(v.corpus_density_total);
  // how many counted works each term reaches: a term that reaches most of the
  // corpus narrows the question very little
  const reach = k > 1
    ? ' Reach of each term, in counted works: '
      + Object.keys(v.per_term_counted).map((t) => `${t} ${n(v.per_term_counted[t])}`).join(' · ') + '.'
    : '';
  if (k > 1 && v.widened) {
    const all = v.carrying_all_terms_counted;
    let s = all
      ? `${count(all, 'counted work carries', 'counted works carry')} all ${k} of your terms, of ${total}`
      : `No counted work carries all ${k} of your terms`;
    if (absence(v)) s += `: ${absence(v)}`;
    return `${s}. Widened to ${v.widened_to_terms} of ${k}: ${n(v.listed)} listed, `
      + `${n(v.counted_in_density)} counted.${reach}`;
  }
  if (!v.counted_in_density && v.filed_under_heading) {
    if (!v.filed_under_heading_counted) {
      return `No counted work is filed under "${v.heading}"; `
        + `${count(v.filed_under_heading, 'record filed there is', 'records filed there are')} listed, `
        + 'none of them counted in the density figures.';
    }
    return `${count(v.filed_under_heading_counted, 'work is', 'works are')} filed under "${v.heading}", of ${total}; `
      + 'none names it in so many words.';
  }
  // Never announce 0 over a list of records: those are records the density
  // figures do not count, and saying so is the honest form.
  if (!v.counted_in_density && v.listed) {
    return `${count(v.listed, 'record', 'records')} listed, none of them counted in the density figures `
      + `(they mention Origen rather than study him), of ${total}.`;
  }
  let s = `${count(v.counted_in_density, 'work matches', 'works match')} of ${total}`;
  if (v.filed_under_heading_counted) s += ` · ${n(v.filed_under_heading_counted)} filed under "${v.heading}"`;
  if (!v.listed && absence(v)) s += `: ${absence(v)}`;
  return s + '.' + reach;
}

/* A query the engine refused to evaluate. The reason goes to stderr, and to
   stdout as JSON when a program is reading. */
function refusal(r) {
  if (r.invalid) {
    return {
      error: 'query_not_understood',
      message: `The query was not evaluated. ${r.errors.map((e) => e.message).join(' ')}`,
      query_errors: r.errors.map(({ kind, token, field, value, message }) => ({ kind, token, field, value, message })),
    };
  }
  return {
    error: 'no_searchable_term',
    message: 'The query holds no searchable term, so nothing was searched. Words under three '
      + 'letters and common stopwords are ignored'
      + (r.droppedTerms.length ? ` (here: ${r.droppedTerms.join(', ')}).` : '.'),
    dropped_terms: r.droppedTerms,
  };
}

/* One author node of graph.json and the records its aut edges reach, counted
   as the Explorer's author view counts them (explorer.js, authorSummary): the
   name as the catalogue writes it, never matched as a prefix and never merged
   with another spelling, since the data holds no link between two nodes. */
function authorIndex(graph, records) {
  const at = new Map(records.map((p) => [p.nodeIndex, p]));
  const nodes = graph.nodes || [];
  const byId = new Map(), ofPub = new Map();
  for (const e of graph.edges || []) {
    if (e.r !== 'aut') continue;
    const p = at.get(e.s), node = nodes[e.t];
    if (!p || !node || node.k !== 'author' || !node.id || !node.label) continue;
    let a = byId.get(node.id);
    if (!a) { a = { id: node.id, label: node.label, pubs: [] }; byId.set(node.id, a); }
    if (a.pubs.includes(p)) continue;
    a.pubs.push(p);
    if (!ofPub.has(p.i)) ofPub.set(p.i, []);
    ofPub.get(p.i).push(a);
  }
  return { byId, ofPub };
}

function authorView(a, idx, sem, records, limit, C) {
  const byYear = (x, y) => {
    const dx = C.isDated(x), dy = C.isDated(y);
    if (dx !== dy) return dx ? -1 : 1;
    if (dx && Number(x.year) !== Number(y.year)) return Number(x.year) - Number(y.year);
    const tx = x.sortTitle || '', ty = y.sortTitle || '';
    return tx < ty ? -1 : tx > ty ? 1 : x.i - y.i;
  };
  const cmp = (x, y) => (x < y ? -1 : x > y ? 1 : 0);
  const keyCounts = (recs, field, vocab) => {
    const n = {};
    recs.forEach((p) => (p[field] || []).forEach((k) => { n[k] = (n[k] || 0) + 1; }));
    return Object.keys(n).map((key) => ({ key, label: vocab[key] ? vocab[key].label : key, counted: n[key] }))
      .sort((x, y) => (y.counted - x.counted) || cmp(x.key, y.key));
  };
  const listed = a.pubs.slice().sort(byYear);
  const dens = listed.filter((p) => p.dens);
  const rel = reliability(dens, C);
  const languages = {}, inContainer = {};
  dens.forEach((p) => {
    languages[p.lang || ''] = (languages[p.lang || ''] || 0) + 1;
    if (p.container) inContainer[p.container] = (inContainer[p.container] || 0) + 1;
  });
  const others = new Map();
  listed.forEach((p) => (idx.ofPub.get(p.i) || []).forEach((o) => { if (o.id !== a.id) others.set(o.id, o.label); }));
  return {
    id: a.id, label: a.label,
    note: 'Records filed under this exact form of the name in the harvested catalogues. '
      + 'Other spellings of the same scholar are separate author entries and are not merged.',
    listed: listed.length, counted_in_density: dens.length,
    mentioned_only: listed.filter((p) => !p.dens && p.rel !== 'none').length,
    held_aside: listed.filter((p) => p.rel === 'none').length,
    corpus_density_total: records.filter((p) => p.dens).length,
    by_decade: dens.reduce((m, p) => {
      if (!C.isDated(p)) return m;
      const d = Math.floor(Number(p.year) / 10) * 10;
      m[d] = (m[d] || 0) + 1; return m;
    }, {}),
    counted_undated: dens.filter((p) => !C.isDated(p)).length,
    review_flagged: rel.review_flagged,
    with_abstract: rel.with_abstract,
    no_year: rel.no_year,
    top_source: rel.top_source,
    themes: keyCounts(dens, 'themes', sem.themes || {}),
    works: keyCounts(dens, 'works', sem.works || {}),
    approaches: keyCounts(dens, 'approaches', sem.approaches || {}),
    languages,
    containers: Object.keys(inContainer).map((title) => ({ title, counted: inContainer[title] }))
      .sort((x, y) => (y.counted - x.counted) || cmp(x.title, y.title)),
    co_authors: [...others].map(([id, label]) => ({ id, label }))
      .sort((x, y) => cmp(C.norm(x.label), C.norm(y.label)) || cmp(x.id, y.id)),
    results: listed.slice(0, limit).map((p) => record(p, 0)),
  };
}

/* ------------------------------------------------------------------ commands */

const USAGE = `origenality: the map of Origen scholarship, for programs

  search <query>        what has been written on this, counted
  gap <query>           the same, framed as: is this ground already taken? (JSON)
  record <id>           one work cluster by Origenality ID or source record ID
  vocabulary [kind]     the controlled vocabulary (themes|works|approaches|domains)
  density <kind> <key>  how thick one heading is, by decade (theme|work|approach|domain)
  crossings <view>      the Observatory's crossings (theme-decade|work-domain|domain-lang)
  author <id|name>      one author entry as the catalogues write the name: records,
                        decades, headings, co-authors (a:crouzel-henri, or "Crouzel, Henri")
  stats                 the harvest, counted: data/stats.json as published; its top-level
                        series count the kept records, "counted" holds the same series
                        on the counted records (core and partial), "population" says which
  coverage              what the corpus cannot answer, in figures
  primary               the primary layer: editions, translations and manuscript
                        witnesses of Origen's own works, never counted in a density
  claims [query]        source-anchored scholar positions; withheld quotes stay withheld

Query grammar (search and gap)
  author:crouzel        the author            year:1971  year:1971-1990  year:<1900
  lang:fr   type:book   ISO 639 language code (fre, ger, arm are accepted), document type
  work:cels             a work of Origen      theme:exegesis   domain:  approach:
  in:adamantius         the journal or volume it sits in
  "free will"           an exact phrase       -rufinus   a term that must not appear
  Filters are conjunctive and never widened: year:1971 does not mean thereabouts.
  A year condition holds for dated records only. A query with an unknown field, an
  invalid year, an unknown language, type or key, or an unclosed quotation mark is
  not evaluated: the CLI says why and exits with status 2.

Options
  --json                machine-readable (default for every command but search)
  --limit N             results to return, 0 or more (default 10): search, gap, density, author, claims
  --local PATH          read a checkout instead of origenality.com
  --refresh             ignore the 12-hour cache
  --lang CODE[,CODE]    restrict to these languages: search, gap, density, vocabulary
  --since YEAR          restrict to records dated YEAR or later: same commands
  --until YEAR          restrict to records dated YEAR or earlier: same commands

Exit status: 0 an answer, 1 a failure (network, missing record), 2 a usage error
or a query that could not be evaluated.

Every figure is computed by site/assets/search-core.js, the file the website
itself runs, on the index that file builds; the crossings by
site/assets/observatory-core.js, the file the Observatory runs. "counts_in_density" marks a record
judged to be ABOUT Origen; the rest are listed but never counted, which is why
two figures are reported.`;

const FILTERING = ['--json', '--limit', '--local', '--refresh', '--lang', '--since', '--until'];
const ACCEPTS = {
  search: FILTERING,
  gap: FILTERING,
  density: FILTERING,
  vocabulary: ['--json', '--local', '--refresh', '--lang', '--since', '--until'],
  record: ['--json', '--local', '--refresh'],
  coverage: ['--json', '--local', '--refresh'],
  stats: ['--json', '--local', '--refresh'],
  crossings: ['--json', '--local', '--refresh'],
  author: ['--json', '--limit', '--local', '--refresh'],
  primary: ['--json', '--local', '--refresh'],
  claims: ['--json', '--limit', '--local', '--refresh'],
};
const WITH_VALUE = new Set(['--limit', '--local', '--lang', '--since', '--until']);

const KINDS = {
  theme: 'themes', themes: 'themes', work: 'works', works: 'works',
  approach: 'approaches', approaches: 'approaches', domain: 'domains', domains: 'domains',
};
const SINGULAR = { themes: 'theme', works: 'work', approaches: 'approach', domains: 'domain' };

function parse(argv) {
  const o = { _: [], limit: 10, json: false, given: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-h' || a === '--help') { o.help = true; continue; }
    if (!a.startsWith('--')) { o._.push(a); continue; }
    if (!(a in { '--json': 1, '--refresh': 1 }) && !WITH_VALUE.has(a)) usage(`Unknown option ${a}.`);
    o.given.push(a);
    if (a === '--json') { o.json = true; continue; }
    if (a === '--refresh') { o.refresh = true; continue; }
    const v = argv[i + 1];
    if (v === undefined || v.startsWith('--')) usage(`${a} needs a value.`);
    i++;
    if (a === '--limit') {
      if (!/^\d+$/.test(v)) usage(`--limit takes a whole number, 0 or more; got "${v}".`);
      o.limit = Number(v);
    } else if (a === '--since' || a === '--until') {
      if (!/^\d{1,4}$/.test(v)) usage(`${a} takes a year such as 1990; got "${v}".`);
      o[a.slice(2)] = Number(v);
    } else if (a === '--lang') {
      o.lang = v.split(',').map((c) => c.trim()).filter(Boolean);
      if (!o.lang.length) usage('--lang needs at least one language code.');
    } else if (a === '--local') {
      if (!existsSync(v)) usage(`--local ${v}: no such directory.`);
      o.local = v;
    }
  }
  if (o.since != null && o.until != null && o.since > o.until) {
    usage(`--since ${o.since} is later than --until ${o.until}.`);
  }
  return o;
}

/* --lang, --since and --until restrict the population the engine reads; they go
   through the same language resolution as lang: in a query. */
function restriction(o, C, records) {
  const tests = [], echo = {};
  if (o.lang) {
    const codes = o.lang.map((code) => {
      const resolved = C.resolveLanguage(code);
      if (!resolved) usage(`--lang: unknown language "${code}"; use ISO 639 codes such as en,fr,de.`);
      return resolved;
    });
    tests.push((p) => codes.includes(C.languageCode(p.rawlang)));
    echo.lang = codes;
  }
  if (o.since != null) { tests.push((p) => C.isDated(p) && Number(p.year) >= o.since); echo.since = o.since; }
  if (o.until != null) { tests.push((p) => C.isDated(p) && Number(p.year) <= o.until); echo.until = o.until; }
  const keep = tests.length ? (p) => tests.every((t) => t(p)) : null;
  return { keep, echo: tests.length ? echo : undefined, records: keep ? records.filter(keep) : records };
}

function print(value) { console.log(JSON.stringify(value, null, 2)); }

async function main(argv) {
  const o = parse(argv);
  const cmd = o._[0];
  if (o.help || (!cmd && !o.given.length)) { console.log(USAGE); return 0; }
  // an option with no command is a usage error, not a request for help
  if (!cmd) usage(`${o.given[0]} needs a command before it.`);
  if (!ACCEPTS[cmd]) usage(`Unknown command "${cmd}".`);
  for (const flag of o.given) if (!ACCEPTS[cmd].includes(flag)) usage(`${cmd} does not take ${flag}.`);

  if (cmd === 'primary') {
    // A separate layer, deliberately: these are the texts, not the studies.
    // Counting them among the scholarship would say the field is larger than
    // it is, so they are served, and never counted.
    if (o._.length > 1) usage('usage: origenality primary');
    print(await load('primary', o));
    return 0;
  }

  if (cmd === 'stats') {
    if (o._.length > 1) usage('usage: origenality stats');
    print(await load('stats', o));
    return 0;
  }

  if (cmd === 'claims') {
    const data = await load('evidence', o);
    const query = o._.slice(1).join(' ').toLowerCase();
    const claims = (data.claims || []).filter((claim) => {
      if (!query) return true;
      const hay = [claim.statement, claim.scholar && claim.scholar.name,
        ...(claim.author_vocabulary || []),
        ...(claim.about || []).map((entry) => entry.id)].join(' ').toLowerCase();
      return hay.includes(query);
    });
    print({
      schema_version: data.schema_version,
      query: query || undefined,
      claims: claims.slice(0, o.limit),
      matched: claims.length,
      note: data.policy && data.policy.statement,
    });
    return 0;
  }

  if (cmd === 'crossings') {
    // the Observatory's three tables, counted by the file the page runs
    const X = crossingsCore(o);
    if (o._.length !== 2 || !X.VIEWS.includes(o._[1])) {
      usage(`usage: origenality crossings <${X.VIEWS.join('|')}>`);
    }
    const [graph, sem] = await Promise.all([load('graph', o), load('semantic', o)]);
    print(X.crossing(o._[1], graph, sem));
    return 0;
  }

  if (cmd === 'record' && (!o._[1] || o._.length > 2)) usage('usage: origenality record <id>');
  if (cmd === 'coverage' && o._.length > 1) usage('usage: origenality coverage');
  if (cmd === 'author' && !o._.slice(1).join(' ').trim()) usage('usage: origenality author <id|name>');
  if (cmd === 'density' && (o._.length !== 3)) {
    usage('usage: origenality density <theme|work|approach|domain> <key>');
  }
  if (cmd === 'density' && !KINDS[o._[1].toLowerCase()]) {
    usage(`Unknown kind "${o._[1]}"; use theme, work, approach or domain.`);
  }
  if (cmd === 'vocabulary' && o._.length > 2) usage('usage: origenality vocabulary [themes|works|approaches|domains]');
  if (cmd === 'vocabulary' && o._[1] && !KINDS[o._[1].toLowerCase()]) {
    usage(`Unknown vocabulary kind "${o._[1]}"; use themes, works, approaches or domains.`);
  }
  if ((cmd === 'search' || cmd === 'gap') && !o._.slice(1).join(' ').trim()) {
    usage(`usage: origenality ${cmd} <query>`);
  }

  const [graph, sem, abstracts, cite] = await Promise.all([
    load('graph', o), load('semantic', o), load('abstracts', o), load('cite', o),
  ]);
  const C = core(o);
  const index = C.buildIndex(graph, sem, abstracts, cite);
  const records = index.records;
  const scope = restriction(o, C, records);
  scope.searchedFields = C.searchedFields(index);

  if (cmd === 'author') {
    // the node by its id, or by its label exactly as the catalogue writes it,
    // or by that label with case and accents folded when only one node has it
    const wanted = o._.slice(1).join(' ').trim();
    const idx = authorIndex(graph, records);
    const all = [...idx.byId.values()];
    let found = idx.byId.get(wanted) ? [idx.byId.get(wanted)] : all.filter((a) => a.label === wanted);
    if (!found.length) found = all.filter((a) => C.norm(a.label) === C.norm(wanted));
    if (found.length !== 1) {
      const near = found.length ? found
        : all.filter((a) => C.norm(a.label).startsWith(C.norm(wanted).split(/[\s,]+/)[0] || '\u0000'));
      console.error(found.length
        ? `origenality: ${found.length} author entries are written "${wanted}"; name one by its id.`
        : `origenality: no author entry is written "${wanted}".`);
      print({ error: found.length ? 'ambiguous_author' : 'unknown_author', author: wanted,
        did_you_mean: near.slice(0, 8).map((a) => ({ id: a.id, label: a.label })) });
      return 1;
    }
    print(authorView(found[0], idx, sem, records, o.limit, C));
    return 0;
  }

  if (cmd === 'vocabulary') {
    const kinds = o._[1] ? [KINDS[o._[1].toLowerCase()]] : ['domains', 'themes', 'works', 'approaches'];
    const out = {};
    for (const k of kinds) {
      out[k] = index.keys[k].map((key) => {
        const v = sem[k][key];
        const tagged = scope.records.filter((p) => p[k].includes(key));
        return {
          key, label: v.label, labels: v.labels || {}, aliases: v.aliases || [],
          records: tagged.length, counted_in_density: tagged.filter((p) => p.dens).length,
        };
      }).sort((a, b) => (b.records - a.records) || (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
    }
    if (scope.echo) out.restricted_to = scope.echo;
    print(out);
    return 0;
  }

  if (cmd === 'density') {
    // One rule with search: the heading is the query work:<key> (or theme:,
    // approach:, domain:), a key or the beginning of one, over the population
    // the options leave.
    const [, kind, key] = o._;
    const field = KINDS[kind.toLowerCase()];
    const r = /[\s"“”«»]/.test(key)
      ? { invalid: true, errors: [{ message: `"${key}" is not a vocabulary key.` }] }
      : C.search(index, `${SINGULAR[field]}:${key}`, { keep: scope.keep });
    if (r.invalid) {
      const k = C.norm(key);
      const head = k.split('.')[0];
      const near = index.keys[field]
        .filter((x) => x.includes(k) || (head && x.startsWith(head)) || k.startsWith(x.split('.')[0]))
        .slice(0, 8);
      const message = r.errors.map((e) => e.message).join(' ');
      console.error(`origenality: ${message}`);
      print({ error: 'unknown_key', kind: SINGULAR[field], key, message, did_you_mean: near });
      return 2;
    }
    const hits = r.order.filter((i) => !r.vocabOnly.has(i));
    const dens = hits.filter((i) => records[i].dens).map((i) => records[i]);
    const rel = reliability(dens, C);
    const nk = C.norm(key);
    print({
      kind: SINGULAR[field], key,
      label: sem[field][key] ? sem[field][key].label : undefined,
      matched_keys: index.keys[field].filter((x) => C.norm(x).startsWith(nk)),
      restricted_to: scope.echo,
      listed: hits.length, counted_in_density: dens.length,
      corpus_density_total: scope.records.filter((p) => p.dens).length,
      by_decade: dens.reduce((m, p) => {
        if (!C.isDated(p)) return m;
        const d = Math.floor(Number(p.year) / 10) * 10;
        m[d] = (m[d] || 0) + 1; return m;
      }, {}),
      counted_undated: dens.filter((p) => !C.isDated(p)).length,
      // what the figure rests on (Method, section 4), on the counted records
      review_flagged: rel.review_flagged,
      with_abstract: rel.with_abstract,
      no_year: rel.no_year,
      top_source: rel.top_source,
      results: dens.slice(0, o.limit).map((p) => record(p, 0)),
    });
    return 0;
  }

  if (cmd === 'record') {
    const wanted = o._[1];
    const p = records.find((x) => x.ppn === wanted ||
      (x.sourceIds || []).some((entry) => entry.id === wanted || `${entry.source}:${entry.id}` === wanted));
    if (!p) { console.error(`origenality: no work cluster or source record has the ID ${wanted}.`); return 1; }
    print({ ...record(p, 0), abstract: p.abstract || undefined,
      subjects: p.subjects, domains: p.domains, approaches: p.approaches,
      relevance: p.relevance });
    return 0;
  }

  if (cmd === 'coverage') {
    const total = records.length;
    const pct = (x) => Math.round((x / total) * 1000) / 10;
    print({
      records: total,
      counted_in_density: records.filter((p) => p.dens).length,
      with_abstract: records.filter((p) => p.abstract).length,
      with_abstract_pct: pct(records.filter((p) => p.abstract).length),
      // every heading of a record, read from cite.json, not only those graph.json keeps
      with_subjects: records.filter((p) => p.subjects.length).length,
      with_theme_tag: records.filter((p) => p.themes.length).length,
      // the index drops the "unspecified" sentinel, a study that names no work
      // of Origen, so a non-empty works list is a work named
      naming_a_work_of_origen: records.filter((p) => p.works.length).length,
      with_doi: records.filter((p) => p.doi).length,
      by_language: records.reduce((m, p) => (m[p.lang || '?'] = (m[p.lang || '?'] || 0) + 1, m), {}),
      searched_fields: scope.searchedFields,
      caveat: `A search reads ${scope.searchedFields.join(', ')}. Where the abstract is missing `
        + '(the majority of the corpus), a subject is only findable if its words are in the title, '
        + 'the subject headings or the name of the journal or volume. A term found in none of '
        + 'these fields may still be treated inside a record, so absence of a hit is weaker '
        + 'evidence than presence of one.',
    });
    return 0;
  }

  // search, gap
  const q = o._.slice(1).join(' ');
  const r = C.search(index, q, { keep: scope.keep });
  if (r.invalid || r.normalisedEmpty) {
    const why = refusal(r);
    console.error(`origenality: ${why.message}`);
    if (o.json || cmd === 'gap') print({ [cmd === 'gap' ? 'question' : 'query']: q, ...why });
    return 2;
  }
  const v = verdict(r, records, scope, o.limit, C);
  if (o.json || cmd === 'gap') {
    print(cmd === 'gap' ? { question: q, answer: sentence(v), ...v } : v);
  } else {
    console.log(sentence(v));
    for (const hit of v.results) {
      console.log(`  ${hit.year || 'undated'}  ${hit.title}${hit.authors.length ? '  · ' + hit.authors.join('; ') : ''}`);
    }
    if (v.shelf_only.length) {
      console.log(`  filed under "${v.heading}":`);
      for (const hit of v.shelf_only.slice(0, 5)) console.log(`  ${hit.year || 'undated'}  ${hit.title}`);
    }
  }
  return 0;
}

main(process.argv.slice(2)).then((code) => { process.exitCode = code; }).catch((e) => {
  if (e instanceof UsageError) {
    console.error(`origenality: ${e.message}\nRun "origenality --help" for the commands and options.`);
    process.exitCode = 2;
    return;
  }
  console.error(`origenality: ${String(e.message || e)}`);
  process.exitCode = 1;
});
