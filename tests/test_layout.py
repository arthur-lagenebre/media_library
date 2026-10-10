"""Les morceaux de page communs : la lettre sous laquelle un titre se range."""

import os
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


class TestFold(unittest.TestCase):
    def test_sans_accents_ni_casse_ni_ligature(self):
        self.assertEqual([layout.fold(t) for t in ("Éden", "ÀBC", "Œuf", None)], ["eden", "abc", "ouf", ""])


class TestChemins(unittest.TestCase):
    def test_relatif_a_la_racine_avec_des_slashs(self):
        racine = Path("D:/Films") if os.name == "nt" else Path("/films")
        self.assertEqual(layout.relative_path(racine / "Saga" / "Heat" / "Heat.mkv", racine), "Saga/Heat/Heat.mkv")

    def test_hors_de_la_racine_chemin_entier(self):
        self.assertEqual(layout.relative_path(Path("Ailleurs/Heat.mkv"), Path("Films")), "Ailleurs/Heat.mkv")

    def test_bloc_vide_sans_chemin(self):
        self.assertEqual((layout.paths_block([]), layout.paths_block(None)), ("", ""))


class TestRetourEnHaut(unittest.TestCase):
    def test_le_bouton_accompagne_celui_de_largeur(self):
        # Les deux boutons viennent ensemble, sur un sommaire comme sur une fiche ; le script de largeur ne doit pas confondre l'un avec l'autre.
        for labels in (layout.INDEX_LABELS, layout.SHEET_LABELS):
            html = layout.mode_button(labels)
            self.assertIn("<button class='totop'", html)
            self.assertIn("scrollTo({top:0", html)
            self.assertEqual(html.count("class='mode'"), 1)


class TestGenres(unittest.TestCase):
    def test_menu_du_plus_frequent_au_moins_frequent(self):
        html = layout.genre_select({"Drame": 2, "Action": 5, "Comédie": 2})
        self.assertLess(html.index("Action (5)"), html.index("Comédie (2)"))
        self.assertLess(html.index("Comédie (2)"), html.index("Drame (2)"))      # à égalité, par nom
        self.assertIn("<option value=''>Tous les genres</option>", html)

    def test_sans_genre_pas_de_menu(self):
        self.assertEqual(layout.genre_select({}), "")
        self.assertEqual(layout.genre_attr([]), "")
        self.assertEqual(layout.genre_attr(["", ""]), "")

    def test_attribut_echappe(self):
        self.assertEqual(layout.genre_attr(["Sci-Fi", "L'aventure"]), " data-g='Sci-Fi|L&#39;aventure'")
        self.assertIn("value='L&#39;aventure'", layout.genre_select({"L'aventure": 1}))


if __name__ == "__main__":
    unittest.main()
