# -*- coding: utf-8 -*-
"""Tests de la devise d'affichage.

Les données restent en euros de bout en bout : la base, l'API, les calculs.
Seule la lecture de l'onglet Patrimoine change, et la conversion se fait au
dernier moment, dans le navigateur. Ces tests gardent cette propriété — c'est
elle qui fait qu'un taux qui bouge ne réécrit jamais l'histoire.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import market  # noqa: E402
from tests.test_api import ApiTestCase  # noqa: E402


class FauxFournisseurFx(market.Provider):
    """Un fournisseur qui compte ses sorties et sait rendre un taux."""

    name = "faux"

    def __init__(self, prix=None, taux=1.0901):
        self.prix = prix or {}
        self.taux = taux
        self.appels_fx = 0

    def quotes(self, items):
        return ({i["cle"]: {"price": self.prix.get(i["symbol"], 100.0),
                            "currency": "EUR", "date": "2026-09-05"}
                 for i in items if i["symbol"] in self.prix},
                [])

    def fx(self, base, quote="EUR"):
        if base == quote:
            return 1.0
        self.appels_fx += 1
        return self.taux if (base, quote) == ("EUR", "USD") else 1.0


class TestTauxDAffichage(ApiTestCase):
    def enable_market(self, key="fake-key"):
        self.client.put("/api/settings", json={
            "market_enabled": True, "market_api_key": key,
        })

    def test_absent_tant_qu_aucun_rafraichissement(self):
        """Un taux jamais relevé n'est pas une panne : l'euro reste seul, et
        l'interface le dit plutôt que de convertir avec un chiffre inventé."""
        res = self.get("/api/fx")
        (usd,) = res["devises"]
        self.assertEqual(usd["code"], "USD")
        self.assertIsNone(usd["taux"])

    def test_releve_pendant_le_rafraichissement_des_cours(self):
        self.enable_market()
        cto = self.post("/api/assets", {
            "type": "CTO", "label": "CTO", "date_acquisition": "2024-01-01",
            "valeur_acquisition": 0,
        })
        self.post(f"/api/assets/{cto['id']}/movements", {
            "date": "2024-01-05", "montant": 1000, "type": "versement",
            "ticker": "CW8", "quantite": 10, "prix_unitaire": 100,
        })
        self.post("/api/securities", {"ticker": "CW8", "symbol": "CW8", "currency": "EUR"})

        with self.app.app_context():
            market.refresh_quotes(FauxFournisseurFx({"CW8": 120.0}))

        (usd,) = self.get("/api/fx")["devises"]
        self.assertEqual(usd["code"], "USD")
        self.assertAlmostEqual(usd["taux"], 1.0901, places=4)
        self.assertTrue(usd["date"])

    def test_repli_sur_le_taux_inverse_deja_en_cache(self):
        """Le cache contient dejà USD -> EUR, relevé depuis toujours pour
        convertir les titres cotés en dollars.

        Attendre un rafraîchissement pour le même renseignement rendait la
        lecture en dollars indisponible sans aucune raison : le chiffre était
        là, simplement à l'envers.
        """
        with self.app.app_context():
            market.store_quote("FX:USDEUR", "faux", "2026-08-31", 0.86084, "EUR")
            taux = market.taux_affichage("USD")
        self.assertAlmostEqual(taux["taux"], 1 / 0.86084, places=5)
        self.assertEqual(taux["date"], "2026-08-31")

    def test_le_taux_direct_prime_sur_l_inverse(self):
        """Un taux relevé dans le bon sens est plus juste qu'un inverse."""
        with self.app.app_context():
            market.store_quote("FX:USDEUR", "faux", "2026-08-31", 0.86084, "EUR")
            market.store_quote("FX:EURUSD", "faux", "2026-09-05", 1.0901, "USD")
            taux = market.taux_affichage("USD")
        self.assertAlmostEqual(taux["taux"], 1.0901, places=4)

    def test_aucune_sortie_reseau_sans_cours_a_demander(self):
        """Le garde-fou : un portefeuille sans rien à coter ne doit déclencher
        aucun appel, taux de change compris."""
        self.enable_market()
        self.post("/api/assets", {
            "type": "Livret", "label": "Livret A", "date_acquisition": "2023-01-01",
            "valeur_acquisition": 6000, "valeur_actuelle": 6000,
        })
        espion = FauxFournisseurFx()
        with self.app.app_context():
            market.refresh_quotes(espion)
        self.assertEqual(espion.appels_fx, 0)

    def test_les_montants_de_l_api_restent_en_euros(self):
        """Le point le plus important : la conversion est un habillage.

        Si un jour l'API se mettait à répondre en dollars, tout l'historique
        deviendrait faux au premier mouvement du taux.
        """
        self.enable_market()
        self.post("/api/assets", {
            "type": "Livret", "label": "Livret A", "date_acquisition": "2023-01-01",
            "valeur_acquisition": 6000, "valeur_actuelle": 6000,
        })
        with self.app.app_context():
            market.refresh_quotes(FauxFournisseurFx({"CW8": 120.0}))
        snap = self.get("/api/assets")
        self.assertEqual(snap["total_actif"], 6000.0)


if __name__ == "__main__":
    unittest.main()
