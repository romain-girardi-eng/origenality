/* Origenality: records as references: BibTeX, RIS, CSL-JSON and COinS,
 * written from the fields the data carries and from nothing else.
 *
 * The Explorer loads this file as a classic script before explorer.js (global
 * OrigenalityCite); node requires it (scripts/test_cite_export.mjs). Pure
 * functions: no DOM, no request.
 *
 * ------------------------------------------------------------------ entry
 * entryFromRecord(record, ctx) -> entry
 *   record  a record of search-core.js buildIndex: title, year, type, authors,
 *           lang, publisher, isbn, doi, url, src, sourceIds, ppn, rel, container.
 *   ctx.containers  map Origenality ID -> {title, type} read from
 *           data/cite.json (citeData) or, when that file cannot be read, from
 *           data/site-merged/corpus.jsonl (containersFromCorpus); or null. With
 *           a map, a record absent from it has no container. Without one, the
 *           record's own `container` is used: graph.json keeps a container only
 *           when five records share it, and gives no container type.
 *   ctx.fields  map Origenality ID -> {publisher, doi, isbn} from data/cite.json,
 *           or null. A value given there is written; a value it lacks falls
 *           back to the record's own field.
 *   ctx.sourceName  function (source key) -> short base name ("IxTheo").
 *   ctx.abstract    {text, credit, url} or null, given only when the reader
 *           asks for abstracts; `credit` is the line the page prints under the
 *           abstract ("Abstract from <database>"), `url` the record it links to.
 *
 *   entry = { key, kind, title, authors, year, container, publisher, isbn, doi,
 *             language, url, urlSource, recordId, flag, abstract }
 *   An absent value is '' or null (authors []), and an absent value is never
 *   written: no field is emitted without data behind it.
 *
 * ------------------------------------------------------------------ types
 * Read from the record's own `type`, never guessed from its other fields.
 *
 *   type       BibTeX          RIS    CSL-JSON
 *   article    @article        JOUR   article-journal
 *   review     @article        JOUR   article-journal   note opens "Review."
 *   chapter    @incollection   CHAP   chapter
 *   book       @book           BOOK   book
 *   other, or any value not above
 *              @misc           GEN    document
 *
 * The container goes where its own type puts it:
 *   host,   on article or review   journal     T2   container-title
 *   host,   on chapter             booktitle   T2   container-title
 *   series, on any type            series      T3   collection-title
 *   host on a book or other, or a container of unknown type on a book or
 *   other: the note says "In <title>." (the data has two books with a host).
 *   Unknown type on article, review or chapter is read as host: in the data
 *   these three types carry no series.
 * No volume, issue or pages exists anywhere in the data, and none is written;
 * the note says so, so a reader does not take the gap for an omission.
 *
 * Every entry: url = the first source record that has a URL; note = "Origenality
 * <source:id>, <base> record <url>." Records mentioned only or held aside are
 * kept and carry the keyword origenality:mentioned-only or origenality:held-aside.
 *
 * ------------------------------------------------------------------ keys
 * baseKey: family name of the first author (the part before the comma of the
 * catalogue form, parentheses dropped), year or "nd", first title word that is
 * neither an article nor a number; letters folded to a-z0-9. No author: the
 * first two title words. assignKeys gives every entry of a set its base key;
 * entries sharing one get a, b, c... in the order of their record id, so the
 * suffix does not depend on the order of the list. The Explorer assigns keys
 * over the whole build once, so a record keeps one key whatever view exports
 * it. Each writer then makes the keys of its own file unique in any case.
 *
 * ------------------------------------------------------------------ text
 * UTF-8 throughout; letters with accents are written as they are. A run of
 * control characters or line separators becomes one space, so every value
 * stays on one line; spaces are kept as the data has them. BibTeX text fields
 * escape \ { } % & # $ _ ~ ^ with commands whose own braces balance
 * (\textbackslash{}, \textbraceleft{}, \textbraceright{}, \%, \&, \#, \$, \_,
 * \textasciitilde{}, \textasciicircum{}); url and doi are written raw, with any
 * brace or backslash percent-encoded. A name without a comma is braced whole,
 * so BibTeX does not split it into first and last names.
 *
 * ------------------------------------------------------------------ CSL-JSON
 * An array of items. Keys written, all optional except id and type:
 *   id string; type string (article-journal | chapter | book | document);
 *   title, container-title, collection-title, publisher, ISBN, DOI, URL,
 *   language, keyword, abstract, note: strings;
 *   author: [{family, given?} | {literal}]  ("Family, Given" is split at its
 *   first comma; a form without a comma is a literal);
 *   issued: {"date-parts": [[year]]}.
 * Romain Girardi, 2026. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.OrigenalityCite = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var KINDS = { article: 1, review: 1, chapter: 1, book: 1, other: 1 };
  var BIB_TYPE = { article: 'article', review: 'article', chapter: 'incollection', book: 'book', other: 'misc' };
  var RIS_TYPE = { article: 'JOUR', review: 'JOUR', chapter: 'CHAP', book: 'BOOK', other: 'GEN' };
  var CSL_TYPE = { article: 'article-journal', review: 'article-journal', chapter: 'chapter', book: 'book', other: 'document' };
  var FORMATS = {
    bibtex: { ext: 'bib', mime: 'application/x-bibtex;charset=utf-8', label: 'BibTeX' },
    ris: { ext: 'ris', mime: 'application/x-research-info-systems;charset=utf-8', label: 'RIS' },
    csl: { ext: 'json', mime: 'application/vnd.citationstyles.csl+json;charset=utf-8', label: 'CSL-JSON' }
  };
  var FLAG = { marginal: 'mentioned-only', none: 'held-aside' };
  var NO_PAGES = 'Volume, issue and pages are not carried by Origenality.';

  function has(v) { return v != null && v !== ''; }
  function oneLine(s) {
    return String(s == null ? '' : s).replace(/[\u0000-\u001f\u007f\u2028\u2029]+/g, ' ').trim();
  }

  /* ------------------------------------------------------------------ entries */
  function containersFromCorpus(text) {
    var out = Object.create(null);
    String(text || '').split('\n').forEach(function (line) {
      if (!line.trim()) return;
      var r;
      try { r = JSON.parse(line); } catch (e) { return; }
      if (!r || !r.origenality_id) return;
      var c = r.container;
      if (typeof c === 'string' && c.trim()) out[r.origenality_id] = { title: c, type: '' };
      else if (c && typeof c === 'object' && has(c.title)) {
        out[r.origenality_id] = { title: String(c.title), type: c.type === 'host' || c.type === 'series' ? c.type : '' };
      }
    });
    return out;
  }

  // data/cite.json (site/build-c/tools/build_cite_data.py): per record, the
  // container with its type, the publisher, the DOI and the ISBN, under short
  // keys c, ct, pb, doi, isbn. Version 2 adds the subject headings (s) and the
  // container as the map files it (in), which search-core.js reads and the
  // export does not. Throws on a file of another shape, so the page falls back
  // to the record file.
  var CITE_SCHEMAS = { 'origenality-cite/1': 1, 'origenality-cite/2': 1 };
  function citeData(json) {
    if (!json || !CITE_SCHEMAS[json.schema] || !json.byPpn || typeof json.byPpn !== 'object') {
      throw new Error('cite.json has an unknown shape');
    }
    var containers = Object.create(null), fields = Object.create(null);
    Object.keys(json.byPpn).forEach(function (id) {
      var r = json.byPpn[id] || {};
      if (has(r.c)) containers[id] = { title: String(r.c), type: r.ct === 'host' || r.ct === 'series' ? r.ct : '' };
      var f = {};
      if (has(r.pb)) f.publisher = String(r.pb);
      if (has(r.doi)) f.doi = String(r.doi);
      if (has(r.isbn)) f.isbn = String(r.isbn);
      if (f.publisher || f.doi || f.isbn) fields[id] = f;
    });
    return { containers: containers, fields: fields };
  }

  function entryFromRecord(p, ctx) {
    ctx = ctx || {};
    var name = typeof ctx.sourceName === 'function' ? ctx.sourceName : function (k) { return k; };
    var container = null;
    if (ctx.containers) {
      var c = ctx.containers[p.ppn];
      if (c && has(c.title)) container = { title: String(c.title), type: c.type || '' };
    } else if (has(p.container)) {
      container = { title: String(p.container), type: '' };
    }
    var first = null;
    (p.sourceIds || []).some(function (e) { if (e && has(e.url)) { first = e; return true; } return false; });
    var firstId = (p.sourceIds || [])[0];
    var recordId = firstId && has(firstId.source) && has(firstId.id) ? firstId.source + ':' + firstId.id : (p.ppn || '');
    var own = (ctx.fields && ctx.fields[p.ppn]) || {};
    var publisher = has(own.publisher) ? own.publisher : p.publisher;
    var isbn = has(own.isbn) ? own.isbn : p.isbn;
    var doi = has(own.doi) ? own.doi : p.doi;
    var url = first ? first.url : (p.url || '');
    var urlSource = first ? first.source : (p.src || '');
    return {
      key: '',
      kind: KINDS[p.type] ? p.type : 'other',
      title: has(p.title) ? String(p.title) : '',
      authors: (p.authors || []).filter(has).map(String),
      year: typeof p.year === 'number' && isFinite(p.year) ? p.year : null,
      container: container,
      publisher: has(publisher) ? String(publisher) : '',
      isbn: has(isbn) ? String(isbn) : '',
      doi: has(doi) ? String(doi) : '',
      language: has(p.lang) ? String(p.lang) : '',
      url: has(url) ? String(url) : '',
      urlSource: has(url) ? name(urlSource) : '',
      recordId: recordId,
      flag: FLAG[p.rel] || null,
      abstract: ctx.abstract && has(ctx.abstract.text) ? {
        text: String(ctx.abstract.text), credit: String(ctx.abstract.credit || ''),
        url: has(ctx.abstract.url) ? String(ctx.abstract.url) : ''
      } : null
    };
  }

  // where the container goes: 'host' (journal, booktitle), 'series', or 'note'
  function containerRole(e) {
    if (!e.container) return null;
    var t = e.container.type;
    if (t === 'series') return 'series';
    if (e.kind === 'article' || e.kind === 'review' || e.kind === 'chapter') return 'host';
    return 'note';
  }

  function noteOf(e) {
    var bits = [];
    if (e.kind === 'review') bits.push('Review.');
    if (containerRole(e) === 'note') bits.push('In ' + oneLine(e.container.title) + '.');
    bits.push('Origenality ' + e.recordId + (e.url ? ', ' + e.urlSource + ' record ' + oneLine(e.url) : '') + '.');
    bits.push(NO_PAGES);
    if (e.abstract && e.abstract.credit) {
      bits.push(oneLine(e.abstract.credit) + (e.abstract.url ? ', ' + oneLine(e.abstract.url) : '') + '.');
    }
    return bits.join(' ');
  }

  /* ------------------------------------------------------------------ keys */
  var STOP = {};
  ('a an the of and on in to for from with by at as is ' +
    'der die das des dem den ein eine einer eines einem und zu zur zum im am vom von bei mit ' +
    'le la les l d de du des un une et en au aux sur dans pour par ' +
    'il lo gli i di del della dello dei degli delle e ed nel nella per con da ' +
    'el los las y al lo una unos unas ' +
    'ad ab ex et cum sub apud').split(' ').forEach(function (w) { STOP[w] = 1; });

  function fold(s) {
    return String(s == null ? '' : s)
      .replace(/ß/g, 'ss').replace(/[æÆ]/g, 'ae').replace(/[œŒ]/g, 'oe').replace(/[øØ]/g, 'o')
      .replace(/[łŁ]/g, 'l').replace(/[đĐ]/g, 'd').replace(/[þÞ]/g, 'th')
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }
  function words(s) { return fold(s).split(/[^a-z0-9]+/).filter(Boolean); }

  function baseKey(e) {
    var family = e.authors.length ? e.authors[0].split(',')[0] : '';
    family = family.replace(/\([^)]*\)|<[^>]*>|\[[^\]]*\]/g, ' ');
    var who = words(family).join('').slice(0, 24);
    var tw = words(e.title).filter(function (w) { return !STOP[w] && !/^\d+$/.test(w); });
    var what = tw[0] || '';
    if (!who) { who = what; what = tw[1] || ''; }
    return (who || 'anon') + (e.year != null ? String(e.year) : 'nd') + what.slice(0, 24);
  }
  function suffix(i) {
    var s = '';
    i += 1;
    while (i > 0) { var m = (i - 1) % 26; s = String.fromCharCode(97 + m) + s; i = Math.floor((i - 1) / 26); }
    return s;
  }
  // gives each entry its key, in place; returns the entries
  function assignKeys(entries) {
    var groups = Object.create(null), order = [];
    entries.forEach(function (e) {
      var b = baseKey(e);
      if (!groups[b]) { groups[b] = []; order.push(b); }
      groups[b].push(e);
    });
    order.forEach(function (b) {
      var g = groups[b];
      if (g.length === 1) { g[0].key = b; return; }
      g.slice().sort(function (x, y) { return x.recordId < y.recordId ? -1 : (x.recordId > y.recordId ? 1 : 0); })
        .forEach(function (e, i) { e.key = b + suffix(i); });
    });
    return uniqueKeys(entries);
  }
  // a file never holds one key twice: a key already taken gets _2, _3...
  function uniqueKeys(entries) {
    var taken = Object.create(null);
    entries.forEach(function (e) { if (e.key) taken[e.key] = (taken[e.key] || 0) + 1; });
    var seen = Object.create(null);
    entries.forEach(function (e) {
      if (!seen[e.key]) { seen[e.key] = 1; return; }
      var n = 2;
      while (taken[e.key + '_' + n]) n++;
      e.key = e.key + '_' + n;
      taken[e.key] = 1; seen[e.key] = 1;
    });
    return entries;
  }
  // copies of the entries a writer works on, every one keyed, keys unique
  function prepare(entries) {
    var copies = entries.map(function (e) { return Object.assign({}, e); });
    var bare = copies.filter(function (e) { return !e.key; });
    if (bare.length) assignKeys(bare);
    return uniqueKeys(copies);
  }

  /* ------------------------------------------------------------------ BibTeX */
  var BIB = {
    '\\': '\\textbackslash{}', '{': '\\textbraceleft{}', '}': '\\textbraceright{}',
    '%': '\\%', '&': '\\&', '#': '\\#', '$': '\\$', '_': '\\_',
    '~': '\\textasciitilde{}', '^': '\\textasciicircum{}'
  };
  function bibText(s) { return oneLine(s).replace(/[\\{}%&#$_~^]/g, function (c) { return BIB[c]; }); }
  function bibRaw(s) {
    return oneLine(s).replace(/[{}\\]/g, function (c) { return '%' + c.charCodeAt(0).toString(16).toUpperCase(); });
  }
  function bibName(a) {
    var s = bibText(a);
    if (a.indexOf(',') < 0) return '{' + s + '}';
    return s.replace(/(^|\s)and(?=\s|$)/gi, '$1{and}');
  }
  function bibEntry(e) {
    var f = [];
    function put(name, value) { f.push('  ' + name + ' = {' + value + '}'); }
    var role = containerRole(e);
    if (e.authors.length) put('author', e.authors.map(bibName).join(' and '));
    if (e.title) put('title', bibText(e.title));
    if (role === 'host') put(e.kind === 'chapter' ? 'booktitle' : 'journal', bibText(e.container.title));
    if (role === 'series') put('series', bibText(e.container.title));
    if (e.year != null) put('year', String(e.year));
    if (e.publisher) put('publisher', bibText(e.publisher));
    if (e.isbn) put('isbn', bibText(e.isbn));
    if (e.doi) put('doi', bibRaw(e.doi));
    if (e.url) put('url', bibRaw(e.url));
    if (e.language) put('language', bibText(e.language));
    if (e.flag) put('keywords', bibText('origenality:' + e.flag));
    if (e.abstract) put('abstract', bibText(e.abstract.text));
    put('note', bibText(noteOf(e)));
    return '@' + BIB_TYPE[e.kind] + '{' + e.key + ',\n' + f.join(',\n') + '\n}\n';
  }
  function toBibTeX(entries, opts) {
    var list = prepare(entries);
    var head = ((opts && opts.header) || []).map(function (line) {
      return '% ' + oneLine(line).replace(/@/g, ' at ');
    });
    return (head.length ? head.join('\n') + '\n\n' : '') + list.map(bibEntry).join('\n');
  }

  /* ------------------------------------------------------------------ RIS */
  function risEntry(e) {
    var lines = [];
    function put(tag, value) { if (has(value)) lines.push(tag + '  - ' + oneLine(value)); }
    var role = containerRole(e);
    put('TY', RIS_TYPE[e.kind]);
    put('ID', e.key);
    e.authors.forEach(function (a) { put('AU', a); });
    put('TI', e.title);
    if (role === 'host') put('T2', e.container.title);
    if (role === 'series') put('T3', e.container.title);
    if (e.year != null) put('PY', String(e.year));
    put('PB', e.publisher);
    put('SN', e.isbn);
    put('DO', e.doi);
    put('UR', e.url);
    put('LA', e.language);
    if (e.flag) put('KW', 'origenality:' + e.flag);
    if (e.abstract) put('AB', e.abstract.text);
    put('N1', noteOf(e));
    lines.push('ER  - ');
    return lines.join('\r\n');
  }
  function toRIS(entries) {
    return prepare(entries).map(risEntry).join('\r\n\r\n') + '\r\n';
  }

  /* ------------------------------------------------------------------ CSL-JSON */
  function cslName(a) {
    var at = a.indexOf(',');
    if (at < 0) return { literal: oneLine(a) };
    var family = oneLine(a.slice(0, at)), given = oneLine(a.slice(at + 1));
    if (!family) return { literal: oneLine(a) };
    return given ? { family: family, given: given } : { family: family };
  }
  function cslItem(e) {
    var it = { id: e.key, type: CSL_TYPE[e.kind] };
    var role = containerRole(e);
    if (e.title) it.title = oneLine(e.title);
    if (e.authors.length) it.author = e.authors.map(cslName);
    if (e.year != null) it.issued = { 'date-parts': [[e.year]] };
    if (role === 'host') it['container-title'] = oneLine(e.container.title);
    if (role === 'series') it['collection-title'] = oneLine(e.container.title);
    if (e.publisher) it.publisher = oneLine(e.publisher);
    if (e.isbn) it.ISBN = oneLine(e.isbn);
    if (e.doi) it.DOI = oneLine(e.doi);
    if (e.url) it.URL = oneLine(e.url);
    if (e.language) it.language = oneLine(e.language);
    if (e.flag) it.keyword = 'origenality:' + e.flag;
    if (e.abstract) it.abstract = oneLine(e.abstract.text);
    it.note = noteOf(e);
    return it;
  }
  function toCSL(entries) {
    return JSON.stringify(prepare(entries).map(cslItem), null, 2) + '\n';
  }

  /* ------------------------------------------------------------------ COinS */
  // The OpenURL ContextObject a reference manager reads off the page
  // (<span class="Z3988" title="...">): the same fields as the files.
  function toCOinS(e) {
    var kv = [['ctx_ver', 'Z39.88-2004']];
    function put(k, v) { if (has(v)) kv.push([k, oneLine(v)]); }
    var role = containerRole(e);
    if (e.kind === 'article' || e.kind === 'review') {
      put('rft_val_fmt', 'info:ofi/fmt:kev:mtx:journal');
      put('rft.genre', 'article');
      put('rft.atitle', e.title);
      if (role === 'host') put('rft.jtitle', e.container.title);
    } else if (e.kind === 'chapter') {
      put('rft_val_fmt', 'info:ofi/fmt:kev:mtx:book');
      put('rft.genre', 'bookitem');
      put('rft.atitle', e.title);
      if (role === 'host') put('rft.btitle', e.container.title);
    } else if (e.kind === 'book') {
      put('rft_val_fmt', 'info:ofi/fmt:kev:mtx:book');
      put('rft.genre', 'book');
      put('rft.btitle', e.title);
    } else {
      put('rft_val_fmt', 'info:ofi/fmt:kev:mtx:dc');
      put('rft.type', 'document');
      put('rft.title', e.title);
    }
    if (role === 'series') put('rft.series', e.container.title);
    e.authors.forEach(function (a) { put(e.kind === 'other' ? 'rft.creator' : 'rft.au', a); });
    if (e.year != null) put('rft.date', String(e.year));
    if (e.kind !== 'other') put('rft.pub', e.publisher);
    else put('rft.publisher', e.publisher);
    if (e.kind !== 'other') put('rft.isbn', e.isbn);
    if (e.doi) put('rft_id', 'info:doi/' + e.doi);
    put('rft_id', e.url);
    put('rft.language', e.language);
    return kv.map(function (p) { return encodeURIComponent(p[0]) + '=' + encodeURIComponent(p[1]); }).join('&');
  }

  /* ------------------------------------------------------------------ files */
  function render(format, entries, opts) {
    if (format === 'bibtex') return toBibTeX(entries, opts);
    if (format === 'ris') return toRIS(entries);
    if (format === 'csl') return toCSL(entries);
    throw new Error('unknown format ' + format);
  }
  function fileName(stem, build, format) {
    var slug = words(stem).join('-').slice(0, 48).replace(/-+$/, '') || 'view';
    return 'origenality-' + slug + (build ? '-' + words(build).join('-') : '') + '.' + FORMATS[format].ext;
  }

  return {
    FORMATS: FORMATS, BIB_TYPE: BIB_TYPE, RIS_TYPE: RIS_TYPE, CSL_TYPE: CSL_TYPE,
    containersFromCorpus: containersFromCorpus, citeData: citeData, entryFromRecord: entryFromRecord,
    containerRole: containerRole, noteOf: noteOf,
    fold: fold, baseKey: baseKey, assignKeys: assignKeys,
    bibText: bibText, toBibTeX: toBibTeX, toRIS: toRIS, toCSL: toCSL, toCOinS: toCOinS,
    render: render, fileName: fileName
  };
});
