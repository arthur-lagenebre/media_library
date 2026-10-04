"""Déroulement complet de Books/Recap.py : ce que produit une invocation sur une petite bibliothèque."""

import base64
import io
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.books import shelfpage, thumbs
from scripts.Books import Recap as recap
from tests.test_books_readers import COMICINFO, make_cbz, make_epub, png


class TestRecapLivres(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        make_cbz(self.racine / "Manga" / "Captain Tsubasa" / "Tome 28.cbz", COMICINFO)
        make_cbz(self.racine / "Manga" / "Captain Tsubasa" / "Tome 29.cbz")          # sans fiche
        make_cbz(self.racine / "BD" / "Megalex" / "1 - L'anomalie.cbz", COMICINFO.replace("Captain Tsubasa", "Megalex"))
        make_epub(self.racine / "Romans" / "Alain Damasio" / "La horde du Contrevent.epub", cover=png())
        (self.racine / "Manuels").mkdir()
        (self.racine / "Manuels" / "Guide.mobi").write_bytes(b"BOOKMOBI")
        (self.racine / "Manga" / "__En cours").mkdir()
        make_cbz(self.racine / "Manga" / "__En cours" / "Brouillon" / "1.cbz")        # pas encore rangé : ignoré
        self.data = self.racine / "__Data__"

    def lancer(self, *options):
        sortie = io.StringIO()
        with mock.patch.object(sys, "argv", ["Recap.py", "--dir", str(self.racine), *options]), redirect_stdout(sortie):
            code = recap.main()
        return code, sortie.getvalue()

    def test_simulation_n_ecrit_ni_fiche_ni_journal_sans_dossier(self):
        code, sortie = self.lancer()
        self.assertEqual(code, 0)
        self.assertFalse(self.data.exists())
        self.assertIn("SIMULATION", sortie)
        self.assertIn("ecrirait", sortie)

    def test_simulation_n_ecrit_que_le_journal_quand_le_dossier_existe(self):
        self.data.mkdir()
        self.lancer()
        self.assertEqual(sorted(p.name for p in self.data.iterdir()), ["recap.log"])

    def test_pdf_ignores_par_defaut_et_comptes_sur_demande(self):
        (self.racine / "Manuels" / "Notice.pdf").write_bytes(b"%PDF-1.4")
        _, sortie = self.lancer()
        self.assertIn("TOTAL : 3/5 livre(s) avec fiche.", sortie)
        self.assertNotIn("Notice", sortie)
        _, sortie = self.lancer("--include-pdf")
        self.assertIn("TOTAL : 3/6 livre(s) avec fiche.", sortie)

    def test_bilan_par_section(self):
        _, sortie = self.lancer()
        self.assertRegex(sortie, r"Manga\s+1 serie\(s\)\s+2 volume\(s\)\s+1 avec fiche")      # __En cours n'est pas compté
        self.assertRegex(sortie, r"Romans\s+1 serie\(s\)\s+1 volume\(s\)\s+1 avec fiche")
        self.assertIn("TOTAL : 3/5 livre(s) avec fiche.", sortie)

    def test_apply_ecrit_sommaire_pages_catalogue_et_journal(self):
        code, _ = self.lancer("--apply")
        self.assertEqual(code, 0)
        self.assertEqual(sorted(p.name for p in self.data.iterdir()), ["Series", "catalog.json", "index.html", "recap.log"])
        self.assertEqual(len(list((self.data / "Series").glob("*.html"))), 4)       # une page par série
        html = (self.data / "index.html").read_text(encoding="utf-8")
        self.assertIn("<title>Livres</title>", html)
        self.assertIn("Captain Tsubasa", html)
        self.assertNotIn("Brouillon", html)

    def test_le_sommaire_mene_a_la_page_de_chaque_serie(self):
        self.lancer("--apply")
        html = (self.data / "index.html").read_text(encoding="utf-8")
        for page in (self.data / "Series").glob("*.html"):
            self.assertIn(page.name.replace(" ", "%20").replace("'", "%27"), html)
            self.assertIn("href='../index.html#s", page.read_text(encoding="utf-8"))

    def test_journal_des_livres_sans_fiche(self):
        self.lancer("--apply")
        journal = (self.data / "recap.log").read_text(encoding="utf-8")
        self.assertIn("[SANS FICHE] Manga/Captain Tsubasa/Tome 29.cbz", journal)
        self.assertIn("[SANS FICHE] Manuels/Guide.mobi", journal)
        self.assertNotIn("Tome 28.cbz", journal)

    def test_livre_illisible_dans_le_journal_et_le_code_de_sortie(self):
        (self.racine / "BD" / "Megalex" / "2 - Tronque.cbz").write_bytes(b"coupe")
        code, sortie = self.lancer("--apply")
        self.assertEqual(code, 1)
        self.assertIn("1 fichier(s) illisible(s)", sortie)
        self.assertIn("[ILLISIBLE] BD/Megalex/2 - Tronque.cbz", (self.data / "recap.log").read_text(encoding="utf-8"))
        page = next((self.data / "Series").glob("Megalex-*.html")).read_text(encoding="utf-8")
        self.assertIn("illisible : archive illisible", page)

    def test_passage_suivant_ne_rouvre_rien_et_ne_reecrit_rien(self):
        self.lancer("--apply")
        avant = {p: p.stat().st_mtime_ns for p in self.data.rglob("*") if p.is_file() and p.name != "recap.log"}
        with mock.patch.object(recap.shelf, "read_info", side_effect=AssertionError("livre rouvert")):
            _, sortie = self.lancer("--apply")
        self.assertIn("5 repris du catalogue, 0 a lire", sortie)
        self.assertIn("index.html inchange", sortie)
        self.assertIn("(0 ecrite(s), 4 inchangee(s))", sortie)
        self.assertEqual(avant, {p: p.stat().st_mtime_ns for p in avant})

    def test_livre_modifie_est_relu_seul(self):
        self.lancer("--apply")
        make_cbz(self.racine / "Manga" / "Captain Tsubasa" / "Tome 29.cbz", COMICINFO.replace("<Number>28", "<Number>29"), pages=("a.png", "b.png", "c.png"))
        _, sortie = self.lancer("--apply")
        self.assertIn("1 a lire", sortie)
        self.assertIn("TOTAL : 4/5 livre(s) avec fiche.", sortie)

    def test_no_cache_rouvre_tout(self):
        self.lancer("--apply")
        _, sortie = self.lancer("--apply", "--no-cache")
        self.assertIn("0 repris du catalogue, 5 a lire", sortie)

    def test_titre_choisi_puis_repris_sans_l_option(self):
        self.lancer("--apply", "--title", "Ma bibliotheque")
        self.lancer("--apply")                       # la tâche de nuit, sans --title
        self.assertIn("<title>Ma bibliotheque</title>", (self.data / "index.html").read_text(encoding="utf-8"))

    def test_sortie_ailleurs(self):
        ailleurs = self.racine.parent / (self.racine.name + "-sortie")
        self.addCleanup(lambda: __import__("shutil").rmtree(ailleurs, ignore_errors=True))
        self.lancer("--apply", "--out", str(ailleurs))
        self.assertTrue((ailleurs / "index.html").exists())
        self.assertFalse(self.data.exists())

    def test_bibliotheque_vide(self):
        with tempfile.TemporaryDirectory() as vide:
            sortie = io.StringIO()
            with mock.patch.object(sys, "argv", ["Recap.py", "--dir", vide]), redirect_stdout(sortie):
                self.assertEqual(recap.main(), 0)
            self.assertIn("Aucun livre trouve", sortie.getvalue())

    def test_dossier_introuvable(self):
        with mock.patch.object(sys, "argv", ["Recap.py", "--dir", str(self.racine / "absent")]), self.assertRaises(SystemExit):
            recap.main()

    @unittest.skipUnless(thumbs.available(), "Pillow n'est pas installé")
    def test_couvertures_integrees_et_reprises_de_la_page_precedente(self):
        _, sortie = self.lancer("--apply")
        self.assertIn("4 couverture(s) extraite(s)", sortie)               # les 3 .cbz et l'.epub ; le .mobi n'en a pas
        page = next((self.data / "Series").glob("Captain Tsubasa-*.html")).read_text(encoding="utf-8")
        self.assertEqual(page.count("<img data-img="), 3)                  # les 2 tomes + l'en-tête
        self.assertIn("data:image/jpeg;base64,", (self.data / "index.html").read_text(encoding="utf-8"))
        # Une page déjà écrite sert de cache : rien n'est rouvert pour la couverture.
        (self.data / "catalog.json").unlink()
        def pas_de_reouverture(volume):
            self.assertEqual(volume.kind, "mobi", f"couverture rouverte : {volume.rel}")      # le .mobi n'en a jamais : rien à rouvrir
            return None
        with mock.patch.object(recap.shelf, "read_cover", pas_de_reouverture):
            _, sortie = self.lancer("--apply")
        self.assertIn("0 couverture(s) extraite(s)", sortie)

    @unittest.skipUnless(thumbs.available(), "Pillow n'est pas installé")
    def test_le_sommaire_porte_des_couvertures_plus_petites_que_les_pages(self):
        from PIL import Image
        make_cbz(self.racine / "Manga" / "Grand" / "1.cbz", pages=("1.png",), size=(600, 900))
        self.lancer("--apply", "--cover-width", "300")

        def largeurs(html):
            return {Image.open(io.BytesIO(base64.b64decode(uri))).width for uri in re.findall(r"src='data:image/jpeg;base64,([^']+)'", html)}
        self.assertIn(300, largeurs(next((self.data / "Series").glob("Grand-*.html")).read_text(encoding="utf-8")))
        self.assertEqual(max(largeurs((self.data / "index.html").read_text(encoding="utf-8"))), recap.INDEX_COVER_WIDTH)

    def test_sans_pillow_des_monogrammes(self):
        with mock.patch.object(thumbs, "Image", None):
            _, sortie = self.lancer("--apply")
        self.assertIn("Pillow absent", sortie)
        self.assertIn("noimg mono", (self.data / "index.html").read_text(encoding="utf-8"))
        self.assertNotIn("data:image/jpeg", (self.data / "index.html").read_text(encoding="utf-8"))

    def test_les_options_invalides_sont_refusees(self):
        for option in (["--workers", "0"], ["--cover-width", "0"]):
            with self.subTest(option=option):
                with mock.patch.object(sys, "argv", ["Recap.py", "--dir", str(self.racine), *option]), redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
                    with self.assertRaises(SystemExit):
                        recap.parse_args()


if __name__ == "__main__":
    unittest.main()
