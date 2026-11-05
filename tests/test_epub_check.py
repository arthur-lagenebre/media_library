"""Contrôler et nettoyer les .epub : libraries/books/epubhealth.py, epubclean.py, et les scripts Books/Verify_Epub.py et Clean_Epub.py.

Les livres sont fabriqués dans un dossier temporaire, octet par octet : aucun réseau, aucun outil externe.
"""

import io
import sys
import tempfile
import unittest
import warnings
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.books import epub, epubclean, epubhealth
from libraries.books.archive import BookError, is_parasite
from scripts.Books import Clean_Epub, Verify_Epub

STORED, DEFLATED = zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED
MIMETYPE = b"application/epub+zip"

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

OPF3 = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">urn:uuid:1234</dc:identifier>
    <dc:title>Le Livre</dc:title>
    <dc:language>fr</dc:language>
    <dc:creator>Auteur</dc:creator>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
    <meta name="calibre:series" content="La Série"/>
    <meta name="calibre:series_index" content="2.0"/>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="ch1"/></spine>
</package>"""

OPF2 = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">urn:uuid:1234</dc:identifier>
    <dc:title>Le Livre</dc:title>
    <dc:language>fr</dc:language>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx"><itemref idref="ch1"/></spine>
</package>"""

XHTML = '<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>c</title></head><body><p>{}</p></body></html>'
CH1 = XHTML.format("Chapitre un")
NAV = XHTML.format("Sommaire")
NCX = '<?xml version="1.0"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><navMap/></ncx>'

DIRTY_LINES = "    <dc:date>0101-01-01T00:00:00+00:00</dc:date>\n    <dc:publisher></dc:publisher>\n    <dc:subject/>\n"


def dirty(opf=OPF3):
    """L'.opf avec la date « zéro » de Calibre et deux éléments vides, avant `</metadata>`."""
    return opf.replace("  </metadata>", DIRTY_LINES + "  </metadata>")


def standard(opf=OPF3):
    return [
        ("mimetype", MIMETYPE, STORED),
        ("META-INF/container.xml", CONTAINER.encode(), DEFLATED),
        ("OEBPS/content.opf", opf.encode(), DEFLATED),
        ("OEBPS/nav.xhtml", NAV.encode(), DEFLATED),
        ("OEBPS/ch1.xhtml", CH1.encode(), STORED),
    ]


def replacing(entries, name, data=None, kind=None):
    """`entries` avec l'entrée `name` changée (ou retirée quand `data` est None)."""
    return [(n, data if n == name and data is not None else d, kind if n == name and kind is not None else k)
            for n, d, k in entries if not (n == name and data is None and kind is None)]


def write_book(path, entries, extra=None):
    """Écrit les entrées telles quelles : l'ordre, le mode de compression et les doublons sont ceux qu'on donne."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")                          # zipfile prévient d'un nom en double : c'est le but
        with zipfile.ZipFile(path, "w") as z:
            for name, data, kind in entries:
                info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
                info.compress_type = kind
                info.extra = (extra or {}).get(name, b"")
                z.writestr(info, data)
    return Path(path)


def messages(path):
    return [d.message for d in epubhealth.audit(path)]


def snapshot(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in Path(folder).rglob("*") if p.is_file()}


class EpubTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def book(self, entries=None, name="livre.epub", **kwargs):
        return write_book(self.dir / name, entries if entries is not None else standard(), **kwargs)


class TestResidus(unittest.TestCase):
    def test_noms_de_residus(self):
        for name in ("__MACOSX/OEBPS/._ch1.xhtml", "__MACOSX/", ".DS_Store", "OEBPS/.DS_Store", "Thumbs.db", "OEBPS/images/thumbs.db",
                     "iTunesMetadata.plist", "META-INF/calibre_bookmarks.txt", "OEBPS/._cover.jpg", "desktop.ini"):
            with self.subTest(name):
                self.assertTrue(is_parasite(name))

    def test_vrais_fichiers_ne_sont_pas_des_residus(self):
        for name in ("mimetype", "META-INF/container.xml", "META-INF/encryption.xml", "OEBPS/ch1.xhtml", "OEBPS/images/cover.jpg", "OEBPS/styles.css"):
            with self.subTest(name):
                self.assertFalse(is_parasite(name))


class TestAudit(EpubTestCase):
    def test_un_livre_sain_n_a_aucun_defaut(self):
        self.assertEqual(messages(self.book()), [])

    def test_un_epub2_sain(self):
        entries = replacing(replacing(standard(OPF2), "OEBPS/nav.xhtml"), "OEBPS/ch1.xhtml", CH1.encode()) + [("OEBPS/toc.ncx", NCX.encode(), DEFLATED)]
        self.assertEqual(messages(self.book(entries)), [])

    def test_fichier_qui_n_est_pas_un_zip(self):
        path = self.dir / "faux.epub"
        path.write_bytes(b"ceci n'est pas un zip")
        self.assertEqual(len(messages(path)), 1)
        self.assertIn("archive illisible", messages(path)[0])

    def test_archive_tronquee(self):
        path = self.book()
        path.write_bytes(path.read_bytes()[:-30])
        self.assertIn("archive illisible", messages(path)[0])

    def test_entree_corrompue_est_vue_par_son_crc(self):
        path = self.book()
        path.write_bytes(path.read_bytes().replace(b"Chapitre un", b"Chapitre uX", 1))           # ch1.xhtml est stocké : un octet change, le CRC non
        self.assertTrue(any("CRC" in m and "ch1.xhtml" in m for m in messages(path)))

    def test_mimetype_absent(self):
        defects = epubhealth.audit(self.book(replacing(standard(), "mimetype")))
        self.assertEqual([(d.message, d.fixable) for d in defects], [("mimetype absent", True)])

    def test_mimetype_absent_sans_conteneur_n_est_pas_reparable(self):
        entries = replacing(replacing(standard(), "mimetype"), "META-INF/container.xml")
        defects = epubhealth.audit(self.book(entries))
        self.assertEqual(defects[0].message, "mimetype absent")
        self.assertFalse(defects[0].fixable)

    def test_mimetype_pas_en_premier(self):
        entries = standard()
        entries.append(entries.pop(0))
        defects = epubhealth.audit(self.book(entries))
        self.assertEqual([(d.message, d.fixable) for d in defects], [("mimetype n'est pas la première entrée de l'archive", True)])

    def test_mimetype_compresse(self):
        defects = epubhealth.audit(self.book(replacing(standard(), "mimetype", kind=DEFLATED)))
        self.assertEqual([(d.message, d.fixable) for d in defects], [("mimetype est compressé (il doit être stocké tel quel)", True)])

    def test_mimetype_avec_un_champ_extra(self):
        defects = epubhealth.audit(self.book(extra={"mimetype": b"\xaa\xaa\x00\x00"}))
        self.assertEqual([d.message for d in defects], ["mimetype porte un champ « extra » (interdit)"])

    def test_mimetype_au_mauvais_contenu(self):
        defects = epubhealth.audit(self.book(replacing(standard(), "mimetype", MIMETYPE + b"\n")))
        self.assertEqual(len(defects), 1)
        self.assertIn("au lieu de application/epub+zip", defects[0].message)
        self.assertTrue(defects[0].fixable)

    def test_entree_en_double(self):
        defects = epubhealth.audit(self.book(standard() + [("OEBPS/ch1.xhtml", CH1.encode(), DEFLATED)]))
        self.assertEqual([(d.message, d.fixable) for d in defects], [("entrée en double : OEBPS/ch1.xhtml", True)])

    def test_nom_d_entree_dangereux(self):
        messages_ = messages(self.book(standard() + [("../evil.txt", b"x", DEFLATED), ("/abs.txt", b"x", DEFLATED)]))
        self.assertIn("nom d'entrée dangereux : ../evil.txt", messages_)
        self.assertIn("nom d'entrée dangereux : /abs.txt", messages_)

    def test_sans_conteneur(self):
        self.assertIn("epub sans .opf lisible", messages(self.book(replacing(standard(), "META-INF/container.xml")))[0])

    def test_fichier_du_manifeste_absent(self):
        defects = epubhealth.audit(self.book(replacing(standard(), "OEBPS/ch1.xhtml")))
        self.assertEqual([(d.message, d.fixable) for d in defects], [("fichier du manifeste absent de l'archive : ch1.xhtml", False)])

    def test_href_avec_espace_encode_et_ancre(self):
        opf = OPF3.replace('href="ch1.xhtml"', 'href="mon%20ch.xhtml#debut"')
        entries = replacing(standard(opf), "OEBPS/ch1.xhtml") + [("OEBPS/mon ch.xhtml", CH1.encode(), DEFLATED)]
        self.assertEqual(messages(self.book(entries)), [])

    def test_ressource_distante_n_est_pas_cherchee_dans_l_archive(self):
        opf = OPF3.replace("</manifest>", '<item id="web" href="https://exemple.org/x.png" media-type="image/png"/></manifest>')
        self.assertEqual(messages(self.book(standard(opf))), [])

    def test_id_en_double_dans_le_manifeste(self):
        opf = OPF3.replace("</manifest>", '<item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/></manifest>')
        self.assertIn("id en double dans le manifeste : ch1", messages(self.book(standard(opf))))

    def test_spine_vide_ou_qui_cite_un_inconnu(self):
        self.assertIn("spine vide ou absent", messages(self.book(standard(OPF3.replace('<itemref idref="ch1"/>', "")))))
        self.assertIn("spine : « fantome » n'est pas dans le manifeste", messages(self.book(standard(OPF3.replace('idref="ch1"', 'idref="fantome"')))))

    def test_epub3_sans_navigation_ni_date_de_modification(self):
        found = messages(self.book(standard(OPF3.replace(' properties="nav"', "").replace('<meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>', ""))))
        self.assertIn("EPUB 3 sans document de navigation (properties=\"nav\")", found)
        self.assertIn("EPUB 3 sans dcterms:modified", found)

    def test_epub2_toc_absent_ou_inconnu(self):
        entries = replacing(replacing(standard(OPF2), "OEBPS/nav.xhtml"), "OEBPS/ch1.xhtml", CH1.encode()) + [("OEBPS/toc.ncx", NCX.encode(), DEFLATED)]
        sans = OPF2.replace(' toc="ncx"', "")
        self.assertIn("EPUB 2 : le spine n'a pas d'attribut toc", messages(self.book(replacing(entries, "OEBPS/content.opf", sans.encode()))))
        faux = OPF2.replace('toc="ncx"', 'toc="zzz"')
        self.assertIn("EPUB 2 : toc « zzz » n'est pas dans le manifeste", messages(self.book(replacing(entries, "OEBPS/content.opf", faux.encode()))))

    def test_version_inconnue(self):
        self.assertIn("version EPUB inconnue : « 9.0 »", messages(self.book(standard(OPF3.replace('version="3.0"', 'version="9.0"')))))

    def test_titre_langue_et_identifiant(self):
        self.assertIn("dc:title absent ou vide", messages(self.book(standard(OPF3.replace("<dc:title>Le Livre</dc:title>", "<dc:title> </dc:title>")))))
        self.assertIn("dc:language absent ou vide", messages(self.book(standard(OPF3.replace("<dc:language>fr</dc:language>", "")))))
        self.assertIn("dc:identifier absent ou vide", messages(self.book(standard(OPF3.replace('<dc:identifier id="uid">urn:uuid:1234</dc:identifier>', "")))))
        self.assertIn("<package> sans unique-identifier", messages(self.book(standard(OPF3.replace(' unique-identifier="uid"', "")))))
        self.assertIn("unique-identifier « autre » ne désigne aucun dc:identifier", messages(self.book(standard(OPF3.replace('unique-identifier="uid"', 'unique-identifier="autre"')))))

    def test_xhtml_mal_forme(self):
        entries = replacing(standard(), "OEBPS/ch1.xhtml", XHTML.format("<b>jamais fermé").encode())
        found = messages(self.book(entries))
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].startswith("XML mal formé : ch1.xhtml ("))

    def test_entite_html_sans_doctype_est_une_erreur(self):
        self.assertTrue(messages(self.book(replacing(standard(), "OEBPS/ch1.xhtml", XHTML.format("a&nbsp;b").encode()))))

    def test_entite_html_avec_doctype_est_admise(self):
        doc = ('<?xml version="1.0"?><!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">'
               '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>c</title></head><body><p>a&nbsp;b &eacute; &amp; &lt;</p></body></html>')
        self.assertEqual(messages(self.book(replacing(standard(), "OEBPS/ch1.xhtml", doc.encode()))), [])

    def test_doctype_ne_masque_pas_un_vrai_defaut(self):
        doc = '<?xml version="1.0"?><!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"><body><p>a&nbsp;b<b></p></body></html>'
        self.assertTrue(messages(self.book(replacing(standard(), "OEBPS/ch1.xhtml", doc.encode()))))

    def test_defauts_de_la_fiche_sont_reparables(self):
        defects = epubhealth.audit(self.book(standard(dirty())))
        self.assertEqual([(d.message, d.fixable) for d in defects], [
            ("date inconnue (0101-01-01T00:00:00+00:00) : le « zéro » de Calibre", True),
            ("élément vide : dc:publisher", True),
            ("élément vide : dc:subject", True),
        ])

    def test_residus(self):
        entries = standard() + [("__MACOSX/._ch1.xhtml", b"x", DEFLATED), (".DS_Store", b"x", DEFLATED), ("META-INF/calibre_bookmarks.txt", b"x", DEFLATED)]
        defects = epubhealth.audit(self.book(entries))
        self.assertEqual(len(defects), 1)
        self.assertTrue(defects[0].fixable)
        self.assertIn("résidus à retirer (3) : __MACOSX/._ch1.xhtml, .DS_Store, META-INF/calibre_bookmarks.txt", defects[0].message)

    def test_un_residu_que_le_manifeste_declare_est_garde(self):
        opf = OPF3.replace("</manifest>", '<item id="db" href="Thumbs.db" media-type="application/octet-stream"/></manifest>')
        self.assertEqual(messages(self.book(standard(opf) + [("OEBPS/Thumbs.db", b"x", DEFLATED)])), [])

    def test_beaucoup_de_residus_sont_resumes(self):
        entries = standard() + [(f"__MACOSX/{n}", b"x", DEFLATED) for n in range(10)]
        self.assertIn("résidus à retirer (10) : __MACOSX/0, __MACOSX/1, __MACOSX/2, …", messages(self.book(entries))[0])


class TestFixOpf(unittest.TestCase):
    def test_retire_la_date_zero_et_les_elements_vides_et_rien_d_autre(self):
        fixed, notes = epubclean.fix_opf(dirty().encode())
        self.assertEqual(fixed, OPF3.encode())
        self.assertEqual(notes, ["1 date inconnue (« zéro » de Calibre) retirée(s)", "élément(s) vide(s) retiré(s) : dc:publisher, dc:subject"])

    def test_une_vraie_date_est_gardee(self):
        opf = OPF3.replace("  </metadata>", "    <dc:date>2004-03-12T23:00:00+00:00</dc:date>\n  </metadata>")
        self.assertEqual(epubclean.fix_opf(opf.encode()), (opf.encode(), []))

    def test_rien_a_faire_rend_les_memes_octets(self):
        self.assertEqual(epubclean.fix_opf(OPF3.encode()), (OPF3.encode(), []))

    def test_titre_langue_identifiant_et_champs_calibre_ne_sont_jamais_retires(self):
        opf = OPF3.replace("<dc:title>Le Livre</dc:title>", "<dc:title></dc:title>").replace("<dc:language>fr</dc:language>", "<dc:language/>")
        fixed, notes = epubclean.fix_opf(opf.encode())
        self.assertEqual((fixed, notes), (opf.encode(), []))
        self.assertIn(b"calibre:series", fixed)

    def test_fins_de_ligne_windows(self):
        crlf = dirty().replace("\n", "\r\n")
        self.assertEqual(epubclean.fix_opf(crlf.encode())[0], OPF3.replace("\n", "\r\n").encode())

    def test_element_vide_avec_attributs(self):
        opf = OPF3.replace("  </metadata>", '    <dc:creator opf:role="aut"></dc:creator>\n    <dc:rights xml:lang="fr" />\n  </metadata>')
        fixed, notes = epubclean.fix_opf(opf.encode())
        self.assertEqual(fixed, OPF3.encode())
        self.assertEqual(notes, ["élément(s) vide(s) retiré(s) : dc:creator, dc:rights"])

    def test_prefixe_dublin_core_different(self):
        opf = OPF3.replace("xmlns:dc=", "xmlns:dcns=").replace("dc:", "dcns:").replace("  </metadata>", "    <dcns:publisher/>\n  </metadata>")
        fixed, _ = epubclean.fix_opf(opf.encode())
        self.assertNotIn(b"publisher", fixed)

    def test_encodage_declare_respecte(self):
        opf = dirty().replace('encoding="utf-8"', 'encoding="iso-8859-1"').replace("La Série", "La Série")
        fixed, _ = epubclean.fix_opf(opf.encode("iso-8859-1"))
        self.assertEqual(fixed, OPF3.replace('encoding="utf-8"', 'encoding="iso-8859-1"').encode("iso-8859-1"))

    def test_bom_conserve(self):
        data = b"\xef\xbb\xbf" + dirty().encode()
        self.assertEqual(epubclean.fix_opf(data)[0], b"\xef\xbb\xbf" + OPF3.encode())

    def test_encodage_illisible_laisse_le_fichier_tel_quel(self):
        data = dirty().replace('encoding="utf-8"', 'encoding="inconnu-9"').encode()
        self.assertEqual(epubclean.fix_opf(data), (data, []))
        data = b"\xff\xfe" + dirty().encode("utf-16-le")
        self.assertEqual(epubclean.fix_opf(data), (data, []))


class TestPlan(EpubTestCase):
    def test_livre_sain_rien_a_faire(self):
        self.assertTrue(epubclean.plan(self.book()).empty)

    def test_plan_complet(self):
        entries = replacing(standard(dirty()), "mimetype", kind=DEFLATED) + [(".DS_Store", b"x", DEFLATED), ("OEBPS/ch1.xhtml", CH1.encode(), DEFLATED)]
        plan = epubclean.plan(self.book(entries))
        self.assertEqual(plan.residues, (".DS_Store",))
        self.assertEqual(plan.archive, ("mimetype est compressé (il doit être stocké tel quel)", "entrée en double (la dernière est gardée) : OEBPS/ch1.xhtml"))
        self.assertEqual(len(plan.metadata), 2)
        self.assertEqual(plan.opf_path, "OEBPS/content.opf")
        self.assertEqual(len(plan.lines()), 5)

    def test_fix_restreint_le_plan(self):
        entries = standard(dirty()) + [(".DS_Store", b"x", DEFLATED)]
        path = self.book(replacing(entries, "mimetype", kind=DEFLATED))
        self.assertEqual(epubclean.plan(path, ("residues",)).archive, ())
        self.assertEqual(epubclean.plan(path, ("residues",)).metadata, ())
        self.assertEqual(epubclean.plan(path, ("archive",)).residues, ())
        self.assertEqual(epubclean.plan(path, ("metadata",)).residues, ())
        self.assertTrue(epubclean.plan(path, ("metadata",)).metadata)

    def test_archive_illisible(self):
        path = self.dir / "faux.epub"
        path.write_bytes(b"pas un zip")
        with self.assertRaises(BookError):
            epubclean.plan(path)

    def test_sans_opf_les_residus_se_retirent_quand_meme(self):
        entries = [("mimetype", MIMETYPE, STORED), (".DS_Store", b"x", DEFLATED), ("a.txt", b"x", DEFLATED)]
        plan = epubclean.plan(self.book(entries))
        self.assertEqual((plan.residues, plan.metadata), ((".DS_Store",), ()))


class TestNettoyage(EpubTestCase):
    def clean(self, path, fixes=epubclean.FIXES, keep_backup=True):
        plan = epubclean.plan(path, fixes)
        return plan, epubclean.apply(path, plan, keep_backup)

    def contents(self, path):
        with zipfile.ZipFile(path) as z:
            return {n: z.read(n) for n in z.namelist()}

    def test_un_livre_sale_devient_sain_et_garde_son_contenu(self):
        entries = replacing(standard(dirty()), "mimetype", kind=DEFLATED)
        entries = [entries[-1]] + entries[:-1] + [("__MACOSX/._x", b"x", DEFLATED), (".DS_Store", b"x", DEFLATED)]
        path = self.book(entries)
        before = self.contents(path)
        fiche = epub.read_info(path)
        self.assertTrue(messages(path))
        _, backup = self.clean(path)
        self.assertEqual(messages(path), [])
        self.assertEqual(epub.read_info(path), fiche)
        after = self.contents(path)
        self.assertEqual(set(before) - set(after), {"__MACOSX/._x", ".DS_Store"})
        for name in after:
            if name != "OEBPS/content.opf":
                self.assertEqual(after[name], before[name], name)
        self.assertEqual(after["OEBPS/content.opf"], OPF3.encode())
        self.assertEqual(backup.name, "livre.epub.bak")
        self.assertEqual(self.contents(backup), before)

    def test_mimetype_en_premier_stocke_et_exact(self):
        path = self.book(replacing(standard(), "mimetype", MIMETYPE + b"\n", DEFLATED)[::-1])
        self.clean(path)
        with zipfile.ZipFile(path) as z:
            first = z.infolist()[0]
            self.assertEqual((first.filename, first.compress_type, z.read(first), first.extra), ("mimetype", STORED, MIMETYPE, b""))

    def test_mimetype_absent_est_ajoute(self):
        path = self.book(replacing(standard(), "mimetype"))
        self.clean(path)
        self.assertEqual(messages(path), [])
        self.assertEqual(zipfile.ZipFile(path).namelist()[0], "mimetype")

    def test_doublon_la_derniere_entree_est_gardee(self):
        path = self.book(standard() + [("OEBPS/ch1.xhtml", XHTML.format("Version finale").encode(), DEFLATED)])
        self.clean(path)
        self.assertEqual(self.contents(path)["OEBPS/ch1.xhtml"], XHTML.format("Version finale").encode())
        self.assertEqual(messages(path), [])

    def test_un_residu_declare_par_le_manifeste_reste(self):
        opf = OPF3.replace("</manifest>", '<item id="db" href="Thumbs.db" media-type="application/octet-stream"/></manifest>')
        path = self.book(standard(opf) + [("OEBPS/Thumbs.db", b"x", DEFLATED), (".DS_Store", b"x", DEFLATED)])
        self.clean(path)
        self.assertEqual(set(self.contents(path)) & {"OEBPS/Thumbs.db", ".DS_Store"}, {"OEBPS/Thumbs.db"})

    def test_sans_sauvegarde(self):
        path = self.book(standard() + [(".DS_Store", b"x", DEFLATED)])
        _, backup = self.clean(path, keep_backup=False)
        self.assertIsNone(backup)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["livre.epub"])

    def test_une_sauvegarde_existante_n_est_jamais_ecrasee(self):
        path = self.book(standard() + [(".DS_Store", b"x", DEFLATED)])
        (self.dir / "livre.epub.bak").write_bytes(b"ancienne sauvegarde")
        _, backup = self.clean(path)
        self.assertEqual(backup.name, "livre.epub.bak2")
        self.assertEqual((self.dir / "livre.epub.bak").read_bytes(), b"ancienne sauvegarde")

    def test_un_second_passage_ne_change_rien(self):
        path = self.book(standard(dirty()) + [(".DS_Store", b"x", DEFLATED)])
        self.clean(path)
        propre = path.read_bytes()
        self.assertTrue(epubclean.plan(path).empty)
        self.assertEqual(path.read_bytes(), propre)

    def test_fix_residues_seul_ne_repare_pas_le_reste(self):
        path = self.book(replacing(standard(dirty()), "mimetype", kind=DEFLATED) + [(".DS_Store", b"x", DEFLATED)])
        self.clean(path, ("residues",))
        found = messages(path)
        self.assertTrue(any("mimetype est compressé" in m for m in found))
        self.assertTrue(any("date inconnue" in m for m in found))
        self.assertFalse(any("résidus" in m for m in found))

    def test_les_dates_et_droits_des_entrees_sont_conserves(self):
        path = self.book(standard() + [(".DS_Store", b"x", DEFLATED)])
        self.clean(path)
        with zipfile.ZipFile(path) as z:
            self.assertEqual({i.date_time for i in z.infolist()}, {(2020, 1, 1, 0, 0, 0)})
            self.assertEqual({i.filename: i.compress_type for i in z.infolist()}["OEBPS/ch1.xhtml"], STORED)

    def test_controle_qui_refuse_l_original_ne_bouge_pas(self):
        path = self.book(standard() + [(".DS_Store", b"x", DEFLATED)])
        avant = path.read_bytes()
        with mock.patch.object(epubclean, "verify_rewrite", side_effect=BookError("refusé")):
            with self.assertRaises(BookError):
                epubclean.apply(path, epubclean.plan(path))
        self.assertEqual(path.read_bytes(), avant)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["livre.epub"])

    def test_controle_reel_refuse_un_contenu_modifie(self):
        path = self.book(standard() + [(".DS_Store", b"x", DEFLATED)])
        real = epubclean.rewrite

        def tricheur(source, destination, wanted):
            real(source, destination, wanted)
            with zipfile.ZipFile(destination, "a") as z:
                z.writestr("intrus.txt", b"x")

        avant = path.read_bytes()
        with mock.patch.object(epubclean, "rewrite", tricheur), self.assertRaises(BookError):
            epubclean.apply(path, epubclean.plan(path))
        self.assertEqual(path.read_bytes(), avant)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["livre.epub"])

    def test_echange_en_echec_remet_l_original(self):
        path = self.book(standard() + [(".DS_Store", b"x", DEFLATED)])
        avant = path.read_bytes()
        reel = Path.rename

        def refuse(self, target):
            if self.name.endswith(".part"):
                raise OSError("disque plein")
            return reel(self, target)

        with mock.patch.object(Path, "rename", refuse), self.assertRaises(OSError):
            epubclean.apply(path, epubclean.plan(path))
        self.assertEqual(path.read_bytes(), avant)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["livre.epub"])


class ScriptTestCase(EpubTestCase):
    def run_script(self, module, *argv):
        """(code de sortie, affichage)."""
        ligne = [str(Path(module.__file__)), "--dir", str(self.dir), *argv]
        with mock.patch.object(sys, "argv", ligne), redirect_stdout(io.StringIO()) as texte:
            try:
                code = module.main()
            except SystemExit as e:
                code = e.code
        return code, texte.getvalue()


class TestVerifyEpub(ScriptTestCase):
    def test_dossier_de_livres_sains(self):
        self.book(name="a.epub")
        (self.dir / "Sous").mkdir()
        self.book(name="Sous/b.epub")
        code, texte = self.run_script(Verify_Epub)
        self.assertEqual(code, 0)
        self.assertIn("TOTAL : 2 livre(s) contrôlée(s)", texte)
        self.assertIn("0 en défaut", texte)
        self.assertIn("Aucun défaut.", (self.dir / "verification_epub.log").read_text(encoding="utf-8"))

    def test_un_livre_en_defaut_fait_sortir_en_code_1_et_est_nomme(self):
        self.book(name="bon.epub")
        self.book(replacing(standard(), "OEBPS/ch1.xhtml"), name="casse.epub")
        code, texte = self.run_script(Verify_Epub)
        self.assertEqual(code, 1)
        self.assertIn("[DÉFAUT] casse.epub", texte)
        self.assertIn("fichier du manifeste absent de l'archive : ch1.xhtml", texte)
        self.assertNotIn("[DÉFAUT] bon.epub", texte)
        self.assertIn("1 en défaut", texte)
        self.assertIn("casse.epub", (self.dir / "verification_epub.log").read_text(encoding="utf-8"))

    def test_ne_modifie_aucun_livre(self):
        self.book(standard(dirty()) + [(".DS_Store", b"x", DEFLATED)], name="sale.epub")
        avant = snapshot(self.dir)
        self.run_script(Verify_Epub)
        apres = snapshot(self.dir)
        apres.pop("verification_epub.log")
        self.assertEqual(apres, avant)

    def test_un_defaut_par_ligne(self):
        self.book(standard(dirty()) + [(".DS_Store", b"x", DEFLATED)], name="sale.epub")
        _, texte = self.run_script(Verify_Epub)
        self.assertIn("date inconnue", texte)
        self.assertIn("élément vide : dc:publisher", texte)
        self.assertIn("résidus à retirer (1)", texte)
        self.assertIn("Clean_Epub.py", texte)

    def test_no_recursive(self):
        self.book(name="a.epub")
        (self.dir / "Sous").mkdir()
        self.book(replacing(standard(), "OEBPS/ch1.xhtml"), name="Sous/casse.epub")
        code, texte = self.run_script(Verify_Epub, "--no-recursive")
        self.assertEqual(code, 0)
        self.assertIn("1 livre(s)", texte)

    def test_aucun_epub(self):
        code, _ = self.run_script(Verify_Epub)
        self.assertIn("Aucun .epub", code)

    def test_journal_ailleurs(self):
        self.book()
        self.run_script(Verify_Epub, "--log", str(self.dir / "mon.log"))
        self.assertTrue((self.dir / "mon.log").is_file())
        self.assertFalse((self.dir / "verification_epub.log").exists())


class TestCleanEpub(ScriptTestCase):
    def sale(self, name="sale.epub"):
        return self.book(standard(dirty()) + [(".DS_Store", b"x", DEFLATED)], name=name)

    def test_simulation_n_ecrit_rien(self):
        self.sale()
        self.book(name="propre.epub")
        avant = snapshot(self.dir)
        code, texte = self.run_script(Clean_Epub)
        self.assertEqual(code, 0)
        self.assertEqual(snapshot(self.dir), avant)
        self.assertIn("SIMULATION", texte)
        self.assertIn("sale.epub", texte)
        self.assertNotIn("propre.epub", texte)
        self.assertIn("retirer 1 résidu(s) : .DS_Store", texte)
        self.assertIn("TOTAL : 2 livre(s) vus, 1 à nettoyer, 1 déjà propre(s).", texte)

    def test_apply_nettoie_et_garde_l_original(self):
        sale = self.sale()
        original = sale.read_bytes()
        code, texte = self.run_script(Clean_Epub, "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(messages(sale), [])
        self.assertEqual((self.dir / "sale.epub.bak").read_bytes(), original)
        self.assertIn("[OK] nettoyé, original gardé : sale.epub.bak", texte)
        self.assertIn("TOTAL : 1 livre(s) vus, 1 nettoyé(s), 0 déjà propre(s).", texte)
        self.assertIn("1 original(aux) gardé(s) en .bak", texte)
        self.assertFalse((self.dir / "sale.epub.part").exists())

    def test_apply_sans_sauvegarde(self):
        self.sale()
        code, texte = self.run_script(Clean_Epub, "--apply", "--no-backup")
        self.assertEqual(code, 0)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["sale.epub"])
        self.assertNotIn(".bak", texte)

    def test_un_second_passage_ne_change_rien(self):
        self.sale()
        self.run_script(Clean_Epub, "--apply")
        avant = snapshot(self.dir)
        code, texte = self.run_script(Clean_Epub, "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(snapshot(self.dir), avant)
        self.assertIn("0 nettoyé(s), 1 déjà propre(s)", texte)

    def test_les_sauvegardes_ne_sont_pas_des_livres(self):
        self.sale()
        self.run_script(Clean_Epub, "--apply")
        _, texte = self.run_script(Clean_Epub)
        self.assertIn("TOTAL : 1 livre(s) vus", texte)

    def test_fix_choisit_les_corrections(self):
        sale = self.sale()
        self.run_script(Clean_Epub, "--apply", "--fix", "residues")
        found = messages(sale)
        self.assertTrue(any("date inconnue" in m for m in found))
        self.assertFalse(any("résidus" in m for m in found))

    def test_fix_inconnu_est_refuse(self):
        self.sale()
        avant = snapshot(self.dir)
        with mock.patch("sys.stderr", io.StringIO()) as erreur:
            code, _ = self.run_script(Clean_Epub, "--apply", "--fix", "tout")
        self.assertEqual(code, 2)
        self.assertIn("--fix attend des corrections parmi residues, archive, metadata, pas 'tout'", erreur.getvalue())
        self.assertEqual(snapshot(self.dir), avant)

    def test_archive_illisible_n_est_pas_touchee_et_sort_en_code_1(self):
        faux = self.dir / "faux.epub"
        faux.write_bytes(b"pas un zip")
        code, texte = self.run_script(Clean_Epub, "--apply")
        self.assertEqual(code, 1)
        self.assertEqual(faux.read_bytes(), b"pas un zip")
        self.assertIn("[NON TRAITÉ] faux.epub", texte)
        self.assertIn("1 livre(s) illisible(s), non touché(s)", texte)

    def test_echec_du_controle_est_signale_et_le_livre_reste_intact(self):
        sale = self.sale()
        avant = sale.read_bytes()
        with mock.patch.object(epubclean, "verify_rewrite", side_effect=BookError("la fiche a changé")):
            code, texte = self.run_script(Clean_Epub, "--apply")
        self.assertEqual(code, 1)
        self.assertEqual(sale.read_bytes(), avant)
        self.assertIn("[ÉCHEC] la fiche a changé (le livre n'a pas été modifié)", texte)
        self.assertIn("1 réécriture(s) en échec", texte)

    def test_aucun_epub(self):
        code, _ = self.run_script(Clean_Epub)
        self.assertIn("Aucun .epub", code)


if __name__ == "__main__":
    unittest.main()
