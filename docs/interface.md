# Interface

Comment l'application se présente et se manipule.

[← Retour au README](../README.md)

---


## Interface

**`app/static/css/tokens.css` fait autorité sur l'identité visuelle.** `app.css`
n'écrit **aucune couleur en dur** — il ne consomme que des *rôles*
(`--bg-page`, `--action`, `--gain`…). Remplacer ce seul fichier suffit à changer
toute l'apparence.

Palette actuelle, « kaki & bronze », bâtie sur six couleurs : `black #08090A`,
`lilac-ash #A7A2A9`, `bright-snow #F4F7F5`, `charcoal #575A5E`,
`black-forest #113406`, `bronze #CE7E0F`.

**Le vert a été ramené vers le bronze.** `black-forest` est à 106° sur la roue,
le bronze à 35° : 71° d'écart, deux couleurs qui se tiraient l'une contre
l'autre. La rampe kaki est reconstruite à **70°**, soit 35° du bronze — deux
teintes analogues, qui s'accordent. La couleur source reste dans le fichier.

**La barre du haut est anthracite**, sans teinte de marque : elle appartient à
la page plutôt qu'elle ne la surplombe. Seul l'onglet actif porte une couleur,
un filet bronze. En thème sombre elle est posée un cran au-dessus du fond de
page pour se détacher sans se colorer.

### Quatre ajouts assumés à la palette

Une palette de six couleurs ne suffit pas à une application financière. Les
ajouts sont documentés en tête de `tokens.css` :

1. **Un rouge** (`--brick`). La palette n'en contient aucun, or une perte doit se
   distinguer d'un gain. Sans lui, il aurait fallu surcharger le bronze — déjà
   pris par l'alerte — et une moins-value serait devenue indistinguable d'un
   avertissement. Le rouge choisi est chaud et désaturé, dans la famille du
   bronze.
2. **Une rampe kaki complète.** La couleur source est à 11 % de luminosité :
   parfaite en texte sur fond clair, invisible sur le noir du thème sombre. Neuf
   nuances, teinte fixe à 70°, seule la luminosité change.
3. **Dix couleurs catégorielles, volontairement hors palette.** Sur un
   camembert, la question n'est pas l'harmonie avec la marque mais de distinguer
   une part de sa voisine : dix nuances de kaki auraient été indéchiffrables.
   Teintes réparties sur toute la roue, avec une variante plus claire pour le
   thème sombre.
4. **Un gris de texte plus foncé que `lilac-ash`.** Mesuré, `lilac-ash` sur
   `bright-snow` ne donne que **2,5:1**, très en dessous du seuil de 4,5:1 — et
   l'application affiche beaucoup de libellés en 12 px. `lilac-ash` garde donc
   les bordures et les états désactivés, où le contraste importe peu.

Contrastes vérifiés par le calcul, dans les deux thèmes. Texte : principal
19,9:1, secondaire 6,9:1, discret 4,9:1, gain 7,0:1, perte 6,3:1, alerte 4,9:1 —
tous au-dessus de 4,5:1. Couleurs de graphique : toutes au-dessus de 3:1, le
seuil des objets graphiques.

### Couleur de texte et surface de bouton sont deux rôles distincts

`--action` habille le **texte**, les bordures et les icônes : en thème sombre il
est clair, pour ressortir du fond. `--action-surface` remplit les **boutons
pleins** : il reste foncé dans les deux thèmes, puisqu'il porte du texte clair.

Les confondre est un piège classique, et il avait été tendu ici : le bouton
primaire prenait en thème sombre un kaki clair sous un libellé clair, soit
**1,56:1** — illisible. Séparés, on obtient 9,3:1 en thème clair et 4,8:1 en
thème sombre, le bouton restant nettement détaché de sa carte (10:1 et 3,5:1).
Le survol assombrit encore, dans les deux thèmes.

### Fond animé

Un fond « lampe à lave » dérive derrière la page : quatre masses kaki et bronze,
floutées, en **mouvement continu**.

Chaque trajet est une **boucle fermée** — l'image à 100 % est identique à celle à
0 % — jouée en `linear`, sans `alternate`. C'est ce qui distingue un vrai
mouvement d'un va-et-vient : avec `alternate` et une courbe `ease-in-out`, la
masse ralentit jusqu'à l'arrêt à chaque extrémité puis repart en marche arrière,
et cet à-coup se voit. Ici la dérive ne s'arrête jamais et ne rebrousse jamais
chemin. Les quatre durées (17, 23, 29 et 13 s) sont premières entre elles : la
composition d'ensemble ne se répète qu'au bout de plusieurs minutes.

**Une animation qui tourne n'est pas une animation qu'on voit.** La première
version parcourait 13 vw en 9 secondes, soit environ 7 px par seconde sur une
forme floutée à 80 px : les quatre animations étaient bien à l'état `running` et
leur timeline avançait, mais le résultat était sous le seuil de perception, donc
immobile à l'œil. Les trajets ont été portés à 34–46 vw sur des cycles deux fois
plus courts, le flou ramené à 56–64 px et l'opacité relevée. Vitesse mesurée :
environ 0,2 largeur de masse par seconde — indépendante de la taille de l'écran,
puisque tout est exprimé en `vw`.

Trois contraintes tenues :

- **Lisibilité.** Cartes, barre de navigation et modales sont opaques : le
  mouvement ne se voit que dans les marges, jamais sous un chiffre.
- **Performance.** Le flou est appliqué **une seule fois sur le conteneur**, pas
  sur chaque masse — une passe GPU au lieu de quatre. L'animation ne touche que
  `transform`, jamais `top`/`left` qui forceraient un recalcul de mise en page à
  chaque image. `contain: strict` isole le rendu du reste de la page.
- **Respect du réglage système.** `prefers-reduced-motion: reduce` fige le
  mouvement en gardant les couleurs.

L'intensité se règle par deux variables dans `tokens.css` : `--lava-opacity`
(0,20 en clair, 0,32 en sombre) et `--lava-blur`. Mettre l'opacité à `0` suffit
à le désactiver.

Le symbole de la marque (quatre barres ascendantes surmontées d'un point) sert
au logo du bandeau, au favicon et à l'icône de l'exe (`app/static/img/`). Il a
été recoloré sur la palette : dégradé de kaki culminant sur le bronze. L'icône
applicative reste posée sur fond clair — sur le kaki profond de la barre de
navigation, sa barre la plus foncée tomberait trop bas en contraste.

Thème clair et sombre via `[data-theme]`, posé sur `<html>` avant le premier
rendu pour éviter tout flash. Par défaut il suit le réglage du système ; le
bouton ☾ du bandeau force un choix, mémorisé localement. Les montants sont en
police monospace tabulaire, conformément aux tokens.

### Trois règles de mise en page

1. **Un chiffre domine chaque écran.** La vue d'ensemble ouvre sur le patrimoine
   net en 40 px, avec sa variation sur un mois ; actifs, dettes et épargne
   descendent d'un cran, les indicateurs secondaires encore d'un cran. Aucun
   chiffre n'est répété d'un niveau à l'autre.
2. **Une seule barre collante.** Identité, navigation et contrôles tiennent dans
   un bandeau de 58 px. Deux bandeaux empilés donnaient une impression
   d'encombrement, et les statistiques glissées dans l'en-tête étaient illisibles
   à cette taille — elles ont été retirées au profit du héros.
3. **Les explications se replient.** Le pédagogique passe en `<details
   class="note">` : disponible pour qui le cherche, silencieux sinon. Les
   **avertissements** (confidentialité, total partiel, estimation indicielle)
   restent toujours visibles — ce n'est pas la même chose.

Moins de cadres, aussi : les groupes d'actifs sont séparés par des filets plutôt
qu'encadrés, les barres de répartition sont passées de 20 à 8 px, et les ombres
au survol ont disparu — la profondeur vient de la hiérarchie, pas du relief.

Les animations sont calées sur la même courbe et les mêmes durées (`--ease`,
`--t-fast` 130 ms, `--t` 220 ms, `--t-slow` 380 ms, définies en haut de
`app/static/css/app.css`) pour que l'ensemble bouge d'un seul bloc : dépli des
groupes d'actifs, barres de répartition qui se remplissent, modales en
fondu-échelle, notifications qui glissent.

### Entrée du contenu : un déroulement, pas une apparition

L'**arrivée du contenu** — au démarrage comme au changement d'onglet — se fait
en cascade du haut vers le bas : chaque bloc monte de 28 px en se dépliant
légèrement depuis son bord supérieur (`transform-origin: top`), comme une bande
qu'on abaisse. `--t-reveal` 1050 ms par bloc, `--reveal-step` 95 ms de décalage,
soit environ 1,9 s pour que la page entière se soit posée.

Les **rangées s'ouvrent cellule par cellule** : la ligne d'indicateurs ne
débarque pas d'un bloc au milieu de la cascade, ses quatre cases se succèdent.
L'ordre est calculé en JavaScript plutôt qu'avec `nth-child`, précisément pour
pouvoir déplier les rangées dans le décompte général.

### Carrousel : changement de mois et d'onglet

Les deux pages sont **côte à côte et défilent ensemble**, sur une largeur de
panneau entière. Celle qu'on quitte part d'un seul tenant, comme une page qu'on
pousse ; celle qui arrive garde son décalage bloc par bloc et son léger
étirement.

Le même mouvement sert **au changement de mois et au changement d'onglet** : les
onglets sont eux aussi ordonnés de gauche à droite, aller de *Dépenses* vers
*Patrimoine* c'est avancer. Le sens se déduit de la position de l'onglet dans la
barre, sans avoir à le préciser à l'appel — et rester sur le même onglet (un
simple rafraîchissement après une saisie) ne déclenche rien : on retombe alors
sur le déroulement vertical.

**Aucun fondu.** C'est le point qui décide de tout : la matière reste opaque et
se contente de se déplacer. Une version précédente faisait disparaître l'ancien
en fondu pendant que le nouveau apparaissait — cela se lisait comme une
substitution, pas comme un geste. L'opacité reste à 1 d'un bout à l'autre de la
course (vérifié par échantillonnage).

La **distance de défilement vaut la largeur de `main`**, mesurée en JavaScript à
chaque transition. `main` reçoit `overflow-x: clip` — sans découpe, on verrait
les blocs défiler dans les marges d'une page large. `clip` plutôt que `hidden` :
il découpe sans créer de conteneur de défilement.

**Une rangée dépliée ne doit rien dessiner.** Les conteneurs listés dans
`RANGEES` (`app.js`) sont ouverts cellule par cellule : la rangée elle-même
n'est jamais animée, seules ses cellules le sont. Un conteneur qui porte une
bordure ou un fond verrait donc ce décor rester immobile pendant que son
contenu s'en va. C'est ce qui arrivait au filet sous le héros : `.hero` y
figurait alors qu'il porte un `border-bottom`, et la ligne grise restait figée à
l'écran le temps de la transition. Le héros s'anime désormais d'un seul tenant.

### Deux niveaux d'animation selon la machine

`data-anim` sur `<html>`, posé **avant le premier rendu** (la première
apparition se joue dès le chargement, un réglage plus tardif arriverait après
elle) :

| | complet | économe |
|---|---|---|
| Flou d'amorce | oui | non |
| Déroulement | 1050 ms, pas de 95 ms | 620 ms, pas de 55 ms |
| Carrousel | 560 ms | 400 ms |
| Fond « lampe à lave » | animé | figé |

Le partage n'est pas arbitraire : un déplacement ou une opacité sont traités par
le compositeur — la couche est dessinée une fois puis déplacée. Un
`filter: blur()` qui varie oblige à **redessiner** l'élément à chaque image, et
jusqu'à dix blocs s'animent ensemble. En dessous de 60 images par seconde, un
flou animé ne se lit plus comme un flou mais comme des saccades. Le mode économe
garde donc les mêmes trajectoires et les mêmes courbes, sans le flou.

Le mode est estimé d'après `hardwareConcurrency` et `deviceMemory`, puis
**corrigé par une mesure réelle** : `App.mesurerFluidite()` échantillonne une
trentaine d'images pendant la première apparition et rétrograde si la médiane
dépasse 22 ms. Médiane et non moyenne — une seule image longue ne doit pas
condamner la machine. La décision est mémorisée : elle vaut pour la machine, pas
pour la session.

Pour forcer un mode, dans la console :

```js
localStorage.setItem('patrimoine.animations', 'economes')   // ou 'completes'
```

`prefers-reduced-motion` force le mode économe et coupe en plus le fond animé.

Le détail qui compte : la découpe se fait au bord de `main`, alors que le
panneau est en retrait de la marge interne. Une première version faisait
parcourir la **largeur du panneau** — parfaitement adjacente en théorie, mais
elle laissait dépasser une bande de la page précédente, large exactement comme
cette marge (24 px), sur le côté de la nouvelle. Prendre la largeur de `main`
ajoute un vide de deux marges entre les deux mois, qui défile en une vingtaine
de millisecondes : invisible, contrairement à la bande résiduelle.

Le défilement dure **560 ms** avec 42 ms de décalage entre blocs, soit environ
940 ms au total — deux fois plus rapide que le déroulement vertical, parce qu'on
suit un geste et non une mise en place. La courbe est symétrique : un carrousel
démarre et s'arrête, il ne freine pas à l'arrivée comme un élément qui se pose.

Le panneau quitté est **cloné avant le rendu** et posé hors flux, à une position
mesurée au pixel puisque les marges changent selon la largeur d'écran. Deux
pièges traités :

- **Un canevas cloné arrive vide** — le clonage copie la balise, pas son dessin.
  Sans report explicite du bitmap, les graphiques auraient disparu au moment
  précis de la transition. Ils sont recopiés sur la copie.
- **Les identifiants sont retirés du clone.** Deux `id` identiques dans la page
  et `App.el('#…')` renverrait un élément de la copie au lieu du vrai.

**Les deux mouvements démarrent au même instant, pas au clic.** La copie est
posée figée dès le clic, mais sa sortie n'est armée qu'une fois le nouveau
contenu prêt. Sans cette attente, l'onglet Historique — le plus long à
calculer — voyait sa page sortir, disparaître, puis la nouvelle arriver
longtemps après : deux mouvements successifs au lieu d'un défilement. L'écart
mesuré entre le départ de la sortie et celui de l'entrée est passé de **704 ms
à 3 ms**. La copie restant à l'écran pendant le calcul, il n'y a pas non plus de
page vide.

La copie s'efface par minuterie **calée sur sa propre durée** : elle part d'un
seul tenant, il n'y a pas de décalage à ajouter. Compter celui des blocs
entrants la laissait traîner une demi-seconde de trop, figée sur sa dernière
image par `animation-fill-mode: both` — ce qui prolongeait d'autant la bande
résiduelle.

Un clic rapide sur le mois suivant remplace la copie en cours au lieu d'en
empiler une seconde. Un changement d'onglet pendant la transition la supprime
aussi. Choisir un mois directement dans le sélecteur ne déclenche pas de
défilement : il n'y a pas de sens à représenter.

Un **flou d'amorce** accompagne les deux mouvements — 7 px pour le déroulement
vertical, 5 px pour le carrousel, plus rapide donc moins gourmand en flou. Une
forme nette qui se déplace vite paraît saccadée ; le flou donne la fluidité d'un
mouvement filé. C'est la seule propriété animée non composée par le GPU du
projet — acceptable sur une poignée d'éléments et une seule fois par navigation.
`--reveal-blur: 0` et `--carousel-blur: 0` le suppriment sans toucher au reste.

**Le marqueur d'entrée est posé au rendu et jamais retiré ensuite.** C'est la
règle qui tient tout : modifier `animation-name` sur un élément déjà affiché
relance son animation. Une première version neutralisait l'apparition pendant le
glissement puis rétablissait la règle par minuterie — le rétablissement
relançait la cascade juste après le glissement, donnant l'impression d'un
rechargement de page. Désormais `.revealing` et l'ordre `--i` sont écrits une
fois, au moment où le contenu est mis en place, et n'évoluent plus jusqu'à la
navigation suivante.

`prefers-reduced-motion: reduce` désactive tout, fond animé compris.


## Les 4 onglets

**Vue d'ensemble** — dépensé ce mois vs mois précédent, patrimoine net et sa
courbe sur 12 mois, répartition cible vs réelle, camembert des catégories,
détail des métriques.

**Dépenses** — un bandeau en tête d'onglet rappelle le dernier relevé importé et
porte le bouton **« + Ajouter un relevé »**. En dessous : transactions du mois,
catégorie modifiable directement dans la liste, ajout manuel, tendance 6 mois.
Un mois vide propose directement l'import plutôt qu'un tableau nu.

**Patrimoine** — **un seul bouton « + Ajouter »**. Il ouvre un choix : quel
produit voulez-vous ajouter ? Livret A, PEA, assurance vie, crypto, bien
immobilier, prêt… Le type choisi, la saisie se limite au nom, au montant et à la
date. En dessous : actifs groupés par famille, passifs avec capital restant dû.

**Historique** — archive mensuelle et journal des imports. Un import peut être
annulé : ses transactions sont supprimées avec lui.

**Paramètres** (icône engrenage) — trois sections : *Classement des dépenses*
(catégories, virements internes, règles), *Objectifs et frais* (répartition
cible, TER et courtage), *Cours de marché* (fournisseur, correspondances de
symboles, types d'actifs personnalisés).


## Observations patrimoniales

Une ligne sous le patrimoine net remonte ce que les chiffres impliquent :
plafond de livret atteint, taux d'endettement au-dessus du seuil courant,
épargne de précaution sous votre cible, écart de répartition, maturité fiscale
d'un PEA, concentration d'une ligne. Dépliée, chaque observation mène à la fiche
ou au réglage concerné.

**Repliée par défaut, sur 40 px.** La synthèse est là pour les chiffres : une
liste dépliée sous le patrimoine net repoussait les indicateurs hors de vue. Le
compte — « 1 point à voir · 4 observations » — suffit à savoir s'il y a lieu de
regarder. Un point à voir se signale par la **couleur**, pas par la taille : le
bloc garde la même hauteur.

**Il n'y a rien à l'écran quand il n'y a rien à signaler.** Un bandeau
perpétuellement présent apprend à ne plus être lu.


## Agrandir un graphique

Chaque carte de la synthèse porte en pied une action discrète qui ouvre une vue
large, avec des angles supplémentaires :

| Graphique | Vues disponibles |
|---|---|
| Patrimoine net | *Total* (net, actifs, dettes) et **Par actif** — une courbe par produit |
| Dépenses par catégorie | *Camembert* et *Tableau* : montant, part, nombre d'opérations, panier moyen |
| Dépenses / revenus | *Barres* et *Tableau* : revenus, dépenses, solde, épargne et taux, mois par mois |

La vue **Par actif** répond à une question que la courbe du net ne pose même
pas : elle dit *combien*, celle-ci dit *d'où ça vient*. Chaque courbe démarre à
la date d'acquisition du produit — valeur `None` avant, plutôt que zéro, pour ne
pas faire ramper une ligne sur l'axe là où le produit n'existait pas encore.

Les cartes de la synthèse gardent leur taille : le détail se demande, il ne
s'impose pas. Les séries déjà chargées sont réutilisées, seule la vue par actif
appelle le serveur (`/api/assets/series`).

### Ce que le logiciel dit, et ce qu'il ne dit pas

Il énonce des **faits vérifiables** — plafonds légaux, ratios, écarts avec les
cibles que *vous* avez fixées. Jamais de recommandation d'allocation ou
d'arbitrage : « votre Livret A a dépassé son plafond de versements » est un
constat, « placez l'excédent sur votre PEA » serait un conseil, et ce logiciel
n'est pas un conseiller agréé.

Trois précisions qui évitent des contresens :

- **Le plafond porte sur les versements, pas sur le solde.** Un livret peut
  légitimement dépasser 22 950 € par capitalisation des intérêts. Le message le
  dit explicitement, au lieu de laisser croire à une irrégularité.
- **La maturité fiscale ne s'affiche que tant qu'elle n'est pas atteinte.** Une
  fois les 5 ans du PEA franchis, il n'y a plus rien à surveiller.
- **La concentration ne concerne que les actifs exposés au marché.** Un livret
  réglementé est garanti en capital : signaler qu'on y concentre son épargne
  serait un faux positif. Et avec un seul produit financier, dire qu'il pèse
  100 % est exact et sans intérêt — il faut au moins deux lignes.

Les plafonds (`plafonds_produits`), seuils et cibles sont des **réglages**, pas
des constantes : ces montants changent par décret, il faut pouvoir les corriger
sans toucher au code.

### Taux d'endettement et reste à vivre

`taux_endettement` rapporte les mensualités des prêts **encore en cours** aux
revenus du mois — compter une mensualité soldée gonflerait le ratio sans raison.
Le seuil de 35 % est la référence bancaire courante.

`reste_a_vivre_mois` retranche des revenus les charges fixes et l'épargne. Les
catégories considérées comme fixes se cochent dans *Paramètres → Classement des
dépenses*, sur le même modèle que les virements internes.


## Une seule façon d'ajouter quelque chose

Il y a eu jusqu'à trois boutons côte à côte — « + Prêt », « + Actif détaillé »,
« + Ajouter mes produits » — dont deux faisaient la même chose à des moments
différents : l'un pour déclarer l'existant, l'autre pour ajouter au fil de
l'eau. La distinction n'existait que dans le code.

Il n'en reste **un seul**. On choisit d'abord *quoi* ajouter dans une liste
lisible, la saisie suit. La déclaration groupée (plusieurs montants d'un coup,
pour la première mise en route) et le formulaire complet restent accessibles,
comme deux entrées parmi les autres — au lieu d'occuper la barre en permanence.

Après avoir créé un PEA ou un portefeuille crypto, l'application ouvre
directement sa fiche : un compte-titres vide n'a d'intérêt qu'une fois ses
lignes renseignées.

### La fiche d'un actif : deux onglets, plus cinq

« Résumé » et « PRU & TRI » affichaient les mêmes lignes sous deux angles. Leurs
chiffres — capital investi, valeur de marché, plus-value, PRU moyen, TRI — sont
maintenant en tête des positions. Reste **Mes supports** (ou *Mes cryptos*) et
**Historique** ; l'immobilier garde son onglet *Prêt & rendement*. La comparaison
à un indice se replie sous les positions.

### Ajouter une ligne : trois champs, plus neuf

Quand l'instrument vient de la recherche, tout est déjà connu : on ne demande
plus que **quantité, prix unitaire et date**. Place, devise, ISIN et indice de
référence se replient sous « Détails de l'instrument » — ils ne servent qu'à la
saisie manuelle.


## Masquer les montants

Le bouton œil de la barre du haut floute les chiffres saillants : le patrimoine
net en gros, les indicateurs, les valeurs de synthèse. **Actif par défaut** — on
choisit d'afficher ses chiffres, on ne les découvre pas par surprise devant
témoin. Le choix est mémorisé localement.

Les tableaux de détail restent lisibles : tout flouter rendrait l'application
inutilisable au quotidien, alors que le risque réel est le grand nombre qu'un
regard de passage attrape en premier. C'est un cache-écran, **pas un
chiffrement** : les valeurs restent dans la page.
