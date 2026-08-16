/* Noyau : état partagé, client HTTP, formatage, modale, toasts, helpers DOM. */
const App = {
  state: {
    month: null,        // 'YYYY-MM'
    meta: null,
    settings: null,
    charts: {},
  },
  tabs: {},             // renseigné par chaque module : { load(), name }
};

/* ---------- HTTP ---------- */
App.api = {
  async request(method, url, payload) {
    const opts = { method, headers: {} };
    if (payload !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(payload);
    }
    const res = await fetch(url, opts);
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = { error: text }; }
    if (!res.ok) throw new Error((data && data.error) || `Erreur ${res.status}`);
    return data;
  },
  get(url) { return App.api.request('GET', url); },
  post(url, body) { return App.api.request('POST', url, body || {}); },
  put(url, body) { return App.api.request('PUT', url, body || {}); },
  del(url) { return App.api.request('DELETE', url); },
};

/* ---------- formatage ---------- */
const eurFmt = new Intl.NumberFormat('fr-FR', {
  style: 'currency', currency: 'EUR', maximumFractionDigits: 2,
});
const eurFmt0 = new Intl.NumberFormat('fr-FR', {
  style: 'currency', currency: 'EUR', maximumFractionDigits: 0,
});
const numFmt = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 2 });

App.fmt = {
  eur(v, compact) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    return (compact ? eurFmt0 : eurFmt).format(v);
  },
  num(v, digits) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    return new Intl.NumberFormat('fr-FR', { maximumFractionDigits: digits ?? 2 }).format(v);
  },
  pct(v, digits) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    const d = digits ?? 1;
    return `${new Intl.NumberFormat('fr-FR', {
      minimumFractionDigits: d, maximumFractionDigits: d,
    }).format(v)} %`;
  },
  /* ratio 0.42 -> "42,0 %" */
  ratio(v, digits) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    return App.fmt.pct(v * 100, digits);
  },
  date(iso) {
    if (!iso) return '—';
    const d = new Date(`${String(iso).slice(0, 10)}T00:00:00`);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric' });
  },
  dateTime(iso) {
    if (!iso) return '—';
    const d = new Date(String(iso).replace(' ', 'T') + 'Z');
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString('fr-FR', {
      day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  },
  month(ym) {
    if (!ym) return '—';
    const [y, m] = ym.split('-').map(Number);
    return new Date(y, m - 1, 1)
      .toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' });
  },
  signed(v) {
    if (v === null || v === undefined) return '—';
    return (v > 0 ? '+' : '') + App.fmt.eur(v);
  },
};

/* ---------- DOM ---------- */
App.el = (sel, root) => (root || document).querySelector(sel);
App.els = (sel, root) => Array.from((root || document).querySelectorAll(sel));

App.h = function (tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
    else if (k === 'dataset') Object.assign(node.dataset, v);
    else node.setAttribute(k, v === true ? '' : v);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
};

App.esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));

App.clear = (node) => { while (node && node.firstChild) node.removeChild(node.firstChild); };

/* ---------- toasts ---------- */
App.toast = function (message, kind = 'info', ms = 3600) {
  const host = App.el('#toast-host');
  const node = App.h('div', { class: `toast ${kind}` }, message);
  host.append(node);
  setTimeout(() => {
    node.classList.add('leaving');
    setTimeout(() => node.remove(), 240);
  }, ms);
};

/* ---------- modale ---------- */
App.modal = {
  open({ title, body, footer, wide }) {
    App.el('#modal-title').textContent = title || '';
    const bodyHost = App.el('#modal-body');
    const footHost = App.el('#modal-foot');
    App.clear(bodyHost); App.clear(footHost);
    if (body) bodyHost.append(body);
    if (footer) footHost.append(...[].concat(footer));
    App.el('#modal').classList.toggle('wide', !!wide);
    App.el('#modal-backdrop').hidden = false;
    document.body.style.overflow = 'hidden';
    const first = bodyHost.querySelector('input, select, textarea');
    if (first) setTimeout(() => first.focus(), 30);
  },
  close() {
    App.el('#modal-backdrop').hidden = true;
    document.body.style.overflow = '';
    App.clear(App.el('#modal-body'));
    App.clear(App.el('#modal-foot'));
  },
  setBody(node) {
    const host = App.el('#modal-body');
    App.clear(host);
    host.append(node);
  },
};

App.confirm = function (message, onYes, yesLabel = 'Supprimer') {
  App.modal.open({
    title: 'Confirmation',
    body: App.h('p', {}, message),
    footer: [
      App.h('button', { class: 'btn', onclick: () => App.modal.close() }, 'Annuler'),
      App.h('button', {
        class: 'btn danger',
        onclick: async () => { App.modal.close(); await onYes(); },
      }, yesLabel),
    ],
  });
};

/* ---------- formulaires ---------- */
App.field = function (label, input, opts = {}) {
  return App.h('div', { class: `field${opts.full ? ' full' : ''}` },
    App.h('label', {}, label), input,
    opts.hint ? App.h('span', { class: 'hint' }, opts.hint) : null);
};

/* Explication repliée : présente pour qui la cherche, silencieuse sinon.
   Réservée au pédagogique — un avertissement reste toujours visible. */
App.note = function (summary, ...children) {
  return App.h('details', { class: 'note' },
    App.h('summary', {}, summary), ...children);
};

App.input = function (name, attrs = {}) {
  return App.h('input', Object.assign({ type: 'text', name }, attrs));
};

App.select = function (name, options, value, attrs = {}) {
  const sel = App.h('select', Object.assign({ name }, attrs));
  for (const opt of options) {
    const [val, label] = Array.isArray(opt) ? opt : [opt, opt];
    const node = App.h('option', { value: val }, label);
    if (String(val) === String(value)) node.selected = true;
    sel.append(node);
  }
  return sel;
};

App.formValues = function (form) {
  const out = {};
  for (const el of form.querySelectorAll('[name]')) {
    out[el.name] = el.type === 'checkbox' ? el.checked : el.value;
  }
  return out;
};

/* ---------- graphiques ---------- */
/* Palette des graphiques : les dix couleurs « classes d'actifs » du design
   system (--actif-1..10), relues à chaque changement de thème. Elles sont
   volontairement hors palette de marque : sur un camembert, il faut
   distinguer une part de sa voisine avant de faire joli. */
App.chartColors = ['#2E6BE6', '#E07A1F', '#12A15C', '#8B5CF6', '#DB2E7C',
  '#0E93B8', '#A8801A', '#D6432F', '#64748B', '#6C9C1F'];

App.readPalette = function () {
  const cs = getComputedStyle(document.documentElement);
  const fallback = App.chartColors;
  App.chartColors = fallback.map(
    (defaut, i) => cs.getPropertyValue(`--actif-${i + 1}`).trim() || defaut);
  return App.chartColors;
};

App.setTheme = function (theme) {
  document.documentElement.setAttribute('data-theme', theme);
  try { localStorage.setItem('patrimoine.theme', theme); } catch (e) { /* ignore */ }
  App.readPalette();
  const btn = App.el('#toggle-theme');
  if (btn) btn.innerHTML = theme === 'dark' ? '&#9788;' : '&#9789;';
};

App.currentTheme = () => document.documentElement.getAttribute('data-theme') || 'light';

/* Masquage des montants. Activé par défaut : on choisit d'afficher ses
   chiffres, on ne les découvre pas par surprise devant témoin. */
App.setPrivacy = function (on) {
  document.body.classList.toggle('privacy', on);
  try { localStorage.setItem('patrimoine.privacy', on ? '1' : '0'); } catch (e) { /* ignore */ }
  const btn = App.el('#toggle-privacy');
  if (btn) {
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    btn.title = on ? 'Afficher les montants' : 'Masquer les montants';
    btn.innerHTML = on ? '&#128065;' : '&#128584;';
  }
};

App.privacyOn = () => document.body.classList.contains('privacy');

App.chart = function (canvasId, config) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || typeof Chart === 'undefined') return null;
  if (App.state.charts[canvasId]) App.state.charts[canvasId].destroy();
  const css = getComputedStyle(document.body);
  const read = (name, fallback) => css.getPropertyValue(name).trim() || fallback;
  const grid = read('--line-soft', '#1e222a');
  const muted = read('--muted', '#7d8695');
  const text = read('--text', '#e8eaee');
  const card = read('--card', '#171a21');
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.font.size = 11.5;

  const defaults = {
    responsive: true,
    maintainAspectRatio: false,
    // Même courbe et même durée que les transitions CSS : tout bouge ensemble.
    animation: reduced ? false : { duration: 620, easing: 'easeOutQuart' },
    animations: reduced ? {} : { colors: false },
    transitions: { active: { animation: { duration: 180 } } },
    plugins: {
      legend: {
        labels: {
          color: muted, boxWidth: 8, boxHeight: 8,
          usePointStyle: true, pointStyle: 'circle', padding: 14,
        },
      },
      tooltip: {
        backgroundColor: card,
        titleColor: text,
        bodyColor: muted,
        borderColor: read('--line', '#262b35'),
        borderWidth: 1,
        padding: 11,
        cornerRadius: 9,
        displayColors: true,
        boxPadding: 5,
        usePointStyle: true,
        titleFont: { weight: '600' },
      },
    },
    scales: config.type === 'doughnut' || config.type === 'pie' ? undefined : {
      x: {
        border: { display: false },
        grid: { display: false },
        ticks: { color: muted, maxRotation: 0, autoSkipPadding: 12 },
      },
      y: {
        border: { display: false },
        grid: { color: grid },
        ticks: { color: muted, padding: 8 },
      },
    },
  };
  config.options = App.deepMerge(defaults, config.options || {});
  App.state.charts[canvasId] = new Chart(canvas, config);
  return App.state.charts[canvasId];
};

/* Anime un changement de mise en page (FLIP).

   Aucune transition CSS ne sait interpoler un changement de grille : passer une
   carte en pleine largeur fait sauter toutes les autres. On mesure donc les
   positions AVANT, on applique la modification, on mesure APRÈS, puis on
   ramène visuellement chaque élément à sa place d'origine et on le laisse
   rejouer le trajet.

   Seule la position est animée, pas la taille : mettre une carte à l'échelle
   déformerait son texte le temps du mouvement. */
App.flip = function (elements, muter, duree) {
  const reduit = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const avant = new Map();
  for (const el of elements) avant.set(el, el.getBoundingClientRect());

  muter();

  if (reduit) return;
  for (const el of elements) {
    const a = avant.get(el);
    const b = el.getBoundingClientRect();
    if (!a || !b.width) continue;
    const dx = a.left - b.left;
    const dy = a.top - b.top;
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1) continue;
    el.animate(
      [{ transform: `translate(${dx}px, ${dy}px)` }, { transform: 'none' }],
      { duration: duree || 420, easing: 'cubic-bezier(.2,.75,.3,1)' },
    );
  }
};

App.deepMerge = function (a, b) {
  const out = Object.assign({}, a);
  for (const [k, v] of Object.entries(b || {})) {
    out[k] = (v && typeof v === 'object' && !Array.isArray(v) && a && typeof a[k] === 'object')
      ? App.deepMerge(a[k], v) : v;
  }
  return out;
};

/* ---------- divers ---------- */
App.todayISO = () => new Date().toISOString().slice(0, 10);
App.monthISO = () => new Date().toISOString().slice(0, 7);

App.shiftMonth = function (ym, delta) {
  const [y, m] = ym.split('-').map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
};

App.categoriesAll = function () {
  const meta = App.state.meta || {};
  return [...(meta.categories_depenses || []), ...(meta.categories_revenus || []),
    'Non categorise'];
};
