"""Détection des prélèvements récurrents, à partir des seules transactions.

Un abonnement ne se déclare pas : il se reconnaît. Trois signes le distinguent
d'une dépense ordinaire chez un commerçant fréquenté, et il les faut tous les
trois — Grab compte quarante-six passages dans un seul relevé sans être un
abonnement pour autant.

1. **Le même marchand revient.** On réutilise `classifier.racine_marchand`,
   qui sait déjà réunir « Grab* A-9la554, Jakarta » et « Grab* A-9lf26h ».
2. **L'écart entre deux prélèvements est régulier.** Une course en taxi tombe
   n'importe quand ; un abonnement tombe toutes les quatre semaines, tous les
   trimestres ou tous les ans.
3. **Le montant ne bouge pas.** C'est le signe le plus sûr : un restaurant
   n'additionne jamais deux fois la même note au centime près.

Ce qui est cherché ici n'est pas la liste de vos abonnements — vous la
connaissez — mais les trois choses qu'on ne voit pas : ce que le total coûte à
l'année, les prix qui ont augmenté sans prévenir, et les prélèvements qui
continuent alors qu'on croyait avoir résilié.
"""
from datetime import date, timedelta
from statistics import median

from .classifier import racine_marchand
from .finance import iso, parse_date

# Les périodicités reconnues : nom, écart en jours, tolérance. La tolérance
# d'un mois est large parce qu'un prélèvement « le 15 » produit des écarts de
# 28 à 31 jours, et qu'un jour ouvré le décale encore.
PERIODES = (
    ("hebdomadaire", 7, 2, 52.0),
    ("mensuel", 30.4, 6, 12.0),
    ("bimestriel", 61, 8, 6.0),
    ("trimestriel", 91, 12, 4.0),
    ("semestriel", 182, 20, 2.0),
    ("annuel", 365, 30, 1.0),
)

# Trois prélèvements : le minimum pour parler de régularité. Deux ne donnent
# qu'un seul écart, et un seul écart n'est jamais régulier — il est unique.
MINIMUM_PRELEVEMENTS = 3

# Part des écarts qui doivent tomber dans la tolérance. En dessous, la série
# n'est pas régulière : c'est un marchand fréquenté, pas un abonnement.
REGULARITE_MINIMALE = 0.6

# Dispersion maximale des montants, rapportée au montant médian. Un abonnement
# dont le prix a augmenté reste un abonnement : la hausse est signalée à part,
# et cette borne laisse passer une augmentation ordinaire.
DISPERSION_MAXIMALE = 0.25

# Au-delà de cette part d'une période sans prélèvement, l'abonnement est
# considéré comme arrêté. Une fois et demie laisse passer un décalage de
# facturation sans déclarer mort un abonnement bien vivant.
TOLERANCE_ARRET = 1.5


def _periode(ecarts):
    """La périodicité de la série, ou None si elle n'est pas régulière."""
    if not ecarts:
        return None
    centre = median(ecarts)
    for nom, jours, tolerance, par_an in PERIODES:
        if abs(centre - jours) > tolerance:
            continue
        dans_la_tolerance = sum(1 for e in ecarts if abs(e - jours) <= tolerance)
        if dans_la_tolerance >= REGULARITE_MINIMALE * len(ecarts):
            return nom, jours, par_an
    return None


def _dispersion(montants):
    """Écart des montants rapporté au médian. 0 quand ils sont identiques."""
    centre = median(montants)
    if centre <= 0:
        return 1.0
    return (max(montants) - min(montants)) / centre


def _augmentation(lignes):
    """La dernière hausse de prix, ou None.

    On compare le dernier montant au précédent qui en diffère : deux
    prélèvements consécutifs au même prix ne disent rien, c'est le changement
    qu'on cherche.
    """
    montants = [l["montant"] for l in lignes]
    dernier = montants[-1]
    for precedent in reversed(montants[:-1]):
        if abs(precedent - dernier) < 0.01:
            continue
        if dernier > precedent:
            return {
                "avant": round(precedent, 2),
                "apres": round(dernier, 2),
                "hausse": round(dernier - precedent, 2),
                "pct": round(100 * (dernier - precedent) / precedent, 1),
            }
        return None
    return None


def detecter(transactions, aujourdhui=None):
    """Les prélèvements récurrents trouvés dans ces transactions.

    `transactions` : des dictionnaires portant `date`, `description`, `amount`
    et `category`. Seuls les débits sont examinés — un abonnement sort de
    l'argent, par définition.
    """
    aujourdhui = aujourdhui or date.today()

    paquets = {}
    for t in transactions:
        montant = float(t.get("amount") or 0)
        if montant >= 0:
            continue
        d = parse_date(t.get("date"))
        if d is None:
            continue
        racine = racine_marchand(t.get("description") or "")
        if not racine:
            continue
        paquets.setdefault(racine, []).append({
            "date": d,
            "montant": -montant,
            "libelle": t.get("description") or "",
            "categorie": t.get("category") or "",
        })

    trouves = []
    for racine, lignes in paquets.items():
        if len(lignes) < MINIMUM_PRELEVEMENTS:
            continue
        lignes.sort(key=lambda l: l["date"])

        ecarts = [(b["date"] - a["date"]).days
                  for a, b in zip(lignes, lignes[1:])]
        # Deux prélèvements le même jour ne sont pas une période : c'est une
        # double facturation, ou deux achats distincts chez le même marchand.
        if any(e == 0 for e in ecarts):
            continue
        rythme = _periode(ecarts)
        if rythme is None:
            continue

        montants = [l["montant"] for l in lignes]
        if _dispersion(montants) > DISPERSION_MAXIMALE:
            continue

        nom, jours, par_an = rythme
        dernier = lignes[-1]
        prochain = dernier["date"] + timedelta(days=round(jours))
        retard = (aujourdhui - dernier["date"]).days
        actif = retard <= jours * TOLERANCE_ARRET

        trouves.append({
            "racine": racine,
            # Le libellé le plus court represente la série : c'est celui qui
            # porte le moins de details propres à un seul prélèvement.
            "libelle": min((l["libelle"] for l in lignes), key=len),
            "periodicite": nom,
            "nb": len(lignes),
            "montant": round(dernier["montant"], 2),
            "cout_annuel": round(dernier["montant"] * par_an, 2),
            "premier": iso(lignes[0]["date"]),
            "dernier": iso(dernier["date"]),
            "prochain": iso(prochain) if actif else None,
            "actif": actif,
            "jours_depuis": retard,
            "categorie": dernier["categorie"],
            "augmentation": _augmentation(lignes),
        })

    # Le plus cher à l'année d'abord : c'est celui sur lequel une décision
    # rapporte le plus. Les abonnements arrêtés passent derrière, ils
    # n'engagent plus rien.
    trouves.sort(key=lambda a: (not a["actif"], -a["cout_annuel"]))
    return trouves


def resume(abonnements):
    """Ce que l'ensemble coûte, et ce qui mérite un regard."""
    actifs = [a for a in abonnements if a["actif"]]
    annuel = round(sum(a["cout_annuel"] for a in actifs), 2)
    return {
        "nb": len(actifs),
        "nb_arretes": len(abonnements) - len(actifs),
        "cout_annuel": annuel,
        "cout_mensuel": round(annuel / 12, 2),
        "augmentations": [a for a in actifs if a["augmentation"]],
    }
