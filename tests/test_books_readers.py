"""Lecture des livres : ComicInfo.xml d'un .cbz, .opf d'un .epub, couvertures, miniatures."""

import io
import struct
import sys
import tempfile
import unittest
import zlib
import zipfile
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.books import archive, cbz, comicinfo, epub, thumbs

COMICINFO = """<?xml version="1.0"?>
<ComicInfo xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Title>Grand final à Paris</Title>
  <Series>Captain Tsubasa</Series>
  <Number>28</Number>
  <Count>37</Count>
  <Year>2015</Year>
  <Month>4</Month>
  <Writer>Yôichi Takahashi</Writer>
  <Publisher>Glénat</Publisher>
  <Genre>Football, Sport</Genre>
  <PageCount>178</PageCount>
  <Summary></Summary>
  <Pages>
    <Page Image="0" Type="Story" />
    <Page Image="1" Type="FrontCover" />
  </Pages>
</ComicInfo>"""


def png(width=4, height=6, color=(200, 30, 30)):
    """Un PNG valide, sans Pillow : de quoi servir de page ou de couverture."""
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    rows = b"".join(b"\x00" + bytes(color) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def make_cbz(path, info=None, pages=("001.png", "002.png"), colors=None, size=(4, 6)):
    """Un .cbz minimal : des pages (de `size` pixels), et un ComicInfo.xml si `info` est donné."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for i, name in enumerate(pages):
            z.writestr(name, png(*size, color=(colors or {}).get(name, (200, 30, 30 + i))))
        if info is not None:
            z.writestr("ComicInfo.xml", info)
    return path


OPF = """<?xml version='1.0' encoding='utf-8'?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uuid_id" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>La horde du Contrevent</dc:title>
    <dc:creator opf:file-as="Damasio, Alain" opf:role="aut">Alain Damasio</dc:creator>
    <dc:creator opf:role="trl">Un Traducteur</dc:creator>
    <dc:contributor opf:role="bkp">calibre (3.15.0)</dc:contributor>
    <dc:publisher>La Volte</dc:publisher>
    <dc:date>2004-03-12T23:00:00+00:00</dc:date>
    <dc:language>fra</dc:language>
    <dc:subject>Science-fiction</dc:subject>
    <dc:subject>Aventure</dc:subject>
    <dc:description>&lt;div&gt;Un groupe &lt;i&gt;avance&lt;/i&gt;.&lt;br/&gt;Contre le vent &amp;amp; la mort.&lt;/div&gt;</dc:description>
    <meta name="cover" content="cover-img"/>
    <meta name="calibre:series" content="Les Vents"/>
    <meta name="calibre:series_index" content="2.0"/>
  </metadata>
  <manifest>
    <item id="cover-img" href="images/cover%20page.jpg" media-type="image/jpeg"/>
    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
</package>"""

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""


def make_epub(path, opf=OPF, cover=b"COVER", container=CONTAINER):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        if cover is not None:
            z.writestr("OEBPS/images/cover page.jpg", cover)
    return path


class TestComicInfo(unittest.TestCase):
    def test_champs_lus(self):
        info = comicinfo.parse(COMICINFO.encode("utf-8"))
        self.assertEqual(info["Series"], "Captain Tsubasa")
        self.assertEqual(info["Title"], "Grand final à Paris")
        self.assertEqual((info["Year"], info["Month"], info["Count"], info["PageCount"]), (2015, 4, 37, 178))
        self.assertEqual(info["Number"], "28")                 # Number reste un texte : "0.5", "HS"

    def test_champ_vide_absent(self):
        self.assertNotIn("Summary", comicinfo.parse(COMICINFO.encode("utf-8")))

    def test_couverture_designee(self):
        self.assertEqual(comicinfo.parse(COMICINFO.encode("utf-8"))["FrontCover"], 1)

    def test_bom_utf8(self):
        self.assertEqual(comicinfo.parse(b"\xef\xbb\xbf" + COMICINFO.encode("utf-8"))["Series"], "Captain Tsubasa")

    def test_xml_illisible_ou_etranger_n_est_pas_une_erreur(self):
        self.assertEqual(comicinfo.parse(b"<ComicInfo><Title>x"), {})
        self.assertEqual(comicinfo.parse(b"<autre><Title>x</Title></autre>"), {})
        self.assertEqual(comicinfo.parse(b""), {})

    def test_entier_invalide_ignore(self):
        self.assertNotIn("Year", comicinfo.parse(b"<ComicInfo><Year>bientot</Year><Title>x</Title></ComicInfo>"))

    def test_valeur_d_un_numero(self):
        for texte, attendu in {"28": 28.0, " 3 ": 3.0, "0.5": 0.5, "0,5": 0.5, "HS": None, "": None, None: None, "1a": None}.items():
            with self.subTest(texte=texte):
                self.assertEqual(comicinfo.number_value(texte), attendu)


class TestArchive(unittest.TestCase):
    def test_ordre_naturel(self):
        self.assertEqual(sorted(["Tome 10", "Tome 2", "tome 1"], key=archive.natural_key), ["tome 1", "Tome 2", "Tome 10"])

    def test_pages_triees_sans_residus(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.cbz"
            with zipfile.ZipFile(path, "w") as z:
                for name in ("10.png", "2.png", "__MACOSX/2.png", "dossier/", ".cache.png", "notes.txt", "1.JPG"):
                    z.writestr(name, b"x")
            with zipfile.ZipFile(path) as z:
                self.assertEqual(archive.image_names(z), ["1.JPG", "2.png", "10.png"])

    def test_archive_tronquee(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.cbz"
            path.write_bytes(b"PK\x03\x04 pas un zip entier")
            with self.assertRaises(archive.BookError):
                archive.open_zip(path)

    def test_nom_d_entree_mal_encode(self):
        # Vu sur un .cbz réel : zipfile lève UnicodeDecodeError à l'ouverture, ce qui arrêtait tout un passage.
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.cbz"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("ééé.png", b"x")
            path.write_bytes(path.read_bytes().replace("ééé".encode("utf-8"), b"\xe1" * 6))
            with self.assertRaises(archive.BookError):
                archive.open_zip(path)

    def test_entree_absente(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.cbz"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("a.png", b"x")
            with zipfile.ZipFile(path) as z, self.assertRaises(archive.BookError):
                archive.read_member(z, "b.png", "page")

    def test_fichier_absent(self):
        with self.assertRaises(archive.BookError):
            archive.open_zip(Path(tempfile.gettempdir()) / "n-existe-pas.cbz")


class TestCbz(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_fiche(self):
        path = make_cbz(self.dir / "a.cbz", COMICINFO)
        self.assertEqual(cbz.read_info(path)["Publisher"], "Glénat")

    def test_sans_fiche(self):
        self.assertEqual(cbz.read_info(make_cbz(self.dir / "a.cbz")), {})

    def test_nom_de_la_fiche_sans_casse(self):
        path = self.dir / "a.cbz"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("comicinfo.XML", COMICINFO)
        self.assertEqual(cbz.read_info(path)["Series"], "Captain Tsubasa")

    def test_archive_illisible_est_une_erreur_de_livre(self):
        path = self.dir / "a.cbz"
        path.write_bytes(b"pas un zip")
        with self.assertRaises(archive.BookError):
            cbz.read_info(path)

    def test_couverture_par_defaut_premiere_page(self):
        path = make_cbz(self.dir / "a.cbz", pages=("2.png", "10.png", "1.png"))
        self.assertEqual(cbz.cover(path), png(color=(200, 30, 32)))       # "1.png" : la dernière écrite, la première dans l'ordre

    def test_couverture_designee_par_la_fiche(self):
        path = make_cbz(self.dir / "a.cbz", COMICINFO)
        self.assertEqual(cbz.cover(path, 1), png(color=(200, 30, 31)))

    def test_rang_hors_limites_retombe_sur_la_premiere(self):
        path = make_cbz(self.dir / "a.cbz")
        self.assertEqual(cbz.cover(path, 99), cbz.cover(path))

    def test_aucune_image(self):
        path = self.dir / "a.cbz"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("notes.txt", "x")
        self.assertIsNone(cbz.cover(path))


class TestEpub(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_fiche_aux_noms_de_comicinfo(self):
        info = epub.read_info(make_epub(self.dir / "a.epub"))
        self.assertEqual(info["Title"], "La horde du Contrevent")
        self.assertEqual(info["Writer"], "Alain Damasio")           # ni le traducteur ni le "bkp" de Calibre
        self.assertEqual(info["Publisher"], "La Volte")
        self.assertEqual((info["Year"], info["Month"], info["Day"]), (2004, 3, 12))
        self.assertEqual(info["Genre"], "Science-fiction, Aventure")
        self.assertEqual((info["Series"], info["Number"]), ("Les Vents", "2"))

    def test_description_en_texte(self):
        self.assertEqual(epub.read_info(make_epub(self.dir / "a.epub"))["Summary"], "Un groupe avance.\nContre le vent & la mort.")

    def test_date_inconnue_de_calibre_n_est_pas_une_annee(self):
        opf = OPF.replace("2004-03-12T23:00:00+00:00", "0101-01-01T00:00:00+00:00")
        self.assertNotIn("Year", epub.read_info(make_epub(self.dir / "a.epub", opf)))

    def test_couverture_declaree(self):
        self.assertEqual(epub.cover(make_epub(self.dir / "a.epub", cover=b"IMG")), b"IMG")     # href encodé, relatif à l'.opf

    def test_couverture_d_epub3(self):
        opf = OPF.replace('<meta name="cover" content="cover-img"/>', "").replace(
            'media-type="image/jpeg"/>', 'media-type="image/jpeg" properties="cover-image"/>')
        self.assertEqual(epub.cover(make_epub(self.dir / "a.epub", opf, cover=b"E3")), b"E3")

    def test_pas_de_couverture(self):
        opf = OPF.replace('<meta name="cover" content="cover-img"/>', "").replace('id="cover-img"', 'id="img1"')
        self.assertIsNone(epub.cover(make_epub(self.dir / "a.epub", opf)))

    def test_couverture_declaree_mais_absente_de_l_archive(self):
        self.assertIsNone(epub.cover(make_epub(self.dir / "a.epub", cover=None)))

    def test_epub_sans_opf(self):
        path = self.dir / "a.epub"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("mimetype", "application/epub+zip")
        with self.assertRaises(archive.BookError):
            epub.read_info(path)

    def test_opf_sans_metadata(self):
        self.assertEqual(epub.parse_opf(ElementTree.fromstring("<package xmlns='http://www.idpf.org/2007/opf'/>")), {})

    def test_texte_brut(self):
        self.assertEqual(epub.plain_text("<p>Un</p><p>  deux   mots </p>"), "Un\ndeux mots")
        self.assertEqual(epub.plain_text(None), "")


@unittest.skipUnless(thumbs.available(), "Pillow n'est pas installé")
class TestMiniatures(unittest.TestCase):
    def dimensions(self, data):
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            return image.format, image.size

    def test_reduit_en_gardant_les_proportions(self):
        jpeg = thumbs.thumbnail(png(1000, 1500), width=100)
        self.assertEqual(self.dimensions(jpeg), ("JPEG", (100, 150)))

    def test_une_petite_image_n_est_pas_agrandie(self):
        self.assertEqual(self.dimensions(thumbs.thumbnail(png(40, 60), width=100))[1], (40, 60))

    def test_image_illisible(self):
        self.assertIsNone(thumbs.thumbnail(b"pas une image"))


class TestSansPillow(unittest.TestCase):
    def test_pas_de_miniature(self):
        from unittest import mock
        with mock.patch.object(thumbs, "Image", None):
            self.assertFalse(thumbs.available())
            self.assertIsNone(thumbs.thumbnail(png()))


if __name__ == "__main__":
    unittest.main()
