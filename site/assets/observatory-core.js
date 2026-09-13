/* Origenality — the crossings of the Observatory, counted once.
   The page (observatory.js) and the command line (cli/origenality.mjs,
   `crossings`) call these functions on the same two files, graph.json and
   semantic.json, so a table on the screen and the JSON a program reads are
   the same numbers. Every count is a count of the records classed core or
   partial: the population of every figure on the site.
   Romain Girardi, 2026. MIT. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.ObservatoryCore = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var COUNTED = ['core', 'partial'];
  /* the languages the Observatory names, in the order of its legend
     (observatory.js, LANGS); any other code, or none, is 'oth' */
  var LANGUAGES = ['en', 'de', 'it', 'fr', 'es'];
  var OTHER = 'oth';
  /* the four languages whose empty cells are listed under the third table */
  var ZERO_LANGUAGES = ['en', 'de', 'fr', 'it'];
  var FIRST_DECADE = 1950;   // earlier years share one column
  var PERIODS = [[1980, 1999], [2010, null]];   // null: up to the latest dated year
  var DRIFT_FLOOR = 10;      // a row under this count in both periods shows no drift
  var WORK_FLOOR = 15;       // a work is a row when this many counted records name it
  var THICK_WORK = 50;       // works named by more records than this have their zero cells listed
  var LEAF_FLOOR = 30;       // themes of this many records or more have their zero language cells listed
  var VIEWS = ['theme-decade', 'work-domain', 'domain-lang'];

  function unique(list) {
    var out = [];
    (list || []).forEach(function (x) { if (out.indexOf(x) < 0) out.push(x); });
    return out;
  }
  function share(n, total) { return total ? Math.round(n * 1000 / total) / 10 : 0; }

  /* the counted records, reduced to what a crossing reads */
  function countedRecords(graph, sem) {
    var tags = sem.byPpn || {}, out = [];
    (graph.nodes || []).forEach(function (n) {
      if (n.k !== 'pub' || !n.ppn) return;
      var rec = tags[n.ppn];
      if (!rec || COUNTED.indexOf(rec.r) < 0) return;
      var themes = unique((rec.t || []).filter(function (t) { return sem.themes[t]; }));
      out.push({
        id: n.ppn,
        year: typeof n.year === 'number' ? n.year : null,
        lang: LANGUAGES.indexOf(n.lang) >= 0 ? n.lang : OTHER,
        sources: unique(n.src || []),
        themes: themes,
        domains: unique(themes.map(function (t) { return sem.themes[t].domain; })),
        works: unique((rec.w || []).filter(function (w) { return w !== 'unspecified' && sem.works[w]; }))
      });
    });
    return out;
  }

  /* crosstab(records, rowFn, colFn): rowFn and colFn return the keys a record
     falls under, several or none. A record is counted once in a cell, once in
     a row total and once in a column total, however many keys it carries. */
  function crosstab(records, rowFn, colFn) {
    var rows = [], cols = [], cells = {}, rowTotals = {}, colTotals = {}, total = 0;
    records.forEach(function (rec) {
      var rs = unique(rowFn(rec)), cs = unique(colFn(rec));
      if (!rs.length || !cs.length) return;
      total++;
      rs.forEach(function (r) {
        if (!Object.prototype.hasOwnProperty.call(rowTotals, r)) { rowTotals[r] = 0; cells[r] = {}; rows.push(r); }
        rowTotals[r]++;
        cs.forEach(function (c) { cells[r][c] = (cells[r][c] || 0) + 1; });
      });
      cs.forEach(function (c) {
        if (!Object.prototype.hasOwnProperty.call(colTotals, c)) { colTotals[c] = 0; cols.push(c); }
        colTotals[c]++;
      });
    });
    return { rows: rows, cols: cols, cells: cells, rowTotals: rowTotals, colTotals: colTotals, total: total };
  }
  function cell(tab, r, c) { return (tab.cells[r] && tab.cells[r][c]) || 0; }
  function rowTotal(tab, r) { return tab.rowTotals[r] || 0; }

  function decadeKey(year) {
    if (year == null) return 'undated';
    if (year < FIRST_DECADE) return 'before-' + FIRST_DECADE;
    return String(Math.floor(year / 10) * 10);
  }
  function latestYear(records) {
    var y = null;
    records.forEach(function (r) { if (r.year != null && (y == null || r.year > y)) y = r.year; });
    return y;
  }
  function decadeColumns(records) {
    var last = FIRST_DECADE;
    records.forEach(function (r) {
      if (r.year != null && r.year >= FIRST_DECADE) last = Math.max(last, Math.floor(r.year / 10) * 10);
    });
    var cols = ['before-' + FIRST_DECADE];
    for (var d = FIRST_DECADE; d <= last; d += 10) cols.push(String(d));
    cols.push('undated');
    return cols;
  }
  function byDomainThenLeaf(sem) {
    return Object.keys(sem.domains).map(function (d) {
      return { key: d, leaves: Object.keys(sem.themes).filter(function (t) { return sem.themes[t].domain === d; }) };
    });
  }
  var themesOf = function (r) { return r.themes; };
  var domainsOf = function (r) { return r.domains; };
  var worksOf = function (r) { return r.works; };

  function themeDecade(graph, sem) {
    var recs = countedRecords(graph, sem);
    var columns = decadeColumns(recs);
    var latest = latestYear(recs);
    var decade = function (r) { return [decadeKey(r.year)]; };
    var periods = PERIODS.map(function (p) {
      var to = p[1] == null ? latest : p[1];
      return {
        from: p[0], to: to,
        records: recs.filter(function (r) { return r.year != null && r.year >= p[0] && r.year <= to; }).length
      };
    });
    var period = function (r) {
      if (r.year == null) return [];
      if (r.year >= periods[0].from && r.year <= periods[0].to) return ['a'];
      if (r.year >= periods[1].from && r.year <= periods[1].to) return ['b'];
      return [];
    };
    function drift(tab, key) {
      var a = cell(tab, key, 'a'), b = cell(tab, key, 'b');
      if (a < DRIFT_FLOOR && b < DRIFT_FLOOR) return null;
      return { from: a, to: b, from_share: share(a, periods[0].records), to_share: share(b, periods[1].records) };
    }
    var dom = crosstab(recs, domainsOf, decade), leaf = crosstab(recs, themesOf, decade);
    var domDrift = crosstab(recs, domainsOf, period), leafDrift = crosstab(recs, themesOf, period);
    var all = crosstab(recs, function () { return ['all']; }, decade);
    var env = crosstab(recs, function (r) { return r.sources; }, decade);
    var hist = {};
    recs.forEach(function (r) { hist[r.themes.length] = (hist[r.themes.length] || 0) + 1; });
    return {
      view: 'theme-decade',
      counted: recs.length,
      columns: columns,
      latest_year: latest,
      periods: periods,
      drift_floor: DRIFT_FLOOR,
      rows: byDomainThenLeaf(sem).map(function (d) {
        return {
          key: d.key, label: sem.domains[d.key].label, total: rowTotal(dom, d.key),
          cells: columns.map(function (c) { return cell(dom, d.key, c); }),
          drift: drift(domDrift, d.key),
          leaves: d.leaves.map(function (t) {
            return {
              key: t, label: sem.themes[t].label, total: rowTotal(leaf, t),
              cells: columns.map(function (c) { return cell(leaf, t, c); }),
              drift: drift(leafDrift, t)
            };
          })
        };
      }),
      column_totals: columns.map(function (c) { return cell(all, 'all', c); }),
      envelope: env.rows.slice().sort(function (a, b) {
        return (env.rowTotals[b] - env.rowTotals[a]) || (a < b ? -1 : 1);
      }).map(function (s) {
        return { source: s, total: env.rowTotals[s], cells: columns.map(function (c) { return cell(env, s, c); }) };
      }),
      themes_per_record: hist
    };
  }

  function workDomain(graph, sem) {
    var recs = countedRecords(graph, sem);
    var domains = Object.keys(sem.domains);
    var tab = crosstab(recs, worksOf, domainsOf);
    var named = crosstab(recs, worksOf, function () { return ['all']; });
    var rows = named.rows.filter(function (w) { return named.rowTotals[w] >= WORK_FLOOR; })
      .sort(function (a, b) { return (named.rowTotals[b] - named.rowTotals[a]) || (a < b ? -1 : 1); })
      .map(function (w) {
        return {
          key: w, label: sem.works[w].label, total: named.rowTotals[w],
          cells: domains.map(function (d) { return cell(tab, w, d); })
        };
      });
    var empty = 0;
    rows.forEach(function (r) { r.cells.forEach(function (n) { if (!n) empty++; }); });
    return {
      view: 'work-domain',
      counted: recs.length,
      without_work: recs.filter(function (r) { return !r.works.length; }).length,
      work_floor: WORK_FLOOR,
      thick_floor: THICK_WORK,
      columns: domains.map(function (d) { return { key: d, label: sem.domains[d].label }; }),
      rows: rows,
      cells: rows.length * domains.length,
      empty_cells: empty,
      thin: rows.filter(function (r) { return r.total > THICK_WORK; }).map(function (r) {
        return {
          key: r.key, label: r.label, total: r.total,
          empty: domains.filter(function (d, i) { return !r.cells[i]; })
        };
      }).filter(function (r) { return r.empty.length; })
    };
  }

  function domainLanguage(graph, sem) {
    var recs = countedRecords(graph, sem);
    var cols = LANGUAGES.concat([OTHER]);
    var lang = function (r) { return [r.lang]; };
    var base = crosstab(recs, function () { return ['all']; }, lang);
    var dom = crosstab(recs, domainsOf, lang), leaf = crosstab(recs, themesOf, lang);
    function row(tab, key, label) {
      var total = rowTotal(tab, key);
      return {
        key: key, label: label, total: total,
        cells: cols.map(function (c) { return cell(tab, key, c); }),
        shares: cols.map(function (c) { return share(cell(tab, key, c), total); })
      };
    }
    var zero = [];
    var rows = byDomainThenLeaf(sem).map(function (d) {
      var out = row(dom, d.key, sem.domains[d.key].label);
      out.leaves = d.leaves.map(function (t) {
        var l = row(leaf, t, sem.themes[t].label);
        if (l.total >= LEAF_FLOOR) {
          var missing = ZERO_LANGUAGES.filter(function (c) { return !l.cells[cols.indexOf(c)]; });
          if (missing.length) zero.push({ key: t, label: l.label, total: l.total, languages: missing });
        }
        return l;
      });
      return out;
    });
    return {
      view: 'domain-lang',
      counted: recs.length,
      columns: cols,
      baseline: cols.map(function (c) { return cell(base, 'all', c); }),
      baseline_shares: cols.map(function (c) { return share(cell(base, 'all', c), recs.length); }),
      rows: rows,
      leaf_floor: LEAF_FLOOR,
      zero_languages: ZERO_LANGUAGES.slice(),
      zero: zero
    };
  }

  /* ---------------------------------------------------------- links to the Explorer
     A count links to the Explorer view that lists the same records, where the
     Explorer's grammar names that set exactly: a heading by its key (theme:,
     domain:, work:), a decade or a period by a year range, a language by its
     code, and "other or none" as none of the five named. A key that begins
     another key of its field would catch both, so it gets no link; nor do the
     records without a year, nor the table of source labels, which no query
     names. The Explorer's headline for a field query counts the counted records
     it lists, which is the count in the cell; site/build-c/qa/check_crossings.py
     recomputes every linked count through search-core.js. */
  function hashValue(v) {
    // the Explorer's own encoding of an address value (explorer.js, hashValue)
    return encodeURIComponent(v).replace(/%3A/gi, ':').replace(/%2C/gi, ',')
      .replace(/%2F/gi, '/').replace(/%20/g, '+');
  }
  function keyTerm(field, key, keys) {
    if (!key || /\s/.test(key)) return null;
    var k = String(key).toLowerCase();
    var clash = keys.some(function (other) {
      return other !== key && String(other).toLowerCase().indexOf(k) === 0;
    });
    return clash ? null : field + ':' + key;
  }
  function decadeTerm(col) {
    if (col.indexOf('before-') === 0) return 'year:<' + col.slice(7);
    var d = /^\d{4}$/.test(col) ? Number(col) : null;
    return d == null ? null : 'year:' + d + '-' + (d + 9);
  }
  function periodTerm(p) { return 'year:' + p.from + '-' + p.to; }
  function langTerm(code) {
    if (LANGUAGES.indexOf(code) >= 0) return 'lang:' + code;
    if (code === OTHER) return LANGUAGES.map(function (c) { return '-lang:' + c; }).join(' ');
    return null;
  }
  function explorerHref(query) { return 'index.html#q=' + hashValue(query); }

  /* Every non-empty count of a crossing that an Explorer query reproduces, as
     { row: [kind, key], col, n, query }. kind is domain, theme, work, or all for
     the foot of a table; col is a column key, total, or period-a and period-b. */
  function crossingLinks(v, sem) {
    var out = [];
    var keys = { theme: Object.keys(sem.themes), domain: Object.keys(sem.domains), work: Object.keys(sem.works) };
    function add(kind, key, col, n, terms) {
      if (!n) return;
      for (var i = 0; i < terms.length; i++) if (!terms[i]) return;
      out.push({ row: [kind, key], col: col, n: n, query: terms.join(' ') });
    }
    var decadeRow = function (kind, r) {
      var t = keyTerm(kind, r.key, keys[kind]);
      add(kind, r.key, 'total', r.total, [t]);
      v.columns.forEach(function (c, i) { add(kind, r.key, c, r.cells[i], [t, decadeTerm(c)]); });
      if (r.drift) {
        add(kind, r.key, 'period-a', r.drift.from, [t, periodTerm(v.periods[0])]);
        add(kind, r.key, 'period-b', r.drift.to, [t, periodTerm(v.periods[1])]);
      }
    };
    var langRow = function (kind, r) {
      var t = keyTerm(kind, r.key, keys[kind]);
      add(kind, r.key, 'total', r.total, [t]);
      v.columns.forEach(function (c, i) { add(kind, r.key, c, r.cells[i], [t, langTerm(c)]); });
    };
    if (v.view === 'theme-decade') {
      v.rows.forEach(function (d) {
        decadeRow('domain', d);
        d.leaves.forEach(function (l) { decadeRow('theme', l); });
      });
      v.columns.forEach(function (c, i) { add('all', '', c, v.column_totals[i], [decadeTerm(c)]); });
      add('all', '', 'period-a', v.periods[0].records, [periodTerm(v.periods[0])]);
      add('all', '', 'period-b', v.periods[1].records, [periodTerm(v.periods[1])]);
    } else if (v.view === 'work-domain') {
      v.rows.forEach(function (r) {
        var t = keyTerm('work', r.key, keys.work);
        add('work', r.key, 'total', r.total, [t]);
        v.columns.forEach(function (c, i) {
          add('work', r.key, c.key, r.cells[i], [t, keyTerm('domain', c.key, keys.domain)]);
        });
      });
    } else if (v.view === 'domain-lang') {
      v.rows.forEach(function (d) {
        langRow('domain', d);
        d.leaves.forEach(function (l) { langRow('theme', l); });
      });
      v.columns.forEach(function (c, i) { add('all', '', c, v.baseline[i], [langTerm(c)]); });
    }
    return out;
  }

  /* The build identifier, as the Explorer derives it (explorer.js, buildIdOf):
     the day META.json says the data layer was generated, as yyyymmdd, a hyphen,
     and the number of work clusters it holds. Null when META.json lacks either
     part, so no page ever types one by hand. */
  function buildIdOf(meta) {
    if (!meta || !/^\d{4}-\d{2}-\d{2}$/.test(String(meta.generated || ''))) return null;
    var n = Number(meta.records);
    if (!(n > 0) || Math.floor(n) !== n) return null;
    return meta.generated.replace(/-/g, '') + '-' + n;
  }

  function crossing(view, graph, sem) {
    if (view === 'theme-decade') return themeDecade(graph, sem);
    if (view === 'work-domain') return workDomain(graph, sem);
    if (view === 'domain-lang') return domainLanguage(graph, sem);
    throw new Error('unknown crossing "' + view + '"; use ' + VIEWS.join(', '));
  }

  return {
    VIEWS: VIEWS, LANGUAGES: LANGUAGES, OTHER: OTHER, ZERO_LANGUAGES: ZERO_LANGUAGES,
    buildIdOf: buildIdOf, crossingLinks: crossingLinks, explorerHref: explorerHref, countedRecords: countedRecords, crosstab: crosstab, decadeKey: decadeKey,
    themeDecade: themeDecade, workDomain: workDomain, domainLanguage: domainLanguage,
    crossing: crossing
  };
}));
