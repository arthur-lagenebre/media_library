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


# Les dossiers de scripts/ : un par domaine, et le domaine de libraries/ qui est le leur.
SCRIPT_DOMAINS = {"Music": "music", "Video": "video", "Books": "books"}


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

    def test_scripts_ne_contient_que_des_dossiers_de_domaine(self):
        # Un dossier par domaine, jamais par type d'action : pas de Converters/ ni de Maintenance/.
        dossiers = {p.name for p in (ROOT / "scripts").iterdir() if p.is_dir() and p.name != "__pycache__"}
        self.assertEqual(dossiers - SCRIPT_DOMAINS.keys(), set())

    def test_les_scripts_n_importent_que_common_et_leur_domaine(self):
        # Les scripts de scripts/<Domaine>/ (sous-dossiers compris : Video/Movies, Video/TV_Shows) n'ont le droit qu'à libraries/common/ et à leur propre domaine.
        for dossier, domaine in SCRIPT_DOMAINS.items():
            interdits = {"video", "music", "books"} - {domaine}
            for path in sorted((ROOT / "scripts" / dossier).rglob("*.py")):
                with self.subTest(path.relative_to(ROOT).as_posix()):
                    self.assertEqual(imported_domains(path) & interdits, set())

    def test_la_garde_des_scripts_voit_tous_les_scripts(self):
        # Une garde qui ne lirait pas les sous-dossiers ne garderait pas la vidéo.
        vus = {p.relative_to(ROOT / "scripts").as_posix() for p in (ROOT / "scripts").rglob("*.py")}
        attendus = {"Video/Movies/Metadata.py", "Video/Movies/Rename_Movies.py",
                    "Video/TV_Shows/Metadata.py", "Video/TV_Shows/Rename_Episodes.py",
                    "Video/Avi_To_Mkv.py", "Video/Mp4_To_Mkv.py", "Video/Verify_Mkv.py"}
        attendus |= {"Music/" + nom + ".py" for nom in ("Cover", "Discography", "Metadata", "Rename_Tracks", "Verify_Flac", "Verify_Mp3", "Wav_To_Flac")}
        attendus |= {"Books/" + nom + ".py" for nom in ("Clean_Epub", "Verify_Epub")}
        self.assertTrue(attendus <= vus, attendus - vus)

    def test_le_detecteur_voit_un_import_interdit(self):
        # Un test de garde qui ne détecterait rien ne garderait rien.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            fichier = Path(d) / "x.py"
            fichier.write_text("from libraries.video import naming\nfrom libraries import music\n", encoding="utf-8")
            self.assertEqual(imported_domains(fichier), {"video", "music"})


if __name__ == "__main__":
    unittest.main()
