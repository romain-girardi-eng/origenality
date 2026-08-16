#!/usr/bin/env python3
"""Origenality — les chiffres publiés par les pages, écrits par la machine.

L'audit 3 relève que Method et Credits annoncent 152 résumés d'IxTheo et 210
d'ailleurs, alors que la ventilation PAR BASE des données publiées en donne
d'autres. Les deux chiffres sont vrais mais ne répondent pas à la même question :
152 / 210 disent d'où le résumé est ARRIVÉ dans le fichier — de la notice IxTheo
elle-même, ou joint depuis le corpus fédéré —, tandis que la ventilation par base
dit QUI l'a écrit. Un résumé d'IxTheo peut arriver par la jointure ; il reste
d'IxTheo. Publier l'un sous le nom de l'autre, c'est se tromper de question.

Ce script tranche en supprimant la saisie à la main. Il lit
`site/data/abstracts.json`, compte, et réécrit des blocs balisés dans les pages :

    <!-- FIGURES:summary-provenance --> … <!-- /FIGURES:summary-provenance -->

Le texte entre les balises est produit ici, jamais tapé ailleurs. Relancer le
script après une reconstruction des données remet les pages d'aplomb ; ne pas le
relancer se voit, puisque les chiffres du bloc ne bougent pas alors que le
fichier de données a bougé — `--check` le dit et sort en 1.

Trois familles de blocs sont produites par le même mécanisme :

- `FIGURES:summary-provenance` — la provenance des résumés ;
- `FIGURES:citation-coverage` — la couverture des citations, qui annonçait encore
  42 246 grappes et deux pourcentages par langue périmés après une refonte de la
  fusion ;
- `FIGURES:population-*` — la population comptée, ajoutée quand le site est passé
  sur la vague 2 fédérée. Ces trois nombres (comptées, mentionnées seulement, hors
  compte) étaient tapés à la main dans quatre pages, si bien que `build_semantic.py`
  refusait d'écrire dès que la donnée bougeait : le garde-fou était honnête et le
  site ne pouvait plus suivre ses propres tags. Ils sont désormais produits ici,
  avec la ventilation des notices marquées pour relecture et la composition du
  réservoir.

`--check` porte sur les trois familles, et sort en 1 si une seule page est périmée.

    python3 site/build-c/tools/build_summary_figures.py
    python3 site/build-c/tools/build_summary_figures.py --check
    python3 site/build-c/tools/build_summary_figures.py --build /tmp/copie
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE.parent
sys.path.insert(0, str(HERE))
from tree_paths import data_dir, repository_root  # noqa: E402

# La racine se cherche à ses documents, elle ne se compte pas en marches :
# l'outil vit sous `site/build-c/tools/` dans le dépôt de travail et sous
# `site/tools/` dans l'arbre public, et compter les marches désignait, dans un
# clone public, le répertoire au-dessus du dépôt (audit 6). Voir `tree_paths`.
ROOT = Path(repository_root(str(HERE)))
DATA = Path(data_dir(str(ROOT)))
ABSTRACTS = DATA / "abstracts.json"
CORPUS = ROOT / "data" / "merged" / "corpus.jsonl"

CITATIONS = ROOT / "data" / "derived" / "citations_coverage.json"
GRAPH = DATA / "graph.json"
# Les vagues de classification livrées : les chiffres du README, de la méthode
# et de la citation se comptent là, jamais à la main.
WAVES = sorted((ROOT / "semantic" / "waves").glob("*/tags.jsonl"))

MARK = "FIGURES:summary-provenance"
CITE_MARK = "FIGURES:citation-coverage"


def marks(name: str) -> tuple[str, str]:
    """Balises ouvrante et fermante d'un bloc généré."""
    return "<!-- %s -->" % name, "<!-- /%s -->" % name


OPEN, CLOSE = marks(MARK)
MD_OPEN, MD_CLOSE = marks(MARK)
CITE_OPEN, CITE_CLOSE = marks(CITE_MARK)

COUNTED_CLASSES = ("core", "partial")

# Les six couleurs de la légende, dans l'ordre où les pages les impriment.
LEGEND_LANGUAGES = (("eng", "English"), ("ger", "German"), ("ita", "Italian"),
                    ("fre", "French"), ("spa", "Spanish"), ("oth", "Other or none"))

# Les quatre motifs que le prompt v2 attache à une notice classée hors compte.
# Liste fermée : un motif inconnu est nommé tel quel plutôt que traduit à vue.
ASIDE_REASONS = {
    "homonym": ("a title where the word is not the name",
                "titles where the word is not the name"),
    "other-subject": ("a record on another subject", "records on another subject"),
    "insufficient-metadata": ("a record too thin to decide on",
                              "records too thin to decide on"),
    "text-by-origen": ("an edition of a text by Origen catalogued as a study of him",
                       "editions of texts by Origen catalogued as studies of him"),
}

# Langues nommées dans la prose, dans l'ordre de lecture. Les autres existent
# dans le fichier de couverture et ne sont pas citées : la phrase donne les cinq
# langues de publication du champ, pas un inventaire.
NAMED_LANGUAGES = (("es", "Spanish"), ("de", "German"), ("en", "English"),
                   ("it", "Italian"), ("fr", "French"))

# Bases citées nommément dans la prose, dans l'ordre où le lecteur les
# rencontrera : la plus fournie d'abord.
ORDER_HINT = ("ixtheo-k10plus", "openalex", "adamantius-girota", "isidore",
              "crossref", "semanticscholar", "bibp", "dialnet", "sbn",
              "thesesfr", "generated")


def spaced(number: int) -> str:
    """1632 -> « 1 632 », séparateur de milliers des pages du site."""
    return f"{number:,}".replace(",", " ")


def figures() -> dict:
    data = json.loads(ABSTRACTS.read_text(encoding="utf-8"))
    coverage = data["coverage"]
    labels = {key: value["label"] for key, value in data["sources"].items()}
    per_source = collections.Counter(entry["s"] for entry in data["byPpn"].values())
    total = sum(per_source.values())
    own_base = per_source.get("ixtheo-k10plus", 0)

    ordered = sorted(
        per_source.items(),
        key=lambda kv: (ORDER_HINT.index(kv[0]) if kv[0] in ORDER_HINT else 99,
                        -kv[1], kv[0]))
    return {
        "records": coverage["records"],
        "with_abstract": total,
        "share": 100 * total / max(1, coverage["records"]),
        "arrived_on_the_record": coverage["from_the_record_itself"],
        "arrived_by_joining": coverage["joined_from_the_federated_corpus"],
        "written_by_the_catalogue": own_base,
        "written_elsewhere": total - own_base,
        "without": coverage["records"] - total,
        "by_source": [{"source": key, "label": labels.get(key, key), "records": value}
                      for key, value in ordered],
        "unsummarised_anywhere": unsummarised_anywhere(data),
        "withdrawn": coverage.get("withdrawn_on_request", 0),
    }


def in_scope_ppns() -> set:
    """Les notices cartographiées : relation about/both dans la moisson IxTheo."""
    path = ROOT / "data" / "raw" / "ixtheo" / "records.jsonl"
    keep = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("relation") in ("about", "both"):
                keep.add(str(record.get("source_id")))
    return keep


def unsummarised_anywhere(data: dict) -> int | None:
    """Notices sans résumé affiché qu'AUCUNE base du corpus fédéré ne résume.

    La page l'annonce pour dire que le reste n'est pas retenu mais absent. Le
    compte se lit dans le corpus fusionné : parmi les notices cartographiées
    qui n'affichent pas de résumé, celles dont la grappe n'en porte aucun.
    """
    if not CORPUS.exists():
        return None
    missing = in_scope_ppns() - set(data["byPpn"])
    count = 0
    with CORPUS.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            cluster = json.loads(line)
            ppn = next((str(entry.get("source_id")) for entry in cluster.get("sources") or []
                        if isinstance(entry, dict)
                        and entry.get("source") == "ixtheo-k10plus"), None)
            if ppn in missing and not cluster.get("abstract"):
                count += 1
    return count


def citation_figures():
    """Les chiffres de couverture des citations, lus dans le fichier dérivé.

    Même mécanisme que la provenance des résumés : la page n'a rien à taper, et
    un fichier régénéré sans repasser ici se voit tout de suite.
    """
    if not CITATIONS.exists():
        return None
    data = json.loads(CITATIONS.read_text(encoding="utf-8"))
    by_language = data.get("by_language") or {}
    languages = []
    for code, label in NAMED_LANGUAGES:
        entry = by_language.get(code)
        if entry:
            languages.append((code, label, 100 * entry["coverage"]))
    return {
        "clusters": data["clusters"],
        "measured": data["measured"],
        "share": 100 * data["coverage"],
        "languages": languages,
    }


def citation_block(values: dict) -> str:
    shares = ", ".join("%s %s" % (label, ("%.1f %%" % share))
                       for _code, label, share in values["languages"])
    return """
      <p><strong>The citation figure is unevenly available, and the unevenness runs along
        languages.</strong> Citation counts come from a single measurable source, and it does
        not cover the field evenly. Across the working corpus of {clusters} clusters, {share} carry
        a count at all, and the share by language of publication is
        <strong>{shares}</strong>.
        A French article is not less cited than a Spanish one; it is less often indexed where
        citations are counted. This is why the weight is a cohort rank rather than a raw
        count — a record is ranked against others of its own decade, type and language, so
        that a thinly indexed language is not read as a thinly cited one — and why the weight
        never filters anything out of a result. Read across languages, the disc sizes still
        carry that bias, and no correction here removes it.</p>
    """.format(clusters=spaced(values["clusters"]),
               share=("%.1f %%" % values["share"]),
               shares=shares)


def population(build: Path) -> dict:
    """La population comptée, recomptée notice par notice comme le font les pages.

    Même règle que `qa/check_one_population.py` et que le front : une notice du
    graphe entre dans les figures si son tag la classe `core` ou `partial`, elle
    est mentionnée seulement si le tag dit `marginal`, elle est tenue hors compte
    sinon — y compris quand elle n'a pas de tag du tout, cas qu'on ne masque pas
    en le rangeant ailleurs.
    """
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    semantic = json.loads((build / "assets" / "semantic.json").read_text(encoding="utf-8"))
    tags = semantic["byPpn"]

    counted, mentioned = [], 0
    aside_classed, aside_untagged = 0, 0
    for node in graph.get("nodes") or []:
        if node.get("k") != "pub" or not node.get("ppn"):
            continue
        record = tags.get(node["ppn"])
        if record is None:
            aside_untagged += 1
        elif record["r"] in COUNTED_CLASSES:
            counted.append((node, record))
        elif record["r"] == "marginal":
            mentioned += 1
        else:
            aside_classed += 1

    languages = collections.Counter()
    approaches = collections.Counter()
    without_work = 0
    for node, record in counted:
        code = node.get("lang")
        languages[code if code in {c for c, _ in LEGEND_LANGUAGES} else "oth"] += 1
        for key in record.get("a") or []:
            if key in semantic["approaches"]:
                approaches[semantic["approaches"][key]["label"]] += 1
        named = [key for key in record.get("w") or []
                 if key in semantic["works"] and key != "unspecified"]
        if not named:
            without_work += 1

    source = semantic.get("source") or {}
    review = source.get("needs_review_by_class") or {}
    weights = json.loads((build / "assets" / "weights.json").read_text(encoding="utf-8"))
    return {
        "harvest": len(counted) + mentioned + aside_classed + aside_untagged,
        "counted": len(counted),
        "mentioned": mentioned,
        "aside": aside_classed + aside_untagged,
        "aside_classed": aside_classed,
        "aside_untagged": aside_untagged,
        "aside_reasons": source.get("held_aside_reasons") or {},
        "review_total": source.get("needs_review", 0),
        "review_by_class": review,
        "review_in_count": sum(review.get(key, 0) for key in COUNTED_CLASSES),
        "review_repaired": source.get("needs_review_repaired", 0),
        "languages": [(label, languages.get(code, 0))
                      for code, label in LEGEND_LANGUAGES],
        "leading_approach": approaches.most_common(1)[0] if approaches else ("", 0),
        "without_work": without_work,
        "weight_covered": weights.get("covered", 0),
        "weight_total": weights.get("total", 0),
    }


def reasons_sentence(values: dict) -> str:
    """« 4 sont des éditions…, 1 est un titre où… », dans l'ordre décroissant."""
    parts = []
    for key, count in sorted(values["aside_reasons"].items(), key=lambda kv: (-kv[1], kv[0])):
        singular, plural = ASIDE_REASONS.get(key, (key, key))
        parts.append("%s %s %s" % (spaced(count), "is" if count == 1 else "are",
                                   singular if count == 1 else plural))
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def index_meta_block(values: dict) -> str:
    return ('\n<meta name="description" content="A map of the scholarship on Origen of '
            'Alexandria: %s counted works out of a harvest of %s, grouped by theme or by work '
            'of Origen, coloured by language of publication.">\n'
            % (spaced(values["counted"]), spaced(values["harvest"])))


def index_scope_block(values: dict) -> str:
    return ('\n  <p class="scope"><b>%s</b> works counted &middot; %s mentioned only '
            '&middot; %s held aside &middot; IxTheo, August 2026</p>\n'
            % (spaced(values["counted"]), spaced(values["mentioned"]),
               spaced(values["aside"])))


def index_held_block(values: dict) -> str:
    return ("""
    <span class="held-note">Every count here counts the {counted} works Origen is the subject of,
      or holds a section of. The {mentioned} that only mention him and the {aside} held outside the
      count stay in the index, answer a search, and enter no figure, here and in the Observatory alike.</span>
""".format(counted=spaced(values["counted"]), mentioned=spaced(values["mentioned"]),
           aside=spaced(values["aside"])))


def observatory_meta_block(values: dict) -> str:
    return ('\n<meta name="description" content="What one harvest of the scholarship on Origen '
            'contains: %s counted records out of %s from IxTheo, by period, language, format, '
            'theme and work.">\n'
            % (spaced(values["counted"]), spaced(values["harvest"])))


def observatory_lede_block(values: dict) -> str:
    return ("""
    <p><strong>One population, on every figure here and in the Explorer alike.</strong> A count
      on this site is a count of the {counted} records where Origen is the subject or holds a
      section of the argument. Of the {harvest} harvested, {mentioned} mention him only and {aside} are
      held outside the count{why}: they stay in the index, they answer
      a search, and they enter no figure. The three sets are drawn below before anything is
      counted.</p>
""".format(counted=spaced(values["counted"]), harvest=spaced(values["harvest"]),
           mentioned=spaced(values["mentioned"]), aside=spaced(values["aside"]),
           why=", as noise or for want of a class" if values["aside_untagged"] else ""))


def observatory_reservoir_block(values: dict) -> str:
    """Ce que le réservoir contient, une fois le plancher curaté appliqué.

    La page lisait « read the third figure as a ceiling » tant que la règle
    sévère de la première vague tenait. Elle ne tient plus, et un plafond sur une
    mesure qui a été refaite serait une précaution pour rien.
    """
    return ("""
      <p><strong>What the third set holds.</strong> The rule of the first wave filed a record as
        <em>not about Origen</em> whenever its metadata did not name him. On a catalogue where
        librarians have already attached every record to Origen's authority record, that rule was
        too severe: it swept in studies where he is one witness among several, and the figure it
        produced had to be read as a ceiling on the noise rather than as a measurement of it. The
        instructions were rewritten and the harvest classed again. On that curated perimeter the
        class now floors at <em>mentioned only</em>, and <em>not about Origen</em> is kept for
        what it was meant for. The third set now holds {aside} records where the first wave held
        223, and the second holds {mentioned} where it held 9. A record of that second set is
        retrieved by a search, listed under the count, and added to no figure.
        Of the {aside} held aside, {classed} are classed: {reasons}.{tail}
        The <a href="methode.html">Method</a> page says what that costs.</p>
""".format(aside=spaced(values["aside"]), mentioned=spaced(values["mentioned"]),
           classed=spaced(values["aside_classed"]), reasons=reasons_sentence(values),
           tail=reservoir_tail(values)))


def reservoir_tail(values: dict) -> str:
    """La phrase sur les notices sans classe — écrite seulement s'il y en a.

    Elle a longtemps été vraie : 28 notices tombaient dans le réservoir faute
    d'un tag, et la page le disait. Elles sont taguées, et une phrase qui
    annonce « the other 0 carry no class » vaudrait moins que rien.
    """
    if values["aside_untagged"]:
        return (" The other %s carry no class at all: their cluster was reshaped by the "
                "deduplication after the wave had run, and no tag was invented to fill the gap."
                % spaced(values["aside_untagged"]))
    return (" None is held aside for want of a tag: a record the deduplication left behind goes "
            "back to the tagger, and the build refuses to publish while one is missing.")


def observatory_languages_block(values: dict) -> str:
    return ("""
    <p class="sub">Language and format as coded in the catalogue record, not as inferred from the
      title. Counted on the same {counted} records as every other figure, which is why these totals
      run below the size of the harvest.</p>
""".format(counted=spaced(values["counted"])))


def observatory_themes_block(values: dict) -> str:
    return ("""
    <p class="sub">Counted on the same {counted} records as the figures above: a record that
      merely mentions Origen thickens no theme, no work and no angle, and is listed rather
      than counted wherever the Explorer returns it.</p>
""".format(counted=spaced(values["counted"])))


def method_stamp_block(values: dict) -> str:
    return ('\n    <p class="stamp">Version of August 2026 · one source · %s records harvested, '
            '%s counted</p>\n' % (spaced(values["harvest"]), spaced(values["counted"])))


def method_bias_block(values: dict) -> str:
    return ("""
      <p><strong>A known bias, and what became of it.</strong> The rule used in the first wave
        demanded that the metadata name Origen positively, and filed everything else as <em>not
        about Origen</em>. On a curated perimeter, where cataloguers have already attached each
        record to Origen's authority record, that rule was too severe: a study of original sin in
        the Fathers, or of ministry in the early Church, was filed out although Origen is one of
        its witnesses. Seven of the eight disagreements in the thirty-record pilot pointed that
        way. The instructions now floor the class at <em>mentioned only</em> for any record
        catalogued as being about him, and keep <em>not about Origen</em> for homonyms and for
        texts by Origen catalogued as texts about him. The harvest was classed again under them:
        the reservoir holds {aside} records where it held 223, and <em>mentioned only</em> holds
        {mentioned} where it held 9 — retrieved by a search, counted in no figure. What remains
        of the bias runs the other way now: a record the catalogue attached to Origen is credited
        with a mention even where the metadata alone would not carry it.</p>
""".format(aside=spaced(values["aside"]), mentioned=spaced(values["mentioned"])))


def method_counted_block(values: dict) -> str:
    return ("""
    <p><strong>Which records count.</strong> Every figure on this site is a count of the same
      {counted} records: those classed <em>core</em> or <em>partial</em>, where Origen is the
      subject or holds an identifiable section of the argument. Of the {harvest} harvested,
      {mentioned} are classed <em>mentioned only</em> and {aside} are held outside the count;
      neither class enters a figure, on any page — not the bars of the
      <a href="observatoire.html">Observatory</a>, not the language counts, not the number on a
      question chip, not the density of a cluster.</p>
    <p>Retrieval is wider than counting, and stays wider. A record where Origen is mentioned
      only still answers a search and still answers the four questions: nothing is put aside,
      as the map says on every page. It is returned, listed and readable — and it is not added
      to the figure. Where a surface can return more than it counts, it says so in words and
      gives the second number: <em>N further works are mentioned only and are listed below the
      count</em>.</p>
    {leftover}
""".format(counted=spaced(values["counted"]), harvest=spaced(values["harvest"]),
           mentioned=spaced(values["mentioned"]), aside=spaced(values["aside"]),
           leftover=leftover_paragraph(values)))


def leftover_paragraph(values: dict) -> str:
    """Ce que le décompte laisse dehors sans classe — au présent, ou au passé.

    Vingt-huit notices l'ont été, le temps qu'une correction de fusion les
    renumérote et qu'aucune vague ne les rattrape. Elles ont été taguées après
    coup ; le paragraphe garde l'épisode plutôt que de disparaître, parce qu'un
    lecteur a le droit de savoir que la chose est arrivée et comment elle est
    tenue.
    """
    if values["aside_untagged"]:
        return (
            "<p><strong>What the count leaves out, and does not hide.</strong> %s of the %s\n"
            "      records carry no class at all. Their cluster was split or joined by the "
            "deduplication after\n      the wave had run, and the tag of the old cluster was not "
            "carried over to a shape it had\n      never seen. They are held outside every figure "
            "with the rest of the reservoir rather than\n      guessed into one, and the next wave "
            "tags them.</p>"
            % (spaced(values["aside_untagged"]), spaced(values["harvest"])))
    return (
        "<p><strong>What the count leaves out, and does not hide.</strong> Every one of the %s\n"
        "      records carries a class. Twenty-eight did not: their cluster had been split or "
        "joined by the\n      deduplication after the wave had run, or a mechanical pre-sort had "
        "set them aside, and the\n      count held them outside every figure for want of a tag "
        "rather than guess one. They were sent\n      back to the tagger in a later pass, and the "
        "build now refuses to publish while a record on\n      display carries no class.</p>"
        % spaced(values["harvest"]))


def method_rule_block(values: dict) -> str:
    return ("""
    <p><strong>One rule for the counts</strong>, on this page, in the questions of the Explorer
      and in the Observatory alike: a figure counts the {counted} records classed <em>core</em> or
      <em>partial</em> (§ 4), and nothing else. The reservoirs hold the rest, named and counted
      as reservoirs. Saying how much of a harvest cannot be placed is part of what a map of a
      field owes its reader.</p>
""".format(counted=spaced(values["counted"])))


def method_questions_block(values: dict) -> str:
    """La réponse courte sur la densité, en bas de la page de méthode.

    Elle se tient seule — c'est à quoi sert une réponse de ce genre — et elle
    porte donc la population, comme les paragraphes qui la précèdent. Générée
    pour la même raison qu'eux : le jour où la population bouge, elle bouge.
    """
    return ("""
    <p>A density is a count of records inside a named node of the vocabulary, and nothing
      more. When the map says forty-seven works sit in a perimeter, forty-seven records of
      this harvest are filed under that node, out of the {counted} the site counts. The node
      has a name, a path and a definition, so the figure can be checked against the same data.
      What a density does not measure is the originality of a project: thin ground may be
      unexplored, or exhausted, or written in a language this catalogue indexes poorly, and the
      map cannot tell those three apart. It opens a question rather than settling one. Academic
      weight, drawn as the size of a disc, is a separate thing again: a citation percentile
      inside a cohort of the same decade, type and language, which never filters a search and
      never enters a count.</p>
""".format(counted=spaced(values["counted"])))


def credits_source_block(values: dict) -> str:
    return ("""
            <td>the {harvest} records mapped here: titles, authors, years, languages, containers,
              subject headings, identifiers. Harvested through the authority record for Origen
              (<a href="https://d-nb.info/gnd/118590235" rel="noopener">GND 118590235</a>) on
              15 August 2026.</td>
""".format(harvest=spaced(values["harvest"])))


# Les blocs du README tiennent sur une seule ligne, sans saut : une balise HTML
# seule sur sa ligne couperait la liste ou le paragraphe qui l'entoure, alors
# qu'un commentaire au fil du texte les laisse intacts.
def readme_reservoirs_block(values: dict) -> str:
    return ("the classifier keeps outside the count (%s); `No single work` holds the studies "
            "that bear on none (%s counted, in work mode)."
            % (spaced(values["aside"]), spaced(values["without_work"])))


def readme_population_block(values: dict) -> str:
    named = ", ".join("%s %s" % (label, spaced(count))
                      for label, count in values["languages"][:4])
    approach, approach_count = values["leading_approach"]
    return ("same set of {counted} records, those where Origen is the subject or holds an "
            "identifiable section of the argument. The {mentioned} that mention him only and the "
            "{aside} held outside the count stay in the index and answer a search; neither enters "
            "a figure. Where a surface returns more than it counts, it says so and gives the "
            "second number rather than folding it into the first. The three sides print the same "
            "values ({named}, `{approach} {approach_count}`, and so on down the list), which is "
            "the point: one number per thing, on every page."
            .format(counted=spaced(values["counted"]), mentioned=spaced(values["mentioned"]),
                    aside=spaced(values["aside"]), named=named, approach=approach,
                    approach_count=spaced(approach_count)))


def root_readme_block(values: dict) -> str:
    """Le README du dépôt, qui annonce la population du site en une phrase."""
    return ("**%s records, of which %s are counted**, %s mentioned only, %s held outside the "
            "count." % (spaced(values["harvest"]), spaced(values["counted"]),
                        spaced(values["mentioned"]), spaced(values["aside"])))


def readme_untagged_block(values: dict) -> str:
    """La ligne du README sur les notices sans classe — au présent ou au passé.

    Seule la première phrase était générée ; la suite était écrite à la main et
    expliquait le trou. Le trou refermé, la phrase générée disait « 0 records »
    et la main disait toujours qu'ils attendaient la prochaine vague. Le bloc
    porte donc la ligne entière.
    """
    count = values["aside_untagged"]
    if count:
        return ("%s record%s carr%s no class at all. Their cluster was split or joined\n"
                "  by the deduplication after the second wave had run, and no tag was invented "
                "to\n  fill the gap: they sit in the reservoir with the rest, outside every "
                "figure, until\n  the next wave tags them."
                % (spaced(count), "" if count == 1 else "s", "ies" if count == 1 else "y"))
    return ("Every record on display carries a class. Twenty-eight did not, until a gap "
            "pass\n  tagged them: their cluster had been split or joined by the deduplication "
            "after the\n  second wave had run, or a mechanical pre-sort had set them aside. The "
            "build now\n  refuses to write this asset while a record on display carries none.")


def readme_weights_block(values: dict) -> str:
    share = 100 * values["weight_covered"] / max(1, values["weight_total"])
    return ("today: %s of %s works (%s), joined on the catalogue number and then on the DOI — "
            "never on the title, which used to carry the citations of a review over to the book "
            "it reviewed."
            % (spaced(values["weight_covered"]), spaced(values["weight_total"]),
               ("%.1f %%" % share)))


def classification() -> dict | None:
    """Les classes de pertinence, recomptées sur les fichiers de tags livrés.

    Le README, la page de méthode et la citation annonçaient 21 080 notices
    classées et un dossier de 6 720 — les chiffres de la vague fédérée avant que
    la passe de rattrapage n'en tague vingt-quatre de plus. Les fichiers livrés
    en portent d'autres, et l'audit 6 a mesuré l'écart. Ils se comptent donc ici,
    sur les fichiers eux-mêmes : une notice retaguée dans une vague ultérieure
    compte une fois, avec sa dernière classe.
    """
    if not WAVES:
        return None
    latest: dict[str, dict] = {}
    for path in WAVES:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                identifier = record.get("notice_id")
                if identifier:
                    latest[identifier] = record
    classes = collections.Counter(record.get("relevance") for record in latest.values())
    return {
        "classified": len(latest),
        "core": classes["core"],
        "partial": classes["partial"],
        "counted": classes["core"] + classes["partial"],
        "marginal": classes["marginal"],
        "none": classes["none"],
        "waves": len(WAVES),
    }


def readme_classification_block(values: dict) -> str:
    return ("""
**Classification.** {classified} clusters have been read against a controlled
vocabulary of themes, works, approaches and relevance. Of those, {core} are about
Origen and {partial} give him a section of the argument: **{counted} records form the
citable dossier**. {marginal} mention him only; {none} are noise the harvest brought
in and the classification pushed out. Every published figure counts the first two
classes and nothing else.
""".format(classified=spaced(values["classified"]), core=spaced(values["core"]),
           partial=spaced(values["partial"]), counted=spaced(values["counted"]),
           marginal=spaced(values["marginal"]), none=spaced(values["none"])))


def methodology_classification_block(values: dict) -> str:
    return ("""
Of the {classified} records classified so far: {core} `core`, {partial} `partial` (the
citable dossier, **{counted}**), {marginal} `marginal`, {none} `none`. The figures are
counted from the wave files published under `semantic/waves/`, and a record
classified again in a later wave counts once, under its last class.
""".format(classified=spaced(values["classified"]), core=spaced(values["core"]),
           partial=spaced(values["partial"]), counted=spaced(values["counted"]),
           marginal=spaced(values["marginal"]), none=spaced(values["none"])))


def citation_abstract_block(values: dict) -> str:
    """L'`abstract` du fichier de citation, réécrit en entier.

    Un fichier lu par une machine ne peut pas porter un chiffre périmé sans le
    propager partout où il est moissonné. Le bloc couvre donc la clé entière, et
    les balises tiennent dans des commentaires YAML pour que le fichier reste
    valide contre le schéma 1.2.0.
    """
    return ("""
abstract: >-
  A federated, deduplicated and thematically classified bibliography of
  scholarship on Origen of Alexandria, published as a queryable map of the
  field. Ten open bibliographic sources, deduplicated into one record per work,
  of which {classified} are classified against a controlled vocabulary of themes,
  works of Origen and approaches: {counted} of them — {core} core and {partial}
  partial — form the citable dossier. The code is under the MIT licence; the data
  are not, and DATA_POLICY.md states the regime that covers them, source by
  source.
# """.format(classified=spaced(values["classified"]), counted=spaced(values["counted"]),
             core=spaced(values["core"]), partial=spaced(values["partial"])))


def population_blocks():
    """Les blocs de population : nom de balise, page, fonction qui l'écrit."""
    return (
        ("FIGURES:population-meta", "index.html", index_meta_block),
        ("FIGURES:population-scope", "index.html", index_scope_block),
        ("FIGURES:population-held", "index.html", index_held_block),
        ("FIGURES:population-meta", "observatoire.html", observatory_meta_block),
        ("FIGURES:population-lede", "observatoire.html", observatory_lede_block),
        ("FIGURES:population-reservoir", "observatoire.html", observatory_reservoir_block),
        ("FIGURES:population-languages", "observatoire.html", observatory_languages_block),
        ("FIGURES:population-themes", "observatoire.html", observatory_themes_block),
        ("FIGURES:population-stamp", "methode.html", method_stamp_block),
        ("FIGURES:population-bias", "methode.html", method_bias_block),
        ("FIGURES:population-counted", "methode.html", method_counted_block),
        ("FIGURES:population-rule", "methode.html", method_rule_block),
        ("FIGURES:population-questions", "methode.html", method_questions_block),
        ("FIGURES:population-source", "credits.html", credits_source_block),
        ("FIGURES:population-reservoirs", "README.md", readme_reservoirs_block),
        ("FIGURES:population-screen", "README.md", readme_population_block),
        ("FIGURES:population-weights", "README.md", readme_weights_block),
        ("FIGURES:population-untagged", "README.md", readme_untagged_block),
    )


# Le README du dépôt vit une marche au-dessus du site : il est traité à part,
# avec le même mécanisme, plutôt que laissé à la saisie à la main.
ROOT_BLOCKS = (("FIGURES:population-root", root_readme_block),)

# Les documents de racine qui annoncent la classification. Même mécanisme, autre
# source : les fichiers de tags livrés plutôt que la couche de données du site.
CLASSIFICATION_BLOCKS = (
    ("FIGURES:classification", "README.md", readme_classification_block),
    ("FIGURES:classification", "docs/methodology.md", methodology_classification_block),
    ("FIGURES:classification", "CITATION.cff", citation_abstract_block),
)


POPULATION_BLOCKS = population_blocks()


def html_block(values: dict) -> str:
    rows = "\n".join(
        "        <tr><td>{label}</td><td class=\"num\">{count}</td></tr>".format(
            label=entry["label"], count=spaced(entry["records"]))
        for entry in values["by_source"])
    return """
    <p><strong>Coverage.</strong> IxTheo is a catalogue, and a catalogue describes rather than
      summarises: {arrived_on_the_record} of the {records} records carry a summary of their own.
      Where another database summarises the same publication, that summary is joined to the
      record by catalogue number, by DOI, or by title and year, and {arrived_by_joining} records
      are covered that way. In all, <strong>{with_abstract} records of {records}
      ({share})</strong> show a summary. The other {without} are not being withheld:
      {unsummarised} of them appear in the working corpus and no database there holds a summary
      of them either.</p>
    <p><strong>Who wrote them.</strong> How a summary reached this file is one question; who
      wrote it is another, and the second is the one the credit answers.
      {written_by_the_catalogue} of the {with_abstract} were written by the catalogue itself and
      {written_elsewhere} by another database, whichever route they took to get here. The full
      breakdown, counted from the published file rather than typed here:</p>
    <div class="tbl-wrap">
      <table class="tbl">
        <thead><tr><th>Database that wrote the summary</th><th class="num">Summaries</th></tr></thead>
        <tbody>
{rows}
        </tbody>
      </table>
    </div>
""".format(
        arrived_on_the_record=spaced(values["arrived_on_the_record"]),
        arrived_by_joining=spaced(values["arrived_by_joining"]),
        records=spaced(values["records"]),
        with_abstract=spaced(values["with_abstract"]),
        share=("%.1f %%" % values["share"]).replace(".", "."),
        without=spaced(values["without"]),
        unsummarised=spaced(values["unsummarised_anywhere"] or 0),
        written_by_the_catalogue=spaced(values["written_by_the_catalogue"]),
        written_elsewhere=spaced(values["written_elsewhere"]),
        rows=rows,
    )


def credits_block(values: dict) -> str:
    named = ", ".join(entry["label"] for entry in values["by_source"][1:])
    return """
    <p>Every summary displayed in the Explorer names the database that wrote it and links to
      the record there. {with_abstract} of the {records} mapped records carry one.
      {written_by_the_catalogue} were written by IxTheo itself and {written_elsewhere} by
      another database that describes the same publication: {named}. A summary written for
      this project, where one exists, says so instead of naming a database.</p>
""".format(
        with_abstract=spaced(values["with_abstract"]),
        records=spaced(values["records"]),
        written_by_the_catalogue=spaced(values["written_by_the_catalogue"]),
        written_elsewhere=spaced(values["written_elsewhere"]),
        named=named,
    )


def readme_block(values: dict) -> str:
    return ("\n%s of the %s records carry one — %s written by IxTheo itself, %s by another "
            "database.\n" % (spaced(values["with_abstract"]), spaced(values["records"]),
                             spaced(values["written_by_the_catalogue"]),
                             spaced(values["written_elsewhere"])))


def replace(path: Path, block: str, opener: str, closer: str) -> bool:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(opener) + r".*?" + re.escape(closer), re.DOTALL)
    if not pattern.search(text):
        sys.exit("REFUS : balises « %s » absentes de %s — ajoutez-les autour du "
                 "passage à générer." % (opener.strip("<!- >"), path))
    updated = pattern.sub(lambda _m: opener + block + closer, text)
    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def main(argv):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="ne rien écrire ; sortir en 1 si une page est périmée")
    parser.add_argument("--build", default=str(BUILD), type=Path,
                        help="répertoire des pages à écrire (une copie, pour un test)")
    arguments = parser.parse_args(argv)
    build = arguments.build

    values = figures()
    citations = citation_figures()
    people = population(build)
    classes = classification()
    targets = []
    # La provenance des résumés se recompte avec le corpus fusionné, qui n'est
    # pas dans l'arbre public : un clone n'a pas de quoi la reconstruire, et
    # contrôler un bloc qu'on ne peut pas recalculer ferait échouer le contrôle
    # sur une absence voulue. Là où le corpus est présent, rien ne change.
    if CORPUS.exists():
        targets += [
            (build / "methode.html", html_block(values), OPEN, CLOSE),
            (build / "credits.html", credits_block(values), OPEN, CLOSE),
            (build / "README.md", readme_block(values), MD_OPEN, MD_CLOSE),
        ]
    if citations is not None:
        targets.append((build / "methode.html", citation_block(citations),
                        CITE_OPEN, CITE_CLOSE))
    for name, page, builder in POPULATION_BLOCKS:
        opener, closer = marks(name)
        targets.append((build / page, builder(people), opener, closer))
    if build == BUILD:
        for name, builder in ROOT_BLOCKS:
            opener, closer = marks(name)
            targets.append((ROOT / "README.md", builder(people), opener, closer))
        if classes is not None:
            for name, document, builder in CLASSIFICATION_BLOCKS:
                opener, closer = marks(name)
                targets.append((ROOT / document, builder(classes), opener, closer))

    stale = []
    for path, block, opener, closer in targets:
        text = path.read_text(encoding="utf-8")
        if opener + block + closer not in text:
            stale.append(path)

    print(json.dumps({k: v for k, v in values.items() if k != "by_source"},
                     ensure_ascii=False, indent=1))
    for entry in values["by_source"]:
        print("   %-20s %5d  %s" % (entry["source"], entry["records"], entry["label"]))
    if not CORPUS.exists():
        print("corpus fusionné absent de cet arbre : blocs de provenance non contrôlés",
              file=sys.stderr)
    if citations is None:
        print("citations_coverage.json absent : bloc de citations non contrôlé",
              file=sys.stderr)
    if classes is None:
        print("aucun fichier de tags de vague : blocs de classification non contrôlés",
              file=sys.stderr)
    else:
        print(json.dumps(classes, ensure_ascii=False, indent=1))
    if citations is not None:
        print(json.dumps({k: v for k, v in citations.items() if k != "languages"},
                         ensure_ascii=False, indent=1))
        for code, label, share in citations["languages"]:
            print("   %-4s %-10s %5.1f %%" % (code, label, share))
    print(json.dumps({k: v for k, v in people.items() if k != "languages"},
                     ensure_ascii=False, indent=1))
    for label, count in people["languages"]:
        print("   %-14s %5d" % (label, count))

    def shown(path: Path) -> str:
        try:
            return str(path.relative_to(ROOT))
        except ValueError:
            return str(path)

    if arguments.check:
        for path in stale:
            print("PÉRIMÉ : %s" % shown(path), file=sys.stderr)
        return 1 if stale else 0

    for path, block, opener, closer in targets:
        changed = replace(path, block, opener, closer)
        print("%s %s" % ("réécrit " if changed else "inchangé", shown(path)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
