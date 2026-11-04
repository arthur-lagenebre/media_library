"""Étiquetage : plan d'une saison, tags produits, choix du film sur TMDB."""

import io
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.video import cast, doubts, episodetags, lookup, mkv, movietags, naming, passfiles, resolve
from libraries.video.tmdb import TmdbError
from libraries.common.report import Report
from scripts.Movies import Metadata as films
from scripts.TV_Shows import Metadata as series

OPTS = mkv.Options(cover=False, date=True, audio_names=True, sub_names=True, flags=True, stats=True, image_size="w780")
SAISON = {"season_number": 1, "name": "Saison 1", "poster_path": "/p.jpg", "episodes": [ {"episode_number": 1, "name": "Pilote", "overview": "Debut", "air_date": "2024-01-02", "crew": [{"name": "R. Real", "job": "Director", "department": "Directing"}], "guest_stars": [{"name": "A. Acteur", "character": "Lui-meme"}], "vote_average": 7.84, "vote_count": 12, "still_path": "/s1.jpg"}, {"episode_number": 2, "name": "Suite", "air_date": "2024-01-09"} ]}


class TestPlanDeSaison(unittest.TestCase):
    def setUp(self):
        self.args = types.SimpleNamespace(probe=False, verify=False, apply=False, skip_done=False, match_threshold=0.55, series_name="Ma Serie")

    def process(self, dossier):
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            resultat = series.process_season(dossier, SAISON, self.args, OPTS, None)
        return resultat, sortie.getvalue()

    def test_dossier_sans_mkv(self):
        # Régression : le retour à 2 valeurs contre 3 attendues faisait planter main().
        with tempfile.TemporaryDirectory() as d:
            resultat, sortie = self.process(Path(d))
        self.assertEqual(resultat, Report())
        self.assertIn("Aucun .mkv", sortie)

    def test_fichier_illisible_reste_non_bloquant(self):
        # mkvmerge refusera ce faux .mkv : le script doit le dire et continuer.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "01 - x.mkv").write_text("pas un vrai mkv", encoding="utf-8")
            report, sortie = self.process(Path(d))
        self.assertEqual((report.matched, report.total), (1, 1))
        self.assertIn("[S01E01]", sortie)


class TestTagsEpisode(unittest.TestCase):
    def setUp(self):
        xml = episodetags.build_tags_xml(SAISON, SAISON["episodes"][0], "Ma Serie")
        self.root = ElementTree.fromstring(xml)

    def valeur(self, cible, nom):
        """Texte du tag `nom` au niveau `cible` (ElementTree ne sait pas filtrer sur un prédicat imbriqué : on retrouve le bloc à la main)."""
        for tag in self.root.findall("Tag"):
            niveau = tag.find("Targets/TargetTypeValue")
            if niveau is not None and niveau.text == str(cible):
                node = tag.find(f"Simple[Name='{nom}']/String")
                if node is not None:
                    return node.text
        return None

    def test_trois_niveaux_de_cible(self):
        niveaux = [n.text for n in self.root.findall("./Tag/Targets/TargetTypeValue")]
        self.assertEqual(niveaux, ["70", "60", "50"])

    def test_niveau_serie_et_saison(self):
        self.assertEqual(self.valeur(70, "TITLE"), "Ma Serie")
        self.assertEqual(self.valeur(60, "TOTAL_PARTS"), "2")

    def test_niveau_episode(self):
        self.assertEqual(self.valeur(50, "TITLE"), "Pilote")
        self.assertEqual(self.valeur(50, "DATE_RELEASED"), "2024-01-02")
        self.assertEqual(self.valeur(50, "DIRECTOR"), "R. Real")
        self.assertEqual(self.valeur(50, "ACTOR"), "A. Acteur (Lui-meme)")
        self.assertEqual(self.valeur(50, "COMMENT"), "TMDB 7.8/10 (12 votes)")

    def test_cible_de_l_episode(self):
        target = episodetags.episode_target(SAISON, SAISON["episodes"][0], "Ma Serie", OPTS)
        self.assertEqual((target.title, target.date), ("Pilote", "2024-01-02"))
        self.assertIsNone(target.poster)                  # opts.cover est False

    def test_apostrophes_et_guillemets_courbes_ecrits_droits(self):
        courbe, ouvrant, fermant = chr(0x2019), chr(0x201C), chr(0x201D)
        episode = dict(SAISON["episodes"][0], name=f"L{courbe}arrivée", overview=f"{ouvrant}Debut{fermant} d{courbe}une série")
        saison = dict(SAISON, name=f"L{courbe}an un", episodes=[episode])
        root = ElementTree.fromstring(episodetags.build_tags_xml(saison, episode, f"Les {ouvrant}Experts{fermant} d{courbe}ici"))
        valeurs = [s.text for s in root.findall(".//Simple/String")]
        for attendu in ("Les \"Experts\" d'ici", "L'an un", "L'arrivée", "\"Debut\" d'une série"):
            self.assertIn(attendu, valeurs)
        self.assertFalse([v for v in valeurs if any(c in v for c in (courbe, ouvrant, fermant))])
        self.assertEqual(episodetags.episode_target(saison, episode, "S", OPTS).title, "L'arrivée")

    def test_jaquette_repliee_sur_l_affiche_de_saison(self):
        opts = mkv.Options(cover=True, date=True, audio_names=True, sub_names=True, flags=True, stats=True, image_size="w780")
        sans_vignette = episodetags.episode_target(SAISON, SAISON["episodes"][1], "Ma Serie", opts)
        self.assertEqual(sans_vignette.poster, "/p.jpg")


class TestFilms(unittest.TestCase):
    def test_tags_de_saga(self):
        movie = {"title": "Iron Man", "release_date": "2008-04-30", "_order": 1, "belongs_to_collection": {"name": "Iron Man - Saga"}, "genres": [{"name": "Action"}, {"name": "Science-Fiction"}], "credits": {"crew": [{"name": "J. Favreau", "job": "Director"}], "cast": [{"name": "R. Downey Jr.", "character": "Tony Stark"}]}}
        root = ElementTree.fromstring(movietags.build_movie_tags_xml(movie))
        niveaux = [n.text for n in root.findall("./Tag/Targets/TargetTypeValue")]
        self.assertEqual(niveaux, ["70", "50"])
        saga = root.find("Tag")
        self.assertEqual(saga.find("Simple[Name='TITLE']/String").text, "Iron Man")
        self.assertEqual(saga.find("Simple[Name='PART_NUMBER']/String").text, "1")
        film = root.findall("Tag")[1]
        self.assertEqual(film.find("Simple[Name='GENRE']/String").text, "Action, Science-Fiction")

    def test_le_suffixe_saga_n_est_pas_inscrit(self):
        self.assertEqual(movietags.collection_title("Iron Man - Saga"), "Iron Man")
        self.assertEqual(movietags.collection_title("Iron Man - saga"), "Iron Man")
        self.assertEqual(movietags.collection_title("Saga Twilight"), "Saga Twilight")
        self.assertEqual(movietags.collection_title(None), "")

    def test_collection_n_est_jamais_retire_d_office(self):
        self.assertEqual(movietags.collection_title("Iron Man Collection"), "Iron Man Collection")
        movie = {"title": "Iron Man", "belongs_to_collection": {"name": "Iron Man Collection"}}
        root = ElementTree.fromstring(movietags.build_movie_tags_xml(movie))
        self.assertEqual(root.find("Tag").find("Simple[Name='TITLE']/String").text, "Iron Man Collection")

    def test_proposition_sans_collection(self):
        self.assertEqual(movietags.collection_proposal("Iron Man Collection"), "Iron Man")
        self.assertEqual(movietags.collection_proposal("Iron Man - Collection"), "Iron Man")
        self.assertEqual(movietags.collection_proposal("Iron Man Collection - Saga"), "Iron Man")
        self.assertIsNone(movietags.collection_proposal("Iron Man - Saga"))
        self.assertIsNone(movietags.collection_proposal("Collection"))
        self.assertIsNone(movietags.collection_proposal(None))

    def test_titre_arrete_inscrit_dans_la_collection(self):
        movie = {"title": "Iron Man", "belongs_to_collection": {"name": "Iron Man Collection"}, "_collection_title": "Iron Man"}
        root = ElementTree.fromstring(movietags.build_movie_tags_xml(movie))
        self.assertEqual(root.find("Tag").find("Simple[Name='TITLE']/String").text, "Iron Man")
        self.assertEqual(movietags.collection_title("Star Wars"), "Star Wars")

    def test_l_identifiant_est_inscrit_dans_le_film(self):
        # Pour que le passage suivant n ait plus rien à chercher.
        root = ElementTree.fromstring(movietags.build_movie_tags_xml({"id": 314, "title": "Catwoman"}))
        film = root.findall("Tag")[-1]
        self.assertEqual(film.find("Simple[Name='TMDB']/String").text, "movie/314")
    def test_film_hors_saga(self):
        movie = {"title": "Heat", "credits": {}}
        root = ElementTree.fromstring(movietags.build_movie_tags_xml(movie))
        self.assertEqual([n.text for n in root.findall("./Tag/Targets/TargetTypeValue")], ["50"])


class TestChoixDeCollection(unittest.TestCase):
    def test_nom_tmdb_sans_saga_sans_collection_et_dossier(self):
        self.assertEqual(movietags.collection_choices("Iron Man Collection", "Marvel"),
                         ([("Iron Man Collection", "TMDB"), ("Iron Man", "sans \" Collection\""), ("Marvel", "nom de ton dossier de saga")], 1))

    def test_rien_a_choisir(self):
        self.assertEqual(movietags.collection_choices("Iron Man - Saga"), ([("Iron Man", "TMDB")], 0))
        self.assertEqual(movietags.collection_choices("Iron Man - Saga", "Iron Man"), ([("Iron Man", "TMDB")], 0))
        self.assertEqual(movietags.collection_choices("Iron Man - Saga", "   "), ([("Iron Man", "TMDB")], 0))

    def test_le_dossier_est_propose_quand_il_differe_meme_d_une_casse(self):
        choix, defaut = movietags.collection_choices("28 jours plus tard - Saga", "28 Jours plus tard")
        self.assertEqual(([t for t, _ in choix], defaut), (["28 jours plus tard", "28 Jours plus tard"], 0))

    def test_le_defaut_est_la_proposition_sans_collection(self):
        self.assertEqual(movietags.collection_choices("The Criterion Collection")[1], 1)


class TestValidationDuTitreDeCollection(unittest.TestCase):
    """" - Saga" part d'office ; le reste se choisit - le nom TMDB, sans " Collection", le dossier de saga, un titre tapé -, une fois par collection."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.fichier = Path(self._tmp.name) / "metadata.collections"

    def regler(self, nom="Iron Man Collection", reponses=(), peut_demander=True, library=None, dossier="", texte=(), **changes):
        """(titre inscrit, nombre de questions, library, affichage). `reponses` : les indices choisis ; `texte` : ce qui est tapé pour "autre"."""
        args = types.SimpleNamespace(verify=False, no_tag=False, no_ask=False)
        for cle, valeur in changes.items():
            setattr(args, cle, valeur)
        library = library or films.Library([], {}, {}, titles_file=self.fichier)
        movie = {"title": "Iron Man", "belongs_to_collection": {"name": nom}}
        entree = naming.MovieFolder(folder=Path("saga"), files=[Path("saga/1 - Iron Man.mkv")], rawname="1 - Iron Man", contexts=[dossier] if dossier else [])
        with mock.patch.object(films.cli, "can_ask", lambda: peut_demander), mock.patch.object(films.cli, "ask_choice", side_effect=list(reponses)) as question,                 mock.patch.object(films.cli, "ask_text", side_effect=list(texte)), redirect_stdout(io.StringIO()) as sortie:
            films.settle_collection(movie, library, args, entree)
        return movie.get("_collection_title"), question.call_count, library, sortie.getvalue()

    def test_oui_retire_collection_et_le_memorise(self):
        titre, questions, library, _ = self.regler(reponses=[1])
        self.assertEqual((titre, questions), ("Iron Man", 1))
        self.assertIn("Iron Man Collection => Iron Man", self.fichier.read_text(encoding="utf-8"))
        self.assertEqual(library.titles, {"Iron Man Collection": "Iron Man"})

    def test_non_garde_le_nom_et_le_memorise(self):
        titre, _, _, _ = self.regler(reponses=[0])
        self.assertEqual(titre, "Iron Man Collection")
        self.assertIn("Iron Man Collection => Iron Man Collection", self.fichier.read_text(encoding="utf-8"))

    def test_la_reponse_vaut_pour_toute_la_collection(self):
        _, _, library, _ = self.regler(reponses=[1])
        titre, questions, _, _ = self.regler(library=library)
        self.assertEqual((titre, questions), ("Iron Man", 0))

    def test_une_reponse_deja_consignee_n_est_pas_redemandee(self):
        self.fichier.write_text("# commentaire\nIron Man Collection => Iron Man (MCU)\n", encoding="utf-8")
        library = films.Library([], {}, {}, titles=passfiles.read_collections(self.fichier), titles_file=self.fichier)
        titre, questions, _, _ = self.regler(library=library)
        self.assertEqual((titre, questions), ("Iron Man (MCU)", 0))

    def test_saga_ne_demande_rien(self):
        titre, questions, _, _ = self.regler(nom="Iron Man - Saga")
        self.assertEqual((titre, questions), (None, 0))
        self.assertFalse(self.fichier.exists())

    def test_sans_terminal_le_nom_est_garde_sans_rien_ecrire(self):
        titre, questions, _, sortie = self.regler(peut_demander=False)
        self.assertEqual((titre, questions), (None, 0))
        self.assertIn("gardé tel quel", sortie)
        self.assertFalse(self.fichier.exists())

    def test_no_ask_verify_et_no_tag_ne_demandent_rien(self):
        for option in ("no_ask", "verify", "no_tag"):
            titre, questions, _, _ = self.regler(**{option: True})
            self.assertEqual((titre, questions), (None, 0), option)

    def test_entree_fermee_cesse_de_demander(self):
        titre, _, library, _ = self.regler(reponses=[films.cli.ASK_STOP])
        self.assertIsNone(titre)
        self.assertFalse(library.asking)
        _, questions, _, _ = self.regler(library=library)
        self.assertEqual(questions, 0)
        self.assertFalse(self.fichier.exists())

    def test_le_dossier_de_saga_est_propose(self):
        # "Iron Man Collection" (TMDB), "Iron Man" (sans Collection), "Marvel" (ton dossier) : trois propositions, la 3e choisie.
        titre, questions, library, sortie = self.regler(reponses=[2], dossier="Marvel")
        self.assertEqual((titre, questions), ("Marvel", 1))
        self.assertEqual(library.titles, {"Iron Man Collection": "Marvel"})
        self.assertIn("2) Iron Man   (sans \" Collection\")   (défaut)", sortie)
        self.assertIn("3) Marvel   (nom de ton dossier de saga)", sortie)
        self.assertIn("4) autre : je tape le titre", sortie)

    def test_un_dossier_de_saga_different_ouvre_le_choix_meme_sans_collection(self):
        # "28 - Saga" -> "28" ; le dossier dit "28 jours plus tard" : deux propositions, donc une question, que "28 - Saga" seul n'aurait pas posée.
        titre, questions, _, sortie = self.regler(nom="28 - Saga", reponses=[1], dossier="28 jours plus tard")
        self.assertEqual((titre, questions), ("28 jours plus tard", 1))
        self.assertIn("1) 28   (TMDB)   (défaut)", sortie)

    def test_un_dossier_de_saga_identique_ne_demande_rien(self):
        titre, questions, _, _ = self.regler(nom="Iron Man - Saga", dossier="Iron Man")
        self.assertEqual((titre, questions), (None, 0))
        self.assertFalse(self.fichier.exists())

    def test_t_prend_le_defaut_pour_cette_collection_et_les_suivantes(self):
        titre, questions, library, _ = self.regler(reponses=[films.cli.ASK_ALL])
        self.assertEqual((titre, questions), ("Iron Man", 1))                         # le défaut : sans " Collection"
        self.assertTrue(library.take_defaults)
        titre, questions, library, sortie = self.regler(nom="Thor Collection", library=library)
        self.assertEqual((titre, questions), ("Thor", 0))
        self.assertIn("'Thor Collection' -> 'Thor' (défaut)", sortie)
        self.assertEqual(library.titles, {"Iron Man Collection": "Iron Man", "Thor Collection": "Thor"})

    def test_un_titre_tape(self):
        titre, questions, library, _ = self.regler(reponses=[3], texte=["Marvel Studios"])
        self.assertEqual((titre, questions), ("Marvel Studios", 1))
        self.assertIn("Iron Man Collection => Marvel Studios", self.fichier.read_text(encoding="utf-8"))
        self.assertEqual(library.titles, {"Iron Man Collection": "Marvel Studios"})

    def test_rien_de_tape_laisse_la_question_sans_reponse(self):
        titre, _, library, _ = self.regler(reponses=[3], texte=[""])
        self.assertIsNone(titre)
        self.assertTrue(library.asking)
        self.assertFalse(self.fichier.exists())

    def test_entree_fermee_pendant_la_saisie_arrete_les_questions(self):
        titre, _, library, _ = self.regler(reponses=[3], texte=[None])
        self.assertIsNone(titre)
        self.assertFalse(library.asking)

    def test_ignorer_ne_memorise_rien(self):
        titre, questions, library, _ = self.regler(reponses=[films.cli.ASK_SKIP])
        self.assertEqual((titre, questions, library.titles), (None, 1, {}))
        self.assertFalse(self.fichier.exists())

    def test_une_collection_sans_suffixe_se_lit_aussi_dans_metadata_collections(self):
        # Avant, seuls les noms en " Collection" consultaient le fichier : une ligne écrite à la main pour "Alien - Saga" est maintenant suivie.
        library = films.Library([], {}, {}, titles={"Iron Man - Saga": "Les Avengers"}, titles_file=self.fichier)
        titre, questions, _, _ = self.regler(nom="Iron Man - Saga", library=library)
        self.assertEqual((titre, questions), ("Les Avengers", 0))

    def test_sans_terminal_le_choix_n_est_pas_demande_mais_dit(self):
        titre, questions, _, sortie = self.regler(peut_demander=False, dossier="Marvel", nom="Iron Man - Saga")
        self.assertEqual((titre, questions), (None, 0))
        self.assertIn("[COLLECTION] 'Iron Man' gardé tel quel", sortie)

    def test_fichier_absent_ou_illisible(self):
        self.assertEqual(passfiles.read_collections(self.fichier), {})


def sous_titre(langue, nom):
    """Piste de sous-titres minimale, telle que mkvmerge la décrit."""
    return {"type": "subtitles", "codec": "", "properties": {"language": langue, "track_name": nom}}

class TestFilmNonTraite(unittest.TestCase):
    """Une piste ambiguë arrête tout le film, et la raison est dite."""

    AMBIGU = {"tracks": [sous_titre("eng", "English"), sous_titre("eng", "English")]}
    SAIN = {"tracks": [sous_titre("fre", "Français forcé"), sous_titre("fre", "Français complet")]}

    def process(self, *infos):
        """Lance process_movie sur un film d un fichier par info donnée."""
        args = types.SimpleNamespace(verify=False, apply=False, skip_done=False)
        chemins = [Path(f"cd{i}.mkv") for i, _ in enumerate(infos, 1)]
        entry = naming.MovieFolder(folder=Path("."), files=chemins, rawname="Film")
        lectures = {p: mkv.Reading(info=info) for p, info in zip(chemins, infos)}
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            report = films.process_movie(entry, {"title": "Film"}, lectures, args, OPTS, None)
        return report, sortie.getvalue()

    def test_film_ambigu_laisse_intact(self):
        report, sortie = self.process(self.AMBIGU)
        self.assertEqual((report.matched, report.total, report.skipped), (1, 1, 1))
        self.assertIn("[NON TRAITÉ]", sortie)
        self.assertIn("st s1 et st s2 [en]", sortie)
        self.assertNotIn(" -> ", sortie)          # aucun renommage n a été préparé

    def test_film_sain_traite_normalement(self):
        report, sortie = self.process(self.SAIN)
        self.assertEqual(report.skipped, 0)
        self.assertIn("+Forced", sortie)

    def test_un_seul_fichier_ambigu_bloque_le_film_entier(self):
        # À moitié etiquete, le film aurait l air fait : le souci passerait à la trappe au passage suivant.
        report, sortie = self.process(self.SAIN, self.AMBIGU)
        self.assertEqual(report.skipped, 1)
        self.assertIn("cd2.mkv : st s1 et st s2", sortie)
        self.assertNotIn("+Forced", sortie)       # cd1.mkv non plus n a été préparé

    def test_le_bilan_le_compte_et_le_signale(self):
        report = Report(matched=1, total=1) + Report(matched=1, total=1, skipped=1)
        self.assertEqual((report.total, report.skipped), (2, 1))
        self.assertIn("1 non traité(s)", report.epilogue())
        self.assertEqual(report.exit_code, 1)

class FauxTmdbFilms:
    """Rend une fiche par id, et une recherche fixe. Note ce qui a été demandé."""

    def __init__(self, resultats=()):
        self.resultats = list(resultats)
        self.details, self.recherches = [], []

    def search_movie(self, title, year=None):
        self.recherches.append(title)
        return list(self.resultats)

    def movie(self, movie_id, language=None):
        self.details.append(int(movie_id))
        return {"id": int(movie_id), "title": f"Film {movie_id}"}

    def local_release_date(self, movie_id, region):
        return None


class TestQuestionsDeFinDePassage(unittest.TestCase):
    """Une association douteuse attend la fin du passage, et une réponse."""

    CANDIDATS = [{"id": 22059, "title": "Les Quatre Fantastiques", "release_date": "1994-01-01"}, {"id": 9738, "title": "Les 4 Fantastiques", "release_date": "2005-07-06"}]

    def setUp(self):
        self.args = types.SimpleNamespace(no_tag=True, artwork=False, apply=False, verify=False, skip_done=False, no_ask=False, language="fr-FR", no_date=True, tmdb_id=None)

    def attente(self, combien=1):
        sortie = []
        for i in range(combien):
            entry = naming.MovieFolder(folder=Path("."), files=[Path(f"f{i}.mkv")], rawname=f"Les Quatre Fantastiques {i}")
            sortie.append((entry, lookup.Doubt(query="Les Quatre Fantastiques", candidates=list(self.CANDIDATS))))
        return sortie

    def poser(self, reponses, combien=1, interactif=True):
        """Joue resolve_pending avec des réponses préfabriquées."""
        tmdb = FauxTmdbFilms()
        library = films.Library([], {}, {})
        restantes, demandes = list(reponses), []

        def faux_choix(nombre, defaut=0):
            demandes.append(nombre)
            return restantes.pop(0)

        sortie = io.StringIO()
        with mock.patch.object(films.cli, "can_ask", lambda: interactif):
            with mock.patch.object(films.cli, "ask_choice", faux_choix):
                with redirect_stdout(sortie):
                    report = films.resolve_pending(self.attente(combien), library, self.args, OPTS, tmdb)
        return report, sortie.getvalue(), tmdb, demandes

    def test_la_reponse_choisit_la_fiche(self):
        report, sortie, tmdb, _ = self.poser([1])
        self.assertEqual(tmdb.details, [9738])          # la 2e, pas la 1re
        self.assertEqual((report.matched, report.pending), (1, 0))
        self.assertIn("tmdbid-9738", sortie)            # comment ne plus la poser

    def test_entree_vide_garde_le_defaut(self):
        _, _, tmdb, _ = self.poser([0])
        self.assertEqual(tmdb.details, [22059])

    def test_ignorer_laisse_le_film_intact(self):
        report, sortie, tmdb, _ = self.poser([films.cli.ASK_SKIP])
        self.assertEqual(tmdb.details, [])
        self.assertEqual((report.matched, report.pending), (1, 1))
        self.assertIn("[NON TRAITÉ]", sortie)

    def test_fiche_inaccessible_apres_la_reponse_reste_a_corriger(self):
        # La réponse est donnée, mais TMDB ne rend pas la fiche choisie : le film n'est ni traité ni « à confirmer », il est sans fiche.
        class EnPanne(FauxTmdbFilms):
            def movie(self, movie_id, language=None):
                raise TmdbError("HTTP 503")

        library = films.Library([], {}, {})
        with mock.patch.object(films.cli, "can_ask", lambda: True), mock.patch.object(films.cli, "ask_choice", lambda nombre, defaut=0: 0), redirect_stdout(io.StringIO()) as sortie:
            report = films.resolve_pending(self.attente(), library, self.args, OPTS, EnPanne())
        self.assertEqual((report.total, report.unresolved, report.pending), (1, 1, 0))
        self.assertEqual(report.exit_code, 1)
        self.assertIn("échec détails TMDB", sortie.getvalue())

    def test_arreter_saute_toutes_les_suivantes(self):
        report, _, tmdb, demandes = self.poser([films.cli.ASK_STOP], combien=3)
        self.assertEqual(len(demandes), 1)              # une seule question posée
        self.assertEqual((report.pending, tmdb.details), (3, []))

    def test_terminal_non_interactif_ne_bloque_pas(self):
        # Sortie redirigée : la question ne serait vue par personne.
        report, sortie, tmdb, demandes = self.poser([], combien=2, interactif=False)
        self.assertEqual((demandes, tmdb.details), ([], []))
        self.assertEqual((report.total, report.pending), (2, 2))
        self.assertIn("non interactif", sortie)

    def resoudre(self):
        tmdb = FauxTmdbFilms(self.CANDIDATS)
        with redirect_stdout(io.StringIO()):
            movie, doute = resolve.resolve_movie("Les Quatre Fantastiques", self.args, tmdb, single=False)
        return movie, doute, tmdb

    def test_no_ask_garde_le_premier_resultat(self):
        # L échappatoire pour les scripts : le comportement d avant.
        self.args.no_ask = True
        movie, doute, _ = self.resoudre()
        self.assertIsNone(doute)
        self.assertEqual(movie["id"], 22059)

    def test_sans_no_ask_la_question_est_mise_de_cote(self):
        movie, doute, tmdb = self.resoudre()
        self.assertIsNone(movie)                        # pas encore charge
        self.assertEqual(tmdb.details, [])              # ni même interroge
        self.assertEqual([c["id"] for c in doute.candidates], [22059, 9738])

class TestIdentifiantLuDansLeFilm(unittest.TestCase):
    """Un identifiant inscrit dans le .mkv dispense de toute recherche."""

    def setUp(self):
        self.args = types.SimpleNamespace(no_ask=False, language="fr-FR", no_date=True, tmdb_id=None)

    def resoudre(self, rawname, tag_id):
        tmdb = FauxTmdbFilms([{"id": 999, "title": "Autre chose"}])
        with redirect_stdout(io.StringIO()) as sortie:
            movie, _ = resolve.resolve_movie(rawname, self.args, tmdb, single=False, tag_id=tag_id)
        return movie, tmdb, sortie.getvalue()

    def test_l_identifiant_du_fichier_evite_la_recherche(self):
        movie, tmdb, sortie = self.resoudre("zzz nom illisible", "314")
        self.assertEqual(movie["id"], 314)
        self.assertEqual(tmdb.recherches, [])          # rien n a été cherché
        self.assertIn("id lu dans le fichier", sortie)

    def test_le_nom_epingle_prime_sur_le_fichier(self):
        # Seul moyen de corriger un identifiant inscrit de travers.
        movie, tmdb, _ = self.resoudre("Un film [tmdbid-27205]", "314")
        self.assertEqual((movie["id"], tmdb.recherches), (27205, []))

    def test_sans_identifiant_la_recherche_reprend(self):
        movie, tmdb, _ = self.resoudre("Un film", None)
        self.assertEqual((movie["id"], tmdb.recherches), (999, ["Un film"]))









class FauxTmdb:
    """Renvoie des sagas préparées, et compte les appels."""

    def __init__(self, sagas, echecs=()):
        self.sagas = sagas
        self.echecs = set(echecs)
        self.appels = []

    def collection(self, ident, language=None):
        self.appels.append(ident)
        if ident in self.echecs:
            raise TmdbError("indisponible")
        return self.sagas[ident]


IRON = {"id": 1, "name": "Iron Man - Saga", "parts": [ {"id": 11, "title": "Iron Man", "release_date": "2008-04-30", "poster_path": "/a.jpg"}, {"id": 12, "title": "Iron Man 2", "release_date": "2010-04-28", "poster_path": "/b.jpg"}, {"id": 13, "title": "Iron Man 3", "release_date": "2013-04-24"} ]}


def film(ident, titre, saga=None, **extra):
    movie = {"id": ident, "title": titre, "release_date": "2008-04-30", "runtime": 126, "poster_path": "/a.jpg"}
    if saga:
        movie["belongs_to_collection"] = {"id": saga["id"], "name": saga["name"]}
    movie.update(extra)
    return movie




class TestDoutesSurLAssociation(unittest.TestCase):
    """Une association dont la durée ou la notoriété ne colle pas est signalée."""

    def doutes(self, minutes, runtime, votes=500, nom="Microcosmos", parts=1):
        fichiers = [Path(f"{nom}.cd{i}.mkv") for i in range(parts)]
        entry = types.SimpleNamespace(rawname=nom, files=fichiers)
        lu = mkv.Reading(info={"container": {"properties": {"duration": int(minutes / parts * 60e9)}}})
        return doubts.identity_doubts(entry, {"runtime": runtime, "vote_count": votes}, {f: lu for f in fichiers})

    def test_court_metrage_pris_pour_le_film(self):
        # Microcosmos (75 min) associé à un court métrage de 3 min qui porte le même nom.
        self.assertIn("durée 75 min, la fiche TMDB en annonce 3", self.doutes(75, 3)[0])

    def test_film_trop_court_pour_la_fiche(self):
        # Destruction finale (95 min) pris pour le film coréen du même nom (128 min).
        self.assertTrue(self.doutes(95, 128))

    def test_version_longue_toleree(self):
        # Kingdom of Heaven, version longue : 189 min pour 144 annoncées.
        self.assertEqual(self.doutes(189, 144), [])

    def test_acceleration_pal_toleree(self):
        self.assertEqual(self.doutes(96, 100), [])

    def test_parties_additionnees(self):
        self.assertEqual(self.doutes(150, 150, parts=2), [])

    def test_fiche_presque_inconnue(self):
        self.assertIn("fiche TMDB presque inconnue (0 vote(s))", self.doutes(75, 75, votes=0))

    def test_identifiant_epingle_jamais_remis_en_cause(self):
        self.assertEqual(self.doutes(189, 3, votes=0, nom="Kingdom of Heaven [tmdbid-1495]"), [])

    def test_sans_duree_lue_pas_de_doute(self):
        entry = types.SimpleNamespace(rawname="X", files=[Path("X.mkv")])
        self.assertEqual(doubts.identity_doubts(entry, {"runtime": 3, "vote_count": 500}, {}), [])




class TestFilmsValides(unittest.TestCase):
    def lire(self, texte):
        with tempfile.TemporaryDirectory() as d:
            fichier = Path(d) / "metadata.ok"
            fichier.write_text(texte, encoding="utf-8")
            return passfiles.read_approved(fichier)

    def test_identifiant_seul_ou_lien(self):
        self.assertEqual(self.lire("1437733\nhttps://www.themoviedb.org/movie/949\n"), {1437733, 949})

    def test_ligne_recopiee_du_journal(self):
        # Le nom peut porter un nombre ("2012") : c'est le lien qui compte.
        ligne = "2012 Une fin du monde   https://www.themoviedb.org/movie/14161  [A VERIFIER] fiche TMDB presque inconnue (6 vote(s))"
        self.assertEqual(self.lire(ligne), {14161})

    def test_commentaires_et_lignes_vides(self):
        self.assertEqual(self.lire("# valides\n\n1437733  # Bref. De bons amis, ok\n  # 99\ntexte sans identifiant\n"), {1437733})

    def test_fichier_absent_ne_valide_rien(self):
        self.assertEqual(passfiles.read_approved(Path("introuvable") / "metadata.ok"), set())






class TestCasseDuTitre(unittest.TestCase):
    """TMDB écrit "28 Ans plus tard", le fichier "28 ans plus tard" : la question est posée une fois, la réponse mémorisée."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.fichier = Path(self._tmp.name) / "metadata.titles"
        self.entree = naming.MovieFolder(folder=Path("saga"), files=[Path("saga/3 - 28 ans plus tard.mkv")], rawname="3 - 28 ans plus tard")

    def regler(self, titre="28 Ans plus tard", nom=None, reponses=(), peut_demander=True, library=None, **changes):
        args = types.SimpleNamespace(verify=False, no_tag=False, no_ask=False)
        for cle, valeur in changes.items():
            setattr(args, cle, valeur)
        library = library or films.Library([], {}, {}, casings_file=self.fichier)
        movie = {"title": titre}
        entree = self.entree if nom is None else naming.MovieFolder(folder=Path("x"), files=[Path("x/film.mkv")], rawname=nom)
        with mock.patch.object(films.cli, "can_ask", lambda: peut_demander), mock.patch.object(films.cli, "ask_choice", side_effect=list(reponses)) as question, redirect_stdout(io.StringIO()) as sortie:
            films.settle_title(entree, movie, library, args)
        return movie["title"], question.call_count, library, sortie.getvalue()

    def test_la_casse_du_fichier_est_proposee_et_memorisee(self):
        titre, questions, library, sortie = self.regler(reponses=[0])
        self.assertEqual((titre, questions), ("28 ans plus tard", 1))
        self.assertIn("28 Ans plus tard => 28 ans plus tard", self.fichier.read_text(encoding="utf-8"))
        self.assertEqual(library.casings, {"28 Ans plus tard": "28 ans plus tard"})
        self.assertIn("(défaut)", sortie)

    def test_garder_celle_de_tmdb_est_memorise_aussi(self):
        titre, _, library, _ = self.regler(reponses=[1])
        self.assertEqual(titre, "28 Ans plus tard")
        self.assertEqual(library.casings, {"28 Ans plus tard": "28 Ans plus tard"})

    def test_la_reponse_vaut_pour_tous_les_films_de_ce_titre(self):
        _, _, library, _ = self.regler(reponses=[0])
        titre, questions, _, _ = self.regler(library=library)
        self.assertEqual((titre, questions), ("28 ans plus tard", 0))

    def test_une_reponse_deja_consignee_n_est_pas_redemandee(self):
        self.fichier.write_text("# commentaire\n28 Ans plus tard => 28 ans plus tard !\n", encoding="utf-8")
        library = films.Library([], {}, {}, casings=passfiles.read_titles(self.fichier), casings_file=self.fichier)
        titre, questions, _, _ = self.regler(library=library)
        self.assertEqual((titre, questions), ("28 ans plus tard !", 0))

    def test_un_titre_anglais_propose_par_defaut_la_casse_de_tmdb(self):
        # Entrée ne doit pas transformer "American History X" en "American history X".
        with mock.patch.object(films.cli, "can_ask", lambda: True), mock.patch.object(films.cli, "ask_choice", return_value=1) as question, redirect_stdout(io.StringIO()):
            films.settle_title(naming.MovieFolder(folder=Path("x"), files=[Path("x/a.mkv")], rawname="American history X"), {"title": "American History X"}, films.Library([], {}, {}), types.SimpleNamespace(verify=False, no_tag=False, no_ask=False))
        self.assertEqual(question.call_args[0], (2, 1, True))

    def test_un_titre_francais_propose_par_defaut_la_casse_du_fichier(self):
        with mock.patch.object(films.cli, "can_ask", lambda: True), mock.patch.object(films.cli, "ask_choice", return_value=0) as question, redirect_stdout(io.StringIO()):
            films.settle_title(self.entree, {"title": "28 Ans plus tard"}, films.Library([], {}, {}), types.SimpleNamespace(verify=False, no_tag=False, no_ask=False))
        self.assertEqual(question.call_args[0], (2, 0, True))

    def test_un_morceau_du_titre_suffit(self):
        # "La naissance d'un empire" (saga "300") : le fichier ne porte pas le "300 :" du titre TMDB.
        titre, questions, _, _ = self.regler(titre="300 : La Naissance d’un Empire", nom="2 - La naissance d'un empire", reponses=[0])
        self.assertEqual((titre, questions), ("300 : La naissance d’un empire", 1))

    def test_rien_a_demander_quand_la_casse_est_la_meme(self):
        for titre, nom in (("Alien vs. Predator", "1 - Alien vs Predator"), ("Dune", "Dune (2021)"), ("Heat", "heat")):
            _, questions, _, _ = self.regler(titre=titre, nom=nom)
            self.assertEqual(questions, 0, titre)
        self.assertFalse(self.fichier.exists())

    def test_un_autre_film_ne_declenche_rien(self):
        _, questions, _, _ = self.regler(titre="Blade", nom="3 - 28 ans plus tard")
        self.assertEqual(questions, 0)

    def test_sans_terminal_le_titre_tmdb_est_garde_sans_rien_ecrire(self):
        titre, questions, _, sortie = self.regler(peut_demander=False)
        self.assertEqual((titre, questions), ("28 Ans plus tard", 0))
        self.assertIn("[CASSE]", sortie)
        self.assertFalse(self.fichier.exists())

    def test_no_ask_verify_et_no_tag_ne_demandent_rien(self):
        for option in ("no_ask", "verify", "no_tag"):
            titre, questions, _, _ = self.regler(**{option: True})
            self.assertEqual((titre, questions), ("28 Ans plus tard", 0), option)

    def test_entree_fermee_cesse_de_demander(self):
        titre, _, library, _ = self.regler(reponses=[cli_stop()])
        self.assertEqual(titre, "28 Ans plus tard")
        self.assertFalse(library.asking)
        _, questions, _, _ = self.regler(library=library)
        self.assertEqual(questions, 0)
        self.assertFalse(self.fichier.exists())

    def test_t_prend_le_defaut_pour_celle_ci_et_les_suivantes_sans_reposer_la_question(self):
        titre, questions, library, _ = self.regler(reponses=[films.cli.ASK_ALL])
        self.assertEqual((titre, questions), ("28 ans plus tard", 1))                # français : la casse du fichier
        self.assertTrue(library.take_defaults)
        titre, questions, library, sortie = self.regler(titre="American History X", nom="American history X", library=library)
        self.assertEqual((titre, questions), ("American History X", 0))               # anglais : la casse de TMDB
        self.assertIn("'American History X' -> 'American History X' (défaut)", sortie)
        self.assertEqual(library.casings, {"28 Ans plus tard": "28 ans plus tard", "American History X": "American History X"})
        self.assertIn("American History X => American History X", self.fichier.read_text(encoding="utf-8"))

    def test_ignorer_garde_le_titre_sans_memoriser(self):
        titre, questions, library, _ = self.regler(reponses=[cli_skip()])
        self.assertEqual((titre, questions), ("28 Ans plus tard", 1))
        self.assertEqual(library.casings, {})
        self.assertTrue(library.asking)
        self.assertFalse(self.fichier.exists())

    def test_le_titre_arrete_est_ecrit_partout_dans_le_mkv(self):
        # Le titre du conteneur et le tag TITLE du film viennent de la même fiche : ils prennent la même casse, et plus rien ne porte l'ancienne.
        movie = {"id": 1100988, "title": "28 Ans plus tard", "overview": "", "credits": {}}
        with mock.patch.object(films.cli, "can_ask", lambda: True), mock.patch.object(films.cli, "ask_choice", return_value=0), redirect_stdout(io.StringIO()):
            films.settle_title(self.entree, movie, films.Library([], {}, {}), types.SimpleNamespace(verify=False, no_tag=False, no_ask=False))
        cible = movietags.movie_target(movie, OPTS)
        titres = [n.text for n in ElementTree.fromstring(cible.tags_xml).findall(".//Simple[Name='TITLE']/String")]
        self.assertEqual((cible.title, titres), ("28 ans plus tard", ["28 ans plus tard"]))
        self.assertNotIn("28 Ans plus tard", cible.tags_xml)

    def test_l_identifiant_epingle_dans_le_nom_ne_gene_pas(self):
        titre, _, _, _ = self.regler(nom="3 - 28 ans plus tard [tmdbid-1100988]", reponses=[0])
        self.assertEqual(titre, "28 ans plus tard")


def cli_stop():
    return films.cli.ASK_STOP


def cli_skip():
    return films.cli.ASK_SKIP


class TestCasseDuNomDeSerie(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.racine = Path(self._tmp.name) / "Les mondes parallèles"
        (self.racine / "Saison 1").mkdir(parents=True)

    def regler(self, repertoire=None, reponses=(), peut_demander=True, **changes):
        args = types.SimpleNamespace(dir=str(repertoire or self.racine), verify=False, no_tag=False)
        for cle, valeur in changes.items():
            setattr(args, cle, valeur)
        with mock.patch.object(series.cli, "can_ask", lambda: peut_demander), mock.patch.object(series.cli, "ask_choice", side_effect=list(reponses)) as question, redirect_stdout(io.StringIO()) as sortie:
            titre = series.settle_series_name("Les Mondes Parallèles", args)
        return titre, question.call_count, sortie.getvalue()

    def memoire(self):
        return (self.racine / "metadata.titles")

    def test_le_dossier_de_la_serie_fait_la_proposition_et_la_reponse_est_memorisee(self):
        titre, questions, _ = self.regler(reponses=[0])
        self.assertEqual((titre, questions), ("Les mondes parallèles", 1))
        self.assertIn("Les Mondes Parallèles => Les mondes parallèles", self.memoire().read_text(encoding="utf-8"))
        self.assertEqual(self.regler()[:2], ("Les mondes parallèles", 0))

    def test_dir_sur_un_dossier_de_saison_regarde_le_dossier_de_la_serie(self):
        titre, questions, _ = self.regler(repertoire=self.racine / "Saison 1", reponses=[0])
        self.assertEqual((titre, questions), ("Les mondes parallèles", 1))

    def test_sans_terminal_verify_et_no_tag_gardent_le_titre_tmdb(self):
        self.assertEqual(self.regler(peut_demander=False)[:2], ("Les Mondes Parallèles", 0))
        self.assertIn("[CASSE]", self.regler(peut_demander=False)[2])
        self.assertEqual(self.regler(verify=True)[:2], ("Les Mondes Parallèles", 0))
        self.assertEqual(self.regler(no_tag=True)[:2], ("Les Mondes Parallèles", 0))
        self.assertFalse(self.memoire().exists())

    def test_t_vaut_le_defaut(self):
        titre, questions, _ = self.regler(reponses=[series.cli.ASK_ALL])
        self.assertEqual((titre, questions), ("Les mondes parallèles", 1))
        self.assertIn("Les Mondes Parallèles => Les mondes parallèles", self.memoire().read_text(encoding="utf-8"))

    def test_ignorer_et_quitter_ne_memorisent_rien(self):
        for reponse in (cli_skip(), cli_stop()):
            self.assertEqual(self.regler(reponses=[reponse])[:2], ("Les Mondes Parallèles", 1))
        self.assertFalse(self.memoire().exists())


if __name__ == "__main__":
    unittest.main()
