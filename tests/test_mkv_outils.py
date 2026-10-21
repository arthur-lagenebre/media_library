"""mkv.py côté outils externes : vérification des outils, lecture (mkvmerge, ffprobe, Python pur), et la commande mkvpropedit qu'on y écrit.

Aucun outil n'est lancé : run_tool est simulé, et on regarde ce qu'on lui demande et comment on traite ce qu'il rend.
"""

import io
import json
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.video import mkv
from libraries.video.tmdb import TmdbError


def resultat(stdout="", stderr="", code=0):
    return types.SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr)


def echec(stderr="", code=2):
    return subprocess.CalledProcessError(code, ["outil"], stderr=stderr)


INFO = {"tracks": [
    {"id": 0, "type": "video"},
    {"id": 1, "type": "audio", "codec": "E-AC-3", "properties": {"language": "fre", "audio_channels": 6, "track_name": "vieux nom"}},
    {"id": 2, "type": "audio", "codec": "AC-3", "properties": {"language": "eng", "audio_channels": 2, "track_name": "AC-3 2.0"}},
    {"id": 3, "type": "subtitles", "codec": "SRT", "properties": {"language": "fre", "track_name": "Français forcé"}},
    {"id": 4, "type": "subtitles", "codec": "SRT", "properties": {"language": "eng"}},
], "attachments": [{"file_name": "cover.jpg"}]}


class TestRaisonDUnEchec(unittest.TestCase):
    def test_premiere_ligne_de_stderr(self):
        self.assertEqual(mkv._reason(echec("Erreur : fichier illisible\nautre ligne")), "Erreur : fichier illisible")

    def test_sans_message_le_code_de_retour(self):
        self.assertEqual(mkv._reason(echec("")), "code 2")
        self.assertEqual(mkv._reason(echec(None)), "code 2")

    def test_autre_exception_son_texte(self):
        self.assertEqual(mkv._reason(FileNotFoundError("mkvmerge")), "mkvmerge")


class TestVerificationDesOutils(unittest.TestCase):
    def verifier(self, presents, **kwargs):
        with mock.patch.object(mkv.shutil, "which", lambda nom: f"/bin/{nom}" if nom in presents else None), redirect_stdout(io.StringIO()) as texte:
            try:
                return mkv.check_tools(**kwargs), texte.getvalue()
            except SystemExit as sortie:
                return sortie.code, texte.getvalue()

    def test_rien_a_ecrire_rien_a_verifier(self):
        self.assertEqual(self.verifier((), needs_mkvtoolnix=False), (False, ""))

    def test_tout_est_la(self):
        self.assertEqual(self.verifier(("mkvpropedit", "mkvmerge", "mkvextract", "ffprobe")), (True, ""))

    def test_ffprobe_absent_n_empeche_rien(self):
        disponible, texte = self.verifier(("mkvpropedit", "mkvmerge", "mkvextract"))
        self.assertFalse(disponible)
        self.assertIn("ffprobe absent", texte)

    def test_mkvtoolnix_manquant_arrete_le_script(self):
        code, texte = self.verifier(("mkvmerge", "ffprobe"))
        self.assertEqual(code, 1)
        self.assertIn("mkvpropedit, mkvextract", texte)
        self.assertIn("winget install MoritzBunkus.MKVToolNix", texte)


class TestLectureParMkvmerge(unittest.TestCase):
    def identifier(self, **retour):
        with mock.patch.object(mkv, "run_tool", **retour):
            return mkv.identify("film.mkv")

    def test_fiche_lue(self):
        info, note = self.identifier(return_value=resultat(json.dumps({"tracks": []})))
        self.assertEqual((info, note), ({"tracks": []}, ""))

    def test_sortie_vide(self):
        info, note = self.identifier(return_value=resultat(""))
        self.assertIsNone(info)
        self.assertIn("sortie vide", note)

    def test_outil_en_echec(self):
        info, note = self.identifier(side_effect=echec("Erreur : format inconnu"))
        self.assertIsNone(info)
        self.assertIn("Erreur : format inconnu", note)

    def test_outil_introuvable(self):
        info, note = self.identifier(side_effect=FileNotFoundError("mkvmerge"))
        self.assertIsNone(info)
        self.assertIn("lecture impossible par mkvmerge", note)

    def test_json_illisible(self):
        info, _ = self.identifier(return_value=resultat("pas du json"))
        self.assertIsNone(info)


class TestSondeFfprobe(unittest.TestCase):
    def sonder(self, sortie=None, **retour):
        retour = retour or {"return_value": resultat(json.dumps(sortie))}
        with mock.patch.object(mkv, "run_tool", **retour):
            return mkv.probe("film.mkv")

    def test_duree_en_minutes_et_debits_par_piste_audio(self):
        sonde = self.sonder({"format": {"duration": "6000.0"}, "streams": [
            {"codec_type": "video"}, {"codec_type": "audio", "bit_rate": "640000"},
            {"codec_type": "audio"}, {"codec_type": "audio", "bit_rate": "192000"}]})
        self.assertEqual(sonde.duration_min, 100.0)
        self.assertEqual(sonde.audio_bitrates, {1: 640, 3: 192})        # numérotées par piste audio, pas par flux

    def test_duree_incomprehensible(self):
        self.assertIsNone(self.sonder({"format": {"duration": "N/A"}, "streams": []}).duration_min)

    def test_duree_absente(self):
        self.assertIsNone(self.sonder({"format": {}, "streams": []}).duration_min)

    def test_debit_non_numerique_ignore(self):
        self.assertEqual(self.sonder({"streams": [{"codec_type": "audio", "bit_rate": "N/A"}]}).audio_bitrates, {})

    def test_outil_en_echec_rend_une_sonde_vide(self):
        sonde = self.sonder(side_effect=echec())
        self.assertEqual((sonde.duration_min, sonde.audio_bitrates), (None, {}))

    def test_sortie_vide_ou_qui_n_est_pas_un_objet(self):
        self.assertIsNone(self.sonder(return_value=resultat("")).duration_min)
        self.assertIsNone(self.sonder(["liste"]).duration_min)

    def test_debits_ajoutes_aux_pistes_audio_pour_leur_nom(self):
        info = json.loads(json.dumps(INFO))
        with mock.patch.object(mkv, "probe", return_value=mkv.Probe(100.0, {1: 640})):
            sonde = mkv.annotate_bitrates(info, "film.mkv")
        self.assertEqual(sonde.duration_min, 100.0)
        audios = [t for t in info["tracks"] if t["type"] == "audio"]
        self.assertEqual(audios[0]["_bitrate_kbps"], 640)
        self.assertNotIn("_bitrate_kbps", audios[1])             # débit inconnu : rien d'inventé

    def test_annotation_sans_fiche(self):
        with mock.patch.object(mkv, "probe", return_value=mkv.Probe()):
            self.assertIsNotNone(mkv.annotate_bitrates(None, "film.mkv"))


class TestLectureEnParallele(unittest.TestCase):
    def test_un_fichier_ou_aucun_se_lit_sans_pool(self):
        with mock.patch.object(mkv, "inspect", side_effect=lambda p, probe, tags: f"lu {p}"):
            self.assertEqual(mkv.inspect_all([]), {})
            self.assertEqual(mkv.inspect_all(["a.mkv"]), {"a.mkv": "lu a.mkv"})

    def test_plusieurs_fichiers_gardent_leur_ordre(self):
        chemins = [f"{n}.mkv" for n in range(20)]
        with mock.patch.object(mkv, "inspect", side_effect=lambda p, probe, tags: f"lu {p}"), mock.patch.object(mkv, "progress"):
            lectures = mkv.inspect_all(chemins, workers=4)
        self.assertEqual(list(lectures), chemins)
        self.assertEqual(lectures["7.mkv"], "lu 7.mkv")

    def test_les_options_de_lecture_sont_transmises(self):
        with mock.patch.object(mkv, "inspect") as lire, mock.patch.object(mkv, "progress"):
            mkv.inspect_all(["a.mkv", "b.mkv"], with_probe=False, with_tags=True)
        lire.assert_any_call("a.mkv", False, True)

    def test_lecture_d_un_fichier_sans_tags_a_relire(self):
        with mock.patch.object(mkv, "identify", return_value=({"tracks": []}, "")), mock.patch.object(mkv, "annotate_bitrates", return_value=mkv.Probe(1.0)), mock.patch.object(mkv, "read_tags") as tags:
            lecture = mkv.inspect("a.mkv", with_probe=True, with_tags=False)
        self.assertEqual(lecture.probe.duration_min, 1.0)
        self.assertIsNone(lecture.tags)               # aucun tag déclaré, aucune relecture demandée : pas de mkvextract
        tags.assert_not_called()

    def test_lecture_qui_echoue_ne_sonde_pas(self):
        with mock.patch.object(mkv, "identify", return_value=(None, "illisible")), mock.patch.object(mkv, "annotate_bitrates") as sonde:
            lecture = mkv.inspect("a.mkv", with_probe=True, with_tags=True)
        sonde.assert_not_called()
        self.assertEqual((lecture.info, lecture.note), (None, "illisible"))

    def test_les_tags_sont_relus_quand_le_fichier_en_declare(self):
        info = {"tracks": [], "global_tags": [{"num_entries": 3}]}
        with mock.patch.object(mkv, "identify", return_value=(info, "")), mock.patch.object(mkv, "read_tags", return_value={(50, "TMDB", "movie/1")}):
            lecture = mkv.inspect("a.mkv", with_probe=False, with_tags=False)
        self.assertEqual(lecture.tags, {(50, "TMDB", "movie/1")})


class TestProgression(unittest.TestCase):
    class Terminal(io.StringIO):
        def isatty(self):
            return True

    def test_muette_hors_terminal(self):
        with redirect_stdout(io.StringIO()) as sortie:
            mkv.progress("lecture", 1, 3)
        self.assertEqual(sortie.getvalue(), "")

    def test_ligne_reecrite_sur_place_puis_retour_a_la_ligne_a_la_fin(self):
        with redirect_stdout(self.Terminal()) as sortie:
            mkv.progress("lecture", 1, 3)
            mkv.progress("lecture", 3, 3)
        self.assertEqual(sortie.getvalue(), "\r  lecture : 1/3\r  lecture : 3/3\n")

    def test_flux_ferme(self):
        def ferme():
            raise ValueError("closed")
        with mock.patch.object(mkv.sys, "stdout", types.SimpleNamespace(isatty=ferme)):
            mkv.progress("lecture", 1, 3)


class TestLectureEnPythonPur(unittest.TestCase):
    def test_tags_et_duree_sans_sous_processus(self):
        with mock.patch.object(mkv.ebml, "read_metadata", return_value=({(50, "TMDB", "movie/1")}, 100.0)):
            lecture = mkv.read_light("film.mkv")
        self.assertEqual(lecture.tags, {(50, "TMDB", "movie/1")})
        self.assertEqual(lecture.info["container"]["properties"]["duration"], int(100.0 * 60e9))
        self.assertEqual(mkv.minutes(lecture), 100.0)

    def test_duree_inconnue(self):
        with mock.patch.object(mkv.ebml, "read_metadata", return_value=(set(), None)):
            lecture = mkv.read_light("film.mkv")
        self.assertEqual(lecture.info, {})
        self.assertIsNone(mkv.minutes(lecture))

    def test_fichier_illisible(self):
        with mock.patch.object(mkv.ebml, "read_metadata", return_value=(None, None)):
            lecture = mkv.read_light("film.mkv")
        self.assertEqual((lecture.info, lecture.note), (None, "lecture impossible"))

    def test_seuls_les_mkv_sont_lus(self):
        with mock.patch.object(mkv, "read_light", side_effect=lambda p: f"lu {Path(p).name}"):
            lectures = mkv.read_light_all([Path("a.mkv"), Path("b.AVI"), Path("c.MKV"), Path("d.mp4")])
        self.assertEqual(sorted(lectures.values()), ["lu a.mkv", "lu c.MKV"])

    def test_aucun_mkv(self):
        self.assertEqual(mkv.read_light_all([Path("b.avi")]), {})
        self.assertEqual(mkv.read_light_all([]), {})


class TestApercuDesPistes(unittest.TestCase):
    def test_piste_par_defaut_marquee(self):
        lignes = mkv.track_preview_lines(INFO, mkv.Options())
        self.assertIn("audio a1 [fre] (défaut)", lignes[0])
        self.assertNotIn("(défaut)", lignes[1])

    def test_sans_noms_ni_drapeaux_rien_a_montrer(self):
        self.assertEqual(mkv.track_preview_lines(INFO, mkv.Options(audio_names=False, sub_names=False, flags=False)), [])


class TestCommandeMkvpropedit(unittest.TestCase):
    """Ce qu'on demande à mkvpropedit, d'un seul appel."""

    def ecrire(self, info=INFO, target=None, opts=None, tmdb=None, retour=None):
        self.commandes = []

        def run(cmd, **kwargs):
            self.commandes.append((cmd, kwargs))
            if isinstance(retour, Exception):
                raise retour
            return retour or resultat("ok")

        target = target or mkv.Target(title="Dune", date="2021-09-15", tags_xml="<Tags/>", poster="/p.jpg")
        self.sortie = io.StringIO()
        with mock.patch.object(mkv, "run_tool", run), redirect_stdout(self.sortie):
            code = mkv.write("film.mkv", info, target, opts or mkv.Options(), tmdb or FauxTmdb())
        self.cmd = self.commandes[0][0] if self.commandes else []
        return code

    def apres(self, option):
        """L'argument qui suit `option` dans la commande."""
        i = self.cmd.index(option)
        return self.cmd[i + 1]

    def test_un_seul_appel_et_son_resultat(self):
        self.assertEqual(self.ecrire(), (0, "ok"))
        self.assertEqual(len(self.commandes), 1)

    def test_titre_et_date_du_segment(self):
        self.ecrire()
        self.assertIn("title=Dune", self.cmd)
        self.assertIn("date=2021-09-15T00:00:00Z", self.cmd)

    def test_sans_date_ou_sans_option_date(self):
        self.ecrire(target=mkv.Target(title="X", tags_xml="<Tags/>"))
        self.assertFalse([a for a in self.cmd if a.startswith("date=")])
        self.ecrire(opts=mkv.Options(date=False))
        self.assertFalse([a for a in self.cmd if a.startswith("date=")])

    def test_tags_et_statistiques(self):
        self.ecrire()
        self.assertEqual(self.apres("--tags"), "all:tags.xml")
        self.assertIn("--add-track-statistics-tags", self.cmd)
        self.ecrire(opts=mkv.Options(stats=False))
        self.assertNotIn("--add-track-statistics-tags", self.cmd)

    def test_les_tags_sont_ecrits_dans_le_dossier_de_travail_de_l_outil(self):
        # Référencés en relatif depuis un dossier temporaire : un « C: » dans le chemin troublerait mkvpropedit.
        contenus = []

        def run(cmd, cwd=None, **kwargs):
            contenus.append((Path(cwd) / "tags.xml").read_text(encoding="utf-8"))
            return resultat()

        with mock.patch.object(mkv, "run_tool", run):
            mkv.write("film.mkv", INFO, mkv.Target(title="X", tags_xml="<Tags>é</Tags>"), mkv.Options(cover=False), None)
        self.assertEqual(contenus, ["<Tags>é</Tags>"])

    def test_pistes_audio_nommees_et_une_seule_par_defaut(self):
        self.ecrire()
        c = " ".join(self.cmd)
        self.assertIn("--edit track:a1 --set name=E-AC-3 5.1 --set flag-default=1", c)
        self.assertIn("--edit track:a2 --set name=AC-3 2.0 --set flag-default=0", c)

    def test_sous_titres_nommes_sans_defaut_et_drapeau_pose_d_apres_le_nom(self):
        self.ecrire()
        c = " ".join(self.cmd)
        self.assertIn("--edit track:s1 --set name=Forced --set flag-default=0 --set flag-forced=1", c)
        self.assertIn("--edit track:s2 --set name=Full --set flag-default=0", c)

    def test_sans_les_options_de_noms_ni_de_drapeaux_les_pistes_sont_laissees(self):
        self.ecrire(opts=mkv.Options(audio_names=False, sub_names=False, flags=False, cover=False))
        self.assertFalse([a for a in self.cmd if a.startswith("track:")])

    def test_nom_vide_efface_celui_qui_existe(self):
        info = {"tracks": [{"id": 1, "type": "audio", "codec": "", "properties": {"track_name": "ancien"}}]}
        self.ecrire(info=info, opts=mkv.Options(flags=False, cover=False))
        self.assertIn("--delete", self.cmd)
        self.assertEqual(self.apres("--delete"), "name")

    def test_nom_vide_sans_nom_existant_ne_touche_a_rien(self):
        info = {"tracks": [{"id": 1, "type": "audio", "codec": "", "properties": {}}]}
        self.ecrire(info=info, opts=mkv.Options(flags=False, cover=False))
        self.assertNotIn("--delete", self.cmd)
        self.assertFalse([a for a in self.cmd if a.startswith("track:")])

    def test_jaquette_remplacee_quand_une_existe_deja(self):
        tmdb = FauxTmdb()
        self.ecrire(tmdb=tmdb)
        self.assertEqual(tmdb.images, [("/p.jpg", "w780")])
        self.assertIn("name:cover.jpg", self.cmd)
        self.assertEqual(self.apres("--add-attachment"), "cover.jpg")

    def test_jaquette_ajoutee_quand_il_n_y_en_a_pas(self):
        self.ecrire(info=dict(INFO, attachments=[]))
        self.assertNotIn("--delete-attachment", self.cmd)
        self.assertIn("--add-attachment", self.cmd)

    def test_jaquette_non_telechargee_sans_l_option(self):
        tmdb = FauxTmdb()
        self.ecrire(opts=mkv.Options(cover=False), tmdb=tmdb)
        self.assertEqual(tmdb.images, [])
        self.assertNotIn("--add-attachment", self.cmd)

    def test_sans_affiche_pas_de_jaquette(self):
        self.ecrire(target=mkv.Target(title="X", tags_xml="<Tags/>"))
        self.assertNotIn("--add-attachment", self.cmd)

    def test_jaquette_introuvable_n_empeche_pas_le_reste(self):
        code = self.ecrire(tmdb=FauxTmdb(erreur=TmdbError("HTTP 404")))
        self.assertEqual(code, (0, "ok"))
        self.assertIn("jaquette ignorée (HTTP 404)", self.sortie.getvalue())
        self.assertNotIn("--add-attachment", self.cmd)
        self.assertIn("title=Dune", self.cmd)

    def test_code_de_retour_et_messages_de_l_outil(self):
        self.assertEqual(self.ecrire(retour=resultat("Warning", "Erreur grave", code=2)), (2, "WarningErreur grave"))

    def test_outil_introuvable_est_un_echec_comme_un_autre(self):
        code, message = self.ecrire(retour=FileNotFoundError("mkvpropedit"))
        self.assertEqual(code, 1)
        self.assertIn("mkvpropedit inutilisable", message)

    def test_dossier_de_travail_temporaire_supprime(self):
        self.ecrire()
        self.assertFalse(Path(self.commandes[0][1]["cwd"]).exists())


class FauxTmdb:
    def __init__(self, erreur=None):
        self.erreur, self.images = erreur, []

    def save_image(self, poster, taille, destination):
        if self.erreur:
            raise self.erreur
        self.images.append((poster, taille))
        Path(destination).write_bytes(b"JPEG")


if __name__ == "__main__":
    unittest.main()
