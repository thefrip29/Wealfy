"""Invariants de la feuille de style que l'oeil seul ne rattrape pas.

Le depot n'a pas de harnais de test pour le front, et n'en veut pas : ce
serait une chaine d'outils entiere pour quelques centaines de lignes. Mais
certaines regles CSS sont des invariants verifiables sans navigateur, et leur
rupture ne se voit qu'a l'usage, dans un cas precis. C'est le cas de l'ordre
d'empilement : le calendrier maison etait sous la modale, et choisir une date
depuis la fiche d'un actif devenait impossible.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CSS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "app", "static", "css", "app.css")


def z_index(selecteur):
    """Valeur de `z-index` effective pour ce selecteur.

    La DERNIERE declaration et non la premiere : `#toast-host` apparait
    d'abord dans une regle groupee qui pose `z-index: 1` a plusieurs couches,
    puis seul avec sa vraie valeur. A specificite egale, c'est la derniere qui
    l'emporte — lire la premiere faisait passer le test pour vert a tort.
    """
    with open(CSS, encoding="utf-8") as f:
        feuille = f.read()
    valeur = None
    for bloc in re.finditer(r"([^{}]+)\{([^{}]*)\}", feuille):
        if selecteur not in bloc.group(1):
            continue
        trouve = re.search(r"z-index:\s*(\d+)", bloc.group(2))
        if trouve:
            valeur = int(trouve.group(1))
    return valeur


class TestOrdreDEmpilement(unittest.TestCase):
    def test_le_calendrier_passe_au_dessus_de_la_modale(self):
        """Sinon le selecteur de date est invisible depuis la fiche d'un actif.

        Le calendrier est attache au `<body>` pour echapper aux `overflow` des
        panneaux defilants : il est donc frere de la modale, et seul le
        `z-index` les departage.
        """
        self.assertGreater(z_index(".calendrier"), z_index(".modal-backdrop"))

    def test_les_toasts_restent_au_dessus_de_tout(self):
        """Ils annoncent les erreurs de saisie, y compris calendrier ouvert."""
        toast = z_index("#toast-host")
        self.assertGreater(toast, z_index(".calendrier"))
        self.assertGreater(toast, z_index(".modal-backdrop"))

    def test_les_valeurs_lues_existent_bien(self):
        """Garde-fou : un selecteur renomme rendrait les tests ci-dessus vides."""
        for selecteur in (".calendrier", ".modal-backdrop", "#toast-host"):
            self.assertIsNotNone(z_index(selecteur), selecteur)


if __name__ == "__main__":
    unittest.main()
