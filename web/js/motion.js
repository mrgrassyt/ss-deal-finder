// Direction-aware page transitions. The direction comes from where the clicked tab sits relative to the active one
// in the CURRENT layout: a top bar or dock slides left/right, a sidebar or rail slides up/down, Settings sub-tabs
// slide left/right. Only transform + opacity are animated (compositor-only, no layout or paint per frame).
const root = document.documentElement;
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const zoom = () => parseFloat(getComputedStyle(document.body).zoom) || 1;

// 'right' = the new tab sits to the right of the old one, so the new page comes in from the right.
export function axisDir(from, to) {
  if (!from || !to || from === to) return null;
  const a = from.getBoundingClientRect(), b = to.getBoundingClientRect();
  if (!a.width || !b.width) return null;
  const dx = (b.left + b.width / 2) - (a.left + a.width / 2), dy = (b.top + b.height / 2) - (a.top + a.height / 2);
  if (Math.abs(dx) < 2 && Math.abs(dy) < 2) return null;
  return Math.abs(dx) >= Math.abs(dy) ? (dx > 0 ? 'right' : 'left') : (dy > 0 ? 'down' : 'up');
}

// direction when there was no click (back/forward, links inside pages): order in the nav, along the nav's own axis
export function orderDir(oldIdx, newIdx, navBox) {
  if (oldIdx < 0 || newIdx < 0 || oldIdx === newIdx || !navBox) return null;
  const row = getComputedStyle(navBox).flexDirection.startsWith('row');
  return newIdx > oldIdx ? (row ? 'right' : 'down') : (row ? 'left' : 'up');
}

// A frozen picture of the outgoing content (a DOM copy; iframes are not copied, they would reload).
export function ghost(el) {
  if (!el || root.dataset.motion !== 'smooth' || reduced()) return null;
  const r = el.getBoundingClientRect(), z = zoom();
  const top = Math.max(r.top, 0), h = Math.min(r.bottom, innerHeight) - top;
  if (h <= 0) return null;
  const g = el.cloneNode(true);
  g.querySelectorAll('iframe, canvas, video').forEach((f) => { const d = document.createElement('div'); d.className = f.className; d.style.cssText = f.style.cssText; f.replaceWith(d); });
  g.removeAttribute('id'); g.querySelectorAll('[id]').forEach((n) => n.removeAttribute('id'));
  g.classList.remove('enter'); g.classList.add('ghost-page'); g.setAttribute('aria-hidden', 'true');
  const inner = document.createElement('div'); inner.style.cssText = `margin-top:${(r.top - top) / z}px`;
  while (g.firstChild) inner.appendChild(g.firstChild);
  g.appendChild(inner);
  Object.assign(g.style, { position: 'fixed', left: r.left / z + 'px', top: top / z + 'px', width: r.width / z + 'px', height: h / z + 'px',
    margin: '0', overflow: 'hidden', pointerEvents: 'none', zIndex: '15', maxWidth: 'none' });
  document.body.appendChild(g);
  return g;
}

const OFFSET = { smooth: { x: 0.22, y: 0.16, ms: 420 }, performance: { x: 0.03, y: 0.03, ms: 140 } };
// slide `el` in from `dir`; the ghost (old content) leaves the opposite way at the same time
export function slideIn(el, dir, old) {
  const mode = root.dataset.motion === 'smooth' ? 'smooth' : 'performance';
  if (!dir || reduced() || !el) { if (old) old.remove(); return; }
  const o = OFFSET[mode], horiz = dir === 'left' || dir === 'right', sign = dir === 'right' || dir === 'down' ? 1 : -1;
  const dist = Math.round((horiz ? innerWidth * o.x : innerHeight * o.y) / zoom());
  const tf = (v) => (horiz ? `translate3d(${v}px,0,0)` : `translate3d(0,${v}px,0)`);
  const ease = 'cubic-bezier(.22,.8,.24,1)';
  // the new page fades in a little late and the old one is gone by 55%: both move the whole time, they never sit on top of each other for long
  el.animate([{ transform: tf(sign * dist), opacity: 0 }, { opacity: old ? 0.15 : 0.6, offset: 0.3 }, { transform: 'none', opacity: 1 }], { duration: o.ms, easing: ease });
  if (old) old.animate([{ transform: 'none', opacity: 1 }, { opacity: 0, offset: 0.55 }, { transform: tf(-sign * dist), opacity: 0 }], { duration: o.ms * 0.8, easing: ease, fill: 'forwards' })
    .finished.then(() => old.remove(), () => old.remove());
}
