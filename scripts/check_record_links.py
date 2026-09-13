#!/usr/bin/env python3
"""Origenality — les liens de notice répondent-ils encore ? (réseau, hors CI)

Chaque notice de la carte renvoie à la base qui la détient, sous le gabarit
d'adresse que la table d'attribution de `DATA_POLICY.md` déclare pour cette
base. Un gabarit faux ne se voit pas dans les données : l'audit du 13 septembre
a trouvé les 354 notices de la Gnomon et les 130 notices de B3Kat derrière des
adresses qui rendaient 404 ou n'aboutissaient pas. Ce contrôle en demande un
échantillon, source par source, aux services eux-mêmes.

Il lit `data/graph.json` (les `source_ids` de chaque publication) et
`META.sources_present[].record_url_pattern`, prend au plus N adresses par source
(les premières dans l'ordre du graphe, donc un tirage rejouable), et rapporte par
source les adresses qui ne rendent pas une page : statut HTTP hors 2xx, délai
dépassé, ou page d'erreur servie en 200. Il vérifie aussi qu'un lien de notice
suit le gabarit déclaré pour sa source (hors DOI).

Politesse : une requête par seconde au plus par hôte, en série, User-Agent
nominatif avec l'adresse de contact ; GET (plusieurs catalogues refusent HEAD).
Il touche le réseau : il ne tourne pas en CI. Il fait partie de la procédure de
publication (README, § « Reproducing it »), avant `scripts/check_release.py`.

    python3 scripts/check_record_links.py                 # 5 adresses par source
    python3 scripts/check_record_links.py --sample 2 --source b3kat,gnomon-gbd
    python3 scripts/check_record_links.py --report data/_proofs_tmp/links.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for tools in (ROOT / "site" / "build-c" / "tools", ROOT / "site" / "tools"):
    if tools.is_dir():
        sys.path.insert(0, str(tools))
from tree_paths import data_dir  # noqa: E402

DATA = Path(data_dir(str(ROOT)))
CONTACT = "romain.girardi@univ-cotedazur.fr"
USER_AGENT = "Origenality-record-links/1.0 (academic research; %s)" % CONTACT
INTERVAL = 1.0
TIMEOUT = 90
DOI_HOSTS = {"doi.org", "dx.doi.org"}
# Une page d'erreur servie en 200 : les catalogues le font quand une notice
# n'existe plus. Le motif ne porte que sur le titre de la page.
ERROR_TITLE = re.compile(r"<title>[^<]*(?:not found|nicht gefunden|introuvable|erreur 404"
                         r"|page not found|no record|keine treffer|error)[^<]*</title>",
                         re.IGNORECASE)


class Throttle:
    """Au plus une requête par intervalle, par hôte."""

    def __init__(self, interval: float = INTERVAL, clock=time.monotonic, sleep=time.sleep):
        self.interval, self.clock, self.sleep = interval, clock, sleep
        self.last: dict[str, float] = {}

    def wait(self, host: str) -> None:
        previous = self.last.get(host)
        if previous is not None:
            remaining = self.interval - (self.clock() - previous)
            if remaining > 0:
                self.sleep(remaining)
        self.last[host] = self.clock()


def sample(graph: dict, per_source: int, sources: set | None = None) -> "OrderedDict[str, list]":
    """source -> [(identifiant, adresse)], au plus N par source, dans l'ordre du graphe."""
    picked: "OrderedDict[str, list]" = OrderedDict()
    for node in graph.get("nodes") or []:
        if node.get("k") != "pub":
            continue
        for entry in node.get("source_ids") or []:
            source, url = entry.get("source"), entry.get("url")
            if not source or not url or (sources and source not in sources):
                continue
            bucket = picked.setdefault(source, [])
            if len(bucket) < per_source and all(url != seen for _, seen in bucket):
                bucket.append((str(entry.get("id")), url))
    return picked


def follows_pattern(url: str, identifier: str, pattern: str | None) -> bool:
    """Le lien suit-il le gabarit déclaré ? Un DOI et une base sans gabarit passent."""
    host = urllib.parse.urlsplit(url).hostname or ""
    if host in DOI_HOSTS or not pattern or "{id}" not in pattern:
        return True
    prefix, _, suffix = pattern.partition("{id}")
    return url.startswith(prefix) and url.endswith(suffix)


def probe(url: str, throttle: Throttle, opener=urllib.request.urlopen) -> tuple[bool, str]:
    """(répond, détail)."""
    throttle.wait(urllib.parse.urlsplit(url).hostname or "")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "text/html,*/*"})
    try:
        with opener(request, timeout=TIMEOUT) as response:
            status = getattr(response, "status", 200)
            head = response.read(65536).decode("utf-8", "replace")
            final = response.geturl() if hasattr(response, "geturl") else url
    except urllib.error.HTTPError as error:
        return False, "HTTP %d" % error.code
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
        return False, "network: %s" % str(getattr(error, "reason", error))[:100]
    if not 200 <= status < 300:
        return False, "HTTP %d" % status
    if ERROR_TITLE.search(head):
        return False, "HTTP %d, error page" % status
    moved = "" if final == url else ", via %s" % urllib.parse.urlsplit(final).hostname
    return True, "HTTP %d%s" % (status, moved)


def main(argv=None, opener=urllib.request.urlopen, throttle: Throttle | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", type=int, default=5, help="adresses par source (défaut 5)")
    parser.add_argument("--source", default=None, help="sources, séparées par des virgules")
    parser.add_argument("--graph", type=Path, default=DATA / "graph.json")
    parser.add_argument("--meta", type=Path, default=DATA / "META.json")
    parser.add_argument("--report", type=Path, default=None, help="rapport JSON")
    args = parser.parse_args(argv)

    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    meta = json.loads(args.meta.read_text(encoding="utf-8"))
    patterns = {entry.get("source"): entry.get("record_url_pattern")
                for entry in meta.get("sources_present") or []}
    wanted = set(args.source.split(",")) if args.source else None
    throttle = throttle or Throttle()

    report: "OrderedDict[str, dict]" = OrderedDict()
    failing = 0
    for source, links in sample(graph, args.sample, wanted).items():
        line = report.setdefault(source, {"pattern": patterns.get(source), "checked": 0,
                                          "resolving": 0, "failing": []})
        for identifier, url in links:
            line["checked"] += 1
            if not follows_pattern(url, identifier, patterns.get(source)):
                line["failing"].append({"id": identifier, "url": url,
                                        "detail": "does not follow the declared pattern"})
                continue
            ok, detail = probe(url, throttle, opener)
            if ok:
                line["resolving"] += 1
            else:
                line["failing"].append({"id": identifier, "url": url, "detail": detail})
        failing += len(line["failing"])
        print("%-16s %d/%d resolve   %s" % (source, line["resolving"], line["checked"],
                                          line["pattern"]))
        for miss in line["failing"]:
            print("   NOT RESOLVING %s:%s  %s  (%s)" % (source, miss["id"], miss["url"],
                                                      miss["detail"]))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                               encoding="utf-8")
    print("record links not resolving: %d" % failing)
    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
