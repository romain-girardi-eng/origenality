#!/usr/bin/env bash
# Origenality — la capture des chiffres affichés, prise sur le DOM rendu.
#
# `check_one_population.py` compare ce que la donnée donne à ce que les pages
# impriment. La seconde moitié valait ce que valait sa capture : elle avait été
# relevée à la main une fois, et l'audit 5 a demandé qu'elle soit soit refaite
# sur le DOM courant, soit datée. Elle est refaite ici, par un rendu sans écran,
# et le fichier qui en sort porte l'heure du rendu et l'adresse servie.
#
#     bash site/build-c/qa/capture_population.sh [session] [base] [sortie]
#
# Le serveur doit tourner à la racine du dépôt : `python3 -m http.server 8020`.
# L'adresse par défaut est celle des pages RELATIVEMENT à cette racine —
# `/site/build-c/` dans le dépôt de travail, `/site/` dans un clone public, où
# la passe de publication a supprimé une marche : rien à retaper d'un arbre à
# l'autre.
# La session du navigateur est refermée par l'appelant, jamais ici : le même
# navigateur sert ensuite aux captures d'écran.
set -euo pipefail

SESSION=${1:-origenality-capture}
HERE=$(cd "$(dirname "$0")" && pwd)
BUILD=$(dirname "$HERE")

# La racine se cherche à ses documents plutôt que de se compter en marches.
ROOT=$BUILD
while [ "$ROOT" != "/" ] && [ ! -f "$ROOT/CITATION.cff" ]; do
    ROOT=$(dirname "$ROOT")
done
BASE=${2:-http://127.0.0.1:8020/${BUILD#"$ROOT"/}/}
OUT=${3:-$HERE/measured_$(date +%Y-%m-%d).json}
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# Le navigateur repart à froid : un script rendu la veille et resté en cache
# ferait passer une capture pour une mesure du jour.
bu --session "$SESSION" close > /dev/null 2>&1 || true

viewport() {
    # L'ordre compte : la taille se pose sur la cible ouverte, donc après la
    # navigation. Posée avant, elle est écrasée par l'ouverture de la page.
    bu --session "$SESSION" python "$(cat <<PY
browser.goto("$4")
browser._run(browser._session._cdp_set_viewport($1, $2, device_scale_factor=$3))
browser.wait(2)
print(browser.url)
PY
)" > /dev/null
}

read_dom() {
    bu --session "$SESSION" --json eval "$1" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["result"])'
}

# ------------------------------------------------------------------ Explorer
INDEX_JS=$(cat <<'JS'
(function () {
  function pair(node) {
    var box = node.querySelector('.n');
    var value = box ? box.textContent.trim() : '';
    var copy = node.cloneNode(true);
    var mark = copy.querySelector('.n');
    if (mark) mark.remove();
    return [copy.textContent.trim(), value];
  }
  var scope = document.querySelector('.scope').textContent.trim();
  var held = document.querySelector('.held-note').textContent.trim();
  var legend = [].map.call(document.querySelectorAll('#legend .lg'), pair);
  var wizard = {}, kinds = ['work', 'approach', 'decade', 'lang'];
  document.getElementById('wiz-open').click();
  for (var i = 0; i < kinds.length; i++) {
    wizard[kinds[i]] = {
      note: document.getElementById('wiz-note').textContent.trim(),
      chips: [].map.call(document.querySelectorAll('#wiz-chips .chip'), pair)
    };
    if (i < kinds.length - 1) document.getElementById('wiz-next').click();
  }
  return JSON.stringify({
    explorer_scope: scope, explorer_held: held,
    explorer_legend: legend, wizard: wizard,
    viewport: window.innerWidth + 'x' + window.innerHeight +
      ' at DPR ' + window.devicePixelRatio
  });
})()
JS
)

# --------------------------------------------------------------- Observatory
OBS_JS=$(cat <<'JS'
(function () {
  function rows(id) {
    return [].map.call(document.querySelectorAll('#' + id + ' .brow'), function (row) {
      var label = row.querySelector('.lb').cloneNode(true);
      var sub = label.querySelector('small');
      if (sub) sub.remove();
      // une barre peut traîner sa part en pourcentage dans un second span :
      // on lit le compte seul, pas le compte collé à sa part
      var value = row.querySelector('.vv').cloneNode(true);
      [].forEach.call(value.querySelectorAll('span'), function (extra) { extra.remove(); });
      return [label.textContent.trim(), value.textContent.trim()];
    });
  }
  var table = document.getElementById('table-decade');
  var head = [].map.call(table.querySelectorAll('thead th'), function (cell) {
    return cell.textContent.trim();
  });
  var body = [].map.call(table.querySelectorAll('tbody tr'), function (line) {
    return [].map.call(line.querySelectorAll('th, td'), function (cell) {
      return cell.textContent.trim();
    });
  });
  return JSON.stringify({
    observatory_stamp: document.getElementById('stamp').textContent.trim(),
    observatory_sets: [].map.call(document.querySelectorAll('#key-sets > span'), function (row) {
      return [row.querySelector('b').textContent.trim(),
              row.textContent.replace(/\s+/g, ' ').trim()];
    }),
    observatory_lang: rows('bars-lang'),
    observatory_fmt: rows('bars-fmt'),
    observatory_decades: body,
    observatory_decade_head: head,
    observatory_review: document.getElementById('review-note').textContent.trim(),
    observatory_timenote: document.getElementById('time-note').textContent.trim()
  });
})()
JS
)

# Une capture doit lire la page telle qu'elle est sur le disque, pas telle que
# le navigateur se la rappelle : un paramètre qui change à chaque passe suffit
# à écarter le cache, sur la page comme sur ses scripts.
STAMP=$(date +%s)
viewport 1440 900 2 "${BASE}index.html?v=$STAMP"
read_dom "$INDEX_JS" > "$WORK/index.json"
viewport 1440 900 2 "${BASE}observatoire.html?v=$STAMP"
read_dom "$OBS_JS" > "$WORK/observatoire.json"

python3 - "$WORK/index.json" "$WORK/observatoire.json" "$OUT" "$BASE" <<'PY'
import json, sys
from datetime import datetime

index, observatory, out, base = sys.argv[1:5]
measured = json.loads(open(index, encoding="utf-8").read())
measured.update(json.loads(open(observatory, encoding="utf-8").read()))
viewport = measured.pop("viewport", "unknown")
measured["_measured"] = "%s, %s, %s, headless render" % (
    datetime.now().strftime("%Y-%m-%d %H:%M"), base, viewport)
with open(out, "w", encoding="utf-8") as handle:
    json.dump(measured, handle, ensure_ascii=False, indent=1)
    handle.write("\n")
print("wrote %s — %s" % (out, measured["_measured"]))
PY
