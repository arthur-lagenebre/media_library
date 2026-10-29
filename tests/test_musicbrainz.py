"""Client MusicBrainz : forme des requêtes, cadence, réessais, pochettes.

Aucun appel réseau : urlopen est remplacé par un double qui rejoue une file de réponses préparées, et l'horloge est figée pour mesurer les attentes sans les subir.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import URLError
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common import cache
from libraries.music import musicbrainz as mb_mod
from libraries.music.musicbrainz import MusicBrainz, MusicBrainzError
from tests.test_tmdb import FakeResponse, http_error


class ClientTestCase(unittest.TestCase):
    def call(self, reponses, methode="get", args=("release/x",), **kwargs):
        """Joue `reponses` et retourne (résultat, requêtes, attentes demandées)."""
        requetes, attentes = [], []

        def fake_urlopen(request, timeout=None):
            requetes.append(request)
            item = reponses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        client = kwargs.pop("client", None) or MusicBrainz(**kwargs)
        with mock.patch.object(mb_mod, "urlopen", fake_urlopen), mock.patch.object(mb_mod.time, "sleep", attentes.append), mock.patch.object(mb_mod.time, "monotonic", lambda: 100.0):
            return getattr(client, methode)(*args), requetes, attentes


class TestRequetes(ClientTestCase):
    def test_user_agent_et_format_json(self):
        _, reqs, _ = self.call([FakeResponse(b"{}")])
        self.assertIn("media_library", reqs[0].headers["User-agent"])
        self.assertTrue(reqs[0].full_url.endswith("release/x?fmt=json"))

    def test_format_ajoute_apres_une_requete_existante(self):
        _, reqs, _ = self.call([FakeResponse(b"{}")], args=("release/x?inc=genres",))
        self.assertIn("?inc=genres&fmt=json", reqs[0].full_url)

    def test_recherche_exacte(self):
        _, reqs, _ = self.call([FakeResponse(b'{"releases": []}')], methode="search_releases", args=("Born Dead", "Body Count"))
        self.assertIn('query=release:"Born Dead" AND artist:"Body Count"', unquote(reqs[0].full_url))

    def test_guillemets_neutralises_dans_l_expression(self):
        _, reqs, _ = self.call([FakeResponse(b'{"releases": []}')], methode="search_releases", args=('Le "grand" album',))
        self.assertIn('release:"Le  grand  album"', unquote(reqs[0].full_url))

    def test_recherche_large_echappe_la_syntaxe(self):
        # "TRON: Legacy" chercherait sinon un champ nommé TRON.
        _, reqs, _ = self.call([FakeResponse(b'{"releases": []}')], methode="search_releases", args=("TRON: Legacy", None, False))
        self.assertIn(r"release:(TRON\: Legacy)", unquote(reqs[0].full_url))

    def test_resultats_rendus(self):
        data, _, _ = self.call([FakeResponse(b'{"releases": [{"id": "a"}]}')], methode="search_releases", args=("A",))
        self.assertEqual(data, [{"id": "a"}])


class TestArtistes(ClientTestCase):
    def test_fiche_d_artiste_avec_relations_et_genres(self):
        _, reqs, _ = self.call([FakeResponse(b'{"id": "a"}')], methode="artist", args=("abc",))
        self.assertTrue(reqs[0].full_url.endswith("artist/abc?inc=url-rels+artist-rels+genres&fmt=json"))

    def test_json_d_un_autre_site_sans_cadence(self):
        data, reqs, attentes = self.call([FakeResponse(b'{"extract": "x"}')], methode="external", args=("https://fr.wikipedia.org/api/rest_v1/page/summary/X",))
        self.assertEqual(data, {"extract": "x"})
        self.assertEqual(reqs[0].full_url, "https://fr.wikipedia.org/api/rest_v1/page/summary/X")
        self.assertIn("media_library", reqs[0].headers["User-agent"])
        self.assertEqual(attentes, [])

    def test_json_d_un_autre_site_illisible(self):
        with self.assertRaises(MusicBrainzError):
            self.call([FakeResponse(b"<html>")], methode="external", args=("https://x.example/",))

    def test_json_d_un_autre_site_garde_en_cache(self):
        with tempfile.TemporaryDirectory() as d:
            client = MusicBrainz(cache=cache.Cache(Path(d)))
            self.call([FakeResponse(b'{"a": 1}')], methode="external", args=("https://x.example/",), client=client)
            data, reqs, _ = self.call([], methode="external", args=("https://x.example/",), client=client)
        self.assertEqual((data, reqs), ({"a": 1}, []))

    def test_le_statut_http_accompagne_l_erreur(self):
        with self.assertRaises(MusicBrainzError) as plante:
            self.call([http_error(404)])
        self.assertEqual(plante.exception.code, 404)
        with self.assertRaises(MusicBrainzError) as plante:
            self.call([http_error(400)])
        self.assertEqual(plante.exception.code, 400)
        with self.assertRaises(MusicBrainzError) as plante:
            self.call([URLError("coupure")] * 2, attempts=2)
        self.assertIsNone(plante.exception.code)


class TestCadence(ClientTestCase):
    def test_deux_requetes_espacees(self):
        client = MusicBrainz(interval=1.1)
        self.call([FakeResponse(b"{}")], client=client)
        _, _, attentes = self.call([FakeResponse(b"{}")], client=client)
        self.assertEqual(len(attentes), 1)
        self.assertAlmostEqual(attentes[0], 1.1)

    def test_premiere_requete_sans_attente(self):
        _, _, attentes = self.call([FakeResponse(b"{}")])
        self.assertEqual(attentes, [])

    def test_le_cache_ne_coute_aucune_attente(self):
        with tempfile.TemporaryDirectory() as d:
            client = MusicBrainz(cache=cache.Cache(Path(d)))
            self.call([FakeResponse(b'{"id": 1}')], client=client)
            data, reqs, attentes = self.call([], client=client)
        self.assertEqual((data, reqs, attentes), ({"id": 1}, [], []))


class TestErreurs(ClientTestCase):
    def test_503_reessaye(self):
        data, reqs, _ = self.call([http_error(503, {"Retry-After": "2"}), FakeResponse(b'{"id": 7}')])
        self.assertEqual((data, len(reqs)), ({"id": 7}, 2))

    def test_connexion_coupee_reessayee(self):
        # Mesuré : depuis urllib, une connexion sur cinq est coupée en pleine négociation TLS.
        data, reqs, _ = self.call([URLError(ConnectionResetError(10054, "coupee")), FakeResponse(b'{"id": 7}')])
        self.assertEqual((data, len(reqs)), ({"id": 7}, 2))

    def test_panne_persistante_abandonnee(self):
        with self.assertRaises(MusicBrainzError):
            self.call([URLError("coupure")] * 2, attempts=2)

    def test_404_n_est_pas_reessaye(self):
        reponses = [http_error(404), FakeResponse(b"{}")]
        with self.assertRaisesRegex(MusicBrainzError, "404"):
            self.call(reponses)
        self.assertEqual(len(reponses), 1)

    def test_requete_refusee_n_est_pas_reessayee(self):
        reponses = [http_error(400), FakeResponse(b"{}")]
        with self.assertRaises(MusicBrainzError):
            self.call(reponses)
        self.assertEqual(len(reponses), 1)

    def test_json_illisible(self):
        with self.assertRaises(MusicBrainzError):
            self.call([FakeResponse(b"<html>maintenance</html>")])


class TestPochettes(ClientTestCase):
    def test_pochette_de_la_sortie(self):
        data, reqs, attentes = self.call([FakeResponse(b"JPEG", {"Content-Length": "4"})], methode="cover", args=("rel", "grp"))
        self.assertEqual(data, b"JPEG")
        self.assertTrue(reqs[0].full_url.endswith("/release/rel/front-1200"))
        self.assertEqual(attentes, [])                  # Cover Art Archive n'impose pas de cadence

    def test_repli_sur_le_release_group(self):
        data, reqs, _ = self.call([http_error(404), FakeResponse(b"JPEG")], methode="cover", args=("rel", "grp", "500"))
        self.assertEqual(data, b"JPEG")
        self.assertTrue(reqs[1].full_url.endswith("/release-group/grp/front-500"))

    def test_release_group_seul(self):
        # La fiche dit déjà que l'édition n'a pas d'image : inutile de demander un 404.
        data, reqs, _ = self.call([FakeResponse(b"JPEG")], methode="cover", args=(None, "grp"))
        self.assertEqual((data, len(reqs)), (b"JPEG", 1))
        self.assertTrue(reqs[0].full_url.endswith("/release-group/grp/front-1200"))

    def test_aucune_pochette(self):
        data, _, _ = self.call([http_error(404), http_error(404)], methode="cover", args=("rel", "grp"))
        self.assertIsNone(data)

    def test_une_panne_reseau_n_est_pas_une_absence_de_pochette(self):
        # Le diagnostic se faisait sur le texte de l'erreur : un « 404 » dans un message réseau faisait passer la panne pour « pas de pochette ».
        pannes = [URLError("hôte cover-404.example injoignable")] * 4
        with self.assertRaises(MusicBrainzError) as ctx:
            self.call(pannes, methode="cover", args=("rel", "grp"))
        self.assertIsNone(ctx.exception.code)

    def test_une_erreur_serveur_n_est_pas_une_absence_de_pochette(self):
        with self.assertRaises(MusicBrainzError):
            self.call([http_error(500)] * 4, methode="cover", args=("rel", "grp"))

    def test_taille_originale(self):
        _, reqs, _ = self.call([FakeResponse(b"JPEG")], methode="cover", args=("rel", None, "original"))
        self.assertTrue(reqs[0].full_url.endswith("/release/rel/front"))

    def test_telechargement_tronque_detecte(self):
        # Embarquée telle quelle, une image coupée resterait dans chaque piste.
        with self.assertRaisesRegex(MusicBrainzError, "incomplet"):
            self.call([FakeResponse(b"JP", {"Content-Length": "4"})], methode="cover", args=("rel",))


class TestPochettesAChoisir(ClientTestCase):
    INDEX = b'{"images": [{"id": 1, "front": true, "image": "http://x/1.jpg", "thumbnails": {"500": "http://x/1-500.jpg", "1200": "http://x/1-1200.jpg"}}, {"id": 2, "front": false, "back": true, "image": "http://x/2.jpg"}]}'

    def test_index_limite_aux_pochettes_de_face(self):
        images, reqs, attentes = self.call([FakeResponse(self.INDEX)], methode="cover_images", args=("rel",))
        self.assertEqual([i["id"] for i in images], [1])
        self.assertTrue(reqs[0].full_url.endswith("/release/rel"))
        self.assertEqual(attentes, [])

    def test_sortie_sans_aucune_image(self):
        images, _, _ = self.call([http_error(404)], methode="cover_images", args=("rel",))
        self.assertEqual(images, [])

    def test_une_panne_n_est_pas_une_absence_d_images(self):
        with self.assertRaises(MusicBrainzError):
            self.call([http_error(500)] * 4, methode="cover_images", args=("rel",))

    def test_miniature_a_la_taille_demandee_en_https(self):
        image = {"image": "http://x/1.jpg", "thumbnails": {"500": "http://x/1-500.jpg"}}
        data, reqs, _ = self.call([FakeResponse(b"JPEG")], methode="cover_image", args=(image, "500"))
        self.assertEqual((data, reqs[0].full_url), (b"JPEG", "https://x/1-500.jpg"))

    def test_original_ou_miniature_absente_donne_l_image_d_origine(self):
        image = {"image": "http://x/1.jpg", "thumbnails": {"500": "http://x/1-500.jpg"}}
        for taille in ("original", "1200"):
            with self.subTest(taille):
                _, reqs, _ = self.call([FakeResponse(b"JPEG")], methode="cover_image", args=(image, taille))
                self.assertEqual(reqs[0].full_url, "https://x/1.jpg")

    def test_editions_d_un_release_group(self):
        editions, reqs, _ = self.call([FakeResponse(b'{"releases": [{"id": "a"}]}')], methode="group_releases", args=("grp",))
        self.assertEqual(editions, [{"id": "a"}])
        self.assertIn("release?release-group=grp&inc=media&limit=100&fmt=json", reqs[0].full_url)


if __name__ == "__main__":
    unittest.main()
