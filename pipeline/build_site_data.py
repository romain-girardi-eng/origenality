#!/usr/bin/env python3
"""Origenality — construction de la couche de données du site public.

Lit une moisson au format JSONL (v0 : IxTheo/K10plus seul) et produit les quatre
fichiers consommés par le front statique :

    site/data/graph.json     graphe publications / auteurs / sujets / contenants
    site/data/stats.json     séries agrégées de l'Observatoire
    site/data/abstracts.json résumés, chacun avec sa base et le lien vers sa notice
    site/data/META.json      provenance et périmètre

Les résumés sont publiés sous le régime d'attribution et de retrait de
`DATA_POLICY.md` : chacun nomme la base qui l'a écrit et renvoie à la notice
d'origine, et tout ayant droit obtient son retrait sur demande. Ils voyagent
dans un fichier à part, chargé après le premier rendu : le graphe pèse trois
mille nœuds et n'a pas à attendre des pages de prose pour s'afficher. Les trois
autres fichiers ne portent aucun résumé, et un contrôle le vérifie à l'écriture.

Le script n'utilise que la bibliothèque standard.

Usage :
    python3 pipeline/build_site_data.py
    python3 pipeline/build_site_data.py --enrich data/derived/abstracts_enrichment.jsonl
    python3 pipeline/build_site_data.py --input data/merged/corpus.jsonl \
        --min-subject 5 --min-container 8
    python3 pipeline/build_site_data.py --overview     # stats internes multi-sources
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fields import norm_year  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_INPUT = os.path.join(BASE, "data", "raw", "ixtheo", "records.jsonl")
def _site_data_dir(base: str) -> str:
    """La couche de données que les pages lisent : `site/data/` dans l'arbre de
    travail, `data/` dans l'arbre public — le générateur écrit là où le front va
    chercher (audit de clôture : le défaut fixe divergeait du fetch())."""
    for tools in (os.path.join(base, "site", "build-c", "tools"),
                  os.path.join(base, "site", "tools")):
        if os.path.exists(os.path.join(tools, "tree_paths.py")):
            sys.path.insert(0, tools)
            try:
                from tree_paths import data_dir  # noqa: E402
                return data_dir(base)
            except Exception:  # pragma: no cover - repli si l'aide est absente
                break
    return os.path.join(base, "site", "data")


DEFAULT_OUTDIR = _site_data_dir(BASE)
OVERVIEW_OUT = os.path.join(BASE, "data", "derived", "sources_overview.json")

HARVEST_DATE = "2026-08-15"
SOURCE_LABEL = "Index Theologicus / K10plus (CC0)"
SCOPE = "publications about Origen of Alexandria (GND 118590235)"

TITLE_MAX = 120
YEAR_MIN_SERIES = 1850
YEAR_MAX_SERIES = 2026
DECADE_START = 1900
TOP_SUBJECTS = 30
TOP_CONTAINERS = 20
TOP_LANGS_SERIES = 6

# Rôles MARC $4 écartés des nœuds « auteur » : ce ne sont pas des contributeurs
# intellectuels de la publication (éditeur commercial, imprimeur, institution
# de soutenance, organisme de normalisation).
ROLES_EXCLUDED = {"pbl", "prt", "dgg", "isb", "wpr"}

# Origène lui-même : sujet de tout le corpus, et auteur des volumes `both`
# (édition + études). Il ferait un moyeu trivial relié à tout le graphe.
ORIGEN_GND = "118590235"
ORIGEN_FORMS = {
    "origenes", "origen", "origene", "origenes von alexandrien",
    "origenes adamantius", "origen of alexandria", "origene di alessandria",
    "origene alessandrino", "origenes alexandrinus",
}

LANG_LABELS = {
    "eng": ("English", "anglais"),
    "ger": ("German", "allemand"),
    "ita": ("Italian", "italien"),
    "fre": ("French", "français"),
    "spa": ("Spanish", "espagnol"),
    "lat": ("Latin", "latin"),
    "grc": ("Ancient Greek", "grec ancien"),
    "gre": ("Greek", "grec"),
    "dut": ("Dutch", "néerlandais"),
    "dan": ("Danish", "danois"),
    "pol": ("Polish", "polonais"),
    "hun": ("Hungarian", "hongrois"),
    "por": ("Portuguese", "portugais"),
    "nor": ("Norwegian", "norvégien"),
    "hrv": ("Croatian", "croate"),
    "swe": ("Swedish", "suédois"),
    "rus": ("Russian", "russe"),
    "cat": ("Catalan", "catalan"),
    "rum": ("Romanian", "roumain"),
    "heb": ("Hebrew", "hébreu"),
    "und": ("Undetermined", "indéterminée"),
    "zxx": ("No linguistic content", "sans contenu linguistique"),
    "": ("Not coded", "non codée"),
}

TEMPORAL_HEADING = re.compile(r"^(Geschichte|History|Storia|Histoire)\s+[\d\[]", re.I)
YEAR_SPAN_HEADING = re.compile(r"^\d{1,4}\s*[-–/]\s*\d{1,4}$")


# --------------------------------------------------------------------------
# normalisation
# --------------------------------------------------------------------------

def strip_diacritics(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def norm_key(text: str) -> str:
    """Clé de dédoublonnage : sans diacritiques, minuscules, espaces resserrés.

    Volontairement conservatrice : elle ne fusionne que des formes identiques
    à la casse, aux accents et aux espaces près. Aucune réconciliation
    d'initiales ni de translittérations — le risque d'homonymie l'interdit.
    """
    text = strip_diacritics(text).lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(".,;:")


def slug(text: str, prefix: str) -> str:
    """Identifiant lisible dérivé d'un libellé.

    On garde les caractères alphanumériques de tous les alphabets : réduire à
    [a-z0-9] transformait en `a:x` ou `s:x` tout nom écrit en grec, en
    cyrillique ou en hébreu, et faisait collisionner entre eux des nœuds sans
    rapport. Un libellé sans aucun caractère alphanumérique retombe sur un
    hachage, jamais sur une constante partagée.
    """
    folded = strip_diacritics(text).lower()
    base = "".join(c if c.isalnum() else "-" for c in folded)
    base = re.sub(r"-+", "-", base).strip("-")
    if not base:
        base = "x" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}:{base}"


def truncate(text: str, limit: int = TITLE_MAX) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip(" ,;:.-") + "…"


# --------------------------------------------------------------------------
# lecture et mise au format commun
# --------------------------------------------------------------------------

def load_records(path: str) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                sys.exit(f"JSON invalide ligne {lineno} de {path} : {exc}")
    return records


# Pertinences qui font entrer une notice dans le périmètre publié. `none` reste
# dehors : c'est le bruit du corpus fédéré, et il est majoritaire.
PUBLISHED_RELEVANCE = ("core", "partial", "marginal")


def is_publication(record: dict, relevance: str | None = None,
                   federated: bool = False) -> bool:
    """Périmètre du graphe : les travaux SUR Origène.

    `relation` vaut "about", "by" ou "both" dans la moisson IxTheo. Les notices
    "by" sont des éditions des œuvres d'Origène : sources primaires, pas
    littérature secondaire ; elles sortent toujours.

    Sur une moisson à source unique, l'absence de `relation` vaut acceptation :
    la moisson a été bâtie sur une notice d'autorité, tout ce qu'elle contient
    est dans le périmètre.

    Sur un corpus FÉDÉRÉ, l'absence de `relation` ne prouve rien : les bases
    bibliométriques n'ont pas ce champ, et le corpus fédéré est majoritairement
    du bruit — vingt-six mille grappes que le tagueur classe `none`. La règle y
    est donc l'inverse : une notice n'entre que si un tag lui reconnaît une
    pertinence `core`, `partial` ou `marginal`. Pas de tag, pas d'entrée.
    """
    relation = record.get("relation")
    if relation is not None and relation not in ("about", "both"):
        return False
    if federated:
        return relevance in PUBLISHED_RELEVANCE
    return True


def ixtheo_pattern(attribution: dict):
    """Gabarit d'adresse de la moisson v0, lu dans DATA_POLICY.md.

    Le front interpole un PPN : le nom du paramètre change, la source de vérité
    non. Une base sans gabarit rend None plutôt qu'une chaîne inventée.
    """
    template = (attribution.get("ixtheo-k10plus") or {}).get("url_template")
    return template.replace("{id}", "{ppn}") if isinstance(template, str) else None


def load_relevance(path: str | None) -> dict[str, str]:
    """`notice_id` → pertinence, lue dans un fichier de tags sémantiques."""
    table: dict[str, str] = {}
    if not path:
        return table
    with open(path, encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                sys.exit(f"JSON invalide ligne {lineno} de {path} : {exc}")
            notice = row.get("notice_id")
            relevance = row.get("relevance")
            if notice and isinstance(relevance, str):
                table[str(notice)] = relevance
    return table


SUBJECT_KEYS = ("term", "display_name", "label", "name", "value")


def record_subjects(record: dict) -> list[str]:
    """Vedettes-matière brutes, tous champs d'indexation confondus.

    IxTheo : 650 (`subjects`) et 689 (`subject_chains`, l'indexation par chaînes
    propre à la base). Les autres moissons exposent `descriptors` ou `topics`.
    Les formes d'objet diffèrent d'une base à l'autre : OpenAlex écrit
    `display_name`, BIBP `{term, weight, index_language}` — son thésaurus, qui
    est la valeur propre de la source, serait perdu si l'on ne lisait que
    `display_name`.
    """
    out = []
    for field in ("subjects", "subject_chains", "descriptors", "topics"):
        values = record.get(field) or []
        if isinstance(values, (str, dict)):
            values = [values]
        for value in values:
            if isinstance(value, str):
                out.append(value)
            elif isinstance(value, dict):
                for key in SUBJECT_KEYS:
                    if isinstance(value.get(key), str) and value[key].strip():
                        out.append(value[key])
                        break
    return out


def clean_headings(raw_headings: list[str]) -> list[str]:
    """Découpe et allège les vedettes : subdivisions retirées, libellés lisibles."""
    cleaned: list[str] = []
    for raw in raw_headings:
        if not raw or not isinstance(raw, str):
            continue
        for part in re.split(r"\s*;\s*", raw):
            part = part.split("--")[0]          # subdivisions LCSH
            part = re.split(r"\s+/\s+", part)[0]  # hiérarchies BISAC/RAMEAU
            part = part.replace("<", " (").replace(">", ")")
            part = re.sub(r"\s+", " ", part).strip(" .,;:")
            if len(part) < 2 or len(part) > 60:
                continue
            if TEMPORAL_HEADING.match(part) or YEAR_SPAN_HEADING.match(part):
                continue
            if norm_key(part) in ORIGEN_FORMS:
                continue
            cleaned.append(part)
    return cleaned


def record_authors(record: dict) -> list[tuple[str, str | None]]:
    """Personnes créditées, hors Origène et hors rôles non intellectuels.

    Renvoie des couples (nom, identifiant GND ou None).
    """
    people = []
    for author in record.get("authors") or []:
        if isinstance(author, str):
            name, role, atype, gnd = author, None, "person", None
        else:
            name = author.get("name")
            role = author.get("role")
            atype = author.get("type", "person")
            gnd = author.get("gnd")
        if not name:
            continue
        if atype and atype != "person":      # congrès, collectivités éditrices
            continue
        if role in ROLES_EXCLUDED:
            continue
        if gnd == ORIGEN_GND or norm_key(name) in ORIGEN_FORMS:
            continue
        people.append((re.sub(r"\s+", " ", name).strip(" .,;"), gnd))
    return people


def author_ambiguity(pubs: list[dict]) -> dict[str, set]:
    """Noms normalisés portant plusieurs identifiants d'autorité distincts.

    Cas réel dans la moisson : « Gregorius » recouvre Grégoire d'Elvire
    (GND 118718711) et un autre Grégoire (118541919). Fusionner sur le nom
    confondrait deux personnes ; ces noms-là sont donc éclatés par GND.
    """
    gnds: dict[str, set] = defaultdict(set)
    for record in pubs:
        for name, gnd in record_authors(record):
            if gnd:
                gnds[norm_key(name)].add(gnd)
    return {k: v for k, v in gnds.items() if len(v) > 1}


def author_key(name: str, gnd: str | None, ambiguous: dict[str, set]) -> str:
    key = norm_key(name)
    if key in ambiguous:
        return f"{key}#{gnd or 'sans-gnd'}"
    return key


def author_label(name: str, gnd: str | None, ambiguous: dict[str, set]) -> str:
    if norm_key(name) in ambiguous:
        return f"{name} (GND {gnd})" if gnd else f"{name} (sans GND)"
    return name


def record_container(record: dict) -> tuple[str, str] | None:
    container = record.get("container")
    if not container:
        return None
    if isinstance(container, str):
        title, ctype = container, "host"
    else:
        title = container.get("title")
        ctype = container.get("type") or "host"
    if not title:
        return None
    title = title.replace("<", " (").replace(">", ")")
    return re.sub(r"\s+", " ", title).strip(" .,;:"), ctype


def record_year(record: dict):
    """Année, quel que soit le champ qui la porte (cf. pipeline/fields.py)."""
    return norm_year(record)


def record_format(record: dict) -> str:
    return record.get("format") or record.get("type") or "Unknown"


def record_lang(record: dict) -> str:
    lang = record.get("language")
    return lang if isinstance(lang, str) and lang.strip() else ""


def record_id(record: dict) -> str:
    """Identifiant de notice, du plus stable au moins stable.

    Sur un corpus fédéré, `source_id` a disparu du niveau supérieur : c'est
    `origenality_id` qui identifie le groupe fusionné. Sans lui, le repli sur
    le titre faisait porter le même identifiant de nœud à toutes les notices
    intitulées « Index » ou « Bibliographie ».
    """
    return str(record.get("origenality_id") or record.get("source_id")
               or record.get("doi") or record.get("title") or "")


def record_sources(record: dict) -> list[str]:
    """Bases d'où provient la notice — une seule, ou plusieurs après fusion."""
    sources = record.get("sources")
    if isinstance(sources, list):
        names = []
        for entry in sources:
            name = entry.get("source") if isinstance(entry, dict) else entry
            if isinstance(name, str) and name and name not in names:
                names.append(name)
        if names:
            return sorted(names)
    single = record.get("source")
    return [single] if isinstance(single, str) and single else []


def record_url(record: dict):
    for field in ("url", "ixtheo_url", "open_access_pdf"):
        value = record.get(field)
        if isinstance(value, str) and value.startswith("http"):
            return value
    doi = record.get("doi")
    if isinstance(doi, str) and doi.startswith("10."):
        return "https://doi.org/" + doi
    return None


# --------------------------------------------------------------------------
# graphe
# --------------------------------------------------------------------------

def build_graph(pubs: list[dict], min_subject: int, min_container: int) -> dict:
    ambiguous = author_ambiguity(pubs)
    # 1er passage : compter pour appliquer les seuils
    subject_counts: Counter = Counter()
    subject_labels: dict[str, Counter] = defaultdict(Counter)
    container_counts: Counter = Counter()
    container_labels: dict[str, Counter] = defaultdict(Counter)
    container_types: dict[str, Counter] = defaultdict(Counter)
    author_labels: dict[str, Counter] = defaultdict(Counter)

    per_record = []
    for record in pubs:
        headings = clean_headings(record_subjects(record))
        heading_keys = []
        for heading in headings:
            key = norm_key(heading)
            if not key or key in heading_keys:
                continue
            heading_keys.append(key)
            subject_labels[key][heading] += 1
        for key in heading_keys:
            subject_counts[key] += 1

        author_keys = []
        for name, gnd in record_authors(record):
            key = author_key(name, gnd, ambiguous)
            if not key or key in author_keys:
                continue
            author_keys.append(key)
            author_labels[key][author_label(name, gnd, ambiguous)] += 1

        container = record_container(record)
        container_key = None
        if container:
            title, ctype = container
            container_key = norm_key(title)
            container_counts[container_key] += 1
            container_labels[container_key][title] += 1
            container_types[container_key][ctype] += 1

        per_record.append((record, author_keys, heading_keys, container_key))

    kept_subjects = {k for k, n in subject_counts.items() if n >= min_subject}
    kept_containers = {k for k, n in container_counts.items() if n >= min_container}

    # 2e passage : nœuds et arêtes
    nodes: list[dict] = []
    index: dict[str, int] = {}
    collisions = 0

    def unique_id(candidate: str, seed: str) -> str:
        """Identifiant de nœud unique. Deux libellés distincts qui se réduisent
        au même slug reçoivent un suffixe de hachage, au lieu de se recouvrir
        silencieusement dans le graphe."""
        nonlocal collisions
        if candidate not in index:
            return candidate
        collisions += 1
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:6]
        disambiguated = f"{candidate}~{digest}"
        suffix = 2
        while disambiguated in index:
            disambiguated = f"{candidate}~{digest}-{suffix}"
            suffix += 1
        return disambiguated

    def add_node(node: dict) -> int:
        index[node["id"]] = len(nodes)
        nodes.append(node)
        return index[node["id"]]

    def preferred(labels: Counter) -> str:
        # forme de surface la plus fréquente ; en cas d'égalité, la plus longue
        # (elle porte les diacritiques et la casse complète)
        return sorted(labels.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))[0][0]

    for position, (record, _, _, _) in enumerate(per_record):
        raw_id = record_id(record) or "sans-id"
        node = {
            "id": unique_id("p:" + raw_id, f"{raw_id}#{position}"),
            "k": "pub",
            "title": truncate(record.get("title") or "[sans titre]"),
            "year": record_year(record),
            "lang": record_lang(record),
            "type": record_format(record),
            "rel": record.get("relation"),
            "ppn": record.get("source_id"),
            "deg": 0,
        }
        sources = record_sources(record)
        if sources:
            node["src"] = sources
        url = record_url(record)
        if url:
            node["url"] = url
        if record.get("doi"):
            node["doi"] = record["doi"]
        # publisher et ISBN : annoncés dans META.fields_published et sur la page
        # Méthode, donc écrits dans la charge utile plutôt que promis à vide.
        publisher = (record.get("publisher") or "").strip()
        if publisher:
            node["pub"] = truncate(publisher, 80)
        isbn = record.get("isbn")
        if isinstance(isbn, list):
            isbn = next((str(v).strip() for v in isbn if str(v).strip()), "")
        isbn = (isbn or "").strip()
        if isbn:
            node["isbn"] = isbn
        add_node(node)

    # les arêtes visent les nœuds par clé, pas par slug recalculé : le slug
    # peut avoir reçu un suffixe de désambiguïsation.
    author_ids: dict[str, str] = {}
    subject_ids: dict[str, str] = {}
    container_ids: dict[str, str] = {}

    for key, labels in author_labels.items():
        node_id = unique_id(slug(key, "a"), "a|" + key)
        author_ids[key] = node_id
        add_node({"id": node_id, "k": "author",
                  "label": preferred(labels), "deg": 0})
    for key in sorted(kept_subjects):
        node_id = unique_id(slug(key, "s"), "s|" + key)
        subject_ids[key] = node_id
        add_node({"id": node_id, "k": "subject",
                  "label": preferred(subject_labels[key]), "deg": 0})
    for key in sorted(kept_containers):
        ctype = container_types[key].most_common(1)[0][0]
        node_id = unique_id(slug(key, "c"), "c|" + key)
        container_ids[key] = node_id
        add_node({"id": node_id, "k": "container",
                  "label": preferred(container_labels[key]),
                  "ctype": ctype, "deg": 0})

    edges = []
    seen_edges = set()

    def add_edge(src: int, tgt: int, rel: str) -> None:
        if (src, tgt) in seen_edges:
            return
        seen_edges.add((src, tgt))
        edges.append({"s": src, "t": tgt, "r": rel})
        nodes[src]["deg"] += 1
        nodes[tgt]["deg"] += 1

    for position, (record, author_keys, heading_keys, container_key) in enumerate(per_record):
        for key in author_keys:
            add_edge(position, index[author_ids[key]], "aut")
        for key in heading_keys:
            if key in kept_subjects:
                add_edge(position, index[subject_ids[key]], "sub")
        if container_key and container_key in kept_containers:
            add_edge(position, index[container_ids[container_key]], "in")

    return {
        "generated": HARVEST_DATE,
        "legend": {
            "k": {"pub": "publication", "author": "auteur",
                  "subject": "sujet", "container": "revue ou collection"},
            "r": {"aut": "publication → auteur", "sub": "publication → sujet",
                  "in": "publication → contenant"},
        },
        "thresholds": {"subject_min_publications": min_subject,
                       "container_min_publications": min_container},
        "counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "id_collisions_disambiguated": collisions,
            "nodes_by_kind": dict(Counter(n["k"] for n in nodes)),
            "edges_by_relation": dict(Counter(e["r"] for e in edges)),
        },
        "nodes": nodes,
        "edges": edges,
    }


# --------------------------------------------------------------------------
# statistiques
# --------------------------------------------------------------------------

def lang_entry(code: str, count: int) -> dict:
    label_en, label_fr = LANG_LABELS.get(code, (code, code))
    return {"code": code or "none", "label_en": label_en,
            "label_fr": label_fr, "count": count}


def build_stats(pubs: list[dict], min_subject: int, min_container: int) -> dict:
    ambiguous = author_ambiguity(pubs)
    by_year: Counter = Counter()
    by_lang: Counter = Counter()
    by_format: Counter = Counter()
    by_lang_year: dict[str, Counter] = defaultdict(Counter)
    authors: set[str] = set()
    subject_counts: Counter = Counter()
    subject_labels: dict[str, Counter] = defaultdict(Counter)
    container_counts: Counter = Counter()
    container_labels: dict[str, Counter] = defaultdict(Counter)
    container_types: dict[str, Counter] = defaultdict(Counter)
    year_unknown = 0
    year_before_series = 0
    years_all: list[int] = []

    for record in pubs:
        year = record_year(record)
        lang = record_lang(record)
        by_lang[lang] += 1
        by_format[record_format(record)] += 1
        if year is None:
            year_unknown += 1
        else:
            years_all.append(year)
            if year < YEAR_MIN_SERIES:
                year_before_series += 1
            elif year <= YEAR_MAX_SERIES:
                by_year[year] += 1
                by_lang_year[lang][year] += 1
        for name, gnd in record_authors(record):
            authors.add(author_key(name, gnd, ambiguous))
        seen_headings = set()
        for heading in clean_headings(record_subjects(record)):
            key = norm_key(heading)
            if not key or key in seen_headings:
                continue
            seen_headings.add(key)
            subject_counts[key] += 1
            subject_labels[key][heading] += 1
        container = record_container(record)
        if container:
            title, ctype = container
            key = norm_key(title)
            container_counts[key] += 1
            container_labels[key][title] += 1
            container_types[key][ctype] += 1

    def preferred(labels: Counter) -> str:
        return sorted(labels.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))[0][0]

    years = list(range(YEAR_MIN_SERIES, YEAR_MAX_SERIES + 1))
    top_langs = [code for code, _ in by_lang.most_common() if code][:TOP_LANGS_SERIES]

    decades = Counter()
    for year in years_all:
        if year >= DECADE_START:
            decades[(year // 10) * 10] += 1
    last_decade = (YEAR_MAX_SERIES // 10) * 10

    return {
        "generated": HARVEST_DATE,
        "totals": {
            "records": len(pubs),
            "distinct_authors": len(authors),
            "distinct_subjects": len(subject_counts),
            "distinct_containers": len(container_counts),
            "year_min": min(years_all) if years_all else None,
            "year_max": max(years_all) if years_all else None,
            "year_unknown": year_unknown,
            "records_before_series_start": year_before_series,
            "records_with_doi": sum(1 for r in pubs if r.get("doi")),
            "records_with_isbn": sum(1 for r in pubs if r.get("isbn")),
        },
        "by_year": {
            "range": [YEAR_MIN_SERIES, YEAR_MAX_SERIES],
            "years": years,
            "total": [by_year.get(y, 0) for y in years],
            "by_language": [
                {"code": code,
                 "label_en": LANG_LABELS.get(code, (code, code))[0],
                 "label_fr": LANG_LABELS.get(code, (code, code))[1],
                 "counts": [by_lang_year[code].get(y, 0) for y in years]}
                for code in top_langs
            ],
            "note": ("série tronquée à mi-2026 ; %d notices sans année et %d antérieures "
                     "à %d ne figurent pas dans la série"
                     % (year_unknown, year_before_series, YEAR_MIN_SERIES)),
        },
        "by_decade": [
            {"decade": d, "count": decades.get(d, 0)}
            for d in range(DECADE_START, last_decade + 1, 10)
        ],
        "by_format": [{"format": f, "count": n} for f, n in by_format.most_common()],
        "by_language": [lang_entry(code, n) for code, n in by_lang.most_common()],
        "top_subjects": [
            {"label": preferred(subject_labels[k]), "count": n}
            for k, n in subject_counts.most_common(TOP_SUBJECTS)
        ],
        "top_containers": [
            {"label": preferred(container_labels[k]),
             "type": container_types[k].most_common(1)[0][0], "count": n}
            for k, n in container_counts.most_common(TOP_CONTAINERS)
        ],
        "graph_thresholds": {"subject_min_publications": min_subject,
                             "container_min_publications": min_container},
    }


# --------------------------------------------------------------------------
# écriture et contrôles
# --------------------------------------------------------------------------

FORBIDDEN_KEYS = {"abstract", "abstract_rights", "abstract_inverted_index", "summary"}


def assert_no_forbidden_key(payload, path: str) -> None:
    """Contrôle structurel : les résumés vivent dans un fichier et un seul.

    Le graphe, les séries et la fiche de provenance ne portent pas de résumé —
    non par interdit juridique, mais parce qu'ils sont chargés au premier rendu
    et qu'une clé de résumé qui s'y glisserait doublerait la charge sans que
    personne le remarque. `abstracts.json` est écrit par un autre chemin.
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.lower() in FORBIDDEN_KEYS:
                sys.exit(f"REFUS : {os.path.basename(path)} porte la clé « {key} ».")
            assert_no_forbidden_key(value, path)
    elif isinstance(payload, list):
        for item in payload:
            assert_no_forbidden_key(item, path)


def dump(path: str, payload: dict, check_keys: bool = True) -> int:
    if check_keys:
        assert_no_forbidden_key(payload, path)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.write("\n")
    return os.path.getsize(path)


def load_attribution(policy_path: str) -> dict:
    """La table des bases créditées, lue dans DATA_POLICY.md et nulle part ailleurs."""
    sys.path.insert(0, os.path.join(BASE, "scripts"))
    import check_release  # noqa: E402  (import tardif : le chemin dépend de BASE)
    from pathlib import Path
    return check_release.load_policy(Path(policy_path))


def build_abstracts(pubs: list[dict], enrich_path: str | None, policy: dict) -> dict:
    """Les résumés du périmètre, chacun avec sa base et le lien vers sa notice.

    Deux apports, dans cet ordre. Le résumé que porte la notice elle-même passe
    d'abord ; l'enrichissement produit par `site/build-c/tools/enrich_abstracts.py`
    ne comble que les vides. Une notice ne reçoit jamais deux résumés, et jamais
    un résumé venu d'ailleurs par-dessus le sien.
    """
    sys.path.insert(0, os.path.join(BASE, "scripts"))
    import check_release  # noqa: E402

    attribution = policy["attribution"]
    # Retraits demandés. Une base inscrite dans `withdrawn` (DATA_POLICY.md)
    # sort du site à la construction suivante : la page Crédits promet que les
    # résumés quittent le site et le dump suivant, et la promesse ne tient que
    # si une seule ligne à ajouter suffit à l'exécuter.
    withdrawn = {str(name) for name in policy.get("withdrawn") or []}
    by_key: dict[str, dict] = {}
    own = 0
    removed = 0
    # Le fichier d'enrichissement couvre toute la moisson ; le site n'en publie
    # que le périmètre retenu. Sans ce garde, des résumés d'éditions d'Origène
    # entreraient dans le fichier et gonfleraient la couverture annoncée.
    in_scope = {record.get("source_id") or record_id(record) for record in pubs}

    for record in pubs:
        text = record.get("abstract")
        if not isinstance(text, str) or not text.strip():
            continue
        source = check_release.abstract_source(record)
        if not source or source not in attribution:
            continue
        if source in withdrawn:
            removed += 1
            continue
        key = record.get("source_id") or record_id(record)
        if not key:
            continue
        entry = {"t": " ".join(text.split()), "s": source}
        # Le lien du crédit mène à la notice QUI A ÉCRIT le résumé, jamais à
        # l'adresse générique de la grappe : celle-ci peut venir d'une tout
        # autre base, et le lecteur qui clique sous un résumé OpenAlex arrivait
        # sur la fiche Adamantius de la même publication. `attribution_link`
        # lit d'abord `abstract_url` (recopié de la notice donatrice à la
        # fusion), sinon applique le gabarit de la base donatrice à SON
        # identifiant — et rend None quand aucune des deux voies n'aboutit.
        link = check_release.attribution_link(record, source, attribution[source])
        if link:
            entry["u"] = link
        by_key[key] = entry
        own += 1

    joined = 0
    if enrich_path and os.path.isfile(enrich_path):
        with open(enrich_path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                key = row.get("ppn")
                if not key or key in by_key or key not in in_scope:
                    continue
                source = row.get("source")
                if source not in attribution:
                    continue
                if source in withdrawn:
                    removed += 1
                    continue
                entry = {"t": row["text"], "s": source, "j": row.get("join")}
                if row.get("url"):
                    entry["u"] = row["url"]
                if source == "generated":
                    entry["k"] = "generated"
                by_key[key] = entry
                joined += 1

    return {
        "generated": HARVEST_DATE,
        "regime": policy.get("regime"),
        "contact": policy.get("contact"),
        "sources": {key: {"label": val["label"]} for key, val in attribution.items()},
        "coverage": {
            "records": len(pubs),
            "with_abstract": len(by_key),
            "from_the_record_itself": own,
            "joined_from_the_federated_corpus": joined,
            "withdrawn_on_request": removed,
        },
        "withdrawn_sources": sorted(withdrawn),
        "byPpn": by_key,
    }


def build_overview(raw_dir: str, out_path: str) -> None:
    """Stats internes de comparaison des moissons. Ne sort jamais dans site/."""
    entries = []
    for name in sorted(os.listdir(raw_dir)):
        path = os.path.join(raw_dir, name, "records.jsonl")
        if not os.path.isfile(path):
            continue
        count = 0
        years: list[int] = []
        noise = 0
        with_doi = 0
        with_abstract = 0
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                count += 1
                year = record_year(record)
                if year and 500 <= year <= 2026:
                    years.append(year)
                if record.get("noise_guess") is True:
                    noise += 1
                if record.get("doi"):
                    with_doi += 1
                if record.get("abstract"):
                    with_abstract += 1
        entries.append({
            "source": name,
            "records": count,
            "year_min": min(years) if years else None,
            "year_max": max(years) if years else None,
            "flagged_noise": noise,
            "with_doi": with_doi,
            "with_abstract": with_abstract,
        })
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump({"generated": HARVEST_DATE,
                   "note": "usage interne ; comptes bruts, aucun filtrage de pertinence",
                   "sources": entries}, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"→ {out_path}")
    for entry in entries:
        print(f"   {entry['source']:<16} {entry['records']:>6} notices  "
              f"bruit {entry['flagged_noise']:>5}  résumés {entry['with_abstract']:>5}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--out-dir", default=DEFAULT_OUTDIR)
    parser.add_argument("--min-subject", type=int, default=3)
    parser.add_argument("--min-container", type=int, default=5)
    parser.add_argument("--source-label", default=None,
                        help="obligatoire sur un corpus fédéré")
    parser.add_argument("--scope", default=None,
                        help="obligatoire sur un corpus fédéré")
    parser.add_argument("--license", default=None,
                        help="licence des métadonnées publiées ; sur un corpus "
                             "fédéré, à défaut, aucune licence unique n'est affirmée")
    parser.add_argument("--harvested", default=HARVEST_DATE)
    parser.add_argument("--enrich", default=os.path.join(BASE, "data", "derived",
                                                         "abstracts_enrichment.jsonl"),
                        help="résumés joints depuis le corpus fédéré ; ignoré s'il n'existe pas")
    parser.add_argument("--policy", default=os.path.join(BASE, "DATA_POLICY.md"))
    parser.add_argument("--tags", default=None,
                        help="tags sémantiques (JSONL) ; obligatoire sur un "
                             "corpus fédéré : la pertinence commande l'entrée")
    parser.add_argument("--dry-run", action="store_true",
                        help="compte et décrit le périmètre, n'écrit aucun fichier")
    parser.add_argument("--overview", action="store_true",
                        help="produit data/derived/sources_overview.json et sort")
    args = parser.parse_args()

    if args.overview:
        build_overview(os.path.join(BASE, "data", "raw"), OVERVIEW_OUT)
        return

    records = load_records(args.input)

    # Un corpus fédéré porte `sources` (liste des bases d'origine du groupe
    # fusionné). Les valeurs par défaut de ce script décrivent IxTheo/K10plus
    # en CC0 : les appliquer à un corpus multi-sources attribuerait à K10plus
    # des notices S2, BIBP, GIROTA, Dialnet ou ISIDORE, et effacerait leur
    # licence propre. On refuse donc l'implicite.
    federated = any(isinstance(r.get("sources"), list) for r in records)
    if federated and (not args.source_label or not args.scope):
        sys.exit(
            "REFUS : corpus fédéré (champ « sources » présent) — --source-label "
            "et --scope sont obligatoires.\n"
            "Les valeurs par défaut (« %s », CC0) ne valent que pour la moisson "
            "IxTheo seule ; les appliquer ici attribuerait à K10plus des notices "
            "venues d'autres bases." % SOURCE_LABEL)
    if federated and not args.tags:
        sys.exit(
            "REFUS : corpus fédéré — --tags est obligatoire.\n"
            "Sans les tags sémantiques, le périmètre se réduirait au champ "
            "`relation`, que les bases bibliométriques n'ont pas : tout le bruit "
            "du corpus fédéré entrerait dans le graphe. Une notice entre sur sa "
            "pertinence (core, partial, marginal), et sur rien d'autre.")
    source_label = args.source_label or SOURCE_LABEL
    scope = args.scope or SCOPE
    policy = load_attribution(args.policy)
    attribution = policy["attribution"]

    if args.license:
        license_label = args.license
    elif federated:
        license_label = ("licences multiples selon la source — aucune licence "
                         "unique affirmée ; voir la licence par source dans "
                         "META.sources_present et la provenance par notice")
    else:
        license_label = attribution.get("ixtheo-k10plus", {}).get(
            "license", "CC0 1.0 (métadonnées K10plus)")

    relevance = load_relevance(args.tags)
    pubs = [r for r in records
            if is_publication(r, relevance.get(record_id(r)), federated)]
    if federated:
        excluded_relevance = Counter(
            relevance.get(record_id(r)) or "(sans tag)" for r in records
            if not is_publication(r, relevance.get(record_id(r)), federated))
        print(f"{len(records)} notices lues, {len(pubs)} retenues "
              f"(relevance core/partial/marginal, relation about/both) depuis "
              f"{os.path.relpath(args.input, BASE)} — corpus fédéré")
        print("   écartées : " + ", ".join(f"{name} {count}" for name, count
                                           in excluded_relevance.most_common()))
    else:
        print(f"{len(records)} notices lues, {len(pubs)} retenues "
              f"(relation about/both) depuis {os.path.relpath(args.input, BASE)}")

    graph = build_graph(pubs, args.min_subject, args.min_container)
    stats = build_stats(pubs, args.min_subject, args.min_container)
    abstracts = build_abstracts(pubs, args.enrich, policy)
    meta = {
        "source": source_label,
        "harvested": args.harvested,
        "records": len(pubs),
        "scope": scope,
        "records_harvested_total": len(records),
        "federated": federated,
        # Chaque base présente est nommée avec SON libellé et SA licence, lus
        # dans DATA_POLICY.md. Un corpus fédéré n'a pas de licence unique :
        # l'afficher « CC0, K10plus » attribuait à un catalogue allemand des
        # notices Dialnet, BIBP ou GIROTA. Le nœud porte `src`, la liste de ses
        # bases ; la table ci-dessous dit ce que vaut chacune.
        "sources_present": [
            {"source": name, "records": count,
             "label": attribution.get(name, {}).get("label", name),
             "license": attribution.get(name, {}).get(
                 "license", "conditions propres à la source, non déclarées ici"),
             "record_url_pattern": attribution.get(name, {}).get("url_template")}
            for name, count in Counter(name for r in pubs
                                       for name in record_sources(r)).most_common()],
        "excluded": {
            "relation_by": sum(1 for r in records if r.get("relation") == "by"),
            "reason": "éditions des œuvres d'Origène : sources primaires, hors littérature secondaire",
        },
        "fields_published": ["title", "authors", "year", "language", "container",
                             "publisher", "doi", "isbn", "subjects", "format", "relation"],
        "summaries": {
            "published": True,
            "regime": policy.get("regime"),
            "contact": policy.get("contact"),
            "coverage": abstracts["coverage"],
            "note": "chaque texte porte sa base d'origine et le lien vers sa notice ; "
                    "retrait sur demande de tout ayant droit",
        },
        "license": license_label,
        # Un gabarit d'adresse unique ne vaut que pour une moisson à source
        # unique. Sur un corpus fédéré, chaque base a le sien, dans
        # `sources_present`.
        "record_url_pattern": (None if federated else ixtheo_pattern(attribution)),
        "relevance_published": list(PUBLISHED_RELEVANCE) if federated else None,
        "tags": os.path.relpath(args.tags, BASE) if args.tags else None,
    }

    if args.dry_run:
        print("essai à blanc : aucun fichier écrit")
        print(f"   notices entrées : {meta['records']}")
        if federated:
            entered = Counter(relevance.get(record_id(r)) or "(sans tag)"
                              for r in pubs)
            print("   pertinences entrées : " + ", ".join(
                f"{name} {count}" for name, count in entered.most_common()))
        print("   sources déclarées dans META :")
        for entry in meta["sources_present"]:
            print(f"     {entry['source']:<20} {entry['records']:>6}  "
                  f"{entry['label']} — {entry['license']}")
        print(f"   licence globale : {meta['license']}")
        print(f"   pertinences publiées : {meta['relevance_published']}")
        counts = graph["counts"]
        print(f"   graphe : {counts['nodes']} nœuds, {counts['edges']} arêtes")
        print(f"   résumés : {abstracts['coverage']['with_abstract']}")
        return

    sizes = {
        "graph.json": dump(os.path.join(args.out_dir, "graph.json"), graph),
        "stats.json": dump(os.path.join(args.out_dir, "stats.json"), stats),
        "abstracts.json": dump(os.path.join(args.out_dir, "abstracts.json"),
                               abstracts, check_keys=False),
        "META.json": dump(os.path.join(args.out_dir, "META.json"), meta),
    }

    coverage = abstracts["coverage"]
    share = 100 * coverage["with_abstract"] / max(1, coverage["records"])
    print(f"résumés : {coverage['with_abstract']} sur {coverage['records']} notices "
          f"({share:.1f} %) — {coverage['from_the_record_itself']} de la notice, "
          f"{coverage['joined_from_the_federated_corpus']} joints")

    counts = graph["counts"]
    print(f"graphe : {counts['nodes']} nœuds {counts['nodes_by_kind']}, "
          f"{counts['edges']} arêtes {counts['edges_by_relation']}")
    for name, size in sizes.items():
        print(f"   {name:<12} {size/1024:8.1f} Ko")


if __name__ == "__main__":
    main()
