#!/usr/bin/env python3
"""Origenality : les chiffres publiés par les pages, écrits par la machine.

L'audit 3 relève que Method et Credits annoncent 152 résumés d'IxTheo et 210
d'ailleurs, alors que la ventilation PAR BASE des données publiées en donne
d'autres. Les deux chiffres sont vrais mais ne répondent pas à la même question :
152 / 210 disent d'où le résumé est ARRIVÉ dans le fichier : de la notice IxTheo
elle-même, ou joint depuis le corpus fédéré :, tandis que la ventilation par base
dit QUI l'a écrit. Un résumé d'IxTheo peut arriver par la jointure ; il reste
d'IxTheo. Publier l'un sous le nom de l'autre, c'est se tromper de question.

Ce script tranche en supprimant la saisie à la main. Il lit
`site/data/abstracts.json`, compte, et réécrit des blocs balisés dans les pages :

    <!-- FIGURES:summary-provenance --> … <!-- /FIGURES:summary-provenance -->

Le texte entre les balises est produit ici, jamais tapé ailleurs. Relancer le
script après une reconstruction des données remet les pages d'aplomb ; ne pas le
relancer se voit, puisque les chiffres du bloc ne bougent pas alors que le
fichier de données a bougé : `--check` le dit et sort en 1.

Trois familles de blocs sont produites par le même mécanisme :

- `FIGURES:summary-provenance` : la provenance des résumés ;
- `FIGURES:citation-coverage` : la couverture des citations, qui annonçait encore
  42 246 grappes et deux pourcentages par langue périmés après une refonte de la
  fusion ;
- `FIGURES:population-*` : la population comptée, ajoutée quand le site est passé
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
META = DATA / "META.json"
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
LEGEND_LANGUAGES = (("en", "English"), ("de", "German"), ("it", "Italian"),
                    ("fr", "French"), ("es", "Spanish"), ("oth", "Other or none"))

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


NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
                "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
                "seventeen", "eighteen", "nineteen", "twenty")


def number_word(number: int, capital: bool = False) -> str:
    """8 -> « eight » : les petits nombres s'écrivent en lettres dans la prose anglaise."""
    word = NUMBER_WORDS[number] if 0 <= number < len(NUMBER_WORDS) else spaced(number)
    return word[:1].upper() + word[1:] if capital else word


def noun(number: int, one: str, many: str) -> str:
    """Accord au nombre : « 1 record », « 2 records » (audit du 13/09, OR-71)."""
    return one if number == 1 else many


def verb(number: int, one: str = "is", many: str = "are") -> str:
    return one if number == 1 else many


def english_label(label: str) -> str:
    """Libellé de base pour une page anglaise : DATA_POLICY.md écrit « Sudoc : Agence… »
    à la française, et la page anglaise ne pose pas un deux-points entre deux espaces."""
    return re.sub(r"\s+[:—–]\s+", ", ", label)


def figures() -> dict:
    data = json.loads(ABSTRACTS.read_text(encoding="utf-8"))
    coverage = data["coverage"]
    labels = {key: english_label(value["label"]) for key, value in data["sources"].items()}
    per_source = collections.Counter(entry["s"] for entry in data["byPpn"].values())
    total = sum(per_source.values())
    # Qui a écrit le résumé : un catalogue d'où vient la notice, ou une autre base.
    # Avant la fusion, toute notice était une notice IxTheo et « IxTheo » valait
    # « la notice elle-même » ; une grappe réunit désormais des notices de sept
    # catalogues, et 36 résumés de K10plus, du Sudoc ou de la LoC passaient pour
    # venus d'ailleurs (OR-49). La base du résumé est comparée aux sources de SA
    # grappe, lues dans le graphe.
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    cluster_sources = {str(node.get("ppn")): set(node.get("src") or [])
                       for node in graph.get("nodes") or [] if node.get("k") == "pub"}
    own, elsewhere = collections.Counter(), collections.Counter()
    for key, entry in data["byPpn"].items():
        (own if entry["s"] in cluster_sources.get(key, ()) else elsewhere)[entry["s"]] += 1

    def ranked(counter):
        return sorted(counter.items(),
                      key=lambda kv: (ORDER_HINT.index(kv[0]) if kv[0] in ORDER_HINT else 99,
                                      -kv[1], kv[0]))

    ordered = ranked(per_source)
    return {
        "records": coverage["records"],
        "with_abstract": total,
        "share": 100 * total / max(1, coverage["records"]),
        "arrived_on_the_record": coverage["from_the_record_itself"],
        "arrived_by_joining": coverage["joined_from_the_federated_corpus"],
        "written_by_the_catalogue": sum(own.values()),
        "written_elsewhere": sum(elsewhere.values()),
        "own_labels": [labels.get(key, key) for key, _ in ranked(own)],
        "other_labels": [labels.get(key, key) for key, _ in ranked(elsewhere)],
        "girota_notes": per_source.get("adamantius-girota", 0),
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
    meta = json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}
    if meta.get("input_status") == "deduplicated-public-snapshot" or not CORPUS.exists():
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
        count (a record is ranked against others of its own decade, type and language, so
        that a thinly indexed language is not read as a thinly cited one), and why the weight
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
    sinon : y compris quand elle n'a pas de tag du tout, cas qu'on ne masque pas
    en le rangeant ailleurs.
    """
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    meta = json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}
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
    kept = len(counted) + mentioned + aside_classed + aside_untagged
    # « Harvested » ne désigne plus qu'une chose : les notices de catalogue avant la
    # fusion (META.records_harvested_total). Les grappes qui en sortent sont « kept ».
    # La même clé portait les deux, et la page disait « 2 490 harvested » à deux
    # lignes de « 2 582 records harvested » (OR-36).
    dedup = meta.get("deduplication") or {}
    harvested_by_source = meta.get("sources_harvested") or {}
    harvested = meta.get("records_harvested_total") or kept
    if harvested_by_source and sum(harvested_by_source.values()) != harvested:
        raise SystemExit("META.sources_harvested does not sum to records_harvested_total")
    excluded = meta.get("excluded") or {}
    return {
        "kept": kept,
        "harvested": harvested,
        "duplicates": dedup.get("duplicates_collapsed") or 0,
        "sources_harvested": dict(harvested_by_source),
        "editions": excluded.get("relation_by") if excluded.get("source") else None,
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
        "source_count": len(meta.get("sources_present") or []),
        "source_counts": {entry.get("source"): entry.get("records", 0)
                          for entry in meta.get("sources_present") or []},
        # Dates lues dans META, jamais tapées : la moisson IxTheo, et le jour où les
        # vedettes et les contenants des notices d'autorité ont été relus (audit du 13/09).
        "harvested_on": meta.get("harvested"),
        "refetched": meta.get("refetched"),
        "refetched_records": meta.get("refetched_records") or 0,
        "refetched_labels": refetched_labels(),
    }


MONTHS_EN = ("January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December")
MONTHS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
             "septembre", "octobre", "novembre", "décembre")


def english_date(iso) -> str:
    """« 2026-09-13 » -> « 13 September 2026 »."""
    year, month, day = (int(part) for part in str(iso).split("-"))
    return "%d %s %d" % (day, MONTHS_EN[month - 1], year)


def french_date(iso) -> str:
    year, month, day = (int(part) for part in str(iso).split("-"))
    return "%d\u00a0%s %d" % (day, MONTHS_FR[month - 1], year)


def refetched_labels() -> int:
    """Libellés de source dont les notices du snapshot ont été relues dans leur catalogue."""
    path = DATA / "site-records.jsonl"
    if not path.exists():
        return 0
    labels = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("subjects_container_basis") == "catalogue-record-refetched":
                labels.add(row.get("source"))
    return len(labels)


def refetch_sentence(values: dict, lead: str) -> str:
    """« The subject headings and containers of 1 173 of <lead>, from seven of the source
    labels, were read again from their own catalogues on 13 September 2026. »"""
    if not values.get("refetched") or not values.get("refetched_records"):
        return ""
    return ("The subject headings and containers of %s of %s, from %s of the source labels, "
            "were read again from their own catalogues on %s."
            % (spaced(values["refetched_records"]), lead,
               number_word(values["refetched_labels"]), english_date(values["refetched"])))


def corpus_figures(build: Path) -> dict:
    """Les chiffres de la fusion, des identifiants et de la couche primaire.

    Tous se lisent dans des fichiers livrés avec la couche de données : le compte
    rendu de fusion, celui de la projection des tags, `stats.json` et la couche
    primaire. Aucun n'était généré : la page de méthode imprimait encore
    « 936 of the 2582 records name a publisher » après la fusion (OR-38).
    """
    merge = json.loads((DATA / "site-merged" / "merge_report.json").read_text(encoding="utf-8"))
    tags = json.loads((DATA / "site-merged" / "tag_merge_report.json").read_text(encoding="utf-8"))
    stats = json.loads((DATA / "stats.json").read_text(encoding="utf-8"))
    totals = stats["totals"]
    # La couverture temporelle du JSON-LD disait 1514/2026 : l'année d'une notice
    # marginale, fausse de surcroît, quand les notices comptées commencent en 1639.
    counted_totals = (stats.get("counted") or {}).get("totals") or totals
    # `multi_source` du compte rendu de fusion compte les grappes de plus d'une
    # notice ; la page les disait « multi-source » quand 19 seulement joignent deux
    # libellés de source (audit du 13/09). Les deux nombres sont recomptés ici.
    clusters = [json.loads(line) for line in
                (DATA / "site-merged" / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()]
    several = sum(1 for cluster in clusters if len(cluster.get("sources") or []) > 1)
    across = sum(1 for cluster in clusters
                 if len({entry.get("source") for entry in cluster.get("sources") or []}) > 1)
    if several != merge["multi_source"]:
        raise SystemExit("merge_report.multi_source differs from the clusters of corpus.jsonl")
    rows = [json.loads(line) for line in
            (DATA / "primary-layer.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    years = [row["year"] for row in rows if isinstance(row.get("year"), int)]
    return {
        "multi_source": merge["multi_source"],
        "cross_source": across,
        "tag_disagreements": tags["clusters_with_tag_disagreement"],
        "clusters": totals["records"],
        "with_publisher": totals["records_with_publisher"],
        "with_isbn": totals["records_with_isbn"],
        "with_doi": totals["records_with_doi"],
        "primary_records": len(rows),
        "primary_before_1001": sum(1 for year in years if year <= 1000),
        "primary_before_1601": sum(1 for year in years if year <= 1600),
        "primary_set_aside": sum(1 for row in rows
                                 if row.get("year") is None and row.get("year_raw") is not None),
        "primary_undated": sum(1 for row in rows
                               if row.get("year") is None and row.get("year_raw") is None),
        "year_min": totals["year_min"],
        "year_max": totals["year_max"],
        "counted_year_min": counted_totals["year_min"],
        "counted_year_max": counted_totals["year_max"],
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
            'Alexandria: %s counted records out of %s work clusters, grouped by theme or by work '
            'of Origen, coloured by language of publication.">\n'
            % (spaced(values["counted"]), spaced(values["kept"])))


def index_scope_block(values: dict) -> str:
    return ('\n  <p class="scope"><b>%s</b> records counted &middot; %s mentioned only '
            '&middot; %s held aside &middot; %s source labels, August 2026</p>\n'
            % (spaced(values["counted"]), spaced(values["mentioned"]),
               spaced(values["aside"]), spaced(values["source_count"])))


def index_held_block(values: dict) -> str:
    return ("""
    <span class="held-note">Every count here counts the {counted} records where Origen is the subject,
      or holds a section of. The {mentioned} that only mention him and the {aside} held outside the
      count stay in the index, answer a search, and enter no figure, here and in the Observatory alike.</span>
""".format(counted=spaced(values["counted"]), mentioned=spaced(values["mentioned"]),
           aside=spaced(values["aside"])))


def observatory_meta_block(values: dict) -> str:
    return ('\n<meta name="description" content="What one harvest of the scholarship on Origen '
            'contains: %s counted records out of %s work clusters from %s source labels, by period, '
            'language, format, theme and work.">\n'
            % (spaced(values["counted"]), spaced(values["kept"]),
               spaced(values["source_count"])))


def observatory_lede_block(values: dict) -> str:
    return ("""
    <p><strong>One population, on every figure here and in the Explorer alike.</strong> A count
      on this site is a count of the {counted} records where Origen is the subject or holds a
      section of the argument. Of the {kept} records kept, {mentioned} {mention_verb} him only and {aside} {aside_verb}
      held outside the count{why}: they stay in the index, they answer
      a search, and they enter no figure. The three sets are drawn below before anything is
      counted.</p>
""".format(counted=spaced(values["counted"]), kept=spaced(values["kept"]),
           mentioned=spaced(values["mentioned"]), aside=spaced(values["aside"]),
           mention_verb=verb(values["mentioned"], "mentions", "mention"),
           aside_verb=verb(values["aside"]),
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
        what it was meant for. The third set now holds {aside} {aside_records} where the first wave held
        223, and the second holds {mentioned} where it held 9. A record of that second set is
        retrieved by a search, listed under the count, and added to no figure.
        Of the {aside} held aside, {classed} {classed_verb} classed: {reasons}.{tail}
        The <a href="methode.html">Method</a> page says what that costs.</p>
""".format(aside=spaced(values["aside"]), mentioned=spaced(values["mentioned"]),
           aside_records=noun(values["aside"], "record", "records"),
           classed=spaced(values["aside_classed"]), reasons=reasons_sentence(values),
           classed_verb="is" if values["aside_classed"] == 1 else "are",
           tail=reservoir_tail(values)))


def reservoir_tail(values: dict) -> str:
    """La phrase sur les notices sans classe : écrite seulement s'il y en a.

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
    counted = spaced(values["counted"])
    kept = spaced(values["kept"])
    return (
        '\n    <p class="census">'
        '<span class="census-n">%s</span>'
        '<span class="census-k">counted records, of %s kept</span>'
        '</p>\n'
        '    <p class="stamp">Version of August 2026 · %s source labels · %s records harvested, '
        '%s kept, %s counted</p>\n'
        % (counted, kept, values["source_count"], spaced(values["harvested"]), kept, counted)
    )


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
        the reservoir holds {aside} {aside_records} where it held 223, and <em>mentioned only</em>
        holds {mentioned} where it held 9, retrieved by a search and counted in no figure. What
        remains of the bias runs the other way now: a record the catalogue attached to Origen is
        credited with a mention even where the metadata alone would not carry it.</p>
""".format(aside=spaced(values["aside"]), mentioned=spaced(values["mentioned"]),
           aside_records=noun(values["aside"], "record", "records")))


def method_counted_block(values: dict) -> str:
    return ("""
    <p><strong>Which records count.</strong> Every figure on this site is a count of the same
      {counted} records: those classed <em>core</em> or <em>partial</em>, where Origen is the
      subject or holds an identifiable section of the argument. Of the {kept} records kept,
      {mentioned} {mentioned_verb} classed <em>mentioned only</em> and {aside} {aside_verb} held outside the
      count. Neither class enters a figure on any page, whether the bars of the
      <a href="observatoire.html">Observatory</a>, the language counts, the number on a
      question chip or the density of a cluster.</p>
    <p>Retrieval is wider than counting, and stays wider. A record where Origen is mentioned
      only still answers a search and still answers the four questions: nothing is put aside,
      as the map says on every page. It is returned, listed and readable, and it is not added
      to the figure. Where a surface can return more than it counts, it says so in words and
      gives the second number: <em>N further works are mentioned only and are listed below the
      count</em>.</p>
    {leftover}
""".format(counted=spaced(values["counted"]), kept=spaced(values["kept"]),
           mentioned=spaced(values["mentioned"]), aside=spaced(values["aside"]),
           mentioned_verb=verb(values["mentioned"]), aside_verb=verb(values["aside"]),
           leftover=leftover_paragraph(values)))


def leftover_paragraph(values: dict) -> str:
    """Ce que le décompte laisse dehors sans classe : au présent, ou au passé.

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
            % (spaced(values["aside_untagged"]), spaced(values["kept"])))
    return (
        "<p><strong>What the count leaves out, and does not hide.</strong> Every one of the %s\n"
        "      records carries a class. Twenty-eight did not: their cluster had been split or "
        "joined by the\n      deduplication after the wave had run, or a mechanical pre-sort had "
        "set them aside, and the\n      count held them outside every figure for want of a tag "
        "rather than guess one. They were sent\n      back to the tagger in a later pass, and the "
        "build now refuses to publish while a record on\n      display carries no class.</p>"
        % spaced(values["kept"]))


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

    Elle se tient seule : c'est à quoi sert une réponse de ce genre : et elle
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
    # Notices moissonnées, avant fusion, comme les sept autres lignes du tableau :
    # la ligne IxTheo lisait le compte des grappes et la table sommait à 2 521 (OR-37).
    # La date vient de META.harvested : elle était tapée dans ce gabarit.
    return ("""
            <td>{records} records: titles, authors, years, languages, containers,
              subject headings and identifiers. Harvested through the authority record for Origen
              (<a href="https://d-nb.info/gnd/118590235" rel="noopener">GND 118590235</a>) on
              {harvested}.</td>
""".format(records=spaced(values["sources_harvested"].get("ixtheo-k10plus", 0)),
           harvested=english_date(values["harvested_on"])))


def credits_sources_sub_block(values: dict) -> str:
    refetch = refetch_sentence(values, "them")
    return ("The map carries %s source labels. The %s catalogue records are\n"
            "      merged into %s work clusters before any density is counted.%s"
            % (number_word(values["source_count"]), spaced(values["harvested"]),
               spaced(values["kept"]), ("\n      " + refetch) if refetch else ""))


def method_merge_block(values: dict) -> str:
    refetch = refetch_sentence(values, "those records")
    return ("The current public build merges %s source records into %s work clusters; its "
            "manifest\n      preserves both counts and the %s collapsed %s.%s"
            % (spaced(values["harvested"]), spaced(values["kept"]), spaced(values["duplicates"]),
               noun(values["duplicates"], "duplicate", "duplicates"),
               ("\n      " + refetch) if refetch else ""))


def method_sources_intro_block(values: dict) -> str:
    return ("%s source labels contribute <strong>%s catalogue records</strong> about Origen:"
            % (number_word(values["source_count"], capital=True), spaced(values["harvested"])))


def sources_word_block(values: dict) -> str:
    return number_word(values["source_count"], capital=True)


def domains_word_block(build: Path) -> str:
    """« Sixteen domains » : le nombre de domaines du vocabulaire livré, en lettres."""
    semantic = json.loads((build / "assets" / "semantic.json").read_text(encoding="utf-8"))
    return number_word(len(semantic["domains"]), capital=True)


# Le JSON-LD de la page de méthode ne peut pas porter de commentaire : ses deux
# valeurs chiffrées sont bornées par leur propre texte. Il annonçait encore une
# couverture 1677/2026 quand stats.json commence en 1514, et « eight source
# labels » tapé à la main (audit du 13/09).
LD_COVERAGE = ('"temporalCoverage": "', '"')
LD_SOURCES = ('"description": "Records of scholarship on Origen of Alexandria, harvested under ',
              " source labels, deduplicated")


def method_dedup_block(values: dict, corpus: dict) -> str:
    return ("The work-level merge collapses %s duplicate %s before the graph is built. It\n"
            "      preserves all source identifiers and every field conflict. %s %s several\n"
            "      records, and %s of those %s records from more than one source label. The %s %s\n"
            "      whose source tags disagree %s marked for review."
            % (spaced(values["duplicates"]), noun(values["duplicates"], "record", "records"),
               spaced(corpus["multi_source"]),
               noun(corpus["multi_source"], "cluster merges", "clusters merge"),
               spaced(corpus["cross_source"]), verb(corpus["cross_source"], "joins", "join"),
               spaced(corpus["tag_disagreements"]),
               noun(corpus["tag_disagreements"], "cluster", "clusters"),
               verb(corpus["tag_disagreements"])))


def identifier_coverage_block(corpus: dict) -> str:
    return ("%s of the %s work clusters %s a publisher, %s an ISBN, %s a DOI."
            % (spaced(corpus["with_publisher"]), spaced(corpus["clusters"]),
               verb(corpus["with_publisher"], "names", "name"), spaced(corpus["with_isbn"]),
               spaced(corpus["with_doi"])))


def primary_dates_block(corpus: dict) -> str:
    return ("%s %s the eleventh century, %s the seventeenth."
            % (number_word(corpus["primary_before_1001"], capital=True),
               noun(corpus["primary_before_1001"], "record predates", "records predate"),
               spaced(corpus["primary_before_1601"])))


def primary_undated_block(corpus: dict) -> str:
    aside, undated = corpus["primary_set_aside"], corpus["primary_undated"]
    first = ("No implausible date had to be set aside" if aside == 0 else
             "%s implausible %s set aside rather than guessed at"
             % (number_word(aside, capital=True), noun(aside, "date was", "dates were")))
    return ("%s, and %s %s no date at all: none was invented for them."
            % (first, spaced(undated), noun(undated, "record carries", "records carry")))


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
            "the point: one number per thing, on every page. `data/stats.json` holds these counts "
            "under its `counted` key; its top-level series count all {kept} kept records, "
            "mentioned and held-aside ones included, and its `population` key says which is which."
            .format(counted=spaced(values["counted"]), mentioned=spaced(values["mentioned"]),
                    aside=spaced(values["aside"]), named=named, approach=approach,
                    approach_count=spaced(approach_count), kept=spaced(values["kept"])))


def root_dates_block(values: dict) -> str:
    """La date de la seconde lecture des notices du site, dans les limites du README."""
    refetch = refetch_sentence(values, "the %s source records of the public site"
                               % spaced(values["harvested"]))
    return ("The figures above describe the August 2026 harvest. %s\n  There is no incremental "
            "update yet." % refetch if refetch else
            "The figures above describe the August 2026 harvest.\n  There is no incremental "
            "update yet.")


def root_readme_block(values: dict) -> str:
    """Le README du dépôt, qui annonce la population du site en une phrase."""
    return ("**%s records, of which %s are counted**, %s mentioned only, %s held outside the "
            "count." % (spaced(values["kept"]), spaced(values["counted"]),
                        spaced(values["mentioned"]), spaced(values["aside"])))


def readme_untagged_block(values: dict) -> str:
    """La ligne du README sur les notices sans classe : au présent ou au passé.

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
    return ("today: %s of %s works (%s), joined on the catalogue number and then on the DOI, "
            "never on the title, which used to carry the citations of a review over to the book "
            "it reviewed."
            % (spaced(values["weight_covered"]), spaced(values["weight_total"]),
               ("%.1f %%" % share)))


def classification() -> dict | None:
    """Les classes de pertinence, recomptées sur les fichiers de tags livrés.

    Le README, la page de méthode et la citation annonçaient 21 080 notices
    classées et un dossier de 6 720 : les chiffres de la vague fédérée avant que
    la passe de rattrapage n'en tague vingt-quatre de plus. Les fichiers livrés
    en portent d'autres, et l'audit 6 a mesuré l'écart. Ils se comptent donc ici,
    sur les fichiers eux-mêmes : une notice retaguée dans une vague ultérieure
    compte une fois, avec sa dernière classe.
    """
    if not WAVES:
        return None
    latest: dict[str, dict] = {}
    counted_waves = 0
    for path in WAVES:
        manifest_path = path.with_name("manifest.json")
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("counts_in_global_cluster_classification") is False:
                continue
        counted_waves += 1
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
        "waves": counted_waves,
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
  works of Origen and approaches: {counted} of them ({core} core and {partial}
  partial) form the citable dossier. The code is under the MIT licence; the data
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
ROOT_BLOCKS = (("FIGURES:population-root", root_readme_block),
               ("FIGURES:harvest-dates", root_dates_block))

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
    absence_note = ("The other %s have no displayed summary." % spaced(values["without"])
                    if values["unsummarised_anywhere"] is None else
                    ("The other %s are not being withheld: %s of them appear in the working "
                     "corpus and no database there holds a summary of them either."
                     % (spaced(values["without"]),
                        spaced(values["unsummarised_anywhere"]))))
    return """
    <p><strong>Coverage.</strong> The source catalogues describe rather than summarise:
      {arrived_on_the_record} of the {records} records carry a summary of their own.
      Where another database summarises the same publication, that summary is joined to the
      record by catalogue number, by DOI, or by title and year, and {arrived_by_joining} records
      are covered that way. In all, <strong>{with_abstract} records of {records}
      ({share})</strong> show a summary. {absence_note}</p>
    <p><strong>Who wrote them.</strong> How a summary reached this file is one question; who
      wrote it is another, and the second is the one the credit answers.
      {written_by_the_catalogue} of the {with_abstract} were written by a catalogue the record was
      harvested from and {written_elsewhere} by another database, whichever route they took to get
      here. The full
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
        absence_note=absence_note,
        written_by_the_catalogue=spaced(values["written_by_the_catalogue"]),
        written_elsewhere=spaced(values["written_elsewhere"]),
        rows=rows,
    )


def labels_list(labels: list[str]) -> str:
    if len(labels) <= 1:
        return "".join(labels)
    return "; ".join(labels[:-1]) + "; and " + labels[-1]


def credits_block(values: dict) -> str:
    return """
    <p>Every summary displayed in the Explorer names the database that wrote it and links to
      the record there. {with_abstract} of the {records} mapped records carry one.
      {written_by_the_catalogue} were written by a catalogue the record was harvested from: {own}.
      The other {written_elsewhere} come from a database that describes the same publication:
      {named}. A summary written for this project, where one exists, says so instead of
      naming a database.</p>
""".format(
        with_abstract=spaced(values["with_abstract"]),
        records=spaced(values["records"]),
        written_by_the_catalogue=spaced(values["written_by_the_catalogue"]),
        written_elsewhere=spaced(values["written_elsewhere"]),
        own=labels_list(values["own_labels"]),
        named=labels_list(values["other_labels"]),
    )


def readme_block(values: dict) -> str:
    return ("\n%s of the %s records carry one: %s written by a catalogue the record was harvested "
            "from, %s by another database.\n" % (spaced(values["with_abstract"]), spaced(values["records"]),
                             spaced(values["written_by_the_catalogue"]),
                             spaced(values["written_elsewhere"])))


def data_readme_block(values: dict, corpus: dict) -> str:
    """Le périmètre du README de la couche de données, en français, sur une ligne.

    Ce README décrivait encore la moisson v0 (IxTheo seul, 2 116 notices) comme le
    périmètre courant (OR-52) ; ses chiffres viennent maintenant d'ici."""
    nbsp = "\u00a0"
    by_source = ", ".join("`%s` %s" % (source, spaced(count)) for source, count in
                          sorted(values["sources_harvested"].items(), key=lambda kv: (-kv[1], kv[0])))
    aside = values["aside"]
    return ("Corpus fédéré de %s libellés de source, interrogés par la notice d'autorité "
            "d'Origène (GND 118590235) et ses équivalents nationaux%s: %s notices de catalogue, "
            "réunies en %s grappes d'œuvre par la fusion (%s doublons réunis). Notices par source, "
            "avant fusion%s: %s. Les chiffres publiés comptent les grappes `core` et `partial` "
            "(%s)%s; %s grappes `marginal` sont listées sans être comptées, et %s %s hors compte. "
            "Les %s éditions, traductions et témoins manuscrits des œuvres d'Origène forment la "
            "couche primaire (`primary-layer.jsonl`), comptée dans aucun chiffre."
            % (spaced(values["source_count"]), nbsp, spaced(values["harvested"]),
               spaced(values["kept"]), spaced(values["duplicates"]), nbsp, by_source,
               spaced(values["counted"]), "\u202f", spaced(values["mentioned"]), spaced(aside),
               "grappe est tenue" if aside == 1 else "grappes sont tenues",
               spaced(corpus["primary_records"])))


def data_basis_block() -> str:
    """D'où viennent les vedettes et le contenant du snapshot, compté sur `site-records.jsonl`.

    Le README disait les sept sources d'autorité en `public-projection` après leur
    relecture dans les catalogues (audit du 13/09, OR-01) : la répartition vient
    maintenant du fichier, par base et par source."""
    nbsp, thin = "\u00a0", "\u202f"
    rows = [json.loads(line) for line in
            (DATA / "site-records.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    order = ("catalogue-record", "catalogue-record-refetched", "public-projection")
    by_basis: dict[str, dict[str, int]] = {}
    projected = []
    for row in rows:
        basis = row.get("subjects_container_basis") or "absent"
        sources = by_basis.setdefault(basis, {})
        sources[row.get("source") or "?"] = sources.get(row.get("source") or "?", 0) + 1
        if basis == "public-projection":
            projected.append("%s:%s" % (row.get("source"), row.get("source_id")))
    meta = json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}
    parts = []
    for basis in sorted(by_basis, key=lambda b: (order.index(b) if b in order else len(order), b)):
        sources = by_basis[basis]
        total = sum(sources.values())
        detail = ", ".join("`%s` %s" % (source, spaced(count)) for source, count in
                           sorted(sources.items(), key=lambda kv: (-kv[1], kv[0])))
        if basis == "public-projection" and len(projected) <= 5:
            detail = ", ".join("`%s`" % key for key in sorted(projected))
        read_again = (", relues dans leur catalogue le %s" % french_date(meta["refetched"])
                      if basis == "catalogue-record-refetched" and meta.get("refetched") else "")
        parts.append("`%s`%s: %s %s (%s)%s" % (basis, nbsp, spaced(total),
                                               "notice" if total == 1 else "notices", detail,
                                               read_again))
    return ("Répartition des %s notices du snapshot%s: %s." %
            (spaced(len(rows)), nbsp, ("%s; " % thin).join(parts)))


def replace(path: Path, block: str, opener: str, closer: str) -> bool:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(opener) + r".*?" + re.escape(closer), re.DOTALL)
    if not pattern.search(text):
        sys.exit("REFUS : balises « %s » absentes de %s : ajoutez-les autour du "
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
    # Les chiffres affichés se recomptent depuis abstracts.json, qui appartient
    # à l'arbre public. Le corpus fusionné n'est requis que pour la question
    # supplémentaire « aucune base ne possède de résumé » ; son absence ne doit
    # plus laisser les comptes publics périmés.
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
    corpus = corpus_figures(build)
    for name, page, block in (
            ("FIGURES:population-merge", "methode.html", method_merge_block(people)),
            ("FIGURES:population-sources-intro", "methode.html", method_sources_intro_block(people)),
            ("FIGURES:sources-word", "methode.html", sources_word_block(people)),
            ("FIGURES:population-dedup", "methode.html", method_dedup_block(people, corpus)),
            ("FIGURES:identifier-coverage", "methode.html", identifier_coverage_block(corpus)),
            ("FIGURES:primary-layer-count", "methode.html", spaced(corpus["primary_records"])),
            ("FIGURES:primary-layer-dates", "methode.html", primary_dates_block(corpus)),
            ("FIGURES:primary-layer-undated", "methode.html", primary_undated_block(corpus)),
            ("FIGURES:population-sources-sub", "credits.html", credits_sources_sub_block(people)),
            # L'Observatoire disait « Eight source labels » et « Seven catalogues » à la
            # main, sur la même page (OR-10, OR-39).
            ("FIGURES:sources-word-scope", "observatoire.html", sources_word_block(people)),
            ("FIGURES:sources-word-limits", "observatoire.html", sources_word_block(people)),
            ("FIGURES:domains-word", "observatoire.html", domains_word_block(build)),
            ("FIGURES:girota-notes", "credits.html", spaced(values["girota_notes"]))):
        opener, closer = marks(name)
        targets.append((build / page, block, opener, closer))
    # Une ligne par source moissonnée, sur la page de méthode (§ 1) et sur les
    # crédits : chaque compte est généré, et une source sans ligne arrête l'écriture.
    for source, count in people["sources_harvested"].items():
        opener, closer = marks("FIGURES:source-count-" + source)
        targets.append((build / "methode.html", spaced(count), opener, closer))
        if source != "ixtheo-k10plus":
            targets.append((build / "credits.html", spaced(count), opener, closer))
    targets.append((build / "methode.html",
                    "%s/%s" % (corpus["counted_year_min"], corpus["counted_year_max"]),
                    *LD_COVERAGE))
    targets.append((build / "methode.html", number_word(people["source_count"]), *LD_SOURCES))
    if people["editions"] is not None and people["editions"] != corpus["primary_records"]:
        raise SystemExit("META.excluded.relation_by differs from the primary layer")
    targets.append((DATA / "README.md", data_readme_block(people, corpus),
                    *marks("FIGURES:data-perimeter")))
    targets.append((DATA / "README.md", data_basis_block(), *marks("FIGURES:data-basis")))
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
