"""Tests des sauvegardes CSV : création, légèreté, rotation, restauration."""
import csv
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import backup, create_app, paths  # noqa: E402


class BackupTestCase(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.mkdtemp()
        self.db_path = os.path.join(self.dossier, "patrimoine.db")
        # `data_dir()` sert de racine aux sauvegardes : on l'isole pour ne pas
        # écrire dans le vrai dossier de l'utilisateur pendant les tests.
        #
        # On remplace `appdata_dir` lui-même, et non la variable d'environnement
        # LOCALAPPDATA : celle-ci n'est lue que sur Windows depuis que le
        # dossier de données suit la convention de chaque système. Sur macOS et
        # sous Linux, l'isolation sautait donc en silence — les tests écrivaient
        # dans ~/Library/Application Support/Wealfy, s'y accumulaient d'un test
        # à l'autre, et polluaient les vraies sauvegardes de l'utilisateur.
        self._appdata = mock.patch.object(
            paths, "appdata_dir", return_value=self.dossier)
        self._appdata.start()
        self._frozen = getattr(sys, "frozen", None)
        sys.frozen = True                       # force le mode « données isolées »
        self.app = create_app(self.db_path)
        self.client = self.app.test_client()
        # Filet : si l'isolation cassait de nouveau, l'échec le dirait tout de
        # suite plutôt que par un compte de sauvegardes inattendu trois tests
        # plus loin.
        self.assertTrue(
            backup.backup_root().startswith(self.dossier),
            "les sauvegardes de test doivent rester dans le dossier temporaire")

    def tearDown(self):
        if self._frozen is None:
            del sys.frozen
        else:
            sys.frozen = self._frozen
        self._appdata.stop()
        shutil.rmtree(self.dossier, ignore_errors=True)

    def post(self, url, payload=None):
        res = self.client.post(url, json=payload or {})
        self.assertIn(res.status_code, (200, 201), res.get_data(as_text=True))
        return res.get_json()

    def get(self, url):
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        return res.get_json()

    def seed(self):
        self.post("/api/assets", {
            "type": "Livret", "label": "Livret A", "date_acquisition": "2026-01-01",
            "valeur_acquisition": 8200, "valeur_actuelle": 8200,
            "metadata": {"taux_annuel": 3}})
        self.post("/api/transactions", {
            "date": "2026-08-05", "description": "Courses", "amount": -42.5,
            "category": "Alimentation"})


class TestCreation(BackupTestCase):
    def test_backup_writes_readable_csv(self):
        self.seed()
        res = self.post("/api/backups")
        self.assertFalse(res["inchange"])

        dossier = res["chemin"]
        fichiers = sorted(os.listdir(dossier))
        self.assertIn("assets.csv", fichiers)
        self.assertIn("transactions.csv", fichiers)
        self.assertIn("resume.csv", fichiers)
        self.assertIn("manifeste.csv", fichiers)

        # Lisible avec le séparateur français, accents intacts.
        with open(os.path.join(dossier, "assets.csv"), encoding="utf-8-sig",
                  newline="") as fh:
            lignes = list(csv.reader(fh, delimiter=";"))
        self.assertIn("label", lignes[0])
        self.assertEqual(lignes[1][lignes[0].index("label")], "Livret A")

    def test_summary_is_understandable_on_its_own(self):
        self.seed()
        res = self.post("/api/backups")
        with open(os.path.join(res["chemin"], "resume.csv"), encoding="utf-8-sig",
                  newline="") as fh:
            lignes = list(csv.reader(fh, delimiter=";"))
        entetes = lignes[0]
        self.assertIn("valeur_eur", entetes)
        plat = [c for ligne in lignes for c in ligne]
        self.assertIn("Patrimoine net", plat)
        self.assertIn("Livret A", plat)

    def test_quotes_cache_is_not_saved(self):
        """La table la plus volumineuse est volontairement exclue."""
        self.seed()
        with self.app.app_context():
            from app import market
            for jour in range(1, 20):
                market.store_quote("CW8", "test", f"2026-08-{jour:02d}", 100 + jour)
        res = self.post("/api/backups")
        self.assertNotIn("quotes.csv", os.listdir(res["chemin"]))

    def test_api_key_never_leaves_the_database(self):
        self.client.put("/api/settings", json={"market_api_key": "SECRET-123"})
        res = self.post("/api/backups")
        for nom in os.listdir(res["chemin"]):
            with open(os.path.join(res["chemin"], nom), encoding="utf-8-sig") as fh:
                self.assertNotIn("SECRET-123", fh.read(), f"clé trouvée dans {nom}")

    def test_backup_stays_small(self):
        self.seed()
        res = self.post("/api/backups")
        self.assertLess(res["taille"], 20_000)   # quelques kilo-octets


class TestLegerete(BackupTestCase):
    def test_identical_content_is_not_written_twice(self):
        self.seed()
        premier = self.post("/api/backups")
        self.assertFalse(premier["inchange"])

        second = self.post("/api/backups")
        self.assertTrue(second["inchange"])
        self.assertEqual(second["id"], premier["id"])
        self.assertEqual(len(self.get("/api/backups")["sauvegardes"]), 1)

    def test_a_change_creates_a_new_backup(self):
        self.seed()
        self.post("/api/backups")
        self.post("/api/transactions", {
            "date": "2026-08-06", "description": "Essence", "amount": -60})
        res = self.post("/api/backups")
        self.assertFalse(res["inchange"])
        self.assertEqual(len(self.get("/api/backups")["sauvegardes"]), 2)

    def test_rotation_removes_the_oldest(self):
        self.client.put("/api/settings", json={"sauvegardes_max": 3})
        for i in range(5):
            self.post("/api/transactions", {
                "date": "2026-08-05", "description": f"Achat {i}", "amount": -10 - i})
            self.post("/api/backups")
        sauvegardes = self.get("/api/backups")["sauvegardes"]
        self.assertEqual(len(sauvegardes), 3)
        # Les plus récentes sont conservées.
        self.assertEqual(sauvegardes, sorted(sauvegardes, key=lambda s: s["date"],
                                             reverse=True))


class TestRestauration(BackupTestCase):
    def test_restore_brings_back_the_saved_state(self):
        self.seed()
        avant = self.get("/api/assets")["patrimoine_net"]
        sauvegarde = self.post("/api/backups")

        # On casse tout après coup.
        for a in self.get("/api/assets")["assets"]:
            self.client.delete(f"/api/assets/{a['id']}")
        self.post("/api/transactions", {
            "date": "2026-08-09", "description": "Erreur", "amount": -9999})
        self.assertEqual(self.get("/api/assets")["patrimoine_net"], 0)

        res = self.post(f"/api/backups/{sauvegarde['id']}/restore")
        self.assertGreater(res["lignes"], 0)
        self.assertEqual(self.get("/api/assets")["patrimoine_net"], avant)
        actifs = self.get("/api/assets")["assets"]
        self.assertEqual(actifs[0]["label"], "Livret A")
        self.assertEqual(actifs[0]["metadata"]["taux_annuel"], 3)
        # La transaction ajoutée après la sauvegarde a bien disparu.
        libelles = [t["description"] for t in self.get("/api/transactions")]
        self.assertNotIn("Erreur", libelles)

    def test_restore_takes_a_safety_backup_first(self):
        """Une restauration sans filet serait irréversible."""
        self.seed()
        sauvegarde = self.post("/api/backups")
        self.post("/api/transactions", {
            "date": "2026-08-08", "description": "A conserver", "amount": -12})

        res = self.post(f"/api/backups/{sauvegarde['id']}/restore")
        securite = res["sauvegarde_de_securite"]
        self.assertIsNotNone(securite)

        # On peut revenir sur ses pas.
        self.post(f"/api/backups/{securite}/restore")
        libelles = [t["description"] for t in self.get("/api/transactions")]
        self.assertIn("A conserver", libelles)

    def test_unknown_backup_is_refused(self):
        res = self.client.post("/api/backups/2020-01-01_00h00/restore")
        self.assertEqual(res.status_code, 404)

    def test_forged_identifier_cannot_escape_the_folder(self):
        """Un identifiant fabriqué ne doit pas atteindre un autre dossier."""
        for mechant in ("..", "../..", "..%2f.."):
            self.assertIsNone(backup._safe_dir(mechant))
        res = self.client.delete("/api/backups/..")
        self.assertEqual(res.status_code, 404)


class TestInventaire(BackupTestCase):
    def test_listing_reports_size_and_net_worth(self):
        self.seed()
        self.post("/api/backups")
        data = self.get("/api/backups")
        self.assertEqual(len(data["sauvegardes"]), 1)
        item = data["sauvegardes"][0]
        self.assertGreater(item["taille"], 0)
        # Le manifeste porte le patrimoine net tel qu'il valait a l'instant T,
        # interets de livret compris.
        self.assertAlmostEqual(item["patrimoine_net"],
                               self.get("/api/assets")["patrimoine_net"], places=2)
        self.assertTrue(data["dossier"].endswith("sauvegarde"))

    def test_delete_removes_the_folder(self):
        self.seed()
        res = self.post("/api/backups")
        self.assertTrue(os.path.isdir(res["chemin"]))
        self.client.delete(f"/api/backups/{res['id']}")
        self.assertFalse(os.path.exists(res["chemin"]))
        self.assertEqual(self.get("/api/backups")["sauvegardes"], [])


if __name__ == "__main__":
    unittest.main()
