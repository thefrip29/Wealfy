"""Analyses : synthese, historique, conseils."""
from datetime import date

from flask import jsonify, request

from .. import advisor, finance, market, services
from ..db import get_setting, query, rows_to_list
from ._blueprint import bp
from ._helpers import as_date, as_int, month_param


@bp.get("/api/overview")
def overview():
    year, month = month_param()
    current = services.month_flows(year, month)
    previous_date = finance.add_months(date(year, month, 1), -1)
    previous = services.month_flows(previous_date.year, previous_date.month)
    # Le patrimoine est photographie a la fin du mois selectionne (ou aujourd'hui
    # si le mois est en cours), pour rester coherent avec les flux affiches.
    _, last_day = finance.month_bounds(year, month)
    as_of = min(last_day, date.today())
    snap = services.portfolio(as_of)
    metrics = services.metrics(as_of)
    repartition = services.repartition(as_of, snap)
    etat_marche = {
        "active": bool(get_setting("market_enabled", False)),
        "cache_perime": market.cache_is_stale(),
    }
    return jsonify({
        "as_of": finance.iso(as_of),
        # Observations factuelles, calculees sur ce qui vient d'etre mesure.
        "alertes": advisor.alertes(snap, metrics, repartition, etat_marche,
                                   at_date=as_of),
        "mois": current,
        "mois_precedent": previous,
        "variation_depenses": round(current["depenses"] - previous["depenses"], 2),
        "variation_depenses_pct": (
            round(100 * (current["depenses"] - previous["depenses"]) / previous["depenses"], 2)
            if previous["depenses"] else None
        ),
        "metrics": metrics,
        "repartition": repartition,
        # Repartition reelle par famille d'actifs, a ne pas confondre avec
        # `repartition` ci-dessus, qui compare des poches a une cible choisie.
        # Celle-ci ne decrit que ce qui est detenu, sans jugement.
        "patrimoine_par_famille": _par_famille(snap),
        "patrimoine_serie": services.net_worth_series(12, as_of),
        # Douze mois et non six : la courbe de depenses a besoin d'une annee
        # pleine pour montrer une saison. L'histogramme n'en affiche que les
        # six derniers, cote interface.
        "depenses_serie": services.expense_series(12, as_of),
    })


def _par_famille(snap):
    """Somme des actifs par famille, la plus grosse d'abord.

    Les valeurs nulles ou negatives sont ecartees : une part de camembert ne
    peut pas etre negative, et une famille a zero n'apprend rien.
    """
    totaux = {}
    for asset in snap["assets"]:
        valeur = asset.get("valeur") or 0
        if valeur <= 0:
            continue
        totaux[asset["famille"]] = totaux.get(asset["famille"], 0) + valeur
    return [
        {"famille": famille, "montant": round(montant, 2)}
        for famille, montant in sorted(totaux.items(), key=lambda kv: -kv[1])
    ]


@bp.get("/api/history")
def history():
    limit = as_int(request.args.get("limit"), None)
    return jsonify({
        "archive": list(reversed(services.monthly_archive(limit))),
        "imports": rows_to_list(query("SELECT * FROM imports ORDER BY date_import DESC")),
    })


@bp.get("/api/metrics")
def metrics_endpoint():
    return jsonify(services.metrics(as_date(request.args.get("date"))))


@bp.get("/api/month")
def month_endpoint():
    year, month = month_param()
    return jsonify(services.month_flows(year, month))


@bp.get("/api/expenses/series")
def expense_series_endpoint():
    return jsonify(services.expense_series(as_int(request.args.get("months"), 6)))


@bp.get("/api/assets/series")
def assets_series_endpoint():
    """Trajectoire de chaque actif : d'ou vient le patrimoine, pas seulement
    combien il vaut."""
    return jsonify(services.assets_series(
        as_int(request.args.get("months"), 12),
        as_date(request.args.get("date")),
    ))
