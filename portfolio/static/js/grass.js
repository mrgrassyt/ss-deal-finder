// The grass field: three canvases at different depths (the far and near ones are blurred in CSS, like a lens focused on the middle).
// Blades sway with a slow wind and lean away from the pointer. Stops when off-screen; one still frame when motion is reduced.
(() => {
  const canvases = [...document.querySelectorAll('canvas[data-grass]')];
  if (!canvases.length) return;
  const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const params = { wind: 1, density: 1, height: 1 };
  const LAYERS = {
    far:  { every: 4.2, w: [1.5, 3], h: [.45, .95], dpr: 1, sway: .7, tone: .45 },
    mid:  { every: 5.2, w: [3, 6.5], h: [.4, 1], dpr: 1.5, sway: 1, tone: 1 },
    near: { every: 46, w: [16, 34], h: [.6, 1.1], dpr: 1, sway: 1.3, tone: .18 },
  };
  const rnd = (a, b) => a + Math.random() * (b - a);
  const hex = c => { const m = c.trim().match(/^#([0-9a-f]{6})$/i); return m ? [0, 2, 4].map(i => parseInt(m[1].slice(i, i + 2), 16)) : [255, 138, 61]; };
  const mix = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
  const rgb = (c, a = 1) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
  let pointer = { x: -9999, y: -9999 }, fields = [];

  class Field {
    constructor(canvas) {
      this.c = canvas; this.ctx = canvas.getContext('2d'); this.L = LAYERS[canvas.dataset.grass] || LAYERS.mid;
      this.visible = true;
      new IntersectionObserver(es => { this.visible = es[0].isIntersecting; }).observe(canvas);
      this.build();
    }
    build() {
      const r = this.c.getBoundingClientRect(), dpr = Math.min(devicePixelRatio || 1, this.L.dpr);
      this.W = r.width; this.H = r.height;
      this.c.width = Math.round(r.width * dpr); this.c.height = Math.round(r.height * dpr);
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const css = getComputedStyle(document.documentElement), light = document.documentElement.dataset.theme === 'light';
      const acc = hex(css.getPropertyValue('--acc')), root = light ? [58, 84, 44] : [9, 14, 10], moss = light ? [96, 140, 66] : [52, 92, 48], tip = light ? [150, 186, 96] : [118, 160, 84];
      const bg = hex(css.getPropertyValue('--bg'));
      this.paints = [0, .12, .25, .4, .58, .8].map(warm => {
        const g = this.ctx.createLinearGradient(0, this.H, 0, 0), t = this.L.tone;
        const tone = c => mix(bg, c, t);
        g.addColorStop(0, rgb(tone(root))); g.addColorStop(.45, rgb(tone(moss))); g.addColorStop(1, rgb(tone(mix(tip, acc, warm))));
        return g;
      });
      const n = Math.round(this.W / this.L.every * params.density);
      this.blades = Array.from({ length: n }, () => ({
        x: rnd(-20, this.W + 20), w: rnd(...this.L.w), h: rnd(...this.L.h) * this.H * .96 * Math.min(1.25, params.height),
        lean: rnd(-.16, .16), phase: rnd(0, 6.28), speed: rnd(.7, 1.5), paint: Math.floor(Math.random() ** 1.7 * 6), push: 0,
      })).sort((a, b) => a.h - b.h);
    }
    draw(t) {
      const { ctx, W, H, L } = this, wind = params.wind * L.sway;
      ctx.clearRect(0, 0, W, H);
      const rect = this.c.getBoundingClientRect(), px = pointer.x - rect.left, py = pointer.y - rect.top;
      for (const b of this.blades) {
        let target = 0;
        const dx = b.x - px, dy = (H - b.h * .6) - py, d = Math.hypot(dx, dy);
        if (d < 170) target = (1 - d / 170) ** 2 * (dx < 0 ? -1 : 1) * .55;
        b.push += (target - b.push) * .08;
        const sway = Math.sin(t * b.speed + b.phase + b.x * .006) * .07 * wind + Math.sin(t * .45 + b.x * .0022) * .11 * wind;
        const bend = b.h * (b.lean + sway + b.push), tx = b.x + bend, ty = H - b.h * (1 - Math.abs(b.lean + sway + b.push) * .25);
        const cx = b.x + bend * .3, cy = H - b.h * .62;
        ctx.beginPath();
        ctx.moveTo(b.x - b.w / 2, H + 2);
        ctx.quadraticCurveTo(cx - b.w * .35, cy, tx, ty);
        ctx.quadraticCurveTo(cx + b.w * .35, cy, b.x + b.w / 2, H + 2);
        ctx.fillStyle = this.paints[b.paint];
        ctx.fill();
      }
    }
  }

  const start = () => {
    fields = canvases.map(c => new Field(c));
    let last = 0;
    const frame = now => {
      if (!document.hidden && now - last > 28) {
        last = now;
        fields.forEach(f => { if (f.visible) f.draw(now / 1000); });
      }
      if (!calm) requestAnimationFrame(frame);
    };
    if (calm) fields.forEach(f => f.draw(0)); else requestAnimationFrame(frame);
  };
  let resizeTimer;
  const rebuild = () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { fields.forEach(f => f.build()); if (calm) fields.forEach(f => f.draw(0)); }, 150); };
  addEventListener('resize', rebuild);
  document.addEventListener('themechange', rebuild);
  addEventListener('pointermove', e => { pointer = { x: e.clientX, y: e.clientY }; }, { passive: true });
  addEventListener('pointerleave', () => { pointer = { x: -9999, y: -9999 }; });
  window.Grass = { set(k, v) { params[k] = v; if (k !== 'wind') rebuild(); } };
  if (document.fonts?.ready) document.fonts.ready.then(start); else start();
})();
