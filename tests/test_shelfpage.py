"""Pages de l'étagère : ce que montrent le sommaire et la page d'une série, et leur relecture comme cache de couvertures."""

import re
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.books import shelf, shelfpage
from tests.test_shelf import ficher

URI = "data:image/jpeg;base64,QUJD"


def tomes(section="Manga", nom="Captain Tsubasa", numeros=(1, 2, 5), total=6, **extra):
    s = shelf.Series(section, nom)
    for n in numeros:
        v = ficher("S", f"Tome {n}.cbz", Number=str(n), Count=total, Series=nom, Title=f"Tome {n}",
                   Writer="Yôichi Takahashi", Publisher="Glénat", Year=2000 + n, Genre="Football, Sport",
                   Summary=f"Le match {n}", PageCount=178, **extra)
        v.section, v.group, v.rel = section, nom, f"{section}/{nom}/Tome {n}.cbz"
        s.volumes.append(v)
    s.sort()
    return s


class TestPlages(unittest.TestCase):
    def test_ranges(self):
        cas = {(3, 5, 6, 7, 12): "3, 5–7, 12", (5, 6): "5, 6", (1, 2, 3): "1–3", (4,): "4", (): ""}
        for numeros, attendu in cas.items():
            with self.subTest(numeros=numeros):
                self.assertEqual(shelfpage.ranges(numeros), attendu)


class TestNomsDePage(unittest.TestCase):
    def test_nom_lisible_et_identifiant(self):
        s = tomes(nom="Locke & Key")
        self.assertEqual(shelfpage.page_name(s), f"Locke & Key-{s.id}.html")

    def test_caracteres_interdits_retires(self):
        self.assertTrue(shelfpage.page_name(shelf.Series("BD", 'Qui? "Quoi": <ça>')).startswith("Qui Quoi ça-"))

    def test_deux_sections_deux_pages(self):
        self.assertNotEqual(shelfpage.page_name(shelf.Series("Manga", "Akira")), shelfpage.page_name(shelf.Series("BD", "Akira")))

    def test_lien_encode_et_relatif(self):
        s = tomes(nom="Locke & Key")
        self.assertEqual(unquote(shelfpage.href(s)), f"Series/{shelfpage.page_name(s)}")
        self.assertNotIn(" ", shelfpage.href(s))

    def test_nom_vide(self):
        self.assertTrue(shelfpage.page_name(shelf.Series("BD", "???")).startswith("serie-"))


class TestSommaire(unittest.TestCase):
    def render(self, sections=None, covers=None, pages=None, titre="Livres"):
        sections = sections or [("Manga", [tomes()])]
        ids = {s.id for _, ss in sections for s in ss} if pages is None else pages
        return shelfpage.build_index(titre, sections, covers or {}, ids)

    def test_titre_resume_et_sections(self):
        html = self.render([("Manga", [tomes(), tomes(nom="Akira")]), ("Romans", [tomes("Romans", "Camus", (1,), 1)])])
        self.assertIn("<title>Livres</title>", html)
        self.assertIn("3 séries · 7 volumes", html)
        self.assertIn("Manga<span class='cnt'>2 · 6 tomes</span>", html)
        self.assertIn("Romans<span class='cnt'>1 · 1 livre</span>", html)

    def test_collection_est_une_section_comptee_comme_sa_section(self):
        s = tomes("Comics", "Batman", (1, 2, 3), 3)
        s.collection = "DC"
        html = shelfpage.build_index("Livres", [("Comics · DC", [s])], {}, {s.id})
        self.assertIn("Comics · DC<span class='cnt'>1 · 3 tomes</span>", html)

    def test_vignette_lien_ancre_et_progression(self):
        s = tomes()
        html = self.render([("Manga", [s])])
        self.assertIn(f"href='{shelfpage.href(s)}' id='s{s.id}'", html)
        self.assertIn("<div class='y warn'>3/6 tomes</div>", html)          # il en manque : mis en avant

    def test_serie_complete_sans_alerte(self):
        html = self.render([("Manga", [tomes(numeros=(1, 2, 3), total=3)])])
        self.assertIn("<div class='y'>3 tomes</div>", html)

    def test_couverture_integree_ou_monogramme(self):
        s = tomes()
        avec = self.render([("Manga", [s])], covers={s.id: URI})
        self.assertIn(f"<img data-img='{s.cover_volume.key}' src='{URI}'", avec)
        sans = self.render([("Manga", [s])])
        self.assertIn("<div class='noimg mono' style='background:#", sans)
        self.assertIn(">CT</div>", sans)

    def test_page_absente_vignette_inerte(self):
        html = self.render(pages=set())
        self.assertNotIn("<a class='bk'", html)
        self.assertIn("<div class='bk' data-s=", html)

    def test_recherche_dans_auteur_editeur_et_genre(self):
        html = self.render()
        recherche = re.search(r"data-s='([^']*)'", html).group(1)
        for mot in ("Captain Tsubasa", "Yôichi Takahashi", "Glénat", "Football"):
            self.assertIn(mot, recherche)

    def test_texte_echappe(self):
        s = tomes(nom="L'Œil <b>&\"")
        html = self.render([("Manga", [s])])
        self.assertNotIn("<b>", html)
        self.assertIn("L&#39;Œil &lt;b&gt;&amp;\"", html)          # les attributs sont entre apostrophes : seule l'apostrophe est dangereuse

    def test_infobulle_resume_tronque(self):
        s = tomes(numeros=(1,), total=1)
        s.volumes[0].info["Summary"] = "mot " * 200
        infobulle = re.search(r"title='([^']*)'", self.render([("Manga", [s])])).group(1)
        self.assertTrue(infobulle.endswith("…"))
        self.assertLessEqual(len(infobulle), shelfpage.SUMMARY_LIMIT + 1)

    def test_sans_resume_l_infobulle_cite_les_auteurs(self):
        s = tomes(numeros=(1,), total=1)
        del s.volumes[0].info["Summary"]
        self.assertIn("title='Yôichi Takahashi'", self.render([("Manga", [s])]))

    def test_html_bien_forme(self):
        html = self.render([("Manga", [tomes()]), ("BD", [tomes("BD", "Megalex", (1,), 1)])], covers={})
        # Le seul XML qu'on peut vérifier ici : les icônes, en SVG.
        icone = re.search(r"href='data:image/svg\+xml,([^']+)'", html).group(1)
        ElementTree.fromstring(unquote(icone))
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertEqual(html.count("<section>"), html.count("</section>"))


class TestPageDeSerie(unittest.TestCase):
    def render(self, s=None, images=None):
        return shelfpage.build_series(s or tomes(), images or {}, "../index.html", "Livres")

    def test_titre_et_retour(self):
        s = tomes()
        html = self.render(s)
        self.assertIn("<title>Captain Tsubasa</title>", html)
        self.assertIn(f"<a class='back' href='../index.html#s{s.id}'>← Livres</a>", html)

    def test_en_tete(self):
        html = self.render()
        self.assertIn("Manga · Glénat · 2001–2005 · 3 tomes", html)
        self.assertIn("<div class='by'>Yôichi Takahashi</div>", html)
        self.assertIn("Football, Sport", html)

    def test_collection_dans_l_en_tete(self):
        s = tomes("Comics", "Batman")
        s.collection = "DC"
        self.assertIn("Comics · DC · Glénat", self.render(s))

    def test_resume_du_premier_tome(self):
        html = self.render()
        self.assertIn("<div class='o'>Le match 1</div>", html)
        self.assertIn("Résumé de « Tome 1 »", html)

    def test_numeros_manquants(self):
        self.assertIn("Manque : 3, 4, 6 <span>(sur 6, d'après les fiches)</span>", self.render())

    def test_pas_d_alerte_pour_une_serie_complete(self):
        self.assertNotIn("Manque", self.render(tomes(numeros=(1, 2, 3), total=3)))

    def test_cycles_nommes(self):
        s = tomes(numeros=(1,), total=3, nom="Cycle B")
        s.name = "Sambre"
        s.volumes += tomes(numeros=(1, 2), total=2, nom="Cycle A").volumes      # complet : rien à en dire
        s.sort()
        html = self.render(s)
        self.assertIn("Manque : Cycle B : 2, 3 ", html)
        self.assertNotIn("Cycle A :", html)

    def test_cycles_pas_de_progression_globale(self):
        s = tomes(numeros=(1,), total=3, nom="Cycle B")
        s.volumes += tomes(numeros=(1, 2), total=2, nom="Cycle A").volumes
        s.sort()
        html = shelfpage.build_index("Livres", [("Manga", [s])], {}, {s.id})
        self.assertIn("<div class='y'>3 tomes</div>", html)             # pas "1/3"

    def test_une_carte_par_volume_avec_sa_couverture(self):
        s = tomes()
        images = {s.volumes[1].key: URI}
        html = self.render(s, images)
        self.assertEqual(html.count("<div class='aff'>"), 4)         # 3 volumes + la couverture de l'en-tête
        self.assertEqual(html.count(f"src='{URI}'"), 1)
        self.assertIn("2002 · 178 p.", html)

    def test_volumes_groupes_par_sous_dossier(self):
        s = tomes(numeros=(1, 2), total=2)
        s.volumes[0].sub, s.volumes[1].sub = "1 - Premier cycle", "2 - Magnakaï"
        html = self.render(s)
        self.assertIn("<h2>1 - Premier cycle<span class='cnt'>1</span></h2>", html)
        self.assertIn("<h2>2 - Magnakaï<span class='cnt'>1</span></h2>", html)

    def test_pas_de_titre_de_groupe_sans_sous_dossier(self):
        self.assertNotIn("<h2>", self.render())

    def test_volume_illisible_signale(self):
        s = tomes(numeros=(1,), total=1)
        s.volumes[0].error = "archive illisible : coupee"
        html = self.render(s)
        self.assertIn("class='bk bad'", html)
        self.assertIn("illisible : archive illisible : coupee", html)

    def test_pdf_montre_son_format(self):
        s = tomes(numeros=(1,), total=1)
        s.volumes[0].kind = "pdf"
        self.assertIn("2001 · 178 p. · PDF", self.render(s))


class TestCache(unittest.TestCase):
    def test_couvertures_relues_dans_la_page_ecrite(self):
        s = tomes()
        images = {v.key: shelfpage.data_uri(f"jpeg{i}".encode()) for i, v in enumerate(s.volumes)}
        with tempfile.TemporaryDirectory() as d:
            page = Path(d) / "p.html"
            page.write_text(shelfpage.build_series(s, images, "../index.html", "Livres"), encoding="utf-8")
            self.assertEqual(shelfpage.read_embedded(page), images)

    def test_page_absente(self):
        self.assertEqual(shelfpage.read_embedded(Path(tempfile.gettempdir()) / "n-existe-pas.html"), {})

    def test_la_cle_change_quand_le_fichier_change(self):
        a, b = ficher("S", "1.cbz"), ficher("S", "1.cbz")
        b.mtime += 1
        self.assertNotEqual(a.key, b.key)
        c = ficher("S", "1.cbz")
        c.size += 1
        self.assertNotEqual(a.key, c.key)


if __name__ == "__main__":
    unittest.main()
