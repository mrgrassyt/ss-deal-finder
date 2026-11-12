import { get, esc, eur } from '../core.js';
import { editTask } from './planner.js';

let cursor = new Date();

export async function render(view) {
  const y = cursor.getFullYear(), m = cursor.getMonth();
  const month = `${y}-${String(m + 1).padStart(2, '0')}`;
  const d = await get('/calendar?month=' + month);
  const byDay = {};
  const add = (ts, html) => { const k = new Date(ts * 1000).toDateString(); (byDay[k] = byDay[k] || []).push(html); };
  d.deals.forEach((x) => add(x.at, `<span class="ev ${x.level}" data-open="${x.listing_id}" title="${esc(x.title)}">${eur(x.price)} ${esc(x.product_name || x.title)}</span>`));
  d.tasks.forEach((t) => add(t.due_at, `<span class="ev task ${t.done ? 'done' : ''}" data-task="${t.id}" title="${esc(t.title)}">✓ ${esc(t.title)}</span>`));
  d.plans.forEach((p) => { if (p.bought_at) add(p.bought_at, `<span class="ev task">Bought: ${esc(p.title)}</span>`); if (p.sold_at) add(p.sold_at, `<span class="ev GOOD_DEAL">Sold: ${esc(p.title)}</span>`); });
  const first = new Date(y, m, 1), start = new Date(first); start.setDate(1 - ((first.getDay() + 6) % 7));
  const cells = [];
  for (let i = 0; i < 42; i++) {
    const day = new Date(start); day.setDate(start.getDate() + i);
    if (i >= 35 && day.getMonth() !== m) break;
    const evs = byDay[day.toDateString()] || [];
    cells.push(`<div class="day ${day.getMonth() !== m ? 'other' : ''} ${day.toDateString() === new Date().toDateString() ? 'today' : ''}" data-day="${day.getTime()}">
      <span class="dnum">${day.getDate()}</span>${evs.slice(0, 5).join('')}${evs.length > 5 ? `<span class="muted small">+${evs.length - 5} more</span>` : ''}</div>`);
  }
  view.innerHTML = `
  <div class="page-head"><div><h1>Calendar</h1><p>Deals discovered on each day, your tasks, purchases and sales. Click a deal to open it, or an empty spot to add a task.</p></div>
    <div class="row"><button class="btn" id="prev" aria-label="Previous month">‹</button><b style="min-width:150px;text-align:center" class="num">${first.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })}</b><button class="btn" id="next" aria-label="Next month">›</button><button class="btn" id="today">Today</button></div></div>
  <div class="card" style="padding:0;overflow:hidden"><div class="cal">${['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((x) => `<div class="dow">${x}</div>`).join('')}${cells.join('')}</div></div>
  <div class="legend"><span><i style="background:var(--good)"></i>Good deal found</span><span><i style="background:var(--warn)"></i>Interesting found</span><span><i style="background:var(--accent-2)"></i>Task / purchase</span></div>`;
  view.querySelector('#prev').onclick = () => { cursor = new Date(y, m - 1, 1); render(view); };
  view.querySelector('#next').onclick = () => { cursor = new Date(y, m + 1, 1); render(view); };
  view.querySelector('#today').onclick = () => { cursor = new Date(); render(view); };
  view.querySelectorAll('[data-task]').forEach((e) => (e.onclick = async (ev) => {
    ev.stopPropagation();
    const ts = await get('/tasks?include_done=true');
    editTask(ts.find((t) => t.id == e.dataset.task), () => render(view));
  }));
  view.querySelectorAll('[data-day]').forEach((c) => (c.onclick = (ev) => {
    if (ev.target.closest('.ev')) return;
    const due = new Date(Number(c.dataset.day)); due.setHours(10);
    editTask({ due_at: due.getTime() / 1000, remind_at: due.getTime() / 1000 }, () => render(view));
  }));
}
