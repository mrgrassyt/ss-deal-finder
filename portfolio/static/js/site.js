// mrgrass.me — behaviour shared by every public page. No dependencies.
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const el = (tag, props = {}, ...kids) => { const n = Object.assign(document.createElement(tag), props); n.append(...kids); return n; };
  const calm = matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.dataset.motion === 'reduced' || document.documentElement.dataset.anim === 'off' || document.documentElement.dataset.perf === 'on';

  // ---- theme, menu ---------------------------------------------------------------------------------------------
  $('#theme-btn')?.addEventListener('click', () => {
    const light = document.documentElement.dataset.theme !== 'light';
    if (light) document.documentElement.dataset.theme = 'light'; else delete document.documentElement.dataset.theme;
    try { localStorage.setItem('theme', light ? 'light' : 'dark'); } catch (e) {}
    document.dispatchEvent(new Event('themechange'));
  });
  const menuBtn = $('#menu-btn');
  menuBtn?.addEventListener('click', () => {
    const open = document.body.classList.toggle('menu-open');
    menuBtn.setAttribute('aria-expanded', open);
  });

  // ---- dialogs -------------------------------------------------------------------------------------------------
  const open = id => { const d = document.getElementById(id); if (d && !d.open) { document.body.classList.remove('menu-open'); d.showModal(); d.dispatchEvent(new Event('opened')); } };
  document.addEventListener('click', e => {
    const opener = e.target.closest('[data-open]');
    if (opener) { e.preventDefault(); open(opener.dataset.open); return; }
    if (e.target instanceof HTMLDialogElement) e.target.close();            // click on the backdrop
    const copy = e.target.closest('[data-copy]');
    if (copy) {
      navigator.clipboard?.writeText(copy.dataset.copy).then(() => {
        const was = copy.textContent; copy.textContent = 'Link copied';
        setTimeout(() => { copy.textContent = was; }, 1800);
      });
    }
  });
  document.addEventListener('keydown', e => {
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || '');
    if ((e.key === '/' && !typing) || (e.key.toLowerCase() === 'k' && (e.ctrlKey || e.metaKey))) { e.preventDefault(); open('search'); }
  });

  // ---- search overlay ------------------------------------------------------------------------------------------
  const sd = $('#search');
  if (sd) {
    const input = $('input', sd), box = $('#s-results');
    let timer, sel = -1, seq = 0;
    const hint = text => box.replaceChildren(el('p', { className: 's-hint', textContent: text }));
    const mark = () => $$('a', box).forEach((a, i) => a.classList.toggle('sel', i === sel));
    sd.addEventListener('opened', () => { input.select(); });
    input.addEventListener('input', () => {
      clearTimeout(timer);
      const q = input.value.trim();
      if (!q) return hint('Type to search everything on the site.');
      hint('Searching…');
      timer = setTimeout(async () => {
        const mine = ++seq;
        try {
          const rows = await (await fetch('/api/search?q=' + encodeURIComponent(q))).json();
          if (mine !== seq) return;
          sel = -1;
          if (!rows.length) return hint(`Nothing matches “${q}”. Try a shorter or different word.`);
          box.replaceChildren(...rows.map(r => el('a', { href: r.url },
            r.thumb ? el('img', { className: 'thumb', src: r.thumb, alt: '' }) : el('span', { className: 'thumb' }),
            el('span', {}, el('b', { textContent: r.title }), el('small', { textContent: r.text })),
            el('span', { className: 'meta', textContent: r.kind }))));
        } catch (e) { hint('Search is not answering. Check your connection and try again.'); }
      }, 160);
    });
    input.addEventListener('keydown', e => {
      const links = $$('a', box);
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        sel = Math.max(-1, Math.min(links.length - 1, sel + (e.key === 'ArrowDown' ? 1 : -1)));
        mark(); links[sel]?.scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter' && sel >= 0) { e.preventDefault(); location.href = links[sel].href; }
    });
  }

  // ---- list filters (projects, lab, shop, listings, photos, devlog) --------------------------------------------
  $$('[data-filter]').forEach(bar => {
    const target = $(bar.dataset.filter);
    if (!target) return;
    const items = $$('[data-item]', target), none = target.parentElement.querySelector('[data-none]');
    const q = $('[data-q]', bar), sort = $('[data-sort]', bar), showHidden = $('[data-show-hidden]', bar), chips = $$('.chip[data-f]', bar);
    let key = '';
    const apply = () => {
      const words = (q?.value || '').toLowerCase().split(/\s+/).filter(Boolean);
      let shown = 0;
      items.forEach(it => {
        const ok = (!key || it.dataset.k === key) && words.every(w => (it.dataset.text || '').includes(w)) &&
          !(bar.dataset.hide && it.dataset.state === bar.dataset.hide && !showHidden?.checked);
        it.hidden = !ok;
        if (ok) { shown++; delete it.dataset.off; } else it.dataset.off = '1';
      });
      if (none) none.style.display = shown ? 'none' : 'block';
    };
    chips.forEach(c => c.addEventListener('click', () => {
      key = c.dataset.f;
      chips.forEach(x => x.setAttribute('aria-pressed', x === c));
      apply();
    }));
    q?.addEventListener('input', apply);
    showHidden?.addEventListener('change', apply);
    sort?.addEventListener('change', () => {
      const by = { featured: a => [-a.dataset.featured, -a.dataset.new], new: a => [-a.dataset.new], low: a => [+a.dataset.price], high: a => [-a.dataset.price] }[sort.value];
      items.sort((a, b) => { const x = by(a), y = by(b); return x[0] - y[0] || (x[1] || 0) - (y[1] || 0); }).forEach(it => target.append(it));
    });
    target.parentElement.querySelector('[data-reset]')?.addEventListener('click', () => { if (q) q.value = ''; chips[0]?.click(); apply(); });
    if (sort) sort.dispatchEvent(new Event('change'));
    apply();
  });

  // ---- lightbox: fullscreen viewer with zoom and an optional before/after slider -------------------------------
  const lb = $('#lb');
  if (lb) {
    const stage = $('#lb-stage'), bar = $('#lb-bar');
    let group = [], at = 0, lastFocus = null;
    const show = i => {
      at = (i + group.length) % group.length;
      const d = group[at].dataset;
      $$('img, .lb-cut', stage).forEach(n => n.remove());
      stage.classList.remove('zoom');
      const img = el('img', { src: d.src, alt: d.title || '' });
      stage.append(img);
      if (d.before) {
        const before = el('img', { src: d.before, alt: 'Before editing', className: 'before' });
        const cut = el('input', { type: 'range', min: 0, max: 100, value: 50, className: 'lb-cut', ariaLabel: 'Before and after' });
        cut.addEventListener('input', () => stage.style.setProperty('--cut', cut.value + '%'));
        stage.style.setProperty('--cut', '50%');
        stage.append(before, cut);
      }
      bar.replaceChildren();
      if (d.title) bar.append(el('b', { textContent: d.title }));
      if (d.text) bar.append(el('span', { textContent: d.text }));
      (d.info || '').split('|').filter(Boolean).forEach(t => bar.append(el('span', { textContent: t })));
      if (d.before) bar.append(el('span', { textContent: 'Drag the slider to compare with the unedited photo' }));
      if (group.length > 1) bar.append(el('span', { textContent: `${at + 1} of ${group.length}`, style: 'margin-left:auto' }));
      bar.style.display = bar.childNodes.length ? '' : 'none';
      $('.lb-prev', lb).hidden = $('.lb-next', lb).hidden = group.length < 2;
    };
    // A picture with data-fly flies between its place on the page and the full-screen viewer.
    const fly = (img, from, reverse) => {
      const to = img.getBoundingClientRect(), f = from.getBoundingClientRect();
      if (!to.width || !f.width) return null;
      const s = f.width / to.width, dx = f.left + f.width / 2 - (to.left + to.width / 2), dy = f.top + f.height / 2 - (to.top + to.height / 2);
      const frames = [{ transform: `translate(${dx}px, ${dy}px) scale(${s}) rotate(-3deg)`, opacity: .9 }, { transform: 'none', opacity: 1 }];
      return img.animate(reverse ? frames.reverse() : frames, { duration: reverse ? 320 : 560, easing: 'cubic-bezier(.2,.8,.2,1)', fill: 'both' });
    };
    const openLb = (name, index, origin) => {
      group = $$(`[data-lb="${name}"]`).filter(n => !n.dataset.off && !n.closest('[data-off]'));
      if (!group.length) return;
      lastFocus = document.activeElement;
      lb.classList.add('open'); document.body.style.overflow = 'hidden';
      show(index); $('.lb-close', lb).focus();
      if (!calm && origin?.hasAttribute('data-fly')) {
        lb.animate([{ background: 'rgba(6,6,7,0)' }, { background: 'rgba(6,6,7,.94)' }], { duration: 420, easing: 'ease-out' });
        const img = $('img:not(.before)', stage), thumb = $('img', origin);
        if (img && thumb) { img.style.opacity = 0; const go = () => { img.style.opacity = ''; const an = fly(img, thumb); if (an) an.onfinish = () => an.cancel(); }; img.complete ? go() : (img.onload = go, setTimeout(go, 1200)); }
      }
    };
    const closeLb = () => {
      const origin = group[at], img = $('img:not(.before)', stage), thumb = origin && $('img', origin);
      const done = () => { lb.classList.remove('open'); document.body.style.overflow = ''; lastFocus?.focus?.(); };
      if (!calm && origin?.hasAttribute('data-fly') && img && thumb && thumb.getBoundingClientRect().bottom > 0 && !stage.classList.contains('zoom')) {
        lb.animate([{ background: 'rgba(6,6,7,.94)' }, { background: 'rgba(6,6,7,0)' }], { duration: 320, fill: 'both' });
        const a = fly(img, thumb, true);
        if (a) { a.onfinish = done; return; }
      }
      done();
    };
    document.addEventListener('click', e => {
      const go = e.target.closest('[data-lb-go]');
      if (go) return openLb(go.dataset.lbGo, +(go.dataset.index || 0));
      const t = e.target.closest('[data-lb]');
      if (t && !lb.contains(t)) {
        if (t.matches('a')) e.preventDefault();               // cards on the home page: the viewer instead of the page
        const all = $$(`[data-lb="${t.dataset.lb}"]`).filter(n => !n.dataset.off);
        openLb(t.dataset.lb, all.indexOf(t), t);
      }
      const thumb = e.target.closest('[data-thumb]');
      if (thumb) {
        const main = $('#buy-main'), src = $$('[data-lb="item"]')[+thumb.dataset.thumb]?.dataset.src;
        if (main && src) { $('img', main).src = src; main.dataset.index = thumb.dataset.thumb; }
        $$('[data-thumb]').forEach(b => b.setAttribute('aria-current', b === thumb));
      }
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Enter' && document.activeElement?.matches?.('figure[data-lb]')) document.activeElement.click();
      if (!lb.classList.contains('open')) return;
      if (e.key === 'Escape') closeLb();
      if (e.key === 'ArrowRight') show(at + 1);
      if (e.key === 'ArrowLeft') show(at - 1);
    });
    $('.lb-close', lb).addEventListener('click', closeLb);
    $('.lb-prev', lb).addEventListener('click', () => show(at - 1));
    $('.lb-next', lb).addEventListener('click', () => show(at + 1));
    // zoom: click toggles, then the picture follows the pointer (or your finger)
    let downX = null;
    const pan = e => {
      const r = stage.getBoundingClientRect();
      $$('img', stage).forEach(i => { i.style.transformOrigin = `${(e.clientX - r.left) / r.width * 100}% ${(e.clientY - r.top) / r.height * 100}%`; });
    };
    stage.addEventListener('pointerdown', e => { downX = e.clientX; });
    stage.addEventListener('pointermove', e => { if (stage.classList.contains('zoom')) pan(e); });
    stage.addEventListener('pointerup', e => {
      if (e.target.closest('button, input')) return;
      const dx = e.clientX - (downX ?? e.clientX);
      if (!stage.classList.contains('zoom') && Math.abs(dx) > 60 && group.length > 1) return show(at + (dx < 0 ? 1 : -1));
      if (e.target.tagName !== 'IMG') return closeLb();
      if (Math.abs(dx) > 8) return;
      const zoom = stage.classList.toggle('zoom');
      pan(e);
      $$('img', stage).forEach(i => { i.style.transform = zoom ? 'scale(2.4)' : ''; });
    });
  }

  // ---- contact / inquiry forms ---------------------------------------------------------------------------------
  $$('form[data-inquiry]').forEach(form => {
    form.addEventListener('submit', async e => {
      e.preventDefault();
      const btn = $('button[type=submit]', form), err = k => $(`[data-err="${k}"]`, form);
      $$('[data-err]', form).forEach(n => { n.textContent = ''; });
      btn.classList.add('loading'); btn.disabled = true;
      try {
        const res = await fetch('/api/inquiry', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.fromEntries(new FormData(form))) });
        const d = await res.json();
        if (d.ok) {
          $$('.field, button[type=submit]', form).forEach(n => { n.hidden = true; });
          $('.done', form).hidden = false;
        } else if (d.errors) {
          Object.entries(d.errors).forEach(([k, v]) => { if (err(k)) err(k).textContent = v; });
          $(`[name="${Object.keys(d.errors)[0]}"]`, form)?.focus();
        } else err('form').textContent = d.error || 'The message could not be sent. Try again in a moment.';
      } catch (x) { err('form').textContent = 'The message could not be sent. Check your connection and try again.'; }
      btn.classList.remove('loading'); btn.disabled = false;
    });
  });

  // ---- project cards lean towards the pointer ------------------------------------------------------------------
  if (!calm && matchMedia('(hover: hover)').matches) {
    $$('[data-tilt]').forEach(card => {
      const pic = $('.shot, .ph', card);
      if (!pic) return;
      card.addEventListener('pointermove', e => {
        const r = pic.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
        pic.style.transform = `perspective(1100px) rotateY(${x * 5}deg) rotateX(${-y * 5}deg) scale(1.012)`;
      });
      card.addEventListener('pointerleave', () => { pic.style.transform = ''; });
    });
  }

  // ---- hero: choose the main photograph with the thumbnails at the bottom right ------------------------------------
  {
    const stage = $('[data-stage]');
    if (stage) {
      const slides = $$('.stage-slide', stage), thumbs = $$('.stage-thumbs .mini-card', stage), cap = $('.stage-cap', stage);
      const loadAll = () => slides.forEach(s => { const im = $('img', s); if (im && im.dataset.lazy) { im.src = im.dataset.lazy; delete im.dataset.lazy; } });
      const show = i => {
        loadAll();
        slides.forEach((s, j) => { const on = j === i; s.classList.toggle('on', on); s.tabIndex = on ? 0 : -1; s.setAttribute('aria-hidden', on ? 'false' : 'true'); });
        thumbs.forEach((t, j) => { t.classList.toggle('on', j === i); t.setAttribute('aria-pressed', j === i ? 'true' : 'false'); });
        if (cap) cap.textContent = slides[i].dataset.title || '';
      };
      thumbs.forEach((t, i) => { t.addEventListener('click', () => show(i)); ['pointerenter', 'focus'].forEach(ev => t.addEventListener(ev, loadAll, { once: true })); });
      addEventListener('load', () => setTimeout(loadAll, 900), { once: true });
    }
  }

  // ---- hero: the photo stack and the name tilt towards the pointer ---------------------------------------------
  if (!calm && matchMedia('(hover: hover)').matches) {
    const hero = $('.hero'), scenes = $$('[data-scene]');
    if (hero && scenes.length) {
      let raf = 0, nx = 0, ny = 0;
      const apply = () => { raf = 0; scenes.forEach(n => { n.style.setProperty('--px', nx.toFixed(3)); n.style.setProperty('--py', ny.toFixed(3)); }); };
      hero.addEventListener('pointermove', e => {
        const r = hero.getBoundingClientRect();
        nx = ((e.clientX - r.left) / r.width - .5) * 2; ny = ((e.clientY - r.top) / r.height - .5) * 2;
        raf = raf || requestAnimationFrame(apply);
      });
      hero.addEventListener('pointerleave', () => { nx = ny = 0; raf = raf || requestAnimationFrame(apply); });
    }
  }
})();
