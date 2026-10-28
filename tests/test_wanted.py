"""Les albums qui manquent : des .txt nommés "1997 - OK Computer.txt" dans le dossier de l'artiste, montrés sur sa fiche."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tempfile

from libraries.common.filenames import safe_name
from libraries.music import library, wanted
from libraries.music.wanted import Wanted
from tests.test_library import piste


class PageTestCase(unittest.TestCase):
    """Une médiathèque temporaire, avec de quoi y poser des albums."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.racine = Path(self._tmp.name)

    def albums(self):
        found = library.scan(self.racine)
        for release in found:
            for track in release.tracks:
                library.read_info(track)
        return found

    def album(self, artiste="Daft Punk", titre="Discovery", pistes=(1, 2, 3), total=3, annee="2001", **kw):
        for n in pistes:
            piste(self.racine / safe_name(artiste) / safe_name(titre), f"{n:02d}.flac", number=n, title=f"Piste {n}", total=total, artist=artiste, album=titre, date=annee, **kw)

    def un(self, **kw):
        self.album(**kw)
        return self.albums()[0]


class TestNom(unittest.TestCase):
    def test_annee_et_titre(self):
        self.assertEqual(wanted.parse("1997 - OK Computer.txt"), Wanted("1997", "OK Computer"))
        self.assertEqual(wanted.parse("2011 – The King of Limbs.TXT"), Wanted("2011", "The King of Limbs"))

    def test_ce_qui_n_est_pas_un_album(self):
        for nom in ("artist.txt", "notes.txt", "OK Computer.txt", "1997 - OK Computer.nfo", "1997 - OK Computer", "1997 - .txt"):
            with self.subTest(nom=nom):
                self.assertIsNone(wanted.parse(nom))

    def test_rangement_par_annee_puis_titre(self):
        trouves = [Wanted("2000", "Kid A"), Wanted("1997", "OK Computer"), Wanted("2000", "Amnesiac")]
        self.assertEqual([w.title for w in sorted(trouves, key=lambda w: w.order)], ["OK Computer", "Amnesiac", "Kid A"])


class TestRecherche(PageTestCase):
    def dire(self, *chemins):
        for chemin in chemins:
            fichier = self.racine / chemin
            fichier.parent.mkdir(parents=True, exist_ok=True)
            fichier.write_text("", encoding="utf-8")

    def trouver(self):
        albums = self.albums()
        return albums, wanted.find(self.racine, albums)

    def test_les_txt_du_dossier_de_l_artiste(self):
        self.album("Radiohead", "The Bends", annee="1995")
        self.dire("Radiohead/1997 - OK Computer.txt", "Radiohead/2000 - Kid A.txt", "Radiohead/artist.txt", "Radiohead/notes.txt")
        albums, trouves = self.trouver()
        self.assertEqual(trouves, {albums[0].artist_id: [Wanted("1997", "OK Computer"), Wanted("2000", "Kid A")]})

    def test_l_image_de_meme_nom_est_la_pochette(self):
        self.album("Radiohead", "The Bends", annee="1995")
        self.dire("Radiohead/1997 - OK Computer.txt", "Radiohead/1997 - OK Computer.png", "Radiohead/1997 - OK Computer.JPG",
                  "Radiohead/2000 - Kid A.txt", "Radiohead/2000 - Kid A.pdf", "Radiohead/cover.jpg")
        _, trouves = self.trouver()
        ok, kid = next(iter(trouves.values()))
        self.assertEqual(ok.cover.name, "1997 - OK Computer.JPG")          # le .jpg l'emporte sur le .png
        self.assertTrue(ok.stamp)
        self.assertIsNone(kid.cover)

    def test_une_image_seule_dit_qu_un_album_manque(self):
        self.album("Radiohead", "The Bends", annee="1995")
        self.dire("Radiohead/1997 - OK Computer.jpg", "Radiohead/cover.jpg", "Radiohead/artist.png", "Radiohead/1995 - The Bends.jpg")
        albums, trouves = self.trouver()
        manquant, = trouves[albums[0].artist_id]
        self.assertEqual((manquant.year, manquant.title, manquant.cover.name), ("1997", "OK Computer", "1997 - OK Computer.jpg"))          # The Bends est possédé

    def test_un_album_deja_possede_n_est_pas_manquant(self):
        self.album("Radiohead", "The Bends", annee="1995")
        self.dire("Radiohead/1995 - The Bends.txt", "Radiohead/1997 - OK Computer.txt")
        _, trouves = self.trouver()
        self.assertEqual([w.title for w in next(iter(trouves.values()))], ["OK Computer"])

    def test_les_signes_qu_un_nom_de_fichier_ne_peut_pas_porter(self):
        self.album("Marvin Gaye", "What's Going On?", annee="1971")
        self.dire("Marvin Gaye/1971 - What's Going On.txt")
        _, trouves = self.trouver()
        self.assertEqual(trouves, {})

    def test_meme_titre_une_autre_annee_reste_manquant(self):
        # Une réédition ou un autre album de même nom : l'année tranche.
        self.album("Genesis", "Genesis", annee="1983")
        self.dire("Genesis/1997 - Genesis.txt")
        _, trouves = self.trouver()
        self.assertEqual([w.year for w in next(iter(trouves.values()))], ["1997"])

    def test_dossier_d_artiste_au_dessus_d_un_dossier_de_rangement(self):
        self.album("Radiohead", "The Bends", annee="1995")
        studio = self.racine / "Radiohead" / "Studio"
        studio.mkdir()
        (self.racine / "Radiohead" / "The Bends").rename(studio / "The Bends")
        self.dire("Radiohead/1997 - OK Computer.txt")
        _, trouves = self.trouver()
        self.assertEqual([w.title for w in next(iter(trouves.values()))], ["OK Computer"])

    def test_la_racine_n_est_pas_un_artiste(self):
        self.album("Radiohead", "The Bends", annee="1995")
        self.dire("1997 - OK Computer.txt")
        _, trouves = self.trouver()
        self.assertEqual(trouves, {})

    def test_un_artiste_sans_album_n_a_rien_a_montrer(self):
        self.album("Radiohead", "The Bends", annee="1995")
        self.dire("Portishead/1994 - Dummy.txt")
        _, trouves = self.trouver()
        self.assertEqual(trouves, {})


if __name__ == "__main__":
    unittest.main()
