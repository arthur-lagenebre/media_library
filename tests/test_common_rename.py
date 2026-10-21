"""libraries/common/rename.py : les renommages qui se gênent entre eux, sans rien perdre en route."""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common import rename


class DossierTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def creer(self, **fichiers):
        for nom, contenu in fichiers.items():
            (self.dir / nom).write_text(contenu, encoding="utf-8")

    def contenu(self):
        """{nom: contenu} de tout le dossier : ce qui compte, c'est qu'aucun contenu ne se perde ni ne se mélange."""
        return {p.name: p.read_text(encoding="utf-8") for p in sorted(self.dir.iterdir())}

    def appliquer(self, planned):
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            done = rename.apply_renames(planned)
        self.sortie = sortie.getvalue()
        return done


class TestNomTemporaire(DossierTestCase):
    def test_garde_l_extension_et_evite_les_noms_pris(self):
        self.creer(**{"a.tmp1.mkv": "x"})
        self.assertEqual(rename.free_name(self.dir / "a.mkv").name, "a.tmp2.mkv")

    def test_aucun_nom_libre(self):
        with mock.patch.object(Path, "exists", return_value=True):
            with self.assertRaises(OSError):
                rename.free_name(self.dir / "a.mkv")


class TestMemeFichier(DossierTestCase):
    def test_fichier_absent(self):
        self.creer(a="x")
        self.assertFalse(rename.same_file(self.dir / "a", self.dir / "absent"))

    def test_deux_fichiers_distincts(self):
        self.creer(a="x", b="y")
        self.assertFalse(rename.same_file(self.dir / "a", self.dir / "b"))

    def test_le_meme_chemin(self):
        self.creer(a="x")
        self.assertTrue(rename.same_file(self.dir / "a", self.dir / "a"))

    def test_une_erreur_du_systeme_n_est_pas_un_plantage(self):
        self.creer(a="x", b="y")
        with mock.patch.object(Path, "samefile", side_effect=OSError("partage coupé")):
            self.assertFalse(rename.same_file(self.dir / "a", self.dir / "b"))


class TestRenommageSimple(DossierTestCase):
    def test_renomme_et_rend_les_sources_traitees(self):
        self.creer(a="A")
        done = self.appliquer([(self.dir / "a", self.dir / "b")])
        self.assertEqual(self.contenu(), {"b": "A"})
        self.assertEqual(done, {self.dir / "a"})

    def test_casse_seule(self):
        # Windows refuse un renommage direct qui ne change que la casse : il passe par un nom intermédiaire.
        self.creer(**{"titre.mkv": "A"})
        done = self.appliquer([(self.dir / "titre.mkv", self.dir / "Titre.mkv")])
        self.assertEqual(self.contenu(), {"Titre.mkv": "A"})
        self.assertEqual(len(done), 1)

    def test_rien_a_faire(self):
        self.assertEqual(self.appliquer([]), set())


class TestRenommagesQuiSeGenent(DossierTestCase):
    def test_numerotation_decalee_d_un_cran(self):
        # 01 -> 02 et 02 -> 03 : le premier doit attendre que le second ait libéré son nom.
        self.creer(**{"01": "A", "02": "B"})
        done = self.appliquer([(self.dir / "01", self.dir / "02"), (self.dir / "02", self.dir / "03")])
        self.assertEqual(self.contenu(), {"02": "A", "03": "B"})
        self.assertEqual(len(done), 2)

    def test_echange_de_deux_noms(self):
        self.creer(**{"01": "A", "02": "B"})
        done = self.appliquer([(self.dir / "01", self.dir / "02"), (self.dir / "02", self.dir / "01")])
        self.assertEqual(self.contenu(), {"01": "B", "02": "A"})
        self.assertEqual(done, {self.dir / "01", self.dir / "02"})

    def test_cycle_de_trois(self):
        self.creer(**{"1": "A", "2": "B", "3": "C"})
        planned = [(self.dir / "1", self.dir / "2"), (self.dir / "2", self.dir / "3"), (self.dir / "3", self.dir / "1")]
        done = self.appliquer(planned)
        self.assertEqual(self.contenu(), {"2": "A", "3": "B", "1": "C"})
        self.assertEqual(len(done), 3)

    def test_cycle_et_renommage_libre_ensemble(self):
        self.creer(**{"1": "A", "2": "B", "x": "X"})
        planned = [(self.dir / "1", self.dir / "2"), (self.dir / "2", self.dir / "1"), (self.dir / "x", self.dir / "y")]
        self.appliquer(planned)
        self.assertEqual(self.contenu(), {"1": "B", "2": "A", "y": "X"})

    def test_aucun_nom_temporaire_ne_reste(self):
        self.creer(**{"01": "A", "02": "B"})
        self.appliquer([(self.dir / "01", self.dir / "02"), (self.dir / "02", self.dir / "01")])
        self.assertFalse([n for n in self.contenu() if "tmp" in n])


class TestConflitsEtEchecs(DossierTestCase):
    def test_fichier_etranger_jamais_ecrase(self):
        # La cible existe et n'est pas dans le plan : personne ne la libérera.
        self.creer(a="A", b="ETRANGER")
        done = self.appliquer([(self.dir / "a", self.dir / "b")])
        self.assertEqual(self.contenu(), {"a": "A", "b": "ETRANGER"})
        self.assertEqual(done, set())
        self.assertIn("[IGNORÉ] existe déjà : b", self.sortie)

    def test_le_conflit_n_empeche_pas_les_autres(self):
        self.creer(a="A", b="ETRANGER", c="C")
        done = self.appliquer([(self.dir / "a", self.dir / "b"), (self.dir / "c", self.dir / "d")])
        self.assertEqual(self.contenu(), {"a": "A", "b": "ETRANGER", "d": "C"})
        self.assertEqual(done, {self.dir / "c"})

    def test_echec_systeme_signale_sans_arreter_les_autres(self):
        self.creer(a="A", c="C")
        vrai = Path.rename

        def capricieux(self_path, cible):
            if self_path.name == "a":
                raise PermissionError(13, "Accès refusé")
            return vrai(self_path, cible)

        with mock.patch.object(Path, "rename", capricieux):
            done = self.appliquer([(self.dir / "a", self.dir / "b"), (self.dir / "c", self.dir / "d")])
        self.assertEqual(self.contenu(), {"a": "A", "d": "C"})
        self.assertEqual(done, {self.dir / "c"})
        self.assertIn("[ÉCHEC] a -> b", self.sortie)

    def test_echec_en_cassant_un_cycle_n_efface_rien(self):
        self.creer(**{"01": "A", "02": "B"})
        with mock.patch.object(rename, "free_name", side_effect=OSError("aucun nom temporaire libre")):
            done = self.appliquer([(self.dir / "01", self.dir / "02"), (self.dir / "02", self.dir / "01")])
        self.assertEqual(self.contenu(), {"01": "A", "02": "B"})
        self.assertEqual(done, set())
        self.assertIn("[ÉCHEC]", self.sortie)


class TestCompteRendu(unittest.TestCase):
    def test_les_bilans_s_additionnent(self):
        total = rename.Tally(named=2, total=3, subtitles=1) + rename.Tally(named=1, total=4, subtitles=0, unresolved=1)
        self.assertEqual((total.named, total.total, total.subtitles, total.unresolved), (3, 7, 1, 1))


if __name__ == "__main__":
    unittest.main()
