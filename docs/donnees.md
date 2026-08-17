# Données

Faire entrer ses données, et ce que l'application en fait.

[← Retour au README](../README.md)

---


## Import de relevés

Coller le contenu dans *Dépenses → Importer un relevé*. Le séparateur (`,` `;`
tabulation `|`), les colonnes (FR/EN, montant unique ou débit/crédit séparés) et
le format des montants (`1 234,56` / `1,234.56` / `(12,00)`) sont détectés
automatiquement.

- **Revolut** : export CSV natif, collé tel quel. Les lignes `REVERTED`,
  `DECLINED` ou `PENDING` sont écartées, les frais déduits du montant.
- **LCL** : pas de parsing PDF dans l'app. Faites extraire le relevé en texte
  tabulé (une conversation Claude suffit), puis collez-le au même endroit.
- **Trade Republic / courtier** : *Patrimoine → fiche du compte → Mes supports →
  Importer un relevé*. Voir la section dédiée ci-dessous.

Chaque ligne reçoit un hash `date + montant + libellé normalisé`. Les doublons
sont signalés et décochés avant confirmation ; un index unique en base bloque
l'insertion même si on force.


## Déclarer son patrimoine existant

*Patrimoine → **+ Ajouter mes produits*** ouvre une liste des placements
courants — Livret A, LDDS, LEP, Livret Jeune, PEL, CEL, dépôt à terme,
assurance vie, PEA, PER, compte-titres, SCPI, compte courant, crypto, bien
immobilier, véhicule. Vous n'inscrivez que les montants des produits que vous
détenez, le total se met à jour en bas, et tout est créé d'un coup.

Deux partis pris à connaître :

- **La plus-value démarre à zéro.** Le montant investi est posé égal au montant
  déclaré. Pour un livret constitué sur dix ans, l'application ne connaît pas
  l'historique des versements : afficher une performance reviendrait à
  l'inventer. Vous pouvez saisir le vrai montant investi ensuite, dans la fiche
  de l'actif.
- **Le taux est laissé vide.** Les taux réglementés changent, et un taux faux
  produirait des intérêts faux en silence. À vous de le renseigner : c'est lui
  qui fait vivre le montant. Sans taux, un livret reste figé à la valeur saisie
  — le bandeau vous le signale.

Les intérêts de livret et la réévaluation immobilière sont des **calculs
purement locaux** : ils fonctionnent sans activer les cours de marché, et sans
le moindre accès réseau.

Pour un actif qui demande plus de détail (métadonnées, mouvements, ISIN), le
bouton **« + Actif détaillé »** ouvre le formulaire complet. Il demande d'abord
la valeur d'aujourd'hui ; le montant investi y est facultatif, et vaut la valeur
actuelle s'il est laissé vide.


## Relevés de courtier : les quantités se mettent à jour toutes seules

*Patrimoine → fiche du compte → **Mes supports** → **Importer un relevé***.

Le relevé est lu ligne par ligne (date, ticker ou ISIN, quantité, prix
unitaire, achat ou vente) et devient des mouvements. **Tout le reste en
découle** : la quantité détenue de chaque ETF, le PRU, la valeur de marché et
le TRI sont recalculés depuis ces mouvements à chaque affichage — jamais
stockés, donc jamais périmés. Un achat de 3 parts importé fait passer la ligne
de 72,99 à 75,99 parts sans rien saisir d'autre. Une vente réduit la quantité
sans toucher au PRU (convention française).

Deux protections, ajoutées parce que la mise à jour automatique n'a de valeur
que si elle est fiable :

**Anti-doublon.** Un relevé se réimporte presque toujours avec un chevauchement
de période — celui de juin reprend les opérations de fin mai. Sans empreinte,
les quantités doubleraient **en silence**, et une quantité fausse fausse toute
la valorisation. Chaque mouvement porte donc une empreinte
`actif + date + ticker + quantité + montant` : les lignes déjà présentes
arrivent signalées et décochées, et un index unique bloque l'insertion même si
on force.

**Amorçage du symbole de cotation.** L'import écrivait un ticker brut, sans
créer la correspondance qui permet de coter la ligne : les supports importés
restaient non cotables, et tout le compte retombait sur sa valeur saisie.
L'import crée désormais la correspondance manquante en reprenant le ticker du
relevé, signale lesquelles sont à vérifier, et **n'écrase jamais** un symbole
que vous avez corrigé à la main.


## Virements entre vos propres comptes

Un virement LCL → Revolut **n'est pas une dépense**. Il apparaît deux fois : en
débit sur le relevé LCL, en crédit sur le relevé Revolut. Sans traitement, le
même euro gonflerait à la fois les dépenses et les revenus, et fausserait la
répartition par catégorie comme le taux d'épargne.

Ces lignes vont dans la catégorie **« Transfert interne »**, listée dans le
réglage `categories_transfert`. Elles sont neutralisées **des deux côtés** :
exclues des dépenses, des revenus, de la répartition par catégorie et de
l'épargne. Le montant déplacé reste affiché sous le total des dépenses
(*« hors 650 € de virements internes »*), pour que rien ne disparaisse
silencieusement.

À ne pas confondre avec `categories_non_depense` (par défaut
« Epargne/Investissement ») : un virement vers un livret n'est pas une dépense
non plus, mais il **compte comme épargne**. Les deux réglages se règlent dans
*Paramètres → Catégories*.

### Deux mécanismes de détection

**1. Mots-clés, à l'import.** `mots_cles_transfert` (par défaut `revolut`,
`virement interne`, `topup`, `transfert compte`…) est cherché dans le libellé,
sans casse ni accents. Attrape les deux sens : le `VIR SEPA VERS REVOLUT` côté
LCL comme le `Top-Up by card` côté Revolut. Vos règles de classification restent
prioritaires.

**2. Rapprochement par paires**, proposé **juste après un import**. Pour les
libellés opaques que les mots-clés ne peuvent pas attraper (`VIR M SAMUEL 88213`
→ `Payment from SAMUEL`), on apparie un débit et un crédit de même montant, à
quelques jours d'écart. Les paires sont proposées avec leur écart de date, à
cocher avant application — rien n'est reclassé sans votre accord.

Il y avait un bouton permanent pour cela ; il a été retiré. Un virement entre
vos comptes n'apparaît qu'une fois les **deux** relevés importés : le seul
moment où la question se pose est donc la fin d'un import. Le reste du temps,
le bouton n'était qu'un encombrement qu'on ne pensait pas à cliquer.
S'il n'y a rien à proposer, rien ne s'affiche.

> **Garde-fou contre les faux positifs** : les deux lignes doivent provenir
> d'**imports différents**. Deux mouvements du même relevé sont sur le même
> compte — ce ne peut pas être un virement entre comptes. Un salaire de 500 € et
> un loyer de 500 € du même relevé ne seront donc jamais appariés. Corollaire
> assumé : deux saisies manuelles ne sont jamais appariées non plus.

La tolérance de date se règle via `transfert_jours_tolerance` (4 jours par
défaut).


## Classification

Ordre d'application :

1. **Règles utilisateur** (`rules`) — sous-chaîne cherchée dans le libellé, sans
   casse ni accents, la plus petite priorité gagne. C'est le seul moyen de
   reconnaître un salaire, l'argent des parents ou un loyer : l'app ne peut pas
   les deviner.
2. **Remboursement de prêt** — déduit sans règle : si le débit correspond à la
   mensualité calculée d'un prêt actif (± 2 € par défaut) et tombe à moins de
   6 jours de l'échéance théorique, la ligne est classée « Remboursement pret »
   et rattachée au prêt (`liability_id`).
3. **Virement interne** — voir la section précédente.
4. **Mots-clés intégrés** — filet de sécurité pour les enseignes courantes.
5. Sinon « Non categorise ».

Les tolérances sont dans les paramètres (`tolerance_mensualite`,
`tolerance_jours_echeance`). Le bouton *Appliquer aux transactions non
catégorisées* rejoue les règles sur l'existant.


## Valorisation en direct (cours de marché)

**Désactivé par défaut.** Tant que le réglage n'est pas activé dans
*Paramètres → Cours de marché*, l'application ne fait **aucun** appel réseau et
se comporte exactement comme avant.

### Ce qui sort de la machine

Une fois activé, à chaque rafraîchissement : **les symboles interrogés et votre
clé API** partent chez le fournisseur. Vos montants, quantités et transactions
ne sortent jamais — mais une liste de tickers renseigne déjà sur la composition
du portefeuille. La clé API est stockée **en clair** dans `patrimoine.db`.

Trois règles tenues par le code :

1. `market_enabled` est faux par défaut.
2. **Aucun appel HTTP dans un chemin de lecture.** Seuls `POST
   /api/market/refresh`, `/api/market/test`, `/api/market/index/refresh` et la
   comparaison d'indice sortent sur le réseau. `portfolio()`, `metrics()` et
   l'archive mensuelle ne lisent que le cache local — un test le vérifie en
   comptant les appels d'un fournisseur espion.
3. Cours indisponible ⇒ repli silencieux sur la valeur saisie. Hors ligne,
   l'application reste pleinement utilisable avec les derniers cours en cache.

### Comment chaque actif est valorisé

| Type | Source | Détail |
|---|---|---|
| PEA, CTO, AV, PER | Twelve Data | Σ quantité × cours, ligne par ligne, converti en EUR |
| Crypto | CoinGecko | quantité × cours, coté directement en EUR, sans clé |
| Livret, LDDS, LEP, Livret Jeune, PEL, CEL, dépôt à terme | calcul local | intérêts par quinzaines au taux saisi, **sans réseau ni réglage** |
| Immobilier, SCPI | indice INSEE | réévaluation du prix d'acquisition, ou taux annuel manuel |
| Tout le reste | saisie manuelle | inchangé |

Chaque ligne de la vue Patrimoine affiche d'où vient sa valeur : *cours de
marché*, *intérêts calculés*, *estimation indicielle*, ou rien si elle est
saisie. La valeur saisie reste consultable en infobulle.

**Si une seule ligne d'un compte-titres n'est pas cotée, tout le compte retombe
sur la valeur saisie** — mieux vaut une valeur manuelle assumée qu'un total
partiel présenté comme complet.

L'estimation immobilière applique l'évolution d'un indice à votre prix
d'acquisition. C'est un ordre de grandeur, **pas une expertise** : aucune API
ne cote un bien précis.

### Choisir ses supports et ses cryptos

La fiche d'un PEA, CTO, assurance vie, PER ou portefeuille crypto ouvre sur un
onglet **« Mes supports »** (ou **« Mes cryptos »**) : la liste de vos lignes
avec quantité, PRU, cours du jour, valeur et gain, et un bouton pour en ajouter.

**Ajouter une ligne passe par une recherche chez le fournisseur** — Twelve Data
pour les titres, CoinGecko pour les cryptos. Vous tapez « MSCI World », « CW8 »
ou « ethereum », vous choisissez dans la liste, vous saisissez la quantité. Deux
raisons à ce choix plutôt qu'un catalogue livré avec l'application :

- un ISIN ou un ticker recopié de mémoire serait faux, et produirait une
  valorisation fausse **en silence** ;
- le symbole retenu vient de la source qui servira ensuite à le coter, donc il
  est coté par construction.

Choisir un instrument **crée aussi sa correspondance de cotation**. C'est le
point qui change tout par rapport à la version précédente : plus besoin d'aller
mapper l'ISIN à la main dans les paramètres. L'écran de correspondance y reste,
pour corriger ou pour saisir un symbole que la recherche ne trouve pas.

Un portefeuille crypto peut désormais contenir **plusieurs pièces** (Bitcoin,
Ethereum… dans le même actif), là où l'ancien modèle se limitait à une seule.
Les cryptos saisies avant ce changement continuent de fonctionner.

Le bouton « Saisir un symbole à la main » reste disponible quand vous êtes hors
ligne ou sans clé API.

### Vérifier la couverture avant de s'y fier

C'est le point de vigilance du cahier des charges : les offres gratuites
couvrent bien mieux les valeurs américaines que les ETF Euronext éligibles PEA.
*Paramètres → Cours de marché → Vérifier la couverture d'un symbole* teste un
symbole à la fois, en symbole court puis en ISIN. **À faire pour chacune de vos
lignes avant de vous fier aux montants affichés.**

> Cette vérification n'a pas pu être faite pendant le développement : elle
> demande votre clé API. Si Twelve Data ne cote pas vos ETF Euronext, le repli
> sérieux est Yahoo Finance (excellente couverture `.PA`, sans clé, mais API non
> officielle) — l'abstraction `Provider` de `app/market.py` rend le basculement
> peu coûteux.

Vos mouvements portent souvent un ISIN, que le fournisseur n'accepte pas tel
quel : la table `securities` fait la correspondance ISIN → symbole, place,
devise, et porte l'indice de référence de la ligne.

### Rafraîchissement

Automatique au lancement si le cache dépasse 24 h (réglable), et à la demande
via *Rafraîchir les cours*. L'interface s'affiche d'abord depuis le cache, les
cours arrivent ensuite : jamais d'attente réseau au démarrage. Une pastille
indique *cours à jour* ou *cours périmés*.

Le cache `quotes` est une **observation de marché datée**, pas une valeur
dérivée figée : il ne contredit pas la règle « aucun snapshot », il l'alimente.
En accumulant des clôtures datées, il permettra à terme de valoriser le
portefeuille à une date passée avec de vrais cours.

### Comparaison à l'indice de référence

Par ligne, à la demande (les séries historiques coûtent plus de quota que les
cours du jour) : performance de la ligne, performance de l'indice, écart, et les
deux courbes rebasées à 100 depuis le premier achat.
