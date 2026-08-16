"""Tests de bout en bout : API HTTP + persistance SQLite."""
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, finance  # noqa: E402


def month_key(offset=0):
    d = finance.add_months(date.today(), offset)
    return f"{d.year:04d}-{d.month:02d}"


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.db_path)
        self.app = create_app(self.db_path)
        self.client = self.app.test_client()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    # -- helpers
    def post(self, url, payload):
        res = self.client.post(url, json=payload)
        self.assertIn(res.status_code, (200, 201), res.get_data(as_text=True))
        return res.get_json()

    def get(self, url):
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        return res.get_json()


class TestCrud(ApiTestCase):
    def test_transaction_lifecycle(self):
        tx = self.post("/api/transactions", {
            "date": f"{month_key()}-05", "description": "Courses", "amount": -42.5,
            "category": "Alimentation",
        })
        self.assertEqual(tx["amount"], -42.5)

        self.client.put(f"/api/transactions/{tx['id']}", json={"category": "Restaurants"})
        again = self.get(f"/api/transactions?month={month_key()}")
        self.assertEqual(again[0]["category"], "Restaurants")

        self.client.delete(f"/api/transactions/{tx['id']}")
        self.assertEqual(self.get(f"/api/transactions?month={month_key()}"), [])

    def test_transaction_rejects_bad_input(self):
        res = self.client.post("/api/transactions", json={"date": "pas une date", "amount": 10})
        self.assertEqual(res.status_code, 400)
        res = self.client.post("/api/transactions", json={"date": "2024-01-01", "amount": "abc"})
        self.assertEqual(res.status_code, 400)

    def test_asset_and_movements(self):
        asset = self.post("/api/assets", {
            "type": "PEA", "label": "PEA Trade Republic",
            "date_acquisition": "2024-01-02", "valeur_acquisition": 0,
        })
        for m in range(1, 4):
            self.post(f"/api/assets/{asset['id']}/movements", {
                "date": f"2024-0{m}-05", "montant": 200, "type": "versement",
                "quantite": 2, "prix_unitaire": 100, "ticker": "CW8",
            })
        detail = self.get(f"/api/assets/{asset['id']}")
        self.assertEqual(detail["asset"]["investi"], 600.0)
        self.assertEqual(detail["marche"]["pru"], 100.0)
        self.assertEqual(detail["marche"]["quantite"], 6.0)
        self.assertEqual(len(detail["movements"]), 3)

        # Valorisation : la valeur du jour prend le pas, le TRI devient calculable.
        self.post(f"/api/assets/{asset['id']}/valorisation", {"valeur": 700})
        detail = self.get(f"/api/assets/{asset['id']}")
        self.assertEqual(detail["asset"]["valeur"], 700.0)
        self.assertEqual(detail["asset"]["plus_value"], 100.0)
        self.assertIsNotNone(detail["marche"]["tri"])

    def test_custom_type_requires_nothing_extra(self):
        asset = self.post("/api/assets", {
            "type": "Custom", "label": "Collection de montres",
            "date_acquisition": "2023-05-01", "valeur_acquisition": 3000,
        })
        detail = self.get(f"/api/assets/{asset['id']}")
        self.assertEqual(detail["asset"]["famille"], "Autre")
        self.assertEqual(detail["asset"]["metadata"], {})

    def test_custom_asset_type_from_settings(self):
        self.client.put("/api/settings", json={
            "types_actifs_custom": [{"type": "Foret", "famille": "Immobilier"}]
        })
        meta = self.get("/api/meta")
        self.assertIn("Foret", [t["type"] for t in meta["asset_types"]])
        asset = self.post("/api/assets", {
            "type": "Foret", "label": "Parcelle Morvan", "valeur_acquisition": 15000,
        })
        detail = self.get(f"/api/assets/{asset['id']}")
        self.assertEqual(detail["asset"]["famille"], "Immobilier")


class TestQuickAdd(ApiTestCase):
    """Saisie initiale du patrimoine existant, en une seule fois."""

    def test_batch_creates_every_product(self):
        res = self.post("/api/assets/batch", {
            "date": "2026-08-01",
            "actifs": [
                {"type": "Livret", "label": "Livret A", "montant": 8200, "taux_annuel": 3},
                {"type": "LivretJeune", "label": "Livret Jeune", "montant": 1600,
                 "taux_annuel": 3.5},
                {"type": "AssuranceVie", "label": "Assurance vie", "montant": 12000},
            ],
        })
        self.assertEqual(res["crees"], 3)
        self.assertEqual(res["total"], 21800.0)

        snap = self.get("/api/assets")
        # Le total declare est le plancher : les deux livrets portent un taux et
        # capitalisent depuis la date de reference, sans qu'aucun reglage
        # supplementaire n'ait ete active.
        self.assertGreaterEqual(snap["total_actif"], 21800.0)
        self.assertEqual(snap["patrimoine_net"], snap["total_actif"])
        par_label = {a["label"]: a for a in snap["assets"]}
        self.assertEqual(par_label["Assurance vie"]["valeur"], 12000.0)
        self.assertEqual(par_label["Livret A"]["valeur_source"], "taux")
        self.assertEqual(par_label["Assurance vie"]["valeur_source"], "saisie")

    def test_plus_value_starts_at_zero(self):
        """On ne fabrique pas de performance sur un produit deja constitue."""
        self.post("/api/assets/batch", {
            "date": "2026-08-01",
            "actifs": [{"type": "Livret", "label": "Livret A", "montant": 8200}],
        })
        asset = self.get("/api/assets")["assets"][0]
        self.assertEqual(asset["valeur"], 8200.0)
        self.assertEqual(asset["investi"], 8200.0)
        self.assertEqual(asset["plus_value"], 0.0)

    def test_rate_is_stored_and_used(self):
        self.client.put("/api/settings", json={"market_enabled": True})
        self.post("/api/assets/batch", {
            "date": "2026-01-01",
            "actifs": [{"type": "LivretJeune", "label": "Livret Jeune",
                        "montant": 1000, "taux_annuel": 3.0}],
        })
        aid = self.get("/api/assets")["assets"][0]["id"]
        detail = self.get(f"/api/assets/{aid}?date=2026-12-31")
        self.assertEqual(detail["asset"]["metadata"]["taux_annuel"], 3.0)
        self.assertEqual(detail["asset"]["valeur_source"], "taux")
        self.assertAlmostEqual(detail["asset"]["valeur"], 1030.0, delta=1.0)

    def test_new_savings_types_are_available_and_liquid(self):
        types = [t["type"] for t in self.get("/api/meta")["asset_types"]]
        for expected in ("LivretJeune", "PEL", "CEL"):
            self.assertIn(expected, types)
        self.post("/api/assets/batch", {
            "actifs": [{"type": "LivretJeune", "label": "LJ", "montant": 1600}]})
        # Le Livret Jeune compte dans l'epargne de precaution.
        self.assertEqual(self.get("/api/metrics")["solde_livrets"], 1600.0)

    def test_empty_and_invalid_lines_are_skipped(self):
        res = self.post("/api/assets/batch", {
            "actifs": [
                {"type": "Livret", "label": "Livret A", "montant": 500},
                {"type": "LEP", "label": "LEP", "montant": None},
                {"type": "", "label": "sans type", "montant": 100},
            ]})
        self.assertEqual(res["crees"], 1)
        self.assertEqual(res["ignores"], 2)

    def test_batch_refuses_empty_payload(self):
        res = self.client.post("/api/assets/batch", json={"actifs": []})
        self.assertEqual(res.status_code, 400)


class TestNetWorth(ApiTestCase):
    def test_asset_minus_liability(self):
        asset = self.post("/api/assets", {
            "type": "Immobilier", "label": "Studio Nantes",
            "date_acquisition": "2024-01-15", "valeur_acquisition": 150000,
            "valeur_actuelle": 160000, "metadata": {"loue": True, "surface_m2": 28},
        })
        self.post("/api/liabilities", {
            "type": "PretImmobilier", "label": "Prêt studio", "asset_id": asset["id"],
            "montant_emprunte": 120000, "taux_annuel": 3.2, "duree_mois": 240,
            "date_debut": "2024-01-15", "assurance_mensuelle": 20,
        })
        snap = self.get("/api/assets")
        self.assertEqual(snap["total_actif"], 160000.0)
        self.assertGreater(snap["total_passif"], 0)
        self.assertLess(snap["total_passif"], 120000)
        self.assertAlmostEqual(
            snap["patrimoine_net"], snap["total_actif"] - snap["total_passif"], places=2)
        # Le brut n'est jamais additionné sans retrancher la dette.
        self.assertLess(snap["patrimoine_net"], 160000)

    def test_rendement_hors_capital_est_superieur_au_cashflow(self):
        """Le remboursement du capital n'est pas une charge : l'inclure fait
        paraitre le bien moins rentable qu'il ne l'est."""
        asset = self.post("/api/assets", {
            "type": "Immobilier", "label": "Studio", "date_acquisition": "2020-01-15",
            "valeur_acquisition": 150000, "valeur_actuelle": 200000,
        })
        self.post("/api/liabilities", {
            "type": "PretImmobilier", "label": "Pret studio", "asset_id": asset["id"],
            "montant_emprunte": 120000, "taux_annuel": 3.0, "duree_mois": 240,
            "date_debut": "2020-01-15", "assurance_mensuelle": 20,
        })
        for i in range(12):
            d = finance.add_months(date.today(), -i)
            self.post("/api/transactions", {
                "date": d.replace(day=5).isoformat(), "description": "Loyer",
                "amount": 800, "category": "Revenu locatif", "asset_id": asset["id"],
            })
        immo = self.get(f"/api/assets/{asset['id']}")["immobilier"]

        # Les interets sont une fraction de la mensualite : le rendement qui les
        # seuls retient est mecaniquement plus favorable.
        self.assertLess(immo["interets_12m"], immo["mensualites_12m"])
        self.assertGreater(immo["rendement_hors_capital_pct"], immo["rendement_net_pct"])
        # Et il reste en dessous du brut, qui ignore toute charge.
        self.assertLess(immo["rendement_hors_capital_pct"], immo["rendement_brut_pct"])

    def test_rental_yield(self):
        asset = self.post("/api/assets", {
            "type": "Immobilier", "label": "Studio", "date_acquisition": "2020-01-15",
            "valeur_acquisition": 100000, "valeur_actuelle": 200000,
        })
        for i in range(12):
            d = finance.add_months(date.today(), -i)
            self.post("/api/transactions", {
                "date": d.replace(day=5).isoformat(), "description": "Loyer",
                "amount": 800, "category": "Revenu locatif", "asset_id": asset["id"],
            })
        detail = self.get(f"/api/assets/{asset['id']}")
        immo = detail["immobilier"]
        self.assertGreaterEqual(immo["loyers_12m"], 8800)
        self.assertIsNotNone(immo["rendement_net_pct"])
        self.assertEqual(immo["valeur_nette"], 200000.0)


class TestImportFlow(ApiTestCase):
    CSV = (
        "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
        "CARD_PAYMENT,Current,2024-03-02 09:12:00,2024-03-02 09:12:00,Carrefour City,-24.30,0.00,EUR,COMPLETED,1200.00\n"
        "TOPUP,Current,2024-03-05 08:00:00,2024-03-05 08:00:00,VIREMENT SALAIRE,2100.00,0.00,EUR,COMPLETED,3300.00\n"
    )

    def test_preview_then_confirm_then_dedup(self):
        self.post("/api/rules", {
            "pattern": "SALAIRE", "cible_type": "type_revenu", "valeur": "Salaire",
        })
        preview = self.post("/api/imports/preview", {"text": self.CSV})
        self.assertEqual(preview["total"], 2)
        self.assertEqual(preview["doublons"], 0)
        salaire = [l for l in preview["lignes"] if l["amount"] > 0][0]
        self.assertEqual(salaire["category"], "Salaire")
        self.assertEqual(salaire["origine"], "regle")

        result = self.post("/api/imports/confirm",
                           {"source": "Revolut", "lignes": preview["lignes"]})
        self.assertEqual(result["importees"], 2)

        txs = self.get("/api/transactions?month=2024-03")
        self.assertEqual(len(txs), 2)
        self.assertTrue(all(t["import_id"] == result["import_id"] for t in txs))

        # Deuxième passage du même relevé : tout est marqué doublon.
        again = self.post("/api/imports/preview", {"text": self.CSV})
        self.assertEqual(again["doublons"], 2)
        self.assertTrue(all(l["ignore"] for l in again["lignes"]))

        # Et si on force, l'index unique empêche l'insertion.
        for line in again["lignes"]:
            line["ignore"] = False
        forced = self.post("/api/imports/confirm",
                           {"source": "Revolut", "lignes": again["lignes"]})
        self.assertEqual(forced["importees"], 0)
        self.assertEqual(forced["ignorees"], 2)
        self.assertEqual(len(self.get("/api/transactions?month=2024-03")), 2)

    def test_journal_and_rollback(self):
        preview = self.post("/api/imports/preview", {"text": self.CSV})
        result = self.post("/api/imports/confirm",
                           {"source": "Revolut", "lignes": preview["lignes"]})
        journal = self.get("/api/imports")
        self.assertEqual(len(journal), 1)
        self.assertEqual(journal[0]["source"], "Revolut")
        self.assertEqual(journal[0]["periode_debut"], "2024-03-02")
        self.assertEqual(journal[0]["periode_fin"], "2024-03-05")
        self.assertEqual(journal[0]["nombre_lignes"], 2)

        self.client.delete(f"/api/imports/{result['import_id']}")
        self.assertEqual(self.get("/api/imports"), [])
        self.assertEqual(self.get("/api/transactions?month=2024-03"), [])

    def test_loan_instalment_classified_without_rule(self):
        loan = self.post("/api/liabilities", {
            "type": "PretImmobilier", "label": "Prêt", "montant_emprunte": 200000,
            "taux_annuel": 3.5, "duree_mois": 240, "date_debut": "2024-01-15",
        })
        detail = self.get(f"/api/liabilities/{loan['id']}")
        mensualite = detail["mensualite"]
        text = f"Date,Description,Amount\n2024-04-15,PRLV CREDIT 8891,-{mensualite:.2f}\n"
        preview = self.post("/api/imports/preview", {"text": text})
        line = preview["lignes"][0]
        self.assertEqual(line["category"], "Remboursement pret")
        self.assertEqual(line["liability_id"], loan["id"])

        self.post("/api/imports/confirm", {"source": "LCL", "lignes": preview["lignes"]})
        txs = self.get(f"/api/transactions?liability_id={loan['id']}")
        self.assertEqual(len(txs), 1)


class TestAnalytics(ApiTestCase):
    def seed(self):
        self.post("/api/assets", {
            "type": "Livret", "label": "Livret A", "date_acquisition": "2023-01-01",
            "valeur_acquisition": 6000, "valeur_actuelle": 6000,
        })
        pea = self.post("/api/assets", {
            "type": "PEA", "label": "PEA", "date_acquisition": "2023-01-01",
            "valeur_acquisition": 0,
        })
        this_month = month_key()
        self.post(f"/api/assets/{pea['id']}/movements", {
            "date": f"{this_month}-03", "montant": 400, "type": "versement",
        })
        self.post("/api/transactions", {
            "date": f"{this_month}-01", "description": "Salaire", "amount": 2000,
            "category": "Salaire",
        })
        self.post("/api/transactions", {
            "date": f"{this_month}-04", "description": "Courses", "amount": -300,
            "category": "Alimentation",
        })
        return pea

    def test_overview_shape(self):
        self.seed()
        data = self.get(f"/api/overview?month={month_key()}")
        self.assertEqual(data["mois"]["revenus"], 2000.0)
        self.assertEqual(data["mois"]["depenses"], 300.0)
        self.assertEqual(data["mois"]["epargne"], 400.0)
        self.assertAlmostEqual(data["mois"]["taux_epargne"], 0.2, places=6)
        self.assertEqual(len(data["patrimoine_serie"]), 12)
        self.assertEqual(len(data["depenses_serie"]), 6)
        self.assertEqual(data["metrics"]["patrimoine_net"], 6400.0)

    def test_savings_transfer_is_not_an_expense(self):
        self.post("/api/transactions", {
            "date": f"{month_key()}-06", "description": "Virement PEA", "amount": -500,
            "category": "Epargne/Investissement",
        })
        flows = self.get(f"/api/month?month={month_key()}")
        self.assertEqual(flows["depenses"], 0.0)
        self.assertEqual(flows["transferts_epargne"], 500.0)
        self.assertEqual(flows["epargne"], 500.0)

    def test_repartition_target_vs_real(self):
        self.seed()
        rep = self.get(f"/api/overview?month={month_key()}")["repartition"]
        labels = {b["label"]: b for b in rep["buckets"]}
        self.assertIn("PEA", labels)
        self.assertIn("Livret", labels)
        self.assertAlmostEqual(sum(b["reel_pct"] for b in rep["buckets"]), 100.0, places=1)
        self.assertGreater(labels["Livret"]["reel_pct"], labels["PEA"]["reel_pct"])
        self.assertAlmostEqual(
            labels["Livret"]["ecart_pct"],
            labels["Livret"]["reel_pct"] - labels["Livret"]["cible_pct"], places=2)

    def test_history_is_recomputed_not_frozen(self):
        self.seed()
        before = self.get("/api/history")["archive"]
        current = [row for row in before if row["mois"] == month_key()][0]
        self.assertEqual(current["depenses"], 300.0)

        # On corrige une donnée du mois : l'archive doit suivre immédiatement.
        tx = self.get(f"/api/transactions?month={month_key()}&category=Alimentation")[0]
        self.client.put(f"/api/transactions/{tx['id']}", json={"amount": -500})
        after = self.get("/api/history")["archive"]
        current = [row for row in after if row["mois"] == month_key()][0]
        self.assertEqual(current["depenses"], 500.0)

    def test_emergency_coverage_uses_liquid_savings(self):
        self.seed()
        prev = finance.add_months(date.today(), -1)
        self.post("/api/transactions", {
            "date": prev.replace(day=10).isoformat(), "description": "Loyer",
            "amount": -900, "category": "Logement",
        })
        m = self.get("/api/metrics")
        self.assertEqual(m["solde_livrets"], 6000.0)
        self.assertAlmostEqual(m["depenses_moyennes_3m"], 300.0, places=2)
        self.assertAlmostEqual(m["mois_couverture_urgence"], 20.0, places=1)


class TestInternalTransfers(ApiTestCase):
    """Un virement LCL <-> Revolut n'est ni une depense ni un revenu."""

    def test_transfer_category_is_neutral_on_both_sides(self):
        month = month_key()
        self.post("/api/transactions", {
            "date": f"{month}-01", "description": "Salaire", "amount": 2000,
            "category": "Salaire"})
        self.post("/api/transactions", {
            "date": f"{month}-05", "description": "Courses", "amount": -100,
            "category": "Alimentation"})
        # Le meme virement, vu des deux cotes.
        self.post("/api/transactions", {
            "date": f"{month}-10", "description": "VIR REVOLUT", "amount": -500,
            "category": "Transfert interne"})
        self.post("/api/transactions", {
            "date": f"{month}-11", "description": "Top-Up", "amount": 500,
            "category": "Transfert interne"})

        flows = self.get(f"/api/month?month={month}")
        self.assertEqual(flows["revenus"], 2000.0)   # le +500 ne gonfle pas les revenus
        self.assertEqual(flows["depenses"], 100.0)   # le -500 ne gonfle pas les depenses
        self.assertEqual(flows["transferts_internes"], 500.0)
        self.assertEqual(flows["epargne"], 0.0)      # ce n'est pas de l'epargne non plus
        categories = [c["category"] for c in flows["par_categorie"]]
        self.assertNotIn("Transfert interne", categories)
        revenus_cat = [c["category"] for c in flows["revenus_par_categorie"]]
        self.assertNotIn("Transfert interne", revenus_cat)

    def test_savings_transfer_still_counts_as_savings(self):
        """La distinction avec l'epargne doit rester nette."""
        month = month_key()
        self.post("/api/transactions", {
            "date": f"{month}-01", "description": "Salaire", "amount": 1000,
            "category": "Salaire"})
        self.post("/api/transactions", {
            "date": f"{month}-06", "description": "Virement Livret A", "amount": -200,
            "category": "Epargne/Investissement"})
        flows = self.get(f"/api/month?month={month}")
        self.assertEqual(flows["depenses"], 0.0)
        self.assertEqual(flows["epargne"], 200.0)
        self.assertEqual(flows["transferts_internes"], 0.0)

    def test_keyword_detection_at_import(self):
        text = ("Date,Description,Amount\n"
                f"{month_key()}-10,VIR SEPA VERS REVOLUT,-500.00\n")
        preview = self.post("/api/imports/preview", {"text": text})
        line = preview["lignes"][0]
        self.assertEqual(line["category"], "Transfert interne")
        self.assertEqual(line["origine"], "transfert")

    def test_pair_detection_across_two_statements(self):
        month = month_key()
        lcl = self.post("/api/imports/confirm", {
            "source": "LCL",
            "lignes": [{"date": f"{month}-10", "description": "VIR EMIS",
                        "amount": -500, "category": "Non categorise"}]})
        self.post("/api/imports/confirm", {
            "source": "Revolut",
            "lignes": [{"date": f"{month}-11", "description": "Top-Up by card",
                        "amount": 500, "category": "Non categorise"}]})
        self.assertIsNotNone(lcl["import_id"])

        detected = self.get("/api/transfers/detect")
        self.assertEqual(detected["total"], 1)
        pair = detected["paires"][0]
        self.assertEqual(pair["montant"], 500.0)
        self.assertEqual(pair["ecart_jours"], 1)

        ids = [pair["sortie"]["id"], pair["entree"]["id"]]
        applied = self.post("/api/transfers/apply", {"ids": ids})
        self.assertEqual(applied["modifiees"], 2)

        flows = self.get(f"/api/month?month={month}")
        self.assertEqual(flows["depenses"], 0.0)
        self.assertEqual(flows["revenus"], 0.0)

    def test_same_statement_is_never_paired(self):
        """Garde-fou : un salaire et une depense du meme releve ne sont pas
        un virement entre comptes, meme au meme montant."""
        month = month_key()
        self.post("/api/imports/confirm", {
            "source": "LCL",
            "lignes": [
                {"date": f"{month}-10", "description": "SALAIRE", "amount": 500,
                 "category": "Salaire"},
                {"date": f"{month}-11", "description": "LOYER", "amount": -500,
                 "category": "Logement"},
            ]})
        self.assertEqual(self.get("/api/transfers/detect")["total"], 0)

    def test_manual_entries_are_never_paired(self):
        """Deux saisies manuelles (sans import) restent hors rapprochement."""
        month = month_key()
        self.post("/api/transactions", {
            "date": f"{month}-10", "description": "A", "amount": -300})
        self.post("/api/transactions", {
            "date": f"{month}-11", "description": "B", "amount": 300})
        self.assertEqual(self.get("/api/transfers/detect")["total"], 0)

    def test_migration_adds_category_to_an_existing_database(self):
        """Une base creee avant l'ajout doit recevoir la categorie."""
        # Simule une base anterieure : liste de categories sans « Transfert interne ».
        self.client.put("/api/settings", json={
            "categories_depenses": ["Alimentation", "Logement"]})
        self.assertNotIn("Transfert interne",
                         self.get("/api/meta")["categories_depenses"])
        # Relance de l'application sur la meme base.
        app = create_app(self.db_path)
        categories = app.test_client().get("/api/meta").get_json()["categories_depenses"]
        self.assertIn("Transfert interne", categories)
        self.assertIn("Alimentation", categories)   # les choix existants sont gardes

    def test_far_apart_dates_are_not_paired(self):
        month = month_key()
        self.post("/api/imports/confirm", {
            "source": "LCL",
            "lignes": [{"date": f"{month}-01", "description": "VIR", "amount": -500,
                        "category": "Non categorise"}]})
        self.post("/api/imports/confirm", {
            "source": "Revolut",
            "lignes": [{"date": f"{month}-25", "description": "Top-Up", "amount": 500,
                        "category": "Non categorise"}]})
        self.assertEqual(self.get("/api/transfers/detect")["total"], 0)


class TestSettingsAndRules(ApiTestCase):
    def test_settings_round_trip(self):
        self.client.put("/api/settings", json={
            "repartition_cible": [{"label": "PEA", "types": ["PEA"], "pct": 100}],
            "frais_annuels": {"2026": {"ter": 45, "courtage": 12}},
        })
        settings = self.get("/api/settings")
        self.assertEqual(settings["repartition_cible"][0]["pct"], 100)
        m = self.get("/api/metrics")
        self.assertEqual(m["frais_annuels"], 57.0)

    def test_apply_rules_to_existing_transactions(self):
        self.post("/api/transactions", {
            "date": f"{month_key()}-08", "description": "VIR PAPA AIDE",
            "amount": 300, "category": "Non categorise",
        })
        self.post("/api/rules", {
            "pattern": "PAPA", "cible_type": "type_revenu", "valeur": "Argent parents",
        })
        res = self.post("/api/rules/apply", {"seulement_non_categorise": True})
        self.assertEqual(res["modifiees"], 1)
        txs = self.get(f"/api/transactions?month={month_key()}")
        self.assertEqual(txs[0]["category"], "Argent parents")


if __name__ == "__main__":
    unittest.main()
