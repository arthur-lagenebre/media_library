"""Flac_To_Mp3 : quels fichiers un passage prend, ce qu'il demande à ffmpeg, et ce que les deux dossiers contiennent APRÈS.

ffmpeg est simulé : il écrit une chaîne de trames MP3 fabriquée octet par octet, que le script étiquette puis contrôle comme un vrai .mp3. Le .flac n'est jamais touché, aucun .mp3 partiel ne traîne. Une dernière classe passe par le vrai ffmpeg quand il est installé avec libmp3lame.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common.tools import PARTIAL_SUFFIX
from libraries.music import flac, mp3
from scripts.Music import Flac_To_Mp3 as conversion
from tests.test_conversion_programmes import ProgrammeTestCase, outils
from tests.test_flac import fichier as fichier_flac, image
from tests.test_mp3 import TRAME_AUDIO

AVEC_LAME = bool(shutil.which("ffmpeg")) and b"libmp3lame" in subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True).stdout
POCHETTE = b"\xff\xd8\xff\xe0" + bytes(60)
SON_10_S = TRAME_AUDIO * 384          # 384 trames CBR de 417 octets à 128 kbit/s : 10,0 s, la durée du .flac d'essai
TAGS = ("TITLE=Été", "ARTIST=AC/DC", "TRACKNUMBER=1", "TRACKTOTAL=9", "MUSICBRAINZ_ALBUMID=4e5d9f0c-09b6-42bf-b495-e2d7cc288bf6", "ENCODER=reference libFLAC 1.4.3")


def options(sortie, **overrides):
    values = dict(apply=True, overwrite=False, output_dir=sortie, quality="320")
    values.update(overrides)
    return types.SimpleNamespace(**values)


class FfmpegSimule:
    """Remplace run_tool : écrit `writes` là où ffmpeg écrirait, et répond `code`."""

    def __init__(self, writes=SON_10_S, code=0, stderr=""):
        self.writes, self.code, self.stderr = writes, code, stderr
        self.commands = []

    def __call__(self, command, **kwargs):
        self.commands.append(command)
        if self.writes is not None:
            Path(command[-1]).write_bytes(self.writes)
        return types.SimpleNamespace(returncode=self.code, stdout="", stderr=self.stderr)


class Flac2Mp3TestCase(ProgrammeTestCase):
    """--dir est self.racine (les .flac), --output-dir un autre dossier temporaire."""

    def setUp(self):
        super().setUp()
        sortie = tempfile.TemporaryDirectory()
        self.addCleanup(sortie.cleanup)
        self.sortie = Path(sortie.name)

    def poser_flac(self, relatif, lignes=TAGS, images=()):
        chemin = self.racine / relatif
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(fichier_flac(lignes, extra=[(flac.PICTURE, image(data)) for data in images]))
        return chemin

    def fichiers(self, dossier):
        return sorted(p.relative_to(dossier).as_posix() for p in dossier.rglob("*") if p.is_file())


class TestFichiers(Flac2Mp3TestCase):
    def test_flac_seuls_racine_d_abord_extension_sans_casse(self):
        (self.racine / "Album").mkdir()
        for nom in ("b.flac", "A.FLAC", "c.mp3", "d.wav", "Album/01.flac"):
            (self.racine / nom).write_bytes(b"")
        self.assertEqual([p.name for p in conversion.flac_files(self.racine)], ["A.FLAC", "b.flac", "01.flac"])

    def test_no_recursive_ne_descend_pas(self):
        (self.racine / "Album").mkdir()
        for nom in ("b.flac", "Album/01.flac"):
            (self.racine / nom).write_bytes(b"")
        self.assertEqual([p.name for p in conversion.flac_files(self.racine, recursive=False)], ["b.flac"])

    def test_mp3_a_recopier_sauf_celui_qu_un_flac_remplace(self):
        (self.racine / "Album").mkdir()
        for nom in ("Album/01.flac", "Album/01.MP3", "Album/02.mp3", "c.mp3", "Album/03.wav"):
            (self.racine / nom).write_bytes(b"")
        flacs = conversion.flac_files(self.racine)
        copies, ecartes = conversion.mp3_files(self.racine, flacs)
        self.assertEqual([p.name for p in copies], ["c.mp3", "02.mp3"])
        self.assertEqual([p.name for p in ecartes], ["01.MP3"])

    def test_mp3_no_recursive_ne_descend_pas(self):
        (self.racine / "Album").mkdir()
        for nom in ("a.mp3", "Album/01.mp3"):
            (self.racine / nom).write_bytes(b"")
        self.assertEqual([p.name for p in conversion.mp3_files(self.racine, [], recursive=False)[0]], ["a.mp3"])

    def test_le_mp3_reprend_l_arborescence(self):
        source = self.racine / "Artiste" / "Album" / "01 - Titre.FLAC"
        self.assertEqual(conversion.target_path(source, self.racine, self.sortie), self.sortie / "Artiste" / "Album" / "01 - Titre.mp3")


class TestCommande(unittest.TestCase):
    def test_mp3_320_constant_son_seul(self):
        commande = conversion.build_command(Path("a.flac"), Path("a.mp3.part"), 44100)
        self.assertEqual(commande[commande.index("-i") + 1], "a.flac")
        self.assertEqual(commande[commande.index("-c:a") + 1], "libmp3lame")
        self.assertEqual(commande[commande.index("-b:a") + 1], "320k")
        self.assertEqual(commande[commande.index("-map") + 1], "0:a:0")
        # ffmpeg n'écrit aucun tag : c'est mp3.py qui s'en charge, à la manière de Picard.
        self.assertEqual(commande[commande.index("-map_metadata") + 1], "-1")
        self.assertEqual(commande[commande.index("-id3v2_version") + 1], "0")
        self.assertNotIn("-ar", commande)
        self.assertNotIn("-q:a", commande)
        self.assertEqual(commande[-3:], ["-f", "mp3", "a.mp3.part"])

    def test_v0_debit_variable_sans_debit_impose(self):
        commande = conversion.build_command(Path("a.flac"), Path("a.mp3.part"), 44100, "v0")
        self.assertEqual(commande[commande.index("-q:a") + 1], "0")
        self.assertNotIn("-b:a", commande)
        self.assertEqual(commande[commande.index("-c:a") + 1], "libmp3lame")

    def test_haute_resolution_ramenee_a_ce_que_le_mp3_connait(self):
        for frequence, attendue in ((48000, None), (96000, 48000), (192000, 48000), (88200, 44100), (176400, 44100)):
            with self.subTest(frequence):
                self.assertEqual(conversion.output_rate(frequence), attendue)
        commande = conversion.build_command(Path("a.flac"), Path("a.mp3"), 96000)
        self.assertEqual(commande[commande.index("-ar") + 1], "48000")


class TestConversion(Flac2Mp3TestCase):
    """Ce que deviennent les deux dossiers, fichier par fichier."""

    def setUp(self):
        super().setUp()
        self.flac = self.poser_flac("Artiste/Album/01 - Titre.flac", images=(POCHETTE,))
        self.original = self.flac.read_bytes()
        self.final = self.sortie / "Artiste" / "Album" / "01 - Titre.mp3"
        self.partial = self.final.with_name(self.final.name + PARTIAL_SUFFIX)

    def convert(self, ffmpeg=None, **overrides):
        with mock.patch.object(conversion, "run_tool", ffmpeg or FfmpegSimule()):
            return conversion.convert(self.flac, self.racine, options(self.sortie, **overrides))

    def test_conversion_reussie_tags_et_pochette_suivent(self):
        status, detail = self.convert()
        self.assertEqual(status, "converti")
        self.assertIn("1 image(s)", detail)
        self.assertEqual(self.fichiers(self.sortie), ["Artiste/Album/01 - Titre.mp3"])
        lu = mp3.read(self.final)
        self.assertEqual(lu.first("TITLE"), "Été")
        self.assertEqual(lu.first("ARTIST"), "AC/DC")
        self.assertEqual((lu.first("TRACKNUMBER"), lu.first("TRACKTOTAL")), ("1", "9"))
        self.assertEqual(lu.first("MUSICBRAINZ_ALBUMID"), "4e5d9f0c-09b6-42bf-b495-e2d7cc288bf6")
        self.assertEqual([p.data for p in lu.pictures if p.kind == 3], [POCHETTE])
        self.assertTrue(self.final.read_bytes().endswith(SON_10_S))      # le son est celui de l'encodeur, intact

    def test_l_encodeur_du_flac_ne_suit_pas(self):
        self.convert()
        self.assertEqual(mp3.read(self.final).first("ENCODER"), "")

    def test_le_flac_n_est_jamais_touche(self):
        self.convert()
        self.assertEqual(self.flac.read_bytes(), self.original)
        self.assertEqual(self.fichiers(self.racine), ["Artiste/Album/01 - Titre.flac"])

    def test_ffmpeg_ecrit_sous_un_nom_provisoire(self):
        ffmpeg = FfmpegSimule()
        self.convert(ffmpeg)
        self.assertEqual(Path(ffmpeg.commands[0][-1]), self.partial)

    def test_simulation_n_ecrit_rien(self):
        ffmpeg = FfmpegSimule()
        status, detail = self.convert(ffmpeg, apply=False)
        self.assertEqual(status, "simule")
        self.assertIn("libmp3lame", detail)
        self.assertEqual(ffmpeg.commands, [])
        self.assertEqual(self.fichiers(self.sortie), [])

    def test_mp3_deja_present_est_passe(self):
        self.final.parent.mkdir(parents=True)
        self.final.write_bytes(b"ANCIEN")
        ffmpeg = FfmpegSimule()
        status, detail = self.convert(ffmpeg)
        self.assertEqual(status, "ignoré")
        self.assertIn("--overwrite", detail)
        self.assertEqual(self.final.read_bytes(), b"ANCIEN")
        self.assertEqual(ffmpeg.commands, [])

    def test_overwrite_reencode(self):
        self.final.parent.mkdir(parents=True)
        self.final.write_bytes(b"ANCIEN")
        status, _ = self.convert(overwrite=True)
        self.assertEqual(status, "converti")
        self.assertEqual(mp3.read(self.final).first("TITLE"), "Été")

    def test_flac_illisible(self):
        self.flac.write_bytes(b"pas un flac")
        ffmpeg = FfmpegSimule()
        status, detail = self.convert(ffmpeg)
        self.assertEqual(status, "erreur")
        self.assertIn("illisible", detail)
        self.assertEqual(ffmpeg.commands, [])

    def test_echec_de_ffmpeg_dit_pourquoi_et_ne_laisse_rien(self):
        status, detail = self.convert(FfmpegSimule(code=1, stderr="bruit\nUnknown encoder 'libmp3lame'"))
        self.assertEqual(status, "erreur")
        self.assertEqual(detail, "Unknown encoder 'libmp3lame'")
        self.assertEqual(self.fichiers(self.sortie), [])

    def test_ffmpeg_qui_n_ecrit_rien(self):
        status, detail = self.convert(FfmpegSimule(writes=None))
        self.assertEqual(status, "erreur")
        self.assertIn("rien pu écrire", detail)

    def test_mp3_coupe_n_est_pas_garde(self):
        status, detail = self.convert(FfmpegSimule(writes=SON_10_S + TRAME_AUDIO[:200]))
        self.assertEqual(status, "erreur")
        self.assertIn("défectueux", detail)
        self.assertEqual(self.fichiers(self.sortie), [])

    def test_mp3_trop_court_n_est_pas_garde(self):
        status, detail = self.convert(FfmpegSimule(writes=TRAME_AUDIO * 100))
        self.assertEqual(status, "erreur")
        self.assertIn("durée", detail)
        self.assertEqual(self.fichiers(self.sortie), [])

    def test_mp3_illisible_n_est_pas_garde(self):
        status, _ = self.convert(FfmpegSimule(writes=b"rien d'audio"))
        self.assertEqual(status, "erreur")
        self.assertEqual(self.fichiers(self.sortie), [])

    def test_reste_d_un_passage_interrompu_n_est_pas_pris_pour_la_sortie(self):
        self.partial.parent.mkdir(parents=True)
        self.partial.write_bytes(SON_10_S)
        status, _ = self.convert(FfmpegSimule(writes=None))
        self.assertEqual(status, "erreur")
        self.assertFalse(self.partial.exists())

    def test_interruption_ne_laisse_pas_de_fichier_provisoire(self):
        def coupe(command, **kwargs):
            Path(command[-1]).write_bytes(TRAME_AUDIO * 10)
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.convert(coupe)
        self.assertEqual(self.fichiers(self.sortie), [])


class TestMain(Flac2Mp3TestCase):
    def setUp(self):
        super().setUp()
        self.poser_flac("A.flac")
        self.poser_flac("Artiste/Album/01 - B.flac", images=(POCHETTE,))
        self.journal = self.sortie.parent / (self.sortie.name + ".log")
        self.addCleanup(lambda: self.journal.unlink(missing_ok=True))

    def lancer(self, *argv, ffmpeg=None, tools=("ffmpeg",), sortie=None):
        return self.lancer_main(conversion, "--output-dir", str(sortie or self.sortie), *argv,
                                run_tool=ffmpeg or FfmpegSimule(), shutil=types.SimpleNamespace(which=outils(*tools)))

    def test_simulation_n_ecrit_rien(self):
        code, texte = self.lancer()
        self.assertEqual(code, 0)
        self.assertIn("SIMULATION", texte)
        self.assertIn("MP3 320 kb/s constant", texte)
        self.assertIn("2 simule", texte)
        self.assertEqual(self.fichiers(self.sortie), [])

    def test_quality_v0_va_jusqu_a_ffmpeg(self):
        ffmpeg = FfmpegSimule()
        code, texte = self.lancer("--apply", "--quality", "v0", ffmpeg=ffmpeg)
        self.assertEqual(code, 0)
        self.assertIn("MP3 V0", texte)
        self.assertEqual(len(ffmpeg.commands), 2)
        for commande in ffmpeg.commands:
            self.assertEqual(commande[commande.index("-q:a") + 1], "0")

    def test_passage_complet_puis_second_passage_qui_ne_change_rien(self):
        code, texte = self.lancer("--apply")
        self.assertEqual(code, 0)
        self.assertIn("2 converti", texte)
        attendus = ["A.mp3", "Artiste/Album/01 - B.mp3"]
        self.assertEqual(self.fichiers(self.sortie), attendus)
        avant = {nom: (self.sortie / nom).read_bytes() for nom in attendus}

        ffmpeg = FfmpegSimule()
        code, texte = self.lancer("--apply", ffmpeg=ffmpeg)
        self.assertEqual(code, 0)
        self.assertIn("2 ignoré", texte)
        self.assertEqual(ffmpeg.commands, [])
        self.assertEqual({nom: (self.sortie / nom).read_bytes() for nom in attendus}, avant)
        self.assertEqual(self.fichiers(self.racine), ["A.flac", "Artiste/Album/01 - B.flac"])

    def test_no_recursive(self):
        code, _ = self.lancer("--apply", "--no-recursive")
        self.assertEqual(code, 0)
        self.assertEqual(self.fichiers(self.sortie), ["A.mp3"])

    def test_une_erreur_sort_en_code_1_et_figure_au_journal(self):
        (self.racine / "Mauvais.flac").write_bytes(b"?")
        code, texte = self.lancer("--apply", "--log", str(self.journal))
        self.assertEqual(code, 1)
        self.assertIn("[ERREUR]", texte)
        self.assertIn("1 écriture(s) en échec", texte)
        contenu = self.journal.read_text(encoding="utf-8")
        self.assertIn("Mauvais.flac", contenu)
        self.assertIn("2 converti", contenu)

    def test_sans_log_aucun_journal(self):
        _, texte = self.lancer()
        self.assertNotIn("[log]", texte)
        self.assertFalse(self.journal.exists())

    def test_sortie_dans_la_source_refusee(self):
        for sortie in (self.racine, self.racine / "MP3"):
            with self.subTest(sortie=sortie):
                code, _ = self.lancer("--apply", sortie=sortie)
                self.assertIn("hors de --dir", code)
        self.assertEqual(self.fichiers(self.racine), ["A.flac", "Artiste/Album/01 - B.flac"])

    def test_ffmpeg_absent(self):
        code, _ = self.lancer(tools=())
        self.assertIn("ffmpeg est introuvable", code)

    def test_aucun_fichier(self):
        vide = self.racine / "vide"
        vide.mkdir()
        self.racine = vide
        code, _ = self.lancer()
        self.assertIn("Aucun .flac ni .mp3 sous", code)

    def test_dossier_introuvable(self):
        self.racine = self.racine / "n_existe_pas"
        code, _ = self.lancer()
        self.assertIn("introuvable", code)


class TestPochettes(Flac2Mp3TestCase):
    """cover.jpg posé à côté des pistes : recopié tel quel dans le dossier correspondant de --output-dir."""

    def poser(self, relatif, contenu=b"IMAGE"):
        chemin = self.racine / relatif
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(contenu)
        return chemin

    def sources(self, *flacs):
        return [p.relative_to(self.racine).as_posix() for p in conversion.cover_sources([self.racine / f for f in flacs], self.racine)]

    def copier(self, source, **overrides):
        return conversion.copy_cover(source, self.racine, options(self.sortie, **overrides))

    def test_pochette_du_dossier_des_pistes_nom_sans_casse(self):
        self.poser("Artiste/Album/Cover.JPG")
        self.poser("Artiste/Album/notes.jpg")
        self.assertEqual(self.sources("Artiste/Album/01.flac", "Artiste/Album/02.flac"), ["Artiste/Album/Cover.JPG"])

    def test_cover_l_emporte_sur_folder(self):
        self.poser("Album/folder.jpg")
        self.poser("Album/cover.png")
        self.assertEqual(self.sources("Album/01.flac"), ["Album/cover.png"])

    def test_album_en_plusieurs_disques_prend_la_pochette_de_l_album(self):
        self.poser("Artiste/Album/cover.jpg")
        self.poser("Artiste/Album/CD2/cover.jpg", b"PROPRE AU CD2")
        self.assertEqual(self.sources("Artiste/Album/CD1/01.flac", "Artiste/Album/CD2/01.flac"),
                         ["Artiste/Album/cover.jpg", "Artiste/Album/CD2/cover.jpg"])

    def test_ne_remonte_pas_au_dessus_de_dir(self):
        # --dir est le dossier d'un album ; la pochette posée au-dessus (celle de l'artiste) n'est pas à lui.
        self.poser("cover.jpg", b"HORS DE DIR")
        album = self.racine / "Album"
        self.assertEqual(conversion.cover_sources([album / "01.flac"], album), [])

    def test_sans_pochette_rien(self):
        self.assertEqual(self.sources("Album/01.flac"), [])

    def test_copie_a_l_identique_puis_a_jour(self):
        source = self.poser("Artiste/Album/cover.jpg", POCHETTE)
        self.assertEqual(self.copier(source), ("copiée", "cover.jpg copiée"))
        self.assertEqual((self.sortie / "Artiste/Album/cover.jpg").read_bytes(), POCHETTE)
        self.assertEqual(self.fichiers(self.sortie), ["Artiste/Album/cover.jpg"])       # aucun .part qui traîne
        self.assertEqual(self.copier(source)[0], "à jour")

    def test_simulation_n_ecrit_rien(self):
        source = self.poser("Album/cover.jpg")
        status, detail = self.copier(source, apply=False)
        self.assertEqual(status, "simule")
        self.assertIn("sera copiée", detail)
        self.assertEqual(self.fichiers(self.sortie), [])

    def test_pochette_changee_est_remplacee_sans_overwrite(self):
        source = self.poser("Album/cover.jpg", b"ANCIENNE")
        self.copier(source)
        source.write_bytes(b"NOUVELLE POCHETTE")
        self.assertEqual(self.copier(source)[0], "remplacée")
        self.assertEqual((self.sortie / "Album/cover.jpg").read_bytes(), b"NOUVELLE POCHETTE")

    def test_date_arrondie_par_une_cle_fat32_ne_fait_pas_recopier(self):
        source = self.poser("Album/cover.jpg")
        self.copier(source)
        copie = self.sortie / "Album/cover.jpg"
        date = source.stat().st_mtime
        os.utime(copie, (date + 1, date + 1))
        self.assertEqual(self.copier(source)[0], "à jour")
        os.utime(copie, (date + 60, date + 60))
        self.assertEqual(self.copier(source)[0], "remplacée")

    def test_echec_de_copie_est_une_erreur_sans_reste(self):
        source = self.poser("Album/cover.jpg")
        with mock.patch.object(conversion.shutil, "copy2", side_effect=OSError(28, "Disque plein")):
            status, detail = self.copier(source)
        self.assertEqual(status, "erreur")
        self.assertIn("Disque plein", detail)
        self.assertEqual(self.fichiers(self.sortie), [])


class TestMainPochettes(Flac2Mp3TestCase):
    def setUp(self):
        super().setUp()
        self.poser_flac("Artiste/Album/01 - A.flac")
        (self.racine / "Artiste/Album/cover.jpg").write_bytes(POCHETTE)

    def lancer(self, *argv):
        return self.lancer_main(conversion, "--output-dir", str(self.sortie), *argv,
                                run_tool=FfmpegSimule(), shutil=types.SimpleNamespace(which=outils("ffmpeg"), copy2=shutil.copy2))

    def test_passage_complet_puis_pochette_a_jour(self):
        code, texte = self.lancer("--apply")
        self.assertEqual(code, 0)
        self.assertIn("Pochettes : 1 copiée", texte)
        self.assertEqual(self.fichiers(self.sortie), ["Artiste/Album/01 - A.mp3", "Artiste/Album/cover.jpg"])
        code, texte = self.lancer("--apply")
        self.assertEqual(code, 0)
        self.assertIn("Pochettes : 1 à jour", texte)
        self.assertNotIn("cover.jpg copiée", texte)

    def test_simulation_annonce_la_pochette_sans_l_ecrire(self):
        code, texte = self.lancer()
        self.assertEqual(code, 0)
        self.assertIn("cover.jpg sera copiée", texte)
        self.assertEqual(self.fichiers(self.sortie), [])

    def test_pochette_en_echec_sort_en_code_1(self):
        with mock.patch.object(conversion, "copy_cover", return_value=("erreur", "cover.jpg non recopiée : Disque plein")):
            code, texte = self.lancer("--apply")
        self.assertEqual(code, 1)
        self.assertIn("[ERREUR] cover.jpg non recopiée", texte)


class TestMp3Recopies(Flac2Mp3TestCase):
    """Un .mp3 déjà rangé sous --dir : recopié octet pour octet, jamais réencodé."""

    def setUp(self):
        super().setUp()
        self.source = self.racine / "Artiste/Album/01 - A.mp3"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(SON_10_S)

    def copier(self, **overrides):
        return conversion.copy_mp3(self.source, self.racine, options(self.sortie, **overrides))

    def test_copie_a_l_identique_puis_a_jour(self):
        self.assertEqual(self.copier(), ("copié", "01 - A.mp3 copié"))
        self.assertEqual((self.sortie / "Artiste/Album/01 - A.mp3").read_bytes(), SON_10_S)
        self.assertEqual(self.fichiers(self.sortie), ["Artiste/Album/01 - A.mp3"])     # aucun .part qui traîne
        self.assertEqual(self.copier()[0], "à jour")

    def test_mp3_change_est_remplace(self):
        self.copier()
        self.source.write_bytes(SON_10_S + TRAME_AUDIO)
        self.assertEqual(self.copier()[0], "remplacé")
        self.assertEqual((self.sortie / "Artiste/Album/01 - A.mp3").read_bytes(), SON_10_S + TRAME_AUDIO)

    def test_simulation_n_ecrit_rien(self):
        status, detail = self.copier(apply=False)
        self.assertEqual((status, detail), ("simule", "01 - A.mp3 sera copié"))
        self.assertEqual(self.fichiers(self.sortie), [])

    def test_echec_de_copie_est_une_erreur_sans_reste(self):
        with mock.patch.object(conversion.shutil, "copy2", side_effect=OSError(28, "Disque plein")):
            status, detail = self.copier()
        self.assertEqual((status, detail), ("erreur", "01 - A.mp3 non recopié : Disque plein"))
        self.assertEqual(self.fichiers(self.sortie), [])


class TestMainMp3(Flac2Mp3TestCase):
    """Une bibliothèque où des albums n'existent qu'en MP3 : la copie les contient aussi, avec leur pochette."""

    def setUp(self):
        super().setUp()
        self.poser_flac("Artiste/Album FLAC/01 - A.flac")
        mp3_seul = self.racine / "Artiste/Album MP3"
        mp3_seul.mkdir(parents=True)
        (mp3_seul / "01 - B.mp3").write_bytes(SON_10_S)
        (mp3_seul / "cover.jpg").write_bytes(POCHETTE)

    def lancer(self, *argv, ffmpeg=None, tools=("ffmpeg",)):
        return self.lancer_main(conversion, "--output-dir", str(self.sortie), *argv,
                                run_tool=ffmpeg or FfmpegSimule(), shutil=types.SimpleNamespace(which=outils(*tools), copy2=shutil.copy2))

    def test_passage_complet_puis_second_passage_qui_ne_change_rien(self):
        code, texte = self.lancer("--apply")
        self.assertEqual(code, 0)
        self.assertIn("1 converti", texte)
        self.assertIn(".mp3 recopiés tels quels : 1 copié", texte)
        self.assertIn("Pochettes : 1 copiée", texte)
        self.assertEqual(self.fichiers(self.sortie), ["Artiste/Album FLAC/01 - A.mp3", "Artiste/Album MP3/01 - B.mp3", "Artiste/Album MP3/cover.jpg"])
        self.assertEqual((self.sortie / "Artiste/Album MP3/01 - B.mp3").read_bytes(), SON_10_S)

        ffmpeg = FfmpegSimule()
        code, texte = self.lancer("--apply", ffmpeg=ffmpeg)
        self.assertEqual(code, 0)
        self.assertIn(".mp3 recopiés tels quels : 1 à jour", texte)
        self.assertNotIn("01 - B.mp3 copié", texte)
        self.assertEqual(ffmpeg.commands, [])
        self.assertEqual(self.fichiers(self.racine), ["Artiste/Album FLAC/01 - A.flac", "Artiste/Album MP3/01 - B.mp3", "Artiste/Album MP3/cover.jpg"])

    def test_simulation_annonce_la_copie_sans_l_ecrire(self):
        code, texte = self.lancer()
        self.assertEqual(code, 0)
        self.assertIn("1 fichier(s) .flac et 1 .mp3 à recopier", texte)
        self.assertIn("01 - B.mp3 sera copié", texte)
        self.assertEqual(self.fichiers(self.sortie), [])

    def test_le_flac_l_emporte_sur_un_mp3_du_meme_nom(self):
        (self.racine / "Artiste/Album FLAC/01 - A.mp3").write_bytes(b"ANCIEN MP3")
        code, texte = self.lancer("--apply")
        self.assertEqual(code, 0)
        self.assertIn("01 - A.mp3 : ignoré, 01 - A.flac est converti à sa place", texte)
        self.assertEqual((self.sortie / "Artiste/Album FLAC/01 - A.mp3").read_bytes()[:len(b"ID3")], b"ID3")

    def test_que_des_mp3_sans_ffmpeg(self):
        (self.racine / "Artiste/Album FLAC/01 - A.flac").unlink()
        code, texte = self.lancer("--apply", tools=())
        self.assertEqual(code, 0)
        self.assertIn("0 .flac", texte)
        self.assertEqual(self.fichiers(self.sortie), ["Artiste/Album MP3/01 - B.mp3", "Artiste/Album MP3/cover.jpg"])

    def test_echec_de_recopie_sort_en_code_1(self):
        with mock.patch.object(conversion, "copy_mp3", return_value=("erreur", "01 - B.mp3 non recopié : Disque plein")):
            code, texte = self.lancer("--apply")
        self.assertEqual(code, 1)
        self.assertIn("[ERREUR] 01 - B.mp3 non recopié", texte)


class TestArguments(unittest.TestCase):
    def parse(self, *argv):
        with mock.patch.object(sys, "argv", ["Flac_To_Mp3.py", "--dir", "x", *argv]):
            return conversion.parse_args()

    def test_valeurs_par_defaut(self):
        args = self.parse("--output-dir", "D:\\MP3")
        self.assertEqual((args.apply, args.quality, args.overwrite, args.no_recursive, args.log, args.output_dir),
                         (False, "320", False, False, None, Path("D:\\MP3")))

    def test_quality_v0_et_valeur_inconnue_refusee(self):
        self.assertEqual(self.parse("--output-dir", "x", "--quality", "v0").quality, "v0")
        for valeur in ("V2", "256", ""):
            with self.subTest(valeur), mock.patch("sys.stderr"), self.assertRaises(SystemExit):
                self.parse("--output-dir", "x", "--quality", valeur)

    def test_output_dir_obligatoire(self):
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            self.parse()


@unittest.skipUnless(AVEC_LAME, "ffmpeg avec libmp3lame absent : le vrai encodage n'est pas testé")
class TestAvecLeVraiFfmpeg(Flac2Mp3TestCase):
    """Un vrai .flac, un vrai .mp3 : ce que les simulations ne peuvent pas dire."""

    def encoder_flac(self, relatif, frequence):
        chemin = self.racine / relatif
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=440:duration=2:sample_rate={frequence}",
                        "-ac", "2", "-metadata", "TITLE=Été", "-metadata", "ARTIST=AC/DC", str(chemin)], check=True)
        meta = flac.read(chemin)
        flac.write(chemin, meta, meta.comments, [flac.front_cover(POCHETTE)])

    def test_320_constant_tags_et_frequence(self):
        self.encoder_flac("cd.flac", 44100)
        self.encoder_flac("hires.flac", 96000)
        code, _ = self.lancer_main(conversion, "--output-dir", str(self.sortie), "--apply")
        self.assertEqual(code, 0)
        for nom, frequence in (("cd.mp3", "44100"), ("hires.mp3", "48000")):
            with self.subTest(nom):
                sonde = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,bit_rate,sample_rate",
                                        "-of", "default=nw=1", str(self.sortie / nom)], capture_output=True, encoding="utf-8").stdout
                self.assertIn("codec_name=mp3", sonde)
                self.assertIn("bit_rate=320000", sonde)
                self.assertIn(f"sample_rate={frequence}", sonde)
                lu = mp3.read(self.sortie / nom)
                self.assertEqual((lu.first("TITLE"), lu.first("ARTIST")), ("Été", "AC/DC"))
                self.assertEqual([p.data for p in lu.pictures], [POCHETTE])
                self.assertAlmostEqual(lu.duration, 2.0, delta=0.1)

    def test_v0_debit_variable_et_duree_relue(self):
        # Un VBR n'a pas de débit fixe : sa durée se lit dans l'en-tête Xing, et doit tout de même passer le contrôle.
        self.encoder_flac("cd.flac", 44100)
        code, _ = self.lancer_main(conversion, "--output-dir", str(self.sortie), "--apply", "--quality", "v0")
        self.assertEqual(code, 0)
        donnees = (self.sortie / "cd.mp3").read_bytes()
        self.assertIn(b"Xing", donnees[:4096])            # "Xing" = débit variable ; un CBR porte "Info"
        lu = mp3.read(self.sortie / "cd.mp3")
        self.assertEqual(lu.first("TITLE"), "Été")
        self.assertAlmostEqual(lu.duration, 2.0, delta=0.1)


if __name__ == "__main__":
    unittest.main()
