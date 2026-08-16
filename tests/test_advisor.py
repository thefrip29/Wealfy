"""Tests des observations patrimoniales.

Chaque règle est vérifiée dans les DEUX sens : qu'elle se déclenche quand il
faut, et surtout qu'elle se tait quand il ne faut pas. Une alerte qui crie pour
rien est pire que pas d'alerte — on apprend à ne plus la lire.
"""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import advisor, finance  # noqa: E402

REGLAGES = {
    "plafonds": {"Livret": 22950, "LDDS": 12000, "LEP": 10000,
                 "LivretJeune": 1600, "PEL": 61200, "CEL": 15300, "PEA": 150000},
    "mois_precaution_cible": 4,
    "seuil_concentration": 40,
    "seuil_crypto": 10,
    "seuil_endettement": 35,
}

METRICS_NEUTRES = {
    "mois_couverture_urgence": 6, "solde_livrets": 12000,
    "depenses_moyennes_3m": 2000, "crypto_pct_patrimoine": 0,
    "crypto_montant": 0, "taux_endettement": 0, "mensualites_mois": 0,
    "revenus_mois": 3000,
}


def actif(**kw):
    base = {"id": "a1", "label": "Actif", "type": "Livret", "valeur": 1000,
            "investi": 1000, "famille": "Epargne reglementee",
            "date_acquisition": "2024-01-01", "metadata": {"taux_annuel": 3}}
    base.update(kw)
    return base


def snapshot(*actifs):
    return {"assets": list(actifs), "liabilities": []}


def titres(alertes):
    return " | ".join(a["titre"] for a in alertes)


class TestPlafonds(unittest.TestCase):
    def test_livret_sous_le_plafond_ne_dit_rien(self):
        snap = snapshot(actif(label="Livret A", type="Livret", valeur=15000))
        self.assertEqual(advisor.alertes(snap, METRICS_NEUTRES, reglages=REGLAGES), [])

    def test_livret_proche_du_plafond(self):
        snap = snapshot(actif(label="Livret A", type="Livret", valeur=22000))
        a = advisor.alertes(snap, METRICS_NEUTRES, reglages=REGLAGES)
        self.assertEqual(len(a), 1)
        self.assertIn("proche du plafond", a[0]["titre"])
        self.assertEqual(a[0]["asset_id"], "a1")

    def test_depassement_explique_les_interets_sans_dramatiser(self):
        """Le plafond porte sur les VERSEMENTS : un depassement par interets
        capitalises est normal et doit etre presente comme tel."""
        snap = snapshot(actif(label="Livret A", type="Livret", valeur=24000))
        a = advisor.alertes(snap, METRICS_NEUTRES, reglages=REGLAGES)[0]
        self.assertIn("au-dessus du plafond", a["titre"])
        self.assertIn("normal", a["detail"])
        self.assertIn("intérêts capitalisés", a["detail"])
        # Un depassement de plafond n'est pas une urgence.
        self.assertEqual(a["niveau"], "info")

    def test_chaque_produit_a_son_propre_plafond(self):
        snap = snapshot(
            actif(id="a1", label="LDDS", type="LDDS", valeur=11800),
            actif(id="a2", label="Livret Jeune", type="LivretJeune", valeur=1600),
            actif(id="a3", label="LEP", type="LEP", valeur=5000),
        )
        a = advisor.alertes(snap, METRICS_NEUTRES, reglages=REGLAGES)
        self.assertEqual(len(a), 2)          # le LEP est loin de son plafond
        self.assertNotIn("LEP", titres(a))

    def test_pea_compare_les_versements_pas_la_valeur(self):
        """Un PEA peut valoir plus que 150 000 € : seul le versement est plafonne."""
        snap = snapshot(actif(id="p", label="PEA", type="PEA",
                              famille="Marches financiers",
                              valeur=200000, investi=100000, metadata={}))
        self.assertEqual(
            [x for x in advisor.alertes(snap, METRICS_NEUTRES, reglages=REGLAGES)
             if "plafond" in x["titre"]], [])

        satur = snapshot(actif(id="p", label="PEA", type="PEA",
                               famille="Marches financiers",
                               valeur=160000, investi=150000, metadata={}))
        a = [x for x in advisor.alertes(satur, METRICS_NEUTRES, reglages=REGLAGES)
             if "plafond" in x["titre"]]
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0]["niveau"], "attention")

    def test_un_produit_sans_plafond_est_ignore(self):
        snap = snapshot(actif(label="Compte courant", type="CompteCourant",
                              famille="Liquidites", valeur=99999, metadata={}))
        a = advisor.alertes(snap, METRICS_NEUTRES, reglages=REGLAGES)
        self.assertNotIn("plafond", titres(a))


class TestMaturites(unittest.TestCase):
    def test_pea_immature_annonce_son_echeance(self):
        ouverture = finance.add_months(date.today(), -24)
        snap = snapshot(actif(id="p", label="PEA", type="PEA",
                              famille="Marches financiers", valeur=5000,
                              investi=5000, metadata={},
                              date_acquisition=ouverture.isoformat()))
        a = [x for x in advisor.alertes(snap, METRICS_NEUTRES, reglages=REGLAGES)
             if "maturité" in x["titre"]]
        self.assertEqual(len(a), 1)
        self.assertIn("36 mois", a[0]["detail"])

    def test_pea_mature_ne_dit_plus_rien(self):
        """Une fois le seuil franchi il n'y a plus rien a surveiller :
        le repeter indefiniment serait du bruit."""
        ouverture = finance.add_months(date.today(), -72)
        snap = snapshot(actif(id="p", label="PEA", type="PEA",
                              famille="Marches financiers", valeur=5000,
                              investi=5000, metadata={},
                              date_acquisition=ouverture.isoformat()))
        a = advisor.alertes(snap, METRICS_NEUTRES, reglages=REGLAGES)
        self.assertNotIn("maturité", titres(a))

    def test_assurance_vie_a_huit_ans(self):
        ouverture = finance.add_months(date.today(), -12)
        snap = snapshot(actif(id="v", label="AV", type="AssuranceVie",
                              famille="Marches financiers", valeur=5000,
                              investi=5000, metadata={},
                              date_acquisition=ouverture.isoformat()))
        a = [x for x in advisor.alertes(snap, METRICS_NEUTRES, reglages=REGLAGES)
             if "maturité" in x["titre"]]
        self.assertEqual(len(a), 1)
        self.assertIn("8 ans", a[0]["detail"])


class TestRatios(unittest.TestCase):
    def test_precaution_sous_la_cible(self):
        metrics = {**METRICS_NEUTRES, "mois_couverture_urgence": 1.5}
        a = advisor.alertes(snapshot(), metrics, reglages=REGLAGES)
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0]["niveau"], "attention")
        self.assertIn("précaution", a[0]["titre"])

    def test_precaution_atteinte_ne_dit_rien(self):
        metrics = {**METRICS_NEUTRES, "mois_couverture_urgence": 4}
        self.assertEqual(advisor.alertes(snapshot(), metrics, reglages=REGLAGES), [])

    def test_precaution_inconnue_ne_dit_rien(self):
        """Sans depenses de reference, le ratio n'existe pas."""
        metrics = {**METRICS_NEUTRES, "mois_couverture_urgence": None}
        self.assertEqual(advisor.alertes(snapshot(), metrics, reglages=REGLAGES), [])

    def test_endettement_au_dessus_du_seuil(self):
        metrics = {**METRICS_NEUTRES, "taux_endettement": 45,
                   "mensualites_mois": 900, "revenus_mois": 2000}
        a = advisor.alertes(snapshot(), metrics, reglages=REGLAGES)
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0]["niveau"], "attention")
        self.assertIn("35", a[0]["detail"])

    def test_endettement_sous_le_seuil(self):
        metrics = {**METRICS_NEUTRES, "taux_endettement": 22}
        self.assertEqual(advisor.alertes(snapshot(), metrics, reglages=REGLAGES), [])


class TestConcentration(unittest.TestCase):
    def test_ligne_dominante_signalee(self):
        snap = snapshot(
            actif(id="a1", label="PEA", type="PEA", famille="Marches financiers",
                  valeur=80000, investi=80000, metadata={}),
            actif(id="a2", label="Livret A", type="Livret", valeur=10000),
        )
        a = [x for x in advisor.alertes(snap, METRICS_NEUTRES, reglages=REGLAGES)
             if "concentre" in x["titre"]]
        self.assertEqual(len(a), 1)
        self.assertIn("PEA", a[0]["titre"])

    def test_repartition_equilibree_ne_dit_rien(self):
        snap = snapshot(
            actif(id="a1", label="PEA", type="PEA", famille="Marches financiers",
                  valeur=10000, investi=10000, metadata={}),
            actif(id="a2", label="Livret A", type="Livret", valeur=10000),
            actif(id="a3", label="LDDS", type="LDDS", valeur=10000),
        )
        a = advisor.alertes(snap, METRICS_NEUTRES, reglages=REGLAGES)
        self.assertNotIn("concentre", titres(a))

    def test_immobilier_exclu_du_calcul(self):
        """Comparer une ligne de PEA au poids d'un appartement n'aurait pas de
        sens : la concentration ne porte que sur les actifs financiers."""
        snap = snapshot(
            actif(id="a1", label="Studio", type="Immobilier", famille="Immobilier",
                  valeur=200000, investi=200000, metadata={}),
            actif(id="a2", label="Livret A", type="Livret", valeur=10000),
        )
        a = advisor.alertes(snap, METRICS_NEUTRES, reglages=REGLAGES)
        self.assertNotIn("concentre", titres(a))

    def test_crypto_au_dessus_du_seuil(self):
        metrics = {**METRICS_NEUTRES, "crypto_pct_patrimoine": 18,
                   "crypto_montant": 9000}
        a = [x for x in advisor.alertes(snapshot(), metrics, reglages=REGLAGES)
             if "crypto" in x["titre"].lower()]
        self.assertEqual(len(a), 1)


class TestRepartitionCible(unittest.TestCase):
    def test_ecart_important_signale(self):
        rep = {"buckets": [
            {"label": "PEA", "reel_pct": 25, "cible_pct": 50,
             "ecart_pct": -25, "ecart_montant": -5000}]}
        a = advisor.alertes(snapshot(), METRICS_NEUTRES, rep, reglages=REGLAGES)
        self.assertEqual(len(a), 1)
        self.assertIn("en dessous", a[0]["titre"])

    def test_plusieurs_ecarts_tiennent_en_une_ligne(self):
        """Trois alertes pour un meme sujet noieraient les autres observations."""
        rep = {"buckets": [
            {"label": "PEA", "reel_pct": 0, "cible_pct": 50,
             "ecart_pct": -50, "ecart_montant": -5000},
            {"label": "Livret", "reel_pct": 100, "cible_pct": 30,
             "ecart_pct": 70, "ecart_montant": 7000},
            {"label": "Depot", "reel_pct": 0, "cible_pct": 20,
             "ecart_pct": -20, "ecart_montant": -2000}]}
        a = advisor.alertes(snapshot(), METRICS_NEUTRES, rep, reglages=REGLAGES)
        self.assertEqual(len(a), 1)
        self.assertIn("3 poches", a[0]["titre"])
        for poche in ("PEA", "Livret", "Depot"):
            self.assertIn(poche, a[0]["detail"])

    def test_petit_ecart_tolere(self):
        rep = {"buckets": [
            {"label": "PEA", "reel_pct": 47, "cible_pct": 50,
             "ecart_pct": -3, "ecart_montant": -600}]}
        self.assertEqual(
            advisor.alertes(snapshot(), METRICS_NEUTRES, rep, reglages=REGLAGES), [])


class TestDivers(unittest.TestCase):
    def test_livret_sans_taux(self):
        snap = snapshot(actif(label="Livret A", type="Livret", valeur=5000,
                              metadata={}))
        a = [x for x in advisor.alertes(snap, METRICS_NEUTRES, reglages=REGLAGES)
             if "Taux manquant" in x["titre"]]
        self.assertEqual(len(a), 1)

    def test_livret_avec_taux_ne_dit_rien(self):
        snap = snapshot(actif(label="Livret A", type="Livret", valeur=5000,
                              metadata={"taux_annuel": 3}))
        self.assertNotIn("Taux manquant",
                         titres(advisor.alertes(snap, METRICS_NEUTRES, reglages=REGLAGES)))

    def test_cours_perimes_seulement_si_actives(self):
        eteint = {"active": False, "cache_perime": True}
        self.assertEqual(
            advisor.alertes(snapshot(), METRICS_NEUTRES, None, eteint, REGLAGES), [])
        allume = {"active": True, "cache_perime": True}
        a = advisor.alertes(snapshot(), METRICS_NEUTRES, None, allume, REGLAGES)
        self.assertEqual(len(a), 1)
        self.assertIn("périmés", a[0]["titre"])

    def test_patrimoine_vide_ne_produit_aucune_alerte(self):
        """Au premier lancement, l'ecran doit rester silencieux."""
        vide = {"mois_couverture_urgence": None, "solde_livrets": 0,
                "depenses_moyennes_3m": 0, "crypto_pct_patrimoine": None,
                "taux_endettement": None, "revenus_mois": 0}
        self.assertEqual(advisor.alertes(snapshot(), vide, reglages=REGLAGES), [])

    def test_les_urgences_passent_devant(self):
        snap = snapshot(actif(label="Livret A", type="Livret", valeur=24000))
        metrics = {**METRICS_NEUTRES, "mois_couverture_urgence": 1}
        a = advisor.alertes(snap, metrics, reglages=REGLAGES)
        self.assertEqual(a[0]["niveau"], "attention")
        self.assertEqual(a[-1]["niveau"], "info")


if __name__ == "__main__":
    unittest.main()
