<!--
  Merci pour cette proposition.

  Les cases ci-dessous ne sont pas une formalite : les deux premieres protegent
  des donnees personnelles, la troisieme la promesse centrale du logiciel.
-->

## Ce que ça change

<!-- En une ou deux phrases. -->

## Pourquoi

<!-- Le problème résolu, ou l'issue liée (« Corrige #12 »). -->

## Comment ça a été vérifié

<!--
  Ce que vous avez lancé, et ce que vous avez observé.
  « Les tests passent » compte ; « j'ai ouvert l'application et cliqué sur X »
  compte davantage.
-->

---

- [ ] Aucune donnée financière réelle n'est ajoutée : ni base `.db`, ni dossier
      `sauvegarde/`, ni `erreur.log`, ni capture d'écran montrant des montants
- [ ] `python -m unittest discover -s tests -t .` passe
- [ ] Aucun nouvel accès réseau, ou alors désactivé par défaut, annoncé dans
      l'interface et documenté dans `SECURITY.md`
- [ ] Aucune ressource chargée depuis un CDN : police, bibliothèque et icône
      vivent dans le dépôt
- [ ] Un changement de comportement s'accompagne d'un test, en particulier s'il
      touche aux chemins de fichiers ou au durcissement réseau
