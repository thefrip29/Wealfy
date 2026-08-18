"""Emplacement des donnees persistantes, plateforme par plateforme.

Ces tests existent parce que l'erreur y est SILENCIEUSE : une base ecrite au
mauvais endroit ne provoque aucune exception, elle donne une application qui
s'ouvre vide alors que les donnees sont ailleurs — ou, pire sur macOS, une base
posee dans un bundle applicatif, effacee a la mise a jour suivante.

Rien ici ne lance l'application : on interroge la resolution de chemin en
simulant tour a tour chaque systeme.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import paths  # noqa: E402


class TestDossierDonnees(unittest.TestCase):
    def test_windows_garde_le_nom_historique(self):
        """Renommer ce dossier rendrait invisible une base deja installee."""
        with mock.patch.object(sys, "platform", "win32"), \
             mock.patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\X\AppData\Local"}):
            self.assertEqual(paths.appdata_dir(),
                             os.path.join(r"C:\Users\X\AppData\Local", "Patrimoine"))

    def test_macos_suit_la_convention_apple(self):
        with mock.patch.object(sys, "platform", "darwin"), \
             mock.patch.object(os.path, "expanduser", return_value="/Users/x"):
            self.assertEqual(
                paths.appdata_dir(),
                os.path.join("/Users/x", "Library", "Application Support", "Wealfy"))

    def test_linux_suit_xdg(self):
        with mock.patch.object(sys, "platform", "linux"), \
             mock.patch.dict(os.environ, {"XDG_DATA_HOME": "/home/x/.local/share"}):
            self.assertEqual(paths.appdata_dir(),
                             os.path.join("/home/x/.local/share", "wealfy"))

    def test_linux_sans_xdg_retombe_sur_le_defaut(self):
        with mock.patch.object(sys, "platform", "linux"), \
             mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(os.path, "expanduser", return_value="/home/x"):
            self.assertEqual(paths.appdata_dir(),
                             os.path.join("/home/x", ".local", "share", "wealfy"))

    def test_hors_windows_jamais_de_mode_portable(self):
        """Le point qui compte : ne JAMAIS ecrire dans Wealfy.app.

        En mode gele, « a cote de l'executable » designe l'interieur du bundle
        sur macOS. Meme si ce dossier est inscriptible — ce qui est le cas d'un
        bundle non signe construit localement — la base ne doit pas y aller.
        """
        faux_bundle = "/Applications/Wealfy.app/Contents/MacOS"
        with mock.patch.object(sys, "platform", "darwin"), \
             mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "_MEIPASS", "/tmp/_MEI123", create=True), \
             mock.patch.object(sys, "executable", faux_bundle + "/Wealfy"), \
             mock.patch.object(paths, "_is_writable", return_value=True), \
             mock.patch.object(os, "makedirs"), \
             mock.patch.object(os.path, "expanduser", return_value="/Users/x"):
            obtenu = paths.data_dir()
        self.assertNotIn(".app", obtenu)
        self.assertEqual(
            obtenu,
            os.path.join("/Users/x", "Library", "Application Support", "Wealfy"))

    def test_windows_conserve_le_mode_portable(self):
        """Non-regression : le comportement Windows ne doit pas avoir bouge.

        Le chemin est construit avec `os.path.join` et non ecrit en dur a la
        windows : `os.path` suit les regles de la machine QUI EXECUTE le test.
        Un « D:\\Cle USB\\Wealfy.exe » n'a aucun separateur aux yeux d'un macOS,
        dont le `dirname` renvoie alors une chaine vide — et `abspath('')` vaut
        le dossier courant. Le test echouait donc sur les runners sans que le
        code ait le moindre defaut.
        """
        exe = os.path.join(os.path.abspath(os.sep), "faux", "Cle USB", "Wealfy.exe")
        pres_exe = os.path.dirname(exe)
        with mock.patch.object(sys, "platform", "win32"), \
             mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "_MEIPASS", os.path.join(os.sep, "tmp", "_MEI"), create=True), \
             mock.patch.object(sys, "executable", exe), \
             mock.patch.object(os.path, "exists", return_value=False), \
             mock.patch.object(paths, "_is_writable", return_value=True), \
             mock.patch.object(os, "makedirs"):
            self.assertEqual(paths.data_dir(), pres_exe)


if __name__ == "__main__":
    unittest.main()
