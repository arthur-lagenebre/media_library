"""Sommaire des séries : lu dans les fiches, et tenu à jour par chaque fiche écrite."""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.video import showindex
from scripts.TV_Shows import Index as index
from scripts.TV_Shows import Metadata as series
from tests.test_flux import FauxTmdbSerie, FluxTestCase

SHOW = {"name": "Dark", "first_air_date": "2017-12-01", "number_of_seasons": 3,
        "overview": "Un enfant disparait 'a Winden' & <la> famille enquete."}
POSTER = ("w185/p.jpg", "data:image/jpeg;base64,QUJD")


def fiche(dossier, show=SHOW, poster=POSTER, saisons=(1, 2)):
    """Une fiche écrite comme Metadata.py l'écrit : dans __Data__/Fiches, à côté des dossiers de série. Retourne son chemin."""
    runs = [series.SeasonRun(dossier / f"Saison {n}", n, {"episodes": []}) for n in saisons]
    dossier.mkdir(parents=True, exist_ok=True)
    html = series.build_recap_html(show["name"], show, runs, "70523", {}, "w300", poster=poster)
    page = showindex.sheet_path(dossier.parent, dossier.name)
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(html, encoding="utf-8")
    return page


def ancienne_fiche(dossier, nom="index.html"):
    """Une fiche comme les versions précédentes l'écrivaient : dans le dossier de la série."""
    page = fiche(dossier)
    (dossier / nom).write_text(page.read_text(encoding="utf-8"), encoding="utf-8")
    page.unlink()
    return dossier / nom


class TestLectureDesFiches(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_la_fiche_decrit_la_serie(self):
        fiche(self.racine / "Dark")
        [entry] = showindex.find_entries(self.racine)
        self.assertEqual((entry.title, entry.year, entry.seasons_label, entry.poster),
                         ("Dark", "2017", "2/3 saisons", POSTER[1]))

    def test_le_resume_suit_la_fiche(self):
        fiche(self.racine / "Dark")
        [entry] = showindex.find_entries(self.racine)
        self.assertEqual(entry.overview, SHOW["overview"])
        html = showindex.build_html("Series", [entry])
        attendu = "Un enfant disparait &#39;a Winden&#39; &amp; &lt;la&gt; famille enquete."
        self.assertIn(f"<div class='o'>{attendu}</div>", html)
        self.assertNotIn("title=", html.split("<body>", 1)[1])        # plus d'infobulle au survol

    def test_sept_par_ligne_et_bouton_sous_la_recherche(self):
        fiche(self.racine / "Dark")
        html = showindex.build_html("Series", showindex.find_entries(self.racine))
        self.assertIn(".grid{display:grid;gap:18px;grid-template-columns:repeat(7,1fr)}", html)
        self.assertIn(".wide .grid{grid-template-columns:repeat(auto-fill,minmax(148px,1fr))}", html)
        en_tete = html[html.index("<header class='top'>"):html.index("</header>")]
        self.assertLess(en_tete.index("<input class='filter'"), en_tete.index("<button class='mode'"))
        self.assertLess(html.index("localStorage.getItem('wide')"), html.index("<style>"))
        self.assertTrue(showindex.GENERATOR_META in html[:html.index("<style>")])    # la marque reste lisible par read_head

    def test_index_alphabetique_suit_le_classement(self):
        # "The Expanse" est classé à T, article compris : la lettre de sa vignette doit être celle de sa place.
        fiche(self.racine / "Expanse", show={**SHOW, "name": "The Expanse"})
        fiche(self.racine / "Dark")
        html = showindex.build_html("Series", showindex.find_entries(self.racine))
        self.assertIn("<nav class='az'", html[html.index("<header class='top'>"):html.index("</header>")])
        self.assertIn("class='serie' href='Fiches/Expanse.html' data-i='T'", html)
        self.assertIn("class='serie' href='Fiches/Dark.html' data-i='D'", html)

    def test_vignette_ancree_sur_le_dossier_de_la_serie(self):
        # C'est l'ancre que la fiche vise à son retour : elle ne dépend que du nom du dossier, pas du titre.
        fiche(self.racine / "Dark")
        html = showindex.build_html("Series", showindex.find_entries(self.racine))
        self.assertIn(f"<a id='{showindex.anchor('Dark')}' class='serie' href='Fiches/Dark.html'", html)
        self.assertNotEqual(showindex.anchor("Dark"), showindex.anchor("Fargo"))

    def test_retour_de_la_fiche_vers_le_sommaire_ecrit(self):
        # La fiche écrit son retour d'après le sommaire de __Data__ : « ← Anime » vers Anime.html, pas « ← Séries » vers tv_shows.html.
        fiche(self.racine / "Dark")
        self.assertEqual(showindex.back_target(self.racine), ("tv_shows.html", "Séries"))      # rien d'écrit encore : le sommaire par défaut
        showindex.write(self.racine, True, title="Anime")
        self.assertEqual(showindex.back_target(self.racine), ("Anime.html", "Anime"))
        showindex.write(self.racine, True)
        self.assertEqual(showindex.back_target(self.racine), ("tv_shows.html", "Séries"))      # plusieurs : le sommaire par défaut passe devant
        self.assertEqual(showindex.back_target(self.racine, "Mes animes"), ("Mes animes.html", "Mes animes"))   # --title est prioritaire

    def test_lien_de_retour_encode_et_ancre(self):
        self.assertEqual(showindex.back_href("Mes animes.html", "Dark"), f"../Mes%20animes.html#{showindex.anchor('Dark')}")
        self.assertEqual(showindex.back_href("tv_shows.html"), "../tv_shows.html")

    def test_genres_ecrits_dans_la_fiche_et_proposes_au_sommaire(self):
        fiche(self.racine / "Dark", show={**SHOW, "genres": [{"name": "Drame"}, {"name": "Science-Fiction"}]})
        fiche(self.racine / "Fargo", show={**SHOW, "name": "Fargo", "genres": [{"name": "Drame"}]})
        fiche(self.racine / "Vieille")                                     # une fiche sans genre : elle reste, mais ne passe aucun filtre
        entries = showindex.find_entries(self.racine)
        self.assertEqual({e.folder: e.genres for e in entries}, {"Dark": ("Drame", "Science-Fiction"), "Fargo": ("Drame",), "Vieille": ()})
        html = showindex.build_html("Series", entries)
        en_tete = html[html.index("<header class='top'>"):html.index("</header>")]
        self.assertIn("<option value='Drame'>Drame (2)</option>", en_tete)
        self.assertIn("<option value='Science-Fiction'>Science-Fiction (1)</option>", en_tete)
        self.assertIn("data-g='Drame|Science-Fiction'", html)
        self.assertIn("gok(c)", html)

    def test_pas_de_menu_sans_genre(self):
        fiche(self.racine / "Dark")
        html = showindex.build_html("Series", showindex.find_entries(self.racine))
        self.assertNotIn("<select", html)

    def test_le_h1_suit_le_titre_choisi(self):
        fiche(self.racine / "Dark")
        html = showindex.build_html("Ma mediatheque", showindex.find_entries(self.racine))
        self.assertIn("<h1>Ma mediatheque</h1>", html)
        self.assertIn("<title>Ma mediatheque</title>", html)

    def test_lien_relatif_encode(self):
        fiche(self.racine / "Dark & Co #1", show={**SHOW, "name": "Dark & Co"})
        html = showindex.build_html("Series", showindex.find_entries(self.racine))
        self.assertIn("href='Fiches/Dark%20%26%20Co%20%231.html'", html)
        self.assertIn("Dark &amp; Co", html)

    def test_ancienne_fiche_sans_meta(self):
        dossier = self.racine / "Lost"
        dossier.mkdir()
        (dossier / "recap.html").write_text("<!DOCTYPE html><html><head><meta name='tmdb-id' content='4607'>"
                                            "<title>Lost</title><style></style></head></html>", encoding="utf-8")
        [entry] = showindex.find_entries(self.racine)
        self.assertEqual((entry.title, entry.poster), ("Lost", ""))

    def test_ancienne_fiche_encore_lue(self):
        # Une fiche pas encore régénérée est restée dans le dossier de la série, sous son ancien nom : le sommaire la trouve, et pointe vers elle.
        for nom in ("index.html", "recap.html"):
            with self.subTest(nom=nom):
                ancienne_fiche(self.racine / "Dark", nom)
                [entry] = showindex.find_entries(self.racine)
                self.assertEqual((entry.href, entry.title), (f"../Dark/{nom}", "Dark"))
                (self.racine / "Dark" / nom).unlink()

    def test_la_fiche_de_data_passe_devant_l_ancienne(self):
        ancienne_fiche(self.racine / "Dark")
        fiche(self.racine / "Dark", show={**SHOW, "name": "Dark (à jour)"})
        [entry] = showindex.find_entries(self.racine)
        self.assertEqual((entry.href, entry.title), ("Fiches/Dark.html", "Dark (à jour)"))
        self.assertTrue((self.racine / "Dark" / "index.html").exists())          # l'ancienne reste en place

    def test_fiche_d_une_serie_retiree_ignoree(self):
        # Les fiches sont dans __Data__ : celle d'une série dont le dossier a disparu y reste, sans plus de lien pour y mener.
        fiche(self.racine / "Dark")
        fiche(self.racine / "Lost")
        (self.racine / "Lost").rmdir()
        self.assertEqual([e.folder for e in showindex.find_entries(self.racine)], ["Dark"])

    def test_titre_par_defaut_puis_conserve(self):
        fiche(self.racine / "Dark")
        page = self.racine / "__Data__" / "tv_shows.html"
        showindex.write(self.racine, True)
        self.assertIn("<title>Séries</title>", page.read_text(encoding="utf-8"))
        showindex.write(self.racine, True, out=page, title="Mes series")
        showindex.write(self.racine, True)
        self.assertIn("<title>Mes series</title>", page.read_text(encoding="utf-8"))

    def test_nom_du_fichier_d_apres_le_titre(self):
        for titre, nom in ((None, "tv_shows.html"), ("", "tv_shows.html"), ("Anime", "Anime.html"), ("Mes séries: 2", "Mes séries 2.html"), ("///", "tv_shows.html")):
            with self.subTest(titre=titre):
                self.assertEqual(showindex.index_name(titre), nom)

    def test_le_sommaire_va_dans_data_sous_le_nom_du_titre(self):
        fiche(self.racine / "Dark")
        showindex.write(self.racine, True, title="Anime")
        self.assertEqual(sorted(p.name for p in (self.racine / "__Data__").iterdir()), ["Anime.html", "Fiches"])
        self.assertIn("<title>Anime</title>", (self.racine / "__Data__" / "Anime.html").read_text(encoding="utf-8"))
        self.assertFalse((self.racine / "index.html").exists())          # rien n'est écrit à la racine de la médiathèque

    def test_les_liens_descendent_de_data_jusqu_aux_fiches(self):
        # Le sommaire et le dossier des fiches sont tous deux dans __Data__ : le lien est relatif à lui.
        fiche(self.racine / "Dark")
        showindex.write(self.racine, True)
        html = (self.racine / "__Data__" / "tv_shows.html").read_text(encoding="utf-8")
        self.assertIn("href='Fiches/Dark.html'", html)
        self.assertTrue((self.racine / "__Data__" / "Fiches/Dark.html").exists())

    def test_le_dossier_data_n_est_pas_une_serie(self):
        fiche(self.racine / "Dark")
        showindex.write(self.racine, True)
        self.assertEqual([e.folder for e in showindex.find_entries(self.racine)], ["Dark"])

    def test_titre_repris_de_l_ancien_sommaire_a_la_racine_qui_reste_en_place(self):
        fiche(self.racine / "Dark")
        ancien = self.racine / "index.html"
        ancien.write_text(showindex.build_html("Mes animes", []), encoding="utf-8")
        showindex.write(self.racine, True)
        self.assertIn("<title>Mes animes</title>", (self.racine / "__Data__" / "tv_shows.html").read_text(encoding="utf-8"))
        self.assertIn("Mes animes", ancien.read_text(encoding="utf-8"))             # ni réécrit ni effacé

    def test_un_index_etranger_a_la_racine_ne_donne_pas_son_titre(self):
        fiche(self.racine / "Dark")
        (self.racine / "index.html").write_text("<html><head><title>A moi</title></head></html>", encoding="utf-8")
        showindex.write(self.racine, True)
        self.assertIn("<title>Séries</title>", (self.racine / "__Data__" / "tv_shows.html").read_text(encoding="utf-8"))

    def test_sommaires_ecrits_retrouves_quel_que_soit_leur_nom(self):
        fiche(self.racine / "Dark")
        showindex.write(self.racine, True, title="Anime")
        showindex.write(self.racine, True)
        (self.racine / "__Data__" / "notes.html").write_text("<html>à moi</html>", encoding="utf-8")
        self.assertEqual([p.name for p in showindex.our_indexes(self.racine)], ["Anime.html", "tv_shows.html"])

    def test_dossier_sans_fiche_ignore(self):
        (self.racine / "Saison 1").mkdir()
        self.assertEqual(showindex.find_entries(self.racine), [])

    def test_affiche_reprise_comme_cache(self):
        page = fiche(self.racine / "Dark")
        self.assertEqual(showindex.recap_poster(page), dict([POSTER]))

    def test_classement_article_compris(self):
        self.assertGreater(showindex.sort_key("The Expanse"), showindex.sort_key("Fargo"))
        self.assertLess(showindex.sort_key("Les Motards de l'espace"), showindex.sort_key("Reacher"))
        self.assertLess(showindex.sort_key("Économie"), showindex.sort_key("Fargo"))

    def test_classement_titres_commencant_par_a(self):
        # Le "A" d'"Alien" n'est pas un article : ces titres se rangeaient à L, R et L, après The Last of Us, Reacher et Kyle XY.
        titres = ["The Last of Us", "Reacher", "Kyle XY", "Alien: Earth", "Arcane", "À l'est d'Éden", "The Office"]
        self.assertEqual(sorted(titres, key=showindex.sort_key),
                         ["À l'est d'Éden", "Alien: Earth", "Arcane", "Kyle XY", "Reacher", "The Last of Us", "The Office"])


class TestIndexPy(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bib = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        fiche(self.bib / "Dark")
        self.index = self.bib / "__Data__" / "tv_shows.html"

    def indexer(self, *options):
        """Index.py sur la médiathèque : il n'a ni TMDB ni clé à simuler."""
        sortie = io.StringIO()
        with mock.patch.object(sys, "argv", ["Index.py", "--dir", str(self.bib), *options]), redirect_stdout(sortie):
            index.main()
        return sortie.getvalue()

    def test_une_nouvelle_fiche_entre_dans_le_sommaire(self):
        self.indexer("--apply")
        fiche(self.bib / "Ma Serie", show={**SHOW, "name": "Ma Serie"})
        self.assertIn("tv_shows.html écrit (2 série(s))", self.indexer("--apply"))
        html = self.index.read_text(encoding="utf-8")
        self.assertIn("href='Fiches/Ma%20Serie.html'", html)
        self.assertIn("href='Fiches/Dark.html'", html)

    def test_sommaire_identique_pas_reecrit(self):
        self.indexer("--apply")
        with mock.patch.object(Path, "write_text", side_effect=AssertionError("reecrit")):
            self.assertIn("tv_shows.html inchangé", self.indexer("--apply"))

    def test_simulation_n_ecrit_rien(self):
        self.assertIn("écrirait tv_shows.html", self.indexer())
        self.assertFalse(self.index.exists())
        self.assertEqual([d.name for d in (self.bib / "__Data__").iterdir()], ["Fiches"])      # le sommaire n'a rien ajouté

    def test_titre_donne_le_nom_du_fichier(self):
        self.assertIn("Anime.html écrit (1 série(s))", self.indexer("--apply", "--title", "Anime"))
        self.assertTrue((self.bib / "__Data__" / "Anime.html").exists())
        self.assertFalse(self.index.exists())
        self.assertIn("<title>Anime</title>", (self.bib / "__Data__" / "Anime.html").read_text(encoding="utf-8"))

    def test_sommaire_etranger_jamais_touche(self):
        self.index.parent.mkdir(exist_ok=True)
        self.index.write_text("<html>a moi</html>", encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.indexer("--apply")
        self.assertEqual(self.index.read_text(encoding="utf-8"), "<html>a moi</html>")

    def test_dossiers_caches_ignores(self):
        fiche(self.bib / ".recycle")
        self.assertEqual([e.folder for e in showindex.find_entries(self.bib)], ["Dark"])


class TestAfficheDesFiches(FluxTestCase):
    def test_l_affiche_n_est_telechargee_qu_une_fois(self):
        with tempfile.TemporaryDirectory() as d:
            serie = Path(d) / "Ma Serie"
            (serie / "Saison 1").mkdir(parents=True)

            def recap(tmdb):
                with mock.patch.object(series.mkv, "check_tools", lambda **k: False):
                    self.lancer(series, ["--dir", str(serie), "--tmdb-id", "42", "--no-tag", "--recap", "--apply"], tmdb=tmdb)

            recap(FauxTmdbSerie())
            tmdb = FauxTmdbSerie()
            with mock.patch.object(tmdb, "image", wraps=tmdb.image) as image:
                recap(tmdb)
            self.assertNotIn(mock.call("/serie.jpg", "w185"), image.call_args_list)
            [entry] = showindex.find_entries(Path(d))
            self.assertTrue(entry.poster.startswith("data:image/jpeg;base64,"))
            self.assertFalse((Path(d) / "index.html").exists())   # Metadata.py n'y touche pas
            self.assertEqual(sorted(p.name for p in serie.iterdir()), ["Saison 1"])         # ni au dossier de la série : la fiche est dans __Data__
            self.assertTrue((Path(d) / "__Data__" / "Fiches" / "Ma Serie.html").is_file())


class TestMarqueDuSommaire(unittest.TestCase):
    """Un sommaire écrit sous l'ancien nom du projet reste le nôtre : il ne doit pas devenir un fichier étranger qu'on refuse de réécrire."""

    def ecrire(self, contenu):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        page = Path(d.name) / "index.html"
        page.write_text(contenu, encoding="utf-8")
        return page

    def test_marque_actuelle(self):
        self.assertTrue(showindex.is_ours(self.ecrire(f"<head>{showindex.GENERATOR_META}</head><style>")))

    def test_marque_d_avant_le_renommage(self):
        self.assertTrue(showindex.is_ours(self.ecrire("<head><meta name='generator' content='mkv_editors-index'></head><style>")))

    def test_page_etrangere(self):
        self.assertFalse(showindex.is_ours(self.ecrire("<head><title>Mon site</title></head><style>")))


if __name__ == "__main__":
    unittest.main()
