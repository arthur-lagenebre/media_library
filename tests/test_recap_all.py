"""Régénération de toutes les fiches : quelles séries, avec quelle commande."""

import io
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.video import showindex
from scripts.TV_Shows import Recap_All as recap_all
from tests.test_index import fiche


class TestRecapAll(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bib = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        fiche(self.bib / "Dark")                                   # fiche avec l'id 70523
        (self.bib / "Lost" / "Saison 1").mkdir(parents=True)        # pas encore de fiche
        (self.bib / "Pinned [tmdbid-1396]" / "Saison 1").mkdir(parents=True)
        fiche(self.bib / "Pinned [tmdbid-1396]")
        (self.bib / "_Divers").mkdir()                              # ni saison ni fiche

    def lancer(self, *options, codes=None):
        """main() avec les sous-processus simulés. Retourne ([commande, ...], code, sortie)."""
        commandes, codes = [], dict(codes or {})

        def run(cmd):
            commandes.append(cmd)
            return types.SimpleNamespace(returncode=codes.get(Path(cmd[cmd.index("--dir") + 1]).name, 0))

        sortie = io.StringIO()
        with mock.patch.object(sys, "argv", ["Recap_All.py", "--dir", str(self.bib), *options]), mock.patch.object(recap_all.subprocess, "run", run), redirect_stdout(sortie):
            code = recap_all.main()
        return commandes, code, sortie.getvalue()

    def par_serie(self, commandes):
        return {Path(c[c.index("--dir") + 1]).name: c for c in commandes}

    def test_series_trouvees_episodes_intouches(self):
        commandes, code, _ = self.lancer("--apply")
        cmds = self.par_serie(commandes)
        self.assertEqual(sorted(cmds), ["Dark", "Lost", "Pinned [tmdbid-1396]"])
        for cmd in commandes:
            self.assertIn("--no-tag", cmd)
            self.assertIn("--recap", cmd)
            self.assertIn("--apply", cmd)
        self.assertEqual(code, 0)

    def test_id_de_la_fiche_repris(self):
        cmds = self.par_serie(self.lancer()[0])
        self.assertEqual(cmds["Dark"][cmds["Dark"].index("--tmdb-id") + 1], "70523")
        self.assertNotIn("--tmdb-id", cmds["Lost"])                  # rien à reprendre : recherche
        self.assertNotIn("--tmdb-id", cmds["Pinned [tmdbid-1396]"])  # l'épinglage passe devant

    def test_title_transmis_aux_fiches(self):
        # Chaque fiche en tire son lien de retour : « ← Anime » vers Anime.html.
        for cmd in self.lancer("--title", "Anime")[0]:
            self.assertEqual(cmd[cmd.index("--title") + 1], "Anime")
        for cmd in self.lancer()[0]:
            self.assertNotIn("--title", cmd)

    def test_simulation_par_defaut(self):
        for cmd in self.lancer()[0]:
            self.assertNotIn("--apply", cmd)

    def test_options_transmises_et_filtre(self):
        commandes, _, _ = self.lancer("--only", "dar", "--no-cache", "--still-size", "w400")
        self.assertEqual(len(commandes), 1)
        self.assertEqual(commandes[0][-3:], ["--no-cache", "--still-size", "w400"])

    def test_un_echec_n_arrete_pas_les_autres(self):
        commandes, code, sortie = self.lancer("--apply", codes={"Dark": 1})
        self.assertEqual(len(commandes), 3)
        self.assertEqual(code, 1)
        self.assertIn("EN ÉCHEC : Dark", sortie)

    def test_sommaire_reecrit_s_il_existe(self):
        _, _, sortie = self.lancer("--apply")
        self.assertEqual([p.name for p in (self.bib / "__Data__").iterdir()], ["Fiches"])      # aucun sommaire écrit ici : il n'y en avait pas
        (self.bib / "__Data__" / "Anime.html").write_text(showindex.build_html("Anime", []), encoding="utf-8")
        (self.bib / "__Data__" / "notes.html").write_text("<html>à moi</html>", encoding="utf-8")
        _, _, sortie = self.lancer("--apply")
        self.assertIn("Anime.html écrit (2 série(s))", sortie)
        self.assertEqual((self.bib / "__Data__" / "notes.html").read_text(encoding="utf-8"), "<html>à moi</html>")   # une page qui n'est pas la nôtre n'est pas touchée

    def test_title_ne_reecrit_que_le_sommaire_de_ce_titre(self):
        (self.bib / "__Data__" / "Anime.html").write_text(showindex.build_html("Anime", []), encoding="utf-8")
        (self.bib / "__Data__" / "Series.html").write_text(showindex.build_html("Series", []), encoding="utf-8")
        _, _, sortie = self.lancer("--apply", "--title", "Anime")
        self.assertIn("Anime.html écrit (2 série(s))", sortie)
        self.assertNotIn("Series.html", sortie)


if __name__ == "__main__":
    unittest.main()
