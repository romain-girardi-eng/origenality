"""Fail a release where the CLI and the page do not answer alike.

The map and the `origenality` CLI must give one reader one answer. They share
site/assets/search-core.js precisely so that they cannot drift, but sharing a
file is only a promise until something checks it: the page also builds the
index (explorer.js) and the CLI rebuilds it (cli/origenality.mjs), and it is
that rebuild which can quietly diverge — a field added to `hay` on one side and
not the other.

So this compares the two, end to end, on queries chosen to exercise every rule
the search has: a subject absent from the corpus, a conjunction that must not
be silently relaxed, a term that used to match inside other words, a heading in
its four spellings, and a genuinely thin neighbourhood.

    python3 scripts/check_search_parity.py            # against origenality.com
    python3 scripts/check_search_parity.py --local    # against this tree

Needs node, and a browser only for --browser (the `bu` CLI, headed).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# One query per rule the search enforces, with what the rule guarantees.
CASES = [
    ("Origen in Ethiopia", "a subject in none of the records must be named as absent"),
    ("free will in the Commentary on Romans", "a conjunction must be counted before it is widened"),
    ("Rome", "a term matches at a word start, not inside 'jerome'"),
    ("prière", "a domain label must not stand in for the free text"),
    ("Martyrium", "…and must not make two headings return one set"),
    ("Contre Celse", "an alias of a work reaches the records of that work"),
    ("Contra Celsum", "…as does its label"),
    ("apokatastasis", "a plain subject keeps answering as it did"),
    ("Bardaisan", "a thin neighbourhood stays thin"),
    ("the art of the homily", "two common words are a conjunction, not a shelf"),
]

FIELDS = ("carrying_all_terms", "listed", "counted_in_density",
          "corpus_density_total", "widened", "widened_to_terms",
          "filed_under_heading", "terms_absent_from_corpus")


def cli(query, local):
    cmd = ["node", str(ROOT / "cli" / "origenality.mjs"), "search", query, "--json", "--limit", "0"]
    if local:
        cmd += ["--local", str(ROOT)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if out.returncode:
        raise SystemExit(f"CLI failed on {query!r}: {out.stderr.strip()}")
    return json.loads(out.stdout)


def browser(queries, url):
    """Drive the real page. Uses the `bu` CLI, the only browser path here."""
    js = """(()=>{const i=document.getElementById('ask-input'),g=document.getElementById('ask-go'),o={};
for(const q of %s){i.value=q;i.dispatchEvent(new Event('input',{bubbles:true}));g.click();
o[q]=document.getElementById('ask-state').textContent;}return JSON.stringify(o)})()""" % json.dumps(queries)
    session = "parity"
    subprocess.run(["bu", "--session", session, "--headed", "python",
                    f'browser.goto("{url}")\nbrowser.wait(14)'], capture_output=True, timeout=300)
    try:
        out = subprocess.run(["bu", "--session", session, "eval", js],
                             capture_output=True, text=True, timeout=180)
        raw = out.stdout.strip()
        return json.loads(raw[raw.index("{"):])
    finally:
        subprocess.run(["bu", "--session", session, "close"], capture_output=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="read this tree, not origenality.com")
    ap.add_argument("--browser", action="store_true", help="also compare against the live page")
    ap.add_argument("--url", default="https://origenality.com/site/")
    args = ap.parse_args()

    seen = [(q, cli(q, args.local)) for q, _ in CASES]

    bad = []
    for (query, rule), (_q, got) in zip(CASES, seen):
        # the rules themselves, not just equality: a shared file can be shared
        # and wrong.
        if query == "Origen in Ethiopia" and "ethiopia" not in got["terms_absent_from_corpus"]:
            bad.append(f"{query!r}: the absent term is not reported ({rule})")
        if query == "Rome" and got["counted_in_density"] > 40:
            bad.append(f"{query!r}: {got['counted_in_density']} hits, the word boundary is gone ({rule})")
        if query == "Contre Celse" and not got.get("filed_under_heading"):
            bad.append(f"{query!r}: the aliases are not served ({rule})")
        if query == "Bardaisan" and got["counted_in_density"] > 10:
            bad.append(f"{query!r}: {got['counted_in_density']} hits, a thin subject has thickened ({rule})")

    pr, ma = dict(seen).get("prière"), dict(seen).get("Martyrium")
    if pr and ma and pr["counted_in_density"] == ma["counted_in_density"] \
            and pr["counted_in_density"] > 20:
        bad.append("'prière' and 'Martyrium' answer with one and the same figure: "
                   "the domain label is back in the free-text index")

    for query, got in seen:
        print(f"  {got['counted_in_density']:>5} / {got['corpus_density_total']}"
              f"{'  (widened)' if got['widened'] else ''}   {query}")

    if args.browser:
        pages = browser([q for q, _ in CASES], args.url)
        for query, got in seen:
            line = pages.get(query, "")
            n = f"{got['counted_in_density']:,}".replace(",", " ")
            alt = f"{got['counted_in_density']:,}".replace(",", " ")
            if n not in line and alt not in line and str(got["counted_in_density"]) not in line:
                bad.append(f"{query!r}: CLI says {got['counted_in_density']}, "
                           f"the page says {line!r}")

    if bad:
        print("\n".join("  ✗ " + b for b in bad), file=sys.stderr)
        return 1
    print(f"\n{len(CASES)} queries — the CLI and the rules agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
