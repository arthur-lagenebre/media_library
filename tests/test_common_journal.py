"""Le journal commun : ce que le script affiche, recopié dans le fichier donné par --log."""

import argparse
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common import journal


class FauxTerminal(io.StringIO):
    """Une console qui se dit terminal, pour vérifier que la question passe toujours par elle."""

    def isatty(self):
        return True


class TestOption(unittest.TestCase):
    def test_sans_log_rien(self):
        parser = argparse.ArgumentParser()
        journal.add_option(parser)
        self.assertIsNone(parser.parse_args([]).log)

    def test_log_prend_un_fichier(self):
        parser = argparse.ArgumentParser()
        journal.add_option(parser)
        self.assertEqual(parser.parse_args(["--log", "x.log"]).log, "x.log")


class TestRecord(unittest.TestCase):
    def setUp(self):
        self._dossier = tempfile.TemporaryDirectory()
        self.dossier = Path(self._dossier.name)
        self.fichier = self.dossier / "passage.log"

    def tearDown(self):
        self._dossier.cleanup()

    def lancer(self, destination, corps, console=None):
        console = console if console is not None else io.StringIO()
        with redirect_stdout(console):
            with journal.record(destination):
                corps()
        return console.getvalue()

    def test_ce_qui_est_affiche_est_recopie_dans_le_fichier(self):
        def corps():
            print("Album 1 : renommé")
            print("Album 2 : déjà bon")
        sortie = self.lancer(self.fichier, corps)
        self.assertEqual(self.fichier.read_text(encoding="utf-8"), "Album 1 : renommé\nAlbum 2 : déjà bon\n")
        self.assertIn("Album 1 : renommé\n", sortie)
        self.assertIn(f"[log] {self.fichier} écrit", sortie)

    def test_sans_destination_rien_n_est_ecrit_ni_ajoute_a_la_console(self):
        sortie = self.lancer(None, lambda: print("bonjour"))
        self.assertEqual(sortie, "bonjour\n")
        self.assertEqual(list(self.dossier.iterdir()), [])

    def test_la_progression_reste_hors_du_fichier(self):
        def corps():
            print("\r  1/2  a.flac", end="", flush=True)
            print("\r          \r", end="")
            print("a.flac : en défaut")
        self.lancer(self.fichier, corps)
        self.assertEqual(self.fichier.read_text(encoding="utf-8"), "a.flac : en défaut\n")

    def test_la_console_reste_un_terminal_pour_les_questions(self):
        vu = []
        self.lancer(self.fichier, lambda: vu.append(sys.stdout.isatty()), console=FauxTerminal())
        self.assertEqual(vu, [True])

    def test_sys_stdout_est_rendu_et_le_journal_ecrit_apres_une_exception(self):
        console = io.StringIO()

        def corps():
            print("avant")
            raise RuntimeError("boum")
        with redirect_stdout(console):
            with self.assertRaises(RuntimeError):
                with journal.record(self.fichier):
                    corps()
            self.assertIs(sys.stdout, console)
        self.assertEqual(self.fichier.read_text(encoding="utf-8"), "avant\n")

    def test_le_journal_est_ecrit_apres_sys_exit(self):
        console = io.StringIO()
        with redirect_stdout(console):
            with self.assertRaises(SystemExit) as fin:
                with journal.record(self.fichier):
                    print("bilan")
                    sys.exit(2)
            self.assertIs(sys.stdout, console)
        self.assertEqual(fin.exception.code, 2)
        self.assertEqual(self.fichier.read_text(encoding="utf-8"), "bilan\n")

    def test_le_message_d_arret_finit_au_journal(self):
        console = io.StringIO()
        with redirect_stdout(console):
            with self.assertRaises(SystemExit):
                with journal.record(self.fichier):
                    print("début")
                    sys.exit("Série non identifiée : relance avec --tmdb-id.")
        self.assertEqual(self.fichier.read_text(encoding="utf-8"), "début\nSérie non identifiée : relance avec --tmdb-id.\n")
        self.assertNotIn("Série non identifiée", console.getvalue().replace(str(self.fichier), ""))

    def test_un_dossier_absent_n_arrete_rien(self):
        destination = self.dossier / "absent" / "passage.log"
        sortie = self.lancer(destination, lambda: print("fait"))
        self.assertIn("fait\n", sortie)
        self.assertIn(f"[log] impossible d'écrire {destination}", sortie)
        self.assertFalse(destination.exists())

    def test_un_chemin_en_texte_est_accepte(self):
        self.lancer(str(self.fichier), lambda: print("fait"))
        self.assertEqual(self.fichier.read_text(encoding="utf-8"), "fait\n")


if __name__ == "__main__":
    unittest.main()
