"""Stamp the served CSS and JS with a content fingerprint.

The files under site/assets/ keep stable names — `explorer.js` stays
`explorer.js` from one release to the next — so a browser that has already
visited the site keeps serving its cached copy for as long as the cache
header allows. On 2026-08-18 that shipped a new welcome.html against a
four-hour-old base.css and the masthead came out unstyled for every returning
reader.

So each reference gets `?v=<first 8 hex of the sha256 of the file as served>`:

* `href`/`src` references to `assets/*.css|js` in the pages, and to
  `/site/assets/*.css|js` in the pages at the deployment root (`404.html` is
  served under any depth and addresses its stylesheets absolutely);
* relative ES-module specifiers inside the scripts themselves
  (`import ... from './dust-field.js'`, `export ... from`, `import('./x.js')`).
  A module imported under a bare name keeps a stable URL while its parent's
  stamp changes, and a browser can pair a fresh parent with a stale child.

Modules are stamped leaves first: a child's stamp is part of its parent's
bytes, so the parent's fingerprint is taken on the parent as it will be
served. Two importers of one file resolve to one URL, which keeps a single
module instance (three.js loaded twice breaks its own class checks).

The pages are found in either geometry, by the marker the pages carry, as
`site/build-c/tools/tree_paths.py` finds the data layer: `site/build-c/` in the
working tree, `site/` in the public tree. Idempotent: run it after any change
under the assets, before exporting.

    python3 scripts/stamp_assets.py [--check] [--root DIR]

--check exits 1 if any stamp is missing or stale, and prints what is wrong.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REF = re.compile(
    r'((?:href|src)=")((?:/site/)?)(assets/[A-Za-z0-9_./-]+\.(?:css|js))(?:\?v=[0-9a-f]+)?(")')
IMPORT = re.compile(
    r"""(\b(?:from|import)\s*\(?\s*)(['"])(\.{1,2}/[A-Za-z0-9_./-]+\.js)"""
    r"""(?:\?v=[0-9a-f]+)?(\2)""")
# iCloud conflict copies: « index 3.html », « assets 6/ ».
CONFLICT = re.compile(r" \d+(?:\.[A-Za-z0-9]+)?$")


def pages_dir(root: Path) -> Path:
    """The directory that holds the pages, in whichever geometry this tree has."""
    for candidate in (root / "site" / "build-c", root / "site"):
        if (candidate / "index.html").is_file():
            return candidate
    return root / "site"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:8]


def conflict_copy(path: Path, base: Path) -> bool:
    return any(CONFLICT.search(part) for part in path.relative_to(base).parts)


class Stamper:
    """Every asset's bytes as served, its own imports stamped, memoised."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.pages = pages_dir(root)
        self.served_bytes: dict[Path, bytes] = {}
        self.open: set[Path] = set()
        self.problems: list[str] = []

    def shown(self, path: Path) -> str:
        return Path(os.path.relpath(path, self.root)).as_posix()

    def served(self, path: Path) -> bytes:
        path = Path(os.path.normpath(path))
        if path in self.served_bytes:
            return self.served_bytes[path]
        raw = path.read_bytes()
        if path.suffix != ".js":
            self.served_bytes[path] = raw
            return raw
        if path in self.open:
            self.problems.append(f"{self.shown(path)}: cycle d'imports")
            return raw
        self.open.add(path)

        def stamp(match: re.Match) -> str:
            target = Path(os.path.normpath(path.parent / match.group(3)))
            if not target.is_file():
                self.problems.append(f"{self.shown(path)}: {match.group(3)} introuvable")
                return match.group(0)
            return (f"{match.group(1)}{match.group(2)}{match.group(3)}"
                    f"?v={digest(self.served(target))}{match.group(4)}")

        out = IMPORT.sub(stamp, raw.decode("utf-8")).encode("utf-8")
        self.open.discard(path)
        self.served_bytes[path] = out
        return out

    def page(self, page: Path, at_root: bool) -> bytes:
        text = page.read_bytes().decode("utf-8")

        def stamp(match: re.Match) -> str:
            base = self.pages if (match.group(2) or not at_root) else self.root
            asset = base / match.group(3)
            if not asset.is_file():
                self.problems.append(f"{self.shown(page)}: {match.group(2)}{match.group(3)} introuvable")
                return match.group(0)
            return (f"{match.group(1)}{match.group(2)}{match.group(3)}"
                    f"?v={digest(self.served(asset))}{match.group(4)}")

        return REF.sub(stamp, text).encode("utf-8")


def plan(root: Path) -> tuple[dict[Path, bytes], list[str], int]:
    """(files whose bytes must change, problems, files read)."""
    stamper = Stamper(root)
    pages = stamper.pages
    changes: dict[Path, bytes] = {}
    read = 0
    if not (pages / "index.html").is_file():
        return changes, ["aucun répertoire de pages sous site/build-c/ ni site/"], read

    scripts = sorted(path for path in (pages / "assets").rglob("*.js")
                     if path.is_file() and not conflict_copy(path, pages))
    for script in scripts:
        read += 1
        out = stamper.served(script)
        if out != script.read_bytes():
            changes[script] = out

    documents = [(page, False) for page in sorted(pages.glob("*.html"))]
    documents += [(page, True) for page in sorted(root.glob("*.html"))]
    for page, at_root in documents:
        if conflict_copy(page, root):
            continue
        read += 1
        out = stamper.page(page, at_root)
        if out != page.read_bytes():
            changes[page] = out
    return changes, stamper.problems, read


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="report missing or stale stamps, write nothing")
    parser.add_argument("--root", type=Path, default=ROOT,
                        help="tree to stamp (default: this repository)")
    arguments = parser.parse_args(argv)
    root = arguments.root.resolve()

    changes, problems, read = plan(root)

    def shown(path: Path) -> str:
        return Path(os.path.relpath(path, root)).as_posix()

    for line in problems:
        print(line)
    if arguments.check:
        for path in sorted(changes):
            print(f"{shown(path)}: empreintes absentes ou périmées")
        if not changes and not problems:
            print(f"empreintes à jour ({read} fichiers lus, pages et imports de modules)")
            return 0
        print(f"{len(changes)} fichier(s) à re-tamponner, {len(problems)} référence(s) en défaut")
        return 1

    for path in sorted(changes):
        path.write_bytes(changes[path])
    print(f"{len(changes)} fichier(s) tamponné(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
