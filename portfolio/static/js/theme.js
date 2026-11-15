// Runs before the page paints so the saved theme never flashes. Dark is the default.
(function () {
  var t = null;
  try { t = localStorage.getItem('theme'); } catch (e) {}
  if (t === 'light') document.documentElement.dataset.theme = 'light';
})();
// Page-to-page transitions can be cut short by a fast second click; that is fine, so keep it out of the console.
addEventListener('pagereveal', function (e) {
  if (e.viewTransition) { e.viewTransition.ready.catch(function () {}); e.viewTransition.finished.catch(function () {}); }
});
