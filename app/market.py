"""Cours de marché : fournisseurs, cache, et valorisation en direct.

**C'est le seul module du projet qui fait des appels réseau**, et uniquement
depuis `refresh_quotes()` / `test_symbol()` / `fetch_series()`, jamais depuis un
chemin de lecture. `portfolio()`, `metrics()` et l'archive mensuelle ne lisent
que le cache local : l'application reste entièrement utilisable hors ligne.

Ce qui sort de la machine quand `market_enabled` est vrai : les symboles
interrogés et la clé API. Ni les montants, ni les quantités, ni les
transactions. Un symbole répété renseigne malgré tout sur la composition du
portefeuille — c'est pour cela que le réglage est désactivé par défaut.
"""
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

from . import finance
from .db import execute, get_setting, new_id, query, rows_to_list, set_setting

TIMEOUT = 8
USER_AGENT = "Wealfy/1.0 (application locale)"

TWELVE_DATA_BASE = "https://api.twelvedata.com"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
FRANKFURTER_BASE = "https://api.frankfurter.app"
INSEE_SDMX = "https://bdm.insee.fr/series/sdmx/data/SERIES_BDM"

MARKET_ASSET_TYPES = {"PEA", "CTO", "AssuranceVie", "PER"}
CRYPTO_ASSET_TYPES = {"Crypto"}
RATE_ASSET_TYPES = {"Livret", "LDDS", "LEP", "LivretJeune", "PEL", "CEL", "DepotTerme"}
INDEXED_ASSET_TYPES = {"Immobilier", "SCPI"}


class MarketError(Exception):
    """Erreur fonctionnelle remontée à l'utilisateur, jamais une trace Python."""


# ==========================================================================
# Transport
# ==========================================================================

def _get_json(url, params=None):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT,
                                    context=ssl.create_default_context()) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise MarketError(f"HTTP {exc.code} sur {urllib.parse.urlsplit(url).netloc}") from exc
    except urllib.error.URLError as exc:
        raise MarketError(f"Reseau indisponible ({exc.reason})") from exc
    except (TimeoutError, OSError) as exc:
        raise MarketError(f"Connexion impossible ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise MarketError("Reponse illisible du fournisseur") from exc


def _get_text(url, params=None):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT,
                                    context=ssl.create_default_context()) as response:
            return response.read().decode("utf-8")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        raise MarketError(f"Appel impossible ({exc})") from exc


# ==========================================================================
# Fournisseurs
# ==========================================================================

class Provider:
    """Interface commune. `quotes` renvoie {clé: {price, currency, date}}."""

    name = "offline"
    needs_key = False

    def quotes(self, items):
        raise NotImplementedError

    def fx(self, base, quote="EUR"):
        return None

    def series(self, symbol, start, end):
        return []


class OfflineProvider(Provider):
    """Fournisseur par défaut : ne sort jamais de la machine.

    Utilisé quand `market_enabled` est faux, et par les tests.
    """

    name = "offline"

    def quotes(self, items):
        return {}, [{"cle": i.get("cle"), "erreur": "Cours de marche desactives"}
                    for i in items]


class TwelveData(Provider):
    """Titres cotés et taux de change. Clé gratuite requise."""

    name = "twelvedata"
    needs_key = True

    def __init__(self, api_key):
        self.api_key = (api_key or "").strip()
        if not self.api_key:
            raise MarketError("Cle API Twelve Data manquante.")

    def _quote_one(self, item):
        params = {"symbol": item["symbol"], "apikey": self.api_key}
        if item.get("exchange"):
            params["exchange"] = item["exchange"]
        payload = _get_json(f"{TWELVE_DATA_BASE}/quote", params)
        # Twelve Data renvoie 200 avec {"code": 4xx, "message": "..."} en erreur.
        if isinstance(payload, dict) and payload.get("status") == "error":
            raise MarketError(payload.get("message") or "Symbole inconnu")
        if not isinstance(payload, dict) or payload.get("close") in (None, ""):
            raise MarketError("Aucun cours renvoye pour ce symbole")
        return {
            "price": float(payload["close"]),
            "currency": (payload.get("currency") or "EUR").upper(),
            "date": (payload.get("datetime") or date.today().isoformat())[:10],
            "label": payload.get("name"),
            "exchange": payload.get("exchange"),
        }

    def quotes(self, items):
        found, errors = {}, []
        for item in items:
            try:
                found[item["cle"]] = self._quote_one(item)
            except MarketError as exc:
                errors.append({"cle": item["cle"], "symbole": item.get("symbol"),
                               "erreur": str(exc)})
        return found, errors

    def fx(self, base, quote="EUR"):
        if base == quote:
            return 1.0
        try:
            payload = _get_json(f"{TWELVE_DATA_BASE}/exchange_rate",
                                {"symbol": f"{base}/{quote}", "apikey": self.api_key})
            if payload.get("rate"):
                return float(payload["rate"])
        except MarketError:
            pass
        # Repli BCE (Frankfurter), sans cle.
        try:
            payload = _get_json(f"{FRANKFURTER_BASE}/latest", {"from": base, "to": quote})
            rate = (payload.get("rates") or {}).get(quote)
            return float(rate) if rate else None
        except MarketError:
            return None

    def series(self, symbol, start, end):
        params = {
            "symbol": symbol, "interval": "1day", "apikey": self.api_key,
            "start_date": finance.iso(start), "end_date": finance.iso(end),
            "outputsize": 5000, "order": "ASC",
        }
        payload = _get_json(f"{TWELVE_DATA_BASE}/time_series", params)
        if payload.get("status") == "error":
            raise MarketError(payload.get("message") or "Serie indisponible")
        return [
            (finance.parse_date(row["datetime"]), float(row["close"]))
            for row in payload.get("values", [])
            if row.get("close") not in (None, "")
        ]


class CoinGecko(Provider):
    """Crypto. Gratuit, sans clé, cote directement en EUR."""

    name = "coingecko"

    def quotes(self, items):
        ids = [i["symbol"] for i in items if i.get("symbol")]
        if not ids:
            return {}, []
        try:
            payload = _get_json(f"{COINGECKO_BASE}/simple/price",
                                {"ids": ",".join(sorted(set(ids))), "vs_currencies": "eur"})
        except MarketError as exc:
            return {}, [{"cle": i["cle"], "erreur": str(exc)} for i in items]
        found, errors = {}, []
        today = date.today().isoformat()
        for item in items:
            entry = payload.get(item["symbol"]) or {}
            if entry.get("eur") is None:
                errors.append({"cle": item["cle"], "symbole": item.get("symbol"),
                               "erreur": "Identifiant CoinGecko inconnu"})
                continue
            found[item["cle"]] = {
                "price": float(entry["eur"]), "currency": "EUR", "date": today,
            }
        return found, errors


def search_instruments(query, kind="titre", api_key=None, limit=25):
    """Recherche un instrument chez le fournisseur. Reseau.

    On interroge le fournisseur plutot que de livrer un catalogue en dur :
    un ISIN ou un ticker recopie de memoire serait faux, et produirait une
    valorisation fausse en silence. Ici, le symbole vient de la source qui
    servira ensuite a le coter.
    """
    query = (query or "").strip()
    if len(query) < 2:
        raise MarketError("Saisissez au moins deux caracteres.")

    if kind == "crypto":
        payload = _get_json(f"{COINGECKO_BASE}/search", {"query": query})
        out = []
        for coin in (payload.get("coins") or [])[:limit]:
            out.append({
                "kind": "crypto",
                "ticker": coin.get("id"),
                "symbol": coin.get("id"),
                "label": coin.get("name"),
                "code": (coin.get("symbol") or "").upper(),
                "exchange": "CoinGecko",
                "currency": "EUR",
                "rang": coin.get("market_cap_rank"),
            })
        return out

    key = (api_key if api_key is not None else get_setting("market_api_key", "")) or ""
    params = {"symbol": query, "outputsize": limit}
    if key.strip():
        params["apikey"] = key.strip()
    payload = _get_json(f"{TWELVE_DATA_BASE}/symbol_search", params)
    if isinstance(payload, dict) and payload.get("status") == "error":
        raise MarketError(payload.get("message") or "Recherche indisponible")
    out = []
    for row in (payload.get("data") or [])[:limit]:
        out.append({
            "kind": "titre",
            "ticker": row.get("symbol"),
            "symbol": row.get("symbol"),
            "label": row.get("instrument_name"),
            "code": row.get("symbol"),
            "exchange": row.get("exchange"),
            "mic": row.get("mic_code"),
            "pays": row.get("country"),
            "currency": (row.get("currency") or "EUR").upper(),
            "type": row.get("instrument_type"),
        })
    return out


def build_provider(name=None, api_key=None):
    """Fabrique le fournisseur configuré. Ne fait aucun appel réseau."""
    if not get_setting("market_enabled", False):
        return OfflineProvider()
    name = (name or get_setting("market_provider", "twelvedata") or "").lower()
    if name == "twelvedata":
        return TwelveData(api_key if api_key is not None else get_setting("market_api_key", ""))
    if name == "coingecko":
        return CoinGecko()
    return OfflineProvider()


# ==========================================================================
# Cache
# ==========================================================================

def store_quote(symbol, source, quote_date, price, currency="EUR"):
    execute(
        "INSERT INTO quotes(symbol, source, date, price, currency, fetched_at) "
        "VALUES (?,?,?,?,?,datetime('now')) "
        "ON CONFLICT(symbol, source, date) DO UPDATE SET "
        "price = excluded.price, currency = excluded.currency, fetched_at = excluded.fetched_at",
        (symbol, source, finance.iso(quote_date), round(float(price), 6), currency),
    )


def cached_prices(at_date=None):
    """Dernier cours connu par clé, à la date demandée ou avant.

    Lecture pure : aucun appel réseau. C'est ce que consomment `portfolio()`
    et tous les calculs.
    """
    at_date = finance.iso(finance.parse_date(at_date) or date.today())
    rows = query(
        "SELECT symbol, price, currency, date, fetched_at FROM quotes "
        "WHERE date <= ? ORDER BY symbol, date DESC",
        (at_date,),
    )
    out = {}
    for row in rows:
        if row["symbol"] in out:
            continue  # la premiere ligne rencontree est la plus recente
        out[row["symbol"]] = {
            "price": float(row["price"]), "currency": row["currency"],
            "date": row["date"], "fetched_at": row["fetched_at"],
        }
    return out


def cache_is_stale():
    last = get_setting("market_last_refresh")
    if not last:
        return True
    ttl = float(get_setting("market_cache_ttl_hours", 24) or 24)
    try:
        stamp = datetime.fromisoformat(str(last))
    except ValueError:
        return True
    return datetime.now() - stamp > timedelta(hours=ttl)


# ==========================================================================
# Correspondance ticker -> symbole fournisseur
# ==========================================================================

def securities_by_ticker():
    return {row["ticker"]: row for row in rows_to_list(query("SELECT * FROM securities"))}


def known_tickers():
    """Tickers réellement présents dans les mouvements, avec leur actif."""
    rows = query(
        "SELECT DISTINCT m.ticker, a.type FROM asset_movements m "
        "JOIN assets a ON a.id = m.asset_id "
        "WHERE m.ticker IS NOT NULL AND trim(m.ticker) <> ''"
    )
    return [(row["ticker"], row["type"]) for row in rows]


def upsert_security(ticker, **fields):
    # `currency` est NOT NULL : un champ laisse vide par l'interface ne doit pas
    # ecraser la valeur existante par NULL.
    if fields.get("currency"):
        fields["currency"] = str(fields["currency"]).upper()
    else:
        fields.pop("currency", None)
    if not fields.get("kind"):
        fields.pop("kind", None)
    existing = query("SELECT id FROM securities WHERE ticker = ?", (ticker,), one=True)
    columns = ["symbol", "exchange", "currency", "isin", "label",
               "benchmark_symbol", "benchmark_label", "kind"]
    if existing:
        sets, args = [], []
        for column in columns:
            if column in fields:
                sets.append(f"{column} = ?")
                args.append(fields[column])
        if sets:
            args.append(existing["id"])
            execute(f"UPDATE securities SET {', '.join(sets)} WHERE id = ?", args)
        return existing["id"]
    sid = new_id()
    execute(
        "INSERT INTO securities(id, ticker, symbol, exchange, currency, isin, label, "
        "benchmark_symbol, benchmark_label, kind) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            sid, ticker, fields.get("symbol") or ticker, fields.get("exchange"),
            (fields.get("currency") or "EUR").upper(), fields.get("isin"),
            fields.get("label"), fields.get("benchmark_symbol"),
            fields.get("benchmark_label"), fields.get("kind") or "titre",
        ),
    )
    return sid


# ==========================================================================
# Rafraîchissement (le seul chemin réseau)
# ==========================================================================

def refresh_quotes(provider=None, crypto_provider=None):
    """Rafraîchit les cours de toutes les lignes connues et des cryptos.

    Ne lève jamais : renvoie un compte rendu que l'interface affiche.
    """
    if not get_setting("market_enabled", False):
        return {"ok": 0, "ko": 0, "erreurs": [], "desactive": True}

    provider = provider or build_provider()
    securities = securities_by_ticker()

    # --- titres cotés et cryptos, séparés par leur fournisseur
    items, coin_items, non_mappes = [], [], []
    for ticker, asset_type in known_tickers():
        if asset_type not in MARKET_ASSET_TYPES and asset_type not in CRYPTO_ASSET_TYPES:
            continue
        sec = securities.get(ticker)
        if not sec or not sec.get("symbol"):
            non_mappes.append(ticker)
            continue
        entry = {"cle": ticker, "symbol": sec["symbol"], "exchange": sec.get("exchange")}
        if sec.get("kind") == "crypto" or asset_type in CRYPTO_ASSET_TYPES:
            coin_items.append(entry)
        else:
            items.append(entry)

    found, errors = ({}, []) if not items else provider.quotes(items)

    # --- conversion de devise
    fx_cache = {"EUR": 1.0}
    for cle, quote in list(found.items()):
        currency = (quote.get("currency") or "EUR").upper()
        if currency not in fx_cache:
            rate = provider.fx(currency, "EUR")
            fx_cache[currency] = rate
            if rate:
                store_quote(f"FX:{currency}EUR", provider.name, date.today(), rate, "EUR")
        rate = fx_cache.get(currency)
        if not rate:
            errors.append({"cle": cle, "erreur": f"Taux {currency}/EUR indisponible"})
            found.pop(cle)
            continue
        quote["price_eur"] = round(quote["price"] * rate, 6)

    # --- cryptos : positions choisies + repli sur l'ancien champ metadata
    for row in query("SELECT id, metadata FROM assets WHERE type = 'Crypto' "
                     "AND archived = 0"):
        meta = json.loads(row["metadata"] or "{}")
        coin = (meta.get("coingecko_id") or "").strip()
        if coin and not any(i["symbol"] == coin for i in coin_items):
            coin_items.append({"cle": coin, "symbol": coin})
    if coin_items:
        crypto_provider = crypto_provider or CoinGecko()
        coins_found, coins_errors = crypto_provider.quotes(coin_items)
        for _cle, quote in coins_found.items():
            quote["price_eur"] = quote["price"]   # CoinGecko cote deja en EUR
        found.update(coins_found)
        errors.extend(coins_errors)

    # --- écriture du cache
    for cle, quote in found.items():
        store_quote(cle, provider.name, quote.get("date") or date.today(),
                    quote.get("price_eur", quote["price"]), "EUR")

    for ticker in non_mappes:
        errors.append({"cle": ticker,
                       "erreur": "Aucune correspondance de symbole definie"})
    non_mappes = sorted(set(non_mappes))

    result = {
        "ok": len(found), "ko": len(errors), "erreurs": errors[:40],
        "non_mappes": non_mappes, "fournisseur": provider.name,
        "horodatage": datetime.now().isoformat(timespec="seconds"),
    }
    set_setting("market_last_refresh", result["horodatage"])
    set_setting("market_last_result", {k: result[k] for k in ("ok", "ko", "fournisseur")})
    return result


def test_symbol(symbol, exchange=None, provider=None):
    """Vérifie qu'un symbole est bien coté. C'est l'outil de vérification de
    couverture Euronext exigé par le cahier des charges."""
    provider = provider or build_provider()
    if isinstance(provider, OfflineProvider):
        raise MarketError("Activez d'abord les cours de marche dans les parametres.")
    found, errors = provider.quotes([{"cle": symbol, "symbol": symbol, "exchange": exchange}])
    if symbol in found:
        quote = found[symbol]
        return {"ok": True, "symbole": symbol, **quote}
    message = errors[0]["erreur"] if errors else "Symbole introuvable"
    return {"ok": False, "symbole": symbol, "erreur": message}


# ==========================================================================
# Valorisation (calcul pur, sans réseau — testable hors ligne)
# ==========================================================================

def line_values(movements, securities, prices):
    """Valeur de marché ligne par ligne, à partir des quantités détenues."""
    out = []
    for ligne in finance.pru_par_ligne(movements):
        ticker = ligne["ticker"]
        quote = prices.get(ticker)
        sec = securities.get(ticker) or {}
        price = quote["price"] if quote else None
        quantite = ligne["quantite"]
        out.append({
            **ligne,
            "symbole": sec.get("symbol"),
            "libelle": sec.get("label"),
            "cours": price,
            "cours_date": quote["date"] if quote else None,
            "valeur": round(quantite * price, 2) if (price and quantite) else None,
            "plus_value": (
                round((price - ligne["pru"]) * quantite, 2)
                if price and quantite and ligne["pru"] else None
            ),
            "ecart_pru_pct": (
                round(100 * (price / ligne["pru"] - 1), 2)
                if price and ligne["pru"] else None
            ),
        })
    return out


def market_value(asset, movements, securities, prices):
    """Valeur de marché d'un actif, ou None si elle ne peut pas être complète.

    Titres et cryptos suivent le même chemin : des positions (ticker + quantité)
    valorisées ligne par ligne. Le `None` est délibéré — mieux vaut retomber sur
    la valeur saisie que d'afficher un total partiel comme s'il était complet.
    """
    asset_type = asset["type"]
    if asset_type not in MARKET_ASSET_TYPES and asset_type not in CRYPTO_ASSET_TYPES:
        return None

    lignes = [l for l in line_values(movements, securities, prices)
              if (l["quantite"] or 0) > 0]
    if lignes:
        if any(l["valeur"] is None for l in lignes):
            return None  # une ligne non cotee => on ne fabrique pas un total faux
        return round(sum(l["valeur"] for l in lignes), 2)

    # Repli pour les cryptos saisies avant l'arrivee des positions : un seul
    # coin decrit dans les metadonnees de l'actif.
    if asset_type in CRYPTO_ASSET_TYPES:
        meta = asset.get("metadata") or {}
        coin = (meta.get("coingecko_id") or "").strip()
        quantite = meta.get("quantite")
        quote = prices.get(coin) or prices.get(f"COIN:{asset['id']}")
        if coin and quote and quantite not in (None, ""):
            return round(float(quantite) * quote["price"], 2)
    return None


def rate_value(asset, movements, at_date=None):
    """Livrets et dépôts à terme : capital + intérêts courus au taux saisi."""
    meta = asset.get("metadata") or {}
    taux = meta.get("taux_annuel")
    if taux in (None, ""):
        return None
    try:
        taux = float(taux)
    except (TypeError, ValueError):
        return None
    return finance.valeur_livret(asset, movements, taux, at_date)


def indexed_value(asset, at_date=None):
    """Immobilier : réévaluation par indice, ou par taux annuel manuel."""
    meta = asset.get("metadata") or {}
    at_date = finance.parse_date(at_date) or date.today()
    acquisition = finance.parse_date(asset["date_acquisition"])
    base = float(asset["valeur_acquisition"] or 0)
    if not acquisition or base <= 0:
        return None

    idbank = (meta.get("indice_insee") or "").strip()
    if idbank:
        serie = cached_index(idbank)
        debut = _index_at(serie, acquisition)
        fin = _index_at(serie, at_date)
        if debut and fin:
            return round(base * fin / debut, 2)

    taux = meta.get("taux_revalorisation_annuel")
    if taux in (None, ""):
        return None
    try:
        taux = float(taux) / 100.0
    except (TypeError, ValueError):
        return None
    annees = (at_date - acquisition).days / 365.25
    return round(base * (1 + taux) ** annees, 2)


def _index_at(serie, at_date):
    """Dernière valeur d'indice connue à cette date."""
    best = None
    for point_date, value in sorted(serie):
        if point_date <= at_date:
            best = value
        else:
            break
    return best


def cached_index(idbank):
    """Série d'indice en cache (lecture pure)."""
    rows = query(
        "SELECT date, price FROM quotes WHERE symbol = ? ORDER BY date",
        (f"INSEE:{idbank}",),
    )
    return [(finance.parse_date(r["date"]), float(r["price"])) for r in rows]


def refresh_index(idbank):
    """Télécharge une série INSEE (SDMX) et la met en cache. Réseau."""
    if not get_setting("market_enabled", False):
        raise MarketError("Activez d'abord les cours de marche dans les parametres.")
    xml = _get_text(f"{INSEE_SDMX}/{idbank}")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise MarketError("Reponse INSEE illisible") from exc

    points = 0
    for obs in root.iter():
        if not obs.tag.endswith("Obs"):
            continue
        period = obs.get("TIME_PERIOD")
        value = obs.get("OBS_VALUE")
        if not period or value in (None, ""):
            continue
        parsed = _parse_insee_period(period)
        if not parsed:
            continue
        try:
            store_quote(f"INSEE:{idbank}", "insee", parsed, float(value), "IDX")
            points += 1
        except (TypeError, ValueError):
            continue
    if points == 0:
        raise MarketError(f"Aucune observation trouvee pour l'idbank {idbank}")
    return {"idbank": idbank, "points": points}


def _parse_insee_period(period):
    """'2024-Q1', '2024-01' ou '2024' -> date de début de période."""
    period = period.strip()
    try:
        if "Q" in period.upper():
            year, quarter = period.upper().split("-Q")
            return date(int(year), 3 * (int(quarter) - 1) + 1, 1)
        parts = period.split("-")
        if len(parts) == 2:
            return date(int(parts[0]), int(parts[1]), 1)
        if len(parts) == 1 and len(parts[0]) == 4:
            return date(int(parts[0]), 1, 1)
        return finance.parse_date(period)
    except (ValueError, TypeError):
        return None


# ==========================================================================
# Comparaison à l'indice de référence
# ==========================================================================

def benchmark_comparison(asset, movements, securities, provider=None):
    """Performance de chaque ligne face à son indice, rebasée à 100."""
    provider = provider or build_provider()
    if isinstance(provider, OfflineProvider):
        raise MarketError("Activez d'abord les cours de marche dans les parametres.")

    dates = [finance.parse_date(m["date"]) for m in movements if m.get("date")]
    start = min([d for d in dates if d], default=None) or finance.parse_date(
        asset["date_acquisition"])
    if not start:
        raise MarketError("Aucune date de depart exploitable.")
    end = date.today()

    out = []
    for ligne in finance.pru_par_ligne(movements):
        sec = securities.get(ligne["ticker"]) or {}
        symbol, benchmark = sec.get("symbol"), sec.get("benchmark_symbol")
        if not symbol or not benchmark:
            continue
        try:
            serie_ligne = provider.series(symbol, start, end)
            serie_indice = provider.series(benchmark, start, end)
        except MarketError as exc:
            out.append({"ticker": ligne["ticker"], "erreur": str(exc)})
            continue
        if len(serie_ligne) < 2 or len(serie_indice) < 2:
            out.append({"ticker": ligne["ticker"], "erreur": "Historique insuffisant"})
            continue
        out.append({
            "ticker": ligne["ticker"],
            "symbole": symbol,
            "indice": benchmark,
            "indice_label": sec.get("benchmark_label") or benchmark,
            "serie_ligne": _rebase(serie_ligne),
            "serie_indice": _rebase(serie_indice),
            "perf_ligne": _perf(serie_ligne),
            "perf_indice": _perf(serie_indice),
            "ecart": round(_perf(serie_ligne) - _perf(serie_indice), 2),
        })
    return {"debut": finance.iso(start), "fin": finance.iso(end), "lignes": out}


def _rebase(serie):
    base = serie[0][1]
    if not base:
        return []
    return [{"date": finance.iso(d), "valeur": round(100 * v / base, 3)} for d, v in serie]


def _perf(serie):
    base, last = serie[0][1], serie[-1][1]
    return round(100 * (last / base - 1), 2) if base else 0.0
