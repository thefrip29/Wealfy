"""Coherence des chiffres d'un ecran a l'autre, et d'une date a l'autre.

Chaque ecran recalcule ses chiffres a la volee. C'est ce qui les garde a jour,
et c'est aussi ce qui les laisse diverger : deux fonctions qui repondent a la
meme question peuvent ne pas donner la meme reponse. Ces tests posent les
egalites qui doivent tenir, sur un jeu de donnees qui melange tout.
"""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import finance  # noqa: E402
from tests.test_api import ApiTestCase  # noqa: E402


def fin_de_mois(offset):
    d = finance.add_months(date.today(), offset)
    return finance.month_bounds(d.year, d.month)[1]


def cle_mois(offset=0):
    d = finance.add_months(date.today(), offset)
    return f"{d.year:04d}-{d.month:02d}"


class TestClotureGardeLePasse(ApiTestCase):
    """Clore un produit le retire de la photo du jour, pas de l'histoire."""

    def setUp(self):
        super().setUp()
        il_y_a_deux_ans = finance.add_months(date.today(), -24).isoformat()
        self.garde = self.post("/api/assets", {
            "type": "Custom", "label": "Garde", "date_acquisition": il_y_a_deux_ans,
            "valeur_acquisition": 1000})["id"]
        self.close = self.post("/api/assets", {
            "type": "Custom", "label": "Close", "date_acquisition": il_y_a_deux_ans,
            "valeur_acquisition": 500})["id"]

    def test_le_patrimoine_d_un_mois_passe_ne_bouge_pas(self):
        passe = fin_de_mois(-3).isoformat()
        avant = self.get(f"/api/assets?date={passe}")["total_actif"]
        self.client.put(f"/api/assets/{self.close}", json={"archived": True})
        self.assertEqual(self.get(f"/api/assets?date={passe}")["total_actif"], avant)
        self.assertEqual(self.get("/api/assets")["total_actif"], 1000.0)

    def test_l_archive_et_la_courbe_ne_bougent_pas(self):
        mois = cle_mois(-3)
        archive = {r["mois"]: r for r in self.get("/api/history")["archive"]}
        avant = archive[mois]["patrimoine_net"]
        self.client.put(f"/api/assets/{self.close}", json={"archived": True})
        archive = {r["mois"]: r for r in self.get("/api/history")["archive"]}
        self.assertEqual(archive[mois]["patrimoine_net"], avant)

        serie = self.get(f"/api/overview?month={cle_mois()}")["patrimoine_serie"]
        self.assertEqual(serie[-4]["patrimoine_net"], avant)
        self.assertEqual(serie[-1]["patrimoine_net"], 1000.0)

    def test_rouvrir_le_ramene_aujourd_hui(self):
        self.client.put(f"/api/assets/{self.close}", json={"archived": True})
        self.client.put(f"/api/assets/{self.close}", json={"archived": False})
        self.assertEqual(self.get("/api/assets")["total_actif"], 1500.0)

    def test_le_gain_de_l_annee_ne_saute_pas(self):
        decembre = date(date.today().year - 1, 12, 15).isoformat()
        for aid in (self.garde, self.close):
            self.post(f"/api/assets/{aid}/valorisation",
                      {"valeur": 2000, "date": decembre})
        avant = self.get("/api/assets")["gain_annuel"]["montant"]
        self.client.put(f"/api/assets/{self.close}", json={"archived": True})
        self.assertEqual(self.get("/api/assets")["gain_annuel"]["montant"], avant)


class TestUneSeuleValeurParActif(ApiTestCase):

    def test_le_bien_immobilier_vaut_la_meme_chose_partout(self):
        bien = self.post("/api/assets", {
            "type": "Immobilier", "label": "Studio", "date_acquisition": "2020-01-15",
            "valeur_acquisition": 100000,
            "metadata": {"taux_revalorisation_annuel": 3}})
        liste = {a["id"]: a for a in self.get("/api/assets")["assets"]}
        fiche = self.get(f"/api/assets/{bien['id']}")
        self.assertGreater(liste[bien["id"]]["valeur"], 100000)
        self.assertEqual(fiche["immobilier"]["valeur"], liste[bien["id"]]["valeur"])
        self.assertEqual(fiche["asset"]["valeur"], liste[bien["id"]]["valeur"])

    def test_le_capital_investi_est_le_meme_dans_la_liste_et_la_fiche(self):
        pea = self.post("/api/assets", {
            "type": "PEA", "label": "PEA", "date_acquisition": "2022-01-10",
            "valeur_acquisition": 0})
        self.post(f"/api/assets/{pea['id']}/movements", {"date": "2022-02-01", "montant": 1000,
            "type": "versement"})
        self.post(f"/api/assets/{pea['id']}/movements", {"date": "2022-03-01", "montant": -12,
            "type": "frais"})
        liste = {a["id"]: a for a in self.get("/api/assets")["assets"]}
        fiche = self.get(f"/api/assets/{pea['id']}")
        self.assertEqual(fiche["asset"]["investi"], liste[pea["id"]]["investi"])
        self.assertEqual(fiche["marche"]["investi"], liste[pea["id"]]["investi"])

    def test_la_trajectoire_finit_sur_la_valeur_du_jour(self):
        self.post("/api/assets", {"type": "Livret", "label": "Livret A",
                                  "valeur_actuelle": 3000,
                                  "metadata": {"taux_annuel": 2.4}})
        self.post("/api/assets", {"type": "Custom", "label": "Montre",
                                  "date_acquisition": "2021-05-01",
                                  "valeur_acquisition": 800})
        liste = {a["id"]: a["valeur"] for a in self.get("/api/assets")["assets"]}
        series = self.get("/api/assets/series")["series"]
        self.assertEqual(len(series), 2)
        for s in series:
            self.assertEqual(s["valeurs"][-1], liste[s["id"]])


class TestFluxDuMois(ApiTestCase):

    def setUp(self):
        super().setUp()
        jour = date.today().replace(day=1)
        self.jour = jour
        for desc, montant, cat in [
            ("Salaire", 2500, "Salaire"),
            ("Carrefour", -120.40, "Alimentation"),
            ("Loyer", -800, "Logement"),
            ("Netflix", -13.49, "Abonnements"),
            ("Vers Revolut", -200, "Transfert interne"),
            ("De LCL", 200, "Transfert interne"),
        ]:
            self.post("/api/transactions", {
                "date": jour.isoformat(), "description": desc,
                "amount": montant, "category": cat})

    def test_les_categories_somment_aux_depenses(self):
        m = self.get(f"/api/month?month={cle_mois()}")
        self.assertAlmostEqual(
            sum(c["montant"] for c in m["par_categorie"]), m["depenses"], places=2)
        self.assertAlmostEqual(m["depenses"], 933.89, places=2)
        self.assertEqual(m["revenus"], 2500.0)

    def test_l_archive_et_la_synthese_disent_la_meme_chose(self):
        ov = self.get(f"/api/overview?month={cle_mois()}")
        ligne = {r["mois"]: r for r in self.get("/api/history")["archive"]}[cle_mois()]
        for cle in ("revenus", "depenses", "epargne", "solde"):
            self.assertEqual(ligne[cle], ov["mois"][cle], cle)
        self.assertEqual(ligne["patrimoine_net"], ov["metrics"]["patrimoine_net"])
        self.assertEqual(ov["patrimoine_serie"][-1]["patrimoine_net"],
                         ov["metrics"]["patrimoine_net"])

    def test_un_virement_d_epargne_n_est_pas_compte_deux_fois(self):
        """Le virement vers le livret figure sur le releve, et le versement
        est saisi sur le livret : c'est le meme euro."""
        livret = self.post("/api/assets", {
            "type": "Livret", "label": "Livret A",
            "date_acquisition": "2020-01-01", "valeur_acquisition": 1000})
        self.post("/api/transactions", {
            "date": self.jour.isoformat(), "description": "VIR LIVRET A",
            "amount": -300, "category": "Epargne/Investissement"})
        self.post(f"/api/assets/{livret['id']}/movements", {"type": "versement", "montant": 300,
            "date": (self.jour + timedelta(days=1)).isoformat()})
        self.assertEqual(self.get(f"/api/month?month={cle_mois()}")["epargne"], 300.0)

    def test_deux_versements_distincts_comptent_tous_les_deux(self):
        livret = self.post("/api/assets", {
            "type": "Livret", "label": "Livret A",
            "date_acquisition": "2020-01-01", "valeur_acquisition": 1000})
        self.post("/api/transactions", {
            "date": self.jour.isoformat(), "description": "VIR PEA",
            "amount": -300, "category": "Epargne/Investissement"})
        self.post(f"/api/assets/{livret['id']}/movements", {"type": "versement", "montant": 150,
            "date": self.jour.isoformat()})
        self.assertEqual(self.get(f"/api/month?month={cle_mois()}")["epargne"], 450.0)


class TestRatios(ApiTestCase):

    def test_la_base_des_ratios_est_exposee(self):
        """« 38 % des revenus » doit dire DE QUELS revenus."""
        for i in (1, 2, 3):
            d = finance.add_months(date.today(), -i).replace(day=2)
            self.post("/api/transactions", {"date": d.isoformat(), "description": "Paie",
                                            "amount": 2000, "category": "Salaire"})
            self.post("/api/transactions", {"date": d.isoformat(), "description": "Loyer",
                                            "amount": -500, "category": "Logement"})
        self.post("/api/transactions", {
            "date": date.today().replace(day=1).isoformat(), "description": "Loyer",
            "amount": -500, "category": "Logement"})
        m = self.get("/api/metrics")
        self.assertEqual(m["revenu_moyen_3m"], 2000.0)
        self.assertAlmostEqual(m["part_charges_fixes"], 25.0, places=2)

    def test_la_part_crypto_se_mesure_sur_les_actifs(self):
        """Avec un pret, le net peut etre minuscule : une part de 300 % ne
        veut rien dire."""
        self.post("/api/assets", {"type": "Custom", "label": "Maison",
                                  "date_acquisition": "2020-01-01",
                                  "valeur_acquisition": 100000})
        self.post("/api/assets", {"type": "Crypto", "label": "BTC",
                                  "date_acquisition": "2020-01-01",
                                  "valeur_acquisition": 10000})
        self.post("/api/liabilities", {
            "type": "PretImmobilier", "label": "Pret", "montant_emprunte": 200000,
            "taux_annuel": 2, "duree_mois": 300, "date_debut": date.today().isoformat()})
        m = self.get("/api/metrics")
        self.assertAlmostEqual(m["crypto_pct_actifs"], 100 * 10000 / 110000, places=1)

    def test_le_seuil_de_precaution_est_partage(self):
        self.client.put("/api/settings", json={"mois_precaution_cible": 6})
        self.assertEqual(self.get("/api/meta")["mois_precaution_cible"], 6)


class TestDecompositionDeLaVariation(ApiTestCase):
    """La variation du net, decoupee en quatre parts qui tombent juste."""

    def setUp(self):
        super().setUp()
        self.debut = finance.add_months(date.today(), -2).replace(day=1).isoformat()
        self.montre = self.post("/api/assets", {
            "type": "Custom", "label": "Montre", "date_acquisition": "2020-01-01",
            "valeur_acquisition": 1000})["id"]
        self.livret = self.post("/api/assets", {
            "type": "Custom", "label": "Coffre", "date_acquisition": "2020-01-01",
            "valeur_acquisition": 5000})["id"]

    def variation(self):
        return self.get(f"/api/overview?month={cle_mois()}")["variation"]

    def test_les_parts_somment_a_la_variation_du_heros(self):
        jour = date.today().replace(day=1).isoformat()
        self.post(f"/api/assets/{self.livret}/movements",
                  {"type": "versement", "montant": 400, "date": jour})
        self.post(f"/api/assets/{self.montre}/valorisation",
                  {"valeur": 1150, "date": jour})
        ov = self.get(f"/api/overview?month={cle_mois()}")
        v = ov["variation"]
        serie = ov["patrimoine_serie"]
        self.assertEqual(v["variation"],
                         round(serie[-1]["patrimoine_net"] - serie[-2]["patrimoine_net"], 2))
        self.assertEqual(v["apports"], 400.0)
        self.assertEqual(v["performance"], 150.0)
        self.assertAlmostEqual(
            v["apports"] + v["performance"] + v["immobilier"] + v["dettes"],
            v["variation"], places=2)

    def test_clore_est_un_retrait_pas_une_perte(self):
        self.client.put(f"/api/assets/{self.montre}", json={"archived": True})
        v = self.variation()
        self.assertEqual(v["apports"], -1000.0)
        self.assertEqual(v["performance"], 0.0)

    def test_un_pret_qui_s_amortit_est_un_remboursement(self):
        self.post("/api/liabilities", {
            "type": "PretConso", "label": "Auto", "montant_emprunte": 12000,
            "taux_annuel": 3, "duree_mois": 48, "date_debut": "2024-01-01"})
        v = self.variation()
        self.assertGreater(v["dettes"], 0)
        self.assertEqual(v["variation"], v["dettes"])

    def test_l_archive_porte_la_meme_decomposition(self):
        jour = date.today().replace(day=1).isoformat()
        self.post(f"/api/assets/{self.livret}/movements",
                  {"type": "versement", "montant": 250, "date": jour})
        ligne = {r["mois"]: r for r in self.get("/api/history")["archive"]}[cle_mois()]
        self.assertEqual(ligne["variation"], self.variation())


class TestEcartsDuMois(ApiTestCase):

    def depense(self, offset, montant, cat="Restaurants"):
        d = finance.add_months(date.today(), offset).replace(day=3)
        self.post("/api/transactions", {"date": d.isoformat(), "description": cat,
                                        "amount": -montant, "category": cat})

    def test_une_categorie_au_dessus_de_son_habitude(self):
        for i in range(1, 7):
            self.depense(-i, 180)
            self.depense(-i, 300, "Alimentation")
        self.depense(0, 420)
        self.depense(0, 310, "Alimentation")
        ecarts = self.get(f"/api/ecarts?month={cle_mois()}")
        self.assertEqual([e["category"] for e in ecarts], ["Restaurants"])
        self.assertEqual(ecarts[0]["habituel"], 180.0)
        self.assertEqual(ecarts[0]["ecart"], 240.0)

    def test_sans_recul_on_ne_dit_rien(self):
        self.depense(-1, 100)
        self.depense(0, 900)
        self.assertEqual(self.get(f"/api/ecarts?month={cle_mois()}"), [])


class TestAbonnementsObserves(unittest.TestCase):

    def abo(self, **k):
        base = {"libelle": "NETFLIX", "periodicite": "mensuel", "montant": 15.99,
                "cout_annuel": 191.88, "actif": True, "jours_depuis": 10,
                "dernier": date.today().isoformat(), "augmentation": None}
        base.update(k)
        return base

    def regle(self, abos):
        from app.advisor import _abonnements
        return _abonnements(abos, date.today())

    def test_une_hausse_recente_remonte(self):
        recent = (date.today() - timedelta(days=20)).isoformat()
        out = self.regle([self.abo(augmentation={
            "avant": 13.49, "apres": 15.99, "hausse": 2.5, "pct": 18.5,
            "depuis": recent})])
        self.assertEqual(len(out), 1)
        self.assertIn("30,00", out[0]["detail"].replace(" ", " "))

    def test_une_hausse_ancienne_se_tait(self):
        vieux = (date.today() - timedelta(days=400)).isoformat()
        self.assertEqual(self.regle([self.abo(augmentation={
            "avant": 13.49, "apres": 15.99, "hausse": 2.5, "pct": 18.5,
            "depuis": vieux})]), [])

    def test_un_arret_recent_remonte_un_arret_ancien_non(self):
        self.assertEqual(len(self.regle([self.abo(actif=False, jours_depuis=60)])), 1)
        self.assertEqual(self.regle([self.abo(actif=False, jours_depuis=500)]), [])


class TestTriAnnualise(ApiTestCase):

    def test_pas_de_tri_sous_un_an(self):
        """19 % en deux mois ne font pas 327 % par an."""
        debut = finance.add_months(date.today(), -2).isoformat()
        pea = self.post("/api/assets", {"type": "PEA", "label": "PEA",
                                        "date_acquisition": debut, "valeur_acquisition": 0})
        self.post(f"/api/assets/{pea['id']}/movements",
                  {"type": "versement", "montant": 1000, "date": debut})
        self.post(f"/api/assets/{pea['id']}/valorisation", {"valeur": 1190})
        marche = self.get(f"/api/assets/{pea['id']}")["marche"]
        self.assertIsNone(marche["tri_pct"])
        self.assertTrue(marche["tri_moins_d_un_an"])

    def test_tri_au_dela_d_un_an(self):
        pea = self.post("/api/assets", {"type": "PEA", "label": "PEA",
                                        "date_acquisition": "2020-01-01",
                                        "valeur_acquisition": 0})
        self.post(f"/api/assets/{pea['id']}/movements",
                  {"type": "versement", "montant": 1000, "date": "2020-01-01"})
        self.post(f"/api/assets/{pea['id']}/valorisation", {"valeur": 1500})
        marche = self.get(f"/api/assets/{pea['id']}")["marche"]
        self.assertIsNotNone(marche["tri_pct"])
        self.assertFalse(marche["tri_moins_d_un_an"])


class TestEpargneLueSurLesLivrets(ApiTestCase):
    """Recaler un livret sur le releve, c'est dire combien on y a mis."""

    def setUp(self):
        super().setUp()
        self.jour = date.today().replace(day=1).isoformat()
        self.livret = self.post("/api/assets", {
            "type": "Livret", "label": "Livret A", "date_acquisition": "2003-10-02",
            "valeur_acquisition": 4000, "metadata": {"taux_annuel": 2.4}})["id"]

    def test_une_hausse_de_solde_est_de_l_epargne_pas_une_plus_value(self):
        self.post(f"/api/assets/{self.livret}/valorisation",
                  {"valeur": 4458, "date": self.jour})
        self.assertEqual(self.get(f"/api/month?month={cle_mois()}")["epargne"], 458.0)
        livret = {a["id"]: a for a in self.get("/api/assets")["assets"]}[self.livret]
        self.assertEqual(livret["plus_value"], 0.0)
        self.assertEqual(self.get(f"/api/overview?month={cle_mois()}")["variation"]["apports"], 458.0)

    def test_une_baisse_de_solde_est_un_retrait(self):
        self.post(f"/api/assets/{self.livret}/valorisation",
                  {"valeur": 3756, "date": self.jour})
        self.assertEqual(self.get(f"/api/month?month={cle_mois()}")["epargne"], -244.0)

    def test_le_solde_pose_a_la_creation_n_est_pas_un_versement(self):
        self.post("/api/assets", {"type": "Livret", "label": "LDDS",
                                  "date_acquisition": "2015-01-01",
                                  "valeur_acquisition": 100, "valeur_actuelle": 2000})
        self.assertEqual(self.get(f"/api/month?month={cle_mois()}")["epargne"], 0.0)


class TestUnEchangeNEstPasDeLEpargne(ApiTestCase):

    def test_retrait_et_versement_s_annulent(self):
        jour = date.today().replace(day=1).isoformat()
        c = self.post("/api/assets", {"type": "Crypto", "label": "Crypto",
                                      "date_acquisition": "2024-01-01",
                                      "valeur_acquisition": 0})["id"]
        self.post(f"/api/assets/{c}/movements",
                  {"type": "retrait", "montant": 25.59, "date": jour, "ticker": "bitcoin"})
        self.post(f"/api/assets/{c}/movements",
                  {"type": "versement", "montant": 25.59, "date": jour, "ticker": "tether"})
        self.assertEqual(self.get(f"/api/month?month={cle_mois()}")["epargne"], 0.0)


if __name__ == "__main__":
    unittest.main()
