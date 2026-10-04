"""Les dépendances entre les dossiers de libraries/ : common/ ne connaît personne, video/, music/ et books/ ne se connaissent pas.

C'est ce qui tient le découpage : tant qu'un seul des deux domaines s'appuie sur l'autre, "common" n'est qu'un nom. Ce test échoue dès qu'un import remonte, avant qu'il ne devienne une habitude.
"""

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Qui n'a pas le droit d'importer qui.
FORBIDDEN = {
    "common": {"video", "music", "books"},
    "video": {"music", "books"},
    "music": {"video", "books"},
    "books": {"video", "music"},
}


def imported_domains(path):
    """Domaines de libraries/ qu'un fichier importe : {'common', 'video', ...}, imports relatifs hors-paquet compris."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            parts = node.module.split(".")
            if parts[0] == "libraries":
                if len(parts) > 1:
                    found.add(parts[1])
                else:                                   # from libraries import video
                    found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "libraries" and len(parts) > 1:
                    found.add(parts[1])
    return found


class TestDependances(unittest.TestCase):
    def test_aucun_import_interdit_dans_les_bibliotheques(self):
        for domain, forbidden in FORBIDDEN.items():
            for path in sorted((ROOT / "libraries" / domain).glob("*.py")):
                with self.subTest(path.relative_to(ROOT).as_posix()):
                    self.assertEqual(imported_domains(path) & forbidden, set())

    def test_les_scripts_de_musique_n_importent_pas_la_video(self):
        for path in sorted((ROOT / "scripts" / "Music").glob("*.py")):
            with self.subTest(path.relative_to(ROOT).as_posix()):
                self.assertNotIn("video", imported_domains(path))

    def test_les_scripts_de_livres_n_importent_ni_la_video_ni_la_musique(self):
        for path in sorted((ROOT / "scripts" / "Books").glob("*.py")):
            with self.subTest(path.relative_to(ROOT).as_posix()):
                self.assertEqual(imported_domains(path) & {"video", "music"}, set())

    def test_le_detecteur_voit_un_import_interdit(self):
        # Un test de garde qui ne détecterait rien ne garderait rien.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            fichier = Path(d) / "x.py"
            fichier.write_text("from libraries.video import naming\nfrom libraries import music\n", encoding="utf-8")
            self.assertEqual(imported_domains(fichier), {"video", "music"})


if __name__ == "__main__":
    unittest.main()
