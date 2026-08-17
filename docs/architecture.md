# Architecture

Comment c'est construit, et pourquoi ainsi.

[← Retour au README](../README.md)

---


## Stack

| Couche | Choix | Pourquoi |
|---|---|---|
| Backend | Python 3 + Flask | seule dépendance externe |
| Stockage | SQLite (stdlib) | fichier unique, pas de serveur |
| Frontend | HTML + JS vanilla + Chart.js | aucun build, pas de npm |
| Graphiques | Chart.js **vendu localement** (`app/static/vendor/`) | l'app fonctionne hors ligne, sans CDN |
| TRI (XIRR) | bissection maison (`app/finance.py`) | évite d'imposer SciPy (~90 Mo) pour 30 lignes de code, testé contre des valeurs de référence |
| Cours de marché | `urllib` (stdlib) | pas de `requests` à ajouter pour trois appels HTTP |
| Serveur | waitress | serveur de production, multi-thread ; celui de Flask est prévu pour le développement |
| Fenêtre | pywebview (WebView2) | le moteur d'Edge est déjà sur la machine : une fenêtre applicative pour ~1 Mo |
| Exécutable | PyInstaller `--onefile --noconsole` | un seul fichier, aucune fenêtre console |
| Installateur | Inno Setup | raccourcis, versions, désinstallation propre |


## Structure

```
run.py                    lancement : serveur + fenêtre native
build_exe.py              icône, exe et installateur
installer.iss             recette Inno Setup
app/
  __init__.py             fabrique Flask
  version.py              numéro de version — source unique
  paths.py                chemins ressources / données (normal, portable, installé)
  schema.sql              les 6 tables du cahier des charges + securities et quotes
  db.py                   connexion, settings, types d'actifs
  finance.py              calculs purs (amortissement, PRU, XIRR, livrets)
  market.py               cours de marché — SEUL module qui fait du réseau
  importer.py             parsing des relevés, dédup, classification
  backup.py               sauvegardes CSV, rotation, restauration
  advisor.py              observations factuelles (plafonds, ratios, ecarts)
  services.py             couche métier (portefeuille, flux, archive, métriques)
  routes/                 routes HTTP, un module par domaine
    _blueprint.py         le blueprint, seul (casse le cycle d'import)
    _helpers.py           conversions partagées (body, as_float, fail…)
    page.py               page unique et métadonnées
    transactions.py       dépenses, revenus, virements
    assets.py             actifs
    movements.py          apports, retraits, valorisations
    positions.py          lignes détenues (PEA, cryptos)
    liabilities.py        prêts et dettes
    bank_imports.py       import de relevés
    analytics.py          synthèse, historique, conseils
    quotes.py             cours de marché
    settings.py           paramètres et règles
    backups.py            sauvegardes CSV
    transfers.py          virements internes
  templates/index.html    page unique
  static/
    splash.html           écran d'attente, autonome (affiché serveur éteint)
    css/tokens.css        design system — fait autorité sur les couleurs
    css/app.css           mise en forme et animations
    img/                  logo, icône applicative
    js/, vendor/
tests/                    149 tests (unittest, sans dépendance, sans réseau)
```

Un seul blueprint pour toute l'API : le découpage de `routes/` sert la lecture,
pas l'adressage — les URL n'ont pas bougé. Importer un module suffit à
enregistrer ses routes, d'où la liste explicite dans `routes/__init__.py`.

```bash
python -m unittest discover -s tests -t .
```


## Calculs

Mensualité à taux fixe :

```
taux_mensuel = taux_annuel / 12 / 100
mensualite   = capital * taux_mensuel / (1 - (1 + taux_mensuel)^(-duree_mois))
```

**Capital restant dû** : tableau d'amortissement recalculé depuis `date_debut`
jusqu'à la date demandée, jamais stocké. La dernière échéance solde exactement
le capital (absorbe les arrondis).

**Patrimoine net** = Σ valeurs des actifs − Σ capitaux restants dus. Un bien
financé n'est jamais compté brut.

**PRU** = Σ(quantité × prix) / Σ(quantité) sur les achats. Une vente ne modifie
pas le PRU : elle réduit le prix de revient total au prorata (convention
française).

**TRI (XIRR)** : versements en négatif, valeur actuelle en positif à la date du
jour, racine de la VAN par bissection. Renvoie `—` si les flux ne changent pas
de signe.

**Rendement locatif — deux mesures, pas une.** Le remboursement du capital n'est
pas une charge : il éteint une dette et vous revient. Le soustraire fait
paraître le bien moins rentable qu'il ne l'est, et l'écart n'est pas
anecdotique — sur le studio de la base de démo, **−2,71 % après mensualités
contre +0,36 % hors capital**.

- *Rendement après mensualités* = (loyers − charges − mensualités totales) / valeur
- *Rendement net hors capital* = (loyers − charges − intérêts − assurance) / valeur

Le premier dit ce qui sort réellement de votre poche, le second mesure la
performance du bien lui-même. Les deux sur 12 mois glissants ; les loyers et
charges sont les transactions rattachées au bien via `asset_id`, les intérêts
sont lus dans l'échéancier du prêt lié.

**Taux d'épargne** = versements sur les actifs (hors compte courant) / revenus du
mois. Un virement d'épargne saisi en transaction n'est compté que s'il n'est pas
déjà rattaché à un actif, pour éviter le double comptage. Les catégories listées
dans `categories_non_depense` (par défaut « Epargne/Investissement ») ne sont pas
comptées comme des dépenses.


## Le coût du « tout recalculé », et comment il est tenu

Le choix de ne rien figer a un prix : l'archive mensuelle rejoue le calcul du
patrimoine pour chaque mois depuis le premier mouvement. Sans précaution, les
mêmes actifs, mouvements et tableaux d'amortissement étaient relus et recalculés
une fois par mois affiché — un tableau d'amortissement, c'est 240 échéances par
prêt, refaites vingt fois.

Un **cache de portée strictement locale** est passé le long du calcul : les
données indépendantes de la date (actifs, mouvements, prêts, échéanciers,
correspondances de symboles) sont lues une seule fois, de même que les
transactions groupées par mois. Il ne survit pas à l'appel, donc il ne peut
jamais être périmé — la règle « tout est recalculé » reste entière.

`/api/history` est passé de **660 ms à 180 ms**, `/api/overview` de 198 à 50 ms.


## Aucun snapshot figé

Il n'existe ni clôture de mois ni copie figée. L'archive mensuelle, la courbe de
patrimoine et toutes les métriques sont des requêtes filtrées par date sur les
données vivantes. Corriger une transaction de mars se répercute immédiatement
partout (c'est vérifié par un test).

**Conséquence à connaître** : la valeur passée d'un actif est reconstituée depuis
ses données datées — valeur d'acquisition, puis mouvements, puis la dernière
`valorisation` enregistrée. Le champ *valeur actuelle* saisi à la main ne vaut
que pour aujourd'hui. Un actif dont vous avez seulement mis à jour la valeur
actuelle affichera donc sa valeur d'acquisition dans le passé, puis un saut au
dernier point. Pour une courbe fidèle, utilisez le bouton **Valoriser** sur
chaque actif (une fois par mois par exemple) : chaque valorisation est un point
daté qui construit l'historique réel.

Les cours de marché atténuent ce problème pour les titres et la crypto, et les
livrets se calculent désormais tout seuls — mais la remarque reste entière pour
les biens valorisés à la main.


## Modèle de données

Les 6 tables du cahier des charges, plus quelques champs de confort :

- `transactions` — `dedup_hash` (index unique partiel) pour la déduplication.
- `assets` — `archived` pour sortir un actif des totaux sans perdre son
  historique. `metadata` en JSON, aucun champ imposé pour le type `Custom`.
- `asset_movements` — `ticker` en plus de quantité/prix, pour le PRU par ligne.
  Type `valorisation` : le `montant` est la valeur totale de l'actif à cette date.
- `liabilities` — `label` et `assurance_mensuelle` (l'assurance change le montant
  réellement prélevé, donc la détection automatique des échéances).
- `imports`, `rules`, `settings` — conformes au cahier des charges.

Deux tables ajoutées pour la valorisation en direct :

- `securities` — correspondance `asset_movements.ticker` (souvent un ISIN) →
  symbole du fournisseur, place, devise, indice de référence, et `kind`
  (`titre` ou `crypto`, qui décide du fournisseur interrogé). Alimentée
  automatiquement quand vous choisissez un support par la recherche.
- `quotes` — cache des cours, taux de change (`FX:USDEUR`), cryptos
  (`COIN:<id>`) et indices INSEE (`INSEE:<idbank>`), tous datés.

Les métadonnées d'actif reconnues pour la valorisation : `taux_annuel`
(livrets), `coingecko_id` et `quantite` (crypto), `indice_insee` ou
`taux_revalorisation_annuel` (immobilier). Pour les titres et les cryptos, les
quantités viennent des positions, pas des métadonnées.

Les types d'actifs prédéfinis sont dans `app/db.py` (`ASSET_TYPES`), chacun
rattaché à une famille pour les regroupements. Des types supplémentaires
s'ajoutent depuis les paramètres, sans toucher au code.


## Reste à faire

- **Vérifier la couverture Euronext** avec votre clé Twelve Data (voir plus
  haut). C'est le seul point du lot « cours de marché » qui n'a pas pu être
  validé sans elle.
- **Renseigner les idbank INSEE** des indices immobiliers. Le code sait lire une
  série SDMX et la mettre en cache, mais aucun identifiant n'est fourni par
  défaut : les inventer aurait été pire que de laisser le champ vide. En
  attendant, le taux de revalorisation annuel manuel fait le travail.
- **Historique de cours** : le cache accumule les clôtures au fil des
  rafraîchissements. Charger un historique complet à la première utilisation
  permettrait de reconstruire la courbe de patrimoine passée avec de vrais
  cours plutôt qu'avec les valorisations saisies.
