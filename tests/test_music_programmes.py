"""Music/Metadata.py et Music/Rename_Tracks.py de bout en bout : questions de fin de passage, pannes, journal, ligne de commande.

MusicBrainz est faux, les .flac sont fabriqués : on vérifie ce qu'un passage laisse sur le disque, ce qu'il dit, et le code de sortie qu'un script planifié lirait.
"""

import io
import sys
import types
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common import cli
from libraries.music import audio, flac, lookup
from libraries.music.musicbrainz import MusicBrainzError, release_url
from scripts.Music import Metadata as music
from scripts.Music import Rename_Tracks as renamer
from tests.test_album import OUTRUN, sortie
from tests.test_flac import fichier
from tests.test_music_metadata import AlbumTestCase, FauxMusicBrainz, arguments

AUTRE = dict(OUTRUN, id="rel-2", **{"release-group": {"id": "rg-2", "primary-type": "Album"}})
RIVAUX = [sortie("rel-1", "OutRun", 3, groupe="rg-1"), sortie("rel-2", "OutRun", 3, groupe="rg-2")]


class MusicBrainzCapricieux(FauxMusicBrainz):
    """Un MusicBrainz qui tombe en panne : sur la recherche, sur la fiche d'une sortie (`release_error` = {mbid: message}) ou sur la pochette."""

    def __init__(self, *args, search_error=None, release_error=None, cover_error=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.search_error, self.release_error, self.cover_error = search_error, release_error or {}, cover_error

    def search_releases(self, title, artist=None, exact=True, limit=25):
        if self.search_error:
            raise self.search_error
        return super().search_releases(title, artist, exact, limit)

    def release(self, mbid):
        if mbid in self.release_error:
            raise MusicBrainzError(self.release_error[mbid])
        return super().release(mbid)

    def cover(self, release_id, release_group_id=None, size="1200"):
        if self.cover_error:
            raise self.cover_error
        return super().cover(release_id, release_group_id, size)


def faux(**kwargs):
    kwargs.setdefault("releases", {"rel-1": OUTRUN, "rel-2": AUTRE})
    kwargs.setdefault("results", [sortie("rel-1", "OutRun", 3)])
    return MusicBrainzCapricieux(**kwargs)


class ProgrammeTestCase(AlbumTestCase):
    """Un album « Kavinsky/2013 - Outrun » de trois .flac, et de quoi lancer main() d'un script."""

    def lancer(self, module, mb, *argv, can_ask=False, answers=(), dossier=None):
        """(code de sortie, affichage). `answers` : réponses aux questions de fin de passage ; `dossier` : --dir, la racine de l'album par défaut."""
        ligne = [str(Path(module.__file__)), "--dir", str(dossier or self.racine()), *argv]
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, "argv", ligne))
            stack.enter_context(mock.patch.object(module, "MusicBrainz", return_value=mb))
            self.cache = stack.enter_context(mock.patch.object(module.cache, "Cache"))
            stack.enter_context(mock.patch.object(cli, "can_ask", lambda: can_ask))
            self.questions = stack.enter_context(mock.patch.object(cli, "ask_choice", side_effect=list(answers)))
            texte = stack.enter_context(redirect_stdout(io.StringIO()))
            code = module.main()
        self.affichage = texte.getvalue()
        return code, self.affichage

    def racine(self):
        return self.dossier.parent.parent

    def noms(self, dossier=None):
        return sorted(p.name for p in (dossier or self.dossier).iterdir())

    def octets(self):
        return {p.name: p.read_bytes() for p in self.dossier.iterdir()}

    def journal(self):
        return (self.racine() / "metadata.log").read_text(encoding="utf-8")


# ----------------------------------------------------------------------------
# Music/Metadata.py
# ----------------------------------------------------------------------------
class TestMetadataDeBoutEnBout(ProgrammeTestCase):
    def test_un_album_est_etiquete_puis_conforme(self):
        self.poser()
        code, texte = self.lancer(music, faux(), "--apply")
        self.assertEqual(code, 0)
        self.assertIn("TOTAL : 1/1 album(s) associé(s).", texte)
        self.assertEqual(flac.read(self.dossier / "01 - Prelude.flac").first("MUSICBRAINZ_ALBUMID"), "rel-1")
        code, _ = self.lancer(music, faux(), "--verify")
        self.assertEqual(code, 0)

    def test_la_simulation_n_ecrit_que_le_journal(self):
        self.poser()
        avant = self.octets()
        code, texte = self.lancer(music, faux())
        self.assertEqual(code, 0)
        self.assertIn("SIMULATION", texte)
        self.assertEqual(self.octets(), avant)
        self.assertTrue((self.racine() / "metadata.log").is_file())

    def test_le_journal_donne_le_lien_de_l_album(self):
        self.poser()
        self.lancer(music, faux())
        self.assertIn(release_url("rel-1"), self.journal())

    def test_verify_signale_les_ecarts_par_le_code_de_sortie(self):
        self.poser()
        code, texte = self.lancer(music, faux(), "--verify")
        self.assertEqual(code, 1)
        self.assertIn("À CORRIGER : 3 fichier(s) non conforme(s)", texte)

    def test_no_cache_n_est_pas_lu_du_cache(self):
        self.poser()
        self.lancer(music, faux(), "--no-cache")
        self.assertEqual(self.cache.call_args.kwargs, {"read": False, "source": "musicbrainz"})
        self.lancer(music, faux())
        self.assertEqual(self.cache.call_args.kwargs, {"read": True, "source": "musicbrainz"})

    def test_dossier_sans_album(self):
        vide = self.racine() / "vide"
        vide.mkdir()
        code, texte = self.lancer(music, faux(), dossier=vide)
        self.assertEqual(code, 0)
        self.assertIn("Aucun album trouvé", texte)

    def test_album_non_associe(self):
        self.poser()
        code, texte = self.lancer(music, faux(results=[]), "--apply")
        self.assertEqual(code, 1)
        self.assertIn("À CORRIGER : 1 sans fiche", texte)
        self.assertIn("[NON ASSOCIÉ]", texte)
        self.assertIn("[NON ASSOCIÉ]", self.journal())
        self.assertIn("sans lien (1)", self.journal())
        self.assertIn("TOTAL : 0/1", texte)

    def test_panne_de_musicbrainz_sur_un_album_ne_bloque_pas_les_suivants(self):
        self.poser()
        autre = self.dossier.parent / "2016 - Autre"
        autre.mkdir()
        for n, titre in enumerate(("Un", "Deux", "Trois"), 1):
            (autre / f"0{n} - {titre}.flac").write_bytes(fichier([f"TITLE={titre}", f"TRACKNUMBER={n}", "ALBUM=Autre", "ARTIST=Kavinsky"]))

        class Instable(MusicBrainzCapricieux):
            def search_releases(self, title, artist=None, exact=True, limit=25):
                if title == "Autre":
                    raise MusicBrainzError("HTTP 503")
                return super().search_releases(title, artist, exact, limit)

        code, texte = self.lancer(music, Instable(releases={"rel-1": OUTRUN}, results=[sortie("rel-1", "OutRun", 3)]), "--apply")
        self.assertIn("échec MusicBrainz : HTTP 503", texte)
        self.assertIn("[ÉCHEC MUSICBRAINZ]", self.journal())
        self.assertEqual(flac.read(self.dossier / "01 - Prelude.flac").first("MUSICBRAINZ_ALBUMID"), "rel-1")
        self.assertIn("TOTAL : 1/2", texte)
        self.assertEqual(code, 1)                    # un album sur deux n'a pas pu être traité : un script planifié doit le voir

    def test_fichier_illisible_bloque_l_album_et_se_voit_au_code_de_sortie(self):
        self.poser()
        (self.dossier / "04 - Casse.flac").write_bytes(b"pas un flac")
        avant = self.octets()
        code, texte = self.lancer(music, faux(), "--apply")
        self.assertEqual(code, 1)
        self.assertIn("[NON TRAITÉ] fichier(s) illisible(s)", texte)
        self.assertIn("[ILLISIBLE]", self.journal())
        self.assertEqual(self.octets(), avant)

    def test_dossier_d_un_format_non_pris_en_charge(self):
        ogg = self.racine() / "Autre artiste" / "Album ogg"
        ogg.mkdir(parents=True)
        (ogg / "01.ogg").write_bytes(b"OggS")
        code, texte = self.lancer(music, faux(), "--apply")
        self.assertEqual(code, 0)
        self.assertIn("[NON PRIS EN CHARGE] 1 fichier(s) .ogg", texte)
        self.assertIn("[NON PRIS EN CHARGE]", self.journal())

    def test_un_autre_format_a_cote_des_flac_est_signale(self):
        self.poser()
        (self.dossier / "bonus.ogg").write_bytes(b"OggS")
        _, texte = self.lancer(music, faux(), "--apply")
        self.assertIn("1 fichier(s) d'un autre format ignoré(s)", texte)
        self.assertIn("TOTAL : 1/1", texte)

    def test_mbid_ignore_quand_plusieurs_albums(self):
        self.poser()
        autre = self.racine() / "Daft Punk" / "Discovery"
        autre.mkdir(parents=True)
        (autre / "01 - One More Time.flac").write_bytes(fichier(["TITLE=One More Time", "TRACKNUMBER=1", "ALBUM=Discovery", "ARTIST=Daft Punk"]))
        _, texte = self.lancer(music, faux(), "--mbid", "4e5d9f0c-09b6-42bf-b495-e2d7cc288bf6")
        self.assertIn("--mbid ne s'applique qu'à un seul album ; 2 détectés", texte)

    def test_mbid_force_la_sortie_d_un_album_seul(self):
        self.poser()
        mb = faux(releases={"4e5d9f0c-09b6-42bf-b495-e2d7cc288bf6": OUTRUN})
        _, texte = self.lancer(music, mb, "--mbid", "4E5D9F0C-09B6-42BF-B495-E2D7CC288BF6")
        self.assertIn("id forcé par --mbid", texte)
        self.assertEqual(mb.searches, [])


class TestMetadataQuestions(ProgrammeTestCase):
    """Deux albums du même titre tiennent : la question attend la fin du passage."""

    def setUp(self):
        super().setUp()
        self.poser()
        self.mb = lambda **kw: faux(results=RIVAUX, **kw)

    def test_hors_terminal_l_album_reste_de_cote(self):
        avant = self.octets()
        code, texte = self.lancer(music, self.mb(), "--apply", can_ask=False)
        self.assertEqual(code, 1)
        self.assertIn("1 association(s) à confirmer", texte)
        self.assertIn("[À CONFIRMER]", self.journal())
        self.assertEqual(self.octets(), avant)

    def test_la_reponse_choisit_l_edition_ecrite(self):
        code, texte = self.lancer(music, self.mb(), "--apply", can_ask=True, answers=[1])
        self.assertEqual(code, 0)
        self.assertEqual(flac.read(self.dossier / "01 - Prelude.flac").first("MUSICBRAINZ_ALBUMID"), "rel-2")
        self.assertIn("[mbid-rel-2]", texte)
        self.assertIn(release_url("rel-2"), self.journal())

    def test_entree_garde_le_premier(self):
        self.lancer(music, self.mb(), "--apply", can_ask=True, answers=[0])
        self.assertEqual(flac.read(self.dossier / "01 - Prelude.flac").first("MUSICBRAINZ_ALBUMID"), "rel-1")

    def test_i_laisse_l_album_de_cote(self):
        avant = self.octets()
        code, texte = self.lancer(music, self.mb(), "--apply", can_ask=True, answers=[cli.ASK_SKIP])
        self.assertEqual(code, 1)
        self.assertIn("[NON TRAITÉ] album non confirmé", texte)
        self.assertEqual(self.octets(), avant)

    def test_no_ask_ne_pose_aucune_question(self):
        code, _ = self.lancer(music, self.mb(), "--apply", "--no-ask", can_ask=True)
        self.assertEqual(code, 0)
        self.assertEqual(self.questions.call_count, 0)
        self.assertEqual(flac.read(self.dossier / "01 - Prelude.flac").first("MUSICBRAINZ_ALBUMID"), "rel-1")

    def test_q_arrete_les_questions_suivantes(self):
        deuxieme = self.dossier.parent / "2016 - OutRun bis"
        deuxieme.mkdir()
        for n, titre in enumerate(("Prelude", "Blizzard", "Protovision"), 1):
            (deuxieme / f"0{n} - {titre}.flac").write_bytes(fichier([f"TITLE={titre}", f"TRACKNUMBER={n}", "ALBUM=Outrun", "ARTIST=Kavinsky"]))
        code, texte = self.lancer(music, self.mb(), "--apply", can_ask=True, answers=[cli.ASK_STOP])
        self.assertEqual(self.questions.call_count, 1)
        self.assertEqual(texte.count("[NON TRAITÉ] album non confirmé"), 2)
        self.assertEqual(code, 1)

    def test_panne_sur_l_edition_choisie(self):
        code, texte = self.lancer(music, self.mb(release_error={"rel-2": "HTTP 503"}), "--apply", can_ask=True, answers=[1])
        self.assertEqual(code, 1)
        self.assertIn("échec MusicBrainz : HTTP 503", texte)
        self.assertIn("[ÉCHEC MUSICBRAINZ]", self.journal())
        self.assertEqual(flac.read(self.dossier / "01 - Prelude.flac").first("MUSICBRAINZ_ALBUMID"), "")        # rien d'écrit


class TestMetadataPannesEtJournal(ProgrammeTestCase):
    def traiter(self, mb, found=None, **changes):
        found = found or self.trouver()
        args = arguments(**changes)
        with redirect_stdout(io.StringIO()) as texte:
            release, group = lookup.fetch_release("rel-1", mb, with_genres=not args.no_genres)
            report = music.process_album(found, release, group, args, mb)
        return report, texte.getvalue()

    def test_panne_de_cover_art_archive_n_empeche_pas_les_tags(self):
        self.poser()
        mb = faux(releases={"rel-1": dict(OUTRUN, **{"cover-art-archive": {"front": True}})}, cover_error=MusicBrainzError("HTTP 503"))
        report, texte = self.traiter(mb)
        self.assertIn("pochette ignorée (HTTP 503)", texte)
        self.assertEqual(report.failures, 0)
        relu = flac.read(self.dossier / "01 - Prelude.flac")
        self.assertEqual(relu.first("MUSICBRAINZ_ALBUMID"), "rel-1")
        self.assertFalse(relu.has_front_cover)

    def test_pas_de_pochette_chez_cover_art_archive(self):
        self.poser()
        _, texte = self.traiter(faux(cover=None))
        self.assertIn("aucune pochette sur Cover Art Archive", texte)
        self.assertEqual(flac.read(self.dossier / "01 - Prelude.flac").first("MUSICBRAINZ_ALBUMID"), "rel-1")

    def test_ecriture_en_echec_se_compte(self):
        self.poser()
        with mock.patch.object(music.audio, "write", side_effect=audio.AudioError("disque plein")):
            report, texte = self.traiter(faux())
        self.assertEqual(report.failures, 3)
        self.assertEqual(texte.count("[ÉCHEC] disque plein"), 3)
        self.assertEqual(report.exit_code, 1)

    def test_artiste_impose_est_annonce(self):
        self.poser()
        found = self.trouver()
        found.artist_name = "Kavinsky"
        report, texte = self.traiter(faux(), found=found)
        self.assertIn("artiste imposé : Kavinsky", texte)
        self.assertNotIn("/!\\ aucun artiste crédité", texte)

    def test_artiste_impose_qui_ne_ressemble_a_aucun_credit(self):
        self.poser()
        found = self.trouver()
        found.artist_name = "Quelqu'un d'autre"
        _, texte = self.traiter(faux(), found=found)
        self.assertIn("aucun artiste crédité de l'album ne ressemble à 'Quelqu'un d'autre'", texte)

    def test_un_fichier_sans_piste_est_note_non_traite_au_journal(self):
        self.poser()
        (self.dossier / "99 - Inconnu.flac").write_bytes(fichier(["TITLE=Inconnu", "TRACKNUMBER=99", "ALBUM=Outrun", "ARTIST=Kavinsky"]))
        journal = music.Journal()
        found = self.trouver()
        with redirect_stdout(io.StringIO()):
            report = music.handle(found, OUTRUN, {}, journal, arguments(), faux())
        self.assertEqual(report.skipped, 1)
        self.assertEqual(journal.entries[0][2], "[NON TRAITÉ]")

    def test_journal_separe_les_albums_lies_de_ceux_sans_lien(self):
        journal = music.Journal()
        journal.note("Kavinsky - Outrun", "rel-1")
        journal.note("Album perdu", None, "[NON ASSOCIÉ]")
        journal.note("Autre", "rel-2", "[NON TRAITÉ]")
        report = music.Report(matched=2, total=3)
        with redirect_stdout(io.StringIO()) as texte:
            music.write_log(self.racine(), journal, arguments(), report)
        contenu = self.journal()
        self.assertIn("# 2/3 album(s) associé(s)", contenu)
        self.assertIn(f"Kavinsky - Outrun  {release_url('rel-1')}", contenu)
        self.assertIn(f"{release_url('rel-2')}  [NON TRAITÉ]", contenu)
        self.assertIn("# --- sans lien (1) ---", contenu)
        self.assertLess(contenu.index("Autre"), contenu.index("sans lien"))
        self.assertIn("2 lien(s), 1 sans lien", texte.getvalue())

    def test_journal_impossible_a_ecrire_n_arrete_pas_le_script(self):
        journal = music.Journal()
        journal.note("x", "rel-1")
        with redirect_stdout(io.StringIO()) as texte:
            music.write_log(self.racine() / "n_existe_pas", journal, arguments(), music.Report())
        self.assertIn("metadata.log non écrit", texte.getvalue())


class TestMetadataLigneDeCommande(unittest.TestCase):
    def parse(self, *argv):
        with mock.patch.object(sys, "argv", ["Metadata.py", "--dir", "D:\\Musique", *argv]):
            return music.parse_args()

    def test_valeurs_par_defaut(self):
        args = self.parse()
        self.assertEqual((args.country, args.apply, args.verify, args.image_size, args.mbid), ("FR", False, False, "1200", None))

    def test_pays_en_majuscules(self):
        self.assertEqual(self.parse("--country", "de").country, "DE")

    def test_mbid_normalise(self):
        self.assertEqual(self.parse("--mbid", "4E5D9F0C-09B6-42BF-B495-E2D7CC288BF6").mbid, "4e5d9f0c-09b6-42bf-b495-e2d7cc288bf6")

    def test_mbid_invalide_refuse(self):
        with redirect_stderr(io.StringIO()) as erreur, self.assertRaises(SystemExit) as ctx:
            self.parse("--mbid", "pas-un-id")
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("--mbid attend un identifiant MusicBrainz", erreur.getvalue())

    def test_taille_de_pochette_inconnue_refusee(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parse("--image-size", "800")


# ----------------------------------------------------------------------------
# Music/Rename_Tracks.py
# ----------------------------------------------------------------------------
class TestRenameTracksDeBoutEnBout(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        self.poser(name_pattern="{n}. {title}.flac")

    def test_simulation_ne_renomme_rien(self):
        avant = self.noms()
        code, texte = self.lancer(renamer, faux())
        self.assertEqual(code, 0)             # des pistes à renommer ne sont pas une erreur : la simulation les annonce
        self.assertEqual(self.noms(), avant)
        self.assertIn("TOTAL : 0/3 piste(s) au bon nom.", texte)
        self.assertIn("-> 01 - Prelude.flac", texte)

    def test_application_renomme_d_apres_musicbrainz(self):
        code, texte = self.lancer(renamer, faux(), "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(self.noms(), ["01 - Prelude.flac", "02 - Blizzard.flac", "03 - Protovision.flac"])
        self.assertIn("TOTAL : 3/3 piste(s) au bon nom.", texte)

    def test_paroles_comptees_et_renommees(self):
        (self.dossier / "1. Prelude.lrc").write_text("[00:01.00]la la", encoding="utf-8")
        _, texte = self.lancer(renamer, faux(), "--apply")
        self.assertIn("01 - Prelude.lrc", self.noms())
        self.assertIn("3/3 piste(s) au bon nom, 1 fichier(s) de paroles renommé(s).", texte)

    def test_paroles_a_renommer_en_simulation(self):
        (self.dossier / "1. Prelude.lrc").write_text("x", encoding="utf-8")
        _, texte = self.lancer(renamer, faux())
        self.assertIn("1 fichier(s) de paroles à renommer.", texte)

    def test_dossier_sans_album(self):
        vide = self.racine() / "vide"
        vide.mkdir()
        code, texte = self.lancer(renamer, faux(), dossier=vide)
        self.assertEqual(code, 0)
        self.assertIn("Aucun album trouvé", texte)

    def test_fichier_illisible_laisse_l_album_en_place(self):
        (self.dossier / "4. Casse.flac").write_bytes(b"pas un flac")
        avant = self.noms()
        code, texte = self.lancer(renamer, faux(), "--apply")
        self.assertEqual(code, 1)
        self.assertIn("[NON TRAITÉ] fichier(s) illisible(s)", texte)
        self.assertEqual(self.noms(), avant)
        self.assertIn("TOTAL : 0/4", texte)

    def test_album_non_reconnu_laisse_ses_pistes_comptees_mal_nommees(self):
        avant = self.noms()
        code, texte = self.lancer(renamer, faux(results=[]), "--apply")
        self.assertEqual(code, 1)
        self.assertIn("À CORRIGER : 1 album(s) non traité(s)", texte)
        self.assertEqual(self.noms(), avant)
        self.assertIn("TOTAL : 0/3", texte)

    def test_panne_de_musicbrainz_ne_renomme_rien(self):
        avant = self.noms()
        code, texte = self.lancer(renamer, faux(search_error=MusicBrainzError("HTTP 503")), "--apply")
        self.assertEqual(code, 1)
        self.assertIn("échec MusicBrainz : HTTP 503", texte)
        self.assertEqual(self.noms(), avant)

    def test_dossier_d_un_format_non_pris_en_charge(self):
        ogg = self.racine() / "Autre" / "Album ogg"
        ogg.mkdir(parents=True)
        (ogg / "01.ogg").write_bytes(b"OggS")
        _, texte = self.lancer(renamer, faux(), "--apply")
        self.assertIn("[NON PRIS EN CHARGE]", texte)
        self.assertEqual(self.noms(ogg), ["01.ogg"])

    def test_un_autre_format_a_cote_est_signale_et_laisse(self):
        (self.dossier / "bonus.ogg").write_bytes(b"OggS")
        code, texte = self.lancer(renamer, faux(), "--apply")
        self.assertEqual(code, 0)
        self.assertIn("1 fichier(s) d'un autre format ignoré(s)", texte)
        self.assertIn("bonus.ogg", self.noms())

    def test_mbid_ignore_quand_plusieurs_albums(self):
        autre = self.racine() / "Daft Punk" / "Discovery"
        autre.mkdir(parents=True)
        (autre / "01.flac").write_bytes(fichier(["TITLE=One More Time", "TRACKNUMBER=1", "ALBUM=Discovery", "ARTIST=Daft Punk"]))
        _, texte = self.lancer(renamer, faux(), "--mbid", "4e5d9f0c-09b6-42bf-b495-e2d7cc288bf6")
        self.assertIn("--mbid ne s'applique qu'à un seul album", texte)


class TestRenameTracksQuestions(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        self.poser(name_pattern="{n}. {title}.flac")

    def test_hors_terminal_rien_n_est_renomme(self):
        avant = self.noms()
        code, texte = self.lancer(renamer, faux(results=RIVAUX), "--apply", can_ask=False)
        self.assertEqual(code, 1)
        self.assertIn("[À CONFIRMER]", texte)
        self.assertEqual(self.noms(), avant)

    def test_la_reponse_choisit_l_edition_qui_renomme(self):
        # rel-2 a des titres différents : la réponse décide des noms écrits.
        autre = dict(AUTRE, media=[dict(OUTRUN["media"][0], tracks=[dict(t, title=f"Titre {t['position']}") for t in OUTRUN["media"][0]["tracks"]])])
        mb = faux(results=RIVAUX, releases={"rel-1": OUTRUN, "rel-2": autre})
        code, _ = self.lancer(renamer, mb, "--apply", can_ask=True, answers=[1])
        self.assertEqual(code, 0)
        self.assertEqual(self.noms(), ["01 - Titre 1.flac", "02 - Titre 2.flac", "03 - Titre 3.flac"])

    def test_i_laisse_l_album_de_cote(self):
        avant = self.noms()
        code, texte = self.lancer(renamer, faux(results=RIVAUX), "--apply", can_ask=True, answers=[cli.ASK_SKIP])
        self.assertEqual(code, 1)
        self.assertIn("[NON TRAITÉ] album non confirmé", texte)
        self.assertEqual(self.noms(), avant)

    def test_panne_sur_l_edition_choisie(self):
        avant = self.noms()
        code, texte = self.lancer(renamer, faux(results=RIVAUX, release_error={"rel-2": "HTTP 503"}), "--apply", can_ask=True, answers=[1])
        self.assertEqual(code, 1)
        self.assertIn("échec MusicBrainz : HTTP 503", texte)
        self.assertEqual(self.noms(), avant)


class TestRenameTracksLigneDeCommande(unittest.TestCase):
    def parse(self, *argv):
        with mock.patch.object(sys, "argv", ["Rename_Tracks.py", "--dir", "D:\\Musique", *argv]):
            return renamer.parse_args()

    def test_valeurs_par_defaut(self):
        args = self.parse()
        self.assertEqual((args.country, args.apply, args.no_ask, args.mbid), ("FR", False, False, None))

    def test_pays_en_majuscules_et_mbid_normalise(self):
        args = self.parse("--country", "be", "--mbid", "4E5D9F0C-09B6-42BF-B495-E2D7CC288BF6")
        self.assertEqual((args.country, args.mbid), ("BE", "4e5d9f0c-09b6-42bf-b495-e2d7cc288bf6"))

    def test_mbid_invalide_refuse(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            self.parse("--mbid", "xyz")
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
