/* Paramètres.

   Sept rubriques, une idée chacune, dans une colonne latérale. Il y avait
   trois onglets de 1 100 à 1 600 pixels de haut, dont un — « Données et
   apparence » — empilait sept sous-titres sans rapport entre eux : le thème,
   les cours, les sauvegardes et les types d'actifs.

   Trois règles tiennent l'ensemble :
   - tout s'enregistre à la modification, sans exception ni bouton
     « Enregistrer » isolé ;
   - une rubrique dit en une phrase à quoi elle sert, et c'est tout : les
     notes repliables expliquaient ce que les libellés doivent dire seuls ;
   - un geste destructeur se confirme SUR PLACE. `App.confirm` remplace la
     modale courante : supprimer une sauvegarde vous sortait des paramètres. */
App.settings = {
  CLE_RUBRIQUE: 'patrimoine.reglages.rubrique',

  async open(focus) {
    const [settings, rules, market] = await Promise.all([
      App.api.get('/api/settings'),
      App.api.get('/api/rules'),
      App.api.get('/api/market/status'),
    ]);
    App.state.settings = settings;

    // Chaque rubrique porte les mots qui y mènent depuis ailleurs : la
    // pastille « cours désactivés » de Patrimoine ouvre sur « cours ».
    const rubriques = [
      {
        id: 'affichage', titre: 'Affichage', alias: ['apparence', 'theme'],
        phrase: 'Thème et animations. Propres à cet ordinateur, ils ne suivent pas vos données.',
        rendu: () => App.settings.panelApparence(),
      },
      {
        id: 'categories', titre: 'Catégories', alias: ['categorie', 'classement', 'budget', 'role'],
        phrase: 'Vos catégories, ce que chacune compte dans les calculs, et le budget visé.',
        rendu: () => App.settings.panelCategories(settings),
      },
      {
        id: 'regles', titre: 'Règles', alias: ['regle'],
        phrase: 'Un mot du libellé, une catégorie : appliquées à chaque relevé importé.',
        rendu: () => App.settings.panelRules(rules, settings),
      },
      {
        id: 'objectifs', titre: 'Objectifs', alias: ['objectif', 'repartition', 'precaution'],
        phrase: 'La répartition visée de votre patrimoine, et le coussin de sécurité.',
        rendu: () => App.settings.panelObjectifs(settings),
      },
      {
        id: 'patrimoine', titre: 'Patrimoine', alias: ['type', 'interet'],
        phrase: 'Les types d’actifs que la liste ne propose pas, et la date des intérêts.',
        rendu: () => App.settings.panelPatrimoine(settings),
      },
      {
        id: 'cours', titre: 'Cours de marché', alias: ['cours', 'marche', 'cle'],
        phrase: 'Valoriser actions, fonds et cryptos au cours du jour.',
        rendu: () => App.settings.panelMarket(settings, market),
      },
      {
        id: 'sauvegardes', titre: 'Sauvegardes', alias: ['sauvegarde', 'restaur'],
        phrase: 'Une copie de vos données en CSV, lisible dans un tableur.',
        rendu: () => App.settings.panelBackups(),
      },
    ];

    const cherche = (focus || '').toLowerCase();
    let memorisee = null;
    try { memorisee = localStorage.getItem(App.settings.CLE_RUBRIQUE); } catch (e) { /* ignore */ }
    const parFocus = cherche && rubriques.find((r) => r.titre.toLowerCase().includes(cherche)
      || r.alias.some((a) => cherche.includes(a)));
    const depart = parFocus || rubriques.find((r) => r.id === memorisee) || rubriques[1];

    const nav = App.h('nav', { class: 'reglages-nav', 'aria-label': 'Rubriques' });
    const contenu = App.h('div', { class: 'reglages-contenu' });
    const rendus = {};

    // Rendu à la première visite seulement : les sauvegardes et la table des
    // symboles interrogent le serveur, inutile de le faire pour une rubrique
    // qu'on n'ouvrira pas.
    const montrer = (r) => {
      App.els('button', nav).forEach((b) => b.classList.toggle('active', b.dataset.id === r.id));
      if (!rendus[r.id]) {
        rendus[r.id] = App.h('section', { class: 'reglages-rubrique' },
          App.h('h3', {}, r.titre),
          App.h('p', { class: 'reglages-phrase' }, r.phrase),
          r.rendu());
      }
      App.clear(contenu);
      contenu.append(rendus[r.id]);
      contenu.scrollTop = 0;
      try { localStorage.setItem(App.settings.CLE_RUBRIQUE, r.id); } catch (e) { /* ignore */ }
    };

    for (const r of rubriques) {
      const b = App.h('button', { type: 'button', 'data-id': r.id }, r.titre);
      b.addEventListener('click', () => montrer(r));
      nav.append(b);
    }
    nav.append(App.h('div', { class: 'reglages-auto' },
      'Enregistrement automatique',
      App.settings.temoin = App.h('span', { class: 'temoin', 'aria-live': 'polite' })));

    App.modal.open({
      title: 'Paramètres',
      wide: true,
      body: App.h('div', { class: 'reglages' }, nav, contenu),
      onClose: async () => {
        if (!App.settings.aRafraichir) return;
        App.settings.aRafraichir = false;
        await App.refreshAll();
      },
      footer: [App.h('button', { class: 'btn primary', onclick: () => App.modal.close() }, 'Fermer')],
    });
    montrer(depart);
  },

  /* Reglages dont dependent les listes de reference de l'application. */
  CLES_META: ['categories_depenses', 'categories_revenus', 'types_actifs_custom',
    'budgets_categories', 'mois_precaution_cible'],

  /* Reglages qui ne changent RIEN de ce qui est affiche a l'instant : ils
     n'agissent que sur de futurs imports ou de futurs appels reseau. */
  CLES_SANS_RENDU: ['market_api_key', 'market_auto_refresh',
    'market_cache_ttl_hours', 'market_provider'],

  /* Le rafraichissement de la page est reporte a la fermeture des reglages :
     une seule fois, au moment ou l'on revient a ce qu'il change. */
  async save(patch, message = 'Enregistré') {
    try {
      await App.api.put('/api/settings', patch);
      Object.assign(App.state.settings, patch);
      App.settings.signaler(message);
      const cles = Object.keys(patch);
      if (cles.some((c) => App.settings.CLES_META.includes(c))) await App.loadMeta();
      if (!cles.every((c) => App.settings.CLES_SANS_RENDU.includes(c))) {
        App.settings.aRafraichir = true;
      }
      return true;
    } catch (e) {
      App.toast(e.message, 'error');
      return false;
    }
  },

  signaler(message) {
    const t = App.settings.temoin;
    if (!t || !t.isConnected) return;
    t.textContent = `✓ ${message}`;
    t.classList.remove('visible');
    void t.offsetWidth;          // relance la transition
    t.classList.add('visible');
    clearTimeout(App.settings.temoinDelai);
    App.settings.temoinDelai = setTimeout(() => t.classList.remove('visible'), 1800);
  },

  /* ---------- briques communes ---------- */

  /* Confirmation sur place : le bouton change de libellé et attend un second
     clic dans les quatre secondes. Pas de modale par-dessus — il n'y en a
     qu'une, et l'ouvrir fermerait les paramètres. */
  confirmerSurPlace(bouton, question, action) {
    if (bouton.dataset.arme === '1') {
      clearTimeout(bouton._delai);
      bouton.dataset.arme = '';
      bouton.textContent = bouton.dataset.libelle;
      bouton.classList.remove('arme');
      return action();
    }
    bouton.dataset.libelle = bouton.textContent;
    bouton.dataset.arme = '1';
    bouton.textContent = question;
    bouton.classList.add('arme');
    bouton._delai = setTimeout(() => {
      bouton.dataset.arme = '';
      bouton.textContent = bouton.dataset.libelle;
      bouton.classList.remove('arme');
    }, 4000);
    return null;
  },

  boutonRetirer(titre, action) {
    const b = App.h('button', { type: 'button', class: 'icon-btn retirer', title: titre, 'aria-label': titre }, '×');
    b.addEventListener('click', action);
    return b;
  },

  /* Un champ suivi de son bouton : la ligne d'ajout, partout la même. */
  ligneAjout(champs, libelle, action) {
    const bouton = App.h('button', { type: 'button', class: 'btn' }, libelle);
    bouton.addEventListener('click', action);
    for (const c of champs) {
      if (c.tagName === 'INPUT') {
        c.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); action(); } });
      }
    }
    return App.h('div', { class: 'reglages-ajout' }, ...champs, bouton);
  },

  bloc(titre, ...enfants) {
    return App.h('div', { class: 'reglages-bloc' },
      titre ? App.h('h4', {}, titre) : null, ...enfants);
  },

  /* ---------- affichage ---------- */
  panelApparence() {
    const theme = App.h('div', { class: 'segmente' });
    const peindreTheme = () => {
      App.clear(theme);
      for (const [code, libelle] of [['systeme', 'Système'], ['clair', 'Clair'], ['sombre', 'Sombre']]) {
        const actif = App.themeChoisi() === code;
        theme.append(App.h('button', {
          type: 'button',
          class: `segmente-cran${actif ? ' actif' : ''}`,
          'aria-pressed': actif ? 'true' : 'false',
          onclick: () => {
            App.setTheme(code);
            App.redessinerGraphiques();
            peindreTheme();
          },
        }, libelle));
      }
    };
    peindreTheme();

    // Le reglage ne passe pas par le serveur : il vaut pour cette machine.
    const reduit = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const cb = App.h('input', { type: 'checkbox', disabled: reduit || null });
    cb.checked = App.animationsEconomes() || reduit;
    cb.addEventListener('change', () => {
      App.setAnimations(cb.checked);
      App.settings.signaler(cb.checked ? 'Animations allégées' : 'Animations complètes');
    });

    return App.h('div', {},
      App.settings.ligneReglage('Thème', theme),
      App.settings.ligneReglage('Animations économes', App.settings.interrupteur(cb),
        reduit ? 'Imposé par votre système.' : 'Fige le fond et retire les flous animés.'));
  },

  /* Libellé et explication à gauche, commande à droite. */
  ligneReglage(libelle, commande, aide) {
    return App.h('div', { class: 'reglage' },
      App.h('div', { class: 'reglage-texte' },
        App.h('div', { class: 'reglage-libelle' }, libelle),
        aide ? App.h('div', { class: 'reglage-aide' }, aide) : null),
      App.h('div', { class: 'reglage-commande' }, commande));
  },

  interrupteur(cb) {
    cb.classList.add('interrupteur-case');
    return App.h('label', { class: 'interrupteur' }, cb, App.h('span', { 'aria-hidden': 'true' }));
  },

  /* ---------- catégories ----------

     Un rôle par catégorie, et un seul. C'étaient trois cases indépendantes —
     épargne, charge fixe, virement interne — que rien n'empêchait de cocher
     ensemble. Or le reste à vivre vaut « revenus − charges fixes − épargne » :
     une catégorie à la fois épargne et charge fixe était soustraite deux fois.
     Un menu rend la contradiction impossible.

     La liste des catégories de dépenses n'existe plus à part : c'est la
     première colonne du tableau. Elle apparaissait deux fois. */
  ROLES: [
    ['', 'Dépense', null],
    ['fixe', 'Charge fixe', 'categories_charges_fixes'],
    ['epargne', 'Épargne', 'categories_non_depense'],
    ['transfert', 'Virement interne', 'categories_transfert'],
  ],

  roleDe(settings, cat) {
    // Ordre de lecture d'une donnée ancienne qui en cumulait plusieurs : le
    // rôle le plus neutre l'emporte, c'est lui qui fausse le moins les totaux.
    if ((settings.categories_transfert || []).includes(cat)) return 'transfert';
    if ((settings.categories_non_depense || []).includes(cat)) return 'epargne';
    if ((settings.categories_charges_fixes || []).includes(cat)) return 'fixe';
    return '';
  },

  nbRoles(settings, cat) {
    return App.settings.ROLES.filter(([, , cle]) => cle && (settings[cle] || []).includes(cat)).length;
  },

  panelCategories(settings) {
    const tbody = App.h('tbody', {});

    const patchRole = (cat, role) => {
      const patch = {};
      for (const [code, , cle] of App.settings.ROLES) {
        if (!cle) continue;
        const set = new Set(settings[cle] || []);
        set.delete(cat);
        if (code === role) set.add(cat);
        patch[cle] = [...set];
      }
      return patch;
    };

    const render = () => {
      App.clear(tbody);
      const cats = settings.categories_depenses || [];
      if (!cats.length) {
        tbody.append(App.h('tr', {}, App.h('td', { colspan: 4, class: 'empty' },
          'Aucune catégorie de dépense.')));
      }
      const budgets = Object.assign({}, settings.budgets_categories || {});
      for (const cat of cats) {
        const role = App.settings.roleDe(settings, cat);
        const conflit = App.settings.nbRoles(settings, cat) > 1;
        const sel = App.select('role', App.settings.ROLES.map(([c, l]) => [c, l]), role);
        if (conflit) {
          sel.classList.add('conflit');
          sel.title = 'Cette catégorie avait plusieurs rôles à la fois. Choisissez-en un.';
        }

        // Un budget n'a de sens que sur une dépense : l'épargne et les
        // virements internes ne sont jamais comptés comme consommés.
        const montant = App.input('b', {
          type: 'number', step: '1', min: '0', placeholder: '—',
          value: budgets[cat] ?? '',
        });
        const sansBudget = () => role === 'epargne' || role === 'transfert';
        montant.disabled = sansBudget();
        montant.title = sansBudget() ? 'Pas de budget sur une catégorie qui n’est pas une dépense' : '';

        sel.addEventListener('change', async () => {
          const patch = patchRole(cat, sel.value);
          Object.assign(settings, patch);
          await App.settings.save(patch, 'Rôle mis à jour');
          render();
        });
        montant.addEventListener('change', async () => {
          const v = parseFloat(montant.value);
          if (Number.isFinite(v) && v > 0) budgets[cat] = v; else delete budgets[cat];
          settings.budgets_categories = budgets;
          await App.settings.save({ budgets_categories: budgets }, 'Budget mis à jour');
        });

        const retirer = App.settings.boutonRetirer(`Supprimer « ${cat} »`, async () => {
          const patch = patchRole(cat, '');
          patch.categories_depenses = cats.filter((c) => c !== cat);
          const b = Object.assign({}, settings.budgets_categories || {});
          delete b[cat];
          patch.budgets_categories = b;
          Object.assign(settings, patch);
          render();
          await App.settings.save(patch, 'Catégorie supprimée');
        });

        tbody.append(App.h('tr', {},
          App.h('td', {}, cat),
          App.h('td', {}, sel),
          App.h('td', { class: 'budget-cell' }, montant),
          App.h('td', { class: 'right' }, retirer)));
      }
    };
    render();

    const nouvelle = App.input('cat', { placeholder: 'Nouvelle catégorie de dépense' });
    const ajouterDepense = async () => {
      const v = nouvelle.value.trim();
      if (!v) return;
      if ((settings.categories_depenses || []).includes(v)) return App.toast('Déjà présente', 'error');
      settings.categories_depenses = [...(settings.categories_depenses || []), v];
      nouvelle.value = '';
      render();
      await App.settings.save({ categories_depenses: settings.categories_depenses }, 'Catégorie ajoutée');
    };

    return App.h('div', {},
      App.settings.bloc('Dépenses',
        App.h('p', { class: 'reglages-aide' },
          App.h('strong', {}, 'Charge fixe'), ' : retirée du reste à vivre. ',
          App.h('strong', {}, 'Épargne'), ' : sort des dépenses, entre dans le taux d’épargne. ',
          App.h('strong', {}, 'Virement interne'), ' : ni dépense, ni revenu.'),
        App.h('div', { class: 'table-wrap' },
          App.h('table', { class: 'table reglages-table' },
            App.h('thead', {}, App.h('tr', {},
              App.h('th', {}, 'Catégorie'),
              App.h('th', { style: 'width:180px' }, 'Rôle'),
              App.h('th', { class: 'right', style: 'width:130px' }, 'Budget / mois'),
              App.h('th', { style: 'width:40px' }))),
            tbody)),
        App.settings.ligneAjout([nouvelle], 'Ajouter', ajouterDepense)),
      App.settings.bloc('Revenus',
        App.settings.listeEditable(settings, 'categories_revenus', 'Nouvelle catégorie de revenu')));
  },

  /* Des étiquettes retirables et un champ d'ajout : catégories de revenus. */
  listeEditable(settings, cle, invite) {
    const liste = App.h('div', { class: 'etiquettes' });
    const render = () => {
      App.clear(liste);
      const valeurs = settings[cle] || [];
      if (!valeurs.length) liste.append(App.h('span', { class: 'muted' }, 'Aucune.'));
      for (const v of valeurs) {
        liste.append(App.h('span', { class: 'etiquette' }, v,
          App.settings.boutonRetirer(`Supprimer « ${v} »`, async () => {
            settings[cle] = (settings[cle] || []).filter((x) => x !== v);
            render();
            await App.settings.save({ [cle]: settings[cle] }, 'Catégorie supprimée');
          })));
      }
    };
    render();
    const champ = App.input('v', { placeholder: invite });
    const ajouter = async () => {
      const v = champ.value.trim();
      if (!v) return;
      if ((settings[cle] || []).includes(v)) return App.toast('Déjà présente', 'error');
      settings[cle] = [...(settings[cle] || []), v];
      champ.value = '';
      render();
      await App.settings.save({ [cle]: settings[cle] }, 'Catégorie ajoutée');
    };
    return App.h('div', {}, liste, App.settings.ligneAjout([champ], 'Ajouter', ajouter));
  },

  /* ---------- règles ----------

     Deux colonnes ont disparu. « Cible » (dépense ou revenu) n'était lue par
     rien au moment de classer : elle se déduit désormais de la catégorie
     choisie. « Priorité » affichait 100 ou 200 sans qu'aucun écran permette de
     la changer. */
  selectCategorie(settings, valeur) {
    const sel = App.h('select', { name: 'valeur' });
    const groupes = [['Dépenses', settings.categories_depenses || []],
      ['Revenus', settings.categories_revenus || []]];
    for (const [libelle, cats] of groupes) {
      const g = App.h('optgroup', { label: libelle });
      for (const c of cats) {
        const o = App.h('option', { value: c }, c);
        if (c === valeur) o.selected = true;
        g.append(o);
      }
      sel.append(g);
    }
    return sel;
  },

  panelRules(rules, settings) {
    const tbody = App.h('tbody', {});
    const render = () => {
      App.clear(tbody);
      if (!rules.length) {
        tbody.append(App.h('tr', {}, App.h('td', { colspan: 3, class: 'empty' },
          'Aucune règle pour l’instant.')));
      }
      const tries = [...rules].sort((a, b) => a.pattern.localeCompare(b.pattern, 'fr'));
      for (const r of tries) {
        tbody.append(App.h('tr', {},
          App.h('td', {}, App.h('code', {}, r.pattern)),
          App.h('td', {}, App.h('span', { class: 'pill accent' }, r.valeur)),
          App.h('td', { class: 'right' }, App.settings.boutonRetirer(
            `Supprimer la règle « ${r.pattern} »`, async () => {
              try {
                await App.api.del(`/api/rules/${r.id}`);
                rules.splice(rules.indexOf(r), 1);
                render();
                App.settings.signaler('Règle supprimée');
              } catch (e) { App.toast(e.message, 'error'); }
            }))));
      }
    };
    render();

    const motif = App.input('pattern', { placeholder: 'Le libellé contient… (ex : NETFLIX)' });
    const valeur = App.settings.selectCategorie(settings, 'Salaire');
    const ajouter = async () => {
      const p = motif.value.trim();
      if (!p) { motif.focus(); return; }
      const estRevenu = (settings.categories_revenus || []).includes(valeur.value);
      const cible = estRevenu ? 'type_revenu' : 'categorie_depense';
      try {
        const res = await App.api.post('/api/rules', { pattern: p, cible_type: cible, valeur: valeur.value });
        rules.push({ id: res.id, pattern: p, cible_type: cible, valeur: valeur.value, priorite: 100 });
        motif.value = '';
        render();
        App.settings.signaler('Règle ajoutée');
      } catch (e) { App.toast(e.message, 'error'); }
    };

    const resultat = App.h('span', { class: 'reglages-aide' });
    const appliquer = App.h('button', { type: 'button', class: 'btn' },
      'Reclasser les transactions non catégorisées');
    appliquer.addEventListener('click', async () => {
      appliquer.disabled = true;
      try {
        const res = await App.api.post('/api/rules/apply', { seulement_non_categorise: true });
        resultat.textContent = `${res.modifiees} transaction(s) reclassée(s).`;
        if (res.modifiees) App.settings.aRafraichir = true;
      } catch (e) { App.toast(e.message, 'error'); }
      appliquer.disabled = false;
    });

    return App.h('div', {},
      App.settings.bloc(null,
        App.settings.ligneAjout([motif, App.h('span', { class: 'fleche' }, '→'), valeur],
          'Ajouter', ajouter),
        App.h('p', { class: 'reglages-aide' },
          'Sans tenir compte des majuscules ni des accents. Le remboursement d’un prêt '
          + 'est reconnu à son montant, sans règle.')),
      App.settings.bloc(`${rules.length} règle(s)`,
        App.h('div', { class: 'table-wrap scroll-y' },
          App.h('table', { class: 'table reglages-table' },
            App.h('thead', {}, App.h('tr', {},
              App.h('th', {}, 'Si le libellé contient'),
              App.h('th', {}, 'Alors'),
              App.h('th', { style: 'width:40px' }))),
            tbody)),
        App.h('div', { class: 'reglages-ajout' }, appliquer, resultat)));
  },

  /* ---------- objectifs ---------- */
  panelObjectifs(settings) {
    return App.h('div', {},
      App.settings.bloc('Répartition cible', App.settings.panelRepartition(settings)),
      App.settings.bloc('Épargne de précaution', App.settings.panelPrecaution(settings)));
  },

  /* Une poche par ligne : nom, pourcentage, types, et rien d'autre en vue.
     Les types d'actifs — une vingtaine de cases par poche, toutes dépliées —
     se rangent derrière un bouton qui dit combien sont cochés. */
  panelRepartition(settings) {
    let poches = JSON.parse(JSON.stringify(settings.repartition_cible || []));
    if (!Array.isArray(poches)) {
      poches = Object.entries(poches).map(([k, v]) => ({ label: k, types: [k], pct: v }));
    }
    const tousTypes = (App.state.meta.asset_types || []).map((t) => t.type);
    const hote = App.h('div', { class: 'poches' });
    const total = App.h('div', { class: 'poches-total' });
    const enregistrer = () => App.settings.save({ repartition_cible: poches }, 'Répartition enregistrée');

    const majTotal = () => {
      const t = poches.reduce((s, p) => s + (parseFloat(p.pct) || 0), 0);
      const juste = Math.abs(t - 100) < 0.01;
      App.clear(total);
      total.append(
        App.h('div', { class: 'poches-barre' },
          App.h('span', { style: `width:${Math.min(100, t)}%`, class: juste ? 'ok' : '' })),
        App.h('span', { class: juste ? 'ok-txt' : 'alerte-txt' },
          `Total ${App.fmt.num(t, 1)} %`
          + (juste ? '' : (t < 100 ? ` — il manque ${App.fmt.num(100 - t, 1)} %`
            : ` — ${App.fmt.num(t - 100, 1)} % de trop`))));
    };

    const render = () => {
      App.clear(hote);
      if (!poches.length) {
        hote.append(App.h('p', { class: 'muted' }, 'Aucune poche : la vue d’ensemble ne montre pas d’écart à la cible.'));
      }
      const nomsProduits = (App.state.assets || []).map((a) => (a.label || '').trim().toLowerCase());
      poches.forEach((p, i) => {
        const panneau = App.h('div', { class: 'poche-types', hidden: true });
        const resume = App.h('button', { type: 'button', class: 'btn small poche-resume' });
        const avertir = App.h('div', { class: 'poche-alerte' });
        const majResume = () => {
          const n = (p.types || []).length;
          resume.textContent = n ? `${n} type${n > 1 ? 's' : ''} ▾` : 'Choisir les types ▾';
          const nom = (p.label || '').trim().toLowerCase();
          const reconnu = tousTypes.some((t) => t.toLowerCase() === nom) || nomsProduits.includes(nom);
          avertir.textContent = !n && !reconnu
            ? 'Aucun type coché : cette poche restera à 0 %.' : '';
        };
        for (const t of tousTypes) {
          const cb = App.h('input', { type: 'checkbox', value: t });
          cb.checked = (p.types || []).includes(t);
          cb.addEventListener('change', () => {
            p.types = Array.from(panneau.querySelectorAll('input:checked')).map((c) => c.value);
            majResume();
            enregistrer();
          });
          panneau.append(App.h('label', { class: 'checkline' }, cb, t));
        }
        resume.addEventListener('click', () => { panneau.hidden = !panneau.hidden; });
        majResume();

        const nom = App.input('l', { value: p.label || '', 'aria-label': 'Nom de la poche' });
        nom.addEventListener('input', () => { p.label = nom.value; majResume(); });
        nom.addEventListener('change', enregistrer);
        const pct = App.input('p', {
          type: 'number', step: '0.5', min: '0', max: '100', value: p.pct ?? 0,
          'aria-label': 'Part visée en pourcentage',
        });
        pct.addEventListener('input', () => { p.pct = parseFloat(pct.value) || 0; majTotal(); });
        pct.addEventListener('change', enregistrer);

        hote.append(App.h('div', { class: 'poche' },
          App.h('div', { class: 'poche-ligne' },
            nom,
            App.h('span', { class: 'poche-pct' }, pct, '%'),
            resume,
            App.settings.boutonRetirer('Retirer cette poche', () => {
              poches.splice(i, 1); render(); majTotal(); enregistrer();
            })),
          avertir, panneau));
      });
    };
    render(); majTotal();

    const ajouter = App.h('button', { type: 'button', class: 'btn' }, '+ Ajouter une poche');
    ajouter.addEventListener('click', () => {
      poches.push({ label: 'Nouvelle poche', types: [], pct: 0 });
      render(); majTotal();
      const champs = hote.querySelectorAll('.poche-ligne input[name="l"]');
      if (champs.length) { champs[champs.length - 1].focus(); champs[champs.length - 1].select(); }
    });

    return App.h('div', {}, hote, total, App.h('div', { class: 'reglages-ajout' }, ajouter));
  },

  /* Le seuil vivait en deux endroits ; un seul réglage, lu par les deux. */
  panelPrecaution(settings) {
    const mois = App.input('mois', {
      type: 'number', min: 1, max: 24, step: '1', class: 'champ-court',
      value: settings.mois_precaution_cible ?? 4, 'aria-label': 'Nombre de mois',
    });
    mois.addEventListener('change', () => {
      const v = Math.min(24, Math.max(1, parseInt(mois.value, 10) || 4));
      mois.value = v;
      App.settings.save({ mois_precaution_cible: v }, 'Cible enregistrée');
    });
    return App.settings.ligneReglage('Mois de dépenses couverts par vos livrets',
      App.h('span', { class: 'champ-unite' }, mois, 'mois'),
      'En dessous, la couverture d’urgence passe en alerte.');
  },

  /* ---------- patrimoine ---------- */
  panelPatrimoine(settings) {
    return App.h('div', {},
      App.settings.bloc('Types d’actifs personnalisés', App.settings.panelAssetTypes(settings)),
      App.settings.bloc('Versement des intérêts', App.settings.panelTaux(settings)));
  },

  panelAssetTypes(settings) {
    const customs = (settings.types_actifs_custom || []).map(
      (c) => (typeof c === 'string' ? { type: c, famille: 'Autre' } : c));
    const liste = App.h('div', { class: 'etiquettes' });
    const render = () => {
      App.clear(liste);
      if (!customs.length) liste.append(App.h('span', { class: 'muted' }, 'Aucun.'));
      customs.forEach((c, i) => {
        liste.append(App.h('span', { class: 'etiquette' }, c.type,
          App.h('span', { class: 'etiquette-sous' }, c.famille),
          App.settings.boutonRetirer(`Supprimer « ${c.type} »`, async () => {
            customs.splice(i, 1);
            render();
            await App.settings.save({ types_actifs_custom: customs }, 'Type supprimé');
          })));
      });
    };
    render();

    const typeIn = App.input('type', { placeholder: 'ex : Forêt, Montre, Parts de SARL' });
    const familleIn = App.select('famille',
      ['Liquidités', 'Épargne réglementée', 'Marchés financiers', 'Immobilier',
        'Crypto', 'Biens', 'Autre'], 'Autre', { 'aria-label': 'Famille' });
    const ajouter = async () => {
      const t = typeIn.value.trim();
      if (!t) { typeIn.focus(); return; }
      customs.push({ type: t, famille: familleIn.value });
      typeIn.value = '';
      render();
      await App.settings.save({ types_actifs_custom: customs }, 'Type ajouté');
    };
    return App.h('div', {}, liste,
      App.settings.ligneAjout([typeIn, familleIn], 'Ajouter', ajouter),
      App.h('p', { class: 'reglages-aide' },
        'La famille ne sert qu’à regrouper l’affichage.'));
  },

  panelTaux(settings) {
    const courant = String(settings.date_credit_interets || '12-31');
    const [mm, jj] = courant.split('-');
    const jour = App.input('jour', {
      type: 'number', min: 1, max: 31, value: Number(jj) || 31, class: 'champ-court',
      'aria-label': 'Jour',
    });
    const mois = App.select('mois', [
      ['01', 'janvier'], ['02', 'février'], ['03', 'mars'], ['04', 'avril'],
      ['05', 'mai'], ['06', 'juin'], ['07', 'juillet'], ['08', 'août'],
      ['09', 'septembre'], ['10', 'octobre'], ['11', 'novembre'], ['12', 'décembre'],
    ], mm || '12', { 'aria-label': 'Mois' });
    const enregistrer = async () => {
      const j = Math.min(31, Math.max(1, parseInt(jour.value, 10) || 31));
      jour.value = j;
      await App.settings.save({ date_credit_interets: `${mois.value}-${String(j).padStart(2, '0')}` },
        'Date enregistrée');
    };
    jour.addEventListener('change', enregistrer);
    mois.addEventListener('change', enregistrer);
    return App.settings.ligneReglage('Intérêts des livrets crédités le',
      App.h('span', { class: 'champ-unite' }, jour, mois),
      'Le 31 décembre pour tous les livrets réglementés. Avant cette date, '
      + 'un livret affiche son capital et les intérêts à venir à côté.');
  },

  /* ---------- cours de marché ----------

     Il n'y a plus de bouton « Enregistrer ». C'était la seule rubrique qui en
     gardait un, au milieu de réglages qui s'écrivaient seuls — rien à l'écran
     ne disait lesquels attendaient le clic. La raison était juste (activer
     les cours fait sortir des données) ; elle est servie autrement : c'est
     l'ACTIVATION, et elle seule, qui se confirme. */
  panelMarket(settings, status) {
    const etat = App.h('div', { class: 'cours-etat' });
    const peindreEtat = (s) => {
      App.clear(etat);
      const pastille = (txt, cls) => App.h('span', { class: `pill ${cls || ''}` }, txt);
      // `append` natif écrit « null » en toutes lettres : on filtre.
      etat.append(...[
        s.active ? pastille('Activés', 'ok') : pastille('Désactivés'),
        App.h('span', { class: 'reglages-aide' },
          s.dernier_refresh ? `Mis à jour le ${App.fmt.dateTime(s.dernier_refresh)}` : 'Jamais mis à jour'),
        App.h('span', { class: 'reglages-aide' }, `${s.nb_cours_en_cache} cours en cache`),
        s.tickers_non_mappes.length
          ? pastille(`${s.tickers_non_mappes.length} ligne(s) sans symbole`, 'warn') : null,
      ].filter(Boolean));
    };
    peindreEtat(status);

    const rafraichirEtat = async () => {
      try { peindreEtat(await App.api.get('/api/market/status')); } catch (e) { /* ignore */ }
    };

    // --- activation, confirmee sur place
    const actif = App.h('input', { type: 'checkbox' });
    actif.checked = !!settings.market_enabled;
    const avertissement = App.h('div', { class: 'callout', hidden: true },
      App.h('p', {}, App.h('strong', {}, 'Des données vont sortir de votre machine. '),
        'À chaque rafraîchissement, les symboles de vos titres et votre clé API sont '
        + 'envoyés au fournisseur. Vos montants et quantités, jamais.'),
      App.h('div', { class: 'actions' },
        App.h('button', {
          type: 'button', class: 'btn',
          onclick: () => { actif.checked = false; avertissement.hidden = true; },
        }, 'Annuler'),
        App.h('button', {
          type: 'button', class: 'btn primary',
          onclick: async () => {
            avertissement.hidden = true;
            if (await App.settings.save({ market_enabled: true }, 'Cours activés')) {
              settings.market_enabled = true;
              majDetails();
              rafraichirEtat();
            } else { actif.checked = false; }
          },
        }, 'Activer')));
    actif.addEventListener('change', async () => {
      if (actif.checked) { avertissement.hidden = false; return; }
      avertissement.hidden = true;
      await App.settings.save({ market_enabled: false }, 'Cours désactivés');
      settings.market_enabled = false;
      majDetails();
      rafraichirEtat();
    });

    // --- fournisseur et cle : la cle n'apparait que si le fournisseur en veut
    const fournisseur = App.select('market_provider', [
      ['twelvedata', 'Twelve Data'],
      ['yahoo', 'Yahoo Finance'],
    ], settings.market_provider || 'twelvedata');

    let cleEnPlace = !!settings.market_api_key_configuree;
    const cle = App.input('market_api_key', { type: 'password', value: '', autocomplete: 'off' });
    const etatCle = App.h('div', { class: 'reglage-aide' });
    const peindreCle = () => {
      cle.placeholder = cleEnPlace ? 'Remplacer la clé enregistrée' : 'Coller la clé API';
      App.clear(etatCle);
      if (cleEnPlace) {
        const oublier = App.h('button', { type: 'button', class: 'lien-discret' }, 'Oublier la clé');
        oublier.addEventListener('click', () => App.settings.confirmerSurPlace(oublier, 'Confirmer ?', async () => {
          if (await App.settings.save({ market_api_key: '' }, 'Clé oubliée')) {
            cleEnPlace = false;
            peindreCle();
            rafraichirEtat();
          }
        }));
        etatCle.append('Une clé est enregistrée. ', oublier);
      } else {
        etatCle.append('Gratuite sur twelvedata.com.');
      }
    };
    peindreCle();
    // Un champ vide n'est jamais envoyé : il effacerait la clé en place.
    cle.addEventListener('change', async () => {
      const v = cle.value.trim();
      if (!v) return;
      if (await App.settings.save({ market_api_key: v }, 'Clé enregistrée')) {
        cleEnPlace = true;
        cle.value = '';
        peindreCle();
        rafraichirEtat();
      }
    });
    const ligneCle = App.h('div', {},
      App.h('div', { class: 'reglage' },
        App.h('div', { class: 'reglage-texte' },
          App.h('div', { class: 'reglage-libelle' }, 'Clé API'), etatCle),
        App.h('div', { class: 'reglage-commande' }, cle)));

    const details = App.h('div', {});
    const majDetails = () => {
      details.hidden = !actif.checked;
      ligneCle.hidden = fournisseur.value !== 'twelvedata';
    };
    fournisseur.addEventListener('change', async () => {
      majDetails();
      await App.settings.save({ market_provider: fournisseur.value }, 'Fournisseur enregistré');
    });

    details.append(
      App.settings.ligneReglage('Fournisseur', fournisseur,
        'Twelve Data demande une clé gratuite. Yahoo n’en demande pas, mais son API n’est pas officielle.'),
      ligneCle,
      App.settings.blocSymboles());
    majDetails();

    return App.h('div', {},
      etat,
      App.settings.ligneReglage('Récupérer les cours en ligne', App.settings.interrupteur(actif),
        'Désactivé, aucune donnée ne quitte votre ordinateur.'),
      avertissement,
      details);
  },

  /* Rarement utile : la recherche depuis la fiche d'un actif remplit cette
     table toute seule. Repliée, mais à portée pour corriger. */
  blocSymboles() {
    const sym = App.input('sym', { placeholder: 'Symbole ou ISIN, ex : CW8' });
    const place = App.input('exch', { placeholder: 'Place (facultatif)' });
    const sortie = App.h('div', {});
    const tester = async () => {
      App.clear(sortie);
      sortie.append(App.h('span', { class: 'reglages-aide' }, 'Test en cours…'));
      try {
        const res = await App.api.post('/api/market/test', {
          symbol: sym.value.trim(), exchange: place.value.trim(),
        });
        App.clear(sortie);
        sortie.append(res.ok
          ? App.h('span', { class: 'pill ok' },
            `${res.symbole} : ${App.fmt.num(res.price, 4)} ${res.currency}`
            + (res.exchange ? ` · ${res.exchange}` : '') + ` · ${App.fmt.date(res.date)}`)
          : App.h('span', { class: 'pill warn' }, `${res.symbole} : ${res.erreur}`));
      } catch (e) {
        App.clear(sortie);
        sortie.append(App.h('span', { class: 'pill warn' }, e.message));
      }
    };

    const tbody = App.h('tbody', {});
    let charge = false;
    const charger = async () => {
      if (charge) return;
      charge = true;
      let data;
      try { data = await App.api.get('/api/securities'); } catch (e) { return App.toast(e.message, 'error'); }
      const parTicker = Object.fromEntries(data.securities.map((s) => [s.ticker, s]));
      const tickers = [...new Set([
        ...data.tickers_utilises.map((t) => t.ticker),
        ...data.securities.map((s) => s.ticker),
      ])].sort();
      App.clear(tbody);
      if (!tickers.length) {
        tbody.append(App.h('tr', {}, App.h('td', { colspan: 6, class: 'empty' },
          'Aucun titre dans vos mouvements.')));
        return;
      }
      for (const ticker of tickers) {
        const sec = parTicker[ticker] || {};
        const label = App.input('l', { value: sec.label || '', placeholder: 'nom affiché' });
        const symbol = App.input('s', { value: sec.symbol || '', placeholder: 'symbole' });
        const exchange = App.input('e', { value: sec.exchange || '', placeholder: 'place' });
        const currency = App.input('c', { value: sec.currency || 'EUR', class: 'champ-court' });
        const bench = App.input('b', { value: sec.benchmark_symbol || '', placeholder: 'indice' });
        const pastille = App.h('span', { class: `pill ${sec.symbol ? 'ok' : 'warn'}` },
          sec.symbol ? 'associé' : 'à faire');
        for (const input of [label, symbol, exchange, currency, bench]) {
          input.addEventListener('change', async () => {
            try {
              await App.api.post('/api/securities', {
                ticker,
                label: label.value.trim(),
                symbol: symbol.value.trim(),
                exchange: exchange.value.trim(),
                currency: currency.value.trim().toUpperCase() || 'EUR',
                benchmark_symbol: bench.value.trim(),
              });
              pastille.className = `pill ${symbol.value.trim() ? 'ok' : 'warn'}`;
              pastille.textContent = symbol.value.trim() ? 'associé' : 'à faire';
              App.settings.signaler('Correspondance enregistrée');
            } catch (e) { App.toast(e.message, 'error'); }
          });
        }
        tbody.append(App.h('tr', {},
          App.h('td', {}, App.h('code', {}, ticker), App.h('div', {}, pastille)),
          App.h('td', {}, label), App.h('td', {}, symbol), App.h('td', {}, exchange),
          App.h('td', {}, currency), App.h('td', {}, bench)));
      }
    };

    const note = App.note('Symboles et correspondances',
      App.h('p', { class: 'reglages-aide' },
        'Remplie automatiquement par la recherche depuis la fiche d’un actif. '
        + 'À corriger seulement si un cours ne remonte pas.'),
      App.settings.ligneAjout([sym, place], 'Tester', tester),
      sortie,
      App.h('div', { class: 'table-wrap scroll-y', style: 'margin-top:10px' },
        App.h('table', { class: 'table reglages-table' },
          App.h('thead', {}, App.h('tr', {},
            App.h('th', {}, 'Ticker / ISIN'), App.h('th', {}, 'Nom affiché'),
            App.h('th', {}, 'Symbole'), App.h('th', {}, 'Place'),
            App.h('th', {}, 'Devise'), App.h('th', {}, 'Indice'))),
          tbody)));
    note.addEventListener('toggle', () => { if (note.open) charger(); });
    return note;
  },

  /* ---------- sauvegardes ---------- */
  panelBackups() {
    const tbody = App.h('tbody', {});
    const entete = App.h('span', { class: 'reglages-aide' });

    const octets = (n) => (n < 1024 ? `${n} o`
      : n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} Ko`
        : `${(n / 1024 / 1024).toFixed(1)} Mo`);

    const recharger = async () => {
      let data;
      try { data = await App.api.get('/api/backups'); } catch (e) { return App.toast(e.message, 'error'); }
      entete.textContent = data.sauvegardes.length
        ? `${data.sauvegardes.length} sauvegarde(s), ${octets(data.taille_totale)} · `
          + `les ${data.maximum} plus récentes sont gardées`
        : 'Aucune sauvegarde pour le moment.';
      App.clear(tbody);
      for (const s of data.sauvegardes) {
        // Restaurer remplace TOUTES les données : le second clic porte la
        // conséquence dans son libellé, pas seulement « Confirmer ».
        const restaurer = App.h('button', { type: 'button', class: 'btn small' }, 'Restaurer');
        restaurer.addEventListener('click', () => App.settings.confirmerSurPlace(
          restaurer, 'Remplacer mes données ?', async () => {
            restaurer.disabled = true;
            try {
              const res = await App.api.post(`/api/backups/${s.id}/restore`, {});
              App.toast(`${res.lignes} ligne(s) restaurée(s). Une copie de sécurité a été prise juste avant.`, 'success');
              App.settings.aRafraichir = true;
              await recharger();
            } catch (e) { App.toast(e.message, 'error'); restaurer.disabled = false; }
          }));
        const supprimer = App.h('button', {
          type: 'button', class: 'icon-btn retirer', title: 'Supprimer cette sauvegarde',
          'aria-label': 'Supprimer cette sauvegarde',
        }, '×');
        supprimer.addEventListener('click', () => App.settings.confirmerSurPlace(
          supprimer, 'Supprimer ?', async () => {
            try {
              await App.api.del(`/api/backups/${s.id}`);
              App.settings.signaler('Sauvegarde supprimée');
              await recharger();
            } catch (e) { App.toast(e.message, 'error'); }
          }));
        tbody.append(App.h('tr', {},
          App.h('td', { class: 'nowrap' }, App.fmt.dateTime(s.date)),
          App.h('td', { class: 'right num' },
            s.patrimoine_net === null ? '—' : App.fmt.eur(s.patrimoine_net)),
          App.h('td', { class: 'right num' }, octets(s.taille)),
          App.h('td', { class: 'right nowrap' }, restaurer, ' ', supprimer)));
      }
    };

    const sauvegarder = App.h('button', { type: 'button', class: 'btn primary' }, 'Sauvegarder maintenant');
    sauvegarder.addEventListener('click', async () => {
      sauvegarder.classList.add('busy');
      sauvegarder.disabled = true;
      try {
        const res = await App.api.post('/api/backups', {});
        App.settings.signaler(res.inchange ? 'Rien n’a changé depuis la dernière' : 'Sauvegarde créée');
        await recharger();
      } catch (e) { App.toast(e.message, 'error'); }
      sauvegarder.classList.remove('busy');
      sauvegarder.disabled = false;
    });
    const dossier = App.h('button', { type: 'button', class: 'btn' }, 'Ouvrir le dossier');
    dossier.addEventListener('click', async () => {
      try { await App.api.post('/api/backups/open', {}); } catch (e) { App.toast(e.message, 'error'); }
    });

    recharger();

    return App.h('div', {},
      App.h('div', { class: 'reglages-ajout' }, sauvegarder, dossier),
      App.h('p', { class: 'reglages-aide' },
        'Ni la clé API ni le cache des cours n’y figurent. Restaurer prend d’abord '
        + 'une copie de sécurité de vos données actuelles.'),
      App.settings.bloc(null, entete,
        App.h('div', { class: 'table-wrap scroll-y', style: 'margin-top:8px' },
          App.h('table', { class: 'table reglages-table' },
            App.h('thead', {}, App.h('tr', {},
              App.h('th', {}, 'Date'),
              App.h('th', { class: 'right' }, 'Patrimoine net'),
              App.h('th', { class: 'right' }, 'Taille'),
              App.h('th', {}))),
            tbody))));
  },
};
