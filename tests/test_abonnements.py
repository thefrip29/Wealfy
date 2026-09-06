# -*- coding: utf-8 -*-
"""Tests du détecteur d'abonnements.

Le risque n'est pas de manquer un abonnement : c'est d'en inventer. Un
marchand fréquenté ressemble de loin à un abonnement — il revient, il coûte —
et le compter gonflerait un total annuel censé aider à décider.
"""
import os
import random
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import abonnements  # noqa: E402

AUJOURDHUI = date(2026, 9, 6)


def serie(libelle, montant, depart, ecart, nombre, categorie="Abonnements"):
    """Une suite de prélèvements réguliers."""
    return [{
        "date": (depart + timedelta(days=round(ecart * i))).isoformat(),
        "description": libelle,
        "amount": -montant,
        "category": categorie,
    } for i in range(nombre)]


class TestCeQuiEstUnAbonnement(unittest.TestCase):
    def test_mensuel(self):
        tx = serie("NETFLIX.COM", 13.49, date(2026, 2, 15), 30.4, 7)
        (a,) = abonnements.detecter(tx, AUJOURDHUI)
        self.assertEqual(a["periodicite"], "mensuel")
        self.assertEqual(a["montant"], 13.49)
        self.assertEqual(a["cout_annuel"], round(13.49 * 12, 2))
        self.assertTrue(a["actif"])

    def test_annuel(self):
        tx = serie("OVH HEBERGEMENT", 71.88, date(2023, 3, 2), 365, 3)
        (a,) = abonnements.detecter(tx, AUJOURDHUI)
        self.assertEqual(a["periodicite"], "annuel")
        self.assertEqual(a["cout_annuel"], 71.88)

    def test_jours_de_prelevement_qui_glissent(self):
        """Un prélèvement « le 15 » tombe à 28, 30 ou 31 jours d'écart, et un
        jour ouvré le décale encore. Exiger 30 pile ne trouverait rien."""
        depart = date(2026, 1, 15)
        jours = [0, 31, 59, 92, 120, 153, 181]
        tx = [{
            "date": (depart + timedelta(days=j)).isoformat(),
            "description": "SPOTIFY", "amount": -11.99, "category": "Abonnements",
        } for j in jours]
        (a,) = abonnements.detecter(tx, AUJOURDHUI)
        self.assertEqual(a["periodicite"], "mensuel")


class TestCeQuiN_enEstPasUn(unittest.TestCase):
    def test_marchand_frequente_mais_irregulier(self):
        """Quarante-six courses Grab dans un mois ne sont pas un abonnement.
        C'est le cas qui doit rester exclu : il revient, et il coûte."""
        random.seed(7)
        tx = [{
            "date": (date(2026, 1, 3) + timedelta(days=random.randint(0, 240))).isoformat(),
            "description": "Grab* A-9l%d, Jakarta" % i,
            "amount": -round(random.uniform(1, 12), 2),
            "category": "Transport",
        } for i in range(30)]
        self.assertEqual(abonnements.detecter(tx, AUJOURDHUI), [])

    def test_montants_trop_disperses(self):
        """Régulier mais de montant variable : une facture d'électricité au
        réel, pas un abonnement à prix fixe."""
        depart = date(2026, 1, 10)
        tx = [{
            "date": (depart + timedelta(days=round(30.4 * i))).isoformat(),
            "description": "EDF FACTURE", "amount": -m, "category": "Logement",
        } for i, m in enumerate([40.0, 95.0, 60.0, 130.0, 55.0, 110.0])]
        self.assertEqual(abonnements.detecter(tx, AUJOURDHUI), [])

    def test_deux_prelevements_ne_suffisent_pas(self):
        """Un seul écart n'est pas régulier : il est unique."""
        tx = serie("CANAL+", 24.90, date(2026, 6, 1), 30.4, 2)
        self.assertEqual(abonnements.detecter(tx, AUJOURDHUI), [])

    def test_plusieurs_achats_le_meme_jour(self):
        """Trois passages en caisse le même jour ne font pas une période."""
        tx = [{
            "date": "2026-05-04", "description": "MONOPRIX",
            "amount": -12.0, "category": "Alimentation",
        } for _ in range(4)]
        self.assertEqual(abonnements.detecter(tx, AUJOURDHUI), [])

    def test_les_credits_sont_ignores(self):
        """Un salaire est mensuel, stable et régulier. Ce n'est pas un
        abonnement : un abonnement sort de l'argent."""
        tx = serie("VIR SALAIRE", -2100.0, date(2026, 2, 1), 30.4, 6)
        self.assertEqual(abonnements.detecter(tx, AUJOURDHUI), [])


class TestCeQuiMeriteUnRegard(unittest.TestCase):
    def test_hausse_de_prix_signalee(self):
        depart = date(2026, 2, 15)
        montants = [11.99, 11.99, 11.99, 13.99, 13.99]
        tx = [{
            "date": (depart + timedelta(days=round(30.4 * i))).isoformat(),
            "description": "SPOTIFY", "amount": -m, "category": "Abonnements",
        } for i, m in enumerate(montants)]
        (a,) = abonnements.detecter(tx, AUJOURDHUI)
        self.assertIsNotNone(a["augmentation"])
        self.assertEqual(a["augmentation"]["avant"], 11.99)
        self.assertEqual(a["augmentation"]["apres"], 13.99)
        self.assertEqual(a["augmentation"]["hausse"], 2.0)

    def test_prix_stable_ne_signale_rien(self):
        tx = serie("NETFLIX", 13.49, date(2026, 2, 15), 30.4, 6)
        (a,) = abonnements.detecter(tx, AUJOURDHUI)
        self.assertIsNone(a["augmentation"])

    def test_abonnement_arrete(self):
        """Plus rien depuis des mois : soit il est résilié, soit il ne l'est
        pas et c'est justement ce qu'on veut savoir."""
        tx = serie("DEEZER", 10.99, date(2025, 1, 10), 30.4, 5)
        (a,) = abonnements.detecter(tx, AUJOURDHUI)
        self.assertFalse(a["actif"])
        self.assertIsNone(a["prochain"])

    def test_le_resume_ne_compte_que_les_actifs(self):
        tx = (serie("NETFLIX", 10.0, date(2026, 3, 1), 30.4, 6)
              + serie("DEEZER", 10.99, date(2024, 1, 10), 30.4, 5))
        trouves = abonnements.detecter(tx, AUJOURDHUI)
        r = abonnements.resume(trouves)
        self.assertEqual(r["nb"], 1)
        self.assertEqual(r["nb_arretes"], 1)
        self.assertEqual(r["cout_annuel"], 120.0)
        self.assertEqual(r["cout_mensuel"], 10.0)

    def test_le_plus_cher_a_l_annee_en_premier(self):
        tx = (serie("PETIT", 3.0, date(2026, 3, 1), 30.4, 6)
              + serie("GROS", 40.0, date(2026, 3, 5), 30.4, 6))
        trouves = abonnements.detecter(tx, AUJOURDHUI)
        self.assertEqual([a["libelle"] for a in trouves], ["GROS", "PETIT"])


if __name__ == "__main__":
    unittest.main()
