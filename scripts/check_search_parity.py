"""Fail a release where the CLI and the page do not answer alike.

The map and the `origenality` CLI must give one reader one answer. They share
site/assets/search-core.js, and since the audit of 13 September 2026 they share
the index too: `buildIndex` in that file is the only code that turns graph.json,
semantic.json and abstracts.json into what the search reads. Sharing a file is
still only a promise until something checks it, so this runs both paths on the
same data and compares them field by field:

  - the page path: search-core.js under node, `buildIndex` then `search`, and
    the figures explorer.js derives from the result (listed, counted, heading);
  - the CLI path: `node cli/origenality.mjs search <q> --json`, as an agent
    would run it.

It also fails when explorer.js does not call `buildIndex`, because a page that
builds its own index is no longer the page path checked here. And it checks the
rules themselves on the CLI answer, one query per rule and per defect fixed:
a subject absent from the corpus, a conjunction that must not be silently
relaxed, word starts, elisions, phrases, headings in several spellings and
with French punctuation, non-Latin input, malformed field syntax, undated
records under a year bound, the 'unspecified' sentinel, language aliases,
density against search, and the figures that travel with a density (records
flagged for review, with an abstract, undated, the leading source).

    python3 scripts/check_search_parity.py            # data from origenality.com
    python3 scripts/check_search_parity.py --local    # data from this tree

Needs node, and a browser only for --browser (the `bu` CLI).
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "cli" / "origenality.mjs"


def first_existing(*paths):
    for p in paths:
        if p.exists():
            return p
    return paths[0]


CORE = first_existing(ROOT / "site/build-c/assets/search-core.js", ROOT / "site/assets/search-core.js")
EXPLORER = first_existing(ROOT / "site/build-c/assets/explorer.js", ROOT / "site/assets/explorer.js")

# (query, rule, options). Options are the CLI restrictions --lang/--since/--until;
# the page path applies the same restriction as `keep`.
CASES = [
    ("Origen in Ethiopia", "a subject in none of the records must be named as absent", {}),
    ("free will in the Commentary on Romans", "a conjunction must be counted before it is widened", {}),
    ("Rome", "a term matches at a word start, not inside 'jerome'", {}),
    ('"Rome"', "a quoted phrase is bounded like a term, never inside 'jerome'", {}),
    ("man", "a short term does not reach the language label 'german'", {}),
    ('"man"', "…nor does the same term quoted", {}),
    ("prière", "a domain label must not stand in for the free text", {}),
    ("Martyrium", "…and must not make two headings return one set", {}),
    ("Contre Celse", "an alias of a work reaches the records of that work", {}),
    ("Contre Celse\u202f?", "trailing French punctuation is not part of a heading", {}),
    ("Contra Celsum", "…as does its label", {}),
    ("apokatastasis", "a plain subject keeps answering as it did", {}),
    ("Bardaisan", "a thin neighbourhood stays thin", {}),
    ("the art of the homily", "two common words are a conjunction, not a shelf", {}),
    ("Origène", "an elided article does not hide the word after it", {}),
    ("d'Origène", "the elided form answers like the bare word", {}),
    ("Écriture", "…for any word after an elision", {}),
    ('"l\'Église"', "a phrase with a typed apostrophe", {}),
    ('"l\u2019Église"', "…answers like the typographic one", {}),
    ("year:2026 Bardaisan allegory", "a term present in the corpus is not declared absent because a filter hides it", {}),
    ("Bardaisan allegory", "…nor because an option restricts the population", {"since": 2026}),
    ("samaritaine samaritains", "a thin answer carrying every term is not labelled widened", {}),
    ("year:<1900", "a year bound reaches dated records only", {}),
    ("Ωριγένους", "a Greek word is a searchable term", {}),
    ("Ориген", "a Cyrillic word is a searchable term, named when absent", {}),
    ("Buße", "ß folds to ss", {}),
    ("großen", "ß does not cut a word in two", {}),
    ("PG", "a query with no searchable term says so, and is not answered with 0", {}),
    ("year:abc", "an invalid year is reported", {}),
    ("year:2000-1990", "a reversed range is reported", {}),
    ("foo:bar", "an unknown field is reported, not turned into free text", {}),
    ("author:", "an empty field is reported", {}),
    ('"free will', "an unclosed quotation mark is reported", {}),
    ("lang:xx", "an unknown language is reported", {}),
    ("type:bok", "an unknown document type is reported", {}),
    ("work:unspecified", "the 'unspecified' sentinel is not a filterable work", {}),
    ("No specific work", "the 'unspecified' sentinel is not a heading", {}),
    ("Origen in general", "…under either half of its label", {}),
    ("origen", "the sentinel does not file most of the corpus under 'origen'", {}),
    ("Contra Celsum", "the heading figure counts the population beside it", {"lang": "es"}),
    ("Origen and Roman law", "the conjunction is the headline; each term's reach is reported", {}),
    ("theme:anthropology.free-will", "the reliability figures travel with a theme", {}),
    # the field grammar: conditions, never widened
    ("author:crouzel", "a field query reaches the author and nothing else, newest first", {}),
    ("year:1971-1980 allegory", "a range narrows, it does not score", {}),
    ('"free will"', "a quoted phrase is those words in that order", {}),
    ("apokatastasis -Balthasar", "an exclusion removes and does not widen", {}),
    ("work:cels", "a vocabulary key reaches its records", {}),
    ("lang:fr", "the canonical ISO 639-1 code reaches French records", {}),
    ("lang:fre", "the former ISO 639-2/B code remains an input alias", {}),
    ("l:fr", "the short field alias reaches the same records", {}),
    ("lang:de", "German by its code", {}),
    ("lang:ger", "…and by its MARC code", {}),
    ("lang:en", "English by its code", {}),
    ("lang:English", "…and by its name", {}),
    ("lang:hy", "Armenian by its ISO 639-1 code", {}),
    ("lang:arm", "…by its ISO 639-2/B code", {}),
    ("lang:hye", "…and by its ISO 639-2/T code", {}),
    ("allegory", "--lang takes the codes lang: takes", {"lang": "FR"}),
    ("allegory lang:FR", "…as in the query", {}),
    # every subject heading is searched, not only those graph.json keeps (S-P1)
    ("Origen Antisemitismus", "a word only one record's subject heading carries is found, never named absent", {}),
    ("Homerus", "a heading fewer than three records share is searched", {}),
    ("Geistesgeschichte", "…and a heading of the subject chains", {}),
]

COMPARED = ("refused", "error_kinds", "query_terms", "dropped_terms", "carrying_all_terms",
            "carrying_all_terms_counted", "listed", "counted_in_density", "corpus_density_total",
            "widened", "widened_to_terms", "filed_under_heading", "terms_absent_from_corpus",
            "terms_absent_under_filters", "per_term", "per_term_counted", "filed_under_heading_counted",
            "reliability", "first_ids")

# The page path. Mirrors explorer.js: buildIndex, search with `keep`, then the
# figures applyMatch derives (hits outside the heading-only shelf, split by
# whether they count), in the order the core returns.
PAGE_JS = r"""
const fs = require('fs'), path = require('path');
const [corePath, root] = process.argv.slice(1);
const C = require(corePath);
const SITE = 'https://origenality.com';
async function read(layer, file) {
  if (root) {
    const priv = fs.existsSync(path.join(root, 'site/build-c/assets/search-core.js'));
    const base = layer === 'data' ? (priv ? 'site/data' : 'data') : (priv ? 'site/build-c' : 'site');
    return JSON.parse(fs.readFileSync(path.join(root, base, file), 'utf8'));
  }
  const res = await fetch(`${SITE}/${layer}/${file}`);
  if (!res.ok) throw new Error(`${layer}/${file}: HTTP ${res.status}`);
  return res.json();
}
(async () => {
  const [graph, sem, abstracts, cite] = await Promise.all([
    read('data', 'graph.json'), read('site', 'assets/semantic.json'), read('data', 'abstracts.json'),
    read('data', 'cite.json')]);
  // as the page does: the index first, cite.json read into it after the first render
  const IDX = C.buildIndex(graph, sem, abstracts);
  C.applyCite(IDX, cite);
  const P = IDX.records;
  const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
  const out = cases.map(({ query, options }) => {
    const tests = [];
    if (options.lang) {
      const codes = options.lang.split(',').map((c) => C.resolveLanguage(c));
      tests.push((p) => codes.includes(C.languageCode(p.rawlang)));
    }
    if (options.since != null) tests.push((p) => C.isDated(p) && Number(p.year) >= options.since);
    if (options.until != null) tests.push((p) => C.isDated(p) && Number(p.year) <= options.until);
    const keep = tests.length ? (p) => tests.every((t) => t(p)) : null;
    const r = C.search(IDX, query, { keep });
    if (r.invalid || r.normalisedEmpty) {
      return { refused: r.invalid ? 'query_not_understood' : 'no_searchable_term',
               error_kinds: r.errors.map((e) => e.kind),
               dropped_terms: r.normalisedEmpty ? r.droppedTerms : null };
    }
    let hit = 0, extra = 0, total = 0;
    P.forEach((p) => { if ((!keep || keep(p)) && p.dens) total++; });
    const listed = r.order.filter((i) => !r.vocabOnly.has(i));
    listed.forEach((i) => { if (P[i].dens) hit++; else extra++; });
    const perTerm = {}, perTermCounted = {};
    r.terms.forEach((t, k) => { perTerm[t] = r.termHits[k]; perTermCounted[t] = r.termHitsCounted[k]; });
    // the headline records: with several terms, the counted ones carrying every term
    const K = r.terms.length;
    const head = listed.filter((i) => P[i].dens && (K < 2 || r.scores[i] >= K)).map((i) => P[i]);
    const bySource = {};
    head.forEach((p) => { if (p.src) bySource[p.src] = (bySource[p.src] || 0) + 1; });
    const top = Object.keys(bySource).sort((a, b) => (bySource[b] - bySource[a]) || (a < b ? -1 : 1))[0];
    return {
      refused: null, error_kinds: [], query_terms: r.terms, dropped_terms: r.droppedTerms,
      carrying_all_terms: r.fullHit, carrying_all_terms_counted: r.fullHitCounted,
      listed: hit + extra, counted_in_density: hit, corpus_density_total: total,
      widened: r.widened, widened_to_terms: r.widened ? r.hitDepth : null,
      filed_under_heading: r.vocabHit || null,
      terms_absent_from_corpus: r.absentTerms, terms_absent_under_filters: r.absentUnderFilters,
      per_term: perTerm,
      per_term_counted: perTermCounted,
      filed_under_heading_counted: r.vocabHit ? r.vocabHitCounted : null,
      reliability: {
        counted: head.length,
        review_flagged: head.filter((p) => p.review).length,
        with_abstract: head.filter((p) => p.abstract).length,
        no_year: head.filter((p) => !C.isDated(p)).length,
        top_source: top ? { source: top, records: bySource[top],
                            share_pct: Math.round((bySource[top] * 100) / head.length) } : null,
      },
      first_ids: listed.slice(0, 10).map((i) => P[i].ppn),
      first_years: listed.slice(0, 40).map((i) => P[i].year),
      undated_under_year: r.filters.some((f) => f.field === 'year')
        ? [...r.matched].filter((i) => !C.isDated(P[i])).length : 0,
      // every record whose title glues an elided article to the term must be
      // among the answers to the bare term
      elided_missed: r.terms.length === 1 && !r.phrases.length && !r.filters.length
        ? P.filter((p) => new RegExp("\\p{L}['\u2019`]\\s*" + r.terms[0], 'u')
            .test(String(p.title || '').toLowerCase().normalize('NFD').replace(/\p{M}+/gu, ''))
            && !r.matched.has(p.i)).length
        : 0,
    };
  });
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { console.error(String(e && e.message || e)); process.exit(1); });
"""


def page_path(local):
    args = ["node", "-e", PAGE_JS, str(CORE)] + ([str(ROOT)] if local else [])
    payload = json.dumps([{"query": q, "options": o} for q, _, o in CASES])
    out = subprocess.run(args, input=payload, capture_output=True, text=True, timeout=300)
    if out.returncode:
        raise SystemExit(f"page path failed: {out.stderr.strip()}")
    return json.loads(out.stdout)


def run_cli(args, local):
    cmd = ["node", str(CLI)] + args + ["--json"] + (["--local", str(ROOT)] if local else [])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180)


def option_args(options):
    args = []
    for key in ("lang", "since", "until"):
        if key in options:
            args += [f"--{key}", str(options[key])]
    return args


def cli_path(query, options, local):
    out = run_cli(["search", query, "--limit", "10"] + option_args(options), local)
    if out.returncode not in (0, 2):
        raise SystemExit(f"CLI failed on {query!r}: {out.stderr.strip()}")
    body = json.loads(out.stdout) if out.stdout.strip() else {}
    if out.returncode == 2:
        if "error" not in body:
            raise SystemExit(f"CLI exited 2 on {query!r} without a JSON reason: {out.stderr.strip()}")
        return {"refused": body["error"],
                "error_kinds": [e["kind"] for e in body.get("query_errors", [])],
                "dropped_terms": body.get("dropped_terms")}
    got = {key: body.get(key) for key in COMPARED if key not in ("refused", "error_kinds", "first_ids")}
    got["refused"] = None
    got["error_kinds"] = []
    got["first_ids"] = [r["id"] for r in body["results"]]
    return got


def compare(page, cli):
    diffs = []
    for key in COMPARED:
        if cli.get("refused") and key not in ("refused", "error_kinds", "dropped_terms"):
            continue
        a, b = page.get(key), cli.get(key)
        if a != b:
            diffs.append(f"{key}: page {a!r}, CLI {b!r}")
    return diffs


def state_numbers(line):
    """Figures from the Explorer state line (stateLine() in explorer.js)."""
    clean = line.replace("\u202f", "").replace("\u00a0", "")
    clean = re.sub(r"(?<=\d) (?=\d{3}\b)", "", clean)
    lead = re.match(r"\s*(\d+)", clean)
    filed = re.search(r"(\d+) (?:filed under|works? (?:is|are) filed under)", clean)
    return {"lead": int(lead.group(1)) if lead else 0,
            "filed": int(filed.group(1)) if filed else None,
            "widened": "widened" in clean.lower()}


def browser(queries, url):
    """Drive the real page. Uses the `bu` CLI, the only browser path here."""
    js = """(()=>{const i=document.getElementById('ask-input'),g=document.getElementById('ask-go'),o={};
for(const q of %s){i.value=q;i.dispatchEvent(new Event('input',{bubbles:true}));g.click();
o[q]=document.getElementById('ask-state').textContent;}return JSON.stringify(o)})()""" % json.dumps(queries)
    session = f"parity-{os.getpid()}"
    subprocess.run(["bu", "--session", session, "python",
                    f'browser.goto("{url}")\nbrowser.wait(14)'], capture_output=True, timeout=300)
    try:
        out = subprocess.run(["bu", "--session", session, "eval", js],
                             capture_output=True, text=True, timeout=180)
        raw = out.stdout.strip()
        return json.loads(raw[raw.index("{"):])
    finally:
        subprocess.run(["bu", "--session", session, "close"], capture_output=True)


def rules(results, local):
    """The rules themselves, not just equality: a shared file can be shared and wrong."""
    bad = []
    by = {(q, json.dumps(o, sort_keys=True)): got for (q, _, o), got in zip(CASES, results)}

    def get(query, **options):
        return by.get((query, json.dumps(options, sort_keys=True)))

    def share(got):
        return got["counted_in_density"] / max(got["corpus_density_total"], 1)

    for (query, rule, options), got in zip(CASES, results):
        if got.get("refused"):
            continue
        if got["widened"] and got["listed"] <= got["carrying_all_terms"]:
            bad.append(f"{query!r}: flagged widened while nothing was added ({rule})")
        if got.get("undated_under_year"):
            bad.append(f"{query!r}: {got['undated_under_year']} undated records under a year bound ({rule})")
        if got.get("elided_missed"):
            bad.append(f"{query!r}: {got['elided_missed']} titles with an elided article missed ({rule})")

    def expect(ok, message):
        if not ok:
            bad.append(message)

    g = get("Origen in Ethiopia")
    expect("ethiopia" in g["terms_absent_from_corpus"], "'Origen in Ethiopia': the absent term is not reported")
    rome, qrome = get("Rome"), get('"Rome"')
    expect(share(rome) <= 0.03, f"'Rome': {rome['counted_in_density']} hits, the word boundary is gone")
    expect(qrome["counted_in_density"] <= rome["counted_in_density"],
           f"'\"Rome\"' ({qrome['counted_in_density']}) exceeds 'Rome' ({rome['counted_in_density']}): the phrase is a substring again")
    man, qman = get("man"), get('"man"')
    expect(qman["counted_in_density"] <= man["counted_in_density"], "'\"man\"' exceeds 'man': the phrase is a substring again")
    cc, ccq = get("Contre Celse"), get("Contre Celse\u202f?")
    expect(bool(cc.get("filed_under_heading")), "'Contre Celse': the aliases are not served")
    expect((ccq["filed_under_heading"], ccq["widened"]) == (cc["filed_under_heading"], cc["widened"]),
           "'Contre Celse ?': the trailing punctuation changes the answer")
    auth = get("author:crouzel")
    expect(0.005 <= share(auth) <= 0.08, f"'author:crouzel': {auth['counted_in_density']} hits, the author filter is off")
    years = [y for y in auth["first_years"] if y is not None]
    expect(years == sorted(years, reverse=True), "'author:crouzel': the records are not listed newest first")
    expect(not get("year:1971-1980 allegory")["widened"], "'year:1971-1980 allegory': a field query was widened")
    expect(get("apokatastasis -Balthasar")["counted_in_density"] < get("apokatastasis")["counted_in_density"],
           "'apokatastasis -Balthasar': the exclusion removed nothing")
    cels = get("work:cels")
    expect(0.005 <= share(cels) <= 0.10, f"'work:cels': {cels['counted_in_density']} hits, the vocabulary key is off")
    bard = get("Bardaisan")
    expect(share(bard) <= 0.01, f"'Bardaisan': {bard['counted_in_density']} hits, a thin subject has thickened")
    pr, ma = get("prière"), get("Martyrium")
    expect(not (pr["counted_in_density"] == ma["counted_in_density"] and pr["counted_in_density"] > 20),
           "'prière' and 'Martyrium' answer with one figure: the domain label is back in the free-text index")
    orig, dorig = get("Origène"), get("d'Origène")
    expect((dorig["listed"], dorig["carrying_all_terms"]) == (orig["listed"], orig["carrying_all_terms"]),
           "\"d'Origène\" and 'Origène' do not answer alike")
    expect(get('"l\'Église"')["listed"] == get('"l\u2019Église"')["listed"],
           "the two apostrophes of \"l'Église\" do not answer alike")
    if bard["carrying_all_terms"]:
        for q, o in (("year:2026 Bardaisan allegory", {}), ("Bardaisan allegory", {"since": 2026})):
            expect("bardaisan" not in get(q, **o)["terms_absent_from_corpus"],
                   f"{q!r} {o}: 'bardaisan' is declared absent from the corpus though it is in it")
    sam = get("samaritaine samaritains")
    expect(not (sam["widened"] and sam["listed"] == sam["carrying_all_terms"]),
           "'samaritaine samaritains': a thin answer is labelled widened")
    greek = get("Ωριγένους")
    expect(bool(greek["query_terms"]) and greek["listed"] > 0, "'Ωριγένους': a Greek word does not reach the Greek titles")
    cyr = get("Ориген")
    expect(cyr["query_terms"] == ["ориген"], "'Ориген': the Cyrillic word is not a term")
    expect(get("Buße")["query_terms"] == ["busse"], "'Buße': ß is not folded")
    expect(get("großen")["query_terms"] == ["grossen"], "'großen': ß cuts the word")
    expect(get("PG").get("refused") == "no_searchable_term", "'PG': a query with no term is answered")
    for q, kind in (("year:abc", "invalid_year"), ("year:2000-1990", "reversed_year_range"),
                    ("foo:bar", "unknown_field"), ("author:", "empty_value"),
                    ('"free will', "unclosed_quote"), ("lang:xx", "unknown_language"),
                    ("type:bok", "unknown_type"), ("work:unspecified", "unknown_key")):
        expect(kind in (get(q).get("error_kinds") or []), f"{q!r}: not reported as {kind}")
    total = get("origen")["corpus_density_total"]
    expect(not get("No specific work").get("filed_under_heading"), "'No specific work': the sentinel is a heading")
    expect((get("Origen in general").get("filed_under_heading") or 0) < 0.1 * total,
           "'Origen in general': the sentinel files the corpus under a heading")
    expect((get("origen").get("filed_under_heading") or 0) < 0.1 * total,
           "'origen': the sentinel files the corpus under 'origen'")
    es, allcc = get("Contra Celsum", lang="es"), get("Contra Celsum")
    expect((es.get("filed_under_heading") or 0) < (allcc.get("filed_under_heading") or 0),
           "'Contra Celsum' --lang es: the heading figure ignores the restriction")
    anti = get("Origen Antisemitismus")
    expect("antisemitismus" not in anti["terms_absent_from_corpus"] and anti["carrying_all_terms"] >= 1,
           "'Origen Antisemitismus': the subject heading 'Antisemitismus' is not searched")
    for word in ("Homerus", "Geistesgeschichte"):
        got = get(word)
        expect(got["listed"] > 0 and not got["terms_absent_from_corpus"],
               f"'{word}': a word of a subject heading is named absent from the corpus")
    law = get("Origen and Roman law")
    expect(len(law["per_term"]) == len(law["query_terms"]) and
           len(law["per_term_counted"]) == len(law["query_terms"]) and
           law["carrying_all_terms_counted"] <= law["carrying_all_terms"] and
           law["reliability"]["counted"] == law["carrying_all_terms_counted"],
           "'Origen and Roman law': per-term reach or the counted conjunction is missing")
    same = lambda *qs: len({(get(q)["listed"], get(q)["counted_in_density"]) for q in qs}) == 1
    expect(same("lang:fr", "lang:fre", "l:fr") and get("lang:fr")["counted_in_density"] > 0,
           "lang:fr, lang:fre and l:fr do not return the same non-empty population")
    expect(same("lang:de", "lang:ger"), "lang:de and lang:ger differ")
    expect(same("lang:en", "lang:English"), "lang:en and lang:English differ")
    expect(same("lang:hy", "lang:arm", "lang:hye") and get("lang:hy")["listed"] > 0,
           "lang:hy, lang:arm and lang:hye do not return the same non-empty population")
    opt, gram = get("allegory", lang="FR"), get("allegory lang:FR")
    expect((opt["listed"], opt["counted_in_density"]) == (gram["listed"], gram["counted_in_density"]),
           "--lang FR and lang:FR do not answer alike")

    # density is the same heading as search, under the same restrictions
    for args in (["work", "cels"], ["theme", "exegesis"], ["theme", "exegesis.allegory", "--since", "2000"],
                 ["work", "hom"], ["theme", "anthropology.free-will"]):
        d = run_cli(["density"] + args, local)
        s = run_cli(["search", f"{args[0]}:{args[1]}", "--limit", "0"] + args[2:], local)
        if d.returncode or s.returncode:
            bad.append(f"density/search {' '.join(args)}: exit {d.returncode}/{s.returncode}")
            continue
        dj, sj = json.loads(d.stdout), json.loads(s.stdout)
        expect((dj["listed"], dj["counted_in_density"]) == (sj["listed"], sj["counted_in_density"]),
               f"density {' '.join(args)} ({dj['listed']}/{dj['counted_in_density']}) disagrees with "
               f"search ({sj['listed']}/{sj['counted_in_density']})")
        rel = sj["reliability"]
        expect([dj.get(k) for k in ("review_flagged", "with_abstract", "no_year", "top_source")] ==
               [rel[k] for k in ("review_flagged", "with_abstract", "no_year", "top_source")],
               f"density {' '.join(args)}: its reliability figures differ from those of search")
    for args in (["density", "themes", "nope"], ["density", "theme", "nope"], ["vocabulary", "foo"]):
        expect(run_cli(args, local).returncode == 2, f"{' '.join(args)}: a bad kind or key does not exit 2")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="read this tree, not origenality.com")
    ap.add_argument("--browser", action="store_true", help="also compare against the served page")
    ap.add_argument("--url", default="https://origenality.com/site/")
    args = ap.parse_args()

    bad = []
    explorer = EXPLORER.read_text(encoding="utf-8") if EXPLORER.exists() else ""
    if "buildIndex(" not in explorer:
        bad.append(f"{EXPLORER.relative_to(ROOT)} does not call buildIndex(): the page builds its own "
                   "index, so the page path checked here is not the one it runs")
    if "CORE.applyCite(IDX" not in explorer:
        bad.append(f"{EXPLORER.relative_to(ROOT)} does not read cite.json into the index (applyCite): "
                   "the page would search fewer headings than the CLI")

    pages = page_path(args.local)
    clis = [cli_path(q, o, args.local) for q, _, o in CASES]

    for (query, rule, options), page, cli in zip(CASES, pages, clis):
        for diff in compare(page, cli):
            bad.append(f"{query!r} {options or ''}: page and CLI differ on {diff} ({rule})")

    merged = [{**cli, **{k: page.get(k) for k in ("first_years", "undated_under_year", "elided_missed")}}
              for page, cli in zip(pages, clis)]
    bad += rules(merged, args.local)

    for (query, _, options), got in zip(CASES, merged):
        opts = " " + " ".join(option_args(options)) if options else ""
        if got.get("refused"):
            kinds = ", ".join(got.get("error_kinds") or []) or got["refused"]
            print(f"  {'refused':>13}   {query}{opts}   ({kinds})")
            continue
        print(f"  {got['counted_in_density']:>5} / {got['corpus_density_total']:<5}"
              f"{'  (widened)' if got['widened'] else ''}   {query}{opts}")

    if args.browser:
        plain = [(q, got) for (q, _, o), got in zip(CASES, merged) if not o and not got.get("refused")]
        lines = browser([q for q, _ in plain], args.url)
        for query, got in plain:
            seen = state_numbers(lines.get(query, ""))
            # the state line leads with a count: the counted conjunction when the
            # list was widened, the counted heading when only a heading answers
            if got["widened"] and len(got["query_terms"]) > 1:
                want = got["carrying_all_terms_counted"]
            elif not got["counted_in_density"] and got.get("filed_under_heading_counted"):
                want = got["filed_under_heading_counted"]
            else:
                want = got["counted_in_density"]
            if seen["lead"] != want or seen["widened"] != bool(got["widened"]):
                bad.append(f"{query!r}: CLI says {want} (widened {got['widened']}), "
                           f"the page says {lines.get(query, '')!r}")
            if got.get("filed_under_heading_counted") and seen["filed"] != got["filed_under_heading_counted"]:
                bad.append(f"{query!r}: CLI files {got['filed_under_heading_counted']} under the heading, "
                           f"the page says {lines.get(query, '')!r}")

    if bad:
        print("\n".join("  ✗ " + b for b in bad), file=sys.stderr)
        return 1
    print(f"\n{len(CASES)} queries: the page path, the CLI and the rules agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
