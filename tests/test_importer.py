"""Tests du parsing des relevés, de la déduplication et de la classification."""
import logging
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import finance, importer  # noqa: E402

REVOLUT = """Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance
CARD_PAYMENT,Current,2024-03-02 09:12:00,2024-03-02 09:12:00,Carrefour City,-24.30,0.00,EUR,COMPLETED,1200.00
TOPUP,Current,2024-03-05 08:00:00,2024-03-05 08:00:00,Virement SALAIRE MARS,2100.00,0.00,EUR,COMPLETED,3300.00
CARD_PAYMENT,Current,2024-03-07 20:01:00,2024-03-07 20:01:00,Netflix,-13.49,0.00,EUR,COMPLETED,3286.51
CARD_PAYMENT,Current,2024-03-08 20:01:00,2024-03-08 20:01:00,Annulee,-99.00,0.00,EUR,REVERTED,3286.51
"""

LCL_TEXT = """Date;Libelle;Debit;Credit
04/03/2024;PRLV EDF FACTURE;89,50;
06/03/2024;VIR M. DUPONT LOYER;;750,00
11/03/2024;CB LECLERC;1 234,56;
"""


class TestAmountParsing(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(importer.parse_amount("-25.30"), -25.30)
        self.assertEqual(importer.parse_amount("1 234,56"), 1234.56)
        self.assertEqual(importer.parse_amount("1,234.56"), 1234.56)
        self.assertEqual(importer.parse_amount("1.234,56"), 1234.56)
        self.assertEqual(importer.parse_amount("89,50 €"), 89.50)
        self.assertEqual(importer.parse_amount("(12,00)"), -12.00)
        self.assertIsNone(importer.parse_amount(""))
        self.assertIsNone(importer.parse_amount("abc"))


class TestStatementParsing(unittest.TestCase):
    def test_revolut_csv(self):
        lines, warnings = importer.parse_statement(REVOLUT)
        self.assertEqual(len(lines), 3, warnings)  # la ligne REVERTED est écartée
        self.assertEqual(lines[0]["date"], "2024-03-02")
        self.assertEqual(lines[0]["amount"], -24.30)
        self.assertEqual(lines[1]["amount"], 2100.00)
        self.assertIn("Netflix", lines[2]["description"])

    def test_lcl_debit_credit_columns(self):
        lines, warnings = importer.parse_statement(LCL_TEXT)
        self.assertEqual(len(lines), 3, warnings)
        self.assertEqual(lines[0]["amount"], -89.50)
        self.assertEqual(lines[1]["amount"], 750.00)
        self.assertEqual(lines[2]["amount"], -1234.56)
        self.assertEqual(lines[2]["date"], "2024-03-11")

    def test_positional_fallback(self):
        lines, warnings = importer.parse_statement(
            "2024-01-05;Boulangerie;-4,20\n2024-01-06;Pharmacie;-18,00")
        self.assertEqual(len(lines), 2)
        self.assertTrue(any("positionnelle" in w for w in warnings))
        self.assertEqual(lines[0]["amount"], -4.20)

    def test_empty_input(self):
        lines, warnings = importer.parse_statement("   ")
        self.assertEqual(lines, [])
        self.assertTrue(warnings)


PDF_DEUX_COLONNES = """
Date       Libelle                              Debit        Credit
01/03/2024 SOLDE PRECEDENT                                 1 240,00
03/03/2024 CB CARREFOUR MARKET                  45,30
07/03/2024 VIR SEPA SALAIRE ACME                            2 450,00
15/03/2024 VIR M DUPONT LOYER                                 700,00
28/03/2024 PRLV NETFLIX                         13,49
31/03/2024 NOUVEAU SOLDE                                    5 550,37
"""

PDF_UNE_COLONNE = """
03/03/2024 CB CARREFOUR 45,30
05/03/2024 PRLV EDF 118,74
07/03/2024 VIR SALAIRE +2450,00
"""


def pypdf_silencieux(test):
    """pypdf journalise sur stderr quand il refuse un PDF. C'est son travail,
    mais dans une suite de tests cette ligne ressemble a un echec."""
    logger = logging.getLogger("pypdf")
    niveau = logger.level
    logger.setLevel(logging.CRITICAL)
    test.addCleanup(logger.setLevel, niveau)


class TestReleveNonDelimite(unittest.TestCase):
    """Un releve imprime ou extrait d'un PDF n'a pas de separateur : ses
    colonnes sont alignees a l'espace, et le sens du montant tient a la colonne
    ou il se trouve, jamais a un signe."""

    def test_colonnes_debit_credit_par_alignement(self):
        lines, warnings = importer.parse_statement(PDF_DEUX_COLONNES)
        montants = {l["description"]: l["amount"] for l in lines}
        self.assertEqual(montants["CB CARREFOUR MARKET"], -45.30)
        self.assertEqual(montants["PRLV NETFLIX"], -13.49)
        self.assertEqual(montants["VIR SEPA SALAIRE ACME"], 2450.00)
        self.assertEqual(montants["VIR M DUPONT LOYER"], 700.00)
        self.assertTrue(any("alignement" in w for w in warnings))

    def test_soldes_ecartes(self):
        """Un solde porte une date et un montant : rien ne le distingue d'une
        operation sinon son libelle. L'inclure fausserait tous les totaux."""
        lines, _ = importer.parse_statement(PDF_DEUX_COLONNES)
        libelles = [l["description"] for l in lines]
        self.assertEqual(len(lines), 4)
        self.assertNotIn("SOLDE PRECEDENT", libelles)
        self.assertNotIn("NOUVEAU SOLDE", libelles)

    def test_une_seule_colonne_lue_en_debit(self):
        """Sans deuxieme colonne, rien ne dit qu'une ligne est un credit : on
        lit un debit et on le dit, plutot que d'inventer un sens."""
        lines, warnings = importer.parse_statement(PDF_UNE_COLONNE)
        self.assertEqual([l["amount"] for l in lines], [-45.30, -118.74, 2450.00])
        self.assertEqual(lines[2]["description"], "VIR SALAIRE")
        self.assertTrue(any("une seule colonne" in w.lower() for w in warnings))

    def test_milliers_sans_separateur(self):
        """« 2450,00 » ne doit pas se lire « 450,00 », le « 2 » restant colle
        au libelle."""
        lines, _ = importer.parse_statement("07/03/2024 VIR SALAIRE -2450,00")
        self.assertEqual(lines[0]["amount"], -2450.00)
        self.assertEqual(lines[0]["description"], "VIR SALAIRE")

    def test_dates_sur_deux_chiffres_et_points(self):
        lines, _ = importer.parse_statement("03.03.24 CB CARREFOUR 45,30")
        self.assertEqual(lines[0]["date"], "2024-03-03")

    def test_csv_delimite_garde_la_main(self):
        """La lecture delimitee distingue debit et credit sans deviner : elle
        reste prioritaire quand elle aboutit."""
        lines, warnings = importer.parse_statement(LCL_TEXT)
        self.assertEqual(len(lines), 3)
        self.assertFalse(any("alignement" in w for w in warnings))

    def test_entete_d_une_seule_colonne_n_est_pas_un_tableau(self):
        """La virgule decimale des montants suffisait a faire croire a un
        separateur : le releve entier etait alors lu de travers, chaque ligne
        atterrissant dans une seule cellule."""
        lines, _ = importer.parse_statement(PDF_DEUX_COLONNES)
        for ligne in lines:
            self.assertIsNone(importer.DATE_LIBRE.match(ligne["description"]))
            self.assertNotEqual(ligne["amount"], 0.0)


class TestExtractionFichier(unittest.TestCase):
    def test_texte_decode_en_utf8_et_cp1252(self):
        self.assertEqual(importer.extract_text("café".encode("utf-8")), "café")
        self.assertEqual(importer.extract_text("café".encode("cp1252")), "café")

    def test_bom_retire(self):
        bom = bytes([0xEF, 0xBB, 0xBF])
        self.assertEqual(importer.extract_text(bom + b"Date;Montant"), "Date;Montant")

    def test_fichier_vide(self):
        self.assertEqual(importer.extract_text(b""), "")

    def test_pdf_illisible_leve_une_erreur_parlante(self):
        pypdf_silencieux(self)
        with self.assertRaises(ValueError) as ctx:
            importer.extract_text(b"%PDF-1.4 nimporte quoi")
        self.assertIn("PDF", str(ctx.exception))


class TestDedup(unittest.TestCase):
    def test_hash_is_stable_and_normalised(self):
        a = importer.dedup_hash("2024-03-02", -24.3, "Carrefour  CITY")
        b = importer.dedup_hash(date(2024, 3, 2), -24.30, "carrefour city")
        self.assertEqual(a, b)
        c = importer.dedup_hash("2024-03-02", -24.31, "Carrefour City")
        self.assertNotEqual(a, c)


class TestClassification(unittest.TestCase):
    def setUp(self):
        self.rules = [
            {"id": "r1", "pattern": "SALAIRE", "cible_type": "type_revenu",
             "valeur": "Salaire", "priorite": 10},
            {"id": "r2", "pattern": "dupont", "cible_type": "type_revenu",
             "valeur": "Revenu locatif", "priorite": 20},
        ]
        liab = {
            "id": "L1", "montant_emprunte": 200000, "taux_annuel": 3.5,
            "duree_mois": 240, "date_debut": "2024-01-15", "assurance_mensuelle": 0.0,
        }
        self.liabs = [(liab, finance.liability_summary(liab, "2024-06-01"))]
        self.mensualite = self.liabs[0][1]["mensualite"]

    def test_rule_wins(self):
        line = {"date": "2024-03-05", "description": "Virement SALAIRE MARS", "amount": 2100.0}
        cat, lid, origin = importer.classify(line, self.rules, self.liabs)
        self.assertEqual(cat, "Salaire")
        self.assertEqual(origin, "regle")
        self.assertIsNone(lid)

    def test_rule_is_accent_and_case_insensitive(self):
        line = {"date": "2024-03-06", "description": "VIR M. DUPÔNT LOYER", "amount": 750.0}
        cat, _, _ = importer.classify(line, self.rules, self.liabs)
        self.assertEqual(cat, "Revenu locatif")

    def test_loan_detected_by_amount_and_date(self):
        line = {"date": "2024-04-15", "description": "PRLV BANQUE 55512",
                "amount": -round(self.mensualite, 2)}
        cat, lid, origin = importer.classify(line, self.rules, self.liabs)
        self.assertEqual(cat, "Remboursement pret")
        self.assertEqual(lid, "L1")
        self.assertEqual(origin, "pret")

    def test_loan_not_detected_when_amount_is_off(self):
        line = {"date": "2024-04-15", "description": "PRLV BANQUE",
                "amount": -(self.mensualite + 50)}
        _, lid, _ = importer.classify(line, self.rules, self.liabs)
        self.assertIsNone(lid)

    def test_loan_not_detected_far_from_due_date(self):
        line = {"date": "2024-04-30", "description": "PRLV BANQUE",
                "amount": -round(self.mensualite, 2)}
        _, lid, _ = importer.classify(line, self.rules, self.liabs)
        self.assertIsNone(lid)

    def test_keyword_fallback(self):
        line = {"date": "2024-03-02", "description": "CARREFOUR CITY", "amount": -24.30}
        cat, _, origin = importer.classify(line, [], [])
        self.assertEqual(cat, "Alimentation")
        self.assertEqual(origin, "mot-cle")

    def test_uncategorised_default(self):
        line = {"date": "2024-03-02", "description": "XYZ 4412", "amount": -10.0}
        cat, _, origin = importer.classify(line, [], [])
        self.assertEqual(cat, "Non categorise")
        self.assertEqual(origin, "defaut")


class TestMovementsParsing(unittest.TestCase):
    def test_broker_statement(self):
        text = (
            "Date,Instrument,Quantity,Price,Amount,Type\n"
            "2024-01-05,IE00B4L5Y983,2.5,89.10,222.75,Buy\n"
            "2024-02-05,IE00B4L5Y983,2.4,92.00,220.80,Buy\n"
            "2024-03-05,IE00B4L5Y983,1,95.00,95.00,Sell\n"
        )
        lines, warnings = importer.parse_movements(text)
        self.assertEqual(len(lines), 3, warnings)
        self.assertEqual(lines[0]["ticker"], "IE00B4L5Y983")
        self.assertEqual(lines[0]["quantite"], 2.5)
        self.assertEqual(lines[0]["prix_unitaire"], 89.10)
        self.assertEqual(lines[0]["type"], "versement")
        self.assertEqual(lines[2]["type"], "retrait")

    def test_amount_derived_from_qty_and_price(self):
        lines, _ = importer.parse_movements(
            "Date;Ticker;Quantite;Prix\n2024-01-05;CW8;2;100,50")
        self.assertEqual(lines[0]["montant"], 201.0)


if __name__ == "__main__":
    unittest.main()
