"""Le fichier cover du dossier d'un album : repéré, préféré à toute pochette embarquée par la fiche et par Metadata.py, et embarqué seul par Cover.py."""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.music import coverfile, library, mp3
from libraries.music.tags import AudioError
from scripts.Music import Cover as cover
from tests.test_flac import image
from tests.test_music_metadata import AlbumTestCase, FauxMusicBrainz, Mp3AlbumTestCase
from tests.test_music_programmes import faux

FICHIER = b"\xff\xd8COVER-DU-DOSSIER"
EN_LIGNE = b"\xff\xd8JPEG"


class TestRecherche(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dossier = Path(self._tmp.name)

    def poser(self, *noms):
        for nom in noms:
            (self.dossier / nom).write_bytes(b"x")

    def test_aucun_fichier(self):
        self.poser("01.flac", "notes.txt")
        self.assertIsNone(coverfile.find(self.dossier))

    def test_cover_jpg(self):
        self.poser("cover.jpg")
        self.assertEqual(coverfile.find(self.dossier).name, "cover.jpg")

    def test_la_casse_ne_compte_pas(self):
        self.poser("Folder.PNG")
        self.assertEqual(coverfile.find(self.dossier).name, "Folder.PNG")

    def test_cover_l_emporte_sur_folder_et_jpg_sur_png(self):
        self.poser("folder.jpg", "cover.png", "cover.jpg")
        self.assertEqual(coverfile.find(self.dossier).name, "cover.jpg")
        (self.dossier / "cover.jpg").unlink()
        self.assertEqual(coverfile.find(self.dossier).name, "cover.png")

    def test_un_autre_nom_n_est_pas_une_cover(self):
        self.poser("scan-arriere.jpg", "cover.jpg.bak")
        self.assertIsNone(coverfile.find(self.dossier))

    def test_un_dossier_nomme_cover_n_est_pas_un_fichier(self):
        (self.dossier / "cover.jpg").mkdir()
        self.assertIsNone(coverfile.find(self.dossier))

    def test_dossier_introuvable(self):
        self.assertIsNone(coverfile.find(self.dossier / "absent"))

    def test_picture_jpeg_et_png(self):
        (self.dossier / "cover.jpg").write_bytes(FICHIER)
        self.assertEqual((coverfile.picture(self.dossier / "cover.jpg").mime, coverfile.picture(self.dossier / "cover.jpg").kind), ("image/jpeg", 3))
        (self.dossier / "cover.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        self.assertEqual(coverfile.picture(self.dossier / "cover.png").mime, "image/png")

    def test_webp_ne_s_embarque_pas(self):
        (self.dossier / "cover.webp").write_bytes(b"RIFF")
        with self.assertRaises(AudioError):
            coverfile.picture(self.dossier / "cover.webp")

    def test_fichier_vide_refuse(self):
        (self.dossier / "cover.jpg").write_bytes(b"")
        self.assertIsNone(coverfile.read(self.dossier / "cover.jpg"))
        with self.assertRaises(AudioError):
            coverfile.picture(self.dossier / "cover.jpg")


class MediathequeTestCase(AlbumTestCase):
    def releases(self):
        albums = library.scan(self.dossier.parent)
        for release in albums:
            for track in release.tracks:
                library.read_info(track)
        return albums


class TestMediatheque(MediathequeTestCase):
    def test_le_fichier_est_repere_au_scan(self):
        self.poser()
        (self.dossier / "Cover.jpg").write_bytes(FICHIER)
        (release,) = self.releases()
        self.assertEqual(release.cover_file.name, "Cover.jpg")

    def test_le_fichier_l_emporte_sur_la_pochette_embarquee(self):
        self.poser(images=[image(b"EMBARQUEE")])
        (self.dossier / "cover.jpg").write_bytes(FICHIER)
        (release,) = self.releases()
        self.assertEqual(library.read_release_cover(release), FICHIER)

    def test_sans_fichier_la_pochette_embarquee_sert(self):
        self.poser(images=[image(b"EMBARQUEE")])
        (release,) = self.releases()
        self.assertIsNone(release.cover_file)
        self.assertEqual(library.read_release_cover(release), b"EMBARQUEE")

    def test_fichier_illisible_la_pochette_embarquee_sert(self):
        self.poser(images=[image(b"EMBARQUEE")])
        (self.dossier / "cover.jpg").write_bytes(b"")
        (release,) = self.releases()
        self.assertEqual(library.read_release_cover(release), b"EMBARQUEE")

    def test_aucune_pochette(self):
        self.poser()
        (release,) = self.releases()
        self.assertIsNone(library.read_release_cover(release))
        self.assertTrue(release.key.endswith("-nocover"))

    def test_la_cle_change_quand_le_fichier_change(self):
        self.poser()
        chemin = self.dossier / "cover.jpg"
        chemin.write_bytes(FICHIER)
        (avant,) = self.releases()
        chemin.write_bytes(FICHIER + b"PLUS-GROS")
        (apres,) = self.releases()
        self.assertIn("-file-", avant.key)
        self.assertNotEqual(avant.key, apres.key)

    def test_le_cover_d_un_dossier_de_disque_ne_compte_pas(self):
        (self.dossier / "CD1").mkdir()
        self.poser(name_pattern="CD1/0{n} - {title}.flac")
        (self.dossier / "CD1" / "cover.jpg").write_bytes(FICHIER)
        (release,) = self.releases()
        self.assertEqual(len(release.tracks), 3)
        self.assertIsNone(release.cover_file)



class TestMetadata(AlbumTestCase):
    """Metadata.py : le fichier cover prime sur Cover Art Archive et sur la pochette déjà embarquée, sans rien télécharger."""

    def test_le_fichier_est_embarque_sans_rien_telecharger(self):
        self.poser()
        (self.dossier / "cover.jpg").write_bytes(FICHIER)
        mb = FauxMusicBrainz(releases=faux().releases)
        report, texte = self.traiter(mb)
        self.assertEqual(report.failures, 0)
        self.assertEqual(mb.covers, [])
        self.assertIn("pochette du dossier (cover.jpg)", texte)
        for n in (1, 2, 3):
            (front,) = [p for p in self.relire(n).pictures if p.kind == 3]
            self.assertEqual(front.data, FICHIER)

    def test_le_fichier_remplace_la_pochette_embarquee_sans_replace_cover(self):
        self.poser(images=[image(b"ANCIENNE")])
        (self.dossier / "cover.jpg").write_bytes(FICHIER)
        self.traiter(faux())
        (front,) = [p for p in self.relire().pictures if p.kind == 3]
        self.assertEqual(front.data, FICHIER)

    def test_fichier_inembarquable_cover_art_archive_le_remplace(self):
        self.poser()
        (self.dossier / "cover.webp").write_bytes(b"RIFF")
        mb = FauxMusicBrainz(releases={"rel-1": dict(faux().releases["rel-1"], **{"cover-art-archive": {"front": True}})})
        _, texte = self.traiter(mb)
        self.assertIn("seuls le JPEG et le PNG s'embarquent", texte)
        (front,) = [p for p in self.relire().pictures if p.kind == 3]
        self.assertEqual(front.data, EN_LIGNE)

    def test_no_cover_ignore_le_fichier(self):
        self.poser()
        (self.dossier / "cover.jpg").write_bytes(FICHIER)
        self.traiter(faux(), no_cover=True)
        self.assertFalse(self.relire().has_front_cover)

    def test_verify_signale_une_pochette_differente_du_fichier(self):
        self.poser(images=[image(b"ANCIENNE")])
        (self.dossier / "cover.jpg").write_bytes(FICHIER)
        report, texte = self.traiter(faux(), verify=True)
        self.assertIn("[DIFF] pochette : différente de cover.jpg", texte)
        self.assertGreaterEqual(report.diffs, 1)

    def test_deuxieme_passage_deja_conforme(self):
        self.poser()
        (self.dossier / "cover.jpg").write_bytes(FICHIER)
        self.traiter(faux())
        report, _ = self.traiter(faux(), verify=True)
        self.assertEqual(report.diffs, 0)


class TestMetadataTelechargement(AlbumTestCase):
    """Metadata.py : la pochette téléchargée est aussi enregistrée en cover.jpg dans le dossier de l'album."""

    def fronts(self, n=1):
        return [p.data for p in self.relire(n).pictures if p.kind == 3]

    def test_la_pochette_telechargee_devient_cover_jpg(self):
        self.poser()
        mb = faux()
        _, texte = self.traiter(mb)
        self.assertEqual((self.dossier / "cover.jpg").read_bytes(), EN_LIGNE)
        self.assertIn("cover.jpg enregistré dans le dossier", texte)
        self.assertEqual([self.fronts(n) for n in (1, 2, 3)], [[EN_LIGNE]] * 3)
        self.assertEqual(len(mb.covers), 1)

    def test_la_simulation_n_ecrit_pas_le_fichier(self):
        self.poser()
        _, texte = self.traiter(faux(), apply=False)
        self.assertFalse((self.dossier / "cover.jpg").exists())
        self.assertIn("+ cover.jpg dans le dossier", texte)

    def test_no_cover_file(self):
        self.poser()
        self.traiter(faux(), no_cover_file=True)
        self.assertFalse((self.dossier / "cover.jpg").exists())
        self.assertEqual(self.fronts(), [EN_LIGNE])

    def test_no_cover_n_enregistre_rien(self):
        self.poser()
        self.traiter(faux(), no_cover=True)
        self.assertFalse((self.dossier / "cover.jpg").exists())

    def test_replace_cover_remplace_l_embarquee_et_enregistre_le_fichier(self):
        self.poser(images=[image(b"RECTO-VERSO")])
        self.traiter(faux(), replace_cover=True)
        self.assertEqual(self.fronts(), [EN_LIGNE])
        self.assertEqual((self.dossier / "cover.jpg").read_bytes(), EN_LIGNE)

    def test_passage_suivant_le_fichier_sert_et_rien_n_est_retelecharge(self):
        self.poser(images=[image(b"RECTO-VERSO")])
        self.traiter(faux(), replace_cover=True)
        (self.dossier / "cover.jpg").write_bytes(FICHIER)         # remplacé à la main
        mb = faux()
        self.traiter(mb, replace_cover=True)
        self.assertEqual(mb.covers, [])
        self.assertEqual(self.fronts(), [FICHIER])
        self.assertEqual((self.dossier / "cover.jpg").read_bytes(), FICHIER)

    def test_pochette_deja_embarquee_sans_replace_cover_rien_n_est_telecharge(self):
        self.poser(images=[image(b"EMBARQUEE")])
        mb = faux()
        self.traiter(mb)
        self.assertEqual(mb.covers, [])
        self.assertFalse((self.dossier / "cover.jpg").exists())

    def test_png_donne_cover_png(self):
        png = b"\x89PNG\r\n\x1a\n" + bytes(30)
        self.poser()
        self.traiter(faux(cover=png))
        self.assertEqual((self.dossier / "cover.png").read_bytes(), png)
        self.assertFalse((self.dossier / "cover.jpg").exists())

    def test_format_inconnu_est_embarque_mais_pas_enregistre(self):
        self.poser()
        _, texte = self.traiter(faux(cover=b"GIF89a-pas-un-jpeg"))
        self.assertIn("ni JPEG ni PNG", texte)
        self.assertEqual(self.fronts(), [b"GIF89a-pas-un-jpeg"])
        self.assertFalse(any(p.name.startswith("cover") for p in self.dossier.iterdir()))

    def test_pas_de_pochette_chez_cover_art_archive_pas_de_fichier(self):
        self.poser()
        self.traiter(faux(cover=None))
        self.assertFalse((self.dossier / "cover.jpg").exists())

    def test_ecriture_du_fichier_en_echec_n_empeche_pas_les_pistes(self):
        self.poser()
        with mock.patch.object(coverfile, "write", side_effect=PermissionError(13, "Accès refusé")):
            report, texte = self.traiter(faux())
        self.assertEqual(report.failures, 0)
        self.assertIn("cover.jpg non enregistré : Accès refusé", texte)
        self.assertEqual(self.fronts(), [EN_LIGNE])


class CoverTestCase(AlbumTestCase):
    def lancer(self, *argv, dossier=None):
        ligne = [str(Path(cover.__file__)), "--dir", str(dossier or self.dossier.parent.parent), *argv]
        with mock.patch.object(sys, "argv", ligne), redirect_stdout(io.StringIO()) as texte:
            code = cover.main()
        return code, texte.getvalue()

    def octets(self):
        return {p.name: p.read_bytes() for p in self.dossier.iterdir()}

    def fronts(self, n=1):
        return [p.data for p in self.relire(n).pictures if p.kind == 3]


class TestCover(CoverTestCase):
    def test_simulation_n_ecrit_rien(self):
        self.poser()
        (self.dossier / "cover.jpg").write_bytes(FICHIER)
        avant = self.octets()
        code, texte = self.lancer()
        self.assertEqual(code, 0)
        self.assertIn("SIMULATION", texte)
        self.assertIn("pochette ajoutée (simulation)", texte)
        self.assertEqual(self.octets(), avant)

    def test_apply_embarque_dans_chaque_piste(self):
        self.poser()
        (self.dossier / "cover.jpg").write_bytes(FICHIER)
        code, texte = self.lancer("--apply")
        self.assertEqual(code, 0)
        self.assertIn("TOTAL : 1/1 album(s) ont un fichier cover.", texte)
        for n in (1, 2, 3):
            self.assertEqual(self.fronts(n), [FICHIER])

    def test_apply_ne_touche_pas_aux_tags(self):
        self.poser()
        (self.dossier / "cover.jpg").write_bytes(FICHIER)
        avant = self.relire().comments
        self.lancer("--apply")
        self.assertEqual(self.relire().comments, avant)

    def test_remplace_la_pochette_de_face_et_garde_les_autres_images(self):
        self.poser(images=[image(b"ANCIENNE", kind=3), image(b"DOS", kind=4)])
        (self.dossier / "cover.jpg").write_bytes(FICHIER)
        _, texte = self.lancer("--apply")
        self.assertIn("pochette remplacée", texte)
        pictures = self.relire().pictures
        self.assertEqual(sorted((p.kind, p.data) for p in pictures), [(3, FICHIER), (4, b"DOS")])

    def test_deuxieme_passage_deja_conforme_sans_reecriture(self):
        self.poser()
        (self.dossier / "cover.jpg").write_bytes(FICHIER)
        self.lancer("--apply")
        avant = self.octets()
        with mock.patch.object(cover.audio, "write", side_effect=AssertionError("réécrit")):
            code, texte = self.lancer("--apply")
        self.assertEqual(code, 0)
        self.assertEqual(texte.count("déjà conforme"), 3)
        self.assertEqual(self.octets(), avant)

    def test_verify_code_1_puis_0(self):
        self.poser()
        (self.dossier / "cover.jpg").write_bytes(FICHIER)
        code, texte = self.lancer("--verify")
        self.assertEqual(code, 1)
        self.assertIn("À CORRIGER : 3 fichier(s) non conforme(s)", texte)
        self.lancer("--apply")
        code, _ = self.lancer("--verify")
        self.assertEqual(code, 0)

    def test_album_sans_fichier_est_liste_sans_erreur(self):
        self.poser(images=[image(b"EMBARQUEE")])
        avant = self.octets()
        code, texte = self.lancer("--apply")
        self.assertEqual(code, 0)
        self.assertIn("Sans fichier cover (1)", texte)
        self.assertIn("TOTAL : 0/1", texte)
        self.assertEqual(self.octets(), avant)

    def test_png(self):
        self.poser()
        png = b"\x89PNG\r\n\x1a\n" + bytes(30)
        (self.dossier / "folder.png").write_bytes(png)
        self.lancer("--apply")
        (front,) = [p for p in self.relire().pictures if p.kind == 3]
        self.assertEqual((front.data, front.mime), (png, "image/png"))

    def test_webp_signale_et_rien_n_est_ecrit(self):
        self.poser()
        (self.dossier / "cover.webp").write_bytes(b"RIFF")
        avant = self.octets()
        code, texte = self.lancer("--apply")
        self.assertEqual(code, 1)
        self.assertIn("seuls le JPEG et le PNG s'embarquent", texte)
        self.assertEqual(self.octets(), avant)

    def test_piste_illisible_bloque_l_album(self):
        self.poser()
        (self.dossier / "cover.jpg").write_bytes(FICHIER)
        (self.dossier / "02 - Blizzard.flac").write_bytes(b"pas un flac")
        avant = self.octets()
        code, texte = self.lancer("--apply")
        self.assertEqual(code, 1)
        self.assertIn("fichier(s) illisible(s)", texte)
        self.assertEqual(self.octets(), avant)

    def test_ecriture_en_echec_se_compte(self):
        self.poser()
        (self.dossier / "cover.jpg").write_bytes(FICHIER)
        with mock.patch.object(cover.audio, "write", side_effect=AudioError("disque plein")):
            code, texte = self.lancer("--apply")
        self.assertEqual(code, 1)
        self.assertIn("3 écriture(s) en échec", texte)

    def test_un_seul_album(self):
        self.poser()
        (self.dossier / "cover.jpg").write_bytes(FICHIER)
        code, _ = self.lancer("--apply", dossier=self.dossier)
        self.assertEqual(code, 0)
        self.assertEqual(self.fronts(), [FICHIER])

    def test_dossier_sans_album(self):
        vide = self.dossier.parent / "vide"
        vide.mkdir()
        code, texte = self.lancer(dossier=vide)
        self.assertEqual(code, 0)
        self.assertIn("Aucun album trouvé", texte)


class TestExtraction(CoverTestCase):
    """--extract : les albums déjà étiquetés donnent leur pochette embarquée en fichier cover."""
    JPEG = b"\xff\xd8EMBARQUEE-JPEG"
    PNG = b"\x89PNG\r\n\x1a\n" + bytes(30)

    def piste(self, n):
        return self.dossier / f"0{n} - {self.TITRES[n - 1]}.flac"

    def test_simulation_n_ecrit_rien(self):
        self.poser(images=[image(self.JPEG)])
        avant = self.octets()
        code, texte = self.lancer("--extract")
        self.assertEqual(code, 0)
        self.assertIn("cover.jpg serait écrit (simulation)", texte)
        self.assertEqual(self.octets(), avant)

    def test_apply_ecrit_cover_jpg_sans_toucher_aux_pistes(self):
        self.poser(images=[image(self.JPEG)])
        pistes = {n: self.piste(n).read_bytes() for n in (1, 2, 3)}
        code, _ = self.lancer("--extract", "--apply")
        self.assertEqual(code, 0)
        self.assertEqual((self.dossier / "cover.jpg").read_bytes(), self.JPEG)
        for n, octets in pistes.items():
            self.assertEqual(self.piste(n).read_bytes(), octets)

    def test_png_donne_cover_png(self):
        self.poser(images=[image(self.PNG, mime="image/png")])
        self.lancer("--extract", "--apply")
        self.assertEqual((self.dossier / "cover.png").read_bytes(), self.PNG)
        self.assertFalse((self.dossier / "cover.jpg").exists())

    def test_l_extension_suit_le_contenu_pas_le_type_declare(self):
        self.poser(images=[image(self.PNG, mime="image/jpeg")])
        self.lancer("--extract", "--apply")
        self.assertTrue((self.dossier / "cover.png").is_file())

    def test_un_fichier_cover_existant_n_est_jamais_remplace(self):
        self.poser(images=[image(self.JPEG)])
        (self.dossier / "Folder.png").write_bytes(b"A MOI")
        code, texte = self.lancer("--extract", "--apply")
        self.assertEqual(code, 0)
        self.assertIn("Folder.png existe déjà", texte)
        self.assertFalse((self.dossier / "cover.jpg").exists())
        self.assertEqual((self.dossier / "Folder.png").read_bytes(), b"A MOI")

    def test_sans_pochette_embarquee_l_album_est_liste(self):
        self.poser()
        code, texte = self.lancer("--extract", "--apply")
        self.assertEqual(code, 0)
        self.assertIn("Sans pochette à extraire (1)", texte)
        self.assertIsNone(coverfile.find(self.dossier))

    def test_image_inconnue_n_est_pas_extraite(self):
        self.poser(images=[image(b"GIF89a-pas-un-jpeg")])
        _, texte = self.lancer("--extract", "--apply")
        self.assertIn("aucune pochette JPEG ou PNG", texte)
        self.assertIsNone(coverfile.find(self.dossier))

    def test_image_pas_de_face_est_signalee(self):
        self.poser(images=[image(self.JPEG, kind=4)])
        _, texte = self.lancer("--extract", "--apply")
        self.assertIn("pas typée « face »", texte)
        self.assertTrue((self.dossier / "cover.jpg").is_file())

    def test_la_face_passe_avant_les_autres_images(self):
        self.poser(images=[image(b"\xff\xd8DOS", kind=4), image(self.JPEG, kind=3)])
        self.lancer("--extract", "--apply")
        self.assertEqual((self.dossier / "cover.jpg").read_bytes(), self.JPEG)

    def test_piste_illisible_sautee(self):
        self.poser(images=[image(self.JPEG)])
        self.piste(1).write_bytes(b"pas un flac")
        code, _ = self.lancer("--extract", "--apply")
        self.assertEqual(code, 0)
        self.assertEqual((self.dossier / "cover.jpg").read_bytes(), self.JPEG)

    def test_ecriture_en_echec_se_compte(self):
        self.poser(images=[image(self.JPEG)])
        with mock.patch.object(cover.coverfile, "write", side_effect=PermissionError(13, "Accès refusé")):
            code, texte = self.lancer("--extract", "--apply")
        self.assertEqual(code, 1)
        self.assertIn("[ÉCHEC] cover.jpg : Accès refusé", texte)

    def test_extraire_puis_embarquer_ne_reecrit_rien(self):
        self.poser(images=[image(self.JPEG)])
        self.lancer("--extract", "--apply")
        code, texte = self.lancer("--verify")
        self.assertEqual(code, 0)
        self.assertEqual(texte.count("déjà conforme"), 3)

    def test_extract_et_verify_s_excluent(self):
        self.poser()
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            self.lancer("--extract", "--verify")


class TestCoverMp3(Mp3AlbumTestCase, CoverTestCase):
    def relire_mp3(self):
        return mp3.read(self.dossier / "01 - Prelude.mp3")

    def test_embarque_dans_un_mp3_sans_toucher_aux_tags(self):
        self.poser()
        (self.dossier / "cover.jpg").write_bytes(FICHIER)
        avant = self.relire_mp3().comments
        code, _ = self.lancer("--apply")
        self.assertEqual(code, 0)
        relu = self.relire_mp3()
        self.assertEqual([p.data for p in relu.pictures if p.kind == 3], [FICHIER])
        self.assertEqual(relu.comments, avant)
        code, _ = self.lancer("--verify")
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
