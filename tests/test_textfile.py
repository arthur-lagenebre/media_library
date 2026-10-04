"""Écriture à l'identique : ce qu'on relit est ce qu'on a écrit."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common import textfile
class TestTextfile(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "recap.html"
        self.addCleanup(self._tmp.cleanup)

    def test_retour_chariot_isole_relu_tel_quel(self):
        # Régression : un synopsis TMDB portait un "\r" isolé, relu "\n" - la fiche ne se reconnaissait jamais et était réécrite chaque nuit.
        text = "<p title='Ligne un\rligne deux'>\n</p>"
        textfile.write(self.path, text)
        self.assertEqual(self.path.read_bytes(), text.encode("utf-8"))
        self.assertTrue(textfile.same(self.path, text))

    def test_contenu_different(self):
        textfile.write(self.path, "a")
        self.assertFalse(textfile.same(self.path, "b"))

    def test_horodatage_ignore(self):
        textfile.write(self.path, "# Metadata.py\n# 2026-10-01 03:00\nfilm\n")
        self.assertTrue(textfile.same(self.path, "# Metadata.py\n# 2026-10-02 03:00\nfilm\n", skip_lines=2))
        self.assertFalse(textfile.same(self.path, "# Metadata.py\n# 2026-10-02 03:00\nautre\n", skip_lines=2))

    def test_fichier_absent(self):
        self.assertFalse(textfile.same(self.path, "x"))


if __name__ == "__main__":
    unittest.main()
