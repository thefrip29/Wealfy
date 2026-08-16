"""Tests de la valorisation en direct.

Aucun test ne touche au réseau : les fournisseurs sont remplacés par des
doublures. Un test vérifie explicitement qu'aucun chemin de lecture n'appelle
un fournisseur.
"""
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, finance, market  # noqa: E402


class FakeProvider(market.Provider):
    """Renvoie des cours en dur et compte ses appels."""

    name = "fake"

    def __init__(self, prices=None, fx_rate=1.0):
        self.prices = prices or {}
        self.fx_rate = fx_rate
        self.calls = 0

    def quotes(self, items):
        self.calls += 1
        found, errors = {}, []
        for item in items:
            entry = self.prices.get(item["symbol"])
            if entry is None:
                errors.append({"cle": item["cle"], "erreur": "inconnu"})
                continue
            price, currency = entry if isinstance(entry, tuple) else (entry, "EUR")
            found[item["cle"]] = {
                "price": price, "currency": currency, "date": date.today().isoformat(),
            }
        return found, errors

    def fx(self, base, quote="EUR"):
        self.calls += 1
        return 1.0 if base == quote else self.fx_rate

    def series(self, symbol, start, end):
        self.calls += 1
        return [(start, 100.0), (end, 100.0 * (1 + self.prices.get(f"perf:{symbol}", 0.1)))]


class MarketTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.db_path)
        self.app = create_app(self.db_path)
        self.client = self.app.test_client()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def post(self, url, payload):
        res = self.client.post(url, json=payload)
        self.assertIn(res.status_code, (200, 201), res.get_data(as_text=True))
        return res.get_json()

    def get(self, url):
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        return res.get_json()

    def enable_market(self, key="fake-key"):
        self.client.put("/api/settings", json={
            "market_enabled": True, "market_api_key": key,
        })

    def seed_pea(self):
        pea = self.post("/api/assets", {
            "type": "PEA", "label": "PEA", "date_acquisition": "2024-01-02",
            "valeur_acquisition": 0,
        })
        self.post(f"/api/assets/{pea['id']}/movements", {
            "date": "2024-01-05", "montant": 1000, "type": "versement",
            "ticker": "IE00B4L5Y983", "quantite": 10, "prix_unitaire": 100,
        })
        self.post("/api/securities", {
            "ticker": "IE00B4L5Y983", "symbol": "CW8", "exchange": "Euronext",
            "currency": "EUR",
        })
        return pea


class TestDisabledByDefault(MarketTestCase):
    def test_market_is_off_and_silent(self):
        status = self.get("/api/market/status")
        self.assertFalse(status["active"])
        self.assertFalse(status["cle_configuree"])

    def test_refresh_refused_when_disabled(self):
        res = self.client.post("/api/market/refresh")
        self.assertEqual(res.status_code, 409)

    def test_offline_provider_is_used_when_disabled(self):
        with self.app.app_context():
            self.assertIsInstance(market.build_provider(), market.OfflineProvider)

    def test_values_unchanged_when_disabled(self):
        pea = self.seed_pea()
        self.client.put(f"/api/assets/{pea['id']}", json={"valeur_actuelle": 1234})
        snap = self.get("/api/assets")
        asset = snap["assets"][0]
        self.assertEqual(asset["valeur"], 1234.0)
        self.assertEqual(asset["valeur_source"], "saisie")


class TestNoNetworkOnReadPaths(MarketTestCase):
    def test_read_routes_never_call_the_provider(self):
        """Garde-fou central : aucune lecture ne doit sortir sur le reseau."""
        self.enable_market()
        self.seed_pea()
        spy = FakeProvider({"CW8": 120.0})
        with self.app.app_context():
            market.refresh_quotes(spy)
        calls_after_refresh = spy.calls
        self.assertGreater(calls_after_refresh, 0)

        for url in ("/api/assets", "/api/overview", "/api/history",
                    "/api/metrics", "/api/month"):
            self.get(url)
        self.assertEqual(spy.calls, calls_after_refresh,
                         "un chemin de lecture a appele le fournisseur")


class TestLiveValuation(MarketTestCase):
    def test_pea_valued_from_lines(self):
        self.enable_market()
        pea = self.seed_pea()
        with self.app.app_context():
            result = market.refresh_quotes(FakeProvider({"CW8": 120.0}))
        self.assertEqual(result["ok"], 1)

        detail = self.get(f"/api/assets/{pea['id']}")
        self.assertEqual(detail["asset"]["valeur"], 1200.0)     # 10 x 120
        self.assertEqual(detail["asset"]["valeur_source"], "marche")
        self.assertEqual(detail["asset"]["valeur_saisie"], 1000.0)
        ligne = detail["marche"]["lignes"][0]
        self.assertEqual(ligne["cours"], 120.0)
        self.assertEqual(ligne["valeur"], 1200.0)
        self.assertEqual(ligne["ecart_pru_pct"], 20.0)

    def test_currency_is_converted_to_eur(self):
        self.enable_market()
        pea = self.seed_pea()
        self.post("/api/securities", {
            "ticker": "IE00B4L5Y983", "symbol": "CW8", "currency": "USD",
        })
        with self.app.app_context():
            market.refresh_quotes(FakeProvider({"CW8": (110.0, "USD")}, fx_rate=0.9))
        detail = self.get(f"/api/assets/{pea['id']}")
        self.assertAlmostEqual(detail["asset"]["valeur"], 990.0, places=2)  # 10 x 110 x 0.9

    def test_partial_coverage_falls_back(self):
        """Une ligne non cotee => on ne fabrique pas un total partiel."""
        self.enable_market()
        pea = self.seed_pea()
        self.post(f"/api/assets/{pea['id']}/movements", {
            "date": "2024-02-05", "montant": 500, "type": "versement",
            "ticker": "FR0000000000", "quantite": 5, "prix_unitaire": 100,
        })
        with self.app.app_context():
            market.refresh_quotes(FakeProvider({"CW8": 120.0}))
        detail = self.get(f"/api/assets/{pea['id']}")
        self.assertEqual(detail["asset"]["valeur_source"], "saisie")
        self.assertEqual(detail["asset"]["valeur"], 1500.0)

    def test_unmapped_ticker_is_reported(self):
        self.enable_market()
        self.post("/api/assets", {"type": "PEA", "label": "PEA nu",
                                  "valeur_acquisition": 0})
        asset = self.get("/api/assets")["assets"][0]
        self.post(f"/api/assets/{asset['id']}/movements", {
            "date": "2024-01-05", "montant": 300, "type": "versement",
            "ticker": "INCONNU", "quantite": 3, "prix_unitaire": 100,
        })
        status = self.get("/api/market/status")
        self.assertIn("INCONNU", status["tickers_non_mappes"])

    def test_crypto_uses_quantity_and_coin_id(self):
        self.enable_market()
        btc = self.post("/api/assets", {
            "type": "Crypto", "label": "Bitcoin", "date_acquisition": "2024-01-01",
            "valeur_acquisition": 1000,
            "metadata": {"coingecko_id": "bitcoin", "quantite": 0.05},
        })
        with self.app.app_context():
            market.refresh_quotes(FakeProvider({}),
                                  crypto_provider=FakeProvider({"bitcoin": 60000.0}))
        detail = self.get(f"/api/assets/{btc['id']}")
        self.assertEqual(detail["asset"]["valeur"], 3000.0)   # 0.05 x 60000
        self.assertEqual(detail["asset"]["valeur_source"], "marche")

    def test_net_worth_follows_market(self):
        self.enable_market()
        self.seed_pea()
        before = self.get("/api/assets")["patrimoine_net"]
        with self.app.app_context():
            market.refresh_quotes(FakeProvider({"CW8": 150.0}))
        after = self.get("/api/assets")["patrimoine_net"]
        self.assertEqual(before, 1000.0)
        self.assertEqual(after, 1500.0)


class TestPositions(MarketTestCase):
    """Choisir ses supports / ses cryptos depuis la fiche de l'actif."""

    def test_adding_a_position_creates_its_quote_mapping(self):
        """Le point clef : plus besoin de passer par les parametres."""
        pea = self.post("/api/assets", {
            "type": "PEA", "label": "PEA", "date_acquisition": "2024-01-02",
            "valeur_acquisition": 0})
        self.post(f"/api/assets/{pea['id']}/positions", {
            "ticker": "IE00B4L5Y983", "symbol": "CW8", "exchange": "Euronext",
            "currency": "EUR", "label": "Amundi MSCI World",
            "date": "2024-01-05", "quantite": 10, "prix_unitaire": 100,
        })
        securities = self.get("/api/securities")["securities"]
        self.assertEqual(len(securities), 1)
        self.assertEqual(securities[0]["symbol"], "CW8")
        self.assertEqual(securities[0]["kind"], "titre")
        # Et la ligne n'apparait plus comme non mappee.
        self.assertEqual(self.get("/api/market/status")["tickers_non_mappes"], [])

    def test_labels_are_shown_even_when_quotes_are_off(self):
        """Couper les cours ne doit pas effacer le nom de vos lignes."""
        pea = self.post("/api/assets", {"type": "PEA", "label": "PEA",
                                        "valeur_acquisition": 0})
        self.post(f"/api/assets/{pea['id']}/positions", {
            "ticker": "IE00B4L5Y983", "symbol": "CW8",
            "label": "Amundi MSCI World", "quantite": 10, "prix_unitaire": 100})
        self.assertFalse(self.get("/api/market/status")["active"])
        ligne = self.get(f"/api/assets/{pea['id']}/positions")["lignes"][0]
        self.assertEqual(ligne["libelle"], "Amundi MSCI World")
        self.assertEqual(ligne["symbole"], "CW8")
        self.assertIsNone(ligne["cours"])       # aucun cours, evidemment

    def test_positions_are_valued_line_by_line(self):
        self.enable_market()
        pea = self.post("/api/assets", {
            "type": "PEA", "label": "PEA", "date_acquisition": "2024-01-02",
            "valeur_acquisition": 0})
        for ticker, symbol, qty, price in [
            ("IE00B4L5Y983", "CW8", 10, 100), ("FR0010315770", "PUST", 20, 30)
        ]:
            self.post(f"/api/assets/{pea['id']}/positions", {
                "ticker": ticker, "symbol": symbol, "date": "2024-01-05",
                "quantite": qty, "prix_unitaire": price})
        with self.app.app_context():
            market.refresh_quotes(FakeProvider({"CW8": 120.0, "PUST": 45.0}))

        positions = self.get(f"/api/assets/{pea['id']}/positions")
        self.assertTrue(positions["complet"])
        self.assertEqual(positions["valeur_totale"], 2100.0)   # 10x120 + 20x45
        self.assertEqual(positions["investi_total"], 1600.0)
        self.assertEqual(self.get("/api/assets")["assets"][0]["valeur"], 2100.0)

    def test_one_uncovered_line_blocks_the_total(self):
        self.enable_market()
        pea = self.post("/api/assets", {
            "type": "PEA", "label": "PEA", "valeur_acquisition": 0})
        self.post(f"/api/assets/{pea['id']}/positions", {
            "ticker": "AAA", "symbol": "AAA", "quantite": 10, "prix_unitaire": 100})
        self.post(f"/api/assets/{pea['id']}/positions", {
            "ticker": "BBB", "symbol": "BBB", "quantite": 5, "prix_unitaire": 50})
        with self.app.app_context():
            market.refresh_quotes(FakeProvider({"AAA": 120.0}))
        positions = self.get(f"/api/assets/{pea['id']}/positions")
        self.assertFalse(positions["complet"])
        self.assertEqual(self.get("/api/assets")["assets"][0]["valeur_source"], "saisie")

    def test_several_cryptos_in_one_wallet(self):
        """Avant, un actif Crypto ne pouvait porter qu'une seule piece."""
        self.enable_market()
        wallet = self.post("/api/assets", {
            "type": "Crypto", "label": "Kraken", "date_acquisition": "2024-01-01",
            "valeur_acquisition": 0})
        self.post(f"/api/assets/{wallet['id']}/positions", {
            "ticker": "bitcoin", "label": "Bitcoin", "quantite": 0.05,
            "prix_unitaire": 40000})
        self.post(f"/api/assets/{wallet['id']}/positions", {
            "ticker": "ethereum", "label": "Ethereum", "quantite": 2,
            "prix_unitaire": 2000})

        securities = {s["ticker"]: s for s in self.get("/api/securities")["securities"]}
        self.assertEqual(securities["bitcoin"]["kind"], "crypto")

        with self.app.app_context():
            market.refresh_quotes(
                FakeProvider({}),
                crypto_provider=FakeProvider({"bitcoin": 60000.0, "ethereum": 3000.0}))
        detail = self.get(f"/api/assets/{wallet['id']}")
        # 0,05 x 60000 + 2 x 3000 = 9000
        self.assertEqual(detail["asset"]["valeur"], 9000.0)
        self.assertEqual(detail["asset"]["valeur_source"], "marche")
        self.assertEqual(len(self.get(f"/api/assets/{wallet['id']}/positions")["lignes"]), 2)

    def test_legacy_single_coin_still_works(self):
        """Une crypto saisie avant les positions ne doit pas casser."""
        self.enable_market()
        btc = self.post("/api/assets", {
            "type": "Crypto", "label": "Bitcoin", "date_acquisition": "2024-01-01",
            "valeur_acquisition": 1000,
            "metadata": {"coingecko_id": "bitcoin", "quantite": 0.05}})
        with self.app.app_context():
            market.refresh_quotes(FakeProvider({}),
                                  crypto_provider=FakeProvider({"bitcoin": 60000.0}))
        self.assertEqual(self.get(f"/api/assets/{btc['id']}")["asset"]["valeur"], 3000.0)

    def test_position_requires_a_quantity(self):
        pea = self.post("/api/assets", {"type": "PEA", "label": "PEA",
                                        "valeur_acquisition": 0})
        res = self.client.post(f"/api/assets/{pea['id']}/positions",
                               json={"ticker": "CW8", "montant": 1000})
        self.assertEqual(res.status_code, 400)

    def test_search_refuses_when_quotes_are_off(self):
        res = self.client.get("/api/market/search?type=titre&q=world")
        self.assertEqual(res.status_code, 409)

    def test_search_rejects_too_short_a_query(self):
        self.enable_market()
        res = self.client.get("/api/market/search?type=crypto&q=b")
        self.assertEqual(res.status_code, 400)


class TestBrokerStatementImport(MarketTestCase):
    """Import d'un releve de courtier (Trade Republic et assimiles)."""

    RELEVE_1 = (
        "Date,Instrument,Quantity,Price,Amount,Type\n"
        "2026-01-05,IE00B4L5Y983,2.5,89.10,222.75,Buy\n"
        "2026-02-05,IE00B4L5Y983,2.4,92.00,220.80,Buy\n"
    )
    # Le mois suivant, avec chevauchement : le releve reprend fevrier.
    RELEVE_2 = (
        "Date,Instrument,Quantity,Price,Amount,Type\n"
        "2026-02-05,IE00B4L5Y983,2.4,92.00,220.80,Buy\n"
        "2026-03-05,IE00B4L5Y983,2.2,95.00,209.00,Buy\n"
    )

    def _pea(self):
        return self.post("/api/assets", {
            "type": "PEA", "label": "PEA", "date_acquisition": "2026-01-01",
            "valeur_acquisition": 0})

    def test_quantities_update_automatically(self):
        """La question de fond : les quantites suivent-elles le releve ?"""
        pea = self._pea()
        preview = self.post(f"/api/assets/{pea['id']}/movements/preview",
                            {"text": self.RELEVE_1})
        self.assertEqual(preview["total"], 2)
        res = self.post(f"/api/assets/{pea['id']}/movements/confirm",
                        {"lignes": preview["lignes"]})
        self.assertEqual(res["crees"], 2)

        ligne = self.get(f"/api/assets/{pea['id']}/positions")["lignes"][0]
        self.assertAlmostEqual(ligne["quantite"], 4.9, places=6)     # 2,5 + 2,4
        self.assertAlmostEqual(ligne["pru"], 90.52, places=2)        # moyenne ponderee
        self.assertAlmostEqual(ligne["investi"], 443.55, places=2)

    def test_overlapping_statement_does_not_double_quantities(self):
        """Le piege : reimporter un releve qui chevauche le precedent."""
        pea = self._pea()
        p1 = self.post(f"/api/assets/{pea['id']}/movements/preview",
                       {"text": self.RELEVE_1})
        self.post(f"/api/assets/{pea['id']}/movements/confirm", {"lignes": p1["lignes"]})

        p2 = self.post(f"/api/assets/{pea['id']}/movements/preview",
                       {"text": self.RELEVE_2})
        self.assertEqual(p2["doublons"], 1)                  # le 5 fevrier
        self.assertTrue(p2["lignes"][0]["ignore"])           # decoche d'office
        self.assertFalse(p2["lignes"][1]["ignore"])

        res = self.post(f"/api/assets/{pea['id']}/movements/confirm",
                        {"lignes": p2["lignes"]})
        self.assertEqual(res["crees"], 1)
        ligne = self.get(f"/api/assets/{pea['id']}/positions")["lignes"][0]
        self.assertAlmostEqual(ligne["quantite"], 7.1, places=6)  # 2,5 + 2,4 + 2,2

    def test_forced_duplicate_is_blocked_by_the_index(self):
        """Meme en forcant, l'index unique protege la quantite."""
        pea = self._pea()
        p1 = self.post(f"/api/assets/{pea['id']}/movements/preview",
                       {"text": self.RELEVE_1})
        self.post(f"/api/assets/{pea['id']}/movements/confirm", {"lignes": p1["lignes"]})

        p2 = self.post(f"/api/assets/{pea['id']}/movements/preview",
                       {"text": self.RELEVE_1})
        for line in p2["lignes"]:
            line["ignore"] = False
        res = self.post(f"/api/assets/{pea['id']}/movements/confirm",
                        {"lignes": p2["lignes"]})
        self.assertEqual(res["crees"], 0)
        self.assertEqual(res["ignorees"], 2)
        ligne = self.get(f"/api/assets/{pea['id']}/positions")["lignes"][0]
        self.assertAlmostEqual(ligne["quantite"], 4.9, places=6)

    def test_import_creates_the_quote_mapping(self):
        """Sans correspondance, la ligne importee resterait non cotable."""
        pea = self._pea()
        preview = self.post(f"/api/assets/{pea['id']}/movements/preview",
                            {"text": self.RELEVE_1})
        self.assertEqual(preview["tickers_sans_symbole"], ["IE00B4L5Y983"])
        res = self.post(f"/api/assets/{pea['id']}/movements/confirm",
                        {"lignes": preview["lignes"]})
        self.assertEqual(res["symboles_amorces"], ["IE00B4L5Y983"])

        securities = self.get("/api/securities")["securities"]
        self.assertEqual(len(securities), 1)
        self.assertEqual(securities[0]["symbol"], "IE00B4L5Y983")
        self.assertEqual(securities[0]["kind"], "titre")
        self.assertEqual(self.get("/api/market/status")["tickers_non_mappes"], [])

    def test_existing_mapping_is_not_overwritten(self):
        """Un symbole deja corrige a la main ne doit pas etre ecrase."""
        pea = self._pea()
        self.post("/api/securities", {
            "ticker": "IE00B4L5Y983", "symbol": "CW8", "exchange": "Euronext"})
        preview = self.post(f"/api/assets/{pea['id']}/movements/preview",
                            {"text": self.RELEVE_1})
        self.assertEqual(preview["tickers_sans_symbole"], [])
        self.post(f"/api/assets/{pea['id']}/movements/confirm",
                  {"lignes": preview["lignes"]})
        securities = self.get("/api/securities")["securities"]
        self.assertEqual(securities[0]["symbol"], "CW8")

    def test_imported_quantities_drive_the_valuation(self):
        """Bout en bout : releve importe, cours rafraichi, valeur a jour."""
        self.enable_market()
        pea = self._pea()
        self.post("/api/securities", {"ticker": "IE00B4L5Y983", "symbol": "CW8"})
        preview = self.post(f"/api/assets/{pea['id']}/movements/preview",
                            {"text": self.RELEVE_1})
        self.post(f"/api/assets/{pea['id']}/movements/confirm",
                  {"lignes": preview["lignes"]})
        with self.app.app_context():
            market.refresh_quotes(FakeProvider({"CW8": 100.0}))
        detail = self.get(f"/api/assets/{pea['id']}")
        self.assertEqual(detail["asset"]["valeur"], 490.0)      # 4,9 x 100
        self.assertEqual(detail["asset"]["valeur_source"], "marche")

    def test_sales_reduce_the_quantity(self):
        pea = self._pea()
        texte = (
            "Date,Instrument,Quantity,Price,Amount,Type\n"
            "2026-01-05,IE00B4L5Y983,10,90.00,900.00,Buy\n"
            "2026-02-05,IE00B4L5Y983,4,95.00,380.00,Sell\n"
        )
        preview = self.post(f"/api/assets/{pea['id']}/movements/preview", {"text": texte})
        self.post(f"/api/assets/{pea['id']}/movements/confirm", {"lignes": preview["lignes"]})
        ligne = self.get(f"/api/assets/{pea['id']}/positions")["lignes"][0]
        self.assertAlmostEqual(ligne["quantite"], 6.0, places=6)
        self.assertAlmostEqual(ligne["pru"], 90.0, places=2)   # une vente ne bouge pas le PRU


class TestLivretInterest(unittest.TestCase):
    def _asset(self, acquisition="2024-01-01", valeur=10000):
        return {"date_acquisition": acquisition, "valeur_acquisition": valeur,
                "valeur_actuelle": None}

    def test_full_year_at_3_percent(self):
        value = finance.valeur_livret(self._asset(), [], 3.0, "2024-12-31")
        self.assertAlmostEqual(value, 10300.0, delta=1.0)

    def test_capitalisation_compounds_the_next_year(self):
        two_years = finance.valeur_livret(self._asset(), [], 3.0, "2025-12-31")
        self.assertGreater(two_years, 10600.0)                 # > interet simple
        self.assertAlmostEqual(two_years, 10609.0, delta=2.0)  # ~ interet compose

    def test_deposit_earns_from_the_next_fortnight(self):
        """Un versement du 1er au 15 porte interet au 16, pas avant."""
        movements = [{"date": "2024-07-10", "montant": 10000, "type": "versement"}]
        value = finance.valeur_livret(self._asset(valeur=0), movements, 3.0, "2024-12-31")
        # Du 16 juillet au 31 decembre : 11 quinzaines sur 24.
        self.assertAlmostEqual(value, 10000 * (1 + 0.03 * 11 / 24), delta=1.0)

    def test_withdrawal_stops_earning_from_the_previous_fortnight(self):
        movements = [{"date": "2024-07-10", "montant": -10000, "type": "retrait"}]
        value = finance.valeur_livret(self._asset(), movements, 3.0, "2024-12-31")
        # Retrait du 1er au 15 juillet : les sommes cessent de produire interet
        # depuis le 16 juin. Elles ont donc rapporte du 1er janvier au 15 juin,
        # soit 11 quinzaines sur 24.
        self.assertAlmostEqual(value, 10000 * 0.03 * 11 / 24, delta=1.0)

    def test_zero_rate_keeps_capital(self):
        self.assertEqual(finance.valeur_livret(self._asset(), [], 0.0, "2030-01-01"), 10000.0)

    def test_before_acquisition_is_zero(self):
        self.assertEqual(finance.valeur_livret(self._asset(), [], 3.0, "2023-06-01"), 0.0)


class TestLivretThroughApi(MarketTestCase):
    def test_rate_asset_uses_computed_interest(self):
        self.enable_market()
        livret = self.post("/api/assets", {
            "type": "Livret", "label": "Livret A", "date_acquisition": "2024-01-01",
            "valeur_acquisition": 10000, "metadata": {"taux_annuel": 3.0},
        })
        detail = self.get(f"/api/assets/{livret['id']}?date=2024-12-31")
        self.assertEqual(detail["asset"]["valeur_source"], "taux")
        self.assertAlmostEqual(detail["asset"]["valeur"], 10300.0, delta=1.0)

    def test_interest_works_without_enabling_market_quotes(self):
        """Les interets sont un calcul local : ils ne doivent rien exiger."""
        livret = self.post("/api/assets", {
            "type": "LivretJeune", "label": "Livret Jeune",
            "date_acquisition": "2024-01-01", "valeur_acquisition": 1000,
            "metadata": {"taux_annuel": 3.0},
        })
        self.assertFalse(self.get("/api/market/status")["active"])
        detail = self.get(f"/api/assets/{livret['id']}?date=2024-12-31")
        self.assertEqual(detail["asset"]["valeur_source"], "taux")
        self.assertAlmostEqual(detail["asset"]["valeur"], 1030.0, delta=1.0)

    def test_property_index_works_without_enabling_market_quotes(self):
        bien = self.post("/api/assets", {
            "type": "Immobilier", "label": "Studio",
            "date_acquisition": "2020-01-01", "valeur_acquisition": 100000,
            "metadata": {"taux_revalorisation_annuel": 2.0},
        })
        detail = self.get(f"/api/assets/{bien['id']}?date=2025-01-01")
        self.assertEqual(detail["asset"]["valeur_source"], "indice")
        self.assertAlmostEqual(detail["asset"]["valeur"], 110408.0, delta=200.0)

    def test_without_rate_falls_back_to_manual(self):
        self.enable_market()
        livret = self.post("/api/assets", {
            "type": "Livret", "label": "Livret sans taux",
            "date_acquisition": "2024-01-01", "valeur_acquisition": 5000,
        })
        detail = self.get(f"/api/assets/{livret['id']}")
        self.assertEqual(detail["asset"]["valeur_source"], "saisie")


class TestIndexedProperty(MarketTestCase):
    def test_manual_rate_revaluation(self):
        self.enable_market()
        bien = self.post("/api/assets", {
            "type": "Immobilier", "label": "Studio",
            "date_acquisition": "2020-01-01", "valeur_acquisition": 100000,
            "metadata": {"taux_revalorisation_annuel": 2.0},
        })
        detail = self.get(f"/api/assets/{bien['id']}?date=2025-01-01")
        self.assertEqual(detail["asset"]["valeur_source"], "indice")
        self.assertAlmostEqual(detail["asset"]["valeur"], 110408.0, delta=200.0)

    def test_insee_index_takes_precedence(self):
        self.enable_market()
        bien = self.post("/api/assets", {
            "type": "Immobilier", "label": "Studio",
            "date_acquisition": "2020-01-01", "valeur_acquisition": 100000,
            "metadata": {"indice_insee": "TEST123", "taux_revalorisation_annuel": 2.0},
        })
        with self.app.app_context():
            market.store_quote("INSEE:TEST123", "insee", "2020-01-01", 100.0, "IDX")
            market.store_quote("INSEE:TEST123", "insee", "2024-01-01", 130.0, "IDX")
        detail = self.get(f"/api/assets/{bien['id']}?date=2025-01-01")
        self.assertEqual(detail["asset"]["valeur"], 130000.0)

    def test_insee_period_parsing(self):
        self.assertEqual(market._parse_insee_period("2024-Q3"), date(2024, 7, 1))
        self.assertEqual(market._parse_insee_period("2024-05"), date(2024, 5, 1))
        self.assertEqual(market._parse_insee_period("2024"), date(2024, 1, 1))
        self.assertIsNone(market._parse_insee_period("n'importe quoi"))


class TestCacheAndSecurities(MarketTestCase):
    def test_cached_prices_returns_latest_before_date(self):
        with self.app.app_context():
            market.store_quote("CW8", "fake", "2024-01-01", 100.0)
            market.store_quote("CW8", "fake", "2024-06-01", 120.0)
            market.store_quote("CW8", "fake", "2024-12-01", 140.0)
            self.assertEqual(market.cached_prices("2024-07-01")["CW8"]["price"], 120.0)
            self.assertEqual(market.cached_prices("2024-01-15")["CW8"]["price"], 100.0)
            self.assertEqual(market.cached_prices("2023-01-01"), {})

    def test_security_upsert_is_idempotent(self):
        self.post("/api/securities", {"ticker": "ISIN1", "symbol": "AAA"})
        self.post("/api/securities", {"ticker": "ISIN1", "symbol": "BBB"})
        rows = self.get("/api/securities")["securities"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "BBB")

    def test_stale_cache_detection(self):
        with self.app.app_context():
            self.assertTrue(market.cache_is_stale())


class TestBenchmark(MarketTestCase):
    def test_comparison_rebases_both_series(self):
        self.enable_market()
        pea = self.seed_pea()
        self.post("/api/securities", {
            "ticker": "IE00B4L5Y983", "symbol": "CW8",
            "benchmark_symbol": "MSCIW", "benchmark_label": "MSCI World",
        })
        provider = FakeProvider({"perf:CW8": 0.25, "perf:MSCIW": 0.10})
        with self.app.app_context():
            result = market.benchmark_comparison(
                {"id": pea["id"], "date_acquisition": "2024-01-02"},
                [{"date": "2024-01-05", "type": "versement", "montant": 1000,
                  "ticker": "IE00B4L5Y983", "quantite": 10, "prix_unitaire": 100}],
                market.securities_by_ticker(), provider)
        ligne = result["lignes"][0]
        self.assertAlmostEqual(ligne["perf_ligne"], 25.0, places=1)
        self.assertAlmostEqual(ligne["perf_indice"], 10.0, places=1)
        self.assertAlmostEqual(ligne["ecart"], 15.0, places=1)
        self.assertEqual(ligne["serie_ligne"][0]["valeur"], 100.0)


if __name__ == "__main__":
    unittest.main()
