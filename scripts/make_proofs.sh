#!/usr/bin/env bash
# Origenality — harnais de preuves.
#
# Un harnais de preuve ne vaut que s'il échoue quand la preuve échoue. Celui-ci
# arrête tout au premier écart : chaque étape déclare le code de retour qu'elle
# attend, et le code obtenu est comparé au code attendu. Cinq étapes attendent
# une sortie non nulle — ce sont les contrôles négatifs, et ils échouent aussi
# s'ils se mettent à passer.
#
#     bash scripts/make_proofs.sh > docs/qa/iteration8_preuves_2026-08-16.txt
#
# Le harnais ne moissonne rien, ne touche pas au réseau, et n'écrit que dans
# data/_proofs_tmp/ (ignoré par git, effacé à chaque passe). Le corpus de
# référence data/merged/ n'est jamais réécrit : la fusion est rejouée dans le
# répertoire temporaire, puis comparée au corpus de référence par SHA-256.
#
# Variable d'environnement facultative :
#   ORIGENALITY_PROSE_SCORER  chemin d'un scorer anti-prose-IA. Absent, l'étape
#                             est déclarée non exécutée dans le récapitulatif
#                             (elle n'est jamais comptée comme réussie).
set -euo pipefail

ROOTDIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOTDIR"

TMP="data/_proofs_tmp"
OUT="$TMP/run.out"

# Les pages du site vivent sous `site/build-c/` dans le dépôt de travail et sous
# `site/` une fois publiées : le harnais prend celle des deux qui existe plutôt
# que d'écrire un chemin qui n'est vrai que d'un côté.
if [ -d site/build-c ]; then BUILD="site/build-c"; else BUILD="site"; fi

STEPS_OK=0
STEPS_NEG=0

# _init : le nettoyage et la création du répertoire de travail.
#
# Cette étape était hors de `_run`, donc hors du contrat : quand le sandbox de
# l'auditeur a refusé le `rm`, le harnais est sorti en 1 au lieu de 90, et le
# lecteur ne pouvait pas distinguer « une preuve a échoué » de « le harnais n'a
# pas démarré ». Elle sort maintenant en 90 comme tout le reste.
_init() {
    printf '\n$ rm -rf %s && mkdir -p %s\n' "$TMP" "$TMP"
    set +e
    rm -rf "$TMP" 2>&1
    status=$?
    if [ "$status" -eq 0 ]; then
        mkdir -p "$TMP" 2>&1
        status=$?
    fi
    set -e
    printf '[exit %s]\n' "$status"
    if [ "$status" -ne 0 ]; then
        printf '\n*** ÉCHEC DU HARNAIS : le répertoire de travail %s n'"'"'a pas pu être préparé.\n' "$TMP"
        printf '*** Aucun récapitulatif ne sera imprimé.\n'
        exit 90
    fi
}

# _run <code attendu> <commande...>
# Imprime la commande sous forme recopiable, sa sortie (chemins de la machine
# remplacés par « . »), son code de retour. Sort du harnais si le code diffère.
_run() {
    expected=$1
    shift
    printf '\n$ '
    for arg in "$@"; do
        case "$arg" in
            *[!A-Za-z0-9_./=-]*) printf '"%s" ' "$arg" ;;
            *) printf '%s ' "$arg" ;;
        esac
    done
    printf '\n'
    set +e
    "$@" > "$OUT" 2>&1
    status=$?
    set -e
    sed "s|$ROOTDIR|.|g" "$OUT"
    printf '[exit %s]\n' "$status"
    if [ "$status" -ne "$expected" ]; then
        printf '\n*** ÉCHEC DU HARNAIS : code %s attendu, %s obtenu.\n' "$expected" "$status"
        printf '*** Aucun récapitulatif ne sera imprimé.\n'
        exit 90
    fi
    if [ "$expected" -eq 0 ]; then
        STEPS_OK=$((STEPS_OK + 1))
    else
        STEPS_NEG=$((STEPS_NEG + 1))
    fi
}

run() { _run 0 "$@"; }
run_expect() { code=$1; shift; _run "$code" "$@"; }

echo "== Origenality — preuves des itérations 8bis et 8ter (16 août 2026) =="
echo
echo "Le harnais s'arrête au premier écart entre le code attendu et le code obtenu."
echo "Son initialisation obéit au même contrat : une sortie 90, comme les étapes."
echo "Contrôles négatifs (une sortie non nulle EST la preuve) :"
echo "  [exit 1] qa_checks.py isbn sur la fusion rejouée SANS le lien ISBN"
echo "  [exit 2] check_release.py sur un dump synthétique sans lien résoluble"
echo "  [exit 1] build_site_data.py fédéré sans --tags"
echo "  [exit 1] remap_tag_ids.py --apply sur une table qui ne reporte qu'une ligne"
echo "  [exit 1] build_summary_figures.py --check sur des pages retouchées à la main"
echo "  [exit 1] retag_gaps.py --check sur le fichier de tags d'avant le rattrapage"
echo "  [exit 1] build_semantic.py sur ce même fichier : il refuse d'écrire"
echo "Racine : $(basename "$ROOTDIR")"
echo "Python : $(python3 -V 2>&1)"
echo "Répertoire de travail du harnais : $TMP (jamais data/merged/)"

_init

# ---------------------------------------------------------------------------
echo
echo "== A4-1 — le harnais écrit hors du corpus de référence =="
echo
echo "-- empreinte du corpus de référence AVANT toute commande --"
run shasum -a 256 data/merged/corpus.jsonl data/merged/merge_report.json
cp data/merged/corpus.jsonl "$TMP/reference_avant.jsonl"

echo
echo "-- la fusion est rejouée DANS le répertoire temporaire --"
run python3 pipeline/merge_dedup.py --out-dir "$TMP/merge_a"

echo
echo "-- déterminisme : deuxième fusion, autre répertoire, sortie byte-identique --"
run python3 pipeline/merge_dedup.py --out-dir "$TMP/merge_b"
run python3 scripts/proofs/compare_corpora.py \
    "$TMP/merge_a/corpus.jsonl" "$TMP/merge_b/corpus.jsonl"

echo
echo "-- la fusion rejouée reproduit le corpus de référence (SHA-256) --"
run python3 scripts/proofs/compare_corpora.py \
    "$TMP/merge_a/corpus.jsonl" data/merged/corpus.jsonl

echo
echo "-- le corpus de référence n'a pas bougé pendant la passe --"
run python3 scripts/proofs/compare_corpora.py \
    "$TMP/reference_avant.jsonl" data/merged/corpus.jsonl

# ---------------------------------------------------------------------------
echo
echo "== A4-2 — lien ISBN : ce qu'il unit, ce qu'il refuse d'unir =="
run python3 scripts/qa_checks.py isbn --corpus "$TMP/merge_a/corpus.jsonl"

echo
echo "-- les cas nommés par l'audit (1951/1991, 3451221098, :47/:627, :48/:628) --"
run python3 scripts/proofs/probe_isbn_cases.py --corpus "$TMP/merge_a/corpus.jsonl"

echo
echo "-- le garde de série, exercé sur un cas synthétique --"
run python3 -m unittest -v scripts.test_data_gates.IsbnLinkTest

echo
echo "-- contrôle négatif : la même fusion SANS le lien ISBN laisse les sous-fusions --"
run python3 pipeline/merge_dedup.py --no-isbn-link --out-dir "$TMP/merge_sans_isbn"
run_expect 1 python3 scripts/qa_checks.py isbn --corpus "$TMP/merge_sans_isbn/corpus.jsonl"

echo
echo "-- origenality_id reste une clé --"
run python3 scripts/proofs/probe_ids.py --corpus "$TMP/merge_a/corpus.jsonl"

echo
echo "-- rapport de fusion : ce que l'ISBN a lié, ignoré, bloqué --"
run python3 scripts/proofs/probe_merge_report.py "$TMP/merge_a/merge_report.json"

echo
echo "-- remap des tags, arbre et étalon : aucun orphelin après la fusion --"
run python3 scripts/proofs/probe_tag_orphans.py --corpus "$TMP/merge_a/corpus.jsonl"

# ---------------------------------------------------------------------------
echo
echo "== A4-3 — le lien d'un résumé mène à la notice qui l'a écrit =="
echo
echo "-- le sondage de l'auditeur, rejoué sur les entrantes du périmètre fédéré --"
run python3 scripts/proofs/probe_federated_abstracts.py --corpus "$TMP/merge_a/corpus.jsonl"

echo
echo "-- contrôle négatif : le build fédéré refuse de tourner sans --tags --"
run_expect 1 python3 pipeline/build_site_data.py \
    --input "$TMP/merge_a/corpus.jsonl" \
    --source-label "corpus fédéré Origenality (10 bases)" \
    --scope "publications about Origen of Alexandria" --dry-run

echo
echo "-- avec --tags : essai à blanc, rien n'est écrit --"
run python3 pipeline/build_site_data.py \
    --input "$TMP/merge_a/corpus.jsonl" \
    --tags semantic/waves/wave2_federated/tags.jsonl \
    --source-label "corpus fédéré Origenality (10 bases)" \
    --scope "publications about Origen of Alexandria" --dry-run

# ---------------------------------------------------------------------------
echo
echo "== A4-4 — un retag remplace l'ancien tag partout en aval =="
run python3 scripts/proofs/probe_retag.py --work "$TMP/retag"
run python3 -m unittest -v scripts.test_data_gates.LastWriteWinsTest

# ---------------------------------------------------------------------------
echo
echo "== A4-5 — attribution : une adresse doit être une adresse =="
run python3 -m unittest -v scripts.test_data_gates.UrlValidationTest

echo
echo "-- contrôle négatif : dump synthétique dont les liens n'en sont pas --"
run python3 scripts/proofs/make_unresolvable_dump.py "$TMP/faux_liens.jsonl"
run_expect 2 python3 scripts/check_release.py "$TMP/faux_liens.jsonl"

echo
echo "-- le corpus complet --"
run python3 scripts/check_release.py "$TMP/merge_a/corpus.jsonl" \
    --report "$TMP/release_check.json"

# ---------------------------------------------------------------------------
echo
echo "== A4-6 — un curseur S2 expiré est purgé, la requête repart page 1 =="
run python3 -m unittest -v scripts.test_data_gates.S2TokenTest

# ---------------------------------------------------------------------------
echo
echo "== A4-7 — les chiffres publiés sont générés, jamais tapés =="
run python3 $BUILD/tools/build_summary_figures.py --check
run python3 scripts/proofs/probe_published_figures.py

# ---------------------------------------------------------------------------
echo
echo "== A4-8 — MARC : les motifs légitimes restent intacts =="
run python3 -m unittest -v scripts.test_data_gates.MarcFalsePositiveTest

# ---------------------------------------------------------------------------
echo
echo "== A4-9 / A4-10 — documentation =="
run python3 scripts/proofs/probe_docs.py

# ---------------------------------------------------------------------------
echo
echo "== A5-1 — un préfixe d'actes de colloque n'est pas une désignation d'ouvrage =="
run python3 -m unittest -v scripts.test_data_gates.SeriesDesignationTest

echo
echo "== A5-2 — l'identifiant qui EST une adresse reste sur l'hôte de sa base =="
run python3 -m unittest -v scripts.test_data_gates.OpenAlexHostTest

echo
echo "== A5-5 — les contournements d'adresse de l'audit 5 =="
run python3 -m unittest -v scripts.test_data_gates.UrlHardeningTest

echo
echo "== A5-3 — un report qui perd dix-neuf lignes sur vingt n'écrit pas =="
run python3 -m unittest -v scripts.test_data_gates.RemapGuardTest

echo
echo "-- contrôle négatif : le report réel refuse la table qui ne reporte qu'une ligne --"
run python3 scripts/proofs/make_partial_remap.py "$TMP/remap"
run_expect 1 python3 semantic/remap_tag_ids.py --apply \
    --map "$TMP/remap/map.json" --tags "$TMP/remap/tags.jsonl" \
    --corpus "$TMP/remap/corpus.jsonl" --output "$TMP/remap/tags.jsonl"

echo
echo "== A5-8 — l'historique des tags est un journal, pas une pile d'états =="
run python3 -m unittest -v scripts.test_data_gates.TagHistoryTest

echo
echo "== A5-9 — un report par titre qui ne tient pas fait échouer la QA =="
run python3 -m unittest -v scripts.test_data_gates.ProjectionGateTest
run python3 scripts/qa_checks.py projections

echo
echo "== A5-4 — le constructeur du site ne lit plus la vague 1 archivée =="
run python3 -m unittest -v scripts.test_data_gates.SiteSemanticInputTest
echo
echo "-- la vague fédérée sur les 1 632 notices du site, écrite hors du site --"
run python3 $BUILD/tools/build_semantic.py --out "$TMP/semantic_wave2.json"

echo
echo "== itération 8bis — les comptes de la vague 2 sont la population publiée =="
echo
echo "-- les chiffres des pages sont ceux que le générateur produirait --"
run python3 $BUILD/qa/check_one_population.py

echo
echo "-- contrôle négatif : un chiffre retouché à la main fait échouer le contrôle --"
run python3 scripts/proofs/make_stale_pages.py "$TMP/pages_periment"
run_expect 1 python3 $BUILD/tools/build_summary_figures.py --check \
    --build "$TMP/pages_periment"

# ---------------------------------------------------------------------------
echo
echo "== itération 8ter — aucune notice affichée ne reste sans classe =="
echo
echo "-- l'état courant : le relevé ne trouve plus de trou --"
run python3 semantic/retag_gaps.py \
    --tags semantic/waves/wave2_federated/tags.jsonl \
    --old-ids data/merged/corpus_ids_before_2026-08-16.tsv \
    --report "$TMP/gaps_now.json" --check

echo
echo "-- contrôle négatif : sur le fichier d'avant le rattrapage, 28 trous --"
head -21080 semantic/waves/wave2_federated/tags.jsonl > "$TMP/tags_avant.jsonl"
run_expect 1 python3 semantic/retag_gaps.py \
    --tags "$TMP/tags_avant.jsonl" \
    --old-ids data/merged/corpus_ids_before_2026-08-16.tsv \
    --report "$TMP/gaps_avant.json" --check

echo
echo "-- contrôle négatif : le constructeur du site refuse d'écrire sur ce fichier --"
run_expect 1 python3 $BUILD/tools/build_semantic.py \
    --tags "$TMP/tags_avant.jsonl" --out "$TMP/semantic_avant.json"

echo
echo "-- le même fichier, trous assumés : 1 376 / 223 / 33 au lieu de 1 402 / 225 / 5 --"
run python3 $BUILD/tools/build_semantic.py \
    --tags "$TMP/tags_avant.jsonl" --out "$TMP/semantic_avant.json" --allow-gaps

echo
echo "-- la passe de rattrapage : 24 grappes, 28 notices, motif par motif --"
run python3 scripts/proofs/recap_gaps.py "$TMP/gaps_avant.json" \
    semantic/waves/wave4_gap28/tags.jsonl

# ---------------------------------------------------------------------------
echo
echo "== suite de tests complète =="
run python3 scripts/test_data_gates.py
# La passe de publication et son contrôle négatif restent dans le dépôt de
# travail : là où ils sont absents, l'étape n'a pas lieu d'être.
if [ -f scripts/test_publish_export.py ]; then
    run python3 scripts/test_publish_export.py
fi

echo
echo "== validation de schéma des tags =="
run python3 semantic/validate_tags.py semantic/waves/wave2_federated/tags.jsonl
run python3 semantic/validate_tags.py semantic/pilot/gold_50.jsonl

# ---------------------------------------------------------------------------
echo
echo "== prose (facultatif, hors dépôt) =="
if [ -n "${ORIGENALITY_PROSE_SCORER:-}" ] && [ -f "${ORIGENALITY_PROSE_SCORER}" ]; then
    run python3 "${ORIGENALITY_PROSE_SCORER}" semantic/README.md --strict
    PROSE="exécuté"
else
    echo "ORIGENALITY_PROSE_SCORER non défini : étape NON EXÉCUTÉE (pas réussie)."
    PROSE="non exécuté"
fi

# ---------------------------------------------------------------------------
echo
echo "== récapitulatif (mesuré, pas récité) =="
echo "étapes attendues à 0 : $STEPS_OK · contrôles négatifs tenus : $STEPS_NEG · prose : $PROSE"
run python3 scripts/proofs/recap.py \
    --merge "$TMP/merge_a" \
    --sans-isbn "$TMP/merge_sans_isbn" \
    --release "$TMP/release_check.json" \
    --semantic-next "$TMP/semantic_wave2.json"

echo
echo "== fin — toutes les étapes ont rendu le code attendu =="
