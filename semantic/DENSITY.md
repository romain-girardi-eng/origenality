# La densité — définition unique

Ce fichier est la seule définition de la densité dans Origenality. Tout autre
document qui en parle renvoie ici et n'en redonne pas une version.

Il en circulait trois : un voisinage pondéré par la fraîcheur et le rayon dans
`CONCEPTION.md`, un simple compte dans `ARCHITECTURE.md`, et dans le code la
cardinalité d'une union d'identifiants. Deux équipes disposant du même corpus
n'auraient pas obtenu le même chiffre, faute de savoir lequel des trois calculer.

## Ce qu'on mesure

**La densité d'une requête est le nombre de notices distinctes que portent les
nœuds retenus pour cette requête, dans le périmètre citable.**

Rien de plus. Ce n'est ni une pondération, ni une distance, ni un score
d'originalité : c'est un effectif, et il se lit « 47 travaux dans ce périmètre ».

## Le chemin exact, du texte au chiffre

1. **Périmètre citable.** L'index thématique (`semantic/tree/topic_tree_*.json`)
   n'indexe que les notices dont le tag sémantique vaut `core` ou `partial`
   (`build_topic_tree.py --min-relevance partial`). Les `marginal` et les `none`
   n'y entrent pas : elles restent retrouvables, elles ne se comptent pas. C'est
   la même règle sur toutes les surfaces qui comptent.
2. **Sélection des nœuds.** `semantic/tree/navigate.py` retient au plus
   `--max-nodes` nœuds (8 par défaut). Deux moteurs, un seul contrat de sortie :
   - le moteur déterministe compte, pour chaque nœud, les termes de la requête
     retrouvés dans son titre, son chemin, son résumé calculé et ses étiquettes
     (concept et entité), diacritiques repliés, préfixes acceptés ; à score égal
     une feuille passe devant un domaine ; les nœuds « neutres » (réservoirs)
     sont exclus ;
   - le moteur de raisonnement, quand il est configuré, choisit parmi une
     présélection bornée produite par le premier.
   **Aucune correspondance ⇒ aucune sélection.** Une requête dont aucun terme
   n'apparaît nulle part renvoie une sélection vide et une densité de zéro, avec
   le message qui le dit. Elle ne renvoie pas les plus gros amas de l'index :
   c'était le cas jusqu'au 16 août 2026, et une requête sans rapport produisait
   alors la densité la plus élevée de tout l'index.
3. **Union.** On réunit les `notice_ids` des nœuds retenus, sans doublon : une
   notice rattachée à trois nœuds retenus compte une fois.
4. **Densité** = cardinalité de cette union, publiée avec son dénominateur,
   `notices_indexed`, pour qu'on sache toujours sur quel ensemble elle porte.

## Ce qui la fait varier, et qu'il faut donc citer avec elle

Une densité n'est comparable qu'à densité de mêmes paramètres. Cinq entrées la
déterminent, et toutes sont écrites dans les fichiers produits :

| Entrée | Où elle est enregistrée |
|---|---|
| version du vocabulaire | `vocabulary_version` (index et tags) |
| version du prompt de tagage | `prompt_version` (tags) |
| seuil de pertinence de l'index | `min_relevance` (index) |
| nombre maximal de nœuds | `--max-nodes`, 8 par défaut |
| moteur de sélection | `engine` dans la sortie de `navigate.py` |

Le moteur de raisonnement n'est pas déterministe d'une exécution à l'autre ; le
moteur déterministe l'est. Une densité destinée à être citée se produit sous
`--no-llm`, et le dit.

## Ce qui n'est PAS implémenté

`CONCEPTION.md` annonçait une densité pondérée par la fraîcheur des travaux et
par un rayon sémantique. **Rien de tel n'existe** : aucune pondération, aucun
rayon, aucun plongement vectoriel n'entre dans le chiffre publié. C'est une
extension possible, pas une propriété actuelle, et elle demanderait d'abord de
fixer la métrique, ses poids et son incertitude. Tant qu'elle n'est pas écrite
ici, la densité est un effectif.

Ne sont pas non plus implémentés : intervalle d'incertitude, sensibilité au
seuil, pondération par langue ou par source. La couverture citationnelle, elle,
est mesurée et son biais est publié (`data/derived/citations_coverage.json`) —
mais elle n'entre pas dans la densité.
