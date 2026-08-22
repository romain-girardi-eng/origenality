#!/usr/bin/env node
/* origenality — the bibliographic map of Origen scholarship, for agents.
 *
 * The map answers one question a human can read off the screen: has this been
 * written about, and how thickly? This exposes the same answer to a program,
 * computed by the SAME code the page runs (site/assets/search-core.js), so a
 * reader and an agent are never shown two different bibliographies.
 *
 * It reads the published data files over HTTPS and caches them, so it works
 * from anywhere with no checkout; --local reads a working tree instead.
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
const FILES = {
  graph: ['data/graph.json', 'data/graph.json'],
  semantic: ['site/assets/semantic.json', 'site/assets/semantic.json'],
  abstracts: ['data/abstracts.json', 'data/abstracts.json'],
  primary: ['data/primary-layer-summary.json', 'data/primary-layer-summary.json'],
  stats: ['data/stats.json', 'data/stats.json'],
};
const CACHE = join(process.env.XDG_CACHE_HOME || join(homedir(), '.cache'), 'origenality');
const MAX_AGE_MS = 12 * 60 * 60 * 1000;

/* ------------------------------------------------------------------ loading */

async function load(name, opts) {
  const [remote, local] = FILES[name];
  if (opts.local) return JSON.parse(readFileSync(join(opts.local, local), 'utf8'));
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
  // the very file the page loads — resolved as a path, never as a package name
  const p = resolve(opts.local
    ? join(opts.local, 'site/assets/search-core.js')
    : join(HERE, '..', 'site/assets/search-core.js'));
  return require(p);
}

/* ------------------------------------------------------------------ model */

/* Rebuilds exactly the index the page builds in explorer.js: the free-text
   `hay` and the controlled-vocabulary `vocab`. Any drift here is caught by
   scripts/check_search_parity.py. */
function buildCorpus(graph, sem, abstracts) {
  const N = graph.nodes, E = graph.edges;
  const aut = new Map(), sub = new Map(), inn = new Map();
  for (const e of E) {
    const m = e.r === 'aut' ? aut : e.r === 'sub' ? sub : inn;
    if (!m.has(e.s)) m.set(e.s, []);
    m.get(e.s).push(e.t);
  }
  const LANG = { eng: 'English', ger: 'German', ita: 'Italian', fre: 'French', spa: 'Spanish' };
  const norm = (s) => (s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  const alt = (e) => (e && e.labels ? ['de', 'fr', 'it'].map((k) => e.labels[k]).filter(Boolean).join(' · ') : '');
  const ali = (e) => (e && e.aliases && e.aliases.length ? e.aliases.join(' · ') : '');
  const byPpn = (abstracts && abstracts.byPpn) || {};

  const out = [];
  N.forEach((n, idx) => {
    if (n.k !== 'p' && !n.title) return;
    const tag = (sem.byPpn && sem.byPpn[n.ppn]) || {};
    const themes = tag.t || [], works = tag.w || [], appr = tag.a || [];
    const doms = [...new Set(themes.map((t) => sem.themes[t] && sem.themes[t].domain).filter(Boolean))];
    const authors = (aut.get(idx) || []).map((t) => N[t].label);
    const subjects = (sub.get(idx) || []).map((t) => N[t].label);
    const container = (inn.get(idx) || []).map((t) => N[t].label)[0] || '';
    const ab = byPpn[n.ppn] || null;

    const semWords = themes.flatMap((t) => [sem.themes[t] && sem.themes[t].label, alt(sem.themes[t])]);
    const vocabWords = [
      ...themes.flatMap((t) => [sem.themes[t] && sem.themes[t].label, alt(sem.themes[t]), ali(sem.themes[t])]),
      ...doms.flatMap((d) => [sem.domains[d] && sem.domains[d].label, alt(sem.domains[d]), ali(sem.domains[d])]),
      ...works.flatMap((w) => [sem.works[w] && sem.works[w].label, alt(sem.works[w]), ali(sem.works[w])]),
      ...appr.flatMap((a) => [sem.approaches[a] && sem.approaches[a].label, alt(sem.approaches[a]), ali(sem.approaches[a])]),
    ];

    out.push({
      i: out.length,
      ppn: n.ppn, title: n.title, year: n.year, lang: n.lang || '',
      type: n.type, url: n.url, doi: n.doi || '',
      authors, subjects, container,
      themes, works, approaches: appr, domains: doms,
      // the fields the advanced grammar filters on (author:, type:, in:, …)
      relevance: tag.r || 'none',
      dens: tag.r === 'core' || tag.r === 'partial',
      abstract: ab ? ab.t : '',
      abstractSource: ab ? ab.s : '',
      hay: norm([n.title, authors.join(' '), subjects.join(' '), container,
        n.year || '', LANG[n.lang] || 'Other or none', semWords.filter(Boolean).join(' '),
        ab ? ab.t : ''].join(' ')),
      vocab: norm(vocabWords.filter(Boolean).join(' · ')),
    });
  });
  return out;
}

/* ------------------------------------------------------------------ output */

function record(p, score) {
  return {
    ppn: p.ppn, title: p.title, year: p.year, lang: p.lang, type: p.type,
    authors: p.authors, container: p.container || undefined,
    themes: p.themes, works: p.works,
    counts_in_density: p.dens,
    url: p.url, doi: p.doi || undefined,
    abstract: p.abstract ? p.abstract.slice(0, 600) : undefined,
    abstract_source: p.abstractSource || undefined,
    terms_matched: score,
  };
}

function verdict(r, corpus, limit) {
  const total = corpus.filter((p) => p.dens).length;
  const hits = [...r.matched]
    .filter((i) => !r.vocabOnly.has(i))
    .sort((a, b) => (r.scores[b] - r.scores[a]) || (corpus[b].year || 0) - (corpus[a].year || 0));
  const shelf = [...r.vocabOnly];
  return {
    query_terms: r.terms,
    terms_absent_from_corpus: r.absentTerms,
    carrying_all_terms: r.fullHit,
    widened: r.relaxed,
    widened_to_terms: r.relaxed ? r.hitDepth : undefined,
    listed: hits.length,
    counted_in_density: hits.filter((i) => corpus[i].dens).length,
    corpus_density_total: total,
    filed_under_heading: r.vocabHit || undefined,
    heading: r.heading || undefined,
    results: hits.slice(0, limit).map((i) => record(corpus[i], r.scores[i])),
    shelf_only: shelf.slice(0, limit).map((i) => record(corpus[i], 0)),
  };
}

function sentence(v) {
  const n = (x) => String(x).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  if (v.query_terms.length > 1 && v.widened) {
    let s = v.carrying_all_terms
      ? `${n(v.carrying_all_terms)} studies carry all ${v.query_terms.length} of your terms`
      : `No study carries all ${v.query_terms.length} of your terms`;
    if (!v.carrying_all_terms && v.terms_absent_from_corpus.length) {
      s += ` — ${v.terms_absent_from_corpus.map((t) => `"${t}"`).join(', ')} in none of the records`;
    }
    return `${s}. Widened to ${v.widened_to_terms} of ${v.query_terms.length}: ${n(v.listed)} listed.`;
  }
  if (!v.counted_in_density && v.filed_under_heading) {
    return `${n(v.filed_under_heading)} works are filed under "${v.heading}", of ${n(v.corpus_density_total)} — none names it in so many words.`;
  }
  // Never announce 0 over a list of records: those are records the density
  // figures do not count, and saying so is the honest form.
  if (!v.counted_in_density && v.listed) {
    return `${n(v.listed)} records listed, none of them counted in the density figures `
      + `(they mention Origen rather than study him), of ${n(v.corpus_density_total)}.`;
  }
  let s = `${n(v.counted_in_density)} works match of ${n(v.corpus_density_total)}`;
  if (v.filed_under_heading) s += ` · ${n(v.filed_under_heading)} filed under "${v.heading}"`;
  return s + '.';
}

/* ------------------------------------------------------------------ commands */

const USAGE = `origenality — the map of Origen scholarship, for programs

  search <query>        what has been written on this, honestly counted
  gap <query>           the same, framed as: is this ground already taken?
  record <ppn>          one record in full
  vocabulary [kind]     the controlled vocabulary (themes|works|approaches|domains)
  density <kind> <key>  how thick one heading is
  stats                 the harvest, counted
  coverage              what the corpus cannot answer, in figures
  primary [--limit N]   the primary layer: editions, translations and manuscript
                        witnesses of Origen's own works, never counted in a density

Query grammar (search and gap)
  author:crouzel        the author            year:1971  year:1971-1990  year:>2000
  lang:fre  type:book   language, document type
  work:cels             a work of Origen      theme:exegesis   domain:  approach:
  in:adamantius         the journal or volume it sits in
  "free will"           an exact phrase       -rufinus   a term that must not appear
  Filters are conjunctive and never widened: year:1971 does not mean thereabouts.

Options
  --json                machine-readable (default for every command but search)
  --limit N             results to return (default 10)
  --local PATH          read a checkout instead of origenality.com
  --refresh             ignore the 12-hour cache
  --lang CODE[,CODE]    restrict to these languages
  --since YEAR / --until YEAR

Every figure is computed by site/assets/search-core.js, the file the website
itself runs. "counts_in_density" marks a record judged to be ABOUT Origen; the
rest are listed but never counted, which is why two figures are reported.`;

function parse(argv) {
  const o = { _: [], limit: 10, json: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--json') o.json = true;
    else if (a === '--refresh') o.refresh = true;
    else if (a === '--limit') o.limit = Number(argv[++i]);
    else if (a === '--local') o.local = argv[++i];
    else if (a === '--lang') o.lang = argv[++i].split(',');
    else if (a === '--since') o.since = Number(argv[++i]);
    else if (a === '--until') o.until = Number(argv[++i]);
    else if (a === '-h' || a === '--help') o.help = true;
    else o._.push(a);
  }
  return o;
}

function filterCorpus(corpus, o) {
  let c = corpus;
  if (o.lang) c = c.filter((p) => o.lang.includes(p.lang));
  if (o.since) c = c.filter((p) => p.year && p.year >= o.since);
  if (o.until) c = c.filter((p) => p.year && p.year <= o.until);
  return c === corpus ? c : c.map((p, i) => ({ ...p, i }));
}

async function main() {
  const o = parse(process.argv.slice(2));
  const cmd = o._[0];
  if (!cmd || o.help) { console.log(USAGE); return; }

  if (cmd === 'primary') {
    // A separate layer, deliberately: these are the texts, not the studies.
    // Counting them among the scholarship would say the field is larger than
    // it is — so they are served, and never counted.
    const sum = await load('primary', o);
    console.log(JSON.stringify(sum, null, 2));
    return;
  }

  if (cmd === 'stats') {
    const s = await load('stats', o);
    console.log(JSON.stringify(s, null, 2));
    return;
  }

  const [graph, sem, abstracts] = await Promise.all([
    load('graph', o), load('semantic', o), load('abstracts', o),
  ]);
  const C = core(o);
  const corpus = buildCorpus(graph, sem, abstracts);

  if (cmd === 'vocabulary') {
    const kind = o._[1];
    const kinds = kind ? [kind] : ['domains', 'themes', 'works', 'approaches'];
    const out = {};
    for (const k of kinds) {
      out[k] = Object.entries(sem[k] || {}).map(([key, v]) => ({
        key, label: v.label, labels: v.labels || {}, aliases: v.aliases || [],
        records: corpus.filter((p) =>
          (k === 'themes' ? p.themes : k === 'works' ? p.works
            : k === 'approaches' ? p.approaches : p.domains).includes(key)).length,
      })).sort((a, b) => b.records - a.records);
    }
    console.log(JSON.stringify(out, null, 2));
    return;
  }

  if (cmd === 'density') {
    const [, kind, key] = o._;
    const field = kind === 'theme' ? 'themes' : kind === 'work' ? 'works'
      : kind === 'approach' ? 'approaches' : 'domains';
    const hits = corpus.filter((p) => p[field].includes(key));
    const dens = hits.filter((p) => p.dens);
    console.log(JSON.stringify({
      kind, key,
      label: (sem[field === 'domains' ? 'domains' : field][key] || {}).label,
      listed: hits.length, counted_in_density: dens.length,
      corpus_density_total: corpus.filter((p) => p.dens).length,
      by_decade: dens.reduce((m, p) => {
        if (!p.year) return m;
        const d = Math.floor(p.year / 10) * 10;
        m[d] = (m[d] || 0) + 1; return m;
      }, {}),
      results: dens.slice(0, o.limit).map((p) => record(p, 0)),
    }, null, 2));
    return;
  }

  if (cmd === 'record') {
    const p = corpus.find((x) => x.ppn === o._[1]);
    if (!p) { console.error(`no record with ppn ${o._[1]}`); process.exit(1); }
    console.log(JSON.stringify({ ...record(p, 0), abstract: p.abstract || undefined,
      subjects: p.subjects, domains: p.domains, approaches: p.approaches,
      relevance: p.relevance }, null, 2));
    return;
  }

  if (cmd === 'coverage') {
    const n = corpus.length;
    const pct = (x) => Math.round((x / n) * 1000) / 10;
    console.log(JSON.stringify({
      records: n,
      counted_in_density: corpus.filter((p) => p.dens).length,
      with_abstract: corpus.filter((p) => p.abstract).length,
      with_abstract_pct: pct(corpus.filter((p) => p.abstract).length),
      with_subjects: corpus.filter((p) => p.subjects.length).length,
      with_theme_tag: corpus.filter((p) => p.themes.length).length,
      // "unspecified" is the sentinel for a study that names no work of
      // Origen; counting it as a tag would report 100% coverage of an axis
      // three quarters of the corpus does not carry.
      naming_a_work_of_origen: corpus.filter((p) => p.works.some((w) => w !== 'unspecified')).length,
      with_doi: corpus.filter((p) => p.doi).length,
      by_language: corpus.reduce((m, p) => (m[p.lang || '?'] = (m[p.lang || '?'] || 0) + 1, m), {}),
      caveat: 'A search reads title, authors, subjects, container, year, language, '
        + 'theme labels and the abstract. Where the abstract is missing — the majority '
        + 'of the corpus — a subject is only findable if its words are in the title or '
        + 'in the indexing. Absence of a hit is weaker evidence than presence of one.',
    }, null, 2));
    return;
  }

  if (cmd === 'search' || cmd === 'gap') {
    const q = o._.slice(1).join(' ');
    if (!q) { console.error('usage: origenality ' + cmd + ' <query>'); process.exit(1); }
    const c = filterCorpus(corpus, o);
    const v = verdict(C.search(c, q), c, o.limit);
    if (o.json || cmd === 'gap') {
      console.log(JSON.stringify(cmd === 'gap'
        ? { question: q, answer: sentence(v), ...v } : v, null, 2));
    } else {
      console.log(sentence(v));
      for (const r of v.results) {
        console.log(`  ${r.year || '—'}  ${r.title}${r.authors.length ? '  — ' + r.authors.join(', ') : ''}`);
      }
      if (v.shelf_only.length) {
        console.log(`  filed under "${v.heading}":`);
        for (const r of v.shelf_only.slice(0, 5)) console.log(`  ${r.year || '—'}  ${r.title}`);
      }
    }
    return;
  }

  console.error(`unknown command: ${cmd}\n`);
  console.log(USAGE);
  process.exit(1);
}

main().catch((e) => { console.error(String(e.message || e)); process.exit(1); });
