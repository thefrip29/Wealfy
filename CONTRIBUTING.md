# Contribuer à Wealfy

Les propositions sont bienvenues : correction, idée, ou simple signalement de ce
qui vous a fait trébucher. Ce document dit comment, et par quoi commencer.

---

## ⚠️ D'abord : vos données

Ce logiciel manipule des relevés bancaires réels. **Les vôtres.** Avant tout
signalement ou toute proposition :

| Ne partagez jamais | Pourquoi |
|---|---|
| `patrimoine.db` | vos transactions, comptes et soldes |
| Le dossier `sauvegarde/` | les mêmes, en CSV lisible |
| Une capture d'écran de l'application | les montants y sont affichés |
| `erreur.log` | les traces peuvent contenir des valeurs |

Une issue GitHub est **publique et indexée par les moteurs de recherche**. Un
fichier joint à une issue reste accessible par son URL même après suppression de
l'issue.

**Pour illustrer un problème :** l'application se lance sur une base vide avec
`PATRIMOINE_DB` :

```bash
python run.py --debug
```

Saisissez deux ou trois montants inventés, et faites votre capture là-dessus.
Le bouton « masquer les montants » (l'œil, en haut à droite) floute aussi
l'affichage si c'est plus rapide.

Le dépôt refuse automatiquement toute base, sauvegarde ou image ajoutée par une
proposition (`.github/workflows/ci.yml`) — mais ce garde-fou est un filet, pas
une permission de ne pas faire attention.

**Une faille de sécurité ne se signale pas par une issue :** voir
[SECURITY.md](SECURITY.md).

---

## Signaler un problème ou proposer une idée

Ouvrez une [issue](../../issues/new/choose). Les modèles proposés vous guident.

Ce qui aide vraiment : ce que vous attendiez, ce qui s'est produit, et comment le
reproduire. Le système et la version aussi — un problème d'affichage macOS n'a
souvent rien à voir avec le même symptôme sous Windows.

---

## Proposer une modification de code

### Mettre en route

```bash
python -m pip install -r requirements.txt
```

```bash
python run.py --debug
```

`--debug` recharge à chaud et autorise une seconde instance à côté de votre
installation habituelle.

### Avant de proposer

```bash
python -m unittest discover -s tests -t .
```

Les tests doivent passer. Ils tournent de toute façon sur Windows, macOS et
Linux à chaque proposition, mais autant le savoir avant.

Pour vérifier que l'application démarre réellement, et pas seulement que le code
compile :

```bash
bash ci/smoke.sh python run.py
```

### Ce que le projet attend d'un changement

**Les commentaires expliquent POURQUOI, pas quoi.** Le code dit déjà ce qu'il
fait. Ce qu'il ne dit pas, c'est ce qui a été essayé avant, ou quel piège la
ligne évite. Le dépôt en est rempli — lisez `app/paths.py` ou
`app/static/splash.html` pour le ton.

**Aucune couleur en dur** hors `app/static/css/tokens.css`. Les seules
exceptions sont les couleurs de marque du logo, qui ne changent pas avec le
thème.

**Rien de nouveau ne doit sortir sur le réseau.** C'est la promesse centrale du
logiciel. Une fonctionnalité qui appelle un service distant doit être
désactivée par défaut, annoncée explicitement dans l'interface, et documentée
dans [SECURITY.md](SECURITY.md). Une police, une bibliothèque ou une icône se
place dans le dépôt, jamais derrière un CDN.

**Les montants ne se lisent pas dans une police fantaisie.** La police à pixels
est réservée à l'identité ; tout ce qui se déchiffre reste en chasse fixe avec
des chiffres tabulaires.

**Un changement de comportement s'accompagne d'un test.** Surtout s'il touche
aux chemins de fichiers ou au durcissement réseau : ce sont les deux endroits où
une erreur est silencieuse.

### La proposition elle-même

Une idée par proposition. Un titre qui dit ce que ça change. Dans le corps :
pourquoi, et ce que vous avez vérifié.

Si c'est un gros changement, ouvrez une issue d'abord — autant discuter de
l'approche avant d'y passer une soirée.

---

## Licence

En proposant du code, vous acceptez qu'il soit distribué sous
[AGPL-3.0](LICENSE), comme le reste du projet.
