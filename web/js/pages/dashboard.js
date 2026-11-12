import { get, esc, eur, ago, dealItem, empty, barChart, catName, dt, n0 } from '../core.js';

const getDash = () => { try { return localStorage.getItem('ssd-dash') || 'overview'; } catch (e) { return 'overview'; } };
const setDash = (v) => { try { localStorage.setItem('ssd-dash', v); } catch (e) { /* ignore */ } };

export async function render(view) {
  const d = await get('/dashboard');
  const t = d.totals, s = d.status, sc = s.scanner;
  const warm = !sc.warmup_complete;
  d.per_day.forEach((x) => { x.rest = Math.max(0, x.n - (x.good || 0) - (x.interesting || 0)); });
  const mode = getDash();
  view.innerHTML = `
  <div class="page-head"><div><h1>Dashboard</h1>
    <p>${warm ? 'Warm-up in progress: the app is reading recent listings to learn market prices. Notifications start when it finishes.' : `SS.lv is checked by periodic polling (not real-time) — last successful scan ${ago(sc.last_success)}.`}</p></div>
    <div class="row"><div class="seg adv-only" id="dmode" role="group" aria-label="Dashboard layout">${[['overview', 'Overview'], ['deals', 'Deals'], ['analytics', 'Analytics']].map(([k, t]) => `<button type="button" data-d="${k}" class="${mode === k ? 'on' : ''}">${t}</button>`).join('')}</div>
      <a class="btn" href="#/listings?classification=GOOD_DEAL,INTERESTING">All open opportunities</a></div></div>
  <div class="dash" data-dash="${mode}">
  <div class="figures adv-only" data-sec="figures">
    <div class="figure"><div class="v">${n0(t.active)}</div><div class="l">Listings monitored</div></div>
    <div class="figure"><div class="v">${n0(t.new_today)}</div><div class="l">New today</div></div>
    <div class="figure good"><div class="v">${n0(t.good_active)}</div><div class="l">Good deals open</div></div>
    <div class="figure warn"><div class="v">${n0(t.interesting_active)}</div><div class="l">Interesting open</div></div>
    <div class="figure"><div class="v">${n0(t.price_drops_24h)}</div><div class="l">Price drops, 24 h</div></div>
    <div class="figure"><div class="v">${n0(t.products_tracked)}</div><div class="l">Products priced</div></div>
    <div class="figure"><div class="v">${eur(t.estimated_profit)}</div><div class="l">Expected profit, ${t.active_plans} plans</div></div>
    <div class="figure"><div class="v">${eur(t.actual_profit)}</div><div class="l">Actual profit</div></div>
  </div>

  <div class="grid g3" data-sec="best">
    <div class="card span2"><div class="card-head"><h2>Best current deals</h2><span class="hint" style="margin-left:8px">Sorted by estimated profit</span><a href="#/listings?classification=GOOD_DEAL&sort=profit">See all</a></div>
      ${d.best.length ? `<div class="deal-list">${d.best.map((l) => dealItem(l, { ruler: true, flip: true })).join('')}</div>` : empty('No good deals open right now', warm ? ' They will appear after the warm-up.' : ' New ones are checked for every few minutes.')}</div>
    <div class="card adv-only"><div class="card-head"><h2>Scanner</h2><a href="#/system">Details</a></div>
      <dl class="kv">
        <dt>State</dt><dd>${esc(s.phase)}</dd>
        <dt>Mode</dt><dd>${esc(sc.mode)}</dd>
        <dt>Last success</dt><dd>${sc.last_success ? dt(sc.last_success) : 'none yet'}</dd>
        <dt>Feeds</dt><dd>${sc.enabled_feeds} enabled, ${sc.priority_feeds} fast</dd>
        <dt>Requests, 1 h</dt><dd>${n0(sc.requests_last_hour)}</dd>
        <dt>SS.lv access</dt><dd>${s.fetcher.cooldown_seconds ? `<span class="error-text">pausing: ${esc(s.fetcher.blocked_reason)}</span>` : `robots.txt ${esc(s.fetcher.robots)}`}</dd>
        <dt>Discord</dt><dd>${esc(s.discord.status)}</dd>
      </dl>
      ${d.errors.length ? `<hr class="sep"><h3>Recent errors</h3><ul class="timeline">${d.errors.map((e) => `<li class="small">${dt(e.at)} — ${esc(e.message.slice(0, 140))}</li>`).join('')}</ul>` : ''}
    </div>
  </div>

  <div class="grid g3" data-sec="lists">
    <div class="card"><div class="card-head"><h2>Interesting</h2><a href="#/listings?classification=INTERESTING">See all</a></div>
      ${d.interesting.length ? `<div class="deal-list">${d.interesting.map((l) => dealItem(l, { flip: true })).join('')}</div>` : empty('Nothing flagged yet')}</div>
    <div class="card"><div class="card-head"><h2>Recent price drops</h2><a href="#/listings?sort=drop">See all</a></div>
      ${d.drops.length ? `<div class="deal-list">${d.drops.map((l) => dealItem(l, { flip: true })).join('')}</div>` : empty('No price drops yet', ' Drops are detected when a listing is seen again at a lower price.')}</div>
    <div class="card"><div class="card-head"><h2>Saved</h2><a href="#/listings?saved=1&status=all">See all</a></div>
      ${d.saved.length ? `<div class="deal-list">${d.saved.map((l) => dealItem(l, { flip: true })).join('')}</div>` : empty('Nothing saved', ' Use Save on a listing or in Discord to keep it here.')}</div>
  </div>

  <div class="grid g2 adv-only" data-sec="charts">
    <div class="card"><h2>New listings per day</h2>
      ${barChart(d.per_day, { width: 560, height: 180, keys: [['good', 'b2'], ['interesting', 'b3'], ['rest', 'b1']], labels: (x) => x.day.slice(5) })}
      <div class="legend"><span><i style="background:var(--chart-2,var(--good))"></i>Good deals</span><span><i style="background:var(--chart-3,var(--warn))"></i>Interesting</span><span><i style="background:var(--chart-1,var(--accent))"></i>Other</span></div></div>
    <div class="card"><h2>Where the opportunities are</h2>
      <div class="table-wrap"><table class="data"><thead><tr><th>Category</th><th class="r">Active</th><th class="r">Good</th><th class="r">Interesting</th></tr></thead>
      <tbody>${d.categories.map((c) => `<tr class="clickable" onclick="location.hash='#/listings?category=${c.category_key}'"><td>${esc(catName(c.category_key))}</td><td class="r num">${c.n}</td><td class="r num">${c.good || 0}</td><td class="r num">${c.interesting || 0}</td></tr>`).join('') || '<tr><td colspan=4 class="muted">No data yet</td></tr>'}</tbody></table></div></div>
  </div>

  <div class="grid g2" data-sec="market">
    <div class="card"><div class="card-head"><h2>Market overview</h2><a href="#/market">All products</a></div>
      <div class="table-wrap"><table class="data"><thead><tr><th>Product</th><th class="r">Typical</th><th class="r">Comparables</th><th class="r">Confidence</th></tr></thead>
      <tbody>${d.market.map((m) => `<tr class="clickable" onclick="location.hash='#/market?key=${encodeURIComponent(m.product_key)}'"><td>${esc(m.product_name)}</td><td class="r num">${eur(m.typical)}</td><td class="r num">${m.n}</td><td class="r num">${Math.round(m.confidence * 100)}%</td></tr>`).join('') || '<tr><td colspan=4 class="muted">Prices appear once enough comparable listings are seen.</td></tr>'}</tbody></table></div>
      <p class="hint">Estimates are based on asking prices unless you record confirmed sales.</p></div>
    <div class="card"><div class="card-head"><h2>Recent purchases</h2><a href="#/roi">ROI planner</a></div>
      ${d.purchases.length ? `<div class="table-wrap"><table class="data"><thead><tr><th>Item</th><th>Status</th><th class="r">Paid</th><th class="r">Profit</th></tr></thead><tbody>
      ${d.purchases.map((p) => `<tr><td>${esc(p.title)}</td><td>${esc(p.status)}</td><td class="r num">${eur(p.actual_purchase ?? p.purchase_price)}</td><td class="r num">${p.actual_profit != null ? eur(p.actual_profit) : eur(p.profit) + ' est.'}</td></tr>`).join('')}</tbody></table></div>` : empty('No purchases recorded', ' Mark a listing as Bought to track it here.')}</div>
  </div></div>`;
  view.querySelectorAll('#dmode [data-d]').forEach((b) => (b.onclick = () => {
    setDash(b.dataset.d); view.querySelector('.dash').dataset.dash = b.dataset.d;
    view.querySelectorAll('#dmode [data-d]').forEach((x) => x.classList.toggle('on', x === b));
  }));
}
