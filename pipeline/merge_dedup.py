#!/usr/bin/env python3
"""Origenality — fusion et dédoublonnage des moissons P1.

Lit tous les data/raw/*/records.jsonl, normalise, dédoublonne, conserve la
provenance et les valeurs concurrentes, écrit data/merged/corpus.jsonl + un
rapport de fusion.

Dédoublonnage — trois liens d'identité, réunis par union-find :

  1. DOI canonique identique (URL-décodé, préfixe résolveur et ponctuation
     terminale retirés) ;
  2. clé fuzzy identique : titre normalisé (80 premiers caractères) + premier
     auteur + signature de tomaison, l'année étant regroupée à ±1 autour de la
     PLUS ANCIENNE année du groupe — ancrage fixe, jamais glissant, donc un
     cluster ne peut pas dériver sur trois millésimes ;
  3. ISBN normalisé identique. Un ISBN désigne un tirage : deux notices qui le
     portent décrivent le même objet physique, quelles que soient les variantes
     de saisie du titre. ISBN-10 et ISBN-13 sont ramenés à une forme unique
     (ISBN-13, tirets et espaces retirés, somme de contrôle vérifiée), de sorte
     que 3451221098 et 9783451221095 sont le même lien. Le catalogue K10plus
     écrit le titre du même volume de trois façons — « … : 4 Liber septimus,
     liber octavus », « … Bd. 4 Liber septimus… », la version bilingue avec son
     sous-titre — et la clé fuzzy les laissait dans trois grappes.

La clé fuzzy s'applique aussi aux notices porteuses d'un DOI : une notice avec
DOI peut donc rejoindre une notice sans DOI, et deux DOI distincts de la même
publication (JSTOR / éditeur) se rejoignent.

Garde-fous :

  - signature de tomaison : deux notices dont les titres complets portent des
    marqueurs de volume différents (« Band I » / « Band II », « Vol. XXXIV »,
    « T. 1 ») ne sont jamais fusionnées, même si leurs 80 premiers caractères
    coïncident ;
  - la normalisation de titre conserve les alphabets non latins (grec,
    cyrillique, hébreu, CJC) : un titre non latin reste dédoublonnable ;
  - la famille `abstract*` voyage en bloc : le résumé retenu, ses droits et le
    lien vers la notice qui l'a écrit (`abstract_url`, recopié de l'adresse de
    la notice donatrice) viennent obligatoirement de la même notice source,
    jamais de deux sources différentes ;
  - un groupe fuzzy de plus de six notices est laissé éclaté : à cette taille,
    la clé n'identifie plus une publication mais un titre de service
    (« Editorial Board », « Front Matter ») ;
  - un ISBN porté par plus de six titres différents n'est pas l'ISBN d'un
    volume mais celui d'une collection ou d'un coffret, recopié sur chacune de
    ses parties : il est ignoré comme lien d'identité ;
  - un lien par ISBN est refusé quand les deux notices portent des marqueurs de
    tomaison différents et tous deux renseignés (« Band I » contre « Band II »).
    Un marqueur absent d'un côté ne bloque rien : c'est le cas ordinaire du
    catalogue, où une seule des saisies écrit « Bd. 4 » ;
  - deux DOI canoniques distincts ne sont rapprochés que sur preuve forte —
    titres complets identiques et longs d'au moins 25 caractères — et jamais
    lorsqu'ils partagent le même préfixe, c'est-à-dire le même déposant : un
    éditeur n'attribue pas deux DOI au même objet, il en attribue un par
    volume, par tirage ou par format (10.1017/cbo9780511996917 et
    …996924 sont les tomes 1 et 2 du commentaire de Jean chez Cambridge) ;
    ni lorsqu'un marqueur de tomaison apparaît dans l'un des textes de la
    notice (titre, sous-titre, résumé) sans apparaître à l'identique dans
    l'autre.

Provenance : `provenance[champ] = {source, source_id}` pour la valeur retenue,
et `conflicts[champ] = [{source, source_id, value}, …]` pour toutes les valeurs
concurrentes écartées. Rien n'est perdu au profit de la source prioritaire.

Identifiants : `origenality_id` = « OR » + 12 hexadécimaux dérivés d'un
hachage stable — DOI canonique s'il existe, sinon titre normalisé + année +
premier auteur, sinon la liste triée des couples source/source_id du groupe.
L'identifiant ne dépend donc ni de l'ordre de lecture ni du nombre de notices ;
ajouter une source ne renumérote pas le corpus.

`origenality_id` est une CLÉ : deux grappes n'en partagent jamais un. Deux
grappes distinctes peuvent pourtant produire la même identité — treize notices
SBN d'un même titre laissées éclatées par le garde-fou des groupes trop
peuplés en sont l'exemple. Dans ce cas toutes les grappes en collision, sans
survivante privilégiée, reçoivent un discriminant dérivé de leur CONTENU : la
liste triée de leurs couples source/source_id, qui est disjointe par
construction puisqu'une notice source n'appartient qu'à une grappe. Aucun
compteur d'ordre n'intervient, donc rejouer la fusion sur les mêmes entrées
rend les mêmes identifiants.
"""
import argparse
import collections
import glob
import hashlib
import json
import os
import re
import sys
import unicodedata
import urllib.parse
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fields import norm_year  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "data", "raw")
OUT_DIR = os.path.join(BASE, "data", "merged")

# priorité des sources pour l'arbitrage des champs (curaté > machine)
SOURCE_PRIORITY = [
    "ixtheo-k10plus", "bibp", "adamantius-girota", "thesesfr",
    "openalex", "crossref", "semanticscholar", "isidore", "dialnet", "sbn",
]

# champs de service, jamais issus des notices sources
RESERVED = {"sources", "provenance", "conflicts", "origenality_id"}

TITLE_KEY_LEN = 80
ABSTRACT_PREFIX = "abstract"

# Un groupe fuzzy trop peuplé n'identifie pas une publication mais un titre de
# service — « Editorial Board », « Front Matter », « Introduction », « 1 » —
# que des dizaines de notices distinctes partagent. Au-delà de ce seuil, le
# groupe est laissé éclaté.
MAX_FUZZY_GROUP = 6
# Rapprocher deux DOI distincts demande une preuve plus forte que 80 caractères
# de préfixe : titres complets identiques et assez longs pour discriminer.
MIN_STRONG_TITLE = 25

ROMAN = r"(?=[ivxlcdm])m{0,3}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})"
VOLUME_RE = re.compile(
    r"\b(?:vol|volume|volumen|volumi|bd|band|baende|t|tom|tome|tomo|tomos|"
    r"teil|parte|part|pt|fasc|heft)\s+(\d{1,3}|" + ROMAN + r")\b")
ROMAN_VALUES = {"m": 1000, "d": 500, "c": 100, "l": 50, "x": 10, "v": 5, "i": 1}


def strip_marks(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def norm_title(t: str) -> str:
    """Titre normalisé, tous alphabets confondus.

    Casse repliée, diacritiques retirés, ponctuation ramenée à l'espace. On
    garde tout caractère alphanumérique Unicode : restreindre à [a-z0-9]
    viderait les titres entièrement grecs, cyrilliques ou hébreux, qui
    deviendraient indédoublonnables.
    """
    if not t:
        return ""
    t = strip_marks(str(t).casefold())
    t = "".join(c if c.isalnum() else " " for c in t)
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", t).strip())


def roman_to_int(token: str):
    total = 0
    previous = 0
    for char in reversed(token):
        value = ROMAN_VALUES.get(char, 0)
        if not value:
            return None
        total = total - value if value < previous else total + value
        previous = max(previous, value)
    return total or None


def volume_signature(title: str) -> tuple:
    """Numéros de tomaison lus dans le titre complet.

    « Lexicon Gregorianum … Band I » et « … Band II » donnent (1,) et (2,) :
    deux publications distinctes, que les 80 premiers caractères ne séparent
    pas. Un titre sans marqueur donne un tuple vide.
    """
    numbers = set()
    for token in VOLUME_RE.findall(norm_title(title)):
        value = int(token) if token.isdigit() else roman_to_int(token)
        if value:
            numbers.add(value)
    return tuple(sorted(numbers))


# Champs où un marqueur de tomaison peut se cacher quand le titre n'en porte
# pas. Les deux volumes du commentaire de Jean chez Cambridge ont le même titre
# et deux DOI ; seuls leurs résumés disent « Volume 1 includes… » / « Volume 2
# includes… ». Ces champs ne servent QU'À BLOQUER un rapprochement entre deux
# DOI distincts, jamais à en autoriser un.
VOLUME_TEXT_FIELDS = ("title", "subtitle", "abstract", "container", "edition")


def doi_prefix(d):
    """Préfixe d'un DOI canonique — « 10.1017 » —, c'est-à-dire son déposant."""
    return d.split("/", 1)[0] if d else ""


def text_volume_signature(record) -> tuple:
    """Marqueurs de tomaison lus dans tous les textes d'une notice."""
    numbers = set()
    for field in VOLUME_TEXT_FIELDS:
        value = record.get(field)
        if isinstance(value, str) and value:
            numbers.update(volume_signature(value))
    return tuple(sorted(numbers))


def norm_doi(d):
    """DOI canonique : minuscules, sans résolveur, URL-décodé, sans ponctuation
    terminale. Sans cela, « …/abc%3adef » et « …/abc:def », ou un DOI suivi
    d'un point, restent deux identifiants distincts."""
    if not d:
        return None
    if isinstance(d, list):
        d = d[0] if d else None
        if not d:
            return None
    d = str(d).strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    d = re.sub(r"^doi:\s*", "", d)
    d = urllib.parse.unquote(d)
    # ponctuation de fin de phrase seulement : une parenthèse fermante peut
    # appartenir au DOI (10.24192/2386-7027(2018)(v10)(08))
    d = d.strip().strip(".,;:\"'")
    d = re.sub(r"\s+", "", d)
    return d if d.startswith("10.") else (d or None)


# --------------------------------------------------------------------------
# ISBN
# --------------------------------------------------------------------------

# Champs où les moissons déposent un ISBN. K10plus écrit `isbn` (liste), BIBP
# écrit `isbn_issn` (un ISSN de huit chiffres y voisine avec des ISBN : le
# contrôle de longueur et la somme de contrôle l'écartent).
ISBN_FIELDS = ("isbn", "isbn_issn")

# Au-delà de ce nombre de titres différents, un ISBN n'identifie plus un volume
# mais une collection recopiée sur chacune de ses parties.
MAX_ISBN_TITLES = 6

# Écart d'années toléré par le lien ISBN. Un même ISBN se retrouve parfois sur
# la notice d'une réédition qui a gardé l'ancien numéro : « Geist und Feuer »
# porte 3894113049 en 1951 chez O. Müller et en 1991 chez Johannes-Verlag. Ce
# sont deux publications, et les fusionner efface la première de toute série
# temporelle. Une année d'écart reste tolérée : une notice datée du dépôt légal
# et une autre de la parution décrivent le même tirage.
MAX_ISBN_YEAR_GAP = 1

# Deux notices d'un même ISBN peuvent porter des numéros de tomaison
# différents parce que le volume appartient à deux hiérarchies de numérotation
# — « studia patristica, vol. LXXXIV » et « Volume 10 » des actes du colloque
# d'Oxford 2015 désignent le même livre chez Peeters. Le marqueur divergent ne
# prouve alors rien : ce qui tranche, c'est que les deux titres portent la même
# désignation d'ouvrage. On l'établit par la plus longue suite de mots commune,
# qui doit être assez longue pour ne pas être un simple nom de collection.
MIN_SHARED_TITLE_RUN = 4
MIN_SHARED_TITLE_CHARS = 20


def _isbn10_check(body: str) -> str:
    total = sum((10 - i) * (10 if c == "X" else int(c))
                for i, c in enumerate(body))
    remainder = (11 - total % 11) % 11
    return "X" if remainder == 10 else str(remainder)


def _isbn13_check(body: str) -> str:
    total = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(body))
    return str((10 - total % 10) % 10)


def norm_isbn(value):
    """ISBN ramené à sa forme ISBN-13, ou None si ce n'en est pas un.

    Tirets, espaces et points sont retirés ; un ISBN-10 valide est converti en
    ISBN-13 (préfixe 978, somme de contrôle recalculée) pour que les deux
    graphies du même volume donnent la même clé. Une somme de contrôle fausse
    fait rejeter la valeur : un numéro de notice ou un ISSN qui traînerait dans
    le champ n'a alors aucune chance de rapprocher deux publications.
    """
    if value is None:
        return None
    text = re.sub(r"[^0-9Xx]", "", str(value)).upper()
    if len(text) == 10:
        if "X" in text[:9] or _isbn10_check(text[:9]) != text[9]:
            return None
        body = "978" + text[:9]
        return body + _isbn13_check(body)
    if len(text) == 13:
        if not text.isdigit() or _isbn13_check(text[:12]) != text[12]:
            return None
        return text
    return None


def record_isbns(record) -> set:
    """ISBN normalisés d'une notice, tous champs et toutes graphies confondus."""
    codes = set()
    for field in ISBN_FIELDS:
        value = record.get(field)
        if value is None:
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            code = norm_isbn(item)
            if code:
                codes.add(code)
    return codes


def longest_common_run(left_words, right_words):
    """Plus longue suite de mots commune à deux titres normalisés.

    Rend (mots, fin_gauche, fin_droite) : la suite elle-même et, dans chacun
    des deux titres, l'indice du mot qui la suit. Ces deux indices servent au
    garde de l'ordre de tête : une suite qui s'arrête juste avant deux
    numéros différents n'est pas une désignation d'ouvrage.
    """
    best_length, best_left, best_right = 0, 0, 0
    previous = [0] * (len(right_words) + 1)
    for i, word in enumerate(left_words, 1):
        current = [0] * (len(right_words) + 1)
        for j, other in enumerate(right_words, 1):
            if word == other:
                current[j] = previous[j - 1] + 1
                if current[j] > best_length:
                    best_length, best_left, best_right = current[j], i, j
        previous = current
    return (left_words[best_left - best_length:best_left], best_left, best_right)


# Mots qui introduisent un numéro de tomaison. Une suite commune qui en porte
# un ne désigne pas un ouvrage : elle désigne une place dans une collection.
VOLUME_WORDS = {
    "vol", "volume", "volumen", "volumi", "bd", "band", "baende", "t", "tom",
    "tome", "tomo", "tomos", "teil", "parte", "part", "pt", "fasc", "heft",
}


def _is_number_word(word: str) -> bool:
    """Un mot qui peut être un numéro de tomaison : chiffres ou romain."""
    if word.isdigit():
        return len(word) <= 3
    return bool(re.fullmatch(ROMAN, word)) and roman_to_int(word) is not None


def same_designation(left_title: str, right_title: str) -> bool:
    """Deux titres désignent-ils le même ouvrage malgré des numéros différents ?

    Mesure volontairement grossière et bornée à un seul usage : lever le garde
    de tomaison sur des notices qui partagent DÉJÀ un ISBN et une année. Il faut
    une suite continue d'au moins quatre mots et vingt caractères — assez pour
    qu'un simple nom de collection (« studia patristica ») ne suffise pas.

    Deux garde-fous, ajoutés après l'audit 5 : un long préfixe d'actes de
    colloque partagé par tous les volumes d'un même congrès n'est pas une
    désignation d'ouvrage, et il ne doit jamais neutraliser une différence de
    numéro de volume. Les deux notices réelles ixtheo :627 (volume 10) et :628
    (volume 20) partagent cent quatre caractères — « papers presented at the
    seventeenth international conference on patristic studies held in oxford
    2015 volume » — puis divergent sur le seul numéro. La suite commune est donc
    refusée quand :

    1. elle contient elle-même un mot de tomaison (« volume », « band », « t. »)
       — c'est une adresse dans une collection, pas un titre ;
    2. elle est immédiatement suivie, des DEUX côtés, d'un nombre : la suite
       s'arrête précisément là où les deux volumes se distinguent.
    """
    left_words, right_words = left_title.split(), right_title.split()
    run, left_end, right_end = longest_common_run(left_words, right_words)
    if not (len(run) >= MIN_SHARED_TITLE_RUN
            and len(" ".join(run)) >= MIN_SHARED_TITLE_CHARS):
        return False
    if any(word in VOLUME_WORDS for word in run):
        return False
    left_next = left_words[left_end] if left_end < len(left_words) else ""
    right_next = right_words[right_end] if right_end < len(right_words) else ""
    if (left_next and right_next
            and _is_number_word(left_next) and _is_number_word(right_next)
            and left_next != right_next):
        return False
    return True


def isbn_group_pairs(indices, titles, volsigs, years):
    """Paires que l'ISBN partagé unit, et raisons des refus.

    Fonction pure : elle ne lit que les quatre tables qu'on lui passe, indexées
    comme les notices. Renvoie (paires, refus) où `refus` compte les motifs —
    `series` quand l'ISBN porte trop de titres différents pour désigner un
    volume, `year_gap` quand les deux années sont trop éloignées pour un même
    tirage, `volume_marker` quand les numéros de tomaison divergent sans que les
    titres désignent le même ouvrage.

    Le refus `series` porte sur le groupe entier : un ISBN de collection ne doit
    unir aucune de ses parties, même deux à deux.
    """
    refusals = collections.Counter()
    if len(indices) < 2:
        return [], refusals
    if len({titles[i][:TITLE_KEY_LEN] for i in indices}) > MAX_ISBN_TITLES:
        refusals["series"] += 1
        return [], refusals

    pairs = []
    for position, i in enumerate(indices):
        for j in indices[position + 1:]:
            left_year, right_year = years[i], years[j]
            if (left_year is not None and right_year is not None
                    and abs(left_year - right_year) > MAX_ISBN_YEAR_GAP):
                refusals["year_gap"] += 1
                continue
            left, right = volsigs[i], volsigs[j]
            if left and right and left != right \
                    and not same_designation(titles[i], titles[j]):
                refusals["volume_marker"] += 1
                continue
            pairs.append((i, j))
    return pairs, refusals


# Particules nobiliaires et prépositionnelles : elles précèdent le patronyme
# sans le constituer. « van den Hoek, Annewies » a pour patronyme Hoek.
PARTICLES = {
    "van", "von", "vander", "vanden", "den", "der", "de", "del", "della",
    "dello", "degli", "dei", "di", "da", "dos", "das", "du", "des", "le",
    "la", "les", "ten", "ter", "af", "av", "zu", "zum", "op", "in", "of",
    "el", "al", "ibn", "bin", "st", "ste",
}


def _is_initial(word: str) -> bool:
    """« F. », « J.-C. », « A » : un mot réduit à des lettres isolées."""
    letters = [p for p in re.split(r"[^\w]+", word, flags=re.UNICODE) if p]
    return bool(letters) and all(len(p) == 1 and p.isalpha() for p in letters)


def first_author_key(authors):
    """Clé du premier auteur, dérivée du PATRONYME.

    Le corpus mélange trois formes que rien ne signale : « Bovon, François »
    (catalogue), « Bovon F. » (dépouillement Adamantius, patronyme d'abord,
    initiales ensuite) et « François Bovon » (bases bibliométriques, prénom
    d'abord). Prendre le token le plus long — l'ancienne règle — rendait
    « francois » pour la première forme et « bovon » pour la deuxième : la même
    publication restait scindée en deux grappes.

    On repère donc le syntagme patronymique avant d'en tirer la clé :

      1. virgule : ce qui précède (« van den Hoek, Annewies » → van den hoek) ;
      2. sinon, présence d'initiales : ce qui les précède, à défaut ce qui les
         suit (« Bovon F. » → bovon ; « Hoek A. van den » → hoek) ;
      3. sinon : le dernier mot (« François Bovon » → bovon).

    Les particules initiales sont retirées, puis la clé est le premier
    sous-token d'au moins deux caractères : un patronyme composé donne la même
    clé quel que soit l'ordre de saisie (« Reydams-Schils G. » et « Gretchen
    Reydams-Schils » donnent tous deux reydams).
    """
    if not authors:
        return ""
    a = authors[0]
    name = a.get("name") if isinstance(a, dict) else str(a)
    if not name:
        return ""
    raw = strip_marks(str(name).casefold()).strip()
    if not raw:
        return ""

    if "," in raw:
        phrase = raw.split(",")[0]
    else:
        words = [w for w in raw.split() if w]
        initials = [i for i, w in enumerate(words) if _is_initial(w)]
        if initials and words:
            head = words[:initials[0]]
            tail = words[initials[-1] + 1:]
            phrase = " ".join(head) if head else " ".join(tail)
        elif words:
            phrase = words[-1]
        else:
            phrase = raw

    tokens = [p for p in re.split(r"[^\w]+", phrase, flags=re.UNICODE)
              if len(p) >= 2 and not p.isdigit()]
    meaningful = [p for p in tokens if p not in PARTICLES]
    if meaningful:
        return meaningful[0]
    return tokens[0] if tokens else ""


def priority(src):
    try:
        return SOURCE_PRIORITY.index(src)
    except ValueError:
        return len(SOURCE_PRIORITY)


def is_empty(value) -> bool:
    return value in (None, "", [], {})


def value_key(value):
    """Forme comparable d'une valeur, pour repérer les vrais désaccords."""
    if isinstance(value, str):
        return re.sub(r"\s+", " ", strip_marks(value.casefold())).strip()
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


# --------------------------------------------------------------------------
# fusion d'un groupe
# --------------------------------------------------------------------------

def merge_records(records):
    """Fusionne des notices considérées identiques.

    La valeur retenue est celle de la source la plus prioritaire qui la
    renseigne ; sa provenance est notée (source + identifiant), et toute valeur
    concurrente est conservée dans `conflicts`.
    """
    records = sorted(records, key=lambda r: (priority(r.get("source", "")),
                                             str(r.get("source", "")),
                                             str(r.get("source_id") or "")))
    merged = {"sources": [], "provenance": {}}
    conflicts = defaultdict(list)
    for r in records:
        merged["sources"].append({"source": r.get("source", "?"),
                                  "source_id": r.get("source_id")})

    for r in records:
        origin = {"source": r.get("source", "?"), "source_id": r.get("source_id")}
        for k, v in r.items():
            if k in ("source", "source_id") or k in RESERVED:
                continue
            if k.startswith(ABSTRACT_PREFIX) or is_empty(v):
                continue
            if k not in merged or is_empty(merged.get(k)):
                merged[k] = v
                merged["provenance"][k] = origin
            elif value_key(merged[k]) != value_key(v):
                conflicts[k].append(dict(origin, value=v))

    # famille abstract : bloc indivisible. Le résumé et ses droits proviennent
    # de la même notice, sinon un résumé sous copyright peut hériter du
    # libellé de licence d'une autre base.
    donor = next((r for r in records if not is_empty(r.get("abstract"))), None)
    if donor is not None:
        origin = {"source": donor.get("source", "?"),
                  "source_id": donor.get("source_id")}
        for k, v in donor.items():
            if k.startswith(ABSTRACT_PREFIX) and not is_empty(v):
                merged[k] = v
                merged["provenance"][k] = origin
        # Le lien vers la notice qui a écrit le résumé fait partie du bloc.
        # `url` au niveau de la grappe peut venir d'une tout autre base : le
        # crédit affiché sous un résumé ISIDORE renverrait alors à la fiche
        # Semantic Scholar de la même publication. On recopie donc l'adresse de
        # la notice DONATRICE, sous un nom qui dit d'où elle vient.
        donor_url = donor.get("url")
        if is_empty(merged.get("abstract_url")) and isinstance(donor_url, str) \
                and donor_url.startswith("http"):
            merged["abstract_url"] = donor_url
            merged["provenance"]["abstract_url"] = origin
        # Les droits concurrents se relèvent que le TEXTE diffère ou non. Trois
        # bases peuvent décrire le même résumé sous trois libellés (« Cairn »,
        # « CC-BY », « © l'éditeur ») ; ne rien noter quand les textes
        # coïncident faisait perdre deux des trois origines, et une demande de
        # retrait par fonds ne les retrouvait plus.
        for r in records:
            if r is donor or is_empty(r.get("abstract")):
                continue
            if value_key(r["abstract"]) != value_key(donor["abstract"]):
                conflicts["abstract"].append({
                    "source": r.get("source", "?"),
                    "source_id": r.get("source_id"),
                    "value": r["abstract"],
                    "abstract_rights": r.get("abstract_rights"),
                })
            for k, v in r.items():
                if not k.startswith(ABSTRACT_PREFIX) or k == "abstract":
                    continue
                if is_empty(v) or value_key(merged.get(k)) == value_key(v):
                    continue
                conflicts[k].append({
                    "source": r.get("source", "?"),
                    "source_id": r.get("source_id"),
                    "value": v,
                })
    if conflicts:
        merged["conflicts"] = dict(conflicts)
    return merged


def cluster_signature(merged) -> str:
    """Signature de composition d'une grappe : ses couples source/source_id,
    triés. Disjointe d'une grappe à l'autre, puisqu'une notice source
    n'appartient qu'à une grappe — c'est ce qui en fait un discriminant sûr."""
    return "|".join(sorted("%s:%s" % (s.get("source"), s.get("source_id"))
                           for s in merged.get("sources", [])))


def cluster_identity(merged) -> str:
    """Clé d'identité stable d'un groupe fusionné (hachée en origenality_id)."""
    doi = norm_doi(merged.get("doi"))
    if doi:
        return "doi:" + doi
    title = norm_title(merged.get("title") or "")
    if title:
        year = norm_year(merged)
        return "t:%s|%s|%s" % (title, year or "",
                               first_author_key(merged.get("authors") or []))
    return "s:" + cluster_signature(merged)


def origenality_id(identity: str) -> str:
    return "OR" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------
# union-find
# --------------------------------------------------------------------------

class Union:
    def __init__(self, size):
        self.parent = list(range(size))

    def find(self, i):
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, i, j):
        ri, rj = self.find(i), self.find(j)
        if ri != rj:
            self.parent[max(ri, rj)] = min(ri, rj)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--out-dir", default=OUT_DIR,
        help="répertoire de sortie ; par défaut data/merged/")
    parser.add_argument(
        "--no-isbn-link", action="store_true",
        help="désactive le troisième lien d'identité. Sert à rejouer l'état "
             "d'avant l'itération 5 et à mesurer ce que l'ISBN a recollé ; "
             "n'a pas d'autre usage.")
    arguments = parser.parse_args(argv)
    out_dir = arguments.out_dir

    os.makedirs(out_dir, exist_ok=True)
    all_records = []
    per_source = defaultdict(int)
    for path in sorted(glob.glob(os.path.join(RAW, "*", "records.jsonl"))):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                all_records.append(r)
                per_source[r.get("source", os.path.basename(os.path.dirname(path)))] += 1

    union = Union(len(all_records))

    # 1. lien par DOI canonique
    by_doi = defaultdict(list)
    dois = []
    for i, r in enumerate(all_records):
        d = norm_doi(r.get("doi"))
        dois.append(d)
        if d:
            by_doi[d].append(i)
    for indices in by_doi.values():
        for i in indices[1:]:
            union.union(indices[0], i)

    # 2. lien fuzzy — DOI ou non, titre + auteur + tomaison, année ancrée
    titles = [norm_title(r.get("title", "")) for r in all_records]
    by_key = defaultdict(list)
    for i, r in enumerate(all_records):
        if not titles[i]:
            continue
        key = (titles[i][:TITLE_KEY_LEN],
               first_author_key(r.get("authors") or []),
               volume_signature(r.get("title", "")))
        by_key[key].append((norm_year(r), i))

    doi_of_root = {}
    doi_srcs_of_root = {}
    volsig_of_root = {}
    for i, d in enumerate(dois):
        root = union.find(i)
        if d:
            doi_of_root.setdefault(root, set()).add(d)
            doi_srcs_of_root.setdefault(root, set()).add(doi_prefix(d))
        marks = text_volume_signature(all_records[i])
        if marks:
            volsig_of_root.setdefault(root, set()).update(marks)

    fuzzy_links = 0
    rejected_groups = 0
    blocked_doi_pairs = 0
    blocked_same_prefix = 0
    blocked_volume_marker = 0

    isbn_links = 0
    isbn_series_ignored = 0
    isbn_blocked_volume_marker = 0

    def fuzzy_union(i, j, strong):
        """Rattache j à i, sauf si cela confondrait deux DOI distincts.

        Deux DOI canoniques distincts ne se rejoignent que sur preuve forte
        (titres complets identiques et longs), et cette preuve tombe dans deux
        cas : les deux DOI partagent un préfixe, donc un déposant — un éditeur
        n'attribue pas deux DOI au même objet, il en attribue un par volume ;
        ou les textes des deux côtés portent des marqueurs de tomaison
        différents.
        """
        nonlocal fuzzy_links, blocked_doi_pairs
        nonlocal blocked_same_prefix, blocked_volume_marker
        ri, rj = union.find(i), union.find(j)
        if ri == rj:
            return False
        di = doi_of_root.get(ri, set())
        dj = doi_of_root.get(rj, set())
        if di and dj and di != dj:
            if not strong:
                blocked_doi_pairs += 1
                return False
            if doi_srcs_of_root.get(ri, set()) & doi_srcs_of_root.get(rj, set()):
                blocked_same_prefix += 1
                return False
            if volsig_of_root.get(ri, set()) != volsig_of_root.get(rj, set()):
                blocked_volume_marker += 1
                return False
        union.union(ri, rj)
        merged_doi = di | dj
        merged_srcs = doi_srcs_of_root.get(ri, set()) | doi_srcs_of_root.get(rj, set())
        merged_vol = volsig_of_root.get(ri, set()) | volsig_of_root.get(rj, set())
        for stale in (ri, rj):
            doi_of_root.pop(stale, None)
            doi_srcs_of_root.pop(stale, None)
            volsig_of_root.pop(stale, None)
        new_root = union.find(ri)
        if merged_doi:
            doi_of_root[new_root] = merged_doi
        if merged_srcs:
            doi_srcs_of_root[new_root] = merged_srcs
        if merged_vol:
            volsig_of_root[new_root] = merged_vol
        fuzzy_links += 1
        return True

    for key in sorted(by_key, key=lambda k: (k[0], k[1], k[2])):
        entries = sorted(by_key[key], key=lambda e: (e[0] is None, e[0] or 0, e[1]))
        if len(entries) > MAX_FUZZY_GROUP:
            rejected_groups += 1
            continue
        full = {titles[i] for _, i in entries}
        strong = len(full) == 1 and len(next(iter(full))) >= MIN_STRONG_TITLE
        anchors = []          # [(année d'ancrage, index représentant)]
        undated = None
        for year, i in entries:
            if year is None:
                if undated is None:
                    undated = i
                else:
                    fuzzy_union(undated, i, strong)
                continue
            target = None
            for anchor_year, rep in anchors:
                if year - anchor_year <= 1:   # ancrage sur la plus ancienne
                    target = rep
                    break
            if target is None:
                anchors.append((year, i))
            else:
                fuzzy_union(target, i, strong)

    # 3. lien par ISBN normalisé
    #
    # Un ISBN désigne un tirage : deux notices qui portent le même ISBN décrivent
    # le même objet, quelles que soient les variantes de saisie du titre. C'est
    # le lien qui manquait — cinquante-sept ISBN se retrouvaient dans deux ou
    # trois grappes, dont le volume 4 du commentaire aux Romains chez Herder,
    # catalogué trois fois par K10plus sous trois libellés de titre.
    #
    # Le lien n'est pas inconditionnel : un numéro repris par une réédition
    # quarante ans plus tard ne désigne plus le même livre. La décision est
    # prise par `isbn_group_pairs`, fonction pure, testée à part.
    fuzzy_links_only = fuzzy_links
    by_isbn = defaultdict(list)
    for i, r in enumerate(all_records):
        for code in record_isbns(r):
            by_isbn[code].append(i)

    record_volsig = [text_volume_signature(r) for r in all_records]
    record_years = [norm_year(r) for r in all_records]
    isbn_blocked_year_gap = 0

    for code in sorted(by_isbn) if not arguments.no_isbn_link else ():
        pairs, refusals = isbn_group_pairs(
            by_isbn[code], titles, record_volsig, record_years)
        isbn_series_ignored += refusals["series"]
        isbn_blocked_volume_marker += refusals["volume_marker"]
        isbn_blocked_year_gap += refusals["year_gap"]
        for i, j in pairs:
            if fuzzy_union(i, j, True):
                isbn_links += 1

    # 4. constitution des groupes, dans l'ordre de première apparition
    groups = defaultdict(list)
    order = []
    for i in range(len(all_records)):
        root = union.find(i)
        if root not in groups:
            order.append(root)
        groups[root].append(i)

    merged_records = []
    doi_and_no_doi = 0
    multi_doi = 0
    conflicts_by_field = defaultdict(int)
    clusters_with_conflicts = 0
    for root in order:
        indices = groups[root]
        cluster = [all_records[i] for i in indices]
        cluster_dois = {dois[i] for i in indices if dois[i]}
        if cluster_dois and any(dois[i] is None for i in indices):
            doi_and_no_doi += 1
        if len(cluster_dois) > 1:
            multi_doi += 1
        m = merge_records(cluster)
        for field, values in m.get("conflicts", {}).items():
            conflicts_by_field[field] += len(values)
        if m.get("conflicts"):
            clusters_with_conflicts += 1
        merged_records.append(m)

    # 5. identifiants stables — et uniques
    #
    # Deux grappes distinctes peuvent produire la même identité : le garde-fou
    # des groupes trop peuplés laisse éclatées treize notices SBN d'un même
    # titre, dont l'identité « titre|année|auteur » est par construction la
    # même. L'ancienne condition ne comparait l'identité qu'à celle d'une
    # collision de hachage et laissait donc passer ces homonymes : 36
    # identifiants pour 91 grappes.
    #
    # Règle : toute identité partagée par plusieurs grappes est écartée pour
    # TOUTES ces grappes, aucune n'ayant plus de titre qu'une autre à garder la
    # forme courte ; chacune reçoit un discriminant dérivé de son contenu — la
    # liste triée de ses couples source/source_id, disjointe d'une grappe à
    # l'autre puisqu'une notice source n'appartient qu'à une grappe. Aucun
    # compteur d'ordre : rejouer la fusion rend les mêmes identifiants.
    identities = [cluster_identity(m) for m in merged_records]
    identity_counts = defaultdict(int)
    for identity in identities:
        identity_counts[identity] += 1

    ambiguous_identities = 0
    ambiguous_clusters = 0
    hash_collisions = 0
    seen_ids = {}
    final_identities = []
    for m, identity in zip(merged_records, identities):
        if identity_counts[identity] > 1:
            ambiguous_clusters += 1
            identity = "%s#%s" % (identity, cluster_signature(m))
        final_identities.append(identity)
    ambiguous_identities = sum(1 for c in identity_counts.values() if c > 1)

    for m, identity in zip(merged_records, final_identities):
        oid = origenality_id(identity)
        # collision de hachage sur deux identités réellement distinctes :
        # on rehache l'identité salée, sans compteur d'ordre.
        while oid in seen_ids and seen_ids[oid] != identity:
            hash_collisions += 1
            identity = identity + "#h"
            oid = origenality_id(identity)
        seen_ids[oid] = identity
        m["origenality_id"] = oid

    duplicate_ids = len(merged_records) - len(seen_ids)
    if duplicate_ids:
        raise SystemExit(
            "origenality_id n'est pas une clé : %d lignes surnuméraires"
            % duplicate_ids)

    out_path = os.path.join(out_dir, "corpus.jsonl")
    with open(out_path, "w") as f:
        for m in merged_records:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    report = {
        "input_records": len(all_records),
        "per_source": dict(per_source),
        "merged_clusters": len(merged_records),
        "dedup_removed": len(all_records) - len(merged_records),
        "with_doi": sum(1 for m in merged_records if m.get("doi")),
        "with_abstract": sum(1 for m in merged_records if m.get("abstract")),
        "multi_source": sum(1 for m in merged_records if len(m["sources"]) > 1),
        "doi_clusters": len(by_doi),
        "fuzzy_links": fuzzy_links_only,
        "isbn_links": isbn_links,
        "isbn_series_ignored": isbn_series_ignored,
        "isbn_blocked_volume_marker": isbn_blocked_volume_marker,
        "isbn_blocked_year_gap": isbn_blocked_year_gap,
        "distinct_isbn": len(by_isbn),
        "isbn_link_enabled": not arguments.no_isbn_link,
        "fuzzy_groups_rejected_too_large": rejected_groups,
        "cross_doi_pairs_blocked": blocked_doi_pairs,
        "cross_doi_blocked_same_prefix": blocked_same_prefix,
        "cross_doi_blocked_volume_marker": blocked_volume_marker,
        "clusters_doi_and_no_doi": doi_and_no_doi,
        "clusters_multiple_dois": multi_doi,
        "clusters_with_conflicts": clusters_with_conflicts,
        "conflicts_by_field": dict(sorted(conflicts_by_field.items(),
                                          key=lambda kv: -kv[1])),
        "ambiguous_identities": ambiguous_identities,
        "id_collisions_disambiguated": ambiguous_clusters,
        "id_hash_collisions_resalted": hash_collisions,
        "unique_ids": len(seen_ids),
    }
    with open(os.path.join(out_dir, "merge_report.json"), "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
