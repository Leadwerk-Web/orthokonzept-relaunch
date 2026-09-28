/* orthoKonzept – Interaktionen. Ohne Abhängigkeiten, progressive enhancement. */
(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* privat */ } }
  };

  /* ── Header: Scrollzustand, Mega-Menü-Position, Tastatur ── */
  const hdr = $('[data-hdr]');
  const setHdrVars = () => {
    if (!hdr) return;
    const r = hdr.getBoundingClientRect();
    document.documentElement.style.setProperty('--hdr-bottom', Math.round(r.bottom) + 'px');
    document.documentElement.style.setProperty('--mnav-top', Math.round(r.bottom) + 'px');
  };
  let lastY = scrollY;
  const dock = $('.dock');
  const onScroll = () => {
    const y = scrollY;
    if (hdr) hdr.classList.toggle('is-scrolled', y > 8);
    if (dock) dock.classList.toggle('is-hidden', y > lastY + 4 && y > 400);
    if (dock && y < lastY - 4) dock.classList.remove('is-hidden');
    lastY = y;
    setHdrVars();
  };
  addEventListener('scroll', onScroll, { passive: true });
  addEventListener('resize', setHdrVars);
  onScroll();

  $$('.has-drop, .has-mega').forEach(item => {
    const link = $('.nav__link', item);
    let t;
    const open = v => { item.classList.toggle('is-open', v); link.setAttribute('aria-expanded', String(v)); if (v) setHdrVars(); };
    item.addEventListener('mouseenter', () => { clearTimeout(t); open(true); });
    item.addEventListener('mouseleave', () => { t = setTimeout(() => open(false), 120); });
    item.addEventListener('focusout', e => { if (!item.contains(e.relatedTarget)) open(false); });
    link.addEventListener('keydown', e => {
      if (e.key === 'ArrowDown' || (e.key === ' ' && !item.classList.contains('is-open'))) {
        e.preventDefault(); open(true); const f = $('.drop a, .mega a', item); if (f) f.focus();
      }
    });
    item.addEventListener('keydown', e => { if (e.key === 'Escape') { open(false); link.focus(); } });
  });

  const burger = $('[data-burger]');
  const mnav = $('#mnav');
  if (burger && mnav) {
    const toggle = v => {
      burger.setAttribute('aria-expanded', String(v));
      burger.setAttribute('aria-label', v ? 'Menü schließen' : 'Menü öffnen');
      mnav.hidden = !v;
      document.body.style.overflow = v ? 'hidden' : '';
      setHdrVars();
    };
    burger.addEventListener('click', () => toggle(burger.getAttribute('aria-expanded') !== 'true'));
    addEventListener('keydown', e => { if (e.key === 'Escape' && !mnav.hidden) { toggle(false); burger.focus(); } });
    matchMedia('(min-width: 1061px)').addEventListener('change', e => { if (e.matches) toggle(false); });
  }

  /* ── Hero-Slider ── */
  $$('[data-slider]').forEach(sl => {
    const slides = $$('.hero__slide', sl);
    if (slides.length < 2) return;
    const root = sl.closest('section');
    const dots = $$('.hero__dot', root);
    const pause = $('[data-pause]', root);
    let i = 0, timer = null, paused = reduce;
    const show = n => {
      i = (n + slides.length) % slides.length;
      slides.forEach((s, k) => s.classList.toggle('is-on', k === i));
      dots.forEach((d, k) => { d.classList.toggle('is-on', k === i); d.setAttribute('aria-current', k === i ? 'true' : 'false'); });
      const img = $('img', slides[i]);
      if (img && img.loading === 'lazy') img.loading = 'eager';
    };
    const play = () => { stop(); if (!paused) timer = setInterval(() => show(i + 1), 6500); };
    const stop = () => clearInterval(timer);
    dots.forEach((d, k) => d.addEventListener('click', () => { show(k); play(); }));
    if (pause) {
      const upd = () => { pause.classList.toggle('is-paused', paused); pause.setAttribute('aria-label', paused ? 'Animation starten' : 'Animation pausieren'); };
      pause.addEventListener('click', () => { paused = !paused; upd(); paused ? stop() : play(); });
      upd();
    }
    document.addEventListener('visibilitychange', () => document.hidden ? stop() : play());
    // Folgebilder nach dem Laden vorwärmen
    addEventListener('load', () => setTimeout(() => slides.forEach(s => { const im = $('img', s); if (im) im.loading = 'eager'; }), 1200));
    play();
  });

  /* ── Einblenden beim Scrollen ── */
  const rev = $$('.reveal');
  if ('IntersectionObserver' in window && !reduce) {
    const io = new IntersectionObserver(es => es.forEach(e => {
      if (e.isIntersecting) { e.target.classList.add('is-in'); io.unobserve(e.target); }
    }), { rootMargin: '0px 0px -8% 0px', threshold: 0.06 });
    rev.forEach((el, k) => {
      const sib = el.parentElement ? Array.from(el.parentElement.children).filter(c => c.classList.contains('reveal')) : [];
      const idx = sib.indexOf(el);
      if (idx > 0) el.style.transitionDelay = Math.min(idx, 6) * 70 + 'ms';
      io.observe(el);
    });
  } else rev.forEach(el => el.classList.add('is-in'));

  /* ── Öffnungsstatus (Mo–Fr 9–13, 14–18, Europe/Berlin) ── */
  const openState = () => {
    const f = new Intl.DateTimeFormat('de-DE', { timeZone: 'Europe/Berlin', weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false });
    const parts = Object.fromEntries(f.formatToParts(new Date()).map(p => [p.type, p.value]));
    const wd = parts.weekday.replace('.', '');
    const m = parseInt(parts.hour, 10) * 60 + parseInt(parts.minute, 10);
    const work = ['Mo', 'Di', 'Mi', 'Do', 'Fr'].includes(wd);
    const open = work && ((m >= 540 && m < 780) || (m >= 840 && m < 1080));
    let txt;
    if (open) txt = m < 780 ? 'Jetzt geöffnet, bis 13 Uhr' : 'Jetzt geöffnet, bis 18 Uhr';
    else if (work && m >= 780 && m < 840) txt = 'Mittagspause, ab 14 Uhr wieder da';
    else if (work && m < 540) txt = 'Geschlossen, öffnet um 9 Uhr';
    else txt = wd === 'Fr' || wd === 'Sa' || wd === 'So' ? 'Geschlossen, öffnet Montag um 9 Uhr' : 'Geschlossen, öffnet morgen um 9 Uhr';
    return { open, txt };
  };
  const st = openState();
  $$('[data-open-badge]').forEach(el => { el.textContent = st.txt; el.classList.add(st.open ? 'is-open' : 'is-closed'); });
  $$('[data-open-status] span').forEach(el => { el.textContent = st.txt; el.classList.add(st.open ? 'is-open' : 'is-closed'); });

  /* ── Lightbox ── */
  const lb = $('[data-lightbox]');
  if (lb && typeof lb.showModal === 'function') {
    const img = document.createElement('img');
    img.alt = '';
    $('[data-lb-prev]', lb).after(img);
    let group = [], idx = 0;
    const show = n => {
      idx = (n + group.length) % group.length;
      const b = group[idx];
      img.src = b.dataset.full;
      const i = $('img', b);
      img.alt = i ? i.alt : '';
      $$('.lightbox__nav', lb).forEach(x => x.hidden = group.length < 2);
    };
    document.addEventListener('click', e => {
      const b = e.target.closest('.gal__btn');
      if (!b) return;
      group = $$('.gal__btn', b.closest('.gal') || document);
      show(group.indexOf(b));
      lb.showModal();
    });
    $('[data-lb-close]', lb).addEventListener('click', () => lb.close());
    $('[data-lb-prev]', lb).addEventListener('click', () => show(idx - 1));
    $('[data-lb-next]', lb).addEventListener('click', () => show(idx + 1));
    lb.addEventListener('click', e => { if (e.target === lb) lb.close(); });
    lb.addEventListener('keydown', e => { if (e.key === 'ArrowLeft') show(idx - 1); if (e.key === 'ArrowRight') show(idx + 1); });
    let sx = null;
    lb.addEventListener('touchstart', e => { sx = e.touches[0].clientX; }, { passive: true });
    lb.addEventListener('touchend', e => { if (sx === null) return; const dx = e.changedTouches[0].clientX - sx; if (Math.abs(dx) > 50) show(idx + (dx < 0 ? 1 : -1)); sx = null; });
  }

  /* ── YouTube erst nach Klick (Datenschutz) ── */
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-yt]');
    if (!b) return;
    const f = document.createElement('iframe');
    f.src = 'https://www.youtube-nocookie.com/embed/' + b.dataset.yt + '?autoplay=1&rel=0';
    f.allow = 'accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture; fullscreen';
    f.allowFullscreen = true;
    f.title = 'YouTube-Video';
    b.replaceWith(f);
  });

  /* ── Film (Begrüßungsseite): eigener Start-Knopf, Kinomodus im Querformat auf dem Handy,
        am Ende der Weg zur Vorschau ── */
  $$('[data-film]').forEach(fig => {
    const v = $('video', fig);
    const frame = $('.film__frame', fig);
    const play = $('[data-film-play]', fig);
    if (!v || !frame || !play) return;
    v.controls = false;
    const phone = matchMedia('(pointer: coarse) and (max-width: 600px), (pointer: coarse) and (max-height: 500px)');
    const portrait = matchMedia('(orientation: portrait)');
    let cinema = false, fsOn = false, turnT = 0;

    // Handy: Film füllt den Bildschirm im Querformat. Android bekommt echtes Vollbild und dreht selbst,
    // das iPhone erlaubt Webseiten beides nicht, dort legt CSS den Film quer (auch bei Hochformatsperre).
    const openCinema = () => {
      if (cinema || !phone.matches) return;
      cinema = true;
      fig.classList.add('is-cinema');
      document.documentElement.classList.add('film-open');
      if (v.controlsList) v.controlsList.add('nofullscreen');
      if (portrait.matches) {
        fig.classList.add('show-turn');
        clearTimeout(turnT);
        turnT = setTimeout(() => fig.classList.remove('show-turn'), 3400);
      }
      if (frame.requestFullscreen && screen.orientation && screen.orientation.lock) {
        frame.requestFullscreen({ navigationUI: 'hide' })
          .then(() => screen.orientation.lock('landscape'))
          .catch(() => {});
      }
    };
    const closeCinema = () => {
      if (!cinema) return;
      cinema = false;
      clearTimeout(turnT);
      fig.classList.remove('is-cinema', 'show-turn');
      document.documentElement.classList.remove('film-open');
      if (v.controlsList) v.controlsList.remove('nofullscreen');
      try { if (screen.orientation && screen.orientation.unlock) screen.orientation.unlock(); } catch (e) { /* nicht gesperrt */ }
      if (document.fullscreenElement === frame && document.exitFullscreen) document.exitFullscreen().catch(() => {});
    };
    document.addEventListener('fullscreenchange', () => {
      if (document.fullscreenElement === frame) fsOn = true;
      else if (fsOn) { fsOn = false; closeCinema(); }
    });
    portrait.addEventListener('change', () => { if (!portrait.matches) fig.classList.remove('show-turn'); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeCinema(); });

    const start = () => {
      fig.classList.remove('is-ended');
      fig.classList.add('is-playing');
      v.controls = true;
      const p = v.play();
      if (p && p.catch) p.catch(() => { fig.classList.remove('is-playing'); v.controls = false; closeCinema(); });
      openCinema();
    };
    play.addEventListener('click', start);
    v.addEventListener('click', () => { if (!fig.classList.contains('is-playing')) start(); });
    const again = $('[data-film-again]', fig);
    if (again) again.addEventListener('click', () => { v.currentTime = 0; start(); });
    const close = $('[data-film-close]', fig);
    if (close) close.addEventListener('click', closeCinema);
    v.addEventListener('ended', () => {
      fig.classList.remove('is-playing');
      fig.classList.add('is-ended');
      v.controls = false;
      // im Kinomodus bleibt der Abschluss groß stehen, sonst ein etwaiges Vollbild des Players verlassen
      if (!cinema && v.webkitDisplayingFullscreen && v.webkitExitFullscreen) v.webkitExitFullscreen();
      if (!cinema && document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(() => {});
    });
  });

  /* ── Google Maps erst nach Klick ── */
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-map-load]');
    if (!b) return;
    const box = b.closest('[data-map]');
    const f = document.createElement('iframe');
    f.src = box.dataset.map;
    f.loading = 'lazy';
    f.title = 'Karte: orthoKonzept, Hirschstraße 35a, Karlsruhe';
    f.referrerPolicy = 'no-referrer-when-downgrade';
    box.innerHTML = '';
    box.appendChild(f);
  });

  /* ── Einwilligung: Statistik nur nach Zustimmung, nur auf der Live-Domain ── */
  const consent = $('[data-consent]');
  const GTM = 'GTM-WLST9BVG';
  const loadGtm = () => {
    if (!/orthokonzept\.de$/.test(location.hostname) || window.__gtm) return;
    window.__gtm = true;
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({ 'gtm.start': Date.now(), event: 'gtm.js' });
    const s = document.createElement('script');
    s.async = true; s.src = 'https://www.googletagmanager.com/gtm.js?id=' + GTM;
    document.head.appendChild(s);
  };
  if (consent) {
    const choice = store.get('ok-consent');
    // Seiten ohne Inhalte von Dritten (Begrüßungsseite) fragen erst auf der nächsten Seite
    if (!choice && !document.body.classList.contains('consent-quiet')) consent.hidden = false;
    if (choice === 'all') loadGtm();
    $$('[data-consent-choice]', consent).forEach(b => b.addEventListener('click', () => {
      store.set('ok-consent', b.dataset.consentChoice);
      consent.hidden = true;
      if (b.dataset.consentChoice === 'all') loadGtm();
    }));
    $$('[data-consent-open]').forEach(b => b.addEventListener('click', () => { consent.hidden = false; $('button', consent).focus(); }));
  }

  /* ── Kontaktformular ── */
  const form = $('[data-form]');
  if (form) {
    const q = new URLSearchParams(location.search);
    const setIf = (name, v) => { const el = form.elements[name]; if (el && v && !el.value) el.value = v; };
    setIf('betreff', q.get('betreff'));
    setIf('nachricht', q.get('nachricht'));
    const msg = form.elements.nachricht, count = $('[data-count]', form), out = $('[data-form-msg]', form);
    const upd = () => { if (count) count.textContent = msg.value.length + ' / 3000'; };
    msg.addEventListener('input', upd); upd();
    if (q.get('nachricht')) setTimeout(() => form.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' }), 300);
    const mailto = data => {
      const body = `Name: ${data.get('name')}\nE-Mail: ${data.get('email')}\nTelefon: ${data.get('telefon') || '-'}\n\n${data.get('nachricht')}`;
      location.href = 'mailto:info@orthokonzept.de?subject=' + encodeURIComponent(data.get('betreff')) + '&body=' + encodeURIComponent(body);
    };
    form.addEventListener('submit', async e => {
      e.preventDefault();
      let ok = true;
      $$('input[required], textarea[required]', form).forEach(el => {
        const bad = el.type === 'checkbox' ? !el.checked : !el.value.trim() || (el.type === 'email' && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(el.value));
        el.classList.toggle('is-invalid', bad);
        el.setAttribute('aria-invalid', String(bad));
        if (bad && ok) { ok = false; el.focus(); }
      });
      out.className = 'form__msg';
      if (!ok) { out.textContent = 'Bitte füllen Sie die markierten Pflichtfelder aus.'; out.classList.add('is-err'); return; }
      const data = new FormData(form);
      if (window.OK_STATIC) {
        // statische Vorschau ohne Server: Nachricht direkt im E-Mail-Programm öffnen
        out.textContent = 'Ihr E-Mail-Programm öffnet sich mit Ihrer Nachricht an info@orthokonzept.de.';
        out.classList.add('is-ok');
        mailto(data);
        return;
      }
      const btn = $('button[type=submit]', form);
      btn.disabled = true;
      out.textContent = 'Wird gesendet …';
      try {
        const r = await fetch(form.action, { method: 'POST', body: data, headers: { Accept: 'application/json' } });
        const j = await r.json();
        if (!r.ok || !j.ok) throw new Error(j.error || 'Fehler');
        form.reset(); upd();
        out.textContent = 'Vielen Dank! Ihre Nachricht ist bei uns angekommen, wir melden uns zeitnah.';
        out.classList.add('is-ok');
      } catch (err) {
        out.textContent = 'Der Versand hat nicht geklappt. Wir öffnen Ihr E-Mail-Programm mit Ihrer Nachricht, oder rufen Sie uns an: 0721 1208575.';
        out.classList.add('is-err');
        mailto(data);
      } finally { btn.disabled = false; }
    });
  }
})();
