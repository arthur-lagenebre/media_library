"""Verify_Mp3.py : ce qu'un passage juge, le bilan, le journal et le code de sortie.

ffmpeg est simulé, hors la dernière classe qui passe par le vrai quand il est installé (avec libmp3lame). Rien n'est jamais écrit à côté des pistes, hors le journal.
"""

import math
import shutil
import subprocess
import sys
import types
import unittest
import wave
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common.tools import run_tool
from libraries.music import decode
from scripts.Music import Verify_Mp3 as verificateur
from tests.test_conversion_programmes import ProgrammeTestCase, outils
from tests.test_mp3 import TRAME_AUDIO, fichier as fichier_mp3
from tests.test_music_decode import FfmpegSimule, resultat

AVEC_LAME = bool(shutil.which("ffmpeg")) and b"libmp3lame" in subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True).stdout


class TestControle(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        self.piste = self.racine / "a.mp3"

    def verifier(self, donnees, complet, ffmpeg=None):
        self.piste.write_bytes(donnees)
        ffmpeg = ffmpeg or FfmpegSimule()
        with mock.patch.object(decode, "run_tool", ffmpeg):
            return verificateur.check(self.piste, complet), ffmpeg

    def test_le_controle_rapide_ne_lance_aucun_outil(self):
        message, ffmpeg = self.verifier(fichier_mp3(), complet=False)
        self.assertEqual(message, "")
        self.assertEqual(ffmpeg.commandes, [])

    def test_une_chaine_rompue_n_attend_pas_le_decodage(self):
        message, ffmpeg = self.verifier(fichier_mp3(son=(TRAME_AUDIO * 40)[:-100]), complet=True)
        self.assertIn("dernière trame incomplète", message)
        self.assertEqual(ffmpeg.commandes, [])

    def test_le_decodage_complete_la_chaine(self):
        message, ffmpeg = self.verifier(fichier_mp3(), complet=True, ffmpeg=FfmpegSimule(resultat(stderr="[mp3float @ 1] Header missing")))
        self.assertEqual(message, "ffmpeg : Header missing")
        self.assertEqual(ffmpeg.commandes[0][-3:], ["-f", "null", "-"])       # pas d'empreinte à comparer dans un .mp3


class TestMain(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        self.sain = fichier_mp3()
        (self.racine / "01 - Sain.mp3").write_bytes(self.sain)
        (self.racine / "02 - Sain.MP3").write_bytes(self.sain)
        (self.racine / "03 - Autre format.flac").write_bytes(b"pas du mp3")     # hors du champ de ce script
        self.avant = {p.name: p.read_bytes() for p in self.racine.iterdir()}

    def lancer(self, *argv, ffmpeg=None, tools=("ffmpeg",)):
        if "--log" not in argv:
            argv = ("--log", str(self.racine / "verification_mp3.log"), *argv)
        with mock.patch.object(decode, "run_tool", ffmpeg or FfmpegSimule()):
            return self.lancer_main(verificateur, *argv, shutil=types.SimpleNamespace(which=outils(*tools)))

    def journal(self):
        return (self.racine / "verification_mp3.log").read_text(encoding="utf-8")

    def test_sans_log_aucun_journal(self):
        with mock.patch.object(decode, "run_tool", FfmpegSimule()):
            code, texte = self.lancer_main(verificateur, shutil=types.SimpleNamespace(which=outils("ffmpeg")))
        self.assertFalse((self.racine / "verification_mp3.log").exists())
        self.assertNotIn("[log]", texte)

    def test_pistes_saines(self):
        code, texte = self.lancer()
        self.assertEqual(code, 0)
        self.assertIn("TOTAL : 2 piste(s) contrôlée(s)", texte)         # le .flac n'est pas pris, ".MP3" l'est
        self.assertIn("0 en défaut", texte)
        self.assertIn("reste invisible", texte)                         # le contrôle dit ce qu'il ne voit pas
        self.assertIn("Aucun défaut.", self.journal())

    def test_piste_coupee_code_1_et_journal(self):
        (self.racine / "04 - Coupee.mp3").write_bytes(fichier_mp3(son=(TRAME_AUDIO * 40)[:-100]))
        code, texte = self.lancer()
        self.assertEqual(code, 1)
        self.assertIn("[DÉFAUT] 04 - Coupee.mp3", texte)
        self.assertIn("ne se répare pas", texte)
        journal = self.journal()
        self.assertIn("04 - Coupee.mp3\n    dernière trame incomplète", journal)
        self.assertNotIn("01 - Sain.mp3", journal)

    def test_trou_dans_le_son(self):
        (self.racine / "04 - Trou.mp3").write_bytes(fichier_mp3(son=TRAME_AUDIO * 10 + bytes(200) + TRAME_AUDIO * 30))
        code, texte = self.lancer()
        self.assertEqual(code, 1)
        self.assertIn("synchro perdue", texte)
        self.assertIn("le son reprend 200 octets plus loin", texte)

    def test_rien_n_est_ecrit_hors_le_journal(self):
        (self.racine / "04 - Coupee.mp3").write_bytes(self.sain[:-100])
        self.avant["04 - Coupee.mp3"] = self.sain[:-100]
        self.lancer()
        self.lancer("--full", ffmpeg=FfmpegSimule(resultat(stderr="[mp3float @ 1] Header missing")))
        self.assertEqual({p.name: p.read_bytes() for p in self.racine.iterdir() if p.name != "verification_mp3.log"}, self.avant)

    def test_le_controle_complet_decode_chaque_piste(self):
        ffmpeg = FfmpegSimule()
        code, texte = self.lancer("--full", ffmpeg=ffmpeg)
        self.assertEqual(code, 0)
        self.assertEqual(len(ffmpeg.commandes), 2)
        self.assertIn("Contrôle complet", texte)
        self.assertIn("reste invisible", texte)                         # --full n'y change rien, et le dit aussi

    def test_defaut_vu_seulement_au_decodage(self):
        code, texte = self.lancer("--full", ffmpeg=FfmpegSimule(resultat(stderr="[mp3float @ 1] Header missing")))
        self.assertEqual(code, 1)
        self.assertIn("2 en défaut", texte)
        self.assertIn("ffmpeg : Header missing", self.journal())

    def test_sans_ffmpeg_le_controle_rapide_marche(self):
        self.assertEqual(self.lancer(tools=())[0], 0)

    def test_sans_ffmpeg_le_controle_complet_s_arrete_avec_le_remede(self):
        code, _ = self.lancer("--full", tools=())
        self.assertIn("ffmpeg est introuvable", code)
        self.assertIn("winget install Gyan.FFmpeg", code)

    def test_dossier_sans_mp3(self):
        for p in self.racine.iterdir():
            if p.suffix.lower() == ".mp3":
                p.unlink()
        self.assertIn("Aucun .mp3", self.lancer()[0])

    def test_sans_recursion(self):
        (self.racine / "Sous").mkdir()
        (self.racine / "Sous" / "Coupee.mp3").write_bytes(self.sain[:-100])
        self.assertEqual(self.lancer("--no-recursive")[0], 0)
        self.assertIn("sans les sous-dossiers", self.journal())
        self.assertEqual(self.lancer()[0], 1)

    def test_journal_ou_l_utilisateur_le_demande(self):
        destination = self.racine / "ailleurs.log"
        self.lancer("--log", str(destination))
        self.assertTrue(destination.exists())
        self.assertFalse((self.racine / "verification_mp3.log").exists())


@unittest.skipUnless(AVEC_LAME, "ffmpeg ou libmp3lame absent : le vrai décodage n'est pas testé")
class TestAvecLeVraiFfmpeg(ProgrammeTestCase):
    """De vrais .mp3 : CBR et VBR (leur en-tête Xing/Info), coupés, troués."""

    def encoder(self, nom, *options):
        wav = self.racine / "source.wav"
        with wave.open(str(wav), "wb") as f:
            f.setnchannels(2)
            f.setsampwidth(2)
            f.setframerate(44100)
            f.writeframes(b"".join(
                int(8000 * math.sin(i / 20 + c) + (i * 7919 % 2001 - 1000)).to_bytes(2, "little", signed=True)
                for i in range(44100 * 2) for c in range(2)))
        sortie = self.racine / nom
        run_tool(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-c:a", "libmp3lame", *options, str(sortie)])
        wav.unlink()
        return sortie

    def test_cbr_et_vbr_sains_passent_aux_deux_niveaux(self):
        for nom, options in (("cbr.mp3", ("-b:a", "128k")), ("vbr.mp3", ("-q:a", "2"))):
            with self.subTest(nom):
                piste = self.encoder(nom, *options)
                self.assertEqual(verificateur.check(piste, complet=False), "")
                self.assertEqual(verificateur.check(piste, complet=True), "")

    def test_etiquette_id3v1_ajoutee_apres_coup_n_est_pas_un_defaut(self):
        piste = self.encoder("cbr.mp3", "-b:a", "128k")
        piste.write_bytes(piste.read_bytes() + b"TAG" + bytes(125))
        self.assertEqual(verificateur.check(piste, complet=False), "")

    def test_fichier_coupe(self):
        piste = self.encoder("cbr.mp3", "-b:a", "128k")
        piste.write_bytes(piste.read_bytes()[:-5000])
        self.assertIn("incomplète", verificateur.check(piste, complet=False))

    def test_trou_de_zeros(self):
        piste = self.encoder("cbr.mp3", "-b:a", "128k")
        donnees = bytearray(piste.read_bytes())
        donnees[20000:20300] = bytes(300)
        piste.write_bytes(bytes(donnees))
        self.assertIn("synchro perdue", verificateur.check(piste, complet=False))


if __name__ == "__main__":
    unittest.main()
