import { get, esc, eur, ago, moneyBox, ruler, scores, levelTag, condTag, flagTags, thumb, priceHtml, empty, catName, debounce, state } from '../core.js';

const VIEWS = [['table', '☰ Table'], ['cards', '▦ Cards'], ['compact', '≡ Compact']];
const getView = () => { try { return localStorage.getItem('ssd-lview') || 'table'; } catch (e) { return 'table'; } };
const setView = (v) => { try { localStorage.setItem('ssd-lview', v); } catch (e) { /* ignore */ } };
const F = { q: '', category: '', min_price: '', max_price: '', condition: '', min_deal: '', min_personal: '', classification: '',
  status: 'active', saved: false, sort: 'newest', page: 1, flag: '', product_key: '' };

export async function render(view, params) {
  const f = { ...F };
  for (const k of Object.keys(F)) if (params.has(k)) f[k] = k === 'saved' ? params.get(k) === '1' : params.get(k);
  if (params.has('q') && !params.has('sort')) f.sort = 'profit';
  if (f.sort === 'deal') f.sort = 'profit';
  const cats = Object.entries(state.meta?.categories || {});
  view.innerHTML = `
  <div class="page-head"><div><h1>Listings</h1><p>Everything the scanner has seen, including removed ads. Click a row for full details and history.</p></div></div>
  <div class="card">
    <form class="filters" id="lf">
      <label class="field" style="grid-column:span 2">Search<input type="search" name="q" value="${esc(f.q)}" placeholder="words in title or description"></label>
      <label class="field">Category<select name="category"><option value="">All categories</option>${cats.map(([k, c]) => `<option value="${k}" ${f.category === k ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</select></label>
      <label class="field adv-only">Opportunity<select name="classification">
        <option value="">Any</option><option value="GOOD_DEAL,INTERESTING" ${f.classification === 'GOOD_DEAL,INTERESTING' ? 'selected' : ''}>Good deal or interesting</option>
        <option value="GOOD_DEAL" ${f.classification === 'GOOD_DEAL' ? 'selected' : ''}>Good deals</option><option value="INTERESTING" ${f.classification === 'INTERESTING' ? 'selected' : ''}>Interesting</option>
        <option value="IGNORE" ${f.classification === 'IGNORE' ? 'selected' : ''}>Ignored by filters</option></select></label>
      <label class="field adv-only">Condition<select name="condition"><option value="">Any</option>${['new', 'used', 'untested', 'broken', 'parts'].map((c) => `<option ${f.condition === c ? 'selected' : ''}>${c}</option>`).join('')}<option value="broken,parts,untested" ${f.condition === 'broken,parts,untested' ? 'selected' : ''}>Repair candidates</option></select></label>
      <label class="field adv-only">Min €<input type="number" name="min_price" value="${esc(f.min_price)}" min="0"></label>
      <label class="field">Max €<input type="number" name="max_price" value="${esc(f.max_price)}" min="0"></label>
      <label class="field adv-only">Min For-you score<input type="number" name="min_personal" value="${esc(f.min_personal)}" min="0" max="100"></label>
      <label class="field adv-only">Status<select name="status"><option value="active" ${f.status === 'active' ? 'selected' : ''}>On SS.lv now</option><option value="removed" ${f.status === 'removed' ? 'selected' : ''}>Removed</option><option value="all" ${f.status === 'all' ? 'selected' : ''}>All</option></select></label>
      <label class="field">Sort<select name="sort">${[['newest', 'Newest'], ['profit', 'Highest profit'], ['roi', 'Highest ROI'], ['personal', 'Best match for me'], ['cheapest', 'Cheapest'], ['expensive', 'Most expensive'], ['drop', 'Biggest price drop'], ['updated', 'Recently seen']].map(([k, t]) => `<option value="${k}" ${f.sort === k ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
      <label class="check adv-only" style="align-self:center"><input type="checkbox" name="saved" ${f.saved ? 'checked' : ''}> Saved only</label>
      <button type="button" class="btn ghost" id="lf-reset">Clear filters</button>
    </form>
  </div>
  <div class="row between" style="margin-top:14px"><span class="muted small" id="lcount"></span>
    <div class="seg" id="lview" role="group" aria-label="Layout">${VIEWS.map(([k, t]) => `<button type="button" data-v="${k}" class="${getView() === k ? 'on' : ''}">${t}</button>`).join('')}</div></div>
  <div id="lwrap" style="margin-top:10px"><div id="lres"><div class="loading">Loading</div></div></div>`;
  const form = view.querySelector('#lf');
  let last = null;
  const draw = () => {
    if (!last) return;
    const res = view.querySelector('#lres'), mode = getView();
    res.innerHTML = renderItems(last, mode);
    view.querySelector('#lcount').textContent = `${last.total.toLocaleString()} listings`;
    res.querySelectorAll('[data-page]').forEach((b) => (b.onclick = () => { f.page = Number(b.dataset.page); load(); window.scrollTo(0, 0); }));
  };
  view.querySelectorAll('#lview [data-v]').forEach((b) => (b.onclick = () => {
    setView(b.dataset.v); view.querySelectorAll('#lview [data-v]').forEach((x) => x.classList.toggle('on', x === b)); draw();
  }));
  let seq = 0;   // only the newest request may draw: the input + change events used to race and show a stale order
  const load = async () => {
    const mine = ++seq;
    const fd = new FormData(form);
    const qs = new URLSearchParams();
    for (const [k, v] of fd.entries()) if (v !== '' && k !== 'saved') qs.set(k, v);
    if (form.saved.checked) qs.set('saved', 'true');
    if (f.flag) qs.set('flag', f.flag);
    if (f.product_key) qs.set('product_key', f.product_key);
    qs.set('page', f.page); qs.set('page_size', state.settings?.ui?.page_size || 50);
    const res = view.querySelector('#lres');
    try {
      const data = await get('/listings?' + qs);
      if (mine !== seq) return;
      last = data; draw();
    } catch (e) { res.innerHTML = `<p class="error-text" style="padding:16px">${esc(e.message)}</p>`; }
  };
  const reload = () => { f.page = 1; load(); };
  form.addEventListener('input', debounce(reload, 250));
  form.addEventListener('change', reload);
  form.addEventListener('submit', (e) => { e.preventDefault(); reload(); });
  view.querySelector('#lf-reset').onclick = () => { location.hash = '#/listings?_r=' + Date.now(); };
  load();
}

function pager(data) {
  const pages = Math.ceil(data.total / data.page_size);
  return `<div class="pager"><span class="muted small">page ${data.page} of ${pages}</span>
    <button class="btn sm" data-page="${data.page - 1}" ${data.page <= 1 ? 'disabled' : ''}>Previous</button>
    <button class="btn sm" data-page="${data.page + 1}" ${data.page >= pages ? 'disabled' : ''}>Next</button></div>`;
}
function renderItems(data, mode) {
  if (!data.items.length) return `<div class="card">${empty('No listings match these filters', ' Try clearing a filter or widening the price range.')}</div>`;
  if (mode === 'cards') return `<div class="lcards">${data.items.map(card).join('')}</div>${pager(data)}`;
  if (mode === 'compact') return `<div class="card" style="padding:6px 10px"><div class="lcompact">${data.items.map(compact).join('')}</div></div>${pager(data)}`;
  return `<div class="card" style="padding:0">${table(data)}</div>`;
}
const title = (l) => esc(l.product_name ? l.product_name + ' — ' + l.title : l.title);
function card(l) {
  const bigThumb = thumb(l).replace('class="thumb', 'class="thumb big');
  return `<div class="card lcard clickable ${l.status === 'removed' ? 'removed' : ''}" data-open="${l.id}">
    <div class="lc-img">${bigThumb}<span class="lc-level">${levelTag(l.classification)}</span></div>
    <div class="ltitle" style="margin-top:8px">${esc(l.product_name || l.title)}</div>
    <div class="lsub">${esc(l.headline || (l.title || '').slice(0, 70))}</div>
    <div class="lc-money">${moneyBox(l)}</div>
    <div class="adv-only" style="margin:6px 0 2px">${ruler(l)}</div>
    <div class="row" style="gap:5px;margin-top:6px">${condTag(l.condition)} ${flagTags((l.flags || []).slice(0, 3))}</div>
    <div class="lsub" style="margin-top:6px">${esc(catName(l.category_key))} · ${ago(l.first_seen)}</div></div>`;
}
function compact(l) {
  return `<div class="lcrow ${l.status === 'removed' ? 'removed' : ''}" data-open="${l.id}">
    <span class="lc-dot ${l.classification || ''}" title="${esc(l.classification || '')}"></span>
    <span class="ltitle one">${title(l)}</span><span class="hide-sm">${condTag(l.condition)}</span>
    <span class="hide-sm lsub">${esc(catName(l.category_key))}</span><span class="lc-p">${priceHtml(l)}</span>
    <span class="num lc-sell muted" title="Likely resale">${l.flip ? '≈ ' + eur(l.flip.resale) : '—'}</span>
    <span class="num lc-profit ${l.flip ? (l.flip.profit >= 0 ? 'pos' : 'neg') : 'muted'}" title="Profit after costs${l.flip ? ', ROI ' + l.flip.roi + '%' : ''}">${l.flip ? (l.flip.profit >= 0 ? '+' : '−') + '€' + Math.abs(l.flip.profit) : '—'}</span></div>`;
}

function table(data) {
  return `<div class="table-wrap"><table class="data"><thead><tr><th></th><th>Listing</th><th class="hide-sm adv-only">Market range vs asking</th><th class="r">Buy · Sell · Profit · ROI</th><th class="hide-sm">Seen</th></tr></thead><tbody>
  ${data.items.map((l) => `<tr class="clickable ${l.status === 'removed' ? 'removed' : ''}" data-open="${l.id}">
    <td style="width:66px">${thumb(l)}</td>
    <td><div class="ltitle">${esc(l.product_name ? l.product_name + ' — ' + l.title : l.title)}</div>
      <div class="lsub row" style="gap:5px;margin-top:4px"><span class="adv-only">${levelTag(l.classification)}</span> ${condTag(l.condition)} <span class="adv-only">${flagTags(l.flags)}</span> <span>${esc(catName(l.category_key))}</span></div>
      ${l.headline ? `<div class="lsub adv-only">${esc(l.headline)}</div>` : ''}</td>
    <td class="hide-sm adv-only" style="width:220px">${ruler(l)}</td>
    <td class="r" style="width:190px">${moneyBox(l)}</td>
    <td class="hide-sm small muted">${ago(l.first_seen)}${l.status === 'removed' ? '<br>removed' : ''}</td></tr>`).join('')}
  </tbody></table></div>
  <div style="padding:0 14px 14px">${pager(data)}</div>`;
}
