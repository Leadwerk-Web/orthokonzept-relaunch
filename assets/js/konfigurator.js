/* THeynis-Konfigurator v3 (statisch, datengetrieben)
   Daten: /theynis/konfigurator/daten.json (erzeugt von _werkzeuge/konfigurator.py)
   Vorschau: SVG mit den echten Materialtexturen als Muster (Draufsicht + Seitenansicht).
   Zustand: URL-Parameter ?cfg=modell.opt.opt… und localStorage. */
(() => {
  'use strict';
  const root = document.querySelector('[data-cfg]');
  if (!root) return;
  const $ = (s, r = root) => r.querySelector(s);
  const $$ = (s, r = root) => Array.from(r.querySelectorAll(s));
  const ROOT = window.OK_BASE || '';               // Pfad-Präfix, z. B. für die öffentliche Vorschau
  const BASE = ROOT + '/theynis/konfigurator/';
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* privat */ } }
  };

  let D, state = {}, step = 0, mode = 'design';
  const svgBox = $('[data-cfg-svg]'), photo = $('[data-cfg-photo]'), body = $('[data-cfg-body]');
  const stepsEl = $('[data-cfg-steps]'), chips = $('[data-cfg-chips]'), live = $('[data-cfg-live]');
  const prevB = $('[data-cfg-prev]'), nextB = $('[data-cfg-next]'), randB = $('[data-cfg-random]');

  const model = () => D.models.find(m => m.id === state.model) || D.models[0];
  const cats = () => D.categories.filter(c => !c.models || c.models.includes(state.model));
  const steps = () => [{ id: 'model', title: 'Modell' }, ...cats().map(c => ({ id: c.id, title: c.title, cat: c })), { id: 'done', title: 'Fertig' }];
  const opt = cid => { const c = D.categories.find(x => x.id === cid); return c && (c.options.find(o => o.id === state[cid]) || c.options[0]); };

  /* ── Zustand ── */
  const defaults = () => {
    const s = { model: 'flip' };
    const pick = { riemen_flip: 'nachtblau', riemen: 'nubuk-braun', baender: 'gold', fussbett: 'marmor-blau', zwischensohle: 'orange', sohle: 'schwarz' };
    D.categories.forEach(c => { s[c.id] = (c.options.find(o => o.id === pick[c.id]) || c.options[0]).id; });
    return s;
  };
  const encode = () => [state.model, ...cats().map(c => state[c.id])].join('.');
  const decode = str => {
    const parts = (str || '').split('.');
    if (!D.models.some(m => m.id === parts[0])) return null;
    const s = { ...defaults(), model: parts[0] };
    const cs = D.categories.filter(c => !c.models || c.models.includes(parts[0]));
    cs.forEach((c, k) => { if (c.options.some(o => o.id === parts[k + 1])) s[c.id] = parts[k + 1]; });
    return s;
  };
  const persist = () => {
    const code = encode();
    store.set('theynis-cfg', code);
    const u = new URL(location.href);
    u.searchParams.set('cfg', code);
    history.replaceState(null, '', u.pathname + u.search + u.hash);
  };
  const shareUrl = () => location.origin + location.pathname + '?cfg=' + encode() + '#konfigurator';

  /* ── Vorschau (SVG) ── */
  const tex = cid => { const o = opt(cid); return o ? BASE + o.tex : ''; };
  const hex = cid => { const o = opt(cid); return o ? o.hex : '#888'; };
  const pattern = (id, cid, size, x = 0, y = 0) =>
    `<pattern id="${id}" patternUnits="userSpaceOnUse" x="${x}" y="${y}" width="${size}" height="${size}"><rect width="${size}" height="${size}" fill="${hex(cid)}"/><image href="${tex(cid)}" width="${size}" height="${size}" preserveAspectRatio="xMidYMid slice"/></pattern>`;

  const FOOT = 'M150 153C230 150 280 172 340 164C400 156 450 118 520 114C600 108 680 112 712 150C735 180 725 228 690 256C650 290 580 300 520 300C440 300 380 284 320 284C260 284 200 290 150 280C95 270 78 240 78 215C78 185 100 157 150 153Z';
  const STRAPS_TOP = {
    flip: { w: 32, paths: ['M628 160Q560 128 468 122', 'M628 160Q575 225 478 298'], thong: true },
    steg: { w: 44, paths: ['M628 160Q560 128 468 122', 'M628 160Q575 225 478 298'], thong: true, buckle: [[470, 272, 60]] },
    single: { w: 86, paths: ['M448 124C470 190 470 230 452 294'], buckle: [[455, 268, 0]] },
    double: { w: 58, paths: ['M556 112C575 180 575 240 560 300', 'M372 160C392 210 392 250 378 286'], buckle: [[562, 276, 0], [380, 264, 0]] },
    triple: { w: 46, paths: ['M598 110C612 170 612 240 598 296', 'M474 120C492 190 492 240 478 296', 'M352 162C370 210 370 250 358 285'], buckle: [[600, 274, 0], [480, 274, 0], [360, 264, 0]] }
  };
  const SIDE_STRAPS = {
    flip: { thong: 'M632 100C612 70 580 56 540 54C500 52 470 58 452 66C444 76 442 90 444 102', w: 16 },
    steg: { thong: 'M632 100C612 68 580 50 540 48C500 46 470 54 452 62C444 74 442 90 444 102', w: 24 },
    single: { arches: [[488, 70]] },
    double: { arches: [[570, 56], [400, 56]] },
    triple: { arches: [[610, 46], [490, 46], [370, 46]] }
  };

  const buckle = (x, y, rot) =>
    `<g transform="translate(${x} ${y}) rotate(${rot})"><rect x="-15" y="-11" width="30" height="22" rx="5" fill="none" stroke="url(#metal)" stroke-width="5"/><path d="M0 -9V9" stroke="url(#metal)" stroke-width="3" stroke-linecap="round"/></g>`;

  const render = () => {
    const m = state.model;
    const top = STRAPS_TOP[m], side = SIDE_STRAPS[m];
    const rid = m === 'flip' ? 'riemen_flip' : 'riemen';
    const strapTop = top.paths.map(p =>
      `<path d="${p}" stroke="#0b1a19" stroke-opacity=".32" stroke-width="${top.w + 8}" stroke-linecap="round" fill="none" filter="url(#blur)" transform="translate(5 9)"/>` +
      `<path d="${p}" stroke="url(#t-riemen)" stroke-width="${top.w}" stroke-linecap="round" fill="none"/>` +
      `<path d="${p}" stroke="url(#sheen)" stroke-width="${top.w}" stroke-linecap="round" fill="none" style="mix-blend-mode:soft-light"/>` +
      ''
    ).join('') +
      (m === 'flip' ? top.paths.map(p => `<path d="${p}" stroke="url(#t-band)" stroke-width="7" stroke-linecap="round" fill="none"/>`).join('') : '') +
      (top.thong ? `<circle cx="628" cy="160" r="${m === 'flip' ? 11 : 14}" fill="url(#t-riemen)" stroke="#0b1a19" stroke-opacity=".35" stroke-width="2"/>` : '') +
      (top.buckle || []).map(b => buckle(...b)).join('');

    const SOLE_SIDE = 'M70 164L730 164Q748 165 744 172Q740 180 724 180L86 180Q66 180 64 172Q63 164 70 164Z';
    const MID_SIDE = 'M64 151L738 151Q747 153 745 159L743 164L68 164Q61 159 64 151Z';
    const BED_SIDE = 'M60 78C70 76 90 94 140 96C200 98 260 84 320 84C390 84 450 100 520 104C580 106 610 96 645 98C690 100 725 108 742 118C749 128 747 142 738 151L64 151C57 128 56 100 60 78Z';
    let strapSide = '';
    if (side.thong) {
      strapSide = `<path d="${side.thong}" stroke="url(#t-riemen)" stroke-width="${side.w}" stroke-linecap="round" fill="none"/>` +
        (m === 'flip' ? `<path d="${side.thong}" stroke="url(#t-band)" stroke-width="5" stroke-linecap="round" fill="none"/>` : '') +
        `<rect x="626" y="92" width="10" height="14" rx="3" fill="url(#t-riemen)"/>`;
    } else {
      strapSide = side.arches.map(([cx, w]) => {
        const l = cx - w - 26, r = cx + w + 26;
        const d = `M${l} 108C${l + 4} 18 ${r - 4} 18 ${r} 108L${r - 28} 108C${r - 30} 52 ${l + 30} 52 ${l + 28} 108Z`;
        return `<path d="${d}" fill="url(#t-riemen)" stroke="#0b1a19" stroke-opacity=".25" stroke-width="1.5"/><path d="${d}" fill="url(#sheenV)" style="mix-blend-mode:soft-light"/>` +
          `<g transform="translate(${r - 16} 86)"><rect x="-9" y="-12" width="18" height="24" rx="4" fill="none" stroke="url(#metal)" stroke-width="4"/></g>`;
      }).join('');
    }
    const label = (x1, y1, x2, y2, t) =>
      `<path d="M${x1} ${y1}L${x2} ${y2}H${x2 + 14}" stroke="#566967" stroke-width="1.2" fill="none"/><circle cx="${x1}" cy="${y1}" r="3.5" fill="#00857e"/><text x="${x2 + 20}" y="${y2 + 4}" font-size="15" font-family="Rubik, sans-serif" fill="#243634">${t}</text>`;

    svgBox.innerHTML = `<svg viewBox="0 0 800 600" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
<defs>
${pattern('t-riemen', rid, 140)}${m === 'flip' ? pattern('t-band', 'baender', 90) : ''}${pattern('t-fussbett', 'fussbett', 820, 20, -260)}${pattern('t-zwischen', 'zwischensohle', 180)}${pattern('t-sohle', 'sohle', 160)}
<linearGradient id="metal" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f4f4f2"/><stop offset=".45" stop-color="#9aa0a3"/><stop offset=".7" stop-color="#e6e7e8"/><stop offset="1" stop-color="#6d7275"/></linearGradient>
<linearGradient id="sheen" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".55"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".45"/></linearGradient>
<linearGradient id="sheenV" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".5"/><stop offset="1" stop-color="#000" stop-opacity=".35"/></linearGradient>
<radialGradient id="bedShade" cx="55%" cy="45%" r="65%"><stop offset="0" stop-color="#fff" stop-opacity=".22"/><stop offset=".7" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".28"/></radialGradient>
<linearGradient id="sideShade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".35"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".3"/></linearGradient>
<filter id="blur" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="6"/></filter>
<filter id="soft" x="-20%" y="-20%" width="140%" height="160%"><feGaussianBlur stdDeviation="14"/></filter>
</defs>
<g class="cfg-top" transform="translate(-6 -4) rotate(-9 400 220)">
  <ellipse cx="410" cy="330" rx="330" ry="36" fill="#0b1a19" opacity=".2" filter="url(#soft)"/>
  <path d="${FOOT}" fill="url(#t-sohle)" stroke="url(#t-sohle)" stroke-width="16" stroke-linejoin="round" transform="translate(0 25)"/>
  <path d="${FOOT}" fill="#000" fill-opacity=".25" stroke="#000" stroke-opacity=".25" stroke-width="16" stroke-linejoin="round" transform="translate(0 25)"/>
  <path d="${FOOT}" fill="url(#t-zwischen)" stroke="url(#t-zwischen)" stroke-width="16" stroke-linejoin="round" transform="translate(0 20)"/>
  <path d="${FOOT}" fill="url(#t-fussbett)" stroke="url(#t-fussbett)" stroke-width="16" stroke-linejoin="round" transform="translate(0 15)"/>
  <path d="${FOOT}" fill="url(#t-fussbett)" stroke="url(#t-fussbett)" stroke-width="16" stroke-linejoin="round" transform="translate(0 8)"/>
  <path d="${FOOT}" fill="#000" fill-opacity=".2" stroke="#000" stroke-opacity=".2" stroke-width="16" stroke-linejoin="round" transform="translate(0 12)"/>
  <path d="${FOOT}" fill="url(#t-fussbett)" stroke="url(#t-fussbett)" stroke-width="14" stroke-linejoin="round"/>
  <path d="${FOOT}" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="3" stroke-linejoin="round" style="mix-blend-mode:soft-light"/>
  <path d="${FOOT}" fill="url(#t-fussbett)"/>
  <path d="${FOOT}" fill="url(#bedShade)"/>
  <path d="M175 215C230 205 300 225 360 218" stroke="#000" stroke-opacity=".08" stroke-width="30" stroke-linecap="round" fill="none" filter="url(#blur)"/>
  <path d="M560 150C590 175 600 215 585 255" stroke="#fff" stroke-opacity=".12" stroke-width="16" stroke-linecap="round" fill="none" filter="url(#blur)"/>
  <path d="${FOOT}" fill="none" stroke="#000" stroke-opacity=".25" stroke-width="1.5"/>
  ${strapTop}
</g>
<g class="cfg-side" transform="translate(40 392) scale(.84)">
  <ellipse cx="400" cy="184" rx="360" ry="10" fill="#0b1a19" opacity=".22" filter="url(#blur)"/>
  <path d="${SOLE_SIDE}" fill="url(#t-sohle)"/>
  <path d="M92 178H718" stroke="#000" stroke-opacity=".35" stroke-width="3" stroke-dasharray="12 9"/>
  <path d="${SOLE_SIDE}" fill="url(#sideShade)" style="mix-blend-mode:soft-light"/>
  <path d="${MID_SIDE}" fill="url(#t-zwischen)"/>
  <path d="${MID_SIDE}" fill="url(#sideShade)" style="mix-blend-mode:soft-light"/>
  <path d="${BED_SIDE}" fill="url(#t-fussbett)"/>
  <path d="${BED_SIDE}" fill="url(#sideShade)" style="mix-blend-mode:soft-light"/>
  <path d="${BED_SIDE}" fill="none" stroke="#000" stroke-opacity=".2" stroke-width="1.2"/>
  ${strapSide}
</g>
<g class="cfg-labels" transform="translate(40 392) scale(.84)">
  ${label(700, 126, 790, 104, 'Fußbett')}${label(712, 157, 790, 140, 'Zwischensohle')}${label(690, 173, 790, 176, 'Laufsohle')}
</g>
<text x="24" y="580" font-size="13" font-family="Rubik, sans-serif" fill="#566967" letter-spacing="1.5">DRAUFSICHT  ·  SEITENANSICHT</text>
<text x="776" y="580" font-size="13" font-family="Rubik, sans-serif" fill="#00857e" text-anchor="end" font-weight="600">THeynis ${esc(model().name)}</text>
</svg>`;
    photo.src = BASE + model().photo;
    photo.alt = 'THeynis ' + model().name + ' (Beispielfoto)';
  };

  /* ── Chips ── */
  const renderChips = () => {
    chips.innerHTML = `<li><i style="background-image:url(${BASE + model().thumb});background-color:#f3f3f1"></i><span>Modell</span> <b>${esc(model().name)}</b></li>` +
      cats().map(c => { const o = opt(c.id); return `<li><i style="background-image:url(${BASE + o.thumb})"></i><span>${esc(c.title)}</span> <b>${esc(o.name)}</b></li>`; }).join('');
  };

  /* ── Schritte ── */
  const renderSteps = () => {
    const ss = steps();
    stepsEl.innerHTML = ss.map((s, k) => `<li><button type="button" data-step="${k}"${k === step ? ' aria-current="step"' : ''} class="${k < step ? 'is-done' : ''}">${esc(s.title)}</button></li>`).join('');
    $$('[data-step]', stepsEl).forEach(b => b.addEventListener('click', () => go(+b.dataset.step)));
    // nur die Schrittleiste horizontal verschieben, nie die Seite
    const cur = $('[aria-current="step"]', stepsEl);
    if (cur) {
      const dx = cur.getBoundingClientRect().left - stepsEl.getBoundingClientRect().left;
      stepsEl.scrollTo({ left: Math.max(0, stepsEl.scrollLeft + dx - (stepsEl.clientWidth - cur.offsetWidth) / 2), behavior: 'smooth' });
    }
  };

  const renderBody = () => {
    const s = steps()[step];
    prevB.hidden = step === 0;
    nextB.hidden = s.id === 'done';
    randB.hidden = s.id === 'done';
    if (s.id === 'model') {
      body.innerHTML = `<fieldset class="cfg__step"><legend>Welches Modell soll es sein?</legend><p class="cfg__hint">Fünf Modelle, alle nach deinem 3D-Scan gefertigt.</p>
        <div class="mdl-grid">${D.models.map(m => `<label class="mdl"><input type="radio" name="model" value="${m.id}"${m.id === state.model ? ' checked' : ''}><span class="mdl__box"><img src="${BASE + m.thumb}" alt="" width="240" height="180" loading="lazy"><b>${esc(m.name)}</b><span>${esc(m.desc)}</span></span></label>`).join('')}</div></fieldset>`;
    } else if (s.id === 'done') {
      body.innerHTML = `<div class="cfg__step"><h3 class="cfg__step-h">Dein THeynis ${esc(model().name)}</h3><p class="cfg__hint">Bring deine Auswahl zur Beratung mit oder schick sie uns vorab. Die Maße nehmen wir im Geschäft per 3D-Scan.</p>
        <ul class="cfg__sum"><li><i style="background-image:url(${BASE + model().thumb});background-color:#f3f3f1"></i><div><small>Modell</small><b>${esc(model().name)}</b></div><button type="button" data-jump="0">ändern</button></li>
        ${cats().map((c, k) => { const o = opt(c.id); return `<li><i style="background-image:url(${BASE + o.thumb})"></i><div><small>${esc(c.title)}</small><b>${esc(o.name)}</b></div><button type="button" data-jump="${k + 1}">ändern</button></li>`; }).join('')}</ul>
        <div class="cfg__done">
          <a class="btn btn--primary btn--lg" href="${requestHref()}"><span>Konfiguration anfragen</span><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg></a>
          <a class="btn btn--ghost" href="tel:+497211208575"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z"/></svg><span>Termin für den 3D-Scan: 0721 1208575</span></a>
          <button type="button" class="btn btn--ghost" data-copy><span>Link zur Konfiguration kopieren</span></button>
          <p class="cfg__copied" aria-live="polite" data-copied></p>
        </div></div>`;
      $$('[data-jump]', body).forEach(b => b.addEventListener('click', () => go(+b.dataset.jump)));
      const cp = $('[data-copy]', body);
      cp.addEventListener('click', async () => {
        const out = $('[data-copied]', body);
        try { await navigator.clipboard.writeText(shareUrl()); out.textContent = 'Link kopiert. Du kannst ihn teilen oder später wieder öffnen.'; }
        catch (e) { out.textContent = shareUrl(); }
      });
    } else {
      const c = s.cat;
      const o = opt(c.id);
      body.innerHTML = `<fieldset class="cfg__step"><legend>${esc(c.title)}</legend><p class="cfg__hint">${esc(c.hint)}</p>
        <p class="cfg__current">Gewählt: <b data-cur>${esc(o.name)}</b> · ${c.options.length} Varianten</p>
        <div class="sw-grid">${c.options.map(x => `<label class="sw" title="${esc(x.name)}"><input type="radio" name="${c.id}" value="${x.id}"${x.id === o.id ? ' checked' : ''}><span class="sw__img" style="background-image:url(${BASE + x.thumb})"></span><span class="sw__name">${esc(x.name)}</span></label>`).join('')}</div></fieldset>`;
    }
    $$('input[type=radio]', body).forEach(inp => inp.addEventListener('change', onPick));
  };

  const onPick = e => {
    const { name, value } = e.target;
    state[name] = value;
    if (name === 'model') {
      live.textContent = 'Modell ' + model().name + ' gewählt';
    } else {
      const o = opt(name);
      const cur = $('[data-cur]', body);
      if (cur) cur.textContent = o.name;
      const c = D.categories.find(x => x.id === name);
      live.textContent = c.title + ': ' + o.name;
    }
    render(); renderChips(); persist();
    if (name === 'model') renderSteps();
  };

  const go = n => {
    const ss = steps();
    step = Math.max(0, Math.min(ss.length - 1, n));
    renderSteps(); renderBody();
    const first = $('input:checked, input, a, button', body);
    if (first && document.activeElement && root.contains(document.activeElement)) first.focus({ preventScroll: true });
    if (innerWidth < 1061) {
      const panel = $('.cfg__panel');
      const r = panel.getBoundingClientRect();
      if (r.top < 0 || r.top > innerHeight * .6) scrollTo({ top: scrollY + r.top - 140, behavior: 'smooth' });
    }
  };

  const requestHref = () => {
    const lines = ['Hallo orthoKonzept-Team,', '', 'ich interessiere mich für folgende THeynis-Konfiguration:', '', 'Modell: ' + model().name]
      .concat(cats().map(c => c.title + ': ' + opt(c.id).name))
      .concat(['', 'Link: ' + shareUrl(), '', 'Bitte melden Sie sich für einen Termin zum 3D-Scan.']);
    return ROOT + '/kontakt/?betreff=' + encodeURIComponent('THeynis-Konfiguration: ' + model().name) + '&nachricht=' + encodeURIComponent(lines.join('\n'));
  };

  const randomize = () => {
    cats().forEach(c => { state[c.id] = c.options[Math.floor(Math.random() * c.options.length)].id; });
    render(); renderChips(); persist(); renderBody();
    live.textContent = 'Zufällige Kombination erstellt';
  };

  /* ── Start ── */
  fetch(root.dataset.src).then(r => r.json()).then(data => {
    D = data;
    const q = new URLSearchParams(location.search).get('cfg');
    state = decode(q) || decode(store.get('theynis-cfg')) || defaults();
    render(); renderChips(); renderSteps(); renderBody();
    if (q) setTimeout(() => document.getElementById('konfigurator').scrollIntoView({ behavior: 'smooth' }), 400);

    prevB.addEventListener('click', () => go(step - 1));
    nextB.addEventListener('click', () => go(step + 1));
    randB.addEventListener('click', randomize);
    $$('[data-cfg-mode]').forEach(b => b.addEventListener('click', () => {
      mode = b.dataset.cfgMode;
      $$('[data-cfg-mode]').forEach(x => { x.classList.toggle('is-on', x === b); x.setAttribute('aria-pressed', String(x === b)); });
      photo.hidden = mode !== 'photo';
      svgBox.hidden = mode === 'photo';
    }));
    document.querySelectorAll('[data-cfg-model]').forEach(b => b.addEventListener('click', () => {
      const id = b.dataset.cfgModel;
      if (!D.models.some(m => m.id === id)) return;
      state.model = id;
      render(); renderChips(); persist();
      go(1);
      document.getElementById('konfigurator').scrollIntoView({ behavior: 'smooth' });
    }));
    // Texturen vorladen
    const warm = () => D.categories.forEach(c => c.options.forEach(o => { const i = new Image(); i.src = BASE + o.tex; }));
    if ('requestIdleCallback' in window) requestIdleCallback(warm); else setTimeout(warm, 2000);
  }).catch(() => { body.innerHTML = '<p class="cfg__loading">Der Konfigurator konnte nicht geladen werden. Ruf uns gern an: 0721 1208575.</p>'; });
})();
