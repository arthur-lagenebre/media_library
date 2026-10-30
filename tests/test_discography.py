"""La discographie d'un artiste et Music/Discography.py : ce qui manque dans son dossier, posé comme wanted.py le lit.

MusicBrainz est faux ; les dossiers et les .flac sont fabriqués dans un dossier temporaire.
"""

import io
import sys
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common import cli
from libraries.music import discography, wanted
from libraries.music.musicbrainz import MusicBrainzError
from scripts.Music import Discography as script
from tests.test_library import piste

RADIOHEAD = "a74b1b7f-71a5-4011-9441-d0b5e4122711"


JPEG = b"\xff\xd8\xff\xe0JPEG"
PNG = b"\x89PNG\r\n\x1a\n" + b"PNG"


def groupe(titre, date="", primaire="Album", secondaires=()):
    return {"id": "rg-" + discography.title_key(titre), "title": titre, "first-release-date": date, "primary-type": primaire, "secondary-types": list(secondaires)}


def titres(releases):
    return [(r.year, r.title) for r in releases]


DISCOGRAPHIE = [
    groupe("Pablo Honey", "1993-02-22"),
    groupe("The Bends", "1995-03-13"),
    groupe("OK Computer", "1997-05-21"),
    groupe("Kid A", "2000-10-02"),
    groupe("Airbag / How Am I Driving?", "1998-02-24", "EP"),
    groupe("Creep", "1992-09-21", "Single"),
    groupe("I Might Be Wrong", "2001-11-12", "Album", ["Live"]),
    groupe("Sans date", "", "Album"),
]


class TestClassement(unittest.TestCase):
    def test_categorie_d_un_release_group(self):
        self.assertEqual(discography.categorize(groupe("x", primaire="Album")), "album")
        self.assertEqual(discography.categorize(groupe("x", primaire="EP")), "ep")
        self.assertEqual(discography.categorize(groupe("x", primaire="Single")), "single")
        self.assertEqual(discography.categorize({"title": "x"}), "other")

    def test_un_album_live_reste_un_live(self):
        self.assertEqual(discography.categorize(groupe("x", secondaires=["Compilation", "Live"])), "live")
        self.assertEqual(discography.categorize(groupe("x", secondaires=["DJ-mix"])), "remix")

    def test_annee(self):
        self.assertEqual(discography.release_year({"first-release-date": "1997-05-21"}), "1997")
        self.assertEqual(discography.release_year({"first-release-date": "2011"}), "2011")
        self.assertEqual(discography.release_year({"first-release-date": ""}), "")
        self.assertEqual(discography.release_year({}), "")

    def test_nom_de_fichier(self):
        self.assertEqual(discography.file_name("1997", "OK Computer"), "1997 - OK Computer")
        self.assertEqual(discography.file_name("2010", "TRON: Legacy?"), "2010 - TRON Legacy")
        self.assertEqual(discography.file_name("1998", "Airbag / How Am I Driving?"), "1998 - Airbag - How Am I Driving")
        self.assertEqual(discography.file_name("1998", "???"), "")

    def test_un_titre_qui_finit_comme_une_extension_garde_un_txt(self):
        self.assertEqual(discography.file_name("1999", "Vol.2"), "1999 - Vol.2.txt")
        self.assertEqual(discography.file_name("1999", "Dr. Dre"), "1999 - Dr. Dre")

    def test_le_nom_de_fichier_se_relit_comme_un_album_manquant(self):
        for titre in ("OK Computer", "Vol.2", "Dr. Dre", "Kid A"):
            with self.subTest(titre=titre):
                lu = wanted.parse(discography.file_name("1997", titre))
                self.assertEqual((lu.year, lu.title), ("1997", titre))

    def test_titres_compares_sans_accents_ni_signes(self):
        self.assertEqual(discography.title_key("OK Computer"), discography.title_key("ok-computer"))
        self.assertEqual(discography.title_key("Amnésiac"), discography.title_key("Amnesiac!"))
        self.assertNotEqual(discography.title_key("Kid A"), discography.title_key("Kid B"))


class TestPlan(unittest.TestCase):
    def test_albums_par_annee(self):
        planned, undated = discography.plan(DISCOGRAPHIE, {"album"})
        self.assertEqual({c: titres(r) for c, r in planned.items()}, {"album": [("1993", "Pablo Honey"), ("1995", "The Bends"), ("1997", "OK Computer"), ("2000", "Kid A")]})
        self.assertEqual(planned["album"][2].group, "rg-okcomputer")
        self.assertEqual(undated, 1)

    def test_categories_demandees(self):
        planned, _ = discography.plan(DISCOGRAPHIE, {"ep", "single", "live"})
        self.assertEqual(sorted(planned), ["ep", "live", "single"])

    def test_meme_titre_la_meme_annee_une_seule_fois(self):
        planned, _ = discography.plan([groupe("Hail to the Thief", "2003"), groupe("Hail To The Thief", "2003-06-09")], {"album"})
        self.assertEqual(len(planned["album"]), 1)

    def test_meme_titre_deux_annees_deux_fichiers(self):
        planned, _ = discography.plan([groupe("Greatest Hits", "1990"), groupe("Greatest Hits", "2000")], {"album"})
        self.assertEqual([r.year for r in planned["album"]], ["1990", "2000"])


class TestArtiste(unittest.TestCase):
    def test_le_nom_exact_l_emporte(self):
        resultats = [{"id": "1", "name": "Muse", "score": 100}, {"id": "2", "name": "Muse Quarter", "score": 90}]
        self.assertEqual([a["id"] for a in discography.candidates(resultats, "muse")], ["1"])

    def test_sans_nom_exact_tous_les_assez_pertinents(self):
        resultats = [{"id": "1", "name": "Muse (band)", "score": 85}, {"id": "2", "name": "Muse X", "score": 80}, {"id": "3", "name": "Autre", "score": 40}]
        self.assertEqual([a["id"] for a in discography.candidates(resultats, "muse")], ["1", "2"])

    def test_descriptif(self):
        artiste = {"name": "Radiohead", "disambiguation": "rock band", "type": "Group", "country": "GB", "life-span": {"begin": "1985-01-01"}}
        self.assertEqual(discography.describe(artiste), "Radiohead (rock band) - Group, GB, depuis 1985")
        self.assertEqual(discography.describe({"name": "X"}), "X")


class DisqueTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.racine = Path(self._tmp.name)

    def album(self, *chemin, artiste="Radiohead", mbid=""):
        dossier = self.racine.joinpath(*chemin)
        extra = (f"MUSICBRAINZ_ALBUMARTISTID={mbid}",) if mbid else ()
        piste(dossier, "01.flac", artist=artiste, extra=extra)
        return dossier

    def vide(self, *chemin):
        fichier = self.racine.joinpath(*chemin)
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text("", encoding="utf-8")


class TestInventaire(DisqueTestCase):
    def test_dossier_inexistant_ou_vide(self):
        self.assertEqual(discography.inventory(self.racine / "Absent").have, set())
        (self.racine / "Vide").mkdir()
        self.assertEqual(discography.inventory(self.racine / "Vide").have, set())

    def test_albums_ranges_et_fichiers_deja_declares(self):
        self.album("Radiohead", "1995 - The Bends")
        self.album("Radiohead", "Radiohead - OK Computer (1997) FLAC [16bit 44.1kHz]")
        self.vide("Radiohead", "1993 - Pablo Honey.txt")
        self.vide("Radiohead", "2000 - Kid A.jpg")
        self.vide("Radiohead", "2001 - Amnesiac")
        self.vide("Radiohead", "artist.txt")
        self.vide("Radiohead", "cover.jpg")
        have = discography.inventory(self.racine / "Radiohead").have
        self.assertEqual(have, {discography.title_key(t) for t in ("The Bends", "OK Computer", "Pablo Honey", "Kid A", "Amnesiac")})

    def test_les_albums_se_rangent_la_ou_l_artiste_range_les_siens(self):
        self.album("Radiohead", "Albums", "1995 - The Bends")
        self.album("Radiohead", "Albums", "1997 - OK Computer")
        inventaire = discography.inventory(self.racine / "Radiohead")
        self.assertEqual(discography.target_folder("album", self.racine / "Radiohead", inventaire.shelves), self.racine / "Radiohead" / "Albums")

    def test_les_albums_d_un_dossier_sans_rangement_vont_dans_le_dossier_de_l_artiste(self):
        self.album("Radiohead", "1995 - The Bends")
        inventaire = discography.inventory(self.racine / "Radiohead")
        self.assertEqual(discography.target_folder("album", self.racine / "Radiohead", inventaire.shelves), self.racine / "Radiohead")

    def test_autres_categories_dans_leur_dossier(self):
        self.album("Radiohead", "1995 - The Bends")
        artiste = self.racine / "Radiohead"
        shelves = discography.inventory(artiste).shelves
        self.assertEqual(discography.target_folder("ep", artiste, shelves), artiste / "EP")
        self.album("Radiohead", "ep", "1998 - Airbag")
        shelves = discography.inventory(artiste).shelves
        self.assertEqual(discography.target_folder("ep", artiste, shelves), artiste / "ep")     # celui qui existe, quelle que soit la casse

    def test_fichiers_vides_remplacables_et_le_reste(self):
        self.vide("Radiohead", "1993 - Pablo Honey")
        self.vide("Radiohead", "1997 - OK Computer.txt")
        (self.racine / "Radiohead" / "2000 - Kid A.txt").write_text("mes notes", encoding="utf-8")
        self.vide("Radiohead", "2001 - Amnesiac.jpg")
        self.album("Radiohead", "1995 - The Bends")
        inventaire = discography.inventory(self.racine / "Radiohead")
        cle = discography.title_key
        self.assertEqual(set(inventaire.empty), {cle("Pablo Honey"), cle("OK Computer")})
        self.assertEqual(inventaire.held, {cle("Kid A"), cle("Amnesiac"), cle("The Bends")})

    def test_missing_ne_cherche_une_pochette_aux_fichiers_vides_que_sur_demande(self):
        self.album("Radiohead", "1995 - The Bends")
        self.vide("Radiohead", "1997 - OK Computer")
        artiste = self.racine / "Radiohead"
        planned, _ = discography.plan(DISCOGRAPHIE, {"album"})
        inventaire = discography.inventory(artiste)
        self.assertEqual([t.release.title for t in discography.missing(planned, inventaire, artiste)], ["Pablo Honey", "Kid A"])
        a_chercher = discography.missing(planned, inventaire, artiste, upgrade=True)
        self.assertEqual([t.release.title for t in a_chercher], ["Pablo Honey", "OK Computer", "Kid A"])
        self.assertEqual(a_chercher[1].replaces, (artiste / "1997 - OK Computer",))
        self.assertEqual(a_chercher[0].replaces, ())

    def test_nom_de_l_image(self):
        todo = discography.Todo(Path("Radiohead"), discography.Release("1997", "OK Computer", "rg"))
        self.assertEqual(todo.path, Path("Radiohead/1997 - OK Computer"))
        self.assertEqual(todo.image(".jpg"), Path("Radiohead/1997 - OK Computer.jpg"))
        self.assertEqual(wanted.parse(todo.image(".png").name).title, "OK Computer")

    def test_de_l_audio_vrac_dans_le_dossier_de_l_artiste_ne_compte_pas(self):
        piste(self.racine / "Radiohead", "01.flac", album="Pablo Honey")
        self.assertEqual(discography.inventory(self.racine / "Radiohead").have, set())


class TestIdentifiantDesFichiers(DisqueTestCase):
    def trouver(self, artiste):
        from libraries.music import album as albums
        return [a for a in albums.find_albums(self.racine / artiste) if a.files]

    def test_identifiant_lu_dans_les_pistes(self):
        self.album("Radiohead", "1995 - The Bends", mbid=RADIOHEAD)
        self.album("Radiohead", "1997 - OK Computer", mbid=RADIOHEAD)
        self.assertEqual(discography.tagged_artist_id(self.trouver("Radiohead")), RADIOHEAD)

    def test_sans_identifiant(self):
        self.album("Radiohead", "1995 - The Bends")
        self.assertEqual(discography.tagged_artist_id(self.trouver("Radiohead")), "")

    def test_plusieurs_artistes_credites_ne_disent_rien(self):
        self.album("Radiohead", "1995 - The Bends", mbid=f"{RADIOHEAD};b95ce3ff-3d05-4e87-9e01-c97b66af13d4")
        self.assertEqual(discography.tagged_artist_id(self.trouver("Radiohead")), "")

    def test_un_identifiant_qui_n_en_est_pas_un_est_ignore(self):
        self.album("Radiohead", "1995 - The Bends", mbid="pas-un-uuid")
        self.assertEqual(discography.tagged_artist_id(self.trouver("Radiohead")), "")


class FauxArtistes:
    """MusicBrainz qui connaît des artistes (nom -> résultats de recherche) et leurs discographies (id -> groupes)."""

    def __init__(self, artistes=None, groupes=None, panne=None, covers=None, cover_panne=None):
        self.covers = covers or {}                 # id de release group -> octets de sa pochette
        self.cover_panne, self.demandes = cover_panne, []
        self.artistes = artistes or {}
        self.groupes = groupes if groupes is not None else {RADIOHEAD: DISCOGRAPHIE}
        self.panne = panne
        self.recherches, self.discographies = [], []

    def search_artists(self, name, limit=10):
        self.recherches.append(name)
        if self.panne:
            raise self.panne
        return self.artistes.get(name, [])

    def cover(self, release_id, release_group_id=None, size="1200"):
        self.demandes.append((release_id, release_group_id, size))
        if self.cover_panne:
            raise self.cover_panne
        return self.covers.get(release_group_id)

    def artist_release_groups(self, mbid):
        self.discographies.append(mbid)
        if self.panne:
            raise self.panne
        return self.groupes.get(mbid, [])


def radiohead(score=100):
    return {"id": RADIOHEAD, "name": "Radiohead", "score": score, "type": "Group", "country": "GB"}


class ProgrammeTestCase(DisqueTestCase):
    def lancer(self, mb, *argv, can_ask=False, answers=()):
        """(code de sortie, affichage)."""
        ligne = [str(Path(script.__file__)), "--dir", str(self.racine), *argv]
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, "argv", ligne))
            stack.enter_context(mock.patch.object(script, "MusicBrainz", return_value=mb))
            stack.enter_context(mock.patch.object(script.cache, "Cache"))
            stack.enter_context(mock.patch.object(cli, "can_ask", lambda: can_ask))
            self.questions = stack.enter_context(mock.patch.object(cli, "ask_choice", side_effect=list(answers)))
            texte = stack.enter_context(redirect_stdout(io.StringIO()))
            code = script.main()
        self.affichage = texte.getvalue()
        return code, self.affichage

    def noms(self, *chemin):
        dossier = self.racine.joinpath(*chemin)
        return sorted(p.name for p in dossier.iterdir()) if dossier.is_dir() else []


class TestDiscographieDeBoutEnBout(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        self.album("Radiohead", "1995 - The Bends", mbid=RADIOHEAD)

    def test_simulation_n_ecrit_rien(self):
        code, texte = self.lancer(FauxArtistes())
        self.assertEqual(code, 0)
        self.assertEqual(self.noms("Radiohead"), ["1995 - The Bends"])
        self.assertIn("+ Radiohead", texte)
        self.assertIn("3 fichier(s) à poser", texte)
        self.assertIn("SIMULATION", texte)

    def test_pose_les_albums_qui_manquent(self):
        code, texte = self.lancer(FauxArtistes(), "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(self.noms("Radiohead"), ["1993 - Pablo Honey", "1995 - The Bends", "1997 - OK Computer", "2000 - Kid A"])
        self.assertIn("id lu dans les fichiers", texte)
        self.assertIn("1 sortie(s) sans année", texte)

    def test_un_deuxieme_passage_n_a_plus_rien_a_poser(self):
        self.lancer(FauxArtistes(), "--apply")
        avant = self.noms("Radiohead")
        code, texte = self.lancer(FauxArtistes(), "--apply")
        self.assertEqual((code, self.noms("Radiohead")), (0, avant))
        self.assertIn("à jour", texte)
        self.assertIn("0 fichier(s) posé(s)", texte)

    def test_le_contenu_d_un_fichier_existant_n_est_jamais_touche(self):
        self.vide("Radiohead", "1997 - OK Computer.txt")
        (self.racine / "Radiohead" / "1997 - OK Computer.txt").write_text("à garder", encoding="utf-8")
        self.lancer(FauxArtistes(), "--apply")
        self.assertEqual((self.racine / "Radiohead" / "1997 - OK Computer.txt").read_text(encoding="utf-8"), "à garder")

    def test_un_fichier_sans_extension_ou_en_txt_declare_deja_l_album(self):
        self.vide("Radiohead", "1997 - OK Computer")
        self.vide("Radiohead", "2000 - Kid A.txt")
        self.lancer(FauxArtistes(), "--apply")
        self.assertEqual(self.noms("Radiohead"), ["1993 - Pablo Honey", "1995 - The Bends", "1997 - OK Computer", "2000 - Kid A.txt"])

    def test_une_image_declare_deja_l_album(self):
        self.vide("Radiohead", "1997 - OK Computer.jpg")
        self.lancer(FauxArtistes(), "--apply")
        self.assertNotIn("1997 - OK Computer", self.noms("Radiohead"))
        self.assertEqual(self.noms("Radiohead").count("1997 - OK Computer.jpg"), 1)

    def test_autres_categories_dans_un_sous_dossier(self):
        self.lancer(FauxArtistes(), "--cats", "ep,single", "--apply")
        self.assertEqual(self.noms("Radiohead", "EP"), ["1998 - Airbag - How Am I Driving"])
        self.assertEqual(self.noms("Radiohead", "Singles"), ["1992 - Creep"])
        self.assertNotIn("1997 - OK Computer", self.noms("Radiohead"))

    def test_all_prend_toutes_les_categories(self):
        self.lancer(FauxArtistes(), "--cats", "all", "--apply")
        self.assertEqual(self.noms("Radiohead", "Live"), ["2001 - I Might Be Wrong"])

    def test_albums_ranges_dans_un_sous_dossier(self):
        (self.racine / "Radiohead" / "1995 - The Bends").rename(self.racine / "Radiohead" / "tmp")
        (self.racine / "Radiohead" / "Albums").mkdir()
        (self.racine / "Radiohead" / "tmp").rename(self.racine / "Radiohead" / "Albums" / "1995 - The Bends")
        self.lancer(FauxArtistes(), "--apply")
        self.assertEqual(self.noms("Radiohead", "Albums"), ["1993 - Pablo Honey", "1995 - The Bends", "1997 - OK Computer", "2000 - Kid A"])

    def test_dossiers_ignores(self):
        for nom in (".cache", "__Data__", "#recycle", "@eaDir"):
            (self.racine / nom).mkdir()
        mb = FauxArtistes()
        self.lancer(mb, "--apply")
        self.assertEqual(mb.recherches, [])
        self.assertEqual(mb.discographies, [RADIOHEAD])


class TestPochettes(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        self.album("Radiohead", "1995 - The Bends", mbid=RADIOHEAD)
        self.covers = {"rg-pablohoney": JPEG, "rg-okcomputer": PNG, "rg-kida": JPEG}

    def test_l_image_remplace_le_fichier_vide(self):
        mb = FauxArtistes(covers=self.covers)
        code, texte = self.lancer(mb, "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(self.noms("Radiohead"), ["1993 - Pablo Honey.jpg", "1995 - The Bends", "1997 - OK Computer.png", "2000 - Kid A.jpg"])
        self.assertEqual((self.racine / "Radiohead" / "1993 - Pablo Honey.jpg").read_bytes(), JPEG)
        self.assertIn("3 fichier(s) posé(s), dont 3 avec pochette", texte)

    def test_sans_pochette_le_fichier_vide_reste(self):
        mb = FauxArtistes(covers={"rg-pablohoney": JPEG})
        self.lancer(mb, "--apply")
        self.assertEqual(self.noms("Radiohead"), ["1993 - Pablo Honey.jpg", "1995 - The Bends", "1997 - OK Computer", "2000 - Kid A"])
        self.assertEqual((self.racine / "Radiohead" / "1997 - OK Computer").stat().st_size, 0)

    def test_la_pochette_se_demande_au_release_group_a_la_taille_choisie(self):
        mb = FauxArtistes(covers=self.covers)
        self.lancer(mb, "--apply", "--image-size", "500")
        self.assertEqual(mb.demandes[0], (None, "rg-pablohoney", "500"))
        self.assertEqual({d[2] for d in mb.demandes}, {"500"})

    def test_par_defaut_1200(self):
        mb = FauxArtistes(covers=self.covers)
        self.lancer(mb, "--apply")
        self.assertEqual({d[2] for d in mb.demandes}, {"1200"})

    def test_sans_pochettes_aucune_demande(self):
        mb = FauxArtistes(covers=self.covers)
        self.lancer(mb, "--apply", "--no-covers")
        self.assertEqual(mb.demandes, [])
        self.assertEqual(self.noms("Radiohead"), ["1993 - Pablo Honey", "1995 - The Bends", "1997 - OK Computer", "2000 - Kid A"])

    def test_la_simulation_ne_telecharge_rien(self):
        mb = FauxArtistes(covers=self.covers)
        code, texte = self.lancer(mb)
        self.assertEqual((code, mb.demandes), (0, []))
        self.assertIn("(pochette si disponible)", texte)
        self.assertEqual(self.noms("Radiohead"), ["1995 - The Bends"])

    def test_un_fichier_vide_deja_pose_est_remplace_par_la_pochette(self):
        self.vide("Radiohead", "1997 - OK Computer")
        self.vide("Radiohead", "2000 - Kid A.txt")
        self.lancer(FauxArtistes(covers=self.covers), "--apply")
        self.assertEqual(self.noms("Radiohead"), ["1993 - Pablo Honey.jpg", "1995 - The Bends", "1997 - OK Computer.png", "2000 - Kid A.jpg"])

    def test_un_fichier_vide_sans_pochette_reste_et_n_est_pas_compte(self):
        self.vide("Radiohead", "1997 - OK Computer")
        mb = FauxArtistes(covers={})
        code, texte = self.lancer(mb, "--apply")
        self.assertEqual(code, 0)
        self.assertIn("1 album(s) déjà déclaré(s) par un fichier vide, sans pochette", texte)
        self.assertIn("2 fichier(s) posé(s) pour", texte)
        self.assertIn("1997 - OK Computer", self.noms("Radiohead"))

    def test_un_fichier_vide_est_remplace_une_fois_pour_toutes(self):
        self.vide("Radiohead", "1997 - OK Computer")
        mb = FauxArtistes(covers=self.covers)
        self.lancer(mb, "--apply")
        mb.demandes.clear()
        self.lancer(mb, "--apply")
        self.assertEqual(mb.demandes, [])

    def test_ce_qui_n_est_pas_un_fichier_vide_n_est_jamais_remplace(self):
        (self.racine / "Radiohead" / "1997 - OK Computer.txt").write_text("mes notes", encoding="utf-8")
        (self.racine / "Radiohead" / "1993 - Pablo Honey.png").write_bytes(b"a moi")
        mb = FauxArtistes(covers=self.covers)
        self.lancer(mb, "--apply")
        self.assertEqual((self.racine / "Radiohead" / "1997 - OK Computer.txt").read_text(encoding="utf-8"), "mes notes")
        self.assertEqual((self.racine / "Radiohead" / "1993 - Pablo Honey.png").read_bytes(), b"a moi")
        self.assertEqual(self.noms("Radiohead"), ["1993 - Pablo Honey.png", "1995 - The Bends", "1997 - OK Computer.txt", "2000 - Kid A.jpg"])

    def test_panne_du_service_de_pochettes_laisse_le_fichier_vide(self):
        mb = FauxArtistes(covers=self.covers, cover_panne=MusicBrainzError("coupure"))
        code, texte = self.lancer(mb, "--apply")
        self.assertEqual(code, 0)
        self.assertIn("pochette indisponible : coupure", texte)
        self.assertEqual(self.noms("Radiohead"), ["1993 - Pablo Honey", "1995 - The Bends", "1997 - OK Computer", "2000 - Kid A"])

    def test_une_image_d_un_autre_format_est_ignoree(self):
        mb = FauxArtistes(covers={"rg-pablohoney": b"GIF89a....", "rg-okcomputer": JPEG})
        self.lancer(mb, "--apply")
        self.assertIn("1993 - Pablo Honey", self.noms("Radiohead"))
        self.assertIn("1997 - OK Computer.jpg", self.noms("Radiohead"))

    def test_ecriture_de_l_image_impossible(self):
        with mock.patch.object(script, "open", create=True, side_effect=PermissionError(13, "Accès refusé")):
            code, texte = self.lancer(FauxArtistes(covers=self.covers), "--apply")
        self.assertEqual(code, 1)
        self.assertIn("[ÉCHEC]", texte)

    def test_autres_categories_aussi(self):
        mb = FauxArtistes(covers={"rg-creep": PNG})
        self.lancer(mb, "--cats", "single", "--apply")
        self.assertEqual(self.noms("Radiohead", "Singles"), ["1992 - Creep.png"])


class TestRechercheParLeNom(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        (self.racine / "Radiohead").mkdir()

    def test_un_seul_artiste_de_ce_nom(self):
        mb = FauxArtistes({"Radiohead": [radiohead()]})
        code, texte = self.lancer(mb, "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(mb.recherches, ["Radiohead"])
        self.assertEqual(len(self.noms("Radiohead")), 4)
        self.assertIn("recherche : Radiohead - Group, GB", texte)

    def test_artist_txt_remplace_le_nom_du_dossier(self):
        (self.racine / "Radiohead" / "artist.txt").write_text("Radiohead\n", encoding="utf-8")
        (self.racine / "Radiohead").rename(self.racine / "Thom et les autres")
        mb = FauxArtistes({"Radiohead": [radiohead()]})
        self.lancer(mb)
        self.assertEqual(mb.recherches, ["Radiohead"])

    def test_artiste_introuvable(self):
        code, texte = self.lancer(FauxArtistes())
        self.assertEqual(code, 1)
        self.assertIn("[NON ASSOCIÉ]", texte)
        self.assertIn("1 sans fiche", texte)

    def test_plusieurs_artistes_question_en_fin_de_passage(self):
        autre = dict(radiohead(), id="autre-id", disambiguation="tribute")
        mb = FauxArtistes({"Radiohead": [autre, radiohead()]}, {"autre-id": [], RADIOHEAD: DISCOGRAPHIE})
        code, texte = self.lancer(mb, "--apply", can_ask=True, answers=[1])
        self.assertEqual(code, 0)
        self.assertIn("question en fin de passage", texte)
        self.assertEqual(mb.discographies, [RADIOHEAD])
        self.assertEqual(len(self.noms("Radiohead")), 4)

    def test_question_sans_reponse_en_terminal_non_interactif(self):
        mb = FauxArtistes({"Radiohead": [radiohead(), dict(radiohead(), id="autre-id")]})
        code, texte = self.lancer(mb, "--apply", can_ask=False)
        self.assertEqual(code, 1)
        self.assertEqual(self.noms("Radiohead"), [])
        self.assertIn("[À CONFIRMER] Radiohead", texte)
        self.assertIn("association(s) à confirmer", texte)

    def test_artiste_laisse_de_cote(self):
        mb = FauxArtistes({"Radiohead": [radiohead(), dict(radiohead(), id="autre-id")]})
        code, _ = self.lancer(mb, "--apply", can_ask=True, answers=[cli.ASK_SKIP])
        self.assertEqual((code, self.noms("Radiohead")), (1, []))

    def test_no_ask_garde_le_premier(self):
        mb = FauxArtistes({"Radiohead": [radiohead(), dict(radiohead(), id="autre-id")]})
        code, _ = self.lancer(mb, "--no-ask", "--apply")
        self.assertEqual((code, mb.discographies), (0, [RADIOHEAD]))
        self.assertEqual(self.questions.call_count, 0)


class TestPannes(ProgrammeTestCase):
    def test_musicbrainz_injoignable_sort_en_code_1(self):
        (self.racine / "Radiohead").mkdir()
        code, texte = self.lancer(FauxArtistes(panne=MusicBrainzError("coupure")), "--apply")
        self.assertEqual(code, 1)
        self.assertIn("échec MusicBrainz : coupure", texte)

    def test_trois_erreurs_de_suite_arretent_le_passage(self):
        for nom in "ABCDE":
            (self.racine / nom).mkdir()
        mb = FauxArtistes(panne=MusicBrainzError("coupure"))
        code, texte = self.lancer(mb)
        self.assertEqual((code, len(mb.recherches)), (1, 3))
        self.assertIn("2 artiste(s) non vu(s)", texte)

    def test_artiste_sans_sortie(self):
        self.album("Radiohead", "1995 - The Bends", mbid=RADIOHEAD)
        code, texte = self.lancer(FauxArtistes(groupes={RADIOHEAD: []}))
        self.assertEqual(code, 1)
        self.assertIn("aucune sortie référencée", texte)

    def test_ecriture_impossible(self):
        self.album("Radiohead", "1995 - The Bends", mbid=RADIOHEAD)
        with mock.patch.object(Path, "touch", side_effect=PermissionError(13, "Accès refusé")):
            code, texte = self.lancer(FauxArtistes(), "--apply")
        self.assertEqual(code, 1)
        self.assertIn("[ÉCHEC]", texte)
        self.assertIn("écriture(s) en échec", texte)


class TestUnSeulArtiste(ProgrammeTestCase):
    def test_cree_le_dossier_sous_le_nom_de_musicbrainz(self):
        mb = FauxArtistes({"radiohead": [radiohead()]})
        code, texte = self.lancer(mb, "--only", "radiohead", "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(self.noms(), ["Radiohead"])
        self.assertEqual(self.noms("Radiohead"), ["1993 - Pablo Honey", "1995 - The Bends", "1997 - OK Computer", "2000 - Kid A"])
        self.assertIn("dossier de l'artiste", texte)

    def test_simulation_ne_cree_pas_le_dossier(self):
        self.lancer(FauxArtistes({"Radiohead": [radiohead()]}), "--only", "Radiohead")
        self.assertEqual(self.noms(), [])

    def test_dossier_cree_meme_sans_aucune_sortie_de_la_categorie(self):
        mb = FauxArtistes({"Radiohead": [radiohead()]}, {RADIOHEAD: [groupe("Creep", "1992", "Single")]})
        self.lancer(mb, "--only", "Radiohead", "--apply")
        self.assertEqual(self.noms(), ["Radiohead"])

    def test_dossier_existant_complete_sans_etre_recree(self):
        self.album("Radiohead", "1995 - The Bends", mbid=RADIOHEAD)
        (self.racine / "Autre").mkdir()
        mb = FauxArtistes()
        self.lancer(mb, "--only", "radiohead", "--apply")
        self.assertEqual(self.noms(), ["Autre", "Radiohead"])
        self.assertEqual(mb.recherches, [])
        self.assertEqual(self.noms("Autre"), [])
        self.assertEqual(len(self.noms("Radiohead")), 4)


class TestLigneDeCommande(unittest.TestCase):
    def analyser(self, *argv):
        with mock.patch.object(sys, "argv", ["Discography.py", *argv]), redirect_stdout(io.StringIO()):
            return script.parse_args()

    def test_albums_par_defaut(self):
        self.assertEqual(self.analyser("--dir", "x").cats, {"album"})

    def test_categories_separees_par_des_virgules(self):
        self.assertEqual(self.analyser("--dir", "x", "--cats", "Album, EP").cats, {"album", "ep"})

    def test_all(self):
        self.assertEqual(self.analyser("--dir", "x", "--cats", "all").cats, set(discography.CATEGORIES))

    def test_categorie_inconnue(self):
        with self.assertRaises(SystemExit), mock.patch.object(sys, "stderr", io.StringIO()):
            self.analyser("--dir", "x", "--cats", "album,bidule")

    def test_dossier_introuvable(self):
        with mock.patch.object(sys, "argv", ["Discography.py", "--dir", "/nulle/part/du/tout"]), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as sortie:
                script.main()
        self.assertIn("introuvable", sortie.exception.code)


if __name__ == "__main__":
    unittest.main()
