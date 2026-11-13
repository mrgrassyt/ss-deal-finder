import { get, put, post, esc, eur, dt, ok, fail, confirmBox, state, withToken, apiToken, debounce, catName } from '../core.js';
import { THEMES, TEXT_SIZES, applyTheme, applyMotion, applyTextSize, DEFAULT_THEME, previewFrame, mountPreviews, fitPreviews } from '../theme.js';

const TABS = [['themes', 'Theme Studio'], ['prices', 'Item prices'], ['scan', 'Scanning'], ['filters', 'Filters & budgets'], ['notify', 'Notifications'],
  ['discord', 'Discord'], ['phone', 'Phone'], ['prefs', 'Preferences & learning'], ['data', 'Startup & data']];

export async function render(view, params) {
  const data = await get('/settings');
  state.settings = data.settings;
  const simple = document.documentElement.dataset.mode === 'simple';
  let tab = params.get('tab') || 'themes';
  if (simple && !['themes', 'prices', 'notify', 'phone', 'data'].includes(tab)) tab = 'themes';
  view.innerHTML = `<div class="page-head"><div><h1>Settings</h1><p>Changes are saved immediately to your data folder and picked up by the monitoring service.</p></div></div>
    <div class="tabs" role="tablist">${TABS.filter(([k]) => !simple || ['themes', 'prices', 'notify', 'phone', 'data'].includes(k)).map(([k, t]) => `<button role="tab" class="${k === tab ? 'on' : ''}" data-tab="${k}">${t}</button>`).join('')}</div>
    <div id="tab"></div>`;
  view.querySelectorAll('[data-tab]').forEach((b) => (b.onclick = () => { location.hash = '#/settings?tab=' + b.dataset.tab; }));
  const el = view.querySelector('#tab');
  ({ themes, prices, scan, filters, notify, discord, phone, prefs, data: dataTab })[tab](el, data, () => render(view, params));
}

async function save(patch, msg = 'Settings saved') {
  try { const r = await put('/settings', patch); state.settings = r.settings; ok(msg); return true; } catch (e) { fail(e); return false; }
}
const num = (k, label, v, attrs = '') => `<label class="field">${label}<input type="number" name="${k}" value="${v ?? ''}" ${attrs}></label>`;
const chk = (k, label, v) => `<label class="check"><input type="checkbox" name="${k}" ${v ? 'checked' : ''}> ${label}</label>`;
function collect(root) {
  const out = {};
  root.querySelectorAll('[name]').forEach((i) => {
    out[i.name] = i.type === 'checkbox' ? i.checked : i.type === 'number' ? (i.value === '' ? 0 : Number(i.value)) : i.value;
  });
  return out;
}

// ------------------------------------------------------------------ Theme Studio
let themeFilter = 'all';
const LAYOUT_NAME = { side: 'Sidebar', top: 'Top bar', rail: 'Icon rail', dock: 'Floating dock', float: 'Floating capsule', right: 'Right sidebar' };
function themes(el, d) {
  const cur = document.documentElement.dataset.theme, motion = document.documentElement.dataset.motion;
  const moods = ['all', 'dark', 'light', 'technical', 'playful', 'soft', 'dense'];
  const list = THEMES.filter((t) => themeFilter === 'all' || t[4].includes(themeFilter));
  el.innerHTML = `
  <div class="card"><div class="card-head"><h2>Performance</h2></div>
    <div class="row"><div class="seg" id="motion"><button data-m="performance" class="${motion === 'performance' ? 'on' : ''}">Performance mode</button><button data-m="smooth" class="${motion === 'smooth' ? 'on' : ''}">Smooth mode</button></div>
    <span class="hint">Performance (default): snappy — no blur, no animation or blend effects, no heavy shadows; pages switch with a very short slide. Smooth: each theme\'s own motion and glass, page slides that follow where the tab sits, animated lists. Big Picture (⛶ in the top bar, Alt+Enter): full screen, larger UI, game controller and keyboard navigation.</span></div></div>
  <div class="card" style="margin-top:14px"><div class="card-head"><h2>Text size</h2></div>
    <div class="row"><div class="seg" id="tsize">${TEXT_SIZES.map(([k, n]) => `<button data-z="${k}" class="${(document.documentElement.dataset.tsize || 'normal') === k ? 'on' : ''}">${n}</button>`).join('')}</div>
    <span class="hint">Smaller text fits more on each page, larger is easier to read. Each theme has its own font, so it also has its own built-in correction — compact fonts like ASCII Art and Blueprint are scaled up/down so "Normal" looks about the same everywhere.</span></div></div>
  <div class="card" style="margin-top:14px"><div class="card-head"><h2>Themes <span class="muted small">· ${THEMES.length} designs, each with its own layout, type and components</span></h2><button class="btn sm" id="treset">Reset to default (Blueprint)</button></div>
    <div class="row" style="margin-bottom:14px" id="tfilter">${moods.map((m) => `<button class="btn sm ${themeFilter === m ? 'primary' : ''}" data-f="${m}">${m === 'all' ? 'All' : m[0].toUpperCase() + m.slice(1)}</button>`).join('')}
      <span class="hint">Previews are live miniatures of the real app. ${motion === 'smooth' ? 'Hover a preview to see its animation.' : 'Switch to Smooth mode to see them move.'}</span></div>
    <div class="theme-grid">${list.map(([k, name, desc, layout, tags]) => `<button class="theme-card ${k === cur ? 'on' : ''}" data-theme-pick="${k}" aria-label="Use theme ${name}" aria-pressed="${k === cur}">
      ${previewFrame(k, layout)}
      <div class="tc-meta"><div class="tc-name"><span>${name}</span>${k === cur ? '<span class="tag accent">Active</span>' : ''}</div><div class="tc-desc">${desc}</div>
        <div class="tc-tags"><span class="tag">${LAYOUT_NAME[layout]}</span>${tags.map((t) => `<span class="tag">${t}</span>`).join('')}</div></div></button>`).join('')}</div></div>`;
  mountPreviews(el);
  const ro = new ResizeObserver(() => fitPreviews(el)); el.querySelectorAll('.tprev-wrap').forEach((w) => ro.observe(w));
  el.querySelectorAll('[data-theme-pick]').forEach((b) => (b.onclick = async () => { ro.disconnect(); await applyTheme(b.dataset.themePick, true, true); themes(el, d); }));
  el.querySelector('#treset').onclick = async () => { ro.disconnect(); await applyTheme(DEFAULT_THEME, true, true); themes(el, d); };
  el.querySelectorAll('[data-m]').forEach((b) => (b.onclick = async () => { ro.disconnect(); await applyMotion(b.dataset.m); themes(el, d); }));
  el.querySelectorAll('[data-z]').forEach((b) => (b.onclick = async () => { ro.disconnect(); await applyTextSize(b.dataset.z); themes(el, d); }));
  el.querySelectorAll('[data-f]').forEach((b) => (b.onclick = () => { ro.disconnect(); themeFilter = b.dataset.f; themes(el, d); }));
}

// ------------------------------------------------------------------ Scanning
function download(name, text, type) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

// Item prices: what the app believes per model; your own number replaces it everywhere (Buy/Sell/Profit, notifications)
function prices(el) {
  const cats = Object.entries(state.meta?.categories || {});
  el.innerHTML = `<div class="card"><h2>Item prices</h2>
    <p class="hint">The typical used price the app currently believes for each model, from the ads it has seen. Type your own price in the last column and it replaces the app's number for that model (working and used units; broken or parts units still use their own market). Clear the box to go back to the app's estimate.</p>
    <div class="filters" style="margin-top:10px">
      <label class="field" style="grid-column:span 2">Find a model<input type="search" id="pq" placeholder="e.g. iphone 13, rx 6700, a7"></label>
      <label class="field">Category<select id="pc"><option value="">All</option>${cats.map(([k, c]) => `<option value="${k}">${esc(c.name)}</option>`).join('')}</select></label>
      <label class="check" style="align-self:center"><input type="checkbox" id="pm"> Only my prices</label>
    </div>
    <div class="row" style="margin:10px 0;gap:8px;flex-wrap:wrap">
      <button class="btn" id="pe-json">Export JSON</button><button class="btn" id="pe-csv">Export CSV</button>
      <label class="btn" style="cursor:pointer">Import file…<input type="file" id="pi" accept=".json,.csv,text/csv,application/json" hidden></label>
      <span class="muted small">Export lists every model with the app's price and yours. In a file, fill in <b>your_price</b> and import it back; blank rows are left alone.</span>
    </div>
    <div id="pres"><div class="loading">Loading</div></div></div>`;
  const q = el.querySelector('#pq'), c = el.querySelector('#pc'), m = el.querySelector('#pm'), res = el.querySelector('#pres');
  const load = async () => {
    const d = await get('/prices?' + new URLSearchParams({ q: q.value, category: c.value, mine: m.checked ? 'true' : 'false' }));
    res.innerHTML = d.items.length ? `<div class="table-wrap"><table class="data"><thead><tr><th>Model</th><th class="hide-sm">Category</th><th class="r">App's price</th><th class="r">Your price €</th><th class="r hide-sm">Based on</th></tr></thead><tbody>
      ${d.items.map((r) => `<tr><td><b>${esc(r.product_name)}</b><div class="lsub">${esc(r.product_key)}</div></td><td class="hide-sm">${esc(catName(r.category_key))}</td>
        <td class="r num">${r.app_price != null ? eur(r.app_price) : '—'}</td>
        <td class="r"><input type="number" min="1" step="1" style="width:110px;text-align:right" data-key="${esc(r.product_key)}" data-was="${r.your_price ?? ''}" value="${r.your_price ?? ''}" placeholder="use app's"></td>
        <td class="r num hide-sm">${r.n} ads${r.your_price != null ? ' · <b>your price</b>' : ''}</td></tr>`).join('')}</tbody></table></div>
      ${d.total > d.items.length ? `<p class="hint">Showing ${d.items.length} of ${d.total}. Search to narrow it down.</p>` : ''}` : '<p class="muted">No models priced yet. Prices appear after the scanner has seen a few ads of the same model.</p>';
    res.querySelectorAll('input[data-key]').forEach((i) => {
      const commit = async () => {
        if (i.value === i.dataset.was) return;
        try { await post('/prices/set', { product_key: i.dataset.key, price: i.value === '' ? null : Number(i.value) }); i.dataset.was = i.value; ok(i.value === '' ? 'Back to the app\'s estimate' : 'Saved. Listings update shortly.'); }
        catch (e) { fail(e); i.value = i.dataset.was; }
      };
      i.onchange = commit;
      i.onkeydown = (e) => { if (e.key === 'Enter') i.blur(); };
    });
  };
  q.addEventListener('input', debounce(load, 250)); c.onchange = load; m.onchange = load;
  const exp = async (fmt) => {
    try { const r = await get('/prices/export?format=' + fmt); download(r.filename, r.content, fmt === 'csv' ? 'text/csv' : 'application/json'); } catch (e) { fail(e); }
  };
  el.querySelector('#pe-json').onclick = () => exp('json'); el.querySelector('#pe-csv').onclick = () => exp('csv');
  el.querySelector('#pi').onchange = async (ev) => {
    const f = ev.target.files[0]; if (!f) return;
    try {
      const r = await post('/prices/import', { text: await f.text() });
      ok(`Imported ${r.applied} price${r.applied === 1 ? '' : 's'}` + (r.skipped_count ? `, skipped ${r.skipped_count} (first: ${r.skipped[0].product_key || 'row'} - ${r.skipped[0].why})` : ''));
      load();
    } catch (e) { fail(e); }
    ev.target.value = '';
  };
  load();
}

function scan(el, d, reload) {
  const s = d.settings.scan;
  el.innerHTML = `
  <div class="card"><h2>Polling intervals</h2>
    <p class="hint">SS.lv is checked on a schedule. Every request goes through one polite queue with a minimum gap, robots.txt is respected, and the scanner backs off when the site asks it to. Lower intervals mean more requests — keep them reasonable.</p>
    <form id="sf" class="field-row" style="margin-top:10px">
      ${num('new_listings_interval_min', 'Fast feeds: check for new ads every (min)', s.new_listings_interval_min, 'min=1')}
      ${num('normal_feed_interval_min', 'Other feeds every (min)', s.normal_feed_interval_min, 'min=1')}
      ${num('price_check_interval_min', 'Price-change check every (min)', s.price_check_interval_min, 'min=5')}
      ${num('market_recalc_interval_min', 'Market recalculation every (min)', s.market_recalc_interval_min, 'min=5')}
      ${num('reconcile_interval_min', 'Full reconciliation every (min)', s.reconcile_interval_min, 'min=30')}
      ${num('min_request_interval', 'Minimum seconds between requests', s.min_request_interval, 'min=2 step=0.5')}
      ${num('max_pages_new', 'Max pages per new-ads check', s.max_pages_new, 'min=1 max=10')}
      ${num('reconcile_pages', 'Pages per feed in reconciliation', s.reconcile_pages, 'min=1 max=30')}
      ${num('detail_fetch_min_score', 'Fetch full ad text when score ≥', s.detail_fetch_min_score, 'min=0 max=100')}
      ${num('backfill_pages', 'Warm-up pages per feed', s.backfill_pages, 'min=0 max=30')}
    </form>
    <div class="row" style="margin-top:12px">${chk('enabled', 'Scanning enabled', s.enabled).replace('name="enabled"', 'name="enabled" form="sf"')}
      <button class="btn primary" id="ssave">Save intervals</button><button class="btn" id="sbackfill">Run warm-up again</button></div>
    <p class="hint" id="sest"></p></div>
  <div class="card" style="margin-top:14px"><h2>SS.lv sections</h2><p class="hint">Fast sections use the fast interval. Disabled sections are not requested at all.</p>
    <div class="table-wrap"><table class="data"><thead><tr><th>Section</th><th>Path</th><th>Enabled</th><th>Fast</th></tr></thead><tbody>
    ${d.feeds.map((f) => `<tr><td>${esc(f.key.replace(/_/g, ' '))}</td><td class="small muted">${esc(f.path)}</td>
      <td><input type="checkbox" data-feed="${f.key}" data-f="enabled" ${f.enabled ? 'checked' : ''}></td><td><input type="checkbox" data-feed="${f.key}" data-f="priority" ${f.priority ? 'checked' : ''}></td></tr>`).join('')}
    </tbody></table></div></div>`;
  const est = () => {
    const v = collect(el.querySelector('#sf'));
    const fast = d.feeds.filter((f) => f.enabled && f.priority).length, slow = d.feeds.filter((f) => f.enabled && !f.priority).length;
    const perHour = fast * 60 / v.new_listings_interval_min + slow * 60 / v.normal_feed_interval_min + 2 * 60 / v.price_check_interval_min;
    el.querySelector('#sest').textContent = `Roughly ${Math.round(perHour)} requests per hour at minimum (≈${Math.round(perHour * 24)} per day), before detail pages. At most ${Math.round(3600 / v.min_request_interval)} per hour are ever possible.`;
  };
  el.querySelector('#sf').addEventListener('input', est); est();
  el.querySelector('#ssave').onclick = async () => { const v = collect(el.querySelector('#sf')); v.enabled = el.querySelector('[name=enabled]').checked; await save({ scan: v }); };
  el.querySelector('#sbackfill').onclick = async () => { try { await post('/scanner/backfill'); ok('Warm-up started'); } catch (e) { fail(e); } };
  el.querySelectorAll('[data-feed]').forEach((c) => (c.onchange = async () => {
    const f = d.feeds.find((x) => x.key === c.dataset.feed); f[c.dataset.f] = c.checked;
    await save({ feeds: { [f.key]: { enabled: f.enabled, priority: f.priority } } }, 'Section updated'); est();
  }));
}

// ------------------------------------------------------------------ Filters
function filters(el, d) {
  const f = d.settings.filters, cats = d.categories, cf = f.categories || {};
  el.innerHTML = `
  <div class="card"><h2>General filters</h2><form id="ff" class="field-row">
    ${num('min_price', 'Ignore listings below €', f.min_price, 'min=0')}${num('max_price', 'Ignore listings above € (0 = no limit)', f.max_price, 'min=0')}
    ${num('junk_value_floor', 'Junk filter: accessories under €', f.junk_value_floor, 'min=0')}</form>
    <div class="row" style="margin-top:10px">${chk('ignore_buying_ads', 'Ignore “wanted” ads (pērku / куплю)', f.ignore_buying_ads)} ${chk('ignore_services', 'Ignore services and rentals', f.ignore_services)} ${chk('ignore_parts', 'Ignore parts &amp; accessories (battery, screen, case… for a device)', f.ignore_parts !== false)}</div>
    <p class="hint">Broken, untested, incomplete items, bundles and lots are never filtered out automatically — they are evaluated instead.</p>
    <button class="btn primary" id="fsave" style="margin-top:10px">Save filters</button></div>
  <div class="card" style="margin-top:14px"><h2>Per category</h2><p class="hint">Watchlist matches within budget are shown even in disabled categories.</p>
    <div class="table-wrap"><table class="data"><thead><tr><th>Category</th><th>Notify</th><th>Max budget €</th><th>Min Deal Score</th></tr></thead><tbody>
    ${Object.entries(cats).map(([k, c]) => `<tr data-cat="${k}"><td>${esc(c.name)}</td><td><input type="checkbox" data-k="enabled" ${cf[k]?.enabled === false ? '' : 'checked'}></td>
      <td><input type="number" data-k="max_budget" value="${cf[k]?.max_budget ?? ''}" min="0" style="width:110px"></td><td><input type="number" data-k="min_deal" value="${cf[k]?.min_deal ?? ''}" min="0" max="100" style="width:90px"></td></tr>`).join('')}
    </tbody></table></div><button class="btn primary" id="csave" style="margin-top:10px">Save category settings</button></div>`;
  el.querySelector('#fsave').onclick = () => { const v = collect(el.querySelector('#ff')); v.ignore_buying_ads = el.querySelector('[name=ignore_buying_ads]').checked; v.ignore_services = el.querySelector('[name=ignore_services]').checked; v.ignore_parts = el.querySelector('[name=ignore_parts]').checked; save({ filters: v }); };
  el.querySelector('#csave').onclick = () => {
    const out = {};
    el.querySelectorAll('[data-cat]').forEach((tr) => {
      const e = tr.querySelector('[data-k=enabled]').checked, b = tr.querySelector('[data-k=max_budget]').value, m = tr.querySelector('[data-k=min_deal]').value;
      if (!e || b || m) out[tr.dataset.cat] = { enabled: e, ...(b ? { max_budget: Number(b) } : {}), ...(m ? { min_deal: Number(m) } : {}) };
    });
    save({ filters: { categories: out } });
  };
}

// ------------------------------------------------------------------ Notifications
function notify(el, d) {
  const n = d.settings.notify, tg = d.settings.telegram || {}, sec = d.secrets || {};
  const testBtn = (ch, label = 'Send test') => `<button class="btn sm" data-test="${ch}">${label}</button>`;
  el.innerHTML = `
  <div class="card"><h2>Where notifications go</h2>
    <div class="table-wrap"><table class="data"><thead><tr><th></th><th>Good deal</th><th>Interesting</th><th></th></tr></thead><tbody>
      <tr><td><b>Windows</b><div class="lsub">Real system notifications (Action Center), with “Open ad” buttons</div></td><td>${chk('desktop_good', '', n.desktop_good)}</td><td>${chk('desktop_interesting', '', n.desktop_interesting)}</td><td class="r">${testBtn('desktop')} ${testBtn('desktop-high', 'Test 🚀')}</td></tr>
      <tr><td><b>Phone: ntfy app</b><div class="lsub">Set the topic under Settings → Phone</div></td><td>${chk('ntfy_good', '', n.ntfy_good)}</td><td>${chk('ntfy_interesting', '', n.ntfy_interesting)}</td><td class="r">${testBtn('ntfy')}</td></tr>
      <tr><td><b>Phone: Telegram</b><div class="lsub">Set up below</div></td><td>${chk('telegram_good', '', n.telegram_good)}</td><td>${chk('telegram_interesting', '', n.telegram_interesting)}</td><td class="r">${testBtn('telegram')}</td></tr>
      <tr><td><b>Discord</b><div class="lsub">Needs a working bot (Settings → Discord)</div></td><td>${chk('discord_good', '', n.discord_good)}</td><td>${chk('discord_interesting', '', n.discord_interesting)}</td><td class="r">${testBtn('discord')}</td></tr></tbody></table></div>
    <p id="testres" class="hint" style="min-height:1.4em"></p>
    <div class="row">${chk('in_app_popups', 'Also show pop-ups inside the app window', n.in_app_popups)}</div>
    <p class="hint">Every notification is also listed on the Notifications page, with what each channel answered (✓ sent, failed, or waiting for the hourly limit).
      Windows: if nothing shows up, check that Focus assist / Do not disturb is off and that “SS Deal Finder” is allowed under Windows Settings → System → Notifications.</p>
  </div>
  <div class="card" style="margin-top:14px"><h2>🚀 High ROI</h2>
    <form id="nroi" class="field-row">
      ${num('high_roi_pct', 'Special alert when ROI is at least (%) — 0 turns it off', n.high_roi_pct, 'min=0 max=1000')}
      ${num('high_roi_min_profit', '…and the estimated profit is at least (€)', n.high_roi_min_profit, 'min=0 max=100000')}</form>
    <p class="hint">These get the eye-catching style everywhere: a 🚀 title, a Windows notification that stays on screen until you close it, top priority on the phone, a highlighted row here.
      They are also sent during quiet hours and above the hourly limit.</p>
    <button class="btn primary" id="nsave2" style="margin-top:10px">Save</button></div>
  <div class="card" style="margin-top:14px"><h2>Telegram (phone)</h2>
    <ol class="small" style="margin:0 0 10px 18px;padding:0;line-height:1.7">
      <li>In Telegram open <b>@BotFather</b>, send <code>/newbot</code>, pick any name. Copy the token it gives you.</li>
      <li>Paste the token here and save it. Then open your new bot in Telegram and send it any message (e.g. “hi”).</li>
      <li>Press <b>Find my chat</b>, then <b>Save Telegram</b> and <b>Send test</b>.</li></ol>
    <div class="field-row">
      <label class="field">Bot token ${sec.telegram_token ? '<span class="tag good">saved</span>' : ''}<input type="password" id="tgtok" placeholder="${sec.telegram_token ? 'saved — paste a new one to replace' : '123456:ABC…'}" autocomplete="off"></label>
      <label class="field">Chat id<input type="text" id="tgchat" value="${esc(tg.chat_id || '')}" placeholder="press Find my chat"></label></div>
    <div class="row" style="margin-top:10px">${chk('tg_enabled', 'Send notifications to Telegram', tg.enabled)}
      <button class="btn sm" id="tgsavetok">Save token</button><button class="btn sm" id="tgfind">Find my chat</button><button class="btn sm primary" id="tgsave">Save Telegram</button></div>
    <p class="hint" id="tgres"></p></div>
  <div class="card" style="margin-top:14px"><h2>When to notify</h2>
    <div class="seg" id="sens">${[['high_recall', 'Show more (high recall)'], ['balanced', 'Balanced'], ['strict', 'Only strong deals']].map(([k, t]) => `<button data-s="${k}" class="${n.sensitivity === k ? 'on' : ''}">${t}</button>`).join('')}</div>
    <form id="nf" class="field-row" style="margin-top:12px">
      ${num('good_deal_threshold', 'Good deal: Deal Score ≥', n.good_deal_threshold, 'min=1 max=100')}${num('interesting_threshold', 'Interesting: Deal Score ≥', n.interesting_threshold, 'min=1 max=100')}
      ${num('personal_good_threshold', 'Good deal: For-you score ≥', n.personal_good_threshold, 'min=1 max=100')}${num('personal_interesting_threshold', 'Interesting: For-you score ≥', n.personal_interesting_threshold, 'min=1 max=100')}
      ${num('renotify_price_drop_pct', 'Notify again after a price drop of (%)', n.renotify_price_drop_pct, 'min=1 max=90')}
      ${num('max_age_hours', 'Only notify for ads newer than (hours)', n.max_age_hours, 'min=1 max=720')}
      ${num('max_per_hour', 'Max push notifications per hour (the rest wait, they are not dropped)', n.max_per_hour, 'min=1 max=200')}
      ${num('calendar_min_score', 'Add to calendar only if Deal Score ≥', n.calendar_min_score, 'min=1 max=100')}</form>
    <div class="row" style="margin-top:10px">${chk('qh', 'Quiet hours', n.quiet_hours.enabled)}<input type="text" id="qs" value="${esc(n.quiet_hours.start)}" style="width:80px" aria-label="Start"> to <input type="text" id="qe" value="${esc(n.quiet_hours.end)}" style="width:80px" aria-label="End"></div>
    <div class="row" style="margin-top:6px">${chk('suppress_during_warmup', 'Stay quiet during the first warm-up', n.suppress_during_warmup)}</div>
    <button class="btn primary" id="nsave" style="margin-top:12px">Save notification settings</button></div>`;
  let sens = n.sensitivity;
  el.querySelectorAll('[data-s]').forEach((b) => (b.onclick = () => { sens = b.dataset.s; el.querySelectorAll('[data-s]').forEach((x) => x.classList.toggle('on', x === b)); }));
  const res = el.querySelector('#testres'), tgres = el.querySelector('#tgres');
  el.querySelectorAll('[data-test]').forEach((b) => (b.onclick = async () => {
    b.disabled = true; res.textContent = 'Sending…'; res.className = 'hint';
    try {
      const r = await post('/notifications/test', { channel: b.dataset.test });
      res.textContent = (r.ok ? '✓ ' : '✗ ') + b.closest('tr').querySelector('b').textContent + ': ' + r.detail;
      res.className = r.ok ? 'hint' : 'error-text';
    } catch (e) { res.textContent = '✗ ' + e.message; res.className = 'error-text'; }
    b.disabled = false;
  }));
  el.querySelector('#tgsavetok').onclick = async () => {
    const v = el.querySelector('#tgtok').value.trim(); if (!v) return fail(new Error('Paste the bot token first'));
    try { await post('/settings/secret', { key: 'telegram_token', value: v }); el.querySelector('#tgtok').value = ''; tgres.textContent = 'Token saved.'; } catch (e) { fail(e); }
  };
  el.querySelector('#tgfind').onclick = async () => {
    tgres.textContent = 'Asking Telegram…';
    try {
      const r = await post('/notifications/telegram/chats', { token: el.querySelector('#tgtok').value.trim() });
      if (!r.chats.length) { tgres.textContent = 'No chats yet: open your bot in Telegram, send it a message, then press Find my chat again.'; return; }
      el.querySelector('#tgchat').value = r.chats[r.chats.length - 1].id;
      tgres.textContent = 'Found: ' + r.chats.map((c) => `${c.name || 'chat'} (${c.id})`).join(', ') + '. Now press Save Telegram.';
    } catch (e) { tgres.textContent = e.message; }
  };
  el.querySelector('#tgsave').onclick = () => save({ telegram: { enabled: el.querySelector('[name=tg_enabled]').checked, chat_id: el.querySelector('#tgchat').value.trim() } }, 'Telegram saved');
  el.querySelector('#nsave').onclick = () => {
    const v = collect(el.querySelector('#nf'));
    Object.assign(v, collect(el.querySelector('#nroi')));
    for (const k of ['desktop_good', 'desktop_interesting', 'discord_good', 'discord_interesting', 'ntfy_good', 'ntfy_interesting', 'telegram_good', 'telegram_interesting', 'suppress_during_warmup', 'in_app_popups']) v[k] = el.querySelector(`[name=${k}]`).checked;
    const qs = el.querySelector('#qs').value, qe = el.querySelector('#qe').value;
    if (!/^\d{1,2}:\d{2}$/.test(qs) || !/^\d{1,2}:\d{2}$/.test(qe)) return fail(new Error('Quiet hours must look like 23:00'));
    v.quiet_hours = { enabled: el.querySelector('[name=qh]').checked, start: qs, end: qe };
    v.sensitivity = sens;
    save({ notify: v });
  };
  el.querySelector('#nsave2').onclick = () => el.querySelector('#nsave').click();
}

// ------------------------------------------------------------------ Discord
function discord(el, d, reload) {
  const c = d.settings.discord, has = d.secrets.discord_token;
  el.innerHTML = `
  <div class="grid g2">
  <div class="card"><h2>Discord bot</h2>
    <form id="df" class="stack" style="gap:10px">
      ${chk('enabled', 'Enable the Discord bot', c.enabled)}
      <label class="field">Bot token ${has ? '<span class="tag good">saved</span>' : '<span class="tag warn">not set</span>'}<input type="password" id="tok" placeholder="${has ? 'Leave empty to keep the saved token' : 'Paste the bot token'}" autocomplete="off"></label>
      <label class="field">Channel ID<input type="text" name="channel_id" value="${esc(c.channel_id)}" placeholder="e.g. 123456789012345678"></label>
      <label class="field">Allowed user IDs (comma separated, empty = anyone in the channel)<input type="text" name="allowed_user_ids" value="${esc(c.allowed_user_ids)}"></label>
      <div class="row"><button class="btn primary">Save Discord settings</button>${has ? '<button type="button" class="btn danger" id="tokdel">Remove token</button>' : ''}</div>
    </form>
    <p class="hint">Status: ${esc(state.status?.discord?.status || 'unknown')}. The token is stored separately (secrets.json), never logged or exported.</p></div>
  <div class="card"><h2>Set up in 5 minutes</h2><ol style="padding-left:18px;margin:0;line-height:1.7">
    <li>Open <a href="https://discord.com/developers/applications" target="_blank" rel="noopener">discord.com/developers/applications</a> → New Application → Bot → Reset Token, copy it.</li>
    <li>On the same Bot page, turn on <b>Message Content Intent</b> (needed to understand your replies).</li>
    <li>OAuth2 → URL Generator: scope <b>bot</b>; permissions <b>View Channels, Send Messages, Embed Links, Read Message History</b>. Open the URL and add the bot to your server.</li>
    <li>In Discord: User Settings → Advanced → Developer Mode on. Right-click your deals channel → Copy Channel ID.</li>
    <li>Paste token and channel ID here, tick “Enable”, save. The bot comes online within ~15 seconds.</li></ol>
    <p class="hint">Then reply to any deal message with e.g. “too expensive”, “I would buy this for €100”, “bought for €120”, “remind me tomorrow”, “7/10”. Commands: !status, !top, !help.</p></div></div>`;
  el.querySelector('#df').onsubmit = async (e) => {
    e.preventDefault();
    const tok = el.querySelector('#tok').value.trim();
    try {
      if (tok) await post('/settings/secret', { key: 'discord_token', value: tok });
      const v = { enabled: el.querySelector('[name=enabled]').checked, channel_id: el.querySelector('[name=channel_id]').value.trim(), allowed_user_ids: el.querySelector('[name=allowed_user_ids]').value.trim() };
      if (await save({ discord: v }, 'Discord settings saved')) reload();
    } catch (err) { fail(err); }
  };
  const td = el.querySelector('#tokdel');
  if (td) td.onclick = async () => { await post('/settings/secret', { key: 'discord_token', value: '' }); ok('Token removed'); reload(); };
}

// ------------------------------------------------------------------ Phone
// Tailscale: a private network between your own devices. "tailscale serve" gives the app an HTTPS address on it.
async function remoteCard(box) {
  let st;
  try {
    const a = await get('/auth');
    if (a.server) {          // running on an always-on server: no Tailscale steps, just the address and log-out
      const who = a.hub ? `<p>You are logged in as <b>${esc(a.user)}</b>. Your deals, settings and alerts are private to this account; other people on this server cannot see or change them.
          <a href="/account">Account &amp; password</a>${a.admin ? ' · <a href="/admin">Manage users / invite someone</a>' : ''}</p>` : '';
      box.innerHTML = `<h2>${a.hub ? 'Your account' : 'Server mode'}</h2>${who}<p>This app runs 24/7 on a server, so your PC can be off. You open it at <b class="num">${esc(location.origin)}</b>${a.hub ? ' and log in once; this device stays logged in for 30 days.' : ' and log in with the password you chose during setup.'}
        On the phone: Android Chrome menu → <b>Install app</b>; iPhone Safari Share → <b>Add to Home Screen</b>.${a.hub ? '' : ' To change the password, edit <code>.env</code> on the server and restart (see SERVER.md).'}</p>
        <div class="row" style="gap:8px;flex-wrap:wrap;margin-top:8px"><button class="btn" id="srv-logout">Log out of this device</button>
          <button class="btn" id="srv-import">Replace ${a.hub ? 'my account' : 'server'} data with my PC data…</button><input type="file" id="srv-file" accept=".zip" hidden></div>
        <p class="hint" id="srv-msg">Make the file on your PC with <b>Pack my data.bat</b>. ${a.hub ? 'Your' : 'The current server'} database is saved in backups first. ${a.hub ? 'Your copy' : 'The server'} restarts for a minute.</p>`;
      box.querySelector('#srv-logout').onclick = async () => { await post('/logout'); location.reload(); };
      return;
    }
  } catch (e) { /* older service: fall through to the Tailscale card */ }
  try { st = await get('/system/remote'); } catch (e) { box.innerHTML = `<h2>Use it anywhere from your phone (Tailscale)</h2><p class="error-text">${esc(e.message)}</p>`; return; }
  const onPc = st.you_are === 'local';
  const step = (done, html) => `<li style="margin:6px 0">${done ? '✅' : '⬜'} ${html}</li>`;
  box.innerHTML = `<h2>Use it anywhere from your phone (Tailscale)</h2>
    <p>Recommended: <b>Tailscale</b> is free for personal use and connects only <i>your own</i> devices. Nothing is opened to the internet, no router settings, and the app gets an HTTPS address, so your phone can install it like an app.
      (Cloudflare Tunnel also works, but needs your own domain and a login page in front of it.)</p>
    ${st.url ? `<div class="card" style="margin:10px 0;background:var(--good-soft);border-color:var(--good)"><b>Your app address:</b> <a href="${esc(st.url)}" target="_blank" rel="noopener" class="num">${esc(st.url)}</a>
      <button class="btn sm" id="rcopy" style="margin-left:8px">Copy</button></div>` : ''}
    <ol style="list-style:none;padding:0;margin:8px 0">
      ${step(st.installed, `Install Tailscale on this PC — easiest: run <b>Phone access anywhere (Tailscale).bat</b> in the app folder; it does steps 1–3 for you. ${st.installed ? '' : '<a href="https://tailscale.com/download/windows" target="_blank" rel="noopener">Download</a>'}`)}
      ${step(st.logged_in, `Sign this PC in to Tailscale${st.dns_name ? ` <span class="muted">(${esc(st.dns_name)})</span>` : ''}`)}
      ${step(st.serving, `Publish the app on your tailnet ${onPc && st.logged_in && !st.serving ? '<button class="btn sm primary" id="rserve">Turn on</button>' : ''}${st.serving && onPc ? ' <button class="btn sm" id="rstop">Turn off</button>' : ''}`)}
      ${step(st.you_are === 'tailscale', 'On the phone: install the Tailscale app, sign in with the same account, open the address above')}
      ${step(false, 'Install it on the phone: Android Chrome menu → <b>Install app</b>; iPhone Safari Share → <b>Add to Home Screen</b>')}
    </ol>
    <p class="hint" id="rmsg">${st.you_are === 'tailscale' ? `You are connected through Tailscale${st.you ? ' as ' + esc(st.you) : ''} — no access token needed.` : ''}
      The PC has to be on with SS Deal Finder running (Startup & data → start with Windows). Only devices signed in to your Tailscale account can open the address.</p>`;
  const msg = box.querySelector('#rmsg');
  const act = (id, on) => { const b = box.querySelector(id); if (b) b.onclick = async () => {
    b.disabled = true; msg.textContent = 'Asking Tailscale… (the first time it may show a link to switch on HTTPS)';
    try {
      const r = await post('/system/remote/serve', { on });
      if (r.enable_link) { msg.innerHTML = `Tailscale needs HTTPS switched on for your account once: <a href="${esc(r.enable_link)}" target="_blank" rel="noopener">open this link</a>, click <b>Enable</b>, then press Turn on again.`; b.disabled = false; return; }
      if (!r.ok) { msg.textContent = 'Tailscale said: ' + (r.output || 'no answer'); b.disabled = false; return; }
      remoteCard(box);
    } catch (e) { msg.textContent = e.message; b.disabled = false; }
  }; };
  act('#rserve', true); act('#rstop', false);
  const cp = box.querySelector('#rcopy'); if (cp) cp.onclick = () => { navigator.clipboard && navigator.clipboard.writeText(st.url); ok('Copied'); };
}

// "Install app" (PWA)
function pwaCard(box) {
  const standalone = matchMedia('(display-mode: standalone)').matches || navigator.standalone;
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  const canPrompt = !!window.__installPrompt;
  box.innerHTML = `<h2>Install as an app</h2>
    ${standalone ? '<p>✅ You are using the installed app.</p>'
      : !isSecureContext ? '<p>Installing needs an HTTPS address — open the app through the Tailscale address above (or on this PC at http://127.0.0.1).</p>'
      : canPrompt ? '<p>Adds SS Deal Finder to your home screen / Start menu with its own icon and window.</p><button class="btn primary" id="pinstall">Install app</button>'
      : ios ? '<p>In Safari tap <b>Share</b> → <b>Add to Home Screen</b>.</p>'
      : '<p>Use your browser menu → <b>Install app</b> (or <b>Add to Home screen</b>).</p>'}`;
  const b = box.querySelector('#pinstall');
  if (b) b.onclick = async () => { const p = window.__installPrompt; window.__installPrompt = null; p.prompt(); await p.userChoice; pwaCard(box); };
}

function phone(el, d) {
  const c = d.settings.ntfy, api = d.settings.api;
  el.innerHTML = `
  <div class="card" id="remote" style="margin-bottom:14px"><h2>Use it anywhere from your phone (Tailscale)</h2><div class="loading">Checking Tailscale</div></div>
  <div class="card" id="pwa" style="margin-bottom:14px"></div>
  <div class="grid g2">
  <div class="card"><h2>Phone notifications today (ntfy)</h2>
    <p>Until the Android companion app exists, the free <a href="https://ntfy.sh" target="_blank" rel="noopener">ntfy</a> app delivers push notifications to your phone. Install it, subscribe to a hard-to-guess topic name, and enter the same name here.</p>
    <form id="pf" class="stack" style="gap:10px">${chk('enabled', 'Send phone notifications', c.enabled)}
      <label class="field">Server<input type="text" name="server" value="${esc(c.server)}"></label>
      <label class="field">Topic<input type="text" name="topic" value="${esc(c.topic)}" placeholder="e.g. ssdeals-k7q2v9x"></label>
      <button class="btn primary">Save phone settings</button></form>
    <p class="hint">Anyone who knows a public ntfy topic can read it — use a random name, or your own ntfy server with a token.</p></div>
  <div class="card"><h2>Same Wi-Fi only (LAN)</h2>
    <p>The interface is responsive and works in a phone browser. To reach it from your phone on the same Wi-Fi, allow LAN access and set an access token, then open <span class="num">http://&lt;PC address&gt;:${api.port}/?token=…</span> — API calls from other devices must send the token.</p>
    <div class="stack" style="gap:10px">${chk('allow_lan', 'Allow access from other devices on my network (restart the service after changing)', api.allow_lan)}
      <label class="field">Access token ${d.secrets.api_token ? '<span class="tag good">saved</span>' : '<span class="tag warn">not set</span>'}<input type="password" id="apitok" placeholder="at least 16 characters"></label>
      <div class="row"><button class="btn" id="apisave">Save remote access</button>
        <button class="btn primary" id="apirestart">Save and restart service now</button></div>
      <p class="hint">Changing LAN access only takes effect after a restart. “Save and restart” does it for you; the page reloads in a few seconds.</p></div></div></div>`;
  remoteCard(el.querySelector('#remote'));
  pwaCard(el.querySelector('#pwa'));
  el.querySelector('#pf').onsubmit = (e) => { e.preventDefault(); save({ ntfy: { enabled: el.querySelector('[name=enabled]').checked, server: el.querySelector('[name=server]').value.trim(), topic: el.querySelector('[name=topic]').value.trim() } }); };
  el.querySelector('#apirestart').onclick = async () => {
    await el.querySelector('#apisave').onclick();
    try { await post('/system/restart', {}); } catch (e) { /* the service closes the connection while restarting */ }
    ok('Restarting the service…');
    const t0 = Date.now();
    const wait = setInterval(async () => {
      try { const r = await fetch('/api/status', { headers: { 'x-api-token': apiToken() } }); if (r.ok || Date.now() - t0 > 40000) { clearInterval(wait); location.reload(); } }
      catch (e) { if (Date.now() - t0 > 40000) { clearInterval(wait); location.reload(); } }
    }, 2000);
  };
  el.querySelector('#apisave').onclick = async () => {
    const t = el.querySelector('#apitok').value.trim();
    const lan = el.querySelector('[name=allow_lan]').checked;
    if (lan && !t && !d.secrets.api_token) return fail(new Error('Set an access token before allowing LAN access'));
    if (t && t.length < 16) return fail(new Error('Use at least 16 characters for the token'));
    try { if (t) await post('/settings/secret', { key: 'api_token', value: t }); await save({ api: { allow_lan: lan } }, 'Saved — restart the service to apply'); } catch (e) { fail(e); }
  };
}

// ------------------------------------------------------------------ Preferences & learning
function prefs(el, d) {
  const p = d.settings.preferences, l = d.settings.learning, cats = d.categories;
  const brands = Object.entries(p.brands || {});
  el.innerHTML = `
  <div class="card"><h2>What you're interested in</h2><p class="hint">Sets your starting Personal Value Score; the app keeps learning from your feedback on top of this. These settings never change market prices.</p>
    <div class="table-wrap"><table class="data"><thead><tr><th>Category</th><th style="width:45%">Interest</th><th>Budget €</th></tr></thead><tbody>
    ${Object.entries(cats).map(([k, c]) => `<tr data-pc="${k}"><td>${esc(c.name)}</td><td><input type="range" min="-1" max="1" step="0.25" value="${p.categories?.[k] ?? 0}" style="width:100%" aria-label="Interest in ${esc(c.name)}"></td>
      <td><input type="number" min="0" value="${p.budgets?.[k] ?? ''}" style="width:100px" aria-label="Budget"></td></tr>`).join('')}</tbody></table></div>
    <div class="field-row" style="margin-top:12px">
      <label class="field">Liked keywords (comma separated)<input type="text" id="kl" value="${esc((p.keywords_like || []).join(', '))}" placeholder="full frame, 16gb, oled"></label>
      <label class="field">Disliked keywords<input type="text" id="kd" value="${esc((p.keywords_dislike || []).join(', '))}" placeholder="mining, cracked"></label>
      <label class="field">Default budget € (0 = none)<input type="number" id="bd" min="0" value="${p.budget_default || 0}"></label></div>
    <h3 style="margin-top:14px">Brand preferences</h3>
    <div id="brands">${brands.map(([b, v]) => brandRow(b, v)).join('')}</div>
    <button class="btn sm" id="badd" style="margin-top:6px">Add brand</button>
    <div style="margin-top:14px"><button class="btn primary" id="psave">Save preferences</button></div></div>
  <div class="card" style="margin-top:14px"><h2>Learning controls</h2><form id="lf" class="field-row">
    ${num('personal_weight', 'Strength of learned preferences (0–3)', l.personal_weight, 'min=0 max=3 step=0.1')}
    ${num('market_correction_weight', 'One market correction counts as N listings', l.market_correction_weight, 'min=0.5 max=50 step=0.5')}
    ${num('confirmed_sale_weight', 'One confirmed sale counts as N listings', l.confirmed_sale_weight, 'min=0.5 max=50 step=0.5')}
    ${num('min_observations', 'Comparables needed before valuing a product', l.min_observations, 'min=1 max=50')}</form>
    <div class="row" style="margin-top:10px">${chk('lenabled', 'Learn automatically from my actions', l.enabled)}<button class="btn primary" id="lsave">Save learning settings</button><a class="btn" href="#/learning">Review what was learned</a></div></div>`;
  el.querySelector('#badd').onclick = () => el.querySelector('#brands').insertAdjacentHTML('beforeend', brandRow('', 0));
  el.querySelector('#brands').addEventListener('click', (e) => { if (e.target.dataset.brm !== undefined) e.target.closest('.row').remove(); });
  el.querySelector('#psave').onclick = () => {
    const categories = {}, budgets = {}, brandsOut = {};
    el.querySelectorAll('[data-pc]').forEach((tr) => {
      const r = Number(tr.querySelector('input[type=range]').value), b = tr.querySelector('input[type=number]').value;
      if (r) categories[tr.dataset.pc] = r; if (b) budgets[tr.dataset.pc] = Number(b);
    });
    el.querySelectorAll('.brand-row').forEach((r) => { const n = r.querySelector('input[type=text]').value.trim(); if (n) brandsOut[n] = Number(r.querySelector('select').value); });
    const split = (s) => s.split(',').map((x) => x.trim()).filter(Boolean);
    save({ preferences: { categories, budgets, brands: brandsOut, keywords_like: split(el.querySelector('#kl').value), keywords_dislike: split(el.querySelector('#kd').value), budget_default: Number(el.querySelector('#bd').value) || 0 } }, 'Preferences saved — listings are being re-scored');
  };
  el.querySelector('#lsave').onclick = () => { const v = collect(el.querySelector('#lf')); v.enabled = el.querySelector('[name=lenabled]').checked; save({ learning: v }); };
}
const brandRow = (b, v) => `<div class="row brand-row" style="margin-bottom:6px"><input type="text" value="${esc(b)}" placeholder="Brand, e.g. ASUS" style="width:180px">
  <select>${[[1, 'Love'], [0.5, 'Like'], [0, 'Neutral'], [-0.5, 'Dislike'], [-1, 'Avoid']].map(([x, t]) => `<option value="${x}" ${Number(v) === x ? 'selected' : ''}>${t}</option>`).join('')}</select>
  <button type="button" class="btn sm ghost" data-brm>Remove</button></div>`;

// ------------------------------------------------------------------ Startup & data
async function dataTab(el, d, reload) {
  const [auto, backups] = await Promise.all([get('/system/autostart'), get('/backups')]);
  const lg = d.settings.logs, b = d.settings.backup;
  const sets = ['listings', 'price_history', 'listing_events', 'market', 'market_history', 'market_corrections', 'feedback', 'notifications', 'watchlist', 'roi_plans', 'tasks', 'scan_runs'];
  el.innerHTML = `
  <div class="grid g2">
  <div class="card"><h2>Startup</h2>
    ${auto.supported ? chk('auto', 'Start background monitoring when I sign in to Windows', auto.enabled) : `<p class="muted">${esc(auto.note)}</p>`}
    <p class="hint">Monitoring runs as a background service. Closing the window does not stop it; use the tray icon or Activity page to pause or stop.</p></div>
  <div class="card"><h2>Logs</h2><form id="lgf" class="field-row">${num('retention_days', 'Keep log files for (days)', lg.retention_days, 'min=1')}${num('max_file_mb', 'Rotate log file at (MB)', lg.max_file_mb, 'min=1')}</form>
    <button class="btn primary" id="lgsave" style="margin-top:10px">Save log settings</button></div>
  <div class="card"><h2>Export data</h2><p class="hint">CSV opens in Excel; JSON / JSONL are convenient for scripts or a local LLM.</p>
    <div class="row"><select id="exs">${sets.map((s) => `<option>${s}</option>`).join('')}</select>
    ${['csv', 'json', 'jsonl'].map((f) => `<button class="btn sm" data-ex="${f}">${f.toUpperCase()}</button>`).join('')}</div></div>
  <div class="card"><h2>Backups</h2>
    <div class="row">${chk('auto_daily', 'Automatic daily backup', b.auto_daily)}<label class="field" style="flex-direction:row;align-items:center;gap:6px">Keep<input type="number" id="bk" value="${b.keep}" min="1" style="width:70px"></label><button class="btn sm" id="bsave">Save</button><button class="btn sm primary" id="bnow">Back up now</button></div>
    <div class="table-wrap" style="margin-top:10px;max-height:240px;overflow-y:auto"><table class="data"><tbody>${backups.map((x) => `<tr><td class="small">${esc(x.name)}</td><td class="small muted">${dt(x.created)}</td><td class="small num">${(x.size / 1048576).toFixed(1)} MB</td>
      <td class="r"><a class="btn sm" href="${withToken('/api/backups/download/' + encodeURIComponent(x.name))}">Download</a> <button class="btn sm" data-restore="${esc(x.name)}">Restore</button></td></tr>`).join('') || '<tr><td class="muted">No backups yet</td></tr>'}</tbody></table></div></div>
  <div class="card span2"><h2>Reset settings</h2><p class="hint">Restores default settings. Your listings, market data, feedback and plans are kept.</p><button class="btn danger" id="sreset">Reset all settings to defaults</button></div></div>`;
  const ac = el.querySelector('[name=auto]');
  if (ac) ac.onchange = async () => { try { await post('/system/autostart', { enabled: ac.checked }); ok(ac.checked ? 'Will start with Windows' : 'Autostart disabled'); } catch (e) { fail(e); ac.checked = !ac.checked; } };
  el.querySelector('#lgsave').onclick = () => save({ logs: collect(el.querySelector('#lgf')) });
  el.querySelectorAll('[data-ex]').forEach((x) => (x.onclick = () => { window.location = withToken(`/api/export/${el.querySelector('#exs').value}.${x.dataset.ex}`); }));
  el.querySelector('#bsave').onclick = () => save({ backup: { auto_daily: el.querySelector('[name=auto_daily]').checked, keep: Number(el.querySelector('#bk').value) || 10 } });
  el.querySelector('#bnow').onclick = async () => { try { const r = await post('/backups'); ok('Backup created: ' + r.name); reload(); } catch (e) { fail(e); } };
  el.querySelectorAll('[data-restore]').forEach((x) => (x.onclick = async () => {
    if (!(await confirmBox(`Restore ${x.dataset.restore}? The current database is backed up first.`, 'Restore'))) return;
    try { const r = await post('/backups/restore', { name: x.dataset.restore }); ok(r.message); } catch (e) { fail(e); }
  }));
  el.querySelector('#sreset').onclick = async () => { if (!(await confirmBox('Reset all settings to defaults?', 'Reset'))) return; await post('/settings/reset', {}); ok('Settings reset'); location.reload(); };
}
