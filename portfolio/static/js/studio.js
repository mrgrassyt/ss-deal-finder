// Theme Studio: pick a look, try it in the preview, then commit it. The choice lives in localStorage ("studio"), read by theme.js before paint.
(() => {
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const root = document.documentElement, sp = $('#sp'), KEY = 'studio';
  if (!sp) return;
  const fallbackLook = root.dataset.defaultLook || 'aurora';
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) {}
  const state = {
    look: saved.look || root.dataset.look || fallbackLook, anim: typeof saved.anim === 'number' ? saved.anim : 100,
    motion: saved.motion === 'reduced', fx: saved.fx !== false, d3: saved.d3 !== false, perf: saved.perf === true,
  };
  const items = $$('.st-item'), names = Object.fromEntries(items.map(b => [b.dataset.look, b.dataset.name]));
  if (!names[state.look]) state.look = fallbackLook;
  let inUse = state.look;

  const set = (n, k, v) => (v ? n.setAttribute(k, v) : n.removeAttribute(k));
  const paint = (n, s) => {                         // the same attributes the whole site reads
    n.dataset.look = s.look;
    n.style.setProperty('--ai', s.anim / 100);
    set(n, 'data-anim', s.anim === 0 ? 'off' : '');
    set(n, 'data-motion', s.motion ? 'reduced' : '');
    set(n, 'data-fx', s.fx ? '' : 'off');
    set(n, 'data-3d', s.d3 ? '' : 'off');
    set(n, 'data-perf', s.perf ? 'on' : '');
  };
  const msg = t => { $('#st-msg').textContent = t; };
  const show = () => {
    paint(sp, state);
    items.forEach(b => {
      const on = b.dataset.look === state.look;
      b.setAttribute('aria-checked', on);
      b.tabIndex = on ? 0 : -1;
      $('.st-now', b).hidden = b.dataset.look !== inUse;
    });
    $('#st-anim').value = state.anim; $('#st-anim-o').textContent = state.anim;
    $('#st-motion').checked = state.motion; $('#st-fx').checked = state.fx; $('#st-3d').checked = state.d3; $('#st-perf').checked = state.perf;
  };
  const choose = look => { state.look = look; msg(''); show(); };

  items.forEach((b, i) => {
    b.addEventListener('click', () => choose(b.dataset.look));
    b.addEventListener('keydown', e => {
      const d = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[e.key];
      if (!d) return;
      e.preventDefault();
      const next = items[(i + d + items.length) % items.length];
      next.focus(); choose(next.dataset.look);
    });
  });
  $('#st-anim').addEventListener('input', e => { state.anim = +e.target.value; $('#st-anim-o').textContent = state.anim; paint(sp, state); });
  [['#st-motion', 'motion'], ['#st-fx', 'fx'], ['#st-3d', 'd3'], ['#st-perf', 'perf']].forEach(([sel, k]) => $(sel).addEventListener('change', e => { state[k] = e.target.checked; msg(''); show(); }));

  $('#st-use').addEventListener('click', () => {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { msg('This browser would not save the choice, but the look is on for this visit.'); }
    inUse = state.look;
    paint(root, state);
    if (state.look !== 'aurora') root.removeAttribute('data-theme');
    else { try { if (localStorage.getItem('theme') === 'light') root.dataset.theme = 'light'; } catch (e) {} }
    show();
    msg(`${names[state.look]} is on. It is saved on this device.`);
  });
  $('#st-reset').addEventListener('click', () => {
    try { localStorage.removeItem(KEY); } catch (e) {}
    Object.assign(state, { look: fallbackLook, anim: 100, motion: false, fx: true, d3: true, perf: false });
    inUse = fallbackLook;
    paint(root, state);
    ['data-anim', 'data-motion', 'data-fx', 'data-3d', 'data-perf'].forEach(a => root.removeAttribute(a));
    root.style.removeProperty('--ai');
    if (fallbackLook !== 'aurora') root.removeAttribute('data-theme');
    show();
    msg('Back to the site default.');
  });

  show();
})();
