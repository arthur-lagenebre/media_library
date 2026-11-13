"""Video/Movies/Metadata.py : le traitement d'un fichier, les sagas qui replacent un film, la fiche et le déroulé complet.

TMDB et les outils MKVToolNix sont simulés : on regarde ce que le script décide d'écrire et ce qu'il en dit.
"""

import io
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.video import lookup, mkv, movietags, naming, passfiles, resolve
from libraries.video.tmdb import TmdbError
from scripts.Video.Movies import Metadata as films
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
        xml = movietags.movie_target(DUNE, OPTS).tags_xml
        self.assertEqual(xml.count("Un désert."), 2)

    def test_sans_synopsis(self):
        xml = movietags.movie_target(dict(DUNE, overview=""), OPTS).tags_xml
        self.assertNotIn("SYNOPSIS", xml)

    def test_apostrophes_et_guillemets_courbes_ecrits_droits(self):
        courbe, ouvrant, fermant = chr(0x2019), chr(0x201C), chr(0x201D)
        film = dict(DUNE, title=f"L{courbe}Empire contre-attaque", overview=f"Un {ouvrant}désert{fermant} d{courbe}épices.",
                    belongs_to_collection={"name": f"La saga d{courbe}Étoiles - Saga"}, credits={"cast": [{"name": "A. Acteur", "character": f"L{courbe}Oracle"}], "crew": []})
        cible = movietags.movie_target(film, OPTS)
        self.assertEqual(cible.title, "L'Empire contre-attaque")
        self.assertIn('Un "désert" d\'épices.', cible.tags_xml)
        self.assertIn("A. Acteur (L'Oracle)", cible.tags_xml)
        self.assertIn("La saga d'Étoiles", cible.tags_xml)
        for courbe_ecrite in (courbe, ouvrant, fermant):
            self.assertNotIn(courbe_ecrite, cible.tags_xml)

    def test_identifiant_inscrit_dans_le_film(self):
        self.assertIn("movie/438631", movietags.movie_target(DUNE, OPTS).tags_xml)


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


class TestTitreSeul(unittest.TestCase):
    """--title-only : le titre du conteneur et les tags TITLE, rien d'autre ; un fichier jamais étiqueté est signalé, pas à moitié étiqueté."""

    FILM = dict(DUNE, title="28 ans plus tard")
    INFO = {"container": {"properties": {"title": "28 Ans plus tard"}}, "tracks": INFO["tracks"]}
    TAGS = {(50, "TITLE", "28 Ans plus tard"), (50, "SYNOPSIS", "Un désert."), (70, "TITLE", "28 jours")}
    XML = ('<?xml version="1.0"?><Tags>'
           '<Tag><Targets><TargetTypeValue>70</TargetTypeValue></Targets><Simple><Name>TITLE</Name><String>28 jours</String></Simple></Tag>'
           '<Tag><Targets/><Simple><Name>TITLE</Name><String>28 Ans plus tard</String></Simple>'
           '<Simple><Name>SYNOPSIS</Name><String>Un désert.</String></Simple></Tag></Tags>')

    def traiter(self, movie=None, tags=None, info=None, ecriture=(0, ""), xml=None, **options):
        self.appels = []
        args = arguments(title_only=True, **options)

        def write_titles(path, title, tags_xml):
            self.appels.append((Path(path).name, title, tags_xml))
            return ecriture

        lecture = mkv.Reading(info=info or self.INFO, tags=self.TAGS if tags is None else tags)
        sortie = io.StringIO()
        with mock.patch.object(films.mkv, "read_tags_xml", lambda path: self.XML if xml is None else xml), \
                mock.patch.object(films.mkv, "write_titles", write_titles), \
                mock.patch.object(films.mkv, "write", side_effect=AssertionError("--title-only ne doit rien écrire d'autre")), redirect_stdout(sortie):
            resultat = films.process_file(Path("28.mkv"), lecture, movie or self.FILM, args, OPTS, None)
        self.sortie = sortie.getvalue()
        return resultat

    def test_simulation_montre_ce_qui_changerait_sans_ecrire(self):
        self.assertEqual(self.traiter(), (0, 0))
        self.assertEqual(self.appels, [])
        self.assertIn("titre du conteneur : '28 Ans plus tard' -> '28 ans plus tard'", self.sortie)
        self.assertIn("tag TITLE du film : '28 Ans plus tard' -> '28 ans plus tard'", self.sortie)
        self.assertNotIn("audio", self.sortie)
        self.assertNotIn("date ->", self.sortie)

    def test_application_ne_change_que_les_titres(self):
        self.assertEqual(self.traiter(apply=True), (0, 0))
        nom, titre, xml = self.appels[0]
        self.assertEqual((nom, titre), ("28.mkv", "28 ans plus tard"))
        self.assertIn("<String>28 ans plus tard</String>", xml)
        self.assertIn("<String>Un désert.</String>", xml)
        self.assertNotIn("28 Ans plus tard", xml)
        self.assertIn("[OK]", self.sortie)

    def test_titre_du_conteneur_seul_ne_reecrit_pas_les_tags(self):
        tags = {(50, "TITLE", "28 ans plus tard"), (50, "SYNOPSIS", "Un désert.")}
        xml = self.XML.replace("28 Ans plus tard", "28 ans plus tard")
        self.assertEqual(self.traiter(tags=tags, xml=xml, apply=True), (0, 0))
        self.assertEqual(self.appels, [("28.mkv", "28 ans plus tard", "")])

    def test_tags_seuls_en_ecart(self):
        info = {"container": {"properties": {"title": "28 ans plus tard"}}, "tracks": INFO["tracks"]}
        self.traiter(info=info, apply=True)
        self.assertEqual(self.appels[0][1], "28 ans plus tard")
        self.assertIn("<String>28 ans plus tard</String>", self.appels[0][2])
        self.assertNotIn("titre du conteneur", self.sortie)

    def test_deja_conforme_ne_touche_a_rien(self):
        info = {"container": {"properties": {"title": "28 ans plus tard"}}, "tracks": INFO["tracks"]}
        tags = {(50, "TITLE", "28 ans plus tard")}
        self.assertEqual(self.traiter(info=info, tags=tags, apply=True), (0, 0))
        self.assertEqual(self.appels, [])
        self.assertIn("[OK] titres déjà conformes", self.sortie)

    def test_la_collection_suit_quand_son_tag_existe(self):
        film = dict(self.FILM, _collection_title="28 jours plus tard")
        self.traiter(movie=film, apply=True)
        xml = self.appels[0][2]
        self.assertIn("<String>28 jours plus tard</String>", xml)
        self.assertNotIn("<String>28 jours</String>", xml)
        self.assertIn("tag TITLE de la collection : '28 jours' -> '28 jours plus tard'", self.sortie)

    def test_pas_de_tag_de_collection_dans_le_fichier_n_en_cree_pas(self):
        film = dict(self.FILM, _collection_title="28 jours plus tard")
        tags = {(50, "TITLE", "28 Ans plus tard")}
        self.traiter(movie=film, tags=tags)
        self.assertNotIn("collection", self.sortie)

    def test_verify_liste_les_ecarts_sans_ecrire(self):
        self.assertEqual(self.traiter(verify=True, apply=True), (1, 0))
        self.assertEqual(self.appels, [])
        self.assertIn("[DIFF] titre du conteneur : actuel = '28 Ans plus tard'", self.sortie)

    def test_fichier_jamais_etiquete_est_signale_pas_etiquete(self):
        self.assertEqual(self.traiter(tags=set(), apply=True), (1, 0))
        self.assertEqual(self.appels, [])
        self.assertIn("[SANS TAGS] pas encore étiqueté", self.sortie)

    def test_tags_non_relus_sont_signales_de_la_meme_facon(self):
        lecture = mkv.Reading(info=self.INFO, tags=None)
        with redirect_stdout(io.StringIO()) as sortie:
            resultat = films.process_file(Path("28.mkv"), lecture, self.FILM, arguments(title_only=True, apply=True), OPTS, None)
        self.assertEqual(resultat, (1, 0))
        self.assertIn("[SANS TAGS]", sortie.getvalue())

    def test_echec_d_ecriture(self):
        self.assertEqual(self.traiter(apply=True, ecriture=(2, "Erreur : verrouillé")), (0, 1))
        self.assertIn("[ÉCHEC] Erreur : verrouillé", self.sortie)

    def test_tags_illisibles_ne_modifient_rien(self):
        self.assertEqual(self.traiter(apply=True, xml="pas du xml"), (0, 1))
        self.assertEqual(self.appels, [])
        self.assertIn("[ÉCHEC] tags illisibles", self.sortie)


@unittest.skipUnless(all(shutil.which(tool) for tool in ("ffmpeg", "mkvmerge", "mkvpropedit", "mkvextract")), "MKVToolNix ou ffmpeg absent : les vrais outils ne sont pas testés")
class TestTitreSeulAvecLesVraisOutils(ProgrammeTestCase):
    """Un vrai .mkv étiqueté par une passe complète, puis retitré : tout le reste doit rester octet pour octet."""

    def setUp(self):
        super().setUp()
        self.film = self.racine / "28 ans plus tard.mkv"
        source = self.racine / "source.mkv"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=64x48:rate=5", "-f", "lavfi", "-i", "sine=duration=1",
                        "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(source)], check=True)
        shutil.move(str(source), str(self.film))
        self.movie = {"id": 1100988, "title": "28 Ans plus tard", "overview": "Un virus & des îles.", "release_date": "2025-06-18",
                      "credits": {"cast": [{"name": "Ralph Fiennes", "character": "Dr. Kelson"}], "crew": []}, "genres": [{"name": "Horreur"}],
                      "belongs_to_collection": {"name": "28 - Saga"}, "_collection_title": "28… plus tard"}
        self.opts = mkv.Options(cover=False, date=True, audio_names=True, sub_names=True, flags=True, stats=True)
        info, _ = mkv.identify(self.film)
        code, message = mkv.write(self.film, info, movietags.movie_target(self.movie, self.opts), self.opts, None)
        self.assertEqual(code, 0, message)

    def etat(self):
        lecture = mkv.inspect(self.film, with_probe=False, with_tags=True)
        brut = mkv.read_tags_xml(self.film)
        # Le contenu des blocs de piste (statistiques) : la langue "und" que mkvpropedit y ajoute à la réécriture est la valeur par défaut de Matroska, pas une différence.
        blocs_de_piste = sorted((b.findtext("Targets/TrackUID"), tuple((x.findtext("Name"), x.findtext("String")) for x in b.findall("Simple")))
                                for b in ElementTree.fromstring(brut.lstrip(chr(0xFEFF))).findall("Tag") if b.find("Targets/TrackUID") is not None)
        proprietes = lecture.info["container"]["properties"]
        pistes = [(t["id"], t["type"], t["properties"].get("track_name"), t["properties"].get("default_track")) for t in lecture.info["tracks"]]
        return lecture, blocs_de_piste, proprietes, pistes

    def retitrer(self, **options):
        lecture, *_ = self.etat()
        film = dict(self.movie, title="28 ans plus tard", _collection_title="28 jours plus tard")
        with redirect_stdout(io.StringIO()) as sortie:
            return films.process_file(self.film, lecture, film, arguments(title_only=True, **options), self.opts, None), sortie.getvalue()

    def test_seuls_les_titres_changent(self):
        avant, pistes_avant, proprietes_avant, pistes_avant_liste = self.etat()
        self.assertIn((50, "TITLE", "28 Ans plus tard"), avant.tags)
        resultat, sortie = self.retitrer(apply=True)
        self.assertEqual(resultat, (0, 0), sortie)
        apres, pistes_apres, proprietes_apres, pistes_apres_liste = self.etat()
        self.assertEqual(proprietes_apres["title"], "28 ans plus tard")
        self.assertEqual(avant.tags - apres.tags, {(50, "TITLE", "28 Ans plus tard"), (70, "TITLE", "28… plus tard")})
        self.assertEqual(apres.tags - avant.tags, {(50, "TITLE", "28 ans plus tard"), (70, "TITLE", "28 jours plus tard")})
        self.assertEqual(pistes_apres, pistes_avant)                           # les statistiques de pistes sont intactes
        self.assertTrue(pistes_apres)
        self.assertEqual(pistes_apres_liste, pistes_avant_liste)               # noms de pistes et drapeaux aussi
        self.assertEqual({k: v for k, v in proprietes_apres.items() if k != "title"}, {k: v for k, v in proprietes_avant.items() if k != "title"})   # date comprise

    def test_un_second_passage_ne_change_plus_rien(self):
        self.retitrer(apply=True)
        avant = self.film.read_bytes()
        resultat, sortie = self.retitrer(apply=True)
        self.assertEqual(resultat, (0, 0))
        self.assertIn("[OK] titres déjà conformes", sortie)
        self.assertEqual(self.film.read_bytes(), avant)

    def test_simulation_et_verify_n_ecrivent_rien(self):
        avant = self.film.read_bytes()
        _, sortie = self.retitrer()
        self.assertIn("-> '28 ans plus tard'", sortie)
        resultat, sortie = self.retitrer(verify=True)
        self.assertEqual(resultat, (1, 0))
        self.assertIn("[DIFF] titre du conteneur", sortie)
        self.assertEqual(self.film.read_bytes(), avant)


class TestOptionTitleOnly(unittest.TestCase):
    def analyser(self, *argv):
        with mock.patch.object(sys, "argv", ["Metadata.py", "--dir", "x", *argv]):
            return films.parse_args()

    def test_absente_par_defaut(self):
        self.assertFalse(self.analyser().title_only)

    def test_activee(self):
        self.assertTrue(self.analyser("--title-only").title_only)

    def test_incompatible_avec_no_tag(self):
        with mock.patch.object(sys, "stderr", io.StringIO()) as erreur, self.assertRaises(SystemExit) as sortie:
            self.analyser("--title-only", "--no-tag")
        self.assertEqual(sortie.exception.code, 2)
        self.assertIn("se contredisent", erreur.getvalue())


class TestOptionCreditsOnly(unittest.TestCase):
    def analyser(self, *argv):
        with mock.patch.object(sys, "argv", ["Metadata.py", "--dir", "x", *argv]):
            return films.parse_args()

    def test_absente_par_defaut_puis_activee(self):
        self.assertFalse(self.analyser().credits_only)
        self.assertTrue(self.analyser("--credits-only").credits_only)

    def test_incompatible_avec_no_tag_et_title_only(self):
        for autre in ("--no-tag", "--title-only"):
            with mock.patch.object(sys, "stderr", io.StringIO()), self.assertRaises(SystemExit) as sortie:
                self.analyser("--credits-only", autre)
            self.assertEqual(sortie.exception.code, 2, autre)

    def test_le_traitement_d_un_fichier_ne_fait_que_le_casting(self):
        tags = {(50, "TITLE", "Dune")}
        with mock.patch.object(films.credits, "process", return_value=(1, 0)) as process, \
                mock.patch.object(films.mkv, "write", side_effect=AssertionError("--credits-only ne doit rien écrire d'autre")), \
                mock.patch.object(films.mkv, "write_titles", side_effect=AssertionError("--credits-only ne touche pas au titre")):
            resultat = films.process_file(Path("dune.mkv"), mkv.Reading(info=INFO, tags=tags), DUNE, arguments(credits_only=True, verify=True), OPTS, None)
        self.assertEqual(resultat, (1, 0))
        chemin, tags_lus, cible, verify, apply = process.call_args[0]
        self.assertEqual((chemin, tags_lus, verify, apply), (Path("dune.mkv"), tags, True, False))
        self.assertIn("Dune", cible.tags_xml)


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
            return resolve.movie_details(1, None, arguments(**changes), self.Tmdb(date))

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
            self.assertEqual(resolve.movie_details(1, 2, arguments(), self.Tmdb(None))["_order"], 2)


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
        racine = racine or self.racine
        with redirect_stdout(io.StringIO()) as sortie:
            passfiles.write_log(racine, self.library.journal, arguments(log=str(racine / "metadata.log")), films.Report(matched=1, total=2))
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

    def test_log_recoit_le_journal_et_ses_voisins_a_cote(self):
        sortie = self.racine / "sortie" / "logs"
        args = arguments(log=str(sortie / "films.log"))
        with redirect_stdout(io.StringIO()):
            passfiles.write_log(self.racine, self.library.journal, args, films.Report(matched=1, total=2))
        self.assertTrue((sortie / "films.log").exists())
        self.assertFalse((self.racine / "metadata.log").exists())
        self.assertEqual(passfiles.approved_path(self.racine, args), sortie / "metadata.ok")
        self.assertEqual(passfiles.collections_path(self.racine, args), sortie / "metadata.collections")
        self.assertEqual(passfiles.titles_path(self.racine, args), sortie / "metadata.titles")

    def test_sans_log_ni_journal_et_les_voisins_a_la_racine(self):
        args = arguments()
        with redirect_stdout(io.StringIO()) as sortie:
            passfiles.write_log(self.racine, self.library.journal, args, films.Report(matched=1, total=2))
        self.assertEqual(list(self.racine.iterdir()), [])
        self.assertEqual(sortie.getvalue(), "")
        self.assertEqual(passfiles.approved_path(self.racine, args), self.racine / "metadata.ok")
        self.assertEqual(passfiles.titles_path(self.racine, args), self.racine / "metadata.titles")

    def test_reponse_de_collection_creee_dans_le_dossier_du_journal(self):
        fichier = self.racine / "sortie" / "metadata.collections"
        with redirect_stdout(io.StringIO()):
            passfiles.remember_collection(fichier, "Iron Man Collection", "Iron Man")
        self.assertEqual(passfiles.read_collections(fichier), {"Iron Man Collection": "Iron Man"})

    def test_journal_impossible_a_ecrire_n_arrete_pas_le_script(self):
        (self.racine / "fichier").write_text("x", encoding="utf-8")       # un fichier là où il faudrait un dossier
        self.assertIn("metadata.log non écrit", self.ecrire(self.racine / "fichier"))



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
        return resolve.saga_candidates(dossier or self.dossier, list(vues), tmdb)

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
            return resolve.saga_corrections(movies, lectures or {}, arguments(), tmdb), movies

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
        code, texte = self.films(Quatre(), "--no-tag", "--log", str(self.racine / "metadata.log"), **{"cli.can_ask": lambda: False})
        self.assertEqual(code, 1)
        self.assertIn("[À CONFIRMER] plusieurs versions portent ce titre", texte)
        self.assertIn("[À CONFIRMER]", (self.racine / "metadata.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
