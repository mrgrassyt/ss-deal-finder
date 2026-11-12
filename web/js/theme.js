// Theme + motion handling. Theme and performance mode are independent settings.
// A theme is more than colours: it chooses a navigation layout (side / top / rail / dock), its own fonts, panel
// shapes, controls, decorative layers (css/themes/<key>.css) and, in Smooth mode, its own ambient animation.
import { put, state, barChart, dealItem } from './core.js';

// key, name, description, layout, mood tags
export const THEMES = [
  ['liquid-glass', 'Liquid Glass', 'Clear lens-like glass, bright corner rims, floating capsule navigation with a sliding glass lens', 'float', ['light', 'depth', 'fluid']],
  ['minimal', 'Minimal', 'Quiet and clean: almost no text, no icons, no borders, big numbers and lots of air', 'top', ['light', 'calm']],
  ['material-you', 'Material You', 'Tonal violet surfaces, pill indicator rail, filled and tonal buttons, rounded containers', 'rail', ['light', 'soft']],
  ['trading-desk', 'Trading Desk', 'Dense market terminal: tiny type, zebra rows, panel title bars, mono numbers — most items per screen', 'side', ['dark', 'technical', 'dense']],
  ['cyber-hud', 'Cyber HUD', 'Head-up display: cut-corner panels, slanted buttons, techno type, navigation on the right', 'right', ['dark', 'bold', 'technical']],
  ['particles', 'Particles', 'Constellation map: star field, node-and-link panels, glowing data points', 'side', ['dark', 'calm']],
  ['liquid-morph', 'Liquid Morph', 'iOS-style liquid glass: morphing blobs, floating dock, jelly buttons', 'dock', ['light', 'fluid']],
  ['holographic', 'Holographic', 'Iridescent foil: rainbow edges, sweeping sheen, spectral type', 'side', ['dark', 'shiny']],
  ['neon-glow', 'Neon Glow', 'Synthwave night: glowing tubes, luminous rail, light-up controls', 'rail', ['dark', 'bold']],
  ['wireframe-3d', 'Wireframe 3D', 'Vector workstation: extruded outlines, rotating cube, top bar', 'top', ['dark', 'technical']],
  ['glassmorphism', 'Glassmorphism', 'Layered frosted panels over colour orbs, specular highlights, floating sidebar', 'side', ['dark', 'depth']],
  ['kinetic-typography', 'Kinetic Typography', 'Poster type: giant condensed headings, black bar, running ticker', 'top', ['light', 'loud']],
  ['isometric', 'Isometric', 'Blocks in 30° projection: stacked extrusions, diamond markers, cubes', 'side', ['light', 'playful']],
  ['clay-3d', 'Clay 3D', 'Soft modelling clay: puffy pillows, pressed-in inputs, round rail', 'rail', ['light', 'soft']],
  ['ascii-art', 'ASCII Art', 'Terminal in plain characters: +---+ frames, [ buttons ], block cursor', 'side', ['dark', 'terminal']],
  ['gradient-mesh', 'Gradient Mesh', 'Airy editorial: drifting colour mesh, serif headlines, pill navigation', 'top', ['light', 'airy']],
  ['comic-book', 'Comic Book', 'Panels and captions: heavy ink, halftone, starburst badges, speech-bubble toasts', 'side', ['light', 'playful']],
  ['split-flap', 'Split-flap', 'Departure board: flip tiles, bolted panels, brass top bar', 'top', ['dark', 'mechanical']],
  ['retro-vhs', 'Retro VHS', 'CRT and tape: scanlines, tracking glitch, VCR on-screen display', 'side', ['dark', 'nostalgic']],
  ['halftone', 'Halftone', 'Newspaper print: masthead, double rules, dot-screen photos', 'top', ['light', 'editorial']],
  ['bauhaus', 'Bauhaus', 'Circle, square, triangle: primary colours, asymmetric geometry, icon rail', 'rail', ['light', 'geometric']],
  ['blueprint', 'Blueprint', 'Technical drawing: figure labels, dimension rulers, title block (default)', 'side', ['dark', 'technical']],
  ['art-deco', 'Art Deco', 'Gold sunburst, stepped corners, ornamented headings, centred masthead', 'top', ['dark', 'elegant']],
  ['neo-brutalism', 'Neo-brutalism', 'Raw blocks: thick outlines, hard shadows, sticker tags, colour-blocked cards', 'side', ['light', 'loud']],
];
export const DEFAULT_THEME = 'blueprint';
export const layoutOf = (name) => (THEMES.find((t) => t[0] === name) || [])[3] || 'side';
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

function setTheme(name) {
  const el = document.documentElement;
  el.dataset.theme = name; el.dataset.layout = layoutOf(name);
  try { localStorage.setItem('ssd-theme', name); localStorage.setItem('ssd-layout', el.dataset.layout); } catch (e) { /* storage may be unavailable */ }
  particles();
}

// `animate` = the user just picked this theme: cross-fade between the old and new look.
export function applyTheme(name, persist = true, animate = false) {
  if (!THEMES.some((t) => t[0] === name)) name = DEFAULT_THEME;
  if (animate && !reduced() && document.documentElement.dataset.theme !== name) {
    if (document.startViewTransition) document.startViewTransition(() => setTheme(name));
    else {
      const el = document.documentElement; el.classList.add('theme-fade'); setTheme(name);
      setTimeout(() => el.classList.remove('theme-fade'), 500);
    }
  } else setTheme(name);
  if (persist) return put('/settings', { ui: { theme: name } }).then((r) => { state.settings = r.settings; });
}

export function applyMotion(mode, persist = true) {
  if (mode !== 'smooth') mode = 'performance';
  document.documentElement.dataset.motion = mode;
  try { localStorage.setItem('ssd-motion', mode); } catch (e) { /* ignore */ }
  particles();
  if (persist) return put('/settings', { ui: { performance_mode: mode } }).then((r) => { state.settings = r.settings; });
}

export function applyMode(mode, persist = true) {
  mode = mode === 'advanced' ? 'advanced' : 'simple';
  document.documentElement.dataset.mode = mode;
  try { localStorage.setItem('ssd-mode', mode); } catch (e) { /* ignore */ }
  if (persist) return put('/settings', { ui: { mode } }).then((r) => { state.settings = r.settings; });
}
export const TEXT_SIZES = [['small', 'Small'], ['normal', 'Normal'], ['large', 'Large'], ['xlarge', 'Extra large']];
export function applyTextSize(size, persist = true) {
  if (!TEXT_SIZES.some((t) => t[0] === size)) size = 'normal';
  document.documentElement.dataset.tsize = size;
  try { localStorage.setItem('ssd-tsize', size); } catch (e) { /* ignore */ }
  if (persist) return put('/settings', { ui: { text_size: size } }).then((r) => { state.settings = r.settings; });
}

// Water-droplet ripple for Liquid Morph buttons (Smooth mode only)
document.addEventListener('pointerdown', (e) => {
  const d = document.documentElement.dataset;
  if (d.theme !== 'liquid-morph' || d.motion !== 'smooth') return;
  const b = e.target.closest && e.target.closest('.btn');
  if (!b) return;
  const r = b.getBoundingClientRect(), z = parseFloat(getComputedStyle(document.body).zoom) || 1, span = document.createElement('span');
  const size = Math.max(r.width, r.height) * 1.6;
  span.className = 'drop-ripple';
  span.style.cssText = `width:${size / z}px;height:${size / z}px;left:${(e.clientX - r.left) / z - size / z / 2}px;top:${(e.clientY - r.top) / z - size / z / 2}px`;
  b.appendChild(span); setTimeout(() => span.remove(), 700);
}, true);

// ---- gallery preview: a miniature of the real app, built from the real components and styled by the real theme CSS
const SAMPLE = [
  { id: 1, product_name: 'AMD RX 6700 10GB', headline: 'Priced 24% under typical', price: 118, initial_price: 135, deal_score: 91, personal_score: 76, value_low: 135, value_high: 190, value_typical: 158, status: 'active' },
  { id: 2, product_name: 'Sony A7 III body', headline: 'Low shutter count', price: 780, deal_score: 74, personal_score: 88, value_low: 760, value_high: 950, value_typical: 860, status: 'active' },
];
const BARS = [4, 7, 5, 9, 6, 11, 8, 12].map((n, i) => ({ n, good: i % 3 === 0 ? 2 : 1, interesting: 1, rest: Math.max(0, n - 3), day: '' }));
// Each preview is a real document in an iframe: it loads base.css plus ONLY that theme's stylesheet, so nothing from the
// active theme can leak in and what you see is exactly what the theme renders.
const PV = { w: 1000, h: 640, zoom: 1.7 };
function miniApp() {
  const nav = [['◧', 'Dashboard', 1], ['☰', 'Listings'], ['◎', 'Watchlist'], ['⌁', 'Market prices'], ['↗', 'ROI planner'], ['▦', 'Calendar']]
    .map(([ic, t, on]) => `<a class="${on ? 'active' : ''}"><span class="ic">${ic}</span><span class="lbl">${t}</span></a>`).join('');
  const chart = barChart(BARS, { width: 250, height: 96, keys: [['good', 'b2'], ['interesting', 'b3'], ['rest', 'b1']] });
  return `<div class="bgfx"><i class="a"></i><i class="b"></i><i class="c"></i><i class="d"></i><i class="e"></i><i class="f"></i></div>
    <div class="app">
      <nav class="nav"><div class="brand"><svg viewBox="0 0 32 32" width="24" height="24"><rect width="32" height="32" rx="7" class="brand-mark"/><path d="M6 22h20M10 22V12m6 10V8m6 14v-6" stroke="currentColor" stroke-width="3" stroke-linecap="round" fill="none"/></svg><span class="brand-name">SS Deal Finder</span></div>
        <div class="nav-links"><div class="nav-group">Deals</div>${nav}</div><div class="nav-foot">1,284 active listings</div></nav>
      <div class="main">
        <header class="topbar"><div class="search"><input type="search" placeholder="Search listings, e.g. rx 6700" tabindex="-1"></div><div class="scan-pill ok"><span class="dot"></span><span class="txt">Last scan 2 min ago</span></div></header>
        <main class="view"><div class="page-head"><div><div class="kicker"><span>◧</span> Deals / Dashboard</div><h1>Dashboard</h1></div><div class="row"><span class="btn primary sm">Open deals</span><span class="btn sm">Save</span></div></div>
          <div class="figures"><div class="figure"><div class="v">1,284</div><div class="l">Monitored</div></div><div class="figure good"><div class="v">12</div><div class="l">Good deals</div></div><div class="figure warn"><div class="v">31</div><div class="l">Interesting</div></div></div>
          <div class="grid g2" style="margin-top:12px"><div class="card"><div class="card-head"><h2>Best deals</h2></div><div class="deal-list">${SAMPLE.map((l) => dealItem(l, { ruler: true })).join('')}</div></div>
            <div class="card"><h2>New per day</h2>${chart}<div style="margin-top:8px" class="row"><span class="tag good">Good deal</span><span class="tag warn">Untested</span><span class="level GOOD_DEAL">Good deal</span></div></div></div>
        </main></div></div>
    <div class="fxtop"></div>`;
}
function previewDoc(key, layout, motion) {
  const base = location.href.split('#')[0].split('?')[0].replace(/[^/]*$/, '');
  return `<!doctype html><html lang="en" data-theme="${key}" data-layout="${layout}" data-motion="${motion}" class="paused"><head><meta charset="utf-8"><base href="${base}">
    <link rel="stylesheet" href="css/base.css"><link rel="stylesheet" href="css/fonts.css"><link rel="stylesheet" href="css/themes/${key}.css">
    <style>html,body{margin:0;height:100%;overflow:hidden}body{zoom:${PV.zoom}}.app{min-height:0!important}.nav{height:calc(100vh / ${PV.zoom})!important}
    html.paused *,html.paused *::before,html.paused *::after{animation-play-state:paused!important}</style></head><body>${miniApp()}</body></html>`;
}
export function previewFrame(key, layout) {
  return `<div class="tprev-wrap" data-k="${key}" data-layout="${layout}"><iframe class="tprev-frame" title="${key} preview" tabindex="-1" aria-hidden="true" loading="lazy" scrolling="no"></iframe></div>`;
}
// fill the iframes, scale them to their frame and let hover play the theme's animation (Smooth mode)
export function mountPreviews(root) {
  const motion = document.documentElement.dataset.motion;
  root.querySelectorAll('.tprev-wrap').forEach((w) => {
    const f = w.querySelector('iframe');
    f.style.width = PV.w + 'px'; f.style.height = PV.h + 'px';
    f.srcdoc = previewDoc(w.dataset.k, w.dataset.layout, motion);
    const card = w.closest('.theme-card');
    const toggle = (run) => { try { f.contentDocument.documentElement.classList.toggle('paused', !run); } catch (e) { /* not loaded yet */ } };
    card.addEventListener('mouseenter', () => toggle(true)); card.addEventListener('mouseleave', () => toggle(false));
    card.addEventListener('focus', () => toggle(true)); card.addEventListener('blur', () => toggle(false));
  });
  fitPreviews(root);
}
export function fitPreviews(root) {
  root.querySelectorAll('.tprev-wrap').forEach((w) => {
    const f = w.querySelector('iframe'); if (f) f.style.transform = `scale(${w.clientWidth / PV.w})`;
  });
}

// Lightweight particle field for the Particles theme — Smooth mode only, paused when hidden.
let raf = null;
function particles() {
  const c = document.getElementById('fx-canvas');
  const on = document.documentElement.dataset.theme === 'particles' && document.documentElement.dataset.motion === 'smooth'
    && !matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (raf) { cancelAnimationFrame(raf); raf = null; }
  c.style.display = on ? 'block' : 'none';
  if (!on) return;
  const ctx = c.getContext('2d');
  const resize = () => { c.width = innerWidth; c.height = innerHeight; };
  resize(); window.onresize = resize;
  const N = Math.min(70, Math.floor(innerWidth * innerHeight / 22000));
  const P = Array.from({ length: N }, () => ({ x: Math.random() * c.width, y: Math.random() * c.height, vx: (Math.random() - .5) * .25, vy: (Math.random() - .5) * .25 }));
  let last = 0;
  const step = (t) => {
    raf = requestAnimationFrame(step);
    if (document.hidden || t - last < 33) return; // ~30 fps cap keeps CPU low
    last = t;
    ctx.clearRect(0, 0, c.width, c.height);
    for (const p of P) {
      p.x = (p.x + p.vx + c.width) % c.width; p.y = (p.y + p.vy + c.height) % c.height;
      ctx.fillStyle = 'rgba(125,211,252,.55)'; ctx.fillRect(p.x, p.y, 2, 2);
    }
    ctx.strokeStyle = 'rgba(125,211,252,.08)';
    for (let i = 0; i < N; i++) for (let j = i + 1; j < N; j++) {
      const dx = P[i].x - P[j].x, dy = P[i].y - P[j].y;
      if (dx * dx + dy * dy < 12000) { ctx.beginPath(); ctx.moveTo(P[i].x, P[i].y); ctx.lineTo(P[j].x, P[j].y); ctx.stroke(); }
    }
  };
  raf = requestAnimationFrame(step);
}
