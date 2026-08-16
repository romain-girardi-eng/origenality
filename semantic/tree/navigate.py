"""Navigate the topic index by reasoning over it, with a deterministic fallback.

Given a free description of a research project, the navigator selects the nodes
of the index worth opening and returns the notices they hold:

    {"selected_nodes": [...], "reasoning": "...", "notice_ids": [...]}

Two engines, one contract. The reasoning engine sends the flattened index —
node identifier, title, path, computed summary, tags — and asks which nodes to
open; the endpoint is reached through the neutral adapter. The fallback scores
the same nodes by term overlap between the query and the node's title, path,
summary and tags. The fallback also runs first as a shortlist when the index is
large, so the reasoning engine always sees a bounded payload, and it runs alone
under --no-llm or when a call fails. Selection is therefore never blocked by
the availability of an endpoint.

L'arbre lu par défaut est celui du corpus FÉDÉRÉ, `topic_tree_federated.json`,
c'est-à-dire l'index sur lequel les chiffres publiés sont mesurés. L'audit 3
relevait que le défaut portait sur `topic_tree.json`, l'arbre du pilote IxTheo :
une commande recopiée d'une preuve donnait alors un autre dénominateur, quand
elle ne rendait pas zéro. À défaut d'arbre fédéré sur le disque, le programme
n'en choisit pas un autre en silence : il demande `--tree`.

    python3 semantic/tree/navigate.py --query "Origen's use of Stoic material on free will"
    python3 semantic/tree/navigate.py --query "..." --no-llm --json
    python3 semantic/tree/navigate.py --query "..." --tree semantic/tree/topic_tree.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import llm_adapter  # noqa: E402
from vocabulary_io import fold  # noqa: E402

NAVIGATION_PROMPT = """\
You are navigating a hierarchical index of scholarship on Origen of Alexandria.

Research project: {query}

Candidate nodes of the index:
{nodes_json}

Select the nodes whose notices a researcher on this project must see. Prefer
direct coverage and breadth over narrow redundancy; select a domain node only
when several of its leaves are relevant. Choose at most {max_nodes} nodes.
Select nothing rather than something loosely related.

Return only JSON:
{{"selected_nodes": [{{"node_id": "...", "reason": "...", "priority": 1}}], "reasoning": "..."}}
"""

SELECTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["selected_nodes", "reasoning"],
    "properties": {
        "selected_nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["node_id", "reason", "priority"],
                "properties": {
                    "node_id": {"type": "string"},
                    "reason": {"type": "string"},
                    "priority": {"type": "integer"},
                },
            },
        },
        "reasoning": {"type": "string"},
    },
}

STOPWORDS = {
    "about", "after", "against", "among", "around", "because", "before", "between",
    "could", "during", "every", "从", "from", "have", "into", "notice", "notices",
    "other", "over", "project", "research", "should", "since", "some", "such",
    "than", "that", "their", "them", "then", "there", "these", "they", "this",
    "those", "through", "under", "very", "were", "what", "when", "where", "which",
    "while", "with", "within", "would", "dans", "avec", "pour", "leur", "leurs",
    "cette", "comme", "plus", "sont", "être", "etre", "chez", "sur", "les", "des",
    "und", "der", "die", "das", "von", "mit", "auf", "für", "fur", "eine", "einen",
    # every node of this index is about Origen: the name carries no signal
    "origen", "origene", "origenes", "origenis", "origenian", "origenien",
    "alexandria", "alexandrie", "alessandria",
}

# Default buckets: they hold notices but denote nothing, so they are never
# candidates for selection.
NEUTRAL_NODE_SUFFIXES = (":unspecified", ":none")


def load_tree(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def flatten(document: dict[str, Any], include_domains: bool = True) -> list[dict[str, Any]]:
    """All nodes below the roots, leaves first in document order."""
    flat: list[dict[str, Any]] = []

    def walk(node: dict[str, Any], axis: str, depth: int) -> None:
        if depth > 0 and (include_domains or not node.get("nodes")):
            flat.append(
                {
                    "axis": axis,
                    "depth": depth,
                    "node_id": node["node_id"],
                    "title": node["title"],
                    "path": node.get("path", ""),
                    "summary": node.get("summary", ""),
                    "concept_tags": node.get("concept_tags", []),
                    "entity_tags": node.get("entity_tags", []),
                    "n_notices": node.get("stats", {}).get("n_notices", 0),
                    "notice_ids": node.get("notice_ids", []),
                }
            )
        for child in node.get("nodes", []):
            walk(child, axis, depth + 1)

    for axis in document.get("axes", []):
        walk(axis["root"], axis["axis"], 0)
    return flat


def query_terms(query: str) -> set[str]:
    """Terms of a query, in any script.

    The pattern used to be a Latin range, so a query in Greek or in Cyrillic
    produced no term at all — and an empty term set matched everything. `\\w`
    with the Unicode default covers the scripts this bibliography actually
    carries; digits alone are dropped, they carry no subject.
    """
    tokens = re.findall(r"\w+", fold(query), flags=re.UNICODE)
    return {token for token in tokens
            if len(token) > 3 and not token.isdigit() and token not in STOPWORDS}


def heuristic_select(query: str, nodes: list[dict[str, Any]], max_nodes: int) -> list[dict[str, Any]]:
    """Deterministic shortlist by term overlap. Leaves outrank domains at equal score.

    No match means no selection. The earlier fallback returned the largest
    clusters of the index whenever nothing matched, so `zzzzyyyyxxxx` and
    `quantum chromodynamics` both came back with the same eight big nodes and
    5 777 notices: a query about nothing produced the highest density in the
    index. An empty selection, with the message that goes with it, is the
    honest answer.
    """
    terms = query_terms(query)
    if not terms:
        return []
    scored: list[tuple[float, int, dict[str, Any]]] = []
    for node in nodes:
        if not node["n_notices"]:
            continue
        if node["node_id"].endswith(NEUTRAL_NODE_SUFFIXES):
            continue
        haystack = fold(
            " ".join(
                [
                    node["title"],
                    node["path"],
                    node.get("summary", ""),
                    " ".join(node["concept_tags"]),
                    " ".join(node["entity_tags"]),
                ]
            )
        )
        hits = sum(1 for term in terms if re.search(rf"\b{re.escape(term)}", haystack))
        if not hits:
            continue
        score = hits + (0.5 if node["depth"] > 1 else 0.0)
        scored.append((score, node["n_notices"], node))
    scored.sort(key=lambda item: (-item[0], -item[1]))
    return [node for _, _, node in scored[:max_nodes]]


def llm_select(
    query: str, candidates: list[dict[str, Any]], max_nodes: int
) -> tuple[list[dict[str, Any]], str, str]:
    """Returns (selected, reasoning, engine). Falls back on any failure."""
    payload = [
        {
            "node_id": node["node_id"],
            "title": node["title"],
            "path": node["path"],
            "summary": node["summary"],
            "tags": node["concept_tags"][:6],
            "n_notices": node["n_notices"],
        }
        for node in candidates
    ]
    prompt = NAVIGATION_PROMPT.format(
        query=query,
        nodes_json=json.dumps(payload, ensure_ascii=False, indent=1),
        max_nodes=max_nodes,
    )
    try:
        result = llm_adapter.complete(
            "You select sections of a bibliographic index. You answer with JSON only.",
            prompt,
            schema=SELECTION_SCHEMA,
            schema_name="origenality_tree_navigation",
        )
        parsed = llm_adapter.extract_json(result.content)
    except Exception:
        return [], "", "heuristic-after-failure"

    by_id = {node["node_id"]: node for node in candidates}
    selected: list[dict[str, Any]] = []
    for item in parsed.get("selected_nodes") or []:
        node = by_id.get(str(item.get("node_id", "")))
        if node and node not in selected:
            enriched = dict(node)
            enriched["reason"] = str(item.get("reason", ""))[:300]
            enriched["priority"] = item.get("priority")
            selected.append(enriched)
    reasoning = str(parsed.get("reasoning", ""))[:1200]
    if not selected:
        return [], reasoning, "heuristic-after-empty"
    return selected[:max_nodes], reasoning, "reasoning"


def navigate(
    query: str,
    document: dict[str, Any],
    *,
    max_nodes: int = 8,
    shortlist: int = 120,
    use_llm: bool = True,
) -> dict[str, Any]:
    nodes = flatten(document)
    pool = [
        node
        for node in nodes
        if node["n_notices"] and not node["node_id"].endswith(NEUTRAL_NODE_SUFFIXES)
    ]
    # Below the cap the reasoning engine sees the whole index: a term-overlap
    # pre-filter would hide the nodes whose wording does not echo the query,
    # which is exactly what reasoning is there to find.
    if len(pool) <= shortlist:
        candidates = sorted(pool, key=lambda node: -node["n_notices"])
    else:
        candidates = heuristic_select(query, pool, shortlist)

    engine = "heuristic"
    reasoning = ""
    selected: list[dict[str, Any]] = []

    if use_llm and llm_adapter.is_configured():
        selected, reasoning, engine = llm_select(query, candidates, max_nodes)
    if not selected:
        selected = heuristic_select(query, pool, max_nodes)
        if engine == "heuristic":
            reasoning = (
                "Deterministic selection: nodes ranked by the number of query terms found in "
                "their title, path, computed summary and tags, leaves preferred over domains "
                "at equal score."
            )
    if not selected:
        reasoning = (
            "No matching node: no term of the query was found in the title, path, computed "
            "summary or tags of any node of the index. The selection is empty, and the density "
            "of an empty selection is zero — the index holds nothing on this query, which is "
            "not the same as holding everything."
        )

    notice_ids: list[str] = []
    for node in selected:
        for notice_id in node.get("notice_ids", []):
            if notice_id not in notice_ids:
                notice_ids.append(notice_id)

    return {
        "query": query,
        "engine": engine,
        "reasoning": reasoning,
        "selected_nodes": [
            {
                "node_id": node["node_id"],
                "axis": node["axis"],
                "title": node["title"],
                "path": node["path"],
                "n_notices": node["n_notices"],
                "summary": node["summary"],
                "reason": node.get("reason", ""),
            }
            for node in selected
        ],
        "notice_ids": notice_ids,
        "density": {
            "notices_in_selection": len(notice_ids),
            "notices_indexed": document.get("counts", {}).get("notices_indexed", 0),
        },
    }


def main(argv: list[str]) -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--query", required=True, help="free description of a research project")
    parser.add_argument(
        "--tree", type=Path, default=None,
        help="index-arbre à lire ; par défaut celui du corpus fédéré, "
             "semantic/tree/topic_tree_federated.json")
    parser.add_argument("--max-nodes", type=int, default=8)
    parser.add_argument(
        "--shortlist",
        type=int,
        default=120,
        help="above this many nodes, the reasoning engine sees a term-overlap shortlist instead of the whole index",
    )
    parser.add_argument("--no-llm", action="store_true", help="deterministic engine only")
    parser.add_argument("--json", action="store_true", help="print the raw result")
    parser.add_argument("--show-notices", type=int, default=0, help="print the first N notice identifiers")
    arguments = parser.parse_args(argv)

    tree = arguments.tree
    if tree is None:
        tree = here / "topic_tree_federated.json"
        if not tree.exists():
            parser.error(
                "aucun arbre fédéré sur le disque (%s) : indiquez --tree.\n"
                "Le défaut ne retombe pas en silence sur l'arbre du pilote, "
                "dont le dénominateur est différent." % tree)
    if not tree.exists():
        parser.error("arbre introuvable : %s" % tree)

    document = load_tree(tree)
    result = navigate(
        arguments.query,
        document,
        max_nodes=arguments.max_nodes,
        shortlist=arguments.shortlist,
        use_llm=not arguments.no_llm,
    )

    if arguments.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"query   : {result['query']}")
    print(f"engine  : {result['engine']}")
    print(f"density : {result['density']['notices_in_selection']} notices out of "
          f"{result['density']['notices_indexed']} indexed")
    print("\nselected nodes:")
    for node in result["selected_nodes"]:
        print(f"  [{node['n_notices']:>4}] {node['node_id']}  {node['path']}")
        if node["reason"]:
            print(f"         {node['reason']}")
    if result["reasoning"]:
        print(f"\nreasoning: {result['reasoning']}")
    if arguments.show_notices:
        print("\nnotices:")
        for notice_id in result["notice_ids"][: arguments.show_notices]:
            print(f"  {notice_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
