"""Cours de marche : rafraichissement et etat du service."""
from flask import jsonify, request

from .. import market
from ..db import get_setting, query, rows_to_list
from ._blueprint import bp
from ._helpers import body, fail


# Deux routes seulement sortent sur le reseau (avec les deux routes de test) :
# `POST /api/market/refresh` et `POST /api/fx/refresh`. Toutes les routes de
# LECTURE de ce module ne touchent que le cache local.
#
# La seconde est de loin la moins bavarde : elle envoie une paire de devises,
# « EUR/USD », et rien d'autre. Les symboles interroges par la premiere
# renseignent sur la composition du portefeuille ; une paire de devises ne dit
# rien de personne.


@bp.get("/api/market/status")
def market_status():
    enabled = bool(get_setting("market_enabled", False))
    securities = rows_to_list(query("SELECT * FROM securities ORDER BY ticker"))
    mapped = {s["ticker"] for s in securities if s["symbol"]}
    # Un support non cote n'a pas de symbole a mapper : le signaler comme « a
    # faire » enverrait l'utilisateur chercher une correspondance inexistante.
    mapped |= {s["ticker"] for s in securities if s["kind"] == market.NON_COTE}
    tickers = market.known_tickers()
    non_mappes = sorted({t for t, atype in tickers
                         if atype in market.MARKET_ASSET_TYPES and t not in mapped})
    prices = market.cached_prices()
    return jsonify({
        "active": enabled,
        "fournisseur": get_setting("market_provider", "twelvedata"),
        "cle_configuree": bool((get_setting("market_api_key", "") or "").strip()),
        "auto_refresh": bool(get_setting("market_auto_refresh", True)),
        "ttl_heures": get_setting("market_cache_ttl_hours", 24),
        "dernier_refresh": get_setting("market_last_refresh"),
        "dernier_resultat": get_setting("market_last_result"),
        "cache_perime": market.cache_is_stale(),
        "nb_cours_en_cache": len(prices),
        "tickers_non_mappes": non_mappes,
        "securities": securities,
    })


@bp.get("/api/fx")
def fx_display_rates():
    """Les taux de change en cache, pour relire le patrimoine dans une autre
    devise.

    Lecture pure : ces taux sont poses par `POST /api/market/refresh`, la seule
    route qui sorte sur le reseau. Un taux absent n'est pas une erreur, c'est
    un « pas encore releve » que l'interface sait dire.
    """
    return jsonify({
        "devises": [market.taux_affichage(c) for c in market.DEVISES_AFFICHAGE],
    })


@bp.post("/api/fx/refresh")
def fx_refresh():
    """Releve le taux de change du moment.

    Appelee quand on quitte l'euro a l'ecran. L'affichage ne l'attend pas : il
    bascule avec le dernier taux connu et se corrige si un plus frais arrive,
    pour qu'un changement de devise ne donne jamais l'impression d'attendre le
    reseau.
    """
    if not get_setting("market_enabled", False):
        return fail("Les cours de marche sont desactives.", 409)
    try:
        provider = market.build_provider()
    except market.MarketError as exc:
        return fail(str(exc))
    return jsonify({"devises": market.rafraichir_taux(provider)})


@bp.post("/api/market/refresh")
def market_refresh():
    if not get_setting("market_enabled", False):
        return fail("Les cours de marche sont desactives.", 409)
    try:
        provider = market.build_provider()
    except market.MarketError as exc:
        return fail(str(exc))
    return jsonify(market.refresh_quotes(provider))


@bp.post("/api/market/test")
def market_test():
    data = body()
    symbol = (data.get("symbol") or "").strip()
    if not symbol:
        return fail("Symbole requis.")
    try:
        return jsonify(market.test_symbol(symbol, (data.get("exchange") or "").strip() or None))
    except market.MarketError as exc:
        return fail(str(exc))


@bp.post("/api/market/index/refresh")
def market_index_refresh():
    idbank = (body().get("idbank") or "").strip()
    if not idbank:
        return fail("Identifiant de serie (idbank) requis.")
    try:
        return jsonify(market.refresh_index(idbank))
    except market.MarketError as exc:
        return fail(str(exc))


@bp.get("/api/market/search")
def market_search():
    """Recherche un ETF/action (Twelve Data) ou une crypto (CoinGecko)."""
    kind = "crypto" if request.args.get("type") == "crypto" else "titre"
    if kind == "titre" and not get_setting("market_enabled", False):
        return fail("Activez les cours de marche pour rechercher un titre.", 409)
    try:
        return jsonify({
            "resultats": market.search_instruments(request.args.get("q"), kind),
            "kind": kind,
        })
    except market.MarketError as exc:
        return fail(str(exc))
