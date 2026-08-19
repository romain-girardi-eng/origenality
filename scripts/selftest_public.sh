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
# tous les chiffres publiés, y sert les pages et vérifie que les quatre
# répondent avec leur donnée. Il s'arrête au premier échec et sort non nul.
#
#     bash scripts/selftest_public.sh
#     bash scripts/selftest_public.sh --keep      # garder le clone pour inspecter
#
set -euo pipefail

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
if [ -d site/build-c ]; then BUILD=site/build-c; else BUILD=site; fi
[ -f "$BUILD/index.html" ] || fail "aucun répertoire de pages"

step "suite de tests"
# Seul le verdict est repris : la sortie des tests porte les chemins des
# répertoires temporaires du système, et une preuve archivée n'a pas à les
# contenir.
python3 scripts/test_data_gates.py > "$WORK/tests.txt" 2>&1 \
    || { grep -E "^(FAILED|ERROR)" "$WORK/tests.txt" >&2; fail "scripts/test_data_gates.py"; }
grep -E "^(Ran |OK)" "$WORK/tests.txt"

step "chiffres publiés recomptés depuis les données livrées"
python3 "$BUILD/tools/build_summary_figures.py" --check > /dev/null \
    || fail "$BUILD/tools/build_summary_figures.py --check"
printf 'tous les blocs générés sont à jour\n'

step "une population par écran"
python3 "$BUILD/qa/check_one_population.py" | tail -1 \
    || fail "$BUILD/qa/check_one_population.py"

step "les quatre pages servies, avec leur couche de données"
PORT=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
python3 -m http.server "$PORT" --bind 127.0.0.1 > /dev/null 2>&1 &
SERVER=$!
# Le serveur sort de la table des travaux : arrêté, il n'écrit pas « Terminated »
# au milieu d'une sortie qu'on archive comme preuve.
disown "$SERVER" 2>/dev/null || true
trap 'kill $SERVER 2>/dev/null || true' EXIT
sleep 3
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
for asset in data/graph.json "$BUILD/assets/semantic.json"; do
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
kill $SERVER 2>/dev/null || true

step "la recherche du CLI et celle de la page répondent pareil"
if command -v node >/dev/null 2>&1; then
    (cd "$WORK/clone" && python3 scripts/check_search_parity.py --local) \
        || fail "le CLI et les règles de la recherche divergent"
    (cd "$WORK/clone" && python3 scripts/stamp_assets.py --check >/dev/null) \
        || fail "une page référence un asset dont l'empreinte est périmée"
else
    printf '  node absent : parité de la recherche non contrôlée\n'
fi

if [ "$KEEP" = "0" ]; then
    cd "$ROOT"
    rm -rf "$WORK"
fi

printf '\n%d étapes, aucune en échec — un clone de ce dépôt tourne seul.\n' "$STEP"
