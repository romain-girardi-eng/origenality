#!/usr/bin/env python3
"""Academic weight of each publication node, for the Explorer of direction C.

Two objective measures, no hand coded judgement:

  cite_rank   percentile of `cited_by_count` (as measured in the derived
              citation table) inside the publication's own cohort — same decade, same
              document type, same language — so that German, older and
              monographic work is not crushed by the English article average.
  struct_rank percentile of a plain PageRank run on graph.json itself
              (publication <-> author, subject, container), which measures how
              tied a work is to the rest of the field as we harvested it.

  weight      mean of the two percentiles, in [0, 1].

A publication with no citation datum keeps its structural percentile alone and
is flagged `nc` (no citation data). It is never pushed below the base size.

Citation figures are never re-derived here. They are read from
`data/derived/citations.jsonl`, the one place where a citation count is attached
to a work, and they are joined on identifiers only — the IxTheo PPN, then the
DOI. Joining on a title alone put the 244 citations of a *Choice* review on the
monograph it reviewed; the title join is gone, and it cannot come back at this
level, because a graph node carries no author and no document type, so the
identity test that the pipeline applies (same title, same first author, same
document type, one year apart at most) cannot be checked here.

Input   ../../data/graph.json                       (the site payload)
        ../../../data/derived/citations.jsonl       (counts, one row per work)
Output  ../assets/weights.json

Run:    python3 site/build-c/tools/build_weights.py
"""

import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tree_paths import data_dir, repository_root  # noqa: E402

ROOT = repository_root(HERE)
GRAPH = os.path.join(data_dir(ROOT), 'graph.json')
CITATIONS = os.path.join(ROOT, 'data', 'derived', 'citations.jsonl')
OUT = os.path.normpath(os.path.join(HERE, '..', 'assets', 'weights.json'))

MIN_COHORT = 8          # below this a cohort is too thin to rank inside
PR_ITER = 45
PR_DAMP = 0.85


def norm_doi(doi):
    d = (doi or '').strip().lower()
    for prefix in ('https://doi.org/', 'http://dx.doi.org/', 'http://doi.org/'):
        if d.startswith(prefix):
            d = d[len(prefix):]
    return d


def load_citations():
    """Citation figures read from data/derived/citations.jsonl, keyed by the two
    identifiers a graph node can be trusted to carry: the IxTheo PPN, then the
    DOI. A row that the pipeline did not measure contributes nothing — an
    unmeasured work has no count, not a count of zero. Where two rows share an
    identifier, which the pipeline's own key rules make rare, the disagreement
    is dropped rather than resolved by taking the larger figure: taking the
    maximum is how a review's count reached the book it reviewed."""
    by_ppn, by_doi = {}, {}
    dropped = {'ppn': 0, 'doi': 0}
    if not os.path.exists(CITATIONS):
        sys.stderr.write('citations.jsonl not found at %s\n' % CITATIONS)
        return by_ppn, by_doi, dropped
    with open(CITATIONS, encoding='utf-8') as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not rec.get('measured'):
                continue
            try:
                c = int(rec['cited_by_count'])
            except (KeyError, TypeError, ValueError):
                continue
            ppn = rec.get('ixtheo_ppn')
            if ppn:
                k = str(ppn)
                if k in by_ppn and by_ppn[k] != c:
                    dropped['ppn'] += 1
                    by_ppn[k] = None
                elif k not in by_ppn:
                    by_ppn[k] = c
            doi = norm_doi(rec.get('doi'))
            if doi:
                if doi in by_doi and by_doi[doi] != c:
                    dropped['doi'] += 1
                    by_doi[doi] = None
                elif doi not in by_doi:
                    by_doi[doi] = c
    by_ppn = {k: v for k, v in by_ppn.items() if v is not None}
    by_doi = {k: v for k, v in by_doi.items() if v is not None}
    return by_ppn, by_doi, dropped


def pagerank(n, adj):
    r = [1.0 / n] * n
    deg = [len(a) or 1 for a in adj]
    for _ in range(PR_ITER):
        nxt = [(1.0 - PR_DAMP) / n] * n
        for i, a in enumerate(adj):
            if not a:
                continue
            share = PR_DAMP * r[i] / deg[i]
            for j in a:
                nxt[j] += share
        r = nxt
    return r


def percentiles(values):
    """value -> percentile in [0, 1], ties share the same rank."""
    order = sorted(values)
    n = len(order)
    if n < 2:
        return {v: 0.5 for v in values}
    seen, out = {}, {}
    for i, v in enumerate(order):
        if v not in seen:
            seen[v] = i
    for v in set(values):
        out[v] = seen[v] / float(n - 1)
    return out


def main():
    graph = json.load(open(GRAPH, encoding='utf-8'))
    nodes, edges = graph['nodes'], graph['edges']

    adj = [[] for _ in nodes]
    for e in edges:
        adj[e['s']].append(e['t'])
        adj[e['t']].append(e['s'])

    pr = pagerank(len(nodes), adj)

    pubs = [(i, n) for i, n in enumerate(nodes) if n['k'] == 'pub']
    struct = percentiles([pr[i] for i, _ in pubs])

    by_ppn, by_doi, dropped = load_citations()
    cites, joined_on = {}, {'ppn': 0, 'doi': 0, 'title': 0}
    for _, n in pubs:
        ppn = n.get('ppn')
        doi = norm_doi(n.get('doi'))
        if ppn in by_ppn:
            cites[ppn] = by_ppn[ppn]; joined_on['ppn'] += 1
        elif doi and doi in by_doi:
            cites[ppn] = by_doi[doi]; joined_on['doi'] += 1
    sys.stderr.write('citation figures joined: %s, total %d of %d publications '
                     '(identifier disagreements dropped: %s)\n'
                     % (joined_on, len(cites), len(pubs), dropped))

    def decade(y):
        return (y // 10) * 10 if isinstance(y, int) else None

    # cohorts, from the most specific to the widest
    keys = [
        lambda n: ('dtl', decade(n.get('year')), n.get('type') or '', n.get('lang') or ''),
        lambda n: ('dl', decade(n.get('year')), n.get('lang') or ''),
        lambda n: ('d', decade(n.get('year'))),
        lambda n: ('all',),
    ]
    buckets = [defaultdict(list) for _ in keys]
    have = [(i, n) for i, n in pubs if n.get('ppn') in cites]
    for i, n in have:
        for k, fn in enumerate(keys):
            buckets[k][fn(n)].append(cites[n['ppn']])

    ranked = [{}, {}, {}, {}]
    for k, b in enumerate(buckets):
        for key, vals in b.items():
            ranked[k][key] = percentiles(vals)

    out = {}
    for i, n in pubs:
        st = struct[pr[i]]
        ppn = n.get('ppn')
        c = cites.get(ppn)
        if c is None:
            out[ppn] = {'w': round(st, 4), 'st': round(st, 4), 'nc': 1}
            continue
        pct, cohort = None, None
        for k, fn in enumerate(keys):
            key = fn(n)
            if len(buckets[k].get(key, ())) >= MIN_COHORT or k == len(keys) - 1:
                pct = ranked[k][key][c]
                cohort = ['decade, type and language', 'decade and language', 'decade', 'whole corpus'][k]
                break
        out[ppn] = {'w': round((pct + st) / 2.0, 4), 'st': round(st, 4),
                    'c': c, 'p': round(pct, 4), 'ch': cohort}

    payload = {
        'generated': '2026-08-16',
        'method': ('weight = mean of two percentiles in [0,1]: the OpenAlex cited_by_count '
                   'percentile inside the cohort of same decade, document type and language '
                   '(widened when a cohort holds fewer than %d works), and the percentile of a '
                   'PageRank run on graph.json. A work with no citation datum keeps the '
                   'structural percentile alone and is marked nc.' % MIN_COHORT),
        'citation_source': 'cited_by_count as measured in data/derived/citations.jsonl, '
                           'joined on the ixtheo-k10plus source identifier (the PPN), then on '
                           'the DOI. No title join: a graph node carries neither author nor '
                           'document type, so two works of the same name — a book and its '
                           'review — cannot be told apart at this level.',
        'joined_on': joined_on,
        'covered': sum(1 for v in out.values() if 'c' in v),
        'total': len(out),
        'w': out,
    }
    with open(OUT, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(',', ':'))
    sys.stderr.write('wrote %s (%d publications, %d with citation data)\n'
                     % (OUT, len(out), payload['covered']))


if __name__ == '__main__':
    main()
