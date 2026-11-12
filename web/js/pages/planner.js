import { get, post, put, del, esc, eur, dday, dt, empty, ok, fail, modal, toLocalInput, formData } from '../core.js';

export const KINDS = { task: 'Task', reminder: 'Reminder', purchase: 'Planned purchase', resale: 'Planned resale', check: 'Check listing again', follow_up: 'Follow-up' };

export async function render(view) {
  const tasks = await get('/tasks?include_done=true');
  const now = Date.now() / 1000;
  const open = tasks.filter((t) => !t.done), done = tasks.filter((t) => t.done);
  const groups = [
    ['Overdue', open.filter((t) => t.due_at && t.due_at < now)],
    ['Today and upcoming', open.filter((t) => t.due_at && t.due_at >= now)],
    ['No date', open.filter((t) => !t.due_at)],
  ];
  view.innerHTML = `
  <div class="page-head"><div><h1>Planner</h1><p>Tasks, reminders, planned purchases and resales. Reminders arrive as desktop, Discord and phone notifications.</p></div>
    <button class="btn primary" id="tnew">New task</button></div>
  <div class="grid g3">
    ${groups.map(([title, items]) => `<div class="card"><h2>${title} <span class="muted num">${items.length}</span></h2>
      ${items.length ? items.map(row).join('') : `<p class="muted small">${title === 'Overdue' ? 'Nothing overdue.' : 'Nothing here.'}</p>`}</div>`).join('')}
  </div>
  <div class="card" style="margin-top:14px"><h2>Done</h2>${done.length ? done.slice(0, 30).map(row).join('') : '<p class="muted small">Completed tasks appear here.</p>'}</div>`;
  view.querySelector('#tnew').onclick = () => editTask({}, () => render(view));
  view.querySelectorAll('[data-done]').forEach((c) => (c.onchange = async () => { await put('/tasks/' + c.dataset.done, { done: c.checked ? 1 : 0 }); render(view); }));
  view.querySelectorAll('[data-tedit]').forEach((b) => (b.onclick = () => editTask(tasks.find((t) => t.id == b.dataset.tedit), () => render(view))));
}

function row(t) {
  return `<div class="row" style="padding:8px 0;border-bottom:1px solid var(--line-soft);align-items:flex-start;flex-wrap:nowrap">
    <input type="checkbox" data-done="${t.id}" ${t.done ? 'checked' : ''} aria-label="Done" style="margin-top:3px">
    <div style="flex:1;min-width:0;${t.done ? 'text-decoration:line-through;opacity:.6' : ''}"><b>${esc(t.title)}</b>
      <div class="lsub">${KINDS[t.kind] || t.kind}${t.due_at ? ' · ' + dt(t.due_at) : ''}${t.remind_at && !t.reminded ? ' · reminder set' : ''}</div>
      ${t.listing_id ? `<div class="lsub"><a href="#/planner?listing=${t.listing_id}">${esc((t.product_name || t.listing_title || '').slice(0, 60))}</a> ${eur(t.listing_price)}</div>` : ''}
      ${t.notes ? `<div class="lsub">${esc(t.notes)}</div>` : ''}</div>
    <button class="btn sm ghost" data-tedit="${t.id}">Edit</button></div>`;
}

export function editTask(t, done) {
  modal(`<h2>${t.id ? 'Edit task' : 'New task'}</h2><form id="tf" class="stack" style="gap:10px;margin-top:10px">
    <label class="field">Title<input type="text" name="title" value="${esc(t.title || '')}" required></label>
    <div class="field-row"><label class="field">Type<select name="kind">${Object.entries(KINDS).map(([k, v]) => `<option value="${k}" ${t.kind === k ? 'selected' : ''}>${v}</option>`).join('')}</select></label>
      <label class="field">Due<input type="datetime-local" name="due_at" value="${toLocalInput(t.due_at)}"></label>
      <label class="field">Remind me at<input type="datetime-local" name="remind_at" value="${toLocalInput(t.remind_at)}"></label></div>
    <label class="field">Notes<textarea name="notes">${esc(t.notes || '')}</textarea></label>
    <p class="error-text" id="terr"></p>
    <div class="row between">${t.id ? '<button type="button" class="btn danger" id="tdel">Delete</button>' : '<span></span>'}
    <div class="row"><button type="button" class="btn" data-close>Cancel</button><button class="btn primary">${t.id ? 'Save task' : 'Create task'}</button></div></div></form>`,
  (box, close) => {
    box.querySelector('#tf').onsubmit = async (e) => {
      e.preventDefault();
      const d = formData(e.target);
      if (t.listing_id) d.listing_id = t.listing_id;
      try { if (t.id) await put('/tasks/' + t.id, d); else await post('/tasks', d); close(); ok(t.id ? 'Task saved' : 'Task created'); done(); } catch (err) { box.querySelector('#terr').textContent = err.message; }
    };
    const dl = box.querySelector('#tdel');
    if (dl) dl.onclick = async () => { try { await del('/tasks/' + t.id); close(); ok('Task deleted'); done(); } catch (err) { fail(err); } };
  });
}
