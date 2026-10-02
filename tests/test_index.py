"""Sommaire des séries : lu dans les fiches, et tenu à jour par chaque fiche écrite."""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mkvlib import showindex
from scripts.TV_Shows import Index as index
from scripts.TV_Shows import Metadata as series
from tests.test_flux import FauxTmdbSerie, FluxTestCase

SHOW = {"name": "Dark", "first_air_date": "2017-12-01", "number_of_seasons": 3,
        "overview": "Un enfant disparait 'a Winden' & <la> famille enquete."}
POSTER = ("w185/p.jpg", "data:image/jpeg;base64,QUJD")


def fiche(dossier, show=SHOW, poster=POSTER, saisons=(1, 2)):
    """Une fiche écrite comme Metadata.py l'écrit."""
    runs = [series.SeasonRun(dossier / f"Saison {n}", n, {"episodes": []}) for n in saisons]
    dossier.mkdir(parents=True, exist_ok=True)
    html = series.build_recap_html(show["name"], show, runs, "70523", {}, "w300", poster=poster)
    (dossier / "index.html").write_text(html, encoding="utf-8")


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
        self.assertIn(f"title='{attendu}'", html)        # en entier au survol

    def test_lien_relatif_encode(self):
        fiche(self.racine / "Dark & Co #1", show={**SHOW, "name": "Dark & Co"})
        html = showindex.build_html("Series", showindex.find_entries(self.racine))
        self.assertIn("href='Dark%20%26%20Co%20%231/index.html'", html)
        self.assertIn("Dark &amp; Co", html)

    def test_ancienne_fiche_sans_meta(self):
        dossier = self.racine / "Lost"
        dossier.mkdir()
        (dossier / "recap.html").write_text("<!DOCTYPE html><html><head><meta name='tmdb-id' content='4607'>"
                                            "<title>Lost</title><style></style></head></html>", encoding="utf-8")
        [entry] = showindex.find_entries(self.racine)
        self.assertEqual((entry.title, entry.poster), ("Lost", ""))

    def test_ancienne_fiche_encore_lue(self):
        # Une fiche pas encore régénérée garde son ancien nom : le sommaire la trouve, et pointe vers elle.
        fiche(self.racine / "Dark")
        (self.racine / "Dark" / "index.html").rename(self.racine / "Dark" / "recap.html")
        [entry] = showindex.find_entries(self.racine)
        self.assertEqual(entry.href, "Dark/recap.html")

    def test_titre_par_defaut_puis_conserve(self):
        fiche(self.racine / "Dark")
        showindex.write(self.racine, True)
        self.assertIn("<title>Séries</title>", (self.racine / "index.html").read_text(encoding="utf-8"))
        showindex.write(self.racine, True, title="Mes series")
        showindex.write(self.racine, True)
        self.assertIn("<title>Mes series</title>", (self.racine / "index.html").read_text(encoding="utf-8"))

    def test_dossier_sans_fiche_ignore(self):
        (self.racine / "Saison 1").mkdir()
        self.assertEqual(showindex.find_entries(self.racine), [])

    def test_affiche_reprise_comme_cache(self):
        fiche(self.racine / "Dark")
        self.assertEqual(showindex.recap_poster(self.racine / "Dark" / "index.html"), dict([POSTER]))

    def test_classement_sans_article(self):
        self.assertLess(showindex.sort_key("The Expanse"), showindex.sort_key("Fargo"))
        self.assertLess(showindex.sort_key("Économie"), showindex.sort_key("Fargo"))


class TestIndexPy(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bib = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        fiche(self.bib / "Dark")
        self.index = self.bib / "index.html"

    def indexer(self, *options):
        """Index.py sur la médiathèque : il n'a ni TMDB ni clé à simuler."""
        sortie = io.StringIO()
        with mock.patch.object(sys, "argv", ["Index.py", "--dir", str(self.bib), *options]), redirect_stdout(sortie):
            index.main()
        return sortie.getvalue()

    def test_une_nouvelle_fiche_entre_dans_le_sommaire(self):
        self.indexer("--apply")
        fiche(self.bib / "Ma Serie", show={**SHOW, "name": "Ma Serie"})
        self.assertIn("index.html ecrit (2 serie(s))", self.indexer("--apply"))
        html = self.index.read_text(encoding="utf-8")
        self.assertIn("href='Ma%20Serie/index.html'", html)
        self.assertIn("href='Dark/index.html'", html)

    def test_sommaire_identique_pas_reecrit(self):
        self.indexer("--apply")
        with mock.patch.object(Path, "write_text", side_effect=AssertionError("reecrit")):
            self.assertIn("index.html inchange", self.indexer("--apply"))

    def test_simulation_n_ecrit_rien(self):
        self.assertIn("ecrirait index.html", self.indexer())
        self.assertFalse(self.index.exists())

    def test_sommaire_etranger_jamais_touche(self):
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


if __name__ == "__main__":
    unittest.main()
