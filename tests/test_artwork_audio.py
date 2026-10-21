"""artwork.py (folder.jpg) et audio.py (le bon lecteur pour le bon format)."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.music import audio, flac, mp3
from libraries.video import artwork
from libraries.video.tmdb import TmdbError


class FauxTmdb:
    """Écrit l'image demandée, ou échoue comme on le lui demande."""

    def __init__(self, error=None):
        self.error, self.calls = error, []

    def save_image(self, poster_path, size, dest):
        self.calls.append((poster_path, size, Path(dest)))
        if self.error:
            raise self.error
        Path(dest).write_bytes(b"JPEG")


class TestAffichePourLeDossier(unittest.TestCase):
    def test_l_affiche_anglaise_est_preferee(self):
        self.assertEqual(artwork.english_poster(lambda: {"poster_path": "/en.jpg"}, "/fr.jpg"), "/en.jpg")

    def test_repli_quand_la_version_anglaise_n_en_a_pas(self):
        self.assertEqual(artwork.english_poster(lambda: {}, "/fr.jpg"), "/fr.jpg")
        self.assertEqual(artwork.english_poster(lambda: {"poster_path": None}, "/fr.jpg"), "/fr.jpg")

    def test_repli_quand_tmdb_echoue(self):
        def echoue():
            raise TmdbError("HTTP 503")
        self.assertEqual(artwork.english_poster(echoue, "/fr.jpg"), "/fr.jpg")

    def test_la_langue_demandee_est_l_anglais(self):
        self.assertEqual(artwork.ARTWORK_LANG, "en-US")


class TestEcritureDeFolderJpg(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dossier = Path(self._tmp.name)

    def test_pas_d_affiche(self):
        tmdb = FauxTmdb()
        self.assertEqual(artwork.write_poster(None, self.dossier, True, tmdb), "pas d'affiche TMDB")
        self.assertEqual(tmdb.calls, [])

    def test_simulation_n_ecrit_rien(self):
        tmdb = FauxTmdb()
        self.assertEqual(artwork.write_poster("/p.jpg", self.dossier, False, tmdb), "écrirait folder.jpg")
        self.assertEqual(tmdb.calls, [])
        self.assertEqual(list(self.dossier.iterdir()), [])

    def test_ecriture(self):
        tmdb = FauxTmdb()
        self.assertEqual(artwork.write_poster("/p.jpg", self.dossier, True, tmdb), "folder.jpg écrit")
        self.assertEqual((self.dossier / "folder.jpg").read_bytes(), b"JPEG")
        self.assertEqual(tmdb.calls, [("/p.jpg", artwork.POSTER_SIZE, self.dossier / "folder.jpg")])

    def test_taille_choisie(self):
        tmdb = FauxTmdb()
        artwork.write_poster("/p.jpg", self.dossier, True, tmdb, size="w780")
        self.assertEqual(tmdb.calls[0][1], "w780")

    def test_echec_tmdb_rendu_sans_exception(self):
        message = artwork.write_poster("/p.jpg", self.dossier, True, FauxTmdb(TmdbError("téléchargement incomplet")))
        self.assertEqual(message, "échec (téléchargement incomplet)")

    def test_echec_disque_rendu_sans_exception(self):
        message = artwork.write_poster("/p.jpg", self.dossier, True, FauxTmdb(PermissionError(13, "Accès refusé")))
        self.assertTrue(message.startswith("échec ("))


class TestAiguillageAudio(unittest.TestCase):
    def test_lecture_d_apres_l_extension(self):
        with mock.patch.object(flac, "read", return_value="flac") as lire_flac, mock.patch.object(mp3, "read", return_value="mp3") as lire_mp3:
            self.assertEqual(audio.read("a/01.flac"), "flac")
            self.assertEqual(audio.read("a/01.mp3"), "mp3")
            self.assertEqual(audio.read(Path("a/01.MP3")), "mp3")        # les extensions en capitales existent
        lire_flac.assert_called_once_with("a/01.flac")
        self.assertEqual(lire_mp3.call_count, 2)

    def test_une_extension_inconnue_va_au_lecteur_flac(self):
        # C'est le lecteur flac qui dira « pas un fichier FLAC » : l'aiguillage ne décide pas du format.
        with mock.patch.object(flac, "read", return_value="flac") as lire_flac:
            audio.read("a/01.ogg")
        lire_flac.assert_called_once()

    def test_ecriture_d_apres_ce_qui_a_ete_lu(self):
        meta_mp3 = mock.create_autospec(mp3.Metadata, instance=True)
        meta_flac = mock.create_autospec(flac.Metadata, instance=True)
        with mock.patch.object(flac, "write", return_value="sur place") as ecrire_flac, mock.patch.object(mp3, "write", return_value="recopie") as ecrire_mp3:
            self.assertEqual(audio.write("a.mp3", meta_mp3, ["c"], ["p"]), "recopie")
            self.assertEqual(audio.write("a.flac", meta_flac, ["c"], ["p"]), "sur place")
        ecrire_mp3.assert_called_once_with("a.mp3", meta_mp3, ["c"], ["p"])
        ecrire_flac.assert_called_once_with("a.flac", meta_flac, ["c"], ["p"])

    def test_les_noms_reexportes_restent_disponibles(self):
        self.assertTrue(issubclass(audio.AudioError, Exception))
        self.assertTrue(callable(audio.front_cover))
        self.assertIsNotNone(audio.FRONT_COVER)


if __name__ == "__main__":
    unittest.main()
