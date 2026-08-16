#!/usr/bin/env python3
"""Origenality — contrôle de publication des résumés.

Les résumés sont publiés ; ce qu'un dump doit garantir, c'est que chacun dise
d'où il vient. Le contrôle ne juge donc plus les droits déclarés par la source :
il vérifie l'attribution. La table des bases créditées n'est pas ici, elle est
dans `DATA_POLICY.md`, dans un bloc JSON balisé, et ce script la lit. Une seule
source de vérité, lisible par un juriste comme par une machine.

Le contrôle refuse trois choses, et seulement trois :

* un `abstract` dont on ne sait pas de quelle base il provient ;
* un `abstract` dont la base d'origine ne figure pas dans la table
  d'attribution — faute d'y figurer, elle n'a ni nom à afficher ni lien vers
  la notice source ;
* un `abstract` dont l'attribution ne se résout pas en LIEN. Un nom de base est
  un crédit typographique, pas une attribution : le lecteur doit pouvoir
  remonter à la notice qui a écrit le résumé. Il faut donc soit `abstract_url`
  — l'adresse de la notice donatrice, recopiée par la fusion depuis cette
  notice et non depuis une autre base de la même grappe —, soit un identifiant
  que le gabarit d'URL de la base transforme en adresse.

Un `abstract` livré sous forme de liste (certaines bases rendent le résumé
découpé en paragraphes) est un résumé comme un autre : il est joint et contrôlé,
au lieu d'être pris pour une absence. La clé se lit quelle qu'en soit la casse.

`abstract_rights` reste relevé et compté : il ne décide de rien, il sert à
retrouver vite les résumés d'un fonds le jour où il faut les retirer.

Sortie : 0 quand le dump est attribuable, 2 quand il ne l'est pas, 3 sur une
erreur d'entrée. `--strip` n'est jamais appliqué d'office ; avec `--withdraw`,
il exécute une demande de retrait.

    python3 scripts/check_release.py data/release/corpus_public.jsonl
    python3 scripts/check_release.py data/merged/corpus.jsonl --sample 3000
    python3 scripts/check_release.py data/merged/corpus.jsonl \
        --withdraw persee --strip out.jsonl
"""
from __future__ import annotations

import argparse
import collections
import ipaddress
import json
import random
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# La politique de données porte le même nom dans les deux arbres. Elle
# s'appelait `DATA_LICENSE.md` dans le dépôt de travail et `DATA_POLICY.md` une
# fois publiée : le renommage à l'export laissait le document public introuvable
# pour tout ce qui le citait par son nom de travail. Un seul nom, celui qui dit
# ce que le document est — aucune licence unique n'est affirmée sur des
# métadonnées venues de dix bases.
DEFAULT_POLICY = ROOT / "DATA_POLICY.md"
FENCE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


class PolicyError(RuntimeError):
    pass


def load_policy(path: Path) -> dict:
    """Le premier bloc ```json de DATA_POLICY.md qui porte une clé `attribution`."""
    text = path.read_text(encoding="utf-8")
    for block in FENCE.findall(text):
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError as exc:
            raise PolicyError(f"bloc JSON illisible dans {path.name} : {exc}") from exc
        if isinstance(parsed, dict) and "attribution" in parsed:
            for key, entry in parsed["attribution"].items():
                if not isinstance(entry, dict) or not entry.get("label"):
                    raise PolicyError(f"base sans libellé d'attribution : {key}")
                # Une base dont l'identifiant EST l'adresse doit dire à quels
                # hôtes cette adresse a le droit d'appartenir : sans liste, la
                # table autorise n'importe quel domaine à porter son nom.
                template = (entry.get("url_template") or "").strip()
                if template == "{id}" and not entry.get("hosts"):
                    raise PolicyError(
                        f"base « {key} » : gabarit {{id}} sans liste d'hôtes autorisés")
            return parsed
    raise PolicyError(f"aucune table d'attribution trouvée dans {path}")


def abstract_source(record) -> str | None:
    """La base d'où vient le résumé, du plus explicite au plus déductible.

    Un dump destiné à la publication porte `abstract_source`, écrit par le
    pipeline. Un corpus fédéré porte la provenance par champ. Une moisson à
    source unique n'a que son champ `source`, qui suffit. Au-delà, on ne
    devine pas : une notice fusionnée depuis plusieurs bases sans provenance
    de résumé n'est pas attribuable, et c'est bien ce qu'il faut dire.
    """
    explicit = record.get("abstract_source")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    provenance = record.get("provenance")
    if isinstance(provenance, dict):
        entry = provenance.get("abstract")
        if isinstance(entry, dict) and isinstance(entry.get("source"), str):
            if entry["source"].strip():
                return entry["source"].strip()
    single = record.get("source")
    if isinstance(single, str) and single.strip():
        return single.strip()
    sources = record.get("sources")
    if isinstance(sources, list):
        names = {
            (entry.get("source") if isinstance(entry, dict) else entry)
            for entry in sources
        }
        names = {n for n in names if isinstance(n, str) and n.strip()}
        if len(names) == 1:
            return names.pop()
    return None


def field(record, name):
    """Valeur d'un champ, la casse de la clé n'important pas.

    Un dump réexporté par un tableur ou par une autre chaîne rend parfois
    `Abstract` au lieu de `abstract`. Lire strictement faisait passer la notice
    pour dépourvue de résumé, donc hors contrôle : la clé est cherchée telle
    quelle d'abord, puis à la casse près.
    """
    if name in record:
        return record[name]
    lowered = name.lower()
    for key, value in record.items():
        if isinstance(key, str) and key.lower() == lowered:
            return value
    return None


def abstract_text(record):
    """Texte du résumé, qu'il vienne en chaîne ou en liste de paragraphes.

    Une liste de chaînes EST un résumé : la traiter comme une absence sortait la
    notice du contrôle au lieu de la lui soumettre. Les éléments sont joints par
    un saut de paragraphe ; tout le reste (nombre, objet, liste vide) n'est pas
    un résumé.
    """
    value = field(record, "abstract")
    if isinstance(value, str):
        return value if value.strip() else None
    if isinstance(value, list):
        parts = [item.strip() for item in value
                 if isinstance(item, str) and item.strip()]
        return "\n\n".join(parts) if parts else None
    return None


def abstract_identifier(record, source):
    """Identifiant de la notice qui a écrit le résumé, dans SA base.

    La provenance par champ le dit sur un corpus fusionné ; une moisson à source
    unique n'a que son `source_id`. On ne prend le `source_id` d'une grappe
    multi-sources que si la provenance du résumé désigne la même base : sinon
    l'identifiant appartient à une autre notice et le lien construit avec lui
    pointerait à côté.
    """
    provenance = record.get("provenance")
    if isinstance(provenance, dict):
        entry = provenance.get("abstract")
        if isinstance(entry, dict) and entry.get("source") == source:
            value = entry.get("source_id")
            if value not in (None, ""):
                return str(value)
    if record.get("source") == source or not isinstance(provenance, dict):
        value = record.get("source_id")
        if value not in (None, ""):
            return str(value)
    return None


LOCAL_HOSTS = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}
HOST_LABEL = re.compile(r"^[a-z0-9¡-￿]([a-z0-9¡-￿-]{0,61}[a-z0-9¡-￿])?$")


def _fully_unquoted(text: str, rounds: int = 5) -> str:
    """Le texte décodé jusqu'au point fixe : `%252E` cache un `%2E` cache un `.`.

    Trois tours suffisaient au cas de l'audit 5 et pas au suivant :
    `%2525252E` demande quatre décodages avant de rendre son point, et l'audit 6
    l'a construit. La boucle va donc jusqu'au point fixe — un texte qui ne bouge
    plus est décodé —, avec une borne de cinq tours qui empêche une chaîne
    fabriquée pour ne jamais converger d'occuper la machine.
    """
    for _ in range(rounds):
        decoded = urllib.parse.unquote(text)
        if decoded == text:
            break
        text = decoded
    return text


def _is_local_host(host: str) -> bool:
    """Boucle locale, réseau privé, lien-local : une adresse qui ne publie rien."""
    if host in LOCAL_HOSTS or host.endswith(".localhost") or host.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (address.is_loopback or address.is_private or address.is_link_local
            or address.is_reserved or address.is_unspecified)


def is_resolvable_url(value) -> bool:
    """L'adresse est-elle une adresse ?

    « Commence par http » n'est pas une validation : `http-not-a-url` la passait,
    et `http://` aussi. Une attribution n'est résoluble que si elle donne un
    schéma http(s), un hôte qui ressemble à un nom de domaine — un point au
    moins, pas d'espace —, et un chemin qui ne remonte pas l'arborescence.

    L'audit 5 a montré que cela ne suffisait pas : `https://user:pass@example.com/x`
    affiche un hôte et en atteint un autre selon le client, `https://example.com\\@evil.example/x`
    aussi, `https://example.com:99999/x` n'a pas de port, `http://127.0.0.1/x` ne
    publie rien, et `%252E%252E` remonte l'arborescence au deuxième décodage.
    Cinq refus de plus, donc : userinfo, antislash, port hors 1-65535, hôte local
    ou privé, et traversée de chemin décodée jusqu'au point fixe.
    """
    if not isinstance(value, str):
        return False
    value = value.strip()
    if not value or any(c.isspace() for c in value):
        return False
    # Le décodage vient AVANT le refus : un antislash ou un « .. » qui n'apparaît
    # qu'au troisième décodage remonte l'arborescence aussi bien qu'un autre.
    if "\\" in _fully_unquoted(value):
        return False
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if "@" in parsed.netloc:
        return False
    try:
        port = parsed.port
    except ValueError:
        return False
    if port is not None and not 1 <= port <= 65535:
        return False
    host = (parsed.hostname or "").lower()
    if not host or _is_local_host(host):
        return False
    if "." not in host or host.startswith(".") or host.endswith("."):
        return False
    if not all(HOST_LABEL.match(label) for label in host.split(".")):
        return False
    decoded = _fully_unquoted(parsed.path)
    if ".." in decoded or "\\" in decoded:
        return False
    return True


def host_of(url: str) -> str:
    """Hôte d'une adresse déjà validée, en minuscules."""
    return (urllib.parse.urlsplit(url).hostname or "").lower()


def host_allowed(url: str, hosts) -> bool:
    """L'hôte figure-t-il dans la liste d'hôtes déclarée par la base ?

    Un sous-domaine d'un hôte déclaré passe (`api.openalex.org` pour
    `openalex.org`) ; rien d'autre. Une liste vide ou absente n'autorise rien :
    la fonction n'est appelée que là où la politique en exige une.
    """
    if not hosts:
        return False
    host = host_of(url)
    return any(host == entry.lower() or host.endswith("." + entry.lower())
               for entry in hosts)


def is_safe_identifier(value) -> bool:
    """Un identifiant de notice ne remonte pas l'arborescence et n'est pas vide.

    Interpolé dans un gabarit d'URL, `../../not-a-record` fabriquait une adresse
    syntaxiquement valide qui ne mène nulle part — et qui, sur un serveur
    complaisant, mène ailleurs.

    Le refus littéral de `..` et de `%2e%2e` laissait passer l'encodage répété :
    `%2525252E%2525252E` ne montre son « .. » qu'au quatrième décodage, et le
    gabarit, lui, le rendait au serveur. L'identifiant est donc décodé jusqu'au
    point fixe avant d'être jugé, sur la forme brute comme sur la forme décodée.
    """
    if value in (None, ""):
        return False
    text = str(value).strip()
    if not text or any(c.isspace() for c in text):
        return False
    decoded = _fully_unquoted(text)
    if any(c.isspace() for c in decoded):
        return False
    for form in (text, decoded):
        lowered = form.lower()
        if ".." in form or "\\" in form:
            return False
        if form.startswith("/") or lowered.startswith(("javascript:", "data:", "file:")):
            return False
    return True


def looks_like_a_url(value) -> bool:
    """L'identifiant est-il lui-même une adresse ? (le cas OpenAlex)."""
    return isinstance(value, str) and value.strip().lower().startswith(("http://", "https://"))


def attribution_link(record, source, entry):
    """Adresse à laquelle le crédit renvoie, ou None si l'on n'en a aucune."""
    explicit = field(record, "abstract_url")
    if is_resolvable_url(explicit):
        return explicit.strip()
    template = entry.get("url_template")
    if not template:
        return None
    identifier = abstract_identifier(record, source)
    if not is_safe_identifier(identifier):
        return None
    identifier = str(identifier).strip()
    if template.strip() == "{id}":
        # Une base dont l'identifiant EST l'adresse (OpenAlex). Le gabarit ne
        # préfixe rien : l'identifiant doit alors satisfaire seul le contrôle
        # d'adresse — et, depuis l'audit 5, l'hôte doit figurer dans la liste
        # que la base déclare dans la table d'attribution. Sans cette liste, un
        # donneur `openalex` porteur d'une adresse quelconque faisait attribuer
        # son résumé à OpenAlex sur un domaine tiers. Pas de liste, pas de lien.
        if not is_resolvable_url(identifier) or not host_allowed(identifier, entry.get("hosts")):
            return None
        link = identifier
    elif looks_like_a_url(identifier):
        # Une adresse complète glissée dans un gabarit qui en préfixe une autre
        # produit une chimère (« https://ixtheo.de/Record/https://… ») : on
        # préfère n'avoir pas de lien plutôt qu'un lien faux.
        return None
    else:
        link = template.replace("{id}", urllib.parse.quote(identifier, safe="/:@"))
    return link if is_resolvable_url(link) else None


def decide(record, policy):
    """Décision d'attribution pour une notice porteuse d'un résumé.

    Renvoie (statut, base, lien). Quatre statuts : `attributed` quand la base
    est nommée dans la table ET que son crédit se résout en lien,
    `unresolvable` quand la base est nommée mais qu'aucun lien ne mène à la
    notice d'origine, `unknown_source` quand la base est absente de la table,
    `no_source` quand la notice ne dit pas d'où vient son résumé.
    """
    source = abstract_source(record)
    if not source:
        return "no_source", None, None
    entry = policy["attribution"].get(source)
    if entry is None:
        return "unknown_source", source, None
    link = attribution_link(record, source, entry)
    if not link:
        return "unresolvable", source, None
    return "attributed", source, link


def read_records(path: Path):
    """JSONL de préférence ; un tableau JSON est accepté."""
    with path.open(encoding="utf-8") as handle:
        head = handle.read(1)
        handle.seek(0)
        if head == "[":
            for record in json.load(handle):
                yield record
            return
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise PolicyError(f"ligne {number} illisible : {exc}") from exc


def identifier(record):
    for key in ("origenality_id", "source_id", "doi", "title"):
        value = record.get(key)
        if value:
            return str(value)[:80]
    return "?"


def check(path, policy, sample, strip_path, max_report, withdraw=None):
    records = list(read_records(path))
    if sample and sample < len(records):
        records = random.Random(42).sample(records, sample)

    pattern = re.compile(withdraw, re.IGNORECASE) if withdraw else None

    counts = collections.Counter()
    by_source = collections.Counter()
    by_rights = collections.Counter()
    violations = []
    withdrawn = 0
    output = strip_path.open("w", encoding="utf-8") if strip_path else None

    reasons = {
        "no_source": "aucune base d'origine pour ce résumé",
        "unknown_source": "base « {source} » absente de la table d'attribution",
        "unresolvable": ("crédit « {source} » sans lien vers la notice d'origine : "
                         "ni abstract_url ni identifiant résoluble"),
    }

    for record in records:
        abstract = abstract_text(record)
        rights = field(record, "abstract_rights")

        if not abstract:
            counts["no_abstract"] += 1
            if output:
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
            continue

        status, source, _link = decide(record, policy)
        counts[f"abstract_{status}"] += 1
        by_source[source or "(indéterminée)"] += 1
        by_rights[str(rights)[:90] if rights else "(absent)"] += 1
        if not rights:
            counts["rights_unrecorded"] += 1

        if status != "attributed":
            violations.append({"id": identifier(record), "source": source,
                               "reason": reasons[status].format(source=source)})

        asked = pattern and (
            pattern.search(source or "") or pattern.search(str(rights or ""))
        )
        if output and asked:
            cleaned = dict(record)
            for key in [k for k in cleaned if isinstance(k, str) and k.lower() == "abstract"]:
                cleaned.pop(key, None)
            cleaned["abstract_withheld"] = f"retrait demandé ({withdraw})"
            output.write(json.dumps(cleaned, ensure_ascii=False) + "\n")
            withdrawn += 1
        elif output:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")

    if output:
        output.close()

    report = {
        "dump": str(path),
        "policy": policy.get("policy_version"),
        "regime": policy.get("regime"),
        "records": len(records),
        "sampled": bool(sample),
        "abstracts": sum(v for k, v in counts.items() if k.startswith("abstract_")),
        "attributed": counts.get("abstract_attributed", 0),
        "unknown_source": counts.get("abstract_unknown_source", 0),
        "unresolvable": counts.get("abstract_unresolvable", 0),
        "no_source": counts.get("abstract_no_source", 0),
        "rights_unrecorded": counts.get("rights_unrecorded", 0),
        "violations": len(violations),
        "withdrawn": withdrawn,
        "by_source": dict(by_source.most_common(20)),
        "by_rights": dict(by_rights.most_common(20)),
        "examples": violations[:max_report],
    }
    return report


def main(argv):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("dump", type=Path)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--sample", type=int, default=0, help="contrôler un échantillon tiré à graine fixe")
    parser.add_argument("--strip", type=Path, help="écrire une copie du dump (facultatif)")
    parser.add_argument("--withdraw", help="expression régulière : base d'origine ou droits dont les résumés sont retirés de la copie")
    parser.add_argument("--report", type=Path, help="écrire le rapport en JSON")
    parser.add_argument("--max-examples", type=int, default=10)
    arguments = parser.parse_args(argv)

    if arguments.withdraw and not arguments.strip:
        print("erreur : --withdraw demande --strip, faute de quoi rien n'est écrit", file=sys.stderr)
        return 3

    try:
        policy = load_policy(arguments.policy)
        report = check(
            arguments.dump,
            policy,
            arguments.sample,
            arguments.strip,
            arguments.max_examples,
            arguments.withdraw,
        )
    except (PolicyError, OSError) as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 3

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if arguments.report:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    if arguments.strip:
        print(
            f"copie écrite : {arguments.strip} ({report['withdrawn']:,} résumés retirés)",
            file=sys.stderr,
        )
    if report["violations"]:
        print(
            f"REFUS : {report['violations']:,} résumés sans attribution résoluble",
            file=sys.stderr,
        )
        return 2
    print("dump attribuable", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
