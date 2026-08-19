/* Origenality — the search, once.
 *
 * The map in the browser and the `origenality` CLI must answer the same
 * question with the same number, or an agent and a reader would be looking at
 * two different bibliographies. So the semantics live here and nowhere else:
 * the page loads this file before explorer.js, the CLI requires it, and
 * scripts/check_search_parity.py fails a release where the two disagree.
 *
 * What the semantics are, and why:
 *
 *   - a term matches at a WORD START, not anywhere inside a word. Substring
 *     matching answered "Rome" with the Jerome bibliography and "man" with
 *     half the corpus, through the indexed language label "german";
 *   - the answer to the question ASKED — the records carrying every term — is
 *     counted before anything is widened, and a widened set never passes for
 *     the answer;
 *   - a term absent from the whole corpus is named. On a map that promises to
 *     show where the scholarship is thin, that is the answer, not a failure;
 *   - the controlled vocabulary (domain, work, approach, theme headings and
 *     their aliases) is a channel of its own, matched as a whole heading. It
 *     used to sit in the free-text index, which made "prière", "Gebet",
 *     "Martyrium" and "vie ascétique" return one and the same set of records:
 *     they are four spellings of a single domain label.
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

  function norm(s) {
    return (s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  }

  function tokens(q) {
    return norm(q).split(/[^0-9a-z']+/).filter(function (w) {
      return w.length > 2 && !STOPSET[w];
    });
  }

  function quote(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  /** A term, anchored at a word start. */
  function termRe(tok) { return new RegExp("(^|[^0-9a-z'])" + quote(tok)); }

  /** A whole heading, bounded at both ends: "Rome" must not answer "Romans". */
  function headingRe(phrase) {
    return new RegExp("(^|[^0-9a-z'])" + quote(phrase) + "([^0-9a-z']|$)");
  }

  /* The relaxation floor: below this many records, widen the query rather than
     leave the reader with nothing to look at. Kept here so the CLI cannot
     drift from the page. */
  var WIDEN_FLOOR = 10;

  /**
   * Score a population against a query.
   *
   * @param records  [{ i, hay, vocab, dens }] — `hay` is the free-text index,
   *                 `vocab` the controlled-vocabulary index, `dens` whether the
   *                 record counts in the density figures.
   * @param query    what the reader typed.
   * @param opts     { keep(record) -> bool } an extra conjunctive filter (the
   *                 four questions in the browser), and { widenFloor }.
   * @returns {{terms, absentTerms, fullHit, hitDepth, relaxed, widened,
   *            matched:Set, scores, vocabOnly:Set, vocabHit, heading}}
   */
  function search(records, query, opts) {
    opts = opts || {};
    var keep = opts.keep || null;
    var floor = opts.widenFloor == null ? WIDEN_FLOOR : opts.widenFloor;

    var toks = tokens(query);
    var res = toks.map(termRe);
    var out = {
      terms: toks, absentTerms: [], fullHit: 0, hitDepth: 0,
      relaxed: false, widened: false, matched: new Set(), scores: {},
      vocabOnly: new Set(), vocabHit: 0, heading: ''
    };

    var phrase = norm(query).trim();
    var vocabSet = null;
    if (phrase.length > 3) {
      var hre = headingRe(phrase);
      vocabSet = new Set();
      records.forEach(function (p) { if (p.vocab && hre.test(p.vocab)) vocabSet.add(p.i); });
      out.vocabHit = vocabSet.size;
      if (out.vocabHit) out.heading = query.trim();
    }

    if (!toks.length && !keep) return out;

    var seen = {};
    records.forEach(function (p) {
      if (keep && !keep(p)) return;
      var sc = 1;
      if (toks.length) {
        sc = 0;
        for (var t = 0; t < toks.length; t++) {
          if (res[t].test(p.hay)) { sc++; seen[t] = 1; }
        }
        // A record reached only through a heading is listed — someone typing
        // "Contre Celse" wants those records — but it is not counted as a
        // textual match, or a domain label would inflate the figure again.
        if (!sc) {
          if (!(vocabSet && vocabSet.has(p.i))) return;
          out.vocabOnly.add(p.i);
        }
      }
      out.scores[p.i] = sc;
      out.matched.add(p.i);
    });

    if (toks.length) {
      out.matched.forEach(function (i) {
        if (!out.vocabOnly.has(i) && out.scores[i] >= toks.length) out.fullHit++;
      });
      for (var t = 0; t < toks.length; t++) if (!seen[t]) out.absentTerms.push(toks[t]);
    } else out.fullHit = out.matched.size;

    if (toks.length > 1 && out.matched.size) {
      for (var need = toks.length; need >= 2; need--) {
        var strict = new Set();
        out.matched.forEach(function (i) {
          if (out.scores[i] >= need || out.vocabOnly.has(i)) strict.add(i);
        });
        if (strict.size >= floor) { out.matched = strict; out.hitDepth = need; break; }
      }
      if (!out.hitDepth) out.hitDepth = 1;
      out.relaxed = out.hitDepth < toks.length;
      out.widened = out.relaxed;
    } else if (toks.length === 1) out.hitDepth = 1;

    return out;
  }

  return {
    STOP: STOP, WIDEN_FLOOR: WIDEN_FLOOR,
    norm: norm, tokens: tokens, termRe: termRe, headingRe: headingRe, search: search
  };
});
