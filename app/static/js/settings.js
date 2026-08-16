/* Paramètres : catégories, règles de classification, répartition cible,
   frais annuels, types d'actifs personnalisés. */
App.settings = {
  async open(focus) {
    const [settings, rules, market] = await Promise.all([
      App.api.get('/api/settings'),
      App.api.get('/api/rules'),
      App.api.get('/api/market/status'),
    ]);
    App.state.settings = settings;

    // Trois sections au lieu de six. Les réglages qui se répondent sont
    // désormais côte à côte : classer ses dépenses, viser une répartition,
    // brancher les cours. Le contenu est intact, seul le rangement change.
    const sections = [
      ['Classement des dépenses', App.h('div', {},
        App.settings.panelCategories(settings),
        App.h('div', { class: 'section-title' }, 'Règles de classification'),
        App.settings.panelRules(rules, settings))],
      ['Objectifs et frais', App.h('div', {},
        App.settings.panelRepartition(settings),
        App.h('div', { class: 'section-title' }, 'Frais annuels'),
        App.settings.panelFees(settings))],
      ['Cours de marché', App.h('div', {},
        App.settings.panelMarket(settings, market),
        App.h('div', { class: 'section-title' }, 'Types d’actifs personnalisés'),
        App.settings.panelAssetTypes(settings))],
      ['Sauvegardes', App.settings.panelBackups(settings)],
    ];
    const trouve = sections.findIndex(
      ([label]) => focus && label.toLowerCase().includes(focus.toLowerCase()));
    const startIndex = trouve >= 0 ? trouve : 0;

    const nav = App.h('div', { class: 'tabs-inline' });
    const stack = App.h('div', {});
    sections.forEach(([label, node], i) => {
      const btn = App.h('button', { class: i === startIndex ? 'active' : '' }, label);
      const panel = App.h('div', { class: `subpanel${i === startIndex ? ' active' : ''}` }, node);
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
      title: 'Paramètres',
      wide: true,
      body: App.h('div', {}, nav, stack),
      footer: [App.h('button', { class: 'btn primary', onclick: () => App.modal.close() }, 'Fermer')],
    });
  },

  async save(patch, message = 'Paramètres enregistrés') {
    try {
      await App.api.put('/api/settings', patch);
      Object.assign(App.state.settings, patch);
      App.toast(message, 'success');
      await App.loadMeta();
      await App.refreshAll();
    } catch (e) { App.toast(e.message, 'error'); }
  },

  /* ---------- catégories ---------- */
  panelCategories(settings) {
    const build = (key, title, hint) => {
      const list = App.h('div', { class: 'actions' });
      const render = () => {
        App.clear(list);
        for (const cat of settings[key] || []) {
          list.append(App.h('span', { class: 'pill' }, cat, ' ',
            App.h('a', {
              href: '#', style: 'color:var(--red);text-decoration:none',
              onclick: async (e) => {
                e.preventDefault();
                settings[key] = settings[key].filter((c) => c !== cat);
                render();
                await App.settings.save({ [key]: settings[key] }, 'Catégorie supprimée');
              },
            }, '×')));
        }
      };
      render();
      const input = App.input('new', { placeholder: 'Nouvelle catégorie…' });
      const add = async () => {
        const value = input.value.trim();
        if (!value) return;
        if ((settings[key] || []).includes(value)) return App.toast('Déjà présente', 'error');
        settings[key] = [...(settings[key] || []), value];
        input.value = '';
        render();
        await App.settings.save({ [key]: settings[key] }, 'Catégorie ajoutée');
      };
      input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } });
      return App.h('div', {},
        App.h('div', { class: 'section-title' }, title),
        hint ? App.h('p', { class: 'hint' }, hint) : null,
        list,
        App.h('div', { class: 'actions', style: 'margin-top:10px' },
          input, App.h('button', { class: 'btn', onclick: add }, 'Ajouter')));
    };

    /* Cases à cocher sur la liste des catégories de dépenses. */
    const checkboxes = (key, message) => {
      const host = App.h('div', {});
      const render = () => {
        App.clear(host);
        for (const cat of settings.categories_depenses || []) {
          const cb = App.h('input', { type: 'checkbox' });
          cb.checked = (settings[key] || []).includes(cat);
          cb.addEventListener('change', async () => {
            const set = new Set(settings[key] || []);
            if (cb.checked) set.add(cat); else set.delete(cat);
            settings[key] = [...set];
            await App.settings.save({ [key]: settings[key] }, message);
          });
          host.append(App.h('label',
            { class: 'checkline', style: 'margin-right:14px' }, cb, cat));
        }
      };
      render();
      return host;
    };

    /* Mots-clés qui trahissent un virement entre comptes de l'utilisateur. */
    const motsHost = App.h('div', { class: 'actions' });
    const renderMots = () => {
      App.clear(motsHost);
      for (const mot of settings.mots_cles_transfert || []) {
        motsHost.append(App.h('span', { class: 'pill accent' }, mot, ' ',
          App.h('a', {
            href: '#', style: 'color:var(--perte);text-decoration:none',
            onclick: async (e) => {
              e.preventDefault();
              settings.mots_cles_transfert = (settings.mots_cles_transfert || [])
                .filter((m) => m !== mot);
              renderMots();
              await App.settings.save(
                { mots_cles_transfert: settings.mots_cles_transfert }, 'Mot-clé supprimé');
            },
          }, '×')));
      }
    };
    renderMots();
    const motInput = App.input('mot', { placeholder: 'ex : revolut, virement interne…' });
    const addMot = async () => {
      const value = motInput.value.trim();
      if (!value) return;
      settings.mots_cles_transfert = [...(settings.mots_cles_transfert || []), value];
      motInput.value = '';
      renderMots();
      await App.settings.save(
        { mots_cles_transfert: settings.mots_cles_transfert }, 'Mot-clé ajouté');
    };
    motInput.addEventListener('keydown',
      (e) => { if (e.key === 'Enter') { e.preventDefault(); addMot(); } });

    return App.h('div', {},
      build('categories_depenses', 'Catégories de dépenses'),
      build('categories_revenus', 'Catégories de revenus'),

      App.h('div', { class: 'section-title' }, 'Comptées comme épargne, pas comme dépense'),
      App.h('p', { class: 'hint' },
        'Un virement vers un livret n’est pas une dépense : coché, il est compté '
        + 'comme épargne et entre dans le taux d’épargne.'),
      checkboxes('categories_non_depense', 'Exclusions mises à jour'),

      App.h('div', { class: 'section-title' }, 'Charges fixes'),
      App.h('p', { class: 'hint' },
        'Ce qui tombe tous les mois quoi qu’il arrive. Ce qui reste une fois '
        + 'ces charges et votre épargne mises de côté, c’est votre reste à vivre.'),
      checkboxes('categories_charges_fixes', 'Charges fixes mises à jour'),

      App.h('div', { class: 'section-title' }, 'Virements internes — neutres des deux côtés'),
      App.h('p', { class: 'hint' },
        'Un virement LCL → Revolut apparaît deux fois : en débit sur un relevé, en '
        + 'crédit sur l’autre. Ces catégories ne comptent donc ni comme dépense, ni '
        + 'comme revenu, ni comme épargne — l’argent a seulement changé de poche.'),
      checkboxes('categories_transfert', 'Virements internes mis à jour'),

      App.h('div', { class: 'section-title' }, 'Mots-clés de détection à l’import'),
      App.note('Comment ils sont utilisés',
        'Cherchés dans le libellé, sans casse ni accents. Vos règles de classification '
        + 'restent prioritaires. Le rapprochement par paires (bouton « Détecter les '
        + 'virements internes » dans l’onglet Dépenses) rattrape ce que les mots-clés '
        + 'manquent, en appariant deux relevés.'),
      App.h('div', { style: 'margin:10px 0' }, motsHost),
      App.h('div', { class: 'actions' },
        motInput, App.h('button', { class: 'btn', onclick: addMot }, 'Ajouter')));
  },

  /* ---------- règles ---------- */
  panelRules(rules, settings) {
    const tbody = App.h('tbody', {});
    const render = () => {
      App.clear(tbody);
      if (!rules.length) {
        tbody.append(App.h('tr', {}, App.h('td', { colspan: 5, class: 'empty' },
          'Aucune règle. Les revenus (salaire, parents, loyers) ne peuvent pas être devinés '
          + 'sans règle : définissez-les ici une fois pour toutes.')));
      }
      for (const r of rules) {
        tbody.append(App.h('tr', {},
          App.h('td', {}, App.h('code', {}, r.pattern)),
          App.h('td', {}, r.cible_type === 'type_revenu' ? 'Revenu' : 'Dépense'),
          App.h('td', {}, App.h('span', { class: 'pill accent' }, r.valeur)),
          App.h('td', { class: 'right num' }, r.priorite),
          App.h('td', { class: 'right' }, App.h('button', {
            class: 'icon-btn',
            onclick: async () => {
              await App.api.del(`/api/rules/${r.id}`);
              rules.splice(rules.indexOf(r), 1);
              render();
              App.toast('Règle supprimée', 'success');
            },
          }, '×'))));
      }
    };
    render();

    const pattern = App.input('pattern', { placeholder: 'ex : VIREMENT DUPONT' });
    const cible = App.select('cible_type',
      [['categorie_depense', 'Dépense'], ['type_revenu', 'Revenu']], 'categorie_depense');
    const valeur = App.select('valeur', App.categoriesAll(), 'Salaire');
    const priorite = App.input('priorite', { type: 'number', value: 100 });

    const add = async () => {
      if (!pattern.value.trim()) return App.toast('Motif requis', 'error');
      try {
        const res = await App.api.post('/api/rules', {
          pattern: pattern.value.trim(), cible_type: cible.value,
          valeur: valeur.value, priorite: priorite.value,
        });
        rules.push({
          id: res.id, pattern: pattern.value.trim(), cible_type: cible.value,
          valeur: valeur.value, priorite: parseInt(priorite.value, 10) || 100,
        });
        pattern.value = '';
        render();
        App.toast('Règle ajoutée', 'success');
      } catch (e) { App.toast(e.message, 'error'); }
    };

    const applyNow = async () => {
      try {
        const res = await App.api.post('/api/rules/apply', { seulement_non_categorise: true });
        App.toast(`${res.modifiees} transaction(s) reclassée(s)`, 'success');
        await App.refreshAll();
      } catch (e) { App.toast(e.message, 'error'); }
    };

    return App.h('div', {},
      App.h('p', { class: 'hint' },
        'Le motif est cherché dans le libellé, sans tenir compte de la casse ni des accents. '
        + 'La règle de plus petite priorité gagne. Le remboursement de prêt est détecté '
        + 'automatiquement par le montant et la date, sans règle.'),
      App.h('div', { class: 'table-wrap scroll-y', style: 'margin-top:10px' },
        App.h('table', { class: 'table' },
          App.h('thead', {}, App.h('tr', {},
            App.h('th', {}, 'Motif'), App.h('th', {}, 'Cible'), App.h('th', {}, 'Valeur'),
            App.h('th', { class: 'right' }, 'Priorité'), App.h('th', {}))),
          tbody)),
      App.h('div', { class: 'section-title' }, 'Nouvelle règle'),
      App.h('div', { class: 'form-grid' },
        App.field('Motif', pattern),
        App.field('Cible', cible),
        App.field('Valeur attribuée', valeur),
        App.field('Priorité', priorite, { hint: 'plus petit = prioritaire' })),
      App.h('div', { class: 'actions', style: 'margin-top:12px' },
        App.h('button', { class: 'btn primary', onclick: add }, 'Ajouter la règle'),
        App.h('button', { class: 'btn', onclick: applyNow },
          'Appliquer aux transactions non catégorisées')));
  },

  /* ---------- répartition cible ---------- */
  panelRepartition(settings) {
    let buckets = JSON.parse(JSON.stringify(settings.repartition_cible || []));
    if (!Array.isArray(buckets)) {
      buckets = Object.entries(buckets).map(([k, v]) => ({ label: k, types: [k], pct: v }));
    }
    const allTypes = (App.state.meta.asset_types || []).map((t) => t.type);
    const host = App.h('div', {});
    const totalNode = App.h('p', { class: 'hint' });

    const render = () => {
      App.clear(host);
      buckets.forEach((b, i) => {
        const typesSel = App.h('select', { multiple: true, size: 4 });
        for (const t of allTypes) {
          const opt = App.h('option', { value: t }, t);
          if ((b.types || []).includes(t)) opt.selected = true;
          typesSel.append(opt);
        }
        typesSel.addEventListener('change', () => {
          b.types = Array.from(typesSel.selectedOptions).map((o) => o.value);
        });
        const labelIn = App.input('l', { value: b.label || '' });
        labelIn.addEventListener('input', () => { b.label = labelIn.value; });
        const pctIn = App.input('p', { type: 'number', step: '0.1', value: b.pct ?? 0 });
        pctIn.addEventListener('input', () => {
          b.pct = parseFloat(pctIn.value) || 0;
          updateTotal();
        });
        host.append(App.h('div', { class: 'form-grid', style: 'margin-bottom:10px' },
          App.field('Poche', labelIn),
          App.field('Cible (%)', pctIn),
          App.field("Types d'actifs inclus", typesSel, { hint: 'Ctrl+clic pour en choisir plusieurs' }),
          App.h('div', { class: 'field' }, App.h('label', {}, ' '),
            App.h('button', {
              class: 'btn danger',
              onclick: () => { buckets.splice(i, 1); render(); updateTotal(); },
            }, 'Retirer'))));
      });
    };
    const updateTotal = () => {
      const total = buckets.reduce((s, b) => s + (parseFloat(b.pct) || 0), 0);
      totalNode.textContent = `Total des cibles : ${App.fmt.num(total, 1)} %`
        + (Math.abs(total - 100) > 0.01 ? ' — attention, la somme n’est pas 100 %.' : ' ✓');
    };
    render(); updateTotal();

    return App.h('div', {},
      App.h('p', { class: 'hint' },
        'Stratégie DCA : définissez la cible de chaque poche. L’écart cible / réel est '
        + 'affiché sur la vue d’ensemble et dans l’archive mensuelle.'),
      App.h('div', { style: 'margin-top:12px' }, host),
      totalNode,
      App.h('div', { class: 'actions', style: 'margin-top:12px' },
        App.h('button', {
          class: 'btn',
          onclick: () => { buckets.push({ label: 'Nouvelle poche', types: [], pct: 0 }); render(); updateTotal(); },
        }, '+ Poche'),
        App.h('button', {
          class: 'btn primary',
          onclick: () => App.settings.save({ repartition_cible: buckets }, 'Répartition enregistrée'),
        }, 'Enregistrer')));
  },

  /* ---------- frais annuels ---------- */
  panelFees(settings) {
    const fees = Object.assign({}, settings.frais_annuels || {});
    const year = String(new Date().getFullYear());
    const yearIn = App.input('annee', { type: 'number', value: year });
    const terIn = App.input('ter', { type: 'number', step: '0.01', value: (fees[year] || {}).ter ?? '' });
    const cIn = App.input('courtage', { type: 'number', step: '0.01', value: (fees[year] || {}).courtage ?? '' });

    const tbody = App.h('tbody', {});
    const render = () => {
      App.clear(tbody);
      const years = Object.keys(fees).sort().reverse();
      if (!years.length) {
        tbody.append(App.h('tr', {}, App.h('td', { colspan: 4, class: 'empty' }, 'Aucun frais saisi.')));
      }
      for (const y of years) {
        const f = fees[y] || {};
        const total = (parseFloat(f.ter) || 0) + (parseFloat(f.courtage) || 0);
        tbody.append(App.h('tr', {},
          App.h('td', {}, y),
          App.h('td', { class: 'right num' }, App.fmt.eur(f.ter || 0)),
          App.h('td', { class: 'right num' }, App.fmt.eur(f.courtage || 0)),
          App.h('td', { class: 'right num' }, App.fmt.eur(total))));
      }
    };
    render();

    const save = async () => {
      const y = String(parseInt(yearIn.value, 10) || new Date().getFullYear());
      fees[y] = { ter: parseFloat(terIn.value) || 0, courtage: parseFloat(cIn.value) || 0 };
      render();
      await App.settings.save({ frais_annuels: fees }, 'Frais enregistrés');
    };

    return App.h('div', {},
      App.h('p', { class: 'hint' },
        'TER des ETF + frais de courtage, saisis une fois par an. Le total est rapporté '
        + 'à l’encours dans la vue d’ensemble.'),
      App.h('div', { class: 'form-grid', style: 'margin-top:12px' },
        App.field('Année', yearIn),
        App.field('TER (€)', terIn),
        App.field('Courtage (€)', cIn)),
      App.h('div', { class: 'actions', style: 'margin:12px 0' },
        App.h('button', { class: 'btn primary', onclick: save }, 'Enregistrer')),
      App.h('div', { class: 'table-wrap' },
        App.h('table', { class: 'table' },
          App.h('thead', {}, App.h('tr', {},
            App.h('th', {}, 'Année'), App.h('th', { class: 'right' }, 'TER'),
            App.h('th', { class: 'right' }, 'Courtage'), App.h('th', { class: 'right' }, 'Total'))),
          tbody)));
  },

  /* ---------- sauvegardes CSV ---------- */
  panelBackups(settings) {
    const host = App.h('div', {});
    const tbody = App.h('tbody', {});
    const entete = App.h('p', { class: 'hint' });

    const octets = (n) => (n < 1024 ? `${n} o`
      : n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} Ko`
        : `${(n / 1024 / 1024).toFixed(1)} Mo`);

    const recharger = async () => {
      let data;
      try { data = await App.api.get('/api/backups'); }
      catch (e) { return App.toast(e.message, 'error'); }

      entete.textContent = data.sauvegardes.length
        ? `${data.sauvegardes.length} sauvegarde(s), ${octets(data.taille_totale)} en tout `
          + `· les ${data.maximum} plus récentes sont conservées`
        : 'Aucune sauvegarde pour le moment.';

      App.clear(tbody);
      if (!data.sauvegardes.length) {
        tbody.append(App.h('tr', {}, App.h('td', { colspan: 4, class: 'empty' },
          'Cliquez sur « Sauvegarder maintenant » pour créer la première.')));
      }
      for (const s of data.sauvegardes) {
        tbody.append(App.h('tr', {},
          App.h('td', { class: 'nowrap' }, App.fmt.dateTime(s.date)),
          App.h('td', { class: 'right num' },
            s.patrimoine_net === null ? '—' : App.fmt.eur(s.patrimoine_net)),
          App.h('td', { class: 'right num' }, octets(s.taille)),
          App.h('td', { class: 'right' },
            App.h('button', {
              class: 'btn small',
              title: 'Remplacer vos données actuelles par celles-ci',
              onclick: () => App.settings.confirmRestore(s, recharger),
            }, 'Restaurer'),
            ' ',
            App.h('button', {
              class: 'btn small danger',
              onclick: () => App.confirm(
                `Supprimer la sauvegarde du ${App.fmt.dateTime(s.date)} ?`,
                async () => {
                  await App.api.del(`/api/backups/${s.id}`);
                  App.toast('Sauvegarde supprimée', 'success');
                  await recharger();
                }),
            }, '×'))));
      }
    };

    const sauvegarder = async (btn) => {
      btn.classList.add('busy');
      try {
        const res = await App.api.post('/api/backups', {});
        if (res.inchange) {
          App.toast(res.message, 'success');
        } else {
          App.toast(`Sauvegarde créée — ${res.fichiers} fichiers, ${octets(res.taille)}`
            + (res.anciennes_supprimees.length
              ? ` · ${res.anciennes_supprimees.length} ancienne(s) effacée(s)` : ''),
          'success');
        }
        await recharger();
      } catch (e) { App.toast(e.message, 'error'); }
      btn.classList.remove('busy');
    };

    recharger();

    return App.h('div', {}, host,
      App.h('p', { class: 'hint' },
        'Chaque sauvegarde est un dossier horodaté contenant un fichier CSV par '
        + 'table, plus un « resume.csv » qui se lit directement dans un tableur.'),
      App.h('div', { class: 'actions', style: 'margin:14px 0' },
        App.h('button', {
          class: 'btn primary', onclick: (e) => sauvegarder(e.target),
        }, 'Sauvegarder maintenant'),
        App.h('button', {
          class: 'btn',
          onclick: async () => {
            try { await App.api.post('/api/backups/open', {}); }
            catch (e) { App.toast(e.message, 'error'); }
          },
        }, 'Ouvrir le dossier')),
      entete,
      App.h('div', { class: 'table-wrap scroll-y', style: 'margin-top:10px' },
        App.h('table', { class: 'table' },
          App.h('thead', {}, App.h('tr', {},
            App.h('th', {}, 'Date'),
            App.h('th', { class: 'right' }, 'Patrimoine net'),
            App.h('th', { class: 'right' }, 'Taille'),
            App.h('th', {}))),
          tbody)),
      App.note('Pourquoi les fichiers restent légers',
        App.h('p', {},
          'Le cache des cours de marché n’est pas sauvegardé : il se '
          + 'retélécharge d’un clic, et c’est la table qui grossit le plus vite '
          + '(un cours par ligne et par jour).'),
        App.h('p', {},
          'Rien n’est réécrit si rien n’a changé depuis la dernière sauvegarde, '
          + 'et les plus anciennes sont effacées automatiquement au-delà du '
          + 'nombre conservé.'),
        App.h('p', {},
          'Votre clé API n’est pas exportée : elle resterait en clair dans '
          + 'autant de fichiers que de sauvegardes.')));
  },

  confirmRestore(s, apres) {
    App.modal.open({
      title: 'Restaurer cette sauvegarde ?',
      body: App.h('div', {},
        App.h('p', {},
          `Vos données actuelles seront remplacées par celles du `
          + `${App.fmt.dateTime(s.date)}`
          + (s.patrimoine_net === null ? '' : ` (patrimoine net ${App.fmt.eur(s.patrimoine_net)})`)
          + '.'),
        App.h('p', { class: 'callout' },
          'Tout ce que vous avez saisi depuis cette date sera perdu. '
          + 'Une sauvegarde de sécurité est prise juste avant, ce qui permet de '
          + 'revenir en arrière — mais l’opération n’est pas anodine.')),
      footer: [
        App.h('button', { class: 'btn', onclick: () => App.modal.close() }, 'Annuler'),
        App.h('button', {
          class: 'btn danger',
          onclick: async () => {
            try {
              const res = await App.api.post(`/api/backups/${s.id}/restore`, {});
              App.modal.close();
              App.toast(`${res.lignes} ligne(s) restaurée(s)`, 'success');
              await apres();
              await App.refreshAll();
            } catch (e) { App.toast(e.message, 'error'); }
          },
        }, 'Restaurer'),
      ],
    });
  },

  /* ---------- cours de marché ---------- */
  panelMarket(settings, status) {
    const enabled = App.h('input', { type: 'checkbox' });
    enabled.checked = !!settings.market_enabled;
    const providerSel = App.select('market_provider',
      [['twelvedata', 'Twelve Data (titres, clé requise)']], settings.market_provider);
    /* La clé n'est plus renvoyée par l'API : le serveur n'expose qu'un booléen
       (voir CLES_SECRETES dans app/routes/settings.py). Le champ part donc
       toujours vide, et son texte d'invite dit l'état plutôt que la valeur. */
    const cleEnPlace = !!settings.market_api_key_configuree;
    const keyIn = App.input('market_api_key', {
      type: 'password', value: '',
      placeholder: cleEnPlace ? 'clé enregistrée — laisser vide pour la garder'
        : 'clé API Twelve Data',
    });
    const autoIn = App.h('input', { type: 'checkbox' });
    autoIn.checked = settings.market_auto_refresh !== false;
    const ttlIn = App.input('ttl', {
      type: 'number', min: 1, value: settings.market_cache_ttl_hours ?? 24,
    });

    const save = () => {
      const reglages = {
        market_enabled: enabled.checked,
        market_provider: providerSel.value,
        market_auto_refresh: autoIn.checked,
        market_cache_ttl_hours: parseInt(ttlIn.value, 10) || 24,
      };
      /* Champ vide alors qu'une clé existe : on ne l'envoie PAS. Sans cette
         garde, le simple fait d'enregistrer un autre réglage effacerait la clé,
         puisque le champ ne peut plus être pré-rempli. Pour la retirer
         volontairement, le bouton « Oublier la clé » ci-dessous. */
      const saisie = keyIn.value.trim();
      if (saisie || !cleEnPlace) reglages.market_api_key = saisie;
      App.settings.save(reglages, 'Réglages des cours enregistrés');
    };

    const oublierCle = async () => {
      await App.settings.save({ market_api_key: '' }, 'Clé oubliée');
      keyIn.value = '';
    };

    /* --- test d'un symbole : la vérification de couverture Euronext --- */
    const testSym = App.input('sym', { placeholder: 'ex : CW8' });
    const testEx = App.input('exch', { placeholder: 'ex : Euronext' });
    const testOut = App.h('div', { class: 'hint' });
    const runTest = async () => {
      testOut.textContent = 'Test en cours…';
      try {
        const res = await App.api.post('/api/market/test', {
          symbol: testSym.value.trim(), exchange: testEx.value.trim(),
        });
        App.clear(testOut);
        testOut.append(res.ok
          ? App.h('span', { class: 'pill ok' },
            `${res.symbole} : ${App.fmt.num(res.price, 4)} ${res.currency}`
            + (res.exchange ? ` · ${res.exchange}` : '') + ` · ${res.date}`)
          : App.h('span', { class: 'pill warn' }, `${res.symbole} : ${res.erreur}`));
      } catch (e) {
        App.clear(testOut);
        testOut.append(App.h('span', { class: 'pill warn' }, e.message));
      }
    };

    /* --- correspondances ticker -> symbole --- */
    const tbody = App.h('tbody', {});
    const renderSecurities = async () => {
      const data = await App.api.get('/api/securities');
      const bySymbol = Object.fromEntries(data.securities.map((s) => [s.ticker, s]));
      const tickers = [...new Set([
        ...data.tickers_utilises.map((t) => t.ticker),
        ...data.securities.map((s) => s.ticker),
      ])].sort();
      App.clear(tbody);
      if (!tickers.length) {
        tbody.append(App.h('tr', {}, App.h('td', { colspan: 6, class: 'empty' },
          'Aucun ticker dans vos mouvements. Renseignez le ticker ou l’ISIN '
          + 'de vos achats pour pouvoir les coter.')));
        return;
      }
      for (const ticker of tickers) {
        const sec = bySymbol[ticker] || {};
        const symbol = App.input('s', { value: sec.symbol || '', placeholder: 'symbole' });
        const exchange = App.input('e', { value: sec.exchange || '', placeholder: 'place' });
        const currency = App.input('c', { value: sec.currency || 'EUR' });
        const bench = App.input('b', {
          value: sec.benchmark_symbol || '', placeholder: 'indice de réf.',
        });
        const persist = async () => {
          await App.api.post('/api/securities', {
            ticker,
            symbol: symbol.value.trim(),
            exchange: exchange.value.trim(),
            currency: currency.value.trim().toUpperCase() || 'EUR',
            benchmark_symbol: bench.value.trim(),
          });
        };
        for (const input of [symbol, exchange, currency, bench]) {
          input.addEventListener('change', async () => {
            try { await persist(); App.toast('Correspondance enregistrée', 'success'); }
            catch (e) { App.toast(e.message, 'error'); }
          });
        }
        tbody.append(App.h('tr', {},
          App.h('td', {}, App.h('code', {}, ticker)),
          App.h('td', {}, symbol),
          App.h('td', {}, exchange),
          App.h('td', {}, currency),
          App.h('td', {}, bench),
          App.h('td', { class: 'right' },
            sec.symbol ? App.h('span', { class: 'pill ok' }, 'mappé')
              : App.h('span', { class: 'pill warn' }, 'à faire'))));
      }
    };
    renderSecurities();

    const statusLine = App.h('div', { class: 'metric-list' });
    const renderStatus = (s) => {
      App.clear(statusLine);
      const rows = [
        ['État', s.active ? 'activé' : 'désactivé (aucun appel réseau)'],
        ['Clé API', s.cle_configuree ? 'configurée' : 'absente'],
        ['Dernier rafraîchissement', s.dernier_refresh
          ? App.fmt.dateTime(s.dernier_refresh) : 'jamais'],
        ['Cours en cache', String(s.nb_cours_en_cache)],
        ['Tickers sans correspondance', s.tickers_non_mappes.length
          ? s.tickers_non_mappes.join(', ') : 'aucun'],
      ];
      for (const [l, v] of rows) {
        statusLine.append(App.h('div', { class: 'metric-row' },
          App.h('span', { class: 'm-label' }, l), App.h('span', { class: 'm-value' }, v)));
      }
    };
    renderStatus(status);

    const refreshNow = async (btn) => {
      btn.classList.add('busy');
      try {
        const res = await App.api.post('/api/market/refresh');
        App.toast(`${res.ok} cours récupéré(s), ${res.ko} en échec`,
          res.ko ? 'error' : 'success');
        renderStatus(await App.api.get('/api/market/status'));
        await App.refreshAll();
      } catch (e) { App.toast(e.message, 'error'); }
      btn.classList.remove('busy');
    };

    return App.h('div', {},
      App.h('div', { class: 'callout' },
        App.h('strong', {}, 'Ceci fait sortir des données de votre machine.'),
        ' Une fois activés, les symboles interrogés et votre clé API sont envoyés '
        + 'au fournisseur à chaque rafraîchissement. Vos montants, quantités et '
        + 'transactions, eux, ne sortent jamais — mais une liste de tickers '
        + 'renseigne déjà sur la composition de votre portefeuille. '
        + 'La clé est stockée en clair dans patrimoine.db.'),

      App.h('div', { class: 'form-grid', style: 'margin-top:16px' },
        App.field('Activer les cours de marché', enabled),
        App.field('Fournisseur', providerSel),
        App.field('Clé API', keyIn, {
          hint: cleEnPlace
            ? 'gratuite sur twelvedata.com — une clé est déjà enregistrée, '
              + 'laissez le champ vide pour la conserver'
            : 'gratuite sur twelvedata.com',
        }),
        App.field('Rafraîchir au lancement', autoIn),
        App.field('Durée de vie du cache (heures)', ttlIn)),
      App.h('div', { class: 'actions', style: 'margin-top:12px' },
        App.h('button', { class: 'btn primary', onclick: save }, 'Enregistrer'),
        App.h('button', {
          class: 'btn', onclick: (e) => refreshNow(e.target),
        }, 'Rafraîchir les cours maintenant'),
        cleEnPlace ? App.h('button', { class: 'btn', onclick: oublierCle },
          'Oublier la clé') : null),

      App.h('div', { class: 'section-title' }, 'Vérifier la couverture d’un symbole'),
      App.h('p', { class: 'hint' },
        'À faire avant de vous fier aux valorisations : les offres gratuites couvrent '
        + 'bien mieux les valeurs américaines que les ETF Euronext éligibles PEA.'),
      App.h('div', { class: 'form-grid', style: 'margin-top:10px' },
        App.field('Symbole ou ISIN', testSym),
        App.field('Place (facultatif)', testEx),
        App.h('div', { class: 'field' }, App.h('label', {}, ' '),
          App.h('button', { class: 'btn', onclick: runTest }, 'Tester'))),
      App.h('div', { style: 'margin-top:10px' }, testOut),

      App.h('div', { class: 'section-title' }, 'Correspondance de vos lignes'),
      App.note('À quoi sert cet écran',
        'Vos mouvements portent souvent un ISIN, que le fournisseur n’accepte pas tel '
        + 'quel. Depuis la fiche d’un actif, choisir un support par la recherche '
        + 'remplit cette table toute seule. Cet écran sert à corriger, ou à saisir '
        + 'un symbole que la recherche ne trouve pas. L’indice de référence sert à '
        + 'la comparaison de performance.'),
      App.h('div', { class: 'table-wrap scroll-y', style: 'margin-top:10px' },
        App.h('table', { class: 'table' },
          App.h('thead', {}, App.h('tr', {},
            App.h('th', {}, 'Ticker / ISIN'), App.h('th', {}, 'Symbole fournisseur'),
            App.h('th', {}, 'Place'), App.h('th', {}, 'Devise'),
            App.h('th', {}, 'Indice de réf.'), App.h('th', { class: 'right' }, 'État'))),
          tbody)),

      App.h('div', { class: 'section-title' }, 'État'),
      statusLine,
      App.h('p', { class: 'hint', style: 'margin-top:12px' },
        'Livrets et dépôts à terme n’utilisent pas d’API : renseignez leur taux annuel '
        + 'dans la fiche de l’actif, les intérêts sont calculés par quinzaines. '
        + 'L’immobilier se réévalue par indice INSEE ou par un taux annuel saisi.'));
  },

  /* ---------- types d'actifs personnalisés ---------- */
  panelAssetTypes(settings) {
    const customs = (settings.types_actifs_custom || []).map(
      (c) => (typeof c === 'string' ? { type: c, famille: 'Autre' } : c));
    const list = App.h('div', { class: 'actions' });
    const render = () => {
      App.clear(list);
      if (!customs.length) list.append(App.h('span', { class: 'muted' }, 'Aucun type personnalisé.'));
      customs.forEach((c, i) => {
        list.append(App.h('span', { class: 'pill accent' }, `${c.type} (${c.famille})`, ' ',
          App.h('a', {
            href: '#', style: 'color:var(--red);text-decoration:none',
            onclick: async (e) => {
              e.preventDefault();
              customs.splice(i, 1);
              render();
              await App.settings.save({ types_actifs_custom: customs }, 'Type supprimé');
            },
          }, '×')));
      });
    };
    render();

    const typeIn = App.input('type', { placeholder: 'ex : Forêt, Montre, Parts de SARL' });
    const familleIn = App.select('famille',
      ['Liquidités', 'Épargne réglementée', 'Marchés financiers', 'Immobilier',
        'Crypto', 'Biens', 'Autre'], 'Autre');
    const add = async () => {
      const t = typeIn.value.trim();
      if (!t) return App.toast('Nom du type requis', 'error');
      customs.push({ type: t, famille: familleIn.value });
      typeIn.value = '';
      render();
      await App.settings.save({ types_actifs_custom: customs }, 'Type ajouté');
    };

    return App.h('div', {},
      App.h('p', { class: 'hint' },
        'Un type personnalisé n’impose aucun champ : libellé, date, valeur et historique suffisent. '
        + 'La famille sert uniquement à regrouper l’affichage.'),
      App.h('div', { style: 'margin:12px 0' }, list),
      App.h('div', { class: 'form-grid' },
        App.field('Nom du type', typeIn),
        App.field('Famille de regroupement', familleIn)),
      App.h('div', { class: 'actions', style: 'margin-top:12px' },
        App.h('button', { class: 'btn primary', onclick: add }, 'Ajouter')));
  },
};
