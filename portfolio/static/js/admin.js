// mrgrass.me dashboard. The forms are built from the schema the server sends (app/schema.py), so new fields appear here by themselves.
(() => {
  const app = document.getElementById('app');
  const el = (tag, props = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === 'class') n.className = v; else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else if (k === 'data') Object.assign(n.dataset, v); else if (v !== false && v != null) n[k] = v;
    }
    n.append(...kids.flat(Infinity).filter(k => k != null && k !== false));
    return n;
  };
  const toast = (text, bad) => { const t = el('div', { class: 'toast' + (bad ? ' bad' : ''), textContent: text }); document.getElementById('toasts').append(t); setTimeout(() => t.remove(), bad ? 6000 : 2600); };
  const api = async (path, opts = {}) => {
    const res = await fetch('/admin/api/' + path, {
      method: opts.method || 'GET', credentials: 'same-origin',
      headers: opts.raw ? { 'X-MG': '1' } : { 'Content-Type': 'application/json', 'X-MG': '1' },
      body: opts.raw || (opts.body ? JSON.stringify(opts.body) : undefined),
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 && path !== 'login') { me = null; login(); throw new Error('signed out'); }
    return { ok: res.ok, status: res.status, ...(Array.isArray(data) ? { list: data } : data) };
  };
  const fmtDate = ts => new Date(ts * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  const today = () => new Date().toISOString().slice(0, 10);
  let me = null, dirty = false, booted = false;
  const leaveOk = () => !dirty || confirm('You have changes that are not saved. Leave anyway?');
  addEventListener('beforeunload', e => { if (dirty) e.preventDefault(); });

  // ---- sign in ------------------------------------------------------------------------------------------------
  function login(message) {
    const pw = el('input', { type: 'password', id: 'pw', autocomplete: 'current-password', required: true });
    const err = el('span', { class: 'err', textContent: message || '' });
    const btn = el('button', { class: 'btn', type: 'submit', textContent: 'Sign in' });
    app.replaceChildren(el('div', { class: 'login' }, el('form', {
      class: 'glass', onsubmit: async e => {
        e.preventDefault(); btn.classList.add('loading');
        const r = await api('login', { method: 'POST', body: { password: pw.value } }).catch(() => ({ error: 'The server did not answer. Try again.' }));
        btn.classList.remove('loading');
        if (r.ok) return boot();
        err.textContent = r.error || 'Could not sign in.'; pw.select();
      },
    }, el('h1', { textContent: 'Dashboard' }), el('p', { textContent: 'Sign in to manage mrgrass.me.' }),
    el('div', { class: 'field' }, el('label', { htmlFor: 'pw', textContent: 'Password' }), pw, err), btn)));
    pw.focus();
  }

  async function boot() {
    try { const r = await api('me'); if (!r.ok) return; me = r; } catch (e) { return; }
    if (!booted) { booted = true; addEventListener('hashchange', route); }
    lastHash = location.hash; route();
  }

  // ---- layout and routing -------------------------------------------------------------------------------------
  const CONTENT = [['Work', ['project', 'post', 'experiment', 'gear', 'photo']], ['Selling', ['listing', 'product']], ['Extras', ['now', 'roadmap', 'toy']]];
  let lastHash = '';
  function route() {
    if (location.hash !== lastHash && !leaveOk()) { history.replaceState(null, '', lastHash || '#/'); return; }
    dirty = false; lastHash = location.hash;
    const [, a, b] = location.hash.split('/');
    const link = (hash, label, badge) => el('a', { href: '#/' + hash, class: (a || '') === hash.split('/')[0] ? 'on' : '' }, label,
      badge != null ? el('i', { class: badge.hot ? 'hot' : '', textContent: badge.n }) : null);
    const nav = el('nav', { class: 'side-nav' },
      el('a', { class: 'brand', href: '/', textContent: 'mrgrass.me', title: 'Open the site' }),
      link('', 'Overview'),
      CONTENT.map(([title, types]) => [el('h6', { textContent: title }), types.map(t => link(t, me.types[t].label, { n: me.counts[t] }))]),
      el('h6', { textContent: 'Site' }),
      link('message', 'Messages', me.unread ? { n: me.unread, hot: true } : { n: me.counts.message }), link('settings', 'Settings'), link('account', 'Password'),
      el('div', { class: 'bottom' }, el('a', { href: '/', target: '_blank', textContent: 'View the site' }),
        el('button', { textContent: 'Sign out', onclick: async () => { if (leaveOk()) { dirty = false; await api('logout', { method: 'POST' }); me = null; login(); } } })));
    const view = el('main', { class: 'view' });
    app.replaceChildren(el('div', { class: 'shell' }, nav, view));
    if (!a) overview(view);
    else if (a === 'settings') settingsView(view);
    else if (a === 'account') accountView(view);
    else if (a === 'message') messagesView(view);
    else if (me.types[a] && b) formView(view, a, b);
    else if (me.types[a]) listView(view, a);
    else overview(view);
    scrollTo(0, 0);
  }
  const refreshMe = async () => { const r = await api('me'); if (r.ok) me = r; };

  // ---- overview -----------------------------------------------------------------------------------------------
  function overview(view) {
    view.append(el('div', { class: 'view-head' }, el('h1', { textContent: 'Overview' })));
    if (me.default_password) view.append(el('div', { class: 'note' }, el('b', { textContent: 'Set your own password' }),
      'You are still using the password that was set on the server. ', el('a', { class: 'link', href: '#/account', textContent: 'Change it now' }), '.'));
    if (me.unread) view.append(el('div', { class: 'note' }, el('b', { textContent: `${me.unread} new message${me.unread === 1 ? '' : 's'}` }),
      el('a', { class: 'link', href: '#/message', textContent: 'Read them' })));
    view.append(el('div', { class: 'tiles' }, CONTENT.flatMap(c => c[1]).map(t => el('div', { class: 'tile' },
      el('b', { textContent: me.counts[t] }), el('span', { textContent: me.types[t].label }),
      el('div', { class: 'row' }, el('a', { class: 'btn small', href: `#/${t}/new`, textContent: 'Add' }), el('a', { class: 'btn ghost small', href: '#/' + t, textContent: 'Manage' }))))));
  }

  // ---- lists --------------------------------------------------------------------------------------------------
  const titleOf = (t, item) => item[me.types[t].title] || 'Untitled';
  const thumbOf = item => { for (const v of Object.values(item)) { if (v && v.thumb) return v.thumb; if (Array.isArray(v) && v[0] && v[0].thumb) return v[0].thumb; } return null; };
  async function listView(view, t) {
    const T = me.types[t];
    const search = el('input', { class: 'input', type: 'search', placeholder: 'Filter this list', style: 'max-width:240px;border-radius:99px;padding:8px 14px' });
    const head = el('div', { class: 'view-head' }, el('h1', { textContent: T.label }), search);
    if (t === 'photo') {
      const pick = el('input', { type: 'file', accept: 'image/*', multiple: true, hidden: true, onchange: () => bulkPhotos([...pick.files], view, t) });
      head.append(pick, el('button', { class: 'btn', textContent: 'Upload photos', onclick: () => pick.click() }), el('a', { class: 'btn ghost', href: `#/${t}/new`, textContent: 'Add one with details' }));
    } else head.append(el('a', { class: 'btn', href: `#/${t}/new`, textContent: `Add ${/^[aeiou]/.test(T.one) ? 'an' : 'a'} ${T.one}` }));
    const box = el('div', { class: 'table' }, el('p', { class: 'boot', style: 'padding:30px', textContent: 'Loading…' }));
    view.append(head, box);
    const r = await api('items?type=' + t);
    const items = r.list || [];
    const draw = () => {
      const q = search.value.toLowerCase();
      const rows = items.filter(i => !q || JSON.stringify(i).toLowerCase().includes(q));
      if (!items.length) return box.replaceChildren(el('p', { style: 'padding:26px;color:var(--mut)' }, `Nothing here yet. Add your first ${T.one} with the button above.`));
      if (!rows.length) return box.replaceChildren(el('p', { style: 'padding:26px;color:var(--mut)', textContent: 'Nothing in this list matches that.' }));
      box.replaceChildren(...rows.map(item => row(t, item, items, draw)));
    };
    search.addEventListener('input', draw);
    draw();
  }
  function row(t, item, items, redraw) {
    const T = me.types[t], thumb = thumbOf(item);
    const patch = async body => {
      const r = await api('items/' + item.id, { method: 'PATCH', body });
      if (!r.ok) return toast(r.error || Object.values(r.errors || {})[0] || 'Could not save that.', true);
      Object.assign(item, r); toast('Saved'); redraw();
    };
    const ctl = el('div', { class: 'ctl' });
    for (const key of T.list) {
      const f = T.fields.find(x => x.key === key);
      if (f.kind === 'select') ctl.append(el('select', { ariaLabel: f.label, onchange: e => patch({ set: { [key]: e.target.value } }) }, f.options.map(o => el('option', { textContent: o, selected: item[key] === o }))));
      else if (f.kind === 'bool') ctl.append(el('button', { class: 'mini' + (item[key] ? ' on' : ''), textContent: item[key] ? '★ Featured' : '☆ Feature', onclick: () => patch({ set: { [key]: !item[key] } }) }));
    }
    ctl.append(
      el('button', { class: 'mini', textContent: item.published ? 'Hide' : 'Publish', title: item.published ? 'Take it off the site without deleting it' : 'Show it on the site', onclick: () => patch({ published: !item.published }) }),
      el('a', { class: 'mini', href: `#/${t}/${item.id}`, textContent: 'Edit', style: 'text-decoration:none' }),
      el('button', { class: 'mini danger', textContent: 'Delete', onclick: async () => {
        if (!confirm(`Delete “${titleOf(t, item)}”? This cannot be undone.`)) return;
        const r = await api('items/' + item.id, { method: 'DELETE' });
        if (!r.ok) return toast(r.error || 'Could not delete that.', true);
        items.splice(items.indexOf(item), 1); me.counts[t]--; toast('Deleted'); redraw();
      } }));
    const sub = [T.list.filter(k => ['text', 'date'].includes(T.fields.find(x => x.key === k).kind)).map(k => item[k]).filter(Boolean).join(', '),
      item.price != null ? `${item.price} ${item.currency || ''}` : '', 'changed ' + fmtDate(item.updated)].filter(Boolean).join(' · ');
    return el('div', { class: 'trow' },
      thumb ? el('img', { class: 'pic', src: thumb, alt: '' }) : el('span', { class: 'pic' }),
      el('div', { style: 'min-width:0' }, el('a', { class: 'name', href: `#/${t}/${item.id}` }, titleOf(t, item), item.published ? null : el('span', { class: 'draft', textContent: 'Hidden' })), el('small', { textContent: sub })),
      ctl);
  }
  async function upload(file, quality) {
    const r = await api('upload?quality=' + (quality || 'normal'), { method: 'POST', raw: file });
    if (!r.ok) throw new Error(r.error || 'The upload failed.');
    return { src: r.src, thumb: r.thumb, w: r.w, h: r.h, exif: r.exif || {} };
  }
  async function bulkPhotos(files, view, t) {
    let done = 0;
    const status = el('div', { class: 'note', textContent: `Uploading 1 of ${files.length}…` });
    view.prepend(status);
    for (const file of files) {
      status.textContent = `Uploading ${done + 1} of ${files.length}…`;
      try {
        const image = await upload(file, 'photo'), x = image.exif;
        const r = await api('items?type=' + t, { method: 'POST', body: { data: { image, title: '', camera: x.camera || '', lens: x.lens || '', settings: x.settings || '', taken: x.taken || '' }, published: true } });
        if (r.ok) done++; else toast(`${file.name}: could not be saved.`, true);
      } catch (e) { toast(`${file.name}: ${e.message}`, true); }
    }
    toast(`${done} photo${done === 1 ? '' : 's'} added`);
    await refreshMe(); route();
  }

  // ---- field widgets: each returns {node, get()} -----------------------------------------------------------------
  function widget(f, value, ctx) {
    const id = 'f-' + f.key, touch = () => { dirty = true; };
    const wrap = (...kids) => el('div', { class: 'field', oninput: e => { const x = e.currentTarget.querySelector('[data-err]'); if (x) x.textContent = ''; } }, f.kind === 'bool' ? null : el('label', { htmlFor: id, textContent: f.label + (f.required ? ' *' : '') }), kids,
      f.help ? el('span', { class: 'help', textContent: f.help }) : null, el('span', { class: 'err', data: { err: f.key } }));
    const k = f.kind;
    if (k === 'text' || k === 'url' || k === 'date' || k === 'number' || k === 'tags') {
      const input = el('input', { id, type: { url: 'url', date: 'date', number: 'number' }[k] || 'text', oninput: touch,
        value: k === 'tags' ? (value || []).join(', ') : value ?? (f.default === 'today' ? today() : f.default ?? ''), min: f.min, max: f.max, step: f.step, placeholder: k === 'url' ? 'https://' : '' });
      return { node: wrap(input), get: () => k === 'number' ? (input.value === '' ? null : +input.value) : input.value, input };
    }
    if (k === 'textarea' || k === 'list' || k === 'rows' || k === 'code') {
      const text = k === 'list' ? (value || []).join('\n') : k === 'rows' ? (value || []).map(r => r.join(' | ')).join('\n') : value || '';
      const area = el('textarea', { id, rows: f.tall ? 18 : f.rows || (k === 'textarea' ? 3 : 5), value: text, oninput: touch, class: k === 'code' ? 'mono' : '', spellcheck: k !== 'code' });
      return { node: wrap(area), get: () => area.value };
    }
    if (k === 'markdown') {
      const area = el('textarea', { id, rows: f.tall ? 20 : 7, value: value || '', oninput: touch });
      const prev = el('div', { class: 'md-prev prose', hidden: true });
      const around = (a, b = a, ph = 'text') => () => {
        const s = area.selectionStart, e = area.selectionEnd, sel = area.value.slice(s, e) || ph;
        area.setRangeText(a + sel + b, s, e, 'select'); area.focus(); touch();
      };
      const pick = el('input', { type: 'file', accept: 'image/*', hidden: true, onchange: async () => {
        try { const img = await upload(pick.files[0]); area.setRangeText(`\n![](${img.src})\n`, area.selectionStart, area.selectionEnd, 'end'); touch(); } catch (e) { toast(e.message, true); }
        pick.value = '';
      } });
      const showBtn = el('button', { type: 'button', class: 'mini', textContent: 'Preview', onclick: async () => {
        if (prev.hidden) { const r = await api('preview', { method: 'POST', body: { text: area.value } }); prev.innerHTML = r.html || ''; }
        prev.hidden = !prev.hidden; area.hidden = !prev.hidden; showBtn.textContent = prev.hidden ? 'Preview' : 'Back to editing';
      } });
      const bar = el('div', { class: 'md-bar' },
        el('button', { type: 'button', class: 'mini', textContent: 'Bold', onclick: around('**') }), el('button', { type: 'button', class: 'mini', textContent: 'Italic', onclick: around('*') }),
        el('button', { type: 'button', class: 'mini', textContent: 'Heading', onclick: around('\n## ', '\n', 'Heading') }), el('button', { type: 'button', class: 'mini', textContent: 'Link', onclick: around('[', '](https://)', 'link text') }),
        el('button', { type: 'button', class: 'mini', textContent: 'List', onclick: around('\n- ', '\n', 'item') }), el('button', { type: 'button', class: 'mini', textContent: 'Code', onclick: around('`') }),
        el('button', { type: 'button', class: 'mini', textContent: 'Image', onclick: () => pick.click() }), pick, showBtn);
      return { node: wrap(bar, area, prev), get: () => area.value };
    }
    if (k === 'select') {
      const sel = el('select', { id, onchange: touch }, f.options.map(o => el('option', { textContent: o, selected: (value ?? f.default) === o })));
      return { node: wrap(sel), get: () => sel.value };
    }
    if (k === 'bool') {
      const box = el('input', { type: 'checkbox', id, checked: !!value, onchange: touch });
      return { node: wrap(el('label', { class: 'switch' }, box, f.label)), get: () => box.checked };
    }
    if (k === 'image' || k === 'images') {
      let list = k === 'image' ? (value ? [value] : []) : [...(value || [])];
      const multi = k === 'images';
      const drop = el('div', { class: 'drop' });
      const pick = el('input', { type: 'file', accept: 'image/*', multiple: multi, hidden: true, onchange: () => add([...pick.files]) });
      const draw = () => {
        drop.replaceChildren(...list.map((img, i) => el('div', { class: 'upl' }, el('img', { src: img.thumb, alt: '' }), el('div', { class: 'ctl' },
          multi && i > 0 ? el('button', { type: 'button', class: 'mini', textContent: '‹', title: 'Move earlier', onclick: () => { list.splice(i - 1, 0, list.splice(i, 1)[0]); touch(); draw(); } }) : null,
          multi && i < list.length - 1 ? el('button', { type: 'button', class: 'mini', textContent: '›', title: 'Move later', onclick: () => { list.splice(i + 1, 0, list.splice(i, 1)[0]); touch(); draw(); } }) : null,
          el('button', { type: 'button', class: 'mini danger', textContent: 'Remove', onclick: () => { list.splice(i, 1); touch(); draw(); } })))),
        el('button', { type: 'button', class: 'btn ghost small', textContent: list.length && !multi ? 'Replace' : multi ? 'Add photos' : 'Choose an image', onclick: () => pick.click() }),
        el('span', { class: 'ph-text', textContent: multi ? 'or drop files here. The first one is the main picture.' : 'or drop a file here' }), pick);
      };
      const add = async files => {
        for (const file of files.filter(x => x.type.startsWith('image/'))) {
          drop.classList.add('over');
          try {
            const img = await upload(file, f.quality);
            list = multi ? [...list, img] : [img]; touch();
            if (ctx?.onExif && f.key === 'image') ctx.onExif(img.exif);
          } catch (e) { toast(`${file.name}: ${e.message}`, true); }
          drop.classList.remove('over'); draw();
        }
      };
      drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('over'); });
      drop.addEventListener('dragleave', () => drop.classList.remove('over'));
      drop.addEventListener('drop', e => { e.preventDefault(); add([...e.dataTransfer.files]); });
      draw();
      return { node: wrap(drop), get: () => multi ? list : list[0] || null };
    }
    return { node: el('div'), get: () => value };
  }
  const showErrors = (form, errors) => {
    form.querySelectorAll('[data-err]').forEach(n => { n.textContent = errors[n.dataset.err] || ''; });
    const first = form.querySelector(`#f-${Object.keys(errors)[0]}`);
    first?.scrollIntoView({ block: 'center', behavior: 'smooth' }); first?.focus?.();
    toast('Check the marked fields.', true);
  };

  // ---- add / edit ---------------------------------------------------------------------------------------------
  async function formView(view, t, id) {
    const T = me.types[t], isNew = id === 'new';
    let item = {};
    if (!isNew) {
      const r = await api('items?type=' + t);
      item = (r.list || []).find(x => String(x.id) === id);
      if (!item) return view.append(el('p', { class: 'note', textContent: 'That item no longer exists.' }), el('a', { class: 'link', href: '#/' + t, textContent: 'Back to the list' }));
    }
    const widgets = {};
    const ctx = { onExif: x => { for (const k of ['camera', 'lens', 'settings', 'taken']) { if (x[k] && widgets[k]?.input && !widgets[k].input.value) widgets[k].input.value = x[k]; } } };
    const form = el('form', { class: 'form', novalidate: true });
    T.fields.forEach(f => { widgets[f.key] = widget(f, item[f.key], ctx); form.append(widgets[f.key].node); });
    const save = async published => {
      const data = Object.fromEntries(T.fields.map(f => [f.key, widgets[f.key].get()]));
      const r = await api(isNew ? 'items?type=' + t : 'items/' + item.id, { method: isNew ? 'POST' : 'PUT', body: { data, published } });
      if (r.errors) return showErrors(form, r.errors);
      if (!r.ok) return toast(r.error || 'Could not save. Try again.', true);
      dirty = false; toast(published ? 'Saved' : 'Saved as hidden draft');
      await refreshMe(); location.hash = '#/' + t;
    };
    const url = !isNew && T.url && item.published ? T.url.replace('{slug}', item.slug) : null;
    const startHidden = isNew ? T.draft_first : !item.published;
    form.append(el('div', { class: 'actions' },
      el('button', { class: 'btn', type: 'button', textContent: startHidden ? 'Publish' : 'Save', onclick: () => save(true) }),
      el('button', { class: 'btn ghost', type: 'button', textContent: startHidden ? 'Save as draft' : 'Save and hide from the site', onclick: () => save(false) }),
      el('a', { class: 'btn ghost', href: '#/' + t, textContent: 'Cancel' }),
      url ? el('a', { class: 'link', href: url, target: '_blank', textContent: 'See it on the site' }) : null));
    view.append(el('div', { class: 'view-head' }, el('h1', { textContent: isNew ? `New ${T.one}` : titleOf(t, item) })), form);
  }

  // ---- messages -----------------------------------------------------------------------------------------------
  async function messagesView(view) {
    view.append(el('div', { class: 'view-head' }, el('h1', { textContent: 'Messages' })));
    if (!me.mail) view.append(el('p', { class: 'help', style: 'margin:-10px 0 18px;color:var(--dim)', textContent: 'Messages from the contact and inquiry forms arrive here. Email forwarding is not set up on the server, so check this page for new ones.' }));
    const r = await api('items?type=message'), list = r.list || [];
    if (!list.length) return view.append(el('p', { class: 'mut', textContent: 'No messages yet. When someone uses the contact form or asks about an item, it shows up here.' }));
    list.forEach(m => {
      const card = el('article', { class: 'msg' + (m.read ? '' : ' unread') },
        el('header', {}, el('b', { textContent: m.name }), el('a', { class: 'link', href: 'mailto:' + m.email, textContent: m.email }), el('span', { class: 'meta', textContent: fmtDate(m.created) }),
          m.about ? el('span', { class: 'tag', textContent: 'About: ' + m.about }) : null),
        el('p', { textContent: m.message }),
        el('div', { class: 'ctl' },
          el('a', { class: 'mini', style: 'text-decoration:none', href: `mailto:${m.email}?subject=${encodeURIComponent('Re: ' + (m.about || 'your message on mrgrass.me'))}`, textContent: 'Reply by email' }),
          el('button', { class: 'mini', textContent: m.read ? 'Mark as new' : 'Mark as read', onclick: async () => { await api('items/' + m.id, { method: 'PATCH', body: { set: { read: !m.read } } }); await refreshMe(); route(); } }),
          el('button', { class: 'mini danger', textContent: 'Delete', onclick: async () => { if (confirm('Delete this message?')) { await api('items/' + m.id, { method: 'DELETE' }); await refreshMe(); route(); } } })));
      view.append(card);
    });
  }

  // ---- settings and password ----------------------------------------------------------------------------------
  function settingsView(view) {
    const widgets = {}, form = el('form', { class: 'form', novalidate: true });
    me.settings_fields.forEach(f => { widgets[f.key] = widget(f, me.settings[f.key]); form.append(widgets[f.key].node); });
    form.append(el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'button', textContent: 'Save settings', onclick: async () => {
      const r = await api('settings', { method: 'PUT', body: Object.fromEntries(me.settings_fields.map(f => [f.key, widgets[f.key].get()])) });
      if (r.errors) return showErrors(form, r.errors);
      if (!r.ok) return toast(r.error || 'Could not save. Try again.', true);
      dirty = false; toast('Settings saved'); await refreshMe();
    } })));
    view.append(el('div', { class: 'view-head' }, el('h1', { textContent: 'Settings' })), form);
  }
  function accountView(view) {
    const cur = el('input', { type: 'password', id: 'f-current', autocomplete: 'current-password' }), nw = el('input', { type: 'password', id: 'f-new', autocomplete: 'new-password' });
    const form = el('form', { class: 'form', style: 'max-width:420px', onsubmit: async e => {
      e.preventDefault();
      const r = await api('password', { method: 'POST', body: { current: cur.value, new: nw.value } });
      if (r.errors) return showErrors(form, r.errors);
      if (!r.ok) return toast(r.error || 'Could not change the password.', true);
      cur.value = nw.value = ''; toast('Password changed. Other devices were signed out.'); await refreshMe();
    } },
    el('div', { class: 'field' }, el('label', { htmlFor: 'f-current', textContent: 'Current password' }), cur, el('span', { class: 'err', data: { err: 'current' } })),
    el('div', { class: 'field' }, el('label', { htmlFor: 'f-new', textContent: 'New password' }), nw, el('span', { class: 'help', textContent: 'At least 10 characters. A few random words work well.' }), el('span', { class: 'err', data: { err: 'new' } })),
    el('div', { class: 'actions' }, el('button', { class: 'btn', type: 'submit', textContent: 'Change password' })));
    view.append(el('div', { class: 'view-head' }, el('h1', { textContent: 'Password' })), form);
  }

  boot().then(() => { if (!me) login(); });
})();
