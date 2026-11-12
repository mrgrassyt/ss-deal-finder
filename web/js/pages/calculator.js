import { get, esc, eur, debounce } from '../core.js';

const n = (v) => (v === '' || v == null || isNaN(Number(v))) ? null : Number(v);
const fmt = (v, d = 2) => v == null || !isFinite(v) ? '—' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d });

const CALCS = [
  { id: 'pct', title: 'Percentage', fields: [['a', 'Value'], ['b', 'of total']],
    out: ({ a, b }) => [['Share', b ? fmt(a / b * 100) + '%' : '—'], [`${fmt(a)}% of ${fmt(b)}`, fmt(a * b / 100)], ['Change from A to B', a ? fmt((b - a) / a * 100) + '%' : '—']] },
  { id: 'profit', title: 'Profit', fields: [['buy', 'Bought for €'], ['sell', 'Sold for €'], ['costs', 'Other costs €'], ['fee', 'Fee %']],
    out: ({ buy, sell, costs, fee }) => { const p = (sell || 0) * (1 - (fee || 0) / 100) - (buy || 0) - (costs || 0); return [['Profit', eur(p, 2)], ['Margin on sale', sell ? fmt(p / sell * 100) + '%' : '—']]; } },
  { id: 'roi', title: 'ROI', fields: [['invest', 'Total invested €'], ['ret', 'Total returned €'], ['days', 'Days held']],
    out: ({ invest, ret, days }) => { const r = invest ? (ret - invest) / invest * 100 : null; return [['ROI', r == null ? '—' : fmt(r) + '%'], ['Annualised', r != null && days ? fmt((Math.pow(ret / invest, 365 / days) - 1) * 100) + '%' : '—']]; } },
  { id: 'disc', title: 'Discount', fields: [['price', 'Original price €'], ['off', 'Discount %'], ['final', 'or final price €']],
    out: ({ price, off, final }) => [['Price after discount', price && off != null ? eur(price * (1 - off / 100), 2) : '—'], ['You save', price && off != null ? eur(price * off / 100, 2) : '—'], ['Discount of final price', price && final != null ? fmt((1 - final / price) * 100) + '%' : '—']] },
  { id: 'cmp', title: 'Price comparison', fields: [['p1', 'Offer A €'], ['u1', 'A units / GB / mm'], ['p2', 'Offer B €'], ['u2', 'B units / GB / mm']],
    out: ({ p1, u1, p2, u2 }) => { const a = u1 ? p1 / u1 : null, b = u2 ? p2 / u2 : null; return [['A per unit', eur(a, 3)], ['B per unit', eur(b, 3)], ['Cheaper', a && b ? (a < b ? `A by ${fmt((1 - a / b) * 100)}%` : `B by ${fmt((1 - b / a) * 100)}%`) : '—']]; } },
  { id: 'bvs', title: 'Buy new vs sell old', fields: [['newp', 'New item price €'], ['oldv', 'Your old item sells for €'], ['buyused', 'Same new item used €'], ['fee', 'Selling fee %']],
    out: ({ newp, oldv, buyused, fee }) => { const net = (oldv || 0) * (1 - (fee || 0) / 100); return [['Upgrade cost (new)', eur((newp || 0) - net, 2)], ['Upgrade cost (used)', buyused ? eur(buyused - net, 2) : '—'], ['Saving by buying used', buyused ? eur((newp || 0) - buyused, 2) : '—']]; } },
];

export async function render(view) {
  view.innerHTML = `
  <div class="page-head"><div><h1>Calculator</h1><p>Quick maths without leaving the app. Results update as you type.</p></div></div>
  <div class="grid g3">${CALCS.map((c) => `<div class="card" data-calc="${c.id}"><h2>${c.title}</h2>
    <div class="field-row">${c.fields.map(([k, l]) => `<label class="field">${l}<input type="number" step="any" name="${k}"></label>`).join('')}</div>
    <dl class="kv" style="margin-top:12px" data-out></dl></div>`).join('')}</div>
  <div class="card" style="margin-top:14px"><div class="card-head"><h2>PC build value</h2><button class="btn sm" id="pcadd">Add component</button></div>
    <p class="hint">Type a component (e.g. “RTX 3070”, “Ryzen 5 5600X”, “DDR4 16GB”, “1TB NVMe”). The app looks up its own market estimate; you can overwrite any price.</p>
    <div class="table-wrap"><table class="data"><thead><tr><th>Component</th><th>Identified as</th><th class="r">Market estimate</th><th class="r">Price used</th><th></th></tr></thead><tbody id="pcrows"></tbody></table></div>
    <div class="row between" style="margin-top:12px"><label class="field" style="max-width:220px">Asking price of the PC €<input type="number" id="pcask"></label>
      <div id="pctot" class="num" style="font-size:16px"></div></div></div>`;
  for (const c of CALCS) {
    const card = view.querySelector(`[data-calc="${c.id}"]`);
    const upd = () => {
      const vals = {}; card.querySelectorAll('input').forEach((i) => { vals[i.name] = n(i.value); });
      card.querySelector('[data-out]').innerHTML = c.out(vals).map(([k, v]) => `<dt>${esc(k)}</dt><dd class="num"><b>${esc(v)}</b></dd>`).join('');
    };
    card.addEventListener('input', upd); upd();
  }
  const rows = view.querySelector('#pcrows');
  const total = () => {
    let sum = 0;
    rows.querySelectorAll('tr').forEach((tr) => { sum += n(tr.querySelector('.used').value) || 0; });
    const ask = n(view.querySelector('#pcask').value);
    view.querySelector('#pctot').innerHTML = `Parts total <b>${eur(sum)}</b>${ask ? ` · asking is ${ask <= sum ? `<span style="color:var(--good)">${fmt((1 - ask / sum) * 100, 0)}% below</span>` : `<span style="color:var(--bad)">${fmt((ask / sum - 1) * 100, 0)}% above</span>`} parts value` : ''}`;
  };
  const addRow = (text = '') => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><input type="text" class="comp" value="${esc(text)}" placeholder="component" style="width:100%"></td><td class="ident small muted">—</td><td class="r est num">—</td>
      <td class="r"><input type="number" class="used" style="width:100px"></td><td><button class="btn sm ghost" aria-label="Remove">✕</button></td>`;
    rows.appendChild(tr);
    const look = debounce(async () => {
      const t = tr.querySelector('.comp').value.trim(); if (!t) return;
      const r = await get('/market/lookup?text=' + encodeURIComponent(t) + '&category=pc_parts_other');
      tr.querySelector('.ident').textContent = r.match ? r.match.name : 'not recognised';
      tr.querySelector('.est').textContent = r.value ? `${eur(r.value.typical)} (${r.value.n})` : 'no data';
      const u = tr.querySelector('.used'); if (r.value && !u.dataset.manual) u.value = Math.round(r.value.typical);
      total();
    }, 400);
    tr.querySelector('.comp').addEventListener('input', look);
    tr.querySelector('.used').addEventListener('input', (e) => { e.target.dataset.manual = '1'; total(); });
    tr.querySelector('button').onclick = () => { tr.remove(); total(); };
    if (text) look();
  };
  ['', '', '', ''].forEach(() => addRow());
  view.querySelector('#pcadd').onclick = () => addRow();
  view.querySelector('#pcask').addEventListener('input', total);
  total();
}
