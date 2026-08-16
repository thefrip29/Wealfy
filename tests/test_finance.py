"""Tests du moteur de calcul : amortissement, PRU, XIRR, valorisation."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import finance  # noqa: E402


class TestDates(unittest.TestCase):
    def test_add_months_clamps_end_of_month(self):
        self.assertEqual(finance.add_months(date(2024, 1, 31), 1), date(2024, 2, 29))
        self.assertEqual(finance.add_months(date(2023, 1, 31), 1), date(2023, 2, 28))
        self.assertEqual(finance.add_months(date(2024, 12, 15), 1), date(2025, 1, 15))
        self.assertEqual(finance.add_months(date(2024, 3, 10), -4), date(2023, 11, 10))

    def test_parse_date_formats(self):
        self.assertEqual(finance.parse_date("2024-05-03"), date(2024, 5, 3))
        self.assertEqual(finance.parse_date("03/05/2024"), date(2024, 5, 3))
        self.assertEqual(finance.parse_date("2024-05-03 14:22:01"), date(2024, 5, 3))
        self.assertIsNone(finance.parse_date("n'importe quoi"))

    def test_months_between(self):
        keys = finance.months_between(date(2023, 11, 5), date(2024, 2, 20))
        self.assertEqual(keys, ["2023-11", "2023-12", "2024-01", "2024-02"])


class TestLoan(unittest.TestCase):
    def test_monthly_payment_reference(self):
        # 200 000 € à 3,5 % sur 20 ans -> 1159,92 € (valeur de référence)
        self.assertAlmostEqual(monthly := finance.monthly_payment(200000, 3.5, 240), 1159.92, places=2)
        self.assertGreater(monthly, 0)

    def test_zero_rate(self):
        self.assertAlmostEqual(finance.monthly_payment(12000, 0, 24), 500.0, places=6)

    def test_schedule_is_fully_amortising(self):
        sched = finance.amortization_schedule(200000, 3.5, 240, "2024-01-15")
        self.assertEqual(len(sched), 240)
        self.assertEqual(sched[-1]["capital_restant"], 0.0)
        # Le capital remboursé couvre le montant emprunté (aux arrondis
        # centime par échéance près).
        self.assertAlmostEqual(sum(r["capital"] for r in sched), 200000, delta=0.05)
        # Première échéance un mois après le début.
        self.assertEqual(sched[0]["date"], "2024-02-15")
        # Les intérêts décroissent, le capital augmente.
        self.assertGreater(sched[0]["interets"], sched[-1]["interets"])
        self.assertLess(sched[0]["capital"], sched[-1]["capital"])

    def test_remaining_principal_is_recomputed(self):
        liab = {
            "montant_emprunte": 200000, "taux_annuel": 3.5,
            "duree_mois": 240, "date_debut": "2024-01-15",
        }
        self.assertEqual(finance.remaining_principal(liab, "2024-01-14"), 200000)
        after_one = finance.remaining_principal(liab, "2024-02-15")
        self.assertLess(after_one, 200000)
        self.assertGreater(after_one, 199000)
        self.assertEqual(finance.remaining_principal(liab, "2044-01-15"), 0.0)

    def test_summary_counts_instalments(self):
        liab = {
            "montant_emprunte": 100000, "taux_annuel": 2.0, "duree_mois": 120,
            "date_debut": "2020-01-01", "assurance_mensuelle": 15.0,
        }
        s = finance.liability_summary(liab, "2021-01-01")
        self.assertEqual(s["echeances_payees"], 12)
        self.assertEqual(s["echeances_totales"], 120)
        self.assertAlmostEqual(
            s["mensualite_avec_assurance"], s["mensualite"] + 15.0, places=2)
        self.assertEqual(s["date_fin"], "2030-01-01")


class TestAssetValue(unittest.TestCase):
    def _asset(self, **kw):
        base = {
            "date_acquisition": "2024-01-01", "valeur_acquisition": 1000.0,
            "valeur_actuelle": None,
        }
        base.update(kw)
        return base

    def test_value_before_acquisition_is_zero(self):
        self.assertEqual(finance.asset_value_at(self._asset(), [], "2023-12-31"), 0.0)

    def test_value_accumulates_movements(self):
        movements = [
            {"date": "2024-02-01", "montant": 500, "type": "versement"},
            {"date": "2024-03-01", "montant": -200, "type": "retrait"},
        ]
        self.assertEqual(finance.asset_value_at(self._asset(), movements, "2024-01-15"), 1000.0)
        self.assertEqual(finance.asset_value_at(self._asset(), movements, "2024-02-15"), 1500.0)
        self.assertEqual(finance.asset_value_at(self._asset(), movements, "2024-03-15"), 1300.0)

    def test_valorisation_resets_the_base(self):
        movements = [
            {"date": "2024-02-01", "montant": 500, "type": "versement"},
            {"date": "2024-06-01", "montant": 2000, "type": "valorisation"},
            {"date": "2024-07-01", "montant": 100, "type": "versement"},
        ]
        self.assertEqual(finance.asset_value_at(self._asset(), movements, "2024-06-15"), 2000.0)
        self.assertEqual(finance.asset_value_at(self._asset(), movements, "2024-07-15"), 2100.0)

    def test_manual_current_value_wins_today(self):
        asset = self._asset(valeur_actuelle=9999.0)
        self.assertEqual(finance.asset_value_at(asset, [], date.today()), 9999.0)
        # ... mais pas dans le passé, qui reste reconstitué.
        self.assertEqual(finance.asset_value_at(asset, [], "2024-02-01"), 1000.0)


class TestPortfolioMaths(unittest.TestCase):
    def test_pru_over_buys_only(self):
        movements = [
            {"type": "versement", "quantite": 10, "prix_unitaire": 100, "montant": 1000, "ticker": "CW8"},
            {"type": "versement", "quantite": 10, "prix_unitaire": 120, "montant": 1200, "ticker": "CW8"},
            {"type": "retrait", "quantite": 5, "prix_unitaire": 150, "montant": -750, "ticker": "CW8"},
        ]
        self.assertEqual(finance.pru(movements), 110.0)
        self.assertEqual(finance.quantity_held(movements), 15.0)
        lignes = finance.pru_par_ligne(movements)
        self.assertEqual(len(lignes), 1)
        self.assertEqual(lignes[0]["ticker"], "CW8")
        self.assertEqual(lignes[0]["pru"], 110.0)

    def test_pru_none_without_quantities(self):
        self.assertIsNone(finance.pru([{"type": "versement", "quantite": None,
                                        "prix_unitaire": None, "montant": 500}]))

    def test_xirr_simple_doubling(self):
        # -1000 puis +1100 un an plus tard -> ~10 %
        rate = finance.xirr([(date(2023, 1, 1), -1000), (date(2024, 1, 1), 1100)])
        self.assertAlmostEqual(rate, 0.10, places=3)

    def test_xirr_dca(self):
        flows = [(date(2023, 1, 1), -100), (date(2023, 7, 1), -100),
                 (date(2024, 1, 1), 215)]
        rate = finance.xirr(flows)
        self.assertIsNotNone(rate)
        self.assertGreater(rate, 0)
        self.assertAlmostEqual(finance.xnpv(rate, flows), 0.0, places=4)

    def test_xirr_returns_none_without_sign_change(self):
        self.assertIsNone(finance.xirr([(date(2023, 1, 1), -100), (date(2024, 1, 1), -100)]))

    def test_rendement_locatif_net(self):
        r = finance.rendement_locatif_net(9600, 1200, 6000, 200000)
        self.assertAlmostEqual(r, 0.012, places=6)
        self.assertIsNone(finance.rendement_locatif_net(9600, 0, 0, 0))


if __name__ == "__main__":
    unittest.main()
