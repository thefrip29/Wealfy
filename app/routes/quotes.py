"""Cours de marche : rafraichissement et etat du service."""
from flask import jsonify, request

from .. import market
from ..db import get_setting, query, rows_to_list
from ._blueprint import bp
from ._helpers import body, fail


# Seul `POST /api/market/refresh` (et les deux routes de test) sortent sur le
# reseau : c'est le seul acces exterieur de toute l'application. Les routes de
# lecture de ce module ne touchent que le cache local.


@bp.get("/api/market/status")
def market_status():
    enabled = bool(get_setting("market_enabled", False))
    securities = rows_to_list(query("SELECT * FROM securities ORDER BY ticker"))
    mapped = {s["ticker"] for s in securities if s["symbol"]}
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
