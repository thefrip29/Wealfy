/* Amorçage : navigation par onglets, sélecteur de mois, rafraîchissements. */
App.currentTab = 'overview';

App.loadMeta = async function () {
  App.state.meta = await App.api.get('/api/meta');
};

App.loadRefs = async function () {
  const [portfolio, liabilities, market] = await Promise.all([
    App.api.get('/api/assets'),
    App.api.get('/api/liabilities'),
    App.api.get('/api/market/status'),
  ]);
  App.state.assets = portfolio.assets;
  App.state.liabilities = liabilities;
  App.state.portfolio = portfolio;
  App.state.market = market;
};

/* Rangées dont les cellules entrent une par une, au lieu d'arriver d'un bloc
   au milieu du déroulement.

   RÈGLE : seuls des conteneurs qui ne dessinent RIEN peuvent figurer ici. Une
   rangée dépliée n'est jamais animée elle-même — seules ses cellules le sont.
   Si elle porte une bordure ou un fond, ce décor reste donc immobile pendant
   que son contenu s'en va, puis disparaît d'un coup à la fin.

   C'est précisément ce qui arrivait au filet sous le héros : `.hero` figurait
   dans cette liste alors qu'il porte un `border-bottom`. La ligne grise restait
   figée à l'écran le temps de la transition. Le héros s'anime donc désormais
   d'un seul tenant, bordure comprise — ses deux cellules forment de toute façon
   un même bloc de lecture, le chiffre et ses statistiques.

   `.grid-2`, `.kpi-grid` et `.hero-side` sont, eux, de purs conteneurs de mise
   en page : ils ne peignent ni bordure ni fond. */
const RANGEES = '.kpi-grid, .grid-2, .hero-side';
const RETARD_MAX = 9;   // au-delà, l'attente cesse d'être agréable

/* Joue l'animation d'entrée du panneau courant.

   Le marqueur et l'ordre sont posés ICI, au rendu, et plus jamais touchés
   ensuite : toute modification d'`animation-name` sur un élément déjà affiché
   relancerait l'animation. C'est ce qui faisait rejouer l'apparition juste
   après un changement de mois. */
App.playReveal = function (sens) {
  const zone = App.el('main');
  const panneau = App.el('.panel.active');
  if (!panneau) return;

  // Le marqueur est retiré de TOUS les panneaux, pas seulement du courant :
  // une transition interrompue en laissait derrière elle sur des panneaux
  // masqués, qui continuaient donc d'animer dans le vide.
  App.els('.panel.revealing').forEach((p) => p.classList.remove('revealing'));
  // Le contenu périmé peut réapparaître : il va être animé dès la ligne
  // suivante, donc recouvert immédiatement.
  App.els('.panel.attente').forEach((p) => p.classList.remove('attente'));
  App.els('.reveal-item', panneau).forEach((el) => {
    el.classList.remove('reveal-item');
    el.style.removeProperty('--i');
  });

  App.revealOrder(panneau).forEach((el, i) => {
    el.classList.add('reveal-item');
    el.style.setProperty('--i', Math.min(i, RETARD_MAX));
  });

  if (sens) {
    zone.dataset.slide = sens;
    // Distance de défilement = largeur de MAIN, pas celle du panneau.
    //
    // La découpe se fait au bord de `main` ; le panneau, lui, est en retrait de
    // la marge interne. Parcourir la largeur du panneau laissait donc dépasser
    // une bande de la page précédente, large exactement comme cette marge.
    // Le petit écart supplémentaire entre les deux mois (deux fois la marge)
    // défile en une vingtaine de millisecondes : invisible.
    zone.style.setProperty('--slide-dist', `${Math.ceil(zone.getBoundingClientRect().width)}px`);
  } else {
    delete zone.dataset.slide;
  }
  void panneau.offsetWidth;          // reflow : l'animation peut repartir
  panneau.classList.add('revealing');

  // Même image, même instant : la page qui part et celle qui arrive doivent
  // se mettre en mouvement ensemble, sinon ce n'est plus un défilement.
  const copies = App.els('.panel-leaving');
  if (copies.length) {
    copies.forEach((c) => c.classList.add('go'));
    clearTimeout(App.snapshotTimer);
    App.snapshotTimer = setTimeout(App.dropSnapshot, App.cssMs('--t-carousel', 560) + 80);
  }

  // Une fois l'apparition terminée, on retire tout ce qui la sert. Sans ce
  // nettoyage, `will-change` et le `filter: blur(0)` de la dernière image
  // maintiennent chaque bloc sur sa propre couche de composition : le texte y
  // est rendu légèrement plus flou, et le flou restait à l'écran jusqu'à la
  // transition suivante.
  const duree = sens ? App.cssMs('--t-carousel', 560) : App.cssMs('--t-reveal', 1050);
  const pas = sens ? App.cssMs('--carousel-step', 45) : App.cssMs('--reveal-step', 95);
  clearTimeout(App.revealTimer);
  App.revealTimer = setTimeout(() => {
    panneau.classList.remove('revealing');
    delete zone.dataset.slide;
  }, duree + pas * RETARD_MAX + 60);
};

/* Fige le panneau courant dans une copie posée par-dessus, le temps qu'elle
   sorte de l'écran. C'est ce qui donne l'impression de POUSSER le mois hors du
   cadre plutôt que de le voir disparaître pour laisser entrer le suivant. */
App.snapshotPanel = function () {
  const zone = App.el('main');
  const panneau = App.el('.panel.active');
  if (!panneau) return;
  App.dropSnapshot();

  const copie = panneau.cloneNode(true);
  copie.className = 'panel-leaving';
  copie.removeAttribute('id');
  // Aucun identifiant en double : App.el() renverrait sinon un élément de la
  // copie au lieu du vrai.
  copie.querySelectorAll('[id]').forEach((el) => el.removeAttribute('id'));

  // Un canevas cloné arrive VIDE : le clonage copie la balise, pas son dessin.
  // Sans ce report, les graphiques disparaîtraient pendant la transition.
  const source = panneau.querySelectorAll('canvas');
  copie.querySelectorAll('canvas').forEach((dst, i) => {
    const src = source[i];
    if (!src || !src.width || !src.height) return;
    dst.width = src.width;
    dst.height = src.height;
    try { dst.getContext('2d').drawImage(src, 0, 0); } catch (e) { /* rien à copier */ }
  });

  // Position exacte, mesurée : les marges de `main` changent selon la largeur
  // d'écran, les recopier en dur se désaligne.
  const r = panneau.getBoundingClientRect();
  const rz = zone.getBoundingClientRect();
  copie.style.top = `${r.top - rz.top + zone.scrollTop}px`;
  copie.style.left = `${r.left - rz.left}px`;
  copie.style.width = `${r.width}px`;

  // Le mois quitté sort d'un seul tenant : aucun décalage entre ses blocs.
  App.revealOrder(copie).forEach((el) => {
    el.classList.remove('reveal-item');
    el.classList.add('leaving-item');
    el.style.removeProperty('--i');
  });

  // La copie est hors flux : sans plancher, la page se replierait à la hauteur
  // du panneau d'arrivée — encore vide — puis se rouvrirait. La barre de
  // défilement sauterait deux fois pendant une transition censée être fluide.
  zone.style.minHeight = `${Math.ceil(r.height)}px`;

  // La copie est posée figée : sa sortie sera armée par `playReveal`, une fois
  // le nouveau contenu prêt, pour que les deux mouvements partent ensemble.
  zone.append(copie);
};

App.dropSnapshot = function () {
  clearTimeout(App.snapshotTimer);
  App.els('.panel-leaving').forEach((el) => el.remove());
  App.el('main').style.removeProperty('min-height');
};

App.cssMs = function (nom, defaut) {
  const v = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(nom));
  return Number.isFinite(v) ? v : defaut;
};

/* Ordre d'entrée/sortie : les rangées sont dépliées pour que leurs cellules
   se succèdent au lieu d'arriver d'un bloc. */
App.revealOrder = function (panneau) {
  const ordre = [];
  for (const bloc of panneau.children) {
    if (bloc.matches(RANGEES) && bloc.children.length) ordre.push(...bloc.children);
    else ordre.push(bloc);
  }
  return ordre;
};

/* Richesse des animations : le mode est posé dans l'en-tête du document, à
   partir du nombre de cœurs et de la mémoire. C'est une estimation, et elle peut
   se tromper — un processeur récent avec un affichage intégré modeste passe pour
   une bonne machine.

   On mesure donc la fluidité RÉELLE pendant la première animation, et on
   rétrograde si elle n'y est pas. La décision est mémorisée : elle vaut pour la
   machine, pas pour la session. Un choix explicite de l'utilisateur n'est jamais
   écrasé. */
App.CLE_ANIM = 'patrimoine.animations';

App.mesurerFluidite = function () {
  const racine = document.documentElement;
  if (racine.dataset.anim !== 'complet') return;      // déjà économe
  try {
    if (localStorage.getItem(App.CLE_ANIM)) return;   // choix explicite, on n'y touche pas
  } catch (e) { return; }

  const intervalles = [];
  let precedent = performance.now();
  let restant = 32;                                   // environ une demi-seconde

  const image = (t) => {
    intervalles.push(t - precedent);
    precedent = t;
    if (--restant > 0) { requestAnimationFrame(image); return; }

    // Médiane plutôt que moyenne : une seule image longue (un ramasse-miettes,
    // une fenêtre qui prend le focus) ne doit pas condamner la machine.
    intervalles.sort((a, b) => a - b);
    const mediane = intervalles[intervalles.length >> 1];
    if (mediane > 22) {                               // moins de ~45 images/s
      racine.dataset.anim = 'econome';
      try { localStorage.setItem(App.CLE_ANIM, 'economes'); } catch (e) { /* ignore */ }
    }
  };
  requestAnimationFrame(image);
};

/* Place le trait de navigation sous l'onglet actif.

   Mesuré plutôt que calculé : les quatre libellés n'ont pas la même longueur, et
   la barre se réorganise sur écran étroit. `offsetLeft` est relatif à `.tabs`,
   qui est le conteneur positionné — pas besoin de corriger le défilement. */
App.placeIndicator = function () {
  const barre = App.el('.tabs');
  const trait = App.el('.tab-indicator');
  const actif = App.el('.tab.active');
  if (!barre || !trait || !actif) return;

  // Le trait s'arrête à la marge interne du bouton, comme l'ancien ::after :
  // il souligne le mot, pas la zone cliquable.
  const marge = parseFloat(getComputedStyle(actif).paddingLeft) || 0;
  barre.style.setProperty('--indicator-x', `${actif.offsetLeft + marge}px`);
  barre.style.setProperty('--indicator-w', `${actif.offsetWidth - 2 * marge}px`);

  // Première pose sans animation, sinon le trait arriverait en glissant depuis
  // le bord gauche au chargement de la page.
  if (!barre.classList.contains('indicator-pret')) {
    void barre.offsetWidth;
    barre.classList.add('indicator-pret');
  }
};

/* Numéro de la dernière transition demandée.

   `showTab` attend le chargement des données au milieu de son travail. Pendant
   cette attente, un second clic pouvait démarrer une transition par-dessus la
   première : deux animations d'entrée se lançaient, et le panneau abandonné
   gardait ses marqueurs. Chaque appel prend donc un numéro et, au retour de
   l'attente, abandonne s'il n'est plus le dernier. */
App.transition = 0;

App.showTab = async function (name, sens) {
  // Les onglets sont ordonnés de gauche à droite, comme les mois : aller vers
  // « Patrimoine » depuis « Dépenses », c'est avancer. Le sens se déduit donc
  // de leur position, sans avoir à le préciser à l'appel.
  if (sens === undefined) {
    const ordre = App.els('.tab').map((b) => b.dataset.tab);
    const depuis = ordre.indexOf(App.currentTab);
    const vers = ordre.indexOf(name);
    if (depuis >= 0 && vers >= 0 && vers !== depuis) sens = vers > depuis ? 'next' : 'prev';
  }

  // La copie de ce qu'on quitte est figée AVANT le basculement : après, le
  // panneau courant a déjà changé et il n'y aurait plus rien à faire sortir.
  if (sens) App.snapshotPanel(); else App.dropSnapshot();

  const numero = ++App.transition;

  App.currentTab = name;
  App.els('.tab').forEach((b) => b.classList.toggle('active', b.dataset.tab === name));
  App.els('.panel').forEach((p) => p.classList.toggle('active', p.id === `tab-${name}`));
  // Le trait part tout de suite, avec le changement de libellé : il accompagne
  // le clic au lieu d'attendre la fin du chargement des données.
  App.placeIndicator();

  // Un panneau garde le contenu de la visite précédente jusqu'à ce que le
  // chargement le remplace. Sans ce masque, ce vieux contenu s'affichait
  // pendant l'aller-retour serveur : un bref reste de l'ancienne page, visible
  // partout où la copie sortante ne le recouvrait pas.
  App.el(`#tab-${name}`).classList.add('attente');

  try {
    await App.tabs[name].load();
  } catch (e) {
    App.toast(e.message, 'error');
  }
  // Une transition plus récente est passée devant pendant le chargement : elle
  // a déjà pris la main sur l'affichage, et jouer celle-ci par-dessus ferait
  // repartir une animation sur un panneau qui n'est plus le sien.
  if (numero !== App.transition) return;

  // Après le rendu du contenu : les cellules des rangées existent enfin.
  App.playReveal(sens);
};

/* Recharge l'onglet courant. */
App.refresh = async function () {
  await App.loadRefs();
  await App.showTab(App.currentTab);
};

/* Recharge tout ce qui est visible après une écriture. */
App.refreshAll = async function () {
  await App.refresh();
};

/* Utilisé après une édition inline : ne recharge pas l'onglet courant
   (pour ne pas perdre le focus), juste les données de référence. */
App.refreshOthers = async function () {
  await App.loadRefs();
};

/* `sens` vaut 'next', 'prev', ou rien quand le mois est choisi directement
   dans le sélecteur — aucun sens de déplacement à représenter dans ce cas. */
App.setMonth = async function (ym, sens) {
  App.state.month = ym;
  App.el('#month-input').value = ym;
  localStorage.setItem('patrimoine.month', ym);

  // `sens || null` et non `sens` : passer `undefined` laisserait showTab
  // déduire un sens depuis les onglets, alors qu'on reste sur le même.
  await App.showTab(App.currentTab, sens || null);
};

/* Depuis l'archive : on change de mois ET d'onglet. Le mois est posé sans
   rendu, pour n'avoir qu'une seule transition au lieu de deux enchaînées. */
App.goToMonth = async function (ym) {
  App.state.month = ym;
  App.el('#month-input').value = ym;
  localStorage.setItem('patrimoine.month', ym);
  await App.showTab('expenses');
};

document.addEventListener('DOMContentLoaded', async () => {
  App.el('#modal-close').addEventListener('click', () => App.modal.close());
  App.el('#modal-backdrop').addEventListener('click', (e) => {
    if (e.target.id === 'modal-backdrop') App.modal.close();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !App.el('#modal-backdrop').hidden) App.modal.close();
  });

  App.els('.tab').forEach((btn) => {
    btn.addEventListener('click', () => {
      // Cliquer l'onglet où l'on se trouve déjà rejouait toute l'apparition :
      // la page repartait de l'opacité zéro, comme si elle se rechargeait.
      // Un onglet actif n'a rien à annoncer, on ne bouge pas.
      if (btn.dataset.tab === App.currentTab) return;
      App.showTab(btn.dataset.tab);
    });
  });

  // La barre se réorganise sur écran étroit (les onglets passent à la ligne) :
  // sans nouvelle mesure, le trait resterait aux coordonnées de l'ancienne mise
  // en page. Sur redimensionnement on replace sans animer le glissement.
  App.placeIndicator();
  let recalage;
  window.addEventListener('resize', () => {
    clearTimeout(recalage);
    recalage = setTimeout(App.placeIndicator, 120);
  });

  const monthInput = App.el('#month-input');
  monthInput.addEventListener('change', () => App.setMonth(monthInput.value));
  App.el('#month-prev').addEventListener('click',
    () => App.setMonth(App.shiftMonth(App.state.month, -1), 'prev'));
  App.el('#month-next').addEventListener('click',
    () => App.setMonth(App.shiftMonth(App.state.month, 1), 'next'));

  App.el('#open-settings').addEventListener('click', () => App.settings.open());
  App.els('[data-zoom]').forEach((b) => b.addEventListener('click',
    () => App.tabs.overview.toggleChart(b.dataset.zoom)));
  App.el('#toggle-privacy').addEventListener('click',
    () => App.setPrivacy(!App.privacyOn()));
  App.el('#toggle-theme').addEventListener('click', async () => {
    App.setTheme(App.currentTheme() === 'dark' ? 'light' : 'dark');
    // Les graphiques lisent leurs couleurs au moment du rendu : on les refait.
    await App.showTab(App.currentTab);
  });

  App.el('#ex-add').addEventListener('click', () => App.tabs.expenses.openForm(null));
  App.el('#ex-import').addEventListener('click', () => App.tabs.expenses.openImport());
  App.el('#ex-search').addEventListener('input', () => App.tabs.expenses.renderTable());
  App.el('#ex-filter-cat').addEventListener('change', () => App.tabs.expenses.renderTable());

  App.el('#we-refresh-quotes').addEventListener('click',
    (e) => App.tabs.wealth.refreshQuotes(e.target));
  App.el('#we-add').addEventListener('click', () => App.tabs.wealth.openAddChooser());
  App.el('#we-archived').addEventListener('change', () => App.tabs.wealth.load());

  App.state.month = localStorage.getItem('patrimoine.month') || App.monthISO();
  monthInput.value = App.state.month;
  App.setTheme(App.currentTheme());
  // Masquage actif par defaut : seul un « 0 » explicitement memorise le leve.
  App.setPrivacy(localStorage.getItem('patrimoine.privacy') !== '0');

  try {
    await App.loadMeta();
    await App.loadRefs();
    await App.showTab('overview');
    // Pendant la toute première apparition : c'est le moment le plus chargé de
    // la session, donc le plus révélateur de ce que la machine encaisse.
    App.mesurerFluidite();
    // Volontairement après le premier rendu, et sans await : l'interface
    // s'affiche immédiatement depuis le cache, les cours arrivent ensuite.
    App.autoRefreshQuotes();
  } catch (e) {
    App.toast(`Chargement impossible : ${e.message}`, 'error', 10000);
  }
});

/* Rafraîchissement automatique au lancement, si le cache a dépassé sa durée de
   vie. Ne bloque jamais l'affichage et reste silencieux en cas d'échec réseau :
   l'application doit rester utilisable hors ligne. */
App.autoRefreshQuotes = async function () {
  let status;
  try {
    status = await App.api.get('/api/market/status');
  } catch (e) {
    return;
  }
  if (!status.active || !status.auto_refresh || !status.cache_perime) return;
  try {
    const res = await App.api.post('/api/market/refresh');
    if (res.ok) {
      App.toast(`Cours mis à jour : ${res.ok} ligne(s)`, 'success');
      await App.refresh();
    }
  } catch (e) {
    App.toast(`Cours indisponibles : ${e.message}. Valeurs en cache affichées.`, 'error');
  }
};
