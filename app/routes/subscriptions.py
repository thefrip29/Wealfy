"""Abonnements et prelevements recurrents."""
from flask import jsonify, request

from .. import abonnements
from ..db import get_setting, query, rows_to_list
from ._blueprint import bp
from ._helpers import as_int

# Deux ans : assez pour qu'un abonnement annuel se manifeste trois fois, ce qui
# est le minimum pour parler de regularite.
MOIS_PAR_DEFAUT = 24


@bp.get("/api/subscriptions")
def detect_subscriptions():
    """Les prelevements recurrents trouves dans l'historique.

    Les virements entre vos propres comptes sont ecartes : un versement mensuel
    sur un livret est parfaitement regulier et parfaitement stable, donc
    indiscernable d'un abonnement par les seuls chiffres. Ce n'en est pas un,
    et le compter gonflerait le total annuel d'une somme qui reste chez vous.
    """
    trouves = detecter_depuis_la_base(as_int(request.args.get("mois"), MOIS_PAR_DEFAUT))
    return jsonify({"abonnements": trouves, **abonnements.resume(trouves)})


def detecter_depuis_la_base(mois=MOIS_PAR_DEFAUT):
    """Abonnements de l'historique. Partage avec les observations."""
    neutres = set(get_setting("categories_transfert", []) or [])
    neutres |= set(get_setting("categories_non_depense", []) or [])

    lignes = rows_to_list(query(
        "SELECT date, description, amount, category FROM transactions "
        "WHERE amount < 0 AND date >= date('now', ?) ORDER BY date",
        (f"-{int(mois)} months",),
    ))
    lignes = [l for l in lignes if (l["category"] or "") not in neutres]
    return abonnements.detecter(lignes)
