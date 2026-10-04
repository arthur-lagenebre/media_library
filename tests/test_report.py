"""Le bilan d'un passage : addition, code de sortie, ligne finale."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common.report import Report


class TestReport(unittest.TestCase):
    def test_addition(self):
        total = Report(1, 1) + Report(2, 3, diffs=1) + Report(failures=2)
        self.assertEqual((total.matched, total.total, total.diffs, total.failures), (3, 4, 1, 2))

    def test_code_de_sortie_nul_quand_tout_va_bien(self):
        self.assertEqual(Report(matched=5, total=5).exit_code, 0)

    def test_code_de_sortie_non_nul(self):
        # --verify doit pouvoir servir dans un script.
        self.assertEqual(Report(diffs=1).exit_code, 1)
        self.assertEqual(Report(failures=1).exit_code, 1)

    def test_epilogue(self):
        self.assertEqual(Report().epilogue(), "")
        self.assertEqual(Report(diffs=2).epilogue(), "2 fichier(s) non conforme(s)")
        self.assertEqual(Report(diffs=1, failures=3).epilogue(), "1 fichier(s) non conforme(s) ; 3 ecriture(s) en echec")


if __name__ == "__main__":
    unittest.main()
