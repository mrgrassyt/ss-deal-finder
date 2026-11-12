import { get, post, esc, eur, dt, ago, dur, ok, fail, state, n0 } from '../core.js';

export async function render(view) {
  const [s, runs, logs, errors] = await Promise.all([get('/status'), get('/runs?limit=60'), get('/logs?n=150'), get('/errors')]);
  const sc = s.scanner, f = s.fetcher;
  const feeds = (state.meta && state.meta.feeds) || {};
  view.innerHTML = `
  <div class="page-head"><div><h1>Activity &amp; logs</h1><p>What the scanner is doing. SS.lv is polled on a schedule — new ads appear within the polling interval, not instantly.</p></div>
    <div class="row">
      ${sc.paused ? '<button class="btn primary" data-sc="resume">Resume scanning</button>' : '<button class="btn" data-sc="pause">Pause scanning</button>'}
      <button class="btn" data-sc="run">Scan fast feeds now</button>
      <button class="btn" id="diag">Test SS.lv parsing</button>
      <button class="btn" id="recheck" title="Apply the current rules to every stored listing and rebuild the prices">Re-check all listings</button>
      ${f.cooldown_seconds ? '<button class="btn" data-sc="reset-cooldown">Retry now</button>' : ''}
    </div></div>
  <div class="card" id="diagout" hidden style="margin-bottom:14px"></div>
  <div class="grid g3">
    <div class="card"><h2>Scanner</h2><dl class="kv">
      <dt>Phase</dt><dd>${esc(s.phase)}</dd><dt>Now</dt><dd>${esc(sc.current || 'idle')}</dd>
      <dt>Last success</dt><dd>${sc.last_success ? dt(sc.last_success) + ' (' + ago(sc.last_success) + ')' : 'none yet'}</dd>
      <dt>Site</dt><dd>${esc(sc.base_url)}</dd><dt>Feeds</dt><dd>${sc.enabled_feeds} enabled (${sc.priority_feeds} fast)</dd>
      <dt>Requests, last hour</dt><dd>${n0(sc.requests_last_hour)}</dd><dt>Uptime</dt><dd>${dur(s.uptime)}</dd></dl></div>
    <div class="card"><h2>SS.lv access</h2><dl class="kv">
      <dt>robots.txt</dt><dd>${esc(f.robots)}</dd><dt>Requests (session)</dt><dd>${n0(f.requests)}</dd><dt>Errors (session)</dt><dd>${n0(f.errors)}</dd>
      <dt>Avg response</dt><dd>${f.avg_latency ? f.avg_latency + ' s' : '—'}</dd>
      <dt>Status</dt><dd>${f.cooldown_seconds ? `<span class="error-text">Waiting ${dur(f.cooldown_seconds)}: ${esc(f.blocked_reason)}</span>` : 'OK'}</dd>
      <dt>Last error</dt><dd>${f.last_error ? esc(f.last_error) + ' · ' + ago(f.last_error_at) : 'none'}</dd></dl>
      <p class="hint">When SS.lv answers with “too many requests”, a block or a CAPTCHA page, the scanner stops and waits longer each time. It never tries to get around protections.</p></div>
    <div class="card"><h2>Integrations</h2><dl class="kv"><dt>Discord bot</dt><dd>${esc(s.discord.status)}${s.discord.last_error ? `<div class="error-text">${esc(s.discord.last_error)}</div>` : ''}</dd>
      <dt>Phone (ntfy)</dt><dd>${s.ntfy.enabled ? 'on' : 'off'}</dd><dt>Version</dt><dd>${esc(s.version)}${s.demo ? ' (demo)' : ''}</dd></dl>
      <a class="btn sm" href="#/settings?tab=discord" style="margin-top:10px">Configure</a></div>
  </div>
  <div class="grid g2" style="margin-top:14px">
    <div class="card"><h2>Recent scan runs</h2><div class="table-wrap" style="max-height:420px;overflow-y:auto"><table class="data"><thead><tr><th>When</th><th>Job</th><th>Feed</th><th class="r">Req.</th><th class="r">New</th><th class="r">Upd.</th><th>Result</th></tr></thead><tbody>
      ${runs.map((r) => `<tr><td class="small">${dt(r.started_at)}</td><td>${esc(r.job)}</td><td class="small">${esc(r.feed_key || '—')}</td><td class="r num">${r.requests}</td><td class="r num">${r.new_count}</td><td class="r num">${r.updated_count + r.removed_count}</td>
        <td class="small">${r.ok ? '<span class="tag good">ok</span>' : r.finished_at ? `<span class="tag bad" title="${esc(r.error || '')}">error</span> ${esc((r.error || '').slice(0, 60))}` : '<span class="tag">running</span>'}</td></tr>`).join('')}</tbody></table></div></div>
    <div class="card"><div class="card-head"><h2>Live log</h2><div class="row"><select id="lvl"><option value="">All levels</option><option>WARNING</option><option>ERROR</option></select></div></div>
      <div id="logbox" style="max-height:420px;overflow-y:auto;font-family:var(--font-mono);font-size:12px">${logRows(logs)}</div>
      <p class="hint">Full logs are JSON lines in the data folder (logs/ssdeal.jsonl) — easy to feed to a local LLM. Secrets are never written.</p></div>
  </div>
  <div class="card" style="margin-top:14px"><h2>Errors</h2>${errors.length ? `<ul class="timeline">${errors.slice(0, 40).map((e) => `<li class="small">${dt(e.at)} · ${esc(e.source)} — ${esc(e.message)}</li>`).join('')}</ul>` : '<p class="muted small">No errors recorded.</p>'}</div>`;
  view.querySelectorAll('[data-sc]').forEach((b) => (b.onclick = async () => {
    try { await post('/scanner/' + b.dataset.sc, {}); ok('Done'); setTimeout(() => render(view), 600); } catch (e) { fail(e); }
  }));
  view.querySelector('#recheck').onclick = async (e) => {
    e.target.disabled = true; e.target.textContent = 'Re-checking…';
    try { const r = await post('/system/recheck', {}); ok(`Re-checked ${r.listings} listings with the current rules`); } catch (err) { fail(err); }
    e.target.disabled = false; e.target.textContent = 'Re-check all listings';
  };
  view.querySelector('#diag').onclick = async () => {
    const box = view.querySelector('#diagout');
    box.hidden = false; box.innerHTML = '<div class="loading">Fetching one list page and one ad (a few seconds — requests are paced)</div>';
    try {
      const r = await post('/diagnose', {});
      const good = r.rows > 0 && r.with_price > 0;
      box.innerHTML = `<h2>SS.lv parsing test</h2><p>${good ? '<span class="tag good">Working</span>' : '<span class="tag bad">Problem</span>'} ${esc(r.url)} — HTTP ${r.status || '—'} ${r.error ? '· ' + esc(r.error) : ''}</p>
        <dl class="kv"><dt>robots.txt</dt><dd>${esc(r.robots)}</dd><dt>Listings found</dt><dd>${r.rows ?? 0} (${r.with_price ?? 0} with a price)</dd><dt>Next page link</dt><dd>${r.has_next_page ? 'yes' : 'no'}</dd>
        <dt>RSS feed</dt><dd>${r.rss_available ? 'available (used automatically)' : 'not available — HTML list pages are used'}</dd>
        ${r.ad ? `<dt>Ad page</dt><dd>price ${eur(r.ad.price)}, ${r.ad.description_chars} characters of text, ${r.ad.photos} photos, ${Object.keys(r.ad.attrs).length} attributes ${r.ad.warnings.length ? '<span class="error-text">' + esc(r.ad.warnings.join('; ')) + '</span>' : ''}</dd>` : ''}</dl>
        ${(r.samples || []).length ? `<table class="data" style="margin-top:10px"><tbody>${r.samples.map((x) => `<tr><td>${esc(x.title)}</td><td class="r num">${x.price == null ? esc(x.price_text || x.kind) : eur(x.price)}</td></tr>`).join('')}</tbody></table>` : ''}`;
    } catch (e) { box.innerHTML = `<p class="error-text">${esc(e.message)}</p>`; }
  };
  view.querySelector('#lvl').onchange = async (e) => { view.querySelector('#logbox').innerHTML = logRows(await get('/logs?n=150&level=' + e.target.value)); };
}

function logRows(logs) {
  return logs.slice().reverse().map((l) => {
    const extra = Object.entries(l).filter(([k]) => !['ts', 'level', 'logger', 'event', 'msg'].includes(k)).map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`).join(' ');
    const col = l.level === 'ERROR' ? 'var(--bad)' : l.level === 'WARNING' ? 'var(--warn)' : 'var(--muted)';
    return `<div style="padding:2px 0;border-bottom:1px solid var(--line-soft)"><span style="color:${col}">${esc(l.ts.slice(11, 19))} ${esc(l.event)}</span> ${esc(l.msg !== l.event ? l.msg : '')} <span class="muted">${esc(extra.slice(0, 240))}</span></div>`;
  }).join('') || '<p class="muted">No log lines yet.</p>';
}
