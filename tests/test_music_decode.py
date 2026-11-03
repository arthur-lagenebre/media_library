"""Décodage ffmpeg d'une piste : ce qu'on lui demande, et ce qu'on retient de sa réponse.

ffmpeg est simulé : ce que les vrais fichiers lui font dire est vérifié dans test_verify_flac.py et test_verify_mp3.py, quand il est installé.
"""

import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.music import decode
from tests.test_conversion_programmes import ProgrammeTestCase
from tests.test_music_integrity import flac, flac_sain

MD5 = bytes(range(1, 17))


def resultat(stdout="", stderr="", code=0):
    return types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=code)


class FfmpegSimule:
    """Remplace run_tool : garde les commandes reçues et rend `reponse`, ou la lève si c'est une exception."""

    def __init__(self, reponse=None):
        self.reponse, self.commandes, self.kwargs = reponse or resultat(), [], []

    def __call__(self, commande, **kwargs):
        self.commandes.append(commande)
        self.kwargs.append(kwargs)
        if isinstance(self.reponse, Exception):
            raise self.reponse
        return self.reponse


class TestCommande(unittest.TestCase):
    def test_avec_empreinte_le_son_est_rendu_a_la_largeur_du_fichier(self):
        commande = decode.command(Path("a.flac"), 24)
        self.assertEqual(commande[-5:], ["-c:a", "pcm_s24le", "-f", "md5", "-"])

    def test_sans_empreinte_le_son_est_decode_pour_rien(self):
        commande = decode.command(Path("a.mp3"))
        self.assertEqual(commande[-3:], ["-f", "null", "-"])
        self.assertNotIn("md5", commande)

    def test_ffmpeg_est_strict_et_ne_prend_que_la_piste_audio(self):
        commande = decode.command(Path("a.mp3"))
        self.assertEqual(commande[commande.index("-err_detect") + 1], decode.STRICT)
        self.assertEqual(commande[commande.index("-map") + 1], "0:a:0")
        self.assertNotIn("-y", commande)                           # rien ne s'écrit nulle part


class TestVerdict(ProgrammeTestCase):
    def piste(self, nom="a.flac", donnees=None):
        trames, total = flac_sain()
        chemin = self.racine / nom
        chemin.write_bytes(flac(trames, total, md5=MD5) if donnees is None else donnees)
        return chemin

    def decoder(self, reponse, digest=None, nom="a.flac"):
        ffmpeg = FfmpegSimule(reponse)
        with mock.patch.object(decode, "run_tool", ffmpeg):
            return decode.check(self.piste(nom), digest), ffmpeg

    def test_son_qui_passe_avec_la_bonne_empreinte(self):
        message, ffmpeg = self.decoder(resultat(stdout=f"MD5={MD5.hex().upper()}\n"), (16, MD5.hex()))
        self.assertEqual(message, "")
        self.assertIn("pcm_s16le", ffmpeg.commandes[0])

    def test_empreinte_differente(self):
        message, _ = self.decoder(resultat(stdout="MD5=" + "ab" * 16), (16, MD5.hex()))
        self.assertIn("n'a pas l'empreinte MD5", message)
        self.assertIn("ab" * 16, message)
        self.assertIn(MD5.hex(), message)

    def test_pas_d_empreinte_rendue(self):
        message, _ = self.decoder(resultat(stdout=""), (16, MD5.hex()))
        self.assertIn("aucune", message)

    def test_sans_empreinte_attendue_rien_n_est_compare(self):
        message, ffmpeg = self.decoder(resultat())
        self.assertEqual(message, "")
        self.assertIn("null", ffmpeg.commandes[0])

    def test_mp3_decode_pour_rien(self):
        message, ffmpeg = self.decoder(resultat(), nom="a.mp3")
        self.assertEqual(message, "")
        self.assertEqual(ffmpeg.commandes[0][-3:], ["-f", "null", "-"])

    def test_erreur_de_ffmpeg_sans_l_adresse_memoire(self):
        for adresse in ("[flac @ 0000029c0c36a380] ", "[flac @ 0x7f3a2c001234] "):
            with self.subTest(adresse):
                message, _ = self.decoder(resultat(stderr=f"{adresse}CRC error at PTS -9223372036854775808\n[aist#0:0/flac @ 000] Decoding error\n"))
                self.assertEqual(message, "ffmpeg : CRC error at PTS -9223372036854775808")

    def test_code_de_sortie_non_nul_sans_message(self):
        message, _ = self.decoder(resultat(code=69))
        self.assertEqual(message, "ffmpeg a échoué (code 69)")

    def test_partage_qui_ne_repond_plus(self):
        message, _ = self.decoder(subprocess.TimeoutExpired("ffmpeg", 120))
        self.assertIn("ne répond plus", message)

    def test_delai_de_lecture_demande_pour_un_partage_reseau(self):
        with mock.patch.object(decode, "read_timeout", return_value=120):
            _, ffmpeg = self.decoder(resultat())
        self.assertEqual(ffmpeg.kwargs[0], {"timeout": 120})


if __name__ == "__main__":
    unittest.main()
