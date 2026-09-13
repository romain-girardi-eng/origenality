#!/usr/bin/env python3
"""Origenality — mesures de contrôle rejouables sur les données produites.

Chaque sous-commande mesure une propriété que l'audit a mise en cause, sur les
fichiers du dépôt, sans argument implicite : lancée depuis la racine du projet,
elle rend le même chiffre que celui archivé dans `docs/qa/`. Aucun réseau,
bibliothèque standard seule.

    python3 scripts/qa_checks.py isbn
    python3 scripts/qa_checks.py isbn --corpus <autre corpus.jsonl>
    python3 scripts/qa_checks.py abstract-rights
    python3 scripts/qa_checks.py projections
    python3 scripts/qa_checks.py vocabulary
    python3 scripts/qa_checks.py site-codes [--root DIR]
    python3 scripts/qa_checks.py served-pages [--root DIR]
    python3 scripts/qa_checks.py all

Sortie 0 quand la propriété tient, 1 sinon. `isbn` tolère les ISBN séparés par
le garde de tomaison et les nomme au lieu de les taire. `site-codes` et
`served-pages` ne lisent que des fichiers publiés : ils tournent sans corpus
fusionné, dans les deux géométries, et sur l'arbre désigné par `--root` (la
copie que `scripts/deploy_pages.sh` s'apprête à déployer).
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "semantic"))

from merge_dedup import (  # noqa: E402
    ISBN_FIELDS, MAX_ISBN_YEAR_GAP, norm_isbn, text_volume_signature, value_key,
)
from fields import norm_year  # noqa: E402
from tags_io import read_tags  # noqa: E402
from vocabulary_io import AXIS_FILES, load_vocabulary  # noqa: E402

DEFAULT_CORPUS = ROOT / "data" / "merged" / "corpus.jsonl"
DEFAULT_CITATIONS = ROOT / "data" / "derived" / "citations.jsonl"
DEFAULT_WAVES = ROOT / "semantic" / "waves"

# Les axes que le classeur assigne, et le champ de l'enregistrement qui les porte.
ASSIGNED_AXES = {"works": "works", "themes": "themes",
                 "approaches": "approaches", "relevance": "relevance"}


def shown(path: Path) -> str:
    """Chemin relatif à la racine du projet : un chemin de machine n'a rien à
    faire dans une preuve qu'un tiers doit rejouer chez lui."""
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if line:
                yield number, json.loads(line)


def cluster_isbns(record) -> set:
    """Tous les ISBN d'une grappe, y compris ceux relégués dans `conflicts`.

    Ne lire que le champ retenu manquerait les ISBN concurrents des autres
    notices de la grappe, et la mesure serait plus indulgente qu'elle ne doit.
    """
    codes = set()
    values = []
    for field in ISBN_FIELDS:
        values.append(record.get(field))
    for field, entries in (record.get("conflicts") or {}).items():
        if field in ISBN_FIELDS:
            values.extend(entry.get("value") for entry in entries)
    for value in values:
        if value is None:
            continue
        for item in (value if isinstance(value, list) else [value]):
            code = norm_isbn(item)
            if code:
                codes.add(code)
    return codes


def split_reason(clusters) -> str:
    """Pourquoi un même ISBN se retrouve dans plusieurs grappes.

    Deux séparations sont légitimes et se nomment : une tomaison divergente
    (chaque grappe porte son propre numéro de volume), et une réédition (les
    années s'écartent de plus que ce que le lien ISBN tolère — un numéro repris
    quarante ans plus tard ne désigne plus le même livre). Toute autre
    séparation est une sous-fusion, et la mesure doit échouer.
    """
    marks = [entry["volume"] for entry in clusters.values() if entry["volume"]]
    if len(marks) == len(clusters) and len(set(marks)) == len(marks):
        return "tomaison"
    years = sorted(entry["year"] for entry in clusters.values()
                   if entry["year"] is not None)
    if len(years) == len(clusters) and all(
            b - a > MAX_ISBN_YEAR_GAP for a, b in zip(years, years[1:])):
        return "réédition"
    return "non expliquée"


def check_isbn(corpus: Path) -> int:
    by_code = collections.defaultdict(dict)
    for _number, record in read_jsonl(corpus):
        for code in cluster_isbns(record):
            by_code[code][record["origenality_id"]] = {
                "volume": text_volume_signature(record),
                "year": norm_year(record),
                "title": (record.get("title") or "")[:58],
            }

    split = {code: clusters for code, clusters in by_code.items() if len(clusters) > 1}
    by_reason = collections.defaultdict(dict)
    for code, clusters in split.items():
        by_reason[split_reason(clusters)][code] = clusters
    offending = by_reason["non expliquée"]

    print("corpus                                  : %s" % shown(corpus))
    print("ISBN normalisés distincts               : %d" % len(by_code))
    print("ISBN présents dans plusieurs grappes    : %d" % len(split))
    for reason in ("tomaison", "réédition"):
        print("  dont séparés — %-24s : %d" % (reason, len(by_reason[reason])))
        for code, clusters in sorted(by_reason[reason].items()):
            for oid, entry in sorted(clusters.items()):
                print("      %s  %s  %s  tomaison %s  %s"
                      % (code, oid, entry["year"] or "????",
                         entry["volume"] or "()", entry["title"]))
    print("  sous-fusions non expliquées           : %d" % len(offending))
    for code, clusters in sorted(offending.items()):
        for oid, entry in sorted(clusters.items()):
            print("      %s  %s  %s  %s"
                  % (code, oid, entry["year"] or "????", entry["title"]))
    return 1 if offending else 0


def check_abstract_rights(corpus: Path) -> int:
    """Un même résumé sous plusieurs libellés de droits doit porter le conflit."""
    raw = {}
    for path in sorted(glob.glob(str(ROOT / "data" / "raw" / "*" / "records.jsonl"))):
        for _number, record in read_jsonl(Path(path)):
            raw[(record.get("source"), str(record.get("source_id")))] = record

    same_text, recorded, any_conflict = 0, 0, 0
    for _number, cluster in read_jsonl(corpus):
        rows = [raw.get((entry.get("source"), str(entry.get("source_id"))))
                for entry in cluster.get("sources") or []]
        rows = [row for row in rows if row and row.get("abstract")]
        groups = collections.defaultdict(set)
        for row in rows:
            groups[value_key(row["abstract"])].add(value_key(row.get("abstract_rights")))
        carried = bool((cluster.get("conflicts") or {}).get("abstract_rights"))
        if carried:
            any_conflict += 1
        if any(len(values) > 1 for values in groups.values()):
            same_text += 1
            if carried:
                recorded += 1

    print("corpus                                            : %s" % shown(corpus))
    print("grappes où UN MÊME texte porte plusieurs droits    : %d" % same_text)
    print("  dont conflicts.abstract_rights enregistré        : %d" % recorded)
    print("grappes portant conflicts.abstract_rights (toutes) : %d" % any_conflict)
    return 0 if same_text == recorded else 1


def check_projections(citations: Path, corpus: Path) -> int:
    """Les reports de compte par titre, chacun réinstruit sur le corpus.

    Imprimer les reports n'était pas les contrôler : la fonction rendait zéro
    quoi qu'elle affiche, et un report erroné entrait sans faire échouer la QA.
    Elle refait ici le raisonnement du report, à partir du corpus : pour chaque
    grappe qui a reçu un compte, on retrouve la clé de report (titre replié +
    patronyme du premier auteur + type), on cherche les grappes MESURÉES qui
    portent la même clé, et on vérifie deux choses — même type déclaré, et écart
    d'années dans la limite du type (zéro pour une pièce de périodique, un an
    pour un livre). Un report sans donneur retrouvable est une anomalie au même
    titre : la sortie est non nulle.
    """
    from enrich_citations import (  # noqa: E402  (import tardif : dépend de ROOT)
        DEFAULT_YEAR_GAP, YEAR_GAP_BY_TYPE, fold_title, projection_key,
    )
    from fields import norm_type  # noqa: E402

    rows = {row["origenality_id"]: row for _number, row in read_jsonl(citations)}
    projected = [row for row in rows.values()
                 if row.get("count_method") == "title-projection"]

    keys, years, types = {}, {}, {}
    for _number, cluster in read_jsonl(corpus):
        oid = cluster.get("origenality_id")
        doc_type = norm_type(cluster)
        key = projection_key(cluster, fold_title(cluster.get("title")), doc_type)
        if key is not None:
            keys[oid] = key
        years[oid] = norm_year(cluster)
        types[oid] = doc_type

    donors = collections.defaultdict(list)
    for oid, key in keys.items():
        row = rows.get(oid)
        if row and row.get("count_method") == "cluster" and row.get("measured"):
            donors[key].append(oid)

    print("table de citations              : %s" % shown(citations))
    print("corpus                          : %s" % shown(corpus))
    print("reports par titre               : %d" % len(projected))

    problems = []
    for row in sorted(projected, key=lambda r: r["origenality_id"]):
        oid = row["origenality_id"]
        key = keys.get(oid)
        candidates = donors.get(key, []) if key else []
        gap_max = YEAR_GAP_BY_TYPE.get(types.get(oid), DEFAULT_YEAR_GAP)
        gaps = [abs(years[oid] - years[donor])
                for donor in candidates
                if isinstance(years.get(oid), int) and isinstance(years.get(donor), int)]
        best = min(gaps) if gaps else None
        print("   %s  %s  compte %s  rang %s  donneurs %d  écart %s (max %d)"
              % (oid, row["cohort"], row["cited_by_count"], row["cohort_rank"],
                 len(candidates), "n/d" if best is None else best, gap_max))
        if not candidates:
            problems.append("%s : aucun donneur mesuré ne porte sa clé de report" % oid)
            continue
        if any(types.get(donor) != types.get(oid) for donor in candidates):
            problems.append("%s : un donneur n'a pas le même type déclaré" % oid)
        if best is None:
            problems.append("%s : année inconnue d'un côté, l'écart n'est pas mesurable" % oid)
        elif best > gap_max:
            problems.append("%s : écart d'années %d, au-delà de %d pour un %s"
                            % (oid, best, gap_max, types.get(oid)))

    serial = [row for row in projected if row["cohort"]["type"] in ("article", "review")]
    print("dont pièces de périodique       : %d "
          "(l'année doit y être exacte, jamais ±1)" % len(serial))
    for line in problems:
        print("   REPORT REFUSÉ  %s" % line)
    print("reports en défaut               : %d" % len(problems))
    return 1 if problems else 0


def retired_values(vocabulary_dir=None) -> dict[str, set]:
    """Valeurs du vocabulaire dont le `status` n'est pas « active ».

    Le champ est déclaré sur chaque valeur des quatre axes mais aucun code du
    classement ne le lit : le rendre au moins mesurable est le minimum, faute
    de quoi retirer une valeur ne serait qu'une note dans un fichier.
    """
    vocab = load_vocabulary(vocabulary_dir)
    out = {}
    for axis in AXIS_FILES:
        table = getattr(vocab, axis)
        out[axis] = {identifier for identifier, entry in table.items()
                     if str(entry.get("status", "active")) != "active"}
    return out


def assigned_values(waves: Path) -> dict[str, collections.Counter]:
    """Ce que les vagues assignent effectivement, axe par axe."""
    counts = {axis: collections.Counter() for axis in ASSIGNED_AXES}
    for path in sorted(glob.glob(str(waves / "*" / "tags.jsonl"))):
        for record in read_tags(path, keep_unidentified=False):
            for axis, field in ASSIGNED_AXES.items():
                value = record.get(field)
                if isinstance(value, list):
                    counts[axis].update(str(v) for v in value)
                elif value is not None:
                    counts[axis][str(value)] += 1
    return counts


def check_vocabulary(waves: Path = DEFAULT_WAVES, vocabulary_dir=None) -> int:
    """Aucune valeur retirée du vocabulaire n'est encore assignée dans les vagues.

    Aujourd'hui toutes les valeurs sont actives et le contrôle ne dit rien. Il
    parlera le jour où l'une passera à `retired` : sans lui, elle resterait
    assignable sans que rien ne le signale, et l'aval — qui, lui, filtre déjà
    sur `status` — la ferait disparaître des écrans sans l'annoncer.
    """
    retired = retired_values(vocabulary_dir)
    counts = assigned_values(Path(waves))
    total_retired = sum(len(v) for v in retired.values())
    print("vagues lues                     : %s" % shown(waves))
    print("valeurs retirées du vocabulaire : %d" % total_retired)
    problems = []
    for axis in sorted(retired):
        for identifier in sorted(retired[axis]):
            used = counts.get(axis, collections.Counter()).get(identifier, 0)
            print("   %-12s %-40s assignée %d fois" % (axis, identifier, used))
            if used:
                problems.append("%s : %s est retirée du vocabulaire et pourtant "
                                "assignée %d fois" % (axis, identifier, used))
    for line in problems:
        print("   VALEUR RETIRÉE ENCORE ASSIGNÉE  %s" % line)
    print("valeurs retirées en usage       : %d" % len(problems))
    return 1 if problems else 0


# ---------------------------------------------------------------------------
# Ce que les pages lisent : codes de langue, poids, pages servies
# ---------------------------------------------------------------------------
LANGS_BLOCK = re.compile(r"\bLANGS\s*=\s*\[(.*?)\]\s*;", re.DOTALL)
LANG_CODE = re.compile(r"""\bcode\s*:\s*['"]([^'"]+)['"]""")
OTHER_LANG = "oth"
LANG_SCREENS = ("explorer.js", "observatory.js")
# Le champ WebGL de la carte tient sa propre table : elle traduit la langue d'une
# notice en emplacement de palette, donc elle décide de la couleur des points.
# Elle est restée en codes MARC après le passage des données en ISO, si bien que
# tout retombait sur « oth » et que la carte se dessinait entièrement en
# graphite. Les deux écrans étaient contrôlés, ce troisième fichier non.
LANG_FIELD = "dust-field.js"
LANG_PAL_BLOCK = re.compile(r"\bLANG_PAL\s*=\s*\{([^}]*)\}")
LANG_PAL_KEY = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*\d+")
COUNTED_RELEVANCE = ("core", "partial")


def site_geometry(root: Path) -> tuple[Path, Path]:
    """(pages, couche de données) dans la géométrie de cet arbre.

    La règle de site/build-c/tools/tree_paths.py : `site/build-c/` et
    `site/data/` dans le dépôt de travail, `site/` et `data/` dans l'arbre
    public.
    """
    pages = root / "site" / "build-c"
    if not (pages / "index.html").is_file():
        pages = root / "site"
    data = root / "site" / "data"
    if not (data / "graph.json").is_file():
        data = root / "data"
    return pages, data


def relative_to(path: Path, root: Path) -> str:
    """Chemin relatif à l'arbre contrôlé, jamais un chemin de machine."""
    return Path(os.path.relpath(path, root)).as_posix()


def page_lang_codes(script: Path) -> list[str] | None:
    """Les codes du tableau LANGS d'un script de page, dans l'ordre de la légende."""
    block = LANGS_BLOCK.search(script.read_text(encoding="utf-8"))
    if not block:
        return None
    return LANG_CODE.findall(block.group(1)) or None


def check_site_codes(root: Path = ROOT) -> int:
    """Les langues que les pages nomment sont celles que les données portent.

    Audit du 13/09 (OR-04) : la carte en ligne nommait ses langues en codes
    MARC (eng, ger, fre) quand graph.json les porte en ISO 639-1 (en, de, fr).
    Chaque langue de la légende comptait zéro notice, tout tombait dans
    « autre », chaque requête lang: répondait « rien », et aucun contrôle ne
    comparait les deux fichiers. Celui-ci échoue quand une langue nommée par
    l'Explorer ou l'Observatoire ne compte aucune notice de la population
    comptée (core + partial, la règle de toutes les pages), quand plus de la
    moitié de cette population tombe hors des langues nommées, quand les deux
    écrans ne nomment pas les mêmes langues, et quand les identifiants de
    weights.json ne sont pas ceux des notices du graphe (la jointure de
    l'Explorer se fait sur `ppn`).
    """
    pages, data = site_geometry(root)
    graph_path = data / "graph.json"
    semantic_path = pages / "assets" / "semantic.json"
    weights_path = pages / "assets" / "weights.json"
    problems = ["%s absent" % relative_to(path, root)
                for path in (graph_path, semantic_path, weights_path) if not path.is_file()]
    if problems:
        for line in problems:
            print("   CODES EN DÉFAUT  %s" % line)
        print("codes et identifiants en défaut : %d" % len(problems))
        return 1

    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    tags = json.loads(semantic_path.read_text(encoding="utf-8")).get("byPpn") or {}
    records = [node for node in graph.get("nodes") or [] if node.get("k") == "pub"]
    counted = [node for node in records if node.get("ppn")
               and (tags.get(node["ppn"]) or {}).get("r") in COUNTED_RELEVANCE]
    languages = collections.Counter(str(node.get("lang") or "") for node in counted)
    print("couche de données                : %s" % relative_to(graph_path, root))
    print("notices comptées (core, partial) : %d sur %d" % (len(counted), len(records)))
    print("codes les plus portés            : %s" % ", ".join(
        "%s %d" % (code or "(vide)", number) for code, number in languages.most_common(8)))

    named_by_screen: dict[str, list[str]] = {}
    for name in LANG_SCREENS:
        script = pages / "assets" / name
        shown_script = relative_to(script, root)
        if not script.is_file():
            problems.append("%s absent" % shown_script)
            continue
        codes = page_lang_codes(script)
        if not codes:
            problems.append("%s : aucun tableau LANGS lisible" % shown_script)
            continue
        named = [code for code in codes if code != OTHER_LANG]
        named_by_screen[name] = named
        other = sum(number for code, number in languages.items() if code not in named)
        print("%-33s: %s, hors légende %d" % (shown_script, ", ".join(
            "%s %d" % (code, languages.get(code, 0)) for code in named), other))
        for code in named:
            if not languages.get(code):
                problems.append("%s : la langue « %s » ne compte aucune notice comptée"
                                % (shown_script, code))
        if counted and other * 2 > len(counted):
            problems.append("%s : %d notices comptées sur %d tombent hors des langues nommées"
                            % (shown_script, other, len(counted)))
    if (len(named_by_screen) == len(LANG_SCREENS)
            and len({frozenset(codes) for codes in named_by_screen.values()}) > 1):
        problems.append("l'Explorer et l'Observatoire ne nomment pas les mêmes langues : %s"
                        % " ; ".join("%s %s" % (name, ",".join(codes))
                                     for name, codes in named_by_screen.items()))

    field = pages / "assets" / LANG_FIELD
    legend = named_by_screen.get("explorer.js")
    if not field.is_file():
        problems.append("%s absent" % relative_to(field, root))
    else:
        shown_field = relative_to(field, root)
        block = LANG_PAL_BLOCK.search(field.read_text(encoding="utf-8"))
        if not block:
            problems.append("%s : aucune table LANG_PAL lisible" % shown_field)
        else:
            keys = LANG_PAL_KEY.findall(block.group(1))
            named_field = [code for code in keys if code != OTHER_LANG]
            print("%-33s: %s, hors légende %d" % (shown_field, ", ".join(
                "%s %d" % (code, languages.get(code, 0)) for code in named_field),
                sum(number for code, number in languages.items() if code not in named_field)))
            for code in named_field:
                if not languages.get(code):
                    problems.append("%s : la couleur « %s » ne couvre aucune notice comptée"
                                    % (shown_field, code))
            if legend is not None and set(named_field) != set(legend):
                problems.append("%s : la palette du champ ne nomme pas les langues de la "
                                "légende (champ %s ; légende %s)"
                                % (shown_field, ",".join(sorted(named_field)),
                                   ",".join(sorted(legend))))
            if OTHER_LANG not in keys:
                problems.append("%s : la palette n'a pas d'emplacement « %s », donc une "
                                "langue inconnue n'a pas de couleur de repli"
                                % (shown_field, OTHER_LANG))

    weights = json.loads(weights_path.read_text(encoding="utf-8"))
    weighted = set((weights.get("w") or {}).keys())
    identifiers = {node["ppn"] for node in records if node.get("ppn")}
    missing, unknown = sorted(identifiers - weighted), sorted(weighted - identifiers)
    print("%-33s: %d identifiants pour %d notices au graphe, %d sans poids, %d inconnus"
          % (relative_to(weights_path, root), len(weighted), len(identifiers),
             len(missing), len(unknown)))
    if missing or unknown:
        problems.append("%s : identifiants différents du graphe (sans poids : %d, ex. %s ; "
                        "inconnus du graphe : %d, ex. %s)"
                        % (relative_to(weights_path, root), len(missing),
                           ", ".join(missing[:3]) or "aucun", len(unknown),
                           ", ".join(unknown[:3]) or "aucun"))
    total = weights.get("total")
    if total is not None and total != len(records):
        problems.append("%s : total %s, le graphe porte %d notices"
                        % (relative_to(weights_path, root), total, len(records)))

    for line in problems:
        print("   CODES EN DÉFAUT  %s" % line)
    print("codes et identifiants en défaut : %d" % len(problems))
    return 1 if problems else 0


class PageAudit(HTMLParser):
    """Scripts, gestionnaires d'événements et références d'une page HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts: list[tuple[int, dict, str]] = []
        self.handlers: list[tuple[int, str, str]] = []
        self.references: list[tuple[int, str, str]] = []
        self.meta: list[dict] = []
        self.links: list[dict] = []
        self._script: list | None = None

    def handle_starttag(self, tag, attrs):
        line = self.getpos()[0]
        values = {name: value or "" for name, value in attrs}
        for name, value in values.items():
            if name.startswith("on"):
                self.handlers.append((line, tag, name))
            elif name in ("href", "src", "action") and value.strip().lower().startswith("javascript:"):
                self.handlers.append((line, tag, name))
            if name in ("href", "src") and value:
                self.references.append((line, tag, value))
        if tag == "meta":
            self.meta.append(values)
        elif tag == "link":
            self.links.append(values)
        elif tag == "script":
            self._script = [line, values, ""]

    def handle_data(self, data):
        if self._script is not None:
            self._script[2] += data

    def handle_endtag(self, tag):
        if tag == "script" and self._script is not None:
            self.scripts.append((self._script[0], self._script[1], self._script[2]))
            self._script = None


def check_served_pages(root: Path = ROOT) -> int:
    """Les pages tiennent sous la politique du site, et une adresse inconnue répond 404.

    La politique de `_headers` est `script-src 'self'` : un script en ligne ou un
    gestionnaire `on…=` y est bloqué, et le navigateur l'écrit en erreur de
    console. La page racine redirigeait par un script en ligne que la politique
    bloquait (audit du 13/09, OR-33). Sans `404.html` à la racine du
    déploiement, Cloudflare Pages sert `index.html` en 200 pour toute adresse
    absente, fichiers JSON de /data/ compris (OR-33, OR-42). Le contrôle échoue
    sur un script en ligne autre qu'un bloc de données JSON-LD, sur un
    gestionnaire d'événement ou une URL javascript:, sur un `404.html` absent,
    indexable ou canonisé, et sur un `404.html` qui adresse un fichier en
    relatif alors qu'il est servi à toutes les profondeurs.
    """
    pages, _data = site_geometry(root)
    documents = sorted(root.glob("*.html")) + sorted(pages.glob("*.html"))
    documents = [page for page in documents if not re.search(r" \d+\.html$", page.name)]
    problems = []
    not_found = root / "404.html"
    if not not_found.is_file():
        problems.append("404.html absent à la racine : Pages servirait index.html en 200 "
                        "pour toute adresse inconnue")
    for page in documents:
        audit = PageAudit()
        audit.feed(page.read_text(encoding="utf-8"))
        audit.close()
        shown_page = relative_to(page, root)
        for line, attributes, body in audit.scripts:
            if attributes.get("src"):
                if body.strip():
                    problems.append("%s:%d : script à la fois externe et en ligne" % (shown_page, line))
                continue
            if attributes.get("type", "").strip().lower() == "application/ld+json":
                continue
            problems.append("%s:%d : script en ligne, bloqué par script-src 'self'"
                            % (shown_page, line))
        for line, tag, name in audit.handlers:
            problems.append("%s:%d : <%s %s> exécute du code dans le balisage"
                            % (shown_page, line, tag, name))
        if page == not_found:
            robots = " ".join(meta.get("content", "") for meta in audit.meta
                              if meta.get("name", "").lower() == "robots")
            if "noindex" not in robots:
                problems.append("%s : pas de <meta name=\"robots\" content=\"noindex\">" % shown_page)
            if any("canonical" in link.get("rel", "").lower().split() for link in audit.links):
                problems.append("%s : une page d'erreur ne porte pas d'adresse canonique" % shown_page)
            for line, tag, value in audit.references:
                if not value.startswith(("/", "#", "https://", "http://", "mailto:", "data:")):
                    problems.append("%s:%d : « %s » est relatif, et la page est servie à toutes "
                                    "les profondeurs" % (shown_page, line, value))
    print("pages lues                      : %d (racine et %s)"
          % (len(documents), relative_to(pages, root)))
    print("404.html à la racine            : %s" % ("présent" if not_found.is_file() else "absent"))
    for line in problems:
        print("   PAGE EN DÉFAUT  %s" % line)
    print("pages en défaut                 : %d" % len(problems))
    return 1 if problems else 0


def main(argv):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("check", choices=("isbn", "abstract-rights", "projections",
                                         "vocabulary", "site-codes", "served-pages", "all"))
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--citations", type=Path, default=DEFAULT_CITATIONS)
    parser.add_argument("--waves", type=Path, default=DEFAULT_WAVES)
    parser.add_argument("--root", type=Path, default=ROOT,
                        help="arbre lu par site-codes et served-pages (défaut : ce dépôt)")
    arguments = parser.parse_args(argv)
    root = arguments.root.resolve()

    # Le contrôle du vocabulaire ne lit que des fichiers publiés : il tourne
    # dans un clone, corpus fusionné ou non, et n'a donc pas à passer le garde
    # qui suit.
    if arguments.check == "vocabulary":
        return check_vocabulary(arguments.waves)
    # Les contrôles du site ne lisent que des fichiers publiés, eux aussi.
    if arguments.check == "site-codes":
        return check_site_codes(root)
    if arguments.check == "served-pages":
        return check_served_pages(root)
    site_status = 0
    if arguments.check == "all":
        site_status |= check_site_codes(root)
        print()
        site_status |= check_served_pages(root)
        print()

    # Ces mesures portent sur le corpus fusionné, qui n'est pas dans le dépôt
    # public : il est volumineux et plusieurs bases demandent que leur dump ne
    # soit pas redistribué. Un clone qui lance la commande doit lire une phrase,
    # pas une trace d'appels sur un fichier absent.
    if not arguments.corpus.exists():
        print("corpus fusionné absent : %s" % shown(arguments.corpus), file=sys.stderr)
        print("Les moissons brutes et le corpus fusionné ne sont pas publiés. Les "
              "reconstruire avec les moissonneurs de scripts/, puis "
              "pipeline/merge_dedup.py --out-dir data/merged.", file=sys.stderr)
        return 1

    status = site_status
    if arguments.check in ("isbn", "all"):
        status |= check_isbn(arguments.corpus)
    if arguments.check in ("abstract-rights", "all"):
        if arguments.check == "all":
            print()
        status |= check_abstract_rights(arguments.corpus)
    if arguments.check in ("projections", "all"):
        if arguments.check == "all":
            print()
        status |= check_projections(arguments.citations, arguments.corpus)
    if arguments.check == "all":
        print()
        status |= check_vocabulary(arguments.waves)
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
