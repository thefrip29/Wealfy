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
  /* Lecture commune : le serveur répond en JSON, sauf quand il tombe avant
     d'y arriver — auquel cas le corps est du texte, et le message d'erreur
     doit tout de même remonter. */
  async lire(res) {
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = { error: text }; }
    if (!res.ok) throw new Error((data && data.error) || `Erreur ${res.status}`);
    return data;
  },
  async request(method, url, payload) {
    const opts = { method, headers: {} };
    if (payload !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(payload);
    }
    return App.api.lire(await fetch(url, opts));
  },
  /* Envoi d'un fichier. Pas de `Content-Type` posé à la main : le navigateur
     doit écrire lui-même la frontière du multipart. */
  async upload(url, file) {
    const form = new FormData();
    form.append('fichier', file);
    return App.api.lire(await fetch(url, { method: 'POST', body: form }));
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
  /* 'MM-JJ' -> « 31 décembre ». La date de crédit des intérêts n'a pas
     d'année : elle revient tous les ans. */
  jourMois(md) {
    const m = /^(\d{2})-(\d{2})$/.exec(String(md || ''));
    if (!m) return '—';
    return new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'long' })
      .format(new Date(2001, Number(m[1]) - 1, Number(m[2])));
  },
  /* Les familles d'actifs sont des clés sans accent (`ASSET_TYPES` dans
     app/db.py), aussi lues par advisor.py et par les réglages enregistrés :
     les accentuer à la source casserait ces correspondances. On les habille
     donc à l'affichage seulement. Une famille venue d'un type personnalisé
     n'est pas dans la table et ressort telle quelle. */
  famille(nom) {
    return {
      'Liquidites': 'Liquidités',
      'Epargne reglementee': 'Épargne réglementée',
      'Marches financiers': 'Marchés financiers',
      'Immobilier': 'Immobilier',
      'Crypto': 'Crypto',
      'Biens': 'Biens',
      'Autre': 'Autre',
    }[nom] || nom;
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
const FOCUSABLES = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

App.modal = {
  /* `garder` protège une saisie longue. Un clic à côté de la modale d'import
     emportait un relevé de trois cents lignes, sans un mot.

     Pas de modale de confirmation par-dessus : il n'y en a qu'une dans la page,
     et l'ouvrir détruirait justement le formulaire qu'on cherche à sauver. Le
     geste est donc redemandé — un second Échap, ou un second clic à côté, dans
     les quelques secondes qui suivent. Le bouton « Annuler » ferme toujours du
     premier coup : lui est explicite. */
  open({ title, body, footer, wide, garder }) {
    App.el('#modal-title').textContent = title || '';
    const bodyHost = App.el('#modal-body');
    const footHost = App.el('#modal-foot');
    App.clear(bodyHost); App.clear(footHost);
    if (body) bodyHost.append(body);
    if (footer) footHost.append(...[].concat(footer));
    App.el('#modal').classList.toggle('wide', !!wide);
    App.el('#modal-backdrop').hidden = false;
    document.body.style.overflow = 'hidden';
    App.modal.garder = !!garder;
    App.modal.abandonArme = false;
    // Où revenir en fermant : sans cela, le focus repart au début du document
    // et la navigation au clavier recommence de zéro à chaque modale.
    App.modal.retour = document.activeElement;
    const first = bodyHost.querySelector('input, select, textarea');
    if (first) setTimeout(() => first.focus(), 30);
  },

  /* Vrai si la modale porte une saisie qu'une fermeture perdrait. */
  saisieEnCours() {
    if (!App.modal.garder) return false;
    return App.els('input, textarea', App.el('#modal-body'))
      .some((c) => c.type !== 'checkbox' && c.type !== 'radio' && c.value.trim());
  },

  /* Fermeture demandée par un geste ambigu (Échap, clic hors cadre). Renvoie
     vrai si la modale s'est effectivement fermée. */
  demanderFermeture() {
    if (!App.modal.saisieEnCours() || App.modal.abandonArme) {
      App.modal.close();
      return true;
    }
    App.modal.abandonArme = true;
    App.toast('Recommencez le geste pour abandonner cette saisie.', 'info', 4000);
    clearTimeout(App.modal.minuterie);
    App.modal.minuterie = setTimeout(() => { App.modal.abandonArme = false; }, 4000);
    return false;
  },

  close() {
    clearTimeout(App.modal.minuterie);
    App.modal.garder = false;
    App.modal.abandonArme = false;
    App.el('#modal-backdrop').hidden = true;
    document.body.style.overflow = '';
    App.clear(App.el('#modal-body'));
    App.clear(App.el('#modal-foot'));
    const retour = App.modal.retour;
    App.modal.retour = null;
    if (retour && retour.isConnected && retour.focus) retour.focus();
  },

  /* Enferme la tabulation dans la modale. Sans cela, Tab en sort et parcourt
     la page derrière, qui est pourtant inatteignable à la souris. */
  piegerFocus(e) {
    if (e.key !== 'Tab' || App.el('#modal-backdrop').hidden) return;
    const cibles = App.els(FOCUSABLES, App.el('#modal'))
      .filter((n) => !n.disabled && n.offsetParent !== null);
    if (!cibles.length) return;
    const premier = cibles[0];
    const dernier = cibles[cibles.length - 1];
    if (e.shiftKey && document.activeElement === premier) {
      e.preventDefault();
      dernier.focus();
    } else if (!e.shiftKey && document.activeElement === dernier) {
      e.preventDefault();
      premier.focus();
    }
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

/* Liste « libellé / valeur ». Le même bloc était réécrit à la main sept fois.

   Il porte aussi la marque des MONTANTS, et c'est le point important : le
   masquage de la barre du haut floutait tout `.m-value`, donc « État : activé »
   dans les réglages, « Ouvert le 12/03/2020 » sur une fiche, ou « Échéances
   payées : 24 / 240 » sur un prêt. Rien de tout cela n'est un montant.

   La marque est déduite du symbole monétaire, que seul `App.fmt.eur` produit.
   Un pourcentage ou une date n'en portent pas, et ne sont donc pas masqués. */
App.metricList = function (rows) {
  const list = App.h('div', { class: 'metric-list' });
  for (const [label, valeur] of rows) {
    const monetaire = typeof valeur === 'string' && valeur.includes('€');
    list.append(App.h('div', { class: 'metric-row' },
      App.h('span', { class: 'm-label' }, label),
      App.h('span', { class: `m-value${monetaire ? ' montant' : ''}` }, valeur)));
  }
  return list;
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

/* Signale un champ obligatoire manquant ou invalide, SUR LE CHAMP.

   C'était un toast : il s'affichait en bas à droite, à l'opposé du regard,
   disparaissait au bout de 3,6 s, et ne disait pas lequel des huit champs
   était en cause. Ici le champ est marqué, ramené sous le curseur, et le
   message sort de l'infobulle native du navigateur — à côté de lui.

   Renvoie toujours `false`, pour s'écrire `return App.invalide(...)` là où on
   écrivait `return App.toast(...)`. */
App.invalide = function (form, name, message) {
  const champ = form && form.querySelector(`[name="${name}"]`);
  // Un champ de date est un conteneur : c'est sa partie visible qui reçoit la
  // marque, le champ nommé étant caché (voir `App.dateField`).
  const cible = champ && champ.type === 'hidden'
    ? champ.parentElement.querySelector('.date-saisie') : champ;
  if (!cible) {
    App.toast(message, 'error');
    return false;
  }
  cible.classList.add('invalide');
  cible.setCustomValidity(message);
  if (cible.reportValidity) cible.reportValidity(); else cible.focus();
  const nettoyer = () => {
    cible.classList.remove('invalide');
    cible.setCustomValidity('');
  };
  cible.addEventListener('input', nettoyer, { once: true });
  cible.addEventListener('change', nettoyer, { once: true });
  return false;
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

/* ---------- champ de date ----------

   `<input type="date">` n'affiche pas le format qu'on lui demande : Chromium
   ignore `<html lang="fr">` pour ce widget et suit le format regional du
   systeme. Sur un Windows configure en anglais, les neuf champs de saisie
   passaient en MM/JJ/AAAA pendant que tout le reste de l'application sortait
   deja de `App.fmt.date`, en fr-FR. Forcer la langue du moteur ne change rien
   non plus : c'est un defaut connu de WebView2, sans autre contournement
   qu'un champ maison.

   La valeur ISO part dans un `<input type="hidden">` qui porte le `name` :
   `App.formValues` ne lit que les elements nommes, donc pas un seul appelant
   n'a eu a changer sa fonction d'enregistrement. */

const JOURS_COURTS = ['L', 'M', 'M', 'J', 'V', 'S', 'D'];
const moisCourtFmt = new Intl.DateTimeFormat('fr-FR', { month: 'short' });

/* ISO vers JJ/MM/AAAA par decoupage de chaine : passer par `Date` ferait
   entrer un fuseau horaire dans une conversion qui n'en a pas besoin. */
function isoVersFR(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''));
  return m ? `${m[3]}/${m[2]}/${m[1]}` : '';
}

function isoDepuis(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/* JJ/MM/AAAA vers ISO : l'inverse de `App.fmt.date`, qui manquait. */
App.parseDateFR = function (texte) {
  const brut = String(texte || '').trim();
  if (!brut) return null;
  let a; let m; let j;
  // Une date ISO collee depuis un tableur doit passer aussi.
  const iso = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(brut);
  const fr = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})$/.exec(brut);
  const nu = /^(\d{2})(\d{2})(\d{2}|\d{4})$/.exec(brut);   // 18082026, ou 180826
  if (iso) [, a, m, j] = iso;
  else if (fr) [, j, m, a] = fr;
  else if (nu) [, j, m, a] = nu;
  else return null;

  a = Number(a); m = Number(m); j = Number(j);
  // Deux chiffres : le siecle courant. Un patrimoine ne se saisit pas en 1926.
  if (a < 100) a += 2000;
  if (m < 1 || m > 12 || j < 1 || a < 1000) return null;
  const d = new Date(a, m - 1, j);
  // Sans ce controle, un 31 fevrier ressortirait en 3 mars sans un mot.
  if (d.getFullYear() !== a || d.getMonth() !== m - 1 || d.getDate() !== j) return null;
  return isoDepuis(d);
};

/* ---------- calendrier ----------
   Attache au `<body>` en position fixe, et non dans le champ : la modale et
   les panneaux defilants ont des `overflow` qui rognaient la fenetre des
   qu'elle depassait d'un bord. */

let calendrierOuvert = null;

function clicHorsCalendrier(e) {
  if (!calendrierOuvert) return;
  if (calendrierOuvert.contains(e.target)) return;
  if (calendrierOuvert.ancre && calendrierOuvert.ancre.contains(e.target)) return;
  App.fermerCalendrier();
}

App.fermerCalendrier = function () {
  if (!calendrierOuvert) return;
  const pop = calendrierOuvert;
  calendrierOuvert = null;
  document.removeEventListener('mousedown', clicHorsCalendrier, true);
  window.removeEventListener('resize', App.fermerCalendrier);
  window.removeEventListener('scroll', App.fermerCalendrier, true);
  pop.classList.add('sortant');
  setTimeout(() => pop.remove(), 120);
};

/* `mode` vaut 'jour' ou 'mois'. `onPick` recoit un ISO complet en mode jour,
   un 'AAAA-MM' en mode mois. */
App.calendrier = function ({ ancre, iso, mode = 'jour', onPick }) {
  const memeAncre = calendrierOuvert && calendrierOuvert.ancre === ancre;
  App.fermerCalendrier();
  if (memeAncre) return;          // second clic sur le meme bouton : on referme

  const pop = App.h('div', {
    class: 'calendrier', role: 'dialog', 'aria-label': 'Choisir une date',
  });
  pop.ancre = ancre;

  const choisi = /^\d{4}-\d{2}-\d{2}$/.test(iso || '') ? iso : null;
  const ancrage = choisi || (/^\d{4}-\d{2}$/.test(iso || '') ? `${iso}-01` : null);
  const depart = ancrage ? new Date(`${ancrage}T00:00:00`) : new Date();
  let curseur = new Date(depart.getFullYear(), depart.getMonth(), 1);
  let vue = mode;

  const rendre = () => {
    App.clear(pop);
    const annee = curseur.getFullYear();
    const mois = curseur.getMonth();
    const pas = vue === 'mois' ? 12 : 1;
    const titre = vue === 'mois' ? String(annee)
      : App.fmt.month(`${annee}-${String(mois + 1).padStart(2, '0')}`);

    pop.append(App.h('div', { class: 'cal-tete' },
      App.h('button', {
        type: 'button', class: 'cal-nav', 'aria-label': 'Précédent',
        onclick: () => { curseur.setMonth(mois - pas); rendre(); },
      }, '‹'),
      App.h('button', {
        type: 'button', class: 'cal-titre',
        // Le titre est un bouton : il passe aux mois, puis revient aux jours.
        // Remonter a mars 2019 demandait sinon quatre-vingts clics.
        onclick: () => { vue = vue === 'mois' ? 'jour' : 'mois'; rendre(); },
        disabled: mode === 'mois' || null,
      }, titre),
      App.h('button', {
        type: 'button', class: 'cal-nav', 'aria-label': 'Suivant',
        onclick: () => { curseur.setMonth(mois + pas); rendre(); },
      }, '›')));

    if (vue === 'mois') {
      const grilleMois = App.h('div', { class: 'cal-mois' });
      for (let i = 0; i < 12; i += 1) {
        const ym = `${annee}-${String(i + 1).padStart(2, '0')}`;
        grilleMois.append(App.h('button', {
          type: 'button',
          class: `cal-case${(iso || '').slice(0, 7) === ym ? ' choisi' : ''}`,
          onclick: () => {
            if (mode === 'mois') { onPick(ym); App.fermerCalendrier(); return; }
            curseur = new Date(annee, i, 1); vue = 'jour'; rendre();
          },
        }, moisCourtFmt.format(new Date(annee, i, 1)).replace('.', '')));
      }
      pop.append(grilleMois);
      return;
    }

    const semaine = App.h('div', { class: 'cal-semaine' });
    for (const j of JOURS_COURTS) semaine.append(App.h('span', {}, j));
    pop.append(semaine);

    const grille = App.h('div', { class: 'cal-jours' });
    const premier = new Date(annee, mois, 1);
    // `getDay()` compte a partir de dimanche ; en France la semaine ouvre le
    // lundi, d'ou le decalage.
    const decalage = (premier.getDay() + 6) % 7;
    const aujourdhui = App.todayISO();
    for (let i = 0; i < 42; i += 1) {
      const jour = new Date(annee, mois, 1 + i - decalage);
      const isoJour = isoDepuis(jour);
      const dehors = jour.getMonth() !== mois;
      grille.append(App.h('button', {
        type: 'button',
        class: `cal-case${dehors ? ' hors' : ''}${isoJour === choisi ? ' choisi' : ''}`
          + `${isoJour === aujourdhui ? ' aujourdhui' : ''}`,
        onclick: () => { onPick(isoJour); App.fermerCalendrier(); },
      }, String(jour.getDate())));
    }
    pop.append(grille);

    pop.append(App.h('div', { class: 'cal-pied' },
      App.h('button', {
        type: 'button', class: 'cal-lien',
        onclick: () => { onPick(aujourdhui); App.fermerCalendrier(); },
      }, 'Aujourd’hui')));
  };

  const placer = () => {
    const r = ancre.getBoundingClientRect();
    const h = pop.offsetHeight;
    const l = pop.offsetWidth;
    // Bascule au-dessus quand le bas de la fenetre est trop proche, et rentre
    // le bord droit : dans une modale etroite, le calendrier sortait a droite.
    const enHaut = r.bottom + h + 8 > window.innerHeight && r.top - h - 8 > 0;
    pop.style.top = `${enHaut ? r.top - h - 6 : r.bottom + 6}px`;
    pop.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - l - 8))}px`;
  };

  // `stopPropagation` : sans lui, Echap fermait la modale entiere derriere le
  // calendrier, et la saisie en cours avec elle.
  pop.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    e.stopPropagation();
    App.fermerCalendrier();
    ancre.focus();
  });

  rendre();
  document.body.append(pop);
  placer();
  calendrierOuvert = pop;
  document.addEventListener('mousedown', clicHorsCalendrier, true);
  window.addEventListener('resize', App.fermerCalendrier);
  window.addEventListener('scroll', App.fermerCalendrier, true);
  const cible = pop.querySelector('.choisi') || pop.querySelector('.cal-case:not(.hors)');
  if (cible) cible.focus();
};

const ICONE_CAL = '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"'
  + ' fill="none" stroke="currentColor" stroke-width="1.4">'
  + '<rect x="1.7" y="3" width="12.6" height="11.3" rx="1.6"/>'
  + '<path d="M1.7 6.6h12.6M5 1.7v2.6M11 1.7v2.6"/></svg>';

/* Champ de date : saisie masquee JJ/MM/AAAA, plus un calendrier. Se pose la
   ou on ecrivait `App.input(nom, { type: 'date' })`. */
App.dateField = function (name, attrs = {}) {
  const cache = App.h('input', { type: 'hidden', name, value: attrs.value || '' });
  const texte = App.h('input', {
    type: 'text', class: 'date-saisie', inputmode: 'numeric', maxlength: '10',
    placeholder: 'JJ/MM/AAAA', autocomplete: 'off', spellcheck: 'false',
    value: isoVersFR(attrs.value), required: attrs.required || null,
  });
  const bouton = App.h('button', {
    type: 'button', class: 'date-cal', tabindex: '-1',
    'aria-label': 'Ouvrir le calendrier', html: ICONE_CAL,
  });

  const controler = () => {
    const iso = App.parseDateFR(texte.value);
    cache.value = iso || '';
    const vide = !texte.value.trim();
    if (vide) texte.setCustomValidity(attrs.required ? 'Saisissez une date.' : '');
    else texte.setCustomValidity(iso ? '' : 'Date invalide. Format attendu : JJ/MM/AAAA.');
    texte.classList.toggle('invalide', !vide && !iso);
    if (attrs.onpick) attrs.onpick(cache.value);
  };

  texte.addEventListener('input', () => {
    // On ne replace les barres obliques que si le curseur est en fin de champ :
    // sinon corriger un chiffre au milieu le renvoyait a la fin a chaque
    // frappe. Une saisie retouchee est normalisee au `blur`.
    if (texte.selectionStart === texte.value.length) {
      const chiffres = texte.value.replace(/\D/g, '').slice(0, 8);
      let out = chiffres.slice(0, 2);
      if (chiffres.length > 2) out += `/${chiffres.slice(2, 4)}`;
      if (chiffres.length > 4) out += `/${chiffres.slice(4, 8)}`;
      texte.value = out;
    }
    controler();
  });
  texte.addEventListener('blur', () => {
    const iso = App.parseDateFR(texte.value);
    if (iso) texte.value = isoVersFR(iso);
    controler();
  });
  bouton.addEventListener('click', () => App.calendrier({
    ancre: bouton, iso: cache.value, mode: 'jour',
    onPick: (iso) => { texte.value = isoVersFR(iso); controler(); texte.focus(); },
  }));

  controler();
  // L'ordre compte : `App.modal.open` donne le focus au premier `input` venu,
  // et le champ cache le capterait s'il passait devant.
  const hote = App.h('div', { class: 'date-field' }, texte, bouton, cache);

  // Le champ natif se lisait en `.value`, et des appelants le font encore
  // (`openQuickAdd`). Le conteneur repond donc comme un input, en ISO.
  Object.defineProperty(hote, 'value', {
    get: () => cache.value,
    set: (iso) => { texte.value = isoVersFR(iso); controler(); },
  });
  return hote;
};

/* ---------- dépôt de fichier ----------

   Le seul chemin d'import était le collage dans un textarea : ouvrir le CSV
   dans un éditeur, tout sélectionner, copier, coller. Le fichier est pourtant
   déjà sur le disque.

   La conversion se fait côté serveur et non par `FileReader`, pour une raison
   précise : un PDF ne se lit pas en JavaScript sans embarquer une bibliothèque
   entière, alors que Python le fait déjà. Le texte extrait REVIENT dans le
   champ, visible et modifiable — l'extraction d'un PDF est imparfaite par
   nature, la cacher reviendrait à demander une confiance aveugle. */

const FORMATS_RELEVE = '.csv,.tsv,.txt,.pdf,text/plain,text/csv,application/pdf';

App.fileDrop = function ({ onText, hint }) {
  const input = App.h('input', { type: 'file', accept: FORMATS_RELEVE, hidden: true });
  const etat = App.h('div', { class: 'depot-etat' });
  const zone = App.h('div', {
    class: 'depot', role: 'button', tabindex: '0',
    'aria-label': 'Choisir un fichier de relevé',
  },
  App.h('div', { class: 'depot-titre' },
    'Déposez votre relevé ici, ou cliquez pour le choisir'),
  App.h('div', { class: 'depot-sub' },
    hint || 'CSV, TSV, TXT, ou PDF téléchargé depuis votre banque'),
  etat, input);

  const charger = async (file) => {
    if (!file) return;
    zone.classList.add('occupe');
    App.clear(etat);
    etat.append(App.h('span', { class: 'sub' }, `Lecture de ${file.name}...`));
    try {
      const res = await App.api.upload('/api/imports/text', file);
      App.clear(etat);
      etat.append(App.h('span', { class: 'pill ok' }, file.name));
      onText(res.text, res.nom || file.name);
    } catch (e) {
      App.clear(etat);
      etat.append(App.h('span', { class: 'pill warn' }, e.message));
    }
    zone.classList.remove('occupe');
    // Redéposer le MÊME fichier doit relancer la lecture : sans cette remise à
    // zéro, `change` ne se déclenche pas une seconde fois.
    input.value = '';
  };

  zone.addEventListener('click', () => input.click());
  zone.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    e.preventDefault();
    input.click();
  });
  // Sans cela, le clic sur le champ caché remonte a la zone, qui le rouvre.
  input.addEventListener('click', (e) => e.stopPropagation());
  input.addEventListener('change', () => charger(input.files[0]));

  for (const nom of ['dragenter', 'dragover']) {
    zone.addEventListener(nom, (e) => { e.preventDefault(); zone.classList.add('survol'); });
  }
  zone.addEventListener('dragleave', () => zone.classList.remove('survol'));
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('survol');
    charger(e.dataTransfer.files[0]);
  });
  return zone;
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

/* Thème : trois choix, « système » compris.

   `App.THEMES` est l'ordre du cycle du bouton. La valeur mémorisée est le
   CHOIX (clair / sombre / systeme), pas l'apparence obtenue : sans cette
   distinction, « système » serait indiscernable d'un choix figé, et c'est
   exactement ce qui rendait l'ancienne version incapable de suivre l'OS. */
App.CLE_THEME = 'wealfy.theme';
App.THEMES = ['systeme', 'clair', 'sombre'];

App.themeChoisi = function () {
  try {
    const v = localStorage.getItem(App.CLE_THEME);
    if (App.THEMES.includes(v)) return v;
  } catch (e) { /* ignore */ }
  return 'systeme';
};

App.systemeEnSombre = () => window.matchMedia('(prefers-color-scheme: dark)').matches;

/* Applique un choix. `memoriser` est faux quand l'appel vient du système qui
   change d'avis : on repeint sans transformer un suivi automatique en choix
   figé. C'est la précaution qui manquait — `setTheme` écrivait à chaque
   démarrage, donc la première lecture du système devenait définitive. */
App.setTheme = function (choix, memoriser = true) {
  const sombre = choix === 'sombre' || (choix === 'systeme' && App.systemeEnSombre());
  document.documentElement.setAttribute('data-theme', sombre ? 'dark' : 'light');
  if (memoriser) {
    try { localStorage.setItem(App.CLE_THEME, choix); } catch (e) { /* ignore */ }
  }
  App.readPalette();

  const btn = App.el('#toggle-theme');
  if (btn) {
    const etats = {
      systeme: ['&#9681;', 'Thème : système'],      // cercle mi-plein
      clair: ['&#9788;', 'Thème : clair'],          // soleil
      sombre: ['&#9789;', 'Thème : sombre'],        // lune
    };
    const [icone, titre] = etats[choix] || etats.systeme;
    btn.innerHTML = icone;
    btn.title = `${titre} (cliquer pour changer)`;
    btn.dataset.choix = choix;
  }
};

/* Suit l'OS en direct, mais seulement tant que le choix est « système ». Sans
   cet écouteur, la bascule jour/nuit de macOS ne se voyait qu'au redémarrage. */
App.suivreThemeSysteme = function () {
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  const reagir = () => {
    if (App.themeChoisi() === 'systeme') App.setTheme('systeme', false);
  };
  if (mq.addEventListener) mq.addEventListener('change', reagir);
  else if (mq.addListener) mq.addListener(reagir);       // WebKit ancien
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
/* Date locale, et non `toISOString()` qui convertit en UTC : en France, entre
   minuit et deux heures, celui-ci renvoyait la veille. Toutes les dates par
   defaut des formulaires etaient alors fausses d'un jour, et en desaccord
   avec le serveur qui, lui, lit `date.today()` a l'heure locale. */
App.todayISO = () => isoDepuis(new Date());
App.monthISO = () => App.todayISO().slice(0, 7);

/* Date d'arrêt d'un mois : son dernier jour, ou aujourd'hui si le mois est en
   cours. C'est la règle que `/api/overview` applique déjà côté serveur
   (`min(dernier_jour, date.today())`) ; l'onglet Patrimoine s'y aligne pour que
   les deux écrans parlent du même instant. */
App.monthAsOf = function (ym) {
  const [y, m] = String(ym || '').split('-').map(Number);
  if (!y || !m) return App.todayISO();
  const dernier = new Date(y, m, 0);          // jour 0 du mois suivant
  const aujourdhui = new Date();
  return isoDepuis(dernier < aujourdhui ? dernier : aujourdhui);
};

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
