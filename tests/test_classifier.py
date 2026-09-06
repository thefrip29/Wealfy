# -*- coding: utf-8 -*-
"""Tests du classifieur local : regroupement par marchand et modèle appris."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import classifier, importer  # noqa: E402


class TestRacineMarchand(unittest.TestCase):
    """Sans racine commune, il y a autant de groupes que de courses, et le
    regroupement ne fait gagner aucune décision."""

    def test_variantes_du_meme_marchand_se_rejoignent(self):
        racines = {
            classifier.racine_marchand("Grab* A-9la554nwwmgeav, Jakarta Pusat"),
            classifier.racine_marchand("Grab* A-9lf26h6gwtxvav"),
            classifier.racine_marchand("CB GRAB 4657189"),
        }
        self.assertEqual(len(racines), 1, racines)

    def test_le_canal_de_paiement_ne_fait_pas_le_marchand(self):
        """« CB Carrefour » et « CB Netflix » ne doivent surtout pas se
        rejoindre sous la racine « cb »."""
        self.assertNotEqual(
            classifier.racine_marchand("CB CARREFOUR CITY"),
            classifier.racine_marchand("CB NETFLIX"),
        )

    def test_un_chiffre_dans_le_nom_n_est_pas_un_identifiant(self):
        """« 12Go » est un marchand, « 4657189 » un numéro de terminal."""
        self.assertEqual(classifier.racine_marchand("12Go"), "12go")
        self.assertEqual(classifier.racine_marchand("Agoda 4657189"), "agoda")


class TestRegroupement(unittest.TestCase):
    def lignes(self):
        return [
            {"description": "Grab", "amount": -6.94},
            {"description": "Grab", "amount": -2.10},
            {"description": "Grab", "amount": -4.00},
            {"description": "Agoda", "amount": -42.59},
            {"description": "Agoda", "amount": -26.04},
            {"description": "Un truc unique", "amount": -1.00},
        ]

    def test_groupes_tries_et_chiffres(self):
        groupes = classifier.regrouper(self.lignes())
        self.assertEqual([g["racine"] for g in groupes], ["grab", "agoda"])
        self.assertEqual(groupes[0]["nb"], 3)
        self.assertEqual(groupes[0]["total"], -13.04)
        self.assertEqual(groupes[0]["indices"], [0, 1, 2])

    def test_une_ligne_isolee_ne_fait_pas_un_groupe(self):
        """Un groupe d'une seule ligne ne fait économiser aucune décision : il
        encombrerait l'écran sans rien apporter."""
        racines = [g["racine"] for g in classifier.regrouper(self.lignes())]
        self.assertNotIn("un truc", racines)


class TestModele(unittest.TestCase):
    def modele(self):
        """Le modèle tel qu'il tourne : amorcé par la taxonomie intégrée.

        Sans cet amorçage, un modèle qui n'apprend que de l'historique ne sait
        rien le premier jour — et le premier jour est justement celui où l'on
        importe le plus."""
        return classifier.Modele().entrainer(
            classifier.exemples_d_amorcage() + [
                ("CARREFOUR MARKET NANTES", -1, "Alimentation"),
                ("CARREFOUR CITY PARIS", -1, "Alimentation"),
                ("LECLERC DRIVE", -1, "Alimentation"),
                ("NETFLIX.COM", -1, "Abonnements"),
                ("SPOTIFY AB STOCKHOLM", -1, "Abonnements"),
            ])

    def test_generalise_a_un_libelle_voisin(self):
        """Le point de tout l'exercice : reconnaître un libellé qu'on n'a jamais
        écrit dans aucune règle."""
        categorie, confiance = self.modele().predire("CARREFOUR EXPRESS LYON", -1)
        self.assertEqual(categorie, "Alimentation")
        self.assertGreaterEqual(confiance, classifier.SEUIL_CONFIANCE)

    def test_se_tait_sur_ce_qu_il_ne_connait_pas(self):
        """C'est le test qui empêche d'inventer. Une ligne « à classer » se voit
        et se corrige ; une ligne mal classée passe inaperçue et fausse les
        totaux. Sans seuil, le modèle tranchait juste six fois sur dix sur des
        marchands jamais vus."""
        _, confiance = self.modele().predire("ZQXJ WVBK", -1)
        self.assertLess(confiance, classifier.SEUIL_CONFIANCE)

    def test_un_modele_vierge_ne_dit_rien(self):
        categorie, confiance = classifier.Modele().predire("CARREFOUR", -1)
        self.assertIsNone(categorie)
        self.assertEqual(confiance, 0.0)

    def test_depenses_et_revenus_ne_se_melangent_pas(self):
        """Un modèle entraîné sur des dépenses n'a rien à dire d'un crédit."""
        depenses_seules = classifier.Modele().entrainer([
            ("CARREFOUR MARKET", -1, "Alimentation"),
            ("NETFLIX.COM", -1, "Abonnements"),
        ])
        categorie, _ = depenses_seules.predire("CARREFOUR CITY", 1)
        self.assertIsNone(categorie)


class TestOrdreDeDecision(unittest.TestCase):
    def ligne(self, description, amount=-12.0):
        return {"date": "2026-01-05", "description": description, "amount": amount}

    def test_une_regle_passe_devant_le_modele(self):
        """L'utilisateur a le dernier mot sur sa propre classification : un
        modèle ne doit jamais passer devant une consigne explicite."""
        modele = classifier.Modele().entrainer(
            classifier.exemples_d_amorcage() + [
                ("CARREFOUR MARKET", -1, "Alimentation"),
                ("CARREFOUR CITY", -1, "Alimentation"),
            ])
        regles = [{"id": "r1", "pattern": "carrefour",
                   "valeur": "Courses maison", "priorite": 1}]
        categorie, _, origine, _ = importer.classify(
            self.ligne("CARREFOUR EXPRESS"), regles, [],
            modele=modele, seuil=classifier.SEUIL_CONFIANCE,
        )
        self.assertEqual(categorie, "Courses maison")
        self.assertEqual(origine, "regle")

    def test_le_modele_est_signale_comme_tel(self):
        modele = classifier.Modele().entrainer(
            classifier.exemples_d_amorcage() + [
                ("PAUL BOULANGER NANTES", -1, "Restaurants"),
                ("PAUL BOULANGER RENNES", -1, "Restaurants"),
                ("PAUL BOULANGER BREST", -1, "Restaurants"),
            ])
        categorie, _, origine, confiance = importer.classify(
            self.ligne("PAUL BOULANGER QUIMPER"), [], [],
            modele=modele, seuil=classifier.SEUIL_CONFIANCE,
        )
        self.assertEqual(categorie, "Restaurants")
        self.assertEqual(origine, "modele")
        self.assertGreater(confiance, 0)

    def test_sans_modele_rien_ne_change(self):
        categorie, _, origine, _ = importer.classify(
            self.ligne("CB CARREFOUR CITY"), [], [])
        self.assertEqual(categorie, "Alimentation")
        self.assertEqual(origine, "mot-cle")


class TestMotsClesAuJeton(unittest.TestCase):
    """Chercher « bp » n'importe où dans un libellé le trouvait aussi bien dans
    « abonnement » que dans une station-service."""

    def test_mot_court_compare_au_jeton_entier(self):
        self.assertEqual(importer._apply_keywords("STATION BP QUIMPER", -1),
                         "Transport")
        self.assertNotEqual(importer._apply_keywords("VIREMENT BPCE", -1),
                            "Transport")

    def test_mot_long_reste_cherche_en_sous_chaine(self):
        """L'extraction d'un PDF colle parfois les mots d'un seul tenant."""
        self.assertEqual(importer._apply_keywords("CARREFOURMARKET", -1),
                         "Alimentation")

    def test_marchands_internationaux_reconnus(self):
        attendu = {
            "Grab": "Transport",
            "Agoda": "Voyages",
            "Dubai Airport": "Voyages",
            "Shopee": "Shopping",
        }
        for libelle, categorie in attendu.items():
            self.assertEqual(importer._apply_keywords(libelle, -1), categorie,
                             libelle)

    def test_revenus_en_anglais(self):
        self.assertEqual(importer._apply_keywords("Net Interest Paid", 1),
                         "Interets")


if __name__ == "__main__":
    unittest.main()
