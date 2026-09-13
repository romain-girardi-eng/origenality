# data : couche de données du site public

Les fichiers que les pages lisent, et ceux qui permettent de les reconstruire. Aucun ne s'édite à la main : chacun sort d'un outil nommé ci-dessous, et les chiffres de ce fichier sont écrits par `site/tools/build_summary_figures.py`, comme ceux des pages.

## Périmètre

<!-- FIGURES:data-perimeter -->Corpus fédéré de 8 libellés de source, interrogés par la notice d'autorité d'Origène (GND 118590235) et ses équivalents nationaux : 2 582 notices de catalogue, réunies en 2 490 grappes d'œuvre par la fusion (92 doublons réunis). Notices par source, avant fusion : `ixtheo-k10plus` 1 409, `gnomon-gbd` 354, `k10plus` 350, `sudoc` 212, `b3kat` 130, `dnb` 51, `loc` 50, `bnf` 26. Les chiffres publiés comptent les grappes `core` et `partial` (2 209) ; 280 grappes `marginal` sont listées sans être comptées, et 1 grappe est tenue hors compte. Les 1 441 éditions, traductions et témoins manuscrits des œuvres d'Origène forment la couche primaire (`primary-layer.jsonl`), comptée dans aucun chiffre.<!-- /FIGURES:data-perimeter -->

La règle de comptage est la même sur toutes les surfaces (`semantic/README.md`, § 2) : les chiffres publiés comptent les grappes `core` et `partial`. Une grappe `marginal` est retrouvée par la recherche et listée, jamais comptée ; une grappe `none` reste indexée et n'entre dans aucun chiffre.

## Reconstruction, dans l'ordre

```bash
python3 site/tools/build_public_snapshot.py     # data/site-records.jsonl ; lit la moisson de relecture là où elle est gardée
python3 site/tools/build_primary_layer.py       # codes de langue de la couche primaire
python3 pipeline/merge_dedup.py --input-jsonl data/site-records.jsonl --out-dir data/site-merged
python3 site/tools/merge_site_tags.py           # data/site-merged/tags.jsonl
python3 pipeline/build_site_data.py             # graph, stats, abstracts, META
python3 site/tools/build_cite_data.py           # data/cite.json, juste après build_site_data
python3 site/tools/backfill_record_urls.py
python3 site/tools/build_semantic.py            # site/assets/semantic.json, puis les chiffres des pages
python3 site/tools/build_weights.py             # site/assets/weights.json
python3 site/tools/build_manifest.py            # data/BUILD.json
python3 scripts/stamp_assets.py                 # empreintes ?v= des feuilles et des scripts
python3 scripts/build_seo_assets.py             # sitemap.xml, llms.txt, sitemap-dates.json ; après les empreintes
```

Une correction de `corrections.json` qui change l'année d'une notice d'autorité s'applique avant le contrôle d'identité de la relecture, qui compare la notice relue à l'année du snapshot. L'ordre est donc : reconstruire le snapshot avec la correction, relire le cache sans réseau (`python3 scripts/hydrate_authority_records.py --reparse`), reconstruire le snapshot, puis tout ce qui suit.

`evidence/build_evidence.py` écrit `data/evidence.json` depuis l'arbre de travail, qui seul détient les textes intégraux.

## Le snapshot d'entrée : `site-records.jsonl`

Une ligne par notice de catalogue, avant fusion, avec sa source et son identifiant. Le fichier combiné de la moisson par autorité du 22 août 2026 n'existe plus ; le snapshot en est une reconstruction, et chaque ligne dit d'où viennent ses vedettes et son contenant, dans `subjects_container_basis` :

- `catalogue-record` : la notice IxTheo elle-même, dont la moisson complète est conservée dans l'arbre de travail. Toutes les vedettes 650 et 689, le contenant avec son type MARC, la relation `about` ou `both`.
- `catalogue-record-refetched` : une notice des sept autres libellés de source (K10plus, Sudoc, B3Kat, Gnomon GBD, DNB, Library of Congress, BnF), demandée de nouveau à son catalogue par `scripts/hydrate_authority_records.py` et retenue parce que son titre et son année concordent avec la ligne. Vedettes, chaînes et contenant avec son type viennent de cette notice ; la relation reste celle de la ligne.
- `public-projection` : une notice que ce contrôle d'identité a refusée ou qu'aucun catalogue n'a rendue. Seul le graphe publié le 22 août en garde une trace, et il ne portait que les vedettes utilisées par au moins 3 notices et les contenants utilisés par au moins 5 ; les vedettes et les contenants sous ces seuils manquent pour elle.

<!-- FIGURES:data-basis -->Répartition des 2 582 notices du snapshot : `catalogue-record` : 1 409 notices (`ixtheo-k10plus` 1 409) ; `catalogue-record-refetched` : 1 173 notices (`gnomon-gbd` 354, `k10plus` 350, `sudoc` 212, `b3kat` 130, `dnb` 51, `loc` 50, `bnf` 26), relues dans leur catalogue le 13 septembre 2026.<!-- /FIGURES:data-basis -->

Conséquence à lire avec les chiffres : `stats.totals.distinct_subjects` et `distinct_containers` sous-comptent les notices en `public-projection`, et elles seules. `BUILD.json` donne la couverture de chaque champ (`field_coverage`) et, dans `limitation`, le nombre de notices concernées. L'outil refuse d'écrire un snapshot dont un champ perd plus de 1 % de ses notices (`--allow-coverage-drop` pour une raison déclarée), et une reconstruction sans la moisson de relecture garde les lignes `catalogue-record-refetched` telles quelles. La moisson de relecture est lue par défaut quand elle est sur le disque (`--no-authority` pour s'en passer) ; chaque ligne qu'elle a donnée porte le jour où sa notice a été lue (`subjects_container_fetched`), et `META.refetched` publie le plus récent. `--check` dit combien de lignes il a pu dériver de nouveau, et de quelles entrées. Un clone n'a aucune des deux moissons : le contrôle n'y vérifie que la structure des lignes, l'unicité de leurs clés et les corrections, il échoue quand il ne dérive aucune ligne, et le selftest le lance avec `--structure-only`, qui le dit.

Les titres viennent eux aussi du graphe publié, où ils étaient tronqués à 120 caractères. Ils ne sont pas rallongés : l'identifiant d'une grappe se calcule sur le titre, et le changer renumérotait la carte.

## Fichiers

| Fichier | Contenu | Écrit par |
|---|---|---|
| `graph.json` | le graphe : publications, auteurs, sujets, contenants | `pipeline/build_site_data.py` |
| `stats.json` | les séries de l'Observatoire | `pipeline/build_site_data.py` |
| `abstracts.json` | les résumés, chacun avec sa base et le lien vers sa notice | `pipeline/build_site_data.py` |
| `cite.json` | pour l'export des références (BibTeX, RIS, CSL-JSON) : contenant avec son type, éditeur, DOI et ISBN par grappe | `site/tools/build_cite_data.py` |
| `META.json` | provenance, périmètre, sources et licences | `pipeline/build_site_data.py` |
| `BUILD.json` | empreintes des fichiers de la construction et couverture des champs | `site/tools/build_manifest.py` |
| `site-records.jsonl` | le snapshot d'entrée, une notice par ligne | `site/tools/build_public_snapshot.py` |
| `site-tags.jsonl` | les tags par notice source | reconstruction du 22 août |
| `site-merged/` | les grappes d'œuvre, leurs tags et les comptes rendus de fusion | `pipeline/merge_dedup.py`, `site/tools/merge_site_tags.py` |
| `corrections.json` | corrections curées, chacune avec sa preuve et son motif | à la main, appliquées par le snapshot |
| `abstract-anomalies.json` | résumés écartés (étiquette vide, texte intégral) | reconstruction du 22 août |
| `citation-counts.json` | comptes de citations par identifiant | `site/tools/build_weights.py` le lit |
| `evidence.json` | projection publique des prises de position ancrées | `evidence/build_evidence.py` |
| `sitemap-dates.json` | empreinte SHA-256 et date de dernier changement de chaque document de `sitemap.xml` | `scripts/build_seo_assets.py` |
| `primary-layer.jsonl`, `primary-layer-summary.json` | éditions, traductions et témoins manuscrits des œuvres d'Origène | moisson du 22 août ; langues : `site/tools/build_primary_layer.py` |

---

## graph.json

JSON compact, sans indentation.

```
{
  "generated": "AAAA-MM-JJ",                 # date de construction
  "legend":     { "k": {…}, "r": {…} },      # libellés des genres de nœud et d'arête
  "thresholds": { "subject_min_publications", "container_min_publications" },
  "counts":     { "nodes", "edges", "nodes_by_kind", "edges_by_relation" },
  "nodes":      [ … ],
  "edges":      [ … ]
}
```

### Nœuds

`nodes` est un tableau ordonné ; **les arêtes référencent les nœuds par leur indice dans ce tableau**, pas par leur `id`. Les publications occupent les premières positions, dans l'ordre du corpus fusionné ; viennent ensuite les auteurs, les sujets, les contenants. `deg` est le degré du nœud, précalculé pour le dimensionnement visuel.

| `k` | champs |
|---|---|
| `pub` | `id` (`p:<clé>`), `ppn` (clé de grappe `OR…`, stable d'une construction à l'autre), `title` (tronqué à 120 caractères), `year` (entier ou `null`), `lang`, `type`, `rel` (`about`, `both`, ou `null` quand la source ne code pas la relation), `src` (libellés des sources de la grappe), `url` (notice retenue), `source_ids` (chaque notice source : `source`, `id`, `url`), `doi`, `pub` (éditeur), `isbn`, `deg` |
| `author` | `id` (`a:<slug>`), `label`, `deg` |
| `subject` | `id` (`s:<slug>`), `label`, `deg` |
| `container` | `id` (`c:<slug>`), `label`, `ctype` (`host` ou `series`), `deg` |

`lang` est un code ISO 639-1, ou ISO 639-2/3 quand aucun code 639-1 n'existe (`grc`, `syr`, `mul`, `und`, `zxx`…) ; chaîne vide si la notice ne code pas sa langue. `doi`, `pub` et `isbn` sont absents quand la notice ne les porte pas. Le gabarit d'adresse de chaque source est dans `META.sources_present[].record_url_pattern`.

### Arêtes

```
{ "s": 42, "t": 1704, "r": "aut" }
```

`s` et `t` sont des indices de nœud, `s` toujours une publication. `r` vaut `aut` (auteur), `sub` (sujet) ou `in` (contenant). Une paire (source, cible) n'apparaît qu'une fois.

---

## stats.json

Deux populations, que la clé `population` nomme. Les séries du premier niveau comptent toutes les grappes gardées (`core`, `partial` et `marginal`). La clé `counted` porte les mêmes séries (`totals`, `by_year`, `by_decade`, `by_format`, `by_language`, `top_subjects`, `top_containers`) calculées sur les seules grappes `core` et `partial` : c'est la population que comptent l'Observatoire et tous les chiffres publiés. Rien n'est estimé ni lissé, et rien n'obéit **aux seuils du graphe**.

- `totals` : grappes, auteurs, sujets et contenants distincts, amplitude chronologique, grappes sans année, grappes antérieures au début des séries, grappes avec DOI, avec ISBN, avec éditeur.
- `by_year` : `years`, `total` aligné dessus, et `by_language`, une série par langue parmi les plus fréquentes. Le champ `note` dit ce que la série laisse dehors.
- `by_decade` : décennies pleines depuis 1900, dernière décennie tronquée.
- `by_format` : types de document normalisés, ordre décroissant.
- `by_language` : toutes les langues, code plus libellé anglais et français. Le code `none` regroupe les grappes sans langue codée. Un code sans libellé arrête la construction.
- `top_subjects`, `top_containers` (avec leur `type`).
- `graph_thresholds` : rappel des seuils du graphe, pour que l'écart entre les deux fichiers soit lisible.

---

## META.json

- `source`, `scope`, `license`, `federated`.
- `harvested` : date de la moisson ; `generated` : date de la construction.
- `refetched` : le jour où les vedettes et les contenants des notices d'autorité ont été relus dans leur catalogue, c'est-à-dire le plus récent `fetched_at` de ces notices, recalculé à chaque construction depuis `site-records.jsonl` ; `refetched_records` en donne le nombre et `refetched_basis` la règle.
- `records` : grappes publiées. `records_harvested_total` : notices de catalogue avant fusion, avec `records_harvested_basis`.
- `sources_present` : libellé, licence et gabarit d'adresse de chaque source, et le nombre de grappes qui portent au moins une de ses notices (`sources_present_basis` : une grappe multi-source compte sous chacune). `sources_harvested` : notices par source, avant fusion.
- `excluded` : `relation_by` compte les éditions mises à part, lues dans la couche primaire (`source`, `basis`) ; elles ne font pas partie de `records_harvested_total`.
- `deduplication` : notices sources, grappes, doublons réunis.
- `summaries` : régime, contact et couverture des résumés.
- `tags`, `build_manifest`, `input_status`, `relevance_published`.

---

## Régime des données

**Les résumés sont publiés, avec leur attribution.** La décision du 16 août 2026 remplace le régime « métadonnées factuelles seules » : un résumé rend le corpus utilisable, et le refuser rendait le site plus pauvre sans protéger personne. Chaque résumé publié nomme la base qui l'a écrit et porte un lien vers la notice d'origine ; tout ayant droit obtient son retrait sur simple demande, à l'adresse inscrite dans `abstracts.json` et sur la page Crédits. Le régime complet et la table des bases créditées sont dans `DATA_POLICY.md`, et `scripts/check_release.py` refuse un dump dont un résumé ne se résout pas en lien.

Les résumés voyagent dans `abstracts.json`, chargé après le premier rendu. Le générateur refuse d'écrire dans `graph.json`, `stats.json` ou `META.json` une clé `abstract`, `abstract_rights`, `abstract_inverted_index` ou `summary`, à quelque profondeur que ce soit.

Champs publiés : titre, auteurs, année, langue, contenant, éditeur, DOI, ISBN, vedettes-matière, format, relation, et le résumé avec sa base et son lien.

---

## Décisions de nettoyage

**Auteurs.** Dédoublonnage par nom normalisé : diacritiques retirés, minuscules, espaces resserrés, ponctuation de fin coupée. La normalisation est volontairement courte : aucune réconciliation d'initiales ni de translittérations, qui fusionnerait des homonymes. Le libellé retenu est la forme la plus fréquente.

Sont écartés des nœuds « auteur » :

- les collectivités et les congrès (`type` différent de `person`) : ce sont des mentions de responsabilité, pas des auteurs ;
- les personnes dont tous les rôles, dans la notice de catalogue, sont non auctoriaux. La liste est dans `pipeline/fields.py`, et le snapshot comme le graphe la lisent. Écartés en MARC21 (`$4`) : `prt` imprimeur, `pbl` éditeur commercial, `bsl` libraire, `sll` vendeur, `dst` distributeur, `egr` graveur, `bnd` relieur, `fmo` ancien possesseur, `own` possesseur, `dnr` donateur, `fnd` financeur, `spn` commanditaire, `dgg` institution de soutenance, `isb` organisme émetteur, `wpr` préfacier, `dte` dédicataire, `rcp` destinataire. Écartés en UNIMARC (`$4`) : 110, 120, 160, 280, 295, 310, 320, 350, 390, 400, 475, 530, 610, 620, 650, 660, 723, 753, 760. Et les mentions en clair équivalentes (`$e`) quand la notice ne code pas le rôle. Tout autre rôle est gardé (auteur, directeur de publication, traducteur, collaborateur, personne honorée `hnr`…), comme toute personne sans rôle codé. Le snapshot garde les noms écartés, avec leurs rôles, dans `authors_not_credited` ;
- Origène lui-même (GND 118590235), auteur des volumes `both`. Relié à tout le corpus, il ne ferait qu'un moyeu sans information.

**Homonymes.** Quand un nom normalisé porte plusieurs identifiants GND, il est éclaté par GND, et le libellé du nœud porte l'identifiant en clair (`Gregorius (GND 118718711)`). La forme nue « Gregorius » recouvre Grégoire d'Elvire et un autre Grégoire : fusionner sur le nom reviendrait à confondre deux Pères. Un nœud d'auteur en trop se voit et se corrige ; une fusion de deux personnes se lit comme un fait.

**Sujets.** Les champs 650 (`subjects`) et 689 (`subject_chains`, l'indexation par chaînes propre à IxTheo) sont versés dans un même vocabulaire, dédoublonnés par notice. Chaque vedette est réduite à sa tête :

- découpage sur `;` (vedettes composites) ;
- coupe à la première subdivision LCSH `--` (`Bible--Criticism--History` devient `Bible`) ;
- coupe à la première barre des hiérarchies BISAC ou RAMEAU (`RELIGION / Christian Theology / Apologetics` devient `RELIGION`) ;
- qualificatifs entre chevrons rendus entre parenthèses (`Caesarea <Palästina>` devient `Caesarea (Palästina)`) ;
- rejet des éléments chronologiques (`Geschichte 200-560`, `30-600`) : ce sont des bornes d'indexation, pas des thèmes ;
- rejet des vedettes de moins de 2 ou de plus de 60 caractères ;
- rejet des formes qui désignent Origène (`Origenes`, `Origen`, `Origene`…) : le sujet du corpus entier n'est pas un thème discriminant. `Origenismus`, en revanche, est conservé.

Les zones de forme ne sont pas des sujets : ni MARC21 655 ni UNIMARC 608 (« Thèses et écrits académiques », « Actes de congrès », « Ouvrages avant 1800 ») n'entrent dans les vedettes relues.

Le vocabulaire reste celui des catalogues, majoritairement allemand, avec des doublons de langue (`Theologie` et `Theology` sont deux nœuds). Aucune traduction ni alignement n'a été tenté : ce serait une décision éditoriale, pas un nettoyage.

**Seuils.** Un sujet devient un nœud du graphe à partir de 3 publications, un contenant à partir de 5 (`graph.thresholds`). Sans seuil, le graphe serait une poussière de feuilles à une arête. `stats.json` compte et classe sans seuil.

**Contenants.** Dédoublonnage par titre normalisé, ce qui regroupe les variantes de casse. `ctype` distingue le champ MARC d'origine : `host` (773, revue ou volume collectif) et `series` (490/830, collection). MARC ne sépare pas la revue du volume collectif : « Adamantius » et « Origenes in den Auseinandersetzungen des 4. Jahrhunderts » sont tous deux `host`. Un contenant sans type à la source compte comme `host`.

Le titre du contenant est coupé de la mention de responsabilité que la notice recopie à sa suite (`Biblica / a Pontificio Instituto Biblico in lucem editi in Urbe` devient `Biblica`) : un directeur, un éditeur scientifique, une liste de personnes, ou une collectivité seule quand le titre restant compte au moins trois mots ou figure tel quel sur une autre notice. Une collectivité reste attachée au titre court qu'elle seule distingue (`Skrifter / Det Norske Videnskaps-Akademi`), et ni une sous-collection (`Vetera Christianorum / Quaderni`) ni une mention de collection entre crochets ne sont coupées. Une citation libre (`In: … (Hrsg.): Die Welt als Bild …, S. 69-79`) est réduite au titre hôte qu'elle nomme avec certitude, ou retirée quand ce titre ne s'isole pas. Le titre tel que catalogué reste dans `container_as_catalogued`.

**Années.** Les notices sans année et celles antérieures au début des séries sortent des séries chronologiques, mais restent comptées dans les totaux, les formats et les langues (`stats.totals.year_unknown`, `records_before_series_start`). Une date contredite par une autre notice de la même publication est corrigée dans `corrections.json`, avec sa preuve.

**Nœuds isolés.** Une publication sans auteur de personne, sans sujet au-dessus du seuil et sans contenant au-dessus du seuil reste dans le graphe, sans arête (`deg` = 0).

---

## Autres entrées du générateur

`pipeline/build_site_data.py` prend n'importe quel JSONL au schéma de moisson : `--input`, `--out-dir`, `--min-subject`, `--min-container`, `--source-label`, `--scope`, `--harvested`, `--generated`. Il accepte indifféremment `format` ou `type`, `subjects`, `subject_chains`, `descriptors` ou `topics`, une liste d'auteurs faite de chaînes ou d'objets, un contenant en chaîne ou en objet `{title, type}`.

**Sur un corpus fédéré, `--tags` est obligatoire et la conservation est fermée par défaut.** Une moisson à source unique est bâtie sur une notice d'autorité : tout ce qu'elle contient est dans le périmètre. Le corpus fédéré de travail, lui, est majoritairement du bruit. La règle y est donc inverse : une grappe n'entre que si un tag lui reconnaît une pertinence `core`, `partial` ou `marginal`. Pas de tag, pas d'entrée ; pas de fichier de tags, pas de construction du tout.

`--overview` produit `data/derived/sources_overview.json` : comptes bruts par moisson, à usage interne. Ce fichier ne va pas sur le site.
