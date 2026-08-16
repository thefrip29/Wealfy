/* Onglet « Patrimoine » : actifs, mouvements, prêts, immobilier, PEA. */
App.tabs.wealth = {
  MARKET: ['PEA', 'CTO', 'Crypto', 'AssuranceVie', 'PER'],
  PROPERTY: ['Immobilier', 'SCPI', 'Vehicule'],
  RATE: ['Livret', 'LDDS', 'LEP', 'LivretJeune', 'PEL', 'CEL', 'DepotTerme'],
  openGroups: new Set(),

  async load() {
    const archived = App.el('#we-archived').checked ? '1' : '0';
    const [snap, market] = await Promise.all([
      App.api.get(`/api/assets?archived=${archived}`),
      App.api.get('/api/market/status'),
    ]);
    App.state.portfolio = snap;
    App.state.market = market;
    App.tabs.wealth.renderKpis(snap);
    App.tabs.wealth.renderAssets(snap);
    App.tabs.wealth.renderLiabilities(snap.liabilities);
    App.tabs.wealth.renderMarketState(market);
  },

  /* Pastille de fraîcheur des cours, à côté du bouton de rafraîchissement. */
  renderMarketState(market) {
    const host = App.el('#we-market-state');
    App.clear(host);
    App.el('#we-refresh-quotes').disabled = !market.active;
    if (!market.active) {
      host.append(App.h('a', {
        href: '#', class: 'pill',
        onclick: (e) => { e.preventDefault(); App.settings.open('cours'); },
      }, 'cours désactivés'));
      return;
    }
    if (!market.dernier_refresh) {
      host.append(App.h('span', { class: 'pill warn' }, 'jamais rafraîchi'));
      return;
    }
    host.append(App.h('span', {
      class: market.cache_perime ? 'pill warn' : 'pill live',
      title: `Dernier rafraîchissement : ${App.fmt.dateTime(market.dernier_refresh)}`,
    }, market.cache_perime ? 'cours périmés' : 'cours à jour'));
    if (market.tickers_non_mappes.length) {
      host.append(' ', App.h('a', {
        href: '#', class: 'pill warn',
        onclick: (e) => { e.preventDefault(); App.settings.open('cours'); },
      }, `${market.tickers_non_mappes.length} ligne(s) sans symbole`));
    }
  },

  async refreshQuotes(btn) {
    btn.classList.add('busy');
    try {
      const res = await App.api.post('/api/market/refresh');
      App.toast(`${res.ok} cours récupéré(s), ${res.ko} en échec`,
        res.ko ? 'error' : 'success');
      await App.refreshAll();
    } catch (e) {
      App.toast(e.message, 'error');
    }
    btn.classList.remove('busy');
  },

  renderKpis(snap) {
    const host = App.el('#we-kpis');
    App.clear(host);
    const kpi = App.tabs.overview.kpi;
    const crypto = snap.assets.filter((a) => a.type === 'Crypto')
      .reduce((s, a) => s + a.valeur, 0);
    const pv = snap.assets.reduce((s, a) => s + a.plus_value, 0);
    host.append(
      kpi('Patrimoine net', App.fmt.eur(snap.patrimoine_net)),
      kpi('Total actifs', App.fmt.eur(snap.total_actif), `${snap.assets.length} actif(s)`),
      kpi('Capital restant dû', App.fmt.eur(snap.total_passif), `${snap.liabilities.length} prêt(s)`),
      kpi('Plus-value latente', App.fmt.signed(pv),
        snap.total_actif ? `crypto : ${App.fmt.pct(100 * crypto / snap.patrimoine_net)} du net` : null,
        pv >= 0 ? 'good' : 'bad'),
    );
  },

  renderAssets(snap) {
    const host = App.el('#we-assets');
    App.clear(host);
    if (!snap.assets.length) {
      host.append(App.h('div', { class: 'empty-cta' },
        App.h('p', {}, 'Votre patrimoine est vide pour le moment.'),
        App.h('button', {
          class: 'btn primary big',
          onclick: () => App.tabs.wealth.openAddChooser(),
        }, '+ Ajouter un premier produit')));
      return;
    }
    const groups = {};
    for (const a of snap.assets) (groups[a.famille] = groups[a.famille] || []).push(a);

    for (const [famille, assets] of Object.entries(groups).sort()) {
      const total = assets.reduce((s, a) => s + a.valeur, 0);
      const isOpen = App.tabs.wealth.openGroups.has(famille)
        || App.tabs.wealth.openGroups.size === 0;
      const group = App.h('div', { class: `group${isOpen ? ' open' : ''}` });
      const head = App.h('div', { class: 'group-head' },
        App.h('div', { class: 'g-left' },
          App.h('span', { class: 'caret' }, '›'),
          App.h('strong', {}, famille),
          App.h('span', { class: 'pill' }, `${assets.length}`)),
        App.h('div', { class: 'num' },
          App.h('strong', {}, App.fmt.eur(total)),
          ' ',
          App.h('span', { class: 'sub' },
            snap.total_actif ? `${App.fmt.num(100 * total / snap.total_actif, 1)} %` : '')));
      head.addEventListener('click', () => {
        group.classList.toggle('open');
        if (group.classList.contains('open')) App.tabs.wealth.openGroups.add(famille);
        else App.tabs.wealth.openGroups.delete(famille);
      });
      group.append(head);

      // `.group-inner` porte l'overflow : c'est ce qui rend le repli fluide
      // (grid-template-rows 0fr -> 1fr).
      const inner = App.h('div', { class: 'group-inner' });
      const bodyNode = App.h('div', { class: 'group-body' }, inner);
      for (const a of assets) {
        const pvClass = a.plus_value > 0 ? 'pos' : (a.plus_value < 0 ? 'neg' : 'muted');
        inner.append(App.h('div', { class: 'asset-row' },
          App.h('div', {},
            App.h('div', { class: 'a-name' }, a.label, a.archived ? ' ' : '',
              a.archived ? App.h('span', { class: 'pill' }, 'archivé') : null),
            App.h('div', { class: 'a-meta' },
              `${a.type} · acquis le ${App.fmt.date(a.date_acquisition)}`)),
          App.h('div', { class: 'right' },
            App.h('div', { class: 'num' }, App.fmt.eur(a.valeur)),
            App.tabs.wealth.sourceBadge(a)),
          App.h('div', { class: `right num ${pvClass}` },
            App.fmt.signed(a.plus_value),
            a.plus_value_pct !== null
              ? App.h('div', { class: 'a-meta' }, App.fmt.ratio(a.plus_value_pct)) : null),
          App.h('div', { class: 'right sub' }, `investi ${App.fmt.eur(a.investi, true)}`),
          App.h('div', { class: 'right' },
            App.h('button', {
              class: 'btn small',
              onclick: () => App.tabs.wealth.openAssetDetail(a.id),
            }, 'Détail'))));
      }
      group.append(bodyNode);
      host.append(group);
    }
  },

  /* D'où vient la valeur affichée : cours de marché, taux, indice, ou saisie. */
  sourceBadge(asset) {
    const map = {
      marche: ['live', 'cours de marché'],
      taux: ['ok', 'intérêts calculés'],
      indice: ['accent', 'estimation indicielle'],
    };
    const badge = map[asset.valeur_source];
    if (!badge) return null;
    const title = asset.valeur_saisie !== undefined && asset.valeur_saisie !== null
      ? `Valeur saisie : ${App.fmt.eur(asset.valeur_saisie)}` : '';
    return App.h('div', { class: 'a-meta' },
      App.h('span', { class: `pill ${badge[0]}`, title }, badge[1]));
  },

  renderLiabilities(liabs) {
    const tbody = App.el('#we-liabilities tbody');
    App.clear(tbody);
    if (!liabs.length) {
      tbody.append(App.h('tr', {}, App.h('td', { colspan: 7, class: 'empty' }, 'Aucun prêt enregistré.')));
      return;
    }
    const assets = (App.state.portfolio && App.state.portfolio.assets) || [];
    for (const l of liabs) {
      const asset = assets.find((a) => a.id === l.asset_id);
      tbody.append(App.h('tr', {},
        App.h('td', {},
          App.h('div', {}, l.label || l.type),
          App.h('div', { class: 'a-meta' },
            `${App.fmt.eur(l.montant_emprunte, true)} à ${App.fmt.num(l.taux_annuel, 2)} % sur ${l.duree_mois} mois`)),
        App.h('td', {}, asset ? App.h('span', { class: 'pill accent' }, asset.label) : App.h('span', { class: 'muted' }, '—')),
        App.h('td', { class: 'right num' }, App.fmt.eur(l.mensualite_avec_assurance)),
        App.h('td', { class: 'right num' }, App.fmt.eur(l.capital_restant)),
        App.h('td', { class: 'right num' }, `${l.echeances_payees} / ${l.echeances_totales}`),
        App.h('td', { class: 'right nowrap' }, App.fmt.date(l.date_fin)),
        App.h('td', { class: 'right' },
          App.h('button', { class: 'btn small', onclick: () => App.tabs.wealth.openLiabilityDetail(l.id) }, 'Détail'))));
    }
  },

  /* ==================================================================
     Positions : lignes d'un PEA/CTO, cryptos détenues.
     Choisir l'instrument crée aussi sa correspondance de cotation —
     plus besoin de passer par les paramètres.
     ================================================================== */

  async panelPositions(asset, data) {
    const host = App.h('div', {});
    await App.tabs.wealth.renderPositions(host, asset, data);
    return host;
  },

  async renderPositions(host, asset, data) {
    const crypto = App.tabs.wealth.MARKET.includes(asset.type) && asset.type === 'Crypto';
    const kind = asset.type === 'Crypto' ? 'crypto' : 'titre';
    const mot = kind === 'crypto' ? 'crypto' : 'ligne';
    let positions;
    try {
      positions = await App.api.get(`/api/assets/${asset.id}/positions`);
    } catch (e) { return App.toast(e.message, 'error'); }
    // `data` vient de la fiche (PRU, TRI, valeur retenue). Absent lors d'un
    // simple rafraîchissement après ajout : on le relit alors.
    if (!data) {
      try { data = await App.api.get(`/api/assets/${asset.id}`); }
      catch (e) { data = null; }
    }
    const marche = (data && data.marche) || {};

    App.clear(host);

    const tbody = App.h('tbody', {});
    if (!positions.lignes.length) {
      tbody.append(App.h('tr', {}, App.h('td', { colspan: 7 },
        App.h('div', { class: 'empty-cta' },
          App.h('p', {}, kind === 'crypto'
            ? 'Aucune crypto dans ce portefeuille.'
            : 'Aucune ligne dans ce compte.'),
          App.h('button', {
            class: 'btn primary',
            onclick: () => App.tabs.wealth.openInstrumentSearch(asset, host),
          }, kind === 'crypto' ? '+ Choisir mes cryptos' : '+ Choisir mes supports')))));
    }
    for (const ligne of positions.lignes) {
      const gain = ligne.plus_value;
      tbody.append(App.h('tr', {},
        App.h('td', {},
          App.h('div', {}, ligne.libelle || ligne.ticker),
          App.h('div', { class: 'a-meta' },
            App.h('code', {}, ligne.ticker),
            ligne.symbole && ligne.symbole !== ligne.ticker ? ` · ${ligne.symbole}` : '')),
        App.h('td', { class: 'right num' }, App.fmt.num(ligne.quantite, 6)),
        App.h('td', { class: 'right num' },
          ligne.pru == null ? '—' : App.fmt.eur(ligne.pru)),
        App.h('td', { class: 'right num' },
          ligne.cours == null
            ? App.h('span', { class: 'pill warn' }, 'non coté')
            : App.fmt.eur(ligne.cours),
          ligne.cours_date
            ? App.h('div', { class: 'a-meta' }, App.fmt.date(ligne.cours_date)) : null),
        App.h('td', { class: 'right num' },
          ligne.valeur == null ? '—' : App.fmt.eur(ligne.valeur)),
        App.h('td', {
          class: `right num ${gain > 0 ? 'pos' : (gain < 0 ? 'neg' : '')}`,
        }, gain == null ? '—' : App.fmt.signed(gain),
          ligne.ecart_pru_pct == null ? null
            : App.h('div', { class: 'a-meta' }, App.fmt.pct(ligne.ecart_pru_pct, 2))),
        App.h('td', { class: 'right' },
          App.h('button', {
            class: 'btn small',
            title: `Ajouter un ${kind === 'crypto' ? 'achat' : 'versement'} sur cette ${mot}`,
            onclick: () => App.tabs.wealth.openPositionForm(asset, host, {
              ticker: ligne.ticker, symbol: ligne.symbole, label: ligne.libelle,
            }),
          }, '+ Achat'))));
    }

    // Chiffres de synthèse en tête : ils occupaient auparavant deux onglets
    // séparés (« Résumé » et « PRU & TRI ») pour les mêmes lignes.
    const resume = App.h('div', { class: 'metric-list' });
    const rows = [
      ['Capital investi', App.fmt.eur(positions.investi_total)],
      ['Valeur de marché', positions.valeur_totale == null
        ? '— (aucun cours en cache)' : App.fmt.eur(positions.valeur_totale)],
    ];
    if (positions.valeur_totale != null) {
      rows.push(['Plus-value latente',
        App.fmt.signed(Math.round(
          (positions.valeur_totale - positions.investi_total) * 100) / 100)]);
    }
    if (marche.pru != null) rows.push(['PRU moyen', App.fmt.eur(marche.pru)]);
    if (marche.tri_pct != null) {
      rows.push(['TRI annualisé', App.fmt.pct(marche.tri_pct, 2)]);
    }
    for (const [l, v] of rows) {
      resume.append(App.h('div', { class: 'metric-row' },
        App.h('span', { class: 'm-label' }, l), App.h('span', { class: 'm-value' }, v)));
    }

    const benchHost = App.h('div', {});
    const loadBenchmark = async (btn) => {
      btn.classList.add('busy');
      try {
        const res = await App.api.get(`/api/assets/${asset.id}/benchmark`);
        App.tabs.wealth.renderBenchmark(benchHost, res);
      } catch (e) { App.toast(e.message, 'error'); }
      btn.classList.remove('busy');
    };

    // Element.append() transforme null en texte « null » — contrairement à
    // App.h qui filtre ses enfants. On nettoie donc explicitement.
    host.append(...[
      resume,
      !positions.complet && positions.lignes.length
        ? App.h('p', { class: 'callout', style: 'margin-top:12px' },
          'Au moins une ligne n’a pas de cours en cache : la valeur de l’actif '
          + 'reste celle que vous avez saisie, plutôt qu’un total partiel présenté '
          + 'comme complet. Rafraîchissez les cours, ou vérifiez le symbole.')
        : null,
      App.h('div', { class: 'table-wrap', style: 'margin-top:14px' },
        App.h('table', { class: 'table' },
          App.h('thead', {}, App.h('tr', {},
            App.h('th', {}, kind === 'crypto' ? 'Crypto' : 'Support'),
            App.h('th', { class: 'right' }, 'Quantité'),
            App.h('th', { class: 'right' }, 'PRU'),
            App.h('th', { class: 'right' }, 'Cours'),
            App.h('th', { class: 'right' }, 'Valeur'),
            App.h('th', { class: 'right' }, 'Gain'),
            App.h('th', {}))),
          tbody)),
      App.h('div', { class: 'actions', style: 'margin-top:14px' },
        App.h('button', {
          class: 'btn primary',
          onclick: () => App.tabs.wealth.openInstrumentSearch(asset, host),
        }, kind === 'crypto' ? '+ Ajouter une crypto' : '+ Ajouter un support'),
        App.h('button', {
          class: 'btn',
          onclick: () => App.tabs.wealth.openMovementImport(asset),
        }, 'Importer un relevé'),
        App.h('button', {
          class: 'btn',
          onclick: () => App.tabs.wealth.openPositionForm(asset, host, null),
        }, 'Saisir un symbole à la main')),
      // Comparaison à l'indice : repliée, elle ne se charge qu'à la demande
      // (les séries historiques coûtent plus de quota que les cours du jour).
      kind === 'crypto' || !positions.lignes.length ? null
        : App.h('details', { class: 'note', style: 'margin-top:18px' },
          App.h('summary', {}, 'Comparer à un indice de référence'),
          App.h('p', {},
            'Nécessite un indice par ligne, défini dans les détails de '
            + 'l’instrument. Les séries historiques ne sont jamais chargées '
            + 'automatiquement.'),
          App.h('div', { class: 'actions', style: 'margin:10px 0' },
            App.h('button', {
              class: 'btn', onclick: (e) => loadBenchmark(e.target),
            }, 'Charger la comparaison')),
          benchHost),
    ].filter(Boolean));
  },

  /* --- recherche d'instrument chez le fournisseur --- */
  openInstrumentSearch(asset, host) {
    const kind = asset.type === 'Crypto' ? 'crypto' : 'titre';
    const input = App.input('q', {
      placeholder: kind === 'crypto'
        ? 'bitcoin, ethereum, solana…'
        : 'MSCI World, CW8, IE00B4L5Y983…',
    });
    const results = App.h('div', { class: 'search-results' });
    let timer = null;

    const run = async () => {
      const q = input.value.trim();
      if (q.length < 2) { App.clear(results); return; }
      App.clear(results);
      results.append(App.h('p', { class: 'hint' }, 'Recherche…'));
      try {
        const res = await App.api.get(
          `/api/market/search?type=${kind}&q=${encodeURIComponent(q)}`);
        App.clear(results);
        if (!res.resultats.length) {
          results.append(App.h('p', { class: 'hint' },
            'Aucun résultat. Essayez le nom complet, le ticker, ou l’ISIN.'));
          return;
        }
        for (const item of res.resultats) {
          results.append(App.h('button', {
            class: 'search-item',
            onclick: () => {
              App.tabs.wealth.openPositionForm(asset, host, item);
            },
          },
          App.h('div', {},
            App.h('div', {}, item.label || item.ticker),
            App.h('div', { class: 'a-meta' },
              [item.code, item.exchange, item.pays, item.currency,
                item.rang ? `#${item.rang}` : null].filter(Boolean).join(' · '))),
          App.h('span', { class: 'pill accent' }, 'Choisir')));
        }
      } catch (e) {
        App.clear(results);
        results.append(App.h('p', { class: 'callout' }, e.message));
      }
    };
    input.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(run, 350);
    });

    App.modal.open({
      title: kind === 'crypto' ? 'Choisir une crypto' : 'Choisir un support',
      body: App.h('div', {},
        App.h('p', { class: 'hint' }, kind === 'crypto'
          ? 'Recherche dans le catalogue CoinGecko — gratuit, sans clé.'
          : 'Recherche chez Twelve Data. Le symbole retenu est celui qui servira '
            + 'ensuite à coter la ligne : rien n’est recopié de mémoire.'),
        App.h('div', { class: 'field', style: 'margin-top:12px' },
          App.h('label', {}, 'Rechercher'), input),
        results),
      footer: [App.h('button', {
        class: 'btn', onclick: () => App.modal.close(),
      }, 'Fermer')],
    });
    setTimeout(() => input.focus(), 50);
  },

  /* --- saisie de la quantité pour l'instrument choisi ---
     Quand l'instrument vient de la recherche, tout est déjà connu : on ne
     demande que combien et à quel prix. Les champs techniques (place, devise,
     indice) se replient — ils ne servent qu'à la saisie manuelle. */
  openPositionForm(asset, host, instrument) {
    const kind = asset.type === 'Crypto' ? 'crypto' : 'titre';
    const item = instrument || {};
    const choisi = !!item.ticker;

    const principal = App.h('div', { class: 'form-grid' },
      App.field('Quantité', App.input('quantite', {
        type: 'number', step: '0.00000001', required: true,
      })),
      App.field('Prix unitaire (€)', App.input('prix_unitaire', {
        type: 'number', step: '0.0001',
      }), { hint: 'Sert au PRU et au TRI' }),
      App.field('Date', App.input('date', { type: 'date', value: App.todayISO() })));

    const avance = App.h('div', { class: 'form-grid' },
      App.field('Instrument', App.input('ticker', {
        value: item.ticker || '',
        placeholder: kind === 'crypto' ? 'bitcoin' : 'CW8 ou ISIN',
      })),
      App.field('Nom affiché', App.input('label', { value: item.label || '' })),
      kind === 'crypto' ? null : App.field('Place', App.input('exchange', {
        value: item.exchange || '', placeholder: 'Euronext',
      })),
      kind === 'crypto' ? null : App.field('Devise', App.input('currency', {
        value: item.currency || 'EUR',
      })),
      App.field('Montant investi (€)', App.input('montant', {
        type: 'number', step: '0.01', placeholder: 'quantité × prix',
      })),
      kind === 'crypto' ? null : App.field('Indice de référence',
        App.input('benchmark_symbol', { value: item.benchmark_symbol || '' })));

    const form = App.h('form', { onsubmit: (e) => e.preventDefault() },
      principal,
      choisi
        ? App.h('details', { class: 'note' },
          App.h('summary', {}, 'Détails de l’instrument'), avance)
        : avance);

    const save = async () => {
      const v = App.formValues(form);
      const ticker = (v.ticker || item.ticker || '').trim();
      if (!ticker) return App.toast('Instrument requis', 'error');
      if (!v.quantite) return App.toast('Quantité requise', 'error');
      try {
        await App.api.post(`/api/assets/${asset.id}/positions`, {
          ...v,
          ticker,
          symbol: item.symbol || ticker,
          currency: v.currency || item.currency || 'EUR',
        });
        App.modal.close();
        App.toast('Position ajoutée', 'success');
        await App.tabs.wealth.renderPositions(host, asset);
        await App.refreshOthers();
      } catch (e) { App.toast(e.message, 'error'); }
    };

    App.modal.open({
      title: item.label ? `${item.label} — combien ?` : 'Ajouter une position',
      body: App.h('div', {},
        choisi ? App.h('p', { class: 'hint', style: 'margin-bottom:14px' },
          [item.code, item.exchange, item.currency].filter(Boolean).join(' · ')) : null,
        form),
      footer: [
        App.h('button', {
          class: 'btn',
          onclick: () => (choisi
            ? App.tabs.wealth.openInstrumentSearch(asset, host)
            : App.modal.close()),
        }, choisi ? 'Retour' : 'Annuler'),
        App.h('button', { class: 'btn primary', onclick: save }, 'Ajouter'),
      ],
    });
  },

  /* ==================================================================
     Un seul point d'entrée pour tout ajouter.

     Il y avait trois boutons — « + Prêt », « + Actif détaillé »,
     « + Ajouter mes produits » — dont deux faisaient la même chose à des
     moments différents. On choisit d'abord QUOI ajouter, la saisie suit.
     ================================================================== */
  openAddChooser() {
    const carte = (type, libelle, sousTitre, action) => App.h('button', {
      class: 'choice', onclick: action,
    },
    App.h('div', {},
      App.h('div', { class: 'choice-title' }, libelle),
      sousTitre ? App.h('div', { class: 'choice-sub' }, sousTitre) : null),
    App.h('span', { class: 'choice-go' }, '→'));

    const body = App.h('div', {});
    for (const [groupe, produits] of App.tabs.wealth.CATALOGUE) {
      body.append(App.h('div', { class: 'section-title' }, groupe));
      const grid = App.h('div', { class: 'choice-grid' });
      for (const [type, libelle, avecTaux] of produits) {
        grid.append(carte(type, libelle,
          App.tabs.wealth.SOUS_TITRES[type] || null,
          () => App.tabs.wealth.openSimpleAssetForm(type, libelle, avecTaux)));
      }
      body.append(grid);
    }

    body.append(
      App.h('div', { class: 'section-title' }, 'Emprunts'),
      App.h('div', { class: 'choice-grid' },
        carte('pret', 'Prêt ou crédit',
          'Mensualité et capital restant dû calculés',
          () => App.tabs.wealth.openLiabilityForm(null))),
      App.h('div', { class: 'section-title' }, 'Autre'),
      App.h('div', { class: 'choice-grid' },
        carte('bulk', 'Déclarer plusieurs produits d’un coup',
          'Pour la première mise en route',
          () => App.tabs.wealth.openQuickAdd()),
        carte('custom', 'Actif d’un autre genre',
          'Formulaire complet, tous les champs',
          () => App.tabs.wealth.openAssetForm(null))));

    App.modal.open({
      title: 'Qu’est-ce que vous voulez ajouter ?',
      wide: true,
      body,
      footer: [App.h('button', {
        class: 'btn', onclick: () => App.modal.close(),
      }, 'Annuler')],
    });
  },

  SOUS_TITRES: {
    Livret: 'Intérêts calculés au taux que vous indiquez',
    LDDS: 'Intérêts calculés au taux que vous indiquez',
    LEP: 'Intérêts calculés au taux que vous indiquez',
    LivretJeune: 'Intérêts calculés au taux que vous indiquez',
    PEL: 'Intérêts calculés au taux que vous indiquez',
    CEL: 'Intérêts calculés au taux que vous indiquez',
    DepotTerme: 'Intérêts calculés au taux que vous indiquez',
    PEA: 'Vous choisirez vos supports ensuite',
    CTO: 'Vous choisirez vos supports ensuite',
    AssuranceVie: 'Vous choisirez vos supports ensuite',
    PER: 'Vous choisirez vos supports ensuite',
    Crypto: 'Vous choisirez vos cryptos ensuite',
    Immobilier: 'Réévaluation possible par indice',
    SCPI: 'Réévaluation possible par indice',
  },

  /* Formulaire court : le type est déjà choisi, on ne demande que
     l'indispensable. Le reste se règle ensuite dans la fiche. */
  openSimpleAssetForm(type, libelle, avecTaux) {
    const marche = App.tabs.wealth.MARKET.includes(type);
    const form = App.h('form', { class: 'form-grid', onsubmit: (e) => e.preventDefault() },
      App.field('Nom', App.input('label', { value: libelle, required: true })),
      App.field('Montant aujourd’hui (€)', App.input('valeur_actuelle', {
        type: 'number', step: '0.01', required: true,
      })),
      App.field('Depuis le', App.input('date_acquisition', {
        type: 'date', value: App.todayISO(),
      })),
      avecTaux ? App.field('Taux annuel (%)', App.input('taux_annuel', {
        type: 'number', step: '0.01',
      }), { hint: 'Laissé vide, le montant reste figé' }) : null);

    const save = async () => {
      const v = App.formValues(form);
      if (!v.valeur_actuelle) return App.toast('Indiquez un montant', 'error');
      const metadata = {};
      if (v.taux_annuel) metadata.taux_annuel = parseFloat(v.taux_annuel);
      try {
        const asset = await App.api.post('/api/assets', {
          type,
          label: v.label.trim() || libelle,
          date_acquisition: v.date_acquisition,
          valeur_acquisition: v.valeur_actuelle,   // pas d'historique connu
          valeur_actuelle: v.valeur_actuelle,
          metadata,
        });
        App.modal.close();
        App.toast(`${v.label || libelle} ajouté`, 'success');
        await App.refreshAll();
        // Un compte-titres ou un portefeuille crypto n'a d'intérêt qu'une fois
        // ses lignes renseignées : on y emmène directement.
        if (marche) await App.tabs.wealth.openAssetDetail(asset.id);
      } catch (e) { App.toast(e.message, 'error'); }
    };

    App.modal.open({
      title: `Ajouter — ${libelle}`,
      body: App.h('div', {}, form,
        marche ? App.h('p', { class: 'hint', style: 'margin-top:14px' },
          'Vous pourrez choisir vos supports juste après, par une recherche.') : null),
      footer: [
        App.h('button', {
          class: 'btn', onclick: () => App.tabs.wealth.openAddChooser(),
        }, 'Retour'),
        App.h('button', { class: 'btn primary', onclick: save }, 'Ajouter'),
      ],
    });
  },

  /* ---------- saisie rapide du patrimoine existant ---------- */

  /* Catalogue des produits courants. Aucun taux n'est pré-rempli : les taux
     réglementés changent, et un taux faux produirait des intérêts faux en
     silence. Le champ est laissé vide, à vous de le renseigner. */
  CATALOGUE: [
    ['Épargne réglementée', [
      ['Livret', 'Livret A', true],
      ['LDDS', 'LDDS', true],
      ['LEP', 'LEP', true],
      ['LivretJeune', 'Livret Jeune', true],
      ['PEL', 'PEL', true],
      ['CEL', 'CEL', true],
      ['DepotTerme', 'Dépôt à terme', true],
    ]],
    ['Placements', [
      ['AssuranceVie', 'Assurance vie', false],
      ['PEA', 'PEA', false],
      ['PER', 'PER', false],
      ['CTO', 'Compte-titres ordinaire', false],
      ['SCPI', 'SCPI', false],
    ]],
    ['Comptes et autres', [
      ['CompteCourant', 'Compte courant', false],
      ['Crypto', 'Crypto', false],
      ['Immobilier', 'Bien immobilier', false],
      ['Vehicule', 'Véhicule', false],
    ]],
  ],

  openQuickAdd() {
    const lignes = [];
    const dateIn = App.input('date', { type: 'date', value: App.todayISO() });
    const totalNode = App.h('strong', {}, App.fmt.eur(0));

    const updateTotal = () => {
      const total = lignes.reduce(
        (sum, l) => sum + (parseFloat(l.montant.value) || 0), 0);
      totalNode.textContent = App.fmt.eur(total);
      const n = lignes.filter((l) => parseFloat(l.montant.value) > 0).length;
      submit.textContent = n
        ? `Ajouter ${n} produit${n > 1 ? 's' : ''}` : 'Ajouter';
      submit.disabled = n === 0;
    };

    const body = App.h('div', {});
    for (const [groupe, produits] of App.tabs.wealth.CATALOGUE) {
      body.append(App.h('div', { class: 'section-title' }, groupe));
      const grid = App.h('div', { class: 'quick-grid' });
      for (const [type, libelle, avecTaux] of produits) {
        const label = App.input('l', { value: libelle });
        const montant = App.input('m', {
          type: 'number', step: '0.01', placeholder: '0,00',
        });
        const taux = avecTaux
          ? App.input('t', { type: 'number', step: '0.01', placeholder: 'taux %' })
          : null;
        montant.addEventListener('input', updateTotal);
        grid.append(App.h('div', { class: 'quick-row' },
          App.h('div', { class: 'quick-label' }, label),
          App.h('div', { class: 'quick-amount' }, montant),
          App.h('div', { class: 'quick-rate' },
            taux || App.h('span', { class: 'sub' }, '—'))));
        lignes.push({ type, label, montant, taux });
      }
      body.append(grid);
    }

    const submit = App.h('button', { class: 'btn primary', disabled: true }, 'Ajouter');
    submit.addEventListener('click', async () => {
      const actifs = lignes
        .filter((l) => parseFloat(l.montant.value) > 0)
        .map((l) => ({
          type: l.type,
          label: l.label.value.trim() || l.type,
          montant: parseFloat(l.montant.value),
          taux_annuel: l.taux && l.taux.value !== '' ? parseFloat(l.taux.value) : null,
        }));
      try {
        const res = await App.api.post('/api/assets/batch',
          { date: dateIn.value, actifs });
        App.modal.close();
        App.toast(`${res.crees} produit(s) ajouté(s) — ${App.fmt.eur(res.total)}`,
          'success');
        await App.refreshAll();
      } catch (e) { App.toast(e.message, 'error'); }
    });

    App.modal.open({
      title: 'Ajouter mon patrimoine existant',
      wide: true,
      body: App.h('div', {},
        App.h('p', { class: 'hint' },
          'Indiquez simplement ce que vous avez aujourd’hui sur chaque produit. '
          + 'Laissez vide ceux que vous n’avez pas. Vous pourrez tout affiner ensuite, '
          + 'produit par produit.'),
        App.note('Plus-value à zéro, taux à renseigner — pourquoi',
          App.h('p', {},
            'La valeur d’acquisition est posée égale au montant déclaré : la '
            + 'plus-value démarre donc à zéro. C’est le seul affichage honnête tant '
            + 'que vos versements passés ne sont pas saisis — sinon l’application '
            + 'inventerait une performance.'),
          App.h('p', {},
            'Le taux, lui, sert à calculer les intérêts à venir. Laissé vide, le '
            + 'montant reste figé jusqu’à votre prochaine mise à jour.')),
        App.h('div', { class: 'form-grid', style: 'margin-top:14px' },
          App.field('Montants arrêtés au', dateIn)),
        body),
      footer: [
        App.h('div', { style: 'margin-right:auto' },
          App.h('span', { class: 'sub' }, 'Total déclaré : '), totalNode),
        App.h('button', { class: 'btn', onclick: () => App.modal.close() }, 'Annuler'),
        submit,
      ],
    });
    updateTotal();
  },

  /* ---------- formulaire actif ---------- */
  openAssetForm(asset) {
    const isEdit = !!asset;
    const types = (App.state.meta.asset_types || []).map((t) => [t.type, `${t.type} — ${t.famille}`]);
    const typeSelect = App.select('type', types, asset ? asset.type : 'PEA');
    const metaHost = App.h('div', { class: 'form-grid' });

    const renderMeta = () => {
      App.clear(metaHost);
      const meta = (asset && asset.metadata) || {};
      const t = typeSelect.value;
      const add = (label, name, attrs) => metaHost.append(
        App.field(label, App.input(`meta_${name}`, Object.assign({ value: meta[name] ?? '' }, attrs))));
      if (App.tabs.wealth.PROPERTY.includes(t)) {
        add('Adresse', 'adresse');
        add('Surface (m²)', 'surface_m2', { type: 'number', step: '0.1' });
        const loue = App.h('input', { type: 'checkbox', name: 'meta_loue' });
        loue.checked = !!meta.loue;
        metaHost.append(App.field('Bien loué', loue));
      }
      if (t === 'Vehicule') {
        add('Immatriculation', 'immatriculation');
        add('Année', 'annee', { type: 'number' });
      }
      if (App.tabs.wealth.PROPERTY.includes(t) && t !== 'Vehicule') {
        add('Indice INSEE (idbank)', 'indice_insee',
          { placeholder: 'ex : 010567037' });
        add('Ou taux de revalorisation annuel (%)', 'taux_revalorisation_annuel',
          { type: 'number', step: '0.01' });
        metaHost.append(App.h('p', { class: 'hint', style: 'grid-column:1/-1' },
          'Aucune API ne cote un bien précis. La valeur est estimée en appliquant '
          + 'l’évolution d’un indice à votre prix d’acquisition — c’est un ordre de '
          + 'grandeur, pas une expertise. À défaut d’indice, le taux annuel est utilisé.'));
      }
      if (App.tabs.wealth.MARKET.includes(t) && t !== 'Crypto') {
        add('Courtier', 'courtier');
        add('Numéro de compte', 'numero_compte');
      }
      if (t === 'Crypto') {
        add('Identifiant CoinGecko', 'coingecko_id', { placeholder: 'ex : bitcoin' });
        add('Quantité détenue', 'quantite', { type: 'number', step: '0.00000001' });
        metaHost.append(App.h('p', { class: 'hint', style: 'grid-column:1/-1' },
          'L’identifiant CoinGecko est celui de l’URL de la page du coin '
          + '(coingecko.com/fr/pieces/bitcoin → « bitcoin »). '
          + 'La quantité est nécessaire pour valoriser au cours du jour.'));
      }
      if (App.tabs.wealth.RATE.includes(t)) {
        add('Taux annuel (%)', 'taux_annuel', { type: 'number', step: '0.01' });
        metaHost.append(App.h('p', { class: 'hint', style: 'grid-column:1/-1' },
          'Les livrets ne se cotent pas : leurs intérêts sont calculés par quinzaines '
          + '(un versement porte intérêt au 1er ou au 16 suivant) et capitalisés '
          + 'au 31 décembre. Aucun appel réseau.'));
      }
      if (t === 'Custom') {
        metaHost.append(App.h('p', { class: 'hint' },
          'Type libre : aucun champ imposé au-delà du libellé, de la date et de la valeur.'));
      }
    };
    typeSelect.addEventListener('change', renderMeta);

    const form = App.h('form', { onsubmit: (e) => e.preventDefault() },
      App.h('div', { class: 'form-grid' },
        App.field('Type', typeSelect),
        App.field('Libellé', App.input('label', { value: (asset && asset.label) || '', required: true })),
        App.field('Valeur aujourd’hui (€)', App.input('valeur_actuelle', {
          type: 'number', step: '0.01', value: (asset && asset.valeur_actuelle) ?? '',
        }), { hint: 'Le montant que vous avez dessus maintenant' }),
        App.field('Depuis le', App.input('date_acquisition', {
          type: 'date', value: (asset && asset.date_acquisition) || App.todayISO(),
        }), { hint: 'Ouverture, achat, ou simplement aujourd’hui' }),
        App.field('Montant investi (€)', App.input('valeur_acquisition', {
          type: 'number', step: '0.01',
          value: asset ? asset.valeur_acquisition : '',
          placeholder: 'idem valeur actuelle',
        }), {
          hint: 'Laissez vide si vous ne connaissez pas l’historique : '
            + 'la plus-value démarrera à zéro plutôt qu’inventée',
        })),
      App.h('div', { class: 'section-title' }, 'Champs spécifiques au type'),
      metaHost);
    renderMeta();

    const save = async () => {
      const v = App.formValues(form);
      const metadata = {};
      for (const [k, val] of Object.entries(v)) {
        if (!k.startsWith('meta_')) continue;
        if (val === '' || val === false) continue;
        metadata[k.slice(5)] = val;
      }
      // Montant investi non renseigné : on le pose égal à la valeur actuelle,
      // pour ne pas afficher une plus-value fabriquée à partir d'un zéro.
      const investi = v.valeur_acquisition === ''
        ? (v.valeur_actuelle === '' ? 0 : v.valeur_actuelle)
        : v.valeur_acquisition;
      const payload = {
        type: v.type,
        label: v.label,
        date_acquisition: v.date_acquisition,
        valeur_acquisition: investi,
        valeur_actuelle: v.valeur_actuelle === '' ? null : v.valeur_actuelle,
        metadata,
      };
      if (!payload.label) return App.toast('Le libellé est obligatoire', 'error');
      try {
        if (isEdit) await App.api.put(`/api/assets/${asset.id}`, payload);
        else await App.api.post('/api/assets', payload);
        App.modal.close();
        App.toast(isEdit ? 'Actif modifié' : 'Actif créé', 'success');
        await App.refreshAll();
      } catch (e) { App.toast(e.message, 'error'); }
    };

    App.modal.open({
      title: isEdit ? 'Modifier l’actif' : 'Nouvel actif',
      body: form,
      footer: [
        isEdit ? App.h('button', {
          class: 'btn danger',
          onclick: () => App.confirm(
            `Supprimer « ${asset.label} » ? Ses mouvements seront supprimés aussi.`,
            async () => {
              await App.api.del(`/api/assets/${asset.id}`);
              App.toast('Actif supprimé', 'success');
              await App.refreshAll();
            }),
        }, 'Supprimer') : null,
        App.h('button', { class: 'btn', onclick: () => App.modal.close() }, 'Annuler'),
        App.h('button', { class: 'btn primary', onclick: save }, 'Enregistrer'),
      ].filter(Boolean),
    });
  },

  /* ---------- détail actif ---------- */
  async openAssetDetail(assetId) {
    let data;
    try { data = await App.api.get(`/api/assets/${assetId}`); }
    catch (e) { return App.toast(e.message, 'error'); }
    const a = data.asset;

    // Trois onglets au maximum. « Résumé » et « PRU & TRI » faisaient doublon
    // avec les positions : leurs chiffres sont désormais en tête de celles-ci.
    const aPositions = App.tabs.wealth.MARKET.includes(a.type);
    const panels = [];
    if (aPositions) {
      panels.push([
        'positions',
        a.type === 'Crypto' ? 'Mes cryptos' : 'Mes supports',
        await App.tabs.wealth.panelPositions(a, data),
      ]);
    } else {
      panels.push(['resume', 'Détail', App.tabs.wealth.panelSummary(data)]);
    }
    if (data.immobilier) panels.push(['immo', 'Prêt & rendement', App.tabs.wealth.panelProperty(data)]);
    panels.push(['mouvements', 'Historique', App.tabs.wealth.panelMovements(data)]);

    const nav = App.h('div', { class: 'tabs-inline' });
    const stack = App.h('div', {});
    panels.forEach(([key, label, node], i) => {
      const btn = App.h('button', { class: i === 0 ? 'active' : '' }, label);
      const panel = App.h('div', { class: `subpanel${i === 0 ? ' active' : ''}` }, node);
      btn.addEventListener('click', () => {
        App.els('button', nav).forEach((b) => b.classList.remove('active'));
        App.els('.subpanel', stack).forEach((p) => p.classList.remove('active'));
        btn.classList.add('active');
        panel.classList.add('active');
      });
      nav.append(btn);
      stack.append(panel);
    });

    App.modal.open({
      title: `${a.label} — ${a.type}`,
      body: App.h('div', {}, nav, stack),
      wide: true,
      footer: [
        App.h('button', { class: 'btn', onclick: () => App.tabs.wealth.openAssetForm(a) }, 'Modifier'),
        App.h('button', { class: 'btn', onclick: () => App.tabs.wealth.openRevalue(a) }, 'Valoriser'),
        App.h('button', { class: 'btn primary', onclick: () => App.modal.close() }, 'Fermer'),
      ],
    });
  },

  panelSummary(data) {
    const a = data.asset;
    const rows = [
      ['Valeur actuelle', App.fmt.eur(a.valeur)],
      ['Capital investi', App.fmt.eur(a.investi)],
      ['Plus-value latente', `${App.fmt.signed(a.plus_value)}${a.plus_value_pct !== null ? ` (${App.fmt.ratio(a.plus_value_pct)})` : ''}`],
      ["Date d'acquisition", App.fmt.date(a.date_acquisition)],
      ["Valeur d'acquisition", App.fmt.eur(a.valeur_acquisition)],
      ['Valeur saisie manuellement', a.valeur_actuelle === null ? 'non (reconstituée)' : App.fmt.eur(a.valeur_actuelle)],
      ['Mouvements enregistrés', String(a.nb_mouvements)],
    ];
    const list = App.h('div', { class: 'metric-list' });
    for (const [l, v] of rows) {
      list.append(App.h('div', { class: 'metric-row' },
        App.h('span', { class: 'm-label' }, l), App.h('span', { class: 'm-value' }, v)));
    }
    const metaEntries = Object.entries(a.metadata || {});
    return App.h('div', {}, list,
      metaEntries.length ? App.h('div', { class: 'section-title' }, 'Champs spécifiques') : null,
      metaEntries.length ? App.h('div', { class: 'metric-list' },
        ...metaEntries.map(([k, v]) => App.h('div', { class: 'metric-row' },
          App.h('span', { class: 'm-label' }, k),
          App.h('span', { class: 'm-value' }, String(v))))) : null,
      data.transactions.length ? App.h('div', { class: 'section-title' }, 'Transactions rattachées') : null,
      data.transactions.length ? App.tabs.wealth.txTable(data.transactions) : null);
  },

  txTable(txs) {
    const tbody = App.h('tbody', {});
    for (const t of txs.slice(0, 60)) {
      tbody.append(App.h('tr', {},
        App.h('td', { class: 'nowrap' }, App.fmt.date(t.date)),
        App.h('td', {}, App.h('div', { class: 'ell' }, t.description)),
        App.h('td', {}, t.category),
        App.h('td', { class: `right num ${t.amount < 0 ? 'neg' : 'pos'}` }, App.fmt.eur(t.amount))));
    }
    return App.h('div', { class: 'table-wrap scroll-y' },
      App.h('table', { class: 'table' },
        App.h('thead', {}, App.h('tr', {},
          App.h('th', {}, 'Date'), App.h('th', {}, 'Libellé'),
          App.h('th', {}, 'Catégorie'), App.h('th', { class: 'right' }, 'Montant'))),
        tbody));
  },

  panelMovements(data) {
    const a = data.asset;
    const tbody = App.h('tbody', {});
    const rebuild = () => {
      App.clear(tbody);
      if (!data.movements.length) {
        tbody.append(App.h('tr', {}, App.h('td', { colspan: 7, class: 'empty' }, 'Aucun mouvement.')));
      }
      for (const m of data.movements) {
        tbody.append(App.h('tr', {},
          App.h('td', { class: 'nowrap' }, App.fmt.date(m.date)),
          App.h('td', {}, App.h('span', { class: `pill ${m.type === 'valorisation' ? '' : 'accent'}` }, m.type)),
          App.h('td', {}, m.ticker || '—'),
          App.h('td', { class: 'right num' }, m.quantite === null ? '—' : App.fmt.num(m.quantite, 6)),
          App.h('td', { class: 'right num' }, m.prix_unitaire === null ? '—' : App.fmt.eur(m.prix_unitaire)),
          App.h('td', { class: `right num ${m.montant < 0 ? 'neg' : ''}` }, App.fmt.eur(m.montant)),
          App.h('td', { class: 'right' }, App.h('button', {
            class: 'icon-btn',
            onclick: () => App.confirm('Supprimer ce mouvement ?', async () => {
              await App.api.del(`/api/movements/${m.id}`);
              App.toast('Mouvement supprimé', 'success');
              App.modal.close();
              await App.refreshAll();
            }),
          }, '×'))));
      }
    };
    rebuild();

    const isMarket = App.tabs.wealth.MARKET.includes(a.type);
    const form = App.h('form', { class: 'form-grid', onsubmit: (e) => e.preventDefault() },
      App.field('Date', App.input('date', { type: 'date', value: App.todayISO() })),
      App.field('Type', App.select('type', [['versement', 'Versement / achat'], ['retrait', 'Retrait / vente'], ['valorisation', 'Valorisation']], 'versement')),
      App.field('Montant (€)', App.input('montant', { type: 'number', step: '0.01' })),
      isMarket ? App.field('Ticker / ISIN', App.input('ticker')) : null,
      isMarket ? App.field('Quantité', App.input('quantite', { type: 'number', step: '0.000001' })) : null,
      isMarket ? App.field('Prix unitaire (€)', App.input('prix_unitaire', { type: 'number', step: '0.0001' })) : null,
      App.field('Note', App.input('note'), { full: true }));

    const add = async () => {
      const v = App.formValues(form);
      if (!v.montant && v.quantite && v.prix_unitaire) {
        v.montant = String(parseFloat(v.quantite) * parseFloat(v.prix_unitaire));
      }
      if (!v.montant) return App.toast('Montant requis', 'error');
      try {
        await App.api.post(`/api/assets/${a.id}/movements`, v);
        App.toast('Mouvement ajouté', 'success');
        App.modal.close();
        await App.refreshAll();
      } catch (e) { App.toast(e.message, 'error'); }
    };

    return App.h('div', {},
      App.h('div', { class: 'table-wrap scroll-y' },
        App.h('table', { class: 'table' },
          App.h('thead', {}, App.h('tr', {},
            App.h('th', {}, 'Date'), App.h('th', {}, 'Type'), App.h('th', {}, 'Ticker'),
            App.h('th', { class: 'right' }, 'Quantité'),
            App.h('th', { class: 'right' }, 'Prix unit.'),
            App.h('th', { class: 'right' }, 'Montant'), App.h('th', {}))),
          tbody)),
      App.h('div', { class: 'section-title' }, 'Ajouter un mouvement'),
      form,
      App.h('div', { class: 'actions', style: 'margin-top:12px' },
        App.h('button', { class: 'btn primary', onclick: add }, 'Ajouter'),
        isMarket ? App.h('button', {
          class: 'btn', onclick: () => App.tabs.wealth.openMovementImport(a),
        }, 'Importer un relevé de titres') : null));
  },

  renderBenchmark(host, res) {
    App.clear(host);
    if (!res.lignes.length) {
      host.append(App.h('p', { class: 'hint' },
        'Aucune ligne ne porte d’indice de référence.'));
      return;
    }
    for (const ligne of res.lignes) {
      if (ligne.erreur) {
        host.append(App.h('p', { class: 'hint' },
          `${ligne.ticker} : ${ligne.erreur}`));
        continue;
      }
      const canvasId = `bench-${ligne.ticker.replace(/[^a-zA-Z0-9]/g, '')}`;
      const rows = [
        ['Performance de la ligne', App.fmt.pct(ligne.perf_ligne, 2)],
        [`Performance de ${ligne.indice_label}`, App.fmt.pct(ligne.perf_indice, 2)],
        ['Écart', `${ligne.ecart > 0 ? '+' : ''}${App.fmt.pct(ligne.ecart, 2)}`],
      ];
      const list = App.h('div', { class: 'metric-list' });
      for (const [l, v] of rows) {
        list.append(App.h('div', { class: 'metric-row' },
          App.h('span', { class: 'm-label' }, l), App.h('span', { class: 'm-value' }, v)));
      }
      host.append(
        App.h('div', { class: 'section-title' }, `${ligne.symbole} vs ${ligne.indice_label}`),
        list,
        App.h('div', { class: 'chart-wrap' }, App.h('canvas', { id: canvasId })));
      // Le canvas doit être dans le DOM avant que Chart.js ne s'y accroche.
      setTimeout(() => App.chart(canvasId, {
        type: 'line',
        data: {
          labels: ligne.serie_ligne.map((p) => p.date),
          datasets: [
            {
              label: ligne.symbole, data: ligne.serie_ligne.map((p) => p.valeur),
              borderColor: App.chartColors[0], borderWidth: 2,
              pointRadius: 0, tension: .25, fill: false,
            },
            {
              label: ligne.indice_label, data: ligne.serie_indice.map((p) => p.valeur),
              borderColor: App.chartColors[3], borderWidth: 1.5, borderDash: [5, 4],
              pointRadius: 0, tension: .25, fill: false,
            },
          ],
        },
        options: {
          interaction: { mode: 'index', intersect: false },
          scales: { x: { ticks: { maxTicksLimit: 8 } }, y: { title: { display: true, text: 'base 100' } } },
        },
      }), 0);
    }
  },

  panelProperty(data) {
    const p = data.immobilier;
    const rows = [
      ['Valeur du bien', App.fmt.eur(p.valeur)],
      ['Capital restant dû', App.fmt.eur(p.capital_restant)],
      ['Valeur nette (bien − dette)', App.fmt.eur(p.valeur_nette)],
      ['Loyers perçus (12 mois)', App.fmt.eur(p.loyers_12m)],
      ['Charges (12 mois)', App.fmt.eur(p.charges_12m)],
      ['Mensualités de prêt (12 mois)', App.fmt.eur(p.mensualites_12m)],
      ['dont intérêts et assurance', App.fmt.eur(p.interets_12m)],
      ['Cash-flow (12 mois)', App.fmt.signed(p.cashflow_12m)],
      ['Rendement brut', p.rendement_brut_pct === null ? '—' : App.fmt.pct(p.rendement_brut_pct, 2)],
      ['Rendement net hors capital',
        p.rendement_hors_capital_pct === null ? '—' : App.fmt.pct(p.rendement_hors_capital_pct, 2)],
      ['Rendement après mensualités',
        p.rendement_net_pct === null ? '—' : App.fmt.pct(p.rendement_net_pct, 2)],
    ];
    const list = App.h('div', { class: 'metric-list' });
    for (const [l, v] of rows) {
      list.append(App.h('div', { class: 'metric-row' },
        App.h('span', { class: 'm-label' }, l), App.h('span', { class: 'm-value' }, v)));
    }
    const out = App.h('div', {}, list,
      App.note('Pourquoi deux rendements',
        App.h('p', {},
          'Le remboursement du capital n’est pas une charge : il éteint une '
          + 'dette et vous revient. Le soustraire fait paraître le bien moins '
          + 'rentable qu’il ne l’est.'),
        App.h('p', {},
          'Le rendement hors capital ne retient que les intérêts et '
          + 'l’assurance : c’est la performance du bien. Le rendement après '
          + 'mensualités, lui, dit ce qui sort réellement de votre poche.')));
    for (const loan of p.prets) {
      out.append(App.h('div', { class: 'section-title' }, `Prêt : ${loan.label || loan.type}`));
      out.append(App.tabs.wealth.loanBlock(loan));
    }
    if (!p.prets.length) {
      out.append(App.h('p', { class: 'hint', style: 'margin-top:12px' },
        'Aucun prêt rattaché à ce bien. Créez-le depuis « + Prêt » et sélectionnez ce bien.'));
    }
    return out;
  },

  loanBlock(loan) {
    const rows = [
      ['Mensualité (hors assurance)', App.fmt.eur(loan.mensualite)],
      ['Mensualité totale prélevée', App.fmt.eur(loan.mensualite_avec_assurance)],
      ['Capital restant dû', App.fmt.eur(loan.capital_restant)],
      ['Échéances payées', `${loan.echeances_payees} / ${loan.echeances_totales}`],
      ['Fin du prêt', App.fmt.date(loan.date_fin)],
      ['Intérêts déjà payés', App.fmt.eur(loan.interets_payes)],
      ['Intérêts totaux', App.fmt.eur(loan.interets_totaux)],
      ['Coût total du crédit', App.fmt.eur(loan.cout_total)],
    ];
    const list = App.h('div', { class: 'metric-list' });
    for (const [l, v] of rows) {
      list.append(App.h('div', { class: 'metric-row' },
        App.h('span', { class: 'm-label' }, l), App.h('span', { class: 'm-value' }, v)));
    }
    const tbody = App.h('tbody', {});
    for (const e of loan.echeancier || []) {
      tbody.append(App.h('tr', {},
        App.h('td', { class: 'right' }, e.n),
        App.h('td', { class: 'nowrap' }, App.fmt.date(e.date)),
        App.h('td', { class: 'right num' }, App.fmt.eur(e.mensualite)),
        App.h('td', { class: 'right num' }, App.fmt.eur(e.interets)),
        App.h('td', { class: 'right num' }, App.fmt.eur(e.capital)),
        App.h('td', { class: 'right num' }, App.fmt.eur(e.capital_restant))));
    }
    return App.h('div', {}, list,
      App.h('div', { class: 'section-title' }, 'Tableau d’amortissement'),
      App.h('div', { class: 'table-wrap scroll-y' },
        App.h('table', { class: 'table' },
          App.h('thead', {}, App.h('tr', {},
            App.h('th', { class: 'right' }, '#'), App.h('th', {}, 'Échéance'),
            App.h('th', { class: 'right' }, 'Mensualité'),
            App.h('th', { class: 'right' }, 'Intérêts'),
            App.h('th', { class: 'right' }, 'Capital'),
            App.h('th', { class: 'right' }, 'Restant dû'))),
          tbody)));
  },

  /* ---------- valorisation ---------- */
  openRevalue(asset) {
    const form = App.h('form', { class: 'form-grid', onsubmit: (e) => e.preventDefault() },
      App.field('Date de valorisation', App.input('date', { type: 'date', value: App.todayISO() })),
      App.field('Valeur totale (€)', App.input('valeur', {
        type: 'number', step: '0.01', value: asset.valeur_actuelle ?? '',
      })),
      App.field('Note', App.input('note'), { full: true }));

    const save = async () => {
      const v = App.formValues(form);
      if (!v.valeur) return App.toast('Valeur requise', 'error');
      try {
        await App.api.post(`/api/assets/${asset.id}/valorisation`, v);
        App.modal.close();
        App.toast('Valorisation enregistrée', 'success');
        await App.refreshAll();
      } catch (e) { App.toast(e.message, 'error'); }
    };

    App.modal.open({
      title: `Valoriser — ${asset.label}`,
      body: App.h('div', {}, form,
        App.h('p', { class: 'hint', style: 'margin-top:12px' },
          'Une valorisation datée alimente la courbe de patrimoine. '
          + 'Répétez-la régulièrement (mensuellement par exemple) pour obtenir un historique réaliste.')),
      footer: [
        App.h('button', { class: 'btn', onclick: () => App.modal.close() }, 'Annuler'),
        App.h('button', { class: 'btn primary', onclick: save }, 'Enregistrer'),
      ],
    });
  },

  /* ---------- import de mouvements de titres ---------- */
  openMovementImport(asset) {
    const textarea = App.h('textarea', {
      rows: 12,
      placeholder: 'Collez le relevé (date, ticker/ISIN, quantité, prix unitaire, montant)…',
    });
    const analyse = async () => {
      try {
        const res = await App.api.post(`/api/assets/${asset.id}/movements/preview`,
          { text: textarea.value });
        App.tabs.wealth.showMovementPreview(asset, res);
      } catch (e) { App.toast(e.message, 'error'); }
    };
    App.modal.open({
      title: `Importer des mouvements — ${asset.label}`,
      wide: true,
      body: App.h('div', {},
        App.h('p', { class: 'hint' },
          'Objectif : récupérer quantité, prix unitaire et ticker de chaque achat pour '
          + 'calculer le PRU et le TRI réels. Colonnes détectées automatiquement.'),
        App.h('div', { class: 'field full', style: 'margin-top:10px' },
          App.h('label', {}, 'Contenu'), textarea)),
      footer: [
        App.h('button', { class: 'btn', onclick: () => App.modal.close() }, 'Annuler'),
        App.h('button', { class: 'btn primary', onclick: analyse }, 'Analyser'),
      ],
    });
  },

  showMovementPreview(asset, res) {
    const lines = res.lignes;
    const tbody = App.h('tbody', {});
    lines.forEach((line) => {
      const check = App.h('input', { type: 'checkbox' });
      check.checked = !line.ignore;         // les doublons arrivent décochés
      check.addEventListener('change', () => { line.ignore = !check.checked; });
      tbody.append(App.h('tr', {},
        App.h('td', {}, check),
        App.h('td', { class: 'nowrap' }, App.fmt.date(line.date)),
        App.h('td', {}, line.ticker || '—'),
        App.h('td', {}, App.h('span', { class: 'pill accent' }, line.type)),
        App.h('td', { class: 'right num' }, line.quantite === null ? '—' : App.fmt.num(line.quantite, 6)),
        App.h('td', { class: 'right num' }, line.prix_unitaire === null ? '—' : App.fmt.eur(line.prix_unitaire)),
        App.h('td', { class: 'right num' }, line.montant === null ? '—' : App.fmt.eur(line.montant)),
        App.h('td', {}, line.doublon
          ? App.h('span', { class: 'pill warn' }, 'déjà importé') : '')));
    });

    const confirm = async () => {
      try {
        const out = await App.api.post(`/api/assets/${asset.id}/movements/confirm`, { lignes: lines });
        App.modal.close();
        App.toast(`${out.crees} mouvement(s) importé(s), ${out.ignorees} ignoré(s)`,
          'success');
        if (out.symboles_amorces.length) {
          App.toast(`Symbole à vérifier pour : ${out.symboles_amorces.join(', ')}`,
            'error', 7000);
        }
        await App.refreshAll();
      } catch (e) { App.toast(e.message, 'error'); }
    };

    App.modal.open({
      title: `Prévisualisation — ${asset.label}`,
      wide: true,
      body: App.h('div', {},
        App.h('p', { class: 'hint' },
          `${res.total} ligne(s) lue(s), ${res.doublons} déjà présente(s) `
          + '(décochées). Les quantités détenues et le PRU se recalculent tout '
          + 'seuls à partir de ces mouvements.'),
        ...(res.avertissements || []).map((w) => App.h('p', { class: 'hint' }, `⚠ ${w}`)),
        res.tickers_sans_symbole && res.tickers_sans_symbole.length
          ? App.h('p', { class: 'callout', style: 'margin:12px 0' },
            `Sans correspondance de cotation : ${res.tickers_sans_symbole.join(', ')}. `
            + 'Le ticker du relevé sera repris tel quel — vérifiez-le ensuite dans '
            + 'les détails de la ligne, sinon elle restera non cotée.')
          : null,
        App.h('div', { class: 'table-wrap scroll-y' },
          App.h('table', { class: 'table' },
            App.h('thead', {}, App.h('tr', {},
              App.h('th', {}, '✓'), App.h('th', {}, 'Date'), App.h('th', {}, 'Ticker'),
              App.h('th', {}, 'Type'), App.h('th', { class: 'right' }, 'Quantité'),
              App.h('th', { class: 'right' }, 'Prix unit.'),
              App.h('th', { class: 'right' }, 'Montant'),
              App.h('th', {}))),
            tbody))),
      footer: [
        App.h('button', { class: 'btn', onclick: () => App.modal.close() }, 'Annuler'),
        App.h('button', { class: 'btn primary', onclick: confirm }, 'Importer'),
      ],
    });
  },

  /* ---------- prêts ---------- */
  openLiabilityForm(liab) {
    const isEdit = !!liab;
    const assets = [['', '— aucun —'],
      ...((App.state.assets || []).map((a) => [a.id, `${a.label} (${a.type})`]))];
    const form = App.h('form', { class: 'form-grid', onsubmit: (e) => e.preventDefault() },
      App.field('Type', App.select('type', App.state.meta.liability_types, liab ? liab.type : 'PretImmobilier')),
      App.field('Libellé', App.input('label', { value: (liab && liab.label) || '' })),
      App.field('Bien financé', App.select('asset_id', assets, liab ? liab.asset_id : ''),
        { hint: 'Lie le prêt à un actif pour le suivi immobilier' }),
      App.field('Montant emprunté (€)', App.input('montant_emprunte', {
        type: 'number', step: '0.01', value: liab ? liab.montant_emprunte : '', required: true,
      })),
      App.field('Taux annuel (%)', App.input('taux_annuel', {
        type: 'number', step: '0.001', value: liab ? liab.taux_annuel : '',
      })),
      App.field('Durée (mois)', App.input('duree_mois', {
        type: 'number', step: '1', value: liab ? liab.duree_mois : '',
      })),
      App.field('Date de début', App.input('date_debut', {
        type: 'date', value: (liab && liab.date_debut) || App.todayISO(),
      })),
      App.field('Assurance mensuelle (€)', App.input('assurance_mensuelle', {
        type: 'number', step: '0.01', value: liab ? liab.assurance_mensuelle : 0,
      })));

    const preview = App.h('p', { class: 'hint' });
    const updatePreview = () => {
      const v = App.formValues(form);
      const p = parseFloat(v.montant_emprunte);
      const t = parseFloat(v.taux_annuel) || 0;
      const n = parseInt(v.duree_mois, 10);
      if (!p || !n) { preview.textContent = ''; return; }
      const r = t / 12 / 100;
      const m = r === 0 ? p / n : (p * r) / (1 - (1 + r) ** (-n));
      const ins = parseFloat(v.assurance_mensuelle) || 0;
      preview.textContent = `Mensualité calculée : ${App.fmt.eur(m)}`
        + (ins ? ` + ${App.fmt.eur(ins)} d'assurance = ${App.fmt.eur(m + ins)}` : '')
        + ` — coût total ${App.fmt.eur(m * n + ins * n)}`;
    };
    form.addEventListener('input', updatePreview);
    setTimeout(updatePreview, 0);

    const save = async () => {
      const v = App.formValues(form);
      try {
        if (isEdit) await App.api.put(`/api/liabilities/${liab.id}`, v);
        else await App.api.post('/api/liabilities', v);
        App.modal.close();
        App.toast(isEdit ? 'Prêt modifié' : 'Prêt créé', 'success');
        await App.refreshAll();
      } catch (e) { App.toast(e.message, 'error'); }
    };

    App.modal.open({
      title: isEdit ? 'Modifier le prêt' : 'Nouveau prêt',
      body: App.h('div', {}, form,
        App.h('div', { style: 'margin-top:12px' }, preview),
        App.h('p', { class: 'hint' },
          'La mensualité et le capital restant dû ne se saisissent jamais : ils sont recalculés '
          + 'depuis le montant, le taux, la durée et la date de début.')),
      footer: [
        isEdit ? App.h('button', {
          class: 'btn danger',
          onclick: () => App.confirm('Supprimer ce prêt ?', async () => {
            await App.api.del(`/api/liabilities/${liab.id}`);
            App.toast('Prêt supprimé', 'success');
            await App.refreshAll();
          }),
        }, 'Supprimer') : null,
        App.h('button', { class: 'btn', onclick: () => App.modal.close() }, 'Annuler'),
        App.h('button', { class: 'btn primary', onclick: save }, 'Enregistrer'),
      ].filter(Boolean),
    });
  },

  async openLiabilityDetail(lid) {
    let loan;
    try { loan = await App.api.get(`/api/liabilities/${lid}`); }
    catch (e) { return App.toast(e.message, 'error'); }
    const body = App.h('div', {}, App.tabs.wealth.loanBlock(loan));
    if (loan.remboursements.length) {
      body.append(App.h('div', { class: 'section-title' }, 'Remboursements détectés'),
        App.tabs.wealth.txTable(loan.remboursements));
    }
    App.modal.open({
      title: `${loan.label || loan.type}`,
      wide: true,
      body,
      footer: [
        App.h('button', { class: 'btn', onclick: () => App.tabs.wealth.openLiabilityForm(loan) }, 'Modifier'),
        App.h('button', { class: 'btn primary', onclick: () => App.modal.close() }, 'Fermer'),
      ],
    });
  },
};
