#!/usr/bin/env python3
"""Origenality — harmonisation des champs hétérogènes des moissons.

Chaque source nomme et code ses champs à sa façon : Adamantius date par
`year_bib_parsed`, IxTheo typologise par `format`, BIBP par `doc_type`,
Semantic Scholar par `publication_types`, et les codes de langue mélangent
ISO 639-1, ISO 639-2/B et des libellés en clair. Tout ce qui compte des
notices — statistiques, fusion, graphe — passe d'abord par ici, faute de quoi
une source entière disparaît des séries ou se dédouble sous deux codes.

Vocabulaire de type retenu : article, book, chapter, review, dissertation,
other (type présent mais non reconnu), "?" (aucun champ de type).
"""
import unicodedata

# --------------------------------------------------------------------------
# années
# --------------------------------------------------------------------------

YEAR_MIN = 500
YEAR_MAX = 2026


def norm_year(record, year_min=YEAR_MIN, year_max=YEAR_MAX):
    """Année de publication, quel que soit le champ qui la porte.

    Ordre : `year`, puis `year_bib_parsed` (Adamantius, liste d'années — on
    retient la plus ancienne), puis les quatre premiers caractères de
    `publication_date`.
    """
    candidates = []
    value = record.get("year")
    if isinstance(value, list):
        candidates.extend(value)
    else:
        candidates.append(value)
    parsed = record.get("year_bib_parsed")
    if isinstance(parsed, list):
        candidates.extend(parsed)
    elif parsed is not None:
        candidates.append(parsed)
    date = record.get("publication_date")
    if isinstance(date, str) and len(date) >= 4:
        candidates.append(date[:4])

    years = []
    for candidate in candidates:
        if isinstance(candidate, bool) or candidate is None:
            continue
        try:
            year = int(str(candidate).strip()[:4])
        except (TypeError, ValueError):
            continue
        if year_min <= year <= year_max:
            years.append(year)
    return min(years) if years else None


# --------------------------------------------------------------------------
# langues
# --------------------------------------------------------------------------

# ISO 639-2/B (et quelques 639-2/T) vers ISO 639-1. Les codes sans équivalent
# 639-1 (grec ancien, syriaque, moyen français, indéterminé) sont conservés.
ISO2_TO_ISO1 = {
    "eng": "en", "ger": "de", "deu": "de", "fre": "fr", "fra": "fr",
    "spa": "es", "ita": "it", "lat": "la", "gre": "el", "ell": "el",
    "dut": "nl", "nld": "nl", "dan": "da", "pol": "pl", "hun": "hu",
    "por": "pt", "nor": "no", "hrv": "hr", "swe": "sv", "rus": "ru",
    "cat": "ca", "rum": "ro", "ron": "ro", "heb": "he", "ara": "ar",
    "tur": "tr", "cze": "cs", "ces": "cs", "jpn": "ja", "kor": "ko",
    "chi": "zh", "zho": "zh", "ukr": "uk", "fin": "fi", "slo": "sk",
    "slk": "sk", "slv": "sl", "bul": "bg", "gle": "ga", "baq": "eu",
    "eus": "eu", "glg": "gl", "mal": "ml", "ind": "id", "war": "war",
    "grc": "grc", "syr": "syr", "frm": "frm", "und": "und", "zxx": "zxx",
    "mul": "mul",
}

# libellés en clair rencontrés chez BIBP et ISIDORE
LANG_NAMES = {
    "francais": "fr", "french": "fr", "anglais": "en", "english": "en",
    "allemand": "de", "german": "de", "espagnol": "es", "spanish": "es",
    "italien": "it", "italian": "it", "latin": "la", "grec": "el",
    "grec ancien": "grc", "portugais": "pt", "portuguese": "pt",
    "neerlandais": "nl", "dutch": "nl", "russe": "ru", "russian": "ru",
    "catalan": "ca", "polonais": "pl", "polish": "pl", "hebreu": "he",
    "arabe": "ar", "syriaque": "syr",
}


def _strip_diacritics(text):
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def norm_lang(value):
    """Code de langue harmonisé, ou "?" si la notice n'en porte pas.

    Accepte un code ISO 639-1 ou 639-2, un libellé en clair, une liste, et les
    valeurs composites du type « fr en » ou « fr; » (on retient la première).
    """
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, str):
        return "?"
    text = _strip_diacritics(value).lower().strip()
    text = text.strip(".;,/ ")
    if not text:
        return "?"
    if text in LANG_NAMES:
        return LANG_NAMES[text]
    first = text.replace(";", " ").replace(",", " ").replace("/", " ").split()
    if not first:
        return "?"
    code = first[0]
    if code in LANG_NAMES:
        return LANG_NAMES[code]
    if code in ISO2_TO_ISO1:
        return ISO2_TO_ISO1[code]
    if len(code) == 2:
        return code
    return code


# --------------------------------------------------------------------------
# types de document
# --------------------------------------------------------------------------

TYPE_FIELDS = ("type", "format", "doc_type", "publication_types")

TYPE_MAP = {
    # article
    "article": "article", "journal-article": "article", "journalarticle": "article",
    "articulo_revista": "article", "articulo cientifico": "article",
    "artículo científico": "article", "info:eu-repo/semantics/article": "article",
    "spoglio / testo a stampa": "article", "spoglio / testo manoscritto": "article",
    "journal article": "article", "articolo": "article", "artigo": "article",
    "journalarticle,review": "review",
    # book
    "book": "book", "monograph": "book", "edited-book": "book", "libro": "book",
    "monografia / testo a stampa": "book", "monografia / testo manoscritto": "book",
    "livre": "book", "bookseries": "book", "monografia": "book",
    "info:eu-repo/semantics/book": "book",
    # chapter
    "book-chapter": "chapter", "chapter": "chapter", "book-part": "chapter",
    "bookchapter": "chapter", "info:eu-repo/semantics/bookpart": "chapter",
    "reference-entry": "chapter", "dictionary entry/article": "chapter",
    "proceedings-article": "chapter", "conference-paper": "chapter",
    "conferencepaper": "chapter", "contribution": "chapter",
    # review
    "review": "review", "book-review": "review", "rev": "review",
    "compterendu": "review", "notecritique": "review", "notcrit": "review",
    "recension": "review", "bookreview": "review", "resena": "review",
    # dissertation
    "dissertation": "dissertation", "these": "dissertation", "thesis": "dissertation",
    "tesis": "dissertation", "tesi": "dissertation", "doctoralthesis": "dissertation",
    "info:eu-repo/semantics/doctoralthesis": "dissertation",
    "info:eu-repo/semantics/masterthesis": "dissertation",
}

TYPE_VOCABULARY = ("article", "book", "chapter", "review", "dissertation", "other")


def _type_candidates(record):
    for field in TYPE_FIELDS:
        value = record.get(field)
        if isinstance(value, str):
            if value.strip():
                yield value.strip()
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    yield item.strip()


def norm_type(record):
    """Type harmonisé. "?" si aucun champ de type n'est renseigné."""
    seen = False
    for raw in _type_candidates(record):
        seen = True
        key = _strip_diacritics(raw).lower().strip()
        if key in TYPE_MAP:
            return TYPE_MAP[key]
    return "other" if seen else "?"


def raw_type(record):
    """Première valeur brute de type, pour signaler ce qui reste non mappé."""
    for raw in _type_candidates(record):
        return raw
    return None
