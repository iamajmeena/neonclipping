// NeonClipping composer: the first screen is a link box, one big button and an Activity list.
// Everything else is grouped behind one "Advanced" button. It only moves existing elements (ids and listeners stay intact).
(function () {
  const $ = id => document.getElementById(id);
  const esc = t => String(t == null ? '' : t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  function init() {
    const view = $('editor-view');
    if (!view || $('adv')) return;
    const importPanel = view.querySelector('.import-panel');
    if (!importPanel) return;
    const panelOf = id => { const el = $(id); return el ? el.closest('section.panel,details.panel') : null; };
    const tools = ['queue-panel', 'ai-panel', 'llm-panel', 'live-panel'].map($);
    const groups = [
      { key: 'options', label: '⚙ Clip options', panels: [$('part-pick'), $('yt-login'), panelOf('accurate')] },
      { key: 'frame', label: '▣ Frame & layout', panels: [panelOf('source')] },
      { key: 'captions', label: 'Aa Captions & heading', panels: [panelOf('captions')] },
      { key: 'style', label: '✦ Style extras', panels: [$('style-panel')] },
      { key: 'tools', label: '🧰 Streams & tools', panels: tools },
    ];
    // panels that other scripts add (transcript search, visual review) get their own tab
    const known = new Set([importPanel, $('saved-edit')].concat(...groups.map(g => g.panels)));
    const rest = [...view.children].filter(e => /^(SECTION|DETAILS)$/.test(e.tagName) && e.classList.contains('panel') && !known.has(e));
    if (rest.length) groups.splice(3, 0, { key: 'search', label: '🔎 Transcript & review', panels: rest });

    const head = importPanel.querySelector('.section-head h2');
    if (head) head.innerHTML = 'Paste a link. <em>Get clips.</em>';

    // ---- Activity (what is running and what is waiting)
    const activity = document.createElement('section');
    activity.id = 'activity';
    activity.className = 'activity';
    activity.hidden = true;
    activity.innerHTML = '<div class="activity-head"><b id="activity-title">Activity</b><span class="muted" id="activity-sub"></span></div><div id="activity-list"></div>';
    importPanel.after(activity);

    // ---- Advanced
    const adv = document.createElement('section');
    adv.id = 'adv';
    adv.className = 'adv';
    adv.innerHTML = '<div class="adv-head"><div id="composer-summary" class="summary" role="status"></div>' +
      '<button type="button" id="adv-toggle" class="adv-toggle" aria-expanded="false">Advanced ▾</button></div>' +
      '<div class="tabs" role="tablist" aria-label="Advanced options" hidden></div><div class="adv-body"></div>';
    activity.after(adv);
    const tabs = adv.querySelector('.tabs');
    const body = adv.querySelector('.adv-body');
    const toggle = $('adv-toggle');

    const empty = document.createElement('div');
    empty.id = 'composer-empty';
    empty.className = 'composer-empty';
    empty.innerHTML = '<b>Your clips will appear here</b><span>Paste a YouTube, Twitch or Kick link above and press Make clips. Everything runs on this PC.</span>';
    const results = $('make-results');
    if (results) results.after(empty);

    // messages written to the status line are mirrored under the link box (the export bar is inside a tab now)
    const composerNote = document.createElement('div');
    composerNote.id = 'composer-note';
    composerNote.className = 'composer-note';
    composerNote.setAttribute('role', 'status');
    composerNote.hidden = true;
    let noteTimer = null;
    const statusLine = $('status');
    if (statusLine) new MutationObserver(() => {
      const t = (statusLine.textContent || '').trim();
      if (!t || /^Add a video to begin/i.test(t)) return;
      composerNote.textContent = t;
      composerNote.hidden = false;
      clearTimeout(noteTimer);
      noteTimer = setTimeout(() => { composerNote.hidden = true; }, 12000);
    }).observe(statusLine, { childList: true, characterData: true, subtree: true });

    // a small "add to queue" link + paste feedback under the link box
    const queueLink = document.createElement('button');
    queueLink.type = 'button';
    queueLink.className = 'linklike queue-add-link';
    queueLink.textContent = '＋ Add to queue instead (runs after the current job)';
    const clearLink = document.createElement('button');
    clearLink.type = 'button';
    clearLink.className = 'url-clear';
    clearLink.textContent = '✕ Clear link';
    clearLink.hidden = true;
    const row = importPanel.querySelector('.url-row');
    if (row) { row.after(queueLink); queueLink.after(clearLink, composerNote); }
    const urlBox = $('url');
    const linkStatus = $('link-status');
    function syncUrlState() {
      const val = (urlBox && urlBox.value.trim()) || '';
      clearLink.hidden = !val;
      if (val) {
        const host = (() => { try { const h = new URL(val).hostname.replace(/^www\./, ''); return /youtu/.test(h) ? 'YouTube' : /twitch/.test(h) ? 'Twitch' : /kick/.test(h) ? 'Kick' : h; } catch { return ''; } })();
        if (host && linkStatus && (!linkStatus.textContent || /^Frames arrive first|^Ready:/.test(linkStatus.textContent.trim()))) {
          linkStatus.textContent = 'Ready: ' + host + ' link pasted — press ⚡ Make clips (or Get preview ↗).';
        }
        const emptyTitle = empty.querySelector('b'), emptySub = empty.querySelector('span');
        if (emptyTitle && emptySub) {
          emptyTitle.textContent = 'Link ready to clip';
          emptySub.textContent = 'Press ⚡ Make clips above (or press Enter) to create captioned clips.';
        }
      } else {
        if (linkStatus && /^Ready:/.test(linkStatus.textContent.trim())) {
          linkStatus.textContent = 'Frames arrive first. Select your areas while the full source downloads.';
        }
        const emptyTitle = empty.querySelector('b'), emptySub = empty.querySelector('span');
        if (emptyTitle && emptySub) {
          emptyTitle.textContent = 'Your clips will appear here';
          emptySub.textContent = 'Paste a YouTube, Twitch or Kick link above and press Make clips. Everything runs on this PC.';
        }
      }
    }
    if (urlBox) {
      urlBox.addEventListener('input', syncUrlState);
      urlBox.addEventListener('paste', () => setTimeout(syncUrlState, 10));
      urlBox.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey && urlBox.value.trim()) {
          e.preventDefault();
          const btn = $('make');
          if (btn && !btn.disabled) btn.click();
        }
      });
      syncUrlState();
    }
    clearLink.onclick = () => { if (urlBox) { urlBox.value = ''; urlBox.focus(); syncUrlState(); } };
    queueLink.onclick = async () => {
      const url = ($('url') && $('url').value.trim()) || '';
      if (!url) { if (typeof status === 'function') status('Paste a video link first.'); return; }
      if ($('queue-urls') && $('queue-add')) {
        $('queue-urls').value = url;
        $('queue-add').click();
        setTimeout(() => { $('url').value = ''; syncUrlState(); refresh(); }, 600);
      }
    };

    const panes = {};
    groups.forEach(g => {
      const pane = document.createElement('div');
      pane.className = 'pane';
      pane.hidden = true;
      g.panels.filter(Boolean).forEach(p => pane.append(p));
      if (g.key === 'frame') { const bar = view.querySelector('.export-bar'); if (bar) pane.append(bar); }
      body.append(pane);
      panes[g.key] = pane;
      const tab = document.createElement('button');
      tab.type = 'button';
      tab.className = 'tab';
      tab.textContent = g.label;
      tab.setAttribute('role', 'tab');
      tab.onclick = () => open(open.current === g.key ? '' : g.key);
      tab.dataset.key = g.key;
      tabs.append(tab);
    });

    function open(key) {
      open.current = key;
      Object.entries(panes).forEach(([k, el]) => { el.hidden = k !== key; });
      tabs.querySelectorAll('.tab').forEach(t => { const on = t.dataset.key === key; t.classList.toggle('on', on); t.setAttribute('aria-selected', on); });
      adv.classList.toggle('opened', !!key);
      if (key) setAdvanced(true);
    }
    open.current = '';
    function setAdvanced(on) {
      tabs.hidden = !on;
      toggle.setAttribute('aria-expanded', on);
      toggle.textContent = on ? 'Advanced ▴' : 'Advanced ▾';
      if (!on) open('');
    }
    toggle.onclick = () => { if (tabs.hidden) { setAdvanced(true); open('options'); } else { setAdvanced(false); } };

    // one line that says what Make clips will do
    function pick(sel) { const el = document.querySelector(sel); return el ? el.textContent.trim() : ''; }
    function summarize() {
      const num = id => ($(id) && $(id).value) || '';
      const select = id => ($(id) && $(id).selectedOptions && $(id).selectedOptions[0] ? $(id).selectedOptions[0].textContent.split('(')[0].trim() : '');
      const parts = [
        (num('count') || '4') + ' clips',
        (num('minlen') || '30') + '–' + (num('length') || '60') + ' s',
        select('srcq'),
        select('language') || 'Auto language',
        pick('[data-layout].active b') || 'auto layout',
        $('captions') && !$('captions').checked ? 'no captions' : (pick('.caption-choice.active b') || 'GTA Neon') + ' captions',
        select('hook-style') ? select('hook-style') + ' heading' : '',
      ].filter(Boolean);
      $('composer-summary').innerHTML = '<span>' + parts.map(p => '<b>' + esc(p) + '</b>').join(' · ') + '</span> <button type="button" class="linklike" id="composer-change">Change</button>';
      $('composer-change').onclick = () => { setAdvanced(true); open('options'); };
    }
    // remember what the person chose last time, so nobody has to open Advanced twice
    const PREFS = 'neon-prefs';
    const PREF_IDS = ['srcq', 'count', 'minlen', 'length', 'mode', 'language', 'aspect', 'resolution', 'accurate'];
    try {
      const saved = JSON.parse(localStorage.getItem(PREFS) || '{}');
      PREF_IDS.forEach(i => { if (saved[i] != null && $(i)) $(i).value = saved[i]; });
      if (saved.captions != null && $('captions')) $('captions').checked = !!saved.captions;
      if (saved.layout) { const b = document.querySelector('[data-layout="' + saved.layout + '"]'); if (b) b.click(); }
      if (saved.style) { const b = document.querySelector('.caption-choice[data-style="' + saved.style + '"]'); if (b) b.click(); }
    } catch (e) { /* first visit or blocked storage */ }
    function savePrefs() {
      try {
        const p = {};
        PREF_IDS.forEach(i => { if ($(i)) p[i] = $(i).value; });
        if ($('captions')) p.captions = $('captions').checked;
        const l = document.querySelector('[data-layout].active'); if (l) p.layout = l.dataset.layout;
        const s = document.querySelector('.caption-choice.active'); if (s) p.style = s.dataset.style;
        localStorage.setItem(PREFS, JSON.stringify(p));
      } catch (e) { /* ignore */ }
    }
    let timer = null;
    const later = () => { clearTimeout(timer); timer = setTimeout(() => { summarize(); savePrefs(); }, 120); };
    ['input', 'change', 'click'].forEach(ev => view.addEventListener(ev, later, true));
    summarize();

    // preview frames arrived: show the frame tab so the facecam and gameplay boxes can be drawn
    const frames = $('frames');
    if (frames) new MutationObserver(() => { if (frames.children.length && !open.current) open('frame'); }).observe(frames, { childList: true });
    // YouTube bot check: show the login helper
    const note = $('link-status');
    if (note) new MutationObserver(() => { if (/bot check|not a bot/i.test(note.textContent || '')) { open('options'); const d = $('yt-login'); if (d) { d.open = true; d.scrollIntoView({ block: 'center' }); } } })
      .observe(note, { childList: true, characterData: true, subtree: true });
    const saved = $('saved-edit');
    // editing a saved clip needs the player and the frame area (inside the Frame tab), so open that tab and bring it into view
    if (saved) new MutationObserver(() => {
      if (saved.hidden) return;
      open('frame');
      const target = $('source') || saved;
      setTimeout(() => (target.closest('.pane') || saved).scrollIntoView({ behavior: 'smooth', block: 'start' }), 120);
    }).observe(saved, { attributes: true, attributeFilter: ['hidden'] });

    // score ring on every result card
    const grid = $('make-grid');
    function ring(card) {
      if (card.dataset.ring) return;
      const viral = card.querySelector('.viral b');
      const m = viral && viral.textContent.match(/(\d+)/);
      if (!m) return;
      card.dataset.ring = '1';
      const n = Math.max(0, Math.min(100, parseInt(m[1], 10)));
      const el = document.createElement('div');
      el.className = 'ring';
      el.style.setProperty('--p', n);
      el.title = 'Viral score ' + n + ' (a heuristic: loudness, shouting, what is said, on-screen action and a local AI read)';
      el.innerHTML = '<span>' + n + '</span>';
      card.prepend(el);
    }
    if (grid) {
      new MutationObserver(() => grid.querySelectorAll('.mk').forEach(ring)).observe(grid, { childList: true, subtree: true });
      grid.querySelectorAll('.mk').forEach(ring);
    }

    // ---- Activity polling: running jobs from /runtime, the persistent queue from /queue
    const nice = u => { try { const x = new URL(u); return x.hostname.replace('www.', '') + (x.searchParams.get('v') ? ' · ' + x.searchParams.get('v') : x.pathname.length > 1 ? x.pathname.slice(0, 24) : ''); } catch (e) { return u; } };
    const progressCache = {};
    async function progressOf(id) {
      try {
        const r = await fetch('/make/' + id);
        if (r.ok) { const j = await r.json(); progressCache[id] = { p: j.progress, phase: j.phase, title: j.title || '', show: !j.internal && j.kind !== 'export' && j.kind !== 'transcribe' }; }
        else { const r2 = await fetch('/status/' + id); if (r2.ok) { const j = await r2.json(); progressCache[id] = { p: j.progress, title: j.title || '', show: !j.internal && !!j.url }; } }
      } catch (e) { /* ignore */ }
      return progressCache[id] || {};
    }
    async function refresh() {
      if (document.hidden) return;
      let runtime = { active: [] };
      let queue = { jobs: [], paused: false };
      try { runtime = await (await fetch('/runtime')).json(); } catch (e) { return; }
      try { queue = await (await fetch('/queue')).json(); } catch (e) { /* queue is PC only */ }
      const items = [];
      const queuedChild = new Set((queue.jobs || []).map(j => j.child).filter(Boolean));
      for (const a of runtime.active || []) {
        if (queuedChild.has(a.id)) continue;
        const pr = await progressOf(a.id);
        if (pr.show === false) continue;          // an internal render step of a bigger job
        items.push({ kind: 'run', title: pr.title || 'Clip job ' + a.id.slice(0, 6), stage: a.stage || a.status, p: pr.p, phase: pr.phase, id: a.id });
      }
      for (const j of queue.jobs || []) {
        const url = (j.payload && (j.payload.url || j.payload.id)) || 'Saved clip';
        if (j.status === 'running') {
          const pr = j.child ? await progressOf(j.child) : {};
          items.push({ kind: 'run', title: nice(url), stage: (j.result && j.result.stage) || 'Running', p: pr.p, phase: pr.phase, id: j.id, queued: true });
        } else if (j.status === 'queued') {
          items.push({ kind: 'wait', title: nice(url), stage: j.not_before > Date.now() / 1000 ? 'Scheduled' : 'Waiting for its turn', id: j.id });
        } else if (['error', 'interrupted'].includes(j.status) && Date.now() / 1000 - (j.updated || 0) < 3 * 3600) {
          items.push({ kind: 'bad', title: nice(url), stage: (j.result && j.result.error) || 'Stopped', id: j.id });
        }
      }
      activity.hidden = !items.length;
      if (!items.length) return;
      const running = items.filter(i => i.kind === 'run').length;
      const waiting = items.filter(i => i.kind === 'wait').length;
      $('activity-title').textContent = 'Activity';
      $('activity-sub').textContent = [running ? running + ' running' : '', waiting ? waiting + ' waiting' : '', queue.paused ? 'queue paused' : ''].filter(Boolean).join(' · ');
      $('activity-list').innerHTML = items.map(i => {
        const pct = typeof i.p === 'number' ? Math.max(3, Math.round(i.p * 100)) : null;
        const chip = i.kind === 'run' ? 'Running' : i.kind === 'wait' ? 'Waiting' : 'Needs retry';
        const bar = i.kind === 'run' ? '<div class="abar"><i style="width:' + (pct == null ? 35 : pct) + '%"' + (pct == null ? ' class="indet"' : '') + '></i></div>' : '';
        const action = i.kind === 'wait' ? '<button type="button" class="mini-btn" data-act="cancel" data-id="' + esc(i.id) + '">Cancel</button>'
          : i.kind === 'bad' ? '<button type="button" class="mini-btn" data-act="retry" data-id="' + esc(i.id) + '">Retry</button>' : '';
        return '<div class="arow ' + i.kind + '"><span class="achip">' + chip + '</span><div class="atext"><b>' + esc(i.title) + '</b><small>' + esc(String(i.stage).slice(0, 140)) + (pct != null && i.kind === 'run' ? ' · ' + pct + '%' : '') + '</small>' + bar + makeStepsMarkup(i.phase) + '</div>' + action + '</div>';
      }).join('');
    }
    $('activity-list').addEventListener('click', async e => {
      const b = e.target.closest('button[data-act]');
      if (!b) return;
      b.disabled = true;
      try { await fetch('/queue/' + b.dataset.id + '/' + b.dataset.act, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }); } catch (err) { /* ignore */ }
      refresh();
    });
    refresh();
    setInterval(refresh, 3000);
  }
  if (document.readyState === 'complete') setTimeout(init, 200);
  else window.addEventListener('load', () => setTimeout(init, 200));
})();
