// Listing detail drawer: full info, both scores with reasons, market context, history and feedback.
import { get, post, esc, eur, dt, ago, ruler, scores, levelTag, condTag, flagTags, lineChart, openDrawer, closeDrawer,
  ok, fail, modal, catName, toLocalInput, state, dealItem, setUnread } from '../core.js';

let currentId = null;

export async function openListing(id) {
  currentId = id;
  openDrawer('<div class="loading">Loading listing</div>');
  // opening a listing counts as reading its notifications
  post('/notifications/read', { listing_id: id }).then((r) => { setUnread(r.unread); document.querySelectorAll(`tr.unread[data-open="${id}"]`).forEach((t) => t.classList.remove('unread')); }).catch(() => {});
  let l;
  try { l = await get('/listings/' + id); } catch (e) { openDrawer(`<p class="error-text">${esc(e.message)}</p>`); return; }
  if (currentId !== id) return;
  render(l);
}

function render(l) {
  const d = l.score_details || {}, deal = d.deal || {}, val = d.valuation || {}, pers = d.personal || {};
  const lv = { ...l, value_low: val.low, value_high: val.high, value_typical: val.typical };
  const ph = l.price_history.map((p) => [p.observed_at, p.price]);
  if (ph.length) ph.push([Date.now() / 1000, ph[ph.length - 1][1]]);
  const mh = (l.market_history || []).map((m) => [new Date(m.day).getTime() / 1000, m.typical]);
  const rep = deal.repair;
  const working = (l.market || []).find((m) => m.bucket === 'working');
  const photos = (l.photos || []).slice(0, 8);
  const fbKinds = [['interested', 'Interested'], [l.saved ? 'unsaved' : 'saved', l.saved ? 'Unsave' : 'Save'], ['ignored', 'Ignore'],
    ['too_expensive', 'Too expensive'], ['not_for_me', 'Not for me'], ['good_deal', 'Good deal']];
  const html = `
  <div class="row between" style="align-items:flex-start">
    <div style="min-width:0;flex:1">
      <div class="row" style="gap:6px;margin-bottom:6px">${levelTag(l.classification)} ${condTag(l.condition)} ${flagTags(l.flags)}
        ${l.status === 'removed' ? '<span class="tag bad">Removed from SS.lv</span>' : ''} ${l.saved ? '<span class="tag accent">Saved</span>' : ''}
        ${l.user_state ? `<span class="tag">${esc(l.user_state.replace('_', ' '))}</span>` : ''}</div>
      <h1 style="font-size:22px">${esc(l.product_name || l.title.slice(0, 90))}</h1>
      <div class="muted small" style="margin-top:4px">${esc(catName(l.category_key))} · ${esc(l.location || 'location unknown')} · first seen ${ago(l.first_seen)}${l.posted_at ? ' · posted ' + dt(l.posted_at) : ''}</div>
    </div>
    <button class="icon-btn" id="dr-close" aria-label="Close">✕</button>
  </div>

  <div class="card" style="margin-top:14px">
    <div class="row between">
      <div><div class="muted small">Asking price</div><div class="price" style="font-size:28px">${l.price == null ? esc(l.price_text || '—') : eur(l.price)}</div>
        ${l.initial_price && l.initial_price !== l.price ? `<div class="small muted">first seen at ${eur(l.initial_price)} · lowest ${eur(l.min_price)}</div>` : ''}</div>
      ${scores(l)}
    </div>
    <div style="margin-top:14px">${ruler(lv, true)}</div>
    <div class="small muted" style="margin-top:4px">${val.typical ? `Estimated market value ${eur(val.low)}–${eur(val.high)} (typical ${eur(val.typical)}), ${val.method === 'component_sum' ? 'from component prices' : (String(val.basis || '').includes('sales') ? 'asking prices plus your confirmed sales' : 'based on asking prices, not confirmed sales')} · confidence ${Math.round((deal.confidence || 0) * 100)}%` : 'No market estimate yet — the model needs more comparable listings.'}</div>
    <div class="row" style="margin-top:14px">
      <a class="btn primary" href="${esc(l.url)}" target="_blank" rel="noopener">Open on SS.lv</a>
      ${fbKinds.map(([k, t]) => `<button class="btn sm" data-act="${k}">${t}</button>`).join('')}
      <button class="btn sm" data-act="bought">Bought…</button>
    </div>
    <div class="row" style="margin-top:10px">
      <span class="small muted">Rate 1–10:</span>
      <div class="seg" id="rate">${[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((i) => `<button data-rate="${i}" class="${l.feedback.find((f) => f.kind === 'rating' && f.active)?.value === i ? 'on' : ''}">${i}</button>`).join('')}</div>
    </div>
    <form class="row" id="reply-form" style="margin-top:10px">
      <input type="text" name="text" placeholder="Or just say it: “would buy for €100”, “remind me tomorrow”, “it's worth €200”" style="flex:1">
      <button class="btn">Send</button>
    </form>
    <div id="reply-out" class="small" style="margin-top:6px"></div>
  </div>

  <div class="grid g2 adv-only" style="margin-top:14px">
    <div class="card"><h2>How the price was judged</h2>
      <ul class="reasons">${(deal.reasons || []).map((r) => `<li><span class="pts ${r.points > 0 ? 'pos' : r.points < 0 ? 'neg' : 'zero'}">${r.points > 0 ? '+' : ''}${Math.round(r.points)}</span><span>${esc(r.text)}</span></li>`).join('') || '<li class="muted" style="display:block">No reasons recorded.</li>'}</ul>
      ${(val.notes || []).filter(Boolean).map((n) => `<p class="hint">${esc(n)}</p>`).join('')}
      <p class="hint">Classification: ${esc(d.classification_reason || '—')}</p>
    </div>
    <div class="card"><h2>Why it is "for you"</h2>
      <ul class="reasons">${(pers.parts || []).map((p) => `<li><span class="pts ${p.points > 0 ? 'pos' : 'neg'}">${p.points > 0 ? '+' : ''}${Math.round(p.points)}</span><span>${esc(p.text)}</span></li>`).join('') || '<li class="muted" style="display:block">Not similar to anything in <a href="#/myitems">My items</a>, so it has no personal score.</li>'}</ul>
    </div>
  </div>

  ${rep ? `<div class="card" style="margin-top:14px"><h2>Repair and parts outlook</h2>
    <dl class="kv">
      <dt>Value when working</dt><dd>${eur(rep.working_value)}</dd>
      <dt>Likely repair cost</dt><dd>${eur(rep.repair_cost_est)}</dd>
      <dt>Chance repair succeeds</dt><dd>${Math.round(rep.success_probability * 100)}%</dd>
      <dt>Value for parts</dt><dd>${eur(rep.parts_value)} <span class="muted">(${esc(rep.parts_basis)})</span></dd>
      <dt>Expected value</dt><dd>${eur(rep.expected_value)} → expected profit <b>${eur(rep.expected_profit)}</b></dd>
      <dt>Best case / worst case</dt><dd>${eur(rep.best_case_profit)} profit / ${eur(rep.worst_case_loss)} loss</dd>
      <dt>Symptoms found</dt><dd>${esc(rep.symptoms.join(', ') || 'none named in the ad')}</dd>
      <dt>Uncertainty</dt><dd>${esc(rep.uncertainty)} — estimates use category averages</dd>
    </dl></div>` : ''}

  <div class="card" style="margin-top:14px"><h2>Listing text</h2>
    <p style="white-space:pre-wrap;max-width:75ch">${esc(l.description || l.title)}</p>
    ${Object.keys(l.attrs || {}).length ? `<dl class="kv">${Object.entries(l.attrs).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>` : ''}
    ${photos.length ? `<div class="row" style="margin-top:10px">${photos.map((p) => `<a href="${esc(p)}" target="_blank" rel="noopener"><img class="thumb" style="width:96px;height:72px" src="${esc(p)}" alt="Photo" loading="lazy" onerror="this.closest('a').textContent='Photo'"></a>`).join('')}</div>` : ''}
    <div class="row" style="margin-top:10px">
      <button class="btn sm" id="refresh">Re-check on SS.lv</button>
      <button class="btn sm" id="correct">Fix identification</button>
      ${l.product_key ? `<button class="btn sm" id="mv">Correct market value</button><a class="btn sm" href="#/market?key=${encodeURIComponent(l.product_key)}">Market page</a>` : ''}
      <button class="btn sm" id="roi">Plan ROI</button>
      <button class="btn sm" id="remind">Remind me…</button>
    </div>
  </div>

  <div class="grid g2" style="margin-top:14px">
    <div class="card"><h2>Price history</h2>${lineChart([{ points: ph, step: true }], { height: 170, width: 380 })}</div>
    <div class="card"><h2>Market trend${working ? ` · ${working.n} comparables` : ''}</h2>${lineChart([{ points: mh }], { height: 170, width: 380 })}</div>
  </div>

  <div class="grid g2" style="margin-top:14px">
    <div class="card"><h2>History</h2><ul class="timeline">${l.events.map((e) => `<li>${dt(e.at)} — ${esc(eventText(e))}</li>`).join('')}</ul>
      ${l.repost ? `<p class="hint">Repost of an earlier ad (#${l.repost.id}, ${eur(l.repost.price)}, ${esc(l.repost.status)}).</p>` : ''}</div>
    <div class="card"><h2>Your feedback</h2>${l.feedback.length ? `<ul class="timeline">${l.feedback.map((f) => `<li style="${f.active ? '' : 'opacity:.5'}">${dt(f.created_at)} — <b>${esc(f.kind.replace('_', ' '))}</b>${f.value != null ? ' ' + esc(f.kind === 'rating' ? f.value + '/10' : eur(f.value)) : ''} <span class="muted">via ${esc(f.source)}</span>${f.effect ? `<div class="hint">${esc(f.effect)}</div>` : ''}</li>`).join('')}</ul>` : '<p class="muted">No feedback yet.</p>'}</div>
  </div>
  ${(l.similar || []).length ? `<div class="card" style="margin-top:14px"><h2>Comparable listings</h2><div class="deal-list">${l.similar.map(dealItem).join('')}</div></div>` : ''}
  `;
  openDrawer(html);
  wire(l);
}

function eventText(e) {
  const d = e.data || {};
  switch (e.type) {
    case 'created': return `first seen at ${eur(d.price)}`;
    case 'price_change': return `price ${eur(d.from)} → ${eur(d.to)}`;
    case 'removed': return `removed (${d.reason || ''})`;
    case 'reappeared': return 'appeared again';
    case 'detail': return `full ad text fetched (${d.photos || 0} photos)`;
    case 'repost': return `repost of listing #${d.of} (was ${eur(d.previous_price)})`;
    case 'corrected': return 'identification corrected by you';
    default: return e.type;
  }
}

async function act(id, kind, value = null, extra = {}) {
  try {
    const r = await post(`/listings/${id}/action`, { kind, value, ...extra });
    ok(r.message);
    openListing(id);
  } catch (e) { fail(e); }
}

function wire(l) {
  const root = document.getElementById('drawer-inner');
  root.querySelector('#dr-close').onclick = closeDrawer;
  root.querySelectorAll('[data-act]').forEach((b) => (b.onclick = () => {
    if (b.dataset.act === 'bought') {
      modal(`<h2>Bought it?</h2><p class="muted">What did you pay? This creates a purchase record in the ROI planner.</p>
        <label class="field">Price paid (€)<input type="number" step="0.01" id="paid" value="${l.price ?? ''}"></label>
        <div class="row" style="justify-content:flex-end;margin-top:14px"><button class="btn" data-close>Cancel</button><button class="btn primary" id="go">Mark as bought</button></div>`,
      (box, close) => { box.querySelector('#go').onclick = () => { close(); act(l.id, 'bought', Number(box.querySelector('#paid').value) || null); }; });
      return;
    }
    act(l.id, b.dataset.act);
  }));
  root.querySelectorAll('[data-rate]').forEach((b) => (b.onclick = () => act(l.id, 'rating', Number(b.dataset.rate))));
  root.querySelector('#reply-form').onsubmit = async (e) => {
    e.preventDefault();
    const text = e.target.text.value.trim(); if (!text) return;
    try {
      const r = await post(`/listings/${l.id}/reply`, { text });
      const out = root.querySelector('#reply-out');
      out.innerHTML = r.messages.map((m) => `<div>✓ ${esc(m)}</div>`).join('') + (r.clarify ? `<div class="error-text">? ${esc(r.clarify.question)}</div>` : '');
      if (!r.clarify) setTimeout(() => openListing(l.id), 900);
    } catch (err) { fail(err); }
  };
  root.querySelector('#refresh').onclick = async () => {
    try { const r = await post(`/listings/${l.id}/refresh`); ok(r.removed ? 'The ad has been removed from SS.lv' : (r.ok ? 'Updated from SS.lv' : (r.error || 'Could not reach SS.lv'))); openListing(l.id); } catch (e) { fail(e); }
  };
  root.querySelector('#roi').onclick = () => { closeDrawer(); location.hash = '#/roi?import=' + l.id; };
  const mv = root.querySelector('#mv');
  if (mv) mv.onclick = () => modal(`<h2>Correct market value</h2>
      <p class="muted">For <b>${esc(l.product_name)}</b>. A reference counts as a few observations; an override replaces the estimate until you remove it. Your personal preferences are not affected.</p>
      <div class="field-row"><label class="field">Value (€)<input type="number" id="v" step="1"></label>
      <label class="field">Type<select id="k"><option value="reference">Reference (recommended)</option><option value="override">Override</option></select></label></div>
      <div class="row" style="justify-content:flex-end;margin-top:14px"><button class="btn" data-close>Cancel</button><button class="btn primary" id="go">Save correction</button></div>`,
  (box, close) => {
    box.querySelector('#go').onclick = async () => {
      const value = Number(box.querySelector('#v').value);
      if (!value) return;
      try { await post('/market/correction', { product_key: l.product_key, value, kind: box.querySelector('#k').value, note: `from listing ${l.id}` }); close(); ok('Market correction saved'); openListing(l.id); } catch (e) { fail(e); }
    };
  });
  root.querySelector('#remind').onclick = () => {
    const t = new Date(Date.now() + 86400000); t.setHours(10, 0, 0, 0);
    modal(`<h2>Remind me about this listing</h2>
      <label class="field">When<input type="datetime-local" id="w" value="${toLocalInput(t.getTime() / 1000)}"></label>
      <label class="field" style="margin-top:10px">Note<input type="text" id="n" placeholder="e.g. ask if the price is negotiable"></label>
      <div class="row" style="justify-content:flex-end;margin-top:14px"><button class="btn" data-close>Cancel</button><button class="btn primary" id="go">Set reminder</button></div>`,
    (box, close) => { box.querySelector('#go').onclick = () => { const at = new Date(box.querySelector('#w').value).getTime() / 1000; close(); act(l.id, 'remind', null, { at, text: box.querySelector('#n').value }); }; });
  };
  root.querySelector('#correct').onclick = () => {
    const cats = Object.entries(state.meta?.categories || {}).map(([k, c]) => `<option value="${k}" ${k === l.category_key ? 'selected' : ''}>${esc(c.name)}</option>`).join('');
    modal(`<h2>Fix identification</h2><p class="muted">Use this when the product, category or condition was detected wrongly. The listing is re-scored immediately.</p>
      <label class="field">Product key<input type="text" id="pk" value="${esc(l.product_key || '')}" placeholder="e.g. gpu:amd:rx-6700"></label>
      <label class="field" style="margin-top:8px">Product name<input type="text" id="pn" value="${esc(l.product_name || '')}"></label>
      <div class="field-row" style="margin-top:8px"><label class="field">Category<select id="ck">${cats}</select></label>
      <label class="field">Condition<select id="cd">${['new', 'used', 'untested', 'broken', 'parts'].map((c) => `<option ${c === l.condition ? 'selected' : ''}>${c}</option>`).join('')}</select></label></div>
      <div class="row" style="justify-content:flex-end;margin-top:14px"><button class="btn" data-close>Cancel</button><button class="btn primary" id="go">Save</button></div>`,
    (box, close) => {
      box.querySelector('#go').onclick = async () => {
        try {
          await post(`/listings/${l.id}/correct`, { product_key: box.querySelector('#pk').value.trim(), product_name: box.querySelector('#pn').value.trim(), category_key: box.querySelector('#ck').value, condition: box.querySelector('#cd').value });
          close(); ok('Identification updated'); openListing(l.id);
        } catch (e) { fail(e); }
      };
    });
  };
}
