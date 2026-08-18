"""Print the landing bust for the particle field.

Each particle is tinted with the colour of the pixel it was BORN on, then
drifts before it is drawn. A grain is therefore only visible where it has
crossed a tonal boundary: born on black it stays black on black, born inside a
smooth plane it lands on its own value. The dust draws itself along the edges
of the carving and nowhere else — which is the whole effect.

Two properties of the asset make or break it:

  - a true black ground, so the frame is not fogged with grains that have
    nothing to sit against;
  - smooth planes with hard edges. Marble has them; a painting does not, its
    brushwork is texture at exactly the scale of a grain.

So this is a hard darkroom print of a photograph that already has both: crush
the ground, hold the stone high and narrow, clip the key side.

    python3 scripts/treat_landing_portrait.py

Reads  assets-src/origen-bust.png         (the 16:9 4K master, not served)
Writes site/assets/marks/origen.jpg       (what the landing loads)
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets-src/origen-bust.png"
DST = ROOT / "site/assets/marks/origen.jpg"

WIDTH = 2560                       # what the landing actually needs
IN_BLACK, IN_WHITE, GAMMA = 0.085, 0.86, 0.94
CLARITY_RADIUS, CLARITY = 2.0, 0.45
SHADOW_ROLL = 0.30                 # below this the stone is let go entirely


def blur(u: np.ndarray, r: float) -> np.ndarray:
    img = Image.fromarray((np.clip(u, 0, 1) * 255).astype(np.uint8), "L")
    return np.asarray(img.filter(ImageFilter.GaussianBlur(r))).astype(np.float32) / 255.0


def ss(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)




def main() -> None:
    src = Image.open(SRC).convert("RGB")
    if src.width > WIDTH:
        src = src.resize((WIDTH, round(src.height * WIDTH / src.width)), Image.LANCZOS)
    a = np.asarray(src).astype(np.float32) / 255.0
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]

    lum = np.clip((lum - IN_BLACK) / (IN_WHITE - IN_BLACK), 0, 1) ** GAMMA

    # clarity: the carving reads at the scale the dust works at
    lum = np.clip(lum + (lum - blur(lum, CLARITY_RADIUS)) * CLARITY, 0, 1)

    # the shadow side goes all the way out, so a grain born there is invisible
    lum = lum * ss(0.0, SHADOW_ROLL, lum) ** 0.55

    lum = np.clip(lum + (lum * lum * (3 - 2 * lum) - lum) * 0.40, 0, 1)

    out = (lum * 255).astype(np.uint8)
    out[:2, :] = out[-2:, :] = 0
    out[:, :2] = out[:, -2:] = 0
    Image.fromarray(out, "L").convert("RGB").save(DST, quality=90, optimize=True)

    tone = out.astype(np.float32) / 255
    print(f"{DST.relative_to(ROOT)}: {out.shape[1]}x{out.shape[0]}, "
          f"{(tone < 0.02).mean():.1%} true black, {(tone > 0.96).mean():.1%} clipped white, "
          f"{DST.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
