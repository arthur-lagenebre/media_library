"""Icônes d'onglet : monogramme des fiches, téléviseur du sommaire."""

import re
import sys
import unittest
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.video import favicon, showindex
from scripts.Movies import Metadata as films
from scripts.TV_Shows import Metadata as series

HREF_RE = re.compile(r"<link rel='icon' type='image/svg\+xml' href='data:image/svg\+xml,([^']+)'>")


def svg_of(html):
    """Le SVG porté par l'icône d'une page, décodé et analysé : un SVG mal formé ne s'affiche pas."""
    return ElementTree.fromstring(unquote(HREF_RE.search(html).group(1)))


class TestInitiales(unittest.TestCase):
    def test_initiales(self):
        cas = {"Breaking Bad": "BB", "Dark": "D", "Game of Thrones": "GT", "The Expanse": "E",
               "La Casa de Papel": "CP", "Star Wars : Andor": "SW", "24": "24", "9-1-1": "9",
               "élite": "É", "Les Uns": "U", "Les": "L", "": "?"}
        for titre, attendu in cas.items():
            with self.subTest(titre=titre):
                self.assertEqual(favicon.initials(titre), attendu)


class TestCouleur(unittest.TestCase):
    def test_stable_et_propre_au_titre(self):
        self.assertEqual(favicon.color("Dark"), favicon.color("Dark"))
        self.assertEqual(favicon.color("Dark"), favicon.color("DARK"))
        self.assertNotEqual(favicon.color("Dark"), favicon.color("Lost"))
        self.assertRegex(favicon.color("Dark"), r"^#[0-9a-f]{6}$")


class TestPages(unittest.TestCase):
    def test_la_fiche_porte_son_monogramme(self):
        html = series.build_recap_html("Tom & Jerry <3>", {}, [], "1", {}, "w300")
        svg = svg_of(html)
        self.assertEqual(svg.find("{http://www.w3.org/2000/svg}text").text, "TJ")
        # Dans l'en-tête, avant le <style> : là où le sommaire s'arrête de lire.
        self.assertLess(html.index("rel='icon'"), html.index("<style>"))

    def test_la_fiche_des_films_porte_le_clap(self):
        html = films.build_recap_html("Films", [], {}, "w185")
        svg_of(html)
        self.assertLess(html.index("rel='icon'"), html.index("<style>"))

    def test_le_sommaire_porte_le_televiseur(self):
        svg_of(showindex.build_html("Series", []))
        self.assertIn("rel='icon'", showindex.build_html("Series", []))


if __name__ == "__main__":
    unittest.main()
