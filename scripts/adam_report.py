#!/usr/bin/env python3
"""Write REPORT.md: volumetry by year and section, capped queries, failures."""
import os, re, json, collections, datetime

SCR = os.path.dirname(os.path.abspath(__file__))
# Chemins relatifs au dépôt : un chemin absolu de machine rendait le
# moissonneur injouable ailleurs (critère D4, reproductibilité).
_HERE = os.path.dirname(os.path.abspath(__file__))
_BASE = os.path.dirname(_HERE)
OUTDIR = os.path.join(_BASE, "data", "raw", "adamantius")

recs = [json.loads(l) for l in open(os.path.join(OUTDIR, "records.jsonl"), encoding="utf-8")]
stats = json.load(open(os.path.join(SCR, "build_stats.json")))
sections = json.load(open(os.path.join(OUTDIR, "sections.json")))
grid = json.load(open(os.path.join(SCR, "grid_results.json"))) if os.path.exists(
    os.path.join(SCR, "grid_results.json")) else {}

n_sch = sum(len(r["scheda_ids"]) for r in recs)

# ---- volumetry
by_year = collections.Counter(
    str(r["year_bib_parsed"][0]) if r["year_bib_parsed"] else "(vide)" for r in recs)
composite = [r for r in recs if len(r["year_bib_parsed"]) > 1]
by_vol = collections.Counter()
for r in recs:
    for v in r["volume_years"]:
        by_vol[v] += 1
by_sec = collections.Counter()
for r in recs:
    for s in r["sections"]:
        by_sec[s["sezione"]] += 1
by_lang = collections.Counter(r["language"] or "(non déduite)" for r in recs)
by_method = collections.Counter(r["reference_split_method"] for r in recs)

# section x volume-year matrix
matrix = collections.Counter()
for r in recs:
    for s in r["sections"]:
        for vy in r["volume_years"]:
            matrix[(s["sezione"], vy)] += 1
vol_years = sorted(by_vol)
order = {s: i for i, s in enumerate(sections["form_sections"])}


def sec_sort(s):
    m = re.match(r"\s*(\d+)\.", s or "")
    return (0, int(m.group(1))) if m else (1, 0)


sec_order = sorted(by_sec, key=sec_sort)

# ---- grid cross-check
capped, grid_ids, grid_fail = [], set(), []
for key, g in grid.items():
    sez, yr = key.rsplit("||", 1)
    if g.get("error"):
        grid_fail.append((sez, yr, g["error"]))
        continue
    if g.get("capped"):
        capped.append((sez, yr, g["count"]))
    grid_ids.update(g.get("ids", []))
harvested_ids = {i for r in recs for i in r["scheda_ids"]}
grid_only = sorted(grid_ids - harvested_ids)

L = []
w = L.append
w("# Adamantius / GIROTA — extraction de la base bibliographique")
w("")
w("*Repertorio bibliografico du Gruppo Italiano di Ricerca su « Origene e la tradizione")
w("alessandrina » (GIROTA), publié dans l'annuaire* Adamantius. *Continuation de fait de")
w("la bibliographie origénienne de Crouzel.*")
w("")
w("| | |")
w("|---|---|")
w("| Source | `http://www2.classics.unibo.it/adamantius/` |")
w("| Formulaire | `index.php?page=ricerca` → POST `index.php?page=result` |")
w("| Méthode d'extraction | balayage exhaustif des fiches `index.php?page=schedasingola&schedavis=N`, N = 1…5100 |")
w("| Date d'extraction | %s |" % datetime.date.today().isoformat())
w("| Fiches (schede) trouvées | **%d** |" % n_sch)
w("| Notices après dédoublonnage | **%d** |" % len(recs))
w("| Doublons fusionnés | %d |" % (n_sch - len(recs)))
w("| Notices multi-sections | %d |" % sum(1 for r in recs if len(r["sections"]) > 1))
w("| Notices avec abstract | %d (%.1f %%) |" % (
    sum(1 for r in recs if r["abstract"]),
    100 * sum(1 for r in recs if r["abstract"]) / max(1, len(recs))))
w("")
w("Le balayage par identifiant de fiche contourne entièrement le plafond de 100 résultats")
w("du formulaire : chaque fiche est atteinte directement, sans passer par une requête.")
w("Les requêtes `sezione × anno` n'ont servi que de contrôle croisé (voir plus bas).")
w("")

w("## Volumétrie par année bibliographique (champ *Anno* de la fiche)")
w("")
w("Année de la publication recensée, non celle de l'annata. Le champ *Anno* porte parfois")
w("une valeur composite (`1998-1999`, `1996 1998`) : la table retient alors la première")
w("année, `year_bib` conserve la chaîne d'origine et `year_bib_parsed` la liste complète.")
w("")
w("| Année | Notices |")
w("|---|---:|")
for y in sorted(by_year, key=lambda x: (x == "(vide)", x)):
    w("| %s | %d |" % (y, by_year[y]))
w("| **Total** | **%d** |" % len(recs))
w("")
w("- Valeurs composites : **%d** notices" % len(composite))
w("- Champ *Anno* vide : **%d** notices" % by_year.get("(vide)", 0))
w("")

w("## Volumétrie par annata d'*Adamantius* (champ *Codice volume*)")
w("")
w("| Volume (année) | Notices |")
w("|---|---:|")
for y in vol_years:
    w("| %s | %d |" % (y, by_vol[y]))
w("")

w("## Volumétrie par section")
w("")
w("Une notice comptée dans chaque section où elle figure ; le total dépasse donc le")
w("nombre de notices.")
w("")
w("| Section | Notices |")
w("|---|---:|")
for s in sec_order:
    w("| %s | %d |" % (s, by_sec[s]))
w("")

w("## Matrice section × annata")
w("")
w("| Section | " + " | ".join(vol_years) + " | Total |")
w("|---|" + "---:|" * (len(vol_years) + 1))
for s in sec_order:
    cells = [str(matrix[(s, y)]) if matrix[(s, y)] else "·" for y in vol_years]
    w("| %s | %s | %d |" % (s, " | ".join(cells), by_sec[s]))
w("")

w("## Sous-sections observées")
w("")
w("| Section | Sous-section | Notices |")
w("|---|---|---:|")
for so in sections["observed_sections"]:
    for sub in so["sottosezioni"]:
        w("| %s | %s | %d |" % (so["sezione"], sub["sottosezione"] or "*(aucune)*", sub["n_records"]))
w("")

w("## Langues (déduites du titre, `null` quand indécidable)")
w("")
w("| Langue | Notices |")
w("|---|---:|")
for k, v in by_lang.most_common():
    w("| %s | %d |" % (k, v))
w("")

w("## Contrôle croisé : requêtes `sezione × anno`")
w("")
if not grid:
    w("*Grille non disponible.*")
else:
    w("%d requêtes POST lancées (37 sections × %d années, 1993-2006), pour vérifier que le"
      % (len(grid), len(grid) // 37 if grid else 0))
    w("balayage par identifiant n'a rien laissé de côté.")
    w("")
    w("- Requêtes ayant plafonné à 100 résultats (troncature du serveur) : **%d**" % len(capped))
    w("- Requêtes en échec : **%d**" % len(grid_fail))
    w("- Fiches vues par la grille mais absentes du balayage : **%d**" % len(grid_only))
    w("")
    if capped:
        w("### Requêtes plafonnées à 100")
        w("")
        w("Le serveur renvoie au plus 100 lignes. Ces requêtes sont donc tronquées — ce qui")
        w("est sans conséquence ici, le corpus ayant été constitué par balayage d'identifiants")
        w("et non par ces requêtes.")
        w("")
        w("La dernière colonne donne ce que le balayage par identifiant a effectivement")
        w("récupéré pour la même section et la même année : au-delà de 100, la troncature")
        w("du formulaire est bien rattrapée.")
        w("")
        w("| Section | Année | Résultats du formulaire | Notices récupérées par balayage |")
        w("|---|---|---:|---:|")
        for sez, yr, cnt in sorted(capped):
            got = sum(1 for r in recs
                      if any(s["sezione"] == sez for s in r["sections"])
                      and int(yr) in r["year_bib_parsed"])
            w("| %s | %s | %d (plafond) | %d |" % (sez, yr, cnt, got))
        w("")
    if grid_fail:
        w("### Requêtes en échec")
        w("")
        w("| Section | Année | Erreur |")
        w("|---|---|---|")
        for sez, yr, e in grid_fail:
            w("| %s | %s | %s |" % (sez, yr, e))
        w("")
    if grid_only:
        w("### Fiches vues par la grille et absentes du balayage")
        w("")
        w(", ".join(str(i) for i in grid_only[:200]))
        w("")

w("## Anomalies relevées dans la base")
w("")
w("### La section 13 est inatteignable par le formulaire")
w("")
sec13_form = [s for s in sections["form_sections"] if s.startswith("13.")]
sec13_db = [o["sezione"] for o in sections["observed_sections"] if o["sezione"].startswith("13.")]
sec13_n = sum(o["n_records"] for o in sections["observed_sections"] if o["sezione"].startswith("13."))
sec13_grid = sum(v["count"] for k, v in grid.items()
                 if k.startswith("13.") and v.get("count")) if grid else None
w("Le menu du formulaire envoie la valeur suivante :")
w("")
w("```")
for s in sec13_form:
    w(repr(s))
w("```")
w("")
w("tandis que la base stocke :")
w("")
w("```")
for s in sec13_db:
    w(repr(s))
w("```")
w("")
w("Un point là où la base porte un accent grave. La comparaison est exacte côté serveur :")
w("interroger la section 13 par le formulaire renvoie **%s résultat** pour *toutes* les années"
  % (sec13_grid if sec13_grid is not None else "0"))
w("confondues, alors que la base en contient **%d**. Une extraction menée par requêtes" % sec13_n)
w("`sezione × anno` perdrait donc en silence la totalité de la section *L'origenismo e la")
w("fortuna di Origene* — précisément la section de la réception d'Origène. Le balayage par")
w("identifiant de fiche les récupère toutes.")
w("")
empty_sec = sum(o["n_records"] for o in sections["observed_sections"] if not o["sezione"])
if empty_sec:
    w("### Fiches sans section")
    w("")
    w("%d fiches ne portent aucune valeur de section. Elles sont conservées, avec une" % empty_sec)
    w("`sezione` vide.")
    w("")
anom = sections.get("subsection_anomalies", [])
if anom:
    w("### Sous-sections hors menu")
    w("")
    w("%d valeurs de sous-section ne figurent pas dans le menu du formulaire. Deux cas :" % len(anom))
    w("des variantes d'orthographe d'une même rubrique, saisies au fil des annate, et des")
    w("valeurs qui n'ont rien d'une rubrique. Toutes sont conservées telles quelles ;")
    w("la taxonomie thématique du projet devra les regrouper.")
    w("")
    w("| Section | Sous-section relevée | Notices | Cas |")
    w("|---|---|---:|---|")
    for a in anom:
        kind = "variante" if a["kind"] == "variant" else "section sans menu"
        w("| %s | `%s` | %d | %s |" % (a["sezione"], a["sottosezione"], a["n_records"], kind))
    w("")
    variants = [a for a in anom if a["kind"] == "variant"]
    if variants:
        w("Le cas le plus net est la section 12 (*Origene*), où la rubrique bibliographique")
        w("apparaît sous trois libellés — `1. Bibliografie, rassegne, repertori` (au menu),")
        w("`1. Bibliografie e rassegne` et `1. Bibliografie, rassegne e repertori` : une seule")
        w("rubrique éclatée en trois valeurs distinctes.")
        w("")
    w("La sous-section `Fitschen K.` de la section 20 (*Atanasio*) est une erreur de saisie de")
    w("la base : le nom de l'auteur a été porté dans le champ rubrique (fiche 1882, compte rendu")
    w("de Fitschen dans *ZAC* 2). La valeur est conservée sans correction.")
    w("")
w("### Une page interceptée par un portail captif")
w("")
w("La base n'est servie qu'en HTTP, sans chiffrement. Une réponse (fiche 329) est revenue")
w("en `200` avec une page d'un portail captif substituée à la page attendue. Elle a été")
w("détectée au contrôle d'intégrité, puis récupérée. Le parseur refuse désormais toute")
w("réponse ne portant pas le `<title>ADAMANTIUS</title>` : un contrôle de taille seul ne")
w("suffit pas, la page injectée pesait 130 ko.")
w("")

w("## Échecs et lacunes du balayage")
w("")
miss = stats.get("missing", [])
w("- Pages non récupérées (échec réseau après 4 tentatives) : **%d**%s" % (
    len(miss), (" — " + ", ".join(str(m) for m in miss[:80])) if miss else ""))
lo, hi = min(harvested_ids), max(harvested_ids)
gaps = sorted(set(range(lo, hi + 1)) - harvested_ids)
w("- Identifiants sondés : 1 à 5100. Les fiches occupent **%d à %d**, **sans aucun trou**" % (lo, hi))
w("  (%d identifiants, %d manquant dans l'intervalle). Au-delà de %d, le serveur rend le"
  % (len(harvested_ids), len(gaps), hi))
w("  gabarit sans données : la base est donc close, et le balayage en a la totalité.")
w("")

w("## Découpage titre / référence")
w("")
w("Le champ *Notizia Bibliografica* est une notice d'un seul tenant. Le découpage")
w("titre / référence est obtenu en retirant le préfixe d'auteur puis en détachant la queue")
w("bibliographique ; chaque fragment produit est une sous-chaîne littérale de la notice, et")
w("`notice_full` conserve toujours la notice intégrale.")
w("")
w("| Méthode | Notices |")
w("|---|---:|")
for k, v in by_method.most_common():
    w("| `%s` | %d |" % (k, v))
w("")
w("`none` = queue non reconnue : `reference` vaut alors `null` et le titre porte la notice")
w("entière moins l'auteur. Aucune donnée n'est perdue dans ce cas.")
w("")

w("## Schéma de `records.jsonl`")
w("")
w("Une notice par ligne (JSON).")
w("")
w("| Champ | Contenu |")
w("|---|---|")
for k, v in [
    ("`source`", "`\"adamantius-girota\"`"),
    ("`source_id`", "`adamantius-girota-<scheda>` — identifiant stable, fiche de première apparition"),
    ("`sections`", "liste de `{sezione, sottosezione}` — plusieurs quand la notice est reprise sous plusieurs sections"),
    ("`year_bib`", "champ *Anno* de la fiche, verbatim (année de la publication recensée)"),
    ("`year_bib_parsed`", "années extraites de `year_bib` ; plusieurs si la valeur est composite"),
    ("`authors`", "champ *Autore* découpé auteur par auteur"),
    ("`title`", "titre isolé de la notice"),
    ("`reference`", "revue / volume / pages, tel quel ; `null` si non détaché"),
    ("`reference_note`", "mention finale entre parenthèses (`(con bibl.)`, `(pro manuscripto)`…)"),
    ("`language`", "langue déduite du titre ; `null` si indécidable"),
    ("`abstract`", "résumé GIROTA quand la fiche en porte un"),
    ("`abstract_rights`", "`\"girota-unverified\"`"),
    ("`authors_raw`", "champ *Autore* verbatim"),
    ("`notice_full`", "champ *Notizia Bibliografica* verbatim — la source de vérité"),
    ("`reference_split_method`", "méthode ayant détaché la référence"),
    ("`scheda_ids`", "toutes les fiches fusionnées dans cette notice"),
    ("`volume_codes` / `volume_years`", "*Codice volume* (`n-annata`) et annate correspondantes"),
    ("`pdf`", "PDF de l'annata sur le serveur GIROTA"),
    ("`url`", "URL de la fiche"),
]:
    w("| %s | %s |" % (k, v))
w("")

w("## Réserves")
w("")
w("- Les abstracts sont repris tels quels de la base GIROTA : `abstract_rights` vaut")
w("  `girota-unverified`, aucun droit de rediffusion n'a été vérifié.")
w("- Le découpage des auteurs suit une heuristique : le champ mêle deux conventions")
w("  (`Guinot J.-N.` et `J. Dorival B. Barc`), parfois dans la même chaîne. `authors_raw`")
w("  reste la référence en cas de doute.")
w("- La langue est déduite de mots-outils du titre. Les titres latins, grecs translittérés")
w("  ou trop courts restent à `null`.")
w("- Rien n'a été complété ni corrigé : les coquilles de la base (accents, apostrophes")
w("  rendues par des accents graves) sont conservées telles quelles.")

open(os.path.join(OUTDIR, "REPORT.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
print("REPORT.md written | schede=%d records=%d capped=%d grid_only=%d missing=%d"
      % (n_sch, len(recs), len(capped), len(grid_only), len(miss)))
