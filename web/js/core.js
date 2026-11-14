// Shared helpers: API access, formatting, components, charts, toasts, drawer, modal.

export const state = { meta: null, settings: null, status: null, lastSeq: -1 };

// Remote / phone access: the service needs its API token for anything but localhost. Open the app once with
// ?token=… (the Android app does this) and it is remembered in this browser and sent with every request.
const TOKEN_KEY = 'ssd-api-token';
export function apiToken() { try { return localStorage.getItem(TOKEN_KEY) || ''; } catch (e) { return ''; } }
(function captureToken() {
  try {
    const q = new URLSearchParams(location.search), t = q.get('token');
    if (t) { localStorage.setItem(TOKEN_KEY, t); q.delete('token'); const rest = q.toString(); history.replaceState(null, '', location.pathname + (rest ? '?' + rest : '') + location.hash); }
  } catch (e) { /* storage may be unavailable */ }
})();
export const withToken = (url) => { const t = apiToken(); return t ? url + (url.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(t) : url; };

export async function api(path, opts = {}) {
  const init = { method: opts.method || 'GET', headers: {} };
  if (apiToken()) init.headers['x-api-token'] = apiToken();
  if (opts.body !== undefined) { init.body = JSON.stringify(opts.body); init.headers['Content-Type'] = 'application/json'; }
  const r = await fetch('/api' + path, init);
  let data = null;
  try { data = await r.json(); } catch (e) { /* empty */ }
  if (!r.ok) {
    if (r.status === 401 && data && data.login) { if (data.hub) location.href = '/login'; else showLogin(); }
    const msg = (data && (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail))) || `Request failed (HTTP ${r.status})`;
    throw new Error(msg);
  }
  return data;
}
// Server mode (app running 24/7 on a rented server): any request without a login gets 401 {login:true} -> password screen.
let loginUp = false;
function showLogin() {
  if (loginUp) return; loginUp = true;
  const d = document.createElement('div');
  d.id = 'login-screen';
  d.style.cssText = 'position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;padding:16px;background:var(--bg,#0f172a);color:var(--text,#e5e7eb)';
  d.innerHTML = `<form class="card" style="width:100%;max-width:340px;padding:22px;display:flex;flex-direction:column;gap:12px" autocomplete="on">
    <h2 style="margin:0">SS Deal Finder</h2><p class="muted" style="margin:0">Log in to your server</p>
    <input type="password" name="password" placeholder="Password" autocomplete="current-password" autofocus style="font-size:16px">
    <button class="btn primary" type="submit">Log in</button><div class="error-text" id="login-err" style="min-height:1.2em"></div></form>`;
  document.body.appendChild(d);
  const f = d.querySelector('form'), err = d.querySelector('#login-err');
  f.onsubmit = async (e) => {
    e.preventDefault(); err.textContent = '';
    try {
      const r = await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: f.password.value }) });
      if (r.ok) { location.reload(); return; }
      let m = ''; try { m = (await r.json()).detail; } catch (x) { /* empty */ }
      err.textContent = m || 'Could not log in';
    } catch (x) { err.textContent = 'Server not reachable'; }
  };
  setTimeout(() => f.password.focus(), 50);
}
export const get = (p) => api(p);
export const post = (p, body = {}) => api(p, { method: 'POST', body });
export const put = (p, body = {}) => api(p, { method: 'PUT', body });
export const del = (p) => api(p, { method: 'DELETE' });

// ---------- formatting
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const eur = (v, d = 0) => (v === null || v === undefined || isNaN(v)) ? '—' : (Number(v) < 0 ? '−€' : '€') + Math.abs(Number(v)).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d });
export const pct = (v) => (v === null || v === undefined) ? '—' : `${Math.round(v)}%`;
export const n0 = (v) => (v === null || v === undefined) ? '—' : Math.round(v).toLocaleString('en-US');
export function ago(ts) {
  if (!ts) return 'never';
  const s = Date.now() / 1000 - ts;
  if (s < 0) return 'in ' + dur(-s);
  if (s < 60) return 'just now';
  return dur(s) + ' ago';
}
export function dur(s) {
  if (s < 3600) return Math.round(s / 60) + ' min';
  if (s < 86400) return Math.round(s / 3600) + ' h';
  return Math.round(s / 86400) + ' d';
}
export const dt = (ts) => ts ? new Date(ts * 1000).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—';
export const dday = (ts) => ts ? new Date(ts * 1000).toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short' }) : '—';
export const catName = (k) => (state.meta?.categories?.[k]?.name) || k || '—';
export const LEVEL_LABEL = { GOOD_DEAL: 'Good deal', INTERESTING: 'Interesting', IGNORE: 'Ignored' };
export const COND_LABEL = { new: 'New', used: 'Used', broken: 'Broken', parts: 'For parts', untested: 'Untested', unknown: 'Unknown' };

// ---------- components
export function ruler(l, big = false) {
  const lo = l.value_low ?? l.low, hi = l.value_high ?? l.high, typ = l.value_typical ?? l.typical, p = l.price;
  if (!lo || !hi || p === null || p === undefined) {
    return `<div class="ruler none">${typ ? 'Est. ' + eur(typ) : 'No market estimate yet'}</div>`;
  }
  const min = Math.min(lo, p) * 0.85, max = Math.max(hi, p) * 1.1;
  const x = (v) => ((v - min) / (max - min) * 100).toFixed(1);
  const over = p > hi;
  return `<div class="ruler ${big ? 'big' : ''}" title="Market range ${eur(lo)}–${eur(hi)}, typical ${eur(typ)}; asking ${eur(p)}">
    <div class="track"></div>
    <div class="range" style="left:${x(lo)}%;width:${(x(hi) - x(lo)).toFixed(1)}%"></div>
    ${typ ? `<div class="typ" style="left:${x(typ)}%"></div>` : ''}
    <div class="ask ${over ? 'over' : ''}" style="left:${x(p)}%"></div>
    ${x(hi) - x(lo) < 22 ? `<span class="lbl" style="left:${((+x(lo) + +x(hi)) / 2).toFixed(1)}%">${eur(lo)}–${eur(hi).slice(1)}</span>`
      : `<span class="lbl" style="left:${x(lo)}%">${eur(lo)}</span><span class="lbl" style="left:${x(hi)}%">${eur(hi)}</span>`}
  </div>`;
}
// Only items you asked for (My items) get a Personal score; everything else shows nothing.
export function scores(l) {
  const p = l.personal_score;
  if (p == null) return '';
  return `<span class="scores"><span class="score-chip personal big ${p < 60 ? 'dim' : ''}" title="How well this fits something from your My items list (0–100)"><b>${Math.round(p)}</b><span>For you</span></span></span>`;
}
export const levelTag = (lv) => lv && lv !== 'IGNORE' ? `<span class="level ${lv}">${LEVEL_LABEL[lv] || lv}</span>` : '';
export function condTag(c) {
  const cls = { new: 'good', broken: 'bad', parts: 'bad', untested: 'warn' }[c] || '';
  return `<span class="tag ${cls}">${COND_LABEL[c] || c || '?'}</span>`;
}
export function flagTags(flags = []) {
  const names = { bundle: 'Bundle', collection: 'Lot', warranty: 'Warranty', mining: 'Mining', shop: 'Shop', urgent: 'Urgent', box: 'Box', receipt: 'Receipt', negotiable: 'Negotiable', exchange: 'Exchange', buying: 'Wanted ad', service: 'Service' };
  const cls = { mining: 'warn', buying: 'bad', service: 'bad', warranty: 'good', bundle: 'accent', collection: 'accent' };
  return flags.filter((f) => names[f]).map((f) => `<span class="tag ${cls[f] || ''}">${names[f]}</span>`).join(' ');
}
export function thumb(l) {
  return l.image_url ? `<img class="thumb" loading="lazy" decoding="async" src="${esc(l.image_url)}" alt="" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'thumb ph',textContent:'▢'}))">` : '<div class="thumb ph">▢</div>';
}
export function priceHtml(l) {
  const old = l.initial_price && l.price < l.initial_price ? `<span class="price-old">${eur(l.initial_price)}</span>` : '';
  return `${old}<span class="price">${l.price == null ? (l.price_text || '—') : eur(l.price)}</span>`;
}
// the money view of a deal: buy price -> likely resale -> profit and ROI after costs
export function flipHtml(l) {
  const f = l.flip;
  if (!f) return l.condition === 'broken' || l.condition === 'parts' || l.condition === 'untested'
    ? `<div class="flip muted small">Needs checking or repair, so no flip estimate. Open it for the repair outlook.</div>` : '';
  if (f.repair) return `<div class="flip" title="${esc(f.why || '')}"><span>Worth ≈ <b>${eur(f.resale_low)}</b> in parts, <b>${eur(f.resale_high)}</b> if fixed</span>
    <span class="${f.profit >= 0 ? 'pos' : 'neg'}">Expected ${f.profit >= 0 ? '+' : '−'}€${Math.abs(f.profit)}</span><span class="conf low">${Math.round((f.fix_chance || 0) * 100)}% fix chance</span></div>`;
  const pos = f.profit >= 0, sign = pos ? '+' : '−';
  const range = f.profit_low != null && f.profit_high != null ? ` <span class="muted">(${f.profit_low >= 0 ? '+' : '−'}€${Math.abs(f.profit_low)} to ${f.profit_high >= 0 ? '+' : '−'}€${Math.abs(f.profit_high)})</span>` : '';
  return `<div class="flip" title="Sells for about ${eur(f.resale)} (typical asking price minus a haircut), minus ${eur(l.price)} to buy and ${eur(f.costs)} costs. Based on ${f.n || '?'} comparable ads.">
    <span>Resale ≈ <b>${eur(f.resale)}</b></span>
    <span class="${pos ? 'pos' : 'neg'}">Profit <b>${sign}€${Math.abs(f.profit)}</b>${f.roi != null ? ` · ROI ${f.roi}%` : ''}${range}</span>
    <span class="conf ${f.confidence}">${f.confidence} confidence</span></div>`;
}
// right-hand money block: what you pay, where it should sell, profit and ROI (replaces the score chips)
export function moneyBox(l) {
  const f = l.flip, sg = (v) => (v >= 0 ? '+' : '−') + '€' + Math.abs(v);
  const tip = (f ? `${f.confidence} confidence, ${f.n || '?'} comparable ads · resale = typical asking price minus a haircut` : '');
  const row = (k, v, cls = '') => `<div class="mrow"><span>${k}</span><b class="${cls}">${v}</b></div>`;
  return `<div class="right moneybox" title="${esc(tip)}">
    ${row('Buy', l.price == null ? '—' : eur(l.price))}
    ${f && f.repair ? row('Sell', `~${eur(f.resale_low)}–${eur(f.resale_high)}`) + row('Profit', '~' + sg(f.profit), f.profit >= 0 ? 'pos' : 'neg') + row('ROI', f.roi == null ? '—' : '~' + f.roi + '%', f.profit >= 0 ? 'pos' : 'neg')
        + `<div class="mconf low" title="${esc(f.why || '')}">parts → fixed (${Math.round((f.fix_chance || 0) * 100)}% fix chance)</div>`
      : f && f.uncertain ? row('Sell', f.resale_low && f.resale_high ? `~${eur(f.resale_low)}–${eur(f.resale_high)}` : '~' + eur(f.resale)) + row('Profit', '~' + sg(f.profit), f.profit >= 0 ? 'pos' : 'neg') + row('ROI', f.roi == null ? '—' : '~' + f.roi + '%', f.profit >= 0 ? 'pos' : 'neg')
        + `<div class="mconf low">model not exact, check it</div>`
      : f && f.rough ? row('Sell', '~' + eur(f.resale)) + row('Profit', '~' + sg(f.profit), f.profit >= 0 ? 'pos' : 'neg') + row('ROI', f.roi == null ? '—' : '~' + f.roi + '%', f.profit >= 0 ? 'pos' : 'neg')
        + `<div class="mconf low" title="${esc(f.why || '')}">rough guess</div>`
      : f ? row('Sell', '≈ ' + eur(f.resale)) + row('Profit', sg(f.profit), f.profit >= 0 ? 'pos' : 'neg') + row('ROI', f.roi == null ? '—' : f.roi + '%', f.profit >= 0 ? 'pos' : 'neg')
        + `<div class="mconf ${f.confidence}">${f.confidence} confidence</div>` : `<div class="mconf low">no price</div>`}
    ${scores(l) ? `<div class="mine">${scores(l)}</div>` : ''}
  </div>`;
}
export function dealItem(l, opts = {}) {
  return `<div class="deal-item ${l.status === 'removed' ? 'removed' : ''}" data-open="${l.id}">
    ${thumb(l)}
    <div style="min-width:0"><div class="ltitle">${esc(l.product_name || l.title)}</div>
      <div class="lsub">${esc(l.headline || l.reason || (l.title || '').slice(0, 80))}</div>
      ${opts.ruler && l.value_low ? `<div class="adv-only" style="max-width:340px;margin-top:4px">${ruler(l)}</div>` : ''}</div>
    ${opts.flip ? moneyBox(l) : `<div class="right">${priceHtml(l)}<div style="margin-top:4px">${scores(l)}</div></div>`}
  </div>`;
}
export function empty(title, text = '', action = '') {
  return `<div class="empty"><b>${esc(title)}</b>${esc(text)}${action ? `<div style="margin-top:12px">${action}</div>` : ''}</div>`;
}

// ---------- charts (plain SVG, themed with CSS variables)
export function lineChart(series, { height = 180, width = 640, yfmt = (v) => eur(v), xfmt = null, area = true } = {}) {
  const pts = series.flatMap((s) => s.points);
  if (Math.max(...series.map((s) => s.points.length)) < 2) return `<div class="empty small">Not enough history yet to draw a chart.</div>`;
  const W = width, H = height, P = { l: 46, r: 10, t: 10, b: 22 };
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]).filter((v) => v != null);
  let x0 = Math.min(...xs), x1 = Math.max(...xs); if (x0 === x1) { x0 -= 1; x1 += 1; }
  let y0 = Math.min(...ys), y1 = Math.max(...ys); const pad = (y1 - y0) * 0.15 || y1 * 0.1 || 1; y0 = Math.max(0, y0 - pad); y1 += pad;
  const X = (v) => P.l + (v - x0) / (x1 - x0) * (W - P.l - P.r), Y = (v) => H - P.b - (v - y0) / (y1 - y0) * (H - P.t - P.b);
  let g = '';
  for (let i = 0; i <= 3; i++) { const v = y0 + (y1 - y0) * i / 3; g += `<line class="gridline" x1="${P.l}" x2="${W - P.r}" y1="${Y(v)}" y2="${Y(v)}"/><text class="axis" x="${P.l - 6}" y="${Y(v) + 3}" text-anchor="end">${yfmt(v)}</text>`; }
  const fx = xfmt || ((v) => new Date(v * 1000).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }));
  g += `<text class="axis" x="${P.l}" y="${H - 6}">${fx(x0)}</text><text class="axis" x="${W - P.r}" y="${H - 6}" text-anchor="end">${fx(x1)}</text>`;
  series.forEach((s, i) => {
    const sp = s.points.filter((p) => p[1] != null);
    if (!sp.length) return;
    const step = s.step;
    let d = '';
    sp.forEach((p, j) => {
      if (j === 0) d += `M${X(p[0])},${Y(p[1])}`;
      else d += step ? `H${X(p[0])}V${Y(p[1])}` : `L${X(p[0])},${Y(p[1])}`;
    });
    if (step) d += `H${X(x1)}`;
    if (area && i === 0) g += `<path class="area" d="${d}L${step ? X(x1) : X(sp[sp.length - 1][0])},${H - P.b}L${X(sp[0][0])},${H - P.b}Z"/>`;
    g += `<path class="s${i + 1}" d="${d}"/>`;
    if (sp.length < 30) sp.forEach((p) => { g += `<circle class="dot" cx="${X(p[0])}" cy="${Y(p[1])}" r="2.5"><title>${yfmt(p[1])}</title></circle>`; });
  });
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img">${g}</svg>`;
}
export function barChart(items, { height = 160, width = 640, keys = [['n', 'b1']], labels = null } = {}) {
  if (!items.length) return `<div class="empty small">No data yet.</div>`;
  const W = width, H = height, P = { l: 30, r: 6, t: 8, b: 20 };
  const max = Math.max(1, ...items.map((it) => keys.reduce((a, [k]) => a + (it[k] || 0), 0)));
  const bw = (W - P.l - P.r) / items.length;
  let g = '';
  for (let i = 0; i <= 2; i++) { const v = max * i / 2, y = H - P.b - v / max * (H - P.t - P.b); g += `<line class="gridline" x1="${P.l}" x2="${W - P.r}" y1="${y}" y2="${y}"/><text class="axis" x="${P.l - 4}" y="${y + 3}" text-anchor="end">${Math.round(v)}</text>`; }
  items.forEach((it, i) => {
    let yb = H - P.b;
    keys.forEach(([k, cls]) => {
      const h = (it[k] || 0) / max * (H - P.t - P.b);
      if (h > 0) g += `<rect class="bar ${cls}" x="${P.l + i * bw + bw * 0.15}" y="${yb - h}" width="${bw * 0.7}" height="${h}" rx="2"><title>${k}: ${it[k]}</title></rect>`;
      yb -= h;
    });
    if (labels && (items.length < 16 || i % 2 === 0)) g += `<text class="axis" x="${P.l + i * bw + bw / 2}" y="${H - 6}" text-anchor="middle">${esc(labels(it))}</text>`;
  });
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img">${g}</svg>`;
}

// ---------- toasts / modal / drawer
export function toast(title, body = '', level = '', onClick = null, ms = 5000) {
  const t = document.createElement('div');
  t.className = 'toast ' + level;
  t.innerHTML = `<b>${esc(title)}</b>${esc(body)}`;
  t.onclick = () => { t.remove(); onClick && onClick(); };
  document.getElementById('toasts').appendChild(t);
  setTimeout(() => t.remove(), ms);
}
export const ok = (msg) => toast(msg, '', '', null, 3500);
// unread counter: update the bell and the menu right away (the 8-second status poll made one click look like none)
export function setUnread(n) {
  const b = document.getElementById('bell-badge');
  if (b) { b.hidden = !n; b.textContent = n > 99 ? '99+' : n; }
  const nu = document.getElementById('nav-unread'); if (nu) nu.textContent = n || '';
  const m = document.getElementById('mnav-unread'); if (m) { m.hidden = !n; m.textContent = n > 99 ? '99+' : (n || ''); }
  if (state.status) state.status.unread = n;
}
export const fail = (e) => toast('Something went wrong', e.message || String(e), 'error', null, 7000);

export function modal(html, onMount) {
  const m = document.getElementById('modal'), box = document.getElementById('modal-box');
  box.innerHTML = html; m.hidden = false;
  const close = () => { m.hidden = true; box.innerHTML = ''; };
  m.onclick = (e) => { if (e.target === m) close(); };
  box.querySelectorAll('[data-close]').forEach((b) => (b.onclick = close));
  onMount && onMount(box, close);
  const f = box.querySelector('input,select,textarea,button'); f && f.focus();
  return close;
}
export function confirmBox(text, yes = 'Confirm') {
  return new Promise((res) => {
    modal(`<h2>${esc(text)}</h2><div class="row" style="justify-content:flex-end;margin-top:18px">
      <button class="btn" data-close>Cancel</button><button class="btn primary" id="cf-yes">${esc(yes)}</button></div>`,
    (box, close) => { box.querySelector('#cf-yes').onclick = () => { close(); res(true); }; box.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', () => res(false))); });
  });
}

const drawer = () => document.getElementById('drawer');
export function openDrawer(html) {
  document.getElementById('drawer-inner').innerHTML = html;
  drawer().classList.add('open'); drawer().setAttribute('aria-hidden', 'false');
  document.getElementById('scrim').hidden = false;
  drawer().scrollTop = 0;
}
export function closeDrawer() {
  drawer().classList.remove('open'); drawer().setAttribute('aria-hidden', 'true');
  document.getElementById('scrim').hidden = true;
  if (location.hash.includes('listing=')) history.replaceState(null, '', location.hash.replace(/[?&]listing=\d+/, ''));
}

// form helpers
export function formData(root) {
  const out = {};
  root.querySelectorAll('[name]').forEach((el) => {
    if (el.type === 'checkbox') out[el.name] = el.checked;
    else if (el.type === 'number') out[el.name] = el.value === '' ? null : Number(el.value);
    else if (el.type === 'datetime-local' || el.type === 'date') out[el.name] = el.value ? new Date(el.value).getTime() / 1000 : null;
    else out[el.name] = el.value;
  });
  return out;
}
export const toLocalInput = (ts) => {
  if (!ts) return '';
  const d = new Date(ts * 1000); d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
};
export function debounce(fn, ms = 250) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
