/* Origenality — boot the landing portrait. Every prop below is the original's,
   including the ones that look like they could be improved.

   The dust is tinted with the colour of the pixel each grain was BORN on and
   drawn over the picture, so a grain only shows where it has crossed a tonal
   boundary. That is why the speckle gathers on the hair, the edge of the
   shadow, the fold of the cloth, and appears nowhere else. It is also why the
   asset is printed the way it is — see scripts/treat_landing_portrait.py.

   Romain Girardi, 2026. */
(function () {
  var reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var land = document.querySelector('.land');
  var root = document.getElementById('land-field');
  var go = document.getElementById('enter');
  /* Motion refused, or no WebGL2 to run it: the still plate is the landing, and
     neither the particle module nor three.js is requested. The module is
     imported below this line, never above it, or the guard saves nothing. */
  if (!land || !root || reduce || typeof WebGL2RenderingContext === 'undefined') return;

  var narrow = matchMedia('(max-width:760px)').matches;

  /* framing only: the aim point is read from the stylesheet, which frames the
     still plate with the same two numbers (landing.css, --focus-x and
     --focus-y). A portrait frame, phone or tablet, is aimed at the head; a
     landscape frame keeps the centre. The plate and the canvas cannot drift. */
  var style = getComputedStyle(land);
  var fx = parseFloat(style.getPropertyValue('--focus-x'));
  var fy = parseFloat(style.getPropertyValue('--focus-y'));
  var focus = isFinite(fx) && isFinite(fy) ? [fx, fy] : [0.5, 0.46];

  import('./particle-image.js?v=369249b4').then(function (module) {
    var field = module.mountParticleImage(root, {
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

      focus: focus,

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
  });
})();
