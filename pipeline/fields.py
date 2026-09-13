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
# rôles des personnes nommées par une notice
# --------------------------------------------------------------------------
# Une notice de catalogue nomme aussi ceux qui ont imprimé, vendu, relié, gravé,
# possédé, reçu ou soutenu le livre. Ce ne sont pas des auteurs : les verser
# dans les auteurs faisait de l'imprimeur Eucario Silber et du duc de Sussex,
# ancien possesseur, deux nœuds d'auteur et deux noms de l'export BibTeX (audit
# du 13 septembre). Une seule liste, lue par le snapshot public
# (`site/build-c/tools/build_public_snapshot.py`) et par le graphe
# (`pipeline/build_site_data.py`). Tout rôle absent de ces tables est gardé :
# auteur, directeur de publication, traducteur, préfacier d'édition critique,
# collaborateur, dédicataire d'un volume d'hommage (`hnr`), et toute personne
# dont la notice ne code pas le rôle.

# MARC21, `$4` des zones 100, 110, 111, 700, 710, 711.
NON_AUTHORIAL_MARC21 = {
    "bnd": "binder", "bsl": "bookseller", "dgg": "degree granting institution",
    "dnr": "donor", "dst": "distributor", "dte": "dedicatee", "egr": "engraver",
    "fmo": "former owner", "fnd": "funder", "isb": "issuing body", "own": "owner",
    "pbl": "publisher", "prt": "printer", "rcp": "addressee", "sll": "seller",
    "spn": "sponsor", "wpr": "writer of preface",
}
# UNIMARC, `$4` des zones 700 à 712.
NON_AUTHORIAL_UNIMARC = {
    "110": "binder", "120": "binding designer", "160": "bookseller",
    "280": "dedicatee", "295": "degree grantor", "310": "distributor",
    "320": "donor", "350": "engraver", "390": "former owner", "400": "funder",
    "475": "issuing body", "530": "metal-engraver", "610": "printer",
    "620": "printer of plates", "650": "publisher", "660": "recipient of letters",
    "723": "sponsor", "753": "vendor", "760": "wood-engraver",
}
# Mentions en clair (`$e`) des notices MARC21 qui ne portent pas de code.
NON_AUTHORIAL_TERMS = {
    "binder", "bookseller", "buchhändler", "buchhändlerin", "degree granting institution",
    "distributor", "drucker", "druckerin", "engraver", "former owner", "imprimeur",
    "imprimeur-libraire", "issuing body", "printer", "publisher", "sponsoring body",
    "verlag", "vorbesitz", "vorbesitzer", "vorbesitzerin",
}


def relator_code(value) -> str:
    """Un code de rôle nu : `prt`, `610`, ou le dernier segment d'une URI
    id.loc.gov (`http://id.loc.gov/vocabulary/relators/prt`) ; une mention en
    clair est rendue en minuscules, sans ponctuation finale."""
    text = str(value or "").strip()
    if "/" in text:
        text = text.rstrip("/").rsplit("/", 1)[-1]
    return text.strip(" .,;:").casefold()


def non_authorial(roles) -> bool:
    """Vrai quand une personne a au moins un rôle et que tous ses rôles sont
    non auctoriaux. Un rôle vide ou inconnu la garde parmi les auteurs."""
    codes = [relator_code(role) for role in roles or []]
    if not codes:
        return False
    known = set(NON_AUTHORIAL_MARC21) | set(NON_AUTHORIAL_UNIMARC) | NON_AUTHORIAL_TERMS
    return all(code in known for code in codes)


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
    "arm": "hy", "hye": "hy",
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
