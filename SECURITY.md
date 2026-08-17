# Sécurité

Wealfy manipule des relevés bancaires. Ce document dit comment signaler une
faille, et surtout ce que le logiciel protège — et ce qu'il ne protège pas.

## Signaler une faille

**N'ouvrez pas d'issue publique.** Une issue est visible de tous, y compris de
quelqu'un qui exploiterait la faille avant qu'elle ne soit corrigée.

Utilisez **[Security → Report a vulnerability](../../security/advisories/new)**.
Le rapport reste privé entre vous et le mainteneur jusqu'à la publication du
correctif.

Décrivez si possible : la version, le système, la manipulation qui déclenche le
problème, et ce qu'un attaquant pourrait en tirer. **N'joignez jamais votre base
`patrimoine.db` ni un export CSV** — ils contiennent vos transactions réelles.
Une base reconstruite avec des montants inventés suffit toujours à démontrer une
faille.

Projet personnel maintenu sur temps libre : comptez quelques jours de délai, pas
quelques heures.

## Versions suivies

Seule la dernière version publiée reçoit des correctifs. Il n'y a pas de branche
de maintenance.

## Modèle de menace

### Ce qui est tenu

**Le serveur n'écoute que sur `127.0.0.1`.** Il est injoignable depuis le réseau
local comme depuis Internet.

**L'en-tête `Host` est vérifié.** Écouter sur la boucle locale ne suffit pas : un
site malveillant peut faire pointer son propre domaine vers `127.0.0.1`
(*DNS rebinding*). Le navigateur considère alors ses requêtes comme de même
origine et peut **lire** les réponses, donc toute la base. Le `Host`, que
l'attaquant ne contrôle pas, est la seule parade. Toute requête dont l'hôte
n'est pas local est refusée en 403.

**L'en-tête `Origin` est vérifié.** Contre le CSRF : une page tierce qui
déclencherait une action sans lire la réponse.

**La clé API des cours ne sort jamais de la base.** L'API n'expose qu'un booléen
indiquant si elle est renseignée. Les sauvegardes CSV l'excluent également.

**Aucune donnée ne part sur le réseau par défaut.** La seule fonction sortante,
le rafraîchissement des cours, est désactivée à l'installation.

Ces protections sont couvertes par des tests automatisés, exécutés à chaque
proposition de modification (`.github/workflows/ci.yml`, tâche
« Garde-fous reseau »).

### Ce qui n'est pas tenu

**Aucune authentification.** Toute personne ayant accès à votre session ouverte
a accès à vos données. C'est un choix : un mot de passe sur une application
locale mono-utilisateur donne un sentiment de sécurité sans la fournir, puisque
la base reste lisible à côté.

**La base n'est pas chiffrée**, et la clé API y est stockée en clair. Sur une
application locale sans mot de passe maître, le chiffrement n'arrêterait
personne : la clé de déchiffrement devrait vivre à côté de la base.

**Les sauvegardes sont des CSV en clair.**

**Les exécutables ne sont pas signés**, ni sur Windows ni sur macOS. Rien ne
prouve cryptographiquement qu'un fichier téléchargé vient bien de ce dépôt — un
certificat Apple coûte 99 $ par an, un certificat Windows davantage. Vérifiez
que vous téléchargez depuis
[la page des versions de ce dépôt](../../releases) et nulle part ailleurs.

**En clair :** le chiffrement du disque de votre machine (BitLocker, FileVault)
est votre véritable protection au repos. Wealfy protège vos données du réseau,
pas de quelqu'un assis devant votre écran déverrouillé.

## Intégrité de la chaîne de construction

Le dépôt étant ouvert aux contributions, voici ce qui empêche une proposition
malveillante de compromettre les binaires publiés :

- **Les binaires ne sont construits que sur un tag** (`release.yml`). Seule une
  personne ayant les droits d'écriture peut en poser un. Une proposition de
  modification ne peut donc produire aucun binaire publié.
- **La vérification des propositions (`ci.yml`) utilise `pull_request`, jamais
  `pull_request_target`.** Le second exécuterait du code étranger avec les
  secrets du dépôt : c'est la faille par laquelle des projets se sont fait
  exfiltrer leurs jetons.
- **`permissions: contents: read`** sur toute la vérification. Le jeton ne peut
  rien écrire, même détourné.
- **Aucun secret n'est exposé** à la vérification des propositions.
- **Les dépendances sont surveillées** par Dependabot
  (`.github/dependabot.yml`).

Si vous repérez une faiblesse dans cette chaîne — pas seulement dans
l'application — elle relève du même signalement privé.
