// Big Picture: full screen, everything 1.5× larger, and the whole app usable from a game controller or the keyboard.
//   Controller (standard mapping, e.g. Xbox / PlayStation): D-pad or left stick move, A select, B back, LB/RB previous/next page,
//   LT/RT previous/next sub-tab, X search, right stick scrolls, Menu/Start leaves Big Picture.
//   Keyboard: arrows move, Enter select, Backspace back, Q/E pages, [ and ] sub-tabs, / search, Alt+Enter or F9 leaves.
const root = document.documentElement;
export const isOn = () => root.dataset.bp === 'on';

// ------------------------------------------------------------------ enter / leave
async function nativeFullscreen(want) {
  try {
    const api = window.pywebview && window.pywebview.api;                  // desktop app: resize the real window
    if (api && api.set_fullscreen) { await api.set_fullscreen(want); return; }
    if (want && !document.fullscreenElement && root.requestFullscreen) await root.requestFullscreen({ navigationUI: 'hide' });
    if (!want && document.fullscreenElement) await document.exitFullscreen();
  } catch (e) { /* not allowed here (e.g. inside a preview): the large layout still applies inside the window */ }
}
export function setBigPicture(on) {
  if (on === isOn()) return;
  if (on) root.dataset.bp = 'on'; else delete root.dataset.bp;
  nativeFullscreen(on);
  hintBar();
  document.querySelectorAll('#bp-btn').forEach((b) => b.setAttribute('aria-pressed', String(on)));
  if (on) setTimeout(() => focusFirst(), 60);
  window.dispatchEvent(new Event('resize'));                                // nav highlight positions, previews
}
export const toggleBigPicture = () => setBigPicture(!isOn());
// the browser's own Esc leaves full screen: follow it (the desktop app reports through pywebview instead)
document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement && isOn() && !(window.pywebview && window.pywebview.api)) setBigPicture(false); });

// ------------------------------------------------------------------ spatial focus
const FOCUSABLE = 'a[href], button:not([disabled]), input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea, [data-open], [tabindex]:not([tabindex="-1"])';
function scope() {
  const modal = document.getElementById('modal');
  if (modal && !modal.hidden) return [modal];
  const drawer = document.getElementById('drawer');
  if (drawer && drawer.classList.contains('open')) return [drawer];
  return [document.querySelector('.nav'), document.querySelector('.topbar'), document.getElementById('view')].filter(Boolean);
}
function visible(el) {
  if (el.closest('[hidden], .ghost-page')) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 4 || r.height < 4) return false;
  const st = getComputedStyle(el);
  return st.visibility !== 'hidden' && st.display !== 'none' && Number(st.opacity) > 0.05;
}
function candidates() {
  const out = [];
  for (const box of scope()) box.querySelectorAll(FOCUSABLE).forEach((el) => {
    if (el.closest('[data-open]') && !el.matches('[data-open]') && !el.matches('button, a, input, select')) return;
    if (visible(el)) out.push(el);
  });
  return out;
}
function focusEl(el) {
  if (!el) return;
  if (!el.matches('a[href], button, input, select, textarea') && el.tabIndex < 0) el.tabIndex = -1;
  el.focus({ preventScroll: true });
  el.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: root.dataset.motion === 'smooth' ? 'smooth' : 'auto' });
}
export function focusFirst() {
  const view = document.getElementById('view');
  const first = view && ([...view.querySelectorAll('[data-open]')].find(visible) || [...view.querySelectorAll('.card a[href], .card button, .btn, input, select')].find(visible));
  focusEl(first || document.querySelector('#nav-links a.active'));
}
function move(dir) {
  const cur = document.activeElement && document.activeElement !== document.body ? document.activeElement : null;
  const list = candidates();
  if (!cur || !list.includes(cur)) { focusFirst(); return; }
  const a = cur.getBoundingClientRect(), ax = a.left + a.width / 2, ay = a.top + a.height / 2;
  let best = null, bestScore = Infinity;
  for (const el of list) {
    if (el === cur || cur.contains(el) || el.contains(cur)) continue;
    const b = el.getBoundingClientRect(), bx = b.left + b.width / 2, by = b.top + b.height / 2;
    // main = gap along the pressed direction; side = gap across it (0 when the two boxes overlap, so wide rows are easy to reach)
    const gapX = Math.max(0, b.left - a.right, a.left - b.right), gapY = Math.max(0, b.top - a.bottom, a.top - b.bottom);
    let main, side, tie;
    if (dir === 'left') { if (bx >= ax - 1) continue; main = a.left - b.right; side = gapY; tie = Math.abs(by - ay); }
    else if (dir === 'right') { if (bx <= ax + 1) continue; main = b.left - a.right; side = gapY; tie = Math.abs(by - ay); }
    else if (dir === 'up') { if (by >= ay - 1) continue; main = a.top - b.bottom; side = gapX; tie = Math.abs(bx - ax); }
    else { if (by <= ay + 1) continue; main = b.top - a.bottom; side = gapX; tie = Math.abs(bx - ax); }
    if (side > Math.max(main, 0) * 2.5 + 80) continue;              // stay inside a cone in the pressed direction
    const score = Math.max(main, 0) + side * 3 + tie * 0.05 + (main < -4 ? 30 : 0);
    if (score < bestScore) { bestScore = score; best = el; }
  }
  if (best) focusEl(best);
  else if (dir === 'down' || dir === 'up') window.scrollBy({ top: (dir === 'down' ? 1 : -1) * innerHeight * 0.5, behavior: 'smooth' });
}

// ------------------------------------------------------------------ actions
function select() {
  const el = document.activeElement;
  if (!el || el === document.body) { focusFirst(); return; }
  if (el.matches('input[type=checkbox], input[type=radio], button, a[href], [data-open]')) el.click();
  else if (el.matches('select')) { try { el.showPicker(); } catch (e) { el.click(); } }
  else if (el.matches('input, textarea')) el.focus();
}
function back() {
  const modal = document.getElementById('modal');
  if (modal && !modal.hidden) { modal.hidden = true; return; }
  const drawer = document.getElementById('drawer');
  if (drawer && drawer.classList.contains('open')) { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); return; }
  if (document.activeElement && document.activeElement.matches('input, textarea, select')) { document.activeElement.blur(); focusFirst(); return; }
  if (location.hash.replace(/^#\/?/, '')) history.back();
}
function cycle(selector, activeSel, step) {
  const items = [...document.querySelectorAll(selector)].filter(visible);
  if (!items.length) return;
  const i = items.findIndex((x) => x.matches(activeSel));
  const next = items[(i + step + items.length) % items.length];
  next.click();
}
const pages = (step) => cycle('#nav-links a', '.active', step);   // the focus moves into the new page after it renders (afterRoute)
const subTabs = (step) => cycle('.view .tabs [data-tab]', '.on', step);
function search() { const s = document.querySelector('#global-search input'); if (s) { s.focus(); s.select(); } }

// ------------------------------------------------------------------ keyboard
let lastInput = 'keys';
document.addEventListener('keydown', (e) => {
  if ((e.altKey && e.key === 'Enter') || e.key === 'F9') { e.preventDefault(); toggleBigPicture(); return; }
  if (!isOn() || e.ctrlKey || e.metaKey || e.altKey) return;
  lastInput = 'keys'; hintBar();
  const t = e.target, typing = t && t.matches && t.matches('input:not([type=checkbox]):not([type=radio]), textarea');
  const k = e.key;
  if (typing) {                                       // inside a text box only Up/Down leave it; Esc/Enter behave normally
    if (k === 'ArrowUp' || k === 'ArrowDown') { e.preventDefault(); move(k === 'ArrowUp' ? 'up' : 'down'); }
    return;
  }
  const map = { ArrowLeft: () => move('left'), ArrowRight: () => move('right'), ArrowUp: () => move('up'), ArrowDown: () => move('down'),
    Backspace: back, q: () => pages(-1), e: () => pages(1), '[': () => subTabs(-1), ']': () => subTabs(1), '/': search };
  if (t && t.matches && t.matches('select') && (k === 'ArrowUp' || k === 'ArrowDown')) return;   // let a focused list change value
  if (map[k]) { e.preventDefault(); map[k](); return; }
  if ((k === 'Enter' || k === ' ') && t && t.matches && t.matches('[data-open]')) { e.preventDefault(); t.click(); }
});

// ------------------------------------------------------------------ game controller (Gamepad API, standard mapping)
const REPEAT_FIRST = 380, REPEAT_NEXT = 110;
let polling = false;
const held = {};
function press(id, now, fn, repeat = false) {
  const h = held[id];
  if (!h) { held[id] = { t: now, n: 0 }; fn(); return; }
  if (repeat && now - h.t > (h.n ? REPEAT_NEXT : REPEAT_FIRST)) { h.t = now; h.n++; fn(); }
}
function poll() {
  const pads = navigator.getGamepads ? [...navigator.getGamepads()].filter(Boolean) : [];
  if (!pads.length) { polling = false; return; }
  requestAnimationFrame(poll);
  if (document.hidden) return;
  const now = performance.now();
  for (const gp of pads) {
    const b = (i) => gp.buttons[i] && (gp.buttons[i].pressed || gp.buttons[i].value > 0.6);
    const ax = gp.axes[0] || 0, ay = gp.axes[1] || 0, ry = gp.axes[3] || 0;
    const acts = {
      menu: [b(9), () => toggleBigPicture(), false],
    };
    if (isOn()) Object.assign(acts, {
      up: [b(12) || ay < -0.55, () => move('up'), true], down: [b(13) || ay > 0.55, () => move('down'), true],
      left: [b(14) || ax < -0.55, () => move('left'), true], right: [b(15) || ax > 0.55, () => move('right'), true],
      a: [b(0), select, false], b: [b(1), back, false], x: [b(2), search, false],
      lb: [b(4), () => pages(-1), true], rb: [b(5), () => pages(1), true], lt: [b(6), () => subTabs(-1), false], rt: [b(7), () => subTabs(1), false],
    });
    let any = false;
    for (const [id, [down, fn, rep]] of Object.entries(acts)) {
      const key = gp.index + id;
      if (down) { any = true; press(key, now, fn, rep); } else delete held[key];
    }
    if (isOn() && Math.abs(ry) > 0.2) { window.scrollBy(0, ry * 22); any = true; }
    if (any && lastInput !== 'pad') { lastInput = 'pad'; hintBar(); }
  }
}
function startPolling() { if (!polling) { polling = true; requestAnimationFrame(poll); } }
window.addEventListener('gamepadconnected', startPolling);
if (navigator.getGamepads && [...navigator.getGamepads()].some(Boolean)) startPolling();

// ------------------------------------------------------------------ on-screen button hints
function hintBar() {
  let bar = document.getElementById('bp-hints');
  if (!isOn()) { if (bar) bar.remove(); return; }
  if (!bar) { bar = document.createElement('div'); bar.id = 'bp-hints'; bar.setAttribute('aria-hidden', 'true'); document.body.appendChild(bar); }
  const pad = lastInput === 'pad';
  const items = pad
    ? [['A', 'Select'], ['B', 'Back'], ['LB RB', 'Page'], ['LT RT', 'Tab'], ['X', 'Search'], ['☰', 'Exit Big Picture']]
    : [['← ↑ → ↓', 'Move'], ['Enter', 'Select'], ['Backspace', 'Back'], ['Q E', 'Page'], ['[ ]', 'Tab'], ['/', 'Search'], ['Alt+Enter', 'Exit']];
  bar.innerHTML = items.map(([k, t]) => `<span><kbd>${k}</kbd>${t}</span>`).join('');
}
// keep the focus inside the page after navigation in Big Picture
export function afterRoute() {
  if (!isOn()) return;
  const a = document.activeElement;
  if (a && a !== document.body && a.closest('#nav-links') && visible(a)) return;     // browsing the menu: stay there
  focusFirst();                                                                       // otherwise continue inside the new page
  // lists load after the page frame: move onto the first item once it appears, unless the user already moved
  let tries = 0; const placed = document.activeElement;
  const wait = setInterval(() => {
    if (++tries > 8 || document.activeElement !== placed) { clearInterval(wait); return; }
    const item = [...document.querySelectorAll('#view [data-open]')].find(visible);
    if (item) { clearInterval(wait); focusEl(item); }
  }, 200);
}

// a listing panel or a dialog opens: put the focus inside it; when it closes, return to where you were
let returnTo = null;
function watchLayer(id, isOpen) {
  const el = document.getElementById(id);
  if (!el) return;
  let was = isOpen(el);
  new MutationObserver(() => {
    const now = isOpen(el);
    if (now === was || !isOn()) { was = now; return; }
    was = now;
    if (now) {
      returnTo = document.activeElement;
      setTimeout(() => focusEl([...el.querySelectorAll('.btn.primary')].find(visible) || [...el.querySelectorAll('button, a[href], input, select, textarea')].find(visible)), 260);
    } else if (returnTo && document.contains(returnTo)) { focusEl(returnTo); returnTo = null; } else focusFirst();
  }).observe(el, { attributes: true, attributeFilter: ['class', 'hidden'] });
}
function initLayers() {
  watchLayer('drawer', (el) => el.classList.contains('open'));
  watchLayer('modal', (el) => !el.hidden);
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initLayers); else initLayers();
