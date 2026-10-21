"""Avi_To_Mkv.py, Mp4_To_Mkv.py et Verify_Files.py de bout en bout : outils manquants, bilan, journal, code de sortie.

mkvmerge, ffprobe et ebml sont simulés (voir test_conversion_atomique pour ce que devient un fichier) : ici on vérifie ce qu'un passage entier dit, écrit dans son journal, et rend à un script qui l'enchaîne.
"""

import io
import sys
import tempfile
import types
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.Converters import Avi_To_Mkv, Mp4_To_Mkv
from scripts.Maintenance import Verify_Files
from tests.test_conversion_atomique import INFO, MkvmergeSimule


class Selectif(MkvmergeSimule):
    """Un mkvmerge qui échoue pour certains fichiers seulement (ceux dont le nom de sortie contient l'un de `echoue`)."""

    def __init__(self, echoue=()):
        super().__init__()
        self.echoue = echoue

    def __call__(self, command, **kwargs):
        self.code = 2 if any(nom in self.output(command).name for nom in self.echoue) else 0
        return super().__call__(command, **kwargs)


def outils(*presents):
    """Un shutil.which qui ne connaît que ces outils."""
    return lambda nom: f"/usr/bin/{nom}" if nom in presents else None


class ProgrammeTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.racine = Path(self._tmp.name)

    def lancer_main(self, module, *argv, **patches):
        """(code, affichage). Un sys.exit("message") rend le message comme code, comme le fait Python."""
        ligne = [str(Path(module.__file__)), "--dir", str(self.racine), *argv]
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, "argv", ligne))
            for nom, valeur in patches.items():
                stack.enter_context(mock.patch.object(module, nom, valeur))
            texte = stack.enter_context(redirect_stdout(io.StringIO()))
            try:
                code = module.main()
            except SystemExit as sortie:
                code = sortie.code
        self.affichage = texte.getvalue()
        return code, self.affichage

    def noms(self, dossier=None):
        return sorted(p.name for p in (dossier or self.racine).iterdir())


# ----------------------------------------------------------------------------
# Les deux convertisseurs
# ----------------------------------------------------------------------------
class MainConvertisseur:
    module = None
    extension = None
    journal = None

    def setUp(self):
        super().setUp()
        (self.racine / f"Film A.{self.extension}").write_bytes(b"A")
        (self.racine / "Sous").mkdir()
        (self.racine / "Sous" / f"Film B.{self.extension}").write_bytes(b"B")

    def lancer(self, *argv, mux=None, tools=("mkvmerge", "ffprobe"), duree=100.0):
        return self.lancer_main(self.module, *argv,
                                shutil=types.SimpleNamespace(which=outils(*tools)),
                                run_tool=mux or MkvmergeSimule(),
                                identify=lambda chemin: (INFO, ""),
                                probe=lambda chemin: types.SimpleNamespace(duration_min=duree))

    def lire_journal(self, nom=None):
        return (self.racine / (nom or self.journal)).read_text(encoding="utf-8")

    # ------------------------------------------------------------ ce qui manque
    def test_mkvmerge_absent(self):
        code, _ = self.lancer(tools=("ffprobe",))
        self.assertIn("mkvmerge est introuvable", code)

    def test_delete_source_exige_ffprobe(self):
        code, _ = self.lancer("--apply", "--delete-source", tools=("mkvmerge",))
        self.assertIn("--delete-source", code)
        self.assertIn("ffprobe", code)
        self.assertEqual(self.noms(), sorted(["Film A." + self.extension, "Sous"]))

    def test_sans_ffprobe_le_passage_continue_en_le_disant(self):
        code, texte = self.lancer(tools=("mkvmerge",))
        self.assertEqual(code, 0)
        self.assertIn("ffprobe absent", texte)

    def test_aucun_fichier(self):
        vide = self.racine / "vide"
        vide.mkdir()
        self.racine = vide
        code, _ = self.lancer()
        self.assertIn(f"Aucun .{self.extension} sous", code)

    def test_dossier_introuvable(self):
        self.racine = self.racine / "n_existe_pas"
        code, _ = self.lancer()
        self.assertIn("introuvable", code)

    # ------------------------------------------------------------ un passage
    def test_simulation_n_ecrit_que_le_journal(self):
        code, texte = self.lancer()
        self.assertEqual(code, 0)
        self.assertIn("SIMULATION", texte)
        self.assertIn("Simulation : rien n'a été écrit", texte)
        self.assertIn("2 simule", texte)
        self.assertEqual(self.noms(), sorted(["Film A." + self.extension, self.journal, "Sous"]))
        self.assertEqual(self.noms(self.racine / "Sous"), ["Film B." + self.extension])
        self.assertIn("Film A.mkv", self.lire_journal())

    def test_application_convertit_tout_et_garde_les_sources(self):
        code, texte = self.lancer("--apply")
        self.assertEqual(code, 0)
        self.assertIn("2 converti", texte)
        self.assertIn(f"Les .{self.extension} sont toujours à côté de leurs .mkv", texte)
        self.assertTrue((self.racine / "Film A.mkv").is_file())
        self.assertTrue((self.racine / "Sous" / "Film B.mkv").is_file())
        self.assertTrue((self.racine / f"Film A.{self.extension}").is_file())

    def test_delete_source_efface_les_sources_converties(self):
        code, texte = self.lancer("--apply", "--delete-source")
        self.assertEqual(code, 0)
        self.assertNotIn("sont toujours à côté", texte)
        self.assertEqual(self.noms(), sorted(["Film A.mkv", self.journal, "Sous"]))

    def test_un_echec_donne_le_code_1_sans_arreter_les_autres(self):
        code, texte = self.lancer("--apply", mux=Selectif(echoue=("Film B",)))
        self.assertEqual(code, 1)
        self.assertIn("[ERREUR]", texte)
        self.assertIn("1 converti, 1 erreur", texte)
        self.assertTrue((self.racine / "Film A.mkv").is_file())
        self.assertFalse((self.racine / "Sous" / "Film B.mkv").exists())
        self.assertTrue((self.racine / "Sous" / f"Film B.{self.extension}").is_file())

    def test_un_ecart_de_duree_donne_le_code_1(self):
        durees = iter([100.0, 10.0, 100.0, 100.0])      # source A, résultat A (trop court), source B, résultat B
        code, texte = self.lancer_main(self.module, "--apply",
                                       shutil=types.SimpleNamespace(which=outils("mkvmerge", "ffprobe")),
                                       run_tool=MkvmergeSimule(),
                                       identify=lambda chemin: (INFO, ""),
                                       probe=lambda chemin: types.SimpleNamespace(duration_min=next(durees)))
        self.assertEqual(code, 1)
        self.assertIn("[ÉCART]", texte)
        self.assertIn("NON CONVERTIS (originaux intacts)", self.lire_journal())

    def test_le_journal_nomme_les_fichiers_non_convertis(self):
        self.lancer("--apply", mux=Selectif(echoue=("Film B",)))
        _, _, non_convertis = self.lire_journal().partition("NON CONVERTIS (originaux intacts) :")
        self.assertIn(f"Film B.{self.extension}", non_convertis)
        self.assertNotIn("Film A", non_convertis)

    def test_sans_recursion_l_etage_seul(self):
        code, texte = self.lancer("--apply", "--no-recursive")
        self.assertEqual(code, 0)
        self.assertIn("(sous-dossiers ignorés)", texte)
        self.assertIn("1 fichier(s)", texte)
        self.assertTrue((self.racine / "Film A.mkv").is_file())
        self.assertFalse((self.racine / "Sous" / "Film B.mkv").exists())
        self.assertIn("sans les sous-dossiers", self.lire_journal())

    def test_journal_a_l_endroit_demande(self):
        ailleurs = self.racine / "journal.txt"
        self.lancer("--log", str(ailleurs))
        self.assertTrue(ailleurs.is_file())
        self.assertFalse((self.racine / self.journal).exists())

    def test_journal_impossible_a_ecrire_n_arrete_pas_le_script(self):
        code, texte = self.lancer("--log", str(self.racine / "absent" / "journal.txt"))
        self.assertEqual(code, 0)
        self.assertIn("impossible d'écrire", texte)

    def test_un_mkv_deja_present_est_ignore_sans_erreur(self):
        (self.racine / "Film A.mkv").write_bytes(b"DEJA")
        code, texte = self.lancer("--apply")
        self.assertEqual(code, 0)
        self.assertIn("1 converti, 1 ignoré", texte)
        self.assertEqual((self.racine / "Film A.mkv").read_bytes(), b"DEJA")


class ArgumentsConvertisseur:
    def parse(self, *argv):
        with mock.patch.object(sys, "argv", ["x.py", "--dir", "D:\\Films", *argv]), redirect_stdout(io.StringIO()) as texte:
            args = self.module.parse_args()
        self.avertissement = texte.getvalue()
        return args

    def test_la_langue_des_sous_titres_suit_celle_de_l_audio(self):
        self.assertEqual(self.parse("--lang", "eng").sub_lang, "eng")
        self.assertEqual(self.parse("--lang", "eng", "--sub-lang", "fre").sub_lang, "fre")

    def test_une_langue_hors_norme_est_signalee(self):
        self.parse("--lang", "fr")
        self.assertIn("code ISO 639-2 à trois lettres", self.avertissement)
        self.parse()
        self.assertEqual(self.avertissement, "")

    def test_output_dir_devient_un_chemin(self):
        self.assertEqual(self.parse("--output-dir", "D:\\Sortie").output_dir, Path("D:\\Sortie"))
        self.assertIsNone(self.parse().output_dir)

    def test_valeurs_par_defaut(self):
        args = self.parse()
        self.assertEqual((args.apply, args.subs, args.tolerance, args.delete_source, args.overwrite), (False, "auto", 2.0, False, False))

    def test_subs_inconnu_refuse(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parse("--subs", "peut-etre")


class TestMainAvi(MainConvertisseur, ProgrammeTestCase):
    module, extension, journal = Avi_To_Mkv, "avi", "conversion.log"


class TestMainMp4(MainConvertisseur, ProgrammeTestCase):
    module, extension, journal = Mp4_To_Mkv, "mp4", "conversion_mp4.log"

    def test_le_bandeau_dit_comment_les_langues_sont_traitees(self):
        _, texte = self.lancer()
        self.assertIn("(--force-lang pour l'imposer)", texte)
        _, texte = self.lancer("--force-lang")
        self.assertIn("sauf ici, où --force-lang l'impose", texte)

    def test_les_journaux_des_deux_passes_ne_se_melangent_pas(self):
        # Les deux passes peuvent viser le même dossier : le journal des .mp4 ne doit pas écraser celui des .avi.
        self.lancer()
        self.assertFalse((self.racine / "conversion.log").exists())


class TestArgumentsAvi(ArgumentsConvertisseur, unittest.TestCase):
    module = Avi_To_Mkv


class TestArgumentsMp4(ArgumentsConvertisseur, unittest.TestCase):
    module = Mp4_To_Mkv

    def test_force_lang(self):
        self.assertTrue(self.parse("--force-lang").force_lang)
        self.assertFalse(self.parse().force_lang)


class TestOrdreDesFichiers(ProgrammeTestCase):
    def test_deux_convertisseurs_ne_prennent_que_leur_extension(self):
        for nom in ("a.avi", "b.AVI", "c.mp4", "d.MP4", "e.mkv"):
            (self.racine / nom).write_bytes(b"")
        self.assertEqual([p.name for p in Avi_To_Mkv.avi_files(self.racine)], ["a.avi", "b.AVI"])
        self.assertEqual([p.name for p in Mp4_To_Mkv.mp4_files(self.racine)], ["c.mp4", "d.MP4"])

    def test_commande_affichee_avec_ses_guillemets(self):
        commande = ["mkvmerge", "--output", "D:\\Mes Films\\a.mkv", "a.avi"]
        self.assertEqual(Avi_To_Mkv.display_command(commande), 'mkvmerge --output "D:\\Mes Films\\a.mkv" a.avi')
        self.assertEqual(Mp4_To_Mkv.display_command(commande), Avi_To_Mkv.display_command(commande))


# ----------------------------------------------------------------------------
# Verify_Files.py
# ----------------------------------------------------------------------------
class TestMainVerify(ProgrammeTestCase):
    """Des fichiers dont on décide d'avance s'ils sont sains (`defauts` : {nom: message})."""

    def setUp(self):
        super().setUp()
        for nom in ("Blade (1998).mkv", "Inception (2010).mkv"):
            (self.racine / nom).write_bytes(b"ORIGINAL " + nom.encode())
        (self.racine / "Sous").mkdir()
        (self.racine / "Sous" / "Dune (2021).mkv").write_bytes(b"ORIGINAL Dune")
        self.complets = []

    def lancer(self, *argv, defauts=None, mux=None, tools=("mkvmerge",)):
        defauts = defauts or {}

        def check(chemin, complet):
            self.complets.append(complet)
            nom = Path(chemin).name
            return "" if nom.endswith(".part") else defauts.get(nom, "")

        return self.lancer_main(Verify_Files, *argv,
                                shutil=types.SimpleNamespace(which=outils(*tools)),
                                check=check, run_tool=mux or MkvmergeSimule(writes=b"REMUX SAIN"))

    def journal(self):
        return (self.racine / "verification.log").read_text(encoding="utf-8")

    def contenu(self, nom):
        return (self.racine / nom).read_bytes()

    # ------------------------------------------------------------ ce qui manque
    def test_dossier_introuvable(self):
        self.racine = self.racine / "n_existe_pas"
        code, _ = self.lancer()
        self.assertIn("Dossier introuvable", code)

    def test_mkvmerge_absent(self):
        code, _ = self.lancer(tools=())
        self.assertIn("mkvmerge est introuvable", code)

    def test_aucun_mkv(self):
        vide = self.racine / "vide"
        vide.mkdir()
        self.racine = vide
        code, _ = self.lancer()
        self.assertIn("Aucun .mkv sous", code)

    # ------------------------------------------------------------ un passage
    def test_tout_est_sain(self):
        code, texte = self.lancer()
        self.assertEqual(code, 0)
        self.assertIn("3 fichier(s) contrôlé(s)", texte)
        self.assertIn("0 en défaut", texte)
        self.assertIn("Le contrôle rapide ne juge que l'index et la queue", texte)
        self.assertIn("Aucun défaut de structure.", self.journal())

    def test_un_defaut_sans_repair_donne_le_code_1(self):
        code, texte = self.lancer(defauts={"Blade (1998).mkv": "fin de fichier tronquée"})
        self.assertEqual(code, 1)
        self.assertIn("[DÉFAUT] Blade (1998).mkv", texte)
        self.assertIn("fin de fichier tronquée", texte)
        self.assertIn("avec --repair", texte)
        self.assertIn("-> non réparé", self.journal())
        self.assertEqual(self.contenu("Blade (1998).mkv"), b"ORIGINAL Blade (1998).mkv")

    def test_repair_remplace_le_fichier_abime(self):
        code, texte = self.lancer("--repair", defauts={"Blade (1998).mkv": "fin de fichier tronquée"})
        self.assertEqual(code, 0)
        self.assertIn("réparé", texte)
        self.assertIn("1 réparé(s), 0 échec(s)", texte)
        self.assertEqual(self.contenu("Blade (1998).mkv"), b"REMUX SAIN")
        self.assertEqual(self.contenu("Inception (2010).mkv"), b"ORIGINAL Inception (2010).mkv")     # les sains ne sont pas touchés
        self.assertIn("-> réparé", self.journal())
        self.assertFalse([n for n in self.noms() if n.endswith(".part")])

    def test_repair_qui_echoue_laisse_l_original_et_donne_le_code_1(self):
        code, texte = self.lancer("--repair", defauts={"Blade (1998).mkv": "x"}, mux=MkvmergeSimule(code=2, writes=b"TRONQUE", stderr="Erreur : disque plein"))
        self.assertEqual(code, 1)
        self.assertIn("ÉCHEC : Erreur : disque plein", texte)
        self.assertEqual(self.contenu("Blade (1998).mkv"), b"ORIGINAL Blade (1998).mkv")
        journal = self.journal()
        self.assertIn("-> RÉPARATION ÉCHOUÉE", journal)
        self.assertIn("RÉPARATIONS ÉCHOUÉES (originaux intacts) :", journal)
        self.assertFalse([n for n in self.noms() if n.endswith(".part")])

    def test_repair_sans_defaut_ne_lance_rien(self):
        mux = MkvmergeSimule()
        code, _ = self.lancer("--repair", mux=mux)
        self.assertEqual((code, mux.commands), (0, []))

    def test_full_descend_dans_les_clusters(self):
        _, texte = self.lancer("--full")
        self.assertIn("Contrôle complet", texte)
        self.assertEqual(set(self.complets), {True})
        self.assertNotIn("Le contrôle rapide ne juge", texte)
        self.assertIn("complet (chaîne entière)", self.journal())

    def test_par_defaut_le_controle_est_rapide(self):
        self.lancer()
        self.assertEqual(set(self.complets), {False})

    def test_sans_recursion_l_etage_seul(self):
        _, texte = self.lancer("--no-recursive", defauts={"Dune (2021).mkv": "x"})
        self.assertIn("2 fichier(s)", texte)
        self.assertIn("(sous-dossiers ignorés)", texte)
        self.assertIn("sans les sous-dossiers", self.journal())

    def test_journal_a_l_endroit_demande(self):
        ailleurs = self.racine / "controle.txt"
        self.lancer("--log", str(ailleurs))
        self.assertTrue(ailleurs.is_file())
        self.assertFalse((self.racine / "verification.log").exists())

    def test_journal_impossible_a_ecrire_n_arrete_pas_le_script(self):
        code, texte = self.lancer("--log", str(self.racine / "absent" / "controle.txt"))
        self.assertEqual(code, 0)
        self.assertIn("impossible d'écrire", texte)


class TestControleReel(unittest.TestCase):
    """check() : la structure d'abord, puis ce que mkvmerge sait lire."""

    def check(self, structure=None, identification=(INFO, ""), complet=False):
        with mock.patch.object(Verify_Files.ebml, "verifier", return_value=structure) as verifier, \
                mock.patch.object(Verify_Files, "identify", return_value=identification) as identifier:
            resultat = Verify_Files.check(Path("Film.mkv"), complet)
        self.verifier, self.identifier = verifier, identifier
        return resultat

    def test_fichier_sain(self):
        self.assertEqual(self.check(), "")

    def test_la_profondeur_demandee_est_transmise(self):
        self.check(complet=True)
        self.verifier.assert_called_once_with(Path("Film.mkv"), complet=True)

    def test_conteneur_abime_dispense_de_lancer_mkvmerge(self):
        self.assertEqual(self.check(structure="queue de fichier absente"), "queue de fichier absente")
        self.identifier.assert_not_called()

    def test_mkvmerge_qui_ne_lit_pas(self):
        self.assertEqual(self.check(identification=(None, "format non reconnu")), "format non reconnu")

    def test_fichier_sans_piste_video(self):
        sans_video = {"tracks": [{"id": 0, "type": "audio"}]}
        self.assertEqual(self.check(identification=(sans_video, "")), "aucune piste vidéo")


class TestAffichage(unittest.TestCase):
    def test_tailles_lisibles(self):
        self.assertEqual(Verify_Files.readable_size(2_000), "2 ko")
        self.assertEqual(Verify_Files.readable_size(5_000_000), "5.00 Mo")
        self.assertEqual(Verify_Files.readable_size(3_500_000_000), "3.50 Go")
        self.assertEqual(Verify_Files.readable_size(4_490_000_000_000), "4.49 To")

    def test_durees_lisibles(self):
        self.assertEqual(Verify_Files.readable_time(5), "5 s")
        self.assertEqual(Verify_Files.readable_time(90), "1.5 min")
        self.assertEqual(Verify_Files.readable_time(7200), "2.0 h")

    def test_progression_muette_hors_terminal(self):
        with redirect_stdout(io.StringIO()) as sortie:
            Verify_Files.progress(1, 3, "Film.mkv")
            Verify_Files.clear_line()
        self.assertEqual(sortie.getvalue(), "")

    def test_progression_en_terminal(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True
        with redirect_stdout(Terminal()) as sortie:
            Verify_Files.progress(2, 3, "Film.mkv")
        self.assertIn("2/3  Film.mkv", sortie.getvalue())
        self.assertTrue(sortie.getvalue().startswith("\r"))

    def test_progression_tronquee_a_la_largeur_du_terminal(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True
        with redirect_stdout(Terminal()) as sortie:
            Verify_Files.progress(1, 1, "x" * 500)
        self.assertEqual(len(sortie.getvalue()), 1 + Verify_Files.LARGEUR)

    def test_flux_ferme_ne_plante_pas(self):
        def ferme():
            raise ValueError("I/O operation on closed file")
        with mock.patch.object(Verify_Files.sys, "stdout", types.SimpleNamespace(isatty=ferme)):
            Verify_Files.progress(1, 1, "x")
            Verify_Files.clear_line()


if __name__ == "__main__":
    unittest.main()
