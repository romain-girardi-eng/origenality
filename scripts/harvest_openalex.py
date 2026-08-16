#!/usr/bin/env python3
"""P1 Origenality — moisson OpenAlex (works, title_and_abstract.search).

Sauvegarde incrémentale : une ligne JSON brute par notice dans RAW/<slug>.jsonl,
état (curseur, compteurs) dans RAW/_state.json. Reprise sur erreur : relancer.
Aucune donnée fabriquée : tout provient de la réponse API.

Reprise sans fenêtre de duplication : l'état porte, à côté du curseur, la
longueur du fichier de sortie AU DERNIER CURSEUR VALIDÉ. À la reprise, le
fichier est tronqué à cette longueur avant la première écriture, puis la page
du curseur enregistré est redemandée. Un plantage entre l'écriture d'une page
et la sauvegarde de l'état ne laisse donc ni doublon (la page inachevée est
tronquée) ni trou (son curseur n'a pas été avancé). L'ordre précédent —
écrire, vider le tampon, puis sauver le curseur — rejouait une page entière
après un plantage.
"""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error

MAILTO = "romain.girardi@univ-cotedazur.fr"
BASE = "https://api.openalex.org/works"
SELECT = ("id,doi,title,display_name,publication_year,language,type,authorships,"
          "primary_location,primary_topic,topics,abstract_inverted_index,"
          "cited_by_count,referenced_works_count")
SCRATCH = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(SCRATCH, "oa_raw")
STATE = os.path.join(RAW, "_state.json")
SLEEP = 0.15

# (slug, valeur du filtre title_and_abstract.search)
QUERIES = [
    ("phrase_origen_of_alexandria", '"origen of alexandria"'),
    ("origen_alexandria",           "origen alexandria"),
    ("origene_fr",                  "origène"),
    ("origenes",                    "origenes"),
    ("origene_it",                  "origene"),
    ("orygenes",                    "orygenes"),
    ("origenis",                    "origenis"),
    ("origenem",                    "origenem"),
    ("origeniana_um",               "origenianum|origeniana"),
    ("origenes_macron",             "ōrigenēs"),
    ("origen_celsus",               "origen celsus"),
    ("origen_contra_celsum",        "origen contra celsum"),
    ("origen_de_principiis",        "origen de principiis"),
    ("origen_peri_archon",          "origen peri archon"),
    ("origen_hexapla",              "origen hexapla"),
    ("origen_philocalia",           "origen philocalia"),
    ("origen_rufinus",              "origen rufinus"),
    ("origen_commentary_romans",    "origen commentary romans"),
    ("origen_apokatastasis",        "origen apokatastasis"),
    ("origen_alexandrian",          "origen alexandrian"),
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

def fetch(url, tries=6):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": f"OrigenalityHarvest/1.0 (mailto:{MAILTO})",
                "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            wait = retry_after(e, min(60, 2 ** i))
            sys.stderr.write(f"  ! {type(e).__name__} {e} — retry dans {wait}s\n")
            time.sleep(wait)
    raise RuntimeError(f"echec definitif: {last}")


def harvest(slug, qval, st):
    entry = st.setdefault(slug, {"query": qval, "cursor": "*", "fetched": 0,
                                 "count": None, "done": False, "errors": [],
                                 "committed_bytes": 0})
    if entry.get("done"):
        print(f"[skip] {slug} (deja complet: {entry['fetched']}/{entry['count']})")
        return
    path = os.path.join(RAW, slug + ".jsonl")
    # reprise : si on repart de zero, on repart d'un fichier vide
    if entry["cursor"] == "*" and os.path.exists(path):
        os.remove(path)
        entry["fetched"] = 0
        entry["committed_bytes"] = 0
    # Tout ce qui a été écrit au-dela du dernier curseur validé appartient a une
    # page dont l'état n'a pas été sauvé : on la retire avant de la redemander.
    committed = int(entry.get("committed_bytes") or 0)
    if os.path.exists(path) and os.path.getsize(path) > committed:
        with open(path, "r+b") as trunc:
            trunc.truncate(committed)
    out = open(path, "a", encoding="utf-8")
    page = 0
    while True:
        params = {
            "filter": "title_and_abstract.search:" + qval,
            "per-page": "200",
            "cursor": entry["cursor"],
            "select": SELECT,
            "mailto": MAILTO,
        }
        url = BASE + "?" + urllib.parse.urlencode(params)
        try:
            data = fetch(url)
        except RuntimeError as e:
            entry["errors"].append(str(e))
            out.close(); save_state(st)
            raise
        meta = data.get("meta", {})
        if entry["count"] is None:
            entry["count"] = meta.get("count")
        results = data.get("results", [])
        for rec in results:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        out.flush()
        os.fsync(out.fileno())
        entry["fetched"] += len(results)
        page += 1
        nxt = meta.get("next_cursor")
        if not results or not nxt:
            entry["done"] = True
            entry["cursor"] = None
            entry["committed_bytes"] = out.tell()
            break
        # le curseur et la longueur validée avancent ensemble, une fois la page
        # entièrement sur disque
        entry["cursor"] = nxt
        entry["committed_bytes"] = out.tell()
        save_state(st)
        time.sleep(SLEEP)
    out.close()
    save_state(st)
    print(f"[ok] {slug}: {entry['fetched']}/{entry['count']} en {page} page(s)")


def main():
    os.makedirs(RAW, exist_ok=True)
    st = load_state()
    for slug, qval in QUERIES:
        harvest(slug, qval, st)
    save_state(st)
    tot = sum(v.get("fetched", 0) for v in st.values())
    print(f"TOTAL lignes brutes: {tot}")


if __name__ == "__main__":
    main()
