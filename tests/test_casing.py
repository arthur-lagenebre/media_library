"""La casse d'un titre : quand le titre TMDB et le nom du fichier ne diffèrent que par elle, et ce qu'on en propose."""

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common import cli
from libraries.video import casing

NBSP, COURBE = chr(0xA0), chr(0x2019)


class TestRecased(unittest.TestCase):
    def test_titre_francais_ecrit_a_l_anglaise_par_tmdb(self):
        self.assertEqual(casing.recased("28 Ans plus tard", "28 ans plus tard"), "28 ans plus tard")
        self.assertEqual(casing.recased("28 Jours plus tard", "28 jours plus tard"), "28 jours plus tard")
        self.assertEqual(casing.recased("28 Semaines plus tard", "28 semaines plus tard"), "28 semaines plus tard")

    def test_la_ponctuation_de_tmdb_est_gardee(self):
        # Le fichier ne peut pas écrire ":" : il met " - ". C'est TMDB qui garde la ponctuation, le fichier qui donne la casse.
        self.assertEqual(casing.recased("28 Ans plus tard : Le Temple des morts", "28 ans plus tard - Le temple des morts"), "28 ans plus tard : Le temple des morts")

    def test_un_morceau_du_titre_suffit(self):
        titre = f"300{NBSP}: La Naissance d{COURBE}un Empire"
        self.assertEqual(casing.recased(titre, "La naissance d'un empire"), f"300{NBSP}: La naissance d{COURBE}un empire")

    def test_le_premier_mot_du_morceau_garde_la_majuscule_de_tmdb(self):
        self.assertEqual(casing.recased("Le Retour du Roi", "le retour du roi"), "Le retour du roi")

    def test_titre_anglais_dont_le_fichier_est_en_minuscules(self):
        self.assertEqual(casing.recased("American History X", "American history X"), "American history X")

    def test_rien_a_demander(self):
        for titre, nom in (("Alien vs. Predator", "Alien vs Predator"), ("American Beauty", "American Beauty"), ("Dune", "dune"), ("Heat", "Heat")):
            with self.subTest(titre):
                self.assertIsNone(casing.recased(titre, nom))

    def test_la_difference_sur_le_seul_premier_mot_n_est_pas_un_probleme(self):
        self.assertIsNone(casing.recased("La Haine", "la Haine"))

    def test_un_autre_film_ne_correspond_pas(self):
        self.assertIsNone(casing.recased("Blade Runner", "28 ans plus tard"))
        self.assertIsNone(casing.recased("28 Ans plus tard", "28 ans plus tard : Le temple des morts"))     # le fichier en dit plus que le titre

    def test_les_accents_comptent(self):
        self.assertIsNone(casing.recased("Les Évadés", "Les evades"))

    def test_nom_d_un_seul_mot_ou_vide(self):
        self.assertIsNone(casing.recased("Dune Part Two", "dune"))
        self.assertIsNone(casing.recased("Dune", ""))
        self.assertIsNone(casing.recased("", "dune part two"))


class TestLooksFrench(unittest.TestCase):
    def test_mots_que_seul_le_francais_emploie(self):
        for titre in ("28 Ans plus tard", "Le Parrain", "300 : La Naissance d'un Empire", "Alien, la résurrection"):
            self.assertTrue(casing.looks_french(titre), titre)

    def test_titres_anglais(self):
        for titre in ("American History X", "Alien vs. Predator", "The Dark Knight", "2 Fast 2 Furious"):
            self.assertFalse(casing.looks_french(titre), titre)


class TestAsk(unittest.TestCase):
    def poser(self, titre, candidat, reponse):
        with mock.patch.object(cli, "ask_choice", return_value=reponse) as question, redirect_stdout(io.StringIO()) as sortie:
            return casing.ask(titre, candidat), question.call_args[0], sortie.getvalue()

    def test_le_choix_rend_le_titre(self):
        self.assertEqual(self.poser("28 Ans plus tard", "28 ans plus tard", 0)[0], "28 ans plus tard")
        self.assertEqual(self.poser("28 Ans plus tard", "28 ans plus tard", 1)[0], "28 Ans plus tard")

    def test_defaut_selon_la_langue_du_titre(self):
        self.assertEqual(self.poser("28 Ans plus tard", "28 ans plus tard", 0)[1], (2, 0, True))
        self.assertEqual(self.poser("American History X", "American history X", 1)[1], (2, 1, True))

    def test_les_deux_versions_sont_montrees(self):
        _, _, sortie = self.poser("28 Ans plus tard", "28 ans plus tard", 0)
        self.assertIn("1) 28 ans plus tard   (casse de ton fichier)   (défaut)", sortie)
        self.assertIn("2) 28 Ans plus tard   (casse de TMDB)", sortie)

    def test_t_est_rendu_tel_quel_et_l_aide_le_dit(self):
        reponse, _, sortie = self.poser("a b", "a B", cli.ASK_ALL)
        self.assertEqual(reponse, cli.ASK_ALL)
        self.assertIn("t = défaut pour toutes les suivantes", sortie)

    def test_defaut_propose(self):
        self.assertEqual(casing.default_choice("28 Ans plus tard", "28 ans plus tard"), "28 ans plus tard")
        self.assertEqual(casing.default_choice("American History X", "American history X"), "American History X")

    def test_ignorer_et_arreter_sont_rendus_tels_quels(self):
        self.assertEqual(self.poser("a b", "a B", cli.ASK_SKIP)[0], cli.ASK_SKIP)
        self.assertEqual(self.poser("a b", "a B", cli.ASK_STOP)[0], cli.ASK_STOP)


if __name__ == "__main__":
    unittest.main()
