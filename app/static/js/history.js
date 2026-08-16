/* Onglet « Historique » : archive mensuelle recalculée + journal des imports. */
App.tabs.history = {
  async load() {
    // Le journal des imports vit desormais dans l'onglet Depenses, la ou les
    // imports se font. Ici, seule l'archive mensuelle.
    const data = await App.api.get('/api/history');
    App.tabs.history.renderArchive(data.archive);
  },

  renderArchive(archive) {
    const tbody = App.el('#hi-archive tbody');
    App.clear(tbody);
    if (!archive.length) {
      tbody.append(App.h('tr', {}, App.h('td', { colspan: 8, class: 'empty' },
        'Aucune donnée historique pour le moment.')));
      return;
    }
    for (const row of archive) {
      const rep = App.h('div', { class: 'actions' });
      for (const b of row.repartition || []) {
        const ecart = b.reel_pct - b.cible_pct;
        rep.append(App.h('span', {
          class: `pill ${Math.abs(ecart) < 5 ? 'ok' : 'warn'}`,
          title: `${b.label} : cible ${App.fmt.num(b.cible_pct, 1)} %`,
        }, `${b.label} ${App.fmt.num(b.reel_pct, 0)} %`));
      }
      const tr = App.h('tr', {},
        App.h('td', {},
          App.h('button', {
            class: 'btn small',
            onclick: () => App.goToMonth(row.mois),
          }, App.fmt.month(row.mois))),
        App.h('td', { class: 'right num pos' }, App.fmt.eur(row.revenus)),
        App.h('td', { class: 'right num' }, App.fmt.eur(row.depenses)),
        App.h('td', { class: `right num ${row.solde >= 0 ? 'pos' : 'neg'}` }, App.fmt.signed(row.solde)),
        App.h('td', { class: 'right num' }, App.fmt.eur(row.epargne)),
        App.h('td', { class: 'right num' },
          row.taux_epargne === null ? '—' : App.fmt.ratio(row.taux_epargne)),
        App.h('td', { class: 'right num' }, App.fmt.eur(row.patrimoine_net)),
        App.h('td', {}, rep));
      tbody.append(tr);
    }
  },

  renderImports(imports) {
    const tbody = App.el('#hi-imports tbody');
    App.clear(tbody);
    if (!imports.length) {
      tbody.append(App.h('tr', {}, App.h('td', { colspan: 5, class: 'empty' },
        'Aucun import enregistré.')));
      return;
    }
    for (const imp of imports) {
      tbody.append(App.h('tr', {},
        App.h('td', { class: 'nowrap' }, App.fmt.dateTime(imp.date_import)),
        App.h('td', {}, App.h('span', { class: 'pill accent' }, imp.source)),
        App.h('td', { class: 'nowrap' },
          `${App.fmt.date(imp.periode_debut)} → ${App.fmt.date(imp.periode_fin)}`),
        App.h('td', { class: 'right num' }, imp.nombre_lignes),
        App.h('td', { class: 'right' },
          App.h('button', {
            class: 'btn small',
            onclick: () => App.tabs.history.showImport(imp),
          }, 'Voir'),
          ' ',
          App.h('button', {
            class: 'btn small danger',
            onclick: () => App.confirm(
              `Annuler cet import ? Les ${imp.nombre_lignes} transaction(s) associée(s) seront supprimées.`,
              async () => {
                await App.api.del(`/api/imports/${imp.id}`);
                App.toast('Import annulé', 'success');
                await App.refreshAll();
              }),
          }, 'Annuler'))));
    }
  },

  async showImport(imp) {
    const txs = await App.api.get(`/api/transactions?import_id=${imp.id}`);
    App.modal.open({
      title: `Import ${imp.source} — ${App.fmt.dateTime(imp.date_import)}`,
      wide: true,
      body: txs.length
        ? App.tabs.wealth.txTable(txs)
        : App.h('p', { class: 'muted' }, 'Aucune transaction rattachée (elles ont peut-être été supprimées).'),
      footer: [App.h('button', { class: 'btn primary', onclick: () => App.modal.close() }, 'Fermer')],
    });
  },
};
