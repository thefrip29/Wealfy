/* Onglet « Vue d'ensemble » : snapshot du mois sélectionné. */
App.tabs.overview = {
  async load() {
    const data = await App.api.get(`/api/overview?month=${App.state.month}`);
    // Conservé pour la vue agrandie : elle rejoue les mêmes séries, inutile
    // de les redemander au serveur.
    App.tabs.overview.dernier = data;
    // Un changement de mois ou d'onglet reconstruit le contenu : on repart
    // toujours d'une synthèse repliée, sinon un graphique resterait agrandi
    // avec un détail devenu périmé.
    App.tabs.overview.expanded = null;
    App.els('#tab-overview .card.expanded').forEach((c) => c.classList.remove('expanded'));
    App.els('#tab-overview .card-extra').forEach(App.clear);
    App.tabs.overview.renderHero(data);
    App.tabs.overview.renderAlertes(data.alertes || []);
    App.tabs.overview.renderKpis(data);
    App.tabs.overview.renderNetWorth(data.patrimoine_serie);
    App.tabs.overview.renderCategories(data.mois);
    App.tabs.overview.renderRepartition(data.repartition, data.metrics);
    App.tabs.overview.renderFlows(data.depenses_serie);
  },

  /* Observations factuelles.

     Repliées sur une seule ligne : la synthèse est là pour les chiffres, et
     une liste dépliée sous le patrimoine net les repoussait hors de vue. Le
     compte suffit à savoir s'il y a lieu de regarder. Rien à signaler ⇒ rien
     à l'écran : un bandeau vide en permanence apprend à ne plus le lire. */
  renderAlertes(alertes) {
    const host = App.el('#ov-alertes');
    App.clear(host);
    if (!alertes.length) return;

    const urgents = alertes.filter((a) => a.niveau === 'attention').length;
    const pluriel = (n, mot) => `${n} ${mot}${n > 1 ? 's' : ''}`;
    const resume = urgents
      ? `${pluriel(urgents, 'point')} à voir · ${pluriel(alertes.length, 'observation')}`
      : pluriel(alertes.length, 'observation');

    const carte = App.h('details', { class: `alertes${urgents ? ' urgent' : ''}` },
      App.h('summary', {}, resume));
    for (const a of alertes) {
      const lien = a.action === 'asset' && a.asset_id
        ? App.h('button', {
          class: 'btn small',
          onclick: () => App.tabs.wealth.openAssetDetail(a.asset_id),
        }, 'Voir')
        : (a.action === 'settings'
          ? App.h('button', {
            class: 'btn small',
            onclick: () => App.settings.open(),
          }, 'Régler')
          : null);

      carte.append(App.h('div', { class: 'alerte' },
        App.h('span', {
          class: `pill ${a.niveau === 'attention' ? 'warn' : 'accent'}`,
        }, a.niveau === 'attention' ? 'à voir' : 'info'),
        App.h('div', {},
          App.h('div', { class: 'alerte-titre' }, a.titre),
          App.h('div', { class: 'alerte-detail' }, a.detail)),
        App.h('div', { class: 'alerte-action' }, lien)));
    }
    host.append(carte);
  },

  /* Un seul chiffre domine la page : le patrimoine net, avec sa variation
     sur le mois. Le reste descend d'un cran dans la hiérarchie. */
  renderHero(data) {
    const host = App.el('#ov-hero');
    App.clear(host);
    const m = data.metrics;
    const serie = data.patrimoine_serie || [];
    const precedent = serie.length > 1 ? serie[serie.length - 2].patrimoine_net : null;
    const variation = precedent === null ? null : m.patrimoine_net - precedent;

    const meta = App.h('div', { class: 'hero-meta' });
    if (variation !== null) {
      const sens = variation >= 0 ? 'pos' : 'neg';
      meta.append(App.h('span', { class: sens },
        `${variation >= 0 ? '▲' : '▼'} ${App.fmt.eur(Math.abs(variation))}`));
      if (precedent) {
        meta.append(App.h('span', { class: sens },
          App.fmt.pct(100 * variation / Math.abs(precedent), 1)));
      }
      meta.append(App.h('span', {}, 'sur un mois'));
    }
    meta.append(App.h('span', { class: 'sub' }, `arrêté au ${App.fmt.date(data.as_of)}`));

    const stat = (label, value, cls) => App.h('div', { class: 'hero-stat' },
      App.h('div', { class: 's-label' }, label),
      App.h('div', { class: `s-value ${cls || ''}` }, value));

    host.append(
      App.h('div', { class: 'hero-main' },
        App.h('div', { class: 'hero-label' }, 'Patrimoine net'),
        App.h('div', { class: 'hero-value' }, App.fmt.eur(m.patrimoine_net)),
        meta),
      App.h('div', { class: 'hero-side' },
        stat('Actifs', App.fmt.eur(m.total_actif, true)),
        stat('Dettes', m.total_passif ? `− ${App.fmt.eur(m.total_passif, true)}` : '—',
          m.total_passif ? 'neg' : ''),
        stat('Épargne du mois', App.fmt.eur(data.mois.epargne, true),
          data.mois.epargne > 0 ? 'pos' : '')));
  },

  /* ==================================================================
     Agrandissement sur place.

     La carte prend toute la largeur de sa grille et pousse les autres, le
     déplacement étant animé en FLIP. Une modale aurait masqué la page ; ici
     le graphique reste dans son contexte, les chiffres autour restent lisibles.
     ================================================================== */
  expanded: null,

  async toggleChart(kind) {
    const bouton = App.el(`[data-zoom="${kind}"]`);
    const carte = bouton.closest('.card');
    const extra = App.el(`#extra-${kind}`);
    const ouvrir = App.tabs.overview.expanded !== kind;

    // Une seule carte agrandie à la fois : deux, et il ne reste plus de vue
    // d'ensemble.
    const precedente = App.tabs.overview.expanded;

    // Toutes les cartes du panneau bougent : elles doivent toutes être
    // mesurées avant, sinon celles d'en dessous sautent.
    const cartes = App.els('#tab-overview .card');
    App.flip(cartes, () => {
      if (precedente && precedente !== kind) {
        App.el(`[data-zoom="${precedente}"]`).closest('.card').classList.remove('expanded');
        App.clear(App.el(`#extra-${precedente}`));
      }
      carte.classList.toggle('expanded', ouvrir);
      App.clear(extra);
    });

    App.tabs.overview.expanded = ouvrir ? kind : null;
    bouton.title = ouvrir ? 'Réduire' : 'Agrandir';

    // Les graphiques se redessinent une fois la nouvelle taille connue.
    if (precedente && precedente !== kind) App.tabs.overview.redraw(precedente);
    if (ouvrir) await App.tabs.overview.fillExtra(kind, extra);
    App.tabs.overview.redraw(kind);

    // Amener le graphique au centre de l'écran : agrandi, il déborde souvent
    // du cadre visible, surtout quand la carte est basse dans la page.
    // Le défilement attend la fin du FLIP : celui-ci anime des décalages en
    // pixels mesurés avant le changement, et bouger la page pendant fausserait
    // le trajet.
    if (!ouvrir) return;
    const reduit = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    setTimeout(() => carte.scrollIntoView({
      behavior: reduit ? 'auto' : 'smooth', block: 'center',
    }), reduit ? 0 : 440);
  },

  redraw(kind) {
    const data = App.tabs.overview.dernier;
    if (!data) return;
    if (kind === 'networth' && App.tabs.overview.expanded !== 'networth') {
      App.tabs.overview.renderNetWorth(data.patrimoine_serie);
    } else if (kind === 'categories') {
      App.tabs.overview.renderCategories(data.mois);
    } else if (kind === 'flows') {
      App.tabs.overview.renderFlows(data.depenses_serie);
    }
    const c = App.state.charts[`chart-${kind}`];
    if (c) c.resize();
  },

  /* Le placement côte à côte est fait par la grille de `.card.expanded` : il
     n'y a qu'à remplir la colonne de droite. */
  async fillExtra(kind, host) {
    const data = App.tabs.overview.dernier;
    if (kind === 'networth') return App.tabs.overview.buildAssetFilters(host);
    // Le camembert donne la forme, le tableau les chiffres exacts : les deux
    // se lisent ensemble.
    if (kind === 'categories') host.append(App.tabs.overview.tableCategories(data.mois));
    if (kind === 'flows') host.append(App.tabs.overview.tableFlows(data.depenses_serie));
    return null;
  },

  /* Filtres par type d'actif : la courbe ne montre que ce qui est coché et
     l'échelle se recalcule sur les seules séries visibles — Chart.js ignore
     les jeux masqués pour borner l'axe. */
  async buildAssetFilters(host) {
    let data;
    try { data = await App.api.get('/api/assets/series?months=12'); }
    catch (e) { host.append(App.h('p', { class: 'callout' }, e.message)); return; }
    if (!data.series.length) {
      host.append(App.h('p', { class: 'hint' }, 'Aucun actif à retracer sur la période.'));
      return;
    }

    const couleur = (i) => App.chartColors[i % App.chartColors.length];
    const jeux = data.series.map((s, i) => ({
      label: s.label, data: s.valeurs, type_actif: s.type,
      borderColor: couleur(i), backgroundColor: 'transparent',
      fill: false, tension: .3, pointRadius: 2, borderWidth: 2, spanGaps: false,
    }));

    const filtres = App.h('div', { class: 'filtres' });
    host.append(filtres);

    App.chart('chart-networth', {
      type: 'line',
      data: { labels: data.mois.map((m) => App.fmt.month(m)), datasets: jeux },
      options: {
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: {
            label: (c) => `${c.dataset.label} : ${App.fmt.eur(c.parsed.y)}` } },
        },
        scales: { y: { ticks: { callback: (v) => App.fmt.eur(v, true) } } },
      },
    });

    // Un type peut porter plusieurs actifs : on coche par type, comme demandé.
    const parType = new Map();
    data.series.forEach((s, i) => {
      const e = parType.get(s.type) || { type: s.type, index: [], total: 0, couleur: couleur(i) };
      e.index.push(i);
      e.total += s.valeurs[s.valeurs.length - 1] || 0;
      parType.set(s.type, e);
    });

    for (const e of [...parType.values()].sort((a, b) => b.total - a.total)) {
      const cb = App.h('input', { type: 'checkbox' });
      cb.checked = true;
      cb.addEventListener('change', () => {
        const chart = App.state.charts['chart-networth'];
        if (!chart) return;
        e.index.forEach((i) => chart.setDatasetVisibility(i, cb.checked));
        chart.update();                 // l'échelle se rebâtit sur le visible
      });
      filtres.append(App.h('label', { class: 'filtre' },
        cb,
        App.h('span', { class: 'puce', style: `background:${e.couleur}` }),
        App.h('span', {}, e.type),
        App.h('span', { class: 'montant' }, App.fmt.eur(e.total, true))));
    }
  },

  tableCategories(mois) {
    const cats = mois.par_categorie;
    const total = cats.reduce((s, c) => s + c.montant, 0);
    const tbody = App.h('tbody', {});
    for (const c of cats) {
      tbody.append(App.h('tr', {},
        App.h('td', {}, c.category),
        App.h('td', { class: 'right num' }, App.fmt.eur(c.montant)),
        App.h('td', { class: 'right num' }, App.fmt.pct(100 * c.montant / total)),
        App.h('td', { class: 'right num muted' }, String(c.nb || 0))));
    }
    tbody.append(App.h('tr', {},
      App.h('td', {}, App.h('strong', {}, 'Total')),
      App.h('td', { class: 'right num' }, App.h('strong', {}, App.fmt.eur(total))),
      App.h('td', {}), App.h('td', {})));
    return App.h('div', { class: 'table-wrap scroll-y' },
      App.h('table', { class: 'table' },
        App.h('thead', {}, App.h('tr', {},
          App.h('th', {}, 'Catégorie'),
          App.h('th', { class: 'right' }, 'Montant'),
          App.h('th', { class: 'right' }, 'Part'),
          App.h('th', { class: 'right' }, 'Opér.'))),
        tbody));
  },

  tableFlows(serie) {
    const tbody = App.h('tbody', {});
    for (const p of serie) {
      const solde = Math.round((p.revenus - p.depenses) * 100) / 100;
      tbody.append(App.h('tr', {},
        App.h('td', {}, App.fmt.month(p.mois)),
        App.h('td', { class: 'right num pos' }, App.fmt.eur(p.revenus)),
        App.h('td', { class: 'right num' }, App.fmt.eur(p.depenses)),
        App.h('td', { class: `right num ${solde >= 0 ? 'pos' : 'neg'}` },
          App.fmt.signed(solde)),
        App.h('td', { class: 'right num muted' },
          p.revenus ? App.fmt.pct(100 * p.epargne / p.revenus) : '—')));
    }
    return App.h('div', { class: 'table-wrap scroll-y' },
      App.h('table', { class: 'table' },
        App.h('thead', {}, App.h('tr', {},
          App.h('th', {}, 'Mois'),
          App.h('th', { class: 'right' }, 'Revenus'),
          App.h('th', { class: 'right' }, 'Dépenses'),
          App.h('th', { class: 'right' }, 'Solde'),
          App.h('th', { class: 'right' }, 'Épargne'))),
        tbody));
  },

  kpi(label, value, delta, deltaClass) {
    return App.h('div', { class: 'kpi' },
      App.h('div', { class: 'label' }, label),
      App.h('div', { class: 'value' }, value),
      delta ? App.h('div', { class: `delta ${deltaClass || ''}` }, delta) : null);
  },

  renderKpis(data) {
    const host = App.el('#ov-kpis');
    App.clear(host);
    const m = data.metrics;
    const cur = data.mois;
    const prev = data.mois_precedent;

    let deltaText = 'aucune dépense le mois précédent';
    let deltaClass = '';
    if (prev.depenses) {
      const sign = data.variation_depenses > 0 ? '+' : '';
      deltaText = `${sign}${App.fmt.eur(data.variation_depenses)} vs ${App.fmt.month(prev.mois)}`;
      deltaClass = data.variation_depenses > 0 ? 'up' : 'down';
    }

    // Le patrimoine net est déjà en héros : ces quatre cases le complètent
    // au lieu de le répéter.
    host.append(
      App.tabs.overview.kpi('Dépensé ce mois', App.fmt.eur(cur.depenses), deltaText, deltaClass),
      App.tabs.overview.kpi('Revenus du mois', App.fmt.eur(cur.revenus),
        cur.transferts_internes
          ? `hors ${App.fmt.eur(cur.transferts_internes)} de virements internes`
          : `${cur.nb_transactions} transaction(s)`),
      App.tabs.overview.kpi("Taux d'épargne",
        cur.taux_epargne === null ? '—' : App.fmt.ratio(cur.taux_epargne),
        `${App.fmt.eur(cur.epargne)} épargnés sur ${App.fmt.eur(cur.revenus)} de revenus`,
        cur.taux_epargne !== null && cur.taux_epargne >= 0.2 ? 'good' : ''),
      App.tabs.overview.kpi("Couverture d'urgence",
        m.mois_couverture_urgence === null ? '—' : `${App.fmt.num(m.mois_couverture_urgence, 1)} mois`,
        `${App.fmt.eur(m.solde_livrets, true)} de livrets`,
        m.mois_couverture_urgence !== null && m.mois_couverture_urgence < 3 ? 'bad' : 'good'),
    );
  },

  renderNetWorth(series) {
    App.chart('chart-networth', {
      type: 'line',
      data: {
        labels: series.map((p) => App.fmt.month(p.mois)),
        datasets: [
          {
            label: 'Patrimoine net',
            data: series.map((p) => p.patrimoine_net),
            borderColor: App.chartColors[0],
            backgroundColor: 'rgba(91,141,239,.14)',
            fill: true, tension: .3, pointRadius: 2, borderWidth: 2,
          },
          {
            label: 'Total actifs',
            data: series.map((p) => p.total_actif),
            borderColor: App.chartColors[1],
            borderDash: [5, 4], fill: false, tension: .3, pointRadius: 0, borderWidth: 1.5,
          },
        ],
      },
      options: {
        interaction: { mode: 'index', intersect: false },
        plugins: {
          tooltip: {
            callbacks: { label: (c) => `${c.dataset.label} : ${App.fmt.eur(c.parsed.y)}` },
          },
        },
        scales: { y: { ticks: { callback: (v) => App.fmt.eur(v, true) } } },
      },
    });
  },

  renderCategories(month) {
    App.el('#ov-cat-month').textContent = App.fmt.month(month.mois);
    const cats = month.par_categorie;
    if (!cats.length) {
      App.chart('chart-categories', {
        type: 'doughnut',
        data: { labels: ['Aucune dépense'], datasets: [{ data: [1], backgroundColor: ['#2a3242'] }] },
        options: { plugins: { tooltip: { enabled: false } } },
      });
      return;
    }
    const total = cats.reduce((s, c) => s + c.montant, 0);
    App.chart('chart-categories', {
      type: 'doughnut',
      data: {
        labels: cats.map((c) => c.category),
        datasets: [{
          data: cats.map((c) => c.montant),
          backgroundColor: cats.map((_, i) => App.chartColors[i % App.chartColors.length]),
          borderWidth: 0,
        }],
      },
      options: {
        cutout: '62%',
        plugins: {
          legend: { position: 'right' },
          tooltip: {
            callbacks: {
              label: (c) => `${c.label} : ${App.fmt.eur(c.parsed)} (${App.fmt.pct(100 * c.parsed / total)})`,
            },
          },
        },
      },
    });
  },

  renderRepartition(rep, metrics) {
    const host = App.el('#ov-repartition');
    App.clear(host);
    // Les frais annuels étaient noyés dans une liste qui répétait le héros ;
    // ils se lisent mieux au pied de la poche qu'ils grèvent.
    const frais = App.el('#ov-frais');
    if (frais) {
      frais.textContent = metrics && metrics.frais_annuels
        ? `Frais annuels : ${App.fmt.eur(metrics.frais_annuels)}`
          + (metrics.frais_pct_encours
            ? ` (${App.fmt.pct(metrics.frais_pct_encours, 2)} de l’encours)` : '')
        : '';
    }
    if (!rep.buckets.length) {
      host.append(App.h('p', { class: 'muted' },
        'Aucune poche définie. Configurez la répartition cible dans les paramètres.'));
      return;
    }
    for (const b of rep.buckets) {
      const ecartClass = Math.abs(b.ecart_pct) < 5 ? 'ok' : 'warn';
      host.append(App.h('div', { class: 'rep-row' },
        App.h('div', { class: 'rep-head' },
          App.h('span', {}, b.label, ' ', App.h('span', { class: 'sub' }, App.fmt.eur(b.montant, true))),
          App.h('span', {},
            App.h('span', { class: `pill ${ecartClass}` },
              `${b.reel_pct > b.cible_pct ? '+' : ''}${App.fmt.num(b.ecart_pct, 1)} pt`),
            ' ',
            App.h('span', { class: 'sub' }, `${App.fmt.num(b.reel_pct, 1)} % / cible ${App.fmt.num(b.cible_pct, 1)} %`))),
        App.h('div', { class: 'rep-bars' },
          App.h('div', { class: 'rep-real', style: `width:${Math.min(100, b.reel_pct)}%` }),
          App.h('div', { class: 'rep-target', style: `left:${Math.min(100, b.cible_pct)}%` }))));
    }
    host.append(App.h('div', { class: 'rep-legend' },
      App.h('span', {}, `Base : ${App.fmt.eur(rep.base)}`),
      rep.hors_poches ? App.h('span', {}, `Hors poches : ${App.fmt.eur(rep.hors_poches)}`) : null,
      App.h('span', {}, '| trait vertical = cible')));
  },

  renderFlows(series) {
    App.chart('chart-flows', {
      type: 'bar',
      data: {
        labels: series.map((p) => App.fmt.month(p.mois)),
        datasets: [
          { label: 'Revenus', data: series.map((p) => p.revenus), backgroundColor: App.chartColors[1], borderRadius: 4 },
          { label: 'Dépenses', data: series.map((p) => p.depenses), backgroundColor: App.chartColors[4], borderRadius: 4 },
          { label: 'Épargne', data: series.map((p) => p.epargne), backgroundColor: App.chartColors[0], borderRadius: 4 },
        ],
      },
      options: {
        plugins: {
          tooltip: { callbacks: { label: (c) => `${c.dataset.label} : ${App.fmt.eur(c.parsed.y)}` } },
        },
        scales: { y: { ticks: { callback: (v) => App.fmt.eur(v, true) } } },
      },
    });
  }
};
