"""Client TMDB : forme des requêtes, classement des erreurs, réessais.

Aucun appel réseau : urlopen est remplacé par un double qui rejoue une file de réponses préparées.
"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common import cache
from libraries.video import tmdb as tmdb_mod
from libraries.video.tmdb import Tmdb, TmdbAuthError, TmdbError, release_region


class FakeResponse(io.BytesIO):
    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def http_error(code, headers=None):
    return HTTPError("http://x", code, "erreur", headers or {}, None)


class ClientTestCase(unittest.TestCase):
    def call(self, reponses, methode="get", args=("movie/1",), **kwargs):
        """Joue `réponses` (réponse ou exception) et retourne (résultat, requêtes)."""
        requetes = []

        def fake_urlopen(request, timeout=None):
            requetes.append(request)
            item = reponses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        client = Tmdb(kwargs.pop("key", "0123456789abcdef"), **kwargs)
        with mock.patch.object(tmdb_mod, "urlopen", fake_urlopen), mock.patch.object(tmdb_mod.time, "sleep", lambda *_: None):
            return getattr(client, methode)(*args), requetes


class TestRequetes(ClientTestCase):
    def test_cle_v3_en_parametre(self):
        _, reqs = self.call([FakeResponse(b'{"id": 1}')])
        self.assertIn("api_key=0123456789abcdef", reqs[0].full_url)
        self.assertIn("language=fr-FR", reqs[0].full_url)
        self.assertNotIn("Authorization", reqs[0].headers)

    def test_token_v4_en_bearer(self):
        jeton = "ey" + "J0eXAiOiJKV1QifQ.charge.signature"
        _, reqs = self.call([FakeResponse(b"{}")], key=jeton)
        self.assertEqual(reqs[0].headers["Authorization"], f"Bearer {jeton}")
        self.assertNotIn("api_key", reqs[0].full_url)

    def test_parametre_ajoute_apres_une_requete_existante(self):
        _, reqs = self.call([FakeResponse(b"{}")], args=("search/movie?query=Dune",))
        self.assertIn("query=Dune&api_key=", reqs[0].full_url)

    def test_recherche_de_serie(self):
        _, reqs = self.call([FakeResponse(b'{"results": []}')], methode="search_tv", args=("Fargo",))
        self.assertIn("search/tv?query=Fargo", reqs[0].full_url)
        self.assertNotIn("first_air_date_year", reqs[0].full_url)

    def test_recherche_de_serie_avec_annee(self):
        _, reqs = self.call([FakeResponse(b'{"results": []}')], methode="search_tv", args=("Fargo", "2014"))
        self.assertIn("first_air_date_year=2014", reqs[0].full_url)

    def test_titre_encode_dans_l_url(self):
        _, reqs = self.call([FakeResponse(b'{"results": []}')], methode="search_tv", args=("Cowboy Bebop",))
        self.assertIn("query=Cowboy%20Bebop", reqs[0].full_url)

    def test_langue_ponctuelle(self):
        _, reqs = self.call([FakeResponse(b"{}")], methode="series", args=(1, "en-US"))
        self.assertIn("language=en-US", reqs[0].full_url)

    def test_casting_cumule_de_la_serie(self):
        _, reqs = self.call([FakeResponse(b"{}")], methode="aggregate_credits", args=(1396,))
        self.assertIn("tv/1396/aggregate_credits", reqs[0].full_url)

    def test_casting_cumule_d_une_saison(self):
        _, reqs = self.call([FakeResponse(b"{}")], methode="aggregate_credits", args=(1396, 2))
        self.assertIn("tv/1396/season/2/aggregate_credits", reqs[0].full_url)

    def test_le_casting_des_speciaux_n_est_pas_celui_de_la_serie(self):
        # Tester la saison 0 comme un booleen renverrait le casting de toute la serie.
        _, reqs = self.call([FakeResponse(b"{}")], methode="aggregate_credits", args=(1396, 0))
        self.assertIn("tv/1396/season/0/aggregate_credits", reqs[0].full_url)


class TestErreurs(ClientTestCase):
    def test_cle_refusee_arrete_tout(self):
        with self.assertRaises(TmdbAuthError):
            self.call([http_error(401)])

    def test_introuvable_est_recuperable(self):
        with self.assertRaises(TmdbError):
            self.call([http_error(404)])

    def test_404_n_est_pas_reessaye(self):
        reponses = [http_error(404), FakeResponse(b"{}")]
        with self.assertRaises(TmdbError):
            self.call(reponses)
        self.assertEqual(len(reponses), 1)      # la 2e réponse n'a pas été consommée

    def test_429_est_reessaye(self):
        (data, reqs) = self.call([http_error(429, {"Retry-After": "1"}), FakeResponse(b'{"id": 7}')])
        self.assertEqual(data, {"id": 7})
        self.assertEqual(len(reqs), 2)

    def test_panne_reseau_reessayee_puis_abandonnee(self):
        with self.assertRaises(TmdbError):
            self.call([URLError("coupure")] * 3, attempts=3)

    def test_json_illisible(self):
        with self.assertRaises(TmdbError):
            self.call([FakeResponse(b"<html>maintenance</html>")])


class TestImages(ClientTestCase):
    def test_telechargement_tronque_detecte(self):
        # Sans ce contrôle, un JPEG coupe finissait embarque tel quel dans le .mkv.
        with self.assertRaises(TmdbError):
            self.call([FakeResponse(b"12345", {"Content-Length": "99"})], methode="image", args=("/a.jpg", "w300"))

    def test_image_complete(self):
        data, _ = self.call([FakeResponse(b"12345", {"Content-Length": "5"})], methode="image", args=("/a.jpg", "w300"))
        self.assertEqual(data, b"12345")


class TestRegion(unittest.TestCase):
    def test_region_extraite_de_la_langue(self):
        self.assertEqual(release_region("fr-FR"), "FR")
        self.assertEqual(release_region("pt-BR"), "BR")
        self.assertIsNone(release_region("fr"))




class TestCacheDesReponses(ClientTestCase):
    def client(self, reponses, cache, **kwargs):
        """Comme ClientTestCase.call, mais avec un cache et plusieurs appels.

        Le remplacement d'urlopen tient jusqu'à la fin du test : sans quoi les appels partiraient pour de bon des le retour de cette méthode.
        """
        requetes = []

        def fake_urlopen(request, timeout=None):
            requetes.append(request)
            return reponses.pop(0)

        patch = mock.patch.object(tmdb_mod, "urlopen", fake_urlopen)
        patch.start()
        self.addCleanup(patch.stop)
        return Tmdb("0123456789abcdef", cache=cache, **kwargs), requetes

    def test_seconde_requete_servie_par_le_cache(self):
        with tempfile.TemporaryDirectory() as d:
            c = cache.Cache(Path(d))
            client, requetes = self.client([FakeResponse(b'{"id": 1}')], c)
            self.assertEqual(client.get("movie/1"), {"id": 1})
            self.assertEqual(client.get("movie/1"), {"id": 1})   # plus aucun appel réseau
            self.assertEqual(len(requetes), 1)

    def test_la_cle_de_cache_ignore_la_cle_d_api(self):
        # Elle ne doit jamais se retrouver sur le disque.
        with tempfile.TemporaryDirectory() as d:
            c = cache.Cache(Path(d))
            client, _ = self.client([FakeResponse(b"{}")], c)
            client.get("movie/1")
            contenus = [f.read_text(encoding="utf-8") for f in Path(d).glob("*.json")]
            self.assertTrue(contenus)
            self.assertFalse(any("0123456789abcdef" in x for x in contenus))
            self.assertTrue(any('"fr-FR:movie/1"' in x for x in contenus))

    def test_langues_differentes_ne_se_melangent_pas(self):
        with tempfile.TemporaryDirectory() as d:
            c = cache.Cache(Path(d))
            client, requetes = self.client([FakeResponse(b'{"t": "fr"}'), FakeResponse(b'{"t": "en"}')], c)
            self.assertEqual(client.get("tv/1"), {"t": "fr"})
            self.assertEqual(client.get("tv/1", "en-US"), {"t": "en"})
            self.assertEqual(len(requetes), 2)

    def test_reponse_illisible_non_mise_en_cache(self):
        with tempfile.TemporaryDirectory() as d:
            c = cache.Cache(Path(d))
            client, _ = self.client([FakeResponse(b"<html>")], c)
            with self.assertRaises(TmdbError):
                client.get("movie/1")
            self.assertEqual(list(Path(d).glob("*.json")), [])

    def test_sans_cache_le_client_marche_pareil(self):
        client, requetes = self.client([FakeResponse(b'{"id": 1}')], None)
        self.assertEqual(client.get("movie/1"), {"id": 1})
        self.assertEqual(len(requetes), 1)


class TestAttentes(unittest.TestCase):
    """Combien de temps on laisse à TMDB avant de réessayer."""

    def attentes(self, reponses, **kwargs):
        pauses = []
        client = Tmdb("0123456789abcdef", **kwargs)

        def fake_urlopen(request, timeout=None):
            item = reponses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        with mock.patch.object(tmdb_mod, "urlopen", fake_urlopen), mock.patch.object(tmdb_mod.time, "sleep", pauses.append):
            try:
                client.get("movie/1")
            except TmdbError:
                pass
        return pauses

    def test_le_delai_demande_par_tmdb_est_respecte(self):
        self.assertEqual(self.attentes([http_error(429, {"Retry-After": "7"}), FakeResponse(b"{}")]), [7])

    def test_le_delai_demande_est_plafonne(self):
        self.assertEqual(self.attentes([http_error(429, {"Retry-After": "3600"}), FakeResponse(b"{}")]), [tmdb_mod.MAX_RETRY_WAIT])

    def test_un_delai_incomprehensible_retombe_sur_l_attente_exponentielle(self):
        (pause,) = self.attentes([http_error(503, {"Retry-After": "bientôt"}), FakeResponse(b"{}")])
        self.assertTrue(1 <= pause <= 1.5)       # 2 ** 0, plus un bruit d'au plus 0,5 s

    def test_sans_delai_demande_l_attente_double_a_chaque_essai(self):
        premiere, seconde = self.attentes([URLError("coupure"), URLError("coupure"), FakeResponse(b"{}")], attempts=3)
        self.assertTrue(1 <= premiere <= 1.5)
        self.assertTrue(2 <= seconde <= 2.5)

    def test_derniere_tentative_sans_attente(self):
        self.assertEqual(len(self.attentes([URLError("coupure")] * 3, attempts=3)), 2)

    def test_panne_serveur_reessayee(self):
        self.assertEqual(len(self.attentes([http_error(500), http_error(502), FakeResponse(b"{}")], attempts=3)), 2)

    def test_retry_after_absent(self):
        self.assertIsNone(Tmdb._retry_after(None))
        self.assertIsNone(Tmdb._retry_after({}))


class TestErreursDefinitives(ClientTestCase):
    def test_autre_erreur_client_non_reessayee(self):
        reponses = [http_error(422), FakeResponse(b"{}")]
        with self.assertRaisesRegex(TmdbError, "HTTP 422"):
            self.call(reponses)
        self.assertEqual(len(reponses), 1)

    def test_acces_interdit_arrete_tout_comme_une_cle_refusee(self):
        with self.assertRaises(TmdbAuthError):
            self.call([http_error(403)])

    def test_une_cle_refusee_ne_se_confond_pas_avec_une_erreur_ponctuelle(self):
        # Les scripts rattrapent TmdbError élément par élément : si la clé invalide en héritait, elle donnerait une cascade de « saison ignorée ».
        self.assertFalse(issubclass(TmdbAuthError, TmdbError))


class TestPointsDAcces(ClientTestCase):
    """Chaque méthode vise le bon chemin, avec ce qu'il faut pour la fiche qu'on en tire."""

    def url(self, methode, *args, reponse=b'{"results": []}', **kwargs):
        _, reqs = self.call([FakeResponse(reponse)], methode=methode, args=args, **kwargs)
        return unquote(reqs[0].full_url)

    def test_recherche_de_film(self):
        self.assertIn("search/movie?query=Les Quatre Fantastiques&", self.url("search_movie", "Les Quatre Fantastiques"))

    def test_recherche_de_film_avec_annee(self):
        self.assertIn("&year=2021&", self.url("search_movie", "Dune", 2021))

    def test_recherche_de_film_sans_annee(self):
        self.assertNotIn("year=", self.url("search_movie", "Dune"))

    def test_recherche_de_saga(self):
        self.assertIn("search/collection?query=Iron Man&", self.url("search_collection", "Iron Man"))

    def test_recherche_sans_resultat_rend_une_liste_vide(self):
        resultats, _ = self.call([FakeResponse(b"{}")], methode="search_movie", args=("x",))
        self.assertEqual(resultats, [])

    def test_film_avec_ses_credits(self):
        self.assertIn("movie/438631?append_to_response=credits&", self.url("movie", 438631, reponse=b"{}"))

    def test_composition_d_une_saga(self):
        self.assertIn("/collection/131292?", self.url("collection", 131292, reponse=b"{}"))

    def test_saison(self):
        self.assertIn("/tv/42/season/3?", self.url("season", 42, 3, reponse=b"{}"))

    def test_serie(self):
        self.assertIn("/tv/42?", self.url("series", 42, reponse=b"{}"))


class TestDateDeSortieNationale(ClientTestCase):
    """Le champ release_date du film est la sortie d'origine : la sortie française vient de /release_dates."""

    def date(self, resultats, region="FR"):
        corps = json.dumps({"results": resultats}).encode()
        date, _ = self.call([FakeResponse(corps)], methode="local_release_date", args=(1, region))
        return date

    @staticmethod
    def pays(code, *sorties):
        return {"iso_3166_1": code, "release_dates": [{"type": t, "release_date": d} for t, d in sorties]}

    def test_la_sortie_en_salles_prime_sur_le_numerique(self):
        self.assertEqual(self.date([self.pays("FR", (4, "2021-12-01T00:00:00.000Z"), (3, "2021-09-15T00:00:00.000Z"))]), "2021-09-15")

    def test_a_type_egal_la_plus_ancienne(self):
        # Sinon une ressortie en salles prendrait le pas sur la sortie initiale.
        self.assertEqual(self.date([self.pays("FR", (3, "2023-06-01T00:00:00.000Z"), (3, "2021-09-15T00:00:00.000Z"))]), "2021-09-15")

    def test_repli_sur_un_type_moins_prefere(self):
        self.assertEqual(self.date([self.pays("FR", (5, "2022-02-01T00:00:00.000Z"))]), "2022-02-01")

    def test_la_bonne_region_seule_compte(self):
        self.assertEqual(self.date([self.pays("US", (3, "2021-10-22T00:00:00.000Z")), self.pays("FR", (3, "2021-09-15T00:00:00.000Z"))]), "2021-09-15")

    def test_region_absente(self):
        self.assertIsNone(self.date([self.pays("US", (3, "2021-10-22T00:00:00.000Z"))]))

    def test_date_vide_ignoree(self):
        self.assertIsNone(self.date([self.pays("FR", (3, ""))]))

    def test_type_inconnu_ignore(self):
        self.assertIsNone(self.date([self.pays("FR", (9, "2021-09-15T00:00:00.000Z"))]))

    def test_aucune_sortie_listee(self):
        self.assertIsNone(self.date([]))

    def test_panne_de_tmdb_rend_none_sans_planter(self):
        # Ce n'est qu'une date : le film se traite avec celle d'origine.
        date, _ = self.call([http_error(404)], methode="local_release_date", args=(1, "FR"))
        self.assertIsNone(date)


class TestEcritureDImage(ClientTestCase):
    def test_l_image_est_ecrite_sur_le_disque(self):
        with tempfile.TemporaryDirectory() as d:
            destination = Path(d) / "cover.jpg"
            self.call([FakeResponse(b"JPEG", {"Content-Length": "4"})], methode="save_image", args=("/a.jpg", "w500", destination))
            self.assertEqual(destination.read_bytes(), b"JPEG")

    def test_une_image_tronquee_n_est_pas_ecrite(self):
        with tempfile.TemporaryDirectory() as d:
            destination = Path(d) / "cover.jpg"
            with self.assertRaises(TmdbError):
                self.call([FakeResponse(b"JP", {"Content-Length": "4"})], methode="save_image", args=("/a.jpg", "w500", destination))
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
