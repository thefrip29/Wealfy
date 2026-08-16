# Composants tiers

Wealfy embarque les composants ci-dessous. Ils gardent leur licence d'origine,
qui n'est pas celle du reste du projet (AGPL-3.0) : une licence s'applique à une
œuvre, pas à un dépôt.

Tout est **embarqué**, rien n'est chargé depuis le réseau à l'exécution — c'est
la condition pour qu'une application censée ne rien laisser sortir tienne
réellement sa promesse, y compris hors ligne.

---

## Geist Pixel

- **Fichier** : `app/static/fonts/geist-pixel.woff`
- **Licence** : SIL Open Font License 1.1 — texte intégral dans
  `app/static/fonts/OFL.txt`, conservé auprès de la police comme l'OFL l'exige
- **Copyright** : 2026 The Geist Project Authors
- **Source** : https://github.com/vercel/geist-font

**Modification apportée** : la police d'origine pèse 3,5 Mo pour 481 glyphes.
Elle est ici réduite au latin-1 et à la ponctuation employée par l'interface,
soit 47 Ko. L'axe variable `ELSH`, qui commande la forme du pixel, est conservé.

Le nom « Geist Pixel » est conservé pour cette version modifiée : l'en-tête de
copyright de l'OFL fournie ne déclare **aucun** *Reserved Font Name*, la clause
qui aurait imposé un renommage.

Emploi dans l'interface : le nom de la marque et l'intitulé qui coiffe le
chiffre principal. Jamais un montant ni un tableau — voir la note en fin de
`app/static/css/tokens.css`.

---

## Chart.js

- **Fichier** : `app/static/vendor/chart.umd.min.js`
- **Licence** : MIT
- **Copyright** : Chart.js Contributors
- **Source** : https://github.com/chartjs/Chart.js

Bibliothèque de graphiques. Embarquée plutôt que servie depuis un CDN : une
application locale ne doit pas dépendre du réseau pour dessiner une courbe, et
un appel à un CDN signalerait chaque ouverture du logiciel à un tiers.

---

## Dépendances Python

Installées par `pip`, non redistribuées dans le dépôt mais présentes dans les
exécutables construits. Voir `requirements.txt`.

| Composant | Licence | Rôle |
|---|---|---|
| Flask | BSD-3-Clause | serveur applicatif local |
| waitress | ZPL-2.1 | serveur HTTP de production |
| pywebview | BSD-3-Clause | fenêtre native |
| pyobjc (macOS) | MIT | liaisons Cocoa et WebKit |
| PyGObject (Linux) | LGPL-2.1 | liaisons GTK et WebKit2 |
| Pillow | MIT-CMU | dessin de l'icône, à la construction |
| PyInstaller | GPL-2.0 avec exception | construction des exécutables |

L'exception de licence de PyInstaller autorise explicitement la distribution
sous toute licence des applications qu'il empaquette.
