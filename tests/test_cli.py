"""Lecture du .env et résolution de la clé TMDB."""

import io
import os
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common import cli
class TestDotenv(unittest.TestCase):
    def charger(self, contenu):
        """Écrit un .env dans un dossier temporaire et le lit depuis ce dossier."""
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".env").write_text(contenu, encoding="utf-8")
            with mock.patch.object(cli.Path, "cwd", staticmethod(lambda: Path(d))), mock.patch.object(cli, "__file__", str(Path(d) / "cli.py")):
                return cli.read_dotenv()

    def test_paire_simple(self):
        self.assertEqual(self.charger("TMDB_KEY=abc123"), {"TMDB_KEY": "abc123"})

    def test_commentaires_et_lignes_vides_ignores(self):
        env = self.charger("# commentaire\n\nTMDB_KEY=abc\nligne sans egal\n")
        self.assertEqual(env, {"TMDB_KEY": "abc"})

    def test_guillemets_retires_et_prefixe_export(self):
        env = self.charger("export TMDB_KEY=\"abc\"\nAUTRE='def'\n")
        self.assertEqual((env["TMDB_KEY"], env["AUTRE"]), ("abc", "def"))

    def test_premiere_ligne_gagne(self):
        self.assertEqual(self.charger("TMDB_KEY=un\nTMDB_KEY=deux")["TMDB_KEY"], "un")

    def test_bom_utf8_tolere(self):
        self.assertEqual(self.charger("﻿TMDB_KEY=abc")["TMDB_KEY"], "abc")

    def test_fichier_absent(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(cli.Path, "cwd", staticmethod(lambda: Path(d))), mock.patch.object(cli, "__file__", str(Path(d) / "cli.py")):
                self.assertEqual(cli.read_dotenv("nexiste_pas.env"), {})

    def test_environnement_ni_lu_ni_ecrit(self):
        # Le .env est la seule source : une variable d'environnement ne le remplace plus, et la lecture ne laisse rien derrière elle.
        with mock.patch.dict(os.environ, {"TMDB_KEY": "de_l_environnement"}, clear=True):
            self.assertEqual(self.charger("TMDB_KEY=du_fichier")["TMDB_KEY"], "du_fichier")
            self.assertEqual(os.environ["TMDB_KEY"], "de_l_environnement")


class TestCleTmdb(unittest.TestCase):
    def resoudre(self, valeurs):
        with mock.patch.object(cli, "read_dotenv", lambda *a, **k: valeurs):
            return cli.resolve_tmdb_key()

    def test_cle_du_fichier(self):
        self.assertEqual(self.resoudre({"TMDB_KEY": "abc123"}), "abc123")

    def test_espaces_ignores(self):
        self.assertEqual(self.resoudre({"TMDB_KEY": "  abc123  "}), "abc123")

    def test_fichier_sans_cle(self):
        with self.assertRaises(SystemExit) as ctx:
            self.resoudre({"AUTRE": "x"})
        self.assertIn("TMDB_KEY", str(ctx.exception))

    def test_cle_vide(self):
        with self.assertRaises(SystemExit):
            self.resoudre({"TMDB_KEY": ""})

    def test_aucun_fichier(self):
        with self.assertRaises(SystemExit) as ctx:
            self.resoudre({})
        self.assertIn(".env", str(ctx.exception))


class TestBanniere(unittest.TestCase):
    def test_libelles(self):
        self.assertEqual(cli.mode_label(types.SimpleNamespace(apply=True, verify=False)), "APPLICATION")
        self.assertEqual(cli.mode_label(types.SimpleNamespace(apply=True, verify=True)), "VÉRIFICATION (aucune écriture)")
        self.assertIn("SIMULATION", cli.mode_label(types.SimpleNamespace(apply=False, verify=False)))

class TestDossier(unittest.TestCase):
    def test_dossier_valide_rendu(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(cli.check_dir(d), Path(d))

    def test_dossier_introuvable(self):
        with self.assertRaises(SystemExit) as ctx:
            cli.check_dir("dossier_qui_n_existe_pas")
        self.assertIn("introuvable", str(ctx.exception))

    def test_fichier_au_lieu_d_un_dossier(self):
        with tempfile.TemporaryDirectory() as d:
            fichier = Path(d) / "film.mkv"
            fichier.write_text("x", encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                cli.check_dir(fichier)
        self.assertIn("pas un fichier", str(ctx.exception))


class TestQuestions(unittest.TestCase):
    """Les questions de fin de passage : une réponse incomprise repose la question, jamais ne décide."""

    def demander(self, reponses, nombre=3, defaut=0):
        with mock.patch("builtins.input", side_effect=reponses) as saisie, redirect_stdout(io.StringIO()) as sortie:
            choix = cli.ask_choice(nombre, defaut)
        return choix, saisie.call_count, sortie.getvalue()

    def test_entree_garde_le_defaut(self):
        self.assertEqual(self.demander([""])[0], 0)
        self.assertEqual(self.demander(["  "], defaut=2)[0], 2)

    def test_un_numero_choisit_sa_proposition(self):
        self.assertEqual(self.demander(["2"])[0], 1)
        self.assertEqual(self.demander(["3"])[0], 2)

    def test_i_laisse_de_cote(self):
        self.assertEqual(self.demander(["i"])[0], cli.ASK_SKIP)
        self.assertEqual(self.demander(["IGNORER"])[0], cli.ASK_SKIP)

    def test_q_arrete_les_questions(self):
        for reponse in ("q", "Quitter", "arreter"):
            self.assertEqual(self.demander([reponse])[0], cli.ASK_STOP)

    def test_une_reponse_incomprise_repose_la_question(self):
        choix, appels, sortie = self.demander(["peut-etre", "0", "4", "-1", "2"])
        self.assertEqual((choix, appels), (1, 5))
        self.assertIn("un numéro de 1 à 3", sortie)

    def test_entree_fermee_arrete_les_questions(self):
        self.assertEqual(self.demander([EOFError()])[0], cli.ASK_STOP)

    def test_ctrl_c_arrete_les_questions(self):
        self.assertEqual(self.demander([KeyboardInterrupt()])[0], cli.ASK_STOP)


class TestPeutOnDemander(unittest.TestCase):
    def avec(self, stdin, stdout):
        with mock.patch.object(cli.sys, "stdin", stdin), mock.patch.object(cli.sys, "stdout", stdout):
            return cli.can_ask()

    @staticmethod
    def flux(tty):
        return types.SimpleNamespace(isatty=lambda: tty)

    def test_terminal_complet(self):
        self.assertTrue(self.avec(self.flux(True), self.flux(True)))

    def test_entree_redirigee(self):
        self.assertFalse(self.avec(self.flux(False), self.flux(True)))

    def test_sortie_redirigee(self):
        self.assertFalse(self.avec(self.flux(True), self.flux(False)))

    def test_pas_d_entree_du_tout(self):
        self.assertFalse(self.avec(None, self.flux(True)))

    def test_flux_ferme(self):
        def ferme():
            raise ValueError("I/O operation on closed file")
        self.assertFalse(self.avec(types.SimpleNamespace(isatty=ferme), self.flux(True)))


if __name__ == "__main__":
    unittest.main()
