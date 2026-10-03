"""Déroulement complet des scripts, TMDB simule : ce que produit une invocation.

Les tests unitaires couvrent les pièces ; ceux-ci vérifient qu'elles sont bien reliées entre elles - c'est la que se logent les options qui ne font rien.
"""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.Movies import Metadata as films
from scripts.TV_Shows import Metadata as series
from scripts.TV_Shows import Rename_Episodes as rename

class FauxTmdb:
    """Répond comme TMDB, sans réseau, et note ce qu'on lui à demande."""

    def __init__(self):
        self.saisons = []

    def search_movie(self, title, year=None):
        return [{"id": 1, "title": "Dune", "release_date": "2021-09-15"}]

    def movie(self, movie_id, language=None):
        return {"id": 1, "title": "Dune", "release_date": "2021-09-15", "poster_path": "/dune.jpg", "credits": {}}

    def local_release_date(self, movie_id, region):
        return None

    def image(self, image_path, size):
        return b"jpeg"

    def save_image(self, image_path, size, dest):
        Path(dest).write_bytes(self.image(image_path, size))

    def season(self, show_id, season_number, language=None):
        self.saisons.append(season_number)
        return {"season_number": season_number, "episodes": [{"episode_number": 1, "name": "Special"}]}


class FauxTmdbSerie(FauxTmdb):
    """Une série d'une saison, avec son casting cumule."""

    def __init__(self):
        super().__init__()
        self.castings = []

    def series(self, show_id, language=None):
        return {"id": show_id, "name": "Ma Serie", "overview": "Resume", "poster_path": "/serie.jpg"}

    def season(self, show_id, season_number, language=None):
        self.saisons.append(season_number)
        return {"season_number": season_number, "name": f"Saison {season_number}",
                "episodes": [{"episode_number": 1, "name": "Pilote", "still_path": "/s1.jpg"}]}

    def aggregate_credits(self, show_id, season_number=None, language=None):
        self.castings.append(season_number)
        return {"cast": [{"id": 7, "name": "A. Acteur", "profile_path": "/a.jpg", "order": 0,
                          "total_episode_count": 1,
                          "roles": [{"character": "Lui-meme", "episode_count": 1}]}]}


class FluxTestCase(unittest.TestCase):
    def lancer(self, module, argv, tmdb=None):
        """Exécute main() du script avec un TMDB simule. Retourne (tmdb, sortie)."""
        tmdb = tmdb or FauxTmdb()
        sortie = io.StringIO()
        with mock.patch.object(sys, "argv", ["script"] + argv), mock.patch.object(module, "Tmdb", lambda *a, **k: tmdb), mock.patch.object(module.cli, "resolve_tmdb_key", lambda *a: "cle"), redirect_stdout(sortie):
            module.main()
        return tmdb, sortie.getvalue()


class TestAnnexesDesFilms(FluxTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self._tmp.name)
        self.film = self.racine / "Dune (2021)"
        self.film.mkdir()
        (self.film / "film.mkv").write_text("x", encoding="utf-8")
        self.addCleanup(self._tmp.cleanup)

    def lancer_films(self, *options):
        """Lance le script films, sans MKVToolNix ni lecture des fichiers (sauf si le test pose self.lecture) : l'écriture dans le .mkv est simulée et notée, ce qu'on regarde ici est ce que le script decide d'écrire."""
        self.ecritures = []

        def faux_write(path, info, target, opts, tmdb):
            self.ecritures.append(Path(path).name)
            return 0, ""

        with mock.patch.object(films.mkv, "check_tools", lambda **k: False), mock.patch.object(films.mkv, "write", faux_write), mock.patch.object(films.mkv, "read_light_all", getattr(self, "lecture", lambda paths: {})):
            return self.lancer(films, ["--dir", str(self.racine), *options])

    def test_affiche_ecrite_meme_sans_etiquetage(self):
        # Régression : --artwork vivait dans le traitement du fichier, que --no-tag saute - l'option ne produisait donc rien.
        self.lancer_films("--no-tag", "--artwork", "--apply")
        self.assertTrue((self.film / "folder.jpg").exists())

    def test_affiche_ecrite_par_un_etiquetage_normal(self):
        self.lancer_films("--artwork", "--apply")
        self.assertTrue((self.film / "folder.jpg").exists())
        self.assertEqual(self.ecritures, ["film.mkv"])     # le .mkv aussi a été écrit

    def test_verify_n_ecrit_aucune_annexe(self):
        _, sortie = self.lancer_films("--artwork", "--verify")
        self.assertFalse((self.film / "folder.jpg").exists())
        self.assertIn("ecrirait folder.jpg", sortie)

    def test_recap_ecrit_sous_no_tag(self):
        self.lancer_films("--no-tag", "--recap", "--apply")
        self.assertTrue((self.racine / "index.html").exists())

    def lancer_peu_vote(self, *options):
        """Un film que presque personne n'a noté : l'association est suspecte."""
        class PeuVote(FauxTmdb):
            def movie(self, movie_id, language=None):
                return {**super().movie(movie_id, language), "vote_count": 3}

        with mock.patch.object(films.mkv, "check_tools", lambda **k: False), mock.patch.object(films.mkv, "read_light_all", lambda paths: {}):
            return self.lancer(films, ["--dir", str(self.racine), "--no-tag", *options], tmdb=PeuVote())

    def test_doute_signale_sans_validation(self):
        _, sortie = self.lancer_peu_vote()
        self.assertIn("presque inconnue", sortie)
        self.assertIn("[A VERIFIER]", (self.racine / "metadata.log").read_text(encoding="utf-8"))

    def test_film_valide_ne_fait_plus_de_doute(self):
        (self.racine / "metadata.ok").write_text("https://www.themoviedb.org/movie/1  # Dune, ok\n", encoding="utf-8")
        _, sortie = self.lancer_peu_vote()
        self.assertNotIn("presque inconnue", sortie)
        self.assertNotIn("A VERIFIER", (self.racine / "metadata.log").read_text(encoding="utf-8"))
        self.assertIn("1 film(s) valide(s)", sortie)

    def test_validation_lue_a_cote_du_journal(self):
        annexes = self.racine / "__Data__"
        annexes.mkdir()
        (annexes / "metadata.ok").write_text("1\n", encoding="utf-8")
        _, sortie = self.lancer_peu_vote("--recap", "--recap-out", str(annexes))
        self.assertNotIn("presque inconnue", sortie)

    def test_chaque_film_a_sa_fiche(self):
        self.lancer_films("--no-tag", "--recap", "--apply")
        fiche = (self.racine / "Fiches" / "1.html").read_text(encoding="utf-8")
        self.assertIn("<title>Dune (2021)</title>", fiche)
        self.assertIn("href='../index.html'", fiche)
        self.assertIn("href='Fiches/1.html'", (self.racine / "index.html").read_text(encoding="utf-8"))

    def test_simulation_n_ecrit_aucune_fiche(self):
        self.lancer_films("--no-tag", "--recap")
        self.assertFalse((self.racine / "Fiches").exists())
        self.assertFalse((self.racine / "index.html").exists())

    def test_fiches_rangees_a_cote_de_l_index(self):
        annexes = self.racine / "__Data__"
        annexes.mkdir()
        self.lancer_films("--no-tag", "--recap", "--recap-out", str(annexes / "films.html"), "--apply")
        self.assertIn("href='../films.html'", (annexes / "Fiches" / "1.html").read_text(encoding="utf-8"))
        self.assertFalse((self.racine / "Fiches").exists())

    def test_fiches_identiques_pas_reecrites(self):
        self.lancer_films("--no-tag", "--recap", "--apply")
        fiche = self.racine / "Fiches" / "1.html"
        avant = fiche.stat().st_mtime_ns
        _, sortie = self.lancer_films("--no-tag", "--recap", "--apply")
        self.assertIn("(0 ecrite(s), 1 inchangee(s))", sortie)
        self.assertEqual(fiche.stat().st_mtime_ns, avant)

    def test_recap_identique_pas_reecrit(self):
        # Lancée chaque nuit sur un NAS, la fiche ne doit pas changer de date tant que rien ne bouge.
        self.lancer_films("--no-tag", "--recap", "--apply")
        _, sortie = self.lancer_films("--no-tag", "--recap", "--apply")
        self.assertIn("index.html inchange", sortie)
        self.assertIn("metadata.log inchange", sortie)

    def test_journal_a_cote_de_la_fiche_rangee_ailleurs(self):
        annexes = self.racine / "__Data__"
        annexes.mkdir()
        self.lancer_films("--no-tag", "--recap", "--recap-out", str(annexes), "--apply")
        self.assertTrue((annexes / "index.html").exists())
        self.assertTrue((annexes / "metadata.log").exists())
        self.assertFalse((self.racine / "metadata.log").exists())

    def test_ancienne_fiche_renommee_et_reprise(self):
        # recap.html devient index.html : renommée plutôt que doublée, elle garde son titre et ses affiches en cache.
        (self.racine / "recap.html").write_text("<html><head><title>Ma videotheque</title></head></html>", encoding="utf-8")
        self.lancer_films("--no-tag", "--recap", "--apply")
        self.assertFalse((self.racine / "recap.html").exists())
        self.assertIn("<title>Ma videotheque</title>", (self.racine / "index.html").read_text(encoding="utf-8"))

    def test_titre_par_defaut_puis_choisi(self):
        self.lancer_films("--no-tag", "--recap", "--apply")
        self.assertIn("<title>Films</title>", (self.racine / "index.html").read_text(encoding="utf-8"))
        self.lancer_films("--no-tag", "--recap", "--title", "Cinematheque", "--apply")
        self.lancer_films("--no-tag", "--recap", "--apply")       # la tache de nuit, sans --title
        self.assertIn("<title>Cinematheque</title>", (self.racine / "index.html").read_text(encoding="utf-8"))

    def test_no_tag_relit_l_id_inscrit_dans_le_film(self):
        # Régression : sous --no-tag, rien n'était lu - "Mortal Kombat" (1995), pourtant identifié dans son fichier, redevenait par recherche celui de 2021.
        read = films.mkv.Reading(info={}, tags={(50, "TMDB", "movie/438631")})
        self.lecture = lambda paths: {p: read for p in paths}
        with mock.patch.object(films.mkv, "inspect_all", side_effect=AssertionError("MKVToolNix sollicite")):
            _, sortie = self.lancer_films("--no-tag", "--recap")
        self.assertIn("id lu dans le fichier", sortie)


class TestAnnexesDesSeries(FluxTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self._tmp.name)
        saison = self.racine / "Saison 1"
        saison.mkdir()
        (saison / "01 - Pilote.mkv").write_text("x", encoding="utf-8")
        self.addCleanup(self._tmp.cleanup)

    def lancer_serie(self, *options):
        with mock.patch.object(series.mkv, "check_tools", lambda **k: False):
            return self.lancer(series, ["--dir", str(self.racine), "--tmdb-id", "42",
                                        "--no-tag", *options], tmdb=FauxTmdbSerie())

    def test_le_recap_porte_l_onglet_casting(self):
        tmdb, _ = self.lancer_serie("--recap", "--apply")
        html = (self.racine / "index.html").read_text(encoding="utf-8")
        self.assertEqual(tmdb.castings, [1])            # une saison, un appel
        self.assertIn("data-s='cast'", html)
        self.assertIn("A. Acteur", html)
        self.assertIn("<img data-img='w185/a.jpg'", html)

    def test_ancienne_fiche_renommee(self):
        (self.racine / "recap.html").write_text("<html><head><title>Ma Serie</title></head></html>", encoding="utf-8")
        self.lancer_serie("--recap", "--apply")
        self.assertFalse((self.racine / "recap.html").exists())
        self.assertTrue((self.racine / "index.html").exists())

    def test_la_simulation_n_interroge_pas_le_casting(self):
        tmdb, sortie = self.lancer_serie("--recap")
        self.assertEqual(tmdb.castings, [])
        self.assertFalse((self.racine / "index.html").exists())
        self.assertIn("ecrirait index.html", sortie)


class TestDoublons(FluxTestCase):
    def test_deux_dossiers_pour_un_film(self):
        # Le récap n'en montrera qu'une vignette (les films y sont indexés par id) : l'écart avec le total doit être expliqué, pas laisse deviner.
        with tempfile.TemporaryDirectory() as d:
            racine = Path(d)
            for nom in ("Dune (2021)", "Dune 4K (2021)"):
                (racine / nom).mkdir()
                (racine / nom / "film.mkv").write_text("x", encoding="utf-8")
            with mock.patch.object(films.mkv, "check_tools", lambda **k: False):
                _, sortie = self.lancer(films, ["--dir", str(racine), "--no-tag"])
        self.assertIn("[DOUBLON]", sortie)
        self.assertIn("TOTAL : 2/2", sortie)       # les deux restent traités


class TestSaisonUnique(FluxTestCase):
    def lancer_rename(self, nom_du_dossier):
        with tempfile.TemporaryDirectory() as d:
            dossier = Path(d) / nom_du_dossier
            dossier.mkdir()
            (dossier / "01 - brut.mkv").write_text("x", encoding="utf-8")
            tmdb, _ = self.lancer(rename, ["--dir", str(dossier), "--tmdb-id", "42"])
            return tmdb.saisons

    def test_dossier_de_speciaux_demande_la_saison_zero(self):
        # Régression : un 'or 1' transformait la saison 0 en saison 1, et les spéciaux se retrouvaient renommés avec les titres des vrais épisodes.
        self.assertEqual(self.lancer_rename("Specials"), [0])

    def test_dossier_de_saison_ordinaire(self):
        self.assertEqual(self.lancer_rename("Saison 3"), [3])

    def test_dossier_sans_numero_vaut_la_premiere_saison(self):
        self.assertEqual(self.lancer_rename("Ma Serie"), [1])

class TestDossierInvalide(FluxTestCase):
    """Une faute de frappe dans --dir doit s'arrêter net, avant tout appel TMDB."""

    def echec(self, module, dossier, options=()):
        tmdb = FauxTmdb()
        with self.assertRaises(SystemExit) as ctx:
            self.lancer(module, ["--dir", str(dossier), *options], tmdb)
        return str(ctx.exception), tmdb

    def test_films_dossier_introuvable(self):
        message, _ = self.echec(films, "dossier_qui_n_existe_pas")
        self.assertIn("introuvable", message)

    def test_rename_dossier_introuvable(self):
        # Régression : levait une FileNotFoundError brute en pleine figure.
        message, tmdb = self.echec(rename, "dossier_qui_n_existe_pas", ["--tmdb-id", "42"])
        self.assertIn("introuvable", message)
        self.assertEqual(tmdb.saisons, [])          # arrêt avant le réseau

    def test_dir_sur_un_fichier(self):
        with tempfile.TemporaryDirectory() as d:
            fichier = Path(d) / "film.mkv"
            fichier.write_text("x", encoding="utf-8")
            message, _ = self.echec(rename, fichier, ["--tmdb-id", "42"])
        self.assertIn("pas un fichier", message)

if __name__ == "__main__":
    unittest.main()
