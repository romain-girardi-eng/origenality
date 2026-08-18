"""Stamp the served CSS and JS with a content fingerprint.

The files under site/assets/ keep stable names — `explorer.js` stays
`explorer.js` from one release to the next — so a browser that has already
visited the site keeps serving its cached copy for as long as the cache
header allows. On 2026-08-18 that shipped a new welcome.html against a
four-hour-old base.css and the masthead came out unstyled for every returning
reader.

So each reference gets `?v=<first 8 hex of the file's sha256>`. The name is
untouched, the URL changes only when the bytes change, and a stale copy can no
longer be served against fresh markup. Idempotent: run it after any change
under site/assets/, before deploying.

    python3 scripts/stamp_assets.py [--check]

--check exits 1 if any stamp is missing or stale, and prints what is wrong.
"""
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
REF = re.compile(r'((?:href|src)=")(assets/[A-Za-z0-9_./-]+\.(?:css|js))(?:\?v=[0-9a-f]+)?(")')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


def main() -> int:
    check = "--check" in sys.argv
    stale: list[str] = []
    touched = 0

    for page in sorted(SITE.glob("*.html")):
        if re.search(r" \d+\.html$", page.name):      # iCloud conflict copies
            continue
        text = page.read_text(encoding="utf-8")

        def stamp(m: re.Match) -> str:
            asset = SITE / m.group(2)
            if not asset.exists():
                stale.append(f"{page.name}: {m.group(2)} introuvable")
                return m.group(0)
            return f"{m.group(1)}{m.group(2)}?v={digest(asset)}{m.group(3)}"

        out = REF.sub(stamp, text)
        if out != text:
            if check:
                stale.append(f"{page.name}: empreintes absentes ou périmées")
            else:
                page.write_text(out, encoding="utf-8")
                touched += 1

    if check:
        for line in stale:
            print(line)
        print("empreintes à jour" if not stale else f"{len(stale)} page(s) à re-tamponner")
        return 1 if stale else 0

    print(f"{touched} page(s) tamponnée(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
