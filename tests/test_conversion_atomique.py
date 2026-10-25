"""Un convertisseur ne laisse jamais de `.mkv` à moitié écrit, ni ne perd d'original (aucun outil externe requis).

mkvmerge, ffprobe et la lecture des pistes sont simulés : ce qu'on vérifie, c'est ce que le dossier contient APRÈS le passage - le `.mkv` n'existe que s'il a été jugé sain, rien ne traîne, l'original n'est effacé que sur un contrôle réussi.
"""

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.video import mkv
from scripts.Converters.Video import Avi_To_Mkv, Mp4_To_Mkv
from scripts.Maintenance import Verify_Files

INFO = {"tracks": [{"id": 0, "type": "video", "properties": {}}, {"id": 1, "type": "audio", "properties": {}}]}


def options(**overrides):
    values = dict(lang="fre", force_lang=False, sub_lang="fre", sub_charset="windows-1252", subs="auto",
                  default_audio=False, default_sub=False, title=False, apply=True, output_dir=None,
                  overwrite=False, tolerance=2.0, delete_source=False)
    values.update(overrides)
    return types.SimpleNamespace(**values)


class MkvmergeSimule:
    """Remplace run_tool : écrit (ou pas) le fichier de sortie, comme le ferait mkvmerge, puis rend son code de retour.

    La sortie se lit après `--output` (convertisseurs) ou `-o` (Verify_Files).
    """

    def __init__(self, code=0, writes=b"MKV", error=None, stderr=""):
        self.code, self.writes, self.error, self.stderr = code, writes, error, stderr
        self.commands = []

    def output(self, command):
        flag = "--output" if "--output" in command else "-o"
        return Path(command[command.index(flag) + 1])

    def __call__(self, command, **kwargs):
        self.commands.append(command)
        if self.writes is not None:
            self.output(command).write_bytes(self.writes)
        if self.error:
            raise self.error
        return types.SimpleNamespace(returncode=self.code, stdout="", stderr=self.stderr)


class ConversionAtomique:
    """Les mêmes garanties pour les deux convertisseurs : une sous-classe fixe module et extension."""

    module = None
    extension = None

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        self.video = self.folder / f"Le Film.{self.extension}"
        self.video.write_bytes(b"SOURCE")
        self.final = self.folder / "Le Film.mkv"
        self.partial = mkv.partial_path(self.final)

    def convert(self, mux, source=100.0, produced=100.0, check_duration=True, **overrides):
        """(statut, détail), pour une source de `source` minutes et un résultat de `produced` minutes (None : durée illisible)."""
        # Le résultat se reconnaît à son suffixe provisoire, où qu'il soit écrit (--output-dir compris).
        probes = lambda path: types.SimpleNamespace(duration_min=produced if Path(path).name.endswith(mkv.PARTIAL_SUFFIX) else source)
        with mock.patch.object(self.module, "identify", return_value=(INFO, "")), \
                mock.patch.object(self.module, "run_tool", mux), \
                mock.patch.object(self.module, "probe", probes):
            return self.module.convert(self.video, options(**overrides), check_duration)

    def folder_content(self):
        return sorted(p.name for p in self.folder.iterdir())

    # ------------------------------------------------------------ le chemin heureux
    def test_mkvmerge_ecrit_sous_un_nom_provisoire(self):
        mux = MkvmergeSimule()
        self.convert(mux)
        self.assertEqual(mux.output(mux.commands[0]), self.partial)

    def test_resultat_sain_prend_son_vrai_nom(self):
        status, _ = self.convert(MkvmergeSimule())
        self.assertEqual(status, "converti")
        self.assertEqual(self.final.read_bytes(), b"MKV")
        self.assertEqual(self.folder_content(), sorted([self.video.name, "Le Film.mkv"]))

    def test_la_source_reste_sans_delete_source(self):
        self.convert(MkvmergeSimule())
        self.assertTrue(self.video.exists())

    def test_delete_source_efface_apres_un_controle_reussi(self):
        status, detail = self.convert(MkvmergeSimule(), delete_source=True)
        self.assertEqual(status, "converti")
        self.assertIn("source effacée", detail)
        self.assertFalse(self.video.exists())
        self.assertTrue(self.final.exists())

    def test_un_avertissement_de_mkvmerge_n_empeche_rien(self):
        status, detail = self.convert(MkvmergeSimule(code=1))
        self.assertEqual(status, "converti")
        self.assertIn("avertissement", detail)
        self.assertTrue(self.final.exists())

    def test_la_simulation_ne_touche_a_rien_et_montre_le_vrai_nom(self):
        mux = MkvmergeSimule()
        status, detail = self.convert(mux, apply=False)
        self.assertEqual(status, "simule")
        self.assertEqual(mux.commands, [])
        self.assertIn("Le Film.mkv", detail)
        self.assertNotIn(".part", detail)
        self.assertEqual(self.folder_content(), [self.video.name])

    # ------------------------------------------------------------ ce qui ne doit rien laisser
    def test_echec_de_mkvmerge_ne_laisse_aucun_mkv(self):
        # mkvmerge a eu le temps d'écrire un début de fichier avant d'échouer.
        status, _ = self.convert(MkvmergeSimule(code=2, writes=b"TRONQUE", stderr="Erreur : disque plein"))
        self.assertEqual(status, "erreur")
        self.assertEqual(self.folder_content(), [self.video.name])

    def test_un_ecart_de_duree_ne_laisse_aucun_mkv(self):
        status, detail = self.convert(MkvmergeSimule(), produced=60.0, delete_source=True)
        self.assertEqual(status, "écart")
        self.assertIn("n'a pas été écrit", detail)
        self.assertEqual(self.folder_content(), [self.video.name])       # l'original est intact, même avec --delete-source

    def test_l_ecart_tolere_passe(self):
        status, _ = self.convert(MkvmergeSimule(), produced=100.0 + 1.0 / 60)      # une seconde de plus
        self.assertEqual(status, "converti")

    def test_ctrl_c_ne_laisse_rien(self):
        with self.assertRaises(KeyboardInterrupt):
            self.convert(MkvmergeSimule(error=KeyboardInterrupt(), writes=b"DEBUT"))
        self.assertEqual(self.folder_content(), [self.video.name])

    def test_le_passage_suivant_refait_la_conversion_apres_un_echec(self):
        # Avant : le .mkv tronqué restait, et le passage suivant répondait « existe déjà ».
        self.convert(MkvmergeSimule(code=2, writes=b"TRONQUE"))
        status, _ = self.convert(MkvmergeSimule())
        self.assertEqual(status, "converti")
        self.assertEqual(self.final.read_bytes(), b"MKV")

    def test_un_reste_de_passage_interrompu_n_est_pas_pris_pour_la_sortie(self):
        self.partial.write_bytes(b"VIEUX RESTE")
        status, _ = self.convert(MkvmergeSimule(code=2, writes=None))     # mkvmerge n'écrit rien
        self.assertEqual(status, "erreur")
        self.assertEqual(self.folder_content(), [self.video.name])

    def test_un_reste_est_remplace_par_le_nouveau_resultat(self):
        self.partial.write_bytes(b"VIEUX RESTE")
        status, _ = self.convert(MkvmergeSimule())
        self.assertEqual(status, "converti")
        self.assertEqual(self.final.read_bytes(), b"MKV")

    def test_overwrite_garde_l_ancien_mkv_si_la_conversion_echoue(self):
        # Avant : mkvmerge écrivait directement sur le .mkv existant, qu'un échec laissait tronqué.
        self.final.write_bytes(b"ANCIEN")
        self.convert(MkvmergeSimule(code=2, writes=b"TRONQUE"), overwrite=True)
        self.assertEqual(self.final.read_bytes(), b"ANCIEN")
        self.assertEqual(self.folder_content(), sorted([self.video.name, "Le Film.mkv"]))

    def test_overwrite_remplace_l_ancien_mkv_si_la_conversion_reussit(self):
        self.final.write_bytes(b"ANCIEN")
        status, _ = self.convert(MkvmergeSimule(), overwrite=True)
        self.assertEqual(status, "converti")
        self.assertEqual(self.final.read_bytes(), b"MKV")

    def test_sans_overwrite_un_mkv_existant_est_laisse(self):
        self.final.write_bytes(b"ANCIEN")
        mux = MkvmergeSimule()
        status, _ = self.convert(mux)
        self.assertEqual(status, "ignoré")
        self.assertEqual(mux.commands, [])
        self.assertEqual(self.final.read_bytes(), b"ANCIEN")

    def test_un_remplacement_impossible_est_une_erreur_sans_reste(self):
        with mock.patch.object(self.module.os, "replace", side_effect=PermissionError(13, "Accès refusé")):
            status, detail = self.convert(MkvmergeSimule(), delete_source=True)
        self.assertEqual(status, "erreur")
        self.assertIn("Accès refusé", detail)
        self.assertEqual(self.folder_content(), [self.video.name])       # source intacte, malgré --delete-source

    def test_output_dir_recoit_le_fichier_fini_et_rien_d_autre(self):
        out = self.folder / "Sortie"
        status, _ = self.convert(MkvmergeSimule(), output_dir=out)
        self.assertEqual(status, "converti")
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["Le Film.mkv"])

    # ------------------------------------------------------------ avant de lancer mkvmerge
    def convert_avec(self, identification, mux=None, **overrides):
        mux = mux or MkvmergeSimule()
        sonde = types.SimpleNamespace(duration_min=100.0)
        with mock.patch.object(self.module, "identify", return_value=identification), mock.patch.object(self.module, "run_tool", mux), mock.patch.object(self.module, "probe", return_value=sonde):
            return self.module.convert(self.video, options(**overrides), True), mux

    def test_fichier_illisible_par_mkvmerge(self):
        (status, detail), mux = self.convert_avec((None, "lecture impossible par mkvmerge (code 2)"))
        self.assertEqual((status, detail), ("erreur", "lecture impossible par mkvmerge (code 2)"))
        self.assertEqual(mux.commands, [])
        self.assertEqual(self.folder_content(), [self.video.name])

    def test_fichier_sans_piste_video(self):
        (status, detail), mux = self.convert_avec(({"tracks": [{"id": 1, "type": "audio", "properties": {}}]}, ""))
        self.assertEqual((status, detail), ("erreur", "aucune piste vidéo"))
        self.assertEqual(mux.commands, [])

    def test_subs_require_sans_sous_titre_passe_son_tour(self):
        (status, detail), mux = self.convert_avec((INFO, ""), subs="require")
        self.assertEqual(status, "ignoré")
        self.assertIn("--subs require", detail)
        self.assertEqual(mux.commands, [])

    def test_subs_none_ignore_ceux_qui_sont_a_cote(self):
        (self.folder / "Le Film.fr.srt").write_text("1", encoding="utf-8")
        (status, _), mux = self.convert_avec((INFO, ""), subs="none")
        self.assertEqual(status, "converti")
        self.assertNotIn("Le Film.fr.srt", " ".join(mux.commands[0]))

    def test_sous_titre_a_cote_embarque_avec_sa_langue_et_son_encodage(self):
        (self.folder / "Le Film.en.srt").write_bytes("Déjà vu".encode("cp1252"))
        (status, detail), mux = self.convert_avec((INFO, ""))
        self.assertEqual(status, "converti")
        self.assertIn("Le Film.en.srt en eng (windows-1252)", detail)

    def test_source_non_effacable_n_annule_pas_la_conversion(self):
        vrai = Path.unlink

        def refuse(chemin, *args, **kwargs):
            if chemin.suffix == f".{self.extension}":
                raise PermissionError(13, "Accès refusé")
            return vrai(chemin, *args, **kwargs)

        with mock.patch.object(Path, "unlink", refuse):
            status, detail = self.convert(MkvmergeSimule(), delete_source=True)
        self.assertEqual(status, "converti")
        self.assertIn("source non effacée : Accès refusé", detail)
        self.assertTrue(self.final.is_file())
        self.assertTrue(self.video.is_file())

    def test_encodage_d_un_sous_titre_illisible_retombe_sur_le_repli(self):
        self.assertEqual(self.module.detect_charset(self.folder / "absent.srt", "windows-1252"), "windows-1252")

    # ------------------------------------------------------------ durée non contrôlable
    def test_sans_ffprobe_converti_mais_non_verifie_et_source_gardee(self):
        status, detail = self.convert(MkvmergeSimule(), check_duration=False, delete_source=True)
        self.assertEqual(status, "non vérifié")
        self.assertIn("ffprobe absent", detail)
        self.assertTrue(self.final.exists())
        self.assertTrue(self.video.exists())

    def test_duree_illisible_converti_mais_non_verifie_et_source_gardee(self):
        status, detail = self.convert(MkvmergeSimule(), produced=None, delete_source=True)
        self.assertEqual(status, "non vérifié")
        self.assertIn("indéterminable", detail)
        self.assertTrue(self.final.exists())
        self.assertTrue(self.video.exists())


class TestAviAtomique(ConversionAtomique, unittest.TestCase):
    module, extension = Avi_To_Mkv, "avi"


class TestMp4Atomique(ConversionAtomique, unittest.TestCase):
    module, extension = Mp4_To_Mkv, "mp4"


class TestReparationAtomique(unittest.TestCase):
    """Verify_Files --repair : l'original n'est remplacé que par un remux sain, et rien ne traîne."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        self.film = self.folder / "Le Film.mkv"
        self.film.write_bytes(b"ABIME")
        self.neuf = mkv.partial_path(self.film)

    def repair(self, mux, remux_check=""):
        with mock.patch.object(Verify_Files, "run_tool", mux), \
                mock.patch.object(Verify_Files, "check", return_value=remux_check):
            return Verify_Files.repair(self.film, complet=False)

    def folder_content(self):
        return sorted(p.name for p in self.folder.iterdir())

    def test_remux_sain_remplace_l_original(self):
        mux = MkvmergeSimule(writes=b"SAIN")
        self.assertEqual(self.repair(mux), (True, ""))
        self.assertEqual(mux.output(mux.commands[0]), self.neuf)
        self.assertEqual(self.film.read_bytes(), b"SAIN")
        self.assertEqual(self.folder_content(), ["Le Film.mkv"])

    def test_echec_de_mkvmerge_laisse_l_original_et_rien_d_autre(self):
        reussi, souci = self.repair(MkvmergeSimule(code=2, writes=b"TRONQUE", stderr="Erreur : disque plein"))
        self.assertFalse(reussi)
        self.assertIn("disque plein", souci)
        self.assertEqual(self.film.read_bytes(), b"ABIME")
        self.assertEqual(self.folder_content(), ["Le Film.mkv"])

    def test_un_avertissement_de_mkvmerge_n_empeche_pas_la_reparation(self):
        self.assertEqual(self.repair(MkvmergeSimule(code=1, writes=b"SAIN")), (True, ""))
        self.assertEqual(self.film.read_bytes(), b"SAIN")

    def test_remux_abime_laisse_l_original_et_rien_d_autre(self):
        reussi, souci = self.repair(MkvmergeSimule(writes=b"ENCORE ABIME"), remux_check="fin de fichier tronquée")
        self.assertFalse(reussi)
        self.assertIn("abîmé lui aussi", souci)
        self.assertEqual(self.film.read_bytes(), b"ABIME")
        self.assertEqual(self.folder_content(), ["Le Film.mkv"])

    def test_ctrl_c_ne_laisse_rien(self):
        with self.assertRaises(KeyboardInterrupt):
            self.repair(MkvmergeSimule(error=KeyboardInterrupt(), writes=b"DEBUT"))
        self.assertEqual(self.film.read_bytes(), b"ABIME")
        self.assertEqual(self.folder_content(), ["Le Film.mkv"])

    def test_un_reste_de_passage_interrompu_n_est_pas_pris_pour_le_remux(self):
        self.neuf.write_bytes(b"VIEUX RESTE")
        reussi, _ = self.repair(MkvmergeSimule(code=2, writes=None))      # mkvmerge n'écrit rien
        self.assertFalse(reussi)
        self.assertEqual(self.film.read_bytes(), b"ABIME")
        self.assertEqual(self.folder_content(), ["Le Film.mkv"])

    def test_remplacement_impossible(self):
        with mock.patch.object(Verify_Files.os, "replace", side_effect=PermissionError(13, "Accès refusé")):
            reussi, souci = self.repair(MkvmergeSimule(writes=b"SAIN"))
        self.assertFalse(reussi)
        self.assertIn("Accès refusé", souci)
        self.assertEqual(self.film.read_bytes(), b"ABIME")
        self.assertEqual(self.folder_content(), ["Le Film.mkv"])

    def test_un_reste_provisoire_n_est_pas_un_film_a_controler(self):
        self.neuf.write_bytes(b"RESTE")
        self.assertEqual([p.name for p in Verify_Files.mkv_files(self.folder)], ["Le Film.mkv"])


if __name__ == "__main__":
    unittest.main()
