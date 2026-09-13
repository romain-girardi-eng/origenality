#!/usr/bin/env python3
"""Refresh the replayable input snapshot of the public map from full records.

The August authority expansion was published from a temporary combined file that
no longer exists.  A first reconstruction rebuilt every record from the served
graph, including each record's subject headings and container, which it read
off graph *edges*.  Edges exist only above the graph thresholds (a heading needs
3 publications, a container 5), so every heading and container below them was
lost, the container type became `host` everywhere and `relation` disappeared
(audit of 13 September, OR-01, OR-44, OR-46).  This tool never reads edges.

The rows of `data/site-records.jsonl` are the base: identity, title, authors,
year, language, type, identifiers, abstracts and curated corrections stay as
they are, since the work clusters and their public identifiers are hashed from
them.  Three groups of fields are then taken from the richest source present:

* `subjects`, `subject_chains`, `container` (with its MARC type) and `relation`
  come from the catalogue record itself when the harvest is on disk
  (`data/raw/ixtheo/records.jsonl`, private working tree only);
* for the seven authority feeds (K10plus, Sudoc, B3Kat, Gnomon GBD, DNB, Library
  of Congress, BnF), `subjects`, `subject_chains` and `container` come from the
  catalogue record fetched again by `scripts/hydrate_authority_records.py`, when
  `--authority` names that harvest and the record passed its identity check
  (title and year against the row); `relation` stays what the row holds;
* otherwise, when `--release-graph` names the served graph of the release the
  snapshot replays, `relation` is read off the publication node and the
  container keeps the type of its container node;
* otherwise the row keeps what it already holds.

Four repairs then apply to every row, whatever its basis, and each is a no-op on
a row it has already repaired, so a rebuild without the harvests keeps them:

* **authors**: a person whose every role in the catalogue record is non-authorial
  (printer, former owner, publisher, bookseller, engraver, dedicatee and the
  other codes of `pipeline/fields.py`) is taken out of `authors` and kept, with
  those roles, in `authors_not_credited`.  The roles are read from the IxTheo
  harvest and from the re-fetched authority records; a row whose record is not
  on disk keeps its authors.  The first author of a work cluster enters its
  public identifier, and no author removed here was a first author;
* **container titles**: a trailing statement of responsibility
  (`Biblica / a Pontificio Instituto Biblico ...`, `Origeniana undecima / edited
  by ...`) is cut, and a free-text citation (`In: Markschies ... (Hrsg.): Die
  Welt als Bild ... S. 69-79`) is reduced to the host title it certainly names,
  or dropped when that title cannot be isolated.  A bracketed series statement
  and a sub-series (`Vetera Christianorum / Quaderni`) are left alone, since
  cutting them would merge a series into its journal.  The title as catalogued
  stays in `container_as_catalogued`;
* **record links**: a row or source link that points at another database's
  record (the B3Kat rows linked to the Gnomon database) is rebuilt from the
  source's own template in `DATA_POLICY.md`; a DOI link is kept;
* **curated corrections** (`data/corrections.json`) are applied last, after the
  authority join.

The re-fetched authority harvest is read by default when it is on disk
(`--no-authority` to leave it out).  `--check` says how many rows it could
actually derive again and from which inputs; in a clone without the harvests it
can only verify the structure of the rows, the uniqueness of their keys and the
corrections, and it fails there unless `--structure-only` says that is what the
caller wants.

Each row says where its headings and container come from, in
`subjects_container_basis`: `catalogue-record` (the IxTheo harvest),
`catalogue-record-refetched` (the authority hydration), or `public-projection`
when only the thresholded projection survives.  A later run without either
harvest keeps such a row as it is, so the snapshot cannot degrade by being
rebuilt.  `--authority` is explicit rather than read by default: that harvest is
dated separately from the release, and each row it gave records the day its record was
read (`subjects_container_fetched`), which `META.refetched` publishes.
The tool also refuses to write a snapshot whose field coverage falls below the
current one (`--allow-coverage-drop` to override, for a declared reason).

    python3 site/build-c/tools/build_public_snapshot.py
    python3 site/build-c/tools/build_public_snapshot.py --release-graph <graph.json>
    python3 site/build-c/tools/build_public_snapshot.py --authority <records.jsonl>
    python3 site/build-c/tools/build_public_snapshot.py --no-authority --output <file.jsonl>
    python3 site/build-c/tools/build_public_snapshot.py --check
    python3 site/build-c/tools/build_public_snapshot.py --check --structure-only   # clone
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
import sys
from urllib.parse import quote, urlsplit


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from tree_paths import data_dir, repository_root  # noqa: E402

ROOT = Path(repository_root(str(HERE)))
DATA = Path(data_dir(str(ROOT)))
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "scripts"))
from fields import non_authorial, relator_code  # noqa: E402
import check_release  # noqa: E402  (la table d'attribution, lue dans DATA_POLICY.md)

POLICY = ROOT / "DATA_POLICY.md"
RECORDS = DATA / "site-records.jsonl"
CORRECTIONS = DATA / "corrections.json"
IXTHEO_RAW = ROOT / "data" / "raw" / "ixtheo" / "records.jsonl"
IXTHEO = "ixtheo-k10plus"
AUTHORITY_RAW = ROOT / "data" / "raw" / "authority" / "records.jsonl"
AUTHORITY_SOURCES = ("k10plus", "sudoc", "b3kat", "gnomon-gbd", "dnb", "loc", "bnf")

CATALOGUE = "catalogue-record"
PROJECTION = "public-projection"
REFETCHED = "catalogue-record-refetched"
FULL_BASES = (CATALOGUE, REFETCHED)

# A rebuild may not lose more than this share of the records carrying a field.
COVERAGE_TOLERANCE = 0.01
COVERED_FIELDS = ("subjects", "container", "container_type", "relation", "doi", "isbn",
                  "publisher", "year", "language", "authors", "abstract")

C1 = str.maketrans({
    "": "‘", "": "’", "": "“", "": "”",
    "": "–", "": "—", "": "", "": "",
})


def clean_text(value):
    if not isinstance(value, str):
        return value
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.IGNORECASE)
    value = value.translate(C1)
    value = unicodedata.normalize("NFC", value)
    return re.sub(r"\s+", " ", value).strip()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def serialise(rows: list[dict]) -> str:
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)


def clean_list(values) -> list[str]:
    if isinstance(values, str):
        values = [values]
    out: list[str] = []
    for value in values or []:
        text = clean_text(value) if isinstance(value, str) else None
        if text and text not in out:
            out.append(text)
    return out


def container_value(title, ctype) -> dict | None:
    title = clean_text(title) if isinstance(title, str) else None
    if not title:
        return None
    return {"title": title, "type": ctype if isinstance(ctype, str) and ctype else None}


def from_catalogue(record: dict) -> dict:
    """The fields a catalogue record gives in full, before any threshold."""
    container = record.get("container")
    if isinstance(container, dict):
        container = container_value(container.get("title"), container.get("type"))
    else:
        container = container_value(container, None)
    return {
        "subjects": clean_list(record.get("subjects")),
        "subject_chains": clean_list(record.get("subject_chains")),
        "container": container,
        "relation": record.get("relation"),
        "subjects_container_basis": CATALOGUE,
    }


def release_projection(graph: dict) -> dict[str, dict]:
    """`source:id` -> relation and container (with its type) of the served graph."""
    nodes = graph["nodes"]
    first_container: dict[int, dict] = {}
    for edge in graph["edges"]:
        if edge.get("r") == "in":
            first_container.setdefault(edge["s"], nodes[edge["t"]])
    table: dict[str, dict] = {}
    for index, node in enumerate(nodes):
        if node.get("k") != "pub":
            continue
        sources = node.get("src") or []
        if len(sources) != 1:
            continue
        container = first_container.get(index)
        table[f"{sources[0]}:{node.get('ppn')}"] = {
            "relation": node.get("rel"),
            "container": (container_value(container.get("label"), container.get("ctype"))
                           if container else None),
        }
    return table


def load_catalogue(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    return {f"{IXTHEO}:{record.get('source_id')}": record for record in read_jsonl(path)
            if record.get("source_id") is not None}


def load_authority(path: Path | None) -> dict[str, dict]:
    """Re-fetched authority records that passed their identity check, by `source:id`.

    A record whose title or year disagreed with the row is written by the
    harvester with `identity.status = "mismatch"`; it is never used here."""
    if path is None or not path.is_file():
        return {}
    return {f"{record['source']}:{record['source_id']}": record
            for record in read_jsonl(path)
            if record.get("source") in AUTHORITY_SOURCES
            and (record.get("identity") or {}).get("status") == "verified"}


def from_authority(record: dict) -> dict:
    """Headings and container of a re-fetched record; its relation is not in it."""
    fields = from_catalogue(record)
    del fields["relation"]
    fields["subjects_container_basis"] = REFETCHED
    fetched = str(record.get("fetched_at") or "")[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", fetched):
        fields["subjects_container_fetched"] = fetched
    return fields


# ---------------------------------------------------------------------------
# Authors: who the catalogue names without crediting them with the work
# ---------------------------------------------------------------------------

def name_key(name) -> str:
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.casefold()).strip(" .,;")


def catalogue_roles(record: dict | None) -> dict[str, list[str]]:
    """Name key -> role codes, from an IxTheo record (authors as objects with a
    `role`) or a re-fetched authority record (`author_roles`).  A name listed
    without a role gets an empty code, which keeps it among the authors."""
    roles: dict[str, list[str]] = {}
    if not isinstance(record, dict):
        return roles
    for author in record.get("authors") or []:
        if isinstance(author, dict) and author.get("name"):
            roles.setdefault(name_key(author["name"]), []).append(author.get("role") or "")
    for entry in record.get("author_roles") or []:
        if isinstance(entry, (list, tuple)) and len(entry) == 2 and entry[0]:
            roles.setdefault(name_key(entry[0]), []).extend(entry[1] or [""])
    return roles


def credited_authors(row: dict, roles: dict[str, list[str]]) -> tuple[list, list[dict]]:
    """(authors kept, persons set aside with their roles)."""
    kept, dropped = [], []
    for author in row.get("authors") or []:
        name = author.get("name") if isinstance(author, dict) else author
        codes = roles.get(name_key(name))
        if codes and non_authorial(codes):
            dropped.append({"name": name,
                            "roles": sorted({relator_code(code) for code in codes})})
        else:
            kept.append(author)
    return kept, dropped


# ---------------------------------------------------------------------------
# Container titles: the title, without the statement of responsibility
# ---------------------------------------------------------------------------

IN_CITATION = re.compile(r"^\s*In\s*:\s*(?P<body>.+)$", re.IGNORECASE | re.DOTALL)
EDITED_BY = re.compile(r"\((?:hrsg|hg|eds?|éds?|dir)\.?\)\s*:\s*", re.IGNORECASE)
CITATION_END = re.compile(r"\.\s*\(|,\s*S\.\s*\d|,\s*pp?\.\s*\d")
EDITORIAL = re.compile(
    r"\b(?:ed|eds|edd|hrsg|hg|red|publ|pubbl|coll|dir|éd|éds)\."
    r"|\((?:ed|eds|hg|hrsg|éd|dir)\.?\)"
    r"|\b(?:edited|editor|editors|editi|herausgegeben|herausgeber\w*|bearbeitet|a cura"
    r"|sous la dir\w*|dirigé|fondata|comitato|auspiciis|im auftr\w*|in zsarb\w*|durch"
    r"|board)\b|\[u\.a\.\]|^per\s+[A-Z]", re.IGNORECASE)
CORPORATE = re.compile(
    r"akademi|academy|accademia|universi|institut|association|associazion|societ|library"
    r"|bibliothe|bibliotec|college|departament|dipartimento|department|facult|cattedra"
    r"|delegazione|kabinet|ustav|fundaci|klasse|commission|kommission|scuola|school"
    r"|\bcent(?:re|er|ro|rul)\b|pontifici", re.IGNORECASE)
NAME_TOKEN = r"(?:[A-ZÀ-ÖØ-Þ][\w'’\-]*\.?|van|von|de|den|der|da|di|du|la|le|del|della)"
PERSON = re.compile(r"^%s(?:\s+%s){1,4}$" % (NAME_TOKEN, NAME_TOKEN))


def split_responsibility(title: str) -> tuple[str, str | None]:
    """(title proper, statement) at the first ` / ` outside square brackets."""
    depth = 0
    for index, char in enumerate(title):
        if char == "[":
            depth += 1
        elif char == "]":
            depth = max(0, depth - 1)
        elif depth == 0 and title.startswith(" / ", index):
            return title[:index], title[index + 3:]
    return title, None


def responsibility_kind(statement: str) -> str | None:
    """`editorial` (an editor, a direction, a founder), `persons` (a list of names),
    `corporate` (an issuing body alone), or None for anything else, a sub-series
    such as `Quaderni` included."""
    statement = statement.strip()
    if not statement:
        return None
    if EDITORIAL.search(statement):
        return "editorial"
    persons = [part.strip() for part in re.split(r"\s*;\s*|\s+(?:and|und|et|&)\s+|,\s+",
                                                 statement) if part.strip()]
    if CORPORATE.search(statement):
        return "corporate"
    if persons and all(PERSON.match(part) for part in persons):
        return "persons"
    return None


def host_of_citation(body: str) -> str | None:
    """The host title of an `In: <editors> (Hrsg.): <title>. (<series>) ...` citation,
    when its end can be found; None otherwise."""
    edited = EDITED_BY.search(body)
    if not edited:
        return None
    tail = body[edited.end():]
    end = CITATION_END.search(tail)
    if not end:
        return None
    return tail[:end.start()].strip(" .,;:") or None


def clean_container_title(title, known_titles=frozenset()):
    """The container title without its statement of responsibility; None when a
    free-text citation names no host title that can be isolated.

    An issuing body alone is what tells `Skrifter / Det Norske Videnskaps-Akademi`
    or `Études / Institut Historique Belge de Rome` from another series of the
    same short name.  It is cut only when the title left has three words or more,
    or when that title already stands, as catalogued, on another record of the
    snapshot (`known_titles`, casefolded), which is the same series counted twice.
    """
    if not isinstance(title, str):
        return title
    text = title.strip()
    cited = IN_CITATION.match(text)
    if cited:
        return host_of_citation(cited.group("body"))
    head, statement = split_responsibility(text)
    head = head.strip().rstrip(" /:;,")
    if statement is None or not head:
        return text
    kind = responsibility_kind(statement)
    if kind is None:
        return text
    if kind == "corporate":
        words = [word for word in re.split(r"\s+", head) if re.search(r"\w", word)]
        if len(words) < 3 and head.casefold() not in known_titles:
            return text
    return head


def known_container_titles(rows: list[dict]) -> frozenset:
    titles = set()
    for row in rows:
        container = row.get("container")
        if isinstance(container, dict) and isinstance(container.get("title"), str):
            titles.add(container["title"].strip().casefold())
    return frozenset(titles)


def clean_container(row: dict, known_titles=frozenset()) -> None:
    container = row.get("container")
    if not isinstance(container, dict) or not isinstance(container.get("title"), str):
        return
    cleaned = clean_container_title(container["title"], known_titles)
    if cleaned == container["title"]:
        return
    row.setdefault("container_as_catalogued", container["title"])
    row["container"] = container_value(cleaned, container.get("type")) if cleaned else None


# ---------------------------------------------------------------------------
# Record links: each record under its own database's address
# ---------------------------------------------------------------------------

DOI_HOSTS = {"doi.org", "dx.doi.org"}


def load_attribution(path: Path = POLICY) -> dict:
    return check_release.load_policy(path)["attribution"] if path.is_file() else {}


def own_record_url(source, identifier, attribution: dict) -> str | None:
    """The record address a source's template gives, or None without a template."""
    if not source or identifier in (None, ""):
        return None
    identifier = str(identifier)
    if source == "bnf":
        ark = identifier if identifier.startswith("ark:/") else "ark:/12148/" + identifier
        return "https://catalogue.bnf.fr/" + ark
    template = (attribution.get(source) or {}).get("url_template")
    if not isinstance(template, str) or "{id}" not in template or template.strip() == "{id}":
        return None
    return template.replace("{id}", quote(identifier, safe="/:@"))


def misdirected(url, expected: str | None) -> bool:
    """A link absent, or on another host than the source's own, and not a DOI."""
    if not expected:
        return False
    if not isinstance(url, str) or not url.startswith("http"):
        return True
    host = urlsplit(url).hostname or ""
    return host != urlsplit(expected).hostname and host not in DOI_HOSTS


def repair_record_urls(row: dict, attribution: dict) -> None:
    """The row's own link may be a DOI; a source entry links its catalogue record.

    A source entry is what the Explorer credits under the database's name, so it
    points at that database's record, never at a DOI: the DNB record 1321906943
    carried a DOI that does not resolve (record-link sample of 13 September)."""
    expected = own_record_url(row.get("source"), row.get("source_id"), attribution)
    if misdirected(row.get("url"), expected):
        row["url"] = expected
    for entry in row.get("sources") or []:
        if not isinstance(entry, dict):
            continue
        expected = own_record_url(entry.get("source"), entry.get("source_id"), attribution)
        if expected and entry.get("url") != expected:
            entry["url"] = expected


def refresh(rows: list[dict], catalogue: dict[str, dict], release: dict[str, dict],
            corrections: dict, authority: dict[str, dict] | None = None,
            attribution: dict | None = None) -> list[dict]:
    authority = authority or {}
    out = []
    for base in rows:
        row = json.loads(json.dumps(base))
        key = row["origenality_id"]
        if key in catalogue:
            row.pop("container_as_catalogued", None)
            row.update(from_catalogue(catalogue[key]))
        elif key in authority and row.get("source") in AUTHORITY_SOURCES:
            row.pop("container_as_catalogued", None)
            row.update(from_authority(authority[key]))
            projected = release.get(key)
            if projected is not None:
                row["relation"] = projected["relation"]
            row.setdefault("relation", None)
        elif row.get("subjects_container_basis") not in FULL_BASES:
            row["subjects_container_basis"] = PROJECTION
            projected = release.get(key)
            if projected is not None:
                row["relation"] = projected["relation"]
                if projected["container"] is not None:
                    row["container"] = projected["container"]
            if isinstance(row.get("container"), str):
                row["container"] = container_value(row["container"], None)
            row.setdefault("relation", None)
            row.setdefault("subject_chains", [])
        record = catalogue.get(key) or (authority.get(key)
                                        if row.get("source") in AUTHORITY_SOURCES else None)
        if record is not None:
            kept, dropped = credited_authors(row, catalogue_roles(record))
            if dropped:
                row["authors"] = kept
                known = {name_key(entry.get("name")) for entry in
                         row.get("authors_not_credited") or []}
                row["authors_not_credited"] = (row.get("authors_not_credited") or []) + [
                    entry for entry in dropped if name_key(entry["name"]) not in known]
        if attribution:
            repair_record_urls(row, attribution)
        out.append(row)
    # The titles as the records give them, before any is cut: a short title that
    # stands bare on another record is the same series counted twice.
    known = known_container_titles(out)
    for row in out:
        clean_container(row, known)
        correction = corrections.get(row["origenality_id"])
        if correction:
            row.update(correction.get("fields") or {})
            row["curated_correction"] = {"basis": correction.get("basis"),
                                         "reason": correction.get("reason")}
    return out


def coverage(rows: list[dict]) -> dict[str, int]:
    """Records carrying each field, and the number of distinct values that matter."""
    def present(row, field):
        if field == "container_type":
            container = row.get("container")
            return isinstance(container, dict) and bool(container.get("type"))
        if field == "subjects":
            return bool(row.get("subjects") or row.get("subject_chains"))
        value = row.get(field)
        return value not in (None, "", [], {})

    counts = {field: sum(1 for row in rows if present(row, field)) for field in COVERED_FIELDS}
    headings, containers = set(), set()
    for row in rows:
        for value in (row.get("subjects") or []) + (row.get("subject_chains") or []):
            headings.add(value.casefold())
        container = row.get("container")
        title = container.get("title") if isinstance(container, dict) else container
        if isinstance(title, str) and title:
            containers.add(title.casefold())
    counts["records"] = len(rows)
    counts["distinct_headings"] = len(headings)
    counts["distinct_containers"] = len(containers)
    counts["basis_catalogue_record"] = sum(
        1 for row in rows if row.get("subjects_container_basis") in FULL_BASES)
    return counts


def coverage_drops(before: dict[str, int], after: dict[str, int],
                   tolerance: float = COVERAGE_TOLERANCE) -> list[str]:
    """Fields whose coverage falls by more than the tolerance between two snapshots."""
    drops = []
    for field, old in before.items():
        new = after.get(field, 0)
        if old and new < old * (1 - tolerance):
            drops.append(f"{field}: {old} -> {new}")
    return drops


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--records", type=Path, default=RECORDS)
    parser.add_argument("--catalogue", type=Path, default=IXTHEO_RAW,
                        help="full IxTheo harvest; skipped when absent")
    parser.add_argument("--release-graph", type=Path, default=None,
                        help="served graph.json of the release this snapshot replays")
    parser.add_argument("--authority", type=Path, nargs="?", const=AUTHORITY_RAW,
                        default=AUTHORITY_RAW if AUTHORITY_RAW.is_file() else None,
                        help="records of the seven authority feeds fetched again by "
                             "scripts/hydrate_authority_records.py (read by default "
                             "when it is on disk)")
    parser.add_argument("--no-authority", action="store_true",
                        help="leave the re-fetched authority records out")
    parser.add_argument("--structure-only", action="store_true",
                        help="with --check, accept that no row can be derived again "
                             "(a clone without the harvests)")
    parser.add_argument("--output", type=Path, default=None,
                        help="where to write, or what --check compares (default: --records)")
    parser.add_argument("--allow-coverage-drop", metavar="REASON", default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    rows = read_jsonl(args.records)
    corrections = (json.loads(CORRECTIONS.read_text(encoding="utf-8"))
                   if CORRECTIONS.exists() else {})
    catalogue = load_catalogue(args.catalogue)
    release = (release_projection(json.loads(args.release_graph.read_text(encoding="utf-8")))
               if args.release_graph else {})
    if args.release_graph and not release:
        raise SystemExit("the release graph holds no single-source publication node")
    authority_path = None if args.no_authority else args.authority
    authority = load_authority(authority_path)
    if authority_path and not authority:
        raise SystemExit("the authority harvest holds no verified record")
    attribution = load_attribution()
    refreshed = refresh(rows, catalogue, release, corrections, authority, attribution)
    output = args.output or args.records
    used = sum(1 for row in refreshed if row.get("subjects_container_basis") == REFETCHED)
    keys = [row.get("origenality_id") for row in rows]
    duplicates = sorted({key for key in keys if keys.count(key) > 1}) if len(set(keys)) != len(keys) else []
    from_ixtheo = sum(1 for row in rows if row.get("origenality_id") in catalogue)
    from_authority_records = sum(1 for row in rows if row.get("origenality_id") in authority
                                 and row.get("source") in AUTHORITY_SOURCES)
    derived = from_ixtheo + from_authority_records

    before, after = coverage(rows), coverage(refreshed)
    drops = coverage_drops(before, after)
    current = output.read_text(encoding="utf-8") if output.is_file() else ""
    wanted = serialise(refreshed)
    if args.check:
        def shown(path: Path | None) -> str:
            if path is None:
                return "not given"
            try:
                return path.resolve().relative_to(ROOT).as_posix()
            except ValueError:
                return path.name
        print(f"rows derived again from catalogue records on disk: {derived} of {len(rows)} "
              f"(IxTheo harvest {from_ixtheo}, {shown(args.catalogue)}"
              f"{'' if args.catalogue.is_file() else ', absent'}; re-fetched authority records "
              f"{from_authority_records}, {shown(authority_path)}"
              f"{'' if authority_path is None or authority_path.is_file() else ', absent'}); "
              f"rows checked as written: {len(rows) - derived}")
        if duplicates:
            print("duplicate record keys: " + ", ".join(duplicates[:20]))
            return 1
        if drops:
            print("coverage would drop: " + "; ".join(drops))
            return 1
        if current != wanted:
            print("public snapshot is stale")
            return 1
        if derived == 0:
            if not args.structure_only:
                print("FAIL: no row could be derived again, so this run checks the structure "
                      "of the rows, the uniqueness of their keys and the curated corrections, "
                      "not their content; pass --structure-only where that is what is meant")
                return 1
            print(f"structure only: {len(rows)} rows well formed, keys unique, corrections "
                  f"applied; no content was checked against a catalogue record")
            return 0
        print(f"public snapshot is current: {len(rows)} records, "
              f"{after['basis_catalogue_record']} with full catalogue headings, "
              f"{derived} derived again from the records on disk")
        return 0
    if drops and not args.allow_coverage_drop:
        print("REFUSED: field coverage would drop: " + "; ".join(drops), file=sys.stderr)
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(wanted, encoding="utf-8")
    print(json.dumps({"before": before, "after": after, "authority_rows": used},
                     indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
