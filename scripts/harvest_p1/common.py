#!/usr/bin/env python3
"""Utilitaires partagés pour la moisson Origenality P1 (FR / ES / IT)."""
import json, os, re, time, unicodedata, urllib.parse, urllib.request
from datetime import datetime, timezone

# Chemins relatifs au dépôt : un chemin absolu de machine rendait la moisson
# injouable ailleurs (critère D4, reproductibilité).
BASE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "raw")
UA = "Origenality-research-harvester/1.0 (PhD thesis, romain.girardi@univ-cotedazur.fr)"

# racine « Origen » toutes graphies : Origène, Origen, Orígenes, Origene,
# origénisme, origenismo, origeniana, Origenes…  (n'attrape PAS « origine »)
RE_ORIG = re.compile(r"or[ií]g[eéèë]n", re.IGNORECASE)
# le nom espagnol d'Origène est « Orígenes » — homographe du pluriel commun
RE_ES_ALEX = re.compile(r"or[ií]genes\s+(de\s+)?alejandr|or[ií]genes\s+alejandrin", re.IGNORECASE)
RE_ES_COMMON = re.compile(
    r"\b(los|sus|nuestros|estos|esos|otros|dos|tres|posibles|nuevos|antiguos|"
    r"primeros|remotos|verdaderos|lejanos|profundos)\s+or[ií]genes\b|"
    r"\bor[ií]genes\s+(de|del|de\s+la|de\s+los|de\s+las|e|y)\b",
    re.IGNORECASE)
RE_ORIGENISM = re.compile(r"origenism|orig[eé]nism|origenian|orig[eé]nien|origeniana", re.IGNORECASE)

# disciplines/domaines manifestement hors SHS-antiquité
RE_OFF_DOMAIN = re.compile(
    r"\b(chimie|chemistry|biolog|m[ée]decine|medicin|pharmac|g[ée]nie|"
    r"informatique|math[ée]matique|physique|astrophys|nanotech|"
    r"agronom|v[ée]t[ée]rinaire|ing[ée]nierie|robotiq|[ée]lectroniq|"
    r"m[ée]canique|neurosc|oncolog|cardiolog|g[ée]olog|climat)", re.IGNORECASE)


def nfc(s):
    return unicodedata.normalize("NFC", s) if isinstance(s, str) else s


def has_orig(*texts):
    for t in texts:
        if t and RE_ORIG.search(nfc(str(t))):
            return True
    return False



# « origen » nom commun espagnol / portugais, et « aborígenes » : faux amis de
# la racine RE_ORIG. On les neutralise avant de tester la pertinence.
RE_ES_FAUX_AMI = re.compile(
    r"\bde\s+or[ií]gen\b|\babor[ií]gen\w*|\bor[ií]gen\s+"
    r"(social|[ée]tnic\w*|nacional|geogr[áa]fic\w*|animal|vegetal|familiar|"
    r"controlad\w*|del?\s)", re.IGNORECASE)


def has_orig_strict(*texts):
    """Comme has_orig, mais après neutralisation des faux amis espagnols."""
    for t in texts:
        if not t:
            continue
        cleaned = RE_ES_FAUX_AMI.sub(" ", nfc(str(t)))
        if RE_ORIG.search(cleaned):
            return True
    return False


RETRY_AFTER_MAX = 3600.0


def retry_after_seconds(error):
    """Délai demandé par le serveur dans l'en-tête `Retry-After`, s'il y en a un.

    L'en-tête se lit en secondes ou en date HTTP. Le rejouer au lieu de notre
    propre pause est la seule façon polie de traiter un 429 ou un 503 : le
    serveur a dit quand revenir, l'ignorer revient à insister.
    """
    headers = getattr(error, "headers", None)
    if headers is None:
        return None
    raw = headers.get("Retry-After")
    if not raw:
        return None
    raw = str(raw).strip()
    if raw.isdigit():
        return min(float(raw), RETRY_AFTER_MAX)
    try:
        from email.utils import parsedate_to_datetime
        moment = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        return None
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    delay = (moment - datetime.now(timezone.utc)).total_seconds()
    return min(max(delay, 0.0), RETRY_AFTER_MAX) if delay > 0 else 0.0


def get(url, tries=4, sleep=2.0, headers=None, timeout=90):
    """GET brut avec retries. Retourne les octets ou lève.

    Un `Retry-After` renvoyé par le serveur l'emporte sur notre propre pause.
    """
    h = {"User-Agent": UA, "Accept-Language": "fr,es,it,en"}
    if headers:
        h.update(headers)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa
            last = e
            wait = retry_after_seconds(e)
            time.sleep(wait if wait is not None else sleep * (i + 1))
    raise last


def get_json(url, **kw):
    return json.loads(get(url, **kw).decode("utf-8", "replace"))


class Sink:
    """Écriture JSONL incrémentale avec dédoublonnage sur source_id."""

    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.seen = {}
        self.order = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    sid = rec.get("source_id")
                    if sid and sid not in self.seen:
                        self.seen[sid] = rec
                        self.order.append(sid)
        self.dirty = False

    def add(self, rec):
        sid = rec["source_id"]
        if sid in self.seen:
            old = self.seen[sid]
            qm = sorted(set(old.get("query_matched", []) or []) | set(rec.get("query_matched", []) or []))
            if qm != old.get("query_matched"):
                old["query_matched"] = qm
                self.dirty = True
            for k, v in rec.items():
                if k == "query_matched":
                    continue
                if old.get(k) in (None, "", [], {}) and v not in (None, "", [], {}):
                    old[k] = v
                    self.dirty = True
            return False
        self.seen[sid] = rec
        self.order.append(sid)
        self.dirty = True
        return True

    def flush(self):
        if not self.dirty:
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for sid in self.order:
                f.write(json.dumps(self.seen[sid], ensure_ascii=False) + "\n")
        os.replace(tmp, self.path)
        self.dirty = False

    def __len__(self):
        return len(self.order)


def record(source, source_id, title=None, authors=None, year=None, language=None,
           container=None, rtype=None, url=None, abstract=None, abstract_rights=None,
           relation=None, noise_guess=None, query_matched=None):
    return {
        "source": source,
        "source_id": source_id,
        "title": nfc(title),
        "authors": [nfc(a) for a in (authors or []) if a],
        "year": year,
        "language": language,
        "container": nfc(container),
        "type": rtype,
        "url": url,
        "abstract": nfc(abstract),
        "abstract_rights": abstract_rights,
        "relation": relation,
        "noise_guess": noise_guess,
        "query_matched": sorted(set(query_matched or [])),
    }


def q(s):
    return urllib.parse.quote(s, safe="")
