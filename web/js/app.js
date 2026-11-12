import { state, get, esc, ago, toast, closeDrawer, dur, confirmBox } from './core.js';
import { openListing } from './pages/detail.js';
import * as dashboard from './pages/dashboard.js';
import * as listings from './pages/listings.js';
import * as watchlist from './pages/watchlist.js';
import * as myitems from './pages/myitems.js';
import * as market from './pages/market.js';
import * as roi from './pages/roi.js';
import * as planner from './pages/planner.js';
import * as calendar from './pages/calendar.js';
import * as calculator from './pages/calculator.js';
import * as learning from './pages/learning.js';
import * as notifications from './pages/notifications.js';
import * as system from './pages/system.js';
import * as settings from './pages/settings.js';
import { applyTheme, applyMotion, applyTextSize, applyMode } from './theme.js';
import { axisDir, orderDir, ghost, slideIn } from './motion.js';
import { toggleBigPicture, afterRoute } from './bigpicture.js';

const ROUTES = [
  { group: 'Deals' },
  { path: '', title: 'Dashboard', ic: '◧', page: dashboard },
  { path: 'listings', title: 'Listings', ic: '☰', page: listings },
  { path: 'myitems', title: 'My items', ic: '♥', page: myitems },
  { path: 'watchlist', title: 'Watchlist', ic: '◎', page: watchlist },
  { adv: true, path: 'market', title: 'Market prices', ic: '⌁', page: market },
  { group: 'Planning' },
  { adv: true, path: 'roi', title: 'ROI planner', ic: '↗', page: roi },
  { adv: true, path: 'planner', title: 'Planner', ic: '✓', page: planner },
  { adv: true, path: 'calendar', title: 'Calendar', ic: '▦', page: calendar },
  { adv: true, path: 'calculator', title: 'Calculator', ic: '±', page: calculator },
  { group: 'System' },
  { adv: true, path: 'learning', title: 'Learning', ic: '◐', page: learning },
  { path: 'notifications', title: 'Notifications', ic: '◔', page: notifications },
  { adv: true, path: 'system', title: 'Activity & logs', ic: '≋', page: system },
  { path: 'settings', title: 'Settings', ic: '⚙', page: settings },
];

function parseHash() {
  const h = location.hash.replace(/^#\/?/, '');
  const [path, qs] = h.split('?');
  return { path: path || '', params: new URLSearchParams(qs || '') };
}

const groupOf = (path) => { let g = ''; for (const r of ROUTES) { if (r.group) g = r.group; else if (r.path === path) return g; } return g; };
function renderNav(active) {
  const simple = document.documentElement.dataset.mode === 'simple';
  const shown = ROUTES.filter((r) => !(simple && r.adv)).filter((r, i, a) => !r.group || (a[i + 1] && !a[i + 1].group));   // drop group headings left empty
  document.getElementById('nav-links').innerHTML = shown.map((r) => r.group
    ? `<div class="nav-group">${r.group}</div>`
    : `<a href="#/${r.path}" class="${r.path === active ? 'active' : ''}"><span class="ic" aria-hidden="true">${r.ic}</span><span class="lbl">${r.title}</span>${r.path === 'notifications' ? '<span class="count" id="nav-unread"></span>' : ''}</a>`).join('');
  // phone: a bottom bar with the four main pages and "More" (the full menu)
  const quick = ['', 'listings', 'myitems', 'notifications'];
  const more = !quick.includes(active);
  document.getElementById('mnav').innerHTML = quick.map((p) => { const r = ROUTES.find((x) => x.path === p && x.page);
    return `<a href="#/${p}" class="${p === active ? 'active' : ''}"><span class="ic" aria-hidden="true">${p === 'notifications' ? '⚑' : r.ic}</span><span>${p === 'notifications' ? 'Alerts' : r.title}</span>${p === 'notifications' ? '<i class="mbadge" id="mnav-unread" hidden></i>' : ''}</a>`; }).join('')
    + `<button type="button" id="mnav-more" class="${more ? 'active' : ''}" aria-label="More pages"><span class="ic" aria-hidden="true">⋯</span><span>${more ? esc((ROUTES.find((x) => x.path === active && x.page) || {}).title || 'More') : 'More'}</span></button>`;
  document.getElementById('mnav-more').onclick = () => document.querySelector('.nav').classList.toggle('open');
  if (state.status) setUnreadMini(state.status.unread);
  // top-bar layouts scroll horizontally on narrow windows: keep the active page visible
  placeBlob();
  const cur = document.querySelector('#nav-links a.active');
  if (cur && cur.scrollIntoView && getComputedStyle(document.getElementById('nav-links')).flexDirection === 'row') cur.scrollIntoView({ inline: 'center', block: 'nearest' });
}

function setUnreadMini(n) { const m = document.getElementById('mnav-unread'); if (m) { m.hidden = !n; m.textContent = n > 99 ? '99+' : (n || ''); } }
let currentPath = null;
let enterTimer = 0;
let pendingNav = null;
const navIndex = (path) => (path === null ? -1 : ROUTES.filter((r) => r.page).findIndex((r) => r.path === path));
// remember where the clicked tab sits relative to the active one (read before the hash changes and the nav re-renders)
document.addEventListener('click', (e) => {
  const t = e.target.closest && e.target.closest('#nav-links a, .tabs [data-tab]');
  if (!t || e.button !== 0) return;
  const cur = t.parentElement.querySelector('a.active, [data-tab].on');
  pendingNav = { dir: axisDir(cur, t) };
}, true);
let currentKey = null;
async function route() {
  const { path, params } = parseHash();
  let r = ROUTES.find((x) => x.path === path && x.page) || ROUTES[1];
  if (r.adv && document.documentElement.dataset.mode === 'simple') { location.hash = '#/'; r = ROUTES[1]; }
  document.querySelector('.nav').classList.remove('open');
  const pageParams = new URLSearchParams(params); pageParams.delete('listing');
  const key = r.path + '?' + pageParams.toString();
  if (key !== currentKey) {
    const view = document.getElementById('view');
    const samePage = currentPath === r.path && currentKey !== null;      // e.g. a Settings sub-tab
    const nav = pendingNav; pendingNav = null;
    let dir = nav ? nav.dir : null;
    if (!nav && !samePage) dir = orderDir(navIndex(currentPath), navIndex(r.path), document.getElementById('nav-links'));
    // what slides: the whole page, or only the tab body when a sub-tab of the same page was picked
    const part = samePage ? view.querySelector('#tab') : view;
    const old = currentKey !== null && dir ? ghost(part) : null;
    currentKey = key;
    currentPath = r.path;
    renderNav(r.path);
    view.classList.remove('enter');
    if (!samePage) {
      void view.offsetWidth;
      if (!dir) view.classList.add('enter');                           // no direction (first load): the gentle rise-in
      if (old) view.style.opacity = '0';                                // the old page stays visible (ghost) while the new one loads
      view.innerHTML = '<div class="loading">Loading</div>';
      window.scrollTo(0, 0);
    }
    const reveal = setTimeout(() => { view.style.opacity = ''; }, 700);  // slow page: show its loading state anyway
    document.title = `${r.title} · SS Deal Finder`;
    view.dataset.page = r.path || 'dashboard'; document.body.dataset.page = view.dataset.page;
    try {
      await r.page.render(view, params);
      const ph = view.querySelector('.page-head > div');
      if (ph && !ph.querySelector('.kicker')) ph.insertAdjacentHTML('afterbegin', `<div class="kicker"><span aria-hidden="true">${r.ic}</span> ${groupOf(r.path)} / ${esc(r.title)}</div>`);
      // entrance animations are done after ~0.8 s: drop them so dozens of rows do not stay as separate layers that repaint on scroll
      clearTimeout(enterTimer); enterTimer = setTimeout(() => view.classList.remove('enter'), 900);
    } catch (e) {
      view.innerHTML = `<div class="card"><h2>This page could not load</h2><p class="error-text">${esc(e.message)}</p><p class="muted">Check that the monitoring service is running, then reload.</p></div>`;
    }
    clearTimeout(reveal); view.style.opacity = '';
    slideIn(samePage ? view.querySelector('#tab') : view, dir, old);
    afterRoute();
  }
  const lid = params.get('listing');
  if (lid) openListing(Number(lid)); else closeDrawer();
}

async function refreshStatus() {
  try {
    const s = await get('/status');
    state.status = s;
    const pill = document.getElementById('scan-pill');
    const sc = s.scanner, f = s.fetcher;
    let cls = 'ok', txt;
    if (!sc.enabled) { cls = 'warn'; txt = 'Scanning off'; }
    else if (sc.paused) { cls = 'warn'; txt = 'Paused'; }
    else if (f.cooldown_seconds > 0) { cls = 'bad'; txt = `Waiting ${dur(f.cooldown_seconds)} (${f.blocked_reason})`; }
    else if (!sc.warmup_complete) { cls = 'warn'; txt = 'Warm-up: building market data'; }
    else txt = sc.current ? `Scanning ${sc.current.split(':')[1] || ''}` : `Last scan ${ago(sc.last_success)}`;
    pill.className = 'scan-pill ' + cls;
    pill.innerHTML = `<span class="dot"></span><span class="txt">${esc(txt)}</span>`;
    const b = document.getElementById('bell-badge');
    b.hidden = !s.unread; b.textContent = s.unread > 99 ? '99+' : s.unread;
    const nu = document.getElementById('nav-unread'); if (nu) nu.textContent = s.unread || '';
    setUnreadMini(s.unread);
    document.getElementById('demo-banner').hidden = !s.demo;
    document.getElementById('nav-foot').innerHTML = `${s.listings.toLocaleString()} active listings<br>${esc(sc.mode)}`;
  } catch (e) {
    const pill = document.getElementById('scan-pill');
    pill.className = 'scan-pill bad';
    pill.innerHTML = '<span class="dot"></span><span class="txt">Service not reachable</span>';
  }
}

async function pollEvents() {
  try {
    const ev = await get('/events?after=' + state.lastSeq);
    const first = state.lastSeq < 0;
    state.lastSeq = ev.seq;
    if (first || !ev.items.length) return;
    if (ev.popups) for (const e of ev.items) {
      toast(e.title, e.body, e.level, () => { if (e.listing_id) location.hash = `#/${currentPath}?listing=${e.listing_id}`; else if (e.url) window.open(e.url); }, e.level === 'HIGH_ROI' ? 15000 : 9000);
    }
    refreshStatus();                                   // new notifications: bump the counter now, not on the next status poll
  } catch (e) { /* service offline: status pill shows it */ }
}

// position of the active nav item, for themes that slide a highlight (Liquid Morph's water-drop swish)
function placeBlob() {
  const box = document.getElementById('nav-links'), a = box && box.querySelector('a.active');
  if (!a) return;
  box.style.setProperty('--ax', a.offsetLeft + 'px'); box.style.setProperty('--ay', a.offsetTop + 'px');
  box.style.setProperty('--aw', a.offsetWidth + 'px'); box.style.setProperty('--ah', a.offsetHeight + 'px');
}
window.addEventListener('resize', placeBlob);

// While the page scrolls, freeze hover effects: rows passing under a still mouse would otherwise restyle and repaint
// every frame (measured: about 4x more raster work during a scroll). Removed ~150 ms after the last scroll event.
{
  const root = document.documentElement; let t = 0;
  addEventListener('scroll', () => {
    if (!root.classList.contains('scrolling')) root.classList.add('scrolling');
    clearTimeout(t); t = setTimeout(() => root.classList.remove('scrolling'), 150);
  }, { passive: true, capture: true });
}

function syncMode() {
  const adv = document.documentElement.dataset.mode === 'advanced';
  document.querySelectorAll('#mode-toggle button').forEach((b) => b.classList.toggle('on', (b.dataset.mode === 'advanced') === adv));
  renderNav(currentPath ?? '');
}
async function init() {
  try {
    const [meta, s] = await Promise.all([get('/meta'), get('/settings')]);
    state.meta = meta; state.settings = s.settings;
    applyTheme(s.settings.ui.theme, false);
    applyMotion(s.settings.ui.performance_mode, false);
    applyTextSize(s.settings.ui.text_size || 'normal', false);
    document.documentElement.dataset.mode = s.settings.ui.mode === 'advanced' ? 'advanced' : 'simple';
    syncMode();
  } catch (e) { /* render anyway */ }
  document.getElementById('global-search').addEventListener('submit', (e) => {
    e.preventDefault();
    const q = new FormData(e.target).get('q');
    location.hash = '#/listings?q=' + encodeURIComponent(q) + '&_r=' + Date.now();
  });
  document.getElementById('nav-toggle').onclick = () => document.querySelector('.nav').classList.toggle('open');
  document.getElementById('scrim').onclick = closeDrawer;
  // phone menu: a tap outside closes it
  document.addEventListener('click', (e) => {
    const nav = document.querySelector('.nav');
    if (nav.classList.contains('open') && !e.target.closest('.nav, #mnav-more, #nav-toggle')) nav.classList.remove('open');
  }, true);
  document.querySelectorAll('#mode-toggle button').forEach((b) => (b.onclick = async () => {
    await applyMode(b.dataset.mode); syncMode(); currentKey = null; route();
  }));
  const quit = document.getElementById('quit-btn');
  if (['127.0.0.1', 'localhost', '[::1]'].includes(location.hostname)) {   // only on the PC that runs it, never from a phone
    quit.hidden = false;
    quit.onclick = async () => {
      if (!(await confirmBox('Quit SS Deal Finder? Monitoring and notifications stop until you start it again.', 'Quit'))) return;
      try { await fetch('/api/system/shutdown', { method: 'POST' }); } catch (e) { /* already gone */ }
      document.body.innerHTML = '<div style="display:grid;place-items:center;height:100vh;font:16px system-ui;color:#888">SS Deal Finder has stopped. You can close this window.</div>';
      try { window.close(); } catch (e) { /* ignored */ }
    };
  }
  document.getElementById('scan-pill').onclick = () => { location.hash = '#/system'; };
  document.getElementById('bp-btn').onclick = () => toggleBigPicture();
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeDrawer(); document.getElementById('modal').hidden = true; } });
  // open a listing from anywhere
  document.addEventListener('click', (e) => {
    const el = e.target.closest('[data-open]');
    if (el && !e.target.closest('a,button,input,select')) {
      const { path, params } = parseHash();
      params.set('listing', el.dataset.open); params.delete('_r');
      location.hash = `#/${path}?${params}`;
    }
  });
  window.addEventListener('hashchange', route);
  await route();
  refreshStatus(); setInterval(refreshStatus, 8000);
  pollEvents(); setInterval(pollEvents, 4000);
  window.addEventListener('ssd-status', refreshStatus);
}
// installable app (PWA): needs HTTPS or this PC (localhost)
window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); window.__installPrompt = e; });
if ('serviceWorker' in navigator && isSecureContext) navigator.serviceWorker.register('sw.js').catch(() => {});
init();
