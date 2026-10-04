"""L'étagère : parcours des sections, séries et volumes, numéros, tomes manquants, catalogue."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.books import shelf
from tests.test_books_readers import COMICINFO, make_cbz, make_epub


def ficher(sous_dossier, nom, **info):
    """Un volume détaché du disque, avec la fiche donnée."""
    chemin = Path("/lib") / sous_dossier / nom
    volume = shelf.Volume(chemin, f"{sous_dossier}/{nom}", "Manga", "Serie", "", 10, 1, "cbz")
    volume.info = info
    return volume


def serie(*volumes):
    s = shelf.Series("Manga", "Serie", list(volumes))
    s.sort()
    return s


class TestIndicesDuNom(unittest.TestCase):
    def test_numero_du_nom(self):
        cas = {"Tome 01": "1", "Tome 1": "1", "1 - L'anomalie": "1", "28.La rue maudite": "28", "T3": "3",
               "Tome 001 (1975-01)": "1", "Vol. 12": "12", "#7": "7", "Tome 0,5": "0.5", "10": "10",
               "21st Century Boys": None, "Illustrations File": None, "Tintin 5": None, "": None}
        for nom, attendu in cas.items():
            with self.subTest(nom=nom):
                self.assertEqual(shelf.name_hints(nom).get("Number"), attendu)

    def test_date_du_nom(self):
        self.assertEqual(shelf.name_hints("Tome 001 (1975-01)"), {"Number": "1", "Year": 1975, "Month": 1})
        self.assertNotIn("Year", shelf.name_hints("Tome 1 (1975-13)"))

    def test_la_fiche_l_emporte_sur_le_nom(self):
        volume = ficher("Serie", "Tome 05.cbz", Number="6", Title="Titre")
        self.assertEqual(volume.number, "6")
        self.assertEqual(volume.title, "Titre")

    def test_sans_fiche_le_nom_fait_foi(self):
        volume = ficher("Serie", "Tome 05.cbz")
        self.assertEqual((volume.number, volume.title), ("5", "Tome 05"))


class TestOrdre(unittest.TestCase):
    def test_tomes_dans_l_ordre_numerique(self):
        s = serie(*(ficher("Serie", f"Tome {n}.cbz") for n in (10, 2, 1)))
        self.assertEqual([v.stem for v in s.volumes], ["Tome 1", "Tome 2", "Tome 10"])

    def test_numerotes_avant_les_autres(self):
        s = serie(ficher("Serie", "Hors serie.cbz"), ficher("Serie", "Tome 2.cbz"), ficher("Serie", "Tome 1.cbz"))
        self.assertEqual([v.stem for v in s.volumes], ["Tome 1", "Tome 2", "Hors serie"])

    def test_sous_dossiers_d_abord(self):
        a, b = ficher("Serie", "Tome 1.cbz"), ficher("Serie", "Tome 1.cbz")
        a.sub, b.sub = "2 - Suite", "1 - Debut"
        self.assertEqual(serie(a, b).volumes, [b, a])


class TestSerie(unittest.TestCase):
    def test_auteurs_par_frequence_sans_doublon(self):
        s = serie(ficher("S", "1.cbz", Writer="A, B", Penciller="B"), ficher("S", "2.cbz", Writer="B", Penciller="C"))
        self.assertEqual(s.authors, ["B", "A", "C"])

    def test_editeur_le_plus_frequent(self):
        s = serie(ficher("S", "1.cbz", Publisher="Glénat"), ficher("S", "2.cbz", Publisher="Kana"), ficher("S", "3.cbz", Publisher="Glénat"))
        self.assertEqual(s.publisher, "Glénat")

    def test_annees(self):
        s = serie(ficher("S", "1.cbz", Year=2001), ficher("S", "2.cbz", Year=1999), ficher("S", "3.cbz"))
        self.assertEqual(s.years, (1999, 2001))
        self.assertIsNone(serie(ficher("S", "1.cbz")).years)

    def test_resume_du_premier_volume_qui_en_a_un(self):
        premier, second = ficher("S", "1.cbz"), ficher("S", "2.cbz", Summary="Il était une fois")
        self.assertEqual(serie(premier, second).summary, ("Il était une fois", second))
        self.assertEqual(serie(premier).summary, ("", None))

    def test_genres(self):
        s = serie(ficher("S", "1.cbz", Genre="Sport, Football"), ficher("S", "2.cbz", Genre="Sport"))
        self.assertEqual(s.genres[0], "Sport")

    def test_identifiant_stable_et_propre_a_la_section(self):
        a, b = shelf.Series("Manga", "Akira"), shelf.Series("BD", "Akira")
        self.assertEqual(a.id, shelf.Series("Manga", "Akira").id)
        self.assertNotEqual(a.id, b.id)


class TestManquants(unittest.TestCase):
    def tomes(self, numeros, total, serie_fiche="Tsubasa"):
        return serie(*(ficher("S", f"{n}.cbz", Number=str(n), Count=total, Series=serie_fiche) for n in numeros))

    def test_numeros_manquants(self):
        self.assertEqual(self.tomes([1, 2, 5], 6).missing(), [("Tsubasa", [3, 4, 6], 6)])

    def test_serie_complete(self):
        self.assertEqual(self.tomes([1, 2, 3], 3).missing(), [])

    def test_un_tome_sans_numero_interdit_de_conclure(self):
        s = serie(ficher("S", "1.cbz", Number="1", Count=4), ficher("S", "Integrale.cbz", Count=4, Title="Intégrale"))
        self.assertEqual(s.missing(), [])

    def test_total_absurde_ou_unique_ignore(self):
        self.assertEqual(self.tomes([1], 1).missing(), [])
        self.assertEqual(self.tomes([1], 99999).missing(), [])

    def test_sans_total(self):
        self.assertEqual(serie(ficher("S", "1.cbz", Number="1")).missing(), [])

    def test_hors_serie_decimal_ne_comble_rien(self):
        s = serie(ficher("S", "1.cbz", Number="1", Count=3), ficher("S", "1b.cbz", Number="1.5", Count=3))
        self.assertEqual(s.missing(), [("", [2, 3], 3)])

    def test_cycles_comptes_a_part(self):
        s = serie(ficher("S", "1.cbz", Number="1", Count=2, Series="Cycle A"), ficher("S", "2.cbz", Number="2", Count=2, Series="Cycle A"),
                  ficher("S", "3.cbz", Number="1", Count=3, Series="Cycle B"))
        self.assertEqual(s.missing(), [("Cycle B", [2, 3], 3)])


class TestParcours(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def toucher(self, rel, contenu=b"x"):
        chemin = self.racine / rel
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(contenu)
        return chemin

    def noms(self, sections):
        return {nom: {s.name: [v.rel for v in s.volumes] for s in series} for nom, series in sections}

    def test_sections_series_et_volumes(self):
        self.toucher("Manga/Akira/Tome 2.cbz")
        self.toucher("Manga/Akira/Tome 1.cbz")
        self.toucher("BD/Megalex/1 - L'anomalie.cbz")
        self.assertEqual(self.noms(shelf.scan(self.racine)), {
            "Manga": {"Akira": ["Manga/Akira/Tome 1.cbz", "Manga/Akira/Tome 2.cbz"]},
            "BD": {"Megalex": ["BD/Megalex/1 - L'anomalie.cbz"]}})

    def test_collection_est_une_sous_section(self):
        # Comics/_DC regroupe des séries : chaque sous-dossier est une série, rangée dans "Comics · DC".
        self.toucher("Comics/_DC/Batman/Tome 1.cbz")
        self.toucher("Comics/_DC/Batman/Tome 2.cbz")
        self.toucher("Comics/_DC/Aquaman/Tome 1.cbz")
        self.toucher("Comics/_Marvel/Avengers/Tome 1.cbz")
        self.toucher("Comics/_Marvel/Un one-shot.cbz")
        self.toucher("Comics/Sandman/Tome 1.cbz")
        self.assertEqual(self.noms(shelf.scan(self.racine)), {
            "Comics": {"Sandman": ["Comics/Sandman/Tome 1.cbz"]},
            "Comics · DC": {"Aquaman": ["Comics/_DC/Aquaman/Tome 1.cbz"], "Batman": ["Comics/_DC/Batman/Tome 1.cbz", "Comics/_DC/Batman/Tome 2.cbz"]},
            "Comics · Marvel": {"Avengers": ["Comics/_Marvel/Avengers/Tome 1.cbz"], "Un one-shot": ["Comics/_Marvel/Un one-shot.cbz"]}})

    def test_collections_rangees_juste_apres_leur_section(self):
        for rel in ("Comics/_Marvel/X/1.cbz", "Comics/_DC/X/1.cbz", "Comics/Y/1.cbz", "Romans/Z/1.epub", "BD/W/1.cbz", "Manga/V/1.cbz"):
            self.toucher(rel)
        self.assertEqual([nom for nom, _ in shelf.scan(self.racine)], ["Manga", "BD", "Comics", "Comics · DC", "Comics · Marvel", "Romans"])

    def test_meme_nom_dans_deux_collections_deux_series(self):
        self.toucher("Comics/_DC/Aliens/1.cbz")
        self.toucher("Comics/_Marvel/Aliens/1.cbz")
        series = [s for _, ss in shelf.scan(self.racine) for s in ss]
        self.assertEqual(len({s.id for s in series}), 2)
        self.assertEqual({s.collection for s in series}, {"DC", "Marvel"})

    def test_la_collection_ne_s_applique_qu_au_premier_niveau(self):
        # Un "_Cycle" plus bas n'est qu'un sous-dossier de la série, pas une collection.
        self.toucher("BD/Sambre/_Cycle/1.cbz")
        ((nom, [serie]),) = shelf.scan(self.racine)
        self.assertEqual((nom, serie.name, serie.volumes[0].sub), ("BD", "Sambre", "_Cycle"))

    def test_ordre_des_sections(self):
        for section in ("Zoo", "Romans", "Manga", "Comics", "BD", "Aaa"):
            self.toucher(f"{section}/X/1.cbz")
        self.toucher("loose.epub")
        self.assertEqual([nom for nom, _ in shelf.scan(self.racine)], ["Manga", "BD", "Comics", "Romans", "Aaa", "Zoo", "Autres"])

    def test_sous_dossiers_restent_dans_la_serie(self):
        self.toucher("BD/Sambre/Sambre/2 - Troisieme generation/9 - Nos yeux.cbz")
        self.toucher("BD/Sambre/Sambre/1 - Premiere/1 - Debut.cbz")
        ((_, [sambre]),) = shelf.scan(self.racine)
        self.assertEqual([(v.sub, v.stem) for v in sambre.volumes], [("Sambre/1 - Premiere", "1 - Debut"), ("Sambre/2 - Troisieme generation", "9 - Nos yeux")])

    def test_fichier_seul_dans_sa_section_est_sa_propre_serie(self):
        self.toucher("Manuels/Un guide.mobi")
        self.toucher("Manuels/Autre guide.epub")
        self.assertEqual(self.noms(shelf.scan(self.racine)), {"Manuels": {"Un guide": ["Manuels/Un guide.mobi"], "Autre guide": ["Manuels/Autre guide.epub"]}})

    def test_fichiers_a_la_racine(self):
        self.toucher("Game Engine Black Book.epub")
        self.assertEqual(self.noms(shelf.scan(self.racine)), {"Autres": {"Game Engine Black Book": ["Game Engine Black Book.epub"]}})

    def test_pdf_ignores_par_defaut(self):
        self.toucher("Manga/Akira/Tome 1.cbz")
        self.toucher("Manga/Akira/Guide.pdf")
        self.toucher("Manuels/Un guide.PDF")
        self.toucher("Livre.pdf")
        self.assertEqual(self.noms(shelf.scan(self.racine)), {"Manga": {"Akira": ["Manga/Akira/Tome 1.cbz"]}})

    def test_pdf_comptes_sur_demande(self):
        self.toucher("Manga/Akira/Tome 1.cbz")
        self.toucher("Manga/Akira/Guide.pdf")
        self.toucher("Manuels/Un guide.PDF")
        self.toucher("Livre.pdf")
        self.assertEqual(self.noms(shelf.scan(self.racine, include_pdf=True)), {
            "Manga": {"Akira": ["Manga/Akira/Tome 1.cbz", "Manga/Akira/Guide.pdf"]},
            "Manuels": {"Un guide": ["Manuels/Un guide.PDF"]},
            "Autres": {"Livre": ["Livre.pdf"]}})

    def test_ce_qui_n_est_pas_un_livre_est_ignore(self):
        for rel in ("Manga/Akira/Thumbs.db", "Manga/Akira/notes.txt", "Manga/Akira/folder.jpg", "Romans/X/metadata.opf", "A recuperer.xlsx"):
            self.toucher(rel)
        self.toucher("Manga/Akira/Tome 1.cbz")
        self.assertEqual(self.noms(shelf.scan(self.racine)), {"Manga": {"Akira": ["Manga/Akira/Tome 1.cbz"]}})

    def test_dossiers_techniques_ignores(self):
        # __Data__ (nos propres pages), __En cours (ce qui n'est pas encore rangé), la corbeille du NAS, les vignettes DSM, les instantanés.
        for dossier in ("__Data__", "__En cours", "#recycle", "@eaDir", "#snapshot", ".cache"):
            self.toucher(f"{dossier}/Serie/1.cbz")
            self.toucher(f"Manga/{dossier}/1.cbz")
        self.toucher("Manga/Akira/1.cbz")
        self.assertEqual(self.noms(shelf.scan(self.racine)), {"Manga": {"Akira": ["Manga/Akira/1.cbz"]}})

    def test_extension_sans_casse(self):
        self.toucher("Manga/Akira/Tome 1.CBZ")
        self.assertEqual(shelf.scan(self.racine)[0][1][0].volumes[0].kind, "cbz")

    def test_series_triees_sans_accent_ni_casse(self):
        for nom in ("Élodie", "akira", "Zorro", "Bleach"):
            self.toucher(f"Manga/{nom}/1.cbz")
        self.assertEqual([s.name for s in shelf.scan(self.racine)[0][1]], ["akira", "Bleach", "Élodie", "Zorro"])

    def test_taille_et_date_relevees(self):
        chemin = self.toucher("Manga/Akira/1.cbz", b"12345")
        volume = shelf.scan(self.racine)[0][1][0].volumes[0]
        self.assertEqual((volume.size, volume.mtime), (5, int(chemin.stat().st_mtime)))

    def test_dossier_vide_ou_absent(self):
        self.assertEqual(shelf.scan(self.racine), [])
        self.assertEqual(shelf.scan(self.racine / "absent"), [])


class TestLecture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def volumes(self, **options):
        return [v for _, series in shelf.scan(self.racine, **options) for s in series for v in s.volumes]

    def test_cbz_epub_et_pdf(self):
        make_cbz(self.racine / "Manga/A/1.cbz", COMICINFO)
        make_epub(self.racine / "Romans/B/Livre.epub")
        (self.racine / "Manuels").mkdir()
        (self.racine / "Manuels/Guide.pdf").write_bytes(b"%PDF")
        par_nom = {v.stem: v for v in self.volumes(include_pdf=True)}
        for volume in par_nom.values():
            shelf.read_info(volume)
        self.assertEqual(par_nom["1"].info["Series"], "Captain Tsubasa")
        self.assertEqual(par_nom["Livre"].info["Writer"], "Alain Damasio")
        self.assertEqual(par_nom["Guide"].info, {})                  # un pdf n'a que son nom
        self.assertTrue(all(v.error is None for v in par_nom.values()))

    def test_fichier_illisible_garde_son_erreur(self):
        (self.racine / "Manga/A").mkdir(parents=True)
        (self.racine / "Manga/A/1.cbz").write_bytes(b"coupe")
        (volume,) = self.volumes()
        shelf.read_info(volume)
        self.assertEqual(volume.info, {})
        self.assertIn("archive illisible", volume.error)

    def test_une_erreur_passee_est_effacee_a_la_relecture(self):
        make_cbz(self.racine / "Manga/A/1.cbz", COMICINFO)
        (volume,) = self.volumes()
        volume.error = "ancienne"
        shelf.read_info(volume)
        self.assertIsNone(volume.error)

    def test_couverture_selon_le_format(self):
        make_cbz(self.racine / "Manga/A/1.cbz", COMICINFO)
        (self.racine / "Manuels").mkdir()
        (self.racine / "Manuels/Guide.pdf").write_bytes(b"%PDF")
        par_nom = {v.stem: v for v in self.volumes(include_pdf=True)}
        shelf.read_info(par_nom["1"])
        self.assertIsNotNone(shelf.read_cover(par_nom["1"]))
        self.assertIsNone(shelf.read_cover(par_nom["Guide"]))


class TestCatalogue(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        make_cbz(self.racine / "Manga/A/1.cbz", COMICINFO)
        make_cbz(self.racine / "Manga/A/2.cbz")

    def volumes(self):
        return [v for _, series in shelf.scan(self.racine) for s in series for v in s.volumes]

    def test_aller_retour(self):
        volumes = self.volumes()
        for v in volumes:
            shelf.read_info(v)
        chemin = self.racine / "catalog.json"
        chemin.write_text(shelf.dump_catalog(volumes), encoding="utf-8")

        relus = self.volumes()
        restant = shelf.apply_catalog(relus, shelf.load_catalog(chemin))
        self.assertEqual(restant, [])
        self.assertEqual(relus[0].info["Series"], "Captain Tsubasa")

    def test_fichier_modifie_est_a_relire(self):
        volumes = self.volumes()
        for v in volumes:
            shelf.read_info(v)
        chemin = self.racine / "catalog.json"
        chemin.write_text(shelf.dump_catalog(volumes), encoding="utf-8")
        make_cbz(self.racine / "Manga/A/1.cbz", COMICINFO.replace("Glénat", "Kana"), pages=("a.png", "b.png", "c.png"))
        relus = self.volumes()
        restant = shelf.apply_catalog(relus, shelf.load_catalog(chemin))
        self.assertEqual([v.stem for v in restant], ["1"])

    def test_illisible_pas_garde(self):
        (self.racine / "Manga/A/3.cbz").write_bytes(b"coupe")
        volumes = self.volumes()
        for v in volumes:
            shelf.read_info(v)
        self.assertNotIn("Manga/A/3.cbz", shelf.dump_catalog(volumes))      # relu au prochain passage

    def test_catalogue_absent_corrompu_ou_d_une_autre_version(self):
        chemin = self.racine / "catalog.json"
        self.assertEqual(shelf.load_catalog(chemin), {})
        chemin.write_text("{pas du json", encoding="utf-8")
        self.assertEqual(shelf.load_catalog(chemin), {})
        chemin.write_text('{"version": 0, "volumes": {"a": {}}}', encoding="utf-8")
        self.assertEqual(shelf.load_catalog(chemin), {})
        chemin.write_text("[]", encoding="utf-8")
        self.assertEqual(shelf.load_catalog(chemin), {})

    def test_entree_deformee_ignoree(self):
        volumes = self.volumes()
        restant = shelf.apply_catalog(volumes, {v.rel: {"size": v.size, "mtime": v.mtime, "info": "pas un dict"} for v in volumes})
        self.assertEqual(restant, volumes)

    def test_dump_deterministe(self):
        volumes = self.volumes()
        for v in volumes:
            shelf.read_info(v)
        self.assertEqual(shelf.dump_catalog(volumes), shelf.dump_catalog(list(reversed(volumes))))


class TestUnites(unittest.TestCase):
    def test_unites(self):
        self.assertEqual(shelf.unit("Manga", 1), "1 tome")
        self.assertEqual(shelf.unit("Manga", 12), "12 tomes")
        self.assertEqual(shelf.unit("Romans", 2), "2 livres")
        self.assertEqual(shelf.unit("Magazines", 3), "3 numéros")


if __name__ == "__main__":
    unittest.main()
