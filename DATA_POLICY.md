# Statut juridique des données d'Origenality

Ce fichier est le squelette de la politique de données. Il vaut pour ce qui est
**publié** : les dumps, l'API, le site. Il ne dit rien du travail interne, où
les notices restent telles que les sources les ont livrées.

Trois strates, à ne pas confondre.

**Les métadonnées bibliographiques** — auteur, titre, année, contenant, pages,
identifiants. Un fait bibliographique n'est pas une œuvre protégée ; la
compilation, elle, peut l'être. Chaque source est créditée nommément dans la
page Crédits, avec le lien vers ses conditions.

**Les résumés.** Ils sont affichés et publiés, parce qu'un lecteur qui ne voit
qu'un titre ne peut rien décider et qu'un instrument bibliographique sans
résumés vaut peu. Le régime est celui de l'attribution et du retrait : chaque
résumé affiché nomme la base d'où il vient et renvoie à la notice d'origine.
Un éditeur, une base partenaire ou un auteur obtient le retrait de ses résumés
sur simple demande, sans discussion et sans délai de négociation.
Le champ `abstract_rights` recopie ce que la source a déclaré et reste
renseigné pour la traçabilité : il sert à savoir quoi retirer, vite, et il ne
conditionne plus l'affichage. `scripts/check_release.py` refuse un dump dont
un résumé n'est pas attribuable.

**Comment demander un retrait.** Un message à l'adresse de contact du projet,
indiquant la base ou l'éditeur concerné, suffit. Les résumés visés sont
retirés du site et du prochain dump ; `scripts/check_release.py --withdraw`
produit la copie expurgée à partir du même corpus, sans reprise manuelle.

**Les tags sémantiques et les agrégats** — les étiquettes du vocabulaire
contrôlé, les décomptes, les densités, l'index-arbre. Ils sont produits par le
projet et publiés sous la licence du dépôt.

## Table d'attribution des résumés

Le bloc ci-dessous est lu par `scripts/check_release.py` et par
`pipeline/build_site_data.py` : c'est la source unique, il n'y a pas de
deuxième copie dans le code. Il donne, pour chaque base moissonnée, le nom sous
lequel elle est créditée, la licence ou les conditions sous lesquelles ses
métadonnées sont reprises, et le gabarit d'URL qui ramène à la notice d'origine.

Une attribution n'est valable que si elle est **résoluble** : un nom de base ne
suffit pas, il faut un lien. Le contrôle exige donc, pour chaque résumé, soit un
`abstract_url` — l'adresse de la notice qui a écrit le résumé, recopiée par la
fusion depuis cette notice et non depuis une autre base de la même grappe —,
soit un identifiant que le gabarit ci-dessous transforme en adresse. Un résumé
dont la base d'origine ne figure pas ici, ou dont l'attribution ne se résout pas
en lien, n'est pas publiable : ce sont les deux seuls motifs de refus.

Les gabarits à `null` correspondent aux bases qui ne publient pas de notice à
adresse construite : leurs résumés ne passent le contrôle que munis de leur
`abstract_url`. Le gabarit d'ISIDORE passe par le résolveur global du système
Handle : les identifiants qu'ISIDORE donne à ses ressources sont tous de la
forme `préfixe/suffixe` (10670 pour Huma-Num, 20.500.13089, 12148 pour Gallica,
10261 pour le CSIC, et des préfixes DOI en 10.x), et `hdl.handle.net` résout
indifféremment les uns et les autres.

```json
{
  "policy_version": "1.1.0",
  "regime": "attribution-and-takedown",
  "contact": "romain.girardi@univ-cotedazur.fr",
  "attribution": {
    "ixtheo-k10plus": {
      "label": "Index Theologicus (IxTheo / K10plus)",
      "url_template": "https://ixtheo.de/Record/{id}",
      "license": "CC0 1.0 (métadonnées K10plus)"
    },
    "openalex": {
      "label": "OpenAlex",
      "url_template": "{id}",
      "hosts": ["openalex.org"],
      "license": "CC0 1.0"
    },
    "crossref": {
      "label": "Crossref",
      "url_template": "https://doi.org/{id}",
      "license": "politique de métadonnées ouvertes de Crossref"
    },
    "semanticscholar": {
      "label": "Semantic Scholar",
      "url_template": "https://www.semanticscholar.org/paper/{id}",
      "note": "ODC-BY : attribution obligatoire par la licence de la source.",
      "license": "ODC-BY 1.0 — attribution obligatoire"
    },
    "bibp": {
      "label": "BIBP — Université Laval",
      "url_template": null,
      "license": "conditions propres à BIBP (Université Laval)"
    },
    "adamantius-girota": {
      "label": "GIROTA / Adamantius",
      "url_template": null,
      "license": "conditions propres à Morcelliana / GIROTA"
    },
    "isidore": {
      "label": "ISIDORE (Huma-Num)",
      "url_template": "https://hdl.handle.net/{id}",
      "license": "conditions de l'agrégateur et de chaque fournisseur"
    },
    "thesesfr": {
      "label": "theses.fr",
      "url_template": "https://theses.fr/{id}",
      "license": "Licence Ouverte / Open Licence"
    },
    "dialnet": {
      "label": "Dialnet",
      "url_template": null,
      "license": "conditions propres à Dialnet (Universidad de La Rioja)"
    },
    "sbn": {
      "label": "SBN — Servizio Bibliotecario Nazionale",
      "url_template": "https://opac.sbn.it/bid/{id}",
      "license": "conditions propres à l'ICCU"
    },
    "k10plus": {
      "label": "K10plus (GBV / BSZ)",
      "url_template": "https://opac.k10plus.de/DB=2.1/PPNSET?PPN={id}",
      "license": "CC0 1.0 (métadonnées K10plus)"
    },
    "b3kat": {
      "label": "B3Kat (Bibliotheksverbund Bayern / KOBV)",
      "url_template": "https://opacplus.bib-bvb.de/TouchPoint_touchpoint/perma.do?q=+0%3D%22{id}%22+IN+%5B2%5D&v=bvb&l=de",
      "license": "CC0 1.0 (métadonnées B3Kat)"
    },
    "gnomon-gbd": {
      "label": "Gnomon Bibliographische Datenbank (Universität Eichstätt)",
      "url_template": "https://www.gbd.digital/Record/{id}",
      "note": "Notices récupérées en MARC21 par le SRU B3Kat : les identifiants GBD sont des numéros BV.",
      "license": "conditions propres à la GBD ; métadonnées servies par B3Kat"
    },
    "dnb": {
      "label": "Deutsche Nationalbibliothek",
      "url_template": "https://d-nb.info/{id}",
      "license": "CC0 1.0"
    },
    "bnf": {
      "label": "Bibliothèque nationale de France",
      "url_template": "https://catalogue.bnf.fr/ark:/12148/{id}",
      "license": "Licence Ouverte / Open Licence (Etalab)"
    },
    "loc": {
      "label": "Library of Congress",
      "url_template": "https://lccn.loc.gov/{id}",
      "note": "Œuvres d'agents fédéraux des États-Unis : domaine public ; la LC déclare CC0 1.0 pour la réutilisation mondiale.",
      "license": "CC0 1.0 / domaine public (US Government work)"
    },
    "sudoc": {
      "label": "Sudoc — Agence bibliographique de l'Enseignement supérieur (ABES)",
      "url_template": "https://www.sudoc.fr/{id}",
      "note": "Le Sudoc mêle des notices produites par son réseau et des notices dérivées d'autres bases (BnF, WorldCat, ISSN, DNB). Les premières sont sous Licence Ouverte ; les secondes restent soumises à la licence de la base productrice, et c'est elle qu'il faut citer quand la notice le dit.",
      "license": "Licence Ouverte / Open Licence (Etalab), mention « Agence bibliographique de l'Enseignement supérieur » exigée"
    },
    "generated": {
      "label": "Résumé produit par Origenality",
      "url_template": null,
      "note": "Marqué comme tel dans les données et sur le site.",
      "license": "licence du dépôt Origenality"
    }
  },
  "withdrawn": []
}
```

## Retraits enregistrés

Le tableau se remplit à la première demande. Une ligne y est écrite le jour où
la demande arrive et l'identifiant de la base est ajouté à `withdrawn` dans le
bloc ci-dessus. Cette seule ligne suffit à exécuter le retrait : la
reconstruction du site (`pipeline/build_site_data.py`) cesse d'écrire les
résumés de cette base dans `site/data/abstracts.json` et en compte le retrait,
et `scripts/check_release.py --withdraw <base> --strip` produit le dump expurgé.
Rien ne se reprend à la main.

| Date | Demandeur | Portée | Suite donnée |
|---|---|---|---|
| — | — | — | — |

Deux fonds appellent une vigilance particulière et sont surveillés sans être
retirés : Persée, dont la mention de copyright autorise la reproduction à des
fins scientifiques ou d'enseignement en excluant l'usage commercial ; et
OpenEdition, dont les notices d'accès ouvert ne portent pas toutes une licence
nommée. Les partenaires ont été informés par écrit le 15 août 2026 (BIBP,
GIROTA, IxTheo) ; une objection vaut retrait.

## Ce que fait le contrôle de publication

```bash
python3 scripts/check_release.py data/release/corpus_public.jsonl
python3 scripts/check_release.py data/merged/corpus.jsonl --sample 3000
python3 scripts/check_release.py data/merged/corpus.jsonl \
    --withdraw persee --strip data/release/corpus_public.jsonl
```

Le contrôle lit chaque notice, résout la base d'origine de son résumé et
refuse le dump si un résumé n'a pas d'attribution résoluble. Il compte aussi
les valeurs de `abstract_rights` rencontrées : ce relevé ne décide de rien, il
sert à retrouver en une commande les résumés d'un fonds donné le jour où on
doit les retirer.

`--strip` est facultatif et n'est jamais appliqué d'office. Il écrit une copie
du dump ; combiné à `--withdraw`, dont l'argument est une expression régulière
testée sur la base d'origine et sur `abstract_rights`, il retire les résumés
visés et inscrit le motif dans `abstract_withheld`, de sorte qu'un lecteur du
dump sache qu'il manque quelque chose et pourquoi.
