/* Origenality — shared chrome: close the Pages fold when the reader
   taps outside it or presses Escape. Romain Girardi, 2026. */
(function () {
  'use strict';
  var fold = document.querySelector('.nav-fold');
  if (!fold) return;
  document.addEventListener('click', function (e) {
    if (!fold.open) return;
    if (!fold.contains(e.target)) fold.removeAttribute('open');
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && fold.open) fold.removeAttribute('open');
  });
})();
