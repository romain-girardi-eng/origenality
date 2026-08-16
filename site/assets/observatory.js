/* Origenality — Observatory. Reads the published statistics and the tag file,
   counts nothing it cannot show, and states the perimeter with every figure.
   Romain Girardi, 2026. No external requests, no third party code. */
(function () {
  'use strict';

  var LANGS = [
    { code: 'eng', label: 'English', col: '#1F5674' },
    { code: 'ger', label: 'German', col: '#A8371F' },
    { code: 'ita', label: 'Italian', col: '#8A6A12' },
    { code: 'fre', label: 'French', col: '#4F7350' },
    { code: 'spa', label: 'Spanish', col: '#B15A17' },
    { code: 'oth', label: 'Other or none', col: '#78766F' }
  ];
  var LCOL = {}; LANGS.forEach(function (l) { LCOL[l.code] = l.col; });
  var SET_COL = { density: '#1F5674', marginal: '#8A6A12', none: '#78766F' };

  function nf(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' '); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function el(id) { return document.getElementById(id); }
  function pc(n, total) { return total ? (n / total * 100) : 0; }

  Promise.all([
    fetch('../data/stats.json').then(function (r) { return r.json(); }),
    fetch('../data/META.json').then(function (r) { return r.json(); }),
    fetch('assets/semantic.json').then(function (r) { return r.json(); }),
    // the records themselves: year, language and format are counted here on the
    // one population the whole site counts, rather than on the raw harvest
    fetch('../data/graph.json').then(function (r) { return r.json(); })
  ]).then(function (r) { render(r[0], r[1], r[2], r[3]); }).catch(function (e) {
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
      return '<span><i style="background:' + SET_COL[row.k] + '"></i><b>' + nf(row.n) + '</b> ' +
        esc(row.label) + ' <span style="color:var(--stone)">— ' + esc(row.note) + '</span></span>';
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
      (untagged ? ' — the other ' + nf(untagged) + ' of the ' + nf(mapTotal) +
        ' on this map carry no class at all —' : '') +
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
    var scope = [
      { v: nf(meta.records_harvested_total || t.records), k: 'records harvested',
        n: 'IxTheo authority record for Origen, ' + esc(meta.harvested || stats.generated) },
      { v: nf((meta.excluded && meta.excluded.relation_by) || 0), k: 'editions set aside',
        n: 'works by Origen, not about him' },
      { v: nf(t.records), k: 'records kept', n: 'the harvest, index and search alike' },
      { v: nf(COUNT_N), k: 'records counted',
        n: 'Origen the subject, or holding a section — the population of every figure here' },
      { v: nf(t.distinct_authors), k: 'distinct authors', n: 'as spelled by the catalogue' },
      { v: nf(t.distinct_containers), k: 'journals and volumes', n: 'containers holding at least one record' },
      { v: nf(t.records_with_doi), k: 'records with a DOI',
        n: nf(t.records_with_isbn) + ' carry an ISBN' }
    ];
    el('scope-grid').innerHTML = scope.map(function (s) {
      return '<div class="card stat"><span class="v">' + s.v + '</span>' +
        '<span class="k">' + esc(s.k) + '</span><span class="n">' + esc(s.n) + '</span></div>';
    }).join('');

    el('stamp').textContent = 'Harvest of ' + (meta.harvested || stats.generated) + ' · ' +
      nf(COUNT_N) + ' counted records of ' + nf(t.records) +
      ' · one source, IxTheo / K10plus (CC0)';
    el('foot-stamp').textContent = 'Figures generated ' + (stats.generated || meta.harvested);

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
      var row = dec[d], h = maxD ? (row.n / maxD * 130) : 0;
      var stack = LANGS.map(function (l) {
        var v = row.lang[l.code] || 0;
        if (!v) return '';
        return '<span style="height:' + (row.n ? (v / row.n * h) : 0).toFixed(1) +
          'px;background:' + l.col + '"></span>';
      }).join('');
      return '<div class="c"><span class="vv">' + row.n + '</span>' +
        '<span class="st" style="height:' + h.toFixed(1) + 'px">' + stack + '</span>' +
        '<span class="lb">' + String(d).slice(2) + '</span></div>';
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
  }
})();
