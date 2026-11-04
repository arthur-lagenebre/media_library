"""Verify_Flac.py : ce qu'un passage juge, le bilan, le journal et le code de sortie.

ffmpeg est simulé, hors la dernière classe qui passe par le vrai quand il est installé. Rien n'est jamais écrit à côté des pistes, hors le journal.
"""

import math
import shutil
import sys
import types
import unittest
import wave
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common.tools import run_tool
from libraries.music import decode, integrity
from scripts.Music import Verify_Flac as verificateur
from tests.test_conversion_programmes import ProgrammeTestCase, outils
from tests.test_music_decode import FfmpegSimule, resultat
from tests.test_music_integrity import flac, flac_sain


class TestControle(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        trames, total = flac_sain()
        self.sain = flac(trames, total)
        self.piste = self.racine / "a.flac"

    def verifier(self, donnees, complet, ffmpeg=None):
        self.piste.write_bytes(donnees)
        ffmpeg = ffmpeg or FfmpegSimule()
        with mock.patch.object(decode, "run_tool", ffmpeg):
            return verificateur.check(self.piste, complet), ffmpeg

    def test_le_controle_rapide_ne_lance_aucun_outil(self):
        message, ffmpeg = self.verifier(self.sain, complet=False)
        self.assertEqual(message, "")
        self.assertEqual(ffmpeg.commandes, [])

    def test_une_structure_rompue_n_attend_pas_le_decodage(self):
        message, ffmpeg = self.verifier(self.sain[:-300], complet=True)
        self.assertIn("incomplète", message)
        self.assertEqual(ffmpeg.commandes, [])

    def test_le_decodage_complete_la_structure(self):
        message, _ = self.verifier(self.sain, complet=True, ffmpeg=FfmpegSimule(resultat(stderr="[flac @ 1] CRC error")))
        self.assertEqual(message, "ffmpeg : CRC error")

    def test_l_empreinte_de_streaminfo_est_comparee(self):
        trames, total = flac_sain()
        message, ffmpeg = self.verifier(flac(trames, total, md5=b"\x01" * 16), complet=True, ffmpeg=FfmpegSimule(resultat(stdout="MD5=" + "02" * 16)))
        self.assertIn("pcm_s16le", ffmpeg.commandes[0])
        self.assertIn("n'a pas l'empreinte MD5", message)


class TestMain(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        trames, total = flac_sain()
        self.sain = flac(trames, total)
        (self.racine / "01 - Sain.flac").write_bytes(self.sain)
        (self.racine / "02 - Sain.flac").write_bytes(self.sain)
        (self.racine / "03 - Autre format.mp3").write_bytes(b"pas du flac")     # hors du champ de ce script
        self.avant = {p.name: p.read_bytes() for p in self.racine.iterdir()}

    def lancer(self, *argv, ffmpeg=None, tools=("ffmpeg",)):
        with mock.patch.object(decode, "run_tool", ffmpeg or FfmpegSimule()):
            return self.lancer_main(verificateur, *argv, shutil=types.SimpleNamespace(which=outils(*tools)))

    def journal(self):
        return (self.racine / "verification_flac.log").read_text(encoding="utf-8")

    def test_pistes_saines(self):
        code, texte = self.lancer()
        self.assertEqual(code, 0)
        self.assertIn("TOTAL : 2 piste(s) contrôlée(s)", texte)         # le .mp3 n'est pas pris
        self.assertIn("0 en défaut", texte)
        self.assertIn("--full", texte)                                  # le contrôle rapide dit ce qu'il ne voit pas
        self.assertIn("Aucun défaut.", self.journal())

    def test_piste_coupee_code_1_et_journal(self):
        (self.racine / "04 - Coupee.flac").write_bytes(self.sain[:-300])
        code, texte = self.lancer()
        self.assertEqual(code, 1)
        self.assertIn("[DÉFAUT] 04 - Coupee.flac", texte)
        self.assertIn("1 en défaut", texte)
        self.assertIn("ne se répare pas", texte)
        journal = self.journal()
        self.assertIn("04 - Coupee.flac\n    la dernière trame audio est incomplète", journal)
        self.assertNotIn("01 - Sain.flac", journal)

    def test_rien_n_est_ecrit_hors_le_journal(self):
        (self.racine / "04 - Coupee.flac").write_bytes(self.sain[:-300])
        self.avant["04 - Coupee.flac"] = self.sain[:-300]
        self.lancer()
        self.lancer("--full", ffmpeg=FfmpegSimule(resultat(stderr="[flac @ 1] CRC error")))
        self.assertEqual({p.name: p.read_bytes() for p in self.racine.iterdir() if p.name != "verification_flac.log"}, self.avant)

    def test_le_controle_complet_decode_chaque_piste(self):
        ffmpeg = FfmpegSimule()
        code, texte = self.lancer("--full", ffmpeg=ffmpeg)
        self.assertEqual(code, 0)
        self.assertEqual(len(ffmpeg.commandes), 2)
        self.assertIn("Contrôle complet", texte)
        self.assertIn("complet (décodage)", self.journal())

    def test_defaut_vu_seulement_au_decodage(self):
        code, texte = self.lancer("--full", ffmpeg=FfmpegSimule(resultat(stderr="[flac @ 1] CRC error")))
        self.assertEqual(code, 1)
        self.assertIn("2 en défaut", texte)
        self.assertIn("ffmpeg : CRC error", self.journal())

    def test_sans_ffmpeg_le_controle_rapide_marche(self):
        self.assertEqual(self.lancer(tools=())[0], 0)

    def test_sans_ffmpeg_le_controle_complet_s_arrete_avec_le_remede(self):
        code, _ = self.lancer("--full", tools=())
        self.assertIsInstance(code, str)
        self.assertIn("ffmpeg est introuvable", code)
        self.assertIn("winget install Gyan.FFmpeg", code)

    def test_dossier_sans_flac(self):
        for p in self.racine.iterdir():
            if p.suffix == ".flac":
                p.unlink()
        self.assertIn("Aucun .flac", self.lancer()[0])

    def test_dossier_introuvable(self):
        ligne = [str(Path(verificateur.__file__)), "--dir", str(self.racine / "absent")]
        with mock.patch.object(sys, "argv", ligne), self.assertRaises(SystemExit) as sortie:
            verificateur.main()
        self.assertIn("Dossier introuvable", sortie.exception.code)

    def test_sans_recursion(self):
        (self.racine / "Sous").mkdir()
        (self.racine / "Sous" / "Coupee.flac").write_bytes(self.sain[:-300])
        self.assertEqual(self.lancer("--no-recursive")[0], 0)
        self.assertIn("sans les sous-dossiers", self.journal())
        self.assertEqual(self.lancer()[0], 1)

    def test_journal_ou_l_utilisateur_le_demande(self):
        destination = self.racine / "ailleurs.log"
        self.lancer("--log", str(destination))
        self.assertTrue(destination.exists())
        self.assertFalse((self.racine / "verification_flac.log").exists())


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg absent : le vrai décodage n'est pas testé")
class TestAvecLeVraiFfmpeg(ProgrammeTestCase):
    """De vraies pistes, de vrais octets abîmés : ce que les simulations ne peuvent pas dire."""

    def encoder(self, nom, largeur=2, canaux=2):
        wav = self.racine / "source.wav"
        with wave.open(str(wav), "wb") as f:
            f.setnchannels(canaux)
            f.setsampwidth(largeur)
            f.setframerate(44100)
            amplitude = 2 ** (8 * largeur - 2)
            f.writeframes(b"".join(
                int(amplitude * math.sin(i / 20 + c) + (i * 7919 % 2001 - 1000)).to_bytes(largeur, "little", signed=True)
                for i in range(44100) for c in range(canaux)))
        options = ["-sample_fmt", "s32", "-bits_per_raw_sample", "24"] if largeur == 3 else []
        sortie = self.racine / nom
        run_tool(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-c:a", "flac", *options, str(sortie)])
        wav.unlink()
        return sortie

    def test_16_bits_24_bits_et_mono_passent_empreinte_comprise(self):
        for nom, largeur, canaux in (("seize.flac", 2, 2), ("vingt-quatre.flac", 3, 2), ("mono.flac", 2, 1)):
            with self.subTest(nom):
                piste = self.encoder(nom, largeur, canaux)
                self.assertIsNotNone(integrity.flac_digest(piste))     # l'empreinte est bien comparée
                self.assertEqual(verificateur.check(piste, complet=True), "")

    def test_octet_altere_vu_seulement_au_decodage(self):
        piste = self.encoder("sain.flac")
        donnees = bytearray(piste.read_bytes())
        donnees[len(donnees) // 2] ^= 0xFF
        piste.write_bytes(bytes(donnees))
        self.assertEqual(verificateur.check(piste, complet=False), "")
        self.assertTrue(verificateur.check(piste, complet=True).startswith("ffmpeg : "))     # le message dépend de ce que l'octet touche : CRC, sous-trame...

    def test_empreinte_trafiquee(self):
        piste = self.encoder("sain.flac")
        donnees = bytearray(piste.read_bytes())
        donnees[8 + 18] ^= 0x55                                    # 4 octets de signature + 4 d'en-tête de bloc + 18 : début de l'empreinte
        piste.write_bytes(bytes(donnees))
        self.assertIn("n'a pas l'empreinte MD5", verificateur.check(piste, complet=True))

    def test_fichier_coupe_vu_des_le_controle_rapide(self):
        piste = self.encoder("sain.flac")
        donnees = piste.read_bytes()
        piste.write_bytes(donnees[:len(donnees) * 2 // 3])
        self.assertIn("incomplète", verificateur.check(piste, complet=False))


if __name__ == "__main__":
    unittest.main()
