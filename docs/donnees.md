# Données

Faire entrer ses données, et ce que l'application en fait.

[← Retour au README](../README.md)

---


## Import de relevés

Déposez le fichier dans *Dépenses → Ajouter un relevé*, ou cliquez pour le
choisir. Il est lu, puis **analysé sans second clic** : il n'y a rien à
demander de plus. Le collage reste possible dans le champ en dessous, pour un
extrait pris à la main.

Le séparateur (`,` `;` tabulation `|`), les colonnes (FR/EN, montant unique ou
débit/crédit séparés) et le format des montants (`1 234,56` / `1,234.56` /
`(12,00)`) sont détectés automatiquement. **Il n'y a plus de menu « Source »** :
il ne servait qu'à étiqueter le journal des imports, et le nom du fichier le dit
mieux qu'une banque choisie dans une liste de quatre.

- **Revolut** : export CSV natif, déposé tel quel. Les lignes `REVERTED`,
  `DECLINED` ou `PENDING` sont écartées, les frais déduits du montant.
- **LCL et relevés PDF** : le PDF téléchargé depuis votre espace client se
  dépose directement. Plus de conversion préalable. Un PDF **scanné** ne
  contient qu'une image et reste illisible — l'application le dit plutôt que de
  renvoyer une liste vide.
- **Trade Republic / courtier** : *Patrimoine → fiche du compte → Mes supports →
  Importer un relevé*, même zone de dépôt. Voir la section dédiée ci-dessous.

### Relevés sans séparateur

Un relevé imprimé ou extrait d'un PDF n'a aucun séparateur : ses colonnes sont
alignées à l'espace. `csv.reader` n'y voyait qu'une colonne par ligne et
renvoyait zéro transaction. Une seconde lecture prend le relais, ligne à ligne :
date en tête, montant en fin.

**Le sens du montant vient de sa colonne, pas de son signe.** Un relevé imprimé
sépare débit et crédit en deux colonnes et n'écrit jamais de moins. Les montants
y sont alignés à droite : c'est donc la position de **fin** qui est stable, pas
celle du début, et le plus grand écart entre deux fins sépare les deux colonnes.
À défaut de seconde colonne, la ligne est lue comme un débit — et l'application
le dit, plutôt que d'inventer un sens.

Les lignes de solde (« solde précédent », « nouveau solde », « report ») portent
une date et un montant comme les autres : seul leur libellé les distingue. Elles
sont écartées, sans quoi tous les totaux seraient faux.

La lecture délimitée garde la priorité quand elle aboutit vraiment : c'est elle
qui distingue débit et crédit sans avoir à deviner. Deux signes la déclarent en
échec : aucune ligne reconnue, ou des libellés qui commencent eux-mêmes par une
date — preuve que le découpage n'a rien découpé et que la ligne entière a atterri
dans une seule cellule.

Le fichier déposé est converti en texte **sur votre machine** (`POST
/api/imports/text`, aucun appel réseau) et le texte extrait revient dans le
champ, visible et modifiable : l'extraction d'un PDF est imparfaite par nature,
la cacher reviendrait à demander une confiance aveugle.

Chaque ligne reçoit un hash `date + montant + libellé normalisé`. Les doublons
sont signalés et décochés avant confirmation ; un index unique en base bloque
l'insertion même si on force.


## Les frais, rattachés à ce qui les cause

Il n'y avait qu'un réglage **global** : `frais_annuels`, deux montants tapés à
la main pour tout le patrimoine. Rien ne rattachait un courtage au PEA qui
l'avait payé, ni un frais de réseau au portefeuille crypto. Le total mélangeait
des coûts sans rapport, et « combien me coûte ce produit » restait sans réponse.

### Deux écritures, parce que l'argent ne circule pas pareil

| | Effet sur la valeur | Effet sur le capital investi |
|---|---|---|
| Colonne `frais` sur un versement / retrait | aucun — cet argent n'est jamais entré dans le produit | **ajouté** |
| Mouvement de type `frais` | **retiré** — l'argent sort du produit | aucun |

- **Un courtage** part chez le courtier : il ne rentre pas dans le produit, mais
  il gonfle votre prix de revient. Achat 1 000 € + 5 € → valeur 1 000, investi
  1 005, plus-value −5.
- **Des frais de gestion** sortent du produit : sa valeur baisse. Investi
  inchangé, plus-value −12.

Les deux baissent la plus-value du montant du frais, ce qui est le résultat
attendu. Ce sont deux écritures, pas deux conventions.

**Le piège** : compter le montant d'un mouvement `frais` dans
`invested_amount` annulerait son effet et le ferait disparaître des comptes.
Un test le garde.

### Le courtage entre dans le PRU

C'est la convention française, celle d'une déclaration fiscale — et celle que
`pru_par_ligne` tenait déjà pour les ventes. Sans lui, le PRU affiché serait
plus bas que celui de votre relevé de courtier.

### Des frais prélevés en nature

Les frais de réseau d'un envoi crypto sont prélevés **en jetons**. Un mouvement
`frais` qui porte un ticker et une quantité réduit donc la quantité détenue,
comme une cession — le PRU ne bouge pas, le prix de revient baisse au prorata.

Un frais **en euros**, lui, ne nomme aucune ligne : il ne doit pas en fabriquer
une. Sans ce garde-fou, des frais de gestion créaient une ligne « (sans
ticker) » à zéro part dans la liste des positions.

### Un frais doit se voir

Pour la date du jour, `asset_value_at` rend `valeur_actuelle` telle quelle sans
regarder les mouvements : le montant déclaré en dernier fait autorité. Un frais
enregistré ne changeait donc **rien à l'écran**. Enregistrer des frais prélevés
diminue désormais le solde déclaré du produit — un frais qu'on ne voit pas n'est
pas comptabilisé.

### Un échange n'est ni un achat ni une vente

Sur une plateforme, échanger de l'ETH contre du SOL ne fait entrer ni sortir le
moindre euro : **deux lignes changent de taille**. L'opération n'existait pas —
il fallait la simuler par une vente puis un achat — et le frais de la plateforme
n'appartenait proprement ni à l'une ni à l'autre.

Le bouton **« ⇄ Échanger »** de chaque ligne écrit **deux mouvements de même
montant, en sens inverse**. Le capital investi ne bouge donc pas : c'est le même
argent qui change de forme. Seul le frais l'augmente.

- Le prix de revient de la ligne **cédée** ne change pas : seule la part sortie
  en est retirée, au prorata (convention française).
- Celui de la ligne **reçue** intègre le frais, comme un courtage d'achat.

Si la plateforme prélève sa commission **en jetons**, il suffit d'indiquer la
quantité réellement reçue : elle est déjà nette. Le champ « frais » sert alors à
ce qui a été débité en euros.

### Un frais est porté par le côté qui peut le porter

Une **valeur de marché** est recalculée à chaque affichage depuis les cours du
jour : elle ne garde **aucune trace** d'un prélèvement passé. Enregistrer 25 €
de frais de plateforme sur un portefeuille crypto ne changeait donc rien — ni la
valeur, ni la plus-value. Le frais était écrit et sans effet.

| Valeur du produit | Qui porte le frais en euros |
|---|---|
| Recalculée au cours du marché ou par indice | le **capital investi** |
| Déclarée par vous, ou reconstituée depuis les mouvements | la **valeur** |

Les deux font baisser la plus-value du montant du frais. Ce qui les sépare est
la capacité de la valeur à en garder trace.

**Un solde re-déclaré contient déjà les frais qui l'ont précédé** : les porter
une seconde fois les ferait payer deux fois. Le partage se fait donc sur l'ordre
de **saisie**, pas sur la date de l'opération — un frais enregistré après votre
dernière déclaration est une information nouvelle, même s'il porte une date
passée. `created_at` ne descend pas sous la seconde : le `rowid`, strictement
croissant, départage deux écritures rapprochées.

Un frais prélevé **en jetons** n'entre pas dans ce partage : il nomme une ligne,
en réduit la quantité, et fait donc baisser la valeur tout seul.

### Le TER, qui n'est jamais prélevé

Un TER n'est pas une transaction : il est **intégré au cours** du support et ne
sort d'aucun compte. Aucun mouvement ne peut le porter.

Il reste donc une **estimation**, saisie en pourcentage sur la fiche du produit
(`ter_annuel` dans ses `metadata`), appliquée à sa valeur. Elle est rendue à
part — `ter_estime` — pour ne jamais être confondue avec les frais réellement
payés.

### Ce que devient l'ancien réglage

Il ne se saisit plus. Ce qu'il portait déjà n'est pas perdu pour autant : il est
compté sous le nom **« Non rattachés (ancien réglage) »**. On ne sait pas à quel
produit ces montants appartenaient — c'est précisément le défaut qu'on corrige —
et leur en inventer un serait pire que de le dire.

`services.frais_par_produit(annee)` rend le détail, `metrics.frais_annuels` le
total. Il est désormais **calculé**, là où il était tapé.


## Vendre, retirer, réduire une quantité

L'écran des positions n'offrait que **« + Achat »** : une quantité ne pouvait
qu'augmenter. Impossible d'enregistrer une vente, ni des frais de réseau qui
réduisent réellement le nombre de jetons.

Le manque était **entièrement dans l'écran**. `add_position`
(`app/routes/positions.py`) acceptait déjà un `type` et gérait le signe du
montant ; `finance.quantity_held` soustrait depuis toujours toute quantité qui
n'est pas un versement. Seul le formulaire n'envoyait jamais autre chose.

Chaque ligne porte donc **« − Vendre »** à côté de « + Achat ». Une vente
supérieure à la quantité détenue est refusée, avec le solde rappelé : sans ce
contrôle, une faute de frappe produit une quantité négative qui traverse ensuite
toute la valorisation sans que rien ne l'arrête.

Un support **hors cote** — un fonds euro — se tient en euros et non en parts :
« vendre une quantité » n'y veut rien dire, le bouton n'y apparaît pas.


## Un solde declare est date du jour ou on le declare

Le formulaire demande **« Montant aujourd'hui »** et **« Depuis le »**, en
invitant à saisir la vraie date d'ouverture. L'application stockait alors le
couple (2003, 3 985 €), qui affirme que la somme était là dès l'ouverture.

Sur un livret, cela faisait courir les intérêts sur vingt-deux ans. Un Livret A
ouvert en 2003 et déclaré 3 985 € en 2026 « valait » ainsi 5 798 € au
31 décembre précédent :

    3 985,01 x 1,017^22,2 = 5 798 €

soit **1 813 € d'intérêts que la banque n'a jamais versés**. Le retour au solde
réel le lendemain se lisait comme une perte, et le gain de l'année affichait
− 949 € alors que rien n'avait été perdu.

C'est le symétrique du principe déjà tenu vers l'avant — *on ne fabrique pas de
performance sur un produit déjà constitué*. La garde manquait vers l'arrière.

**Deux corrections, qui se répondent.**

1. **À la création**, un montant du jour sur un produit ouvert antérieurement
   pose une **valorisation datée d'aujourd'hui**. Le solde devient un fait daté
   au lieu d'une affirmation sur le passé. La date d'ouverture reste ce qu'elle
   est : l'ancienneté du produit, qui compte pour un PEA.
2. **Avant le premier solde connu**, `valeur_livret` ne compose plus rien. Le
   montant est reporté tel quel, corrigé des seuls mouvements réels. Plat, parce
   qu'on ne sait pas — et c'est le seul choix qui n'invente pas de passé.

**Sans aucune valorisation, rien ne change** : la valeur d'acquisition est alors
bien ce qu'elle dit, un dépôt à cette date, et ses intérêts sont dus. C'est ce
qui distingue « j'ai déposé 10 000 € en janvier 2024 » de « mon livret ouvert
en 2024 contient 10 000 € aujourd'hui » : le second passe par le formulaire, qui
date le solde.


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

**1. Une règle de classification.** Un motif (`revolut`, `virement interne`,
`topup`, `transfert compte`…) est cherché dans le libellé, sans casse ni
accents, et attribue une catégorie marquée « virement interne ». Attrape les
deux sens : le `VIR SEPA VERS REVOLUT` côté LCL comme le `Top-Up by card` côté
Revolut.

C'était un réglage séparé, `mots_cles_transfert`, avec son propre écran et son
propre vocabulaire — alors qu'une règle fait exactement cela : chercher un texte
dans un libellé pour attribuer une catégorie. **Deux mécanismes pour une seule
idée.** Les motifs sont donc devenus des règles ordinaires : visibles dans le
tableau des règles, modifiables et supprimables comme les autres.

Ils portent la priorité **200**, au-dessus de la valeur par défaut de 100 : ils
passent donc après les règles que vous écrivez, exactement comme les mots-clés
passaient après elles. Une base existante est convertie au premier démarrage
(`_fondre_mots_cles_dans_les_regles`, `app/db.py`), une base neuve reçoit les
mêmes motifs directement en règles.

**2. Rapprochement par paires**, proposé **juste après un import**. Pour les
libellés opaques qu'aucun motif ne décrit (`VIR M SAMUEL 88213`
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
| PEA, CTO, AV, PER | Twelve Data ou Yahoo | Σ quantité × cours, ligne par ligne, converti en EUR |
| Support non coté (fonds euro…) | calcul local | capital + intérêts au taux saisi, **sans réseau** |
| Crypto | CoinGecko | quantité × cours, coté directement en EUR, sans clé |
| Livret, LDDS, LEP, Livret Jeune, PEL, CEL, dépôt à terme | calcul local | capital, intérêts crédités au 31 décembre, **sans réseau** |
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

### Livrets : le capital, et les intérêts à venir

**La valeur affichée d'un livret est son capital**, celui de votre relevé
bancaire. Les intérêts de l'année en cours ne sont pas encore acquis : votre
banque ne les affiche pas, l'application non plus. Ils figurent à côté, sous la
forme **« +72 € prévus au 31 décembre »**, avec le taux annuel.

Une version précédente ajoutait ces intérêts au capital en continu. L'application
affichait donc, toute l'année, plus que le relevé — et une « plus-value » sur un
livret, qui n'en a pas : ce chiffre n'était rien d'autre que les intérêts courus,
présentés comme un rendement partiel non annualisé.

Le calcul suit la règle française des quinzaines : un versement porte intérêt au
1er ou au 16 qui suit, un retrait cesse d'en produire au 1er ou au 16 qui
précède, et **une quinzaine ne paie qu'une fois révolue**. Un livret déclaré
aujourd'hui vaut donc exactement ce que vous avez saisi, sans un centime de plus.

**La date de crédit se règle** dans *Paramètres → Objectifs et frais → Produits à
taux*. Le 31 décembre par défaut, ce qui vaut pour le Livret A, le LDDS, le LEP,
le Livret Jeune, le PEL et le CEL. À changer si vous détenez un dépôt à terme
qui crédite à sa date anniversaire.

Enfin, **« Valeur aujourd'hui » recale le calcul** : la saisir pose une
valorisation datée, et les intérêts repartent de là. Auparavant ce champ n'avait
aucun effet sur un produit à taux, et le montant affiché ignorait ce que vous
aviez inscrit.

### Ce qu'aucune place ne cote : fonds euro et supports non cotés

Un fonds euro n'a ni ticker, ni ISIN, ni cours : ce n'est pas un instrument
coté, c'est l'actif général de l'assureur. **Aucune API ne le renverra jamais**,
et le chercher chez un fournisseur est une impasse. Le bouton
**« + Support non coté »** de l'onglet *Mes supports* existe pour lui, et pour
tout ce qui est dans le même cas : SCPI logée en unité de compte, UC introuvable
chez le fournisseur, support en attente d'arbitrage.

Vous saisissez un nom, un montant, et **un taux annuel facultatif**. Sans taux,
la valeur reste celle que vous avez inscrite. Avec, les intérêts sont calculés
au prorata et crédités au 31 décembre — le rythme réel d'un fonds euro, dont la
participation aux bénéfices tombe une fois l'an, là où un livret réglementé
compte par quinzaines. Comme pour les livrets, le taux est laissé vide par
défaut : un taux inventé produirait une valorisation fausse en silence.

Deux conséquences à connaître :

- **Aucun appel réseau** n'est fait pour ces lignes, ni à la saisie ni au
  rafraîchissement. Elles sont donc saisissables **cours de marché désactivés**,
  exactement comme les livrets.
- **Elles ne cassent plus la valorisation de l'enveloppe.** Une ligne sans cours
  fait normalement retomber tout le compte sur sa valeur saisie — mieux vaut une
  valeur assumée qu'un total partiel présenté comme complet. Un support non coté
  n'entre pas dans ce cas : il fournit toujours une valeur, donc une assurance
  vie « fonds euro + ETF » garde sa valorisation de marché.

### Vérifier la couverture avant de s'y fier

C'est le point de vigilance du cahier des charges : les offres gratuites
couvrent bien mieux les valeurs américaines que les ETF Euronext éligibles PEA.
*Paramètres → Cours de marché → Vérifier la couverture d'un symbole* teste un
symbole à la fois, en symbole court puis en ISIN. **À faire pour chacune de vos
lignes avant de vous fier aux montants affichés.**

> Cette vérification n'a pas pu être faite pendant le développement : elle
> demande votre clé API. Si Twelve Data ne cote pas vos ETF Euronext,
> **Yahoo Finance est désormais disponible** dans le même écran : bonne
> couverture `.PA`, aucune clé à saisir, mais API non officielle, susceptible
> de changer sans préavis. Twelve Data reste le choix par défaut.

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
