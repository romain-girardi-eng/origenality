#!/usr/bin/env bash
# Origenality — l'arbre public rejoué depuis un clone, comme un tiers le reçoit.
#
# Un dépôt public tient sa promesse quand ses commandes marchent chez celui qui
# le clone, pas quand elles marchent chez celui qui l'écrit. L'audit 6 a montré
# l'écart : un outil remontait une racine de trop, un README prescrivait une
# géométrie qui n'existait plus, et rien ne s'en apercevait tant que tout
# tournait dans l'arbre d'origine, où les fichiers manquants sont là.
#
# Ce contrôle refait donc le geste du tiers : il clone le dépôt DANS un
# répertoire jetable (ignoré par git), y lance la suite de tests, y recompte
# tous les chiffres publiés, confronte ce que les pages nomment à ce que les
# données portent, y sert les pages et vérifie qu'elles répondent avec leur
# donnée. Il s'arrête au premier échec et sort non nul. Il rejoue le dernier
# COMMIT : un changement non commité n'y entre pas.
#
#     bash scripts/selftest_public.sh
#     bash scripts/selftest_public.sh --keep      # garder le clone pour inspecter
#
set -euo pipefail

# Les contrôles importent les modules du dépôt : aucun bytecode ne doit rester
# dans le clone, ni dans un arbre qu'on déploierait ensuite.
export PYTHONDONTWRITEBYTECODE=1

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1

WORK=$ROOT/_selftest
CLONE=$WORK/clone
STEP=0

say() { printf '\n== %s\n' "$1"; }
fail() { printf 'ÉCHEC (étape %d) : %s\n' "$STEP" "$1" >&2; exit 1; }
step() { STEP=$((STEP + 1)); say "$STEP. $1"; }

# Un clone jetable, dans le dépôt et hors de son suivi. `git clone` prend le
# dernier commit : c'est bien ce qu'un tiers reçoit, et non l'arbre de travail
# de celui qui lance le contrôle.
step "clone du dépôt dans un répertoire jetable"
rm -rf "$WORK"
mkdir -p "$WORK"
git clone --quiet --no-hardlinks . "$CLONE" || fail "git clone"
printf 'clone : %s (%s fichiers)\n' "_selftest/clone" \
    "$(find "$CLONE" -type f -not -path '*/.git/*' | wc -l | tr -d ' ')"
cd "$CLONE"

# La géométrie diffère d'un arbre à l'autre : `site/build-c/` dans le dépôt de
# travail, `site/` une fois publié. On prend celle qui existe.
if [ -d site/build-c ]; then BUILD=site/build-c; DATA=site/data; else BUILD=site; DATA=data; fi
[ -f "$BUILD/index.html" ] || fail "aucun répertoire de pages"

step "suites de tests"
# Chaque suite Python passe par `python3 -m unittest discover` sur son dossier :
# la même commande tourne dans les deux géométries, depuis la racine du clone,
# sans dépendre de la façon dont un fichier de test se lance lui-même. Les
# suites sont celles qui existent dans le clone, pas une liste écrite ici : un
# test ajouté est rejoué sans qu'on touche à ce script.
#
# Seul le verdict est repris : la sortie des tests porte les chemins des
# répertoires temporaires du système, et une preuve archivée n'a pas à les
# contenir.
: > "$WORK/tests.txt"
suite() {
    label=$1
    shift
    if "$@" > "$WORK/suite.txt" 2>&1; then
        cat "$WORK/suite.txt" >> "$WORK/tests.txt"
        verdict=$(grep -E '^Ran [0-9]+ tests?' "$WORK/suite.txt" | tail -1 || true)
        printf '  %-36s %s\n' "$label" "${verdict:-sortie 0}"
    else
        cat "$WORK/suite.txt" >> "$WORK/tests.txt"
        grep -E "^(FAIL|ERROR|FAILED)" "$WORK/suite.txt" >&2 || tail -40 "$WORK/suite.txt" >&2
        fail "$label"
    fi
}
# Un contrôle d'une ligne : sa dernière ligne de sortie, ou toute sa sortie s'il échoue.
gate() {
    label=$1
    shift
    "$@" > "$WORK/gate.txt" 2>&1 || { cat "$WORK/gate.txt" >&2; fail "$label"; }
    printf '  %-36s %s\n' "$label" "$(tail -1 "$WORK/gate.txt")"
}
suites=0
for test_file in scripts/test_*.py; do
    [ -f "$test_file" ] || continue
    name=$(basename "$test_file")
    # test_publish_export.py relit l'arbre public voisin et importe la passe
    # d'export : il ne sort pas du dépôt de travail et n'a rien à lire dans un
    # clone.
    [ "$name" = "test_publish_export.py" ] && continue
    suite "$test_file" python3 -m unittest discover -s scripts -p "$name"
    suites=$((suites + 1))
done
[ "$suites" -gt 0 ] || fail "aucune suite de tests sous scripts/"
if [ -d evidence/tests ]; then
    suite "evidence/tests" python3 -m unittest discover -s evidence/tests -p 'test_*.py'
elif ls evidence/*.py >/dev/null 2>&1; then
    fail "evidence/ est livré sans evidence/tests"
fi
# node est requis : sans lui, les tests du moteur de recherche et des exports, la
# comparaison au CLI et la relecture des liens de l'Observatoire ne tournent pas,
# et le selftest passait quand même (audit du 13/09, C-8).
command -v node >/dev/null 2>&1 || fail "node absent : tests node, CLI et liens non contrôlables"
for test_file in scripts/test_*.mjs; do
    [ -f "$test_file" ] || continue
    suite "$test_file" node "$test_file"
done

step "chiffres publiés recomptés depuis les données livrées"
python3 "$BUILD/tools/build_summary_figures.py" --check > /dev/null \
    || fail "$BUILD/tools/build_summary_figures.py --check"
printf 'tous les blocs générés sont à jour\n'

step "une population par écran"
python3 "$BUILD/qa/check_one_population.py" | tail -1 \
    || fail "$BUILD/qa/check_one_population.py"
python3 "$BUILD/tools/backfill_record_urls.py" --check > /dev/null \
    || fail "$BUILD/tools/backfill_record_urls.py --check"
python3 "$BUILD/tools/build_manifest.py" --check > /dev/null \
    || fail "$BUILD/tools/build_manifest.py --check"

# Les fichiers livrés que des outils écrivent, relus contre leur générateur, sans
# rien lire d'ignoré par git. Un clone n'a ni la moisson IxTheo ni la moisson de
# relecture : le contrôle du snapshot n'y vérifie que la structure des lignes,
# l'unicité de leurs clés et les corrections, et il le dit (--structure-only) ;
# le contenu des lignes se contrôle dans l'arbre de travail. Puis les croisements
# de l'Observatoire recomptés et confrontés au CLI, et les liens de notice de la
# publication précédente : le commit le plus récent du clone dont le graphe
# diffère, lu dans l'historique (un clone sans historique échoue).
step "données reconstruites (structure), croisements, liens de notice"
gate "build_public_snapshot.py --check --structure-only (structure, not content)" \
    python3 "$BUILD/tools/build_public_snapshot.py" --check --structure-only
gate "build_primary_layer.py --check" python3 "$BUILD/tools/build_primary_layer.py" --check
gate "build_cite_data.py --check" python3 "$BUILD/tools/build_cite_data.py" --check
gate "check_crossings.py" python3 "$BUILD/qa/check_crossings.py"
gate "check_source_id_continuity.py" python3 "$BUILD/qa/check_source_id_continuity.py"

# Ce que les pages nomment contre ce que les données portent (OR-04), les pages
# sous la politique du site et la 404 (OR-33, OR-42), les empreintes des
# feuilles, des scripts et des imports de modules (OR-66).
step "langues, poids, pages servies, empreintes"
gate "qa_checks.py site-codes" python3 scripts/qa_checks.py site-codes
gate "qa_checks.py served-pages" python3 scripts/qa_checks.py served-pages
gate "stamp_assets.py --check" python3 scripts/stamp_assets.py --check

step "les quatre pages servies, avec leur couche de données"
PORT=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
python3 -m http.server "$PORT" --bind 127.0.0.1 > /dev/null 2>&1 &
SERVER=$!
# Le serveur sort de la table des travaux : arrêté, il n'écrit pas « Terminated »
# au milieu d'une sortie qu'on archive comme preuve.
disown "$SERVER" 2>/dev/null || true
trap 'kill $SERVER 2>/dev/null || true' EXIT
# Le serveur est attendu, pas deviné : sur une machine où l'interpréteur démarre
# lentement, il a mis plus de vingt secondes à écouter, et une attente fixe de
# trois secondes faisait échouer l'étape sans que rien ne soit en défaut.
python3 - "$PORT" <<'PY' || fail "le serveur local ne répond pas après 90 s"
import sys, time, urllib.request
port = sys.argv[1]
deadline = time.monotonic() + 90
while True:
    try:
        with urllib.request.urlopen("http://127.0.0.1:%s/" % port, timeout=2):
            break
    except Exception:  # noqa: BLE001 — pas encore à l'écoute
        if time.monotonic() > deadline:
            sys.exit(1)
        time.sleep(0.5)
PY
for page in index.html observatoire.html methode.html credits.html; do
    code=$(python3 - "$PORT" "$BUILD/$page" <<'PY'
import sys, urllib.request
port, path = sys.argv[1], sys.argv[2]
try:
    with urllib.request.urlopen("http://127.0.0.1:%s/%s" % (port, path), timeout=5) as answer:
        print("%d %d" % (answer.status, len(answer.read())))
except Exception as error:  # noqa: BLE001 — le code de sortie porte le verdict
    print("0 %s" % error)
PY
)
    case "$code" in
        200\ *) printf '  %-20s %s octets\n' "$page" "${code#200 }" ;;
        *) fail "$page non servie ($code)" ;;
    esac
done
for asset in "$DATA/graph.json" "$DATA/evidence.json" "$BUILD/assets/semantic.json"; do
    code=$(python3 - "$PORT" "$asset" <<'PY'
import sys, urllib.request
port, path = sys.argv[1], sys.argv[2]
try:
    with urllib.request.urlopen("http://127.0.0.1:%s/%s" % (port, path), timeout=5) as answer:
        print("%d %d" % (answer.status, len(answer.read())))
except Exception as error:  # noqa: BLE001
    print("0 %s" % error)
PY
)
    case "$code" in
        200\ *) printf '  %-20s %s octets\n' "$(basename "$asset")" "${code#200 }" ;;
        *) fail "$asset non servi ($code)" ;;
    esac
done
# Une prise de position que evidence.json publie : le CLI doit la retrouver, pas
# seulement sortir en 0 sur une liste vide.
claims=$(node cli/origenality.mjs claims Scarponi --local . --limit 1 \
    | python3 -c 'import json, sys; print(json.load(sys.stdin)["matched"])') \
    || fail "cli/origenality.mjs claims"
[ "${claims:-0}" -gt 0 ] || fail "cli/origenality.mjs claims Scarponi : aucune prise de position"
printf '  %-20s %s\n' "claims Scarponi" "$claims"
kill $SERVER 2>/dev/null || true

step "la recherche du CLI et celle de la page répondent pareil"
(cd "$WORK/clone" && python3 scripts/check_search_parity.py --local) \
    || fail "le CLI et les règles de la recherche divergent"

if [ "$KEEP" = "0" ]; then
    cd "$ROOT"
    rm -rf "$WORK"
fi

printf '\n%d étapes, aucune en échec — un clone de ce dépôt tourne seul.\n' "$STEP"
