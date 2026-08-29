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
    App.tabs.expenses.renderImports(imports);
  },

  renderLastImport(imports) {
    const host = App.el('#ex-last-import');
    if (!imports.length) {
      host.textContent = 'Aucun relevé importé pour le moment. '
        + 'Déposez un export CSV, ou le PDF téléchargé depuis votre banque.';
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
      // Compter TOUT le mois sous « Revenus » ne disait rien : le nombre
      // englobait les dépenses.
      kpi('Revenus', App.fmt.eur(f.revenus), `${f.nb_revenus} ligne(s)`),
      kpi('Dépenses', App.fmt.eur(f.depenses),
        f.transferts_internes
          ? `hors ${App.fmt.eur(f.transferts_internes)} de virements internes`
          : `${f.nb_depenses} ligne(s)`),
      kpi('Solde', App.fmt.signed(f.solde), null, f.solde >= 0 ? 'good' : 'bad'),
      kpi('Épargne', App.fmt.eur(f.epargne),
        f.taux_epargne === null ? null : `taux ${App.fmt.ratio(f.taux_epargne)}`),
    );
  },

  /* Le filtre gagne « À classer » en tête : c'est le geste principal après un
     import, et il n'y avait aucun moyen d'isoler ces lignes. */
  NON_CATEGORISE: 'Non categorise',

  fillCategoryFilter() {
    const sel = App.el('#ex-filter-cat');
    const current = sel.value;
    App.clear(sel);
    sel.append(App.h('option', { value: '' }, 'Toutes catégories'));
    sel.append(App.h('option', { value: App.tabs.expenses.NON_CATEGORISE }, 'À classer'));
    const used = [...new Set(App.tabs.expenses.cache.transactions.map((t) => t.category))]
      .filter((c) => c !== App.tabs.expenses.NON_CATEGORISE).sort();
    for (const c of used) sel.append(App.h('option', { value: c }, c));
    sel.value = current;
  },

  /* Lignes cochées, pour les actions groupées. Conservées entre deux rendus :
     filtrer, cocher, changer de filtre, cocher encore, agir une seule fois. */
  selection: new Set(),

  lignesFiltrees() {
    const q = (App.el('#ex-search').value || '').trim().toLowerCase();
    const cat = App.el('#ex-filter-cat').value;
    return App.tabs.expenses.cache.transactions.filter((t) => (
      (!q || t.description.toLowerCase().includes(q))
      && (!cat || t.category === cat)
    ));
  },

  /* Cellule de catégorie.

     C'était un `<select>` par ligne, portant toutes les catégories, reconstruit
     intégralement à chaque frappe dans la recherche : deux cents listes
     déroulantes vivantes pour un seul choix à faire, et un tableau qui ne
     ressemblait plus à un tableau. Le texte redevient du texte, et la liste
     n'existe qu'au moment où on la déroule. */
  celluleCategorie(t) {
    const cell = App.h('td', {});
    const afficher = () => {
      App.clear(cell);
      cell.append(App.h('button', {
        class: 'cat-cell', title: 'Changer la catégorie',
        onclick: () => editer(),
      }, t.category));
    };
    const editer = () => {
      App.clear(cell);
      const sel = App.select('category', App.categoriesAll(), t.category,
        { class: 'small-select' });
      const enregistrer = async () => {
        if (sel.value === t.category) { afficher(); return; }
        try {
          await App.api.put(`/api/transactions/${t.id}`, { category: sel.value });
          t.category = sel.value;
          App.toast('Catégorie mise à jour', 'success');
          await App.refreshOthers();
        } catch (e) { App.toast(e.message, 'error'); }
        afficher();
      };
      sel.addEventListener('change', enregistrer);
      sel.addEventListener('blur', () => { if (sel.isConnected) afficher(); });
      cell.append(sel);
      sel.focus();
    };
    afficher();
    return cell;
  },

  /* Barre d'actions groupées, visible dès la première ligne cochée. */
  renderBulk() {
    const host = App.el('#ex-bulk');
    App.clear(host);
    const n = App.tabs.expenses.selection.size;
    host.hidden = n === 0;
    if (!n) return;

    const sel = App.select('cat', App.categoriesAll(), null, { class: 'small-select' });
    sel.selectedIndex = -1;
    sel.addEventListener('change', async () => {
      try {
        const res = await App.api.post('/api/transactions/categorie',
          { ids: [...App.tabs.expenses.selection], category: sel.value });
        App.toast(`${res.modifiees} ligne(s) classée(s) en « ${res.category} »`, 'success');
        App.tabs.expenses.selection.clear();
        await App.refreshAll();
      } catch (e) { App.toast(e.message, 'error'); }
    });

    host.append(
      App.h('span', {}, `${n} ligne(s) sélectionnée(s)`),
      App.h('span', { class: 'sub' }, 'Classer en'),
      sel,
      App.h('button', {
        class: 'btn small danger',
        onclick: () => App.confirm(`Supprimer ${n} transaction(s) ?`, async () => {
          try {
            const res = await App.api.post('/api/transactions/suppression',
              { ids: [...App.tabs.expenses.selection] });
            App.toast(`${res.supprimees} transaction(s) supprimée(s)`, 'success');
            App.tabs.expenses.selection.clear();
            await App.refreshAll();
          } catch (e) { App.toast(e.message, 'error'); }
        }),
      }, 'Supprimer'),
      App.h('button', {
        class: 'btn small',
        onclick: () => {
          App.tabs.expenses.selection.clear();
          App.tabs.expenses.renderTable();
        },
      }, 'Tout décocher'));
  },

  renderTable() {
    const tbody = App.el('#ex-table tbody');
    App.clear(tbody);
    const rows = App.tabs.expenses.lignesFiltrees();
    const toutCocher = App.el('#ex-select-all');

    if (!rows.length) {
      toutCocher.checked = false;
      App.tabs.expenses.renderBulk();
      const vide = App.tabs.expenses.cache.transactions.length === 0;
      tbody.append(App.h('tr', {}, App.h('td', { colspan: 7 },
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

      const coche = App.h('input', { type: 'checkbox', 'aria-label': 'Sélectionner' });
      coche.checked = App.tabs.expenses.selection.has(t.id);
      coche.addEventListener('change', () => {
        if (coche.checked) App.tabs.expenses.selection.add(t.id);
        else App.tabs.expenses.selection.delete(t.id);
        toutCocher.checked = rows.every((r) => App.tabs.expenses.selection.has(r.id));
        App.tabs.expenses.renderBulk();
      });

      tbody.append(App.h('tr', {},
        App.h('td', { class: 'center' }, coche),
        App.h('td', { class: 'nowrap' }, App.fmt.date(t.date)),
        App.h('td', {}, App.h('div', { class: 'ell', title: t.description }, t.description)),
        App.tabs.expenses.celluleCategorie(t),
        App.h('td', { class: `right num ${t.amount < 0 ? 'neg' : 'pos'}` }, App.fmt.eur(t.amount)),
        App.h('td', {}, link
          ? App.h('span', { class: 'pill accent' }, link)
          : App.h('span', { class: 'muted' }, '—')),
        App.h('td', { class: 'right' },
          App.h('button', {
            class: 'icon-btn', title: 'Modifier',
            onclick: () => App.tabs.expenses.openForm(t),
          }, '\u270e'))));
    }
    toutCocher.checked = rows.every((r) => App.tabs.expenses.selection.has(r.id));
    App.tabs.expenses.renderBulk();
  },

  /* Coche ou décoche ce que le filtre courant laisse voir, et rien d'autre :
     cocher des lignes invisibles serait une action à l'aveugle. */
  toutSelectionner(actif) {
    for (const t of App.tabs.expenses.lignesFiltrees()) {
      if (actif) App.tabs.expenses.selection.add(t.id);
      else App.tabs.expenses.selection.delete(t.id);
    }
    App.tabs.expenses.renderTable();
  },

  /* ---------- journal des imports ----------
     Il s'affichait dans cet onglet mais son code vivait dans
     `App.tabs.history`, qui ne le rendait pas : c'est `expenses.load()`
     qui appelait la fonction de l'autre module. Le code rejoint l'ecran. */
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
            onclick: () => App.tabs.expenses.showImport(imp),
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

  /* ---------- saisie manuelle ---------- */
  openForm(tx) {
    const isEdit = !!tx;
    const assets = [['', '— aucun —'], ...(App.state.assets || []).map((a) => [a.id, `${a.label} (${a.type})`])];
    const liabs = [['', '— aucun —'], ...(App.state.liabilities || []).map((l) => [l.id, l.label || l.type])];

    const form = App.h('form', { class: 'form-grid', onsubmit: (e) => e.preventDefault() },
      App.field('Date', App.dateField('date', {
        value: (tx && tx.date) || App.todayISO(), required: true,
      })),
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
      if (Number.isNaN(values.amount)) {
        return App.invalide(form, 'amount', 'Indiquez un montant. Négatif pour une dépense.');
      }
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

  /* ---------- import ----------

     Le fichier est lu, puis ANALYSE tout de suite : il n'y a rien a demander
     de plus, le parseur deduit deja separateur, colonnes et format des
     montants. Le texte extrait reste affiche en dessous, pour qu'un PDF mal
     decoupe puisse etre corrige avant confirmation.

     Le menu deroulant « Source » a disparu. Il ne servait qu'a etiqueter le
     journal des imports, et le nom du fichier le dit mieux qu'une banque
     choisie dans une liste de quatre. */
  openImport() {
    const textarea = App.h('textarea', {
      name: 'text', rows: 10,
      placeholder: '… ou collez ici le contenu de votre relevé',
    });
    let source = 'Collé';

    const analyse = async () => {
      try {
        const res = await App.api.post('/api/imports/preview', { text: textarea.value });
        App.tabs.expenses.showPreview(res, source);
      } catch (e) { App.toast(e.message, 'error'); }
    };

    const depot = App.fileDrop({
      onText: (text, nom) => {
        textarea.value = text;
        source = nom || 'Fichier';
        analyse();
      },
    });

    App.modal.open({
      title: 'Importer un relevé',
      wide: true,
      garder: true,
      body: App.h('div', {},
        depot,
        App.h('div', { class: 'field full', style: 'margin-top:14px' },
          App.h('label', {}, 'Ou coller le contenu'), textarea),
        App.note('Ce qui est reconnu',
          App.h('p', {},
            'Les exports CSV ou TSV de votre banque, et les relevés PDF '
            + 'téléchargés depuis votre espace client. Le séparateur, les colonnes '
            + 'et le format des montants sont détectés automatiquement.'),
          App.h('p', {},
            'Un PDF scanné ne contient pas de texte, seulement une image : '
            + 'celui-là ne peut pas être lu.'))),
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
      garder: true,
      footer: [
        App.h('button', { class: 'btn', onclick: () => App.tabs.expenses.openImport() }, 'Retour'),
        App.h('button', { class: 'btn primary', onclick: confirm }, 'Confirmer l’import'),
      ],
    });
  },
};
