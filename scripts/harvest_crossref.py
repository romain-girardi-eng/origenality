#!/usr/bin/env python3
"""P1 Origenality — moisson Crossref (query.bibliographic, tri pertinence, CAP 3000/requête).

Sauvegarde incrémentale : cr_raw/<slug>.jsonl (une notice brute par ligne),
état dans cr_raw/_state.json. Reprise sur erreur : relancer le script.
Backoff exponentiel sur 429/503, `Retry-After` honoré. Aucune donnée fabriquée.

Reprise sans fenêtre de duplication : l'état porte, à côté du curseur, la
longueur du fichier de sortie AU DERNIER CURSEUR VALIDÉ. À la reprise, le
fichier est tronqué à cette longueur avant la première écriture, puis la page
du curseur enregistré est redemandée. Un plantage entre l'écriture d'une page
et la sauvegarde de l'état ne laisse donc ni doublon (la page inachevée est
tronquée) ni trou (son curseur n'a pas été avancé). L'ordre précédent —
écrire, vider le tampon, puis sauver le curseur — rejouait une page entière
après un plantage.
"""
import json, os, sys, time, urllib.parse, urllib.request

MAILTO = "romain.girardi@univ-cotedazur.fr"
UA = f"OrigenalityHarvest/1.0 (+https://openalex.org; mailto:{MAILTO})"
BASE = "https://api.crossref.org/works"
SCRATCH = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(SCRATCH, "cr_raw")
STATE = os.path.join(RAW, "_state.json")
SLEEP = 0.5
CAP = 3000
ROWS = 200

QUERIES = [
    ("origen_of_alexandria",  "Origen of Alexandria"),
    ("origene_fr",            "Origène"),
    ("origenes_alexandrinus", "Origenes Alexandrinus"),
    ("origen_contra_celsum",  "Origen Contra Celsum"),
    ("origen_de_principiis",  "Origen De principiis"),
    ("origeniana",            "Origeniana"),
]


def load_state():
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return {}


def save_state(st):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)



RETRY_AFTER_MAX = 3600.0   # une heure : le serveur peut demander plus de cinq minutes


def retry_after(error, fallback):
    """Délai demandé par le serveur (`Retry-After`), en secondes, sinon `fallback`.

    Le serveur dit quand revenir ; nos propres paliers ne sont qu'un défaut.
    """
    headers = getattr(error, "headers", None)
    raw = headers.get("Retry-After") if headers is not None else None
    if not raw:
        return fallback
    raw = str(raw).strip()
    if raw.isdigit():
        return min(float(raw), RETRY_AFTER_MAX)
    try:
        from email.utils import parsedate_to_datetime
        from datetime import datetime, timezone
        moment = parsedate_to_datetime(raw)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        delay = (moment - datetime.now(timezone.utc)).total_seconds()
        return min(max(delay, 0.0), RETRY_AFTER_MAX)
    except Exception:  # noqa: BLE001
        return fallback

def fetch(url, tries=7):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            wait = retry_after(e, min(120, 3 * (2 ** i)))
            sys.stderr.write(f"  ! {type(e).__name__} {e} — retry dans {wait}s\n")
            time.sleep(wait)
    raise RuntimeError(f"echec definitif: {last}")


def harvest(slug, qval, st):
    e = st.setdefault(slug, {"query": qval, "cursor": "*", "fetched": 0,
                             "total": None, "done": False, "capped": False,
                             "errors": [], "http_retries": 0,
                             "committed_bytes": 0})
    if e.get("done"):
        print(f"[skip] {slug} ({e['fetched']}/{e['total']})")
        return
    path = os.path.join(RAW, slug + ".jsonl")
    if e["cursor"] == "*" and os.path.exists(path):
        os.remove(path)
        e["fetched"] = 0
        e["committed_bytes"] = 0
    committed = int(e.get("committed_bytes") or 0)
    if os.path.exists(path) and os.path.getsize(path) > committed:
        with open(path, "r+b") as trunc:
            trunc.truncate(committed)
    out = open(path, "a", encoding="utf-8")
    pages = 0
    while True:
        params = {"query.bibliographic": qval, "rows": str(ROWS),
                  "cursor": e["cursor"], "mailto": MAILTO}
        url = BASE + "?" + urllib.parse.urlencode(params)
        try:
            data = fetch(url)
        except RuntimeError as err:
            e["errors"].append(str(err))
            out.close(); save_state(st)
            raise
        msg = data.get("message", {})
        if e["total"] is None:
            e["total"] = msg.get("total-results")
        items = msg.get("items", [])
        for it in items:
            it.pop("reference", None)  # allege : listes de references non requises en P1
            out.write(json.dumps(it, ensure_ascii=False) + "\n")
        out.flush()
        os.fsync(out.fileno())
        e["fetched"] += len(items)
        pages += 1
        nxt = msg.get("next-cursor")
        if not items or not nxt:
            e["done"] = True; e["cursor"] = None
            e["committed_bytes"] = out.tell()
            break
        if e["fetched"] >= CAP:
            e["done"] = True; e["capped"] = True; e["cursor"] = None
            e["committed_bytes"] = out.tell()
            break
        e["cursor"] = nxt
        e["committed_bytes"] = out.tell()
        save_state(st)
        time.sleep(SLEEP)
    out.close(); save_state(st)
    print(f"[ok] {slug}: {e['fetched']}/{e['total']} en {pages} page(s)"
          f"{' [CAP 3000]' if e['capped'] else ''}")


def main():
    os.makedirs(RAW, exist_ok=True)
    st = load_state()
    for slug, qval in QUERIES:
        harvest(slug, qval, st)
    save_state(st)
    print("TOTAL lignes brutes:", sum(v.get("fetched", 0) for v in st.values()))


if __name__ == "__main__":
    main()
