import { get, post, esc, eur, dt, empty, ok, fail, confirmBox, catName, barChart } from '../core.js';

const KIND = { rating: 'Rating', interested: 'Interested', saved: 'Saved', unsaved: 'Unsaved', ignored: 'Ignored', too_expensive: 'Too expensive',
  bought: 'Bought', would_pay: 'Would pay', not_for_me: 'Not for me', good_deal: 'Good deal', brand_dislike: 'Brand dislike', brand_like: 'Brand like',
  remind: 'Reminder', market_value: 'Market value', sold: 'Sold', overpriced: 'Overpriced' };
const TYPE = { cat: 'Categories', brand: 'Brands', product: 'Products', cond: 'Conditions', band: 'Price bands', flag: 'Bundles & lots' };

export async function render(view) {
  const d = await get('/learning');
  const f = d.summary.features;
  const bar = (v) => `<span style="display:inline-block;width:${Math.min(60, Math.abs(v) * 120)}px;height:8px;border-radius:2px;background:${v >= 0 ? 'var(--good)' : 'var(--bad)'};vertical-align:middle"></span>`;
  const featTable = (type) => {
    const items = (f[type] || []).filter((x) => Math.abs(x.preference) > 0.01);
    if (!items.length) return '<p class="muted small">Nothing learned yet.</p>';
    return `<table class="data"><tbody>${items.slice(0, 8).map((x) => `<tr><td>${esc(type === 'cat' ? catName(x.value) : x.value)}</td><td class="r num">${x.preference > 0 ? '+' : ''}${x.preference.toFixed(2)}</td><td style="width:70px">${bar(x.preference)}</td><td class="r small muted">${x.evidence.toFixed(1)} evid.</td></tr>`).join('')}</tbody></table>`;
  };
  const active = d.feedback.filter((x) => x.active).length;
  view.innerHTML = `
  <div class="page-head"><div><h1>Learning</h1><p>What the app has learned about your taste. Feedback no longer changes any score; the Personal score now comes only from your My items list. This page is kept for history. Every change is listed below and can be undone.</p></div>
    <button class="btn danger" id="reset">Reset personal learning</button></div>
  <div class="figures">
    <div class="figure"><div class="v">${active}</div><div class="l">Active feedback events</div></div>
    <div class="figure"><div class="v">${d.rating_by_level.reduce((a, r) => a + r.n, 0)}</div><div class="l">Ratings given</div></div>
    ${d.rating_by_level.map((r) => `<div class="figure"><div class="v">${r.avg_rating ? r.avg_rating.toFixed(1) : '—'}</div><div class="l">Avg rating, ${esc((r.level || 'unknown').replace('_', ' ').toLowerCase())}</div></div>`).join('')}
  </div>
  <div class="grid g3" style="margin-top:14px">
    ${['cat', 'brand', 'product'].map((t) => `<div class="card"><h2>${TYPE[t]}</h2>${featTable(t)}</div>`).join('')}
    ${['cond', 'band', 'flag'].map((t) => `<div class="card"><h2>${TYPE[t]}</h2>${featTable(t)}</div>`).join('')}
  </div>
  <div class="grid g3" style="margin-top:14px">
    <div class="card"><h2>Ratings by Deal Score</h2>${barChart(d.rating_by_deal_band, { width: 380, keys: [['avg_rating', 'b1']], labels: (x) => x.band + '+' })}
      <p class="hint">Shows whether high Deal Scores match what you actually rate highly.</p></div>
    <div class="card"><h2>Usually ignored</h2>${d.ignored_categories.length ? `<table class="data"><tbody>${d.ignored_categories.map((x) => `<tr><td>${esc(catName(x.category))}</td><td class="r num">${x.n}</td></tr>`).join('')}</tbody></table>` : '<p class="muted small">No ignored listings yet.</p>'}</div>
    <div class="card"><h2>Typical budget</h2>${d.budget.length ? `<table class="data"><tbody>${d.budget.map((x) => `<tr><td>${esc(catName(x.category))}</td><td class="r num">${eur(x.typical_price)}</td><td class="r small muted">${x.n}</td></tr>`).join('')}</tbody></table>` : '<p class="muted small">Learned from items you save, buy or say you would pay for.</p>'}
      ${Object.keys(d.summary.price_targets || {}).length ? `<h3 style="margin-top:12px">Prices you'd pay</h3><table class="data"><tbody>${Object.entries(d.summary.price_targets).map(([k, v]) => `<tr><td class="small">${esc(k)}</td><td class="r num">${eur(v)}</td></tr>`).join('')}</tbody></table>` : ''}</div>
  </div>
  <div class="card" style="margin-top:14px"><h2>Learning history</h2>
    ${d.feedback.length ? `<div class="table-wrap"><table class="data"><thead><tr><th>When</th><th>Feedback</th><th>Listing</th><th>Effect</th><th></th></tr></thead><tbody>
      ${d.feedback.map((x) => `<tr style="${x.active ? '' : 'opacity:.5'}"><td class="small">${dt(x.created_at)}<div class="lsub">${esc(x.source)}</div></td>
        <td><b>${KIND[x.kind] || x.kind}</b>${x.value != null ? ` ${x.kind === 'rating' ? x.value + '/10' : eur(x.value)}` : ''}${x.superseded_by ? '<div class="lsub">replaced by a newer rating</div>' : ''}</td>
        <td class="small">${x.listing_id ? `<a href="#/learning?listing=${x.listing_id}">${esc((x.product_name || x.title || '').slice(0, 50))}</a>` : '—'}</td>
        <td class="small muted" style="max-width:380px">${esc(x.effect || '')}</td>
        <td class="r">${x.active ? `<button class="btn sm" data-undo="${x.id}">Undo</button>` : (x.superseded_by ? '' : `<button class="btn sm" data-redo="${x.id}">Restore</button>`)}</td></tr>`).join('')}</tbody></table></div>`
      : empty('No feedback yet', ' Rate notifications, save listings or reply in Discord — the app adapts automatically.')}</div>`;
  view.querySelector('#reset').onclick = async () => {
    if (!(await confirmBox('Reset all personal learning? History is kept and can be restored item by item.', 'Reset learning'))) return;
    try { const r = await post('/learning/reset'); ok(r.message); render(view); } catch (e) { fail(e); }
  };
  view.querySelectorAll('[data-undo]').forEach((b) => (b.onclick = async () => { try { const r = await post('/learning/undo/' + b.dataset.undo); ok(r.message); render(view); } catch (e) { fail(e); } }));
  view.querySelectorAll('[data-redo]').forEach((b) => (b.onclick = async () => { try { await post('/learning/redo/' + b.dataset.redo); ok('Restored'); render(view); } catch (e) { fail(e); } }));
}
