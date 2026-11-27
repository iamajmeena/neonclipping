// Right sidebar: Live Preview (9:16) of the clip you are making, with Caption / Layout / Heading / Output tabs, plus what is being made right now.
// It mirrors the page's own preview canvas, so what you see is the real caption style, layout and heading, and its tabs press the page's real controls.
(function () {
  const $ = id => document.getElementById(id);
  const esc = t => String(t == null ? '' : t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const get = async path => { const r = await fetch(path); if (!r.ok) throw new Error('x'); return r.json(); };
  const STYLES = [['karaoke', 'Karaoke'], ['tiktok', 'TikTok'], ['pill', 'Pill'], ['oneword', 'One word'], ['cine', 'Cinematic'], ['boxed', 'Boxed'], ['outlined', 'Outlined'], ['comic', 'Comic'], ['gta', 'GTA Neon'], ['bold', 'Impact'], ['hormozi', 'Hormozi'], ['mrbeast', 'MrBeast'], ['clean', 'Clean']];
  const LAYOUTS = [['stack', 'Face + game'], ['bottom', 'Game + face'], ['blur', 'Blurred'], ['fill', 'Fill'], ['game', 'Game only'], ['pip_tl', 'Cam ↖'], ['pip_tr', 'Cam ↗'], ['pip_bl', 'Cam ↙'], ['pip_br', 'Cam ↘'], ['circle', 'Circle'], ['side', 'Side by side']];
  const HEADINGS = [['impact', 'Impact'], ['neon', 'Neon'], ['banner', 'Banner'], ['box', 'Box']];
  const POS = [['Top', 520], ['Middle', 950], ['Bottom', 1450]];
  const QUAL = [['720p', '720'], ['1080p', '1080'], ['4K', '2160']];
  const ASPECT = [['9:16', 'vertical'], ['1:1', 'square'], ['4:5', 'portrait'], ['3:4', 'threefour'], ['16:9', 'landscape']];
  let tab = 'caption', open = true;

  function setField(id, value) {
    const el = $(id); if (!el) return;
    if (el.type === 'checkbox') el.checked = !!value; else el.value = String(value);
    el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true }));
  }
  const press = sel => { const b = document.querySelector(sel); if (b) b.click(); };
  const cur = id => { const e = $(id); return e ? (e.type === 'checkbox' ? e.checked : e.value) : ''; };
  const curStyle = () => { try { return typeof style === 'string' ? style : 'karaoke'; } catch (e) { return 'karaoke'; } };
  const curLayout = () => { try { return typeof layout === 'string' ? layout : 'stack'; } catch (e) { return 'stack'; } };

  function layoutSvg(id) {
    const g = '#4a4a5a', c = '#ff3d6e', r = (x, y, w, h, f) => '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" rx="2" fill="' + f + '"/>';
    const body = { stack: r(0, 0, 36, 22, c) + r(0, 22, 36, 42, g), bottom: r(0, 0, 36, 42, g) + r(0, 42, 36, 22, c), blur: r(0, 0, 36, 64, '#2a2a38') + r(0, 18, 36, 28, g), fill: r(0, 0, 36, 64, g), game: r(0, 0, 36, 64, g),
      pip_tl: r(0, 0, 36, 64, g) + r(3, 3, 14, 14, c), pip_tr: r(0, 0, 36, 64, g) + r(19, 3, 14, 14, c), pip_bl: r(0, 0, 36, 64, g) + r(3, 47, 14, 14, c), pip_br: r(0, 0, 36, 64, g) + r(19, 47, 14, 14, c),
      circle: r(0, 0, 36, 64, g) + '<circle cx="18" cy="48" r="9" fill="' + c + '"/>', side: r(0, 0, 18, 64, c) + r(18, 0, 18, 64, g) }[id] || r(0, 0, 36, 64, g);
    return '<svg viewBox="0 0 36 64" width="28" height="50">' + body + '</svg>';
  }
  const chip = (attrs, label, on) => '<button type="button" class="rb-chip' + (on ? ' on' : '') + '" ' + attrs + '>' + label + '</button>';

  function drawPane() {
    const pane = $('rb-pane'); if (!pane) return;
    document.querySelectorAll('#rb-tabs [data-tab]').forEach(b => b.classList.toggle('on', b.dataset.tab === tab));
    if (tab === 'caption') {
      pane.innerHTML = '<div class="rb-styles">' + STYLES.map(([k, n]) => '<button type="button" class="rb-style' + (curStyle() === k ? ' on' : '') + '" data-style="' + k + '"><canvas width="132" height="46" data-demo="' + k + '"></canvas><small>' + n + '</small></button>').join('') + '</div>' +
        '<h4>Position</h4><div class="rb-row">' + POS.map(([n, v]) => chip('data-pos="' + v + '"', n, Math.abs(Number(cur('caption-y')) - v) < 200 && !(v === 1450 && Number(cur('caption-y')) < 1200) && !(v === 520 && Number(cur('caption-y')) > 700))).join('') + '</div>' +
        '<label class="rb-chk"><input type="checkbox" data-cb="captions"' + (cur('captions') ? ' checked' : '') + '> Captions on</label>';
      pane.querySelectorAll('canvas[data-demo]').forEach(c => { const x = c.getContext('2d'); x.fillStyle = '#0a0a0f'; x.fillRect(0, 0, c.width, c.height); if (window.NeonCaption) window.NeonCaption.draw(x, { style: c.dataset.demo, words: ['YOUR', 'STORY'], active: 1, cx: c.width / 2, cy: c.height / 2, fs: 17, maxW: c.width - 10 }); });
    } else if (tab === 'layout') {
      pane.innerHTML = '<div class="rb-lays">' + LAYOUTS.map(([k, n]) => '<button type="button" class="rb-lay' + (curLayout() === k ? ' on' : '') + '" data-layout="' + k + '">' + layoutSvg(k) + '<small>' + n + '</small></button>').join('') + '</div>';
    } else if (tab === 'heading') {
      pane.innerHTML = '<label class="rb-chk"><input type="checkbox" data-cb="hook-enabled"' + (cur('hook-enabled') ? ' checked' : '') + '> Opening heading</label>' +
        '<input id="rb-hook" class="rb-text" maxlength="65" placeholder="Opening line" value="' + esc(cur('hook')) + '">' +
        '<div class="rb-row">' + HEADINGS.map(([k, n]) => chip('data-hs="' + k + '"', n, cur('hook-style') === k)).join('') + '</div>';
    } else {
      pane.innerHTML = '<h4>Shape</h4><div class="rb-row">' + ASPECT.map(([n, v]) => chip('data-asp="' + v + '"', n, cur('aspect') === v)).join('') + '</div>' +
        '<h4>Download quality</h4><div class="rb-row">' + QUAL.map(([n, v]) => chip('data-q="' + v + '"', n, cur('srcq') === v)).join('') + '</div>' +
        '<h4>Clips</h4><div class="rb-row">' + [3, 5, 8, 12].map(n => chip('data-n="' + n + '"', n, Number(cur('count')) === n)).join('') + '</div>';
    }
  }

  // mirror the page's own preview canvas
  function mirror() {
    const dst = $('rb-canvas');
    try {
      if (dst && typeof pc !== 'undefined' && pc.canvas && document.body.classList.contains('rb-open')) {
        const x = dst.getContext('2d'); x.fillStyle = '#000'; x.fillRect(0, 0, dst.width, dst.height);
        if (typeof c !== 'undefined' && c.width && typeof still !== 'undefined') x.drawImage(pc.canvas, 0, 0, dst.width, dst.height);
        if (!window.__rbHint) { window.__rbHint = 1; }
      }
    } catch (e) { /* page preview not ready */ }
    requestAnimationFrame(mirror);
  }

  async function refresh() {
    if (document.hidden) return;
    const live = $('rb-live'); if (!live) return;
    try {
      const rt = await get('/runtime');
      let q = [];
      try { q = ((await get('/queue')).jobs || []).filter(j => ['running', 'queued'].includes(j.status)); } catch (e) { /* PC only */ }
      const child = new Set(q.map(j => j.child).filter(Boolean));
      const rows = [];
      const prog = async id => { try { const r = await fetch('/make/' + id); if (r.ok) { const j = await r.json(); return { p: j.progress, title: j.title || '', show: !j.internal && j.kind !== 'export' && j.kind !== 'transcribe' }; } const r2 = await fetch('/status/' + id); if (r2.ok) { const j = await r2.json(); return { p: j.progress, title: j.title || '', show: !j.internal && !!j.url }; } } catch (e) { /* ignore */ } return {}; };
      for (const a of (rt.active || [])) {
        if (!['running', 'queued', 'starting', 'recording'].includes(a.status) || child.has(a.id)) continue;
        const pr = await prog(a.id); if (pr.show === false) continue;       // internal render step of a bigger job
        rows.push({ t: pr.title || 'Making clips', s: a.stage || a.status, p: pr.p });
      }
      for (const j of q) {
        const url = (j.payload && (j.payload.url || j.payload.id)) || j.url || 'Queued link';
        if (j.status === 'running') { const pr = j.child ? await prog(j.child) : {}; rows.push({ t: String(url).replace(/^https?:\/\/(www\.)?/, '').slice(0, 44), s: (j.result && j.result.stage) || 'Running', p: pr.p }); }
        else rows.push({ t: String(url).replace(/^https?:\/\/(www\.)?/, '').slice(0, 44), s: 'Waiting for its turn in the queue', wait: true });
      }
      live.innerHTML = rows.length ? rows.map(r => {
        const pct = typeof r.p === 'number' ? Math.max(2, Math.min(100, Math.round(r.p * 100))) : null;
        return '<div class="rb-row2"><div class="rb-top"><b>' + esc(r.t) + '</b>' + (r.wait ? '<span class="rb-pct">waiting</span>' : '<span class="rb-pct">' + (pct == null ? '…' : pct + '%') + '</span>') + '</div>' +
          (r.wait ? '' : '<div class="rb-bar"><i' + (pct == null ? ' class="indet"' : ' style="width:' + pct + '%"') + '></i></div>') + '<small>' + esc(String(r.s).slice(0, 120)) + '</small></div>';
      }).join('') : '<small class="rb-empty">Nothing is being made right now.</small>';
    } catch (e) { live.innerHTML = '<small class="rb-empty">Activity is unavailable.</small>'; }
  }

  function init() {
    if ($('right-bar')) return;
    const bar = document.createElement('aside');
    bar.id = 'right-bar'; bar.className = 'right-bar';
    bar.innerHTML = '<button type="button" id="rb-toggle" class="rb-toggle" aria-label="Open or close the live preview">▶</button>' +
      '<div class="rb-inner"><div class="rb-head"><b>Live Preview (9:16)</b><span class="rb-badge">● Real-time style preview</span></div>' +
      '<div class="rb-stage"><canvas id="rb-canvas" width="360" height="640"></canvas><div class="rb-empty-note" id="rb-empty">Paste a link and press Get preview to see your clip here.</div></div>' +
      '<button type="button" class="rb-make" id="rb-make" style="background:linear-gradient(90deg,#35e0d0,#c8f94b)!important;color:#10101a!important">⚡ Make clips</button><div id="rb-live"></div>' +
      '<div class="rb-tabs" id="rb-tabs">' + [['caption', 'Aa Caption'], ['layout', '▦ Layout'], ['heading', '✦ Heading'], ['output', '⚙ Output']].map(([k, n]) => '<button type="button" data-tab="' + k + '">' + n + '</button>').join('') + '</div>' +
      '<div class="rb-pane" id="rb-pane"></div></div>';
    document.body.append(bar);
    try { open = localStorage.getItem('neon-rightbar') !== '0' && window.innerWidth > 1280; } catch (e) { /* ignore */ }
    const set = on => { document.body.classList.toggle('rb-open', on); $('rb-toggle').textContent = on ? '▶' : '◀'; try { localStorage.setItem('neon-rightbar', on ? '1' : '0'); } catch (e) { /* ignore */ } };
    set(open);
    $('rb-toggle').onclick = () => set(!document.body.classList.contains('rb-open'));
    bar.addEventListener('click', e => {
      const t = e.target; let b;
      if (t.closest('#rb-make')) { const m = $('make'); if (m) { m.click(); setTimeout(refresh, 800); } return; }
      if ((b = t.closest('[data-tab]'))) { tab = b.dataset.tab; drawPane(); return; }
      if ((b = t.closest('[data-style]'))) { press('.caption-choice[data-style="' + b.dataset.style + '"]'); }
      else if ((b = t.closest('[data-layout]'))) { press('.choice[data-layout="' + b.dataset.layout + '"]'); }
      else if ((b = t.closest('[data-pos]'))) setField('caption-y', b.dataset.pos);
      else if ((b = t.closest('[data-hs]'))) setField('hook-style', b.dataset.hs);
      else if ((b = t.closest('[data-asp]'))) setField('aspect', b.dataset.asp);
      else if ((b = t.closest('[data-q]'))) setField('srcq', b.dataset.q);
      else if ((b = t.closest('[data-n]'))) setField('count', b.dataset.n);
      else return;
      setTimeout(drawPane, 60);
    });
    bar.addEventListener('change', e => { const cb = e.target.closest('[data-cb]'); if (cb) { setField(cb.dataset.cb, cb.checked); } });
    bar.addEventListener('input', e => { if (e.target.id === 'rb-hook') setField('hook', e.target.value); });
    drawPane(); mirror(); refresh(); setInterval(refresh, 2000);
    setInterval(() => { const e = $('rb-empty'); if (e) { try { e.style.display = (typeof sourceW !== 'undefined' && sourceW) ? 'none' : ''; } catch (x) { /* ignore */ } } }, 700);
  }
  if (document.readyState === 'complete') setTimeout(init, 600); else window.addEventListener('load', () => setTimeout(init, 600));
})();
