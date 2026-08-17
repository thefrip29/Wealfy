<p align="center">
  <img src="app/static/img/logo-symbole.svg" alt="" width="120">
</p>

<h1 align="center">Wealfy</h1>

<p align="center">
  <strong>Gestion patrimoniale locale.</strong><br>
  Vos relevés bancaires ne quittent pas votre machine.
</p>

<p align="center">
  <a href="LICENSE"><img alt="Licence AGPL-3.0" src="https://img.shields.io/badge/licence-AGPL--3.0-7D9440"></a>
  <img alt="Windows et macOS" src="https://img.shields.io/badge/Windows%20%7C%20macOS-DD8C10">
  <img alt="Python 3.13+" src="https://img.shields.io/badge/Python-3.13%2B-7D9440">
</p>

---

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


## Documentation

| | |
|---|---|
| [**Interface**](docs/interface.md) | Comment l'application se présente : les quatre onglets, les graphiques, l'ajout d'un élément, le masquage des montants |
| [**Données**](docs/donnees.md) | Import de relevés, déclaration du patrimoine existant, virements internes, classification, cours de marché |
| [**Architecture**](docs/architecture.md) | Stack, structure du code, calculs, modèle de données, et pourquoi rien n'est figé dans un snapshot |
| [**Sécurité**](SECURITY.md) | Modèle de menace complet, signalement d'une faille, intégrité de la chaîne de construction |
| [**Contribuer**](CONTRIBUTING.md) | Mettre en route, ce que le projet attend d'un changement |
| [**Composants tiers**](THIRD-PARTY.md) | Geist Pixel, Chart.js et les dépendances Python |


## Contribuer

Les propositions sont bienvenues — correction, idée, ou simple signalement de ce
qui vous a fait trébucher. Voir [CONTRIBUTING.md](CONTRIBUTING.md).

**Un rappel qui vaut d'être lu avant d'ouvrir une issue :** ce logiciel manipule
vos relevés bancaires réels, et une issue GitHub est publique et indexée. Ne
joignez jamais votre base `patrimoine.db`, le dossier `sauvegarde/`, ni une
capture d'écran montrant des montants. `python run.py --debug` ouvre
l'application sur une base vide où saisir des montants inventés.

**Une faille de sécurité ne se signale pas par une issue** mais en privé :
voir [SECURITY.md](SECURITY.md).


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
