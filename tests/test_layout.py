"""Les morceaux de page communs : la lettre sous laquelle un titre se range."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common import layout


class TestInitiale(unittest.TestCase):
    def test_lettre_sans_accent_ni_casse(self):
        self.assertEqual([layout.initial(t) for t in ("Alien", "énorme", "ÀBC", "œuf")], ["A", "E", "A", "O"])

    def test_chiffre_ou_signe_sous_diese(self):
        self.assertEqual([layout.initial(t) for t in ("12 hommes", "28 jours", "[REC]", "", None, "…", "Δ")], ["#", "#", "R", "#", "#", "#", "#"])

    def test_pas_d_article_retire(self):
        # La page classe "Le robot" à L : l'index suit le classement, pas l'usage.
        self.assertEqual(layout.initial("Le robot sauvage"), "L")

    def test_une_entree_par_lettre_et_diese(self):
        self.assertEqual(layout.index_nav().count("data-l="), 27)


if __name__ == "__main__":
    unittest.main()
