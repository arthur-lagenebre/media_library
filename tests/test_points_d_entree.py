"""Les scripts lancés comme un utilisateur les lance (`python script.py`), et les cas limites de la recherche TMDB.

Un script qui plante en pile d'appels sur une clé refusée, ou qui prend un dossier vide pour un succès, se voit à la première panne : ces tests le vérifient avant.
"""

import io
import runpy
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common import cli
from libraries.video import lookup, mkv
from libraries.video.tmdb import Tmdb, TmdbAuthError, TmdbError
from scripts.Movies import Rename_Movies as renommeur
from tests.test_codes_de_sortie_video import ProgrammeTestCase
from tests.test_flux import FauxTmdb

RACINE = Path(__file__).resolve().parent.parent


class TestCleTmdbRefusee(unittest.TestCase):
    """Une clé invalide arrête tout avec un message clair : ni pile d'appels, ni cascade de « saison ignorée »."""

    SCRIPTS = {
        "Movies/Metadata.py": ["--no-tag"],
        "Movies/Rename_Movies.py": [],
        "TV_Shows/Metadata.py": ["--tmdb-id", "42", "--no-tag"],
        "TV_Shows/Rename_Episodes.py": ["--tmdb-id", "42"],
    }

    def lancer(self, script, options):
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            if script.startswith("Movies"):
                (racine / "Dune (2021)").mkdir()
                (racine / "Dune (2021)" / "film.mkv").write_text("x", encoding="utf-8")
            else:
                (racine / "Saison 1").mkdir()
                (racine / "Saison 1" / "01 - Pilote.mkv").write_text("x", encoding="utf-8")
            ligne = [str(RACINE / "scripts" / script), "--dir", str(racine), *options]
            refus = TmdbAuthError("clé TMDB refusée par l'API (HTTP 401). Vérifie la ligne TMDB_KEY=... de ton fichier .env.")
            with mock.patch.object(sys, "argv", ligne), mock.patch.object(cli, "resolve_tmdb_key", lambda *a: "mauvaise"), \
                    mock.patch.object(Tmdb, "_request", side_effect=refus), mock.patch.object(mkv, "check_tools", lambda **k: False), \
                    mock.patch.object(mkv, "read_light_all", lambda paths: {}), redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as sortie:
                    runpy.run_path(ligne[0], run_name="__main__")
            return sortie.exception.code

    def test_chaque_script_rend_un_message_et_pas_une_pile_d_appels(self):
        for script, options in self.SCRIPTS.items():
            with self.subTest(script):
                message = self.lancer(script, options)
                self.assertIsInstance(message, str)
                self.assertTrue(message.startswith("TMDB : clé TMDB refusée"), message)


class TestRechercheDUnFilm(unittest.TestCase):
    class Tmdb:
        def __init__(self, film=None, search=None, par_id=None):
            self.film = film or {"id": 7, "title": "Dune", "release_date": "2021-09-15"}
            self.search, self.par_id = search, par_id

        def movie(self, movie_id, language=None):
            if self.par_id:
                raise self.par_id
            return dict(self.film, id=int(movie_id))

        def search_movie(self, title, year=None):
            if self.search:
                raise self.search
            return [self.film]

    def chercher(self, tmdb, rawname, tag_id=None):
        with redirect_stdout(io.StringIO()) as sortie:
            return lookup.find_movie(tmdb, rawname, (), tag_id), sortie.getvalue()

    def test_id_epingle_inutilisable(self):
        (film, ordre), sortie = self.chercher(self.Tmdb(par_id=TmdbError("HTTP 404")), "Dune (2021) [tmdbid-7]")
        self.assertIsNone(film)
        self.assertIn("id épinglé 7 inutilisable", sortie)

    def test_id_du_fichier_inutilisable_retombe_sur_la_recherche(self):
        # Un identifiant inscrit autrefois puis disparu de TMDB ne doit pas empêcher de retrouver le film par son nom.
        (film, _), sortie = self.chercher(self.Tmdb(par_id=TmdbError("HTTP 404")), "Dune (2021)", tag_id="9")
        self.assertEqual(film["id"], 7)
        self.assertIn("id 9 lu dans le fichier inutilisable", sortie)
        self.assertIn("-> recherche", sortie)

    def test_recherche_en_panne(self):
        (film, _), sortie = self.chercher(self.Tmdb(search=TmdbError("HTTP 503")), "Dune (2021)")
        self.assertIsNone(film)
        self.assertIn("échec recherche TMDB", sortie)

    def test_titres_partages_signales_apres_la_recherche(self):
        class Deux(self.Tmdb):
            def search_movie(self, title, year=None):
                return [{"id": 1, "title": "Dune", "release_date": "2021-09-15"}, {"id": 2, "title": "Dune", "release_date": "1984-12-14"}]

        (film, _), sortie = self.chercher(Deux(), "Dune")
        self.assertEqual(film["id"], 1)
        self.assertIn("/!\\ titre partagé avec Dune (1984)", sortie)


class TestResolutionDeLaSerie(unittest.TestCase):
    class Tmdb:
        def __init__(self, resultats=(), erreur=None):
            self.resultats, self.erreur, self.recherches = list(resultats), erreur, []

        def search_tv(self, name, year=None):
            self.recherches.append((name, year))
            if self.erreur:
                raise self.erreur
            return self.resultats if (year is None or self.recherches[-1][1] is None) and self.resultats else []

    def resoudre(self, tmdb, dossier, forced=None):
        with redirect_stdout(io.StringIO()) as sortie:
            return lookup.resolve_show_id(tmdb, dossier, forced), sortie.getvalue()

    def test_id_force_dispense_de_tout(self):
        tmdb = self.Tmdb()
        self.assertEqual(self.resoudre(tmdb, "Ma Serie", forced=42)[0], 42)
        self.assertEqual(tmdb.recherches, [])

    def test_nom_de_dossier_inexploitable(self):
        resultat, sortie = self.resoudre(self.Tmdb(), "[1080p]")
        self.assertIsNone(resultat)
        self.assertIn("inexploitable", sortie)

    def test_recherche_en_panne(self):
        resultat, sortie = self.resoudre(self.Tmdb(erreur=TmdbError("HTTP 503")), "Breaking Bad")
        self.assertIsNone(resultat)
        self.assertIn("Échec de la recherche TMDB : HTTP 503", sortie)

    def test_aucune_serie(self):
        resultat, sortie = self.resoudre(self.Tmdb(), "Breaking Bad (2008)")
        self.assertIsNone(resultat)
        self.assertIn("Aucune série TMDB pour 'Breaking Bad' (2008)", sortie)

    def test_repli_sans_l_annee_quand_elle_ne_donne_rien(self):
        tmdb = self.Tmdb([{"id": 1396, "name": "Breaking Bad", "first_air_date": "2008-01-20"}])
        resultat, _ = self.resoudre(tmdb, "Breaking Bad (2009)")
        self.assertEqual(resultat, 1396)
        self.assertEqual(tmdb.recherches, [("Breaking Bad", "2009"), ("Breaking Bad", None)])

    def test_remarques_de_choix_affichees(self):
        tmdb = self.Tmdb([{"id": 1, "name": "Titre Sans Rapport", "first_air_date": "2008-01-20"}])
        _, sortie = self.resoudre(tmdb, "Breaking Bad")
        self.assertIn("/!\\", sortie)


class TestIdentifiantsLusDansLesFichiers(unittest.TestCase):
    def test_file_ids_lit_les_tags_sans_outil_externe(self):
        entree = types.SimpleNamespace(files=[Path("a.mkv"), Path("b.mkv")])
        lectures = {Path("a.mkv"): mkv.Reading(tags={(50, "TMDB", "movie/42")}), Path("b.mkv"): mkv.Reading(tags=set())}
        with mock.patch.object(renommeur.mkv, "read_light_all", lambda paths: lectures):
            ids = renommeur.file_ids([entree])
        self.assertEqual(ids, {Path("a.mkv"): "42", Path("b.mkv"): None})


class TestDossiersSansRienADire(ProgrammeTestCase):
    """Un dossier sans fiche ou sans série n'est pas un succès : le script le dit et sort en erreur."""

    def lancer_script(self, script, *options):
        ligne = [str(RACINE / "scripts" / script), "--dir", str(self.racine), *options]
        with mock.patch.object(sys, "argv", ligne), redirect_stdout(io.StringIO()) as texte:
            with self.assertRaises(SystemExit) as sortie:
                runpy.run_path(ligne[0], run_name="__main__")
        return sortie.exception.code, texte.getvalue()

    def test_index_sans_aucune_fiche(self):
        message, _ = self.lancer_script("TV_Shows/Index.py")
        self.assertIn("Aucune fiche dans", message)

    def test_index_n_ecrase_pas_une_page_etrangere(self):
        (self.racine / "index.html").write_text("<html>à moi</html>", encoding="utf-8")
        message, _ = self.lancer_script("TV_Shows/Index.py", "--apply")
        self.assertIn("n'a pas été écrit par ce script", message)
        self.assertEqual((self.racine / "index.html").read_text(encoding="utf-8"), "<html>à moi</html>")

    def test_recap_all_sans_serie(self):
        message, _ = self.lancer_script("TV_Shows/Recap_All.py")
        self.assertIn("Aucune série dans", message)
        self.assertIn("un sous-dossier par série", message)

    def test_recap_all_filtre_sans_resultat(self):
        (self.racine / "Breaking Bad" / "Saison 1").mkdir(parents=True)
        message, _ = self.lancer_script("TV_Shows/Recap_All.py", "--only", "Dexter")
        self.assertIn("dont le nom contient 'Dexter'", message)


if __name__ == "__main__":
    unittest.main()
