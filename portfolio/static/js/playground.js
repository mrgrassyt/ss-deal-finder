// Built-in playground tools. Everything is computed in the browser.
(() => {
  const $ = id => document.getElementById(id);
  const money = v => (v < 0 ? '−' : '') + '€' + Math.abs(v).toLocaleString('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const pct = v => isFinite(v) ? (v * 100).toFixed(1) + '%' : 'n/a';

  // ---- flip calculator -----------------------------------------------------------------------------------------
  if ($('flip')) {
    const num = id => Math.max(0, parseFloat($(id).value) || 0);
    const calc = () => {
      const buy = num('f-buy'), sell = num('f-sell'), parts = num('f-parts'), ship = num('f-ship'), fee = Math.min(100, num('f-fee')) / 100, hours = num('f-hours');
      const feeAmt = sell * fee, spent = buy + parts + ship, profit = sell - feeAmt - spent;
      $('f-profit').textContent = money(profit);
      $('f-profit').className = 'big ' + (profit >= 0 ? 'pos' : 'neg');
      $('f-roi').textContent = spent ? pct(profit / spent) : 'n/a';
      $('f-margin').textContent = sell ? pct(profit / sell) : 'n/a';
      $('f-feeamt').textContent = money(feeAmt);
      $('f-hour').textContent = hours ? money(profit / hours) + ' / h' : 'n/a';
      $('f-even').textContent = fee < 1 ? money(spent / (1 - fee)) : 'n/a';
    };
    $('flip').addEventListener('input', calc);
    calc();
  }

  // ---- value comparison ----------------------------------------------------------------------------------------
  if ($('cmp')) {
    const rows = $('c-rows'), unit = $('c-unit');
    const add = () => {
      const tr = document.createElement('tr');
      tr.innerHTML = '<td><input placeholder="Name" aria-label="Name"></td><td><input type="number" min="0" step="0.01" placeholder="0.00" inputmode="decimal" aria-label="Price"></td>' +
        '<td><input type="number" min="0" step="any" placeholder="0" inputmode="decimal" aria-label="Amount"></td><td class="val"></td>' +
        '<td><button class="icon-btn" aria-label="Remove this row" title="Remove">×</button></td>';
      tr.querySelector('button').addEventListener('click', () => { tr.remove(); calc(); });
      rows.append(tr);
    };
    const calc = () => {
      const u = unit.value.trim() || 'unit';
      $('c-unit-h').textContent = u;
      const list = [...rows.children].map(tr => {
        const [name, price, amount] = [...tr.querySelectorAll('input')].map(i => i.value);
        const v = parseFloat(price) / parseFloat(amount);
        tr.classList.remove('best');
        tr.querySelector('.val').textContent = isFinite(v) && v > 0 ? `€${v < 1 ? v.toFixed(3) : v.toFixed(2)} / ${u}` : '';
        return { tr, name: name.trim() || 'This one', v };
      }).filter(r => isFinite(r.v) && r.v > 0).sort((a, b) => a.v - b.v);
      const verdict = $('c-verdict');
      if (list.length < 2) { verdict.textContent = 'Fill in at least two items to compare.'; return; }
      list[0].tr.classList.add('best');
      const worse = list[list.length - 1];
      verdict.textContent = `${list[0].name} gives the most for the money: ${((1 - list[0].v / worse.v) * 100).toFixed(0)}% cheaper per ${u} than ${worse.name === 'This one' ? 'the most expensive one' : worse.name}.`;
    };
    $('c-add').addEventListener('click', () => { add(); });
    $('cmp').addEventListener('input', calc);
    add(); add(); add(); calc();
  }

  // ---- grass sliders -------------------------------------------------------------------------------------------
  ['wind', 'density', 'height'].forEach(k => $('g-' + k)?.addEventListener('input', e => window.Grass?.set(k, +e.target.value)));
})();
