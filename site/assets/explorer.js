/* Origenality — Explorer, direction C.
   Clusters drawn as particle clouds on a cream field. One particle = one
   publication, tinted by its language of publication. The clusters are named
   from the controlled vocabulary: theme domains and their leaves, or the works
   of Origen. Romain Girardi, 2026. No external requests, no third party code. */
(function () {
  'use strict';

  var RM = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var MOBILE = matchMedia('(max-width:760px)').matches;

  /* ------------------------------------------------------------------ palette */
  var LANGS = [
    { code: 'eng', label: 'English', col: '#1F5674' },
    { code: 'ger', label: 'German', col: '#A8371F' },
    { code: 'ita', label: 'Italian', col: '#8A6A12' },
    { code: 'fre', label: 'French', col: '#4F7350' },
    { code: 'spa', label: 'Spanish', col: '#B15A17' },
    { code: 'oth', label: 'Other or none', col: '#78766F' }
  ];
  var LCOL = {}, LLAB = {};
  LANGS.forEach(function (l) { LCOL[l.code] = l.col; LLAB[l.code] = l.label; });
  function lkey(c) { return LCOL[c] ? c : 'oth'; }

  var INK = '#23201B', STONE = '#6A6353', ACCENT = '#A03620', PAPER = '#F7F2E6';

  /* ------------------------------------------------------------------ utilities */
  function norm(s) {
    return (s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  }
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
    'isidore': 'ISIDORE', 'thesesfr': 'theses.fr', 'dialnet': 'Dialnet', 'sbn': 'SBN'
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
  var GAP_PUB = 0.9, GAP_SUB = 3.2;
  // the gap between two clouds follows their own size, so a field of small
  // clusters stays gathered instead of drifting apart
  function gapOf(a, b) {
    var ra = a.mr == null ? a.r : a.mr, rb = b.mr == null ? b.r : b.mr;
    return Math.max(20, Math.min(46, (ra + rb) * 0.5));
  }
  var langOff = {};                       // language code -> hidden
  var sel = null, hover = null, query = '';
  var wizAns = { work: [], approach: [], decade: [], lang: [] };
  var matched = null;                     // Set of publication indices, or null for "everything"
  var matchLabel = '', hitDepth = 0, tokCount = 0;
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
  var W = 0, H = 0, DPR = Math.min(devicePixelRatio || 1, 2);

  function resize() {
    W = innerWidth; H = innerHeight;
    cv.width = W * DPR; cv.height = H * DPR;
    cv.style.width = W + 'px'; cv.style.height = H + 'px';
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    invalidate();
  }
  resize();

  /* ------------------------------------------------------------------ load */
  Promise.all([
    fetch('../data/graph.json').then(function (r) { return r.json(); }),
    fetch('assets/weights.json').then(function (r) { return r.json(); }).catch(function () { return null; }),
    fetch('assets/semantic.json').then(function (r) { return r.json(); }),
    // the summaries: a record reads better with one, and the reader who
    // searches expects their words to count. Missing, the map still works.
    fetch('../data/abstracts.json').then(function (r) { return r.json(); }).catch(function () { return null; })
  ]).then(function (r) {
    WEIGHTS = r[1]; SEM = r[2]; ABS = r[3]; build(r[0]);
  }).catch(function (e) {
    document.getElementById('ask-state').textContent = 'The map could not be loaded.';
    console.error(e);
  });

  /* ------------------------------------------------------------------ model */
  function build(g) {
    DATA = g;
    var N = g.nodes, E = g.edges;

    var pubSub = [], pubAut = [], pubIn = [];
    for (var i = 0; i < N.length; i++) { pubSub.push(null); pubAut.push(null); pubIn.push(null); }
    E.forEach(function (e) {
      if (e.r === 'sub') { (pubSub[e.s] || (pubSub[e.s] = [])).push(e.t); }
      else if (e.r === 'aut') { (pubAut[e.s] || (pubAut[e.s] = [])).push(e.t); }
      else { (pubIn[e.s] || (pubIn[e.s] = [])).push(e.t); }
    });

    N.forEach(function (n, i) {
      if (n.k !== 'pub') return;
      var subs = pubSub[i] || [], auts = pubAut[i] || [], cont = (pubIn[i] || [])[0];
      var subLabels = subs.map(function (t) { return N[t].label; });
      var autLabels = auts.map(function (t) { return N[t].label; });
      var wr = (WEIGHTS && WEIGHTS.w && WEIGHTS.w[n.ppn]) || null;
      var wv = wr ? wr.w : 0.5;
      var tier = 0;
      while (tier < TIER_CUT.length && wv > TIER_CUT[tier]) tier++;

      var tag = (SEM.byPpn && SEM.byPpn[n.ppn]) || { r: 'none' };
      var themes = (tag.t || []).filter(function (t) { return SEM.themes[t]; });
      var works = (tag.w || []).filter(function (w) { return SEM.works[w] && w !== 'unspecified'; });
      var appr = (tag.a || []).filter(function (a) { return SEM.approaches[a]; });
      var doms = [], seenDom = {};
      themes.forEach(function (t) {
        var d = SEM.themes[t].domain;
        if (!seenDom[d]) { seenDom[d] = 1; doms.push(d); }
      });

      var semWords = [];
      themes.forEach(function (t) { semWords.push(SEM.themes[t].label, altLine(SEM.themes[t])); });
      doms.forEach(function (d) { semWords.push(SEM.domains[d].label, altLine(SEM.domains[d])); });
      works.forEach(function (w) { semWords.push(SEM.works[w].label); });
      appr.forEach(function (a) { semWords.push(SEM.approaches[a].label); });

      var ab = (ABS && ABS.byPpn && ABS.byPpn[n.ppn]) || null;

      PUBS.push({
        i: PUBS.length, title: n.title, year: n.year, lang: lkey(n.lang), rawlang: n.lang || '',
        w: wv, tier: tier, r: TIERS[tier], wr: wr,
        type: n.type, ppn: n.ppn, doi: n.doi || '',
        url: n.url || '', src: (n.src && n.src[0]) || '',
        publisher: n.pub || '', isbn: n.isbn || '',
        authors: autLabels, container: cont != null ? N[cont].label : '',
        rel: tag.r || 'none', review: !!tag.n,
        themes: themes, doms: doms, works: works, appr: appr,
        dens: tag.r === 'core' || tag.r === 'partial',
        o: {}, lobeName: null, ab: ab,
        hay: norm([n.title, autLabels.join(' '), subLabels.join(' '), cont != null ? N[cont].label : '',
          n.year || '', LLAB[lkey(n.lang)], semWords.join(' '), ab ? ab.t : ''].join(' '))
      });
    });

    buildMode('theme');
    useMode('theme', false);
    boot();
    invalidate();
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
        if (p.dens || c.id === OFF) c.mix[p.lang] = (c.mix[p.lang] || 0) + 1;
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
    tcam.s = Math.max(0.18, s);
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
      return option(l.code, l.label, function (p) { return p.lang === l.code; });
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
  var STOP = ('the and for with from that this was are its our not but all any how who '
    + 'des les une dans pour sur avec par aux ses est comme entre chez '
    + 'der die das und von den dem ein eine des mit auf ist als bei aus '
    + 'che del della dei con per una nel nella sul '
    + 'los las una del por con para sobre entre').split(' ');
  var STOPSET = {}; STOP.forEach(function (w) { STOPSET[w] = 1; });
  function tokens(q) {
    return norm(q).split(/[^0-9a-z']+/).filter(function (w) {
      return w.length > 2 && !STOPSET[w];
    });
  }
  function chosen(kind) {
    return wizAns[kind].map(function (id) {
      for (var i = 0; i < OPTS[kind].length; i++) if (OPTS[kind][i].id === id) return OPTS[kind][i];
      return null;
    }).filter(Boolean);
  }

  function computeMatch() {
    var toks = tokens(query);
    var picked = {}, anyPick = false;
    QUESTIONS.forEach(function (q) {
      picked[q.kind] = chosen(q.kind);
      if (picked[q.kind].length) anyPick = true;
    });
    if (!toks.length && !anyPick) { matched = null; matchLabel = ''; return; }

    var set = new Set(), scores = {};
    PUBS.forEach(function (p) {
      for (var k = 0; k < QUESTIONS.length; k++) {
        var opts = picked[QUESTIONS[k].kind];
        if (!opts.length) continue;
        var ok = false;
        for (var o = 0; o < opts.length; o++) if (opts[o].test(p)) { ok = true; break; }
        if (!ok) return;
      }
      var sc = 1;
      if (toks.length) {
        sc = 0;
        for (var t = 0; t < toks.length; t++) if (p.hay.indexOf(toks[t]) >= 0) sc++;
        if (!sc) return;
      }
      scores[p.i] = sc;
      set.add(p.i);
    });
    // a described project is read as a conjunction as far as the corpus allows:
    // keep the most demanding threshold that still leaves a usable neighbourhood
    hitDepth = 0;
    if (toks.length > 1 && set.size) {
      for (var need = toks.length; need >= 2; need--) {
        var strict = new Set();
        set.forEach(function (i) { if (scores[i] >= need) strict.add(i); });
        if (strict.size >= 10) { set = strict; hitDepth = need; break; }
      }
      if (!hitDepth) hitDepth = 1;
    } else if (toks.length === 1) hitDepth = 1;
    tokCount = toks.length;
    matched = set;
    window.__scores = scores;

    var bits = [];
    if (query.trim()) bits.push('“' + query.trim() + '”');
    QUESTIONS.forEach(function (q) {
      if (picked[q.kind].length) {
        bits.push(picked[q.kind].map(function (o) { return o.label; }).join(', '));
      }
    });
    matchLabel = bits.join(' · ');
  }

  function visiblePub(p) { return !langOff[p.lang]; }

  function applyMatch(openPanel) {
    computeMatch();
    CLUSTERS.forEach(function (c) {
      c.mn = 0; c.mdens = 0;
      if (!matched) { c.mn = c.n; c.mdens = c.dens; return; }
      c.pubs.forEach(function (p) {
        if (matched.has(p.i)) { c.mn++; if (p.dens) c.mdens++; }
      });
    });
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
    // the state line counts what every other figure counts, and says what else
    // the answer returns
    var hit = 0, extra = 0;
    if (matched) {
      PUBS.forEach(function (p) {
        if (!matched.has(p.i)) return;
        if (counts(p)) hit++; else extra++;
      });
    }
    document.getElementById('ask-state').textContent = matched
      ? nf(hit) + (hit === 1 ? ' work matches' : ' works match')
        + (tokCount > 1 && hitDepth ? ', on ' + hitDepth + ' of your ' + tokCount + ' terms' : '')
        + (extra ? ' · ' + nf(extra) + ' more listed, mentioned only or held aside' : '')
      : '';
    renderHeld();
    if (openPanel) { sel = null; renderPanel(); }
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
  // names is measured against it rather than against an absolute zoom
  var restScale = 1;
  function leafFade() { return Math.min(1, Math.max(0, (cam.s / restScale - 0.97) / 0.26)); }

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

    // links, drawn as faint dotted trails
    var links = window.__links || [];
    ctx.fillStyle = hexA('#A2916D', 0.55);
    links.forEach(function (l) {
      var a = CLUSTERS[l.a], b = CLUSTERS[l.b];
      if (!a || !b) return;
      var al = Math.min(a.a, b.a); if (al < 0.14) return;
      var ax = wx(a.px), ay = wy(a.py), bx = wx(b.px), by = wy(b.py);
      var dx = bx - ax, dy = by - ay, len = Math.hypot(dx, dy);
      if (len < 8 || len > Math.max(W, H) * 2.2) return;
      var mx = (ax + bx) / 2 - dy * 0.055, my = (ay + by) / 2 + dx * 0.055;
      var steps = Math.max(6, Math.min(54, Math.round(len / 11)));
      ctx.globalAlpha = 0.62 * al;
      for (var i = 1; i < steps; i++) {
        var u = i / steps, iu = 1 - u;
        var px = iu * iu * ax + 2 * iu * u * mx + u * u * bx;
        var py = iu * iu * ay + 2 * iu * u * my + u * u * by;
        ctx.fillRect(px - 0.75, py - 0.75, 1.5, 1.5);
      }
    });
    ctx.globalAlpha = 1;

    drawHalos();

    // publication discs, packed without overlap, batched per language and alpha
    var buckets = {};
    LANGS.forEach(function (l) { buckets[l.code] = {}; });
    var hl = hover || sel;
    CLUSTERS.forEach(function (c) {
      if (c.a < 0.03) return;
      var R = radiusOf(c) * cam.s;
      var cxp = wx(c.px), cyp = wy(c.py);
      if (cxp < -R - 80 || cxp > W + R + 80 || cyp < -R - 80 || cyp > H + R + 80) return;
      var lit = hl === c;
      var base = c.a * (lit ? 1 : (hl ? 0.45 : 1)) * (c.kind === 'tail' ? 0.55 : 1);
      c.pubs.forEach(function (p) {
        if (!visiblePub(p)) return;
        var a = base;
        if (matched && !matched.has(p.i)) a *= animating ? 0.1 : 0;
        if (a < 0.05) return;
        var key = Math.round(a * 8);
        var g = buckets[p.lang][key] || (buckets[p.lang][key] = []);
        var ox = p.cox == null ? p.ox : p.cox, oy = p.coy == null ? p.oy : p.coy;
        g.push(cxp + ox * cam.s, cyp + oy * cam.s, Math.max(0.6, p.r * cam.s));
      });
    });
    LANGS.forEach(function (l) {
      var byA = buckets[l.code];
      Object.keys(byA).forEach(function (key) {
        var g = byA[key];
        ctx.fillStyle = hexA(l.col, Math.min(0.94, (+key) / 8 * 0.94));
        ctx.beginPath();
        for (var j = 0; j < g.length; j += 3) {
          ctx.moveTo(g[j] + g[j + 2], g[j + 1]);
          ctx.arc(g[j], g[j + 1], g[j + 2], 0, 6.2832);
        }
        ctx.fill();
      });
    });

    layoutLabels(now);
    // the leaves inside a cluster, then the titles themselves, appear at zoom.
    // Each rank clears its own boxes first, so the rank below it never reads a
    // name that is no longer on the screen.
    LOBE_BOXES = [];
    if (leafFade() > 0.03 && !MOBILE) drawLobeLabels();
    if (cam.s > restScale * 2 && !MOBILE) drawPubLabels();

    drawClusterLabels();
    if (keepDrawing) invalidate();
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
  /* Names are set by repulsion. Each name is pushed away from every cloud, from
     the furniture of the page and from the names already set; it takes the first
     free slot on a ring that grows outward, the widest clouds choosing first. A
     name that had to leave its cloud keeps a hairline back to it. Nothing is
     dropped: if no free slot exists the least crowded one is used. */
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
  // the shortest push that separates two boxes, or null when they are apart
  function boxPush(a, b) {
    var ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
    if (ox <= 0) return null;
    var oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
    if (oy <= 0) return null;
    var cx = (a.x + a.w / 2) - (b.x + b.w / 2), cy = (a.y + a.h / 2) - (b.y + b.h / 2);
    if (ox < oy) return [(cx < 0 ? -ox : ox), 0];
    return [0, (cy < 0 ? -oy : oy)];
  }
  // the shortest push that clears a box from a disc
  function discPush(b, d) {
    var nx = Math.max(b.x, Math.min(d.x, b.x + b.w));
    var ny = Math.max(b.y, Math.min(d.y, b.y + b.h));
    var dx = nx - d.x, dy = ny - d.y, dist = Math.hypot(dx, dy);
    if (dist >= d.r) return null;
    if (dist < 0.001) {
      var cx = (b.x + b.w / 2) - d.x, cy = (b.y + b.h / 2) - d.y;
      var m = Math.hypot(cx, cy) || 1;
      return [cx / m * d.r, cy / m * d.r];
    }
    var k = (d.r - dist) / dist;
    return [dx * k, dy * k];
  }

  /* The repair pass: every name that the ring search could not seat is put at
     its preferred place, and the whole set is then relaxed — names push each
     other, push off the clouds and off the furniture, and each one is pulled
     back toward its own cloud. What still sits on something at the end is left
     to the tap on a narrow screen, and drawn anyway on a wide one. */
  function relaxLabels(items, discs, chrome) {
    var i, j, p, PASSES = 150;
    for (var pass = 0; pass < PASSES; pass++) {
      // the pull toward the cloud eases off, so the last passes only separate
      var pull = pass < PASSES - 40 ? 0.055 : 0;
      // once the pull is off, the pushes work on a slightly grown box, so what
      // settles keeps a real gap rather than resting exactly on contact
      var pad = pull ? 0 : 1.6;
      var moved = 0;
      for (i = 0; i < items.length; i++) {
        var a = items[i];
        var ab = pad ? { x: a.box.x - pad, y: a.box.y - pad, w: a.box.w + 2 * pad, h: a.box.h + 2 * pad }
          : a.box;
        for (j = 0; j < items.length; j++) {
          if (j === i) continue;
          p = boxPush(ab, items[j].box);
          if (p) { a.box.x += p[0] * 0.55; ab.x += p[0] * 0.55; a.box.y += p[1] * 0.55; ab.y += p[1] * 0.55; moved++; }
        }
        for (j = 0; j < chrome.length; j++) {
          p = boxPush(ab, chrome[j]);
          if (p) { a.box.x += p[0]; ab.x += p[0]; a.box.y += p[1]; ab.y += p[1]; moved++; }
        }
        for (j = 0; j < discs.length; j++) {
          p = discPush(ab, discs[j]);
          if (p) { a.box.x += p[0]; ab.x += p[0]; a.box.y += p[1]; ab.y += p[1]; moved++; }
        }
        if (pull) {
          var dx = a.px - (a.box.x + a.box.w / 2), dy = a.py - (a.box.y + a.box.h / 2);
          a.box.x += dx * pull; a.box.y += dy * pull;
        }
        a.box.x = Math.min(Math.max(8, a.box.x), Math.max(8, W - a.box.w - 8));
        a.box.y = Math.min(Math.max(8, a.box.y), Math.max(8, H - a.box.h - 8));
      }
      if (!moved && !pull) break;
    }
    // what is still sitting on something: a name is kept only when it stands
    // clear of everything, with a hair of margin
    var E = 0;
    function tight(b) { return { x: b.x + E, y: b.y + E, w: b.w - 2 * E, h: b.h - 2 * E }; }
    items.forEach(function (a) {
      a.clean = true;
      var ta = tight(a.box), k;
      for (k = 0; k < items.length; k++) {
        if (items[k] !== a && boxPush(ta, tight(items[k].box))) { a.clean = false; return; }
      }
      for (k = 0; k < chrome.length; k++) if (boxPush(ta, chrome[k])) { a.clean = false; return; }
      for (k = 0; k < discs.length; k++) {
        if (discPush(ta, { x: discs[k].x, y: discs[k].y, r: discs[k].r - E })) { a.clean = false; return; }
      }
    });
  }

  function rectOverlap(a, b) {
    var ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
    var oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
    return ox > 0 && oy > 0 ? ox * oy : 0;
  }
  // under the cloud first, then over it, then beside it, then on the diagonals
  var ANGLES = [90, 270, 0, 180, 62, 118, 298, 242, 34, 146, 326, 214, 76, 104, 284, 256,
    18, 162, 342, 198, 48, 132, 312, 228].map(function (d, i) {
      return { a: d * Math.PI / 180, p: i };
    });
  var RINGS = 14, RING_STEP = 17;

  var LAB = [], DISCS = [], LOBE_BOXES = [], labSig = '';
  function layoutLabels(now) {
    refreshChrome(now);
    var hl = hover || sel;
    var chromeSig = 0;
    chromeBoxes.forEach(function (b) { chromeSig += b.x + b.y * 3 + b.w * 7 + b.h * 11; });
    var sig = [Math.round(cam.s * 200), Math.round(cam.x), Math.round(cam.y), MODE, W, H,
      hl ? hl.k : -1, matched ? matched.size : -1, Math.round(chromeSig)].join(',');
    if (!animating && sig === labSig) return;
    labSig = sig;

    var discs = [];
    CLUSTERS.forEach(function (c) {
      if (c.a < 0.06) return;
      discs.push({ x: wx(c.px), y: wy(c.py), r: haloR(c) + 2, c: c });
    });
    DISCS = discs;
    var order = CLUSTERS.filter(function (c) { return c.a >= 0.3; }).sort(function (a, b) {
      var pa = (a === hl ? 4 : 0) + (matched && a.mn > 0 ? 2 : 0);
      var pb = (b === hl ? 4 : 0) + (matched && b.mn > 0 ? 2 : 0);
      if (pa !== pb) return pb - pa;
      return (matched ? b.mn - a.mn : b.n - a.n);
    });
    var boxes = chromeBoxes.slice(), items = [];
    LAB = [];
    var cap = MOBILE ? 30 : 60;

    order.forEach(function (c) {
      var R = radiusOf(c) * cam.s, ax = wx(c.px), ay = wy(c.py);
      // a cloud whose centre has left the screen, or sits under a panel, keeps
      // its name off the screen too
      if (ax < -20 || ax > W + 20 || ay < -20 || ay > H + 20) return;
      for (var ci = 0; ci < chromeBoxes.length; ci++) {
        var cb = chromeBoxes[ci];
        if (ax > cb.x && ax < cb.x + cb.w && ay > cb.y && ay < cb.y + cb.h) return;
      }
      if (items.length >= cap && c !== hl) return;
      var step = c.n >= 60 ? 16.5 : (c.n >= 25 ? 14.2 : 12.4);
      if (MOBILE) step -= 2.6;
      if (c === hl) step += 1.4;
      var fs = MOBILE ? Math.min(12.4, Math.max(10.6, step))
        : Math.max(11.5, step * Math.min(Math.max(cam.s, 0.8), 1.2));
      ctx.font = (c === hl ? 600 : 500) + ' ' + fs + 'px "EB Garamond",Georgia,serif';
      // a long name breaks into two lines rather than being cut short
      var lines = wrapLabel(c.label, MOBILE ? 15 : 26, MOBILE ? 3 : 2);
      var tw = 0;
      lines.forEach(function (ln) { tw = Math.max(tw, ctx.measureText(ln).width); });
      var lh = fs * 1.18, bw = tw + 14, bh = lh * lines.length + 7;

      function at(ai, ring) {
        var a = ANGLES[ai].a;
        var half = Math.abs(Math.cos(a)) * bw / 2 + Math.abs(Math.sin(a)) * bh / 2;
        var d = R + 9 + ring * RING_STEP + half;
        var b = { x: ax + Math.cos(a) * d - bw / 2, y: ay + Math.sin(a) * d - bh / 2, w: bw, h: bh };
        if (b.x < 8 || b.y < 8 || b.x + bw > W - 8 || b.y + bh > H - 8) return null;
        var pen = 0, i;
        for (i = 0; i < discs.length; i++) if (rectHitsDisc(b, discs[i])) pen += 4e5;
        for (i = 0; i < boxes.length; i++) pen += rectOverlap(b, boxes[i]) * 14;
        return { box: b, pen: pen, ang: ai, ring: ring };
      }

      // a name whose hairline would run across another cloud is a second choice
      function crossings(b) {
        var nx = Math.max(b.x, Math.min(ax, b.x + b.w));
        var ny = Math.max(b.y, Math.min(ay, b.y + b.h));
        var vx = nx - ax, vy = ny - ay, len = Math.hypot(vx, vy);
        if (len < R + 10) return 0;
        var k = 0;
        for (var i = 0; i < discs.length; i++) {
          var dd = discs[i];
          if (Math.abs(dd.x - ax) < 1 && Math.abs(dd.y - ay) < 1) continue;
          var u = ((dd.x - ax) * vx + (dd.y - ay) * vy) / (len * len);
          if (u < 0 || u > 1) continue;
          var qx = ax + vx * u - dd.x, qy = ay + vy * u - dd.y;
          if (qx * qx + qy * qy < dd.r * dd.r) k++;
        }
        return k;
      }
      var got = null, clear = null, fall = null, fpen = 1e18, t;
      if (c._sl) { t = at(c._sl[0], c._sl[1]); if (t && !t.pen && !crossings(t.box)) got = t; }
      for (var ring = 0; ring <= RINGS && !got; ring++) {
        for (var ai = 0; ai < ANGLES.length; ai++) {
          t = at(ai, ring);
          if (!t) continue;
          if (!t.pen) {
            if (!crossings(t.box)) { got = t; break; }
            if (!clear) clear = t;
            continue;
          }
          var tot = t.pen + ring * 60 + ANGLES[ai].p * 8;
          if (tot < fpen) { fpen = tot; fall = t; }
        }
      }
      if (!got && clear) got = clear;
      var slot = got || fall;
      if (!slot) {
        slot = { ang: 0, ring: 0, box: {
          x: Math.min(Math.max(8, ax - bw / 2), Math.max(8, W - bw - 8)),
          y: Math.min(Math.max(8, ay + R + 9), Math.max(8, H - bh - 8)), w: bw, h: bh } };
      }
      c._sl = got ? [slot.ang, slot.ring] : null;
      boxes.push(slot.box);
      items.push({ c: c, box: slot.box, lines: lines, fs: fs, lh: lh,
        ax: ax, ay: ay, R: R, lit: c === hl, free: !!got, clean: !!got, px: ax, py: ay });
    });

    // whatever the ring search could not seat sends the whole set through one
    // relaxation; a name still sitting on something is left to the tap on a
    // narrow screen, and kept on a wide one rather than lost
    if (items.some(function (i) { return !i.free; })) {
      relaxLabels(items, discs, chromeBoxes);
    }
    LAB = items.filter(function (i) { return i.clean || !MOBILE || i.c === hl; });
    LAB.forEach(function (i) { i.free = i.clean; });
    // a programmatic check can read what was named and what was not
    var onScreen = CLUSTERS.filter(function (c) {
      if (c.a < 0.3) return false;
      var x = wx(c.px), y = wy(c.py);
      return x > -20 && x < W + 20 && y > -20 && y < H + 20;
    });
    window.__labels = {
      mode: MODE,
      clusters: onScreen.length,
      named: LAB.length,
      crowded: LAB.filter(function (l) { return !l.free; }).length,
      names: LAB.map(function (l) { return l.c.label; }),
      boxes: LAB.map(function (l) {
        return { n: l.c.label, x: l.box.x, y: l.box.y, w: l.box.w, h: l.box.h };
      }),
      discs: discs.map(function (d) { return { x: d.x, y: d.y, r: d.r }; }),
      chrome: chromeBoxes.map(function (b) { return { x: b.x, y: b.y, w: b.w, h: b.h }; }),
      missing: onScreen.filter(function (c) {
        return LAB.every(function (l) { return l.c !== c; });
      }).map(function (c) { return c.label; })
    };
  }

  function drawClusterLabels() {
    LAB.forEach(function (l) {
      var c = l.c, b = l.box;
      // the hairline back to the cloud, drawn only when the name had to move out
      var nx = Math.max(b.x, Math.min(l.ax, b.x + b.w));
      var ny = Math.max(b.y, Math.min(l.ay, b.y + b.h));
      var dx = nx - l.ax, dy = ny - l.ay, d = Math.hypot(dx, dy);
      if (d > l.R + 10) {
        ctx.strokeStyle = hexA(STONE, 0.46 * c.a); ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(l.ax + dx / d * (l.R + 2), l.ay + dy / d * (l.R + 2));
        ctx.lineTo(nx, ny);
        ctx.stroke();
      }
      ctx.font = (l.lit ? 600 : 500) + ' ' + l.fs + 'px "EB Garamond",Georgia,serif';
      ctx.fillStyle = hexA(PAPER, 0.9 * c.a);
      roundRect(b.x, b.y, b.w, b.h, 5); ctx.fill();
      ctx.fillStyle = hexA(c.kind === 'tail' ? STONE : INK, Math.min(1, c.a * 1.05));
      ctx.textAlign = 'center'; ctx.textBaseline = 'top';
      var cx = b.x + b.w / 2;
      l.lines.forEach(function (ln, li) { ctx.fillText(ln, cx, b.y + 3.5 + li * l.lh); });
      if (l.lit) {
        ctx.strokeStyle = hexA(ACCENT, 0.5); ctx.lineWidth = 1;
        roundRect(b.x, b.y, b.w, b.h, 5); ctx.stroke();
      }
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
      ctx.fillStyle = hexA('#8E8264', 0.05 * c.a);
      ctx.beginPath(); ctx.arc(x, y, ring, 0, 6.2832); ctx.fill();
      ctx.strokeStyle = hexA(STONE, 0.17 * c.a); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(x, y, ring, 0, 6.2832); ctx.stroke();
      if (c.lobes && c.lobes.length > 1 && !matched) {
        ctx.strokeStyle = hexA(STONE, (0.1 + 0.07 * leaf) * c.a);
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
    var placed = LAB.map(function (l) { return l.box; }).concat(chromeBoxes);
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
        for (i = 0; i < DISCS.length; i++) {
          if (DISCS[i].c !== c && rectHitsDisc(box, DISCS[i])) return;
        }
        for (i = 0; i < placed.length; i++) {
          var q = placed[i];
          if (bx < q.x + q.w && bx + bw > q.x && by < q.y + q.h && by + bh > q.y) return;
        }
        placed.push(box);
        // the third rank of names reads these before it places a title
        LOBE_BOXES.push(box);
        ctx.fillStyle = hexA(PAPER, paper);
        roundRect(bx, by, bw, bh, 4); ctx.fill();
        ctx.fillStyle = hexA(STONE, ink);
        ctx.fillText(t, x, y);
        drawn++;
      });
    });
    window.__leaves = { fade: +up.toFixed(3), full: full, tried: tried, drawn: drawn };
  }

  function drawPubLabels() {
    // nearest cluster to the centre of the view, its titles unfold
    var best = null, bd = 1e9;
    CLUSTERS.forEach(function (c) {
      if (c.a < 0.5) return;
      var d = Math.hypot(wx(c.px) - W / 2, wy(c.py) - H / 2);
      if (d < bd) { bd = d; best = c; }
    });
    if (!best || bd > Math.min(W, H) * 0.42) return;
    var cx = wx(best.px), cy = wy(best.py);
    var list = best.pubs.filter(function (p) {
      return visiblePub(p) && (!matched || matched.has(p.i));
    }).sort(function (a, b) { return b.w - a.w; }).slice(0, 30);
    // titles come last: after the names of the clouds, after the names of the
    // leaves inside them, and never on top of either
    var placed = LAB.map(function (l) { return l.box; })
      .concat(chromeBoxes).concat(LOBE_BOXES);
    ctx.font = '400 11.5px "Literata",Georgia,serif';
    ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    list.forEach(function (p) {
      var x = cx + (p.cox == null ? p.ox : p.cox) * cam.s, y = cy + (p.coy == null ? p.oy : p.coy) * cam.s;
      if (x < 20 || x > W - 20 || y < 70 || y > H - 20) return;
      var t = p.title.length > 42 ? p.title.slice(0, 41) + '…' : p.title;
      var tw = ctx.measureText(t).width;
      var bx = x + 5, by = y - 8, bw = tw + 9, bh = 16;
      var clash = false;
      for (var i = 0; i < placed.length; i++) {
        var q = placed[i];
        if (bx < q.x + q.w && bx + bw > q.x && by < q.y + q.h && by + bh > q.y) { clash = true; break; }
      }
      if (clash) return;
      placed.push({ x: bx, y: by, w: bw, h: bh });
      ctx.fillStyle = hexA(PAPER, 0.86);
      roundRect(bx, by, bw, bh, 4); ctx.fill();
      ctx.fillStyle = hexA(INK, 0.9);
      ctx.fillText(t, bx + 4.5, y);
    });
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

  /* ------------------------------------------------------------------ panel */
  var panel = document.getElementById('panel');
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
  function abstractHTML(p, index) {
    if (!p.ab || !p.ab.t) return '';
    var text = p.ab.t;
    var long = text.length > ABSTRACT_FOLD;
    var id = 'ab-' + index;
    var credit;
    if (p.ab.k === 'generated') {
      credit = 'Summary written for Origenality';
    } else {
      var label = (ABS && ABS.sources && ABS.sources[p.ab.s] && ABS.sources[p.ab.s].label) || p.ab.s;
      credit = 'Abstract from ' + (p.ab.u
        ? '<a href="' + esc(p.ab.u) + '" target="_blank" rel="noopener">' + esc(label) + '</a>'
        : esc(label));
    }
    return '<div class="abstract">' +
      '<p class="abstract-text' + (long ? ' folded' : '') + '" id="' + id + '">' + esc(text) + '</p>' +
      (long ? '<button type="button" class="abstract-more" aria-expanded="false" aria-controls="' +
        id + '">Read the full abstract</button>' : '') +
      '<p class="abstract-credit">' + credit + '</p></div>';
  }

  function recordHTML(p) {
    var meta = [];
    if (p.authors.length) meta.push(esc(p.authors.slice(0, 3).join(', ')) + (p.authors.length > 3 ? ' and others' : ''));
    if (p.year != null) meta.push(String(p.year));
    if (p.container) meta.push('<i>' + esc(p.container) + '</i>');
    if (p.publisher) meta.push(esc(p.publisher));
    // the link is the one the record carries, under the name of the base that
    // holds it; a record without a link gets no link rather than a guessed one
    var links = [];
    if (p.url) {
      links.push('<a href="' + esc(p.url) + '" target="_blank" rel="noopener">' +
        esc(sourceName(p.src)) + ' record</a>');
    }
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
      '<span class="dot">·</span><span class="lang"><i style="background:' + LCOL[p.lang] + '"></i>' +
      esc(LLAB[p.lang]) + '</span>' +
      (p.type ? '<span class="dot">·</span>' + esc(p.type) : '') + '</p>' +
      (tags.length ? '<p class="tags">' + tags.join(' · ') +
        (flags.length ? ' <span class="flag">· ' + flags.join(' · ') + '</span>' : '') + '</p>'
        : (flags.length ? '<p class="tags"><span class="flag">' + flags.join(' · ') + '</span></p>' : '')) +
      '<p class="weight" title="Node size = mean of the citation percentile inside the cohort and ' +
      'the PageRank percentile in this graph"><span class="tier t' + p.tier + '"></span>' + wgt + '</p>' +
      abstractHTML(p, p.i) +
      '<div class="links">' + links.join('') + '</div></article>';
  }

  function renderPanel() {
    var list, title, adjacent = [], dens = 0;
    if (sel) {
      list = sel.pubs.filter(function (p) { return visiblePub(p) && (!matched || matched.has(p.i)); });
      title = sel.label;
      pSubject.textContent = sel.note;
      pAlt.textContent = sel.alt || '';
      adjacent = sel.near.slice(0, 4).map(function (l) { return CLUSTERS[l.k]; })
        .filter(function (c) { return c && c.kind === 'subject'; });
    } else {
      list = PUBS.filter(function (p) { return visiblePub(p) && (!matched || matched.has(p.i)); });
      if (matched && window.__scores) {
        list.sort(function (a, b) { return (window.__scores[b.i] || 0) - (window.__scores[a.i] || 0); });
      }
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

    // the headline figure is the counted population, the same one every other
    // surface prints; what the list holds beyond it is named underneath
    var mention = 0, aside = 0;
    list.forEach(function (p) {
      if (p.dens) dens++;
      else if (p.rel === 'none') aside++;
      else mention++;
    });
    currentList = list;
    var n = list.length;
    // the reservoir of records held as not about Origen states its own size:
    // it is a reservoir, not a figure of the field
    var headline = (sel && sel.id === OFF) ? aside : dens;
    pDensity.innerHTML = nf(headline) + (headline === 1 ? ' work' : ' works') + '<small>' +
      (sel ? 'in ' + esc(title) + (matched ? ', under your current answers' : '')
           : (matched ? 'in the neighbourhood of ' + esc(matchLabel)
                        + (tokCount > 1 && hitDepth && hitDepth < tokCount
                            ? ', matching ' + hitDepth + ' of your ' + tokCount + ' terms' : '')
                      : 'in the whole corpus')) +
      '</small>';

    var zoneBits = [];
    if (sel && sel.id === OFF) {
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
    if (sel && sel.kind === 'subject' && sel.lobes) {
      var leaves = sel.lobes.filter(function (lo) { return lo.name; }).slice(0, 5);
      if (leaves.length) {
        zoneBits.push('<p><b>Inside</b> ' + leaves.map(function (lo) {
          return esc(lo.name) + ' (' + lo.dens + ')';
        }).join(', ') + '</p>');
      }
    }
    if (!sel) {
      var conc = CLUSTERS.filter(function (c) { return c.kind === 'subject' && c.mn > 0; })
        .sort(function (a, b) { return b.mn - a.mn; }).slice(0, 3);
      if (conc.length) {
        zoneBits.push('<p><b>Concentrated in</b> ' + conc.map(function (c) {
          return '<button class="z" data-k="' + c.k + '">' + esc(c.label) + '</button> (' + c.mn + ')';
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
      b.addEventListener('click', function () { openCluster(CLUSTERS[+b.dataset.k]); });
    });

    shownCount = 0;
    pBody.innerHTML = '';
    if (!n) {
      pBody.innerHTML = '<p class="empty"><svg class="mk" viewBox="0 0 100 100" width="12" height="12" aria-hidden="true">' +
        '<g stroke="currentColor" stroke-width="12" fill="none"><path d="M50 14 L50 86"/><path d="M14 50 L86 50"/></g>' +
        '<g fill="currentColor"><circle cx="27" cy="27" r="8"/><circle cx="73" cy="27" r="8"/>' +
        '<circle cx="27" cy="73" r="8"/><circle cx="73" cy="73" r="8"/></g></svg> The harvest holds nothing under these ' +
        'conditions. Widen the languages, or drop one answer.</p>';
      openPanel();
      return;
    }
    var head = document.createElement('div');
    head.className = 'listhead';
    head.innerHTML = '<span>Sources</span><span>' + nf(n) + ' listed</span>';
    pBody.appendChild(head);
    appendMore();
    openPanel();
    pBody.scrollTop = 0;
  }

  function appendMore() {
    var slice = currentList.slice(shownCount, shownCount + 20);
    var frag = document.createElement('div');
    frag.innerHTML = slice.map(recordHTML).join('');
    while (frag.firstChild) pBody.appendChild(frag.firstChild);
    shownCount += slice.length;
    var old = pBody.querySelector('.more'); if (old) old.remove();
    if (shownCount < currentList.length) {
      var b = document.createElement('button');
      b.className = 'btn-quiet more';
      b.textContent = 'Show 20 more of ' + nf(currentList.length - shownCount);
      b.addEventListener('click', appendMore);
      pBody.appendChild(b);
    }
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

  function openPanel() {
    var was = panel.classList.contains('open');
    if (!was) {
      var from = document.activeElement;
      lastFocus = (from && from !== document.body && !panel.contains(from)) ? from : null;
    }
    document.body.classList.add('panel-open');
    panel.classList.add('open');
    setPanelInert(false);
    if (!was) {
      panel.focus({ preventScroll: true });
      if (!MOBILE) fitView();
      settle();
    }
  }
  function closePanel() {
    var was = panel.classList.contains('open');
    var inside = was && panel.contains(document.activeElement);
    document.body.classList.remove('panel-open');
    panel.classList.remove('open');
    setPanelInert(true);
    sel = null;
    if (was) {
      if (inside) {
        var back = (lastFocus && document.contains(lastFocus)) ? lastFocus : cv;
        back.focus({ preventScroll: true });
      }
      lastFocus = null;
      if (!MOBILE) fitView();
      settle();
    }
  }
  function openCluster(c) {
    if (!c) return;
    sel = c;
    renderPanel();
    if (!MOBILE) {
      var s = Math.max(cam.s, Math.min(2.4, 190 / Math.max(radiusOf(c), 14)));
      tcam.s = s;
      tcam.x = (W - 436) / 2 - c.px * s;
      tcam.y = (H + 170) / 2 - c.py * s;
    }
    invalidate();
  }
  document.getElementById('panel-close').addEventListener('click', closePanel);

  // one listener for every fold in the list, present and future
  pBody.addEventListener('click', function (ev) {
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

  var peek = document.getElementById('peek');
  function showPeek(c, sx, sy) {
    var mix = LANGS.filter(function (l) { return c.mix[l.code]; }).map(function (l) {
      return { l: l, n: c.mix[l.code] };
    }).sort(function (a, b) { return b.n - a.n; });
    var mixTotal = 0;
    mix.forEach(function (m) { mixTotal += m.n; });
    var bars = mix.map(function (m) {
      return '<span style="width:' + (mixTotal ? m.n / mixTotal * 100 : 0).toFixed(1) +
        '%;background:' + m.l.col + '"></span>';
    }).join('');
    var count = clusterCount(c), extra = clusterExtra(c);
    peek.innerHTML = '<h4>' + esc(c.label) + '</h4>' +
      (c.alt ? '<p class="alt">' + esc(c.alt) + '</p>' : '') +
      '<p class="cnt">' + count.text + (count.one ? ' work' : ' works') +
      (extra ? '<span class="extra">' + nf(extra) + ' mentioned only</span>' : '') + '</p>' +
      '<div class="mix">' + bars + '</div>' +
      '<p class="mixlbl">' + mix.slice(0, 3).map(function (m) {
        return esc(m.l.label) + ' ' + m.n;
      }).join(' · ') + '</p>' +
      (c.lobes && c.lobes.length > 1
        ? '<p class="mixlbl">' + c.lobes.filter(function (lo) { return lo.name && lo.dens; })
            .slice(0, 3).map(function (lo) { return esc(lo.name) + ' ' + lo.dens; })
            .join(' · ') + '</p>'
        : '');
    var w = 262, x = Math.min(Math.max(12, sx + 18), W - w - 12), y = Math.min(Math.max(70, sy + 16), H - 160);
    peek.style.left = x + 'px'; peek.style.top = y + 'px';
    peek.classList.add('on');
  }
  function hidePeek() { peek.classList.remove('on'); }

  /* ------------------------------------------------------------------ pointer */
  var down = null, panning = false, pinch = null;
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
        hidePeek(); hover = null; invalidate();
        return;
      }
    }
    var c = pick(e.clientX, e.clientY);
    if (c !== hover) invalidate();
    hover = c;
    cv.style.cursor = c ? 'pointer' : 'grab';
    if (c && !MOBILE) showPeek(c, e.clientX, e.clientY); else hidePeek();
  });
  cv.addEventListener('pointerup', function (e) {
    var dist = down ? Math.hypot(e.clientX - down[0], e.clientY - down[1]) : 0;
    if (dist < 5) {
      var c = pick(e.clientX, e.clientY);
      if (c) openCluster(c); else closePanel();
    }
    panning = false; down = null; cv.classList.remove('grabbing');
  });
  cv.addEventListener('pointerleave', function () { hidePeek(); hover = null; invalidate(); });
  cv.addEventListener('wheel', function (e) {
    e.preventDefault();
    var f = Math.exp(-e.deltaY * 0.0014);
    var wx0 = (e.clientX - cam.x) / cam.s, wy0 = (e.clientY - cam.y) / cam.s;
    tcam.s = Math.max(0.18, Math.min(4, tcam.s * f));
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
      tcam.s = Math.max(0.18, Math.min(4, pinch.s * d / pinch.d));
      tcam.x = pinch.mx - wx0 * tcam.s; tcam.y = pinch.my - wy0 * tcam.s;
      invalidate();
    }
  }, { passive: false });
  cv.addEventListener('touchend', function (e) { if (e.touches.length < 2) pinch = null; });

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
    // the slot each name held on the old screen is forgotten: kept, it seats a
    // few names in places that made sense at the old width and leaves the
    // clusters that come after them unnamed. A turned phone gets the same
    // arrangement it would have got had it loaded that way.
    Object.keys(BUILT).forEach(function (m) {
      BUILT[m].clusters.forEach(function (c) { c._sl = null; });
    });
    startTween(RM ? 1 : 620);
    fitView();
  }
  var rzTimer = null;
  function onViewportChange() {
    MOBILE = matchMedia('(max-width:760px)').matches;
    var h = document.getElementById('hint');
    if (h) {
      h.textContent = MOBILE
        ? 'Pinch to zoom · tap a cluster to open it'
        : 'Drag to move · scroll to zoom · click a cluster to open it';
    }
    resize(); fitView(); measureLegend();
    if (rzTimer) clearTimeout(rzTimer);
    rzTimer = setTimeout(function () { rzTimer = null; relayout(); }, 220);
  }
  addEventListener('resize', onViewportChange);
  addEventListener('orientationchange', onViewportChange);
  addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { closePanel(); hidePeek(); }
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
    if (!MOBILE) showPeek(c, wx(c.px), wy(c.py));
    invalidate();
  });
  cv.addEventListener('blur', function () { hidePeek(); hover = null; kbIndex = -1; invalidate(); });

  /* ------------------------------------------------------------------ chrome */
  function boot() {
    if (MOBILE) {
      var h = document.getElementById('hint');
      if (h) h.textContent = 'Pinch to zoom · tap a cluster to open it';
    }
    // legend
    var lg = document.getElementById('legend');
    // the same population as the Observatory: core and partial
    var byLang = {};
    PUBS.forEach(function (p) { if (counts(p)) byLang[p.lang] = (byLang[p.lang] || 0) + 1; });
    LANGS.forEach(function (l) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'lg';
      b.setAttribute('aria-pressed', 'true');
      b.innerHTML = '<i style="background:' + l.col + '"></i>' + esc(l.label) +
        '<span class="n">' + nf(byLang[l.code] || 0) + '</span>';
      b.addEventListener('click', function () {
        langOff[l.code] = !langOff[l.code];
        b.classList.toggle('off', !!langOff[l.code]);
        b.setAttribute('aria-pressed', langOff[l.code] ? 'false' : 'true');
        if (panel.classList.contains('open')) renderPanel();
        invalidate();
      });
      lg.appendChild(b);
    });

    // grouping axis
    var mt = document.getElementById('mode-theme'), mw = document.getElementById('mode-work');
    function setMode(mode) {
      if (mode === MODE) return;
      useMode(mode, true);
      mt.setAttribute('aria-pressed', mode === 'theme' ? 'true' : 'false');
      mw.setAttribute('aria-pressed', mode === 'work' ? 'true' : 'false');
      kbIndex = -1;
      closePanel();
      applyMatch(false);
    }
    mt.addEventListener('click', function () { setMode('theme'); });
    mw.addEventListener('click', function () { setMode('work'); });

    // search
    var input = document.getElementById('ask-input');
    var fieldEl = document.getElementById('ask-field');
    var clear = document.getElementById('ask-clear');
    function runSearch() {
      query = input.value;
      fieldEl.classList.toggle('filled', !!query.trim());
      applyMatch(true);
    }
    document.getElementById('ask-go').addEventListener('click', runSearch);
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') runSearch(); });
    input.addEventListener('input', function () {
      fieldEl.classList.toggle('filled', !!input.value.trim());
    });
    clear.addEventListener('click', function () {
      input.value = ''; query = ''; fieldEl.classList.remove('filled');
      applyMatch(false); closePanel();
    });

    document.getElementById('reset').addEventListener('click', function () {
      query = ''; input.value = ''; fieldEl.classList.remove('filled');
      wizAns = { work: [], approach: [], decade: [], lang: [] };
      Object.keys(langOff).forEach(function (k) { langOff[k] = false; });
      lg.querySelectorAll('.lg').forEach(function (b) {
        b.classList.remove('off'); b.setAttribute('aria-pressed', 'true');
      });
      closeWiz();
      applyMatch(false); closePanel();
    });

    OPTS = buildOptions();
    initWizard();
    applyMatch(false);
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
    wiz.classList.add('open');
    settle();
    document.getElementById('wiz-open').textContent = 'close the questions';
    paintWiz();
  }
  function closeWiz() {
    wiz.classList.remove('open');
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
      wizAns[q.kind] = [];
      paintWiz(); applyMatch(false);
    });
    var nbox = document.getElementById('wiz-none');
    nbox.innerHTML = '';
    nbox.appendChild(none);
  }
})();
