/* Origenality — Observatory. Reads the published statistics and the tag file,
   counts nothing it cannot show, and states the perimeter with every figure.
   Romain Girardi, 2026. No external requests, no third party code. */
(function () {
  'use strict';
  // The build is read from META.json (ObservatoryCore.buildIdOf, the rule the
  // Explorer applies), never typed here; it keys the cache of the larger files.
  var CORE = window.ObservatoryCore || null;

  var LANGS = [
    { code: 'en', label: 'English', col: '#1F5674' },
    { code: 'de', label: 'German', col: '#A8371F' },
    { code: 'it', label: 'Italian', col: '#8A6A12' },
    { code: 'fr', label: 'French', col: '#4F7350' },
    { code: 'es', label: 'Spanish', col: '#B15A17' },
    { code: 'oth', label: 'Other or none', col: '#78766F' }
  ];
  var LCOL = {}; LANGS.forEach(function (l) { LCOL[l.code] = l.col; });
  var SET_COL = { density: '#1F5674', marginal: '#8A6A12', none: '#78766F' };

  function nf(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' '); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function el(id) { return document.getElementById(id); }
  function attr(s) { return esc(s).replace(/"/g, '&quot;'); }
  function pc(n, total) { return total ? (n / total * 100) : 0; }

  wireCrossings();

  fetch('../data/META.json', { cache: 'no-cache' }).then(function (r) {
    if (!r.ok) throw new Error('META.json answered ' + r.status);
    return r.json();
  }).then(function (meta) {
    var build = CORE ? CORE.buildIdOf(meta) : null;
    var opt = build ? {} : { cache: 'no-cache' };
    function versioned(url) { return build ? url + '?v=' + build : url; }
    return Promise.all([
      fetch(versioned('../data/stats.json'), opt).then(function (r) { return r.json(); }),
      meta,
      fetch(versioned('assets/semantic.json'), opt).then(function (r) { return r.json(); }),
      // the records themselves: year, language and format are counted here on the
      // one population the whole site counts, rather than on the raw harvest
      fetch(versioned('../data/graph.json'), opt).then(function (r) { return r.json(); })
    ]);
  }).then(function (r) { render(r[0], r[1], r[2], r[3]); }).catch(function (e) {
    el('stamp').textContent = 'The figures could not be loaded.';
    console.error(e);
  });

  function bars(node, rows, opts) {
    opts = opts || {};
    var max = 0;
    rows.forEach(function (row) { max = Math.max(max, row.n); });
    node.innerHTML = rows.map(function (row) {
      var w = max ? (row.n / max * 100).toFixed(1) : 0;
      return '<div class="brow"><span class="lb">' + esc(row.label) +
        (row.sub ? '<small>' + esc(row.sub) + '</small>' : '') + '</span>' +
        '<span class="tr"><span class="fl" style="width:' + w + '%' +
        (row.col ? ';background:' + row.col : '') + '"></span></span>' +
        '<span class="vv">' + nf(row.n) +
        (opts.share ? ' <span style="color:var(--stone)">' + pc(row.n, opts.share).toFixed(0) + '%</span>' : '') +
        '</span></div>';
    }).join('');
  }

  function render(stats, meta, sem, graph) {
    var tags = sem.byPpn, ppns = Object.keys(tags);
    var total = ppns.length;

    /* ------------------------------------------------- the counted population
       One rule for every figure on this page, and the same one the Explorer
       applies: a count is a count of the records classed core or partial. The
       records that merely mention Origen, and those held as not about him, keep
       their place in the index and answer a search; they enter no figure. Year,
       language and format used to be read off the whole harvest, which put three
       different populations on one screen. They are counted here, record by
       record, on the same 1 400. */
    function thematic(rec) { return rec.r === 'core' || rec.r === 'partial'; }
    var COUNTED = [], MENTION = 0, ASIDE = 0;
    (graph.nodes || []).forEach(function (n) {
      if (n.k !== 'pub' || !n.ppn) return;
      var rec = tags[n.ppn];
      if (!rec) { ASIDE++; return; }
      if (thematic(rec)) COUNTED.push(n);
      else if (rec.r === 'marginal') MENTION++;
      else ASIDE++;
    });
    var COUNT_N = COUNTED.length;
    function outsideLine() {
      return nf(MENTION) + (MENTION === 1 ? ' record mentions' : ' records mention') +
        ' Origen only, and ' + nf(ASIDE) + ' are held outside the count as not about him ' +
        'or without a class: ' + nf(MENTION + ASIDE) +
        ' in all, outside this figure and every other one here.';
    }

    /* ---------------------------------------------------------- three sets
       The band is drawn on the records of the map, not on the records the wave
       tagged: a record whose cluster was reshaped after the wave ran carries no
       class, and counting it nowhere would put a second population on the same
       screen — the band would read 5 held aside where the header reads 33. It
       falls in the third set with the rest, and the note below says how many of
       them are there for that reason. */
    var sets = { density: COUNT_N, marginal: MENTION, none: ASIDE }, review = 0;
    var relLabel = {};
    Object.keys(sem.relevance).forEach(function (k) { relLabel[k] = sem.relevance[k].label; });
    var reviewBy = { core: 0, partial: 0, marginal: 0, none: 0 };
    ppns.forEach(function (id) {
      var t = tags[id];
      if (t.n) { review++; reviewBy[t.r] = (reviewBy[t.r] || 0) + 1; }
    });
    var untagged = ASIDE - (function () {
      var n = 0;
      ppns.forEach(function (id) {
        var r = tags[id].r;
        if (r !== 'core' && r !== 'partial' && r !== 'marginal') n++;
      });
      return n;
    })();
    var setRows = [
      { k: 'density', label: 'Counted in the density', n: sets.density,
        note: 'Origen is the subject, or is treated substantially among others' },
      { k: 'marginal', label: relLabel.marginal || 'Mentioned only', n: sets.marginal,
        note: 'kept in the index, outside every count of density' },
      { k: 'none', label: 'Held outside the count', n: sets.none,
        note: untagged
          ? 'harvest noise and ' + nf(untagged) + ' records left without a class, in one reservoir on the map'
          : 'harvest noise, held in its own reservoir on the map' }
    ];
    var mapTotal = COUNT_N + MENTION + ASIDE;
    el('band-sets').innerHTML = setRows.map(function (row) {
      return '<span style="width:' + pc(row.n, mapTotal).toFixed(2) + '%;background:' + SET_COL[row.k] + '"></span>';
    }).join('');
    el('key-sets').innerHTML = setRows.map(function (row) {
      return '<div class="set" style="color:' + SET_COL[row.k] + '">' +
        '<span class="set-v">' + nf(row.n) + '</span>' +
        '<span class="set-k">' + esc(row.label) + '</span>' +
        '<span class="set-n">' + esc(row.note) + '</span></div>';
    }).join('');
    /* What the flag actually means, rather than the one case that reads best.
       A record is flagged when the classifier answered below its confidence
       floor, when the metadata was too thin to decide, when it hesitated
       between two adjacent classes and took the lower one, or when a value it
       returned had to be repaired at validation. Most of the flagged records
       are in the reservoir, which is where a thin record lands. */
    var inCount = (reviewBy.core || 0) + (reviewBy.partial || 0);
    el('review-note').innerHTML = '<strong>' + nf(review) + ' records</strong> of the ' +
      nf(total) + ' the wave classed' +
      (untagged ? '; the other ' + nf(untagged) + ' of the ' + nf(mapTotal) +
        ' on this map carry no class at all;' : '') +
      ' are flagged for review: the classifier answered below its confidence floor, ' +
      'read metadata too thin to decide, hesitated between two adjacent classes and took the ' +
      'lower one, or returned a value that had to be repaired when it was checked against the ' +
      'vocabulary. They fall where a thin record falls: <strong>' + nf(reviewBy.none || 0) +
      '</strong> are classed as not about Origen, <strong>' + nf(reviewBy.marginal || 0) +
      '</strong> as mentioned only, and <strong>' + nf(inCount) + '</strong> are inside the ' +
      'counted population. ' + nf((sem.source && sem.source.needs_review_repaired) || 0) +
      ' of the whole set carry a repair. They are counted where they stand, and marked in ' +
      'the Explorer.';

    /* ---------------------------------------------------------- scope */
    var t = stats.totals || {};
    var scope = scopeRows(stats, meta, COUNT_N);
    el('scope-grid').innerHTML = scope.map(function (s) {
      return '<div class="reg-row"><span class="reg-v">' + s.v + '</span>' +
        '<span class="reg-k">' + esc(s.k) + '</span><span class="reg-n">' + esc(s.n) + '</span></div>';
    }).join('');

    el('census-n').textContent = nf(COUNT_N);
    el('census-k').textContent = 'counted records, of ' + nf(t.records) + ' kept';
    el('census').hidden = false;

    el('stamp').textContent = stampText(meta, stats, COUNT_N);
    el('foot-stamp').textContent = footStampText(meta, stats);

    /* ---------------------------------------------------------- decades */
    var dec = {}, order = [], noYear = 0, early = 0;
    COUNTED.forEach(function (n) {
      if (n.year == null) { noYear++; return; }
      if (n.year < 1900) { early++; return; }
      var d = Math.floor(n.year / 10) * 10;
      if (!dec[d]) { dec[d] = { d: d, n: 0, lang: {} }; order.push(d); }
      dec[d].n++;
      var code = LCOL[n.lang] ? n.lang : 'oth';
      dec[d].lang[code] = (dec[d].lang[code] || 0) + 1;
    });
    order.sort(function (a, b) { return a - b; });
    var maxD = 0, sumD = 0;
    order.forEach(function (d) { maxD = Math.max(maxD, dec[d].n); sumD += dec[d].n; });
    el('cols-decade').innerHTML = order.map(function (d) {
      var row = dec[d], h = maxD ? (row.n / maxD * 100) : 0;
      var stack = LANGS.map(function (l) {
        var v = row.lang[l.code] || 0;
        if (!v) return '';
        return '<span style="flex:' + v + ';background:' + l.col + '"></span>';
      }).join('');
      return '<div class="c"><span class="vv">' + row.n + '</span>' +
        '<div class="plot"><span class="st" style="height:' + h.toFixed(1) + '%">' + stack + '</span></div>' +
        '<span class="lb' + (d % 20 ? ' lb-minor' : '') + '">' + d + '</span></div>';
    }).join('');

    /* The same series in words and figures, for a reader who does not see the
       columns. It is folded under a control rather than hidden from the page:
       hidden from the eye and hidden from a screen reader are not the same
       thing, and a chart with no readable values says nothing to either. */
    var langsPresent = LANGS.filter(function (l) {
      return order.some(function (d) { return dec[d].lang[l.code]; });
    });
    /* the description of the table sits outside the scrolling box and names it,
       so it is read with the table and never cut off by the horizontal scroll */
    el('table-decade-cap').textContent = 'Records per decade and language of publication: the ' +
      nf(sumD) + ' counted records dated 1900 or later, of ' + nf(COUNT_N) + ' counted in all.';
    el('table-decade').innerHTML =
      '<thead><tr><th scope="col">Decade</th>' +
      langsPresent.map(function (l) { return '<th scope="col">' + esc(l.label) + '</th>'; }).join('') +
      '<th scope="col">All</th></tr></thead><tbody>' +
      order.map(function (d) {
        return '<tr><th scope="row">' + d + 's</th>' +
          langsPresent.map(function (l) {
            return '<td>' + (dec[d].lang[l.code] || 0) + '</td>';
          }).join('') + '<td>' + dec[d].n + '</td></tr>';
      }).join('') + '</tbody>';
    el('cols-decade').setAttribute('aria-label',
      'Records per decade, stacked by language, from the 1900s to the 2020s. ' +
      'The figures are in the table below the chart.');

    el('time-tot').textContent = nf(sumD) + ' counted records, 1900 onwards';
    el('time-note').textContent = 'Decades from 1900 to the 2020s, on the ' + nf(COUNT_N) +
      ' counted records. ' + nf(noYear) + ' of them carry no year and ' + nf(early) +
      ' are earlier than 1900; the last column stops in mid-2026. ' + outsideLine();
    el('key-lang').innerHTML = LANGS.map(function (l) {
      return '<span><i style="background:' + l.col + '"></i>' + esc(l.label) + '</span>';
    }).join('');

    /* ---------------------------------------------------------- languages */
    var lc = {};
    COUNTED.forEach(function (n) {
      var code = LCOL[n.lang] ? n.lang : 'oth';
      lc[code] = (lc[code] || 0) + 1;
    });
    bars(el('bars-lang'), LANGS.filter(function (l) { return lc[l.code]; }).map(function (l) {
      return { label: l.label, n: lc[l.code], col: l.col };
    }).sort(function (a, b) { return b.n - a.n; }), { share: COUNT_N });
    el('lang-tot').textContent = nf(COUNT_N) + ' counted records';

    var fc = {}, fmtKeys = [];
    COUNTED.forEach(function (n) {
      var f = n.type || 'Not coded';
      if (fc[f] == null) { fc[f] = 0; fmtKeys.push(f); }
      fc[f]++;
    });
    fmtKeys.sort(function (a, b) { return fc[b] - fc[a]; });
    bars(el('bars-fmt'), fmtKeys.slice(0, 7).map(function (f) {
      return { label: f, n: fc[f] };
    }), { share: COUNT_N });
    el('fmt-tot').textContent = fmtKeys.length + ' formats coded';

    /* ---------------------------------------------------------- themes */
    var domCount = {}, domDens = 0;
    ppns.forEach(function (id) {
      var rec = tags[id];
      if (!thematic(rec) || !rec.t || !rec.t.length) return;
      var leaf = sem.themes[rec.t[0]];
      if (!leaf) return;
      domCount[leaf.domain] = (domCount[leaf.domain] || 0) + 1;
      domDens++;
    });
    bars(el('bars-dom'), Object.keys(domCount).sort(function (a, b) {
      return domCount[b] - domCount[a];
    }).map(function (d) {
      return { label: sem.domains[d].label, sub: sem.domains[d].labels.de || '', n: domCount[d] };
    }), { share: domDens });
    el('dom-tot').textContent = nf(domDens) + ' records with a theme';

    /* ---------------------------------------------------------- works */
    var wc = {}, wTotal = 0, noWork = 0;
    ppns.forEach(function (id) {
      var rec = tags[id];
      if (!thematic(rec)) return;
      var list = (rec.w || []).filter(function (w) { return w !== 'unspecified' && sem.works[w]; });
      if (!list.length) { noWork++; return; }
      list.forEach(function (w) { wc[w] = (wc[w] || 0) + 1; wTotal++; });
    });
    bars(el('bars-work'), Object.keys(wc).sort(function (a, b) { return wc[b] - wc[a]; })
      .slice(0, 12).map(function (w) {
        return { label: sem.works[w].label, n: wc[w] };
      }));
    el('work-tot').textContent = nf(noWork) + ' name no single work';

    var ac = {}, aTotal = 0;
    ppns.forEach(function (id) {
      var rec = tags[id];
      if (!thematic(rec)) return;
      (rec.a || []).forEach(function (a) { if (sem.approaches[a]) { ac[a] = (ac[a] || 0) + 1; aTotal++; } });
    });
    bars(el('bars-appr'), Object.keys(ac).sort(function (a, b) { return ac[b] - ac[a]; })
      .map(function (a) { return { label: sem.approaches[a].label, n: ac[a] }; }));
    el('appr-tot').textContent = nf(aTotal) + ' angles on ' + nf(sets.density) + ' records';

    renderCrossings(graph, sem, meta);
  }
  /* The register of the harvest. The records harvested and kept say what they
     are; every figure after the count counts the counted records, as the lede
     promises, from the series stats.json holds under `counted` (the top-level
     totals are the records kept). A figure the file gives only for the kept
     records says so in its own row. Harvested is the date the catalogues were
     read (META.harvested), generated the date these files were built
     (META.generated): two dates, two labels. Nothing here is typed. */
  function scopeRows(stats, meta, countN) {
    var t = stats.totals || {};
    var c = (stats.counted && stats.counted.totals) || null;
    var of = c || t;
    var kept = nf(t.records);
    var dedup = (meta.deduplication && meta.deduplication.duplicates_collapsed) || 0;
    return [
      { v: nf(meta.records_harvested_total || t.records), k: 'records harvested',
        n: 'catalogue records about Origen, under ' + nf((meta.sources_present || []).length) +
          ' source labels, harvested on ' + harvestOf(meta, stats) },
      { v: nf((meta.excluded && meta.excluded.relation_by) || 0), k: 'editions kept apart',
        n: "editions, translations and manuscripts of Origen's own works from the same harvest: " +
          'a layer of their own, not among the records harvested' },
      { v: kept, k: 'records kept',
        n: 'work clusters, once ' + nf(dedup) + (dedup === 1 ? ' duplicate is' : ' duplicates are') +
          ' merged; the index and the search read all of them' },
      { v: nf(countN), k: 'records counted',
        n: 'Origen the subject, or holding a section. The population of every figure here' },
      { v: nf(of.distinct_authors), k: 'distinct authors',
        n: 'as spelled by the catalogue, ' + (c ? 'in the counted records' : 'in the ' + kept + ' records kept') },
      { v: nf(of.distinct_containers), k: 'journals and volumes',
        n: c ? 'holding at least one counted record' : 'holding at least one of the ' + kept + ' records kept' },
      { v: nf(of.records_with_doi), k: c ? 'counted records with a DOI' : 'records kept with a DOI',
        n: nf(of.records_with_isbn) + ' carry an ISBN' }
    ];
  }
  function harvestOf(meta, stats) { return meta.harvested || stats.generated; }
  // the second reading of part of the harvest (META.refetched), in words
  function refetchPhrase(meta) {
    if (!meta.refetched || !meta.refetched_records) return '';
    return nf(meta.refetched_records) + ' source records read again on ' + meta.refetched +
      ' for their subject headings and containers';
  }
  function stampText(meta, stats, countN) {
    var again = refetchPhrase(meta), t = stats.totals || {};
    return 'Harvest of ' + harvestOf(meta, stats) + (again ? ', ' + again : '') + ' · ' +
      nf(countN) + ' counted records of ' + nf(t.records) + ' kept' +
      ' · ' + nf((meta.sources_present || []).length) + ' source labels';
  }
  function footStampText(meta, stats) {
    var again = refetchPhrase(meta);
    return 'Figures generated ' + (meta.generated || stats.generated) + ', from the harvest of ' +
      harvestOf(meta, stats) + (again ? '; ' + again : '');
  }

  /* crossings */
  /* Theme by decade, work by domain, domain by language. The counting is done
     in observatory-core.js, which the command line runs too; this part sets
     the counts as tables and writes, under each one, what it cannot count. */
  var NUMBER_WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine'];
  var EMPTY_CELL = 'A 0 counts what these catalogues hold. The ground under it may be unexplored, ' +
    'or exhausted, or written where the catalogues index poorly, and the count cannot tell the three ' +
    'apart (<a href="methode.html">Method</a>, section 4).';

  function pct1(x) { return x.toFixed(1) + '%'; }
  function arrow(a, b) { return a + ' → ' + b; }
  function joined(items, last) {
    return items.length < 2 ? items.join('') :
      items.slice(0, -1).join(', ') + ' ' + last + ' ' + items[items.length - 1];
  }
  /* DATA_POLICY.md writes some labels the French way, with a spaced colon */
  function sourceLabel(label) { return String(label).replace(/\s+[:—–]\s+/g, ', '); }
  function colLabel(c) {
    if (c.indexOf('before-') === 0) return 'Before ' + c.slice(7);
    if (c === 'undated') return 'Undated';
    return c + 's';
  }
  function yearSpan(p) { return p.from + '–' + String(p.to).slice(2); }
  function maxCell(rows) {
    var m = 0;
    rows.forEach(function (r) { r.cells.forEach(function (n) { m = Math.max(m, n); }); });
    return m;
  }
  /* the name a linked count is read by: its row, its column and what it counts,
     since the figure alone ("672") says neither (U-5) */
  function cellName(row, col, n) {
    return row + ', ' + col + ': ' + nf(n) + (n === 1 ? ' counted record' : ' counted records');
  }
  /* a count, as a link to the Explorer view that lists the same records when
     observatory-core.js gives one (crossingLinks), as plain figures otherwise */
  function num(n, link, name) {
    if (!link) return nf(n);
    return '<a href="' + esc(link.href) + '"' + (name ? ' aria-label="' + attr(name) + '"' : '') +
      ' title="' + attr('Open in the Explorer: ' + link.query) + '">' + nf(n) + '</a>';
  }
  /* a count, with the shade behind it: weight over the largest weight of the table */
  function shade(n, weight, max, extra, link, name) {
    var t = n && max ? Math.min(1, weight / max) : 0;
    return '<td' + (t ? ' style="--t:' + t.toFixed(2) + '"' : '') + (n ? '' : ' class="zero"') + '>' +
      num(n, n ? link : null, name) + (extra || '') + '</td>';
  }
  /* the links of one crossing, by row kind, row key and column */
  function linker(core, v, sem) {
    var map = {};
    core.crossingLinks(v, sem).forEach(function (l) {
      map[l.row[0] + '|' + l.row[1] + '|' + l.col] = { href: core.explorerHref(l.query), query: l.query };
    });
    return function (kind, key, col) { return map[kind + '|' + key + '|' + col] || null; };
  }
  function toggle(id, label) {
    return '<button type="button" class="cross-toggle" aria-expanded="false" aria-controls="' + id +
      '">' + esc(label) + '</button>';
  }
  function notes(node, items) {
    node.innerHTML = items.map(function (s) { return '<li>' + s + '</li>'; }).join('');
  }
  function severalThemes(counted) {
    return 'A record carrying several themes is counted in each of their rows, so the rows add up to ' +
      'more than the ' + nf(counted) + ' counted records.';
  }

  function renderThemeDecade(v, sourceLabels, link) {
    var dmax = maxCell(v.rows), lmax = 0;
    v.rows.forEach(function (d) { lmax = Math.max(lmax, maxCell(d.leaves)); });
    var A = v.periods[0], B = v.periods[1];
    var heads = v.columns.map(function (c) { return '<th scope="col">' + colLabel(c) + '</th>'; }).join('');
    function drift(d, kind, key, label) {
      if (!d) {
        return '<td class="cross-drift"><span class="sr">under ' + v.drift_floor +
          ' in both periods</span></td>';
      }
      /* the space between the two spans keeps them apart when the page is read unstyled */
      return '<td class="cross-drift"><span class="cross-dv">' +
        arrow(num(d.from, link(kind, key, 'period-a'), cellName(label, yearSpan(A), d.from)),
          num(d.to, link(kind, key, 'period-b'), cellName(label, yearSpan(B), d.to))) + '</span> ' +
        '<span class="cross-ds">(' + arrow(pct1(d.from_share), pct1(d.to_share)) + ')</span></td>';
    }
    function cells(r, max, kind) {
      return '<td class="cross-tot">' + num(r.total, link(kind, r.key, 'total'), cellName(r.label, 'all decades', r.total)) + '</td>' +
        r.cells.map(function (n, i) {
          return shade(n, n, max, '', link(kind, r.key, v.columns[i]), cellName(r.label, colLabel(v.columns[i]), n));
        }).join('') +
        drift(r.drift, kind, r.key, r.label);
    }
    el('cap-theme-decade').textContent = 'Counted records by theme and decade of publication. Each ' +
      'domain opens onto its themes; the last column sets ' + yearSpan(A) + ' against ' + yearSpan(B) + '.';
    el('table-theme-decade').innerHTML =
      '<thead><tr><th scope="col">Theme</th><th scope="col">Records</th>' + heads +
      '<th scope="col">' + yearSpan(A) + ' → ' + yearSpan(B) + '</th></tr></thead>' +
      v.rows.map(function (d) {
        var id = 'td-' + d.key;
        return '<tbody><tr class="cross-dom"><th scope="row">' + toggle(id, d.label) + '</th>' +
          cells(d, dmax, 'domain') + '</tr></tbody>' +
          '<tbody id="' + id + '" class="cross-leaves" hidden>' + d.leaves.map(function (l) {
            return '<tr class="cross-leaf"><th scope="row">' + esc(l.label) + '</th>' + cells(l, lmax, 'theme') + '</tr>';
          }).join('') + '</tbody>';
      }).join('') +
      '<tfoot><tr><th scope="row">All counted records</th><td class="cross-tot">' + nf(v.counted) + '</td>' +
      v.column_totals.map(function (n, i) {
        return '<td>' + num(n, link('all', '', v.columns[i]), cellName('All counted records', colLabel(v.columns[i]), n)) + '</td>';
      }).join('') +
      '<td class="cross-drift"><span class="cross-dv">' +
      arrow(num(A.records, link('all', '', 'period-a'), cellName('All counted records', yearSpan(A), A.records)),
        num(B.records, link('all', '', 'period-b'), cellName('All counted records', yearSpan(B), B.records))) +
      '</span></td></tr></tfoot>';

    var hist = v.themes_per_record, parts = [];
    Object.keys(hist).map(Number).filter(function (k) { return k > 0; })
      .sort(function (a, b) { return a - b; }).forEach(function (k) {
        var n = hist[k], word = NUMBER_WORDS[k] || nf(k);
        parts.push(parts.length ? nf(n) + ' ' + word :
          nf(n) + (n === 1 ? ' carries ' : ' carry ') + word + (k === 1 ? ' theme' : ' themes'));
      });
    var none = hist[0] || 0, undated = v.column_totals[v.column_totals.length - 1];
    notes(el('notes-theme-decade'), [
      severalThemes(v.counted) + ' Of those, ' + joined(parts, 'and') + '.' +
        (none ? ' ' + nf(none) + (none === 1 ? ' carries no theme and sits' : ' carry no theme and sit') +
          ' in no row.' : ''),
      'The right-hand column gives the records of a row in ' + yearSpan(A) + ' and in ' + yearSpan(B) +
        ', then each count as a share of all counted records dated in its period (' + nf(A.records) +
        ' and ' + nf(B.records) + '). It is left blank where both counts are under ' + v.drift_floor + '.',
      'The last decade is open: it stops at ' + v.latest_year + '. ' + nf(undated) +
        (undated === 1 ? ' counted record carries no year and is' : ' counted records carry no year and are') +
        ' in neither period.',
      'A count opens the Explorer view that lists the same counted records, a decade as a range of years. ' +
        'The Undated column and the table of source labels below have no such query, and their counts stay plain.',
      EMPTY_CELL
    ]);

    var emax = maxCell(v.envelope), sum = 0;
    v.envelope.forEach(function (s) { sum += s.total; });
    el('cap-envelope').textContent = 'Counted records held by each source label, by decade of ' +
      'publication, to read an empty cell above against what was catalogued. A work cluster merged from ' +
      'several catalogues counts under each, so the rows add up to ' + nf(sum) + ' for ' +
      nf(v.counted) + ' records.';
    el('table-envelope').innerHTML =
      '<thead><tr><th scope="col">Source label</th><th scope="col">Records</th>' + heads + '</tr></thead><tbody>' +
      v.envelope.map(function (s) {
        return '<tr><th scope="row">' + esc(sourceLabels[s.source] || s.source) + '</th>' +
          '<td class="cross-tot">' + nf(s.total) + '</td>' +
          s.cells.map(function (n) { return shade(n, n, emax); }).join('') + '</tr>';
      }).join('') + '</tbody>';
  }

  function renderWorkDomain(v, domainLabel, link) {
    var max = maxCell(v.rows);
    el('cap-work-domain').textContent = 'Counted records by work of Origen and by the domains their ' +
      'themes fall in, for the ' + nf(v.rows.length) + ' works named by ' + v.work_floor +
      ' or more counted records.';
    el('table-work-domain').innerHTML =
      '<thead><tr><th scope="col">Work</th><th scope="col">Records</th>' +
      v.columns.map(function (c) { return '<th scope="col">' + esc(c.label) + '</th>'; }).join('') +
      '</tr></thead><tbody>' +
      v.rows.map(function (r) {
        return '<tr><th scope="row">' + esc(r.label) + '</th><td class="cross-tot">' +
          num(r.total, link('work', r.key, 'total'), cellName(r.label, 'all domains', r.total)) + '</td>' +
          r.cells.map(function (n, i) {
            return shade(n, n, max, '', link('work', r.key, v.columns[i].key), cellName(r.label, v.columns[i].label, n));
          }).join('') + '</tr>';
      }).join('') + '</tbody>';
    notes(el('notes-work-domain'), [
      nf(v.without_work) + ' of the ' + nf(v.counted) + ' counted records name no single work of ' +
        'Origen and are in no row.',
      'A study is counted under each domain its themes fall in, so a row adds up to more than its ' +
        'records. ' + nf(v.empty_cells) + ' of the ' + nf(v.cells) + ' cells hold 0.',
      'A count opens the Explorer view that lists the same counted records.',
      EMPTY_CELL
    ]);
    el('thin-work-domain-h').textContent = 'Zero cells in the works named by more than ' +
      v.thick_floor + ' counted records';
    el('thin-work-domain').innerHTML = v.thin.length ? v.thin.map(function (r) {
      var names = r.empty.map(function (d) { return esc(domainLabel[d] || d); });
      return '<li><strong>' + esc(r.label) + '</strong>: ' + nf(r.total) + ' counted, 0 in ' +
        (names.length > 1 ? 'each of ' + names.join('; ') : names[0]) + '.</li>';
    }).join('') : '<li>Each of these works has a counted record in every domain.</li>';
  }

  function renderDomainLang(v, langLabel, link) {
    var maxShare = 0;
    v.rows.forEach(function (r) { r.shares.forEach(function (s) { maxShare = Math.max(maxShare, s); }); });
    function cells(r, kind) {
      return '<td class="cross-tot">' + num(r.total, link(kind, r.key, 'total'), cellName(r.label, 'all languages', r.total)) +
        '</td>' + r.cells.map(function (n, i) {
          return shade(n, r.shares[i], maxShare, ' <span class="cross-sh">(' + pct1(r.shares[i]) + ')</span>',
            link(kind, r.key, v.columns[i]), cellName(r.label, langLabel[v.columns[i]] || v.columns[i], n));
        }).join('');
    }
    el('cap-domain-lang').textContent = 'Counted records by domain and language of publication, each ' +
      'count with its share of the row. Under each language, its share of all ' + nf(v.counted) +
      ' counted records. Each domain opens onto its themes.';
    el('table-domain-lang').innerHTML =
      '<thead><tr><th scope="col">Domain</th><th scope="col">Records</th>' +
      v.columns.map(function (c, i) {
        return '<th scope="col">' + esc(langLabel[c] || c) + ' <span class="cross-base">' +
          pct1(v.baseline_shares[i]) + ' of all</span></th>';
      }).join('') + '</tr></thead>' +
      v.rows.map(function (d) {
        var id = 'dl-' + d.key;
        return '<tbody><tr class="cross-dom"><th scope="row">' + toggle(id, d.label) + '</th>' + cells(d, 'domain') +
          '</tr></tbody><tbody id="' + id + '" class="cross-leaves" hidden>' + d.leaves.map(function (l) {
            return '<tr class="cross-leaf"><th scope="row">' + esc(l.label) + '</th>' + cells(l, 'theme') + '</tr>';
          }).join('') + '</tbody>';
      }).join('') +
      '<tfoot><tr><th scope="row">All counted records</th><td class="cross-tot">' + nf(v.counted) + '</td>' +
      v.baseline.map(function (n, i) {
        return '<td>' + num(n, link('all', '', v.columns[i]), cellName('All counted records', langLabel[v.columns[i]] || v.columns[i], n)) +
          ' <span class="cross-sh">(' + pct1(v.baseline_shares[i]) + ')</span></td>';
      }).join('') + '</tr></tfoot>';
    notes(el('notes-domain-lang'), [
      severalThemes(v.counted),
      esc(langLabel.oth || 'Other') + ' gathers the records with no language code and those in a ' +
        'language outside the ' + NUMBER_WORDS[v.columns.length - 1] + ' named.',
      'A count opens the Explorer view that lists the same counted records; ' + esc(langLabel.oth || 'Other') +
        ' opens as none of the ' + NUMBER_WORDS[v.columns.length - 1] + ' named languages.',
      'A share describes these catalogues as much as the field: see ' +
        '<a href="#limits">what these figures cannot say</a>.',
      EMPTY_CELL
    ]);
    var named = v.zero_languages.map(function (c) { return langLabel[c] || c; });
    el('zero-domain-lang-h').textContent = 'Themes of ' + v.leaf_floor + ' or more counted records ' +
      'with none in ' + joined(named, 'or');
    el('zero-domain-lang').innerHTML = v.zero.length ? v.zero.map(function (r) {
      return '<li><strong>' + esc(r.label) + '</strong>: ' + nf(r.total) + ' counted, 0 in ' +
        esc(joined(r.languages.map(function (c) { return langLabel[c] || c; }), 'and')) + '.</li>';
    }).join('') : '<li>Every theme of that size has a record in each of the ' +
      NUMBER_WORDS[named.length] + ' languages.</li>';
  }

  function wireCrossings() {
    var tabs = [].slice.call(document.querySelectorAll('#cross-tabs [role="tab"]'));
    if (!tabs.length) return;
    function select(tab, focus) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute('aria-selected', on ? 'true' : 'false');
        t.tabIndex = on ? 0 : -1;
        el(t.getAttribute('aria-controls')).hidden = !on;
      });
      markOverflow();
      if (focus) tab.focus();
    }
    tabs.forEach(function (tab, i) {
      tab.addEventListener('click', function () { select(tab, false); });
      tab.addEventListener('keydown', function (e) {
        var j = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 :
          e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : null;
        if (j == null) return;
        e.preventDefault();
        select(tabs[(j + tabs.length) % tabs.length], true);
      });
    });
    el('crossings').addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('.cross-toggle') : null;
      if (!b) return;
      var open = b.getAttribute('aria-expanded') !== 'true';
      b.setAttribute('aria-expanded', open ? 'true' : 'false');
      el(b.getAttribute('aria-controls')).hidden = !open;
      markOverflow();
    });
    var pending = false;
    window.addEventListener('resize', function () {
      if (pending) return;
      pending = true;
      requestAnimationFrame(function () { pending = false; markOverflow(); });
    });
  }

  function markOverflow() {
    [].forEach.call(document.querySelectorAll('.cross-wrap'), function (wrap) {
      wrap.classList.toggle('overflows', wrap.scrollWidth > wrap.clientWidth + 1);
    });
  }

  function renderCrossings(graph, sem, meta) {
    var core = window.ObservatoryCore;
    if (!core) throw new Error('observatory-core.js is not loaded');
    var sourceLabels = {}, langLabel = {}, domainLabel = {};
    (meta.sources_present || []).forEach(function (s) { sourceLabels[s.source] = sourceLabel(s.label); });
    LANGS.forEach(function (l) { langLabel[l.code] = l.label; });
    Object.keys(sem.domains).forEach(function (d) { domainLabel[d] = sem.domains[d].label; });
    var td = core.crossing('theme-decade', graph, sem), wd = core.crossing('work-domain', graph, sem);
    var dl = core.crossing('domain-lang', graph, sem);
    renderThemeDecade(td, sourceLabels, linker(core, td, sem));
    renderWorkDomain(wd, domainLabel, linker(core, wd, sem));
    renderDomainLang(dl, langLabel, linker(core, dl, sem));
    markOverflow();
  }
  /* /crossings */
})();
