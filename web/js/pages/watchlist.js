import { get, post, put, del, esc, eur, ago, empty, modal, ok, fail, confirmBox, dealItem, state, catName, formData } from '../core.js';

export async function render(view) {
  const rows = await get('/watchlist');
  view.innerHTML = `
  <div class="page-head"><div><h1>Watchlist</h1><p>Products you want to catch. Matches within budget are always treated as good deals and notified; price drops on matches notify again.</p></div>
    <button class="btn primary" id="wl-add">Add to watchlist</button></div>
  <div class="grid g2" id="wl-grid">${rows.length ? rows.map(card).join('') : `<div class="card span2">${empty('Your watchlist is empty', ' Add models like “rx 6700”, “d610” or “a7 iii” with a maximum price.', '<button class="btn primary" id="wl-add2">Add the first item</button>')}</div>`}</div>`;
  const add = () => edit(null);
  view.querySelector('#wl-add').onclick = add;
  const a2 = view.querySelector('#wl-add2'); if (a2) a2.onclick = add;
  view.querySelectorAll('[data-edit]').forEach((b) => (b.onclick = () => edit(rows.find((r) => r.id == b.dataset.edit))));
  view.querySelectorAll('[data-del]').forEach((b) => (b.onclick = async () => {
    if (!(await confirmBox('Delete this watchlist item and its match history?', 'Delete'))) return;
    try { await del('/watchlist/' + b.dataset.del); ok('Deleted'); render(view); } catch (e) { fail(e); }
  }));
  view.querySelectorAll('[data-toggle]').forEach((b) => (b.onclick = async () => {
    const w = rows.find((r) => r.id == b.dataset.toggle);
    try { await put('/watchlist/' + w.id, { ...w, active: !w.active }); render(view); } catch (e) { fail(e); }
  }));
  view.querySelectorAll('[data-matches]').forEach((b) => (b.onclick = async () => {
    const box = view.querySelector(`#m-${b.dataset.matches}`);
    if (box.innerHTML) { box.innerHTML = ''; return; }
    const ms = await get(`/watchlist/${b.dataset.matches}/matches`);
    box.innerHTML = ms.length ? `<div class="deal-list">${ms.map(dealItem).join('')}</div>` : '<p class="muted small">No matches yet.</p>';
  }));
}

function card(w) {
  return `<div class="card" style="${w.active ? '' : 'opacity:.6'}">
    <div class="card-head"><h2>${esc(w.name)}</h2><div class="row">
      <button class="btn sm" data-toggle="${w.id}">${w.active ? 'Pause' : 'Resume'}</button>
      <button class="btn sm" data-edit="${w.id}">Edit</button><button class="btn sm danger" data-del="${w.id}">Delete</button></div></div>
    <dl class="kv">
      ${w.query ? `<dt>Search words</dt><dd>${esc(w.query)}${w.exclude ? ` <span class="muted">(excluding ${esc(w.exclude)})</span>` : ''}</dd>` : ''}
      ${w.category_key ? `<dt>Category</dt><dd>${esc(catName(w.category_key))}</dd>` : ''}
      <dt>Max price</dt><dd>${w.max_price ? eur(w.max_price) : 'no limit'}</dd>
      <dt>Condition</dt><dd>${esc(w.condition || 'any')}</dd>
      <dt>Min Deal Score</dt><dd>${w.min_deal ?? 'none'}</dd>
      <dt>Matches</dt><dd>${w.matches} total, ${w.active_matches} on SS.lv now${w.best_price ? ` · cheapest ${eur(w.best_price)}` : ''}</dd>
      <dt>Added</dt><dd>${ago(w.created_at)}</dd>
    </dl>
    <button class="btn sm" style="margin-top:10px" data-matches="${w.id}">Show matches</button>
    <div id="m-${w.id}" style="margin-top:8px"></div></div>`;
}

function edit(w) {
  w = w || { condition: 'any', notify: 1, notify_drops: 1, active: 1 };
  const cats = Object.entries(state.meta?.categories || {});
  modal(`<h2>${w.id ? 'Edit watchlist item' : 'Add to watchlist'}</h2>
    <form id="wf" class="stack" style="gap:10px;margin-top:10px">
      <label class="field">Name<input type="text" name="name" value="${esc(w.name || '')}" placeholder="e.g. Sony A7 III"></label>
      <label class="field">Search words (all must appear; use | for alternatives)<input type="text" name="query" value="${esc(w.query || '')}" placeholder="a7 iii|a7iii|a7m3"></label>
      <label class="field">Exclude words<input type="text" name="exclude" value="${esc(w.exclude || '')}" placeholder="e.g. xt  battery  box"></label>
      <div class="field-row">
        <label class="field">Max price (€)<input type="number" name="max_price" value="${w.max_price ?? ''}" min="0"></label>
        <label class="field">Min Deal Score<input type="number" name="min_deal" value="${w.min_deal ?? ''}" min="0" max="100"></label>
        <label class="field">Condition<select name="condition">${[['any', 'Any'], ['working', 'Working (not broken)'], ['used', 'Used or new'], ['new', 'New only']].map(([k, t]) => `<option value="${k}" ${w.condition === k ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
        <label class="field">Category<select name="category_key"><option value="">Any</option>${cats.map(([k, c]) => `<option value="${k}" ${w.category_key === k ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</select></label>
      </div>
      <label class="check"><input type="checkbox" name="notify" ${w.notify ? 'checked' : ''}> Notify on new matches</label>
      <label class="check"><input type="checkbox" name="notify_drops" ${w.notify_drops ? 'checked' : ''}> Notify on price drops</label>
      <p class="error-text" id="werr"></p>
      <div class="row" style="justify-content:flex-end"><button type="button" class="btn" data-close>Cancel</button><button class="btn primary">${w.id ? 'Save changes' : 'Add to watchlist'}</button></div>
    </form>`, (box, close) => {
    box.querySelector('#wf').onsubmit = async (e) => {
      e.preventDefault();
      const data = formData(e.target); data.active = w.active ?? 1;
      try {
        if (w.id) await put('/watchlist/' + w.id, data); else await post('/watchlist', data);
        close(); ok(w.id ? 'Watchlist item saved' : 'Added to watchlist'); render(document.getElementById('view'));
      } catch (err) { box.querySelector('#werr').textContent = err.message; }
    };
  });
}
