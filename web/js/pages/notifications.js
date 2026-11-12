import { get, post, esc, dt, empty, levelTag, thumb, moneyBox, setUnread, fail } from '../core.js';

const SORTS = [['newest', 'Newest first'], ['oldest', 'Oldest first'], ['unread', 'Unread first'], ['level', 'Best level first (🚀, good, interesting)'],
  ['profit', 'Highest profit'], ['roi', 'Highest ROI %'], ['personal', 'Best match for me'], ['cheapest', 'Cheapest'], ['expensive', 'Most expensive']];
const CH = { app: 'App', desktop: 'Windows', discord: 'Discord', ntfy: 'Phone (ntfy)', telegram: 'Telegram' };
const getSort = () => { try { return localStorage.getItem('ssd-nsort') || 'newest'; } catch (e) { return 'newest'; } };

function sentTo(n) {
  const errs = n.push_errors || {};
  const ok = n.channels.map((c) => `<span class="tag ${c === 'app' ? '' : 'good'}">${esc(CH[c] || c)}</span>`).join(' ');
  const bad = Object.entries(errs).filter(([c]) => c !== 'held').map(([c, e]) => `<span class="tag bad" title="${esc(e)}">${esc(CH[c] || c)} failed</span>`).join(' ');
  const held = errs.held ? `<span class="tag warn" title="${esc(errs.held)}">${n.push_pending ? 'waiting' : 'not pushed'}</span>` : '';
  return `${ok} ${bad} ${held}`;
}

export async function render(view, params) {
  const sort = params && params.get('sort') || getSort();
  const rows = await get('/notifications?limit=200&sort=' + encodeURIComponent(sort));
  view.innerHTML = `
  <div class="page-head"><div><h1>Notifications</h1><p>Everything the app flagged and where it was sent. Opening one marks it read.</p></div>
    <div class="row"><label class="field" style="min-width:230px">Sort<select id="nsort">${SORTS.map(([k, t]) => `<option value="${k}" ${k === sort ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
    <button class="btn" id="readall">Mark all as read</button></div></div>
  <div class="card small adv-only" style="margin-bottom:12px"><b>How to read this.</b> <b>Profit</b> = estimated resale (typical asking price minus a small haircut) − what you pay − extra costs; <b>ROI</b> = profit ÷ what you pay.
    “~” and “rough guess” mean there was too little market data. <b>For you</b> is your personal rating (My items and what you liked before). 🚀 rows passed your high-ROI threshold.</div>
  <div class="card" style="padding:0">${rows.length ? `<div class="table-wrap"><table class="data ntable"><thead><tr><th></th><th>Listing</th><th class="hide-sm">Why</th><th class="hide-sm">Sent to</th><th class="r">Buy · Sell · Profit · ROI</th><th></th></tr></thead><tbody>
    ${rows.map((n) => `<tr class="clickable ${n.read ? '' : 'unread'} ${n.high_roi ? 'hiroi' : ''}" data-open="${n.listing_id}" data-nid="${n.id}">
      <td style="width:66px">${thumb(n)}</td>
      <td><div class="ltitle">${n.high_roi ? `<span class="roi-badge">🚀 ROI ${(n.flip && n.flip.roi != null) ? n.flip.roi + '%' : n.roi_est != null ? Math.round(n.roi_est) + '%' : ''}</span> ` : ''}${esc(n.product_name || n.title)}</div>
        <div class="lsub">${levelTag(n.level)} ${dt(n.created_at)}${n.status === 'removed' ? ' · removed' : ''}</div></td>
      <td class="small hide-sm" style="max-width:320px">${esc(n.reason || '')}</td>
      <td class="small hide-sm">${sentTo(n)}</td>
      <td class="r">${moneyBox(n)}</td>
      <td class="r">${n.read ? '' : `<button class="btn sm ghost" data-read="${n.id}" title="Mark as read">✓</button>`}</td></tr>`).join('')}</tbody></table></div>`
    : empty('No notifications yet', ' Good deals and interesting listings will be listed here as soon as they are found.')}</div>`;
  view.querySelector('#nsort').onchange = (e) => { try { localStorage.setItem('ssd-nsort', e.target.value); } catch (er) { /* ignore */ } render(view, new URLSearchParams()); };
  view.querySelector('#readall').onclick = async (e) => {
    const b = e.currentTarget; b.disabled = true;
    view.querySelectorAll('tr.unread').forEach((t) => t.classList.remove('unread'));      // show it at once
    view.querySelectorAll('[data-read]').forEach((x) => x.remove());
    try { setUnread((await post('/notifications/read', {})).unread); } catch (er) { fail(er); render(view, params); }
    b.disabled = false;
  };
  view.querySelectorAll('[data-read]').forEach((b) => (b.onclick = async (e) => {
    e.stopPropagation();
    const tr = b.closest('tr'); tr.classList.remove('unread'); b.remove();
    try { setUnread((await post('/notifications/read', { id: Number(b.dataset.read) })).unread); } catch (er) { fail(er); }
  }));
}
