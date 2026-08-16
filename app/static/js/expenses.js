/* Onglet « Dépenses » : flux courants, saisie manuelle, import de relevés. */
App.tabs.expenses = {
  cache: { transactions: [], month: null },

  async load() {
    const month = App.state.month;
    const [flows, txs, imports] = await Promise.all([
      App.api.get(`/api/month?month=${month}`),
      App.api.get(`/api/transactions?month=${month}`),
      App.api.get('/api/imports'),
    ]);
    App.tabs.expenses.cache = { transactions: txs, month };
    App.el('#ex-month-label').textContent = App.fmt.month(month);
    App.tabs.expenses.renderLastImport(imports);
    App.tabs.expenses.renderKpis(flows);
    App.tabs.expenses.fillCategoryFilter();
    App.tabs.expenses.renderTable();
    App.tabs.history.renderImports(imports);
  },

  renderLastImport(imports) {
    const host = App.el('#ex-last-import');
    if (!imports.length) {
      host.textContent = 'Aucun relevé importé pour le moment. '
        + 'Collez votre export CSV Revolut, ou votre relevé LCL converti en texte.';
      return;
    }
    const last = imports[0];
    host.textContent = `Dernier : ${last.source}, ${last.nombre_lignes} ligne(s) `
      + `jusqu’au ${App.fmt.date(last.periode_fin)} · ${imports.length} import(s) au total`;
  },

  renderKpis(f) {
    const host = App.el('#ex-kpis');
    App.clear(host);
    const kpi = App.tabs.overview.kpi;
    host.append(
      kpi('Revenus', App.fmt.eur(f.revenus), `${f.nb_transactions} transaction(s)`),
      kpi('Dépenses', App.fmt.eur(f.depenses),
        f.transferts_internes
          ? `hors ${App.fmt.eur(f.transferts_internes)} de virements internes` : null),
      kpi('Solde', App.fmt.signed(f.solde), null, f.solde >= 0 ? 'good' : 'bad'),
      kpi('Épargne', App.fmt.eur(f.epargne),
        f.taux_epargne === null ? null : `taux ${App.fmt.ratio(f.taux_epargne)}`),
    );
  },

  fillCategoryFilter() {
    const sel = App.el('#ex-filter-cat');
    const current = sel.value;
    App.clear(sel);
    sel.append(App.h('option', { value: '' }, 'Toutes catégories'));
    const used = [...new Set(App.tabs.expenses.cache.transactions.map((t) => t.category))].sort();
    for (const c of used) sel.append(App.h('option', { value: c }, c));
    sel.value = current;
  },

  renderTable() {
    const tbody = App.el('#ex-table tbody');
    App.clear(tbody);
    const q = (App.el('#ex-search').value || '').toLowerCase();
    const cat = App.el('#ex-filter-cat').value;
    const rows = App.tabs.expenses.cache.transactions.filter((t) => (
      (!q || t.description.toLowerCase().includes(q))
      && (!cat || t.category === cat)
    ));

    if (!rows.length) {
      const vide = App.tabs.expenses.cache.transactions.length === 0;
      tbody.append(App.h('tr', {}, App.h('td', { colspan: 6 },
        App.h('div', { class: 'empty-cta' },
          App.h('p', {}, vide
            ? `Aucune transaction en ${App.fmt.month(App.state.month)}.`
            : 'Aucune transaction ne correspond à ce filtre.'),
          vide ? App.h('button', {
            class: 'btn primary big',
            onclick: () => App.tabs.expenses.openImport(),
          }, '+ Ajouter un relevé') : null,
          vide ? ' ' : null,
          vide ? App.h('button', {
            class: 'btn',
            onclick: () => App.tabs.expenses.openForm(null),
          }, 'Saisir une transaction') : null))));
      return;
    }

    const assets = App.state.assets || [];
    const liabs = App.state.liabilities || [];
    for (const t of rows) {
      const link = t.asset_id
        ? (assets.find((a) => a.id === t.asset_id) || {}).label
        : (t.liability_id ? ((liabs.find((l) => l.id === t.liability_id) || {}).label
          || 'Prêt') : null);

      const catSelect = App.select('category', App.categoriesAll(), t.category, {
        class: 'small-select',
      });
      catSelect.addEventListener('change', async () => {
        try {
          await App.api.put(`/api/transactions/${t.id}`, { category: catSelect.value });
          t.category = catSelect.value;
          App.toast('Catégorie mise à jour', 'success');
          App.refreshOthers('expenses');
        } catch (e) { App.toast(e.message, 'error'); }
      });

      tbody.append(App.h('tr', {},
        App.h('td', { class: 'nowrap' }, App.fmt.date(t.date)),
        App.h('td', {}, App.h('div', { class: 'ell', title: t.description }, t.description)),
        App.h('td', {}, catSelect),
        App.h('td', { class: `right num ${t.amount < 0 ? 'neg' : 'pos'}` }, App.fmt.eur(t.amount)),
        App.h('td', {}, link ? App.h('span', { class: 'pill accent' }, link) : App.h('span', { class: 'muted' }, '—')),
        App.h('td', { class: 'right' },
          App.h('button', {
            class: 'icon-btn', title: 'Modifier',
            onclick: () => App.tabs.expenses.openForm(t),
          }, '✎'))));
    }
  },

  /* ---------- saisie manuelle ---------- */
  openForm(tx) {
    const isEdit = !!tx;
    const assets = [['', '— aucun —'], ...(App.state.assets || []).map((a) => [a.id, `${a.label} (${a.type})`])];
    const liabs = [['', '— aucun —'], ...(App.state.liabilities || []).map((l) => [l.id, l.label || l.type])];

    const form = App.h('form', { class: 'form-grid', onsubmit: (e) => e.preventDefault() },
      App.field('Date', App.input('date', { type: 'date', value: (tx && tx.date) || App.todayISO(), required: true })),
      App.field('Montant (€)', App.input('amount', {
        type: 'number', step: '0.01', value: tx ? tx.amount : '', required: true,
      }), { hint: 'Négatif = dépense, positif = revenu' }),
      App.field('Libellé', App.input('description', { value: (tx && tx.description) || '' }), { full: true }),
      App.field('Catégorie', App.select('category', App.categoriesAll(), tx ? tx.category : 'Non categorise')),
      App.field('Actif rattaché', App.select('asset_id', assets, tx ? tx.asset_id : ''),
        { hint: 'Loyer perçu, charge d’un bien…' }),
      App.field('Prêt rattaché', App.select('liability_id', liabs, tx ? tx.liability_id : '')),
    );

    const save = async () => {
      const values = App.formValues(form);
      values.amount = parseFloat(values.amount);
      if (Number.isNaN(values.amount)) return App.toast('Montant invalide', 'error');
      try {
        if (isEdit) await App.api.put(`/api/transactions/${tx.id}`, values);
        else await App.api.post('/api/transactions', values);
        App.modal.close();
        App.toast(isEdit ? 'Transaction modifiée' : 'Transaction ajoutée', 'success');
        await App.refreshAll();
      } catch (e) { App.toast(e.message, 'error'); }
    };

    const footer = [
      isEdit ? App.h('button', {
        class: 'btn danger',
        onclick: () => App.confirm('Supprimer cette transaction ?', async () => {
          await App.api.del(`/api/transactions/${tx.id}`);
          App.toast('Transaction supprimée', 'success');
          await App.refreshAll();
        }),
      }, 'Supprimer') : null,
      App.h('button', { class: 'btn', onclick: () => App.modal.close() }, 'Annuler'),
      App.h('button', { class: 'btn primary', onclick: save }, 'Enregistrer'),
    ].filter(Boolean);

    App.modal.open({ title: isEdit ? 'Modifier la transaction' : 'Nouvelle transaction', body: form, footer });
  },

  /* ---------- virements internes ---------- */

  /* Proposé après un import, seulement s'il y a quelque chose à proposer. */
  async suggestTransfers() {
    let res;
    try { res = await App.api.get('/api/transfers/detect'); } catch (e) { return; }
    if (!res.total) return;
    App.toast(
      App.h('span', {},
        `${res.total} virement(s) interne(s) possible(s) — `,
        App.h('a', {
          href: '#',
          onclick: (e) => { e.preventDefault(); App.tabs.expenses.openTransferDetection(res); },
        }, 'vérifier')),
      'info', 9000);
  },

  async openTransferDetection(prefetched) {
    let res = prefetched;
    if (!res) {
      try { res = await App.api.get('/api/transfers/detect'); }
      catch (e) { return App.toast(e.message, 'error'); }
    }
    if (!res.total) return App.toast('Aucun virement interne à rapprocher', 'success');

    const selected = new Set(res.paires.map((_, i) => i));
    const tbody = App.h('tbody', {});
    res.paires.forEach((pair, i) => {
      const check = App.h('input', { type: 'checkbox' });
      check.checked = true;
      check.addEventListener('change', () => {
        if (check.checked) selected.add(i); else selected.delete(i);
      });
      tbody.append(App.h('tr', {},
        App.h('td', {}, check),
        App.h('td', { class: 'right num' }, App.fmt.eur(pair.montant)),
        App.h('td', {},
          App.h('div', { class: 'ell', title: pair.sortie.description },
            `− ${pair.sortie.description}`),
          App.h('div', { class: 'a-meta' },
            `${App.fmt.date(pair.sortie.date)} · ${pair.sortie.category}`)),
        App.h('td', {},
          App.h('div', { class: 'ell', title: pair.entree.description },
            `+ ${pair.entree.description}`),
          App.h('div', { class: 'a-meta' },
            `${App.fmt.date(pair.entree.date)} · ${pair.entree.category}`)),
        App.h('td', { class: 'right' },
          App.h('span', { class: pair.ecart_jours <= 2 ? 'pill ok' : 'pill warn' },
            pair.ecart_jours === 0 ? 'même jour' : `${pair.ecart_jours} j`))));
    });

    const apply = async () => {
      const ids = [];
      res.paires.forEach((pair, i) => {
        if (selected.has(i)) ids.push(pair.sortie.id, pair.entree.id);
      });
      if (!ids.length) return App.toast('Aucune paire sélectionnée', 'error');
      try {
        const out = await App.api.post('/api/transfers/apply', { ids });
        App.modal.close();
        App.toast(`${out.modifiees} transaction(s) reclassées en « ${res.categorie} »`,
          'success');
        await App.refreshAll();
      } catch (e) { App.toast(e.message, 'error'); }
    };

    App.modal.open({
      title: 'Virements internes détectés',
      wide: true,
      body: App.h('div', {},
        App.h('p', { class: 'hint' },
          `${res.total} paire(s) trouvée(s), ${App.fmt.eur(res.montant_total)} au total. `
          + `Classées en « ${res.categorie} », ces lignes ne compteront `
          + 'ni comme dépense ni comme revenu : l’argent a simplement changé de poche.'),
        App.h('p', { class: 'hint' },
          'Seules des lignes issues de deux relevés différents sont appariées — '
          + 'vérifiez tout de même chaque paire avant de valider.'),
        App.h('div', { class: 'table-wrap scroll-y', style: 'margin-top:12px' },
          App.h('table', { class: 'table' },
            App.h('thead', {}, App.h('tr', {},
              App.h('th', {}, '✓'), App.h('th', { class: 'right' }, 'Montant'),
              App.h('th', {}, 'Débit'), App.h('th', {}, 'Crédit'),
              App.h('th', { class: 'right' }, 'Écart'))),
            tbody))),
      footer: [
        App.h('button', { class: 'btn', onclick: () => App.modal.close() }, 'Annuler'),
        App.h('button', { class: 'btn primary', onclick: apply },
          'Marquer comme virements internes'),
      ],
    });
  },

  /* ---------- import ---------- */
  openImport() {
    const textarea = App.h('textarea', {
      name: 'text', rows: 12,
      placeholder: 'Collez ici le CSV Revolut, ou le texte formaté extrait de votre relevé LCL…',
    });
    const source = App.select('source', ['Revolut', 'LCL', 'TradeRepublic', 'Manuel'], 'Revolut');

    const body = App.h('div', {},
      App.h('div', { class: 'form-grid' },
        App.field('Source', source),
        App.h('div', { class: 'field' },
          App.h('label', {}, 'Aide'),
          App.h('span', { class: 'hint' },
            'CSV, TSV ou texte séparé par des points-virgules. '
            + 'Le séparateur, les colonnes et le format des montants sont détectés automatiquement. '
            + 'Pour un relevé LCL en PDF, faites-le convertir en texte tabulé, puis collez-le ici.'))),
      App.h('div', { class: 'field full', style: 'margin-top:12px' },
        App.h('label', {}, 'Contenu du relevé'), textarea));

    const analyse = async () => {
      try {
        const res = await App.api.post('/api/imports/preview', { text: textarea.value });
        App.tabs.expenses.showPreview(res, source.value);
      } catch (e) { App.toast(e.message, 'error'); }
    };

    App.modal.open({
      title: 'Importer un relevé',
      body,
      wide: true,
      footer: [
        App.h('button', { class: 'btn', onclick: () => App.modal.close() }, 'Annuler'),
        App.h('button', { class: 'btn primary', onclick: analyse }, 'Analyser'),
      ],
    });
  },

  showPreview(res, sourceName) {
    const lines = res.lignes;
    const table = App.h('table', { class: 'table' },
      App.h('thead', {}, App.h('tr', {},
        App.h('th', { style: 'width:34px' }, '✓'),
        App.h('th', { style: 'width:104px' }, 'Date'),
        App.h('th', {}, 'Libellé'),
        App.h('th', { style: 'width:180px' }, 'Catégorie'),
        App.h('th', { class: 'right', style: 'width:110px' }, 'Montant'),
        App.h('th', { style: 'width:120px' }, 'Détection'))));
    const tbody = App.h('tbody', {});
    table.append(tbody);

    lines.forEach((line) => {
      const check = App.h('input', { type: 'checkbox' });
      check.checked = !line.ignore;
      check.addEventListener('change', () => { line.ignore = !check.checked; });

      const cat = App.select('c', App.categoriesAll(), line.category);
      cat.addEventListener('change', () => { line.category = cat.value; });

      const badge = {
        regle: ['accent', 'règle'],
        pret: ['ok', 'prêt détecté'],
        transfert: ['ok', 'virement interne'],
        'mot-cle': ['', 'mot-clé'],
        defaut: ['', '—'],
      }[line.origine] || ['', ''];

      tbody.append(App.h('tr', {},
        App.h('td', {}, check),
        App.h('td', { class: 'nowrap' }, App.fmt.date(line.date)),
        App.h('td', {}, App.h('div', { class: 'ell', title: line.description }, line.description)),
        App.h('td', {}, cat),
        App.h('td', { class: `right num ${line.amount < 0 ? 'neg' : 'pos'}` }, App.fmt.eur(line.amount)),
        App.h('td', {},
          line.doublon
            ? App.h('span', { class: 'pill warn' }, 'doublon')
            : App.h('span', { class: `pill ${badge[0]}` }, badge[1]))));
    });

    const body = App.h('div', {},
      App.h('p', { class: 'hint' },
        `${res.total} ligne(s) reconnue(s), ${res.doublons} doublon(s) déjà en base `
        + '(décochés par défaut). Vérifiez les catégories avant de confirmer.'),
      ...(res.avertissements || []).map((w) => App.h('p', { class: 'hint' }, `⚠ ${w}`)),
      App.h('div', { class: 'actions', style: 'margin:10px 0' },
        App.h('button', {
          class: 'btn small',
          onclick: () => App.els('input[type=checkbox]', tbody).forEach((c, i) => {
            c.checked = true; lines[i].ignore = false;
          }),
        }, 'Tout cocher'),
        App.h('button', {
          class: 'btn small',
          onclick: () => App.els('input[type=checkbox]', tbody).forEach((c, i) => {
            c.checked = false; lines[i].ignore = true;
          }),
        }, 'Tout décocher')),
      App.h('div', { class: 'table-wrap scroll-y' }, table));

    const confirm = async () => {
      try {
        const out = await App.api.post('/api/imports/confirm', { source: sourceName, lignes: lines });
        App.modal.close();
        App.toast(`${out.importees} transaction(s) importée(s), ${out.ignorees} ignorée(s)`, 'success');
        await App.refreshAll();
        // Un virement entre vos comptes n'apparaît qu'une fois les deux relevés
        // importés : c'est donc ici, et nulle part ailleurs, qu'il faut
        // regarder. Silencieux s'il n'y a rien à proposer — plutôt qu'un
        // bouton permanent qu'on ne pense jamais à cliquer.
        await App.tabs.expenses.suggestTransfers();
      } catch (e) { App.toast(e.message, 'error'); }
    };

    App.modal.open({
      title: `Prévisualisation — ${sourceName}`,
      body,
      wide: true,
      footer: [
        App.h('button', { class: 'btn', onclick: () => App.tabs.expenses.openImport() }, 'Retour'),
        App.h('button', { class: 'btn primary', onclick: confirm }, 'Confirmer l’import'),
      ],
    });
  },
};
