"""Noms de fichiers communs : nettoyage d'un titre, listage par extension, chemin affichable."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common import filenames


class TestNomValide(unittest.TestCase):
    def test_caracteres_interdits_windows(self):
        brut = 'A<B>C:D"E/F' + chr(92) + 'G|H?I*J'
        self.assertEqual(filenames.safe_name(brut), "ABCDEFGHIJ")

    def test_point_final_supprime(self):
        self.assertEqual(filenames.safe_name("Fin de partie..."), "Fin de partie")

    def test_titre_vide(self):
        self.assertEqual(filenames.safe_name(None), "")


class TestFichiersParExtension(unittest.TestCase):
    def test_extensions_triees_sans_casse(self):
        with tempfile.TemporaryDirectory() as d:
            for nom in ("b.FLAC", "a.flac", "c.mp3", "notes.txt"):
                (Path(d) / nom).write_text("x", encoding="utf-8")
            (Path(d) / "dossier.flac").mkdir()                  # un dossier n'est pas un fichier
            self.assertEqual([f.name for f in filenames.files_with_ext(d, {".flac"})], ["a.flac", "b.FLAC"])

    def test_dossier_illisible_rend_une_liste_vide(self):
        self.assertEqual(filenames.files_with_ext(Path("introuvable"), {".flac"}), [])


class TestCheminAffichable(unittest.TestCase):
    def test_sans_le_prefixe_commun(self):
        racine = Path("musique")
        self.assertEqual(filenames.relative_name(racine / "CD1" / "01.flac", racine), str(Path("CD1") / "01.flac"))

    def test_hors_de_la_racine(self):
        self.assertEqual(filenames.relative_name(Path("ailleurs") / "x.flac", Path("musique")), str(Path("ailleurs") / "x.flac"))


if __name__ == "__main__":
    unittest.main()
