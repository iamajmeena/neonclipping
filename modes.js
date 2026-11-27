// Speed modes as three big tiles (Fast / Balanced / Best), a "What runs" panel where every feature is a tile you can switch on or off,
// and a "Put your API key" window with free providers (Groq, Google Gemini, NVIDIA, xAI Grok, OpenRouter).
// Endpoints: GET /modes, GET/POST /llm/settings, POST /llm/models, POST /llm/test. Feature choices are kept in this browser.
(function () {
  const $ = id => document.getElementById(id);
  const esc = t => String(t == null ? '' : t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const MODE_INFO = {
    fast: ['⚡', 'Fast', 'About 2-3 min. Every PC. Most features on.'],
    balanced: ['⚖', 'Balanced', 'A bit slower. AI fixes spellings and reads the whole talk.'],
    deep: ['🔬', 'Best', 'Slowest. Full video scan and the fairest comparing.'],
  };
  const LOAD = { light: ['Light', 'l'], medium: ['Medium', 'm'], heavy: ['Heavy', 'h'] };
  let cat = null, own = {};
  try { own = JSON.parse(localStorage.getItem('nc-features') || '{}') || {}; } catch (e) { own = {}; }
  const saveOwn = () => { try { localStorage.setItem('nc-features', JSON.stringify(own)); } catch (e) { } };
  const mode = () => (($('mode') || {}).value) || 'fast';
  const isOn = f => (f.key in own) ? own[f.key] : f.modes.includes(mode());
  let panelOpen = false;          // closed by default: the home screen stays calm
  const whatLabel = () => { const n = Object.keys(own).length, on = cat ? cat.features.filter(isOn).length : 0;
    return '☰ What runs in ' + esc((MODE_INFO[mode()] || [, mode()])[1]) + ' <small>' + on + ' on</small>' + (n ? ' <i>' + n + ' changed</i>' : '') + ' <b>' + (panelOpen ? '▴' : '▾') + '</b>'; };

  function ensureBalancedOption() {
    const sel = $('mode'); if (!sel || [...sel.options].some(o => o.value === 'balanced')) return;
    const o = document.createElement('option'); o.value = 'balanced'; o.textContent = '⚖ Balanced'; sel.insertBefore(o, sel.options[1] || null);
    sel.options[0].textContent = '⚡ Fast'; if (sel.options[2]) sel.options[2].textContent = '🔬 Best';
  }

  function draw() {
    const box = $('mode-tiles'); if (!box || !cat) return;
    const m = mode(), extra = Object.keys(own).length;
    box.innerHTML = '<div class="mt-row">' + cat.modes.map(x => { const [ic, name, line] = MODE_INFO[x.key] || ['', x.label, '']; return '<button type="button" class="mt' + (x.key === m ? ' on' : '') + '" data-mode="' + x.key + '"><span class="mt-ic">' + ic + '</span><b>' + esc(name) + '</b><small>' + esc(line) + '</small></button>'; }).join('') +
      '</div><div class="mt-foot"><button type="button" class="mt-link what' + (panelOpen ? ' open' : '') + '" id="mt-what" aria-expanded="' + panelOpen + '">' + whatLabel() + '</button></div>' +
      '<div class="mt-panel" id="mt-panel"' + (panelOpen ? '' : ' hidden') + '></div>';
    if (panelOpen) drawPanel();
  }

  function drawPanel() {
    const p = $('mt-panel'); if (!p || !cat) return;
    p.innerHTML = '<div class="mt-panel-head"><b>What runs in ' + esc((MODE_INFO[mode()] || [, mode()])[1]) + '</b><small>Tap a tile to switch it on or off. Your choice stays for next time.</small>' +
      (Object.keys(own).length ? '<button type="button" class="mt-link" id="mt-reset">Back to the mode\'s choice</button>' : '') + '</div><div class="mt-feats">' +
      cat.features.map(f => { const on = isOn(f), [ln, lc] = LOAD[f.load] || ['', '']; return '<button type="button" class="mf' + (on ? ' on' : '') + (f.key in own ? ' own' : '') + '" data-feat="' + f.key + '" aria-pressed="' + on + '"><span class="mf-top"><b>' + esc(f.name) + '</b><span class="ld ' + lc + '">' + ln + '</span></span><small>' + esc(f.line) + '</small><span class="mf-sw">' + (on ? 'ON' : 'OFF') + '</span></button>'; }).join('') + '</div>';
  }

  // ---------- Settings (left sidebar): AI key and Shortcut live here, not on the home screen
  let installPrompt = null;
  window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); installPrompt = e; });
  function settingsDialog(tab) {
    let d = $('key-dialog');
    if (!d) { d = document.createElement('dialog'); d.id = 'key-dialog'; d.className = 'key-dialog'; document.body.append(d); }
    d.innerHTML = '<div class="kd-head"><b>⚙ Settings</b><button type="button" class="mt-link" data-kd="close">✕</button></div>' +
      '<div class="st-tabs"><button type="button" data-st="key"' + (tab !== 'shortcut' ? ' class="on"' : '') + '>🔑 AI key (free)</button><button type="button" data-st="shortcut"' + (tab === 'shortcut' ? ' class="on"' : '') + '>📌 Shortcut</button><button type="button" data-st="auto"' + (tab === 'auto' ? ' class="on"' : '') + '>⚙ Automation</button></div><div id="st-body"></div>';
    if (!d.open) d.showModal();
    if (tab === 'shortcut') shortcutPane(); else if (tab === 'auto') autoPane(); else keyDialog();
  }
  // ---------- Automation: watch folder, webhook, words to avoid
  async function autoPane() {
    const b = $('st-body'); b.innerHTML = 'Loading…'; let s = {};
    try { s = await request('/automation'); } catch (e) { b.textContent = e.message; return; }
    b.innerHTML = '<div class="au-card"><label class="au-sw"><input type="checkbox" id="au-on"' + (s.watch_on ? ' checked' : '') + '><b>📂 Watch a folder</b></label>' +
      '<small>Drop a finished recording into this folder and clips are made by themselves, even overnight. Status: <b id="au-status">' + esc(s.status || 'off') + '</b>' + (s.last ? ' · last: ' + esc(s.last) : '') + '</small>' +
      '<input id="au-folder" placeholder="Full folder path, e.g. D:\Recordings" value="' + esc(s.watch_folder || '') + '">' +
      '<div class="kd-row"><label>Clips per video <input id="au-count" type="number" min="1" max="12" value="' + (s.watch_count || 4) + '" style="width:70px"></label>' +
      '<label>Mode <select id="au-mode"><option value="fast"' + (s.watch_mode === 'fast' ? ' selected' : '') + '>Fast</option><option value="balanced"' + (s.watch_mode === 'balanced' ? ' selected' : '') + '>Balanced</option><option value="deep"' + (s.watch_mode === 'deep' ? ' selected' : '') + '>Best</option></select></label></div></div>' +
      '<div class="au-card"><b>🔔 Tell me when a clip is ready</b><small>A web address (Discord webhook, Zapier, your own script). It gets only the title, hook, score and hashtags; the video is never sent.</small>' +
      '<input id="au-hook" placeholder="https://… (leave empty for none)" value="' + esc(s.webhook_url || '') + '"></div>' +
      '<div class="au-card"><b>🚫 Words to avoid</b><small>A clip whose title, hook, description or captions contain one of these gets a red "Check before posting" tag.</small>' +
      '<textarea id="au-banned" rows="3" placeholder="one word per line or separated by commas">' + esc((s.banned || []).join(', ')) + '</textarea></div>' +
      '<div class="au-card"><b>🚀 Auto video upload</b><small>Automatically upload finished clips to YouTube, X, Instagram, Facebook, TikTok, LinkedIn, Threads or custom endpoints.</small>' +
      '<button type="button" class="mt-link" data-au="open-social">Open My clips → Publish &amp; Auto-upload</button></div>' +
      '<div class="kd-row"><button type="button" class="primary" data-au="save">Save</button><span class="muted" id="au-note"></span></div>';
  }
  async function autoSave() {
    const note = t => { const n = $('au-note'); if (n) n.textContent = t; };
    note('Saving…');
    try {
      const s = await request('/automation', { watch_folder: $('au-folder').value.trim(), watch_on: $('au-on').checked, watch_count: Number($('au-count').value) || 4, watch_mode: $('au-mode').value, webhook_url: $('au-hook').value.trim(), banned: $('au-banned').value });
      note('✓ Saved' + (s.watch_on ? ' · watching ' + s.watch_folder : ''));
    } catch (e) { note('✗ ' + e.message); }
  }

  function shortcutPane() {
    $('st-body').innerHTML = '<p class="muted">Come back to NeonClipping in one click. The shortcut opens it if it is running and starts it if not.</p>' +
      '<div class="kd-grid"><button type="button" class="kd-p" data-sc="desk"><b>🖥 Desktop + Start Menu</b><small>An icon on your Desktop and in the Start Menu (Windows), or on the Desktop (Mac / Linux).</small></button>' +
      '<button type="button" class="kd-p" data-sc="app"><b>⬇ Install as an app</b><small>Its own window and taskbar icon from Chrome or Edge, no browser tabs.</small></button></div><p class="muted" id="sc-note"></p>';
  }
  async function shortcutAction(kind) {
    const note = t => { const n = $('sc-note'); if (n) n.innerHTML = t; };
    if (kind === 'desk') { note('Making it…'); try { const r = await request('/shortcut', {}); note(r.made && r.made.length ? '✓ ' + esc(r.note) : '✗ ' + esc(r.note)); } catch (e) { note('✗ ' + esc(e.message)); } return; }
    if (installPrompt) { installPrompt.prompt(); const c = await installPrompt.userChoice.catch(() => ({})); note(c.outcome === 'accepted' ? '✓ Installed. Find NeonClipping in your Start Menu / apps.' : 'Not installed.'); installPrompt = null; return; }
    note('In Chrome: menu <b>⋮</b> → <b>Cast, save and share</b> → <b>Install page as app</b>. In Edge: menu <b>…</b> → <b>Apps</b> → <b>Install this site as an app</b>.');
  }
  function addSidebarItem() {
    const side = document.querySelector('aside.sidebar'); if (!side || $('side-settings')) return;
    const navs = side.querySelectorAll('.nav'); const last = navs[navs.length - 1]; if (!last) return;
    const b = document.createElement('button'); b.type = 'button'; b.className = 'nav'; b.id = 'side-settings'; b.innerHTML = '⚙ &nbsp; Settings';
    b.onclick = () => settingsDialog('key');
    const campaigns = $('side-campaigns');
    if (campaigns) campaigns.before(b); else last.after(b);
  }

  // ---------- API key pane
  function keyDialog() {
    const d = $('key-dialog');
    $('st-body').innerHTML = '<p class="muted">A free key lets an online AI do the thinking (picking moments, hooks, titles, spelling) so a slow PC still feels fast. Only the <b>text</b> of a clip is sent; your video and audio stay on this PC. You can switch it off any time.</p>' +
      '<div class="kd-grid" id="kd-grid">Loading…</div><div class="kd-steps" id="kd-steps" hidden></div>';
    request('/llm/settings').then(s => {
      const order = ['groq', 'gemini', 'nvidia', 'xai', 'openrouter', 'openai', 'lmstudio'], pr = s.presets || {};
      $('kd-grid').innerHTML = order.filter(k => pr[k]).map(k => '<button type="button" class="kd-p" data-prov="' + k + '"><b>' + esc(pr[k].label) + '</b><small>' + esc(pr[k].free || '') + '</small></button>').join('');
      d.dataset.presets = JSON.stringify(pr);
      if (s.ready) $('kd-grid').insertAdjacentHTML('beforebegin', '<p class="kd-ok">✓ Working now: ' + esc(s.model) + '</p>');
    }).catch(e => { $('kd-grid').textContent = e.message; });
  }
  function keySteps(k) {
    const d = $('key-dialog'), p = JSON.parse(d.dataset.presets || '{}')[k]; if (!p) return;
    d.dataset.prov = k;
    const st = $('kd-steps'); st.hidden = false;
    st.innerHTML = '<div class="kd-step"><span>1</span><div><b>Get a free key</b><a class="kd-go" href="' + esc(p.key_url) + '" target="_blank" rel="noopener">Open ' + esc(p.label) + ' ↗</a><small>Sign in, press "Create API key", copy it.</small></div></div>' +
      '<div class="kd-step"><span>2</span><div><b>Paste it here</b><input id="kd-key" type="password" autocomplete="off" placeholder="paste the key"></div></div>' +
      '<div class="kd-step"><span>3</span><div><b>Model</b><div class="kd-row"><input id="kd-model" value="' + esc(p.model) + '" placeholder="press Find models"><button type="button" class="mt-link" data-kd="models">Find models</button></div><div id="kd-list" class="kd-list"></div></div></div>' +
      '<div class="kd-row"><button type="button" class="primary" data-kd="save">Save and test</button><span class="muted" id="kd-note"></span></div>';
  }
  async function keyAction(a) {
    const d = $('key-dialog'), p = JSON.parse(d.dataset.presets || '{}')[d.dataset.prov] || {}, note = t => { const n = $('kd-note'); if (n) n.textContent = t; };
    if (a === 'close') { d.close(); return; }
    if (a === 'models') {
      const l = $('kd-list'); l.textContent = 'Asking the provider…';
      try { const r = await request('/llm/models', { base_url: p.base_url, api_key: $('kd-key').value }); l.innerHTML = (r.models || []).slice(0, 40).map(m => '<button type="button" class="kd-m" data-model="' + esc(m) + '">' + esc(m) + '</button>').join('') || 'No models listed.'; }
      catch (e) { l.textContent = e.message; }
      return;
    }
    if (a === 'save') {
      note('Saving and testing…');
      try {
        await request('/llm/settings', { enabled: true, base_url: p.base_url, model: $('kd-model').value.trim(), api_key: $('kd-key').value.trim() });
        const r = await request('/llm/test', {});
        note(r.ok ? '✓ Works (' + r.ms + ' ms). Clips will now use ' + r.model + '.' : '✗ ' + (r.error || 'Did not work. Check the key and the model.'));
        if (r.ok) { $('kd-key').value = ''; const sum = $('mt-key'); if (sum) sum.classList.add('ok'); }
      } catch (e) { note('✗ ' + e.message); }
    }
  }

  document.addEventListener('click', e => {
    if (e.target.closest('[data-qs="close"]')) { try { localStorage.setItem('nc-quick', '1'); } catch (x) { } const q = $('quick-start'); if (q) q.remove(); return; }
    const b = e.target.closest('[data-mode]'); if (b && $('mode')) { $('mode').value = b.dataset.mode; $('mode').dispatchEvent(new Event('change', { bubbles: true })); draw(); return; }
    if (e.target.closest('#mt-what')) { panelOpen = !panelOpen; draw(); return; }
    if (e.target.closest('#mt-reset')) { own = {}; saveOwn(); draw(); return; }
    if (e.target.closest('[data-au="open-social"]')) { const d = $('key-dialog'); if (d && d.open) d.close(); const nav = document.querySelector('.nav[data-view="library"]'); if (nav) nav.click(); const sp = $('social-panel'); if (sp) { sp.open = true; const ab = $('social-auto-box'); if (ab) ab.open = true; sp.scrollIntoView({ behavior: 'smooth' }); } return; }
    if (e.target.closest('[data-au="save"]')) { autoSave(); return; }
    if (e.target.closest('[data-sc]')) { shortcutAction(e.target.closest('[data-sc]').dataset.sc); return; }
    const f = e.target.closest('[data-feat]'); if (f && cat) { const feat = cat.features.find(x => x.key === f.dataset.feat); const def = feat.modes.includes(mode()); const next = !isOn(feat); if (next === def) delete own[feat.key]; else own[feat.key] = next; saveOwn(); draw(); return; }
    const stt = e.target.closest('[data-st]'); if (stt) { document.querySelectorAll('.st-tabs button').forEach(x => x.classList.toggle('on', x === stt)); if (stt.dataset.st === 'shortcut') shortcutPane(); else if (stt.dataset.st === 'auto') autoPane(); else keyDialog(); return; }
    const pv = e.target.closest('[data-prov]'); if (pv) { document.querySelectorAll('.kd-p').forEach(x => x.classList.toggle('on', x === pv)); keySteps(pv.dataset.prov); return; }
    const mm = e.target.closest('[data-model]'); if (mm) { $('kd-model').value = mm.dataset.model; return; }
    const ka = e.target.closest('[data-kd]'); if (ka) keyAction(ka.dataset.kd);
  });
  document.addEventListener('change', e => { if (e.target && e.target.id === 'mode') { draw(); const p = $('mt-panel'); if (p && !p.hidden) drawPanel(); } });

  // every Make clips request carries the feature tiles you changed
  const wrap = () => {
    if (!window.request || window.request._modes) return;
    const orig = window.request;
    window.request = function (path, body) { if (path === '/make' && body && Object.keys(own).length) body = { ...body, features: { ...own } }; return orig(path, body); };
    window.request._modes = true;
  };

  async function init() {
    ensureBalancedOption(); wrap(); addSidebarItem(); setTimeout(addSidebarItem, 800);
    const ls = $('link-status');      // the default help line under the link box only shows once something happens
    if (ls) { const upd = () => ls.classList.toggle('quiet', /^Frames arrive first/.test(ls.textContent.trim())); upd(); new MutationObserver(upd).observe(ls, { childList: true, characterData: true, subtree: true }); }
    let seen = false; try { seen = localStorage.getItem('nc-quick') === '1'; } catch (e) { }      // first-run quick start: three steps, gone for good after one click
    const row = $('make') && $('make').closest('.url-row');
    if (!seen && row && !$('quick-start')) {
      const q = document.createElement('div'); q.id = 'quick-start'; q.className = 'qs';
      q.innerHTML = '<div class="qs-steps"><span><b>1</b> Paste a video link</span><i>→</i><span><b>2</b> Pick <em>Fast</em></span><i>→</i><span><b>3</b> Press <em>Make clips</em></span></div>' +
        '<small>That is all. Everything else (caption style, layout, Settings) is optional and is applied when you press Make clips.</small><button type="button" data-qs="close">Got it</button>';
      row.before(q);
    }
    const make = document.querySelector('.make-row') || ($('make') && $('make').closest('.url-row'));
    if (!make || $('mode-tiles')) return;
    const box = document.createElement('div'); box.id = 'mode-tiles'; box.className = 'mode-tiles'; make.after(box);
    try { cat = await request('/modes'); } catch (e) { box.remove(); return; }
    draw();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(init, 0)); else setTimeout(init, 0);
})();
