// Web language control: interface language switcher (saved in localStorage) + quick spoken/caption language control.
(function () {
  const $ = id => document.getElementById(id);
  const KEY = 'nc-ui-lang';
  const UI_LANGS = [
    ['en', 'English'],
    ['hinglish', 'Hinglish'],
    ['hi', 'हिंदी (Hindi)'],
    ['es', 'Español'],
    ['fr', 'Français'],
    ['de', 'Deutsch'],
    ['pt', 'Português'],
    ['ar', 'العربية'],
  ];

  const DICT = {
    hinglish: {
      nav_editor: '◫  Clips banao',
      nav_library: '▦  Mere clips',
      nav_youtube: '▶  YouTube',
      nav_creators: '◉  Creators',
      nav_campaigns: '🎯  Campaigns',
      nav_settings: '⚙  Settings',
      hero_sub: 'Link paste karo. ~2 minute mein captioned 9:16 clips pao. Free, local, open-source.',
      url_ph: 'YouTube, Twitch ya Kick replay link paste karo',
      btn_preview: 'Preview dekho ↗',
      btn_make: '⚡ Clips banao',
      btn_adv_closed: 'Advanced ▾',
      btn_adv_open: 'Advanced ▴',
      lib_title: 'Aapke clips, taiyaar hain.',
      lib_refresh: 'Library refresh karo',
      ui_lang_label: 'Web bhasha',
      cap_lang_label: 'Caption bhasha',
    },
    hi: {
      nav_editor: '◫  क्लिप्स बनाएं',
      nav_library: '▦  मेरे क्लिप्स',
      nav_youtube: '▶  यूट्यूब',
      nav_creators: '◉  क्रिएटर्स',
      nav_campaigns: '🎯  कैंपेन',
      nav_settings: '⚙  सेटिंग्स',
      hero_sub: 'लिंक पेस्ट करें। लगभग 2 मिनट में कैप्शन वाले 9:16 क्लिप्स पाएं। मुफ्त और लोकल।',
      url_ph: 'YouTube, Twitch या Kick वीडियो लिंक पेस्ट करें',
      btn_preview: 'प्रीव्यू देखें ↗',
      btn_make: '⚡ क्लिप्स बनाएं',
      btn_adv_closed: 'एडवांस्ड ▾',
      btn_adv_open: 'एडवांस्ड ▴',
      lib_title: 'आपके क्लिप्स तैयार हैं।',
      lib_refresh: 'लाइब्रेरी रीफ्रेश करें',
      ui_lang_label: 'वेब भाषा',
      cap_lang_label: 'कैप्शन भाषा',
    },
    es: {
      nav_editor: '◫  Crear clips',
      nav_library: '▦  Mis clips',
      nav_youtube: '▶  YouTube',
      nav_creators: '◉  Creadores',
      nav_campaigns: '🎯  Campañas',
      nav_settings: '⚙  Ajustes',
      hero_sub: 'Pega un enlace. Obtén clips 9:16 con subtítulos en unos minutos. Gratis y local.',
      url_ph: 'Pega un enlace de YouTube, Twitch o Kick',
      btn_preview: 'Vista previa ↗',
      btn_make: '⚡ Crear clips',
      btn_adv_closed: 'Avanzado ▾',
      btn_adv_open: 'Avanzado ▴',
      lib_title: 'Tus clips, listos.',
      lib_refresh: 'Actualizar biblioteca',
      ui_lang_label: 'Idioma web',
      cap_lang_label: 'Idioma de subtítulos',
    },
    fr: {
      nav_editor: '◫  Créer des clips',
      nav_library: '▦  Mes clips',
      nav_youtube: '▶  YouTube',
      nav_creators: '◉  Créateurs',
      nav_campaigns: '🎯  Campagnes',
      nav_settings: '⚙  Paramètres',
      hero_sub: 'Collez un lien. Obtenez des clips 9:16 sous-titrés en deux minutes. Gratuit et local.',
      url_ph: 'Collez un lien YouTube, Twitch ou Kick',
      btn_preview: 'Aperçu ↗',
      btn_make: '⚡ Créer des clips',
      btn_adv_closed: 'Avancé ▾',
      btn_adv_open: 'Avancé ▴',
      lib_title: 'Vos clips sont prêts.',
      lib_refresh: 'Actualiser la bibliothèque',
      ui_lang_label: 'Langue web',
      cap_lang_label: 'Langue des sous-titres',
    },
    de: {
      nav_editor: '◫  Clips erstellen',
      nav_library: '▦  Meine Clips',
      nav_youtube: '▶  YouTube',
      nav_creators: '◉  Creator',
      nav_campaigns: '🎯  Kampagnen',
      nav_settings: '⚙  Einstellungen',
      hero_sub: 'Link einfügen. Untertitelte 9:16-Clips in ca. 2 Minuten erhalten. Kostenlos & lokal.',
      url_ph: 'YouTube-, Twitch- oder Kick-Link einfügen',
      btn_preview: 'Vorschau ↗',
      btn_make: '⚡ Clips erstellen',
      btn_adv_closed: 'Erweitert ▾',
      btn_adv_open: 'Erweitert ▴',
      lib_title: 'Deine Clips sind bereit.',
      lib_refresh: 'Bibliothek aktualisieren',
      ui_lang_label: 'Web-Sprache',
      cap_lang_label: 'Untertitelsprache',
    },
    pt: {
      nav_editor: '◫  Criar clipes',
      nav_library: '▦  Meus clipes',
      nav_youtube: '▶  YouTube',
      nav_creators: '◉  Criadores',
      nav_campaigns: '🎯  Campanhas',
      nav_settings: '⚙  Configurações',
      hero_sub: 'Cole um link. Gere clipes 9:16 com legendas em cerca de dois minutos. Grátis e local.',
      url_ph: 'Cole um link do YouTube, Twitch ou Kick',
      btn_preview: 'Pré-visualizar ↗',
      btn_make: '⚡ Criar clipes',
      btn_adv_closed: 'Avançado ▾',
      btn_adv_open: 'Avançado ▴',
      lib_title: 'Seus clipes, prontos.',
      lib_refresh: 'Atualizar biblioteca',
      ui_lang_label: 'Idioma da web',
      cap_lang_label: 'Idioma da legenda',
    },
    ar: {
      nav_editor: '◫  إنشاء مقاطع',
      nav_library: '▦  مقاطعي',
      nav_youtube: '▶  يوتيوب',
      nav_creators: '◉  المبدعون',
      nav_campaigns: '🎯  الحملات',
      nav_settings: '⚙  الإعدادات',
      hero_sub: 'الصق الرابط واحصل على مقاطع 9:16 مترجمة خلال دقيقتين. مجاني ومحلي.',
      url_ph: 'الصق رابط يوتيوب أو تويتش أو كيك',
      btn_preview: 'معاينة ↗',
      btn_make: '⚡ إنشاء مقاطع',
      btn_adv_closed: 'خيارات متقدمة ▾',
      btn_adv_open: 'خيارات متقدمة ▴',
      lib_title: 'مقاطعك جاهزة.',
      lib_refresh: 'تحديث المكتبة',
      ui_lang_label: 'لغة الواجهة',
      cap_lang_label: 'لغة الترجمة',
    },
  };

  function setButtonLead(el, text) {
    if (!el) return;
    if (!el.dataset.enText) el.dataset.enText = el.firstChild && el.firstChild.nodeType === 3 ? el.firstChild.textContent : el.textContent;
    const val = text || el.dataset.enText;
    if (el.firstChild && el.firstChild.nodeType === 3) el.firstChild.textContent = val;
    else el.textContent = val;
  }

  function applyUiLanguage(code) {
    const lang = DICT[code] ? code : 'en';
    const d = DICT[lang] || {};
    document.documentElement.lang = lang === 'hinglish' ? 'en' : lang;
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
    try { localStorage.setItem(KEY, lang); } catch {}

    setButtonLead(document.querySelector('.nav[data-view="editor"]'), d.nav_editor);
    setButtonLead(document.querySelector('.nav[data-view="library"]'), d.nav_library);
    setButtonLead(document.querySelector('.nav[data-view="youtube"]'), d.nav_youtube);
    setButtonLead(document.querySelector('.nav[data-view="creators"]'), d.nav_creators);
    setButtonLead($('side-campaigns'), d.nav_campaigns);
    setButtonLead($('side-settings'), d.nav_settings);

    const heroSub = document.querySelector('main > header > p');
    if (heroSub) {
      if (!heroSub.dataset.enText) heroSub.dataset.enText = heroSub.textContent;
      heroSub.textContent = d.hero_sub || heroSub.dataset.enText;
    }
    const urlInput = $('url');
    if (urlInput) {
      if (!urlInput.dataset.enPh) urlInput.dataset.enPh = urlInput.placeholder;
      urlInput.placeholder = d.url_ph || urlInput.dataset.enPh;
    }
    setButtonLead($('link'), d.btn_preview);
    setButtonLead($('make'), d.btn_make);
    const advBtn = $('adv-toggle');
    if (advBtn) {
      const open = advBtn.getAttribute('aria-expanded') === 'true';
      setButtonLead(advBtn, open ? d.btn_adv_open : d.btn_adv_closed);
    }
    const libHead = document.querySelector('.library-heading h2');
    if (libHead) {
      if (!libHead.dataset.enHtml) libHead.dataset.enHtml = libHead.innerHTML;
      if (d.lib_title) libHead.textContent = d.lib_title;
      else libHead.innerHTML = libHead.dataset.enHtml;
    }
    setButtonLead($('refresh-library'), d.lib_refresh);
    const uiLbl = $('ui-lang-label');
    if (uiLbl) uiLbl.textContent = d.ui_lang_label || 'Web language';
    const capLbl = $('quick-lang-label');
    if (capLbl) capLbl.textContent = d.cap_lang_label || 'Caption language';
    if ($('ui-lang-select')) $('ui-lang-select').value = lang;
  }

  function installControls() {
    const savedUi = (() => { try { return localStorage.getItem(KEY) || 'en'; } catch { return 'en'; } })();

    // 1. Web UI language selector in the header social bar
    const socialBar = document.querySelector('main > header .social');
    if (socialBar && !$('ui-lang-wrap')) {
      const wrap = document.createElement('label');
      wrap.id = 'ui-lang-wrap';
      wrap.style.cssText = 'display:inline-flex;flex-direction:row;align-items:center;gap:6px;margin:0;font-size:11.5px;color:#fbf6ff;background:#0b09128c;border:1px solid #ffffff44;border-radius:999px;padding:3px 10px';
      wrap.innerHTML = '<span>🌐</span><span id="ui-lang-label">Web language</span>';
      const sel = document.createElement('select');
      sel.id = 'ui-lang-select';
      sel.setAttribute('aria-label', 'Web language');
      sel.style.cssText = 'border:0;background:transparent!important;color:#fff!important;padding:2px 4px;font-weight:700;cursor:pointer';
      for (const [code, label] of UI_LANGS) sel.add(new Option(label, code));
      sel.value = savedUi;
      sel.onchange = () => applyUiLanguage(sel.value);
      wrap.append(sel);
      socialBar.prepend(wrap);
    }

    // 2. Quick Caption / Spoken Language selector aligned next to Download quality on Row 2 (url is full-width Row 1)
    const hiddenLang = $('language');
    const srcqLabel = $('srcq') && $('srcq').closest('label');
    if (srcqLabel && hiddenLang && !$('quick-lang')) {
      const ql = document.createElement('label');
      ql.className = 'srcq-inline';
      ql.title = 'Spoken / caption language used when making clips and transcripts.';
      const lbl = document.createElement('span');
      lbl.id = 'quick-lang-label';
      lbl.textContent = 'Caption language';
      const qsel = document.createElement('select');
      qsel.id = 'quick-lang';
      qsel.innerHTML = hiddenLang.innerHTML;
      qsel.value = hiddenLang.value;
      qsel.onchange = () => {
        hiddenLang.value = qsel.value;
        hiddenLang.dispatchEvent(new Event('change', { bubbles: true }));
      };
      hiddenLang.addEventListener('change', () => { qsel.value = hiddenLang.value; });
      ql.append(lbl, qsel);
      srcqLabel.after(ql);
    }

    applyUiLanguage(savedUi);
    // Re-apply after modes.js adds #side-settings asynchronously
    setTimeout(() => applyUiLanguage(($('ui-lang-select') && $('ui-lang-select').value) || savedUi), 600);
  }

  window.neonSetUiLanguage = applyUiLanguage;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(installControls, 40));
  else setTimeout(installControls, 40);
})();
