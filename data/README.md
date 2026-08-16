# site/data — couche de données du site public

Quatre fichiers, générés par `pipeline/build_site_data.py`, consommés directement
par le front statique : `graph.json` (le graphe), `stats.json` (les séries de
l'Observatoire), `abstracts.json` (les résumés, chacun avec sa base et le lien vers
sa notice) et `META.json` (la provenance et le périmètre). Ils sont recalculables
en quelques secondes à partir de la moisson ; ne pas les éditer à la main.

```bash
python3 pipeline/build_site_data.py
```

## Périmètre v0

IxTheo / K10plus seul (licence CC0), moisson du 15 août 2026 : 2 116 notices,
dont 1 632 portent sur Origène (`relation` = `about` ou `both`). Les 484 notices
`by` sont des éditions des œuvres d'Origène : sources primaires, écartées du
graphe. Les autres moissons présentes dans `data/raw/` (OpenAlex, Crossref,
Semantic Scholar, BIBP, Adamantius, francophone, SBN, Dialnet) ne sont pas
branchées : filtrage de pertinence non fait, licences non tranchées.

Attention au décompte : `about` 1 585 + `both` 47 = **1 632**. Le chiffre 1 632
est déjà l'ensemble « sur Origène » ; y rajouter les 47 `both` compterait deux
fois les volumes qui sont à la fois édition et recueil d'études.

## Régime des données

**Les résumés sont publiés, avec leur attribution.** La décision du 16 août 2026
remplace le régime « métadonnées factuelles seules » décrit ici jusqu'à
l'itération 5 : un résumé rend le corpus utilisable, et le refuser rendait le
site plus pauvre sans protéger personne. Chaque résumé publié nomme la base qui
l'a écrit et porte un lien vers la notice d'origine ; tout ayant droit obtient
son retrait sur simple demande, à l'adresse inscrite dans `abstracts.json` et
sur la page Crédits. Le régime complet et la table des bases créditées sont dans
`DATA_POLICY.md`, et `scripts/check_release.py` refuse un dump dont un résumé
ne se résout pas en lien.

Les résumés voyagent dans `abstracts.json`, chargé après le premier rendu : le
graphe n'a pas à attendre des pages de prose pour s'afficher. Les trois autres
fichiers n'en portent aucun, et un contrôle le vérifie à l'écriture — le
générateur refuse d'écrire dans `graph.json`, `stats.json` ou `META.json` une clé
`abstract`, `abstract_rights`, `abstract_inverted_index` ou `summary`, à quelque
profondeur que ce soit.

Champs publiés : titre, auteurs, année, langue, contenant, éditeur, DOI, ISBN,
vedettes-matière, format, relation, et le résumé avec sa base et son lien.

---

## graph.json

Charge utile de rendu, ~607 Ko, JSON compact (sans indentation).

```
{
  "generated": "2026-08-15",
  "legend":     { "k": {…}, "r": {…} },      # libellés des genres de nœud et d'arête
  "thresholds": { "subject_min_publications": 3, "container_min_publications": 5 },
  "counts":     { "nodes", "edges", "nodes_by_kind", "edges_by_relation" },
  "nodes":      [ … ],
  "edges":      [ … ]
}
```

### Nœuds

`nodes` est un tableau ordonné ; **les arêtes référencent les nœuds par leur
indice dans ce tableau**, pas par leur `id`. Les 1 632 publications occupent les
positions 0 à 1 631, dans l'ordre du fichier source ; viennent ensuite les
auteurs, les sujets, les contenants.

Champ `deg` sur tous les nœuds : degré dans le graphe, précalculé pour le
dimensionnement visuel. Pour un auteur, un sujet ou un contenant, il vaut le
nombre de publications rattachées.

| `k` | champs |
|---|---|
| `pub` | `id` (`p:<ppn>`), `title` (tronqué à 120 caractères, ellipse finale), `year` (entier ou `null`), `lang` (code ISO 639-2/B, chaîne vide si non codé), `type` (format IxTheo), `rel` (`about` ou `both`), `ppn`, `doi` (absent si aucun), `deg` |
| `author` | `id` (`a:<slug>`), `label`, `deg` |
| `subject` | `id` (`s:<slug>`), `label`, `deg` |
| `container` | `id` (`c:<slug>`), `label`, `ctype` (`host` ou `series`), `deg` |

La notice complète se retrouve sur `https://ixtheo.de/Record/<ppn>` (motif donné
dans `META.json`).

### Arêtes

```
{ "s": 42, "t": 1704, "r": "aut" }
```

`s` et `t` sont des indices de nœud, `s` toujours une publication. `r` vaut
`aut` (→ auteur), `sub` (→ sujet) ou `in` (→ contenant). Pas de doublon : une
paire (source, cible) n'apparaît qu'une fois.

---

## stats.json

Tout est calculé sur les 1 632 publications, rien n'est estimé ni lissé.

- `totals` — notices, auteurs distincts, sujets distincts, contenants distincts,
  amplitude chronologique, notices sans année, notices antérieures à 1850,
  notices avec DOI, notices avec ISBN.
- `by_year` — `years` (1850 à 2026), `total` aligné dessus, et `by_language`,
  une série par langue du top 6 (`eng`, `ger`, `ita`, `fre`, `spa`, `lat`).
  Le champ `note` rappelle ce que la série laisse dehors.
- `by_decade` — décennies pleines de 1900 à 2020, série tronquée à mi-2026.
- `by_format` — formats IxTheo (Article, Book, Review, Dictionary entry/article…),
  ordre décroissant.
- `by_language` — toutes les langues, code ISO plus libellé anglais et français.
  Le code `none` regroupe les 127 notices sans langue codée à la source.
- `top_subjects` — 30 vedettes, **sans seuil** (contrairement au graphe).
- `top_containers` — 20 contenants avec leur `type`.
- `graph_thresholds` — rappel des seuils appliqués au graphe, pour que l'écart
  entre les deux fichiers soit lisible.

Contrôle de cohérence : `sum(by_year.total)` = 1 569 = 1 632 − 52 notices sans
année − 11 notices antérieures à 1850.

---

## META.json

Provenance : source et licence, date de moisson, nombre de notices publiées,
périmètre (autorité GND 118590235), total moissonné, notices écartées et motif,
liste des champs publiés et des champs retenus en interne, motif d'URL de notice.

---

## Décisions de nettoyage

**Auteurs.** Dédoublonnage par nom normalisé : diacritiques retirés, minuscules,
espaces resserrés, ponctuation de fin coupée. La normalisation est volontairement
courte — aucune réconciliation d'initiales ni de translittérations, qui
fusionnerait des homonymes. Sur cette moisson, elle ne regroupe d'ailleurs aucune
paire de formes de surface distinctes : les 985 noms normalisés de la moisson
donnent 937 nœuds, l'écart venant des exclusions et de la levée d'ambiguïté
ci-dessous. Le libellé retenu est la forme la plus fréquente.

Sont écartés des nœuds « auteur » :

- les collectivités et les congrès (`type` ≠ `person`) — colloques origéniens,
  académies, universités : ce sont des mentions de responsabilité, pas des
  auteurs ;
- les rôles MARC `pbl`, `prt`, `dgg`, `isb`, `wpr` (éditeur commercial,
  imprimeur, institution de soutenance) ;
- Origène lui-même (GND 118590235), auteur des 47 volumes `both`. Relié à tout
  le corpus, il ne ferait qu'un moyeu sans information.

**Homonymes.** Onze noms normalisés portent plus d'un identifiant GND dans la
moisson ; après exclusion des congrès et des collectivités, il en reste quatre :
Cattaneo, Gregorius, Molland, Ferraro. Le cas « Gregorius » tranche la question —
la forme nue recouvre Grégoire d'Elvire (GND 118718711), auteur des *Gregorii
Iliberritani episcopi quae supersunt*, et un autre Grégoire (GND 118541919) :
fusionner sur le nom reviendrait à confondre deux Pères. Règle retenue : quand un
nom normalisé porte plusieurs GND, il est éclaté par GND, et le libellé du nœud
porte l'identifiant en clair (`Gregorius (GND 118718711)`). Le coût est trois
dédoublements probablement abusifs — Molland et Ferraro sont visiblement des
doublons d'autorité (même titre, deux notices), Cattaneo est incertain — contre
une confusion de personnes évitée. Un nœud d'auteur en trop se voit et se
corrige ; une fusion de deux Pères se lit comme un fait.

**Sujets.** Les champs 650 (`subjects`, 34 % des notices) et 689
(`subject_chains`, l'indexation par chaînes propre à IxTheo, 70 %) sont versés
dans un même vocabulaire, dédoublonnés par notice. Chaque vedette est réduite à
sa tête :

- découpage sur `;` (vedettes composites) ;
- coupe à la première subdivision LCSH `--` (`Bible--Criticism--History` →
  `Bible`) ;
- coupe à la première barre des hiérarchies BISAC ou RAMEAU
  (`RELIGION / Christian Theology / Apologetics` → `RELIGION`) ;
- qualificatifs entre chevrons rendus entre parenthèses (`Caesarea <Palästina>`
  → `Caesarea (Palästina)`) ;
- rejet des éléments chronologiques (`Geschichte 200-560`, `30-600`) : ce sont
  des bornes d'indexation, pas des thèmes ;
- rejet des vedettes de moins de 2 ou de plus de 60 caractères ;
- rejet des formes qui désignent Origène (`Origenes`, `Origen`, `Origene`…),
  présentes sur 1 120 notices — le sujet du corpus entier n'est pas un thème
  discriminant. `Origenismus`, en revanche, est conservé.

Le vocabulaire reste celui d'IxTheo, majoritairement allemand, avec des doublons
de langue (`Theologie` et `Theology` sont deux nœuds). Aucune traduction ni
alignement n'a été tenté : ce serait une décision éditoriale, pas un nettoyage.

**Seuils.** Un sujet devient un nœud à partir de 3 publications (371 nœuds sur
1 527 vedettes distinctes), un contenant à partir de 5 (52 nœuds sur 672). Sans
seuil, le graphe serait une poussière de feuilles à une arête. `stats.json`
donne les palmarès sans seuil.

**Contenants.** Dédoublonnage par titre normalisé, ce qui regroupe les variantes
de casse (`Oxford early Christian studies` et `Oxford Early Christian Studies`).
`ctype` distingue le champ MARC d'origine : `host` (773 — revue ou volume
collectif) et `series` (490/830 — collection). MARC ne sépare pas la revue du
volume collectif : « Adamantius » (54 notices) et « Origenes in den
Auseinandersetzungen des 4. Jahrhunderts » (35) sont tous deux `host`.

**Années.** 52 notices sans année et 11 antérieures à 1850 (la plus ancienne :
1677) sont hors des séries chronologiques, mais comptées dans les totaux, les
formats et les langues.

**Nœuds isolés.** Six publications n'ont ni auteur de personne, ni sujet
au-dessus du seuil, ni contenant au-dessus du seuil. Elles restent dans le
graphe, sans arête (`deg` = 0).

---

## Branchement du corpus fédéré

Le générateur prend n'importe quel JSONL au schéma de moisson :
`--input data/merged/corpus.jsonl`, `--out-dir`, `--min-subject`,
`--min-container`, `--source-label`, `--scope`, `--harvested`. Il accepte
indifféremment `format` ou `type`, `subjects`, `subject_chains`, `descriptors`
ou `topics`, une liste d'auteurs faite de chaînes ou d'objets.

**Sur un corpus fédéré, `--tags` est obligatoire et la conservation est
fermée par défaut.** Une moisson à source unique est bâtie sur une notice
d'autorité : tout ce qu'elle contient est dans le périmètre, et une notice sans
champ `relation` y est retenue. Le corpus fédéré, lui, est majoritairement du
bruit — la vague de tags en classe la plus grande part `none`. La règle y est
donc inverse : une grappe n'entre que si un tag lui reconnaît une pertinence
`core`, `partial` ou `marginal`. Pas de tag, pas d'entrée ; pas de fichier de
tags, pas de construction du tout, et le générateur sort en erreur au lieu de
publier un graphe de bruit.

```bash
python3 pipeline/build_site_data.py \
    --input data/merged/corpus.jsonl \
    --tags semantic/waves/wave2_federated/tags.jsonl \
    --source-label "corpus fédéré Origenality (10 bases)" \
    --scope "publications about Origen of Alexandria" --dry-run
```

Rappel de la règle de comptage, identique sur toutes les surfaces : les chiffres
publiés comptent `core` et `partial`. Les notices `marginal` sont retrouvées par
la recherche et listées, jamais comptées ; les notices `none` ne sont pas
publiées.

`--overview` produit `data/derived/sources_overview.json` : comptes bruts par
moisson (notices, amplitude, notices marquées bruit, DOI, résumés), à usage
interne. Ce fichier ne va pas sur le site.
