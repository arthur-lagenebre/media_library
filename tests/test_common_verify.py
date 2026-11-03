"""Ce que les scripts de contrôle partagent : les fichiers pris, la boucle, le bilan et le journal."""

import io
import sys
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common import verify
from libraries.common.report import Report
from tests.test_conversion_programmes import ProgrammeTestCase


class TestFichiers(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        album = self.racine / "Album"
        album.mkdir()
        (self.racine / "Single.FLAC").write_bytes(b"")
        (album / "02 - B.mp3").write_bytes(b"")
        (album / "01 - A.flac").write_bytes(b"")
        (album / "cover.jpg").write_bytes(b"")
        (album / "._01 - A.flac").write_bytes(b"")                 # résidu d'une copie depuis macOS : pas une piste
        (album / "01 - A.flac.part").write_bytes(b"")              # conversion en cours : pas encore une piste

    def noms(self, extensions, **options):
        return [p.name for p in verify.files(self.racine, extensions, **options)]

    def test_les_extensions_demandees_a_la_racine_d_abord_puis_dossier_par_dossier(self):
        self.assertEqual(self.noms((".flac", ".mp3")), ["Single.FLAC", "01 - A.flac", "02 - B.mp3"])

    def test_une_seule_extension(self):
        self.assertEqual(self.noms((".mp3",)), ["02 - B.mp3"])

    def test_sans_recursion_l_etage_seul(self):
        self.assertEqual(self.noms((".flac", ".mp3"), recursif=False), ["Single.FLAC"])

    def test_aucun_fichier_arrete_le_programme_avec_ce_qu_on_cherchait(self):
        args = types.SimpleNamespace(dir=str(self.racine), no_recursive=False)
        with self.assertRaises(SystemExit) as sortie:
            verify.locate(args, (".ogg",))
        self.assertIn(f"Aucun .ogg sous {self.racine}", sortie.exception.code)

    def test_locate_rend_la_racine_et_les_fichiers(self):
        for sans_recursion, attendus in ((False, ["Single.FLAC", "01 - A.flac"]), (True, ["Single.FLAC"])):
            with self.subTest(sans_recursion=sans_recursion):
                racine, fichiers = verify.locate(types.SimpleNamespace(dir=str(self.racine), no_recursive=sans_recursion), (".flac",))
                self.assertEqual(racine, self.racine)
                self.assertEqual([p.name for p in fichiers], attendus)


class TestBoucleEtBilan(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        self.fichiers = []
        for nom in ("a.flac", "b.flac", "c.flac"):
            (self.racine / nom).write_bytes(b"x")
            self.fichiers.append(self.racine / nom)

    def test_seuls_les_fichiers_en_defaut_sont_rendus_et_signales(self):
        vus = []

        def check(chemin, complet):
            vus.append((chemin.name, complet))
            return "coupé" if chemin.name == "b.flac" else ""

        with redirect_stdout(io.StringIO()) as sortie:
            defauts = verify.check_all(self.fichiers, self.racine, check, True)
        self.assertEqual(defauts, [(self.racine / "b.flac", "coupé")])
        self.assertEqual(vus, [("a.flac", True), ("b.flac", True), ("c.flac", True)])
        self.assertIn("[DÉFAUT] b.flac", sortie.getvalue())
        self.assertIn("coupé", sortie.getvalue())

    def test_bilan_d_un_passage_propre_dit_ce_que_le_rapide_ne_voit_pas(self):
        with redirect_stdout(io.StringIO()) as sortie:
            verify.summarize(Report(total=3), 2, types.SimpleNamespace(full=False), "piste", "REMÈDE", "NOTE")
        self.assertIn("TOTAL : 3 piste(s) contrôlée(s) en 2 s, 0 en défaut.", sortie.getvalue())
        self.assertIn("NOTE", sortie.getvalue())
        self.assertNotIn("REMÈDE", sortie.getvalue())

    def test_bilan_avec_defaut_donne_le_remede_et_pas_la_note(self):
        with redirect_stdout(io.StringIO()) as sortie:
            verify.summarize(Report(total=3, diffs=1), 2, types.SimpleNamespace(full=False), "piste", "REMÈDE", "NOTE")
        self.assertIn("REMÈDE", sortie.getvalue())
        self.assertNotIn("NOTE", sortie.getvalue())

    def test_bilan_complet_propre_n_a_pas_de_note(self):
        with redirect_stdout(io.StringIO()) as sortie:
            verify.summarize(Report(total=3), 2, types.SimpleNamespace(full=True), "piste", "REMÈDE", "NOTE")
        self.assertNotIn("NOTE", sortie.getvalue())

    def test_journal(self):
        destination = self.racine / "x.log"
        with redirect_stdout(io.StringIO()):
            verify.write_log(destination, self.racine, 3, [(self.racine / "b.flac", "coupé")], "piste", "rapide (R)", "complet (C)", False, False)
        texte = destination.read_text(encoding="utf-8")
        self.assertIn("Contrôle rapide (R), sans les sous-dossiers", texte)
        self.assertIn("3 piste(s) contrôlée(s), 1 en défaut.", texte)
        self.assertIn("b.flac\n    coupé", texte)

    def test_journal_illisible_ne_plante_pas(self):
        with redirect_stdout(io.StringIO()) as sortie:
            verify.write_log(self.racine / "absent" / "x.log", self.racine, 0, [], "piste", "R", "C", True, True)
        self.assertIn("impossible d'écrire", sortie.getvalue())


if __name__ == "__main__":
    unittest.main()
