"""Un classifieur local : il apprend de vos corrections, et rien ne sort d'ici.

Deux mécanismes, qui ne servent pas au même moment.

**Le regroupement par marchand** travaille dès le premier import, sur une base
vide. Il ramène un relevé de deux cents lignes à une poignée de marchands
récurrents : sur le relevé qui a servi de témoin, neuf marchands couvraient 74 %
des lignes. Neuf décisions au lieu de deux cents, sans rien avoir appris.

**Le modèle** prend le relais ensuite. C'est un bayésien naïf — la technique des
filtres anti-spam — écrit à la main, sans dépendance : ajouter scikit-learn
ferait entrer NumPy, et l'exécutable doublerait de taille. Il s'entraîne sur vos
propres transactions déjà catégorisées, donc sur vos corrections : le troisième
relevé est mieux classé que le premier sans que vous ayez rien fait de plus que
corriger ce qui était faux.

Il ne tranche qu'au-dessus d'un seuil de confiance. En dessous, il se tait
plutôt que d'inventer une catégorie — une ligne « à classer » se voit et se
corrige, une ligne mal classée passe inaperçue et fausse les totaux.
"""
import math
from collections import defaultdict

from .db import query
from .importer import DEFAULT_KEYWORDS, INCOME_KEYWORDS, norm

# Au-dessus, la catégorie est appliquée et signalée ; en dessous, la ligne reste
# à classer. Le seuil est l'écart entre les deux meilleures hypothèses, ramené
# au nombre de traits observés — il ne dépend donc pas de la longueur du libellé.
SEUIL_CONFIANCE = 0.35

# Mots qui ne désignent aucun marchand : ils décrivent le canal de paiement, pas
# ce qu'on a acheté. Les garder rapprocherait « CB Carrefour » de « CB Netflix ».
JETONS_BRUIT = {
    "cb", "carte", "card", "paiement", "payment", "achat", "purchase", "vir",
    "virement", "transfer", "transfert", "prlv", "prelevement", "sepa", "to",
    "from", "de", "du", "la", "le", "les", "des", "au", "aux", "pour", "for",
    "ref", "reference", "facture", "invoice", "no", "num", "numero", "op",
    "operation", "date", "the", "and", "et", "by", "via", "sur", "chez",
}

# Un mot d'au moins quatre lettres nomme un marchand à lui seul : « grab »,
# « agoda », « 12go ». En dessous, il en faut deux — « net interest », « el
# royale » — sans quoi la racine serait un mot vide de sens.
LONGUEUR_SUFFISANTE = 4


def _jetons(texte):
    return [j for j in norm(texte).split() if j]


def _est_identifiant(jeton):
    """Un identifiant de transaction : ni un mot, ni un nombre rond.

    « 9la554nwwmgeav », « 4657189 », « 535456 » ne disent rien du marchand et
    changent à chaque opération — les garder ferait autant de groupes que de
    lignes. Mais « 12go » est bien un nom de marchand : un jeton court qui
    commence par un chiffre reste.
    """
    if len(jeton) <= 4:
        return False
    if jeton.isdigit():
        return True
    return any(c.isdigit() for c in jeton) and len(jeton) >= 6


def racine_marchand(description):
    """Ce qui reste d'un libellé quand on retire tout ce qui varie.

    « Grab* A-9la554nwwmgeav, Jakarta » et « Grab* A-9lf26h6gwtxvav » doivent
    tomber dans le même groupe, sans quoi il y a autant de groupes que de
    courses.
    """
    jetons = [j for j in _jetons(description)
              if len(j) > 1 and j not in JETONS_BRUIT and not _est_identifiant(j)]
    if not jetons:
        return ""
    # Prendre deux jetons systématiquement séparerait « Grab, Jakarta » de
    # « Grab » tout court — or c'est le même marchand, et le regroupement
    # n'existe que pour les réunir. Un premier jeton assez long se suffit.
    if len(jetons[0]) >= LONGUEUR_SUFFISANTE:
        return jetons[0]
    return " ".join(jetons[:2])


def regrouper(lignes, minimum=2):
    """Les marchands qui reviennent, du plus fréquent au moins fréquent.

    `lignes` : des dictionnaires portant au moins `description` et `amount`.
    Chaque groupe renvoie les indices de ses lignes, pour qu'une seule décision
    puisse s'appliquer à toutes.
    """
    paquets = defaultdict(list)
    for i, ligne in enumerate(lignes):
        racine = racine_marchand(ligne.get("description") or "")
        if racine:
            paquets[racine].append(i)

    groupes = []
    for racine, indices in paquets.items():
        if len(indices) < minimum:
            continue
        groupes.append({
            "racine": racine,
            # Le libellé le plus court represente le groupe : c'est celui qui
            # porte le moins de details propres a une seule operation.
            "libelle": min((lignes[i].get("description") or "" for i in indices),
                           key=len),
            "nb": len(indices),
            "total": round(sum(float(lignes[i].get("amount") or 0)
                               for i in indices), 2),
            "indices": indices,
        })
    groupes.sort(key=lambda g: (-g["nb"], g["racine"]))
    return groupes


# --- le modèle -----------------------------------------------------------


def traits(description):
    """Ce que le modèle regarde d'un libellé.

    Les mots, et les tranches de quatre caractères. Les secondes rapprochent
    « CARREFOUR MKT 1234 » de « CARREFOUR CITY », que les premiers laisseraient
    étrangers l'un à l'autre.
    """
    texte = norm(description)
    sortie = [j for j in texte.split() if j]
    compact = texte.replace(" ", "")
    sortie += [compact[i:i + 4] for i in range(len(compact) - 3)]
    return sortie


class Modele:
    """Un bayésien naïf multinomial, lissé de Laplace, calculé en logarithmes.

    Deux modèles en un : les dépenses et les revenus ne partagent pas leurs
    catégories, et le signe du montant suffit à savoir lequel interroger.
    """

    def __init__(self):
        # sens -> categorie -> {trait: compte}
        self.comptes = {1: defaultdict(lambda: defaultdict(int)),
                        -1: defaultdict(lambda: defaultdict(int))}
        self.totaux = {1: defaultdict(int), -1: defaultdict(int)}
        self.documents = {1: defaultdict(int), -1: defaultdict(int)}
        self.vocabulaire = {1: set(), -1: set()}

    def apprendre(self, description, sens, categorie):
        sens = 1 if sens > 0 else -1
        self.documents[sens][categorie] += 1
        for trait in traits(description):
            self.comptes[sens][categorie][trait] += 1
            self.totaux[sens][categorie] += 1
            self.vocabulaire[sens].add(trait)

    def entrainer(self, exemples):
        for description, sens, categorie in exemples:
            if description and categorie:
                self.apprendre(description, sens, categorie)
        return self

    def predire(self, description, sens):
        """(categorie, confiance). Confiance nulle quand le modèle ne sait rien.

        La confiance est l'écart entre les deux meilleures hypothèses ramené au
        nombre de traits DÉJÀ VUS : un libellé long ne doit pas paraître plus sûr
        qu'un court simplement parce qu'il offre plus de matière, et un trait
        inconnu compte pareil pour toutes les catégories — il n'apporte aucune
        information, il ne ferait que diluer celle des autres. Sans cette
        nuance, « CARREFOUR EXPRESS LYON » paraissait deux fois moins sûr que
        « CARREFOUR » tout court, alors qu'on en sait autant.
        """
        sens = 1 if sens > 0 else -1
        documents = self.documents[sens]
        if len(documents) < 2:
            return None, 0.0
        observes = traits(description)
        if not observes:
            return None, 0.0
        taille = max(1, len(self.vocabulaire[sens]))
        total_docs = sum(documents.values())

        scores = []
        for categorie, nb in documents.items():
            score = math.log(nb / total_docs)
            comptes = self.comptes[sens][categorie]
            denominateur = self.totaux[sens][categorie] + taille
            for trait in observes:
                score += math.log((comptes.get(trait, 0) + 1) / denominateur)
            scores.append((score, categorie))
        scores.sort(reverse=True)

        connus = sum(1 for t in observes if t in self.vocabulaire[sens])
        if not connus:
            return None, 0.0
        meilleur, second = scores[0], scores[1]
        ecart = (meilleur[0] - second[0]) / connus
        return meilleur[1], round(1.0 - math.exp(-ecart), 4)


def exemples_d_amorcage():
    """La taxonomie intégrée, servie au modèle comme autant d'exemples.

    Sans elle, un modèle qui n'apprend que de l'historique ne sait rien le
    premier jour — et le premier jour est justement celui où l'on importe le
    plus.
    """
    exemples = []
    for categorie, mots in DEFAULT_KEYWORDS.items():
        exemples += [(mot, -1, categorie) for mot in mots]
    for categorie, mots in INCOME_KEYWORDS.items():
        exemples += [(mot, 1, categorie) for mot in mots]
    return exemples


# Les catégories fourre-tout n'apprennent rien à personne : les donner en
# exemple apprendrait au modèle à ne pas savoir.
CATEGORIES_SANS_LECON = ("Non categorise", "Autre revenu", "Autre depense")

_CACHE = {"signature": None, "modele": None}


def modele_entraine():
    """Le modèle, entraîné sur vos propres transactions déjà catégorisées.

    C'est là qu'est la boucle d'apprentissage, et elle est gratuite : chaque
    correction faite à la main dans le tableau des dépenses est déjà enregistrée
    dans `transactions.category`. Aucune table supplémentaire, aucun réglage —
    corriger une ligne suffit à instruire le prochain import.

    La signature couvre le nombre de lignes ET le contenu des catégories :
    corriger une catégorie ne change ni le compte ni les dates, et un cache qui
    ne regarderait que ceux-là servirait éternellement un modèle périmé.
    """
    etat = query(
        "SELECT COUNT(*) AS n, MAX(created_at) AS dernier, "
        "COUNT(DISTINCT category) AS familles, "
        "SUM(LENGTH(COALESCE(category, ''))) AS empreinte FROM transactions"
    )[0]
    signature = (etat["n"], etat["dernier"], etat["familles"], etat["empreinte"])
    if _CACHE["signature"] != signature:
        exemples = exemples_d_amorcage()
        marques = ", ".join("?" for _ in CATEGORIES_SANS_LECON)
        for r in query(
            "SELECT description, amount, category FROM transactions "
            f"WHERE category IS NOT NULL AND category NOT IN ({marques})",
            CATEGORIES_SANS_LECON,
        ):
            exemples.append((r["description"],
                             1 if (r["amount"] or 0) > 0 else -1,
                             r["category"]))
        _CACHE["signature"] = signature
        _CACHE["modele"] = Modele().entrainer(exemples)
    return _CACHE["modele"]
