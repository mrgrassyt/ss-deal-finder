import { get, post, del, esc, eur, dt, ago, lineChart, dealItem, empty, ok, fail, catName, debounce, state, confirmBox } from '../core.js';

export async function render(view, params) {
  if (params.get('key')) return product(view, params.get('key'));
  const cats = Object.entries(state.meta?.categories || {});
  view.innerHTML = `
  <div class="page-head"><div><h1>Market prices</h1><p>The app's own price database, built from the listings it observes. Ranges are the middle half of comparable asking prices; confirmed sales and your corrections are blended in when you add them.</p></div>
    <button class="btn" id="recalc">Recalculate now</button></div>
  <div class="card"><div class="filters">
    <label class="field" style="grid-column:span 2">Find a product<input type="search" id="mq" placeholder="e.g. rx 6700, d610, iphone 13"></label>
    <label class="field">Category<select id="mc"><option value="">All</option>${cats.map(([k, c]) => `<option value="${k}">${esc(c.name)}</option>`).join('')}</select></label>
    <label class="field">Sort<select id="ms"><option value="n">Most comparables</option><option value="name">Name</option><option value="price">Highest value</option><option value="confidence">Confidence</option><option value="updated">Recently updated</option></select></label>
  </div></div>
  <div class="card" style="margin-top:14px;padding:0" id="mres"><div class="loading">Loading</div></div>
  <div class="card" style="margin-top:14px" id="mcats"></div>`;
  const load = async () => {
    const qs = new URLSearchParams({ q: view.querySelector('#mq').value, category: view.querySelector('#mc').value, sort: view.querySelector('#ms').value });
    const d = await get('/market?' + qs);
    view.querySelector('#mres').innerHTML = d.items.length ? `<div class="table-wrap"><table class="data"><thead><tr><th>Product</th><th class="hide-sm">Category</th><th class="r">Low</th><th class="r">Typical</th><th class="r">High</th><th class="r">Comparables</th><th class="r">Confidence</th><th class="hide-sm">Basis</th></tr></thead><tbody>
      ${d.items.map((m) => `<tr class="clickable" data-key="${esc(m.product_key)}"><td><b>${esc(m.product_name)}</b><div class="lsub">${esc(m.product_key)}</div></td><td class="hide-sm">${esc(catName(m.category_key))}</td>
        <td class="r num">${eur(m.low)}</td><td class="r num"><b>${eur(m.typical)}</b></td><td class="r num">${eur(m.high)}</td><td class="r num">${m.n} <span class="muted">(${m.n_active} live)</span></td>
        <td class="r num">${Math.round(m.confidence * 100)}%</td><td class="hide-sm small">${basisText(m.basis)}</td></tr>`).join('')}</tbody></table></div>`
      : empty('No products priced yet', ' Prices appear after the scanner has seen a few comparable listings of the same model.');
    view.querySelectorAll('[data-key]').forEach((r) => (r.onclick = () => { location.hash = '#/market?key=' + encodeURIComponent(r.dataset.key); }));
    view.querySelector('#mcats').innerHTML = `<h2>Category reference prices</h2><p class="hint">Used to spot unidentified items that are unusually cheap for their category.</p>
      <div class="table-wrap"><table class="data"><thead><tr><th>Category</th><th class="r">Lower quarter</th><th class="r">Median</th><th class="r">Listings</th></tr></thead><tbody>
      ${d.categories.map((c) => `<tr><td>${esc(catName(c.category_key))}</td><td class="r num">${eur(c.low)}</td><td class="r num">${eur(c.typical)}</td><td class="r num">${c.n}</td></tr>`).join('')}</tbody></table></div>`;
  };
  view.querySelector('#mq').addEventListener('input', debounce(load, 250));
  view.querySelector('#mc').onchange = load; view.querySelector('#ms').onchange = load;
  view.querySelector('#recalc').onclick = async () => { try { await post('/scanner/recalc'); ok('Market recalculated'); load(); } catch (e) { fail(e); } };
  load();
}

const basisText = (b) => b === 'manual' ? 'your override' : (b || '').includes('sales') ? 'asking prices + sales' : (b || '').includes('corrections') ? 'asking prices + your references' : 'asking prices';

async function product(view, key) {
  const d = await get('/market/product?key=' + encodeURIComponent(key));
  const w = d.stats.find((s) => s.bucket === 'working');
  const bucket = (b) => d.stats.find((s) => s.bucket === b);
  const hist = d.history.map((h) => [new Date(h.day).getTime() / 1000, h.typical]);
  const lows = d.history.map((h) => [new Date(h.day).getTime() / 1000, h.low]);
  const highs = d.history.map((h) => [new Date(h.day).getTime() / 1000, h.high]);
  view.innerHTML = `
  <div class="page-head"><div><a href="#/market" class="small">Market prices</a><h1>${esc(w?.product_name || key)}</h1><p class="muted">${esc(key)}</p></div>
    <a class="btn" href="#/listings?product_key=${encodeURIComponent(key)}&status=all">All listings</a></div>
  <div class="grid g4">
    ${['working', 'used', 'new', 'broken'].map((b) => { const s = bucket(b); return `<div class="card"><h3>${{ working: 'All working units', used: 'Used', new: 'New', broken: 'Broken / for parts' }[b]}</h3>
      ${s ? `<div class="price" style="font-size:24px;margin-top:6px">${eur(s.typical)}</div><div class="small muted">${eur(s.low)}–${eur(s.high)} · ${s.n} comparables · ${Math.round(s.confidence * 100)}% confidence</div>
        <div class="small muted">median ${eur(s.median)}, mean ${eur(s.mean)}${s.avg_days_listed ? ` · sells in ~${Math.round(s.avg_days_listed)} days` : ''}${s.bundle_premium != null ? ` · bundles +${Math.round(s.bundle_premium * 100)}%` : ''}</div>`
        : '<p class="muted small">No data yet</p>'}</div>`; }).join('')}
  </div>
  <div class="grid g3" style="margin-top:14px">
    <div class="card span2"><h2>Typical price over time</h2>${lineChart([{ points: hist }, { points: lows }, { points: highs }], { height: 220, width: 760 })}
      <div class="legend"><span><i style="background:var(--chart-1,var(--accent))"></i>Typical</span><span><i style="background:var(--chart-2,var(--good))"></i>Low</span><span><i style="background:var(--chart-3,var(--warn))"></i>High</span></div>
      <p class="hint">${w ? `Updated ${ago(w.updated_at)}. Basis: ${basisText(w.basis)}. Asking prices are not confirmed sale prices.` : ''}</p></div>
    <div class="card"><h2>Correct this estimate</h2>
      <p class="hint">A reference counts as a few observations, so one wrong number can't distort the database. An override replaces the estimate until removed. Recording a sale in the ROI planner adds a confirmed sale price.</p>
      <div class="field-row"><label class="field">Value (€)<input type="number" id="cv" min="1"></label>
      <label class="field">Type<select id="ck"><option value="reference">Reference</option><option value="override">Override</option></select></label></div>
      <button class="btn primary" id="csave" style="margin-top:10px">Save correction</button>
      <hr class="sep"><h3>Corrections and sales</h3>
      ${d.corrections.length ? `<ul class="timeline">${d.corrections.map((c) => `<li style="${c.active ? '' : 'opacity:.5'}">${dt(c.created_at)} — ${esc(c.kind)} ${eur(c.value)} ${c.note ? `<span class="muted">${esc(c.note)}</span>` : ''} ${c.active ? `<button class="btn sm ghost" data-cdel="${c.id}">Remove</button>` : '(removed)'}</li>`).join('')}</ul>` : '<p class="muted small">None</p>'}
    </div>
  </div>
  <div class="card" style="margin-top:14px"><h2>Observed listings</h2>${d.listings.length ? `<div class="deal-list">${d.listings.map(dealItem).join('')}</div>` : empty('No listings')}</div>`;
  view.querySelector('#csave').onclick = async () => {
    const value = Number(view.querySelector('#cv').value); if (!value) return fail(new Error('Enter a value in euros'));
    try { await post('/market/correction', { product_key: key, value, kind: view.querySelector('#ck').value, note: 'market page' }); ok('Correction saved'); product(view, key); } catch (e) { fail(e); }
  };
  view.querySelectorAll('[data-cdel]').forEach((b) => (b.onclick = async () => {
    if (!(await confirmBox('Remove this correction?', 'Remove'))) return;
    try { await del('/market/correction/' + b.dataset.cdel); ok('Removed'); product(view, key); } catch (e) { fail(e); }
  }));
}
