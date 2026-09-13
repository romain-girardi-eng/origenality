#!/usr/bin/env python3
"""Relit dans leur propre catalogue les notices des sept flux d'autorité.

Le snapshot public (`site-records.jsonl`) porte 1 173 notices qui ne viennent
pas d'IxTheo : K10plus, Sudoc, B3Kat, Gnomon GBD, DNB, Library of Congress et
BnF. Leurs notices complètes ont disparu du disque ; il n'en restait que la
projection du graphe publié, qui ne garde une vedette que si trois notices la
portent et un contenant que si cinq le portent (audit du 13 septembre, OR-01).
Ce moissonneur retourne chercher chaque notice par son identifiant, dans
l'interface ouverte du catalogue qui la détient, et en extrait les vedettes et
le contenant, rien d'autre.

Interfaces (une requête par notice, réponse brute gardée en cache) :

  k10plus              SRU K10plus, `pica.ppn=<PPN>`, MARCXML
  dnb                  SRU de la DNB, `idn=<IDN>`, MARC21-xml
  b3kat, gnomon-gbd    SRU B3Kat, `marcxml.idn=<BV>` (les identifiants GBD
                       sont des numéros B3Kat ; l'interface ne répond qu'en http)
  loc                  SRU de la Library of Congress, `bath.lccn=<LCCN>`, MARCXML
                       (le permalien `/<LCCN>/marcxml` bloque après une rafale ;
                       les notices qu'il a servies avant restent lues du cache)
  sudoc                notice par PPN, `/<PPN>.xml`, UNIMARC
  bnf                  SRU du catalogue général, `bib.persistentid`, UNIMARC

Ce qui est extrait :

  subjects         la vedette principale ($a) de chaque zone matière 6XX
                   retenue (voir SUBJECT_TAGS), dans l'ordre de la notice, sans
                   doublon, comme `ixtheo_hydrate_sru.py` le fait pour IxTheo ;
  subject_chains   le $a des chaînes RSWK (689), là où le catalogue en porte ;
  subject_fields   chaque vedette avec la zone qui la porte (provenance) ;
  author_roles     chaque personne ou collectivité nommée (1XX et 7XX), avec ses
                   codes de rôle (`$4`, à défaut la mention `$e`) : le snapshot
                   écarte des auteurs l'imprimeur, l'ancien possesseur et les
                   autres rôles non auctoriaux de `pipeline/fields.py` ;
  container        la notice hôte (773 en MARC21, 463 puis 461 en UNIMARC),
                   de type `host`, sinon la collection (490 puis 830 ; 225
                   puis 410), de type `series` : la règle de typage du snapshot
                   IxTheo ;
  title, authors, year, language   pour le seul contrôle d'identité. Le titre
                   publié n'est jamais remplacé : les identifiants de grappe se
                   calculent sur lui.

Une notice dont le titre ou l'année ne concorde pas avec la ligne du snapshot
est écrite avec `identity.status = "mismatch"` et n'est pas utilisée. Une notice
introuvable est journalisée avec sa cause dans `failures.jsonl` et redemandée au
passage suivant.

Politesse : une requête par seconde par hôte (B3Kat et GBD partagent le leur ;
une toutes les six secondes vers la Library of Congress, qui bloque au-delà),
User-Agent nominatif avec l'adresse de contact du projet, reprise sur 429 et
5xx avec attente croissante et respect de `Retry-After`. Reprise : une notice
déjà écrite dans `records.jsonl` n'est pas redemandée ; une réponse déjà en
cache est relue sans réseau.

    python3 scripts/hydrate_authority_records.py                 # moisson
    python3 scripts/hydrate_authority_records.py --limit 2       # essai, 2 par source
    python3 scripts/hydrate_authority_records.py --reparse       # relit le cache seul
    python3 scripts/hydrate_authority_records.py --report        # tableau par source
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "site" / "build-c" / "tools"))
sys.path.insert(0, str(HERE.parent / "site" / "tools"))
sys.path.insert(0, str(HERE.parent / "pipeline"))
from tree_paths import data_dir, repository_root  # noqa: E402
from fields import relator_code  # noqa: E402
from harvest_p1.common import retry_after_seconds  # noqa: E402

ROOT = Path(repository_root(str(HERE)))
RECORDS_IN = Path(data_dir(str(ROOT))) / "site-records.jsonl"
OUT_DIR = ROOT / "data" / "raw" / "authority"

CONTACT = "romain.girardi@univ-cotedazur.fr"
USER_AGENT = f"Origenality-authority-hydration/1.0 (academic research; {CONTACT})"
MIN_INTERVAL = 1.0          # secondes entre deux requêtes vers un même hôte
TRIES = 5
BACKOFF = 5.0               # 5, 10, 20, 40 s
TIMEOUT = 90
# Le permalien LCCN coupe l'accès après une rafale à une requête par seconde :
# 404 à corps vide, y compris pour une notice servie une minute plus tôt.
LOC_INTERVAL = 6.0

K10PLUS_SRU = "https://sru.k10plus.de/opac-de-627"
DNB_SRU = "https://services.dnb.de/sru/dnb"
B3KAT_SRU = "http://bvbr.bib-bvb.de:5661/bvb01sru"
LOC_PERMALINK = "https://lccn.loc.gov"
LOC_SRU = "http://lx2.loc.gov:210/lcdb"
SUDOC = "https://www.sudoc.fr"
BNF_SRU = "https://catalogue.bnf.fr/api/SRU"


def lccn_key(identifier: str) -> str:
    """LCCN normalisé pour le permalien : sans espaces (« a  51005034 »)."""
    return re.sub(r"\s+", "", identifier)


def sru(base: str, query: str, schema: str, version: str = "1.1") -> str:
    return "%s?%s" % (base, urllib.parse.urlencode({
        "version": version, "operation": "searchRetrieve", "query": query,
        "recordSchema": schema, "maximumRecords": "2"}))


SOURCES: dict[str, dict] = {
    "k10plus": {"format": "marc21", "id_in_001": True,
                "url": lambda i: sru(K10PLUS_SRU, "pica.ppn=%s" % i, "marcxml")},
    "dnb": {"format": "marc21", "id_in_001": True,
            "url": lambda i: sru(DNB_SRU, "idn=%s" % i, "MARC21-xml")},
    "b3kat": {"format": "marc21", "id_in_001": True,
              "url": lambda i: sru(B3KAT_SRU, "marcxml.idn=%s" % i, "marcxml")},
    "gnomon-gbd": {"format": "marc21", "id_in_001": True,
                   "url": lambda i: sru(B3KAT_SRU, "marcxml.idn=%s" % i, "marcxml")},
    "loc": {"format": "marc21", "id_in_001": False, "interval": LOC_INTERVAL,
            "url": lambda i: sru(LOC_SRU, "bath.lccn=%s" % lccn_key(i), "marcxml")},
    "sudoc": {"format": "unimarc", "id_in_001": True,
              "url": lambda i: "%s/%s.xml" % (SUDOC, urllib.parse.quote(i))},
    "bnf": {"format": "unimarc", "id_in_001": False,
            # `all` ne retrouve pas une partie des ark récents ; `any` les retrouve
            # tous, et `select_record` vérifie que la notice rendue porte l'ark demandé.
            "url": lambda i: sru(BNF_SRU, 'bib.persistentid any "%s"' % i,
                                 "unimarcXchange", version="1.2")},
}

# Zones matière retenues. MARC21 : noms (600, 610, 611), titres (630), sujets
# (650) et lieux (651) ; UNIMARC : 600 à 607. Vedette principale ($a) seule.
# Ni les zones de forme (MARC21 655 : « Aufsatzsammlung », « Hochschulschrift » ;
# UNIMARC 608 : « Thèses et écrits académiques », « Actes de congrès »,
# « Ouvrages avant 1800 ») ni le thésaurus local de la GBD (688 : « Origenes
# theol. TLG 2042 »). Une forme dit ce qu'est le document, pas de quoi il parle :
# 608 restait dans le jeu UNIMARC quand 655 était exclu du jeu MARC21, et
# 54 vedettes de forme comptaient comme sujets dans 52 notices (audit du
# 13 septembre).
SUBJECT_TAGS = {
    "marc21": ("600", "610", "611", "630", "650", "651"),
    "unimarc": ("600", "601", "602", "604", "605", "606", "607"),
}


class FetchError(Exception):
    """Une notice qu'on n'a pas pu obtenir, avec une cause lisible."""

    def __init__(self, cause: str, detail: str = ""):
        super().__init__(cause)
        self.cause = cause
        self.detail = detail


# ---------------------------------------------------------------------------
# Lecture MARCXML, sans dépendre des espaces de noms (Sudoc n'en déclare aucun,
# la BnF écrit marcxchange, les autres MARC21 slim).
# ---------------------------------------------------------------------------

def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def is_marc_record(element) -> bool:
    return local(element.tag) == "record" and any(
        local(child.tag) in ("leader", "controlfield", "datafield") for child in element)


def marc_records(root) -> list:
    return [element for element in root.iter() if is_marc_record(element)]


def number_of_records(root):
    for element in root.iter():
        if local(element.tag) == "numberOfRecords" and (element.text or "").strip().isdigit():
            return int(element.text.strip())
    return None


def controlfield(record, tag: str) -> str:
    for child in record:
        if local(child.tag) == "controlfield" and child.get("tag") == tag:
            return child.text or ""
    return ""


def datafields(record, tags) -> list:
    tags = (tags,) if isinstance(tags, str) else tags
    return [child for child in record
            if local(child.tag) == "datafield" and child.get("tag") in tags]


def subfields(field, codes: str) -> list[str]:
    return [(child.text or "").strip() for child in field
            if local(child.tag) == "subfield" and child.get("code") in codes
            and (child.text or "").strip()]


def first(field, code: str):
    values = subfields(field, code)
    return values[0] if values else None


def clean(value):
    """La ponctuation ISBD de fin de sous-zone, comme `ixtheo_hydrate_sru.clean`."""
    if not value:
        return None
    value = unicodedata.normalize("NFC", value)
    # Marques de non-classement MARC (NSB/NSE, U+0098 et U+009C) : « \u0098Das\u009c ».
    value = value.replace("\u0098", "").replace("\u009c", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip().rstrip(" /:;,.=").strip() or None


def years_in(text) -> list[int]:
    return [int(y) for y in re.findall(r"(?<!\d)(\d{4})(?!\d)", text or "")]


def unique(values) -> list:
    out = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out


# ---------------------------------------------------------------------------
# MARC21 (K10plus, DNB, B3Kat, GBD, LoC)
# ---------------------------------------------------------------------------

def marc21_title(record):
    for field in datafields(record, "245"):
        main = " ".join(p for p in (clean(first(field, "a")),
                                    *[clean(v) for v in subfields(field, "np")]) if p)
        rest = clean(first(field, "b"))
        if main and rest:
            return "%s : %s" % (main, rest)
        return main or rest
    return None


def marc21_years(record) -> list[int]:
    fixed = controlfield(record, "008")
    found = [int(fixed[s:s + 4]) for s in (7, 11) if fixed[s:s + 4].isdigit()]
    for field in datafields(record, ("264", "260")):
        found += [y for value in subfields(field, "c") for y in years_in(value)]
    for field in datafields(record, "773"):
        found += [y for value in subfields(field, "gd") for y in years_in(value)]
    return unique(found)


def marc21_language(record):
    for field in datafields(record, "041"):
        value = first(field, "a")
        if value:
            return value
    code = controlfield(record, "008")[35:38].strip()
    return code if code and code not in ("|||", "und") else None


def marc21_authors(record) -> list[str]:
    return unique(clean(first(field, "a"))
                  for field in datafields(record, ("100", "110", "111", "700", "710", "711")))


def marc21_author_roles(record) -> list[list]:
    """[nom, [codes de rôle]] des zones 100, 110, 111, 700, 710, 711.

    Le code `$4` d'abord (`prt`, ou l'URI id.loc.gov du code) ; à défaut, la
    mention en clair `$e` (« printer », « DruckerIn »). Une zone sans l'un ni
    l'autre donne une liste vide : le rôle n'est pas connu."""
    roles: "OrderedDict[str, list]" = OrderedDict()
    for field in datafields(record, ("100", "110", "111", "700", "710", "711")):
        name = clean(first(field, "a"))
        if not name:
            continue
        codes = [relator_code(v) for v in subfields(field, "4")]
        if not codes:
            codes = [relator_code(v) for v in subfields(field, "e")]
        known = roles.setdefault(name, [])
        known.extend(code for code in codes if code and code not in known)
    return [[name, codes] for name, codes in roles.items()]


def marc21_container(record):
    for field in datafields(record, "773"):
        title = clean(first(field, "t")) or clean(first(field, "a"))
        if title:
            return {"type": "host", "title": title, "details": subfields(field, "g") or None,
                    "issn": first(field, "x")}
    for tag in ("490", "830"):
        for field in datafields(record, tag):
            title = clean(first(field, "a"))
            if title:
                return {"type": "series", "title": title, "details": subfields(field, "v") or None,
                        "issn": first(field, "x")}
    return None


def marc21_subject_fields(record, tags) -> list[list[str]]:
    out = []
    for field in datafields(record, tags):
        heading = clean(first(field, "a"))
        if heading:
            out.append([field.get("tag"), heading])
    return out


def marc21_chains(record) -> list[str]:
    return unique(clean(first(field, "a")) for field in datafields(record, "689"))


# ---------------------------------------------------------------------------
# UNIMARC (Sudoc, BnF)
# ---------------------------------------------------------------------------

def unimarc_title(record):
    for field in datafields(record, "200"):
        main = " ".join(p for p in (clean(first(field, "a")),
                                    *[clean(v) for v in subfields(field, "hi")]) if p)
        rest = clean(first(field, "e"))
        if main and rest:
            return "%s : %s" % (main, rest)
        return main or rest
    return None


def unimarc_years(record) -> list[int]:
    found = []
    for field in datafields(record, "100"):
        coded = first(field, "a") or ""
        found += [int(coded[s:s + 4]) for s in (9, 13) if coded[s:s + 4].isdigit()]
    for field in datafields(record, ("210", "214")):
        found += [y for value in subfields(field, "dh") for y in years_in(value)]
    for field in datafields(record, ("461", "463")):
        found += [y for value in subfields(field, "dv") for y in years_in(value)]
    return unique(found)


def unimarc_language(record):
    for field in datafields(record, "101"):
        value = first(field, "a")
        if value:
            return value
    return None


def unimarc_name(field):
    name, forename = clean(first(field, "a")), clean(first(field, "b"))
    if name and forename:
        return "%s, %s" % (name, forename)
    return name


def unimarc_authors(record) -> list[str]:
    return unique(unimarc_name(field)
                  for field in datafields(record, ("700", "701", "702", "710", "711", "712")))


def unimarc_author_roles(record) -> list[list]:
    """[nom, [codes de rôle]] des zones 700 à 712, codes `$4` (`070`, `610`)."""
    roles: "OrderedDict[str, list]" = OrderedDict()
    for field in datafields(record, ("700", "701", "702", "710", "711", "712")):
        name = unimarc_name(field)
        if not name:
            continue
        known = roles.setdefault(name, [])
        known.extend(code for code in (relator_code(v) for v in subfields(field, "4"))
                     if code and code not in known)
    return [[name, codes] for name, codes in roles.items()]


def unimarc_container(record):
    for tag in ("463", "461"):
        for field in datafields(record, tag):
            title = clean(first(field, "t")) or clean(first(field, "a"))
            if title:
                return {"type": "host", "title": title, "details": subfields(field, "v") or None,
                        "issn": first(field, "x")}
    for tag, code in (("225", "a"), ("410", "t")):
        for field in datafields(record, tag):
            title = clean(first(field, code))
            if title:
                return {"type": "series", "title": title, "details": subfields(field, "v") or None,
                        "issn": first(field, "x")}
    return None


def unimarc_subject_fields(record, tags) -> list[list[str]]:
    out = []
    for field in datafields(record, tags):
        tag = field.get("tag")
        heading = clean(first(field, "a"))
        if heading:
            out.append([tag, heading])
    return out


# ---------------------------------------------------------------------------
# Une notice complète
# ---------------------------------------------------------------------------

def parse_record(record, fmt: str) -> dict:
    """Les champs utiles d'une notice MARC21 ou UNIMARC."""
    if fmt == "unimarc":
        subject_fields = unimarc_subject_fields(record, SUBJECT_TAGS["unimarc"])
        parsed = {"title": unimarc_title(record), "authors": unimarc_authors(record),
                  "author_roles": unimarc_author_roles(record),
                  "years": unimarc_years(record), "language": unimarc_language(record),
                  "container": unimarc_container(record), "subject_chains": []}
    else:
        subject_fields = marc21_subject_fields(record, SUBJECT_TAGS["marc21"])
        parsed = {"title": marc21_title(record), "authors": marc21_authors(record),
                  "author_roles": marc21_author_roles(record),
                  "years": marc21_years(record), "language": marc21_language(record),
                  "container": marc21_container(record), "subject_chains": marc21_chains(record)}
    parsed["year"] = parsed["years"][0] if parsed["years"] else None
    parsed["subject_fields"] = subject_fields
    parsed["subjects"] = unique(heading for _, heading in subject_fields)
    parsed["record_id"] = controlfield(record, "001").strip() or None
    return parsed


def select_record(body: bytes, source: str, identifier: str):
    """La notice demandée dans une réponse brute, ou FetchError."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError as error:
        raise FetchError("unparseable-response", str(error)[:120]) from None
    if local(root.tag) == "error":
        raise FetchError("not-found", (root.text or "").strip()[:120])
    records = marc_records(root)
    declared = number_of_records(root)
    if declared == 0 or not records:
        raise FetchError("no-record", "numberOfRecords=%s" % declared)
    if len(records) > 1:
        if SOURCES[source]["id_in_001"]:
            matching = [r for r in records if controlfield(r, "001").strip() == identifier]
        else:
            matching = [r for r in records if r.get("id") == identifier]
        if len(matching) != 1:
            raise FetchError("ambiguous-response", "%d records" % len(records))
        records = matching
    declared_id = records[0].get("id")
    if declared_id and not SOURCES[source]["id_in_001"] and declared_id != identifier:
        raise FetchError("wrong-record", declared_id[:120])
    return records[0]


# ---------------------------------------------------------------------------
# Contrôle d'identité : la notice relue est-elle celle du snapshot ?
# ---------------------------------------------------------------------------

TITLE_SHARE = 0.8     # part des mots du titre publié retrouvés dans la notice
TITLE_PROPER_SHARE = 0.5


def title_tokens(text) -> list[str]:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("\u0098", "").replace("\u009c", "").replace("\u00ac", "")
    return re.findall(r"\w+", text.casefold())


def title_agreement(published, fetched, fetched_proper=None) -> str:
    """`prefix`, `shared-words` ou `differs`.

    Le titre publié est tronqué à 120 caractères (« … ») : son dernier mot peut
    être coupé et n'est pas exigé."""
    snapshot = title_tokens(published)
    if isinstance(published, str) and published.rstrip().endswith("…") and len(snapshot) > 1:
        snapshot = snapshot[:-1]
    record = title_tokens(fetched)
    if not snapshot or not record:
        return "differs"
    shortest = min(len(snapshot), len(record))
    if snapshot[:shortest] == record[:shortest]:
        return "prefix"
    shared = set(snapshot) & set(record)
    proper = set(title_tokens(fetched_proper)) or set(record)
    if (len(shared) / len(set(snapshot)) >= TITLE_SHARE
            and len(shared & proper) / len(proper) >= TITLE_PROPER_SHARE):
        return "shared-words"
    return "differs"


def identity_check(row: dict, parsed: dict) -> dict:
    title = title_agreement(row.get("title"), parsed.get("title"), parsed.get("title_proper"))
    snapshot_year = row.get("year")
    if not isinstance(snapshot_year, int):
        year = "unverifiable-snapshot"
    elif not parsed.get("years"):
        year = "unverifiable-record"
    elif snapshot_year in parsed["years"]:
        year = "match"
    else:
        year = "differs"
    status = "verified" if title != "differs" and year != "differs" else "mismatch"
    return {"status": status, "title": title, "year": year,
            "snapshot_title": row.get("title"), "snapshot_year": snapshot_year}


def title_proper(record, fmt: str):
    tag, code = ("200", "a") if fmt == "unimarc" else ("245", "a")
    for field in datafields(record, tag):
        return clean(first(field, code))
    return None


def build_entry(row: dict, body: bytes, fetched_at: str, origin: str) -> dict:
    source, identifier = row["source"], row["source_id"]
    fmt = SOURCES[source]["format"]
    record = select_record(body, source, identifier)
    parsed = parse_record(record, fmt)
    parsed["title_proper"] = title_proper(record, fmt)
    entry = OrderedDict()
    entry["source"] = source
    entry["source_id"] = identifier
    entry["fetched_at"] = fetched_at
    entry["fetched_from"] = origin
    entry["request_url"] = SOURCES[source]["url"](identifier)
    entry["format"] = fmt
    entry["record_id"] = parsed["record_id"]
    entry["title"] = parsed["title"]
    entry["authors"] = parsed["authors"]
    entry["author_roles"] = parsed["author_roles"]
    entry["year"] = parsed["year"]
    entry["years"] = parsed["years"]
    entry["language"] = parsed["language"]
    entry["subjects"] = parsed["subjects"]
    entry["subject_chains"] = parsed["subject_chains"]
    entry["subject_fields"] = parsed["subject_fields"]
    entry["container"] = parsed["container"]
    entry["identity"] = identity_check(row, parsed)
    entry["cache"] = cache_path(Path("data/raw/authority"), source, identifier).as_posix()
    return entry


# ---------------------------------------------------------------------------
# Réseau, cache, reprise
# ---------------------------------------------------------------------------

def cache_path(out_dir: Path, source: str, identifier: str) -> Path:
    return out_dir / source / (re.sub(r"[^A-Za-z0-9._-]", "_", identifier) + ".xml")


class Throttle:
    """Au plus une requête par intervalle, pour un hôte."""

    def __init__(self, interval: float = MIN_INTERVAL, clock=time.monotonic, sleep=time.sleep):
        self.interval, self.clock, self.sleep = interval, clock, sleep
        self.last = None

    def wait(self):
        if self.last is not None:
            remaining = self.interval - (self.clock() - self.last)
            if remaining > 0:
                self.sleep(remaining)
        self.last = self.clock()


def fetch(url: str, throttle: Throttle, opener=urllib.request.urlopen, sleep=time.sleep) -> bytes:
    """GET poli : 404 sans reprise, 429 et 5xx repris avec attente croissante."""
    last = None
    for attempt in range(TRIES):
        throttle.wait()
        request = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT, "Accept": "application/xml, text/xml"})
        try:
            with opener(request, timeout=TIMEOUT) as response:
                body = response.read()
                kind = (response.headers.get("Content-Type") or "").lower()
            if "html" in kind:
                raise FetchError("not-marcxml", kind)
            return body
        except urllib.error.HTTPError as error:
            if error.code == 404:
                empty = not (error.fp and error.read())
                raise FetchError("not-found", "HTTP 404" + (", empty body" if empty else "")) from None
            if error.code != 429 and error.code < 500:
                raise FetchError("http-%d" % error.code) from None
            last = FetchError("http-%d" % error.code, "after %d tries" % TRIES)
            wait = retry_after_seconds(error)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
            last = FetchError("network", str(getattr(error, "reason", error))[:120])
            wait = None
        sleep(wait if wait is not None else BACKOFF * (2 ** attempt))
    raise last


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def key_of(entry: dict) -> str:
    return "%s:%s" % (entry["source"], entry["source_id"])


def pending_rows(rows: list[dict], done: set, sources=None, limit=None) -> list[dict]:
    """Les lignes du snapshot à relire : sources d'autorité, pas encore écrites."""
    per_source = defaultdict(int)
    out = []
    for row in rows:
        source = row.get("source")
        if source not in SOURCES or (sources and source not in sources):
            continue
        if limit is not None and per_source[source] >= limit:
            continue
        per_source[source] += 1
        if key_of(row) not in done:
            out.append(row)
    return out


def host_of(source: str) -> str:
    return urllib.parse.urlsplit(SOURCES[source]["url"]("x")).hostname


def summarise(rows: list[dict], records: list[dict], failures: list[dict], sources=None) -> dict:
    """Le tableau par source : demandées, obtenues, lues, avec vedettes, etc."""
    table = OrderedDict()
    for row in rows:
        source = row.get("source")
        if source in SOURCES and (not sources or source in sources):
            table.setdefault(source, OrderedDict(
                requested=0, fetched=0, parsed=0, verified=0, with_subjects=0,
                with_container=0, mismatches=0, failures=0))["requested"] += 1
    written = set()
    for entry in records:
        if entry["source"] not in table:
            continue
        written.add(key_of(entry))
        line = table[entry["source"]]
        line["fetched"] += 1
        line["parsed"] += 1
        if entry["identity"]["status"] == "verified":
            line["verified"] += 1
            line["with_subjects"] += bool(entry["subjects"] or entry["subject_chains"])
            line["with_container"] += bool(entry["container"])
        else:
            line["mismatches"] += 1
    latest = {}
    for failure in failures:
        latest[key_of(failure)] = failure
    for key, failure in latest.items():
        if key not in written and failure["source"] in table:
            table[failure["source"]]["failures"] += 1
    return table


class Harvest:
    def __init__(self, out_dir: Path, rows: list[dict]):
        self.out_dir = out_dir
        self.records_path = out_dir / "records.jsonl"
        self.failures_path = out_dir / "failures.jsonl"
        self.progress_path = out_dir / "progress.json"
        self.rows = rows
        self.lock = threading.Lock()
        self.started = now()

    def write_progress(self, done: bool, sources=None):
        table = summarise(self.rows, read_jsonl(self.records_path),
                          read_jsonl(self.failures_path), sources)
        payload = {"started_at": self.started, "updated_at": now(), "done": done,
                   "sources": table}
        temporary = self.progress_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        temporary.replace(self.progress_path)

    def append(self, path: Path, entry: dict):
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def one(self, row: dict, throttle: Throttle):
        source, identifier = row["source"], row["source_id"]
        cached = cache_path(self.out_dir, source, identifier)
        try:
            if cached.is_file():
                body = cached.read_bytes()
                fetched_at = datetime.fromtimestamp(cached.stat().st_mtime, timezone.utc)\
                    .replace(microsecond=0).isoformat()
                entry = build_entry(row, body, fetched_at, "cache")
            else:
                fetched_at = now()
                body = fetch(SOURCES[source]["url"](identifier), throttle)
                select_record(body, source, identifier)
                cached.parent.mkdir(parents=True, exist_ok=True)
                temporary = cached.with_suffix(".tmp")
                temporary.write_bytes(body)
                temporary.replace(cached)
                entry = build_entry(row, body, fetched_at, "network")
        except FetchError as error:
            with self.lock:
                self.append(self.failures_path, {"source": source, "source_id": identifier,
                                                 "at": now(), "cause": error.cause,
                                                 "detail": error.detail})
            return
        except Exception as error:  # noqa: BLE001 : une notice illisible n'arrête pas l'hôte
            with self.lock:
                self.append(self.failures_path, {"source": source, "source_id": identifier,
                                                 "at": now(), "cause": "parse-error",
                                                 "detail": repr(error)[:160]})
            return
        with self.lock:
            self.append(self.records_path, entry)
            if entry["identity"]["status"] != "verified":
                self.append(self.failures_path, {"source": source, "source_id": identifier,
                                                 "at": now(), "cause": "identity-mismatch",
                                                 "detail": entry["identity"]})

    def run(self, todo: list[dict], sources=None):
        self.out_dir.mkdir(parents=True, exist_ok=True)
        by_host = defaultdict(list)
        for row in todo:
            by_host[host_of(row["source"])].append(row)

        def worker(items):
            throttle = Throttle(max(SOURCES[row["source"]].get("interval", MIN_INTERVAL)
                                    for row in items))
            for count, row in enumerate(items, 1):
                self.one(row, throttle)
                if count % 10 == 0:
                    with self.lock:
                        self.write_progress(False, sources)

        threads = [threading.Thread(target=worker, args=(items,), daemon=True)
                   for items in by_host.values()]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.write_progress(True, sources)


def reparse(out_dir: Path, rows: list[dict]) -> int:
    """Réécrit records.jsonl depuis le cache seul, sans réseau (règle changée)."""
    records_path = out_dir / "records.jsonl"
    previous = {key_of(entry): entry for entry in read_jsonl(records_path)}
    entries = []
    for row in rows:
        if row.get("source") not in SOURCES:
            continue
        cached = cache_path(out_dir, row["source"], row["source_id"])
        if not cached.is_file():
            continue
        old = previous.get(key_of(row))
        fetched_at = old["fetched_at"] if old else datetime.fromtimestamp(
            cached.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat()
        entry = build_entry(row, cached.read_bytes(), fetched_at, "cache")
        if old:
            entry["fetched_from"] = old.get("fetched_from", "cache")
            entry["request_url"] = old.get("request_url", entry["request_url"])
        entries.append(entry)
    temporary = records_path.with_suffix(".tmp")
    temporary.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries),
                         encoding="utf-8")
    temporary.replace(records_path)
    return len(entries)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--records", type=Path, default=RECORDS_IN)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--sources", default=None, help="liste séparée par des virgules")
    parser.add_argument("--limit", type=int, default=None, help="notices par source (essai)")
    parser.add_argument("--reparse", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args(argv)

    rows = read_jsonl(args.records)
    sources = set(args.sources.split(",")) if args.sources else None
    if sources and not sources <= set(SOURCES):
        parser.error("unknown source: %s" % ", ".join(sorted(sources - set(SOURCES))))
    if args.reparse:
        print("reparsed %d records from the cache" % reparse(args.out_dir, rows))
    elif not args.report:
        done = {key_of(entry) for entry in read_jsonl(args.out_dir / "records.jsonl")}
        todo = pending_rows(rows, done, sources, args.limit)
        print("to fetch: %d (already written: %d)" % (len(todo), len(done)), flush=True)
        Harvest(args.out_dir, rows).run(todo, sources)
    table = summarise(rows, read_jsonl(args.out_dir / "records.jsonl"),
                      read_jsonl(args.out_dir / "failures.jsonl"), sources)
    print(json.dumps(table, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
