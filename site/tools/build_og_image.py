#!/usr/bin/env python3
"""L'image de partage — dessinée dans le langage graphique du site, jamais tapée.

Les réseaux et les moteurs affichent une vignette quand un lien est partagé, et
un PNG est le seul format qu'ils lisent tous : un SVG en `og:image` n'est pas
rendu. Cette image est donc produite ici, à partir des fontes du site et des
chiffres recomptés par `build_summary_figures.population()`, pour qu'aucun
nombre affiché ne soit saisi à la main et que la vignette suive le fond crème,
le rouge de la marque et l'astérisque hexaplaire des pages.

Le PNG produit est versionné : personne n'a besoin de rejouer ce script pour
servir le site. Il se rejoue quand la population change ou quand le libellé
bouge, et il demande alors deux paquets hors bibliothèque standard, Pillow et
fontTools (avec brotli, pour ouvrir les woff2 du site) — d'où sa place dans
`site/tools/` et non dans les commandes qu'un clone frais doit pouvoir lancer.

    python3 site/tools/build_og_image.py
    python3 site/tools/build_og_image.py --check   # sort en 1 si le PNG manque
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from tree_paths import repository_root  # noqa: E402

import build_summary_figures as figures  # noqa: E402

ROOT = Path(repository_root(str(HERE)))
BUILD = HERE.parent
ASSETS = BUILD / "assets"
OUT = ASSETS / "marks" / "og.png"

WIDTH, HEIGHT = 1200, 630

GROUND_LIFT = (247, 242, 230)
GROUND = (239, 233, 218)
GROUND_DEEP = (230, 222, 203)
INK = (35, 32, 27)
INK_2 = (90, 83, 70)
STONE = (106, 99, 83)
ACCENT = (160, 54, 32)


def ttf(woff2: Path, into: Path) -> Path:
    """Un woff2 du site rendu lisible par Pillow, sans quitter le dépôt."""
    from fontTools.ttLib import TTFont

    out = into / (woff2.stem + ".ttf")
    font = TTFont(str(woff2))
    font.flavor = None
    font.save(str(out))
    return out


def ground(image) -> None:
    """Le fond crème du site : clair au centre, plus dense sur les bords."""
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    cx, cy = WIDTH * 0.5, HEIGHT * 0.46
    far = (cx ** 2 + cy ** 2) ** 0.5
    for step in range(120, -1, -1):
        t = step / 120
        radius = far * t
        if t <= 0.52:
            u = t / 0.52
            colour = tuple(round(a + (b - a) * u) for a, b in zip(GROUND_LIFT, GROUND))
        else:
            u = (t - 0.52) / 0.48
            colour = tuple(round(a + (b - a) * u) for a, b in zip(GROUND, GROUND_DEEP))
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=colour)


def mark(image, x: float, y: float, size: float, colour, opacity: float = 1.0) -> None:
    """L'astérisque hexaplaire de la marque : une croix et quatre points."""
    from PIL import Image, ImageDraw

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    unit = size / 100.0
    fill = colour + (round(255 * opacity),)
    width = round(11 * unit)
    draw.line([(x + 50 * unit, y + 14 * unit), (x + 50 * unit, y + 86 * unit)],
              fill=fill, width=width)
    draw.line([(x + 14 * unit, y + 50 * unit), (x + 86 * unit, y + 50 * unit)],
              fill=fill, width=width)
    for dx, dy in ((27, 27), (73, 27), (27, 73), (73, 73)):
        r = 8 * unit
        draw.ellipse([x + dx * unit - r, y + dy * unit - r,
                      x + dx * unit + r, y + dy * unit + r], fill=fill)
    image.alpha_composite(layer)


def build() -> Path:
    from PIL import Image, ImageDraw, ImageFont

    values = figures.population(BUILD)
    counted = figures.spaced(values["counted"])

    image = Image.new("RGBA", (WIDTH, HEIGHT), GROUND)
    ground(image)
    # La marque en grand, coupée par le bord droit : une texture, pas un logo.
    mark(image, WIDTH - 210, (HEIGHT - 430) / 2, 430, ACCENT, 0.07)

    with tempfile.TemporaryDirectory() as work:
        into = Path(work)
        serif = ttf(ASSETS / "fonts" / "EBGaramond-VF.subset.woff2", into)
        text = ttf(ASSETS / "fonts" / "literata-var.woff2", into)
        title_font = ImageFont.truetype(str(serif), 104)
        sub_font = ImageFont.truetype(str(text), 34)
        foot_font = ImageFont.truetype(str(text), 24)

        draw = ImageDraw.Draw(image)
        left = 96
        # La croix se cale sur la hauteur d'œil du titre, comme dans le bandeau.
        mark(image, left - 4, 120, 62, ACCENT)
        draw = ImageDraw.Draw(image)
        draw.text((left + 78, 104), "Origenality", font=title_font, fill=INK, anchor="lt")
        draw.text((left, 300), "A bibliographic map of Origen studies",
                  font=sub_font, fill=INK_2, anchor="lt")
        draw.text((left, 356), "Where the scholarship is dense, and where it is thin.",
                  font=sub_font, fill=STONE, anchor="lt")
        draw.line([(left, 470), (WIDTH - left, 470)], fill=(35, 32, 27, 38), width=1)
        draw.text((left, 500),
                  "%s works counted · Index Theologicus, August 2026 · origenality.com"
                  % counted,
                  font=foot_font, fill=STONE, anchor="lt")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(OUT, "PNG", optimize=True)
    return OUT


def main(argv) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="ne rien dessiner, dire seulement si le PNG est là")
    args = parser.parse_args(argv)

    if args.check:
        if OUT.exists():
            print("%s : %d octets" % (OUT.relative_to(ROOT), OUT.stat().st_size))
            return 0
        print("%s manque" % OUT.relative_to(ROOT), file=sys.stderr)
        return 1

    path = build()
    print("%s : %d octets, %dx%d" % (path.relative_to(ROOT), path.stat().st_size,
                                     WIDTH, HEIGHT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
