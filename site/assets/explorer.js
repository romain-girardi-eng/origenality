/* Origenality — Explorer, direction C.
   Clusters drawn as dust on a cream field. One publication is one gaussian
   of grains from the earlier personal-graph particle engine. Language tints the grain.
   Named from the controlled vocabulary: theme domains and their leaves, or
   the works of Origen. Romain Girardi, 2026. */
import { createDustField } from './dust-field.js?v=497d3748';

(function () {
  'use strict';

  var RM = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var MOBILE = matchMedia('(max-width:760px)').matches;
  // The build this page shows is read from the data layer at load (buildIdOf),
  // never typed here: the citation, the b= key of a link and the line that says
  // a link was made on another build all follow the data the page reads.
  var DATA_VERSION = null, META = null;
  // references (BibTeX, RIS, CSL-JSON, COinS): cite.js, a classic script loaded
  // before this module, required as it is by scripts/test_cite_export.mjs
  var CITE = (typeof OrigenalityCite !== 'undefined') ? OrigenalityCite : null;

  /* ------------------------------------------------------------------ palette */
  var LANGS = [
    { code: 'en', label: 'English', col: '#1F5674' },
    { code: 'de', label: 'German', col: '#A8371F' },
    { code: 'it', label: 'Italian', col: '#8A6A12' },
    { code: 'fr', label: 'French', col: '#4F7350' },
    { code: 'es', label: 'Spanish', col: '#B15A17' },
    { code: 'oth', label: 'Other or none', col: '#78766F' }
  ];
  var LCOL = {}, LLAB = {};
  LANGS.forEach(function (l) { LCOL[l.code] = l.col; LLAB[l.code] = l.label; });
  function lkey(c) { return LCOL[c] ? c : 'oth'; }

  var INK = '#23201B', STONE = '#6A6353', ACCENT = '#A03620', PAPER = '#F7F2E6';

  /* ------------------------------------------------------------------ utilities */
  // The search semantics live in search-core.js, loaded before this file and
  // required by the CLI: one implementation, so a reader and an agent cannot
  // be shown two different bibliographies. See scripts/check_search_parity.py.
  var CORE = (typeof OrigenalitySearch !== 'undefined') ? OrigenalitySearch : null;
  var norm = CORE ? CORE.norm : function (s) {
    return (s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  };
  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  function nf(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' '); }
  function hexA(hex, a) {
    var r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
    return 'rgba(' + r + ',' + g + ',' + b + ',' + a + ')';
  }
  function easeOut(t) { return 1 - Math.pow(1 - t, 3); }
  function ordinal(n) {
    var s = ['th', 'st', 'nd', 'rd'], v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  }
  // the short name of a base, for the line that links back to its record
  var SRC_NAME = {
    'ixtheo-k10plus': 'IxTheo', 'openalex': 'OpenAlex', 'crossref': 'Crossref',
    'semanticscholar': 'Semantic Scholar', 'bibp': 'BIBP', 'adamantius-girota': 'Adamantius',
    'isidore': 'ISIDORE', 'thesesfr': 'theses.fr', 'dialnet': 'Dialnet', 'sbn': 'SBN',
    'gnomon-gbd': 'Gnomon', 'k10plus': 'K10plus', 'sudoc': 'Sudoc', 'b3kat': 'B3Kat',
    'dnb': 'DNB', 'loc': 'Library of Congress', 'bnf': 'BnF'
  };
  function sourceName(key) {
    if (SRC_NAME[key]) return SRC_NAME[key];
    var s = ABS && ABS.sources && ABS.sources[key];
    return (s && s.label) || key || 'Catalogue';
  }
  function altLine(entry) {
    if (!entry || !entry.labels) return '';
    return ['de', 'fr', 'it'].map(function (k) { return entry.labels[k]; })
      .filter(Boolean).join(' · ');
  }
  /* ------------------------------------------------------------------ state */
  var DATA = null, WEIGHTS = null, SEM = null, ABS = null;
  // beyond this many characters a summary is folded to four lines, with a
  // control to unfold it: the panel lists twenty records at a time and three
  // full abstracts in a row would bury the rest.
  var ABSTRACT_FOLD = 320;
  var CLUSTERS = [], PUBS = [], BUILT = {}, MODE = 'theme';
  // five clear size tiers, so the eye reads rank rather than a continuum
  var TIERS = [2.3, 3.0, 3.9, 4.9, 6.2], TIER_CUT = [0.2, 0.4, 0.6, 0.8];
  var GAP_PUB = 2.6, GAP_SUB = 5.2;
  // the gap between two clouds follows their own size, so a field of small
  // clusters stays gathered instead of drifting apart
  function gapOf(a, b) {
    var ra = a.mr == null ? a.r : a.mr, rb = b.mr == null ? b.r : b.mr;
    return Math.max(20, Math.min(46, (ra + rb) * 0.5));
  }
  var langOff = {};                       // language code -> hidden
  var sel = null, hover = null, selPub = null, hoverPub = null, query = '';
  var wizAns = { work: [], approach: [], decade: [], lang: [] };
  var matched = null;                     // Set of publication indices, or null for "everything"
  var shelfOnly = null;                   // Set of indices reached only through a heading
  var matchLabel = '', hitDepth = 0, tokCount = 0;
  // What the answer really is, kept apart from what the relaxation returns.
  // fullHit: records that carry EVERY term. absentToks: terms that appear
  // nowhere in the corpus. relaxed: the answer on screen is not the answer asked.
  var fullHit = 0, absentToks = [], relaxed = false, vocabHit = 0, vocabLabel = '';
  // fullHitCounted: the same, counted. absentFiltered: terms present in the
  // corpus but in none of the records the filters leave. vocabHitCounted: the
  // heading figure, counted. queryProblem: why the text was not searched.
  var fullHitCounted = 0, absentFiltered = [], vocabHitCounted = 0, queryProblem = '';
  // IDX: the shared index. LAST: the engine's last result, RANK its reading
  // order by record index. scopeDens: counted records the questions leave.
  var IDX = null, LAST = null, RANK = null, scopeDens = 0;
  // VIEW: what the open panel shows (see renderPanel), read by the citation
  // and by any later surface that works on the current view.
  var VIEW = null;
  // CMP: the query the decade strip sets beside the view (cmp= in the address).
  // STRIP: the rows the strip shows, which the SVG and the CSV are written from.
  var CMP = '', STRIP = null;
  // selAuthor: the author node whose records the panel lists (a= in the address);
  // shownAuthor: the author of the view on screen, from a click or an author: query.
  // AUTHORS: the author nodes of graph.json and the records their edges reach.
  var selAuthor = null, shownAuthor = null, AUTHORS = null;
  // linkBuild: the build a restored link was made on, when it is not this one
  var linkBuild = null;
  // headings: what the index holds of each record's subject headings and
  // container. 'loading' until data/cite.json is read after the first render,
  // 'complete' once it is, 'failed' when it cannot be read: the index then holds
  // only the headings graph.json keeps. absentPartial: the terms a partial index
  // did not find, which no surface calls absent.
  var headings = 'loading', absentPartial = [];
  // stateText: the state line as the answer writes it, before the build note
  var stateText = '';
  var cam = { s: 1, x: 0, y: 0 }, tcam = { s: 1, x: 0, y: 0 };
  var tweenT0 = 0, tweenMs = 0, animating = false;

  // A reservoir is folded by default: named and counted under the field, drawn
  // on the map only when the reader asks for it. The named clusters come first.
  var folded = {};
  function isFolded(c) { return c.kind === 'tail' && folded[c.id] !== false; }
  // One population per screen, and the same one the Observatory counts: every
  // figure printed here is a count of the 1 400 records classed core or partial.
  // Retrieval is wider than counting — a record where Origen is mentioned only
  // still answers a question and is still listed — so the two are kept apart:
  //   counts(p)    the record enters a figure
  //   reachable(p) the record can be returned by a question or a search
  // Wherever the two differ, the surface says by how many, in words.
  function counts(p) { return p.dens; }
  function reachable(p) { return p.rel !== 'none'; }

  var OFF = '__off', NO_THEME = '__nothe', NO_WORK = '__nowork';
  var TAIL_LABEL = {};
  TAIL_LABEL[OFF] = 'Not about Origen';
  TAIL_LABEL[NO_THEME] = 'No theme recorded';
  TAIL_LABEL[NO_WORK] = 'No single work';

  var cv = document.getElementById('field-c'), ctx = cv.getContext('2d');
  var glc = document.getElementById('field-gl');
  var W = 0, H = 0, DPR = Math.min(devicePixelRatio || 1, 2);
  var dust = null;

  function sizeField() {
    W = innerWidth; H = innerHeight;
    cv.width = W * DPR; cv.height = H * DPR;
    cv.style.width = W + 'px'; cv.style.height = H + 'px';
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    if (glc) {
      glc.style.width = W + 'px';
      glc.style.height = H + 'px';
    }
    if (dust) dust.resize(W, H);
  }
  sizeField();
  try {
    if (glc) dust = createDustField(glc, { mobile: MOBILE, reduceMotion: RM });
    if (dust) dust.resize(W, H);
  } catch (err) {
    dust = null;
    console.warn('Explorer dust: WebGL field could not start.', err);
  }

  function resize() {
    sizeField();
    invalidate();
  }

  /* ------------------------------------------------------------------ load */
  // The build identifier: the day the data layer was generated, as yyyymmdd, a
  // hyphen, and the number of work clusters it holds; the form the links made
  // since 24 August carry. BUILD.json and META.json hold no identifier of their own;
  // META.json holds both parts, and graph.json holds the same two.
  function buildIdOf(meta) {
    if (!meta || !/^\d{4}-\d{2}-\d{2}$/.test(String(meta.generated || ''))) return null;
    var n = Number(meta.records);
    if (!(n > 0) || Math.floor(n) !== n) return null;
    return meta.generated.replace(/-/g, '') + '-' + n;
  }
  function versioned(url) { return DATA_VERSION ? url + '?v=' + DATA_VERSION : url; }
  // META.json is small and revalidated on every visit; its build then keys the
  // cache of the larger files, so a new build is never served from an old copy
  fetch('../data/META.json', { cache: 'no-cache' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .catch(function () { return null; })
    .then(function (meta) {
      META = meta;
      DATA_VERSION = buildIdOf(meta);
      var opt = DATA_VERSION ? {} : { cache: 'no-cache' };
      return Promise.all([
        fetch(versioned('../data/graph.json'), opt).then(function (r) { return r.json(); }),
        fetch(versioned('assets/weights.json'), opt).then(function (r) { return r.json(); }).catch(function () { return null; }),
        fetch(versioned('assets/semantic.json'), opt).then(function (r) { return r.json(); }),
        // the summaries: a record reads better with one, and the reader who
        // searches expects their words to count. Missing, the map still works.
        fetch(versioned('../data/abstracts.json'), opt).then(function (r) { return r.json(); }).catch(function () { return null; })
      ]);
    }).then(function (r) {
      WEIGHTS = r[1]; SEM = r[2]; ABS = r[3];
      // META.json unread: the graph gives the day and the records itself
      if (!DATA_VERSION) {
        DATA_VERSION = buildIdOf({
          generated: r[0].generated,
          records: (r[0].nodes || []).filter(function (n) { return n && n.k === 'pub'; }).length
        });
      }
      build(r[0]);
      completeIndex();
    }).catch(function (e) {
    document.getElementById('ask-state').textContent = 'The map could not be loaded.';
    console.error(e);
  });

  /* ------------------------------------------------------------------ model */
  function build(g) {
    DATA = g;
    // The one index, built by search-core.js for the page and for the CLI alike.
    // `lang` and `rawlang` keep the catalogue's code, the value the lang: filter
    // compares; the page adds `lkey`, the colour and legend key, and the fields
    // it draws with (weight, tier, disc radius, grains).
    IDX = CORE.buildIndex(g, SEM, ABS);
    PUBS = IDX.records;
    RECORD_KEYS = null;
    AUTHORS = null;
    PUBS.forEach(function (p) {
      p.lkey = lkey(p.rawlang);
      var wr = (WEIGHTS && WEIGHTS.w && WEIGHTS.w[p.ppn]) || null;
      var wv = wr ? wr.w : 0.5;
      var tier = 0;
      while (tier < TIER_CUT.length && wv > TIER_CUT[tier]) tier++;
      p.w = wv; p.tier = tier; p.r = TIERS[tier]; p.wr = wr;
      p.o = {}; p.lobeName = null;
      attachGrains(p);
    });

    buildMode('theme');
    useMode('theme', false);
    boot();
    invalidate();
  }

  /* Every subject heading and container of a record, read after the first
     render. graph.json keeps a heading only when three records share it and a
     container only when five do; until data/cite.json is read the index holds
     those alone, the state line says so, and no term is called absent. The CLI
     reads the same file before it answers, through the same applyCite. */
  var citeAsked = null;
  function readCiteFile() {
    if (!citeAsked) {
      citeAsked = fetch(versioned('../data/cite.json')).then(function (r) {
        if (!r.ok) throw new Error('cite.json answered ' + r.status);
        return r.json();
      });
    }
    return citeAsked;
  }
  function completeIndex() {
    readCiteFile().then(function (json) {
      CORE.applyCite(IDX, json);
      headings = IDX.fields === 'complete' ? 'complete' : 'failed';
    }, function (err) {
      headings = 'failed';
      console.warn('Explorer search: ' + err.message + '; only the headings graph.json keeps are searched');
    }).then(refreshAnswer);
  }
  // the answer on screen, counted again on the completed index; the field is
  // laid out again only when the records it answers with have changed
  function refreshAnswer() {
    if (!CLUSTERS.length) return;
    var open = panel.classList.contains('open');
    var had = document.activeElement;
    var inside = open && !!had && had !== panel && panel.contains(had);
    if (matched || queryProblem || !CORE.queryIsBlank(query)) applyMatch(false, true);
    if (open && VIEW) {
      renderPanel();
      // only a control inside the panel that the redraw took away hands the
      // focus on; the panel itself, or a field outside it, keeps it
      if (inside && !document.contains(had)) focusPanelHead();
    }
  }

  /* ------------------------------------------------------------------ grouping */
  function homeOf(p, mode) {
    if (p.rel === 'none') return { c: OFF, lobe: null };
    if (mode === 'work') {
      if (!p.works.length) return { c: NO_WORK, lobe: lobeDomain(p) };
      return { c: 'w:' + p.works[0], lobe: lobeDomain(p) };
    }
    if (!p.themes.length) return { c: NO_THEME, lobe: null };
    var t0 = p.themes[0];
    return { c: 'dom:' + SEM.themes[t0].domain, lobe: SEM.themes[t0].label };
  }
  function lobeDomain(p) {
    if (!p.themes.length) return null;
    return SEM.domains[SEM.themes[p.themes[0]].domain].label;
  }
  function clusterMeta(id) {
    if (id.indexOf('dom:') === 0) {
      var d = SEM.domains[id.slice(4)];
      return { kind: 'subject', label: d.label, alt: altLine(d), note: 'Theme domain', rank: 'leaf' };
    }
    if (id.indexOf('w:') === 0) {
      var w = SEM.works[id.slice(2)];
      var cat = SEM.workCategories[w.category];
      return {
        kind: 'subject', label: w.label, alt: cat ? cat.label : '',
        note: 'Work of Origen', rank: 'domain'
      };
    }
    if (id === OFF) {
      return {
        kind: 'tail', label: TAIL_LABEL[id],
        alt: 'Harvest noise: homonyms, or metadata too thin to answer the question. Kept, never deleted.',
        note: 'Held outside the density'
      };
    }
    return {
      kind: 'tail', label: TAIL_LABEL[id] || id,
      alt: id === NO_WORK ? 'Studies that bear on no single work of Origen.' : '',
      note: 'Outside the named clusters'
    };
  }

  function buildMode(mode) {
    if (BUILT[mode]) return;
    var byId = {}, list = [];
    function ensure(id) {
      if (!byId[id]) {
        var m = clusterMeta(id);
        byId[id] = {
          id: id, kind: m.kind, label: m.label, alt: m.alt, note: m.note,
          pubs: [], mix: {}, x: 0, y: 0, r: 0
        };
        list.push(byId[id]);
      }
      return byId[id];
    }
    PUBS.forEach(function (p) {
      var h = homeOf(p, mode);
      p.lobeName = h.lobe;
      ensure(h.c).pubs.push(p);
    });
    list = list.filter(function (c) { return c.pubs.length > 0; });
    list.forEach(function (c, k) {
      c.k = k; c.n = c.pubs.length;
      c.dens = 0;
      c.pubs.forEach(function (p) {
        // the language mix breaks down the figure the card prints, not the
        // wider set the cluster holds: the reservoir of records held aside
        // shows its own, everything else shows the counted records
        if (p.dens || c.id === OFF) c.mix[p.lkey] = (c.mix[p.lkey] || 0) + 1;
        if (p.dens) c.dens++;
      });
    });

    var links = mode === 'work' ? workLinks(list, byId) : themeLinks(list, byId);
    list.forEach(function (c) { c.near = []; });
    links.forEach(function (l) {
      list[l.a].near.push({ k: l.b, w: l.w });
      list[l.b].near.push({ k: l.a, w: l.w });
    });
    list.forEach(function (c) { c.near.sort(function (x, y) { return y.w - x.w; }); });

    // keep the strongest three drawn trails per cluster, so the field stays readable
    var kept = [], cnt = {};
    links.slice().sort(function (x, y) { return y.w - x.w; }).forEach(function (l) {
      cnt[l.a] = cnt[l.a] || 0; cnt[l.b] = cnt[l.b] || 0;
      if (cnt[l.a] < 3 && cnt[l.b] < 3) { kept.push(l); cnt[l.a]++; cnt[l.b]++; }
    });

    var saved = CLUSTERS;
    CLUSTERS = list;
    list.forEach(packCluster);
    layoutBase(list, kept);
    PUBS.forEach(function (p) { p.o[mode] = [p.ox, p.oy]; });
    CLUSTERS = saved;
    BUILT[mode] = { clusters: list, links: kept };
  }

  // two domains are adjacent when publications carry themes from both
  function themeLinks(list, byId) {
    var pairs = {};
    PUBS.forEach(function (p) {
      if (p.doms.length < 2) return;
      var here = [];
      p.doms.forEach(function (d) { var c = byId['dom:' + d]; if (c) here.push(c.k); });
      here.sort(function (a, b) { return a - b; });
      for (var a = 0; a < here.length; a++) for (var b = a + 1; b < here.length; b++) {
        var key = here[a] + ':' + here[b];
        pairs[key] = (pairs[key] || 0) + 1;
      }
    });
    return toLinks(pairs, 4);
  }

  // two works are adjacent when the studies devoted to them share theme leaves
  function workLinks(list, byId) {
    var profile = {};
    PUBS.forEach(function (p) {
      if (p.rel === 'none' || !p.works.length || !p.themes.length) return;
      var c = byId['w:' + p.works[0]];
      if (!c) return;
      var row = profile[c.k] || (profile[c.k] = {});
      p.themes.forEach(function (t) { row[t] = (row[t] || 0) + 1; });
    });
    var keys = Object.keys(profile), pairs = {};
    for (var i = 0; i < keys.length; i++) {
      for (var j = i + 1; j < keys.length; j++) {
        var A = profile[keys[i]], B = profile[keys[j]], w = 0;
        Object.keys(A).forEach(function (t) { if (B[t]) w += Math.min(A[t], B[t]); });
        if (w) {
          var a = +keys[i], b = +keys[j];
          pairs[(a < b ? a : b) + ':' + (a < b ? b : a)] = w;
        }
      }
    }
    return toLinks(pairs, 3);
  }
  function toLinks(pairs, floor) {
    var out = [];
    Object.keys(pairs).forEach(function (key) {
      var s = key.split(':');
      if (pairs[key] >= floor) out.push({ a: +s[0], b: +s[1], w: pairs[key] });
    });
    return out;
  }

  function useMode(mode, animate) {
    buildMode(mode);
    MODE = mode;
    CLUSTERS = BUILT[mode].clusters;
    window.__links = BUILT[mode].links;
    // the new arrangement is drawn in place and faded up, so nothing flies across
    PUBS.forEach(function (p) {
      var o = p.o[mode];
      p.ox = o[0]; p.oy = o[1];
      p.tox = p.ox; p.toy = p.oy;
      p.cox = p.ox; p.coy = p.oy;
    });
    CLUSTERS.forEach(function (c) {
      c.px = c.bx; c.py = c.by; c.cr = c.r;
      c.tx = c.bx; c.ty = c.by; c.mr = c.r;
      c.ta = isFolded(c) ? 0 : 1;
      c.a = isFolded(c) ? 0 : (animate && !RM ? 0 : 1);
    });
    sel = null; hover = null;
    if (!animate) { fitView(); cam = { s: tcam.s, x: tcam.x, y: tcam.y }; }
    invalidate();
  }

  /* ------------------------------------------------------------------ packing */
  // Relaxation packing: discs are pushed apart until nothing overlaps, then
  // drawn toward the centre. Deterministic: no random seed anywhere.
  function packDiscs(items, pad) {
    var n = items.length;
    if (!n) return 0;
    if (n === 1) { items[0].x = 0; items[0].y = 0; return items[0].r; }
    items.sort(function (a, b) { return b.r - a.r; });
    var area = 0, maxR = 0;
    items.forEach(function (it) { area += (it.r + pad) * (it.r + pad) * Math.PI; maxR = Math.max(maxR, it.r); });
    var R0 = Math.sqrt(area / Math.PI) * 1.28;
    items.forEach(function (it, i) {
      var a = i * 2.3999632, rad = R0 * Math.sqrt((i + 0.5) / n);
      it.x = Math.cos(a) * rad; it.y = Math.sin(a) * rad;
    });
    var cell = (maxR + pad) * 2.05;
    for (var pass = 0; pass < 190; pass++) {
      var grid = {}, moved = 0;
      for (var i = 0; i < n; i++) {
        var it = items[i];
        var key = Math.floor(it.x / cell) + ',' + Math.floor(it.y / cell);
        (grid[key] || (grid[key] = [])).push(i);
      }
      for (var i2 = 0; i2 < n; i2++) {
        var a2 = items[i2];
        var gx = Math.floor(a2.x / cell), gy = Math.floor(a2.y / cell);
        for (var dx = -1; dx <= 1; dx++) for (var dy = -1; dy <= 1; dy++) {
          var bucket = grid[(gx + dx) + ',' + (gy + dy)];
          if (!bucket) continue;
          for (var q = 0; q < bucket.length; q++) {
            var j = bucket[q]; if (j <= i2) continue;
            var b2 = items[j];
            var ddx = b2.x - a2.x, ddy = b2.y - a2.y;
            var d = Math.sqrt(ddx * ddx + ddy * ddy);
            var want = a2.r + b2.r + pad;
            if (d < want) {
              if (d < 1e-6) { ddx = (i2 % 2 ? 1 : -1) * 0.5; ddy = 0.31; d = 0.59; }
              var push = (want - d) / d * 0.5;
              a2.x -= ddx * push; a2.y -= ddy * push;
              b2.x += ddx * push; b2.y += ddy * push;
              moved++;
            }
          }
        }
      }
      if (pass < 150) items.forEach(function (it) { it.x *= 0.988; it.y *= 0.988; });
      else if (!moved) break;
    }
    var R = 0;
    items.forEach(function (it) { R = Math.max(R, Math.hypot(it.x, it.y) + it.r); });
    return R;
  }

  // publications -> theme lobes -> cluster
  function packCluster(c) {
    var lobes = {}, order = [];
    c.pubs.forEach(function (p) {
      var key = p.lobeName || '·';
      if (!lobes[key]) { lobes[key] = { name: p.lobeName, pubs: [] }; order.push(key); }
      lobes[key].pubs.push(p);
    });
    // lobes under three works fold into the cluster's own body
    var rest = { name: null, pubs: [] }, live = [];
    order.forEach(function (k) {
      var lo = lobes[k];
      if (!lo.name || lo.pubs.length < 3) { rest.pubs = rest.pubs.concat(lo.pubs); }
      else live.push(lo);
    });
    if (rest.pubs.length) live.push(rest);
    live.sort(function (a, b) {
      if (b.pubs.length !== a.pubs.length) return b.pubs.length - a.pubs.length;
      return (a.name || '') < (b.name || '') ? -1 : 1;
    });
    live.forEach(function (lo) {
      lo.pubs.sort(function (a, b) { return b.r - a.r || (a.title < b.title ? -1 : 1); });
      lo.r = packDiscs(lo.pubs, GAP_PUB);
      // a leaf is drawn from everything it holds and counted like everything
      // else on the site: on the records that count
      lo.dens = 0;
      lo.pubs.forEach(function (p) { if (p.dens) lo.dens++; });
    });
    c.lobes = live;
    c.r = live.length === 1 ? live[0].r : packDiscs(live, GAP_SUB);
    if (live.length === 1) { live[0].x = 0; live[0].y = 0; }
    live.forEach(function (lo) {
      lo.pubs.forEach(function (p) { p.ox = lo.x + p.x; p.oy = lo.y + p.y; });
    });
    c.r = Math.max(c.r, 8);
  }

  /* ------------------------------------------------------------------ layout */
  // the field takes the proportions of the screen it is drawn on, so turning a
  // phone or dragging a window edge gives a field of the right shape
  function stretch() { return Math.max(0.55, Math.min(2.2, W / Math.max(H, 1) * 1.25)); }

  function layoutBase(all, links) {
    var named = all.filter(function (c) { return c.kind === 'subject'; });
    var tails = all.filter(function (c) { return c.kind === 'tail'; });
    var n = named.length;
    var order = named.slice().sort(function (a, b) { return b.n - a.n; });
    order.forEach(function (c, i) {
      var ang = i * 2.399963, rad = 58 * Math.sqrt(i + 0.6);
      c.x = Math.cos(ang) * rad * 1.5; c.y = Math.sin(ang) * rad * 0.8;
    });

    for (var it = 0; it < 340; it++) {
      for (var i = 0; i < n; i++) {
        var a = named[i];
        for (var j = i + 1; j < n; j++) {
          var b = named[j];
          var dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 0.01;
          var want = a.r + b.r + gapOf(a, b);
          if (d < want) {
            var push = (want - d) / d * 0.42;
            a.x -= dx * push; a.y -= dy * push; b.x += dx * push; b.y += dy * push;
          } else {
            var rep = 140 / d;
            a.x -= dx / d * rep * 0.02; a.y -= dy / d * rep * 0.02;
            b.x += dx / d * rep * 0.02; b.y += dy / d * rep * 0.02;
          }
        }
      }
      links.forEach(function (l) {
        var a = all[l.a], b = all[l.b];
        if (a.kind !== 'subject' || b.kind !== 'subject') return;
        var dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 0.01;
        var want = a.r + b.r + gapOf(a, b) + 30;
        var k = (d - want) * 0.012;
        a.x += dx / d * k; a.y += dy / d * k; b.x -= dx / d * k; b.y -= dy / d * k;
      });
      // the field is flattened toward the shape of a screen, wide rather than round
      named.forEach(function (c) { c.x *= 0.9994; c.y *= 0.9972; });
    }
    // widen toward the proportions of the screen in hand, then only ever push
    // apart, so the field keeps its width instead of rounding itself off again
    var wide = stretch();
    named.forEach(function (c) { c.x *= wide; });
    for (var fp = 0; fp < 400; fp++) {
      var hit = 0;
      for (var i2 = 0; i2 < n; i2++) for (var j2 = i2 + 1; j2 < n; j2++) {
        var a2 = named[i2], b2 = named[j2];
        var dx2 = b2.x - a2.x, dy2 = b2.y - a2.y, d2 = Math.hypot(dx2, dy2) || 0.01;
        var want2 = a2.r + b2.r + gapOf(a2, b2);
        if (d2 < want2) {
          var p2 = (want2 - d2) / d2 * 0.5;
          a2.x -= dx2 * p2; a2.y -= dy2 * p2; b2.x += dx2 * p2; b2.y += dy2 * p2;
          hit++;
        }
      }
      if (!hit) break;
    }
    var cx = 0, cy = 0, lo = 1e9, hi = -1e9, bot = -1e9;
    named.forEach(function (c) {
      cx += c.x; cy += c.y;
      lo = Math.min(lo, c.x - c.r); hi = Math.max(hi, c.x + c.r);
      bot = Math.max(bot, c.y + c.r);
    });
    cx /= n || 1; cy /= n || 1;
    // the unnamed reservoirs sit under the field, side by side, plainly apart
    var gx = 0;
    tails.sort(function (a, b) { return b.n - a.n; });
    tails.forEach(function (c) { gx += c.r * 2; });
    gx += (tails.length - 1) * 90;
    var cur = cx - gx / 2;
    tails.forEach(function (c) {
      c.x = cur + c.r; c.y = bot + 62 + c.r; cur += c.r * 2 + 110;
    });
    all.forEach(function (c) { c.bx = c.x - cx; c.by = c.y - cy; });
  }

  // second layout: the matched clusters gather at the centre, the rest drifts out
  function layoutFocus(set) {
    var live = CLUSTERS.filter(function (c) { return set.has(c.k); });
    if (!live.length) { CLUSTERS.forEach(function (c) { c.tx = c.bx; c.ty = c.by; }); return; }
    live.sort(function (a, b) { return b.mn - a.mn; });
    live.forEach(function (c, i) {
      var ang = i * 2.399963, rad = 40 * Math.sqrt(i + 0.5);
      c.tx = Math.cos(ang) * rad; c.ty = Math.sin(ang) * rad * 0.9;
    });
    for (var it = 0; it < 420; it++) {
      var hit = 0;
      for (var i = 0; i < live.length; i++) {
        var a = live[i];
        for (var j = i + 1; j < live.length; j++) {
          var b = live[j];
          var dx = b.tx - a.tx, dy = b.ty - a.ty, d = Math.hypot(dx, dy) || 0.01;
          var want = (a.mr || a.r) + (b.mr || b.r) + gapOf(a, b);
          if (d < want) {
            var p = (want - d) / d * 0.44;
            a.tx -= dx * p; a.ty -= dy * p; b.tx += dx * p; b.ty += dy * p;
            hit++;
          }
        }
        if (it < 340) { a.tx *= 0.997; a.ty *= 0.997; }
      }
      if (it >= 340 && !hit) break;
    }
    CLUSTERS.forEach(function (c) {
      if (set.has(c.k)) return;
      var d = Math.hypot(c.bx, c.by) || 1;
      c.tx = c.bx / d * (d * 1.5 + 300);
      c.ty = c.by / d * (d * 1.5 + 300);
    });
  }

  function fitView() {
    var mnx = 1e9, mny = 1e9, mxx = -1e9, mxy = -1e9, any = false;
    CLUSTERS.forEach(function (c) {
      if (c.ta < 0.25) return;
      any = true;
      var r = (c.mr == null ? c.r : c.mr) * 1.12;
      mnx = Math.min(mnx, c.tx - r); mxx = Math.max(mxx, c.tx + r);
      mny = Math.min(mny, c.ty - r); mxy = Math.max(mxy, c.ty + r);
    });
    if (!any) return;
    // the field keeps clear of the furniture actually on the page, whatever its
    // height: the search block above, the key and the controls below
    var askEl = document.querySelector('.ask');
    var lwEl = document.querySelector('.legend-wrap');
    var ctEl = document.querySelector('.controls');
    var topPad = MOBILE ? 214 : 236, botPad = MOBILE ? 262 : 140;
    if (askEl) topPad = Math.max(MOBILE ? 150 : 130, askEl.getBoundingClientRect().bottom + 22);
    var under = H;
    if (lwEl) under = Math.min(under, lwEl.getBoundingClientRect().top);
    if (ctEl) under = Math.min(under, ctEl.getBoundingClientRect().top);
    botPad = Math.max(MOBILE ? 120 : 46, H - under + 16);
    var free = H - topPad - botPad;
    if (free < 200) {
      var over = 200 - free;
      topPad = Math.max(60, topPad - over * 0.7);
      botPad = Math.max(40, botPad - over * 0.3);
    }
    var sidePad = MOBILE ? 22 : 90;
    var reserve = (!MOBILE && panel && panel.classList.contains('open')) ? 436 : 0;
    var vw = W - sidePad * 2 - reserve, vh = H - topPad - botPad;
    var gw = mxx - mnx || 1, gh = mxy - mny || 1;
    // a narrow screen keeps the field well inside its frame on purpose: the
    // names are set around the clouds and need the room
    var room = (MOBILE && !matched) ? 0.68 : 1;
    var s = Math.min(vw / gw * room, vh / gh * room,
      matched ? (MOBILE ? 3.2 : 4) : (MOBILE ? 0.95 : 1.55));
    tcam.s = clampS(s);
    tcam.x = sidePad + vw / 2 - (mnx + mxx) / 2 * tcam.s;
    tcam.y = topPad + vh / 2 - (mny + mxy) / 2 * tcam.s;
    if (!matched && !reserve) restScale = tcam.s;
    invalidate();
  }

  /* ------------------------------------------------------------------ questions */
  // Every option reads its values from the controlled vocabulary, the same file
  // the clusters are named from. Decades and languages come from the harvest.
  var QUESTIONS = [
    { kind: 'work', q: 'Which works of Origen?',
      note: 'Works named in the tagged notices. A study that names no work is not excluded: it answers the other questions.' },
    { kind: 'approach', q: 'Which angle of approach?',
      note: 'The ten angles of the vocabulary. A publication often carries two.' },
    { kind: 'decade', q: 'Which period of scholarship?', note: 'Year of publication, by decade.' },
    { kind: 'lang', q: 'Which languages do you read?', note: 'Language of publication as coded in the catalogue.' }
  ];
  var OPTS = null;

  // The number on a chip is the count of the same population the Observatory
  // counts: the records classed core or partial. What the chip returns is wider
  // — a record where Origen is mentioned only is never put aside — so each
  // question also carries the number of those records, in a line under the
  // chips. One population per screen, and the difference said rather than hidden.
  function buildOptions() {
    var out = { work: [], approach: [], decade: [], lang: [] };

    // an option is described once: its label, the records it returns, and the
    // two counts drawn from that same test
    function option(id, label, test) {
      var n = 0, m = 0;
      PUBS.forEach(function (p) {
        if (!reachable(p) || !test(p)) return;
        if (counts(p)) n++; else m++;
      });
      return {
        id: id, label: label, n: n, m: m,
        test: function (p) { return reachable(p) && test(p); }
      };
    }

    var wc = {};
    PUBS.forEach(function (p) {
      if (!counts(p)) return;
      p.works.forEach(function (w) { wc[w] = (wc[w] || 0) + 1; });
    });
    out.work = Object.keys(wc).sort(function (a, b) {
      return wc[b] - wc[a] || (SEM.works[a].label < SEM.works[b].label ? -1 : 1);
    }).map(function (id) {
      return option(id, SEM.works[id].label, function (p) { return p.works.indexOf(id) >= 0; });
    });

    var ac = {};
    PUBS.forEach(function (p) {
      if (!counts(p)) return;
      p.appr.forEach(function (a) { ac[a] = (ac[a] || 0) + 1; });
    });
    out.approach = Object.keys(SEM.approaches).filter(function (id) { return ac[id]; })
      .sort(function (a, b) { return ac[b] - ac[a]; })
      .map(function (id) {
        return option(id, SEM.approaches[id].label, function (p) { return p.appr.indexOf(id) >= 0; });
      });

    var dc = {}, before = 0;
    PUBS.forEach(function (p) {
      if (!counts(p) || p.year == null) return;
      if (p.year < 1950) { before++; return; }
      var d = Math.floor(p.year / 10) * 10;
      dc[d] = (dc[d] || 0) + 1;
    });
    if (before) {
      out.decade.push(option('pre1950', 'Before 1950', function (p) {
        return p.year != null && p.year < 1950;
      }));
    }
    Object.keys(dc).map(Number).sort(function (a, b) { return a - b; }).forEach(function (d) {
      out.decade.push(option('d' + d, d + 's', function (p) {
        return p.year != null && p.year >= d && p.year < d + 10;
      }));
    });

    out.lang = LANGS.map(function (l) {
      return option(l.code, l.label, function (p) { return p.lkey === l.code; });
    }).filter(function (o) { return o.n > 0; });

    return out;
  }

  // how many records a question can return without entering its counts
  function mentionedOnly(kind) {
    var seen = {}, k = 0;
    (OPTS[kind] || []).forEach(function (o) {
      PUBS.forEach(function (p) {
        if (counts(p) || seen[p.i] || !o.test(p)) return;
        seen[p.i] = 1; k++;
      });
    });
    return k;
  }

  /* ------------------------------------------------------------------ filtering */
  function chosen(kind) {
    return wizAns[kind].map(function (id) {
      for (var i = 0; i < OPTS[kind].length; i++) if (OPTS[kind][i].id === id) return OPTS[kind][i];
      return null;
    }).filter(Boolean);
  }

  // A query the engine could not evaluate is said in words and never drawn as a
  // zero: an unknown field, an invalid year, a quotation mark left open, or text
  // with no searchable word in it.
  function problemLine(r) {
    if (r.invalid) {
      return 'The query was not searched. ' + r.errors.map(function (e) { return e.message; }).join(' ');
    }
    return 'Nothing was searched: words under three letters and common words are left out' +
      (r.droppedTerms.length ? ' (here: ' + r.droppedTerms.join(', ') + ')' : '') + '.';
  }

  // The four questions filter conjunctively, before anything textual. The
  // search runs under this restriction, and so does a query the decade strip
  // compares, so that both count what the search field would count.
  function answersKeep() {
    var picked = {}, anyPick = false;
    QUESTIONS.forEach(function (q) {
      picked[q.kind] = chosen(q.kind);
      if (picked[q.kind].length) anyPick = true;
    });
    return anyPick ? function (p) {
      for (var k = 0; k < QUESTIONS.length; k++) {
        var opts = picked[QUESTIONS[k].kind];
        if (!opts.length) continue;
        var ok = false;
        for (var o = 0; o < opts.length; o++) if (opts[o].test(p)) { ok = true; break; }
        if (!ok) return false;
      }
      return true;
    } : null;
  }

  function computeMatch() {
    var picked = {}, anyPick = false;
    QUESTIONS.forEach(function (q) {
      picked[q.kind] = chosen(q.kind);
      if (picked[q.kind].length) anyPick = true;
    });
    fullHit = 0; fullHitCounted = 0; absentToks = []; absentFiltered = []; absentPartial = []; relaxed = false;
    vocabHit = 0; vocabHitCounted = 0; vocabLabel = ''; tokCount = 0; hitDepth = 0;
    queryProblem = ''; LAST = null; RANK = null; scopeDens = 0;
    // blank is decided by the engine's own parser: `l:fr`, `foo:bar` and `PG`
    // all reach it, and come back as an answer or as a reported problem
    var blank = CORE.queryIsBlank(query);
    if (blank && !anyPick) { matched = null; shelfOnly = null; matchLabel = ''; return; }

    var keep = answersKeep();

    var r = CORE.search(IDX, query, { keep: keep });
    var textSearched = !blank;
    if (r.invalid || r.normalisedEmpty) {
      queryProblem = problemLine(r) +
        (anyPick ? ' The map shows your answers to the four questions without it.' : '');
      textSearched = false;
      if (!anyPick) { matched = null; shelfOnly = null; matchLabel = ''; return; }
      r = CORE.search(IDX, '', { keep: keep });
    }
    LAST = r;
    matched = r.matched;
    shelfOnly = r.vocabOnly;
    fullHit = r.fullHit;
    fullHitCounted = r.fullHitCounted;
    absentToks = r.absentTerms;
    absentFiltered = r.absentUnderFilters;
    absentPartial = r.absentFromPartialIndex || [];
    relaxed = r.relaxed;
    hitDepth = r.hitDepth;
    tokCount = r.terms.length;
    vocabHit = r.vocabHit;
    vocabHitCounted = r.vocabHitCounted;
    vocabLabel = r.heading;
    RANK = {};
    r.order.forEach(function (i, at) { RANK[i] = at; });
    PUBS.forEach(function (p) { if (counts(p) && (!keep || keep(p))) scopeDens++; });

    var bits = [];
    if (textSearched && query.trim()) bits.push('“' + query.trim() + '”');
    QUESTIONS.forEach(function (q) {
      if (picked[q.kind].length) {
        bits.push(picked[q.kind].map(function (o) { return o.label; }).join(', '));
      }
    });
    matchLabel = bits.join(' · ');
  }

  function quoteTerms(terms) {
    return terms.map(function (x) { return '“' + x + '”'; }).join(', ');
  }
  function absentPhrase(terms, where) {
    return quoteTerms(terms) + (terms.length === 1 ? ' appears' : ' appear') + ' in none of ' + where;
  }
  // the fields a term was looked for in, as the engine names them
  function fieldsSearched() {
    return CORE.searchedFields(IDX).join(', ');
  }
  // While the subject headings of each record are loading, or when they could
  // not be read, a count may be short and a term not found is not called absent.
  function partialPhrase(terms) {
    var are = terms.length === 1 ? ' is' : ' are';
    if (headings === 'loading') return quoteTerms(terms) + are + ' not found yet: the subject headings of each record are still loading';
    return quoteTerms(terms) + are + ' not found, and not called absent: the subject headings of each record could not be read';
  }
  function headingsNote(r) {
    if (headings === 'complete' || !r || r.invalid) return '';
    var free = r.terms.length || r.phrases.length || r.exclude.length || r.excludePhrases.length ||
      r.filters.some(function (f) { return f.field === 'container'; });
    if (!free) return '';
    if (absentPartial.length) return ' · ' + partialPhrase(absentPartial);
    if (headings === 'loading') return ' · the subject headings of each record are still loading, so this count may rise';
    var t = (IDX && IDX.thresholds && IDX.thresholds.subject_min_publications) || 'several';
    return ' · the subject headings of each record could not be read: only headings ' + t +
      ' or more records share were searched';
  }

  // One sentence, and it must survive a reader who checks it. The order is:
  // what your terms actually answer, counted, then the denominator, then what
  // was widened, then what a filter or a language toggle is hiding.
  function stateLine(t, total) {
    var hit = t.hit, extra = t.mention + t.aside, out;
    if (tokCount > 1 && relaxed) {
      // the question asked is every term at once: that count leads, and the
      // widened list is named second, as a list
      out = t.full
        ? nf(t.full) + (t.full === 1 ? ' counted work carries' : ' counted works carry') +
          ' all ' + tokCount + ' of your terms'
        : 'No counted work carries all ' + tokCount + ' of your terms';
      if (absentToks.length) out += ': ' + absentPhrase(absentToks, 'the ' + nf(PUBS.length) + ' records');
      out += ' · widened to ' + hitDepth + ' of ' + tokCount + ': ' + nf(hit) + ' counted';
    } else if (!hit && vocabHit) {
      // The reader named a shelf rather than a phrase: the shelf IS the answer,
      // counted like every other figure
      out = vocabHitCounted
        ? nf(vocabHitCounted) + (vocabHitCounted === 1 ? ' work is filed under “' : ' works are filed under “') +
          vocabLabel + '”' + (total ? ', of ' + nf(total) : '') + ' · none names it in so many words'
        : 'No counted work is filed under “' + vocabLabel + '”';
      extra += t.shelf - t.shelfCounted;
      if (extra) out += ' · ' + nf(extra) + ' more listed, mentioned only or held aside';
      if (t.hidden) out += ' · ' + nf(t.hidden) + ' hidden by the language filter';
      return out;
    } else {
      out = nf(hit) + (hit === 1 ? ' work matches' : ' works match');
      if (total && hit) out += ' of ' + nf(total);
      if (!hit && !t.shelf && absentToks.length) {
        out += ': ' + absentPhrase(absentToks, 'the ' + nf(PUBS.length) + ' records');
      }
    }
    if (vocabHitCounted && vocabLabel) {
      out += ' · ' + nf(vocabHitCounted) + ' filed under the heading “' + vocabLabel + '”';
    }
    if (absentFiltered.length) out += ' · ' + absentPhrase(absentFiltered, 'the records your filters leave');
    if (extra) out += ' · ' + nf(extra) + ' more listed, mentioned only or held aside';
    if (t.hidden) out += ' · ' + nf(t.hidden) + ' hidden by the language filter';
    return out;
  }

  function visiblePub(p) { return !langOff[p.lkey]; }

  // The figures of one answer, computed once for the state line and for the
  // panel, so that the two cannot print different numbers. A record hidden by
  // the language filter is set apart first; a record reached only through a
  // heading (`shelf`) is listed and enters neither figure, as in search-core.js.
  // With several terms, `full` counts the counted records carrying all of them.
  function tallyMatch(list, shelf, scores, terms) {
    var t = { hit: 0, full: 0, mention: 0, aside: 0, shelf: 0, shelfCounted: 0, hidden: 0 };
    list.forEach(function (p) {
      if (!visiblePub(p)) { t.hidden++; return; }
      if (shelf && shelf.has(p.i)) { t.shelf++; if (counts(p)) t.shelfCounted++; return; }
      if (counts(p)) {
        t.hit++;
        if (terms > 1 && scores && (scores[p.i] || 0) >= terms) t.full++;
      } else if (p.rel === 'none') t.aside++;
      else t.mention++;
    });
    return t;
  }

  // The records a headline counts, out of the records a view lists (`list`,
  // tallied as `t`) for the engine result `r` (null for the map at rest): the
  // counted records, less those reached only through a heading; with several
  // terms, those carrying every term; for a query that names a heading and no
  // word of it, the counted records filed under that heading. A cluster is never
  // answered by a heading, and the reservoir held aside counts nothing.
  function headlineRecords(list, t, r, inCluster, held) {
    if (held) return [];
    var k = r ? r.terms.length : 0, shelf = r ? r.vocabOnly : null, scores = r ? r.scores : null;
    var conj = !!r && k > 1;
    var shelfAnswer = !inCluster && !!r && !t.hit && t.shelf > 0 && r.vocabHitCounted > 0;
    return list.filter(function (p) {
      if (!counts(p)) return false;
      if (shelfAnswer) return shelf.has(p.i);
      if (shelf && shelf.has(p.i)) return false;
      return !conj || (scores[p.i] || 0) >= k;
    });
  }

  function sameMatch(a, b) {
    if (!a || !b) return a === b;
    if (a.size !== b.size) return false;
    var same = true;
    a.forEach(function (i) { if (!b.has(i)) same = false; });
    return same;
  }
  // quiet: a recount of the same question (the index completed); the field
  // keeps its layout when the records answering have not changed
  function applyMatch(openPanel, quiet) {
    var before = matched;
    computeMatch();
    var still = !!quiet && sameMatch(before, matched);
    CLUSTERS.forEach(function (c) {
      c.mn = 0; c.mdens = 0;
      if (!matched) { c.mn = c.n; c.mdens = c.dens; return; }
      c.pubs.forEach(function (p) {
        if (!matched.has(p.i)) return;
        c.mn++;
        if (p.dens && !shelfOnly.has(p.i)) c.mdens++;
      });
    });
    if (!still) {
      var live = new Set();
      if (matched) {
        CLUSTERS.forEach(function (c) {
          if (c.mn > 0) live.add(c.k);
          packMatched(c);
        });
        layoutFocus(live);
        CLUSTERS.forEach(function (c) { c.ta = (c.mn > 0 && !isFolded(c)) ? 1 : 0; });
      } else {
        CLUSTERS.forEach(function (c) {
          c.tx = c.bx; c.ty = c.by; c.ta = isFolded(c) ? 0 : 1; c.mr = c.r;
          c.pubs.forEach(function (p) { p.tox = p.ox; p.toy = p.oy; });
        });
      }
      startTween(RM ? 1 : 780);
      fitView();
    }
    // The state line says what was asked before it says what was found, gives
    // the denominator, and never passes a widened set off as the answer.
    var state = '';
    if (matched) {
      var total = 0;
      PUBS.forEach(function (p) { if (counts(p)) total++; });
      var t = tallyMatch(PUBS.filter(function (p) { return matched.has(p.i); }), shelfOnly,
        LAST ? LAST.scores : null, tokCount);
      state = stateLine(t, total) + headingsNote(LAST);
    }
    if (queryProblem) state = queryProblem + (state ? ' ' + state : '');
    stateText = state;
    renderState();
    renderHeld();
    if (openPanel) {
      // a refused query has no neighbourhood to show: the state line says why
      if (queryProblem && !matched) closePanel();
      else { sel = null; selPub = null; selAuthor = null; renderPanel(); }
    }
    syncHash(false);
  }

  function renderState() {
    document.getElementById('ask-state').textContent = linkBuild
      ? buildNote() + (stateText ? ' ' + stateText : '') : stateText;
  }
  // A link made on another build is noted until the reader moves on from the
  // view it opened; a view replayed from an address keeps the note.
  function userMoved() {
    if (restoring || !linkBuild) return;
    linkBuild = null;
    renderState();
    var note = panel.querySelector('.cite-note');
    if (note) note.remove();
  }

  /* ------------------------------------------------------------------ reservoirs */
  // Named, counted, folded under the field. One click draws a reservoir on the
  // map and opens its records; a second click folds it away again.
  // the legend block grows and shrinks with what it has to say; the controls
  // above it are told how much room it takes rather than guessing
  function measureLegend() {
    var wrap = document.querySelector('.legend-wrap');
    if (!wrap) return;
    document.documentElement.style.setProperty('--legend-h', wrap.offsetHeight + 'px');
  }
  function setKeyOpen(on) {
    var wrap = document.getElementById('legend-wrap');
    var tog = document.getElementById('key-toggle');
    if (!wrap || !tog) return;
    wrap.classList.toggle('open', !!on);
    tog.setAttribute('aria-expanded', on ? 'true' : 'false');
    tog.textContent = on ? 'Hide key' : 'Key';
    measureLegend();
    requestAnimationFrame(measureLegend);
  }

  function renderHeld() {
    var box = document.getElementById('held-chips');
    if (!box) return;
    var tails = CLUSTERS.filter(function (c) { return c.kind === 'tail'; })
      .sort(function (a, b) { return b.n - a.n; });
    box.innerHTML = '';
    tails.forEach(function (c) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'held-chip';
      var on = !isFolded(c);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      b.title = (c.alt || '') + (on ? ' Drawn on the map.' : ' Click to draw it on the map.');
      b.innerHTML = esc(c.label) + '<span class="n">' + clusterCount(c).text + '</span>';
      b.addEventListener('click', function () {
        userMoved();
        var show = isFolded(c);
        folded[c.id] = !show;
        applyMatch(false);
        if (show) openCluster(c);
        else if (sel === c) closePanel();
      });
      box.appendChild(b);
    });
    measureLegend();
  }

  function startTween(ms) {
    CLUSTERS.forEach(function (c) {
      c.sx = c.px; c.sy = c.py; c.sa = c.a;
      c.sr = c.cr == null ? c.r : c.cr;
      c.pubs.forEach(function (p) {
        p.sox = p.cox == null ? p.ox : p.cox;
        p.soy = p.coy == null ? p.oy : p.coy;
      });
    });
    tweenT0 = performance.now(); tweenMs = ms; animating = true;
    invalidate();
  }

  // pack only the works that answer the question, so the cluster shrinks to them
  function packMatched(c) {
    var live = c.pubs.filter(function (p) { return matched.has(p.i); });
    if (!live.length) {
      c.mr = c.r;
      c.pubs.forEach(function (p) { p.tox = p.ox; p.toy = p.oy; });
      return;
    }
    var items = live.map(function (p) { return { p: p, r: p.r }; });
    c.mr = Math.max(packDiscs(items, GAP_PUB), 7);
    items.forEach(function (it) { it.p.tox = it.x; it.p.toy = it.y; });
    c.pubs.forEach(function (p) {
      if (!matched.has(p.i)) { p.tox = p.ox; p.toy = p.oy; }
    });
  }

  /* ------------------------------------------------------------------ drawing */
  // the scale the whole field settles at on this screen; the second rank of
  // names is measured against it rather than against an absolute zoom.
  // Wheel and pinch used to stop at 4, which left every work a pinprick.
  var restScale = 1;
  var MIN_S = 0.18, MAX_S = 22;
  function clampS(s) { return Math.max(MIN_S, Math.min(MAX_S, s)); }
  function leafFade() { return Math.min(1, Math.max(0, (cam.s / restScale - 0.97) / 0.26)); }
  // A work is only worth aiming at once its cloud is a real patch, not a
  // speck inside a far cluster. After a cluster is framed it fills enough
  // of the view that its works can be clicked even if the field zoom is
  // still modest.
  function clusterInHand(c) {
    return !!c && radiusOf(c) * cam.s > Math.min(W, H) * 0.28;
  }
  function hostCluster() {
    if (sel && sel.a > 0.35 && clusterInHand(sel)) return sel;
    var best = null, bd = 1e9;
    CLUSTERS.forEach(function (c) {
      if (c.a < 0.5 || !clusterInHand(c)) return;
      var d = Math.hypot(wx(c.px) - W / 2, wy(c.py) - H / 2);
      if (d < bd) { bd = d; best = c; }
    });
    return best;
  }
  function worksPickable(sx, sy) {
    if (sel) return true;
    if (cam.s >= restScale * 2) return true;
    var over = pick(sx, sy);
    return over && clusterInHand(over);
  }
  function pubReach(p) {
    return Math.max(14, p.r * cam.s * 1.45);
  }

  function radiusOf(c) { return c.cr == null ? c.r : c.cr; }
  function wx(x) { return x * cam.s + cam.x; }
  function wy(y) { return y * cam.s + cam.y; }

  /* The field is drawn when it changes, not sixty times a second while it sits
     still. Every gesture and every answer calls invalidate(); the loop keeps
     running as long as a tween or the camera is still moving, and stops when
     both have settled. A map at rest costs nothing. */
  var frameQueued = false, keepDrawing = false;
  function invalidate() {
    if (frameQueued) return;
    frameQueued = true;
    requestAnimationFrame(draw);
  }
  function camMoving() {
    return Math.abs(tcam.s - cam.s) > 0.0004 ||
      Math.abs(tcam.x - cam.x) > 0.05 || Math.abs(tcam.y - cam.y) > 0.05;
  }

  function draw(now) {
    frameQueued = false;
    now = now || performance.now();
    keepDrawing = animating || camMoving();
    if (!keepDrawing) { cam.s = tcam.s; cam.x = tcam.x; cam.y = tcam.y; }
    if (animating) {
      var t = tweenMs <= 1 ? 1 : Math.min(1, (now - tweenT0) / tweenMs), k = easeOut(t);
      CLUSTERS.forEach(function (c) {
        c.px = c.sx + (c.tx - c.sx) * k;
        c.py = c.sy + (c.ty - c.sy) * k;
        c.a = c.sa + (c.ta - c.sa) * k;
        c.cr = c.sr + ((c.mr == null ? c.r : c.mr) - c.sr) * k;
        c.pubs.forEach(function (p) {
          p.cox = p.sox + ((p.tox == null ? p.ox : p.tox) - p.sox) * k;
          p.coy = p.soy + ((p.toy == null ? p.oy : p.toy) - p.soy) * k;
        });
      });
      if (t >= 1) animating = false;
    }
    cam.s += (tcam.s - cam.s) * (RM ? 1 : 0.11);
    cam.x += (tcam.x - cam.x) * (RM ? 1 : 0.11);
    cam.y += (tcam.y - cam.y) * (RM ? 1 : 0.11);

    ctx.clearRect(0, 0, W, H);

    drawPathways();
    drawHalos();
    if (dust) syncDust();
    else drawUnits();

    refreshChrome(now);
    TAG_BOXES = [];
    LOBE_BOXES = [];
    var host = hostCluster();
    var worksNamed = !!(host && cam.s >= restScale * 2.4);
    if (worksNamed) drawLocalNerves(host);
    if (!worksNamed) {
      drawClusterTags(null);
      if (cam.s > restScale * 1.85 && !MOBILE) drawLobeLabels();
    } else {
      drawClusterTags(host);
      drawPubTags(host);
    }
    if (keepDrawing) invalidate();
  }

  function dustNodes() {
    var out = [];
    CLUSTERS.forEach(function (c) {
      if (isFolded(c) || c.a < 0.04) return;
      c.pubs.forEach(function (p) {
        if (!visiblePub(p)) return;
        if (matched && !matched.has(p.i)) return;
        var ox = p.cox == null ? p.ox : p.cox, oy = p.coy == null ? p.oy : p.coy;
        out.push({
          id: String(p.i),
          x: c.px + ox,
          y: c.py + oy,
          r: p.r,
          lang: p.lkey,
          weight: p.tier + 1
        });
      });
    });
    return out;
  }
  var dustIds = '';
  function syncDust() {
    if (!dust) return;
    dust.syncCamera(cam, W, H);
    var nodes = dustNodes();
    var ids = nodes.map(function (n) { return n.id; }).join('\0');
    if (ids !== dustIds) {
      dustIds = ids;
      dust.setNodes(nodes);
    } else if (animating) {
      dust.moveNodes(nodes);
    }
    dust.focus(selPub ? String(selPub.i) : null);
  }

  function grain(n) {
    var x = Math.sin(n * 127.1 + 311.7) * 43758.5453;
    return x - Math.floor(x);
  }
  function attachGrains(p) {
    var n = 32 + p.tier * 8, g = [], i = 0, k = 0, sig = p.r * 0.32;
    while (k < n) {
      var u1 = grain(p.i * 31 + i) || 1e-4, u2 = grain(p.i * 47 + i + 3);
      var rad = sig * Math.sqrt(-2 * Math.log(u1)), t = 6.28318530718 * u2;
      var x = rad * Math.cos(t), y = rad * Math.sin(t);
      g.push(x, y); k++;
      if (k < n) { g.push(-x, -y); k++; }
      i += 2;
    }
    p.grains = g;
  }

  // How much of its packing disc a work paints. Far out the blot is larger
  // than the gap, so neighbours melt into one cloud. Close in it shrinks
  // relative to the gap, so each work reads as one unit of dust.
  function unitMix() {
    var z = cam.s / Math.max(restScale, 0.15);
    var close = Math.min(1, Math.max(0, (z - 1) / 3.2));
    return 1.45 - close * 0.95;
  }
  function unitR(p) {
    return Math.max(2.4, p.r * cam.s * unitMix());
  }

  var PUFF = {};
  function puffSprite(col) {
    if (PUFF[col]) return PUFF[col];
    var s = 64, off = document.createElement('canvas');
    off.width = off.height = s;
    var g = off.getContext('2d');
    var grd = g.createRadialGradient(32, 32, 0, 32, 32, 31);
    grd.addColorStop(0, hexA(col, 0.58));
    grd.addColorStop(0.28, hexA(col, 0.32));
    grd.addColorStop(0.62, hexA(col, 0.1));
    grd.addColorStop(1, hexA(col, 0));
    g.fillStyle = grd;
    g.beginPath();
    g.arc(32, 32, 31, 0, 6.2832);
    g.fill();
    PUFF[col] = off;
    return off;
  }
  function stampPuff(col, x, y, r, a) {
    if (a < 0.04 || r < 0.6) return;
    var d = r * 2;
    ctx.globalAlpha = a;
    ctx.drawImage(puffSprite(col), x - r, y - r, d, d);
  }
  function drawUnits() {
    var hl = hover || sel;
    var z = cam.s / Math.max(restScale, 0.15);
    var grainN = z < 1.35 ? 0 : (z < 3 ? 14 : 36);
    var later = [];
    CLUSTERS.forEach(function (c) {
      if (c.a < 0.03) return;
      var R = radiusOf(c) * cam.s;
      var cxp = wx(c.px), cyp = wy(c.py);
      if (cxp < -R - 80 || cxp > W + R + 80 || cyp < -R - 80 || cyp > H + R + 80) return;
      var litC = hl === c;
      var base = c.a * (litC ? 1 : (hl || hoverPub ? 0.78 : 1)) * (c.kind === 'tail' ? 0.55 : 1);
      c.pubs.forEach(function (p) {
        if (!visiblePub(p)) return;
        var a = base;
        if (matched && !matched.has(p.i)) a *= animating ? 0.1 : 0;
        if (a < 0.05) return;
        var litP = hoverPub === p || selPub === p;
        var ox = p.cox == null ? p.ox : p.cox, oy = p.coy == null ? p.oy : p.coy;
        var x = cxp + ox * cam.s, y = cyp + oy * cam.s;
        var r = unitR(p);
        if (litP) { later.push({ p: p, x: x, y: y, r: r, a: a }); return; }
        paintUnit(p, x, y, r, a, grainN, false);
      });
    });
    later.forEach(function (u) { paintUnit(u.p, u.x, u.y, u.r * 1.18, Math.min(1, u.a + 0.2), Math.max(grainN, 20), true); });
    ctx.globalAlpha = 1;
  }
  function paintUnit(p, x, y, r, a, grainN, lit) {
    var col = LCOL[p.lkey] || LCOL.oth;
    if (!grainN || r < 6) {
      stampPuff(col, x, y, r, a * (lit ? 0.95 : 0.72));
      return;
    }
    var grains = p.grains || [];
    var cap = Math.min(grains.length / 2, grainN);
    var gr = r * 0.7;
    stampPuff(col, x, y, r * 0.82, a * 0.42);
    for (var i = 0; i < cap; i++) {
      stampPuff(col, x + grains[i * 2] * cam.s, y + grains[i * 2 + 1] * cam.s, gr, a * 0.38);
    }
  }

  // the furniture of the page moves on its own clock — the panel slides, the
  // wizard drops — and the names have to step aside as it goes. A short series
  // of frames follows such a movement, then the field is left alone again.
  var settleTimer = null;
  function settle(ms) {
    var t0 = performance.now(), until = ms || 640;
    if (settleTimer) clearInterval(settleTimer);
    settleTimer = setInterval(function () {
      invalidate();
      if (performance.now() - t0 > until) { clearInterval(settleTimer); settleTimer = null; }
    }, 70);
    invalidate();
  }

  /* ---------------------------------------------------------- naming the clouds */
  /* A cloud's name is a tag set on the centroid of its visible works, the
     largest clouds first; a tag that would sit on the furniture of the page or
     on a tag already set is not drawn (drawClusterTags). Leaf names follow the
     same rule inside their own domain (drawLobeLabels). */
  var chromeBoxes = [], chromeAt = -1e9;
  var CHROME_SEL = ['.bar', '.ask-field', '.ask-alt', '.wiz.open', '.legend-wrap',
    '.controls', '.panel.open'];
  function refreshChrome(now) {
    if (now - chromeAt < 200) return;
    chromeAt = now;
    chromeBoxes = [];
    CHROME_SEL.forEach(function (s) {
      var el = document.querySelector(s);
      if (!el) return;
      var r = el.getBoundingClientRect();
      if (r.width < 4 || r.height < 4) return;
      if (r.right < 0 || r.left > W || r.bottom < 0 || r.top > H) return;
      chromeBoxes.push({ x: r.left - 7, y: r.top - 7, w: r.width + 14, h: r.height + 14 });
    });
  }
  function rectHitsDisc(b, d) {
    var nx = Math.max(b.x, Math.min(d.x, b.x + b.w));
    var ny = Math.max(b.y, Math.min(d.y, b.y + b.h));
    var dx = d.x - nx, dy = d.y - ny;
    return dx * dx + dy * dy < d.r * d.r;
  }
  var LOBE_BOXES = [], TAG_BOXES = [];

  function tagHits(box, list) {
    var i, q;
    for (i = 0; i < list.length; i++) {
      q = list[i];
      if (box.x < q.x + q.w && box.x + box.w > q.x && box.y < q.y + q.h && box.y + box.h > q.y) return true;
    }
    return false;
  }
  function measureTag(lines, fs, padX, padY) {
    ctx.font = '500 ' + fs + 'px "EB Garamond",Georgia,serif';
    var tw = 0, i;
    for (i = 0; i < lines.length; i++) tw = Math.max(tw, ctx.measureText(lines[i]).width);
    var lh = fs * 1.15;
    return { w: tw + padX * 2, h: lines.length * lh + padY * 2, lh: lh };
  }
  function drawTag(cx, cy, lines, o) {
    o = o || {};
    var fs = o.fs || 12, padX = o.padX == null ? 9 : o.padX, padY = o.padY == null ? 4 : o.padY;
    var a = o.a == null ? 1 : o.a, lit = !!o.lit;
    var m = measureTag(lines, fs, padX, padY);
    var bx = cx - m.w / 2, by = cy - m.h / 2;
    ctx.fillStyle = hexA(PAPER, 0.93 * a);
    ctx.strokeStyle = hexA('#C4B79A', (lit ? 0.72 : 0.48) * a);
    ctx.lineWidth = 1;
    roundRect(bx, by, m.w, m.h, Math.min(m.h / 2, 14));
    ctx.fill();
    ctx.stroke();
    ctx.font = (lit ? 600 : 500) + ' ' + fs + 'px "EB Garamond",Georgia,serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = hexA(lit ? ACCENT : (o.ink || INK), a);
    var y0 = cy - ((lines.length - 1) * m.lh) / 2;
    lines.forEach(function (ln, i) { ctx.fillText(ln, cx, y0 + i * m.lh); });
    return { x: bx, y: by, w: m.w, h: m.h };
  }
  function clusterCentroid(c) {
    var sx = 0, sy = 0, n = 0;
    c.pubs.forEach(function (p) {
      if (!visiblePub(p)) return;
      if (matched && !matched.has(p.i)) return;
      var ox = p.cox == null ? p.ox : p.cox, oy = p.coy == null ? p.oy : p.coy;
      sx += c.px + ox; sy += c.py + oy; n++;
    });
    if (!n) return { x: c.px, y: c.py };
    return { x: sx / n, y: sy / n };
  }
  function drawClusterTags(hide) {
    var hl = hover || sel;
    var order = CLUSTERS.filter(function (c) {
      return c.a >= 0.35 && c !== hide;
    }).sort(function (a, b) { return (b === hl) - (a === hl) || b.n - a.n; });
    order.forEach(function (c) {
      var mid = clusterCentroid(c);
      var x = wx(mid.x), y = wy(mid.y);
      if (x < 24 || x > W - 24 || y < 80 || y > H - 24) return;
      var fs = MOBILE ? 11 : 12;
      var lines = wrapLabel(c.label, MOBILE ? 15 : 20, 2);
      var m = measureTag(lines, fs, 8, 3.5);
      var box = { x: x - m.w / 2, y: y - m.h / 2, w: m.w, h: m.h };
      if (tagHits(box, chromeBoxes) || tagHits(box, TAG_BOXES)) return;
      TAG_BOXES.push(drawTag(x, y, lines, {
        fs: fs, padX: 8, padY: 3.5, a: Math.min(1, c.a),
        lit: c === hl, ink: c.kind === 'tail' ? STONE : INK
      }));
    });
  }

  /* The first rank of the hierarchy, drawn at rest: a hairline holds each domain
     together, and a lighter one holds each of its leaves. Faint enough to read
     as a boundary rather than as a mark of its own. */
  function haloR(c) {
    var R = radiusOf(c) * cam.s;
    return R + Math.min(9, 4 + R * 0.05);
  }
  function drawHalos() {
    var leaf = leafFade();
    CLUSTERS.forEach(function (c) {
      if (c.a < 0.12 || c.kind !== 'subject') return;
      var R = radiusOf(c) * cam.s, x = wx(c.px), y = wy(c.py);
      if (x + R < -40 || x - R > W + 40 || y + R < -40 || y - R > H + 40) return;
      var ring = haloR(c);
      var far = 1 - Math.min(1, Math.max(0, (cam.s / Math.max(restScale, 0.15) - 1.15) / 2.2));
      if (far < 0.04) return;
      var glow = ctx.createRadialGradient(x, y, ring * 0.15, x, y, ring);
      glow.addColorStop(0, hexA('#8E8264', 0.07 * c.a * far));
      glow.addColorStop(1, hexA('#8E8264', 0));
      ctx.fillStyle = glow;
      ctx.beginPath(); ctx.arc(x, y, ring, 0, 6.2832); ctx.fill();
      if (far > 0.35 && leaf > 0.85 && c.lobes && c.lobes.length > 1 && !matched) {
        ctx.strokeStyle = hexA(STONE, 0.12 * c.a * far); ctx.lineWidth = 1;
        c.lobes.forEach(function (lo) {
          if (!lo.name || lo.pubs.length < 4) return;
          ctx.beginPath();
          ctx.arc(x + lo.x * cam.s, y + lo.y * cam.s, lo.r * cam.s + 2.5, 0, 6.2832);
          ctx.stroke();
        });
      }
    });
  }

  // the second rank of the hierarchy: the theme leaves inside a domain
  function drawLobeLabels() {
    // At the resting scale each domain shows its widest leaf, in grey, and only
    // when the name fits inside its own cloud. Zooming in opens the rest.
    //
    // Theme mode only. In work mode the clouds are Origen's works and their
    // lobes are named after thematic domains, so the same grey names — Exegesis
    // and hermeneutics, Bible, text and canon — reappeared at the centre of the
    // largest work clusters and read as leftovers from the other mode. A second
    // rank is worth drawing when it refines the first; here it contradicts it.
    if (MODE !== 'theme') { window.__leaves = { tried: 0, drawn: 0, mode: MODE }; return; }
    var up = leafFade(), full = up > 0.8, drawn = 0, tried = 0;
    var ink = Math.min(0.95, 0.66 + up * 0.3), paper = Math.min(0.9, 0.7 + up * 0.2);
    ctx.font = '500 11px "Literata",Georgia,serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    var placed = TAG_BOXES.concat(chromeBoxes);
    // every drawn cloud, as a disc on the screen: a leaf name may not land on
    // a neighbour's disc
    var discs = CLUSTERS.filter(function (c) { return c.a >= 0.06; }).map(function (c) {
      return { x: wx(c.px), y: wy(c.py), r: haloR(c) + 2, c: c };
    });
    LOBE_BOXES = [];
    CLUSTERS.forEach(function (c) {
      if (c.a < 0.6 || c.kind === 'tail' || !c.lobes || matched) return;
      var cx = wx(c.px), cy = wy(c.py), R = radiusOf(c) * cam.s;
      var live = c.lobes.filter(function (lo) {
        return lo.name && lo.pubs.length >= (full ? 6 : 12);
      });
      if (!full) live = live.slice(0, 1);
      live.forEach(function (lo) {
        tried++;
        var x = cx + lo.x * cam.s, y = cy + lo.y * cam.s;
        if (x < 60 || x > W - 60 || y < 80 || y > H - 60) return;
        var t = lo.name.length > 34 ? lo.name.slice(0, 33) + '…' : lo.name;
        var tw = ctx.measureText(t).width;
        var bx = x - tw / 2 - 5, by = y - 8, bw = tw + 10, bh = 16;
        var box = { x: bx, y: by, w: bw, h: bh }, i;
        // a leaf name stays on its own domain and never lands on a neighbour
        if (Math.hypot(x - cx, y - cy) + bw / 2 > R * 1.4 + 26) return;
        for (i = 0; i < discs.length; i++) {
          if (discs[i].c !== c && rectHitsDisc(box, discs[i])) return;
        }
        for (i = 0; i < placed.length; i++) {
          var q = placed[i];
          if (bx < q.x + q.w && bx + bw > q.x && by < q.y + q.h && by + bh > q.y) return;
        }
        placed.push(box);
        LOBE_BOXES.push(box);
        ctx.lineWidth = 2.6; ctx.lineJoin = 'round';
        ctx.strokeStyle = hexA(PAPER, paper);
        ctx.strokeText(t, x, y);
        ctx.fillStyle = hexA(STONE, ink);
        ctx.fillText(t, x, y);
        drawn++;
      });
    });
    window.__leaves = { fade: +up.toFixed(3), full: full, tried: tried, drawn: drawn };
  }

  function pubShort(p) {
    var t = p.title || '';
    if (t.length > 20) t = t.slice(0, 19) + '…';
    return t;
  }
  function drawPubTags(host) {
    if (!host) return;
    var cxp = wx(host.px), cyp = wy(host.py);
    var placed = TAG_BOXES.concat(chromeBoxes);
    var queue = [];
    host.pubs.forEach(function (p) {
      if (!visiblePub(p)) return;
      if (matched && !matched.has(p.i)) return;
      var ox = p.cox == null ? p.ox : p.cox, oy = p.coy == null ? p.oy : p.coy;
      var x = cxp + ox * cam.s, y = cyp + oy * cam.s;
      var pr = Math.max(6, p.r * cam.s * 0.7);
      if (x < 28 || x > W - 28 || y < 86 || y > H - 22) return;
      if (pr < 9 && p !== hoverPub && p !== selPub) return;
      queue.push({ p: p, x: x, y: y });
    });
    queue.sort(function (a, b) {
      var ha = (a.p === hoverPub || a.p === selPub) ? 1 : 0;
      var hb = (b.p === hoverPub || b.p === selPub) ? 1 : 0;
      return hb - ha || b.p.w - a.p.w;
    });
    var cap = MOBILE ? 5 : 8, drawn = 0;
    queue.forEach(function (it) {
      var must = it.p === hoverPub || it.p === selPub;
      if (!must && drawn >= cap) return;
      var lines = [pubShort(it.p)];
      var m = measureTag(lines, 10, 7, 3);
      var box = { x: it.x - m.w / 2, y: it.y - m.h / 2, w: m.w, h: m.h };
      if (!must && (tagHits(box, placed) || tagHits(box, chromeBoxes))) return;
      placed.push(drawTag(it.x, it.y, lines, {
        fs: 10, padX: 7, padY: 3, a: 0.96, lit: must
      }));
      drawn++;
    });
  }
  function drawPathways() {
    var links = window.__links || [];
    links.forEach(function (l) {
      var a = CLUSTERS[l.a], b = CLUSTERS[l.b];
      if (!a || !b) return;
      var al = Math.min(a.a, b.a); if (al < 0.16) return;
      var ax = wx(a.px), ay = wy(a.py), bx = wx(b.px), by = wy(b.py);
      var dx = bx - ax, dy = by - ay, len = Math.hypot(dx, dy);
      if (len < 16 || len > Math.max(W, H) * 2.2) return;
      var mx = (ax + bx) / 2 - dy * 0.08, my = (ay + by) / 2 + dx * 0.08;
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.quadraticCurveTo(mx, my, bx, by);
      ctx.strokeStyle = hexA('#8A7348', 0.2 * al);
      ctx.lineWidth = 1.2;
      ctx.stroke();
      var steps = Math.max(8, Math.min(36, Math.round(len / 16)));
      ctx.fillStyle = hexA('#8A7348', 0.32 * al);
      for (var i = 1; i < steps; i++) {
        var u = i / steps, iu = 1 - u;
        var px = iu * iu * ax + 2 * iu * u * mx + u * u * bx;
        var py = iu * iu * ay + 2 * iu * u * my + u * u * by;
        ctx.beginPath();
        ctx.arc(px, py, 1.05, 0, 6.2832);
        ctx.fill();
      }
    });
  }
  function drawLocalNerves(host) {
    if (!host) return;
    var pts = [];
    var cxp = wx(host.px), cyp = wy(host.py);
    host.pubs.forEach(function (p) {
      if (!visiblePub(p)) return;
      if (matched && !matched.has(p.i)) return;
      var ox = p.cox == null ? p.ox : p.cox, oy = p.coy == null ? p.oy : p.coy;
      pts.push({ x: cxp + ox * cam.s, y: cyp + oy * cam.s });
    });
    if (pts.length < 3 || pts.length > 90) return;
    ctx.strokeStyle = hexA('#8A7348', 0.11);
    ctx.lineWidth = 0.8;
    var i, j, best, bd, d;
    for (i = 0; i < pts.length; i++) {
      best = -1; bd = 48;
      for (j = 0; j < pts.length; j++) {
        if (i === j) continue;
        d = Math.hypot(pts[j].x - pts[i].x, pts[j].y - pts[i].y);
        if (d > 10 && d < bd) { bd = d; best = j; }
      }
      if (best < 0 || best < i) continue;
      ctx.beginPath();
      ctx.moveTo(pts[i].x, pts[i].y);
      ctx.lineTo(pts[best].x, pts[best].y);
      ctx.stroke();
    }
  }

  function wrapLabel(label, max, maxLines) {
    if (label.length <= max) return [label];
    var words = label.split(' '), lines = [], cur = '';
    words.forEach(function (w) {
      if (!cur) { cur = w; return; }
      if ((cur + ' ' + w).length > max && lines.length < maxLines - 1) { lines.push(cur); cur = w; }
      else cur += ' ' + w;
    });
    if (cur) lines.push(cur);
    var last = lines.length - 1;
    if (lines[last].length > max + 8) lines[last] = lines[last].slice(0, max + 7) + '…';
    return lines;
  }

  function roundRect(x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  /* ------------------------------------------------------------------ picking */
  function pick(sx, sy) {
    var best = null, bd = 1e9;
    CLUSTERS.forEach(function (c) {
      if (c.a < 0.25) return;
      var R = radiusOf(c) * cam.s;
      var d = Math.hypot(wx(c.px) - sx, wy(c.py) - sy);
      if (d < R + 12 && d < bd) { bd = d; best = c; }
    });
    return best;
  }
  function pickPub(sx, sy) {
    if (!worksPickable(sx, sy)) return null;
    var best = null, bd = 1e9;
    CLUSTERS.forEach(function (c) {
      if (c.a < 0.25) return;
      var R = radiusOf(c) * cam.s, cxp = wx(c.px), cyp = wy(c.py);
      if (Math.hypot(cxp - sx, cyp - sy) > R + 24) return;
      c.pubs.forEach(function (p) {
        if (!visiblePub(p)) return;
        if (matched && !matched.has(p.i)) return;
        var ox = p.cox == null ? p.ox : p.cox, oy = p.coy == null ? p.oy : p.coy;
        var d = Math.hypot(cxp + ox * cam.s - sx, cyp + oy * cam.s - sy);
        var reach = pubReach(p);
        if (d < reach && d < bd) { bd = d; best = p; }
      });
    });
    return best;
  }

  /* ------------------------------------------------------------------ panel */
  var panel = document.getElementById('panel');
  var veil = document.getElementById('veil');
  var pSubject = document.getElementById('p-subject');
  var pDensity = document.getElementById('p-density');
  var pAlt = document.getElementById('p-alt');
  var pZones = document.getElementById('p-zones');
  var pBody = document.getElementById('p-body');
  var shownCount = 0, currentList = [];

  /* The summary, its fold, and the line that says where it comes from.
     Every displayed summary names the database that wrote it and links to the
     record there; one written for this project says so instead. Any rights
     holder who asks has theirs removed — the procedure is on the Credits page. */
  // the credit an abstract carries, in words: the list prints it under the
  // abstract, and an export that includes the abstract writes the same words
  function abstractCredit(p) {
    if (!p.ab || !p.ab.t) return null;
    if (p.ab.k === 'generated') return { text: 'Summary written for Origenality', label: '', url: '' };
    // set as the English pages set a catalogue label (no spaced colon)
    var label = englishLabel((ABS && ABS.sources && ABS.sources[p.ab.s] && ABS.sources[p.ab.s].label) || p.ab.s);
    return { text: 'Abstract from ' + label, label: label, url: p.ab.u || '' };
  }
  function abstractHTML(p, index) {
    if (!p.ab || !p.ab.t) return '';
    var text = p.ab.t;
    var long = text.length > ABSTRACT_FOLD;
    var id = 'ab-' + index;
    var c = abstractCredit(p);
    var credit = c.label && c.url
      ? 'Abstract from <a href="' + esc(c.url) + '" target="_blank" rel="noopener">' + esc(c.label) + '</a>'
      : esc(c.text);
    return '<div class="abstract">' +
      '<p class="abstract-text' + (long ? ' folded' : '') + '" id="' + id + '">' + esc(text) + '</p>' +
      (long ? '<button type="button" class="abstract-more" aria-expanded="false" aria-controls="' +
        id + '">Read the full abstract</button>' : '') +
      '<p class="abstract-credit">' + credit + '</p></div>';
  }

  // The link is the one the record carries, under the name of the base that
  // holds it; a record without a link gets no link rather than a guessed one.
  // A merged record can hold several records of one base: each of those links
  // then carries its catalogue number, or the reader sees identical links.
  function recordLinks(p) {
    var links = [], perSource = {}, seen = {};
    (p.sourceIds || []).forEach(function (entry) {
      if (entry.url) perSource[entry.source] = (perSource[entry.source] || 0) + 1;
    });
    (p.sourceIds || []).forEach(function (entry) {
      if (!entry.url) return;
      var label = esc(sourceName(entry.source)) + ' record';
      var many = perSource[entry.source];
      if (many > 1) {
        seen[entry.source] = (seen[entry.source] || 0) + 1;
        label += '<span class="rec-id">\u00a0' +
          (entry.id ? esc(entry.id) : seen[entry.source] + ' of ' + many) + '</span>';
      }
      links.push('<a href="' + esc(entry.url) + '" target="_blank" rel="noopener">' + label + '</a>');
    });
    if (!links.length && p.url) {
      links.push('<a href="' + esc(p.url) + '" target="_blank" rel="noopener">' +
        esc(sourceName(p.src)) + ' record</a>');
    }
    return links;
  }

  function recordHTML(p) {
    var meta = [];
    if (p.authors.length) meta.push(authorsHTML(p) + (p.authors.length > 3 ? ' and others' : ''));
    if (p.year != null) meta.push(String(p.year));
    if (p.container) meta.push('<i>' + esc(p.container) + '</i>');
    if (p.publisher) meta.push(esc(p.publisher));
    var links = recordLinks(p);
    if (p.doi) links.push('<a href="https://doi.org/' + esc(p.doi) + '" target="_blank" rel="noopener">DOI</a>');
    if (p.isbn) links.push('<span class="isbn">ISBN ' + esc(p.isbn) + '</span>');
    var wgt;
    if (p.wr && p.wr.c != null) {
      var pc = Math.round(p.wr.p * 100);
      var rank = pc <= 0 ? 'at the foot of its cohort'
        : (pc >= 100 ? 'at the head of its cohort' : ordinal(pc) + ' percentile of its cohort');
      wgt = 'cited ' + p.wr.c + (p.wr.c === 1 ? ' time' : ' times') + ', ' + rank +
        ' (' + esc(p.wr.ch) + ')';
    } else {
      wgt = 'no citation data';
    }
    var tags = [];
    p.themes.slice(0, 3).forEach(function (t) { tags.push(esc(SEM.themes[t].label)); });
    p.works.slice(0, 2).forEach(function (w) { tags.push('<i>' + esc(SEM.works[w].label) + '</i>'); });
    var flags = [];
    if (!p.dens) flags.push(esc(SEM.relevance[p.rel] ? SEM.relevance[p.rel].label : p.rel));
    if (p.review) flags.push('flagged for review');

    return '<article class="rec"><h5>' + esc(p.title) + '</h5>' +
      '<p class="meta">' + meta.join('<span class="dot">·</span>') +
      '<span class="dot">·</span><span class="lang"><i style="background:' + LCOL[p.lkey] + '"></i>' +
      esc(LLAB[p.lkey]) + '</span>' +
      (p.type ? '<span class="dot">·</span>' + esc(p.type) : '') + '</p>' +
      (tags.length ? '<p class="tags">' + tags.join(' · ') +
        (flags.length ? ' <span class="flag">· ' + flags.join(' · ') + '</span>' : '') + '</p>'
        : (flags.length ? '<p class="tags"><span class="flag">' + flags.join(' · ') + '</span></p>' : '')) +
      '<p class="weight" title="Node size = mean of the citation percentile inside the cohort and ' +
      'the PageRank percentile in this graph"><span class="tier t' + p.tier + '"></span>' + wgt + '</p>' +
      abstractHTML(p, p.i) +
      '<div class="links">' + links.join('') + '</div>' + coinsHTML(p) + '</article>';
  }

  /* What a density figure rests on (Method, section 4): of the counted records
     the figure counts, how many are flagged for review, how many were classified
     with an abstract, how many carry no year, and which catalogue gave most of
     them. Computed on the records, never typed. */
  function ledgerFigures(list) {
    var f = { n: 0, review: 0, withAbstract: 0, undated: 0, topSource: null, topCount: 0, topShare: 0 };
    var bySource = {};
    list.forEach(function (p) {
      if (!counts(p)) return;
      f.n++;
      if (p.review) f.review++;
      if (p.abstract) f.withAbstract++;
      if (!CORE.isDated(p)) f.undated++;
      if (p.src) bySource[p.src] = (bySource[p.src] || 0) + 1;
    });
    var top = Object.keys(bySource).sort(function (a, b) {
      return (bySource[b] - bySource[a]) || (a < b ? -1 : 1);
    })[0];
    if (top) {
      f.topSource = top; f.topCount = bySource[top];
      f.topShare = Math.round((bySource[top] * 100) / f.n);
    }
    return f;
  }
  function ledgerHTML(f) {
    if (!f.n) return '';
    var bits = [];
    bits.push(f.review ? nf(f.review) + ' flagged for review' : 'none flagged for review');
    if (!f.withAbstract) bits.push('none with an abstract, so classified from title, headings and container');
    else if (f.withAbstract === f.n) bits.push(f.n === 1 ? 'classified with its abstract' : 'all with an abstract');
    else bits.push(nf(f.withAbstract) + ' with an abstract, the rest classified from title, headings and container');
    if (f.undated) bits.push(nf(f.undated) + ' undated');
    if (f.topSource) bits.push(f.topShare + '% from ' + esc(sourceName(f.topSource)));
    if (f.n < 10) bits.push('small figure');
    var src = (SEM && SEM.source) || {};
    var classes = (src.counts_in_density || ['core', 'partial']).join(' and ');
    var wave = src.wave ? 'wave ' + esc(src.wave) : 'the tagging of ' + esc(SEM.generated || 'this build');
    return '<p class="ledger">' + (f.n === 1 ? 'Of this work: ' : 'Of these ' + nf(f.n) + ': ') +
      bits.join(' · ') + '.</p>' +
      '<p class="ledger">Tags from ' + wave + '; counted: ' + esc(classes) + '. Tagging agreement is ' +
      'reported in Method, § 1; no current figure against the hand-tagged set (§ 3).</p>';
  }

  /* How many counted works each term of the query reaches, in the population
     the questions leave. A term that reaches most of it narrows the question
     very little, and the reader should see that before reading the figure. */
  function termReach(r, total) {
    return r.terms.map(function (term, j) {
      var n = r.termHitsCounted ? r.termHitsCounted[j] : 0;
      return {
        term: term, n: n, most: total > 0 && n * 2 > total,
        absent: r.absentTerms.indexOf(term) >= 0 ? 'corpus'
          : (r.absentUnderFilters.indexOf(term) >= 0 ? 'filters'
            : ((r.absentFromPartialIndex || []).indexOf(term) >= 0 ? 'partial' : null))
      };
    });
  }
  function reachHTML(rows, narrowed) {
    if (!rows.length) return '';
    var notes = [];
    var cells = rows.map(function (row) {
      var q = '“' + esc(row.term) + '”';
      if (row.absent === 'corpus') {
        notes.push(q + ' appears in none of the ' + nf(PUBS.length) + ' records, in any field searched (' +
          esc(fieldsSearched()) + ')');
      } else if (row.absent === 'partial') notes.push(partialPhrase([esc(row.term)]));
      else if (row.absent === 'filters') notes.push(q + ' appears in none of the records your answers leave');
      else if (row.most) {
        notes.push(q + ' matches most of ' + (narrowed ? 'the works your answers leave' : 'the corpus') +
          ', so it narrows little');
      }
      return '<span class="zc">' + esc(row.term) + ' ' + nf(row.n) + '</span>';
    });
    var said = notes.join('; ');
    return '<p class="reach"><b>Reach of each term</b>, in counted works: ' + cells.join(' · ') + '.' +
      (said ? ' ' + said.charAt(0).toUpperCase() + said.slice(1) + '.' : '') + '</p>';
  }

  function byRank(a, b) {
    var ra = RANK && RANK[a.i] != null ? RANK[a.i] : Infinity;
    var rb = RANK && RANK[b.i] != null ? RANK[b.i] : Infinity;
    return ra === rb ? a.i - b.i : (ra < rb ? -1 : 1);
  }

  function renderPanel() {
    var list, title, adjacent = [];
    printShown = null;
    shownAuthor = null;
    panel.classList.toggle('one-work', !!selPub);
    if (selPub) {
      list = [selPub];
      title = selPub.title;
      pSubject.textContent = (selPub.year != null ? selPub.year + ' · ' : '') + (LLAB[selPub.lkey] || '');
      pDensity.innerHTML = esc(selPub.title);
      pAlt.textContent = '';
      var home = CLUSTERS.filter(function (c) {
        return c.kind === 'subject' && c.pubs.indexOf(selPub) >= 0;
      })[0];
      pZones.innerHTML = home
        ? '<p>In <button class="z" data-k="' + home.k + '">' + esc(home.label) + '</button></p>'
        : '';
      if (home) {
        pZones.querySelectorAll('.z').forEach(function (b) {
          b.addEventListener('click', function () { openCluster(CLUSTERS[+b.dataset.k]); focusPanelHead(); });
        });
      }
      VIEW = { kind: 'record', title: title, record: selPub, cluster: home || null,
        records: list, counted: selPub.dens ? list : [], figures: null };
      currentList = list;
      shownCount = 0;
      pBody.innerHTML = citeHTML();
      var head = document.createElement('div');
      head.className = 'listhead';
      head.innerHTML = '<span>Source</span><span>1 listed</span>';
      pBody.appendChild(head);
      appendMore();
      openPanel();
      pBody.scrollTop = 0;
      return;
    }
    // an author opened by name, or a query that is one author and nothing else
    var author = selAuthor || (sel ? null : soleAuthor());
    if (author) { renderAuthor(author); return; }
    if (sel) {
      list = sel.pubs.filter(function (p) { return visiblePub(p) && (!matched || matched.has(p.i)); });
      title = sel.label;
      pSubject.textContent = sel.note;
      pAlt.textContent = sel.alt || '';
      adjacent = sel.near.slice(0, 4).map(function (l) { return CLUSTERS[l.k]; })
        .filter(function (c) { return c && c.kind === 'subject'; });
    } else {
      list = PUBS.filter(function (p) { return visiblePub(p) && (!matched || matched.has(p.i)); });
      title = matchLabel || 'The whole corpus';
      pSubject.textContent = '';
      pAlt.textContent = '';
      var top = CLUSTERS.filter(function (c) { return c.kind === 'subject' && c.mn > 0; })
        .sort(function (a, b) { return b.mn - a.mn; }).slice(0, 3);
      var seen = {}; top.forEach(function (c) { seen[c.k] = 1; });
      var adjScore = {};
      top.forEach(function (c) {
        c.near.forEach(function (l) {
          if (seen[l.k]) return;
          if (!CLUSTERS[l.k] || CLUSTERS[l.k].kind !== 'subject') return;
          adjScore[l.k] = (adjScore[l.k] || 0) + l.w;
        });
      });
      adjacent = Object.keys(adjScore).sort(function (a, b) { return adjScore[b] - adjScore[a]; })
        .slice(0, 3).map(function (k) { return CLUSTERS[+k]; });
    }
    // an answer reads in the order the engine returned it, a cluster included
    if (matched && RANK) list.sort(byRank);

    // the headline figure is the counted population, the same one every other
    // surface prints and the same tally as the state line; what the list holds
    // beyond it is named underneath
    var scores = matched && LAST ? LAST.scores : null;
    var k = matched ? tokCount : 0;
    var t = tallyMatch(list, matched ? shelfOnly : null, scores, k);
    var mention = t.mention, aside = t.aside, shelf = t.shelf;
    var dens = t.hit;
    currentList = list;
    var n = list.length;
    var held = !!(sel && sel.id === OFF);
    // several terms: the headline is the records carrying all of them
    var conj = !!matched && k > 1 && !held;
    // a named shelf with no word of the query in its records: the state line
    // gives the shelf as the answer, and so does the headline, counted
    var shelfAnswer = !sel && !!matched && !dens && shelf > 0 && vocabHitCounted > 0;
    // the reservoir of records held as not about Origen states its own size:
    // it is a reservoir, not a figure of the field
    var headline = held ? n : (shelfAnswer ? vocabHitCounted : (conj ? t.full : dens));
    // the records the headline counts, which the reliability line describes
    var headRecs = headlineRecords(list, t, matched ? LAST : null, !!sel, held);
    var corpusDens = 0;
    PUBS.forEach(function (p) { if (counts(p)) corpusDens++; });
    // A thin neighbourhood is the point of this site, so it is typeset as an
    // answer: the figure, then what it is a figure OF.
    var where;
    if (sel) where = 'in ' + esc(title) + (matched ? ', under your current answers' : '');
    else if (matched) where = 'in the neighbourhood of ' + esc(matchLabel) + ', of ' + nf(corpusDens);
    else where = 'in the whole corpus';
    if (conj) {
      var wide = relaxed
        ? 'widened to ' + hitDepth + ' of ' + k + ' terms: ' + nf(n) + ' listed, ' + nf(dens) + ' counted, ' + where
        : '';
      if (t.full) {
        pDensity.innerHTML = nf(t.full) + (t.full === 1 ? ' work' : ' works') +
          '<small>' + (t.full === 1 ? 'carries' : 'carry') + ' all ' + k + ' of your terms' +
          (relaxed ? '' : ', ' + where) + '</small>' +
          (wide ? '<small>' + wide + '</small>' : '');
      } else {
        pDensity.innerHTML = '<span class="words">No counted work carries all ' + k + ' terms</span>' +
          '<small>' + (wide || (n ? nf(n) + (n === 1 ? ' record' : ' records') +
            ' listed, none of them counted, ' + where : where)) + '</small>';
      }
    } else if (shelfAnswer) {
      pDensity.innerHTML = nf(headline) + (headline === 1 ? ' work' : ' works') + '<small>' +
        'filed under “' + esc(vocabLabel) + '”, of ' + nf(corpusDens) +
        '; none names it in so many words</small>';
    } else if (!headline && n) {
      pDensity.innerHTML = nf(n) + (n === 1 ? ' record' : ' records') + '<small>' +
        'listed, none of them counted in the density figures, ' + where + '</small>';
    } else {
      pDensity.innerHTML = nf(headline) + (headline === 1 ? ' work' : ' works') +
        '<small>' + where + '</small>';
    }

    var zoneBits = [];
    zoneBits.push(ledgerHTML(ledgerFigures(headRecs)));
    if (conj && LAST) zoneBits.push(reachHTML(termReach(LAST, scopeDens), scopeDens !== corpusDens));
    if (held) {
      zoneBits.push('<p>This reservoir is held outside every figure on the site. ' +
        'Its records stay in the index and stay searchable.</p>');
    } else if (mention || aside) {
      var tail = [];
      if (mention) {
        tail.push(nf(mention) + (mention === 1 ? ' further work is mentioned only'
          : ' further works are mentioned only'));
      }
      if (aside) {
        tail.push(nf(aside) + (aside === 1 ? ' is held as not about Origen'
          : ' are held as not about Origen'));
      }
      zoneBits.push('<p>' + tail.join(', and ') + '. They are listed below the count, ' +
        'and they enter no figure on this site.</p>');
    }
    if (shelf && !shelfAnswer && !held) {
      zoneBits.push('<p>' + nf(shelf) + (shelf === 1 ? ' more work is' : ' more works are') +
        ' filed under the heading “' + esc(vocabLabel) + '” without naming it: ' +
        (shelf === 1 ? 'it is' : 'they are') + ' listed, and left out of this count.</p>');
    }
    if (sel && sel.kind === 'subject' && sel.lobes) {
      var leaves = sel.lobes.filter(function (lo) { return lo.name; }).slice(0, 5);
      if (leaves.length) {
        zoneBits.push('<p><b>Inside</b> ' + leaves.map(function (lo) {
          return esc(lo.name) + ' (' + lo.dens + ')';
        }).join(', ') + '</p>');
      }
    }
    if (!sel) {
      // the figure beside each zone is a count like the headline: counted records only
      var conc = CLUSTERS.filter(function (c) { return c.kind === 'subject' && c.mdens > 0; })
        .sort(function (a, b) { return b.mdens - a.mdens || b.mn - a.mn; }).slice(0, 3);
      if (conc.length) {
        zoneBits.push('<p><b>Concentrated in</b> ' + conc.map(function (c) {
          // the zone and its figure are kept together on one line when they fit
          return '<span class="zc"><button class="z" data-k="' + c.k + '">' + esc(c.label) +
            ' <span class="zn">(' + nf(c.mdens) + ')</span></button></span>';
        }).join(', ') + '</p>');
      }
    }
    if (adjacent.length) {
      zoneBits.push('<p><b>Adjacent zones</b> ' + adjacent.map(function (c) {
        return '<button class="z" data-k="' + c.k + '">' + esc(c.label) + '</button>';
      }).join(', ') + '</p>');
    }
    pZones.innerHTML = zoneBits.join('');
    pZones.querySelectorAll('.z').forEach(function (b) {
      b.addEventListener('click', function () { openCluster(CLUSTERS[+b.dataset.k]); focusPanelHead(); });
    });

    // what a later surface (export, print, decade strip) reads of this view
    VIEW = {
      kind: sel ? 'cluster' : (matched ? 'search' : 'corpus'),
      title: title, record: null, cluster: sel || null,
      records: list, counted: headRecs,
      figures: {
        headline: headline, counted: dens, full: t.full, conj: conj, relaxed: relaxed,
        depth: hitDepth, terms: k, listed: n, mention: mention, aside: aside, shelf: shelf,
        total: corpusDens, held: held, shelfAnswer: shelfAnswer
      }
    };

    shownCount = 0;
    pBody.innerHTML = '';
    if (!n) {
      // Nothing found is a finding: say what was asked, say what is missing from
      // the corpus, and only offer a remedy that applies here.
      var why = [];
      if (absentToks.length) {
        why.push(absentPhrase(absentToks.map(esc), 'the ' + nf(PUBS.length) + ' records') +
          ', in any field searched (' + esc(fieldsSearched()) + ')');
      }
      if (absentPartial.length) why.push(partialPhrase(absentPartial.map(esc)));
      if (absentFiltered.length) why.push(absentPhrase(absentFiltered.map(esc), 'the records your filters leave'));
      var offs = LANGS.filter(function (l) { return langOff[l.code]; });
      var fixes = [];
      if (offs.length) fixes.push('bring back the languages you switched off');
      var anyAns = false;
      QUESTIONS.forEach(function (q) { if (wizAns[q.kind] && wizAns[q.kind].length) anyAns = true; });
      if (anyAns) fixes.push('drop one answer');
      if (tokCount > 1) fixes.push('use fewer terms');
      pBody.innerHTML = citeHTML() +
        '<p class="empty"><svg class="mk" viewBox="0 0 100 100" width="12" height="12" aria-hidden="true">' +
        '<g stroke="currentColor" stroke-width="12" fill="none"><path d="M50 14 L50 86"/><path d="M14 50 L86 50"/></g>' +
        '<g fill="currentColor"><circle cx="27" cy="27" r="8"/><circle cx="73" cy="27" r="8"/>' +
        '<circle cx="27" cy="73" r="8"/><circle cx="73" cy="73" r="8"/></g></svg> ' +
        'Nothing in the harvest answers this' +
        (why.length ? ': ' + why.join('; ') : '') + '.' +
        (fixes.length ? ' You could ' + fixes.join(', or ') + '.' : '') +
        '</p>';
      openPanel();
      return;
    }
    pBody.innerHTML = (headRecs.length || CMP ? STRIP_SHELL : '') + citeHTML();
    renderStrip();
    var head2 = document.createElement('div');
    head2.className = 'listhead';
    head2.innerHTML = '<span>Sources</span><span>' + nf(n) + ' listed</span>';
    pBody.appendChild(head2);
    appendMore();
    openPanel();
    pBody.scrollTop = 0;
  }

  /* ------------------------------------------------------------------ citing a view */
  // The view named in words, with the figures the panel prints. The address and
  // the date are taken when the reader asks for them, not when the panel opened.
  function viewDescription(v) {
    var s = 'build ' + DATA_VERSION + ', ';
    if (!v) return s + 'the map';
    if (v.kind === 'record') {
      var p = v.record;
      return s + 'record “' + p.title + '”' + (p.year != null ? ', ' + p.year : '') +
        ' (' + recordKey(p) + ')';
    }
    var f = v.figures;
    if (v.kind === 'author') {
      s += 'author “' + v.author.label + '”, the records filed under that form of the name';
    } else if (v.kind === 'cluster') {
      s += 'cluster “' + v.cluster.label + '”, grouped by ' +
        (MODE === 'work' ? 'work of Origen' : 'theme') + (matched ? ', under ' + matchLabel : '');
    } else if (v.kind === 'search') s += 'view ' + matchLabel;
    else s += 'the whole corpus';
    var fig;
    if (f.held) fig = nf(f.listed) + ' held outside every count';
    else if (f.conj) {
      fig = nf(f.full) + ' counted carrying all ' + f.terms + ' terms, of ' + nf(f.total) +
        (f.relaxed ? ', widened to ' + f.depth + ' terms: ' + nf(f.listed) + ' listed, ' + nf(f.counted) + ' counted' : '');
    } else {
      fig = nf(f.headline) + ' counted of ' + nf(f.total) +
        (f.mention ? ', ' + nf(f.mention) + ' mentioned only' : '') +
        (f.aside ? ', ' + nf(f.aside) + ' held aside' : '');
    }
    var hidden = v.kind === 'author' ? []
      : LANGS.filter(function (l) { return langOff[l.code]; }).map(function (l) { return l.label; });
    return s + ': ' + fig + (hidden.length ? ', not shown: ' + hidden.join(', ') : '');
  }
  function viewUrl() {
    // resolved against the page in hand, so a copy made under a path prefix or
    // in a local preview points back to that same page
    var u = new URL(location.href);
    u.hash = addressOf(currentState());
    return u.href;
  }
  function isoDay(d) {
    function two(x) { return (x < 10 ? '0' : '') + x; }
    return d.getFullYear() + '-' + two(d.getMonth() + 1) + '-' + two(d.getDate());
  }
  function citationText() {
    return 'Origenality, ' + viewDescription(VIEW) + ', ' + viewUrl() + ', accessed ' + isoDay(new Date()) + '.';
  }
  function buildNote() {
    return 'Link made on build ' + linkBuild + '; figures shown are from build ' + DATA_VERSION + '.';
  }
  function citeHTML() {
    var v = VIEW, canExport = !!(CITE && v && v.records && v.records.length);
    return '<div class="cite">' +
      (linkBuild ? '<p class="cite-note">' + esc(buildNote()) + '</p>' : '') +
      '<p class="cite-line">' + esc(citationText()) + '</p>' +
      '<p class="cite-url" hidden></p>' +
      '<div class="cite-tools">' +
      '<button type="button" class="btn-quiet cite-link">Copy link</button>' +
      '<button type="button" class="btn-quiet cite-copy">Copy citation</button>' +
      // Print comes before Export, so the key reaches the export fold straight
      // after the control that opens it
      '<button type="button" class="btn-quiet cite-print">Print this view</button>' +
      (canExport ? '<button type="button" class="btn-quiet cite-export" aria-expanded="false" ' +
        'aria-controls="export-fold">' + esc(exportLabel(v)) + '</button>' : '') +
      '<span class="cite-said" role="status" aria-live="polite"></span></div>' +
      (canExport ? exportHTML(v) : '') + '</div>';
  }
  function copyView(asCitation, box) {
    var text = asCitation ? citationText() : viewUrl();
    var line = box.querySelector('.cite-line'), urlEl = box.querySelector('.cite-url');
    var said = box.querySelector('.cite-said');
    line.textContent = citationText();
    function selectInstead() {
      var target = line;
      if (!asCitation) { urlEl.textContent = text; urlEl.hidden = false; target = urlEl; }
      try {
        var range = document.createRange();
        range.selectNodeContents(target);
        var s = getSelection();
        s.removeAllRanges(); s.addRange(range);
      } catch (e) { /* the text stays on screen to be copied by hand */ }
      said.textContent = (asCitation ? 'The citation' : 'The link') +
        ' is selected: copy it from the menu or the keyboard.';
    }
    try {
      navigator.clipboard.writeText(text).then(function () {
        said.textContent = asCitation ? 'Citation copied.' : 'Link copied.';
      }, selectInstead);
    } catch (e) { selectInstead(); }
  }

  // focusNew: the reader asked for more, so the focus goes to the first record
  // added before the control that asked is taken away
  function appendMore(focusNew) {
    var slice = currentList.slice(shownCount, shownCount + 20);
    var first = pBody.querySelectorAll('.rec').length;
    var frag = document.createElement('div');
    frag.innerHTML = slice.map(recordHTML).join('');
    while (frag.firstChild) pBody.appendChild(frag.firstChild);
    shownCount += slice.length;
    if (focusNew) {
      var added = pBody.querySelectorAll('.rec')[first];
      var h = added && added.querySelector('h5');
      if (h) { h.setAttribute('tabindex', '-1'); h.focus(); }
    }
    placeMore();
  }
  function placeMore() {
    var old = pBody.querySelector('.more'); if (old) old.remove();
    if (shownCount < currentList.length) {
      var b = document.createElement('button');
      b.className = 'btn-quiet more';
      b.textContent = 'Show 20 more of ' + nf(currentList.length - shownCount);
      b.addEventListener('click', function () { appendMore(true); });
      pBody.appendChild(b);
    }
  }

  /* ------------------------------------------------------------------ exporting a view
     The records of the open view as references for a reference manager. What
     is exported is what the panel lists, in its order: counted records, and the
     records mentioned only or held aside alike, marked by a keyword; the control
     says how many. Every field comes from the record, and cite.js says which
     goes where. Containers are read from the record file when the control is
     first opened, because graph.json keeps a container only when five records
     share it. The light file data/cite.json (tools/build_cite_data.py) holds what
     the export needs of each record; the whole record file is read only when
     that one cannot be. */
  var CONTAINERS = null, CITE_FIELDS = null, containersTried = false, containersAsked = null, CITE_KEYS = null;
  function loadContainers() {
    if (!containersAsked) {
      // the file the search index reads after the first render, fetched once
      containersAsked = readCiteFile()
        .then(function (json) {
          var d = CITE.citeData(json);
          CONTAINERS = d.containers;
          CITE_FIELDS = d.fields;
        })
        .catch(function (first) {
          console.warn('Explorer export: ' + first.message + '; reading the record file');
          return fetch(versioned('../data/site-merged/corpus.jsonl'))
            .then(function (r) {
              if (!r.ok) throw new Error('record file answered ' + r.status);
              return r.text();
            })
            .then(function (text) { CONTAINERS = CITE.containersFromCorpus(text); CITE_FIELDS = null; })
            .catch(function (err) { CONTAINERS = null; CITE_FIELDS = null; console.warn('Explorer export: ' + err.message); });
        })
        .then(function () { containersTried = true; return CONTAINERS; });
    }
    return containersAsked;
  }
  // one key per record over the whole build, so a record keeps its key
  // whichever view exports it
  function citeKeys() {
    if (!CITE_KEYS) {
      CITE_KEYS = Object.create(null);
      CITE.assignKeys(PUBS.map(function (p) { return CITE.entryFromRecord(p, {}); }))
        .forEach(function (e) { CITE_KEYS[e.recordId] = e.key; });
    }
    return CITE_KEYS;
  }
  function citeEntry(p, withAbstract) {
    var credit = withAbstract ? abstractCredit(p) : null;
    var e = CITE.entryFromRecord(p, {
      containers: CONTAINERS, fields: CITE_FIELDS, sourceName: sourceName,
      abstract: credit ? { text: p.ab.t, credit: credit.text, url: credit.url } : null
    });
    e.key = citeKeys()[e.recordId] || '';
    return e;
  }
  // an empty COinS span, read by the browser connector of a reference manager;
  // its container is the one the list shows until an export has read the file
  function coinsHTML(p) {
    if (!CITE) return '';
    return '<span class="Z3988" title="' +
      esc(CITE.toCOinS(CITE.entryFromRecord(p, { containers: CONTAINERS, fields: CITE_FIELDS, sourceName: sourceName }))) + '"></span>';
  }
  function exportCounts(records) {
    var c = { n: records.length, mention: 0, aside: 0, abstracts: 0 };
    records.forEach(function (p) {
      if (!counts(p)) { if (p.rel === 'none') c.aside++; else c.mention++; }
      if (p.ab && p.ab.t) c.abstracts++;
    });
    return c;
  }
  function exportLabel(v) {
    if (v.kind === 'record') return 'Export this record';
    var n = v.records.length;
    return 'Export ' + nf(n) + (n === 1 ? ' record' : ' records');
  }
  function exportHTML(v) {
    var c = exportCounts(v.records), what;
    if (v.kind === 'record') {
      what = 'This record as a reference, with the fields its catalogue record gives and a link back to that record.';
    } else {
      what = (c.n === 1 ? 'The record listed here' : 'The ' + nf(c.n) + ' records listed here, in the order shown') +
        ', with the fields each catalogue record gives and a link back to it.';
      var marked = [];
      if (c.mention) marked.push(nf(c.mention) + ' mentioned only');
      if (c.aside) marked.push(nf(c.aside) + ' held aside');
      if (marked.length) what += ' Included and marked by a keyword: ' + marked.join(', ') + '.';
    }
    what += ' The data holds no volume, issue or pages.';
    var abs = '';
    if (c.abstracts) {
      abs = '<label class="export-abs"><input type="checkbox" class="export-abstracts"> ' +
        (c.n === 1 ? 'Include its abstract' : (c.abstracts === 1 ? 'Include the one abstract'
          : 'Include the ' + nf(c.abstracts) + ' abstracts')) +
        (c.abstracts === 1 ? ', credited to the database that wrote it' : ', each credited to the database that wrote it') +
        '</label>';
    }
    return '<div class="export" id="export-fold" hidden>' +
      '<p class="export-what">' + esc(what) + '</p>' + abs +
      '<div class="export-formats">' +
      ['bibtex', 'ris', 'csl'].map(function (f) {
        return '<button type="button" class="btn-quiet export-fmt" data-format="' + f + '" aria-label="' +
          esc(CITE.FORMATS[f].label + ', .' + CITE.FORMATS[f].ext + ' file') + '">' +
          esc(CITE.FORMATS[f].label) + ' <span class="ext">.' + CITE.FORMATS[f].ext + '</span></button>';
      }).join('') +
      '<button type="button" class="linkish export-copy" data-format="bibtex">Copy as BibTeX</button>' +
      '</div></div>';
  }
  function toggleExport(btn) {
    var fold = document.getElementById(btn.getAttribute('aria-controls'));
    if (!fold) return;
    var open = fold.hasAttribute('hidden');
    if (open) fold.removeAttribute('hidden'); else fold.setAttribute('hidden', '');
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    // the record file is read as the control opens, so the format chosen next
    // is written within the reader's own click
    if (open && CITE) loadContainers();
  }
  function download(text, name, mime) {
    var url = URL.createObjectURL(new Blob([text], { type: mime }));
    var a = document.createElement('a');
    a.href = url; a.download = name; a.hidden = true;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
  }
  function exportView(format, copy, box) {
    if (!CITE || !CITE.FORMATS[format] || !VIEW || !VIEW.records || !VIEW.records.length) return;
    var said = box.querySelector('.cite-said');
    var check = box.querySelector('.export-abstracts');
    var withAbstracts = !!(check && check.checked);
    var view = VIEW;
    function write() {
      if (VIEW !== view) return;
      var entries = view.records.map(function (p) { return citeEntry(p, withAbstracts); });
      var many = nf(entries.length) + (entries.length === 1 ? ' entry' : ' entries');
      var text = CITE.render(format, entries, {
        header: ['Origenality, ' + viewDescription(view), viewUrl(),
          'accessed ' + isoDay(new Date()) + ', ' + many + ', UTF-8']
      });
      var thin = CONTAINERS ? '' : ' The record file could not be read, so a container is given only where five records share it.';
      if (copy) {
        var done = function () { said.textContent = many + ' copied as BibTeX.' + thin; };
        var refused = function () { said.textContent = 'The browser refused the copy; the BibTeX file holds the same text.' + thin; };
        try { navigator.clipboard.writeText(text).then(done, refused); } catch (e) { refused(); }
        return;
      }
      // a file with abstracts is named apart, so it never replaces one without
      var name = CITE.fileName((view.kind === 'record' ? 'record ' + recordKey(view.record) : view.title) +
        (withAbstracts ? ' with abstracts' : ''), DATA_VERSION, format);
      download(text, name, CITE.FORMATS[format].mime);
      said.textContent = many + ' written to ' + name + '.' + thin;
    }
    if (containersTried) write();
    else {
      said.textContent = 'Reading the record file…';
      loadContainers().then(write);
    }
  }

  /* ------------------------------------------------------------------ an author
     One author node of graph.json and the records its edges reach: the name as
     the catalogue writes it. Two spellings of one scholar are two nodes, and the
     data holds no link between them, so nothing here merges them. The view lists
     every record under the name, whatever the search and the filters leave. */
  var AUTHOR_NOTE = 'Records filed under this exact form of the name in the harvested catalogues. ' +
    'Other spellings of the same scholar are separate entries and are not merged. ' +
    'Your search and the filters do not narrow this list.';

  function authorsOf(g, records) {
    var at = {}, byId = Object.create(null), ofPub = {}, list = [];
    records.forEach(function (p) { at[p.nodeIndex] = p; });
    ((g && g.edges) || []).forEach(function (e) {
      if (e.r !== 'aut') return;
      var p = at[e.s], node = g.nodes[e.t];
      if (!p || !node || node.k !== 'author' || !node.id || !node.label) return;
      var a = byId[node.id];
      if (!a) { a = byId[node.id] = { id: node.id, label: node.label, pubs: [], seen: {} }; list.push(a); }
      if (a.seen[p.i]) return;
      a.seen[p.i] = 1;
      a.pubs.push(p);
      (ofPub[p.i] || (ofPub[p.i] = [])).push(a);
    });
    return { byId: byId, ofPub: ofPub, list: list };
  }
  function authorIndex() { return AUTHORS || (AUTHORS = authorsOf(DATA, PUBS)); }

  // a scholar's records in the order they were published, the undated last
  function byYear(a, b) {
    var da = CORE.isDated(a), db = CORE.isDated(b);
    if (da !== db) return da ? -1 : 1;
    if (da && Number(a.year) !== Number(b.year)) return Number(a.year) - Number(b.year);
    var ta = a.sortTitle || '', tb = b.sortTitle || '';
    return ta < tb ? -1 : (ta > tb ? 1 : a.i - b.i);
  }
  // the vocabulary keys a set of records carries, most carried first
  function keyCounts(records, field, vocab) {
    var n = {};
    records.forEach(function (p) { (p[field] || []).forEach(function (k) { n[k] = (n[k] || 0) + 1; }); });
    return Object.keys(n).map(function (k) {
      return { key: k, label: vocab && vocab[k] ? vocab[k].label : k, n: n[k] };
    }).sort(function (x, y) { return y.n - x.n || (x.key < y.key ? -1 : (x.key > y.key ? 1 : 0)); });
  }
  // What the author view prints, computed once. Every figure counts the counted
  // records; the co-authors are names without a figure, in alphabetical order,
  // so nothing here ranks one scholar above another.
  function authorSummary(a, sem, ofPub) {
    var records = a.pubs.slice().sort(byYear);
    var counted = records.filter(counts);
    var s = {
      id: a.id, label: a.label, records: records, counted: counted, mention: 0, aside: 0,
      themes: keyCounts(counted, 'themes', sem.themes), works: keyCounts(counted, 'works', sem.works),
      approaches: keyCounts(counted, 'approaches', sem.approaches),
      languages: {}, containers: [], coauthors: []
    };
    records.forEach(function (p) {
      if (counts(p)) return;
      if (p.rel === 'none') s.aside++; else s.mention++;
    });
    var inC = {};
    counted.forEach(function (p) {
      var code = p.lang || '';
      s.languages[code] = (s.languages[code] || 0) + 1;
      if (p.container) inC[p.container] = (inC[p.container] || 0) + 1;
    });
    s.containers = Object.keys(inC).map(function (c) { return { label: c, n: inC[c] }; })
      .sort(function (x, y) { return y.n - x.n || (x.label < y.label ? -1 : (x.label > y.label ? 1 : 0)); });
    var seen = {};
    records.forEach(function (p) {
      (ofPub[p.i] || []).forEach(function (o) {
        if (o.id === a.id || seen[o.id]) return;
        seen[o.id] = 1;
        s.coauthors.push({ id: o.id, label: o.label });
      });
    });
    s.coauthors.sort(function (x, y) {
      var nx = norm(x.label), ny = norm(y.label);
      return nx < ny ? -1 : (nx > ny ? 1 : (x.id < y.id ? -1 : (x.id > y.id ? 1 : 0)));
    });
    return s;
  }

  // A query that holds one author: condition and nothing else, with no answer
  // and no language switched off, and whose records are exactly those of one
  // author node, is shown as that author's view: the same records, the same
  // figures. A name that several nodes answer stays a search.
  function soleAuthor() {
    var r = LAST;
    if (!r || !matched || queryProblem || r.terms.length || r.phrases.length || r.exclude.length ||
      r.excludePhrases.length || r.filters.length !== 1 || r.filters[0].field !== 'authors' || r.filters[0].neg) {
      return null;
    }
    if (answersKeep() || LANGS.some(function (l) { return langOff[l.code]; })) return null;
    return soleAuthorOf(r, authorIndex());
  }
  function soleAuthorOf(r, idx) {
    var seen = {}, hit = null, many = false;
    r.matched.forEach(function (i) {
      (idx.ofPub[i] || []).forEach(function (a) {
        if (many || seen[a.id]) return;
        seen[a.id] = 1;
        // the name alone, put to the engine with the query as typed
        if (!CORE.search([{ i: 0, authors: [a.label], hay: '', vocab: '' }], r.query).matched.size) return;
        if (hit) many = true; else hit = a;
      });
    });
    return hit && !many && hit.pubs.length === r.matched.size ? hit : null;
  }

  // the first three names of a record, each a button that opens that author,
  // when the graph holds a node for each name of the record
  function authorsHTML(p) {
    var own = (DATA ? authorIndex().ofPub[p.i] : null) || [];
    var aligned = own.length === p.authors.length &&
      own.every(function (a, k) { return a.label === p.authors[k]; });
    return p.authors.slice(0, 3).map(function (name, k) {
      if (!aligned || own[k] === shownAuthor) return esc(name);
      return '<button type="button" class="au" data-a="' + esc(own[k].id) + '">' + esc(name) + '</button>';
    }).join(', ');
  }

  function openAuthor(a) {
    if (!a) return;
    userMoved();
    selAuthor = a;
    sel = null;
    selPub = null;
    renderPanel();
    invalidate();
    syncHash(true);
  }

  // items of a zone line, each carrying its own comma, so no line opens on one
  function zoneList(items) {
    return items.map(function (html, i) {
      return '<span class="zc">' + html + (i < items.length - 1 ? ',' : '') + '</span>';
    }).join(' ');
  }
  function zoneKeys(title, rows, field, italic) {
    if (!rows.length) return '';
    return '<p><b>' + title + '</b> ' + zoneList(rows.slice(0, 5).map(function (r) {
      var label = italic ? '<i>' + esc(r.label) + '</i>' : esc(r.label);
      // the count sits inside the button, so it never wraps away from its heading
      return '<button type="button" class="z" data-q="' + esc(field + ':' + r.key) + '">' + label +
        ' <span class="zn">(' + nf(r.n) + ')</span></button>';
    })) + '</p>';
  }

  function renderAuthor(a) {
    var s = authorSummary(a, SEM, authorIndex().ofPub);
    shownAuthor = a;
    panel.classList.remove('one-work');
    var list = s.records, n = list.length, dens = s.counted.length;
    var corpusDens = 0;
    PUBS.forEach(function (p) { if (counts(p)) corpusDens++; });
    pSubject.textContent = 'Author, as the catalogues write the name';
    pDensity.innerHTML = dens
      ? nf(dens) + (dens === 1 ? ' work' : ' works') + '<small>filed under ' + esc(a.label) + ', of ' +
        nf(corpusDens) + '</small>'
      : nf(n) + (n === 1 ? ' record' : ' records') + '<small>listed under ' + esc(a.label) +
        ', none of them counted in the density figures</small>';
    pAlt.textContent = AUTHOR_NOTE;

    var zoneBits = [ledgerHTML(ledgerFigures(s.counted))];
    if (s.mention || s.aside) {
      var tail = [];
      if (s.mention) {
        tail.push(nf(s.mention) + (s.mention === 1 ? ' further work is mentioned only'
          : ' further works are mentioned only'));
      }
      if (s.aside) tail.push(nf(s.aside) + (s.aside === 1 ? ' is held as not about Origen' : ' are held as not about Origen'));
      zoneBits.push('<p>' + tail.join(', and ') + '. They are listed below the count, ' +
        'and they enter no figure on this site.</p>');
    }
    zoneBits.push(zoneKeys('Themes', s.themes, 'theme', false));
    zoneBits.push(zoneKeys('Works of Origen', s.works, 'work', true));
    zoneBits.push(zoneKeys('Angles', s.approaches, 'approach', false));
    var byKey = {};
    Object.keys(s.languages).forEach(function (code) {
      var k = lkey(code);
      byKey[k] = (byKey[k] || 0) + s.languages[code];
    });
    var langs = LANGS.filter(function (l) { return byKey[l.code]; })
      .sort(function (x, y) { return byKey[y.code] - byKey[x.code]; });
    if (langs.length) {
      zoneBits.push('<p><b>Languages</b> ' + zoneList(langs.map(function (l) {
        return esc(l.label) + ' (' + nf(byKey[l.code]) + ')';
      })) + '</p>');
    }
    if (s.containers.length) {
      var more = s.containers.length - 5;
      var inItems = s.containers.slice(0, 5).map(function (c) { return '<i>' + esc(c.label) + '</i> (' + nf(c.n) + ')'; });
      if (more > 0) inItems.push('and ' + nf(more) + (more === 1 ? ' other journal or volume' : ' other journals or volumes'));
      zoneBits.push('<p><b>In</b> ' + zoneList(inItems) + '</p>');
    }
    if (s.coauthors.length) {
      zoneBits.push('<p><b>With</b> ' + zoneList(s.coauthors.map(function (o) {
        return '<button type="button" class="z" data-a="' + esc(o.id) + '">' + esc(o.label) + '</button>';
      })) + '</p>');
    }
    pZones.innerHTML = zoneBits.join('');

    VIEW = {
      kind: 'author', title: a.label, author: a, record: null, cluster: null,
      records: list, counted: s.counted,
      figures: {
        headline: dens, counted: dens, full: 0, conj: false, relaxed: false, depth: 0, terms: 0,
        listed: n, mention: s.mention, aside: s.aside, shelf: 0, total: corpusDens, held: false, shelfAnswer: false
      }
    };
    currentList = list;
    shownCount = 0;
    pBody.innerHTML = (dens || CMP ? STRIP_SHELL : '') + citeHTML();
    renderStrip();
    var head = document.createElement('div');
    head.className = 'listhead';
    head.innerHTML = '<span>By year of publication</span><span>' + nf(n) + ' listed</span>';
    pBody.appendChild(head);
    appendMore();
    openPanel();
    pBody.scrollTop = 0;
  }

  // a heading of the author view opens the Explorer view of that heading, as a
  // new step: Back returns to the author
  function searchFor(q) {
    try { history.pushState({ view: 1 }, '', location.href); } catch (e) { /* the search still runs */ }
    query = q;
    linkBuild = null;
    document.getElementById('ask-input').value = q;
    document.getElementById('ask-field').classList.toggle('filled', !!q.trim());
    selAuthor = null;
    applyMatch(true);
  }

  /* ------------------------------------------------------------------ decades of a view
     The counted records the headline counts, by decade of publication, in the
     columns of decadeRows; a second query beside them, run through the same
     engine under the same answers and language key, and counted as the search
     field counts it. The strip, the SVG and the CSV are written from the same
     rows, so the three cannot disagree. */
  var STRIP_SHELL = '<div class="strip" id="p-strip"></div>';

  function compareSeries(q) {
    q = String(q || '').trim();
    if (!q) return null;
    var r = CORE.search(IDX, q, { keep: answersKeep() });
    if (r.invalid || r.normalisedEmpty) {
      return { label: '“' + q + '”', query: q, records: [], listed: 0, problem: problemLine(r) };
    }
    var list = PUBS.filter(function (p) { return visiblePub(p) && r.matched.has(p.i); });
    var t = tallyMatch(list, r.vocabOnly, r.scores, r.terms.length);
    return {
      label: '“' + q + '”', query: q, records: headlineRecords(list, t, r, false, false),
      listed: list.length, problem: ''
    };
  }
  function stripState(v) {
    if (!v || v.kind === 'record' || !v.figures || v.figures.held) return null;
    var series = [{ label: v.title, query: '', records: v.counted, listed: v.records.length, problem: '' }];
    var cmp = compareSeries(CMP);
    if (cmp && !cmp.problem) series.push(cmp);
    return {
      view: v, series: series, rows: decadeRows(series.map(function (x) { return x.records; }), buildYear()),
      problem: cmp && cmp.problem ? cmp.problem : ''
    };
  }
  function shortDecade(r) {
    if (r.key === 'before-1950') return '<span aria-hidden="true">&lt;1950</span><span class="sr">Before 1950</span>';
    // one term for a record with no year, on screen, on paper, in the SVG and the CSV
    if (r.key === 'undated') return 'Undated';
    // on a phone eleven columns at 11 px leave a decade 30 px: its label is
    // abbreviated there (’50s), with the full label as the abbreviation's title
    return '<span class="dl">' + esc(r.label) + '</span><abbr class="ds" title="' + esc(r.label) + '">\u2019' +
      esc(String(r.key).slice(2)) + 's</abbr>' + (r.open ? '<small>open</small>' : '');
  }
  function stripHTML(st) {
    var max = 0;
    st.rows.forEach(function (r) { r.n.forEach(function (x) { max = Math.max(max, x); }); });
    var restricted = !!answersKeep() || LANGS.some(function (l) { return langOff[l.code]; });
    var legend = st.series.map(function (x, i) {
      return '<li class="s' + i + '"><i aria-hidden="true"></i><span>' + esc(x.label) + ', ' + nf(x.records.length) +
        ' counted' + (i === 0 && x.listed > x.records.length ? ' of ' + nf(x.listed) + ' listed' : '') + '</span></li>';
    }).join('');
    var table = '<table class="decades" aria-labelledby="strip-cap"><thead><tr><th scope="col"><span class="sr">Series</span></th>' +
      st.rows.map(function (r) {
        return '<th scope="col"' + (r.key === 'undated' ? ' class="undated"' : (r.key === 'before-1950' ? ' class="pre"' : '')) + '>' +
          shortDecade(r) + '</th>';
      }).join('') +
      '</tr></thead><tbody>' + st.series.map(function (x, i) {
        return '<tr class="s' + i + '"><th scope="row"><i aria-hidden="true"></i><span class="sr">' + esc(x.label) + '</span></th>' +
          st.rows.map(function (r) {
            var c = r.n[i];
            return '<td' + (c ? ' style="--h:' + (c / max).toFixed(3) + '"' : ' class="zero"') + '><span>' + nf(c) + '</span></td>';
          }).join('') + '</tr>';
      }).join('') + '</tbody></table>';
    var notes = ['Counted records, core and partial. Records before 1950 share one column, and undated records have their own.'];
    var open = st.rows.filter(function (r) { return r.open; })[0];
    if (open) {
      notes.push('The ' + open.label + ' are open: this build was generated on ' +
        esc((META && META.generated) || String(buildYear())) + '.');
    }
    if (st.series.length > 1 && restricted) {
      notes.push('The compared query runs under your answers and the language key, as the search field runs it' +
        (st.view.kind === 'author' ? '; the author’s records do not.' : '.'));
    }
    return '<p class="strip-cap" id="strip-cap">Counted records by decade of publication</p>' +
      '<ul class="strip-legend">' + legend + '</ul>' +
      '<div class="strip-wrap" role="region" tabindex="0" aria-label="Counted records by decade">' + table + '</div>' +
      '<p class="strip-note">' + notes.join(' ') + '</p>' +
      '<form class="strip-cmp" novalidate><label for="strip-q">Compare with</label><span class="strip-field">' +
      '<input id="strip-q" type="search" autocomplete="off" spellcheck="false" placeholder="work:princ" value="' + esc(CMP) + '">' +
      '<button type="submit" class="btn-quiet">Compare</button></span>' +
      (CMP ? '<button type="button" class="linkish strip-drop">Remove the comparison</button>' : '') + '</form>' +
      // said once, by the live region outside the strip (sayCompare)
      (st.problem ? '<p class="strip-problem">' + esc(st.problem) + '</p>' : '') +
      '<div class="strip-tools"><button type="button" class="btn-quiet strip-svg">Download SVG</button>' +
      '<button type="button" class="btn-quiet strip-csv">Download CSV</button>' +
      '<button type="button" class="linkish strip-copy">Copy SVG</button>' +
      '<span class="strip-said" role="status" aria-live="polite"></span></div>';
  }
  function renderStrip() {
    var box = document.getElementById('p-strip');
    STRIP = stripState(VIEW);
    if (!box) return;
    if (!STRIP) { box.hidden = true; box.innerHTML = ''; return; }
    box.hidden = false;
    box.innerHTML = stripHTML(STRIP);
  }
  function setCompare(q) {
    userMoved();
    CMP = String(q || '').trim();
    renderStrip();
    var input = document.getElementById('strip-q');
    if (input) input.focus({ preventScroll: true });
    sayCompare();
    syncHash(false);
  }
  // The strip is written again whole, so a live region inside it is never
  // heard: the result is said by one that stays in the panel.
  function compareMessage(st, cmp) {
    if (!st) return cmp ? 'This view has no decade table to compare with.' : '';
    if (st.problem) return st.problem;
    if (st.series.length > 1) {
      var a = st.series[0], b = st.series[1];
      return 'Compared by decade: ' + b.label + ', ' + nf(b.records.length) + ' counted, beside ' +
        a.label + ', ' + nf(a.records.length) + ' counted.';
    }
    return 'The comparison is removed.';
  }
  function sayCompare() {
    var live = document.getElementById('strip-live');
    if (!live) return;
    var text = compareMessage(STRIP, CMP);
    live.textContent = '';
    setTimeout(function () { live.textContent = text; }, 60);
  }

  // What the exported figure says of itself, in lines: the view and its figures,
  // the compared query, what is counted, the open decade, what the catalogues
  // are, the address and the day.
  function figureCaption(st) {
    var legend = st.series.map(function (x, i) {
      return x.label + ': ' + nf(x.records.length) + ' counted' +
        (i === 0 && x.listed > x.records.length ? ' of ' + nf(x.listed) + ' listed' : '');
    });
    var lines = ['Origenality, ' + viewDescription(st.view) + '.'];
    if (st.series.length > 1) {
      var hidden = LANGS.filter(function (l) { return langOff[l.code]; }).map(function (l) { return l.label; });
      lines.push('Compared with ' + st.series[1].label + ', counted as the search field counts it' +
        (answersKeep() ? ', under the same answers' : '') + (hidden.length ? ', not shown: ' + hidden.join(', ') : '') + '.');
    }
    lines.push('Counted records are those classed core or partial. Records before 1950 share one column; ' +
      'undated records have their own.');
    var open = st.rows.filter(function (r) { return r.open; })[0];
    if (open) {
      lines.push('The ' + open.label + ' are open: build ' + DATA_VERSION + ' was generated on ' +
        ((META && META.generated) || buildYear()) + '.');
    }
    lines.push('A count of the harvested catalogues, not of the literature.');
    lines.push(viewUrl());
    lines.push('Accessed ' + isoDay(new Date()) + '.');
    return { title: 'Counted records by decade of publication', legend: legend, lines: lines };
  }
  function xmlText(s) {
    return String(s == null ? '' : s).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, ' ')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&apos;');
  }
  // lines of at most `max` characters, broken at spaces, or inside a word (an
  // address) longer than a line
  function wrapText(text, max) {
    var out = [], cur = '';
    String(text).split(/\s+/).filter(Boolean).forEach(function (w) {
      while (w.length > max) {
        if (cur) { out.push(cur); cur = ''; }
        out.push(w.slice(0, max));
        w = w.slice(max);
      }
      if (!w) return;
      if (!cur) cur = w;
      else if ((cur + ' ' + w).length > max) { out.push(cur); cur = w; } else cur += ' ' + w;
    });
    if (cur) out.push(cur);
    return out;
  }
  // A standalone SVG: no script, no font file, no external reference. The first
  // series is filled terracotta, the second hatched in ink with an ink outline,
  // so the two stay apart in black and white; every column carries its number.
  function figureSVG(st, cap) {
    var W = 760, pad = 34, font = "'EB Garamond', Georgia, serif", ink = '#23201B', paper = '#FFFDF8';
    var fills = ['#A03620', 'url(#or-hatch)'];
    var out = [], y = 46;
    out.push('<text x="' + pad + '" y="' + y + '" font-size="21" font-weight="500">' + xmlText(cap.title) + '</text>');
    y += 14;
    cap.legend.forEach(function (line, i) {
      y += 22;
      out.push('<rect x="' + pad + '" y="' + (y - 12) + '" width="15" height="15" fill="' + fills[i] +
        '" stroke="' + ink + '" stroke-width="1"/>');
      out.push('<text x="' + (pad + 24) + '" y="' + y + '" font-size="14">' + xmlText(line) + '</text>');
    });
    var top = y + 40, plotH = 210, base = top + plotH;
    var m = Math.max(1, st.rows.length), k = st.series.length, gw = (W - pad * 2) / m;
    var bw = Math.min(30, gw * (k === 1 ? 0.56 : 0.36)), gap = 3, max = 0;
    st.rows.forEach(function (r) { r.n.forEach(function (x) { max = Math.max(max, x); }); });
    st.rows.forEach(function (r, j) {
      var cx = pad + gw * (j + 0.5), left = cx - (k * bw + (k - 1) * gap) / 2;
      r.n.forEach(function (x, i) {
        var bx = left + i * (bw + gap), h = max ? x / max * plotH : 0;
        if (h > 0) {
          out.push('<rect x="' + bx.toFixed(1) + '" y="' + (base - h).toFixed(1) + '" width="' + bw.toFixed(1) +
            '" height="' + h.toFixed(1) + '" fill="' + fills[i] + '" stroke="' + ink + '" stroke-width="' + (i ? 1 : 0.6) + '"/>');
        }
        out.push('<text x="' + (bx + bw / 2).toFixed(1) + '" y="' + (base - h - 5).toFixed(1) +
          '" font-size="12" text-anchor="middle">' + x + '</text>');
      });
      out.push('<text x="' + cx.toFixed(1) + '" y="' + (base + 19) + '" font-size="12.5" text-anchor="middle">' +
        xmlText(r.label) + '</text>');
      if (r.open) {
        out.push('<text x="' + cx.toFixed(1) + '" y="' + (base + 34) +
          '" font-size="11" font-style="italic" text-anchor="middle">open</text>');
      }
    });
    out.push('<line x1="' + pad + '" y1="' + base + '" x2="' + (W - pad) + '" y2="' + base +
      '" stroke="' + ink + '" stroke-width="1"/>');
    y = base + 66;
    cap.lines.forEach(function (line) {
      wrapText(line, 104).forEach(function (part) {
        out.push('<text x="' + pad + '" y="' + y + '" font-size="12.5">' + xmlText(part) + '</text>');
        y += 17;
      });
    });
    var H = Math.ceil(y + 16);
    return '<?xml version="1.0" encoding="UTF-8"?>\n' +
      '<svg xmlns="http://www.w3.org/2000/svg" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H +
      '" role="img" aria-labelledby="or-title or-desc">\n' +
      '<title id="or-title">' + xmlText(cap.title) + '</title>\n' +
      '<desc id="or-desc">' + xmlText(sentences(cap.legend.concat(cap.lines))) + '</desc>\n' +
      '<defs><pattern id="or-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">' +
      '<rect width="6" height="6" fill="' + paper + '"/><rect width="2.4" height="6" fill="' + ink + '"/></pattern></defs>\n' +
      '<rect width="' + W + '" height="' + H + '" fill="' + paper + '"/>\n' +
      '<g font-family="' + font + '" fill="' + ink + '">\n' + out.join('\n') + '\n</g>\n</svg>\n';
  }
  // lines read aloud one after the other: each ends with a full stop
  function sentences(lines) {
    return lines.map(function (l) { l = String(l).trim(); return /[.!?]$/.test(l) ? l : l + '.'; }).join(' ');
  }
  var CSV_QUOTED = /[",\r\n]/;
  function csvCell(v) {
    var s = String(v == null ? '' : v);
    return CSV_QUOTED.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  // The same rows as the strip: the caption as # lines, a header naming each
  // series and its population, one row per decade, the total of each series.
  function figureCSV(st, cap) {
    // a caption line is one cell: quoted like any other, so its commas do not split it
    var lines = [cap.title].concat(cap.legend, cap.lines).map(function (l) {
      return csvCell('# ' + String(l).replace(/[\r\n]+/g, ' '));
    });
    lines.push(['decade'].concat(st.series.map(function (x) {
      return x.label + ': counted records (core and partial)';
    })).map(csvCell).join(','));
    st.rows.forEach(function (r) { lines.push([r.label].concat(r.n).map(csvCell).join(',')); });
    lines.push(['All counted'].concat(st.series.map(function (x) { return x.records.length; })).map(csvCell).join(','));
    return lines.join('\r\n') + '\r\n';
  }
  function figureFileName(st, ext) {
    var stem = st.series.map(function (x) { return x.query || x.label; }).join(' and ');
    var folded = CITE ? CITE.fold(stem) : norm(stem);
    var slug = folded.split(/[^a-z0-9]+/).filter(Boolean).join('-').slice(0, 60).replace(/-+$/, '') || 'view';
    return 'origenality-decades-' + slug + (DATA_VERSION ? '-' + DATA_VERSION : '') + '.' + ext;
  }
  function stripTool(kind, box) {
    if (!STRIP || STRIP.view !== VIEW) renderStrip();
    if (!STRIP || !box) return;
    var said = box.querySelector('.strip-said');
    var cap = figureCaption(STRIP);
    if (kind === 'csv') {
      var csvName = figureFileName(STRIP, 'csv');
      download(figureCSV(STRIP, cap), csvName, 'text/csv;charset=utf-8');
      if (said) said.textContent = 'Written to ' + csvName + '.';
      return;
    }
    var svg = figureSVG(STRIP, cap);
    if (kind === 'svg') {
      var svgName = figureFileName(STRIP, 'svg');
      download(svg, svgName, 'image/svg+xml;charset=utf-8');
      if (said) said.textContent = 'Written to ' + svgName + '.';
      return;
    }
    var done = function () { if (said) said.textContent = 'SVG copied.'; };
    var refused = function () { if (said) said.textContent = 'The browser refused the copy; the SVG file holds the same figure.'; };
    try { navigator.clipboard.writeText(svg).then(done, refused); } catch (e) { refused(); }
  }

  // the controls of the strip and of the author view, present and future
  panel.addEventListener('submit', function (ev) {
    var form = ev.target.closest ? ev.target.closest('.strip-cmp') : null;
    if (!form) return;
    ev.preventDefault();
    setCompare(form.querySelector('input').value);
  });
  panel.addEventListener('click', function (ev) {
    var t = ev.target.closest ? ev.target.closest('.strip-svg, .strip-csv, .strip-copy, .strip-drop, [data-a], [data-q]') : null;
    if (!t || !panel.contains(t)) return;
    if (t.hasAttribute('data-a')) {
      var a = authorIndex().byId[t.getAttribute('data-a')];
      if (a) { openAuthor(a); focusPanelHead(); }
    } else if (t.hasAttribute('data-q')) { searchFor(t.getAttribute('data-q')); focusPanelHead(); }
    else if (t.classList.contains('strip-drop')) setCompare('');
    else {
      stripTool(t.classList.contains('strip-svg') ? 'svg' : (t.classList.contains('strip-csv') ? 'csv' : 'copy'),
        t.closest('.strip'));
    }
  });

  /* ------------------------------------------------------------------ printing a view
     A view prints as a dossier: what it is (title, address, build, day), its
     figures and what they rest on, the citation, every record listed with its
     abstract unfolded and credited, then the catalogues the records come from.
     The list shows twenty records at a time, so it is filled to the end before
     printing and goes back to the reader's length afterwards. */
  var printShown = null;
  function prepareForPrint() {
    if (!panel.classList.contains('open')) return;
    if (printShown == null) printShown = shownCount;
    while (shownCount < currentList.length) appendMore();
    fillPrint();
  }
  function afterPrint() {
    if (printShown == null) return;
    var keep = printShown;
    printShown = null;
    var recs = pBody.querySelectorAll('.rec');
    for (var i = keep; i < recs.length; i++) recs[i].remove();
    shownCount = Math.min(keep, recs.length);
    placeMore();
  }
  function printView() {
    prepareForPrint();
    try { window.print(); } catch (e) { /* a frame that refuses to print keeps a working page */ }
  }
  addEventListener('beforeprint', prepareForPrint);
  addEventListener('afterprint', afterPrint);

  function buildYear() {
    var y = parseInt(String(DATA_VERSION || '').slice(0, 4), 10);
    return isFinite(y) ? y : null;
  }
  // a catalogue label as the English pages write it (build_summary_figures.py)
  function englishLabel(s) { return String(s).replace(/\s+[:\u2014\u2013]\s+/g, ', '); }
  // Counted records by decade of publication: before 1950 in one column, as the
  // questions group it; every decade from the first to the build's own, which
  // is marked open; the undated in a column of their own.
  // The columns every series of the strip shares: before 1950 in one column, as
  // the questions group it, when any series has a record there; every decade from
  // the first to the build's own, which is marked open; the undated in a column
  // of their own when any series has one. `series` is a list of record lists;
  // each row carries one count per series.
  function decadeRows(series, year) {
    var m = series.length, cols = {}, lo = null, hi = null, anyPre = false, anyNone = false;
    function zero() { var z = []; for (var s = 0; s < m; s++) z.push(0); return z; }
    var pre = zero(), none = zero();
    series.forEach(function (records, s) {
      records.forEach(function (p) {
        if (!CORE.isDated(p)) { none[s]++; anyNone = true; return; }
        var y = Number(p.year);
        if (y < 1950) { pre[s]++; anyPre = true; return; }
        var d = Math.floor(y / 10) * 10;
        (cols[d] || (cols[d] = zero()))[s]++;
        lo = lo == null ? d : Math.min(lo, d);
        hi = hi == null ? d : Math.max(hi, d);
      });
    });
    var now = year != null ? Math.floor(year / 10) * 10 : null;
    if (now != null) { lo = lo == null ? now : lo; hi = hi == null ? now : Math.max(hi, now); }
    var out = [];
    if (anyPre) out.push({ key: 'before-1950', label: 'Before 1950', n: pre, open: false });
    if (lo != null) {
      for (var d = lo; d <= hi; d += 10) {
        out.push({ key: String(d), label: d + 's', n: cols[d] || zero(), open: now != null && d === now });
      }
    }
    if (anyNone) out.push({ key: 'undated', label: 'Undated', n: none, open: false });
    return out;
  }
  // Counted records of one view by decade of publication, in those columns.
  function decadeTally(records, year) {
    return decadeRows([records], year).map(function (r) { return { label: r.label, n: r.n[0], open: r.open }; });
  }
  // the catalogues behind the records listed, by the label META.json gives them
  function sourcesHTML(v) {
    var by = {}, order = [];
    v.records.forEach(function (p) {
      var seen = {};
      (p.sourceIds || []).forEach(function (e) {
        if (!e || !e.source || seen[e.source]) return;
        seen[e.source] = 1;
        if (!by[e.source]) { by[e.source] = 0; order.push(e.source); }
        by[e.source]++;
      });
    });
    if (!order.length) return '';
    order.sort(function (a, b) { return by[b] - by[a] || (a < b ? -1 : 1); });
    var labels = {};
    ((META && META.sources_present) || []).forEach(function (s) { if (s && s.source) labels[s.source] = s.label; });
    var n = v.records.length;
    return '<p>Catalogues behind the ' + (n === 1 ? 'record' : nf(n) + ' records') + ' listed: ' +
      order.map(function (k) { return esc(englishLabel(labels[k] || sourceName(k))) + ', ' + nf(by[k]); }).join('; ') +
      '. A record merged from several catalogues counts under each. Every abstract printed names the database ' +
      'that wrote it. Licences and required attributions are set out at ' +
      esc(new URL('credits.html', location.href).href) + '.</p>';
  }
  function fillPrint() {
    var head = document.getElementById('p-print-head'), foot = document.getElementById('p-print-foot');
    if (!head || !foot) return;
    var v = VIEW;
    if (!v) { head.innerHTML = ''; foot.innerHTML = ''; return; }
    var rows = [['Address', viewUrl()], ['Build', DATA_VERSION || 'not read'], ['Printed', isoDay(new Date())]];
    head.innerHTML = '<p class="print-eyebrow">Origenality, Explorer dossier</p>' +
      (v.kind !== 'record' ? '<h1 class="print-title">' + esc(v.title) + '</h1>' : '') +
      '<dl class="print-meta">' + rows.map(function (r) {
        return '<dt>' + r[0] + '</dt><dd>' + esc(r[1]) + '</dd>';
      }).join('') + '</dl>';
    foot.innerHTML = sourcesHTML(v);
  }

  /* A closed panel holds buttons and links. Hiding it with aria-hidden while it
     kept them in the tab order sent the keyboard to a Close button no one could
     see. It is now inert while closed — with the tabindex sweep for a browser
     that does not know the attribute, and visibility:hidden in the stylesheet
     behind both — the focus moves into it when it opens, and returns to
     whatever opened it when it closes. */
  var INERT_OK = 'inert' in HTMLElement.prototype;
  var lastFocus = null;

  function sweepFocusable(off) {
    if (INERT_OK) return;
    panel.querySelectorAll('a[href],button,input,select,textarea,[tabindex]').forEach(function (el) {
      if (off) {
        if (el.getAttribute('data-ti') == null) {
          el.setAttribute('data-ti', el.getAttribute('tabindex') == null ? '' : el.getAttribute('tabindex'));
        }
        el.setAttribute('tabindex', '-1');
      } else {
        var v = el.getAttribute('data-ti');
        if (v == null) return;
        if (v === '') el.removeAttribute('tabindex'); else el.setAttribute('tabindex', v);
        el.removeAttribute('data-ti');
      }
    });
  }
  function setPanelInert(off) {
    if (off) panel.setAttribute('inert', ''); else panel.removeAttribute('inert');
    sweepFocusable(off);
  }
  setPanelInert(true);

  /* On a phone the sheet keeps its figure in the fixed head and lets everything
     that explains it (what it rests on, each term's reach, the tails, the
     zones) scroll with the list, so the records keep the room. On a wider
     screen the zones stay under the figure, in the head. */
  function placeZones() {
    var top = panel.querySelector('.panel-top');
    if (!top) return;
    if (MOBILE) {
      if (pZones.parentNode !== pBody || pBody.firstChild !== pZones) pBody.insertBefore(pZones, pBody.firstChild);
    } else if (pZones.parentNode !== top) {
      top.insertBefore(pZones, top.querySelector('.sep'));
    }
  }

  function openPanel() {
    placeZones();
    fillPrint();
    var was = panel.classList.contains('open');
    if (!was) {
      var from = document.activeElement;
      lastFocus = (from && from !== document.body && !panel.contains(from)) ? from : null;
    }
    document.body.classList.add('panel-open');
    panel.classList.add('open');
    if (veil) veil.setAttribute('aria-hidden', 'false');
    setPanelInert(false);
    if (!was) {
      panel.classList.toggle('by-pointer', byPointer);
      panel.focus({ preventScroll: true });
      settle();
    }
  }
  // a control that redraws the panel from inside it hands the focus to the
  // figure at its head, rather than letting it drop to the page
  function focusPanelHead() {
    if (!panel.classList.contains('open')) return;
    // no ring round the figure after a click; a key pressed afterwards restores it
    panel.classList.toggle('by-pointer', byPointer);
    pDensity.setAttribute('tabindex', '-1');
    pDensity.focus({ preventScroll: true });
  }
  // byReader: the reader closed the panel (the close button, Escape, the veil,
  // a pull, a tap on the empty map). When the view had added a history step and
  // closing returns to the address before it, Back is taken instead of writing
  // that address over the step, which would leave Back with nothing to undo.
  function closePanel(byReader) {
    var was = panel.classList.contains('open');
    var inside = was && panel.contains(document.activeElement);
    document.body.classList.remove('panel-open');
    panel.classList.remove('open');
    panel.style.transform = '';
    if (veil) veil.setAttribute('aria-hidden', 'true');
    setPanelInert(true);
    sel = null;
    selPub = null;
    selAuthor = null;
    shownAuthor = null;
    panel.classList.remove('one-work');
    if (was) {
      if (inside) {
        var back = (lastFocus && document.contains(lastFocus)) ? lastFocus : cv;
        back.focus({ preventScroll: true });
      }
      lastFocus = null;
      settle();
    }
    VIEW = null;
    if (byReader === true && stepBack()) return;
    syncHash(false);
  }
  function stepBack() {
    if (!addressReady || restoring) return false;
    var st = history.state;
    if (!st || st.view !== 1 || typeof st.from !== 'string') return false;
    if (canonical(st.from) !== canonical(addressOf(currentState()))) return false;
    if (canonical(location.hash) === canonical(st.from)) return false;
    lastHash = st.from;
    try { history.back(); } catch (e) { return false; }
    return true;
  }
  function frameCluster(c) {
    var R = Math.max(radiusOf(c), 10);
    var topPad = MOBILE ? 150 : 130;
    var askEl = document.querySelector('.ask');
    if (askEl) topPad = Math.max(MOBILE ? 120 : 100, askEl.getBoundingClientRect().bottom + 16);
    var botPad = MOBILE ? Math.round(H * 0.46) : 70;
    var sidePad = MOBILE ? 18 : 36;
    var right = MOBILE ? 0 : 420;
    var vw = Math.max(160, W - sidePad - right);
    var vh = Math.max(140, H - topPad - botPad);
    var s = clampS(Math.min(vw, vh) / (R * 2.2));
    var keep = Math.max(cam.s, tcam.s);
    tcam.s = keep + 0.02 < s ? s : clampS(keep);
    var cx = MOBILE ? W / 2 : sidePad + vw / 2;
    var cy = topPad + vh / 2;
    tcam.x = cx - c.px * tcam.s;
    tcam.y = cy - c.py * tcam.s;
  }
  function openCluster(c) {
    if (!c) return;
    userMoved();
    sel = c;
    selPub = null;
    selAuthor = null;
    renderPanel();
    frameCluster(c);
    invalidate();
    syncHash(true);
  }
  function openPub(p) {
    if (!p) return;
    userMoved();
    selPub = p;
    sel = null;
    selAuthor = null;
    renderPanel();
    invalidate();
    syncHash(true);
  }
  document.getElementById('panel-close').addEventListener('click', function () { closePanel(true); });
  /* The veil closes the sheet only for a gesture that began on the veil. A tap
     on the map opens the sheet on pointerup; the browser then sends that tap's
     compatibility click to the same point, where the veil has just appeared,
     and the sheet used to close in the frame it opened. */
  var veilDown = false, byPointer = false;
  // a panel opened by a tap or a click takes the focus without drawing the
  // keyboard frame round the whole sheet; a key pressed afterwards restores it
  addEventListener('pointerdown', function (e) { byPointer = true; veilDown = e.target === veil; }, true);
  addEventListener('keydown', function () { byPointer = false; panel.classList.remove('by-pointer'); }, true);
  if (veil) {
    veil.addEventListener('click', function () {
      if (veilDown) closePanel(true);
      veilDown = false;
    });
  }

  /* on a phone the sheet can be pulled down to close, unless the list itself
     is mid-scroll — that gesture belongs to the records */
  var dragY = null, dragDy = 0;
  function sheetDragging(el) {
    return MOBILE && el && (el === panel || (panel.contains(el) && !(pBody.contains(el) && pBody.scrollTop > 0)));
  }
  panel.addEventListener('touchstart', function (e) {
    if (!sheetDragging(e.target) || e.touches.length !== 1) { dragY = null; return; }
    dragY = e.touches[0].clientY; dragDy = 0;
  }, { passive: true });
  panel.addEventListener('touchmove', function (e) {
    if (dragY == null || e.touches.length !== 1) return;
    dragDy = e.touches[0].clientY - dragY;
    if (dragDy > 0) panel.style.transform = 'translateY(' + dragDy + 'px)';
  }, { passive: true });
  panel.addEventListener('touchend', function () {
    if (dragY == null) return;
    panel.style.transform = '';
    if (dragDy > 72) closePanel(true);
    dragY = null; dragDy = 0;
  });

  // one listener for every fold in the list, present and future
  pBody.addEventListener('click', function (ev) {
    var tool = ev.target.closest
      ? ev.target.closest('.cite-link, .cite-copy, .cite-export, .cite-print, .export-fmt, .export-copy') : null;
    if (tool) {
      var box = tool.closest('.cite');
      if (tool.classList.contains('cite-export')) toggleExport(tool);
      else if (tool.classList.contains('cite-print')) printView();
      else if (tool.classList.contains('export-fmt') || tool.classList.contains('export-copy')) {
        exportView(tool.getAttribute('data-format'), tool.classList.contains('export-copy'), box);
      } else copyView(tool.classList.contains('cite-copy'), box);
      return;
    }
    var button = ev.target.closest ? ev.target.closest('.abstract-more') : null;
    if (!button) return;
    var text = document.getElementById(button.getAttribute('aria-controls'));
    if (!text) return;
    var folded = text.classList.toggle('folded');
    button.setAttribute('aria-expanded', folded ? 'false' : 'true');
    button.textContent = folded ? 'Read the full abstract' : 'Fold the abstract';
  });

  /* ------------------------------------------------------------------ hover card */
  // A cluster is counted on the same population as everything else. The one
  // reservoir that holds what no figure counts states its own size instead of
  // reading zero: it is named as held aside, not as a measurement.
  function clusterCount(c) {
    var aside = c.id === OFF;
    var v = aside ? (matched ? c.mn : c.n) : (matched ? c.mdens : c.dens);
    var whole = aside ? c.n : c.dens;
    return { text: matched ? nf(v) + ' of ' + nf(whole) : nf(v), one: v === 1 && !matched, v: v };
  }
  function clusterExtra(c) {
    if (c.id === OFF) return 0;
    return matched ? Math.max(0, c.mn - c.mdens) : Math.max(0, c.n - c.dens);
  }

  /* ------------------------------------------------------------------ pointer */
  // touchTap: a touch tap on the field was handled on pointerup, so its
  // compatibility mouse events and click are cancelled on touchend
  var down = null, panning = false, pinch = null, touchTap = false;
  cv.addEventListener('pointerdown', function (e) {
    cv.setPointerCapture(e.pointerId);
    down = [e.clientX, e.clientY];
    panning = true; cv.classList.add('grabbing');
  });
  cv.addEventListener('pointermove', function (e) {
    if (panning && down) {
      var dx = e.clientX - down[0], dy = e.clientY - down[1];
      if (Math.abs(dx) + Math.abs(dy) > 2) {
        tcam.x += dx; tcam.y += dy; cam.x += dx; cam.y += dy;
        down = [e.clientX, e.clientY];
        hover = null; hoverPub = null; invalidate();
        return;
      }
    }
    var p = pickPub(e.clientX, e.clientY);
    var c = p ? null : pick(e.clientX, e.clientY);
    if (p !== hoverPub || c !== hover) invalidate();
    hoverPub = p; hover = c;
    cv.style.cursor = (p || c) ? 'pointer' : 'grab';
  });
  cv.addEventListener('pointerup', function (e) {
    var dist = down ? Math.hypot(e.clientX - down[0], e.clientY - down[1]) : 0;
    if (dist < 5) {
      touchTap = e.pointerType === 'touch';
      var p = pickPub(e.clientX, e.clientY);
      if (p) openPub(p);
      else {
        var c = pick(e.clientX, e.clientY);
        if (c) openCluster(c); else closePanel(true);
      }
    }
    panning = false; down = null; cv.classList.remove('grabbing');
  });
  cv.addEventListener('pointerleave', function () {
    hover = null; hoverPub = null;
    invalidate();
  });
  cv.addEventListener('wheel', function (e) {
    e.preventDefault();
    var f = Math.exp(-e.deltaY * 0.0014);
    var wx0 = (e.clientX - cam.x) / cam.s, wy0 = (e.clientY - cam.y) / cam.s;
    tcam.s = clampS(tcam.s * f);
    tcam.x = e.clientX - wx0 * tcam.s; tcam.y = e.clientY - wy0 * tcam.s;
    invalidate();
  }, { passive: false });
  function tdist(t) { return Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY); }
  cv.addEventListener('touchstart', function (e) {
    if (e.touches.length === 2) {
      panning = false;
      pinch = { d: tdist(e.touches), s: tcam.s, mx: (e.touches[0].clientX + e.touches[1].clientX) / 2,
        my: (e.touches[0].clientY + e.touches[1].clientY) / 2 };
    }
  }, { passive: true });
  cv.addEventListener('touchmove', function (e) {
    if (pinch && e.touches.length === 2) {
      e.preventDefault();
      var d = tdist(e.touches);
      var wx0 = (pinch.mx - cam.x) / cam.s, wy0 = (pinch.my - cam.y) / cam.s;
      tcam.s = clampS(pinch.s * d / pinch.d);
      tcam.x = pinch.mx - wx0 * tcam.s; tcam.y = pinch.my - wy0 * tcam.s;
      invalidate();
    }
  }, { passive: false });
  cv.addEventListener('touchend', function (e) {
    if (e.touches.length < 2) pinch = null;
    if (touchTap && e.cancelable) e.preventDefault();
    touchTap = false;
  }, { passive: false });

  // A turned phone or a dragged window edge gets its own field: the arrangement
  // is computed again once the movement stops, and the clouds travel to their
  // new places in one movement, or in none at all under reduced motion.
  function relayout() {
    if (!CLUSTERS.length) return;
    var saved = CLUSTERS;
    Object.keys(BUILT).forEach(function (m) {
      CLUSTERS = BUILT[m].clusters;
      layoutBase(BUILT[m].clusters, BUILT[m].links);
    });
    CLUSTERS = saved;
    if (!matched) CLUSTERS.forEach(function (c) { c.tx = c.bx; c.ty = c.by; });
    startTween(RM ? 1 : 620);
    fitView();
  }
  // A phone's field shows about thirty characters: the short text keeps one
  // example of a field, and the whole grammar stays one tap away under the field.
  var ASK_PLACEHOLDER = {
    wide: 'Describe your project, or name a field: author:crouzel',
    narrow: 'A topic, or author:crouzel'
  };
  function setAskPlaceholder() {
    var input = document.getElementById('ask-input');
    if (input) input.placeholder = MOBILE ? ASK_PLACEHOLDER.narrow : ASK_PLACEHOLDER.wide;
  }
  setAskPlaceholder();

  var rzTimer = null;
  function onViewportChange() {
    MOBILE = matchMedia('(max-width:760px)').matches;
    placeZones();
    setAskPlaceholder();
    var h = document.getElementById('hint');
    if (h) {
      h.textContent = MOBILE
        ? 'Pinch to zoom · tap a cluster, then a work'
        : 'Drag to move · scroll to zoom · click a cluster, then a work';
    }
    resize(); fitView(); measureLegend();
    if (rzTimer) clearTimeout(rzTimer);
    rzTimer = setTimeout(function () { rzTimer = null; relayout(); }, 220);
  }
  addEventListener('resize', onViewportChange);
  addEventListener('orientationchange', onViewportChange);
  // Escape folds one layer per press: the four questions or the field grammar
  // first, then the panel
  addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (wiz.classList.contains('open')) {
      var inWiz = wiz.contains(document.activeElement);
      closeWiz();
      if (inWiz) document.getElementById('wiz-open').focus();
      return;
    }
    if (advIsOpen()) { setAdvOpen(false); return; }
    // an open export fold is folded first, and its control keeps the focus
    var fold = panel.classList.contains('open') ? panel.querySelector('.cite-export[aria-expanded="true"]') : null;
    if (fold) { toggleExport(fold); fold.focus(); return; }
    closePanel(true);
  });

  // keyboard path across the map: arrows walk the clusters, Enter opens one
  var kbIndex = -1;
  cv.addEventListener('keydown', function (e) {
    var walkable = CLUSTERS.filter(function (c) { return c.ta > 0.2; })
      .sort(function (a, b) { return a.px - b.px || a.py - b.py; });
    if (!walkable.length) return;
    var step = 0;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') step = 1;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') step = -1;
    else if (e.key === 'Enter' || e.key === ' ') {
      if (kbIndex >= 0) { e.preventDefault(); openCluster(walkable[kbIndex % walkable.length]); }
      return;
    } else return;
    e.preventDefault();
    kbIndex = (kbIndex + step + walkable.length) % walkable.length;
    var c = walkable[kbIndex];
    hover = c;
    var kc = clusterCount(c), kx = clusterExtra(c);
    document.getElementById('live-cluster').textContent =
      c.label + ', ' + kc.text + ' works' +
      (kx ? ', ' + kx + ' mentioned only' : '');
    invalidate();
  });
  cv.addEventListener('blur', function () { hover = null; kbIndex = -1; invalidate(); });

  /* ------------------------------------------------------------------ chrome */
  function boot() {
    if (MOBILE) {
      var h = document.getElementById('hint');
      if (h) h.textContent = 'Pinch to zoom · tap a cluster, then a work';
    }
    // legend
    var lg = document.getElementById('legend');
    // the same population as the Observatory: core and partial
    var byLang = {};
    PUBS.forEach(function (p) { if (counts(p)) byLang[p.lkey] = (byLang[p.lkey] || 0) + 1; });
    LANGS.forEach(function (l) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'lg';
      b.dataset.code = l.code;
      b.setAttribute('aria-pressed', 'true');
      b.innerHTML = '<i style="background:' + l.col + '"></i>' + esc(l.label) +
        '<span class="n">' + nf(byLang[l.code] || 0) + '</span>';
      b.addEventListener('click', function () {
        userMoved();
        setLangOff(l.code, !langOff[l.code]);
        // the state line counts hidden records too, so it has to be recomputed,
        // and an open panel is rebuilt from the same answer (sel and selPub kept)
        if (matched) applyMatch();
        if (panel.classList.contains('open')) renderPanel();
        invalidate();
        syncHash(false);
      });
      lg.appendChild(b);
    });

    // grouping axis
    document.getElementById('mode-theme').addEventListener('click', function () { setMode('theme'); });
    document.getElementById('mode-work').addEventListener('click', function () { setMode('work'); });

    // search
    var input = document.getElementById('ask-input');
    var fieldEl = document.getElementById('ask-field');
    var clear = document.getElementById('ask-clear');
    function runSearch() {
      query = input.value;
      linkBuild = null;
      fieldEl.classList.toggle('filled', !!query.trim());
      applyMatch(true);
    }
    document.getElementById('ask-go').addEventListener('click', runSearch);
    var advBtn = document.getElementById('adv-open');
    if (advBtn) advBtn.addEventListener('click', function () { setAdvOpen(!advIsOpen()); });
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') runSearch(); });
    input.addEventListener('input', function () {
      fieldEl.classList.toggle('filled', !!input.value.trim());
    });
    clear.addEventListener('click', function () {
      input.value = ''; query = ''; linkBuild = null; CMP = ''; fieldEl.classList.remove('filled');
      applyMatch(false); closePanel();
    });

    document.getElementById('reset').addEventListener('click', function () {
      query = ''; input.value = ''; linkBuild = null; CMP = ''; fieldEl.classList.remove('filled');
      wizAns = { work: [], approach: [], decade: [], lang: [] };
      LANGS.forEach(function (l) { setLangOff(l.code, false); });
      closeWiz();
      applyMatch(false); closePanel();
    });

    var keyTog = document.getElementById('key-toggle');
    if (keyTog) {
      keyTog.addEventListener('click', function () {
        setKeyOpen(!document.getElementById('legend-wrap').classList.contains('open'));
      });
    }
    measureLegend();

    if (window.visualViewport) {
      visualViewport.addEventListener('resize', function () {
        if (!MOBILE) return;
        var ask = document.querySelector('.ask');
        if (!ask) return;
        var kb = innerHeight - visualViewport.height > 80;
        ask.style.top = kb ? (visualViewport.offsetTop + 8) + 'px' : '';
      });
    }

    OPTS = buildOptions();
    initWizard();
    applyMatch(false);
    initAddress();
  }

  function setMode(mode) {
    if (mode === MODE) return;
    userMoved();
    useMode(mode, true);
    document.getElementById('mode-theme').setAttribute('aria-pressed', mode === 'theme' ? 'true' : 'false');
    document.getElementById('mode-work').setAttribute('aria-pressed', mode === 'work' ? 'true' : 'false');
    kbIndex = -1;
    closePanel();
    applyMatch(false);
  }
  function setLangOff(code, off) {
    langOff[code] = !!off;
    var b = document.querySelector('#legend .lg[data-code="' + code + '"]');
    if (!b) return;
    b.classList.toggle('off', !!off);
    b.setAttribute('aria-pressed', off ? 'false' : 'true');
  }

  /* ------------------------------------------------------------------ addresses
   * Every view has an address in the fragment, never in the query string, so
   * nothing reaches the server's routing or logs and a fragment survives the
   * redirect from a short address:
   *
   *   #q=<query>&m=work&c=<cluster id>&r=<record>&a=<author id>&w=<work,...>
   *    &ap=<approach,...>&d=<decade,...>&l=<language,...>&off=<hidden colour keys>
   *    &cmp=<compared query>&b=<build>
   *
   * q the text searched; m the grouping, written only when it is not theme;
   * c a cluster by its id (dom:<domain key>, w:<work key>, or a reservoir:
   * __off, __nothe, __nowork), never by its position in the array; r a record
   * by its first source identifier, source:id, which survives a rebuild that
   * rehashes the Origenality ID (a bare catalogue number or an OR ID resolve
   * too); a an author by the id of its node in graph.json (a:crouzel-henri); w,
   * ap, d, l the answers to the four questions, by option id; off the languages
   * switched off in the key; cmp the query the decade strip compares the view
   * with; b the build the link was made on. A record wins over an author, and an
   * author over a cluster. Keys
   * this version does not know are ignored, so a later one may add some.
   * Opening a cluster or a record adds a step to the history, so Back closes
   * it; every other change replaces the current address.
   */
  var LIST_KEYS = { w: 1, ap: 1, d: 1, l: 1, off: 1 };
  var addressReady = false, restoring = false, lastHash = '', RECORD_KEYS = null;

  function hashValue(v) {
    return encodeURIComponent(v).replace(/%3A/gi, ':').replace(/%2C/gi, ',')
      .replace(/%2F/gi, '/').replace(/%20/g, '+');
  }
  function serializeState(s) {
    var parts = [];
    function put(key, v) { if (v != null && v !== '') parts.push(key + '=' + hashValue(String(v))); }
    put('q', s.q);
    if (s.m && s.m !== 'theme') put('m', s.m);
    put('c', s.c);
    put('r', s.r);
    put('a', s.a);
    ['w', 'ap', 'd', 'l', 'off'].forEach(function (key) {
      if (s[key] && s[key].length) put(key, s[key].join(','));
    });
    put('cmp', s.cmp);
    put('b', s.b);
    return parts.join('&');
  }
  function parseHash(h) {
    var s = { q: '', m: 'theme', c: null, r: null, a: null, w: [], ap: [], d: [], l: [], off: [], cmp: '', b: null };
    String(h || '').replace(/^#/, '').split('&').forEach(function (part) {
      if (!part) return;
      var at = part.indexOf('=');
      var key = at < 0 ? part : part.slice(0, at);
      var v = at < 0 ? '' : part.slice(at + 1);
      try { v = decodeURIComponent(v.replace(/\+/g, ' ')); } catch (e) { return; }
      if (key === 'q') s.q = v;
      else if (key === 'cmp') s.cmp = v;
      else if (key === 'm') s.m = v === 'work' ? 'work' : 'theme';
      else if (key === 'c' || key === 'r' || key === 'a' || key === 'b') s[key] = v || null;
      else if (LIST_KEYS[key] === 1) {
        s[key] = v.split(',').filter(function (x, i, all) { return x && all.indexOf(x) === i; });
      }
    });
    return s;
  }
  function viewIsDefault(s) {
    return !s.q && s.m !== 'work' && !s.c && !s.r && !s.a && !s.w.length && !s.ap.length &&
      !s.d.length && !s.l.length && !s.off.length && !s.cmp;
  }
  // the address of a view: empty for the map at rest, so the plain page keeps
  // its plain address
  function addressOf(s) { return viewIsDefault(s) ? '' : serializeState(s); }

  // a record by its first source identifier; an Origenality ID when it has none
  function recordKey(p) {
    var e = (p.sourceIds || [])[0];
    return e && e.source && e.id != null && e.id !== '' ? e.source + ':' + e.id : p.ppn;
  }
  function recordKeys(records) {
    var m = { pair: Object.create(null), id: Object.create(null), ppn: Object.create(null) };
    records.forEach(function (p) {
      if (p.ppn) m.ppn[p.ppn] = p;
      (p.sourceIds || []).forEach(function (e) {
        if (e.id == null || e.id === '') return;
        var id = String(e.id);
        m.pair[e.source + ':' + id] = p;
        // a catalogue number two records share names neither without its source
        m.id[id] = (m.id[id] && m.id[id] !== p) ? false : p;
      });
    });
    return m;
  }
  function resolveRecord(v, keys) {
    v = String(v == null ? '' : v).trim();
    if (!v) return null;
    if (v.indexOf('p:') === 0) v = v.slice(2);
    return keys.pair[v] || keys.ppn[v] || keys.id[v] || null;
  }

  function currentState() {
    var s = {
      q: query.trim(), m: MODE, c: null, r: null, a: null,
      w: wizAns.work.slice(), ap: wizAns.approach.slice(), d: wizAns.decade.slice(), l: wizAns.lang.slice(),
      off: LANGS.filter(function (l) { return langOff[l.code]; }).map(function (l) { return l.code; }),
      cmp: CMP, b: DATA_VERSION
    };
    if (selPub) s.r = recordKey(selPub);
    else if (selAuthor) s.a = selAuthor.id;
    else if (sel) s.c = sel.id;
    return s;
  }
  function canonical(h) {
    var s = parseHash(h);
    s.b = null;
    return addressOf(s);
  }
  function syncHash(push) {
    if (!addressReady || restoring) return;
    var h = addressOf(currentState());
    lastHash = h;
    if (h === location.hash.replace(/^#/, '')) return;
    var url = h ? '#' + h : location.pathname + location.search;
    try {
      // the step remembers the address it was taken from (stepBack)
      if (push) history.pushState({ view: 1, from: location.hash.replace(/^#/, '') }, '', url);
      else history.replaceState(history.state, '', url);
    } catch (e) { /* a frame that refuses history keeps a working page */ }
  }

  function knownAnswers(kind, ids) {
    return ids.filter(function (id) {
      return (OPTS[kind] || []).some(function (o) { return o.id === id; });
    });
  }
  function showMissing(kind, id) {
    sel = null; selPub = null; selAuthor = null; shownAuthor = null; VIEW = null; STRIP = null;
    panel.classList.remove('one-work');
    pSubject.textContent = '';
    pDensity.innerHTML = '<span class="words">This ' + kind + ' is not in build ' + esc(DATA_VERSION) + '</span>';
    pAlt.textContent = kind === 'record'
      ? 'The link names “' + id + '”. A record is found by its catalogue number, by source and ' +
        'number, or by its Origenality ID, and none of these matches a record of this build.'
      : 'The link names “' + id + '”, which is not ' + (kind === 'author' ? 'an author' : 'a cluster') + ' of this build.';
    pZones.innerHTML = '';
    currentList = []; shownCount = 0;
    pBody.innerHTML = '';
    openPanel();
  }
  // Replays an address with the functions a reader's clicks call. Returns false
  // when the address names a record or a cluster this build does not hold.
  function applyState(s) {
    var missing = null;
    restoring = true;
    try {
      linkBuild = s.b && s.b !== DATA_VERSION ? s.b : null;
      var mode = s.m;
      if (s.c && (s.c.indexOf('w:') === 0 || s.c === NO_WORK)) mode = 'work';
      else if (s.c && (s.c.indexOf('dom:') === 0 || s.c === NO_THEME)) mode = 'theme';
      if (mode !== MODE) setMode(mode);
      LANGS.forEach(function (l) { setLangOff(l.code, s.off.indexOf(l.code) >= 0); });
      wizAns = {
        work: knownAnswers('work', s.w), approach: knownAnswers('approach', s.ap),
        decade: knownAnswers('decade', s.d), lang: knownAnswers('lang', s.l)
      };
      if (wiz.classList.contains('open')) paintWiz();
      query = s.q;
      document.getElementById('ask-input').value = s.q;
      document.getElementById('ask-field').classList.toggle('filled', !!s.q.trim());
      CMP = s.cmp || '';
      var pub = null, cluster = null, author = null;
      if (s.r) {
        pub = resolveRecord(s.r, RECORD_KEYS || (RECORD_KEYS = recordKeys(PUBS)));
        if (!pub) missing = ['record', s.r];
      } else if (s.a) {
        author = authorIndex().byId[s.a] || null;
        if (!author) missing = ['author', s.a];
      } else if (s.c) {
        // a reservoir named in a link is drawn on the map
        if (TAIL_LABEL[s.c]) folded[s.c] = false;
        cluster = CLUSTERS.filter(function (c) { return c.id === s.c; })[0] || null;
        if (!cluster) missing = ['cluster', s.c];
      }
      var answered = !!s.q.trim() || QUESTIONS.some(function (q) { return wizAns[q.kind].length > 0; });
      applyMatch(answered && !pub && !cluster && !author && !missing);
      if (pub) openPub(pub);
      else if (author) openAuthor(author);
      else if (cluster) openCluster(cluster);
      else if (missing) showMissing(missing[0], missing[1]);
      else if (!answered) closePanel();
    } finally {
      restoring = false;
    }
    return !missing;
  }
  function onAddress() {
    var h = location.hash.replace(/^#/, '');
    // an anchor such as the skip link's #ask-input is not a view
    if (h && h.indexOf('=') < 0) return;
    if (canonical(h) === canonical(lastHash)) return;
    lastHash = h;
    applyState(parseHash(h));
  }
  function initAddress() {
    var h = location.hash.replace(/^#/, '');
    addressReady = true;
    if (h && h.indexOf('=') >= 0) {
      lastHash = h;
      // a link that names what this build lacks keeps its address, so the
      // reader can see what it asked for
      if (applyState(parseHash(h))) syncHash(false);
    }
    addEventListener('popstate', onAddress);
    addEventListener('hashchange', onAddress);
  }

  /* ------------------------------------------------------------------ folds */
  // The four questions and the field grammar share the column under the search
  // field: opening one closes the other, so the column stays on the screen.
  function advIsOpen() {
    var adv = document.getElementById('adv');
    return !!adv && !adv.hasAttribute('hidden');
  }
  function setAdvOpen(on) {
    var adv = document.getElementById('adv'), btn = document.getElementById('adv-open');
    if (!adv || !btn) return;
    if (on && wiz.classList.contains('open')) closeWiz();
    if (on) adv.removeAttribute('hidden'); else adv.setAttribute('hidden', '');
    btn.setAttribute('aria-expanded', on ? 'true' : 'false');
    btn.textContent = on ? 'hide the fields' : 'or search by field';
  }

  /* ------------------------------------------------------------------ wizard */
  var wiz = document.getElementById('wiz'), step = 0;
  function initWizard() {
    document.getElementById('wiz-open').addEventListener('click', function () {
      if (wiz.classList.contains('open')) { closeWiz(); } else { step = 0; openWiz(); }
    });
    document.getElementById('wiz-skip').addEventListener('click', function () { closeWiz(); });
    document.getElementById('wiz-back').addEventListener('click', function () {
      if (step > 0) { step--; paintWiz(); }
    });
    document.getElementById('wiz-next').addEventListener('click', function () {
      if (step < QUESTIONS.length - 1) { step++; paintWiz(); }
      else { closeWiz(); applyMatch(true); }
    });
  }
  function openWiz() {
    if (advIsOpen()) setAdvOpen(false);
    wiz.classList.add('open');
    document.body.classList.add('wiz-open');
    setKeyOpen(false);
    settle();
    document.getElementById('wiz-open').textContent = 'close the questions';
    paintWiz();
  }
  function closeWiz() {
    wiz.classList.remove('open');
    document.body.classList.remove('wiz-open');
    settle();
    document.getElementById('wiz-open').textContent = 'or answer four questions';
  }
  function paintWiz() {
    var q = QUESTIONS[step];
    document.getElementById('wiz-q').textContent = q.q;
    var extra = mentionedOnly(q.kind);
    document.getElementById('wiz-note').textContent = q.note +
      ' Each number counts the works where Origen is the subject or holds a section of the argument.' +
      (extra ? ' ' + nf(extra) + (extra === 1
        ? ' further work is mentioned only and is listed below the count.'
        : ' further works are mentioned only and are listed below the count.') : '');
    document.getElementById('wiz-step').textContent = 'Question ' + (step + 1) + ' of ' + QUESTIONS.length;
    document.getElementById('wiz-back').disabled = step === 0;
    document.getElementById('wiz-next').textContent =
      step === QUESTIONS.length - 1 ? 'Show the neighbourhood' : 'Next';
    var dots = document.getElementById('wiz-dots').children;
    for (var i = 0; i < dots.length; i++) dots[i].classList.toggle('on', i <= step);

    var box = document.getElementById('wiz-chips');
    box.innerHTML = '';
    OPTS[q.kind].forEach(function (o) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'chip';
      var on = wizAns[q.kind].indexOf(o.id) >= 0;
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      b.innerHTML = esc(o.label) + '<span class="n">' + nf(o.n) + '</span>';
      b.addEventListener('click', function () {
        var arr = wizAns[q.kind], k = arr.indexOf(o.id);
        userMoved();
        if (k >= 0) arr.splice(k, 1); else arr.push(o.id);
        b.setAttribute('aria-pressed', arr.indexOf(o.id) >= 0 ? 'true' : 'false');
        applyMatch(false);
      });
      box.appendChild(b);
    });
    var none = document.createElement('button');
    none.type = 'button'; none.className = 'chip none';
    none.setAttribute('aria-pressed', wizAns[q.kind].length ? 'false' : 'true');
    none.innerHTML = 'No preference';
    none.addEventListener('click', function () {
      userMoved();
      wizAns[q.kind] = [];
      paintWiz(); applyMatch(false);
    });
    var nbox = document.getElementById('wiz-none');
    nbox.innerHTML = '';
    nbox.appendChild(none);
  }
})();
