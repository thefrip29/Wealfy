/* Onglet « Historique » : archive mensuelle, recalculée à la volée.

   Deux lectures du même passé :
   - **Mois** : une ligne par mois, regroupées par année avec leur total.
     L'année en cours est dépliée, les autres se résument en une ligne ;
   - **Catégories** : les douze derniers mois en colonnes, une ligne par
     catégorie de dépense. Le mois le plus lourd de chaque ligne ressort, ce
     qui montre d'un coup d'œil quelle dépense a dérivé. */
App.tabs.history = {
  vue: (() => {
    try { return localStorage.getItem('wealfy.historique.vue') || 'mois'; }
    catch (e) { return 'mois'; }
  })(),
  anneesOuvertes: new Set([String(new Date().getFullYear())]),
  archive: [],

  async load() {
    const data = await App.api.get('/api/history');
    App.tabs.history.archive = data.archive;
    App.tabs.history.render();
  },

  render() {
    const h = App.tabs.history;
    h.renderVue();
    const host = App.el('#hi-contenu');
    App.clear(host);
    if (!h.archive.length) {
      host.append(App.h('p', { class: 'empty' }, 'Aucune donnée historique pour le moment.'));
      return;
    }
    host.append(h.vue === 'categories' ? h.tableCategories() : h.tableMois());
  },

  renderVue() {
    const host = App.el('#hi-vue');
    App.clear(host);
    for (const [code, libelle] of [['mois', 'Mois'], ['categories', 'Catégories']]) {
      const actif = App.tabs.history.vue === code;
      host.append(App.h('button', {
        class: `segmente-cran${actif ? ' actif' : ''}`,
        'aria-pressed': actif ? 'true' : 'false',
        onclick: () => {
          if (actif) return;
          App.tabs.history.vue = code;
          try { localStorage.setItem('wealfy.historique.vue', code); } catch (e) { /* ignore */ }
          App.tabs.history.render();
        },
      }, libelle));
    }
  },

  /* Ce qui a fait bouger le patrimoine net, en infobulle de la variation. */
  detailVariation(v) {
    if (!v) return '';
    return [
      ['Apports', v.apports], ['Performance', v.performance],
      ['Immobilier', v.immobilier], ['Dettes', v.dettes],
    ].filter(([nom, x]) => nom === 'Performance' || Math.abs(x) >= 0.01)
      .map(([nom, x]) => `${nom} ${App.fmt.signed(x)}`).join(' · ');
  },

  /* ---------- vue par mois ---------- */
  tableMois() {
    const h = App.tabs.history;
    const parAnnee = new Map();
    for (const row of h.archive) {      // du plus récent au plus ancien
      const an = row.mois.slice(0, 4);
      if (!parAnnee.has(an)) parAnnee.set(an, []);
      parAnnee.get(an).push(row);
    }

    const tbody = App.h('tbody', {});
    for (const [an, mois] of parAnnee) {
      const ouverte = h.anneesOuvertes.has(an);
      tbody.append(h.ligneAnnee(an, mois, ouverte));
      if (ouverte) for (const row of mois) tbody.append(h.ligneMois(row));
    }

    return App.h('div', { class: 'table-wrap' },
      App.h('table', { class: 'table', id: 'hi-archive' },
        App.h('thead', {}, App.h('tr', {},
          App.h('th', {}, 'Mois'),
          App.h('th', { class: 'right' }, 'Revenus'),
          App.h('th', { class: 'right' }, 'Dépenses'),
          App.h('th', { class: 'right' }, 'Solde'),
          App.h('th', { class: 'right' }, 'Épargne'),
          App.h('th', { class: 'right' }, 'Taux d’épargne'),
          App.h('th', { class: 'right' }, 'Patrimoine net'),
          App.h('th', { class: 'right', title: 'Survolez un montant pour son détail' },
            'Variation'),
          App.h('th', {}, 'Répartition atteinte'))),
        tbody));
  },

  cellulesChiffres(r) {
    return [
      App.h('td', { class: 'right num pos' }, App.fmt.eur(r.revenus)),
      App.h('td', { class: 'right num' }, App.fmt.eur(r.depenses)),
      App.h('td', { class: `right num ${r.solde >= 0 ? 'pos' : 'neg'}` }, App.fmt.signed(r.solde)),
      App.h('td', { class: 'right num' }, App.fmt.eur(r.epargne)),
      App.h('td', { class: 'right num' },
        r.taux_epargne === null ? '—' : App.fmt.ratio(r.taux_epargne)),
      App.h('td', { class: 'right num' }, App.fmt.eur(r.patrimoine_net)),
      App.h('td', {
        class: `right num ${r.variation.variation >= 0 ? 'pos' : 'neg'}`,
        title: App.tabs.history.detailVariation(r.variation),
      }, App.fmt.signed(r.variation.variation)),
    ];
  },

  /* Une ligne de texte plutôt qu'une pile de pastilles : trois poches
     empilées triplaient la hauteur de chaque mois. Seul l'écart à la cible
     prend la couleur d'alerte. */
  repartition(row) {
    const rep = App.h('span', { class: 'rep-ligne' });
    // Un mois sans versement n'a pas de répartition à comparer.
    const poches = (row.repartition || []).filter((b) => b.reel_pct !== null);
    if (!poches.length) return App.h('span', { class: 'sub' }, '—');
    poches.forEach((b, i) => {
      const ecart = b.reel_pct - b.cible_pct;
      if (i) rep.append(App.h('span', { class: 'sub' }, ' · '));
      rep.append(App.h('span', {
        class: Math.abs(ecart) < 5 ? '' : 'alerte-txt',
        title: `${b.label} : ${App.fmt.num(b.reel_pct, 1)} % pour une cible de `
          + `${App.fmt.num(b.cible_pct, 1)} %`,
      }, `${b.label} ${App.fmt.num(b.reel_pct, 0)} %`));
    });
    return rep;
  },

  ligneMois(row) {
    return App.h('tr', {},
      App.h('td', { class: 'nowrap' },
        App.h('button', {
          class: 'btn small', title: 'Voir les transactions du mois',
          onclick: () => App.goToMonth(row.mois),
        }, App.fmt.month(row.mois))),
      ...App.tabs.history.cellulesChiffres(row),
      App.h('td', {}, App.tabs.history.repartition(row)));
  },

  /* Une année se résume par ses sommes. Le taux d'épargne se recalcule sur
     les totaux, et non en moyenne des taux mensuels : un mois sans revenu
     pèserait autant qu'un mois de salaire. Le patrimoine net est celui du
     dernier mois connu de l'année. */
  ligneAnnee(an, mois, ouverte) {
    const somme = (cle) => Math.round(mois.reduce((s, r) => s + (r[cle] || 0), 0) * 100) / 100;
    const variation = {};
    for (const cle of ['variation', 'apports', 'performance', 'immobilier', 'dettes']) {
      variation[cle] = Math.round(mois.reduce((s, r) => s + (r.variation[cle] || 0), 0) * 100) / 100;
    }
    const revenus = somme('revenus');
    const total = {
      revenus,
      depenses: somme('depenses'),
      solde: somme('solde'),
      epargne: somme('epargne'),
      taux_epargne: revenus >= 50 ? somme('epargne') / revenus : null,
      patrimoine_net: mois[0].patrimoine_net,
      variation,
    };
    return App.h('tr', { class: 'annee' },
      App.h('td', {},
        App.h('button', {
          class: 'annee-btn', 'aria-expanded': ouverte ? 'true' : 'false',
          onclick: () => {
            const s = App.tabs.history.anneesOuvertes;
            if (s.has(an)) s.delete(an); else s.add(an);
            App.tabs.history.render();
          },
        }, `${ouverte ? '▾' : '▸'} ${an}`,
          App.h('span', { class: 'sub' }, ` · ${mois.length} mois`))),
      ...App.tabs.history.cellulesChiffres(total),
      App.h('td', {}, App.tabs.history.repartition(mois[0])));
  },

  /* ---------- vue par catégorie ---------- */
  tableCategories() {
    const mois = App.tabs.history.archive.slice(0, 12).reverse();   // chronologique
    const totaux = {};
    for (const m of mois) {
      for (const [cat, v] of Object.entries(m.categories || {})) {
        totaux[cat] = (totaux[cat] || 0) + v;
      }
    }
    const cats = Object.keys(totaux).sort((a, b) => totaux[b] - totaux[a]);
    if (!cats.length) {
      return App.h('p', { class: 'empty' }, 'Aucune dépense sur ces douze mois.');
    }
    const court = (ym) => {
      const [y, m] = ym.split('-').map(Number);
      return new Date(y, m - 1, 1).toLocaleDateString('fr-FR', { month: 'short', year: '2-digit' });
    };

    const tbody = App.h('tbody', {});
    for (const cat of cats) {
      const valeurs = mois.map((m) => (m.categories || {})[cat] || 0);
      const pic = Math.max(...valeurs);
      tbody.append(App.h('tr', {},
        App.h('td', { class: 'nowrap' }, cat),
        ...valeurs.map((v, i) => App.h('td', {
          class: `right num cliquable${v && v === pic && valeurs.filter(Boolean).length > 1 ? ' pic' : ''}`,
          title: v ? `${cat}, ${App.fmt.month(mois[i].mois)} : voir les transactions` : null,
          onclick: v ? () => {
            App.tabs.expenses.filtreAPoser = cat;
            App.goToMonth(mois[i].mois);
          } : null,
        }, v ? App.fmt.eur(v, true) : '·')),
        App.h('td', { class: 'right num moyenne' },
          App.fmt.eur(totaux[cat] / mois.length, true))));
    }

    return App.h('div', { class: 'table-wrap' },
      App.h('table', { class: 'table compacte' },
        App.h('thead', {}, App.h('tr', {},
          App.h('th', {}, 'Catégorie'),
          ...mois.map((m) => App.h('th', { class: 'right' }, court(m.mois))),
          App.h('th', { class: 'right' }, 'Moyenne'))),
        tbody));
  },
};
