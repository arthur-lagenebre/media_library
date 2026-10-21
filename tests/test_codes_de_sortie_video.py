"""Films et séries : ce que rend un passage à un script qui l'enchaîne - 0 si tout est passé, 1 s'il reste un film sans fiche ou une saison sans réponse de TMDB.

Même règle que pour la musique : une panne de TMDB pendant la tâche planifiée du NAS ne doit pas passer pour un succès. TMDB est simulé.
"""

import io
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.video.tmdb import TmdbError
from scripts.Movies import Metadata as films
from scripts.Movies import Rename_Movies as renommeur
from scripts.TV_Shows import Metadata as series
from scripts.TV_Shows import Rename_Episodes as episodes
from tests.test_flux import FauxTmdb, FauxTmdbSerie


class ProgrammeTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.racine = Path(self._tmp.name)

    def lancer(self, module, tmdb, *argv, **patches):
        """(code de sortie, affichage). Un sys.exit("message") rend le message comme code."""
        ligne = [str(Path(module.__file__)), "--dir", str(self.racine), *argv]
        if hasattr(module, "mkv"):
            patches.setdefault("mkv.check_tools", lambda **k: False)        # ni MKVToolNix ni FFmpeg
        with mock.patch.object(sys, "argv", ligne), mock.patch.object(module, "Tmdb", lambda *a, **k: tmdb), \
                mock.patch.object(module.cli, "resolve_tmdb_key", lambda *a: "cle"), \
                redirect_stdout(io.StringIO()) as texte, _patches(module, patches):
            try:
                code = module.main()
            except SystemExit as sortie:
                code = sortie.code
        self.affichage = texte.getvalue()
        return code, self.affichage


class _patches:
    """mock.patch.object pour plusieurs cibles « module.attribut » à la fois (`mkv.check_tools` : l'attribut d'un sous-objet du module)."""

    def __init__(self, module, patches):
        self.actifs = []
        for chemin, valeur in patches.items():
            *parents, nom = chemin.split(".")
            cible = module
            for parent in parents:
                cible = getattr(cible, parent)
            self.actifs.append(mock.patch.object(cible, nom, valeur))

    def __enter__(self):
        for p in self.actifs:
            p.start()

    def __exit__(self, *exc):
        for p in reversed(self.actifs):
            p.stop()


# ----------------------------------------------------------------------------
# Movies/Metadata.py
# ----------------------------------------------------------------------------
class TmdbFilmsEnPanne(FauxTmdb):
    def __init__(self, recherche=None, details=None):
        super().__init__()
        self.recherche, self.details = recherche, details

    def search_movie(self, title, year=None):
        if self.recherche:
            raise self.recherche
        return super().search_movie(title, year)

    def movie(self, movie_id, language=None):
        if self.details:
            raise self.details
        return super().movie(movie_id, language)


class TmdbSansResultat(FauxTmdb):
    def search_movie(self, title, year=None):
        return []


class TestCodeDeSortieMetadataFilms(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        self.dune = self.racine / "Dune (2021)"
        self.dune.mkdir()
        (self.dune / "film.mkv").write_text("x", encoding="utf-8")

    def films(self, tmdb, *options):
        return self.lancer(films, tmdb, "--no-tag", *options, **{"mkv.read_light_all": lambda paths: {}})

    def test_tout_est_associe(self):
        code, texte = self.films(FauxTmdb())
        self.assertEqual(code, 0)
        self.assertNotIn("À CORRIGER", texte)

    def test_film_non_associe(self):
        code, texte = self.films(TmdbSansResultat())
        self.assertEqual(code, 1)
        self.assertIn("À CORRIGER : 1 sans fiche", texte)
        self.assertIn("[NON ASSOCIÉ]", (self.racine / "metadata.log").read_text(encoding="utf-8"))

    def test_recherche_tmdb_en_panne(self):
        code, texte = self.films(TmdbFilmsEnPanne(recherche=TmdbError("HTTP 503")))
        self.assertEqual(code, 1)
        self.assertIn("échec recherche TMDB", texte)
        self.assertIn("À CORRIGER : 1 sans fiche", texte)

    def test_fiche_tmdb_en_panne_pour_un_id_epingle(self):
        epingle = self.racine / "Blade (1998) [tmdbid-36586]"
        epingle.mkdir()
        (epingle / "film.mkv").write_text("x", encoding="utf-8")
        code, texte = self.films(TmdbFilmsEnPanne(details=TmdbError("HTTP 503")))
        self.assertEqual(code, 1)
        self.assertIn("échec détails TMDB", texte)

    def test_un_film_perdu_suffit_a_signaler_le_passage(self):
        class Selectif(FauxTmdb):
            def search_movie(self, title, year=None):
                return [] if "Blade" in title else super().search_movie(title, year)

        blade = self.racine / "Blade (1998)"
        blade.mkdir()
        (blade / "film.mkv").write_text("x", encoding="utf-8")
        code, texte = self.films(Selectif())
        self.assertEqual(code, 1)
        self.assertIn("TOTAL : 1/2", texte)


# ----------------------------------------------------------------------------
# Movies/Rename_Movies.py
# ----------------------------------------------------------------------------
class TestCodeDeSortieRenameMovies(ProgrammeTestCase):
    def renommer(self, tmdb, *options):
        return self.lancer(renommeur, tmdb, *options, file_ids=lambda movies: {})

    def creer(self, nom):
        (self.racine / nom).mkdir()
        (self.racine / nom / "film.mkv").write_text("x", encoding="utf-8")

    def test_tout_est_reconnu(self):
        self.creer("Dune (2021)")
        code, texte = self.renommer(FauxTmdb())
        self.assertEqual(code, 0)
        self.assertNotIn("À CORRIGER", texte)

    def test_des_films_a_renommer_en_simulation_ne_sont_pas_une_erreur(self):
        self.creer("dune.2021.1080p")
        code, _ = self.renommer(FauxTmdb())
        self.assertEqual(code, 0)

    def test_film_non_reconnu(self):
        self.creer("Dune (2021)")
        code, texte = self.renommer(TmdbSansResultat())
        self.assertEqual(code, 1)
        self.assertIn("À CORRIGER : 1 film(s) sans fiche", texte)

    def test_tmdb_en_panne(self):
        self.creer("Dune (2021)")
        code, texte = self.renommer(TmdbFilmsEnPanne(recherche=TmdbError("HTTP 503")))
        self.assertEqual(code, 1)
        self.assertIn("À CORRIGER", texte)

    def test_dossier_sans_film(self):
        code, texte = self.renommer(FauxTmdb())
        self.assertEqual(code, 0)
        self.assertIn("Aucun .mkv trouvé", texte)


# ----------------------------------------------------------------------------
# TV_Shows/Metadata.py et Rename_Episodes.py
# ----------------------------------------------------------------------------
class SerieDontUneSaisonEchoue(FauxTmdbSerie):
    def __init__(self, en_panne=(2,)):
        super().__init__()
        self.en_panne = en_panne

    def season(self, show_id, season_number, language=None):
        if season_number in self.en_panne:
            raise TmdbError("HTTP 503")
        return super().season(show_id, season_number, language)


class TestCodeDeSortieSeries(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        for numero in (1, 2):
            saison = self.racine / f"Saison {numero}"
            saison.mkdir()
            (saison / "01 - Pilote.mkv").write_text("x", encoding="utf-8")

    def metadata(self, tmdb):
        return self.lancer(series, tmdb, "--tmdb-id", "42", "--no-tag")

    def renommer(self, tmdb):
        return self.lancer(episodes, tmdb, "--tmdb-id", "42")

    def test_toutes_les_saisons_repondent(self):
        self.assertEqual(self.metadata(FauxTmdbSerie())[0], 0)
        self.assertEqual(self.renommer(FauxTmdbSerie())[0], 0)

    def test_metadata_une_saison_sans_reponse(self):
        code, texte = self.metadata(SerieDontUneSaisonEchoue())
        self.assertEqual(code, 1)
        self.assertIn("saison ignorée", texte)
        self.assertIn("À CORRIGER : 1 sans fiche", texte)

    def test_rename_une_saison_sans_reponse(self):
        code, texte = self.renommer(SerieDontUneSaisonEchoue())
        self.assertEqual(code, 1)
        self.assertIn("saison ignorée", texte)
        self.assertIn("À CORRIGER : 1 saison(s) ignorée(s)", texte)

    def test_la_saison_qui_repond_est_quand_meme_renommee(self):
        # Une saison en panne n'empêche pas les autres : elles se renomment, et le code de sortie dit qu'il reste à faire.
        (self.racine / "Saison 1" / "01 - Pilote.mkv").rename(self.racine / "Saison 1" / "S01E01.mkv")
        code, _ = self.lancer(episodes, SerieDontUneSaisonEchoue(), "--tmdb-id", "42", "--apply")
        self.assertEqual(code, 1)
        self.assertEqual([p.name for p in (self.racine / "Saison 1").iterdir()], ["01 - Pilote.mkv"])

    def test_saison_unique_sans_reponse_s_arrete_net(self):
        for saison in ("Saison 1", "Saison 2"):
            (self.racine / saison / "01 - Pilote.mkv").unlink()
            (self.racine / saison).rmdir()
        (self.racine / "01 - Pilote.mkv").write_text("x", encoding="utf-8")
        for appel in (self.metadata, self.renommer):
            code, _ = appel(SerieDontUneSaisonEchoue(en_panne=(1,)))
            self.assertIn("Échec de l'appel TMDB", code)


if __name__ == "__main__":
    unittest.main()
