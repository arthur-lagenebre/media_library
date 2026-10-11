"""Déroulement complet de Music/Recap.py : ce que produit une invocation sur une petite médiathèque."""

import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common import thumbs
from libraries.music import flac
from scripts.Music import Recap as recap
from tests import test_mp3
from tests.test_books_readers import png
from tests.test_flac import fichier, image
from tests.test_library import MBID, piste


class TestRecapMusique(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        for n in (1, 2, 4):
            piste(self.racine / "Daft Punk" / "Discovery", f"{n:02d}.flac", number=n, total=4, title=f"Titre {n}", mbid=MBID, cover=n == 1)
        piste(self.racine / "Daft Punk" / "Homework", "01.flac", album="Homework", date="1997", mbid=MBID.replace("4e", "5f"))
        piste(self.racine / "Kavinsky" / "Outrun", "01.flac", artist="Kavinsky", album="Outrun", date="2013")        # pas encore étiqueté
        (self.racine / "Kavinsky" / "Outrun" / "02.m4a").write_bytes(b"x")
        piste(self.racine / "__Data__" / "Ancien", "01.flac")                                                    # nos propres pages : ignoré
        self.data = self.racine / "__Data__"

    def lancer(self, *options):
        sortie = io.StringIO()
        with mock.patch.object(sys, "argv", ["Recap.py", "--dir", str(self.racine), *options]), redirect_stdout(sortie):
            code = recap.main()
        return code, sortie.getvalue()

    def test_simulation_n_ecrit_ni_fiche_ni_journal_sans_dossier(self):
        shutil.rmtree(self.data)
        code, sortie = self.lancer()
        self.assertEqual(code, 0)
        self.assertFalse(self.data.exists())
        self.assertIn("SIMULATION", sortie)
        self.assertIn("ecrirait", sortie)

    def test_simulation_n_ecrit_que_le_journal_quand_le_dossier_existe(self):
        self.lancer()
        self.assertEqual(sorted(p.name for p in self.data.iterdir() if p.is_file()), ["recap.log"])
        self.assertFalse((self.data / "index.html").exists())

    def test_bilan(self):
        _, sortie = self.lancer()
        self.assertIn("3 album(s), 2 artiste(s), 5 piste(s), 4 etiquetee(s)", sortie)
        self.assertIn("TOTAL : 4/5 piste(s) etiquetee(s) par MusicBrainz.", sortie)
        self.assertNotIn("Ancien", sortie)

    def test_application_ecrit_sommaire_fiches_catalogue_et_journal(self):
        code, _ = self.lancer("--apply")
        self.assertEqual(code, 0)
        self.assertEqual(sorted(p.name for p in self.data.iterdir() if p.is_file()), ["catalog.json", "index.html", "recap.log"])
        self.assertEqual(len(list((self.data / "Albums").glob("*.html"))), 3)
        index = (self.data / "index.html").read_text(encoding="utf-8")
        self.assertIn("<title>Musique</title>", index)
        self.assertEqual(len(re.findall(r"href='Albums/", index)), 3)

    def test_aucune_ecriture_dans_la_musique(self):
        avant = {p: p.read_bytes() for p in self.racine.rglob("*") if p.is_file() and "__Data__" not in p.parts}
        self.lancer("--apply")
        self.assertEqual({p: p.read_bytes() for p in avant}, avant)

    def test_journal(self):
        self.lancer("--apply")
        journal = (self.data / "recap.log").read_text(encoding="utf-8")
        self.assertIn("[NON ETIQUETE] Kavinsky/Outrun (0/1)", journal)
        self.assertIn("[MANQUE] Daft Punk/Discovery : disque 1, piste(s) 3 (sur 4)", journal)
        self.assertIn("[NON PRIS EN CHARGE] Kavinsky/Outrun : 02.m4a", journal)
        self.assertNotIn("Homework", journal)

    def test_titre_choisi_survit_aux_passages_suivants(self):
        self.lancer("--apply", "--title", "Ma musique")
        self.lancer("--apply")
        self.assertIn("<title>Ma musique</title>", (self.data / "index.html").read_text(encoding="utf-8"))

    def test_sortie_ailleurs(self):
        ailleurs = self.racine.parent / (self.racine.name + "-out")
        self.addCleanup(shutil.rmtree, ailleurs, ignore_errors=True)
        self.lancer("--apply", "--out", str(ailleurs))
        self.assertTrue((ailleurs / "index.html").exists())
        self.assertFalse((self.data / "index.html").exists())

    def test_deuxieme_passage_ne_reecrit_rien_et_reprend_le_catalogue(self):
        self.lancer("--apply")
        fichiers = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in self.data.rglob("*") if p.is_file() and p.name != "recap.log"}
        _, sortie = self.lancer("--apply")
        self.assertIn("5 piste(s), 5 reprise(s) du catalogue, 0 a lire", sortie)
        self.assertIn("0 ecrite(s), 3 inchangee(s)", sortie)
        self.assertIn("inchange", sortie)
        self.assertEqual({p: (p.stat().st_mtime_ns, p.read_bytes()) for p in fichiers}, fichiers)

    def test_piste_modifiee_est_relue(self):
        self.lancer("--apply")
        piste(self.racine / "Daft Punk" / "Discovery", "04.flac", number=4, total=4, title="Un titre plus long qu'avant", mbid=MBID)
        _, sortie = self.lancer("--apply")
        self.assertIn("4 reprise(s) du catalogue, 1 a lire", sortie)
        self.assertIn("1 ecrite(s)", sortie)

    def test_no_cache_rouvre_tout(self):
        self.lancer("--apply")
        _, sortie = self.lancer("--apply", "--no-cache")
        self.assertIn("0 reprise(s) du catalogue, 5 a lire", sortie)

    def test_catalogue_corrompu_est_ignore(self):
        self.lancer("--apply")
        (self.data / "catalog.json").write_text("{", encoding="utf-8")
        _, sortie = self.lancer("--apply")
        self.assertIn("0 reprise(s) du catalogue, 5 a lire", sortie)

    def test_fichier_illisible_code_1_et_journal(self):
        (self.racine / "Daft Punk" / "Discovery" / "03.flac").write_bytes(b"coupe")
        code, sortie = self.lancer("--apply")
        self.assertEqual(code, 1)
        self.assertIn("A CORRIGER : 1 fichier(s) illisible(s)", sortie)
        self.assertIn("[ILLISIBLE] Daft Punk/Discovery/03.flac", (self.data / "recap.log").read_text(encoding="utf-8"))
        self.assertTrue((self.data / "index.html").exists())

    def test_catalogue_sans_piste_illisible(self):
        (self.racine / "Daft Punk" / "Discovery" / "03.flac").write_bytes(b"coupe")
        self.lancer("--apply")
        catalogue = json.loads((self.data / "catalog.json").read_text(encoding="utf-8"))["tracks"]
        self.assertNotIn("Daft Punk/Discovery/03.flac", catalogue)

    def test_dossier_sans_musique(self):
        vide = self.racine / "Vide"
        vide.mkdir()
        with mock.patch.object(sys, "argv", ["Recap.py", "--dir", str(vide)]), redirect_stdout(io.StringIO()) as sortie:
            self.assertEqual(recap.main(), 0)
        self.assertIn("Aucun .flac ni .mp3", sortie.getvalue())

    def test_dossier_introuvable(self):
        with mock.patch.object(sys, "argv", ["Recap.py", "--dir", str(self.racine / "nulle part")]):
            with self.assertRaises(SystemExit):
                recap.main()

    def test_options_invalides(self):
        with mock.patch.object(sys, "argv", ["Recap.py", "--dir", str(self.racine), "--workers", "0"]), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                recap.main()

    def test_un_mp3_compte_comme_un_flac(self):
        dossier = self.racine / "Air" / "Moon Safari"
        dossier.mkdir(parents=True)
        trames = [test_mp3.trame("TIT2", test_mp3.texte(["La femme d'argent"])), test_mp3.trame("TALB", test_mp3.texte(["Moon Safari"])),
                  test_mp3.trame("TPE1", test_mp3.texte(["Air"])), test_mp3.trame("TRCK", test_mp3.texte(["1/10"])),
                  test_mp3.trame("TXXX", test_mp3.txxx("MusicBrainz Album Id", [MBID]))]
        (dossier / "01.mp3").write_bytes(test_mp3.fichier(trames))
        _, sortie = self.lancer("--apply")
        self.assertIn("4 album(s), 3 artiste(s), 6 piste(s), 5 etiquetee(s)", sortie)
        fiche = next((self.data / "Albums").glob("Air - Moon Safari-*.html")).read_text(encoding="utf-8")
        self.assertIn("MP3", fiche)
        self.assertIn("La femme d&#39;argent", fiche)
        self.assertIn("Manque : pistes 2–10", fiche)

    @unittest.skipUnless(thumbs.available(), "Pillow n'est pas installé")
    def test_pochette_reduite_et_reprise_de_la_page(self):
        chemin = self.racine / "Daft Punk" / "Discovery" / "01.flac"
        chemin.write_bytes(fichier(["TITLE=Titre 1", "ARTIST=Daft Punk", "ALBUM=Discovery", "TRACKNUMBER=1", "MUSICBRAINZ_ALBUMID=" + MBID],
                                   extra=[(flac.PICTURE, image(png(900, 900)))]))
        _, sortie = self.lancer("--apply")
        self.assertIn("1 pochette(s) extraite(s)", sortie)
        index = (self.data / "index.html").read_text(encoding="utf-8")
        self.assertIn("src='data:image/jpeg;base64,", index)
        self.assertEqual(len(re.findall(r"<img data-img=", index)), 1)
        # Deuxième passage : la page sert de cache, la pochette n'est pas rouverte.
        with mock.patch.object(recap.library, "read_cover", side_effect=AssertionError("pochette rouverte")):
            _, sortie = self.lancer("--apply")
        self.assertIn("0 pochette(s) extraite(s)", sortie)
        self.assertEqual((self.data / "index.html").read_text(encoding="utf-8"), index)

    def test_sans_pillow_monogrammes(self):
        chemin = self.racine / "Daft Punk" / "Discovery" / "01.flac"
        chemin.write_bytes(fichier(["TITLE=Titre 1", "ARTIST=Daft Punk", "ALBUM=Discovery", "TRACKNUMBER=1"], extra=[(flac.PICTURE, image(png()))]))
        with mock.patch.object(thumbs, "Image", None):
            _, sortie = self.lancer("--apply")
        self.assertIn("Pillow absent", sortie)
        self.assertNotIn("<img data-img=", (self.data / "index.html").read_text(encoding="utf-8"))

    def test_pochette_illisible_n_arrete_pas_le_passage(self):
        chemin = self.racine / "Daft Punk" / "Discovery" / "01.flac"
        chemin.write_bytes(fichier(["TITLE=Titre 1", "ARTIST=Daft Punk", "ALBUM=Discovery", "TRACKNUMBER=1"], extra=[(flac.PICTURE, image(b"pas une image"))]))
        code, _ = self.lancer("--apply")
        self.assertEqual(code, 0)
        self.assertNotIn("<img data-img=", next((self.data / "Albums").glob("Daft Punk - Discovery-*.html")).read_text(encoding="utf-8"))

    def test_fiche_d_un_album_sorti_de_la_mediatheque_reste_sur_le_disque(self):
        self.lancer("--apply")
        shutil.rmtree(self.racine / "Kavinsky")
        self.lancer("--apply")
        self.assertEqual(len(list((self.data / "Albums").glob("*.html"))), 3)
        self.assertEqual(len(re.findall(r"href='Albums/", (self.data / "index.html").read_text(encoding="utf-8"))), 2)


if __name__ == "__main__":
    unittest.main()
