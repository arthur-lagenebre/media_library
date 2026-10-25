"""Wav_To_Flac : quels fichiers un passage prend, ce qu'il demande à ffmpeg, et ce que le dossier contient APRÈS.

ffmpeg et ffprobe sont simulés : le .flac n'existe que si l'empreinte du son décodé est la même que celle du .wav, rien ne traîne, l'original n'est effacé que sur ce contrôle réussi. Un dernier test, lui, passe par le vrai ffmpeg quand il est installé.
"""

import io
import json
import math
import shutil
import struct
import sys
import tempfile
import types
import unittest
import wave
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common.tools import PARTIAL_SUFFIX
from scripts.Converters.Music import Wav_To_Flac as conversion


def options(**overrides):
    values = dict(compression=8, apply=True, output_dir=None, overwrite=False, delete_source=False)
    values.update(overrides)
    return types.SimpleNamespace(**values)


class FfmpegSimule:
    """Remplace run_tool : répond comme ffprobe (codec), ffmpeg (encodage) ou ffmpeg -f md5 (empreinte).

    `hashes` donne, fichier après fichier, l'empreinte de la source puis celle du .flac produit (sans lui, toutes sont identiques) ; `codec` ce que ffprobe dit du .wav.
    """

    def __init__(self, codec="pcm_s16le", code=0, writes=b"FLAC", stderr="", hashes=None, probe_code=0):
        self.codec, self.code, self.writes, self.stderr, self.probe_code = codec, code, writes, stderr, probe_code
        self.hashes = None if hashes is None else list(hashes)   # None : toujours la même empreinte, quel que soit le nombre de fichiers
        self.commands = []

    def __call__(self, command, **kwargs):
        self.commands.append(command)
        if command[0] == "ffprobe":
            streams = [{"codec_name": self.codec}] if self.codec else []
            return types.SimpleNamespace(returncode=self.probe_code, stdout=json.dumps({"streams": streams}), stderr="")
        if "md5" in command:
            if self.hashes is None:
                return types.SimpleNamespace(returncode=0, stdout="MD5=AA\n", stderr="")
            if not self.hashes:
                return types.SimpleNamespace(returncode=1, stdout="", stderr="illisible")
            return types.SimpleNamespace(returncode=0, stdout=self.hashes.pop(0) + "\n", stderr="")
        if self.writes is not None:
            Path(command[-1]).write_bytes(self.writes)
        return types.SimpleNamespace(returncode=self.code, stdout="", stderr=self.stderr)

    def encodings(self):
        return [c for c in self.commands if c[0] == "ffmpeg" and "md5" not in c]


class ProgrammeTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.racine = Path(self._tmp.name)

    def noms(self, dossier=None):
        return sorted(p.name for p in (dossier or self.racine).iterdir())


class TestFichiers(ProgrammeTestCase):
    def test_wav_seuls_racine_d_abord_extension_sans_casse(self):
        (self.racine / "Album").mkdir()
        for nom in ("b.wav", "A.WAV", "c.flac", "d.mp3", "Album/01.wav"):
            (self.racine / nom).write_bytes(b"")
        self.assertEqual([p.name for p in conversion.wav_files(self.racine)], ["A.WAV", "b.wav", "01.wav"])

    def test_no_recursive_ne_descend_pas(self):
        (self.racine / "Album").mkdir()
        for nom in ("b.wav", "Album/01.wav"):
            (self.racine / nom).write_bytes(b"")
        self.assertEqual([p.name for p in conversion.wav_files(self.racine, recursive=False)], ["b.wav"])

    def test_un_dossier_nomme_wav_n_est_pas_un_fichier(self):
        (self.racine / "Mix.wav").mkdir()
        self.assertEqual(conversion.wav_files(self.racine), [])


class TestCommande(unittest.TestCase):
    def test_commande_ffmpeg(self):
        commande = conversion.build_command(Path("a.wav"), Path("a.flac.part"), options(compression=12))
        self.assertEqual(commande[0], "ffmpeg")
        self.assertEqual(commande[commande.index("-i") + 1], "a.wav")
        self.assertEqual(commande[commande.index("-compression_level") + 1], "12")
        self.assertEqual(commande[commande.index("-c:a") + 1], "flac")
        self.assertEqual(commande[commande.index("-map") + 1], "0:a:0")
        self.assertEqual(commande[commande.index("-map_metadata") + 1], "0")
        # Le format est dit à ffmpeg : il ne le devinerait pas d'un nom en .part.
        self.assertEqual(commande[-3:], ["-f", "flac", "a.flac.part"])

    def test_commande_affichee_avec_ses_guillemets(self):
        commande = ["ffmpeg", "-i", "D:\\Ma Musique\\a.wav"]
        self.assertEqual(conversion.display_command(commande), 'ffmpeg -i "D:\\Ma Musique\\a.wav"')

    def test_derniere_ligne_d_erreur(self):
        resultat = types.SimpleNamespace(stderr="Guessed Channel Layout\n\nError opening output: Invalid argument\n")
        self.assertEqual(conversion.last_error(resultat), "Error opening output: Invalid argument")
        self.assertEqual(conversion.last_error(types.SimpleNamespace(stderr=None)), "")


class TestConversion(ProgrammeTestCase):
    """Ce que devient un dossier, fichier par fichier."""

    def setUp(self):
        super().setUp()
        self.wav = self.racine / "01 - Titre.wav"
        self.wav.write_bytes(b"W" * 1000)
        self.final = self.racine / "01 - Titre.flac"
        self.partial = self.racine / ("01 - Titre.flac" + PARTIAL_SUFFIX)

    def convert(self, ffmpeg, **overrides):
        with mock.patch.object(conversion, "run_tool", ffmpeg):
            return conversion.convert(self.wav, options(**overrides))

    def test_conversion_reussie(self):
        status, detail = self.convert(FfmpegSimule(writes=b"F" * 400))
        self.assertEqual(status, "converti")
        self.assertIn("son identique (16 bits)", detail)
        self.assertIn("40%", detail)
        self.assertEqual(self.final.read_bytes(), b"F" * 400)
        self.assertEqual(self.noms(), ["01 - Titre.flac", "01 - Titre.wav"])   # la source reste, rien d'autre ne traîne

    def test_24_bits_aussi(self):
        status, detail = self.convert(FfmpegSimule(codec="pcm_s24le"))
        self.assertEqual(status, "converti")
        self.assertIn("24 bits", detail)

    def test_ffmpeg_ecrit_sous_un_nom_provisoire(self):
        ffmpeg = FfmpegSimule()
        self.convert(ffmpeg)
        self.assertEqual(Path(ffmpeg.encodings()[0][-1]), self.partial)

    def test_simulation_n_ecrit_rien(self):
        ffmpeg = FfmpegSimule()
        status, detail = self.convert(ffmpeg, apply=False)
        self.assertEqual(status, "simule")
        self.assertIn("ffmpeg", detail)
        self.assertEqual(ffmpeg.encodings(), [])
        self.assertEqual(self.noms(), ["01 - Titre.wav"])

    def test_flac_deja_present_est_passe(self):
        self.final.write_bytes(b"ANCIEN")
        ffmpeg = FfmpegSimule()
        status, detail = self.convert(ffmpeg)
        self.assertEqual(status, "ignoré")
        self.assertIn("--overwrite", detail)
        self.assertEqual(self.final.read_bytes(), b"ANCIEN")
        self.assertEqual(ffmpeg.commands, [])

    def test_overwrite_remplace_l_ancien(self):
        self.final.write_bytes(b"ANCIEN")
        status, _ = self.convert(FfmpegSimule(writes=b"NEUF"), overwrite=True)
        self.assertEqual(status, "converti")
        self.assertEqual(self.final.read_bytes(), b"NEUF")

    def test_ecart_de_son_ne_laisse_aucun_flac_et_garde_la_source(self):
        status, detail = self.convert(FfmpegSimule(hashes=("MD5=AA", "MD5=BB")), delete_source=True)
        self.assertEqual(status, "écart")
        self.assertIn("l'original est gardé", detail)
        self.assertEqual(self.noms(), ["01 - Titre.wav"])

    def test_ecart_n_ecrase_pas_un_flac_existant(self):
        self.final.write_bytes(b"ANCIEN")
        status, _ = self.convert(FfmpegSimule(hashes=("MD5=AA", "MD5=BB")), overwrite=True)
        self.assertEqual(status, "écart")
        self.assertEqual(self.final.read_bytes(), b"ANCIEN")
        self.assertFalse(self.partial.exists())

    def test_empreinte_illisible_est_une_erreur(self):
        status, detail = self.convert(FfmpegSimule(hashes=()), delete_source=True)
        self.assertEqual(status, "erreur")
        self.assertIn("comparé", detail)
        self.assertEqual(self.noms(), ["01 - Titre.wav"])

    def test_echec_de_ffmpeg_dit_pourquoi_et_ne_laisse_rien(self):
        status, detail = self.convert(FfmpegSimule(code=1, stderr="bruit\nDisque plein"))
        self.assertEqual(status, "erreur")
        self.assertEqual(detail, "Disque plein")
        self.assertEqual(self.noms(), ["01 - Titre.wav"])

    def test_ffmpeg_qui_n_ecrit_rien(self):
        status, detail = self.convert(FfmpegSimule(writes=None))
        self.assertEqual(status, "erreur")
        self.assertIn("rien pu écrire", detail)

    def test_reste_d_un_passage_interrompu_n_est_pas_pris_pour_la_sortie(self):
        self.partial.write_bytes(b"VIEUX")
        status, _ = self.convert(FfmpegSimule(writes=None))
        self.assertEqual(status, "erreur")
        self.assertFalse(self.partial.exists())

    def test_interruption_ne_laisse_pas_de_fichier_provisoire(self):
        def coupe(command, **kwargs):
            if command[0] == "ffmpeg" and "md5" not in command:
                Path(command[-1]).write_bytes(b"A MOITIE")
                raise KeyboardInterrupt
            return FfmpegSimule()(command)
        with self.assertRaises(KeyboardInterrupt):
            self.convert(coupe)
        self.assertEqual(self.noms(), ["01 - Titre.wav"])

    def test_delete_source_apres_controle(self):
        status, detail = self.convert(FfmpegSimule(), delete_source=True)
        self.assertEqual(status, "converti")
        self.assertIn("source effacée", detail)
        self.assertEqual(self.noms(), ["01 - Titre.flac"])

    def test_source_non_effacee_sans_delete_source(self):
        self.convert(FfmpegSimule())
        self.assertTrue(self.wav.exists())

    def test_flottant_refuse_car_ffmpeg_l_arrondirait(self):
        ffmpeg = FfmpegSimule(codec="pcm_f32le")
        status, detail = self.convert(ffmpeg, delete_source=True)
        self.assertEqual(status, "erreur")
        self.assertIn("pcm_f32le", detail)
        self.assertEqual(ffmpeg.encodings(), [])
        self.assertEqual(self.noms(), ["01 - Titre.wav"])

    def test_32_bits_et_8_bits_refuses(self):
        for codec in ("pcm_s32le", "pcm_u8"):
            with self.subTest(codec):
                status, _ = self.convert(FfmpegSimule(codec=codec))
                self.assertEqual(status, "erreur")

    def test_fichier_sans_audio_ou_illisible(self):
        for ffmpeg in (FfmpegSimule(codec=None), FfmpegSimule(probe_code=1)):
            with self.subTest(codec=ffmpeg.codec, code=ffmpeg.probe_code):
                status, detail = self.convert(ffmpeg)
                self.assertEqual(status, "erreur")
                self.assertIn("aucune piste audio", detail)

    def test_output_dir_pose_a_plat_et_cree_le_dossier(self):
        sortie = self.racine / "Flac" / "Album"
        status, _ = self.convert(FfmpegSimule(), output_dir=sortie)
        self.assertEqual(status, "converti")
        self.assertEqual(self.noms(sortie), ["01 - Titre.flac"])

    def test_wav_vide_ne_divise_pas_par_zero(self):
        self.wav.write_bytes(b"")
        status, detail = self.convert(FfmpegSimule())
        self.assertEqual(status, "converti")
        self.assertNotIn("%", detail)


def outils(*presents):
    """Un shutil.which qui ne connaît que ces outils."""
    return lambda nom: f"/usr/bin/{nom}" if nom in presents else None


class TestMain(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        (self.racine / "A.wav").write_bytes(b"A" * 100)
        (self.racine / "Sous").mkdir()
        (self.racine / "Sous" / "B.wav").write_bytes(b"B" * 100)

    def lancer(self, *argv, ffmpeg=None, tools=("ffmpeg", "ffprobe")):
        """(code, affichage). Un sys.exit("message") rend le message comme code, comme le fait Python."""
        ligne = [str(Path(conversion.__file__)), "--dir", str(self.racine), *argv]
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, "argv", ligne))
            stack.enter_context(mock.patch.object(conversion, "shutil", types.SimpleNamespace(which=outils(*tools))))
            stack.enter_context(mock.patch.object(conversion, "run_tool", ffmpeg or FfmpegSimule()))
            texte = stack.enter_context(redirect_stdout(io.StringIO()))
            try:
                code = conversion.main()
            except SystemExit as sortie:
                code = sortie.code
        return code, texte.getvalue()

    def journal(self):
        return (self.racine / "conversion_flac.log").read_text(encoding="utf-8")

    def test_ffmpeg_absent(self):
        code, _ = self.lancer(tools=("ffprobe",))
        self.assertIn("ffmpeg est introuvable", code)

    def test_ffprobe_absent(self):
        code, _ = self.lancer(tools=("ffmpeg",))
        self.assertIn("ffprobe est introuvable", code)

    def test_les_deux_absents(self):
        code, _ = self.lancer(tools=())
        self.assertIn("ffmpeg et ffprobe sont introuvables", code)

    def test_aucun_fichier(self):
        vide = self.racine / "vide"
        vide.mkdir()
        self.racine = vide
        code, _ = self.lancer()
        self.assertIn("Aucun .wav sous", code)

    def test_dossier_introuvable(self):
        self.racine = self.racine / "n_existe_pas"
        code, _ = self.lancer()
        self.assertIn("introuvable", code)

    def test_simulation_n_ecrit_que_le_journal(self):
        code, texte = self.lancer()
        self.assertEqual(code, 0)
        self.assertIn("SIMULATION", texte)
        self.assertIn("Simulation : rien n'a été écrit", texte)
        self.assertEqual(self.noms(), ["A.wav", "Sous", "conversion_flac.log"])
        self.assertIn("2 simule", self.journal())

    def test_passage_complet(self):
        code, texte = self.lancer("--apply")
        self.assertEqual(code, 0)
        self.assertIn("2 converti", texte)
        self.assertIn("Music/Metadata.py", texte)
        self.assertEqual(self.noms(), ["A.flac", "A.wav", "Sous", "conversion_flac.log"])
        self.assertEqual(self.noms(self.racine / "Sous"), ["B.flac", "B.wav"])

    def test_no_recursive(self):
        code, texte = self.lancer("--apply", "--no-recursive")
        self.assertEqual(code, 0)
        self.assertIn("(sous-dossiers ignorés)", texte)
        self.assertEqual(self.noms(self.racine / "Sous"), ["B.wav"])

    def test_delete_source_ne_rappelle_pas_d_etiqueter_les_wav(self):
        code, texte = self.lancer("--apply", "--delete-source")
        self.assertEqual(code, 0)
        self.assertNotIn("sont toujours à côté", texte)
        self.assertEqual(self.noms(), ["A.flac", "Sous", "conversion_flac.log"])

    def test_un_fichier_en_erreur_sort_en_code_1_et_figure_au_journal(self):
        (self.racine / "Mauvais.wav").write_bytes(b"?")
        ffmpeg = FfmpegSimule(hashes=("MD5=AA", "MD5=AA", "MD5=AA", "MD5=BB", "MD5=AA", "MD5=AA"))
        code, texte = self.lancer("--apply", ffmpeg=ffmpeg)
        self.assertEqual(code, 1)
        self.assertIn("[ÉCART]", texte)
        journal = self.journal()
        self.assertIn("NON CONVERTIS (originaux intacts) :", journal)
        self.assertIn("2 converti", journal)
        self.assertIn("1 écart", journal)

    def test_log_place_ailleurs(self):
        ailleurs = self.racine / "mon.log"
        self.lancer("--log", str(ailleurs))
        self.assertTrue(ailleurs.exists())
        self.assertFalse((self.racine / "conversion_flac.log").exists())


class TestArguments(unittest.TestCase):
    def parse(self, *argv):
        with mock.patch.object(sys, "argv", ["Wav_To_Flac.py", "--dir", "x", *argv]):
            return conversion.parse_args()

    def test_valeurs_par_defaut(self):
        args = self.parse()
        self.assertEqual((args.apply, args.compression, args.delete_source, args.overwrite, args.no_recursive, args.output_dir),
                         (False, 8, False, False, False, None))

    def test_output_dir_devient_un_chemin(self):
        self.assertEqual(self.parse("--output-dir", "D:\\Flac").output_dir, Path("D:\\Flac"))

    def test_compression_hors_bornes_refusee(self):
        for valeur in ("-1", "13", "max"):
            with self.subTest(valeur), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.parse("--compression", valeur)

    def test_compression_aux_bornes(self):
        self.assertEqual(self.parse("--compression", "0").compression, 0)
        self.assertEqual(self.parse("--compression", "12").compression, 12)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg absent : le vrai encodage n'est pas testé")
class TestAvecLeVraiFfmpeg(ProgrammeTestCase):
    """Un vrai .wav, un vrai .flac : ce que les simulations ne peuvent pas dire."""

    def ecrire_wav(self, chemin, largeur=2, canaux=2):
        with wave.open(str(chemin), "wb") as wav:
            wav.setnchannels(canaux)
            wav.setsampwidth(largeur)
            wav.setframerate(44100)
            amplitude = 2 ** (8 * largeur - 2)
            wav.writeframes(b"".join(
                int(amplitude * math.sin(i / 20 + canal)).to_bytes(largeur, "little", signed=True)
                for i in range(4410) for canal in range(canaux)))

    def lancer(self, *argv):
        ligne = [str(Path(conversion.__file__)), "--dir", str(self.racine), "--apply", *argv]
        with mock.patch.object(sys, "argv", ligne), redirect_stdout(io.StringIO()):
            return conversion.main()

    def test_16_et_24_bits_ressortent_identiques(self):
        self.ecrire_wav(self.racine / "seize.wav", largeur=2)
        self.ecrire_wav(self.racine / "vingt-quatre.wav", largeur=3, canaux=1)
        self.assertEqual(self.lancer(), 0)
        self.assertEqual(self.noms(), ["conversion_flac.log", "seize.flac", "seize.wav", "vingt-quatre.flac", "vingt-quatre.wav"])
        for nom in ("seize", "vingt-quatre"):
            self.assertEqual(conversion.sound_hash(self.racine / f"{nom}.wav"), conversion.sound_hash(self.racine / f"{nom}.flac"))
        self.assertEqual((self.racine / "seize.flac").read_bytes()[:4], b"fLaC")

    def test_wav_corrompu_ne_donne_pas_de_flac(self):
        (self.racine / "faux.wav").write_bytes(b"RIFF" + struct.pack("<I", 4) + b"WAVE")
        self.assertEqual(self.lancer(), 1)
        self.assertEqual(self.noms(), ["conversion_flac.log", "faux.wav"])


if __name__ == "__main__":
    unittest.main()
