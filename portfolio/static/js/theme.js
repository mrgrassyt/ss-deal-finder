// Runs before the page paints so the saved choices never flash. The look, and the Theme Studio controls, live in one "studio" entry.
(function () {
  var d = document.documentElement, S = {}, t = null;
  try { S = JSON.parse(localStorage.getItem('studio') || '{}') || {}; } catch (e) {}
  try { t = localStorage.getItem('theme'); } catch (e) {}
  if (typeof S.look === 'string' && /^[a-z0-9-]{1,24}$/.test(S.look)) d.dataset.look = S.look;
  if (t === 'light' && d.dataset.look === 'aurora') d.dataset.theme = 'light';     // day and night belong to the Aurora look
  if (typeof S.anim === 'number') { d.style.setProperty('--ai', Math.max(0, Math.min(100, S.anim)) / 100); if (S.anim === 0) d.dataset.anim = 'off'; }
  if (S.motion === 'reduced') d.dataset.motion = 'reduced';
  if (S.fx === false) d.dataset.fx = 'off';
  if (S.d3 === false) d.dataset['3d'] = 'off';
  if (S.perf === true) d.dataset.perf = 'on';
})();
// Page-to-page transitions can be cut short by a fast second click; that is fine, so keep it out of the console.
addEventListener('pagereveal', function (e) {
  if (e.viewTransition) { e.viewTransition.ready.catch(function () {}); e.viewTransition.finished.catch(function () {}); }
});
