#!/usr/bin/env python3
"""Engendre `vocabulary/tag_record.schema.json` depuis le vocabulaire du dépôt.

Le schéma publié n'est pas une pièce indépendante qu'on tiendrait à jour à la
main : c'est le rendu de `vocabulary_io.tag_record_schema(vocab, full=True)`.
La même fonction fabrique le schéma envoyé au moteur, ce qui est tout l'intérêt :
le contrôle a posteriori porte sur le schéma du contrôle a priori, et aucun des
deux ne peut prendre de l'avance sur l'autre. Auparavant, seules les
énumérations étaient tenues ensemble par les marqueurs `x-enum-source` ; le
reste divergeait, et de fait `uniqueItems` et les bornes de la confiance ne
figuraient que du côté publié.

    python3 semantic/build_tag_schema.py            # écrit
    python3 semantic/build_tag_schema.py --check    # sort 1 si le fichier est obsolète
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from vocabulary_io import load_vocabulary, tag_record_schema  # noqa: E402

OUT = HERE / "vocabulary" / "tag_record.schema.json"


def render(vocabulary_dir: Path | str | None = None) -> str:
    vocab = load_vocabulary(vocabulary_dir)
    return json.dumps(tag_record_schema(vocab, full=True),
                      ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="ne rien écrire ; sortir en erreur si le fichier est obsolète")
    parser.add_argument("--vocabulary", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=OUT)
    arguments = parser.parse_args(argv)

    text = render(arguments.vocabulary)
    if arguments.check:
        if not arguments.out.exists():
            print(f"ABSENT   {arguments.out}")
            return 1
        if arguments.out.read_text(encoding="utf-8") != text:
            print(f"OBSOLÈTE {arguments.out}")
            return 1
        print(f"À JOUR   {arguments.out}")
        return 0
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(text, encoding="utf-8")
    print(f"ÉCRIT    {arguments.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
