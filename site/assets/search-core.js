/* Origenality — the search, once.
 *
 * The map in the browser and the `origenality` CLI must answer the same
 * question with the same number, or an agent and a reader would be looking at
 * two different bibliographies. So the semantics live here and nowhere else,
 * and so does the index they run on: the page loads this file before
 * explorer.js, the CLI requires it, and scripts/check_search_parity.py fails a
 * release where the two disagree.
 *
 * What the semantics are, and why:
 *
 *   - a term matches at a WORD START, not anywhere inside a word. Substring
 *     matching answered "Rome" with the Jerome bibliography and "man" with
 *     half the corpus, through the indexed language label "german". An elided
 *     article is its own word: "d'Origène" is "d" then "origene", so
 *     "Origène" finds it, whichever apostrophe the cataloguer typed;
 *   - letters that Unicode does not decompose are folded (ß to ss, ł to l,
 *     ø to o, æ to ae, œ to oe, final ς to σ), and Greek or Cyrillic words
 *     are searchable terms like any other;
 *   - a quoted phrase is those words in that order, bounded at both ends like
 *     a heading, and it never runs from one field into the next;
 *   - the answer to the question ASKED (the records carrying every term) is
 *     counted before anything is widened, and a widened set never passes for
 *     the answer. A query is marked widened only when the widening added a
 *     record;
 *   - a term absent from the whole corpus is named. On a map that promises to
 *     show where the scholarship is thin, that is the answer, not a failure.
 *     A term missing only from what the filters leave is reported apart;
 *   - the controlled vocabulary (domain, work, approach, theme headings and
 *     their aliases) is a channel of its own, matched as a whole heading and
 *     counted over the same population as the figure it sits next to;
 *   - a query the grammar cannot honour (unknown field, invalid year, unknown
 *     language, unclosed quotation mark) is not evaluated. It is reported, so
 *     that no reader is shown a zero, or the answer to another question.
 *
 * ------------------------------------------------------------------ API
 *
 * buildIndex(graph, semantic, abstracts, cite) -> { records, keys, fields, ... }
 *   The one index. `graph` is data/graph.json, `semantic` assets/semantic.json,
 *   `abstracts` data/abstracts.json (may be null), `cite` data/cite.json (may be
 *   null). `records` holds one entry per node of kind 'pub', in graph order,
 *   with `i` equal to its position.
 *
 *   graph.json keeps a subject heading only when several records share it and
 *   a container only when more records share it (graph.thresholds), so on its
 *   own it leaves most headings and containers out of the search, and a word a
 *   heading carries would be reported as absent from the corpus. data/cite.json
 *   (version 2, site/build-c/tools/build_cite_data.py) gives every record all
 *   its headings and its container. `fields` says which the index holds:
 *   'complete' once cite.json is read, 'partial' before (or when the file is
 *   missing or of version 1), and a partial index names no term as absent.
 *   Fields: i, nodeIndex, ppn, title, year, lang (canonical code as stored,
 *   '' if none), rawlang (same), type, url, doi, src, sourceIds, publisher,
 *   isbn, authors[], subjects[] (every heading once cite.json is read),
 *   container (the journal or volume, as the map files it), relevance and rel ('none' when
 *   untagged), review, themes[], works[] (the 'unspecified' sentinel removed),
 *   approaches[] and appr (same array), domains[] and doms (same array), dens
 *   (counts in the density figures), ab (the abstract entry or null), abstract,
 *   abstractSource, sortTitle, hay (free-text index), vocab (heading index).
 *   `keys` lists the vocabulary keys a field query may name, per field.
 *
 * applyCite(index, cite) -> index
 *   Completes a partial index in place with data/cite.json: every record gets
 *   all its headings and its container, and its free-text index is written
 *   again. buildIndex(graph, sem, abstracts, cite) is buildIndex without cite
 *   followed by this, so the page, which reads cite.json after its first render,
 *   and the CLI, which reads it at once, end on the same index.
 *
 * searchedFields(index) -> [string]
 *   The fields a free-text term is looked for in, in words, as a surface names
 *   them next to an absent term.
 *
 *   The page adopts it like this, in explorer.js build(g):
 *
 *     var IDX = OrigenalitySearch.buildIndex(g, SEM, ABS);   // partial
 *     PUBS = IDX.records;
   *     PUBS.forEach(function (p) {
 *       p.lkey = lkey(p.rawlang);          // colour key, a field of its own:
 *                                          // lang and rawlang keep the code
 *       // weight, tier, r, wr, o, lobeName ... then attachGrains(p)
 *     });
 *     ...
 *     var r = CORE.search(IDX, query, { keep: keep });
 *
 *   and replaces its emptiness test `!tokens(query).length` with
 *   `CORE.queryIsBlank(query)`, so that `l:fr` or `PG` reach the engine and
 *   come back as an answer or as a reported problem.
 *
 * search(index, query, opts) -> result
 *   `index` is what buildIndex returns, or a bare records array (the older
 *   entry point, still accepted). opts: { keep(record) -> bool, a conjunctive
 *   restriction such as the page's four questions or the CLI's --lang/--since/
 *   --until; widenFloor; universe, the records against which absence is
 *   judged (default: all records); keys, overriding index.keys }.
 *
 *   Result fields:
 *     query              the query as given
 *     terms              searchable terms, normalised
 *     droppedTerms       words removed as too short (under three letters) or
 *                        as stopwords
 *     normalisedEmpty    true when text was typed but no searchable term, filter
 *                        or phrase remains ("PG", "the"): nothing was searched
 *     blank              true when nothing was typed at all
 *     invalid            true when `errors` is not empty; nothing was evaluated
 *     errors             [{ kind, token, field, value, message }], kind one of
 *                        unknown_field, empty_value, unclosed_quote,
 *                        invalid_year, reversed_year_range, unknown_language,
 *                        unknown_type, unknown_key
 *     unknownFields      the field names among them that the grammar lacks
 *     filters            [{ field, value, neg, raw, from, to }] (from/to for year)
 *     phrases, exclude, excludePhrases   normalised strings
 *     matched            Set of record indices listed (hits and heading-only)
 *     scores             { i: number of terms the record carries } (1 for a
 *                        field-only query, 0 for a heading-only record)
 *     order              matched indices in reading order: score descending,
 *                        then year descending (undated last), then title, then i
 *     vocabOnly          Set of indices reached only through a heading
 *     fullHit            records (not heading-only) carrying every term
 *     fullHitCounted     the same, restricted to records that count in density
     *     termHits           per term, parallel to `terms`: records in scope that
 *                        carry it
 *     termHitsCounted    the same, restricted to records that count in density
 *     hitDepth           number of terms the listed set was relaxed to
 *     relaxed, widened   true only when the listed set holds more textual
 *                        matches than fullHit
 *     absentTerms        terms found in no record of the universe (hay or vocab);
 *                        empty on a partial index
 *     absentFromPartialIndex  the same terms on a partial index: not found in
 *                        what it holds, which is not the whole record
 *     fields             'complete' or 'partial', the index searched
 *     absentUnderFilters terms present in the corpus but in no record that
 *                        keep and the field filters leave
     *     vocabHit           records in scope filed under the heading typed
 *     vocabHitCounted    the same, restricted to records that count in density:
 *                        the figure a surface prints as a count
 *     vocabHitAll        the same as vocabHit over the universe, ignoring keep
 *     heading            the heading as typed, outer punctuation trimmed
 *
 * Other exports: norm, tokens, splitWords, termRe, phraseRe, headingRe,
 * parseQuery, queryIsBlank, languageCode, resolveLanguage, isDated, compareHits,
 * applyCite, searchedFields, STOP, WIDEN_FLOOR, FIELDS, LANG_ALIASES, FIELD_SEP,
 * CITE_SCHEMA.
 *
 * Romain Girardi, 2026.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.OrigenalitySearch = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var STOP = ('the and for with from that this was are its our not but all any how who '
    + 'des les une dans pour sur avec par aux ses est comme entre chez '
    + 'der die das und von den dem ein eine des mit auf ist als bei aus '
    + 'che del della dei con per una nel nella sul '
    + 'los las una del por con para sobre entre').split(' ');
  var STOPSET = {};
  STOP.forEach(function (w) { STOPSET[w] = 1; });

  /* Letters NFD leaves whole. Folded on both sides, the index and the query,
     so "Buße" finds "Bußlehre" and "Busse" finds both. */
  var FOLD = {
    '\u00df': 'ss', '\u0142': 'l', '\u0140': 'l', '\u00f8': 'o', '\u00e6': 'ae',
    '\u0153': 'oe', '\u0111': 'd', '\u00f0': 'd', '\u00fe': 'th', '\u0131': 'i',
    '\u03c2': '\u03c3'
  };
  var FOLD_RE = /[\u00df\u0142\u0140\u00f8\u00e6\u0153\u0111\u00f0\u00fe\u0131\u03c2]/g;
  // every apostrophe a catalogue uses, typed or typographic, ends a word
  var APOS_RE = /['`\u00b4\u2018\u2019\u02bb\u02bc]/g;
  var MARKS_RE = /\p{M}+/gu;

  function norm(s) {
    return String(s == null ? '' : s).toLowerCase().normalize('NFD')
      .replace(MARKS_RE, '')
      .replace(FOLD_RE, function (c) { return FOLD[c]; })
      .replace(APOS_RE, ' ');
  }

  var NONWORD_SPLIT = /[^\p{L}\p{N}]+/u;
  var WORD = '\\p{L}\\p{N}';
  /* Fields of a record are joined with a separator no text contains, so a
     phrase cannot start in a title and end in an author's name. */
  var FIELD_SEP = ' \u001f ';
  // between two words of a phrase: any run of non-letters, except a field or
  // label separator
  var GAP = '[^' + WORD + '\\u001f\\u00b7]+';

  function splitWords(q) {
    return norm(q).split(NONWORD_SPLIT).filter(Boolean);
  }
  function keepWord(w) { return w.length > 2 && !STOPSET[w]; }

  function tokens(q) { return splitWords(q).filter(keepWord); }

  function quote(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  var NEVER = /(?!)/;

  /** A term, or several words in order, anchored at a word start. */
  function prefixRe(words) {
    if (typeof words === 'string') words = splitWords(words);
    if (!words.length) return NEVER;
    return new RegExp('(^|[^' + WORD + '])' + words.map(quote).join(GAP), 'u');
  }
  function termRe(tok) { return prefixRe(tok); }

  /** Words in order, bounded at both ends: "Rome" must not answer "Romans". */
  function phraseRe(phrase) {
    var words = typeof phrase === 'string' ? splitWords(phrase) : phrase;
    if (!words.length) return NEVER;
    return new RegExp('(^|[^' + WORD + '])' + words.map(quote).join(GAP) + '(?![' + WORD + '])', 'u');
  }
  var headingRe = phraseRe;

  /* ---------------------------------------------------------------- grammar
   * A reader looking for one publication does not want a neighbourhood, they
   * want that publication. So a query may name the field it is about:
   *
   *   author:crouzel            the author, matched at a word start
   *   year:1971  year:1971-1990 a year or a range; year:<1900, year:>=2000
   *   lang:fr                   the ISO 639 language code (fre, ger, arm... and
   *                             English names such as "french" are accepted)
   *   type:book                 the document type
   *   work:cels                 a work of Origen, by vocabulary key
   *   theme:exegesis.allegory   a theme, by key (a prefix is enough)
   *   in:journal-name           the containing volume or journal
   *   "free will"               an exact phrase, in that order
   *   -rufinus                  a term that must NOT appear
   *
   * Anything outside a field is free text, scored as before. Filters are
   * conjunctive and never relaxed: a reader who wrote year:1971 did not mean
   * "or thereabouts", and the widening that helps a described project would be
   * a lie here. A year condition holds only for a dated record.
   */
  var FIELDS = {
    author: 'authors', a: 'authors',
    year: 'year', y: 'year',
    lang: 'lang', l: 'lang',
    type: 'type', t: 'type',
    work: 'works', w: 'works',
    theme: 'themes',
    domain: 'domains',
    approach: 'approaches',
    in: 'container'
  };
  var FIELD_LIST = 'author:, year:, lang:, type:, work:, theme:, domain:, approach:, in:';
  var KEY_NOUN = { works: 'work', themes: 'theme', domains: 'domain', approaches: 'approach' };

  // ISO 639-2 bibliographic and terminological codes, to their ISO 639-1 code
  var LANG_ALIASES = {
    eng: 'en', ger: 'de', deu: 'de', fre: 'fr', fra: 'fr', ita: 'it', spa: 'es',
    dut: 'nl', nld: 'nl', por: 'pt', rum: 'ro', ron: 'ro', gre: 'el', ell: 'el',
    arm: 'hy', hye: 'hy', lat: 'la', heb: 'he', pol: 'pl', rus: 'ru', cze: 'cs',
    ces: 'cs', hun: 'hu', cat: 'ca', swe: 'sv', dan: 'da', nor: 'no', fin: 'fi',
    ara: 'ar', jpn: 'ja', chi: 'zh', zho: 'zh', kor: 'ko', geo: 'ka', kat: 'ka',
    hrv: 'hr', slv: 'sl', srp: 'sr', alb: 'sq', sqi: 'sq', bul: 'bg', ukr: 'uk',
    tur: 'tr', per: 'fa', fas: 'fa', wel: 'cy', cym: 'cy', gle: 'ga', ice: 'is',
    isl: 'is', slo: 'sk', slk: 'sk', mac: 'mk', mkd: 'mk', baq: 'eu', eus: 'eu',
    glg: 'gl', est: 'et', lav: 'lv', lit: 'lt', mlt: 'mt', afr: 'af', bel: 'be',
    bos: 'bs', ind: 'id', vie: 'vi', hin: 'hi'
  };
  var LANG_NAMES = {
    english: 'en', german: 'de', deutsch: 'de', french: 'fr', francais: 'fr',
    italian: 'it', italiano: 'it', spanish: 'es', espanol: 'es', latin: 'la',
    dutch: 'nl', portuguese: 'pt', romanian: 'ro', russian: 'ru', polish: 'pl',
    hungarian: 'hu', czech: 'cs', danish: 'da', norwegian: 'no', hebrew: 'he',
    japanese: 'ja', korean: 'ko', croatian: 'hr', arabic: 'ar', armenian: 'hy',
    syriac: 'syr'
  };
  var ISO1 = {};
  ('aa ab ae af ak am an ar as av ay az ba be bg bi bm bn bo br bs ca ce ch co cr cs cu '
    + 'cv cy da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he '
    + 'hi ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja jv ka kg ki kj kk kl km kn ko '
    + 'kr ks ku kv kw ky la lb lg li ln lo lt lu lv mg mh mi mk ml mn mr ms mt my na nb nd '
    + 'ne ng nl nn no nr nv ny oc oj om or os pa pi pl ps pt qu rm rn ro ru rw sa sc sd se '
    + 'sg si sk sl sm sn so sq sr ss st su sv sw ta te tg th ti tk tl tn to tr ts tt tw ty '
    + 'ug uk ur uz ve vi vo wa wo xh yi yo za zh zu').split(' ')
    .forEach(function (c) { ISO1[c] = 1; });

  /** A stored or typed code, in its canonical form. Never fails. */
  function languageCode(value) {
    value = norm(value).trim();
    return LANG_ALIASES[value] || value;
  }

  /** What a reader typed after lang: or --lang, as a code; null if it is none. */
  function resolveLanguage(value) {
    var v = norm(value).replace(/\s+/g, ' ').trim();
    if (!v) return null;
    if (LANG_ALIASES[v]) return LANG_ALIASES[v];
    if (LANG_NAMES[v]) return LANG_NAMES[v];
    if (/^[a-z]{2}$/.test(v)) return ISO1[v] ? v : null;
    if (/^[a-z]{3}$/.test(v)) return v;
    return null;
  }

  function isDated(rec) {
    return rec != null && rec.year != null && rec.year !== '' && isFinite(Number(rec.year));
  }

  var OPENERS = { '"': '"\u201d\u201c', '\u201c': '\u201d"\u201c', '\u201d': '\u201d"',
                  '\u201e': '\u201c\u201d"', '\u00ab': '\u00bb' };

  function problem(out, kind, token, field, value, message) {
    out.errors.push({ kind: kind, token: token, field: field || null,
                      value: value == null ? null : value, message: message });
  }

  function parseYear(out, token, value, neg) {
    var v = value.replace(/\s+/g, '');
    var m;
    var f = { field: 'year', value: v, neg: neg, raw: value, from: null, to: null };
    if ((m = /^(\d{3,4})[-–](\d{3,4})$/.exec(v))) {
      f.from = Number(m[1]); f.to = Number(m[2]);
      if (f.from > f.to) {
        problem(out, 'reversed_year_range', token, 'year', value,
          'The year range ' + v + ' runs backwards; write year:' + m[2] + '-' + m[1] + '.');
        return;
      }
    } else if ((m = /^([<>]=?)(\d{3,4})$/.exec(v))) {
      var n = Number(m[2]);
      if (m[1] === '<') f.to = n - 1;
      else if (m[1] === '<=') f.to = n;
      else if (m[1] === '>') f.from = n + 1;
      else f.from = n;
    } else if (/^\d{3,4}$/.test(v)) {
      f.from = f.to = Number(v);
    } else {
      problem(out, 'invalid_year', token, 'year', value,
        'Invalid year "' + value + '"; use year:1971, year:1971-1990, year:<1900 or year:>=2000.');
      return;
    }
    out.filters.push(f);
  }

  function parseQuery(q) {
    var out = { free: '', phrases: [], exclude: [], excludePhrases: [], filters: [],
                errors: [], unknownFields: [] };
    var s = String(q == null ? '' : q);
    var rest = [];
    var i = 0, len = s.length;
    var space = /\s/;
    while (i < len) {
      while (i < len && space.test(s[i])) i++;
      if (i >= len) break;
      var start = i, neg = false, name = null;
      if (s[i] === '-' && i + 1 < len && !space.test(s[i + 1])) { neg = true; i++; }
      var fm = /^([A-Za-z]+):/.exec(s.slice(i, i + 40));
      if (fm) {
        var after = i + fm[0].length;
        var known = FIELDS[fm[1].toLowerCase()];
        if (after < len && !space.test(s[after])) { name = fm[1]; i = after; }
        else if (known) {
          // a field named and left empty
          problem(out, 'empty_value', s.slice(start, after), known, '',
            '"' + fm[0] + '" has no value.');
          i = after;
          continue;
        }
      }
      var value, quoted = false, closed = true;
      var closers = OPENERS[s[i]];
      if (closers) {
        quoted = true;
        var end = -1;
        for (var j = i + 1; j < len; j++) if (closers.indexOf(s[j]) >= 0) { end = j; break; }
        if (end < 0) { closed = false; value = s.slice(i + 1); i = len; }
        else { value = s.slice(i + 1, end); i = end + 1; }
      } else {
        var k = i;
        while (k < len && !space.test(s[k])) k++;
        value = s.slice(i, k); i = k;
      }
      var token = s.slice(start, i);

      if (name) {
        var field = FIELDS[name.toLowerCase()];
        if (!field) {
          out.unknownFields.push(name.toLowerCase());
          problem(out, 'unknown_field', token, name.toLowerCase(), value,
            'Unknown field "' + name + ':"; the fields are ' + FIELD_LIST + '.');
          continue;
        }
        if (!closed) {
          problem(out, 'unclosed_quote', token, field, value,
            'A quotation mark is opened and not closed in ' + token + '.');
          continue;
        }
        if (!value.trim()) {
          problem(out, 'empty_value', token, field, '', '"' + name + ':" has no value.');
          continue;
        }
        if (field === 'year') { parseYear(out, token, value, neg); continue; }
        if (field === 'lang') {
          var code = resolveLanguage(value);
          if (!code) {
            problem(out, 'unknown_language', token, 'lang', value,
              'Unknown language "' + value + '"; use an ISO 639 code such as en, fr, de, la or grc.');
            continue;
          }
          out.filters.push({ field: 'lang', value: code, neg: neg, raw: value });
          continue;
        }
        if (KEY_NOUN[field]) {
          out.filters.push({ field: field, value: norm(value).trim(), neg: neg, raw: value });
          continue;
        }
        var fw = splitWords(value);
        if (!fw.length) {
          problem(out, 'empty_value', token, field, value, '"' + name + ':" has no searchable word.');
          continue;
        }
        out.filters.push({ field: field, value: fw.join(' '), neg: neg, raw: value });
        continue;
      }

      if (quoted) {
        if (!closed) {
          problem(out, 'unclosed_quote', token, null, value,
            'A quotation mark is opened and not closed in ' + token + '.');
          continue;
        }
        var pw = splitWords(value);
        if (!pw.length) {
          problem(out, 'empty_value', token, null, value, 'The quotation marks hold no searchable word.');
          continue;
        }
        (neg ? out.excludePhrases : out.phrases).push(pw.join(' '));
        continue;
      }
      if (neg) {
        var ew = splitWords(value);
        if (ew.length) { out.exclude.push(ew.join(' ')); continue; }
      }
      rest.push(neg ? '-' + value : value);
    }
    out.free = rest.join(' ');
    return out;
  }

  /** True when the query holds nothing at all: no word, no field, no quotation. */
  function queryIsBlank(q) {
    var p = parseQuery(q);
    return !p.free.trim() && !p.filters.length && !p.phrases.length && !p.exclude.length
      && !p.excludePhrases.length && !p.errors.length;
  }

  function listOf(rec, field) {
    if (field === 'approaches') return rec.approaches || rec.appr || [];
    if (field === 'domains') return rec.domains || rec.doms || [];
    return rec[field] || [];
  }

  function fieldValue(rec, field) {
    var v = rec[field];
    if (v == null) return '';
    if (Array.isArray(v)) return norm(v.join(FIELD_SEP));
    return norm(String(v));
  }

  function recordLang(rec) {
    return languageCode(rec.rawlang != null ? rec.rawlang : rec.lang);
  }

  function passesFilter(rec, f) {
    var ok;
    if (f.field === 'year') {
      // an undated record is not known to be before 1900, nor after it
      if (!isDated(rec)) return false;
      var y = Number(rec.year);
      ok = (f.from == null || y >= f.from) && (f.to == null || y <= f.to);
    } else if (KEY_NOUN[f.field]) {
      // a key, or the beginning of one: theme:exegesis catches every theme of
      // that domain without the reader having to know the full key
      ok = listOf(rec, f.field).some(function (k) { return norm(k).indexOf(f.value) === 0; });
    } else if (f.field === 'lang') {
      ok = recordLang(rec) === f.value;
    } else {
      if (!f.re) f.re = prefixRe(f.value);
      ok = f.re.test(fieldValue(rec, f.field));
    }
    return f.neg ? !ok : ok;
  }

  /* Checks that need the corpus: a type or a vocabulary key nobody could reach
     is a mistyped query, and a zero would read as thin ground. */
  function validateAgainst(q, universe, keys) {
    var types = null, derived = null;
    q.filters.forEach(function (f) {
      if (f.field === 'type') {
        if (!types) {
          types = {};
          universe.forEach(function (p) { if (p.type) types[norm(p.type)] = 1; });
        }
        var re = prefixRe(f.value);
        var names = Object.keys(types).sort();
        if (!names.some(function (t) { return re.test(t); })) {
          problem(q, 'unknown_type', (f.neg ? '-' : '') + 'type:' + f.raw, 'type', f.raw,
            'Unknown document type "' + f.raw + '"; the types in this corpus are '
            + names.join(', ') + '.');
        }
      } else if (KEY_NOUN[f.field]) {
        var list = keys && keys[f.field];
        if (!list) {
          if (!derived) {
            derived = { works: {}, themes: {}, domains: {}, approaches: {} };
            universe.forEach(function (p) {
              Object.keys(derived).forEach(function (fl) {
                listOf(p, fl).forEach(function (k) { derived[fl][k] = 1; });
              });
            });
          }
          list = Object.keys(derived[f.field]);
        }
        if (!f.value || !list.some(function (k) { return norm(k).indexOf(f.value) === 0; })) {
          problem(q, 'unknown_key', (f.neg ? '-' : '') + KEY_NOUN[f.field] + ':' + f.raw,
            f.field, f.raw,
            'No ' + KEY_NOUN[f.field] + ' in the vocabulary has a key starting with "' + f.raw + '".');
        }
      }
    });
  }

  /** Reading order: score, then newest first (undated last), then title. */
  function compareHits(a, b, scores) {
    var sa = scores ? scores[a.i] || 0 : 0, sb = scores ? scores[b.i] || 0 : 0;
    if (sb !== sa) return sb - sa;
    var ya = isDated(a) ? Number(a.year) : -Infinity, yb = isDated(b) ? Number(b.year) : -Infinity;
    if (yb !== ya) return yb > ya ? 1 : -1;
    var ta = a.sortTitle != null ? a.sortTitle : norm(a.title);
    var tb = b.sortTitle != null ? b.sortTitle : norm(b.title);
    if (ta !== tb) return ta < tb ? -1 : 1;
    return a.i - b.i;
  }

  /* The relaxation floor: below this many records, widen the query rather than
     leave the reader with nothing to look at. Kept here so the CLI cannot
     drift from the page. */
  var WIDEN_FLOOR = 10;

  function search(index, query, opts) {
    opts = opts || {};
    var isArr = Array.isArray(index);
    var records = isArr ? index : (index && index.records) || [];
    // a partial index (graph.json without cite.json) holds only the headings
    // and containers several records share: a term it lacks may be in a record
    var partial = !isArr && !!index && index.fields === 'partial';
    var keys = opts.keys || (!isArr && index && index.keys) || null;
    var universe = opts.universe || records;
    var keep = opts.keep || null;
    var floor = opts.widenFloor == null ? WIDEN_FLOOR : opts.widenFloor;

    var q = parseQuery(query);
    var words = splitWords(q.free);
    var toks = words.filter(keepWord);
    var dropped = [];
    words.forEach(function (w) { if (!keepWord(w) && dropped.indexOf(w) < 0) dropped.push(w); });
    validateAgainst(q, universe, keys);

    var structured = q.filters.length || q.phrases.length || q.exclude.length
      || q.excludePhrases.length;
    var out = {
      query: String(query == null ? '' : query),
      terms: toks, droppedTerms: dropped,
      normalisedEmpty: false, blank: false,
      invalid: q.errors.length > 0, errors: q.errors, unknownFields: q.unknownFields,
      filters: q.filters, phrases: q.phrases, exclude: q.exclude, excludePhrases: q.excludePhrases,
      matched: new Set(), scores: {}, order: [], vocabOnly: new Set(),
      fullHit: 0, fullHitCounted: 0, termHits: toks.map(function () { return 0; }),
      termHitsCounted: toks.map(function () { return 0; }),
      hitDepth: 0, relaxed: false, widened: false,
      absentTerms: [], absentUnderFilters: [], absentFromPartialIndex: [],
      fields: partial ? 'partial' : 'complete',
      vocabHit: 0, vocabHitCounted: 0, vocabHitAll: 0, heading: ''
    };
    if (out.invalid) return out;
    if (!toks.length && !structured) {
      if (q.free.trim()) out.normalisedEmpty = true;
      else out.blank = true;
      if (!keep) return out;
    }

    // A reader who writes operators is naming a field, not a shelf: the
    // controlled-vocabulary channel would only add noise to a precise query.
    // The heading is the words typed, whatever punctuation surrounds them
    // ("Contre Celse ?" is the heading "Contre Celse").
    // A leading elided article is not part of the heading: "d'Origène" and
    // "l'Église" name the headings "Origène" and "Église".
    var headWords = words.slice();
    while (headWords.length > 1 && headWords[0].length === 1) headWords.shift();
    var vocabSet = null;
    if (headWords.join(' ').length > 3 && !structured) {
      var hre = phraseRe(headWords);
      vocabSet = new Set();
      universe.forEach(function (p) {
        if (!p.vocab || !hre.test(p.vocab)) return;
        out.vocabHitAll++;
        if (keep && !keep(p)) return;
        vocabSet.add(p.i);
        if (p.dens) out.vocabHitCounted++;
      });
      out.vocabHit = vocabSet.size;
      if (out.vocabHitAll) {
        out.heading = q.free.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '');
      }
    }

    var res = toks.map(function (t) { return prefixRe([t]); });
    var phraseRes = q.phrases.map(function (s) { return phraseRe(s); });
    var exclRes = q.exclude.map(function (s) { return prefixRe(s); });
    var exclPhraseRes = q.excludePhrases.map(function (s) { return phraseRe(s); });

    // Field filters, exact phrases and exclusions are conditions, not scores:
    // they hold whatever the widening does below.
    function admissible(p) {
      var hay = p.hay || '';
      for (var i = 0; i < q.filters.length; i++) if (!passesFilter(p, q.filters[i])) return false;
      for (var j = 0; j < phraseRes.length; j++) if (!phraseRes[j].test(hay)) return false;
      for (var k = 0; k < exclRes.length; k++) if (exclRes[k].test(hay)) return false;
      for (var m = 0; m < exclPhraseRes.length; m++) if (exclPhraseRes[m].test(hay)) return false;
      return true;
    }

    var byI = {};
    records.forEach(function (p) {
      if (keep && !keep(p)) return;
      if (!admissible(p)) return;
      var sc = 1;
      if (toks.length) {
        sc = 0;
        for (var t = 0; t < toks.length; t++) {
          if (res[t].test(p.hay || '')) {
            sc++; out.termHits[t]++;
            if (p.dens) out.termHitsCounted[t]++;
          }
        }
        // A record reached only through a heading is listed (someone typing
        // "Contre Celse" wants those records) but it is not counted as a
        // textual match, or a domain label would inflate the figure again.
        if (!sc) {
          if (!(vocabSet && vocabSet.has(p.i))) return;
          out.vocabOnly.add(p.i);
        }
      }
      byI[p.i] = p;
      out.scores[p.i] = sc;
      out.matched.add(p.i);
    });

    if (toks.length) {
      out.matched.forEach(function (i) {
        if (!out.vocabOnly.has(i) && out.scores[i] >= toks.length) {
          out.fullHit++;
          if (byI[i].dens) out.fullHitCounted++;
        }
      });
      // Absence is judged against the whole corpus, not against what the
      // filters leave: "in none of the records" has to be true.
      toks.forEach(function (tok, t) {
        var re = res[t];
        var present = universe.some(function (p) {
          return re.test(p.hay || '') || re.test(p.vocab || '');
        });
        if (!present) (partial ? out.absentFromPartialIndex : out.absentTerms).push(tok);
        else if (!out.termHits[t] && (keep || structured)) out.absentUnderFilters.push(tok);
      });
    } else {
      out.fullHit = out.matched.size;
      out.matched.forEach(function (i) { if (byI[i].dens) out.fullHitCounted++; });
    }

    if (toks.length > 1 && out.matched.size) {
      for (var need = toks.length; need >= 2; need--) {
        var strict = new Set();
        out.matched.forEach(function (i) {
          if (out.scores[i] >= need || out.vocabOnly.has(i)) strict.add(i);
        });
        if (strict.size >= floor) { out.matched = strict; out.hitDepth = need; break; }
      }
      if (!out.hitDepth) out.hitDepth = 1;
      // Widened means the list holds a record that does not carry every term.
      var listedText = 0;
      out.matched.forEach(function (i) { if (!out.vocabOnly.has(i)) listedText++; });
      out.relaxed = out.hitDepth < toks.length && listedText > out.fullHit;
      if (!out.relaxed) out.hitDepth = toks.length;
      out.widened = out.relaxed;
    } else if (toks.length === 1) out.hitDepth = 1;

    var list = [];
    out.matched.forEach(function (i) { list.push(byI[i]); });
    list.sort(function (a, b) { return compareHits(a, b, out.scores); });
    out.order = list.map(function (p) { return p.i; });
    return out;
  }

  /* ------------------------------------------------------------------ index
   * Built once, here, for the page and for the CLI. Two indexes per record,
   * not one. `hay` holds what a record is ABOUT closely enough to answer a
   * free-text search: title, authors, subjects, container, year, language
   * label, theme labels, abstract. The controlled vocabulary (the domain a
   * theme belongs to, the work, the approach, and every alias) goes to `vocab`,
   * matched as a whole phrase and counted in its own channel. Folding a domain
   * label into the free-text index made "prière", "Gebet", "Martyrium" and
   * "vie ascétique" return the same records, because they are all spellings of
   * one domain label.
   */
  var HAY_LANG = { en: 'English', de: 'German', it: 'Italian', fr: 'French', es: 'Spanish' };
  var OTHER_LANG = 'Other or none';
  // "No specific work / Origen in general" is a sentinel of the tagging, not a
  // heading: indexed, it would file three records in four under "origen".
  var EXCLUDED_WORKS = { unspecified: 1 };

  function labelsOf(entry, withAliases) {
    if (!entry) return [];
    var out = [entry.label];
    if (entry.labels) ['de', 'fr', 'it'].forEach(function (k) { out.push(entry.labels[k]); });
    if (withAliases && entry.aliases) out = out.concat(entry.aliases);
    return out.filter(Boolean);
  }

  /* data/cite.json of this version carries every heading and container */
  var CITE_SCHEMA = 'origenality-cite/2';

  // What a free-text term is looked for in, in the order hayOf joins it.
  function hayOf(p, sem) {
    var TH = (sem && sem.themes) || {};
    var semWords = [];
    p.themes.forEach(function (t) { semWords = semWords.concat(labelsOf(TH[t], false)); });
    var parts = [p.title].concat(p.authors, p.subjects, [p.container,
      p.year == null ? '' : String(p.year), HAY_LANG[p.lang] || OTHER_LANG], semWords, [p.abstract]);
    return norm(parts.filter(function (x) { return x != null && x !== ''; }).join(FIELD_SEP));
  }

  function searchedFields(index) {
    var t = (index && !Array.isArray(index) && index.thresholds) || {};
    if (index && !Array.isArray(index) && index.fields === 'partial') {
      return ['title', 'authors',
        'subject headings shared by ' + (t.subject_min_publications || 'several') + ' or more records',
        'journals and volumes shared by ' + (t.container_min_publications || 'several') + ' or more records',
        'year', 'language', 'theme labels', 'abstract'];
    }
    return ['title', 'authors', 'subject headings', 'journal or volume', 'year', 'language',
      'theme labels', 'abstract'];
  }

  function applyCite(index, cite) {
    if (!index || Array.isArray(index)) return index;
    var by = cite && cite.schema === CITE_SCHEMA && cite.byPpn;
    if (!by || typeof by !== 'object') return index;
    index.records.forEach(function (p) {
      var r = by[p.ppn] || {};
      p.subjects = Array.isArray(r.s)
        ? r.s.filter(function (x) { return typeof x === 'string' && x !== ''; }) : [];
      p.container = typeof r.in === 'string' ? r.in : (typeof r.c === 'string' ? r.c : '');
      p.hay = hayOf(p, index.sem);
    });
    index.fields = 'complete';
    return index;
  }

  function buildIndex(graph, sem, abstracts, cite) {
    var N = (graph && graph.nodes) || [], E = (graph && graph.edges) || [];
    sem = sem || {};
    var TH = sem.themes || {}, WK = sem.works || {}, AP = sem.approaches || {}, DM = sem.domains || {};
    var tags = sem.byPpn || {};
    var byPpn = (abstracts && abstracts.byPpn) || {};

    var aut = {}, sub = {}, inn = {};
    E.forEach(function (e) {
      var m = e.r === 'sub' ? sub : e.r === 'aut' ? aut : inn;
      (m[e.s] || (m[e.s] = [])).push(e.t);
    });
    function labels(ids) {
      return (ids || []).map(function (t) { return N[t] ? N[t].label : ''; }).filter(Boolean);
    }

    var records = [];
    N.forEach(function (n, ni) {
      if (!n || n.k !== 'pub') return;
      var tag = tags[n.ppn] || { r: 'none' };
      var themes = (tag.t || []).filter(function (t) { return TH[t]; });
      var works = (tag.w || []).filter(function (w) { return WK[w] && !EXCLUDED_WORKS[w]; });
      var appr = (tag.a || []).filter(function (a) { return AP[a]; });
      var doms = [], seenDom = {};
      themes.forEach(function (t) {
        var d = TH[t].domain;
        if (d && !seenDom[d]) { seenDom[d] = 1; doms.push(d); }
      });
      var authors = labels(aut[ni]), subjects = labels(sub[ni]);
      var container = labels(inn[ni])[0] || '';
      var ab = byPpn[n.ppn] || null;
      var lang = n.lang || '';

      var vocabWords = [];
      themes.forEach(function (t) { vocabWords = vocabWords.concat(labelsOf(TH[t], true)); });
      doms.forEach(function (d) { vocabWords = vocabWords.concat(labelsOf(DM[d], true)); });
      works.forEach(function (w) { vocabWords = vocabWords.concat(labelsOf(WK[w], true)); });
      appr.forEach(function (a) { vocabWords = vocabWords.concat(labelsOf(AP[a], true)); });

      var rec = {
        i: records.length, nodeIndex: ni,
        ppn: n.ppn, title: n.title, year: n.year, lang: lang, rawlang: lang,
        type: n.type, url: n.url || '', doi: n.doi || '',
        src: (n.src && n.src[0]) || '', sourceIds: n.source_ids || [],
        publisher: n.pub || '', isbn: n.isbn || '',
        authors: authors, subjects: subjects, container: container,
        relevance: tag.r || 'none', rel: tag.r || 'none', review: !!tag.n,
        themes: themes, works: works, approaches: appr, appr: appr, domains: doms, doms: doms,
        dens: tag.r === 'core' || tag.r === 'partial',
        ab: ab, abstract: ab && ab.t ? ab.t : '', abstractSource: ab && ab.s ? ab.s : '',
        sortTitle: norm(n.title),
        hay: '',
        vocab: norm(vocabWords.join(FIELD_SEP))
      };
      rec.hay = hayOf(rec, sem);
      records.push(rec);
    });

    var index = {
      records: records,
      keys: {
        works: Object.keys(WK).filter(function (w) { return !EXCLUDED_WORKS[w]; }),
        themes: Object.keys(TH), domains: Object.keys(DM), approaches: Object.keys(AP)
      },
      fields: 'partial', sem: sem, thresholds: (graph && graph.thresholds) || null
    };
    return cite ? applyCite(index, cite) : index;
  }

  return {
    STOP: STOP, WIDEN_FLOOR: WIDEN_FLOOR, FIELDS: FIELDS, LANG_ALIASES: LANG_ALIASES,
    FIELD_SEP: FIELD_SEP,
    norm: norm, tokens: tokens, splitWords: splitWords,
    termRe: termRe, phraseRe: phraseRe, headingRe: headingRe,
    parseQuery: parseQuery, queryIsBlank: queryIsBlank,
    languageCode: languageCode, resolveLanguage: resolveLanguage, isDated: isDated,
    compareHits: compareHits, buildIndex: buildIndex, search: search,
    applyCite: applyCite, searchedFields: searchedFields, CITE_SCHEMA: CITE_SCHEMA
  };
});
