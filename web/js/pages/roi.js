import { get, post, put, del, esc, eur, dt, empty, ok, fail, confirmBox, modal } from '../core.js';

const STATUS = { planned: 'Planned', bought: 'Bought', sold: 'Sold', skipped: 'Skipped' };

// same maths as the server (_plan_calc) so the form updates instantly
export function calc(p) {
  const g = (k) => Number(p[k]) || 0;
  const invest = g('purchase_price') + g('repair_cost') + g('transport_cost') + g('accessories_cost') + g('other_costs');
  const fp = g('platform_fees');
  const fee = (s) => fp <= 30 ? s * fp / 100 : fp;
  const resale = g('resale_price'), low = Number(p.resale_low) || resale * 0.85, high = Number(p.resale_high) || resale * 1.1;
  const profit = resale - fee(resale) - invest;
  return { invest, profit, roi: invest ? profit / invest * 100 : 0, breakeven: fp <= 30 ? invest / (1 - fp / 100) : invest + fp,
    best: high - fee(high) - invest, worst: low * 0.9 - fee(low * 0.9) - invest - g('repair_cost') * 0.5 };
}

export async function render(view, params) {
  const [plans, acc] = await Promise.all([get('/roi'), get('/roi/accuracy')]);
  const selected = new Set();
  view.innerHTML = `
  <div class="page-head"><div><h1>ROI planner</h1><p>Plan purchases for resale, then record what really happened. Real outcomes feed back into future resale estimates.</p></div>
    <div class="row"><button class="btn" id="cmp" disabled>Compare selected</button><button class="btn primary" id="new">New plan</button></div></div>
  ${acc._all ? `<div class="card" style="margin-bottom:14px"><h2>Your estimate accuracy</h2><p>Across ${acc._all.n} sold items you sold at ${Math.round(acc._all.raw_median * 100)}% of the predicted resale price (median). New imports are adjusted by ${Math.round(acc._all.ratio * 100)}%.</p>
    <div class="row">${Object.entries(acc).filter(([k]) => k !== '_all').map(([k, v]) => `<span class="tag">${esc(k)}: ${Math.round(v.raw_median * 100)}% (${v.n})</span>`).join('')}</div></div>` : ''}
  <div class="card" style="padding:0">${plans.length ? `<div class="table-wrap"><table class="data"><thead><tr><th></th><th>Plan</th><th>Status</th><th class="r">Investment</th><th class="r">Resale</th><th class="r">Expected profit</th><th class="r">ROI</th><th class="r">Actual profit</th><th></th></tr></thead><tbody>
    ${plans.map((p) => `<tr><td><input type="checkbox" data-sel="${p.id}" aria-label="Select for comparison"></td>
      <td><b>${esc(p.title)}</b><div class="lsub">${p.listing_id ? `<a href="#/roi?listing=${p.listing_id}">listing #${p.listing_id}</a> · ` : ''}updated ${dt(p.updated_at)}</div></td>
      <td><span class="tag ${p.status === 'sold' ? 'good' : p.status === 'bought' ? 'accent' : ''}">${STATUS[p.status]}</span></td>
      <td class="r num">${eur(p.investment)}</td><td class="r num">${eur(p.resale_price)}</td>
      <td class="r num" style="color:${p.profit >= 0 ? 'var(--good)' : 'var(--bad)'}">${eur(p.profit)}</td><td class="r num">${p.roi}%</td>
      <td class="r num">${p.actual_profit != null ? `${eur(p.actual_profit)}<div class="lsub">${p.prediction_error >= 0 ? '+' : ''}${eur(p.prediction_error)} vs plan</div>` : '—'}</td>
      <td class="r"><button class="btn sm" data-edit="${p.id}">Open</button></td></tr>`).join('')}</tbody></table></div>`
    : empty('No plans yet', ' Open a listing and choose “Plan ROI”, or start an empty plan.', '<button class="btn primary" id="new2">New plan</button>')}</div>`;
  const open = (p) => editor(p, () => render(view, new URLSearchParams()));
  view.querySelector('#new').onclick = () => open({ status: 'planned', platform_fees: 0 });
  const n2 = view.querySelector('#new2'); if (n2) n2.onclick = () => open({ status: 'planned', platform_fees: 0 });
  view.querySelectorAll('[data-edit]').forEach((b) => (b.onclick = () => open(plans.find((p) => p.id == b.dataset.edit))));
  view.querySelectorAll('[data-sel]').forEach((c) => (c.onchange = () => { c.checked ? selected.add(Number(c.dataset.sel)) : selected.delete(Number(c.dataset.sel)); view.querySelector('#cmp').disabled = selected.size < 2; }));
  view.querySelector('#cmp').onclick = () => compare(plans.filter((p) => selected.has(p.id)));
  if (params.get('import')) {
    try { const imp = await get('/roi/import/' + params.get('import')); history.replaceState(null, '', '#/roi'); open({ ...imp, status: 'planned', platform_fees: 0, _note: imp.note }); } catch (e) { fail(e); }
  }
}

function editor(p, done) {
  const f = (k, label, extra = '') => `<label class="field">${label}<input type="number" step="0.01" min="0" name="${k}" value="${p[k] ?? ''}" ${extra}></label>`;
  modal(`<h2>${p.id ? 'Edit plan' : 'New ROI plan'}</h2>${p._note ? `<p class="hint">${esc(p._note)}</p>` : ''}
  <form id="rf" class="stack" style="gap:12px;margin-top:8px">
    <label class="field">Title<input type="text" name="title" value="${esc(p.title || '')}" required></label>
    <div class="field-row">${f('purchase_price', 'Purchase price')}${f('resale_price', 'Expected resale')}${f('resale_low', 'Resale, low')}${f('resale_high', 'Resale, high')}</div>
    <div class="field-row">${f('repair_cost', 'Repair costs')}${f('transport_cost', 'Transport')}${f('accessories_cost', 'Accessories')}${f('platform_fees', 'Fees (≤30 = % of sale, else €)')}${f('other_costs', 'Other costs')}
      <label class="field">Days to sell<input type="number" name="expected_days" min="0" value="${p.expected_days ?? ''}"></label></div>
    <div class="card" id="rcalc" style="padding:12px"></div>
    <h3>Outcome</h3>
    <div class="field-row"><label class="field">Status<select name="status">${Object.entries(STATUS).map(([k, t]) => `<option value="${k}" ${p.status === k ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
      ${f('actual_purchase', 'Actual purchase')}${f('actual_repair', 'Actual repair')}${f('actual_other', 'Actual other costs')}${f('actual_sale', 'Actual sale price')}</div>
    <label class="field">Notes<textarea name="notes">${esc(p.notes || '')}</textarea></label>
    <input type="hidden" name="listing_id" value="${p.listing_id ?? ''}"><input type="hidden" name="product_key" value="${esc(p.product_key || '')}">
    <p class="error-text" id="rerr"></p>
    <div class="row between">${p.id ? '<button type="button" class="btn danger" id="rdel">Delete plan</button>' : '<span></span>'}
      <div class="row"><button type="button" class="btn" data-close>Cancel</button><button class="btn primary">${p.id ? 'Save plan' : 'Create plan'}</button></div></div>
  </form>`, (box, close) => {
    const form = box.querySelector('#rf');
    const data = () => Object.fromEntries([...new FormData(form).entries()]);
    const upd = () => {
      const c = calc(data());
      box.querySelector('#rcalc').innerHTML = `<div class="grid g3" style="gap:8px">
        <div><div class="muted small">Total investment</div><b class="num">${eur(c.invest, 2)}</b></div>
        <div><div class="muted small">Expected profit (realistic)</div><b class="num" style="color:${c.profit >= 0 ? 'var(--good)' : 'var(--bad)'}">${eur(c.profit, 2)}</b></div>
        <div><div class="muted small">ROI</div><b class="num">${c.roi.toFixed(1)}%</b></div>
        <div><div class="muted small">Break-even sale price</div><b class="num">${eur(c.breakeven, 2)}</b></div>
        <div><div class="muted small">Best case</div><b class="num">${eur(c.best, 2)}</b></div>
        <div><div class="muted small">Worst case</div><b class="num">${eur(c.worst, 2)}</b></div></div>`;
    };
    form.addEventListener('input', upd); upd();
    form.onsubmit = async (e) => {
      e.preventDefault();
      try { if (p.id) await put('/roi/' + p.id, data()); else await post('/roi', data()); close(); ok(p.id ? 'Plan saved' : 'Plan created'); done(); } catch (err) { box.querySelector('#rerr').textContent = err.message; }
    };
    const d = box.querySelector('#rdel');
    if (d) d.onclick = async () => { if (!(await confirmBox('Delete this plan?', 'Delete'))) return; try { await del('/roi/' + p.id); ok('Plan deleted'); done(); } catch (err) { fail(err); } };
  });
}

function compare(ps) {
  const rows = [['Investment', 'investment'], ['Expected resale', 'resale_price'], ['Expected profit', 'profit'], ['ROI %', 'roi'], ['Break-even', 'breakeven'], ['Best case', 'best_profit'], ['Worst case', 'worst_profit'], ['Days to sell', 'expected_days'], ['Actual profit', 'actual_profit']];
  const best = (k) => Math.max(...ps.map((p) => Number(p[k]) || -Infinity));
  modal(`<h2>Compare plans</h2><div class="table-wrap"><table class="data"><thead><tr><th></th>${ps.map((p) => `<th class="r">${esc(p.title)}</th>`).join('')}</tr></thead><tbody>
    ${rows.map(([t, k]) => `<tr><td>${t}</td>${ps.map((p) => `<td class="r num" style="${['profit', 'roi', 'best_profit', 'worst_profit'].includes(k) && Number(p[k]) === best(k) ? 'color:var(--good);font-weight:700' : ''}">${p[k] == null ? '—' : k === 'roi' ? p[k] + '%' : k === 'expected_days' ? p[k] : eur(p[k])}</td>`).join('')}</tr>`).join('')}
  </tbody></table></div><div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-close>Close</button></div>`);
}
