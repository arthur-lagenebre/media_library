"""Fiche d'un film : ce qu'elle montre, et qu'elle sait être relue comme cache d'images."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.video import embed, filmpage
INCEPTION = {
    "id": 27205, "title": "Inception", "release_date": "2010-07-16", "runtime": 148,
    "tagline": "Votre esprit est la scène du crime.", "overview": "Un voleur s'infiltre dans les rêves.",
    "poster_path": "/inc.jpg", "genres": [{"name": "Action"}, {"name": "Science-Fiction"}],
    "credits": {
        "crew": [{"name": "Christopher Nolan", "job": "Director"}, {"name": "Christopher Nolan", "job": "Director"},
                 {"name": "Hans Zimmer", "job": "Composer"}],
        "cast": [{"name": "Leonardo DiCaprio", "character": "Cobb", "profile_path": "/leo.jpg"},
                 {"name": "Elliot Page", "character": "Ariadne", "profile_path": None},
                 {"name": "Tom Hardy", "character": "Eames", "profile_path": "/tom.jpg"}]},
}


def render(movie=INCEPTION, images=None, **kw):
    return filmpage.build_html(movie, images or {}, "../index.html", "Films", **kw)


class TestMiseEnPage(unittest.TestCase):
    def test_en_tete_fixe_avec_retour_et_bouton(self):
        html = render()
        en_tete = html[html.index("<header class='top'>"):html.index("</header>")]
        self.assertIn("<a class='back' href='../index.html#f27205'>", en_tete)
        self.assertIn("<button class='mode'", en_tete)
        self.assertIn(".top{position:sticky;top:0", html)

    def test_pleine_largeur_ou_centree_selon_le_choix_retenu(self):
        html = render()
        self.assertIn(".wide .wrap{max-width:none}", html)
        self.assertIn("'Centrée'", html)
        # Posé dans le <head> : sinon la fiche s'afficherait centrée avant de basculer.
        self.assertLess(html.index("localStorage.getItem('wide')"), html.index("<style>"))


class TestContenu(unittest.TestCase):
    def test_titre_de_l_onglet_porte_l_annee(self):
        self.assertIn("<title>Inception (2010)</title>", render())

    def test_titre_sans_date(self):
        self.assertIn("<title>Inception</title>", render({"title": "Inception"}))

    def test_resume_realisateur_et_casting(self):
        html = render()
        self.assertIn("Un voleur s&#39;infiltre dans les rêves.", html)
        self.assertIn("De Christopher Nolan</div>", html)       # le doublon du crédit n'est cité qu'une fois
        self.assertIn("Leonardo DiCaprio", html)
        self.assertIn(">Cobb<", html)
        self.assertNotIn("Hans Zimmer", html)                   # un compositeur n'est pas un réalisateur

    def test_ligne_de_faits(self):
        self.assertIn("2010 · 148 min · Action, Science-Fiction", render())

    def test_casting_borne(self):
        html = render(limit=2)
        self.assertIn("Elliot Page", html)
        self.assertNotIn("Tom Hardy", html)

    def test_sans_casting_pas_de_section_vide(self):
        html = render({"title": "Court", "overview": "Un film."})
        self.assertNotIn("Casting", html)
        self.assertNotIn("De ", html.split("<h1>")[1])

    def test_sans_resume(self):
        self.assertIn("Pas de résumé.", render({"title": "X"}))

    def test_lien_de_retour(self):
        self.assertIn("<a class='back' href='../index.html#f27205'>← Films</a>", render())

    def test_retour_sans_identifiant_vers_l_index_seul(self):
        self.assertIn("<a class='back' href='../index.html'>", render({"title": "X"}))

    def test_ancre_de_retour_est_celle_de_la_vignette(self):
        self.assertEqual(filmpage.anchor(27205), "f27205")

    def test_retour_en_arriere_depuis_l_index(self):
        # Le script ne détourne le lien que si on vient bien de l'index : ouverte directement, la fiche suit l'ancre.
        self.assertIn("history.back()", render())
        self.assertIn("document.referrer", render())

    def test_texte_echappe(self):
        html = render({"title": "Tom & Jerry <3", "overview": "<script>x</script>"})
        self.assertIn("Tom &amp; Jerry &lt;3", html)
        self.assertNotIn("<script>x</script>", html)


class TestImages(unittest.TestCase):
    def test_affiche_et_portraits_integres(self):
        images = {"w342/inc.jpg": "data:image/jpeg;base64,AFFICHE", "w185/leo.jpg": "data:image/jpeg;base64,LEO"}
        html = render(images=images)
        self.assertIn("<img data-img='w342/inc.jpg' src='data:image/jpeg;base64,AFFICHE'", html)
        self.assertIn("<img data-img='w185/leo.jpg' src='data:image/jpeg;base64,LEO'", html)

    def test_image_manquante_remplacee(self):
        # Aucune image téléchargée : un emplacement vide pour l'affiche, un par acteur.
        self.assertEqual(render().count("<div class='noimg'></div>"), 4)

    def test_silhouette_pour_un_acteur_sans_portrait(self):
        html = render()
        self.assertIn(".actor .noimg{background:#21232b url('data:image/svg+xml,", html)
        # Une seule règle pour tous les acteurs, et pas pour l'affiche manquante : une silhouette n'a rien à faire sur une affiche.
        self.assertEqual(html.count("data:image/svg+xml"), 2)       # l'icône de l'onglet, et la silhouette
        self.assertNotIn(".head .noimg{background", html)

    def test_images_a_telecharger(self):
        self.assertEqual(filmpage.poster_images(INCEPTION), {"w342/inc.jpg": "/inc.jpg"})
        # Elliot Page n'a pas de portrait : rien à télécharger pour lui.
        self.assertEqual(filmpage.profile_images(INCEPTION), {"w185/leo.jpg": "/leo.jpg", "w185/tom.jpg": "/tom.jpg"})
        self.assertEqual(filmpage.profile_images(INCEPTION, limit=1), {"w185/leo.jpg": "/leo.jpg"})

    def test_relue_comme_cache(self):
        # La fiche écrite doit rendre ses images au passage suivant, sinon elles seraient retéléchargées chaque nuit.
        images = {"w342/inc.jpg": "data:image/jpeg;base64,AFFICHE", "w185/leo.jpg": "data:image/jpeg;base64,LEO"}
        with tempfile.TemporaryDirectory() as d:
            page = Path(d) / "27205.html"
            page.write_text(render(images=images), encoding="utf-8")
            self.assertEqual(embed.read_embedded(page), images)


class TestChemins(unittest.TestCase):
    def test_nom_et_lien(self):
        self.assertEqual(filmpage.name(27205), "27205.html")
        self.assertEqual(filmpage.href(27205), "Fiches/27205.html")


if __name__ == "__main__":
    unittest.main()
