"""Movies/Metadata.py : le traitement d'un fichier, les sagas qui replacent un film, la fiche et le déroulé complet.

TMDB et les outils MKVToolNix sont simulés : on regarde ce que le script décide d'écrire et ce qu'il en dit.
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
from libraries.video import lookup, mkv, naming
from libraries.video.tmdb import TmdbError
from scripts.Movies import Metadata as films
from tests.test_codes_de_sortie_video import ProgrammeTestCase
from tests.test_flux import FauxTmdb

OPTS = mkv.Options(cover=False, date=True, audio_names=True, sub_names=True, flags=True, stats=True, image_size="w780")
INFO = {"tracks": [{"id": 0, "type": "video"}, {"id": 1, "type": "audio", "codec": "AC-3", "properties": {"language": "fre", "audio_channels": 2}}]}
DUNE = {"id": 438631, "title": "Dune", "overview": "Un désert.", "release_date": "2021-09-15", "credits": {}}


def arguments(**changes):
    args = dict(verify=False, apply=False, skip_done=False, no_tag=False, no_date=False, language="fr-FR", artwork=False, tmdb_id=None, dir="")
    args.update(changes)
    return types.SimpleNamespace(**args)


class TestTagsDuFilm(unittest.TestCase):
    def test_synopsis_ecrit_deux_fois(self):
        # SYNOPSIS pour les lecteurs qui le connaissent, SUMMARY pour les autres.
        xml = films.movie_target(DUNE, OPTS).tags_xml
        self.assertEqual(xml.count("Un désert."), 2)

    def test_sans_synopsis(self):
        xml = films.movie_target(dict(DUNE, overview=""), OPTS).tags_xml
        self.assertNotIn("SYNOPSIS", xml)

    def test_identifiant_inscrit_dans_le_film(self):
        self.assertIn("movie/438631", films.movie_target(DUNE, OPTS).tags_xml)


class TestTraitementDUnFichier(unittest.TestCase):
    def traiter(self, args=None, lecture=None, verify_rend=(), conforme=False, ecriture=(0, ""), movie=DUNE):
        self.ecritures = []

        def write(path, info, target, opts, tmdb):
            self.ecritures.append(Path(path).name)
            return ecriture

        sortie = io.StringIO()
        with mock.patch.object(films.mkv, "verify", lambda *a: list(verify_rend)), mock.patch.object(films.mkv, "is_conform", lambda *a: conforme), \
                mock.patch.object(films.mkv, "write", write), redirect_stdout(sortie):
            resultat = films.process_file(Path("Dune.mkv"), lecture or mkv.Reading(info=INFO), movie, args or arguments(), OPTS, None)
        self.sortie = sortie.getvalue()
        return resultat

    def test_simulation_montre_sans_ecrire(self):
        self.assertEqual(self.traiter(), (0, 0))
        self.assertEqual(self.ecritures, [])
        self.assertIn("date -> 2021-09-15 (sortie d'origine)", self.sortie)
        self.assertIn("audio a1 [fre]", self.sortie)

    def test_date_nationale_annoncee(self):
        self.traiter(movie=dict(DUNE, _date_region="FR"))
        self.assertIn("(sortie FR)", self.sortie)

    def test_note_de_lecture_reprise(self):
        self.traiter(lecture=mkv.Reading(info=INFO, note="lecture impossible par mkvmerge (code 2)"))
        self.assertIn("lecture impossible par mkvmerge (code 2)", self.sortie)

    def test_application_ecrit(self):
        self.assertEqual(self.traiter(arguments(apply=True)), (0, 0))
        self.assertEqual(self.ecritures, ["Dune.mkv"])
        self.assertIn("[OK]", self.sortie)

    def test_echec_d_ecriture(self):
        self.assertEqual(self.traiter(arguments(apply=True), ecriture=(2, "Erreur : verrouillé")), (0, 1))
        self.assertIn("[ÉCHEC] Erreur : verrouillé", self.sortie)

    def test_skip_done(self):
        self.assertEqual(self.traiter(arguments(apply=True, skip_done=True), conforme=True), (0, 0))
        self.assertEqual(self.ecritures, [])
        self.assertIn("[SKIP] déjà à jour", self.sortie)

    def test_skip_done_ecrit_ce_qui_n_est_pas_a_jour(self):
        self.traiter(arguments(apply=True, skip_done=True), conforme=False)
        self.assertEqual(self.ecritures, ["Dune.mkv"])

    def test_verification_avec_ecarts(self):
        self.assertEqual(self.traiter(arguments(verify=True), verify_rend=[("titre", False, "ancien"), ("date", True, "ok")]), (1, 0))
        self.assertIn("[DIFF] titre : actuel = 'ancien'", self.sortie)
        self.assertEqual(self.ecritures, [])

    def test_verification_conforme(self):
        self.assertEqual(self.traiter(arguments(verify=True), verify_rend=[("titre", True, "ok")]), (0, 0))
        self.assertIn("[OK] déjà conforme", self.sortie)


class TestFilmEnPlusieursFichiers(unittest.TestCase):
    def test_chaque_fichier_est_nomme_et_traite(self):
        entree = naming.MovieFolder(folder=Path("."), files=[Path("Dune CD1.mkv"), Path("Dune CD2.mkv")], rawname="Dune")
        lectures = {p: mkv.Reading(info=INFO) for p in entree.files}
        ecrits = []
        with mock.patch.object(films.mkv, "write", lambda path, *a: ecrits.append(Path(path).name) or (0, "")), redirect_stdout(io.StringIO()) as sortie:
            report = films.process_movie(entree, DUNE, lectures, arguments(apply=True), OPTS, None)
        self.assertEqual(ecrits, ["Dune CD1.mkv", "Dune CD2.mkv"])
        self.assertIn("· Dune CD1.mkv", sortie.getvalue())
        self.assertEqual((report.matched, report.total, report.failures), (1, 1, 0))


class TestDateNationale(unittest.TestCase):
    class Tmdb:
        def __init__(self, date):
            self.date = date

        def movie(self, movie_id, language=None):
            return dict(DUNE, id=int(movie_id))

        def local_release_date(self, movie_id, region):
            return self.date

    def details(self, date, **changes):
        with redirect_stdout(io.StringIO()):
            return films.movie_details(1, None, arguments(**changes), self.Tmdb(date))

    def test_sortie_nationale_remplace_celle_d_origine(self):
        film = self.details("2021-09-22")
        self.assertEqual((film["release_date"], film["_date_region"]), ("2021-09-22", "FR"))

    def test_sans_sortie_nationale_celle_d_origine_reste(self):
        film = self.details(None)
        self.assertEqual(film["release_date"], "2021-09-15")
        self.assertNotIn("_date_region", film)

    def test_no_date_ne_cherche_pas(self):
        self.assertNotIn("_date_region", self.details("2021-09-22", no_date=True))

    def test_ordre_de_saga_retenu(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(films.movie_details(1, 2, arguments(), self.Tmdb(None))["_order"], 2)


class TestQuestionAvecRemarques(unittest.TestCase):
    def test_les_remarques_du_doute_sont_affichees_avant_les_candidats(self):
        entree = naming.MovieFolder(folder=Path("."), files=[Path("f.mkv")], rawname="Dracula")
        doute = lookup.Doubt(query="Dracula", candidates=[{"id": 1, "title": "Dracula", "release_date": "1931-02-12"}, {"id": 2, "title": "Dracula", "release_date": "1992-11-13"}], notes=["trois films portent ce titre"])
        with mock.patch.object(films.cli, "can_ask", lambda: True), mock.patch.object(films.cli, "ask_choice", lambda n, d=0: films.cli.ASK_SKIP), redirect_stdout(io.StringIO()) as sortie:
            films.resolve_pending([(entree, doute)], films.Library([], {}, {}), arguments(), OPTS, None)
        texte = sortie.getvalue()
        self.assertIn("/!\\ trois films portent ce titre", texte)
        self.assertLess(texte.index("/!\\ trois films"), texte.index("1) "))


class TestJournal(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.racine = Path(self._tmp.name)
        self.library = films.Library([], {}, {})
        self.library.note("Dune (2021)", 438631)
        self.library.note("Film perdu", None, "[NON ASSOCIÉ]")

    def ecrire(self, racine=None):
        with redirect_stdout(io.StringIO()) as sortie:
            films.write_log(racine or self.racine, self.library, arguments(), films.Report(matched=1, total=2))
        return sortie.getvalue()

    def test_liens_d_abord_puis_les_films_sans_lien(self):
        self.ecrire()
        contenu = (self.racine / "metadata.log").read_text(encoding="utf-8")
        self.assertLess(contenu.index("Dune (2021)"), contenu.index("sans lien"))
        self.assertIn("themoviedb.org/movie/438631", contenu)
        self.assertIn("Film perdu", contenu)

    def test_journal_inchange_non_reecrit(self):
        self.assertIn("écrit (1 lien(s), 1 sans lien)", self.ecrire())
        avant = (self.racine / "metadata.log").stat().st_mtime_ns
        self.assertIn("metadata.log inchangé", self.ecrire())
        self.assertEqual((self.racine / "metadata.log").stat().st_mtime_ns, avant)

    def test_journal_impossible_a_ecrire_n_arrete_pas_le_script(self):
        self.assertIn("metadata.log non écrit", self.ecrire(self.racine / "absent"))



# ----------------------------------------------------------------------------
# Les sagas
# ----------------------------------------------------------------------------
BATMAN_V_SUPERMAN = {"id": 2, "title": "Batman v Superman : L'Aube de la justice", "release_date": "2016-03-23"}
MAN_OF_STEEL = {"id": 1, "title": "Man of Steel", "release_date": "2013-06-12"}


class TmdbSaga(FauxTmdb):
    """Une saga « DCEU » de deux films, et un homonyme qui détourne « Batman v Superman » vers un autre film."""

    def __init__(self, collection_error=None, search_error=None, collections=None):
        super().__init__()
        self.collection_error, self.search_error = collection_error, search_error
        self.collections = collections if collections is not None else [{"id": 500, "name": "DCEU"}]

    def search_movie(self, title, year=None):
        if "batman" in title.lower():
            return [{"id": 99, "title": "Batman v Superman Homonyme", "release_date": "2010-01-01"}]
        if "man of steel" in title.lower():
            return [MAN_OF_STEEL]
        return []

    def search_collection(self, name):
        if self.search_error:
            raise self.search_error
        return list(self.collections)

    def collection(self, collection_id, language=None):
        if self.collection_error:
            raise self.collection_error
        return {"parts": [MAN_OF_STEEL, BATMAN_V_SUPERMAN]}

    def movie(self, movie_id, language=None):
        base = {1: MAN_OF_STEEL, 2: BATMAN_V_SUPERMAN}.get(int(movie_id), {"title": "Batman v Superman Homonyme"})
        return dict(base, id=int(movie_id), credits={}, belongs_to_collection={"id": 500} if int(movie_id) in (1, 2) else None)


class SagaTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.racine = Path(self._tmp.name)
        self.dossier = self.racine / "DCEU"
        self.dossier.mkdir()
        for nom in ("01 - Man of Steel.mkv", "02 - Batman v Superman.mkv"):
            (self.dossier / nom).write_text("x", encoding="utf-8")


class TestPistesDeSaga(SagaTestCase):
    def candidats(self, tmdb, vues=(), dossier=None):
        return films.saga_candidates(dossier or self.dossier, list(vues), tmdb)

    def test_la_saga_du_nom_du_dossier(self):
        self.assertEqual(self.candidats(TmdbSaga()), [[MAN_OF_STEEL, BATMAN_V_SUPERMAN]])

    def test_une_saga_qui_ne_ressemble_pas_au_dossier_est_ecartee(self):
        # Un dossier « films » ramène « MIRRORLIAR FILMS » : ce n'est pas une saga.
        tmdb = TmdbSaga(collections=[{"id": 7, "name": "MIRRORLIAR FILMS"}])
        self.assertEqual(self.candidats(tmdb, dossier=self.racine / "films"), [])

    def test_saga_vers_laquelle_plusieurs_films_pointent(self):
        tmdb = TmdbSaga(collections=[])
        self.assertEqual(self.candidats(tmdb, vues=[500, 500]), [[MAN_OF_STEEL, BATMAN_V_SUPERMAN]])

    def test_un_seul_film_ne_fait_pas_une_saga(self):
        self.assertEqual(self.candidats(TmdbSaga(collections=[]), vues=[500, None]), [])

    def test_recherche_de_saga_en_panne(self):
        self.assertEqual(self.candidats(TmdbSaga(search_error=TmdbError("HTTP 503"))), [])
        self.assertEqual(self.candidats(TmdbSaga(search_error=TmdbError("HTTP 503")), vues=[500, 500]), [[MAN_OF_STEEL, BATMAN_V_SUPERMAN]])

    def test_composition_de_saga_en_panne(self):
        self.assertEqual(self.candidats(TmdbSaga(collection_error=TmdbError("HTTP 503"))), [])

    def test_deux_pistes_quand_le_nom_et_les_films_designent_deux_sagas(self):
        class DeuxSagas(TmdbSaga):
            def collection(self, collection_id, language=None):
                return {"parts": [{"id": collection_id, "title": "Film"}]}

        resultat = self.candidats(DeuxSagas(collections=[{"id": 500, "name": "DCEU"}]), vues=[600, 600])
        self.assertEqual([[p["id"] for p in parts] for parts in resultat], [[500], [600]])


class TestCorrectionsDeSaga(SagaTestCase):
    def corrections(self, tmdb, lectures=None):
        movies = naming.find_movies(self.racine)
        with redirect_stdout(io.StringIO()):
            return films.saga_corrections(movies, lectures or {}, arguments(), tmdb), movies

    def test_l_homonyme_est_remplace_par_le_film_de_la_saga(self):
        corrections, movies = self.corrections(TmdbSaga())
        noms = {m.display for m in movies}
        self.assertEqual(len(noms), 2)
        (affiche,) = corrections                       # un seul film est replacé : celui que l'homonyme avait détourné
        self.assertIn("Batman", affiche)
        self.assertEqual(corrections[affiche]["id"], 2)

    def test_sans_saga_aucune_correction(self):
        corrections, _ = self.corrections(TmdbSaga(collections=[]))
        self.assertEqual(corrections, {})

    def test_un_identifiant_epingle_ne_se_discute_pas(self):
        # « [tmdbid-99] » : l'utilisateur a tranché, la saga ne peut ni le déplacer ni lui prendre sa fiche.
        (self.dossier / "02 - Batman v Superman.mkv").rename(self.dossier / "02 - Batman v Superman [tmdbid-99].mkv")
        corrections, _ = self.corrections(TmdbSaga())
        self.assertEqual(corrections, {})

    def test_numerotation_plus_longue_que_la_saga(self):
        # Trois numéros pour une collection de deux films : c'est un dossier de rangement, pas cette saga.
        (self.dossier / "03 - Man of Steel 2.mkv").write_text("x", encoding="utf-8")
        corrections, _ = self.corrections(TmdbSaga())
        self.assertEqual(corrections, {})

    def test_une_seconde_piste_n_est_pas_essayee_quand_la_premiere_a_tout_place(self):
        class DeuxPistes(TmdbSaga):
            appels = []

            def movie(self, movie_id, language=None):
                return dict(super().movie(movie_id, language), belongs_to_collection={"id": 600})

            def collection(self, collection_id, language=None):
                self.appels.append(collection_id)
                return super().collection(collection_id, language)

        tmdb = DeuxPistes()
        corrections, _ = self.corrections(tmdb)
        self.assertEqual(len(corrections), 1)
        self.assertEqual(tmdb.appels, [500, 600])          # les deux pistes sont lues, mais la seconde n'a plus rien à placer

    def test_aucun_fichier_a_replacer_quand_tout_est_epingle(self):
        for nom in list(p.name for p in self.dossier.iterdir()):
            base = nom[:-4]
            (self.dossier / nom).rename(self.dossier / f"{base} [tmdbid-{1 if 'Steel' in base else 2}].mkv")
        corrections, _ = self.corrections(TmdbSaga())
        self.assertEqual(corrections, {})

    def test_dossier_a_un_seul_film_hors_sujet(self):
        (self.dossier / "02 - Batman v Superman.mkv").unlink()
        corrections, _ = self.corrections(TmdbSaga())
        self.assertEqual(corrections, {})


class TestSagaDeBoutEnBout(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        (self.racine / "DCEU").mkdir()
        for nom in ("01 - Man of Steel.mkv", "02 - Batman v Superman.mkv"):
            (self.racine / "DCEU" / nom).write_text("x", encoding="utf-8")

    def lancer_films(self, *options):
        return self.lancer(films, TmdbSaga(), "--no-tag", *options, **{"mkv.read_light_all": lambda paths: {}})

    def test_main_annonce_les_films_replaces(self):
        code, texte = self.lancer_films()
        self.assertIn("1 film(s) replacé(s) par leur saga TMDB.", texte)
        self.assertIn("placé par sa saga", texte)
        self.assertEqual(code, 0)

    def test_no_saga_court_circuite_la_passe(self):
        _, texte = self.lancer_films("--no-saga")
        self.assertNotIn("replacé(s) par leur saga", texte)
        self.assertNotIn("placé par sa saga", texte)


# ----------------------------------------------------------------------------
# Le déroulé complet
# ----------------------------------------------------------------------------
class TestFilmsDeBoutEnBout(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        self.dune = self.racine / "Dune (2021)"
        self.dune.mkdir()
        (self.dune / "film.mkv").write_text("x", encoding="utf-8")

    def films(self, tmdb=None, *options, **patches):
        patches.setdefault("mkv.read_light_all", lambda paths: {})
        return self.lancer(films, tmdb or FauxTmdb(), *options, **patches)

    def test_dossier_sans_film(self):
        (self.dune / "film.mkv").unlink()
        self.dune.rmdir()
        code, texte = self.films(None, "--no-tag")
        self.assertIn("Aucun .mkv trouvé", texte)
        self.assertEqual(code, None)

    def test_tmdb_id_ignore_quand_plusieurs_films(self):
        autre = self.racine / "Blade (1998)"
        autre.mkdir()
        (autre / "film.mkv").write_text("x", encoding="utf-8")
        _, texte = self.films(None, "--no-tag", "--tmdb-id", "5")
        self.assertIn("--tmdb-id ne s'applique qu'à un seul film ; 2 détectés", texte)

    def test_tmdb_id_force_la_fiche_d_un_film_seul(self):
        _, texte = self.films(None, "--no-tag", "--tmdb-id", "5")
        self.assertNotIn("--tmdb-id ne s'applique", texte)
        self.assertIn("TOTAL : 1/1", texte)

    def test_artwork_sans_effet_quand_aucun_dossier_n_a_un_seul_film(self):
        (self.dune / "film.mkv").rename(self.racine / "Dune.mkv")
        self.dune.rmdir()
        _, texte = self.films(None, "--no-tag", "--artwork")
        self.assertIn("--artwork sans effet ici", texte)

    def test_no_tag_sans_annexe_ne_produit_rien(self):
        _, texte = self.films(None, "--no-tag")
        self.assertIn("--no-tag sans --artwork ne produit rien", texte)

    def test_titre_a_plusieurs_versions_attend_la_fin_du_passage(self):
        class Quatre(FauxTmdb):
            def search_movie(self, title, year=None):
                return [{"id": 22059, "title": "Les Quatre Fantastiques", "release_date": "1994-01-01"}, {"id": 9738, "title": "Les 4 Fantastiques", "release_date": "2005-07-06"}]

        for nom in ("Les Quatre Fantastiques", "Blade"):         # un film seul n'est jamais soumis à la question
            (self.racine / nom).mkdir()
            (self.racine / nom / "film.mkv").write_text("x", encoding="utf-8")
        code, texte = self.films(Quatre(), "--no-tag", **{"cli.can_ask": lambda: False})
        self.assertEqual(code, 1)
        self.assertIn("[À CONFIRMER] plusieurs versions portent ce titre", texte)
        self.assertIn("[À CONFIRMER]", (self.racine / "metadata.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
