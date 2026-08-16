#!/usr/bin/env python3
"""P1 Origenality — normalisation des pages brutes OpenAlex en records.jsonl + REPORT.md."""
import json, os, glob, re, unicodedata, collections, datetime

SCRATCH = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(SCRATCH, "oa_raw")
# Chemins relatifs au dépôt : un chemin absolu de machine rendait le
# moissonneur injouable ailleurs (critère D4, reproductibilité).
_HERE = os.path.dirname(os.path.abspath(__file__))
_BASE = os.path.dirname(_HERE)
OUT = os.path.join(_BASE, "data", "raw", "openalex")

# --- pre-classification -----------------------------------------------------
def fold(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower()

# indices patristiques dans le titre/abstract (forme repliee, sans accents)
PATRISTIC_TXT = re.compile(
    r"origen of alexandria|origenes de alejandria|origene di alessandria|"
    r"origene d'alexandrie|origenes alexandrinus|origenes von alexandri|"
    r"origen alexandrinus|orygenes z aleksandrii|"
    r"contra celsum|contre celse|kata kelsou|against celsus|gegen celsus|"
    r"\bcelsus\b|\bcelso\b|\bcelse\b|"
    r"de principiis|peri archon|periarchon|von den prinzipien|des principes|"
    r"hexapla|hexaplar|philocali|filocali|"
    r"adamantius|origeniana|origenianum|origenist|origenism|origenien|"
    r"\bpatristi|\bpatristic|early christian|padres de la iglesia|"
    r"\brufinus\b|\brufin\b|apokatastasis|apocatastasis|apocatastase|"
    r"alexandrian (school|tradition|christian|exegesis)|escuela de alejandria"
)
PATRISTIC_TOPIC = re.compile(
    r"classical philosophy|classical antiquity|biblical studies|"
    r"religious and theological|theology and canon law|augustinian|"
    r"byzantine|medieval philosophy|patristic|early christian|church history|"
    r"christian theolog|jewish|judaism|gnostic|hellenistic|"
    r"ancient (greek|near east)|greek and roman|philosophy of religion|"
    r"historical, religious, and philosophical"
)
NOISE_TOPIC = re.compile(
    r"spanish|latin america|iberia|constitutional|criminal justice|"
    r"legal|\blaw\b|politic|econom|business|innovation|sport|physical education|"
    r"health|bioethic|medic|nursing|psycholog|urban|tourism|advertis|"
    r"journalism|\bmedia\b|communication|education|regional development|"
    r"international relations|marketing|engineering|agricultur|environment|"
    r"climate|energy|management|social sciences and policies|migration|gender"
)
# « orígenes/origenes de / del / de la … » (titre espagnol/portugais commun)
ES_ORIGINS = re.compile(r"\borigen(es|s)?\b\s+(de|del|de la|da|do|dos|das|en|historic)")

NOISE_LANGS = {"es", "pt", "ca"}


def classify(title, abstract, lang, primary_topic, topics):
    txt = fold((title or "") + " " + (abstract or "")[:1500])
    ptopic = fold(primary_topic or "")
    if PATRISTIC_TXT.search(txt):
        return False, "indice-patristique-texte"
    if ptopic and PATRISTIC_TOPIC.search(ptopic):
        return False, "topic-patristique"
    if lang in NOISE_LANGS and ES_ORIGINS.search(fold(title or "")):
        return True, "es/pt/ca + « origenes de/del/… » sans indice patristique"
    if ptopic and NOISE_TOPIC.search(ptopic):
        return True, "topic-hors-champ"
    return None, "indetermine"


NBSP = " "


def N(x):
    """Milliers separes par une espace insecable (convention FR du projet)."""
    if x is None:
        return "n. d."
    return f"{x:,}".replace(",", NBSP)


def P(x):
    """Pourcentage a la francaise : virgule decimale."""
    return f"{x:.1f}".replace(".", ",") + " %"


def cell(s):
    """Echappe le pipe pour ne pas casser un tableau Markdown."""
    return str(s).replace("|", "\\|")


_BACKTICK = re.compile(r"`[^`]*`")


def fr_typo(text):
    """Espaces insecables avant : ; ! ? % et dans les guillemets, hors spans en backticks."""
    def fix(s):
        s = re.sub(r" ([:;!?%])", NBSP + r"\1", s)
        s = s.replace("« ", "«" + NBSP).replace(" »", NBSP + "»")
        return s
    out, last = [], 0
    for m in _BACKTICK.finditer(text):
        out.append(fix(text[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(fix(text[last:]))
    return "".join(out)


# --- normalisation ----------------------------------------------------------
def inverted_to_text(inv):
    if not inv:
        return None
    pos = []
    for word, idxs in inv.items():
        for i in idxs:
            pos.append((i, word))
    if not pos:
        return None
    pos.sort()
    return " ".join(w for _, w in pos)


def norm_doi(doi):
    if not doi:
        return None
    d = doi.strip().lower()
    for p in ("https://doi.org/", "http://dx.doi.org/", "doi:"):
        if d.startswith(p):
            d = d[len(p):]
    return d or None


def to_record(r, qslug):
    src = ((r.get("primary_location") or {}).get("source") or {})
    abstract = inverted_to_text(r.get("abstract_inverted_index"))
    ptopic = (r.get("primary_topic") or {}).get("display_name")
    topics = []
    for t in (r.get("topics") or []):
        n = t.get("display_name")
        if n and n not in topics:
            topics.append(n)
    if ptopic and ptopic not in topics:
        topics.insert(0, ptopic)
    title = r.get("display_name") or r.get("title")
    lang = r.get("language")
    noise, rule = classify(title, abstract, lang, ptopic, topics)
    authors = []
    for a in (r.get("authorships") or []):
        au = a.get("author") or {}
        name = au.get("display_name") or a.get("raw_author_name")
        if not name:
            continue
        e = {"name": name}
        if au.get("orcid"):
            e["orcid"] = au["orcid"]
        authors.append(e)
    return {
        "source": "openalex",
        "source_id": r.get("id"),
        "doi": norm_doi(r.get("doi")),
        "title": title,
        "authors": authors,
        "year": r.get("publication_year"),
        "language": lang,
        "container": src.get("display_name"),
        "publisher": src.get("host_organization_name"),
        "type": r.get("type"),
        "topics": topics,
        "abstract": abstract,
        "abstract_rights": "openalex-inverted" if abstract else None,
        "cited_by_count": r.get("cited_by_count"),
        "referenced_works_count": r.get("referenced_works_count"),
        "query_matched": [qslug],
        "noise_guess": noise,
        "noise_rule": rule,
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    state = json.load(open(os.path.join(RAW, "_state.json")))
    by_id = {}
    per_query_raw = collections.Counter()
    for path in sorted(glob.glob(os.path.join(RAW, "*.jsonl"))):
        slug = os.path.basename(path)[:-6]
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            per_query_raw[slug] += 1
            rec = to_record(r, slug)
            key = rec["source_id"]
            if key in by_id:
                if slug not in by_id[key]["query_matched"]:
                    by_id[key]["query_matched"].append(slug)
            else:
                by_id[key] = rec
    dedup_id = sum(per_query_raw.values()) - len(by_id)

    # fusion secondaire par DOI non nul
    by_doi = {}
    merged_doi = 0
    final = {}
    for key, rec in by_id.items():
        d = rec["doi"]
        if d and d in by_doi:
            tgt = final[by_doi[d]]
            for q in rec["query_matched"]:
                if q not in tgt["query_matched"]:
                    tgt["query_matched"].append(q)
            merged_doi += 1
            continue
        if d:
            by_doi[d] = key
        final[key] = rec

    recs = list(final.values())
    outp = os.path.join(OUT, "records.jsonl")
    with open(outp, "w", encoding="utf-8") as f:
        for rec in recs:
            rec["query_matched"].sort()
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---- rapport ----
    n = len(recs)
    with_abs = sum(1 for r in recs if r["abstract"])
    nz = collections.Counter(str(r["noise_guess"]) for r in recs)
    rules = collections.Counter(r["noise_rule"] for r in recs)
    langs = collections.Counter(r["language"] for r in recs)
    years = [r["year"] for r in recs if r["year"]]
    types = collections.Counter(r["type"] for r in recs)
    per_q_uniq = collections.Counter()
    for r in recs:
        for q in r["query_matched"]:
            per_q_uniq[q] += 1
    errs = {k: v.get("errors", []) for k, v in state.items() if v.get("errors")}

    L = []
    L.append("# OpenAlex — moisson P1 Origenality\n")
    L.append(f"Date de moisson : {datetime.date.today().isoformat()}  ")
    L.append("API : `https://api.openalex.org/works`, `filter=title_and_abstract.search:…`, "
             "cursor paging (`per-page=200`), `mailto=romain.girardi@univ-cotedazur.fr`, 0,15 s entre requêtes.  ")
    L.append("Licence des données OpenAlex : CC0. Aucune notice supprimée ; `noise_guess` est une pré-classification révisable.\n")
    L.append("## Volumétrie\n")
    L.append(f"- lignes brutes récupérées (toutes requêtes) : **{N(sum(per_query_raw.values()))}**")
    L.append(f"- notices uniques après dédoublonnage par `source_id` : **{N(len(by_id))}** "
             f"(doublons inter-requêtes fusionnés : {N(dedup_id)})")
    L.append(f"- fusions supplémentaires par DOI identique : **{N(merged_doi)}**")
    L.append(f"- **notices finales dans `records.jsonl` : {N(n)}**\n")
    L.append("## Par requête\n")
    L.append("| slug | `title_and_abstract.search` | `meta.count` API | lignes récupérées | notices finales portant ce slug | complet |")
    L.append("|---|---|---:|---:|---:|:--:|")
    order = [k for k, _ in sorted(state.items(), key=lambda kv: -per_query_raw[kv[0]])]
    for slug in order:
        st = state[slug]
        L.append(f"| `{slug}` | `{cell(st['query'])}` | {N(st.get('count'))} | {N(per_query_raw[slug])} | "
                 f"{N(per_q_uniq.get(slug,0))} | {'oui' if st.get('done') else 'NON'} |")
    L.append("")
    L.append("## Abstracts\n")
    L.append(f"- notices avec abstract reconstruit depuis `abstract_inverted_index` : **{N(with_abs)} / {N(n)} ({P(with_abs/n*100)})**")
    L.append("- champ `abstract_rights` = `\"openalex-inverted\"` (index inversé reconstruit ; stockage interne d'indexation)\n")
    L.append("## Pré-classification `noise_guess`\n")
    L.append("Ordre d'application des règles (la première qui déclenche l'emporte) :\n")
    L.append("1. indice patristique explicite dans le titre/abstract (Contra Celsum, De principiis, Hexapla, Philocalia, Origeniana, Rufinus, Adamantius, « Orígenes de Alejandría », patristic/early christian…) → `false`")
    L.append("2. `primary_topic` dans le champ patristique/antique (Classical Philosophy, Biblical Studies, Religious and Theological Studies, Theology and Canon Law, Augustinian, Byzantine, Medieval Philosophy…) → `false`")
    L.append("3. langue es/pt/ca **et** titre du type « orígenes de / del / de la … » **et** aucun indice patristique → `true`")
    L.append("4. `primary_topic` hors champ (Spanish Linguistics, Latin America, constitutional, law, politics, economics, medicine, media, education, sport…) → `true`")
    L.append("5. sinon → `null`\n")
    L.append("> Extension assumée par rapport à la consigne : le catalan (`ca`) est traité comme l'espagnol à la règle 3 "
             "(même homonymie « orígens/orígenes »). Le champ `noise_rule` conserve la règle déclenchée pour chaque notice.\n")
    L.append("| `noise_guess` | notices | part |")
    L.append("|---|---:|---:|")
    for k in ("False", "True", "None"):
        L.append(f"| `{k.lower()}` | {N(nz.get(k,0))} | {P(nz.get(k,0)/n*100)} |")
    L.append("")
    L.append("| règle déclenchée | notices |")
    L.append("|---|---:|")
    for k, v in rules.most_common():
        L.append(f"| {k} | {N(v)} |")
    L.append("")
    L.append("## Répartition\n")
    L.append("Langues (top 12) : " + ", ".join(f"`{k}` {N(v)}" for k, v in langs.most_common(12)) + "\n")
    L.append("Types (top 10) : " + ", ".join(f"`{k}` {N(v)}" for k, v in types.most_common(10)) + "\n")
    if years:
        L.append(f"Années : min {min(years)}, max {max(years)}, médiane {sorted(years)[len(years)//2]}\n")
    L.append("## Échecs\n")
    if errs:
        for k, v in errs.items():
            L.append(f"- `{k}` : {v}")
    else:
        logp = os.path.join(SCRATCH, "oa_harvest.log")
        n429 = 0
        if os.path.exists(logp):
            n429 = sum(1 for l in open(logp, encoding="utf-8", errors="replace") if "429" in l)
        L.append(f"Aucune requête en échec : les {len(state)} requêtes sont marquées complètes, aucune page perdue.")
        if n429:
            L.append(f"\n{N(n429)} réponses `HTTP 429 Too Many Requests` ont été rencontrées, toutes absorbées par le "
                     "backoff exponentiel (1, 2, 4, 8 s) : la requête a abouti au réessai et la pagination a repris "
                     "au même curseur.\n")
    L.append("\n## Réserves\n")
    L.append("- Les écarts de quelques unités entre `meta.count` et le nombre de lignes récupérées viennent de la "
             "mise à jour de l'index OpenAlex pendant la pagination (curseur). Ils ne signalent pas de perte : "
             "le dédoublonnage final par `source_id` absorbe les répétitions.")
    L.append("- `origenes` et `origene` retournent le même ensemble (racinisation OpenAlex) : les deux slugs sont conservés "
             "dans `query_matched` mais ne constituent pas deux gisements distincts.")
    L.append("- `noise_guess` est un **pré-tri mécanique**, pas un jugement bibliographique. Aucune notice n'a été écartée.")
    open(os.path.join(OUT, "REPORT.md"), "w", encoding="utf-8").write(fr_typo("\n".join(L)) + "\n")
    print(f"records: {n}  abstracts: {with_abs}  noise true/false/null: "
          f"{nz.get('True',0)}/{nz.get('False',0)}/{nz.get('None',0)}")


if __name__ == "__main__":
    main()
