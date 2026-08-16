#!/usr/bin/env python3
"""Build sections.json: the GIROTA section taxonomy (form menus + observed usage)."""
import os, re, json, html, collections, datetime

import sys

SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCR)
from adam_paths import BASE, ensure_form

OUTDIR = os.path.join(BASE, "data", "raw", "adamantius")

form = ensure_form()


def options(name):
    sel = re.search(r'<select name="%s">(.*?)</select>' % name, form, re.S).group(1)
    out = []
    for m in re.finditer(r"<option(?:\s+value=\"([^\"]*)\")?\s*>(.*?)</option>", sel, re.S):
        val = m.group(1)
        label = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(2)))).strip()
        out.append((val, label))
    return out


# --- top-level sections (value attribute is the canonical string used by the DB)
sec1 = [html.unescape(v) for v, l in options("sezione1sel") if v]

# --- subsection menu: value="" entries are group headers for the preceding parent
sub_by_parent, cur = collections.OrderedDict(), None
for v, l in options("sezione2sel"):
    if v == "" and l and not l.startswith("--") and l != "tutte le sezioni":
        cur = l.rstrip(":").strip()
        sub_by_parent.setdefault(cur, [])
    elif v and cur:
        sub_by_parent[cur].append(html.unescape(v))

# --- observed usage in the harvested records
recs = [json.loads(l) for l in open(os.path.join(OUTDIR, "records.jsonl"), encoding="utf-8")]
pair_counts = collections.Counter()
sec_counts = collections.Counter()
for r in recs:
    for s in r["sections"]:
        sec_counts[s["sezione"]] += 1
        pair_counts[(s["sezione"], s["sottosezione"])] += 1

order = {s: i for i, s in enumerate(sec1)}


def sec_sort(s):
    """Order by the section's own number, so a section absent from the form menu
    (13, whose menu value is corrupted) still lands in its proper place."""
    m = re.match(r"\s*(\d+)\.", s or "")
    return (0, int(m.group(1))) if m else (1, 0)


observed = []
for sez in sorted(sec_counts, key=sec_sort):
    subs = sorted([(sub, n) for (s, sub), n in pair_counts.items() if s == sez],
                  key=lambda t: t[0])
    menu = sub_by_parent.get(sez, [])
    observed.append({
        "sezione": sez,
        "in_form_menu": sez in order,
        "n_records": sec_counts[sez],
        "sottosezioni": [{"sottosezione": sub or None, "n_records": n,
                          "in_form_menu": bool(sub) and sub in menu}
                         for sub, n in subs],
    })

# --- subsections used by the data but absent from the form menu of their parent
sub_anomalies = []
for so in observed:
    menu = sub_by_parent.get(so["sezione"], [])
    for sub in so["sottosezioni"]:
        if not sub["sottosezione"] or sub["in_form_menu"]:
            continue
        sub_anomalies.append({
            "sezione": so["sezione"],
            "sottosezione": sub["sottosezione"],
            "n_records": sub["n_records"],
            # 'variant'  : the parent has a subsection menu, this value is not in it
            # 'no_menu'  : the parent has no subsection menu at all in the form
            "kind": "variant" if menu else "no_menu",
            "menu_values": menu,
        })

out = {
    "source": "adamantius-girota",
    "source_url": "http://www2.classics.unibo.it/adamantius/index.php?page=ricerca",
    "retrieved": datetime.date.today().isoformat(),
    "note": ("Taxonomy as published by the GIROTA repertorio bibliografico. "
             "form_sections / form_subsections_by_parent are read verbatim from the "
             "search form's <select> menus; observed_sections counts the harvested records."),
    "known_issues": [
        {"kind": "form_value_mismatch",
         "form_value": "13. L.origenismo e la fortuna di Origene",
         "database_value": "13. L`origenismo e la fortuna di Origene",
         "effect": ("The search form sends a dot where the database stores a backtick, so "
                    "querying section 13 through the form returns 0 results for every year. "
                    "These records are only reachable by fetching schede directly.")}
    ],
    "n_form_sections": len(sec1),
    "form_sections": sec1,
    "form_subsections_by_parent": sub_by_parent,
    "subsection_anomalies": sub_anomalies,
    "observed_sections": observed,
}
json.dump(out, open(os.path.join(OUTDIR, "sections.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("form sections:", len(sec1), "| parents with subsections:", len(sub_by_parent),
      "| observed sections:", len(observed))
for k, v in sub_by_parent.items():
    print("  ", k, "->", len(v))
print("subsection anomalies:", len(sub_anomalies))
for a in sub_anomalies:
    print("   %s | %r (%d)" % (a["sezione"][:28], a["sottosezione"], a["n_records"]))
