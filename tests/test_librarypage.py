"""Pages de la médiathèque musicale : ce que montrent le sommaire et la fiche d'un album, et leur relecture comme cache de pochettes."""

import re
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common.filenames import safe_name
from libraries.music import library, librarypage
from tests.test_library import MBID, piste

URI = "data:image/jpeg;base64,QUJD"


class PageTestCase(unittest.TestCase):
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


class TestFormats(unittest.TestCase):
    def test_horloge(self):
        for secondes, attendu in ((0, ""), (None, ""), (5, "0:05"), (222, "3:42"), (3723, "1:02:03"), (59.6, "1:00")):
            with self.subTest(secondes=secondes):
                self.assertEqual(librarypage.clock(secondes), attendu)

    def test_duree(self):
        for secondes, attendu in ((10, ""), (2880, "48 min"), (3600, "1 h"), (4320, "1 h 12 min"), (36000, "10 h")):
            with self.subTest(secondes=secondes):
                self.assertEqual(librarypage.length(secondes), attendu)

    def test_pistes(self):
        self.assertEqual((librarypage.tracks_label(1), librarypage.tracks_label(13)), ("1 piste", "13 pistes"))


class TestNomsDePage(PageTestCase):
    def test_nom_lisible_et_identifiant(self):
        album = self.un()
        self.assertEqual(librarypage.page_name(album), f"Daft Punk - Discovery-{album.id}.html")

    def test_caracteres_interdits_retires(self):
        album = self.un(artiste="AC/DC", titre='Who Made Who? "Live"')
        self.assertTrue(librarypage.page_name(album).startswith("ACDC - Who Made Who Live-"))

    def test_lien_encode_et_relatif(self):
        album = self.un(titre="Un titre & des espaces")
        lien = librarypage.href(album)
        self.assertTrue(lien.startswith("Albums/"))
        self.assertNotIn(" ", lien)
        self.assertEqual(unquote(lien), f"Albums/{librarypage.page_name(album)}")


class TestSommaire(PageTestCase):
    def sommaire(self, **kw):
        sections = library.sections(self.albums())
        pages = {r.id for _, releases in sections for r in releases}
        return librarypage.build_index("Musique", sections, {}, pages if kw.get("pages", True) else set())

    def test_une_section_par_artiste_a_plusieurs_albums(self):
        self.album("Daft Punk", "Homework", annee="1997")
        self.album("Daft Punk", "Discovery")
        self.album("Kavinsky", "Outrun", annee="2013")
        html = self.sommaire()
        self.assertEqual(re.findall(r"<h2[^>]*>(.*?)<span", html), ["Daft Punk", "Autres artistes"])
        self.assertLess(html.index("Homework"), html.index("Discovery"))

    def test_resume(self):
        self.album("Daft Punk", "Homework", annee="1997")
        self.album("Kavinsky", "Outrun")
        self.assertIn("2 albums · 2 artistes · 6 pistes", self.sommaire())

    def test_la_pochette_mene_a_la_fiche(self):
        album = self.un()
        html = self.sommaire()
        self.assertIn(f"id='{librarypage.anchor(album)}'", html)
        self.assertIn(f"href='{librarypage.href(album)}'", html)

    def test_sans_fiche_la_pochette_reste_inerte(self):
        self.album()
        html = self.sommaire(pages=False)
        self.assertNotIn("href='Albums/", html)
        self.assertNotIn("<a class='al'", html)

    def test_monogramme_sans_pochette(self):
        self.album(titre="Discovery")
        self.assertIn("class='noimg mono'", self.sommaire())

    def test_pochette_encodee_dans_la_page(self):
        album = self.un()
        html = librarypage.build_index("Musique", library.sections([album]), {album.id: URI}, {album.id})
        self.assertIn(f"<img data-img='{album.key}' src='{URI}'", html)

    def test_pistes_manquantes_en_orange(self):
        self.album(pistes=(1, 2), total=6)
        html = self.sommaire()
        self.assertIn("<div class='y warn'>2001 · 2/6 pistes</div>", html)

    def test_albums_seuls_montrent_leur_artiste_et_se_rangent_par_artiste(self):
        self.album("Kavinsky", "Outrun")
        html = self.sommaire()
        self.assertIn("<div class='a'>Kavinsky</div>", html)
        self.assertIn("data-i='K'", html)

    def test_recherche_dans_artiste_label_et_genre(self):
        self.album("Daft Punk", "Discovery", genres=("Electronic", "House"), label="Virgin")
        texte = re.search(r"data-s='([^']*)'", self.sommaire()).group(1)
        for mot in ("Discovery", "Daft Punk", "Virgin", "House"):
            self.assertIn(mot, texte)

    def test_genres_filtrables(self):
        self.album("Daft Punk", "Discovery", genres=("Electronic",))
        html = self.sommaire()
        self.assertIn("class='genre'", html)
        self.assertIn("Electronic (1)", html)
        self.assertIn("data-g='Electronic'", html)

    def test_titre_et_icone(self):
        self.album()
        html = self.sommaire()
        self.assertIn("<title>Musique</title>", html)
        self.assertIn("rel='icon'", html)

    def test_apostrophe_dans_un_titre_n_ouvre_pas_l_attribut(self):
        self.album("Air", "L'Oeil du cyclone")
        html = self.sommaire()
        self.assertIn("L&#39;Oeil du cyclone", html)
        self.assertNotIn("data-s='L'Oeil", html)


class TestFiche(PageTestCase):
    def fiche(self, album, image=None):
        return librarypage.build_release(album, image, "../index.html", "Musique")

    def test_titre_artiste_faits(self):
        html = self.fiche(self.un(mbid=MBID))
        self.assertIn("<h1>Discovery</h1>", html)
        self.assertIn("<div class='artist'>Daft Punk</div>", html)
        self.assertIn("2001 · Virgin · 3 pistes · FLAC", html)

    def test_label_sans_numero_de_catalogue(self):
        html = self.fiche(self.un(label="Craft Recordings", extra=("CATALOGNUMBER=[none]",)))
        self.assertIn("2001 · Craft Recordings · 3 pistes", html)
        self.assertNotIn("[none]", html)

    def test_label_et_numero_de_catalogue(self):
        self.assertIn("Craft Recordings (CR00123)", self.fiche(self.un(label="Craft Recordings", extra=("CATALOGNUMBER=CR00123",))))

    def test_retour_au_sommaire_sur_la_vignette(self):
        album = self.un()
        self.assertIn(f"href='../index.html#{librarypage.anchor(album)}'", self.fiche(album))

    def test_pistes_dans_l_ordre_avec_leur_duree(self):
        html = self.fiche(self.un())
        lignes = re.findall(r"<td class='n'>(\d+)</td><td>(.*?)</td><td class='d'>(.*?)</td>", html)
        self.assertEqual(lignes, [("1", "Piste 1", "0:10"), ("2", "Piste 2", "0:10"), ("3", "Piste 3", "0:10")])

    def test_pistes_manquantes_grisees_a_leur_place(self):
        html = self.fiche(self.un(pistes=(1, 2, 5), total=6))
        self.assertEqual(re.findall(r"<tr class='absent'><td class='n'>(\d+)</td>", html), ["3", "4", "6"])
        self.assertLess(html.index("Piste 2"), html.index("<tr class='absent'><td class='n'>3"))
        self.assertLess(html.index("<tr class='absent'><td class='n'>4"), html.index("Piste 5"))
        self.assertIn("Manque : pistes 3, 4, 6 <span>(sur 6, d'après les tags)</span>", html)

    def test_une_seule_piste_manquante_au_singulier(self):
        self.assertIn("Manque : piste 3 <", self.fiche(self.un(pistes=(1, 2, 4), total=4)))

    def test_album_complet_sans_manque(self):
        html = self.fiche(self.un())
        self.assertNotIn("Manque", html)
        self.assertNotIn("absent", html.split("<style>")[1].split("</style>")[1])

    def test_plusieurs_disques(self):
        for disc in (1, 2):
            piste(self.racine / "A" / f"CD{disc}", "01.flac", number=1, total=1, disc=disc, disctotal=2, title=f"D{disc}")
        html = self.fiche(self.albums()[0])
        self.assertEqual(re.findall(r"<h2>(Disque \d)", html), ["Disque 1", "Disque 2"])

    def test_disque_absent_signale(self):
        piste(self.racine / "A", "01.flac", number=1, total=1, disc=1, disctotal=2)
        self.assertIn("Manque : disque 2 ", self.fiche(self.albums()[0]))

    def test_artiste_de_piste_montre_quand_il_differe(self):
        piste(self.racine / "A", "01.flac", number=1, artist="Kavinsky", albumartist="Various Artists", title="Nightcall")
        piste(self.racine / "A", "02.flac", number=2, artist="Various Artists", albumartist="Various Artists", title="Autre")
        html = self.fiche(self.albums()[0])
        self.assertEqual(re.findall(r"<div class='by'>(.*?)</div>", html), ["Kavinsky"])

    def test_lien_musicbrainz_seulement_avec_l_identifiant(self):
        self.assertIn(f"https://musicbrainz.org/release/{MBID}", self.fiche(self.un(mbid=MBID)))

    def test_sans_identifiant_pas_de_lien(self):
        self.assertNotIn("musicbrainz", self.fiche(self.un()))

    def test_chemin_de_l_album(self):
        self.assertIn("<div class='path'>Daft Punk/Discovery</div>", self.fiche(self.un()))

    def test_pochette_ou_monogramme(self):
        album = self.un()
        self.assertIn(f"<img data-img='{album.key}' src='{URI}'", self.fiche(album, URI))
        self.assertIn("class='noimg mono'", self.fiche(album))

    def test_fichier_illisible_signale_sur_la_fiche(self):
        album = self.un()
        album.tracks[0].error = "bloc tronque"
        self.assertIn("illisible : bloc tronque", self.fiche(album))

    def test_formats_non_pris_en_charge(self):
        album = self.un()
        album.unsupported = ["04.m4a"]
        self.assertIn("Non pris en charge : 04.m4a", self.fiche(album))


class TestCache(PageTestCase):
    def test_pochettes_relues_dans_une_page_ecrite(self):
        album = self.un()
        page = self.racine / "fiche.html"
        page.write_text(librarypage.build_release(album, URI, "../index.html", "Musique"), encoding="utf-8")
        self.assertEqual(librarypage.read_embedded(page), {album.key: URI})

    def test_page_absente(self):
        self.assertEqual(librarypage.read_embedded(self.racine / "rien.html"), {})

    def test_monogramme_ne_laisse_aucune_pochette(self):
        album = self.un()
        page = self.racine / "fiche.html"
        page.write_text(librarypage.build_release(album, None, "../index.html", "Musique"), encoding="utf-8")
        self.assertEqual(librarypage.read_embedded(page), {})


if __name__ == "__main__":
    unittest.main()
