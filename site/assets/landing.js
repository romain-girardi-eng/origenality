/* Origenality — boot the landing portrait. Every prop below is the original's,
   including the ones that look like they could be improved.

   The dust is tinted with the colour of the pixel each grain was BORN on and
   drawn over the picture, so a grain only shows where it has crossed a tonal
   boundary. That is why the speckle gathers on the hair, the edge of the
   shadow, the fold of the cloth, and appears nowhere else. It is also why the
   asset is printed the way it is — see scripts/treat_landing_portrait.py.

   Romain Girardi, 2026. */
import { mountParticleImage } from './particle-image.js';

(function () {
  var reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var land = document.querySelector('.land');
  var root = document.getElementById('land-field');
  var go = document.getElementById('enter');
  if (!land || !root || reduce) return;

  var narrow = matchMedia('(max-width:760px)').matches;

  var field = mountParticleImage(root, {
    imageUrl: 'assets/marks/origen.jpg',

    particleCount: narrow ? 120000 : 250000,
    particleSize: 2,
    particleOpacity: 0.5,
    speed: 1,
    noiseScale: 0.004,
    noiseStrength: 0.04,
    damping: 0.98,
    lifespan: 400,
    showImage: true,
    imageOpacity: 1,
    cursorInteraction: !narrow,
    cursorStrength: 0.08,
    cursorRadius: 90,
    dpr: 2,

    /* framing only: the plate is 16:9 and the frame is close to it, so cover
       barely crops. On a phone the bust is aimed at the head. */
    focus: narrow ? [0.24, 0.34] : [0.5, 0.46],

    graph: { clusters: narrow ? 9 : 14, filamentShare: 0.20 },

    onLive: function () {
      requestAnimationFrame(function () { land.classList.add('is-live'); });
    }
  });

  /* the departure: the dust leaves the portrait, gathers into a graph, and
     only then does the Explorer open */
  if (go && field && field.toGraph) {
    var leaving = false;
    go.addEventListener('click', function (event) {
      if (leaving || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
      event.preventDefault();
      leaving = true;
      land.classList.add('is-leaving');
      field.toGraph(1700).then(function () {
        land.classList.add('is-gone');
        setTimeout(function () { window.location.href = go.getAttribute('href'); }, 420);
      });
    });
  }
})();
