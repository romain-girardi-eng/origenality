# Couche sémantique d'Origenality

Cette couche répond à une question simple : **de quoi parle une notice ?** Elle
ne pose pas d'embeddings. Elle attribue à chaque notice des étiquettes prises
dans un vocabulaire fermé, puis range ces étiquettes en un index-arbre que l'on
traverse par raisonnement, à la manière d'un PageIndex. Le voisinage d'un sujet
se lit alors comme un chemin dans l'arbre et un compte de notices, pas comme une
distance dans un espace latent.

Le choix se défend sur trois points. Un identifiant de vocabulaire est stable :
il ne bouge pas quand le modèle change, un vecteur si. Une étiquette est
auditable : on peut demander pourquoi elle a été posée et lire la réponse. Et la
mesure de densité qui fonde le score reste explicable à un jury — « 47 travaux
dans ce périmètre » désigne un nœud nommé, pas un rayon de similarité.

## 1. Contenu

L'arborescence ci-dessous est celle du dépôt de travail. D'une vague, la passe
de publication ne sort que le fichier de tags compacté et un `README.md` qu'elle
écrit depuis ce fichier : le pilote, les notes de conduite et les rapports de
run décrivent la conduite d'une passe plutôt que le jeu de données, et restent
là où ils ont été écrits.

```
semantic/
├── vocabulary/            le vocabulaire contrôlé, versionné, quatre axes
│   ├── works.json         33 œuvres d'Origène + « unspecified »
│   ├── themes.json        16 domaines, 61 feuilles, libellés en/de/fr/it
│   ├── approaches.json    10 angles ou méthodes
│   ├── relevance.json     4 valeurs : core, partial, marginal, none
│   └── tag_record.schema.json   la forme d'un enregistrement de sortie
├── vocabulary_io.py       chargeur unique + fabrique du schéma strict
├── llm_adapter.py         adaptateur neutre (endpoint lu dans l'environnement)
├── tag_notices.py         l'outil de tagging
├── retag_gaps.py          les notices affichées qu'aucune vague n'a taguées
├── pilot/                 le pilote sur les notices IxTheo + le jeu étalon
│   ├── gold_50.jsonl          50 notices taguées à la main (jeu étalon en vigueur)
│   ├── gold_ixtheo_30.jsonl   30 notices, jeu étalon du pilote, conservé comme archive
│   ├── report.py              distributions, taux de reprise, accord
│   └── REPORT.md              le rapport du run
├── waves/                 les vagues, une par répertoire daté
│   ├── wave2_federated/       le corpus fédéré + la reprise (voir son README)
│   ├── wave3_gold50/          la reprise du jeu étalon sous v2.1
│   └── wave4_gap28/           la passe de rattrapage des 28 notices sans classe
└── tree/
    ├── build_topic_tree.py    l'index-arbre (thèmes + œuvres)
    └── navigate.py            navigation par raisonnement, repli déterministe
```

### Les trous d'une vague, et comment ils se referment

Une vague tague des grappes ; le site affiche des notices, et les rattache à
leur grappe au moment du build. Entre les deux, la fusion bouge : une grappe se
scinde et l'un des deux morceaux prend un identifiant neuf, un pré-tri mécanique
en écarte une autre. Le tag ne suit pas, et la notice paraît sans classe — rangée
avec les exclus alors que personne ne l'a jugée. Vingt-huit notices y sont
restées jusqu'au 16 août au soir, dont Grafton et Williams.

`retag_gaps.py` compare le graphe du site, le corpus fusionné et les fichiers de
tags, imprime les manquantes avec le motif de chacune, et écrit le JSONL que le
tagueur reprend. `--check` sort en 1 s'il en reste une. En aval,
`build_semantic.py` refuse d'écrire l'asset du site tant qu'une publication
affichée n'a pas de classe : `--allow-gaps` lève le refus et publie le trou comme
un trou.

## 2. Le vocabulaire

Quatre axes indépendants, chacun un fichier JSON versionné sur un même modèle
d'ontologie : un en-tête `$schema` / `title` / `version`, puis un
dictionnaire d'identifiants portant `label`, `category` ou `domain`, `aliases`,
`status`, et une couleur par catégorie.

**Œuvres** (`works.json`). Les 33 identifiants suivent les sigles et les titres
latins d'usage : `princ`, `cels`, `comm-jo`, `comm-mt`, `comm-rom`, `comm-cant`,
la série des homélies, `orat`, `mart`, `pascha`, `dial`, `hex`, `epist`,
`philoc`, `frag`, `dubia`, plus la valeur par défaut `unspecified`. Les
catégories reprennent les genres littéraires. Chaque entrée porte des alias en
quatre langues, qui servent au repli déterministe et au contrôle : vingt-cinq
sigles ont été confrontés aux titres et vedettes des 1 632 notices IxTheo avant
d'entrer dans le vocabulaire, vingt d'entre eux y sont attestés — `cels` 32
fois, `comm-cant` 26, `comm-rom` 25, `hom-gen` 24, `orat` 19, `princ` 16,
`comm-jo` 14, `hex` et `comm-mt` 10, `pascha` 9, `hom-ps` 8.

**Thèmes** (`themes.json`, version 1.1.0). Deux niveaux, 16 domaines et 61 feuilles. Seules les
feuilles s'écrivent dans un enregistrement ; les domaines servent à l'agrégation
et à l'arbre. La construction croise deux sources et le fichier en garde la
trace :

- les 37 sections publiées par le repertorio Adamantius
  (`data/raw/adamantius/sections.json`) donnent l'axe « auteur et milieu », de
  Philon et Clément aux Cappadociens, à Rufin, à Jérôme, à Évagre et à Maxime ;
  on le retrouve dans les feuilles `philosophy.alexandrian-school`,
  `reception.latin-transmission`, `reception.greek-and-byzantine` ;
- les vedettes et chaînes de vedettes des notices IxTheo
  (`data/raw/ixtheo/records.jsonl`, `relation` dans `about|both`, n = 1 632)
  donnent l'axe doctrinal et exégétique : `Exegese` 32, `Hermeneutik` 32,
  `Rezeption` 29, `Christologie` 25, `Allegorese` 17, `Platonismus` 15,
  `Eschatologie` 13, et dans les chaînes `Apokatastasis` 16, `Willensfreiheit` 8.

Chaque feuille liste dans `ix_headings` les vedettes attestées qui l'ont
motivée, et dans `adamantius_sections` la section correspondante quand il y en a
une. Les libellés allemands et anglais sont les vedettes elles-mêmes lorsqu'il en
existe une ; l'italien suit la formulation d'Adamantius quand elle existe ; le
reste est une traduction fournie par le vocabulaire, et le fichier le dit.

La version 1.1.0 ajoute une feuille, `context.general-presentation`. Le pilote
avait montré que `exegesis.hermeneutic-theory` servait de refuge : elle
recevait la théorie de l'interprétation et, avec elle, tout ce qui était trop
général pour aller ailleurs — un article intitulé « Origen », une notice de
dictionnaire, un chapitre de manuel. La nouvelle feuille prend ces
présentations d'ensemble et laisse `scholarship.research-surveys` à ce pour
quoi elle a été faite, les bilans de recherche et les bibliographies. Les tags
de la vague 1 ne sont pas réécrits : ils portent `themes=1.0.0`, et la vague 2
porte `themes=1.1.0`.

**Angles** (`approaches.json`). Dix valeurs : philologique, exégétique,
doctrinal, historique, réception, comparatif, méthodologique, édition,
recension, synthèse. L'axe sert à distinguer un thème saturé sous un seul angle
d'un thème vraiment retourné dans tous les sens — distinction que le décompte
brut de notices ne rend pas.

**Pertinence** (`relevance.json`). Le classifieur P2 annoncé dans
`CONCEPTION.md` § 4 : `core`, `partial`, `marginal`, `none`. Seuls `core` et
`partial` comptent dans la densité ; `marginal` et `none` restent dans les
données, marqués, et servent à mesurer le bruit de moisson au lieu de le cacher.

> **Règle de comptage — une seule, valable partout.** Toute statistique
> thématique — décompte par domaine, par thème, par œuvre, par angle, densité
> d'un amas, chiffre publié dans l'Observatoire ou dans un article — se calcule
> sur `core` + `partial`, et sur rien d'autre. Une notice `marginal` porte des
> tags valides : elle reste indexée, elle répond à une recherche et elle répond
> aux quatre questions de l'Explorateur, mais elle n'épaissit aucun thème. Une
> notice `none` reste hors de tout décompte, thématique ou non.
>
> La recherche n'obéit pas à cette règle, et c'est voulu : rien n'est mis de
> côté (`ARCHITECTURE.md` § 1.4bis). Un décompte de retour de recherche peut
> donc dépasser le décompte thématique du même libellé. Là où les deux diffèrent,
> les deux s'affichent côte à côte plutôt qu'un seul.
>
> Écrite ici, elle est reprise mot pour mot dans `methode.html` § 4 et dans la
> section Thèmes d'`observatoire.html`, et appliquée dans `observatory.js`
> (fonction `thematic`) et dans `explorer.js` (champ `dens`).

## 3. L'outil de tagging

`tag_notices.py` lit un JSONL de notices et écrit un JSONL d'enregistrements de
tags, un par notice.

```bash
python3 tag_notices.py --print-schema          # le schéma strict résolu
python3 tag_notices.py --print-system-prompt   # le prompt, vocabulaire inclus

# vague 1 : les notices IxTheo seules
python3 tag_notices.py \
  --input ../data/raw/ixtheo/records.jsonl \
  --output pilot/tags_ixtheo.jsonl \
  --wave semantic_tags_ixtheo_2026_08 \
  --concurrency 6

# vague 2 : le corpus fédéré, hors bruit et hors textes d'Origène
python3 tag_notices.py \
  --input ../data/merged/corpus.jsonl \
  --output waves/wave2_federated/tags.jsonl \
  --wave semantic_tags_federated_2026_08 \
  --relations "" --exclude-relations by --skip-noise \
  --source-order "ixtheo-k10plus,adamantius-girota,bibp,semanticscholar,crossref,openalex,isidore,dialnet,sbn,thesesfr" \
  --concurrency 8
```

La même commande relancée reprend où elle s'est arrêtée : la vague déjà écrite
est relue au démarrage, et une notice est sautée quand son identifiant, la
version du prompt, celle du vocabulaire et l'empreinte de sa fiche coïncident
avec une ligne déjà produite. Une coupure de réseau, une session fermée, un
endpoint indisponible se rattrapent ainsi sans perdre ce qui est acquis ; une
notice dont la fiche a changé depuis, elle, repart.

Ce qui est garanti :

- **Schéma strict, énumérations fermées.** Le schéma envoyé au modèle est
  fabriqué à partir des quatre fichiers de vocabulaire par
  `vocabulary_io.tag_record_schema()` ; il ne peut pas diverger d'eux. Une
  valeur hors vocabulaire qui passerait quand même est écartée à la validation,
  la réparation est consignée dans `repairs` et l'enregistrement passe en
  `needs_review`.
- **Identifiants déterministes.** `<source>:<source_id>` quand les deux
  existent, sinon un sha1 sur titre + premier auteur + année. Deux exécutions
  visent les mêmes objets.
- **Reprise sur une clé complète.** Au démarrage, la vague déjà écrite est
  relue, et une notice n'est sautée que si son identifiant, la version du
  prompt, celle du vocabulaire ET l'empreinte de la fiche soumise
  (`input_digest`) coïncident avec ce qui a déjà été produit. Corriger un
  titre, verser un résumé, changer de prompt : la notice repart, et le run
  l'annonce en clair. Un rejet est comparé aux mêmes versions, de sorte qu'un
  refus prononcé sous d'autres consignes ne gèle pas la notice. Ce qui n'est
  PAS garanti : deux exécutions sur la même entrée ne rendent pas la même
  sortie, puisque la réponse du moteur n'est pas déterministe — la reprise
  garantit qu'on ne resoumet pas ce qui est acquis, pas que deux runs
  coïncident. L'écriture est en append avec `flush` et `fsync` à chaque ligne :
  rien ne se perd dans un tampon.
- **Une notice, un tag : le dernier écrit.** L'écriture en ajout laisse deux
  lignes derrière elle quand une notice est retaguée. Ce sont un tag et son
  brouillon, pas deux tags : `semantic/tags_io.py` donne la règle une fois pour
  toutes — la dernière ligne d'une notice l'emporte, à la place de la première,
  pour qu'un retag ne renumérote pas l'index. `validate_tags.py`,
  `tree/build_topic_tree.py` et `remap_tag_ids.py` la suivent tous les trois ;
  l'arbre gardait auparavant le thème corrigé dehors et l'ancien dedans. En fin
  de vague, le tagueur compacte son fichier — une ligne par notice — et verse
  l'historique complet dans `<output>.history.jsonl` : rien n'est perdu, et
  l'aval n'a plus à trancher.
- **Rejets conservés.** Les erreurs de transport, les réponses illisibles et les
  validations impossibles vont dans `<output>.rejects.jsonl` avec leur étape et
  leur cause. Aucune notice ne disparaît en silence.
- **Concurrence bornée** par `--concurrency`, avec repli exponentiel sur les
  codes réessayables.
- **Garde-fous d'invention.** Le prompt interdit d'utiliser autre chose que les
  métadonnées fournies, impose `relevance=none` quand rien n'atteste qu'Origène
  est discuté, avertit des homonymes (`origen`/`orígenes` espagnols, *Origenes
  Platonicus*), n'autorise une œuvre que si elle est nommée ou clairement
  impliquée, et impose de prendre la valeur basse plus `needs_review` en cas
  d'hésitation.
- **`--dry-run`** écrit les prompts exacts et le schéma résolu sans appeler quoi
  que ce soit, et mesure le volume de texte qu'une passe enverrait.

### Ce que le prompt v2 change

`tag-notice-v1` a tagué les 1 632 notices IxTheo. `tag-notice-v2` a tagué le
corpus fédéré. Quatre différences, toutes tirées de la lecture du pilote.

**Le plancher du périmètre curaté.** La règle v1 imposait `none` dès que les
métadonnées ne montraient pas positivement qu'Origène est discuté. Sur un
corpus curaté, elle produit un contresens : les catalogueurs de Tübingen ont
rattaché chaque notice à la notice d'autorité d'Origène, et le titre ne le
nomme pas toujours — le péché originel chez les Pères, les ministères dans
l'Église ancienne. Sur huit désaccords de pertinence du jeu étalon, sept
allaient dans ce sens. La v2 ajoute une règle 2bis : quand le champ
`curated_scope` est présent, le plancher est `marginal`. Trois périmètres le
déclenchent — les notices IxTheo, la BIBP, et les sections 12 et 13 du
repertorio Adamantius, celle d'Origène et celle de l'origénisme. Le plancher
est appliqué deux fois, dans le prompt et après la réponse, pour qu'il tienne
quoi que réponde le moteur.

**Deux sorties de secours au plancher.** Un homonyme et un texte d'Origène
catalogué comme tel gardent `none` même dans un périmètre curaté. Pour que le
code sache les distinguer, le schéma reçoit un champ obligatoire
`relevance_none_reason` — `homonym`, `text-by-origen`, `insufficient-metadata`,
`other-subject`, ou `not-applicable` quand la pertinence n'est pas `none`. Un
enregistrement dont le plancher a joué porte `relevance_floor_applied: true` :
la décision reste lisible et se compte.

**La feuille des présentations d'ensemble.** Règle 6bis : une entrée de
dictionnaire, un chapitre de manuel, une introduction, un portrait, bref une
notice qui présente Origène en entier, prend `context.general-presentation` et
non `exegesis.hermeneutic-theory`.

**Des métadonnées de dix sources au lieu d'une.** La charge soumise réunit
maintenant les cinq vocabulaires que les sources emploient — vedettes IxTheo,
sections Adamantius, topics OpenAlex, descripteurs BIBP, Rameau de theses.fr —
sous un seul champ `subjects`, plus le type et l'éditeur. Le tagueur les lit
tous de la même façon, comme des indices de ce dont la notice traite.

### Provenance

Chaque enregistrement porte la même convention de vague : `wave`, `run_id`,
`source_model`, `auto_generated`, `confidence`, plus
`tagged_at`, `vocabulary_version`, `prompt_version` et `input_digest` — le sha1
de la charge exacte soumise. Deux exécutions de même `input_digest` et de même
`prompt_version` sont comparables ligne à ligne.

### Agnosticisme de fournisseur

`llm_adapter.py` est le seul point de contact avec un moteur. Il lit
`ORIGENALITY_LLM_BASE_URL`, `ORIGENALITY_LLM_API_KEY` et
`ORIGENALITY_LLM_MODEL` dans l'environnement du processus et parle un
`/chat/completions` en `urllib`, dans la forme que la plupart des moteurs
exposent. Aucun nom de fournisseur, aucun nom de modèle, aucune URL et aucune
clé ne figurent dans le code, dans les fichiers de configuration ou dans la
documentation. `source_model` recopie `ORIGENALITY_LLM_MODEL_ALIAS`, et lui
seul : sans alias, la provenance porte `engine-unaliased`, jamais l'identifiant
réel — un garde qui s'ouvre quand on l'oublie n'en est pas un. La sortie structurée se dégrade seule : schéma JSON
strict, puis objet JSON, puis texte libre, selon ce que l'endpoint accepte.

Reste la tension relevée par le constat 11 de l'audit : interdire de nommer le
moteur rend le classement irreproductible. Elle se résout en séparant les deux
niveaux. Les données de travail portent l'identifiant exact, sans quoi personne
ne peut rejouer le run. À la publication, `ORIGENALITY_LLM_MODEL_ALIAS` fait
écrire à sa place un libellé neutre et stable ; la correspondance entre les deux
se conserve hors du dépôt public et se communique sur demande motivée. Ce qui
est publié reste donc reproductible : même vocabulaire, même prompt, même
schéma, mêmes identifiants de notices. Un tiers qui rejoue le pilote avec son
propre moteur mesure l'écart ligne à ligne.

## 4. L'index-arbre

`tree/build_topic_tree.py` transforme les tags en un document JSON à deux axes
sur les mêmes notices : `themes` (racine → 16 domaines → 61 feuilles → notices)
et `works` (racine → catégories de genre → œuvres → notices). Un nœud porte
`node_id`, `title`, `path`, `summary`, `concept_tags`, `entity_tags` et
`nodes[]`, plus deux champs ajoutés parce que l'on indexe des notices et non des
passages : `notice_ids` et `stats`.

Les résumés de nœuds sont **calculés**, pas générés : nombre de notices,
amplitude des années, répartition par langue, angles dominants, œuvres les plus
citées. Le fichier ne contient aucun appel à un moteur ; l'arbre est une
fonction déterministe des tags et du vocabulaire.

```bash
python3 tree/build_topic_tree.py \
  --tags pilot/tags_ixtheo.jsonl \
  --notices ../data/raw/ixtheo/records.jsonl \
  --output tree/topic_tree.json --min-relevance partial
```

`tree/navigate.py` prend une description libre de projet et rend
`{selected_nodes, reasoning, notice_ids}`. Deux moteurs, un seul contrat : le
moteur de raisonnement reçoit l'index aplati (identifiant, titre, chemin, résumé
calculé, étiquettes) et choisit les nœuds à ouvrir ; le repli déterministe note
les mêmes nœuds par recouvrement de termes entre la requête et le titre, le
chemin, le résumé et les étiquettes, les feuilles primant sur les domaines à
score égal. Le repli sert aussi de présélection quand l'index est grand, si bien
que le moteur de raisonnement voit toujours une charge bornée. Sans endpoint, ou
avec `--no-llm`, la navigation fonctionne quand même.

```bash
python3 tree/navigate.py --query "Origen on free will against Valentinian determinism"
python3 tree/navigate.py --query "..." --no-llm --json
```

## 5. Protocole de reproductibilité

Ce paragraphe répond au constat 11 de l'audit externe du 15 août 2026 : un score de
densité n'est recevable que si le classement qui le nourrit est reproductible et
documenté.

1. **Le vocabulaire est versionné et cité.** Chaque enregistrement porte
   `vocabulary_version`. Un changement de vocabulaire est un changement de
   version, donc une nouvelle vague : les tags anciens restent lisibles et
   comparables, ils ne sont jamais réécrits en place.
2. **Le prompt est versionné et imprimable.** `prompt_version` sur chaque
   enregistrement, `--print-system-prompt` pour l'obtenir mot pour mot.
3. **Le schéma est dérivé, pas recopié.** `--print-schema` imprime les
   énumérations réellement envoyées.
4. **L'entrée est empreintée.** `input_digest` fixe la charge soumise, indépendamment
   du fichier source.
5. **Le moteur est déclaré sans être imposé.** `source_model` recopie la valeur
   d'environnement du run. Un tiers rejoue le pilote avec son propre endpoint :
   les identifiants de notices, les prompts, le schéma et le vocabulaire sont
   identiques, seul `source_model` change, et l'écart entre les deux sorties se
   mesure ligne à ligne sur `notice_id`.
6. **Un jeu étalon fixe la référence humaine.** `pilot/gold_50.jsonl` :
   50 notices tirées par `random.Random(42).sample`, taguées à la main contre le
   même vocabulaire et les mêmes consignes, marquées `auto_generated: false` et
   `source_model: manual-gold`. Le jeu de trente notices du pilote,
   `pilot/gold_ixtheo_30.jsonl`, reste sur le disque comme archive : il a été
   annoté sous des consignes depuis réécrites, et ne mesure plus rien. `pilot/report.py` mesure l'accord — pertinence
   exacte, à une classe près, et « compte dans la densité ou non » ; thèmes et
   œuvres en Jaccard moyen et en recouvrement partiel ; matrice de confusion et
   liste nominative des désaccords.
7. **Les rejets sont publiés avec les tags.** Un taux de rejet et un taux de
   `needs_review` accompagnent toute statistique tirée de ces données.
8. **La densité se déclare avec son périmètre.** Un compte de notices dans un
   nœud n'a de sens qu'accompagné du corpus source, de la vague, du seuil de
   pertinence retenu (`--min-relevance`) et de la part de `needs_review` du
   nœud. Ces quatre valeurs sont dans `topic_tree.json`, aux champs
   `source_tags`, `min_relevance` et `counts`, et dans les `stats` de chaque
   nœud. Un seul fichier définit la densité, [`DENSITY.md`](DENSITY.md) : ce
   qu'on compte, par quel chemin, et ce qui n'est pas implémenté. Aucun autre
   document n'en donne de variante.

Limites à énoncer avec les chiffres, et non après : la densité mesure d'abord la
couverture de la base moissonnée ; sur un corpus mono-source elle mesure la
politique d'indexation de cette base. Les vedettes IxTheo sont plus riches sur
les notices récentes, ce qui déplace mécaniquement les décomptes vers les
décennies bien indexées. Les feuilles jamais employées sont listées dans le
rapport du pilote : ce sont soit des trous réels du champ, soit des défauts du
vocabulaire, et rien dans les données ne permet de trancher sans lecture.
