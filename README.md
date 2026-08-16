# Wealfy — logiciel de gestion patrimoniale

Application locale de suivi des dépenses, du patrimoine et des prêts. Le serveur
n'écoute que sur `127.0.0.1` et tout tient dans un unique fichier SQLite
(`patrimoine.db`, emplacement précisé plus bas).

Une seule fonction peut sortir sur le réseau : le rafraîchissement des cours de
marché, **désactivé par défaut** — voir la section qui lui est consacrée. Tant
qu'il n'est pas activé, aucune donnée ne quitte la machine.

## Installation

Les fichiers sont dans [la dernière version publiée](../../releases/latest).

### Windows

`Wealfy-<version>-Setup.exe` — raccourcis menu Démarrer et Bureau,
désinstallation propre. `Wealfy-<version>-portable.exe` fonctionne aussi seul,
sans installation, y compris depuis une clé USB.

SmartScreen peut afficher un avertissement au premier lancement : l'application
n'est pas signée par un certificat d'éditeur. « Informations complémentaires »
puis « Exécuter quand même ».

Vos données vont dans `%LOCALAPPDATA%\Patrimoine`, ou à côté de l'exe en mode
portable.

### macOS

`Wealfy-<version>-arm64.dmg` pour les Mac Apple Silicon (M1 à M4),
`Wealfy-<version>-x86_64.dmg` pour les Mac Intel. Ouvrez l'image et glissez
**Wealfy** dans **Applications**.

**Au premier lancement, macOS refusera d'ouvrir l'application** — un message
annonce que le développeur n'est pas identifié, ou, sur Apple Silicon, que
l'application « est endommagée ». Elle ne l'est pas. Wealfy n'est pas signée par
un certificat Apple, qui coûte 99 $ par an ; macOS bloque par défaut tout
logiciel qui n'en a pas, quel qu'il soit.

Pour l'autoriser une fois pour toutes, ouvrez le **Terminal**
(Applications → Utilitaires) et collez :

```bash
xattr -dr com.apple.quarantine /Applications/Wealfy.app
```

Puis lancez l'application normalement. Cette commande retire le seul drapeau que
macOS pose sur les fichiers téléchargés ; elle ne modifie rien d'autre.

*Sans passer par le Terminal :* double-cliquez Wealfy, fermez le message, puis
**Réglages Système → Confidentialité et sécurité**, descendez jusqu'à « Wealfy a
été bloquée », cliquez **Ouvrir quand même**. Sur macOS 15 et suivants, l'ancien
contournement par clic droit → Ouvrir ne fonctionne plus.

Vos données vont dans `~/Bibliothèque/Application Support/Wealfy`.

### Linux

Aucun paquet n'est fourni — il n'existe pas de format unique. L'application
fonctionne depuis les sources (voir ci-dessous) ; il faut le paquet système
`gir1.2-webkit2-4.1` en plus des dépendances Python. Les données vont dans
`~/.local/share/wealfy`.

## Lancement

L'application s'ouvre dans sa propre fenêtre — ni console, ni navigateur, ni
adresse à retenir. La fermer arrête l'application.

En mode développement :

```bash
python -m pip install -r requirements.txt
```

```bash
python run.py
```

Options : `--browser` (ouvrir dans le navigateur au lieu de la fenêtre),
`--no-browser` (serveur seul), `--debug` (serveur de développement Flask avec
rechargement à chaud), et les variables d'environnement `PATRIMOINE_PORT` et
`PATRIMOINE_DB` (pour travailler sur une base de test). Si le port est occupé,
le suivant libre est choisi automatiquement.

**Une seule copie à la fois.** Relancer l'application alors qu'elle tourne déjà
ouvre une fenêtre sur celle en cours au lieu d'en démarrer une seconde : deux
copies écrivant dans la même base SQLite finiraient par se marcher dessus.
`--debug` fait exception, pour pouvoir en lancer une seconde à côté.

### Où sont mes données

| Mode de lancement | Emplacement de la base |
|---|---|
| Windows, installé | `%LOCALAPPDATA%\Patrimoine\patrimoine.db` |
| Windows, exe posé dans un dossier inscriptible | `patrimoine.db` à côté de l'exe |
| macOS | `~/Bibliothèque/Application Support/Wealfy/patrimoine.db` |
| Linux | `~/.local/share/wealfy/patrimoine.db` |
| `python run.py` | `patrimoine.db` à la racine du projet |

**Le mode portable est propre à Windows**, où l'exe est un fichier qu'on pose où
l'on veut. Sur macOS, « à côté de l'exécutable » désignerait l'intérieur de
`Wealfy.app` : y écrire invaliderait la signature du bundle et les données
disparaîtraient à la mise à jour suivante, quand le bundle entier est remplacé.

Sous Windows, l'exe choisit tout seul : si une base existe déjà à côté de lui, il
la prend ; à défaut, si une base existe dans `%LOCALAPPDATA%\Patrimoine`, il la
reprend — on ne repart jamais d'une base vide alors que les données existent
ailleurs. Sinon il en crée une à côté de lui si le dossier l'accepte, dans
`%LOCALAPPDATA%` sinon (cas d'une installation dans `Program Files`, non
inscriptible).

La désinstallation ne touche jamais à `%LOCALAPPDATA%\Patrimoine` : les données
survivent aux mises à jour comme aux réinstallations.

Ce dossier garde son nom d'origine sous Windows alors que le logiciel s'appelle
désormais Wealfy : le renommer rendrait invisible la base d'une installation
existante, pour le seul bénéfice d'un nom de dossier que personne ne voit. macOS
et Linux n'ayant aucune installation antérieure à ménager, le nom actuel y est
employé directement.

### Ce contre quoi l'application protège, et ce contre quoi elle ne protège pas

Autant l'écrire franchement, puisque le logiciel manipule des données bancaires.

**Ce qui est tenu.** Le serveur n'écoute que sur `127.0.0.1` : il est
injoignable depuis le réseau local comme depuis Internet. Les requêtes dont
l'en-tête `Host` n'est pas une adresse locale sont refusées, ce qui ferme
l'attaque par *DNS rebinding* — un site malveillant qui ferait pointer son
domaine vers `127.0.0.1` pour lire votre base à travers votre navigateur. Les
requêtes provenant d'une autre origine sont refusées également. La clé API des
cours n'est jamais renvoyée par l'API, seulement l'information qu'elle est
renseignée ou non. Les sauvegardes ne l'exportent pas non plus.

**Ce qui ne l'est pas.** Il n'y a **aucune authentification** : toute personne
ayant accès à votre session Windows ou macOS ouverte a accès à vos données. La
base SQLite n'est **pas chiffrée**, et la clé API des cours y est stockée en
clair — sur une application locale sans mot de passe maître, un chiffrement
n'arrêterait de toute façon personne, puisque la clé de déchiffrement devrait
vivre à côté. Les sauvegardes sont des CSV en clair. Enfin, les exécutables ne
sont signés ni sur Windows ni sur macOS : rien ne prouve
cryptographiquement qu'un fichier téléchargé vient bien de ce dépôt.

**En clair** : le chiffrement du disque de votre machine (BitLocker, FileVault)
est votre véritable protection au repos. Wealfy protège vos données du réseau,
pas de quelqu'un devant votre écran déverrouillé.

Une seule fonction peut faire sortir des données de la machine, le
rafraîchissement des cours, **désactivé par défaut** : il transmet au
fournisseur les symboles interrogés et votre clé API. Vos montants, quantités et
transactions ne sortent jamais — mais une liste de tickers renseigne déjà sur la
composition d'un portefeuille.

Base de développement et base de l'exe restent **distinctes** : l'exe embarque
une copie figée du code, il ne voit pas les données de la version
développement, et inversement.

Sans console, une erreur au démarrage n'a nulle part où s'afficher : elle est
écrite dans `erreur.log`, à côté de la base.

Sauvegarde = copie du fichier `.db`. Rien d'autre. Pour une sauvegarde lisible
sans l'application, voir la section suivante.

### Sauvegardes CSV

*Paramètres → Sauvegardes → **Sauvegarder maintenant***. Chaque sauvegarde est
un dossier horodaté dans `sauvegarde/`, à côté de la base :

```
sauvegarde/2026-08-11_20h27/
  manifeste.csv      date, empreinte, patrimoine net, nombre de lignes
  resume.csv         la situation à l'instant T, lisible telle quelle
  assets.csv  transactions.csv  liabilities.csv  …
```

`resume.csv` se lit directement dans un tableur : une ligne par actif avec sa
valeur, son capital investi, sa plus-value et l'origine de la valeur, puis les
passifs et les totaux. C'est ce qu'on vient consulter des mois plus tard sans
vouloir relancer l'application.

Les fichiers sont en **UTF-8 avec BOM et séparateur point-virgule** — ce
qu'attend Excel en configuration française. Sans le BOM, les accents sont
illisibles à l'ouverture ; sans le point-virgule, tout atterrit dans une seule
colonne.

**Trois mesures pour que le dossier ne gonfle pas :**

1. **Le cache des cours n'est pas sauvegardé.** C'est de loin la table qui
   grossit le plus vite (un cours par ligne et par jour) et elle se retélécharge
   d'un clic. La sauvegarder doublerait la taille pour rien.
2. **Rien n'est réécrit si rien n'a changé.** Une empreinte du contenu est
   comparée à la dernière sauvegarde ; sauvegarder deux fois de suite ne crée
   pas deux dossiers.
3. **Rotation automatique** au-delà de `sauvegardes_max` (30 par défaut).

Ordre de grandeur mesuré sur huit mois de données complètes : **26 Ko** par
sauvegarde, soit moins d'un mégaoctet pour les trente conservées.

**La clé API n'est pas exportée.** Elle serait recopiée en clair dans autant de
fichiers que de sauvegardes ; elle reste dans la base seule.

**Restauration** — le bouton *Restaurer* remplace les données vivantes par
celles de la sauvegarde. Irréversible, donc : une sauvegarde de sécurité est
prise juste avant, l'écriture se fait en une seule transaction (annulée
entièrement en cas d'erreur), et l'interface demande confirmation en disant ce
qui sera perdu.

### Reconstruire l'exe

Après toute modification du code, l'exe doit être régénéré (il contient une
copie du code au moment du build) :

```bash
python build_exe.py
```

Le script génère l'icône multi-tailles depuis le symbole de la marque, écrit les
métadonnées de version lues par Windows, lance PyInstaller en `--onefile
--noconsole`, puis compile l'installateur. Il produit deux fichiers dans
`dist/` : `Wealfy.exe` et `Setup_Wealfy.exe`.

`python build_exe.py --exe-seul` s'arrête à l'exe, pour itérer plus vite.

Nécessite `pyinstaller` et `pillow` (construction uniquement, non embarqués),
plus Inno Setup pour l'installateur :

```bash
winget install JRSoftware.InnoSetup
```

Sans lui, le script construit l'exe et signale simplement que l'installateur a
été sauté.

Le numéro de version vit dans `app/version.py`, **source unique** : l'exe,
l'installateur et l'écran *À propos* le lisent tous là. L'augmenter avant un
build suffit à ce que Windows reconnaisse une mise à jour.

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

## Licence

Wealfy est distribué sous **GNU Affero General Public License v3.0** — texte
intégral dans [`LICENSE`](LICENSE).

```
Copyright (C) 2026 The Wealfy Authors

Ce programme est un logiciel libre : vous pouvez le redistribuer et le modifier
selon les termes de la GNU Affero General Public License, version 3, telle que
publiée par la Free Software Foundation.

Il est distribué dans l'espoir qu'il sera utile, mais SANS AUCUNE GARANTIE —
sans même la garantie implicite de VALEUR MARCHANDE ou d'ADÉQUATION À UN USAGE
PARTICULIER. Voir la GNU Affero General Public License pour plus de détails.
```

L'AGPL plutôt que la GPL pour une raison précise : sa clause 13 impose de
publier le code source à quiconque **héberge** une version modifiée comme
service en ligne, là où la GPL ne l'exige qu'à la redistribution du logiciel.
Un gestionnaire de patrimoine est exactement le genre d'outil qu'on transforme
en service fermé.

Les composants tiers embarqués gardent leur propre licence : voir
[`THIRD-PARTY.md`](THIRD-PARTY.md).
