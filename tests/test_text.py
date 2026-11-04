"""Texte : l'apostrophe et le guillemet droits, partout où un titre est écrit dans un tag."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common import text

COURBE = chr(0x2019)        # l'apostrophe typographique, celle que MusicBrainz et TMDB écrivent souvent
OUVRANT = chr(0x2018)       # le guillemet simple ouvrant, qui fait la paire avec COURBE fermant
MODIFICATEUR = chr(0x02BC)  # la lettre modificatrice, que certains claviers produisent à sa place
DOUBLE_OUVRANT, DOUBLE_FERMANT, DOUBLE_BAS, DOUBLE_HAUT = chr(0x201C), chr(0x201D), chr(0x201E), chr(0x201F)
DROIT = chr(0x22)


class TestApostropheDroite(unittest.TestCase):
    def test_apostrophe_typographique(self):
        self.assertEqual(text.straight_quotes(f"C{COURBE}est ça que les gens veulent"), "C'est ça que les gens veulent")
        self.assertEqual(text.straight_quotes(f"L{COURBE}homme qui voulait 3 milliards"), "L'homme qui voulait 3 milliards")

    def test_toutes_les_occurrences(self):
        self.assertEqual(text.straight_quotes(f"Rock{COURBE}n{COURBE}Roll"), "Rock'n'Roll")
        self.assertEqual(text.straight_quotes(f"Guns N{COURBE} Roses"), "Guns N' Roses")

    def test_lettre_modificatrice(self):
        self.assertEqual(text.straight_quotes(f"Don{MODIFICATEUR}t Stop"), "Don't Stop")

    def test_une_apostrophe_droite_reste_telle_quelle(self):
        self.assertEqual(text.straight_quotes("Don't Stop"), "Don't Stop")

    def test_guillemets_simples_courbes_laisses_intacts(self):
        # (ouvrant)mot(courbe) : fermer en apostrophe droite laisserait une paire dépareillée, mieux vaut ne rien toucher.
        citation = f"Le {OUVRANT}mot{COURBE} juste"
        self.assertEqual(text.straight_quotes(citation), citation)


class TestGuillemetDoubleDroit(unittest.TestCase):
    def test_guillemets_doubles_courbes(self):
        self.assertEqual(text.straight_quotes(f"Le {DOUBLE_OUVRANT}Parrain{DOUBLE_FERMANT}"), f"Le {DROIT}Parrain{DROIT}")

    def test_les_quatre_variantes(self):
        for courbe in (DOUBLE_OUVRANT, DOUBLE_FERMANT, DOUBLE_BAS, DOUBLE_HAUT):
            with self.subTest(hex(ord(courbe))):
                self.assertEqual(text.straight_quotes(f"a{courbe}b"), f"a{DROIT}b")

    def test_guillemet_droit_inchange(self):
        self.assertEqual(text.straight_quotes(f"Le {DROIT}Parrain{DROIT}"), f"Le {DROIT}Parrain{DROIT}")

    def test_les_deux_ensemble(self):
        self.assertEqual(text.straight_quotes(f"{DOUBLE_OUVRANT}C{COURBE}est ça{DOUBLE_FERMANT}"), f"{DROIT}C'est ça{DROIT}")

    def test_les_guillemets_francais_restent(self):
        # « » est la typographie française, pas une variante du guillemet droit.
        titre = "« Hasta la vista »"
        self.assertEqual(text.straight_quotes(titre), titre)

    def test_guillemets_doubles_redresses_meme_avec_un_guillemet_simple_ouvrant(self):
        self.assertEqual(text.straight_quotes(f"{OUVRANT}a{COURBE} {DOUBLE_OUVRANT}b{DOUBLE_FERMANT}"), f"{OUVRANT}a{COURBE} {DROIT}b{DROIT}")


class TestRienDAutre(unittest.TestCase):
    def test_rien_d_autre_ne_change(self):
        titre = "Cinquième as — « Hasta la vista » (intro) 2001 – Dégâts collatéraux..."
        self.assertEqual(text.straight_quotes(titre), titre)
        self.assertEqual(text.straight_quotes(""), "")


if __name__ == "__main__":
    unittest.main()
