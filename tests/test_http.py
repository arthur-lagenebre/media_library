"""GET avec réessais commun aux clients : ce que les deux clients en attendent, sans passer par eux.

Aucun appel réseau : urlopen est remplacé par un double qui rejoue une file de réponses préparées.
"""

import http.client
import io
import sys
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common import http as http_mod
from tests.test_tmdb import CoupeEnRoute, FakeResponse, http_error


class Echec(Exception):
    pass


class Refus(Exception):
    pass


class TestFetch(unittest.TestCase):
    def fetch(self, reponses, attempts=3, base=1, before_attempt=None):
        pauses = []

        def fake_urlopen(request, timeout=None):
            item = reponses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        with mock.patch.object(http_mod, "urlopen", fake_urlopen), mock.patch.object(http_mod.time, "sleep", pauses.append):
            try:
                result = http_mod.fetch("http://x", {}, 5, attempts, fail=Echec, refuse=lambda e: Refus(e.code), base=base, before_attempt=before_attempt)
            except (Echec, Refus) as e:
                result = e
        return result, pauses

    def test_reponse_rendue_avec_ses_en_tetes(self):
        (corps, en_tetes), pauses = self.fetch([FakeResponse(b"ok", {"Content-Length": "2"})])
        self.assertEqual((corps, en_tetes["Content-Length"], pauses), (b"ok", "2", []))

    def test_erreur_definitive_confiee_a_refuse_sans_reessai(self):
        reponses = [http_error(404), FakeResponse(b"ok")]
        erreur, pauses = self.fetch(reponses)
        self.assertIsInstance(erreur, Refus)
        self.assertEqual((erreur.args, len(reponses), pauses), ((404,), 1, []))

    def test_429_et_5xx_toujours_reessayes(self):
        _, pauses = self.fetch([http_error(429), http_error(500), FakeResponse(b"ok")])
        self.assertEqual(len(pauses), 2)

    def test_reponse_coupee_reessayee_puis_echec(self):
        erreur, pauses = self.fetch([CoupeEnRoute(), CoupeEnRoute(), URLError("coupure")])
        self.assertIsInstance(erreur, Echec)
        self.assertEqual(len(pauses), 2)

    def test_base_de_l_attente_exponentielle(self):
        _, un = self.fetch([URLError("x"), URLError("x"), FakeResponse(b"ok")], base=1)
        _, deux = self.fetch([URLError("x"), URLError("x"), FakeResponse(b"ok")], base=2)
        self.assertTrue(1 <= un[0] <= 1.5 and 2 <= un[1] <= 2.5)
        self.assertTrue(2 <= deux[0] <= 2.5 and 4 <= deux[1] <= 4.5)

    def test_la_connexion_d_une_erreur_http_est_fermee(self):
        # Le corps d'une erreur ne sert à rien : sa connexion ne doit pas rester ouverte pendant l'attente, ni après l'abandon.
        for code, reponses in ((503, 3), (404, 1)):
            with self.subTest(code=code):
                corps = [io.BytesIO(b"erreur") for _ in range(reponses)]
                erreurs = [HTTPError("http://x", code, "erreur", {}, c) for c in corps]
                self.fetch(erreurs + [FakeResponse(b"ok")] * (3 - reponses))
                self.assertTrue(all(c.closed for c in corps))

    def test_avant_chaque_tentative_meme_reessayee(self):
        appels = []
        self.fetch([URLError("x"), URLError("x"), FakeResponse(b"ok")], before_attempt=lambda: appels.append(1))
        self.assertEqual(len(appels), 3)


if __name__ == "__main__":
    unittest.main()
