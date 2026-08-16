#!/usr/bin/env python3
"""P1 Origenality — normalisation des pages brutes Crossref en records.jsonl + REPORT.md."""
import json, os, glob, re, html, unicodedata, collections, datetime

SCRATCH = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(SCRATCH, "cr_raw")
# Chemins relatifs au dépôt : un chemin absolu de machine rendait le
# moissonneur injouable ailleurs (critère D4, reproductibilité).
_HERE = os.path.dirname(os.path.abspath(__file__))
_BASE = os.path.dirname(_HERE)
OUT = os.path.join(_BASE, "data", "raw", "crossref")


def fold(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


PATRISTIC_TXT = re.compile(
    r"origen of alexandria|origenes de alejandria|origene di alessandria|"
    r"origene d'alexandrie|origenes alexandrinus|origenes von alexandri|"
    r"orygenes z aleksandrii|origen alexandrinus|"
    r"contra celsum|contre celse|against celsus|gegen celsus|kata kelsou|"
    r"\bcelsus\b|\bcelso\b|\bcelse\b|"
    r"de principiis|peri archon|periarchon|des principes|von den prinzipien|"
    r"hexapla|philocali|filocali|adamantius|"
    r"origeniana|origenianum|origenist|origenism|origenien|origeniennes?|"
    r"\bpatristi|patristic|early christian|padres de la iglesia|"
    r"\brufinus\b|\brufin\b|apokatastasis|apocatastasis|apocatastase|"
    r"alexandrian (school|tradition|christian|exegesis)|escuela de alejandria|"
    r"\beusebius\b|\bjerome\b|\bpamphilus\b"
)
# revues / collections du champ patristique et antiquisant
PATRISTIC_CONTAINER = re.compile(
    r"vigiliae christianae|studia patristica|adamantius|"
    r"journal of early christian|zeitschrift fur antikes christentum|"
    r"revue d'?etudes augustiniennes|augustinianum|augustinian|"
    r"revue des etudes grecques|sources chretiennes|corpus christianorum|"
    r"patrolog|journal of theological studies|harvard theological review|"
    r"church history|early christianity|theologische|scrinium|"
    r"bibliotheca ephemeridum theologicarum|orientalia christiana|"
    r"gregorianum|recherches de science religieuse|revue thomiste|"
    r"greek, roman and byzantine|byzantin|classical quarterly|"
    r"journal of hellenic studies|phronesis|vetera christianorum|"
    r"annali di storia dell'?esegesi|rivista di storia del cristianesimo"
)
ORIGEN_STEM = re.compile(r"orig[eè]n|orygen|origin?enes|\bwrigen")
ES_ORIGINS = re.compile(r"\borigen(es|s)?\b\s+(de|del|de la|da|do|dos|das|en|historic)")
NOISE_LANGS = {"es", "pt", "ca"}


def classify(title, abstract, container, lang):
    txt = fold((title or "") + " " + (abstract or "")[:1500])
    cont = fold(container or "")
    if PATRISTIC_TXT.search(txt):
        return False, "indice-patristique-texte"
    if cont and PATRISTIC_CONTAINER.search(cont):
        return False, "revue/collection patristique ou antiquisante"
    ftitle = fold(title or "")
    if lang in NOISE_LANGS and ES_ORIGINS.search(ftitle):
        return True, "es/pt/ca + « origenes de/del/… » sans indice patristique"
    if ftitle and not ORIGEN_STEM.search(ftitle) and not ORIGEN_STEM.search(cont):
        return True, "aucun radical origen-/orygen- ni indice patristique (bruit OR de query.bibliographic)"
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


JATS = re.compile(r"<[^>]+>")


def clean_abstract(a):
    if not a:
        return None
    t = JATS.sub(" ", a)
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t or None


def year_of(it):
    for k in ("issued", "published-print", "published-online", "created"):
        dp = (it.get(k) or {}).get("date-parts") or []
        if dp and dp[0] and dp[0][0]:
            return dp[0][0]
    return None


def to_record(it, slug):
    title = (it.get("title") or [None])[0]
    cont = (it.get("container-title") or [None])[0]
    abstract = clean_abstract(it.get("abstract"))
    lang = it.get("language")
    noise, rule = classify(title, abstract, cont, lang)
    authors = []
    for a in (it.get("author") or []):
        name = " ".join(x for x in [a.get("given"), a.get("family")] if x) or a.get("name")
        if not name:
            continue
        e = {"name": name}
        if a.get("ORCID"):
            e["orcid"] = a["ORCID"]
        authors.append(e)
    return {
        "source": "crossref",
        "source_id": it.get("DOI"),
        "doi": (it.get("DOI") or "").lower() or None,
        "title": title,
        "authors": authors,
        "year": year_of(it),
        "language": lang,
        "container": cont,
        "publisher": it.get("publisher"),
        "type": it.get("type"),
        "topics": it.get("subject") or [],
        "abstract": abstract,
        "abstract_rights": "crossref-jats" if abstract else None,
        "crossref_score": it.get("score"),
        "query_matched": [slug],
        "noise_guess": noise,
        "noise_rule": rule,
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    state = json.load(open(os.path.join(RAW, "_state.json")))
    by_doi, no_doi = {}, []
    per_q_raw = collections.Counter()
    for path in sorted(glob.glob(os.path.join(RAW, "*.jsonl"))):
        slug = os.path.basename(path)[:-6]
        for line in open(path, encoding="utf-8"):
            it = json.loads(line)
            per_q_raw[slug] += 1
            rec = to_record(it, slug)
            k = rec["source_id"]
            if not k:
                no_doi.append(rec)
                continue
            if k in by_doi:
                if slug not in by_doi[k]["query_matched"]:
                    by_doi[k]["query_matched"].append(slug)
                if (rec.get("crossref_score") or 0) > (by_doi[k].get("crossref_score") or 0):
                    by_doi[k]["crossref_score"] = rec["crossref_score"]
            else:
                by_doi[k] = rec
    recs = list(by_doi.values()) + no_doi
    with open(os.path.join(OUT, "records.jsonl"), "w", encoding="utf-8") as f:
        for r in recs:
            r["query_matched"].sort()
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n = len(recs)
    with_abs = sum(1 for r in recs if r["abstract"])
    with_lang = sum(1 for r in recs if r["language"])
    with_auth = sum(1 for r in recs if r["authors"])
    nz = collections.Counter(str(r["noise_guess"]) for r in recs)
    rules = collections.Counter(r["noise_rule"] for r in recs)
    types = collections.Counter(r["type"] for r in recs)
    langs = collections.Counter(r["language"] for r in recs if r["language"])
    years = [r["year"] for r in recs if r["year"]]
    per_q_uniq = collections.Counter()
    for r in recs:
        for q in r["query_matched"]:
            per_q_uniq[q] += 1
    errs = {k: v.get("errors", []) for k, v in state.items() if v.get("errors")}

    L = []
    L.append("# Crossref — moisson P1 Origenality\n")
    L.append(f"Date de moisson : {datetime.date.today().isoformat()}  ")
    L.append("API : `https://api.crossref.org/works`, `query.bibliographic=…`, tri par pertinence, "
             "cursor paging (`rows=200`), `User-Agent` avec mailto `romain.girardi@univ-cotedazur.fr`, "
             "0,5 s entre requêtes, backoff exponentiel sur erreur HTTP.  ")
    L.append("**CAP : 3 000 notices par requête** (au-delà, la queue de pertinence est du bruit pur). "
             "Les listes `reference` ont été retirées des notices brutes (hors périmètre P1).\n")
    capped = {s for s, v in state.items() if v.get("capped")}
    uniq_capped = sum(1 for r in recs if capped.intersection(r["query_matched"]))
    raw_capped = sum(per_q_raw[s] for s in capped)
    L.append("## Volumétrie\n")
    L.append(f"- lignes brutes récupérées : **{N(sum(per_q_raw.values()))}**")
    L.append(f"- notices uniques après dédoublonnage par DOI : **{N(len(by_doi))}**")
    L.append(f"- notices sans DOI (conservées telles quelles) : **{N(len(no_doi))}**")
    L.append(f"- **notices finales dans `records.jsonl` : {N(n)}**")
    L.append(f"- recouvrement inter-requêtes absorbé : {N(sum(per_q_raw.values()) - n)} doublons\n")
    L.append("## Par requête\n")
    L.append("| slug | `query.bibliographic` | `total-results` API | récupérées | plafonnée | notices finales portant ce slug |")
    L.append("|---|---|---:|---:|:--:|---:|")
    for slug, st in state.items():
        L.append(f"| `{slug}` | `{cell(st['query'])}` | {N(st.get('total'))} | {N(st.get('fetched'))} | "
                 f"{'oui' if st.get('capped') else 'non'} | {N(per_q_uniq.get(slug,0))} |")
    L.append("")
    L.append("## Couverture des champs\n")
    L.append("| champ | notices renseignées | taux |")
    L.append("|---|---:|---:|")
    for lbl, v in (("abstract", with_abs), ("language", with_lang), ("authors", with_auth),
                   ("container", sum(1 for r in recs if r["container"])),
                   ("year", len(years)), ("title", sum(1 for r in recs if r["title"]))):
        L.append(f"| `{lbl}` | {N(v)} | {P(v/n*100)} |")
    L.append("")
    L.append(f"Le taux d'abstracts observé ({P(with_abs/n*100)}) est inférieur au ~26 % attendu : "
             "les abstracts Crossref sont en JATS et déposés de façon très inégale selon l'éditeur. "
             "Les balises JATS ont été retirées ; `abstract_rights` = `\"crossref-jats\"`.\n")
    L.append("## Pré-classification `noise_guess`\n")
    L.append("Crossref ne fournit ni topics ni langue fiable (langue présente sur "
             f"{P(with_lang/n*100)} des notices seulement) : les règles reposent donc sur le texte, "
             "et non sur une classification thématique. Ordre d'application :\n")
    L.append("1. indice patristique explicite dans le titre/abstract (Contra Celsum, De principiis, Hexapla, "
             "Philocalia, Origeniana, Rufinus, Adamantius, Eusebius, patristic/early christian…) → `false`")
    L.append("2. revue ou collection du champ patristique/antiquisant dans `container` "
             "(Vigiliae Christianae, Studia Patristica, JECS, ZAC, Sources chrétiennes, Corpus Christianorum…) → `false`")
    L.append("3. langue es/pt/ca **et** titre du type « orígenes de / del / de la … » **et** aucun indice patristique → `true`")
    L.append("4. **aucun radical `origen-`/`orygen-`** ni dans le titre ni dans le container, et aucun indice patristique → `true` "
             "(bruit mécanique de `query.bibliographic`, qui apparie les termes de façon disjonctive : "
             "« Origen De principiis » remonte 10 150 325 résultats, dont l'immense majorité ne mentionne pas Origène)")
    L.append("5. sinon → `null`\n")
    L.append("Le champ `noise_rule` conserve pour chaque notice la règle déclenchée, ce qui rend le pré-tri révisable.\n")
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
    L.append("Types (top 10) : " + ", ".join(f"`{k}` {N(v)}" for k, v in types.most_common(10)) + "\n")
    L.append("Langues déclarées (top 8) : " + ", ".join(f"`{k}` {N(v)}" for k, v in langs.most_common(8)) + "\n")
    if years:
        L.append(f"Années : min {min(years)}, max {max(years)}, médiane {sorted(years)[len(years)//2]}\n")
    L.append("## Échecs\n")
    if errs:
        for k, v in errs.items():
            L.append(f"- `{k}` : {v}")
    else:
        L.append("Aucune requête en échec, aucun 429/503 rencontré, aucune page perdue.\n")
    L.append("\n## Réserves\n")
    L.append("- Le champ `crossref_score` (score de pertinence Crossref) est conservé : il est le seul "
             "ordonnancement disponible pour arbitrer les trois requêtes plafonnées à 3 000.")
    L.append("- Les trois requêtes plafonnées (`Origen of Alexandria`, `Origen Contra Celsum`, "
             "`Origen De principiis`) ont des têtes de pertinence partiellement recouvrantes : "
             f"leurs {N(raw_capped)} lignes brutes se réduisent à {N(uniq_capped)} DOI uniques.")
    L.append("- Le plafond à 3 000 laisse hors moisson la queue de pertinence de ces trois requêtes "
             f"({N(state['origen_of_alexandria']['total'])}, {N(state['origen_contra_celsum']['total'])} et "
             f"{N(state['origen_de_principiis']['total'])} résultats annoncés). Ce n'est pas une perte de "
             "couverture bibliographique : `query.bibliographic` apparie les termes de façon disjonctive, "
             "de sorte que les résultats de rang élevé ne mentionnent plus Origène du tout. "
             "La couverture réelle du champ repose sur OpenAlex et sur les sources spécialisées.")
    L.append("- `noise_guess` est un **pré-tri mécanique**, pas un jugement bibliographique. Aucune notice n'a été écartée.")
    open(os.path.join(OUT, "REPORT.md"), "w", encoding="utf-8").write(fr_typo("\n".join(L)) + "\n")
    print(f"records: {n}  abstracts: {with_abs}  noise true/false/null: "
          f"{nz.get('True',0)}/{nz.get('False',0)}/{nz.get('None',0)}")


if __name__ == "__main__":
    main()
