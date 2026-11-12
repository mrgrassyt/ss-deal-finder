import { get, post, put, del, esc, eur, empty, modal, ok, fail, confirmBox, dealItem, catName, formData, state } from '../core.js';

export async function render(view) {
  const [rows, found] = await Promise.all([get('/wants'), get('/listings?min_personal=1&sort=personal&status=active&page_size=60')]);
  const items = found.items || [];
  view.innerHTML = `
  <div class="page-head"><div><h1>My items</h1><p>Add things you like or want. Only ads that are the same as, or similar to, these get a <b>For you</b> score — nothing else is ever scored for you.</p></div>
    <button class="btn primary" id="mi-add">Add an item</button></div>
  <div class="grid g2">
    <div class="card"><div class="card-head"><h2>What I want</h2></div>
      ${rows.length ? `<div class="deal-list">${rows.map((w) => `<div class="deal-item" style="display:block;${w.active ? '' : 'opacity:.55'}">
        <div style="min-width:0"><div class="ltitle">${esc(w.name)}</div>
          <div class="lsub">${w.max_price ? `up to ${eur(w.max_price)}` : 'any price'}${w.category_key ? ` · ${esc(catName(w.category_key))}` : ''}${w.keywords ? ` · ${esc(w.keywords)}` : ''}</div></div>
        <div class="row" style="margin-top:8px"><button class="btn sm" data-toggle="${w.id}">${w.active ? 'Pause' : 'Resume'}</button><button class="btn sm" data-edit="${w.id}">Edit</button><button class="btn sm danger" data-del="${w.id}">Delete</button></div></div>`).join('')}</div>`
        : empty('Nothing here yet', ' Type a model like “Sony A7 III” or “iPhone 13”. Add a maximum price if you have one.', '<button class="btn primary" id="mi-add2">Add the first item</button>')}
      <p class="hint" style="margin-top:10px">Same item: 85–99 · close (e.g. a mini or Pro version): 62–84 · similar (same brand and category): 52–61. Being under your price limit adds points, being well over it removes some.</p>
    </div>
    <div class="card"><div class="card-head"><h2>Ads that fit</h2><span class="muted small">${items.length} found</span></div>
      ${items.length ? `<div class="deal-list">${items.map((l) => dealItem(l, { flip: true })).join('')}</div>` : empty('No matching ads yet', rows.length ? ' The list fills in after the next re-check or scan.' : ' Add an item first.')}
    </div>
  </div>`;
  const add = () => edit(null);
  view.querySelector('#mi-add').onclick = add;
  const a2 = view.querySelector('#mi-add2'); if (a2) a2.onclick = add;
  view.querySelectorAll('[data-edit]').forEach((b) => (b.onclick = () => edit(rows.find((r) => r.id == b.dataset.edit))));
  view.querySelectorAll('[data-del]').forEach((b) => (b.onclick = async () => {
    if (!(await confirmBox('Remove this item from My items?', 'Remove'))) return;
    try { await del('/wants/' + b.dataset.del); ok('Removed'); render(view); } catch (e) { fail(e); }
  }));
  view.querySelectorAll('[data-toggle]').forEach((b) => (b.onclick = async () => {
    const w = rows.find((r) => r.id == b.dataset.toggle);
    try { await put('/wants/' + w.id, { ...w, active: !w.active }); render(view); } catch (e) { fail(e); }
  }));
  function edit(w) {
    const cats = Object.entries(state.meta?.categories || {});
    modal(`<h2>${w ? 'Edit item' : 'Add an item'}</h2>
      <form id="mi-f" class="stack">
        <label class="field">What is it?<input name="name" required value="${esc(w?.name || '')}" placeholder="e.g. Sony A7 III, iPhone 13, RX 6700"></label>
        <label class="field">Max price € (optional)<input type="number" name="max_price" min="0" value="${w?.max_price ?? ''}"></label>
        <label class="field">Category (optional, lets similar items in the same category count)<select name="category_key"><option value="">Any</option>${cats.map(([k, c]) => `<option value="${k}" ${w?.category_key === k ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</select></label>
        <label class="field">Extra words (optional)<input name="keywords" value="${esc(w?.keywords || '')}" placeholder="e.g. 128gb black"></label>
        <div class="row" style="justify-content:flex-end;margin-top:14px"><button type="button" class="btn" data-close>Cancel</button><button class="btn primary">Save</button></div>
      </form>`, (box, close) => {
      box.querySelector('#mi-f').onsubmit = async (e) => {
        e.preventDefault();
        const b = formData(e.target);
        try {
          if (w) await put('/wants/' + w.id, { ...b, active: w.active }); else await post('/wants', b);
          close(); ok('Saved. Scores update on the next re-check.'); render(view);
        } catch (er) { fail(er); }
      };
    });
  }
}
