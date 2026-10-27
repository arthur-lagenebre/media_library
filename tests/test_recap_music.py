"""Déroulement complet de Music/Recap.py : ce que produit une invocation sur une petite médiathèque."""

import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common import thumbs
from libraries.music import artistinfo, flac
from libraries.music.musicbrainz import MusicBrainzError
from scripts.Music import Recap as recap
from tests import test_mp3
from tests.test_books_readers import png
from tests.test_flac import fichier, image
from tests.test_artistinfo import EN, FR, WIKIDATA, ClientFactice, groupe, resume
from tests.test_library import ARTISTE, MBID, piste

SITELINKS = {"entities": {"Q185": {"sitelinks": {"frwiki": {"title": "Daft Punk"}, "enwiki": {"title": "Daft Punk"}}}}}


class TestRecapMusique(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        for n in (1, 2, 4):
            piste(self.racine / "Daft Punk" / "Discovery", f"{n:02d}.flac", number=n, total=4, title=f"Titre {n}", mbid=MBID, cover=n == 1)
        piste(self.racine / "Daft Punk" / "Homework", "01.flac", album="Homework", date="1997", mbid=MBID.replace("4e", "5f"))
        piste(self.racine / "Kavinsky" / "Outrun", "01.flac", artist="Kavinsky", album="Outrun", date="2013")        # pas encore étiqueté
        (self.racine / "Kavinsky" / "Outrun" / "02.m4a").write_bytes(b"x")
        piste(self.racine / "__Data__" / "Ancien", "01.flac")                                                    # nos propres pages : ignoré
        self.data = self.racine / "__Data__"
        # Jamais de vrai réseau : sans réponse préparée, le client factice dit qu'il n'a rien trouvé.
        self.reseau = ClientFactice({})
        patch = mock.patch.object(recap, "MusicBrainz", lambda *a, **k: self.reseau)
        patch.start()
        self.addCleanup(patch.stop)

    def etiqueter_daft_punk(self):
        for n in (1, 2, 4):
            piste(self.racine / "Daft Punk" / "Discovery", f"{n:02d}.flac", number=n, total=4, title=f"Titre {n}", mbid=MBID, extra=(f"MUSICBRAINZ_ALBUMARTISTID={ARTISTE}",))
        self.reseau.reponses.update({f"artist/{ARTISTE}": groupe(), WIKIDATA: SITELINKS, FR: resume()})

    def fiche_daft_punk(self):
        return next((self.data / "Artistes").glob("Daft Punk-*.html")).read_text(encoding="utf-8")

    def lancer(self, *options):
        sortie = io.StringIO()
        with mock.patch.object(sys, "argv", ["Recap.py", "--dir", str(self.racine), *options]), redirect_stdout(sortie):
            code = recap.main()
        return code, sortie.getvalue()

    def test_simulation_n_ecrit_ni_fiche_ni_journal_sans_dossier(self):
        shutil.rmtree(self.data)
        code, sortie = self.lancer()
        self.assertEqual(code, 0)
        self.assertFalse(self.data.exists())
        self.assertIn("SIMULATION", sortie)
        self.assertIn("écrirait", sortie)

    def test_simulation_n_ecrit_que_le_journal_quand_le_dossier_existe(self):
        self.lancer()
        self.assertEqual(sorted(p.name for p in self.data.iterdir() if p.is_file()), ["recap.log"])
        self.assertFalse((self.data / "music.html").exists())

    def test_bilan(self):
        _, sortie = self.lancer()
        self.assertIn("3 album(s), 2 artiste(s), 5 piste(s), 4 étiquetée(s)", sortie)
        self.assertIn("TOTAL : 4/5 piste(s) étiquetée(s) par MusicBrainz.", sortie)
        self.assertNotIn("Ancien", sortie)

    def test_application_ecrit_un_seul_fichier_pour_le_sommaire_et_le_lecteur(self):
        code, _ = self.lancer("--apply")
        self.assertEqual(code, 0)
        self.assertEqual(sorted(p.name for p in self.data.iterdir() if p.is_file()), ["catalog.json", "music.html", "recap.log"])
        self.assertEqual(len(list((self.data / "Albums").glob("*.html"))), 3)
        index = (self.data / "music.html").read_text(encoding="utf-8")
        self.assertIn("<title>Musique</title>", index)
        self.assertEqual(len(re.findall(r"href='Albums/", index)), 3)
        self.assertEqual(index.count("<audio"), 1)                  # le sommaire est aussi le lecteur
        self.assertFalse((self.data / "index.html").exists())
        self.assertFalse((self.data / "lecteur.html").exists())

    def test_une_fiche_par_artiste_et_des_liens_qui_y_mennent(self):
        self.lancer("--apply")
        fiches = sorted(p.name for p in (self.data / "Artistes").glob("*.html"))
        self.assertEqual([n.rsplit("-", 1)[0] for n in fiches], ["Daft Punk", "Kavinsky"])
        index = (self.data / "music.html").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"href='Artistes/", index)), 2)
        album = next((self.data / "Albums").glob("Daft Punk - Discovery-*.html")).read_text(encoding="utf-8")
        self.assertIn("<a href='../Artistes/Daft%20Punk-", album)
        artiste = next((self.data / "Artistes").glob("Daft Punk-*.html")).read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"href='\.\./Albums/", artiste)), 2)

    def test_lien_musicbrainz_de_l_artiste_lu_dans_les_tags(self):
        self.etiqueter_daft_punk()
        self.lancer("--apply", "--no-artist-info")
        daft = next((self.data / "Artistes").glob("Daft Punk-*.html")).read_text(encoding="utf-8")
        kavinsky = next((self.data / "Artistes").glob("Kavinsky-*.html")).read_text(encoding="utf-8")
        self.assertIn(f"https://musicbrainz.org/artist/{ARTISTE}", daft)
        self.assertNotIn("musicbrainz.org", kavinsky)

    def test_fiche_d_artiste_complete_par_musicbrainz_et_wikipedia(self):
        self.etiqueter_daft_punk()
        _, sortie = self.lancer("--apply")
        daft = self.fiche_daft_punk()
        self.assertIn("1 fiche(s) obtenue(s) sur 1", sortie)
        self.assertIn("<div class='kind'>Groupe · France · depuis 1993</div>", daft)
        self.assertIn("French electronic duo", daft)
        self.assertIn("Daft Punk est un duo français.", daft)
        self.assertIn("Source : Wikipédia (fr)", daft)
        self.assertIn("https://www.daftpunk.com/", daft)
        self.assertIn("Site officiel", daft)
        self.assertIn("<summary>Membres<", daft)
        self.assertIn("<summary>Anciens membres<", daft)
        self.assertLess(daft.index("Thomas Bangalter"), daft.index("Guy-Manuel"))
        self.assertEqual(self.reseau.appels, [f"artist/{ARTISTE}", WIKIDATA, FR])

    def test_les_artistes_sans_identifiant_ne_coutent_aucune_requete(self):
        self.lancer("--apply")
        self.assertEqual(self.reseau.appels, [])
        self.assertFalse((self.data / "artists.json").exists())

    def test_reponses_gardees_le_passage_suivant_ne_demande_rien(self):
        self.etiqueter_daft_punk()
        self.lancer("--apply")
        avant = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in self.data.rglob("*") if p.is_file() and p.name != "recap.log"}
        self.reseau.appels.clear()
        _, sortie = self.lancer("--apply")
        self.assertEqual(self.reseau.appels, [])
        self.assertNotIn("à demander", sortie)
        self.assertEqual({p: (p.stat().st_mtime_ns, p.read_bytes()) for p in avant}, avant)

    def test_reponses_perimees_redemandees(self):
        self.etiqueter_daft_punk()
        self.lancer("--apply")
        gardees = artistinfo.load(self.data / "artists.json")
        gardees[ARTISTE]["fetched"] = "2020-01-01"
        (self.data / "artists.json").write_text(artistinfo.dump(gardees), encoding="utf-8")
        self.reseau.appels.clear()
        self.lancer("--apply")
        self.assertEqual(self.reseau.appels[0], f"artist/{ARTISTE}")
        self.assertNotEqual(artistinfo.load(self.data / "artists.json")[ARTISTE]["fetched"], "2020-01-01")

    def test_no_cache_redemande_tout(self):
        self.etiqueter_daft_punk()
        self.lancer("--apply")
        self.reseau.appels.clear()
        self.lancer("--apply", "--no-cache")
        self.assertEqual(self.reseau.appels[0], f"artist/{ARTISTE}")

    def test_no_artist_info_n_interroge_personne_mais_garde_ce_qu_on_savait(self):
        self.etiqueter_daft_punk()
        self.lancer("--apply")
        self.reseau.appels.clear()
        self.lancer("--apply", "--no-artist-info", "--no-cache")
        self.assertEqual(self.reseau.appels, [])
        self.assertIn("Daft Punk est un duo français.", self.fiche_daft_punk())

    def test_simulation_n_interroge_personne(self):
        self.etiqueter_daft_punk()
        _, sortie = self.lancer()
        self.assertEqual(self.reseau.appels, [])
        self.assertIn("interrogerait MusicBrainz et Wikipédia sur 1 artiste(s)", sortie)

    def test_panne_du_reseau_n_efface_rien_et_n_arrete_pas_le_passage(self):
        self.etiqueter_daft_punk()
        self.lancer("--apply")
        self.reseau.reponses[f"artist/{ARTISTE}"] = MusicBrainzError("coupure")
        _, sortie = self.lancer("--apply", "--no-cache")
        self.assertIn("Daft Punk : coupure", sortie)
        self.assertIn("Daft Punk est un duo français.", self.fiche_daft_punk())

    def test_abandon_apres_trois_echecs_d_affilee(self):
        for n in range(5):
            piste(self.racine / f"Groupe {n}" / "Album", "01.flac", artist=f"Groupe {n}", album="Album", extra=(f"MUSICBRAINZ_ALBUMARTISTID=00000000-0000-0000-0000-00000000000{n}",))
            self.reseau.reponses[f"artist/00000000-0000-0000-0000-00000000000{n}"] = MusicBrainzError("coupure")
        _, sortie = self.lancer("--apply")
        self.assertEqual(len(self.reseau.appels), 3)
        self.assertIn("3 échecs d'affilée : abandon", sortie)
        self.assertTrue((self.data / "Artistes").is_dir())

    def test_fiche_disparue_notee_pour_ne_pas_etre_redemandee(self):
        self.etiqueter_daft_punk()
        del self.reseau.reponses[f"artist/{ARTISTE}"]
        self.lancer("--apply")
        self.assertEqual(artistinfo.load(self.data / "artists.json")[ARTISTE]["info"], {})
        self.reseau.appels.clear()
        self.lancer("--apply")
        self.assertEqual(self.reseau.appels, [])
        self.assertIn(f"https://musicbrainz.org/artist/{ARTISTE}", self.fiche_daft_punk())

    def test_artiste_inconnu_sans_fiche(self):
        piste(self.racine / "Mystere", "01.flac", artist="", albumartist=False, album="Mystere")
        self.lancer("--apply")
        self.assertEqual(sorted(p.name.rsplit("-", 1)[0] for p in (self.data / "Artistes").glob("*.html")), ["Daft Punk", "Kavinsky"])
        index = (self.data / "music.html").read_text(encoding="utf-8")
        self.assertIn("<h2 data-i='A'>Artiste inconnu<span", index)          # sa section, sans lien : il n'a pas de fiche

    def test_aucune_ecriture_dans_la_musique(self):
        avant = {p: p.read_bytes() for p in self.racine.rglob("*") if p.is_file() and "__Data__" not in p.parts}
        self.lancer("--apply")
        self.assertEqual({p: p.read_bytes() for p in avant}, avant)

    def test_albums_manquants_sur_la_fiche_de_l_artiste_et_dans_le_journal(self):
        (self.racine / "Daft Punk" / "2005 - Human After All.txt").write_text("", encoding="utf-8")
        (self.racine / "Daft Punk" / "1997 - Homework.txt").write_text("", encoding="utf-8")       # possédé : ni montré ni signalé
        code, sortie = self.lancer("--apply")
        self.assertEqual(code, 0)
        self.assertIn("1 album(s) manquant(s) chez 1 artiste(s)", sortie)
        journal = (self.data / "recap.log").read_text(encoding="utf-8")
        self.assertIn("[ABSENT] Daft Punk : 2005 - Human After All", journal)
        self.assertNotIn("[ABSENT] Daft Punk : 1997", journal)
        fiche, = (self.data / "Artistes").glob("Daft Punk-*.html")
        html = fiche.read_text(encoding="utf-8")
        self.assertIn("<div class='al gone'>", html)
        self.assertIn("Human After All", html)
        self.assertEqual(html.count("<div class='al gone'>"), 1)

    def test_journal(self):
        self.lancer("--apply")
        journal = (self.data / "recap.log").read_text(encoding="utf-8")
        self.assertIn("[NON ÉTIQUETÉ] Kavinsky/Outrun (0/1)", journal)
        self.assertIn("[MANQUE] Daft Punk/Discovery : disque 1, piste(s) 3 (sur 4)", journal)
        self.assertIn("[NON PRIS EN CHARGE] Kavinsky/Outrun : 02.m4a", journal)
        self.assertNotIn("Homework", journal)

    def test_titre_choisi_survit_aux_passages_suivants(self):
        self.lancer("--apply", "--title", "Ma musique")
        self.lancer("--apply")
        self.assertIn("<title>Ma musique</title>", (self.data / "music.html").read_text(encoding="utf-8"))

    def test_titre_repris_d_un_ancien_sommaire_ou_d_un_ancien_lecteur(self):
        for ancien in ("musique.html", "index.html", "lecteur.html"):
            with self.subTest(ancien):
                (self.data / "music.html").unlink(missing_ok=True)
                (self.data / "index.html").unlink(missing_ok=True)
                (self.data / "musique.html").unlink(missing_ok=True)
                (self.data / "lecteur.html").unlink(missing_ok=True)
                (self.data / ancien).write_text("<html><head><title>Ma discothèque</title></head></html>", encoding="utf-8")
                self.lancer("--apply")
                self.assertIn("<title>Ma discothèque</title>", (self.data / "music.html").read_text(encoding="utf-8"))
                self.assertTrue((self.data / ancien).exists())          # jamais effacé

    def test_sortie_ailleurs(self):
        ailleurs = self.racine.parent / (self.racine.name + "-out")
        self.addCleanup(shutil.rmtree, ailleurs, ignore_errors=True)
        self.lancer("--apply", "--out", str(ailleurs))
        self.assertTrue((ailleurs / "music.html").exists())
        self.assertFalse((self.data / "music.html").exists())

    def test_les_fiches_d_album_jouent_les_pistes_depuis_la_racine(self):
        self.lancer("--apply")
        fiche = next((self.data / "Albums").glob("Daft Punk - Discovery-*.html")).read_text(encoding="utf-8")
        self.assertIn("data-src='../../Daft%20Punk/Discovery/01.flac'", fiche)
        # Le lien tient : depuis le dossier des fiches, il retombe sur le fichier.
        self.assertTrue((self.data / "Albums" / "../../Daft Punk/Discovery/01.flac").exists())

    def test_les_liens_suivent_une_sortie_ailleurs(self):
        ailleurs = self.racine.parent / (self.racine.name + "-out")
        self.addCleanup(shutil.rmtree, ailleurs, ignore_errors=True)
        self.lancer("--apply", "--out", str(ailleurs))
        fiche = next((ailleurs / "Albums").glob("Daft Punk - Discovery-*.html")).read_text(encoding="utf-8")
        lien = re.search(r"data-src='([^']+)'", fiche).group(1)
        self.assertTrue((ailleurs / "Albums" / lien.replace("%20", " ")).resolve().exists())

    def test_le_sommaire_lit_les_pistes_depuis_la_racine(self):
        self.lancer("--apply")
        index = (self.data / "music.html").read_text(encoding="utf-8")
        self.assertIn("../Daft%20Punk/Discovery/01.flac", index)
        self.assertTrue((self.data / "../Daft Punk/Discovery/01.flac").exists())

    def test_les_fiches_reviennent_a_musique_html(self):
        self.lancer("--apply")
        fiche = next((self.data / "Albums").glob("Daft Punk - Discovery-*.html")).read_text(encoding="utf-8")
        self.assertIn("href='../music.html#", fiche)
        self.assertNotIn("index.html", fiche)

    def test_no_player_n_ajoute_aucun_lecteur(self):
        self.lancer("--apply", "--no-player")
        for page in [*(self.data / "Albums").glob("*.html"), self.data / "music.html"]:
            self.assertNotIn("<audio", page.read_text(encoding="utf-8"), page.name)
        self.assertFalse((self.data / "lecteur.html").exists())

    def test_deuxieme_passage_ne_reecrit_rien_et_reprend_le_catalogue(self):
        self.lancer("--apply")
        fichiers = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in self.data.rglob("*") if p.is_file() and p.name != "recap.log"}
        _, sortie = self.lancer("--apply")
        self.assertIn("5 piste(s), 5 reprise(s) du catalogue, 0 à lire", sortie)
        self.assertIn("0 écrite(s), 3 inchangée(s)", sortie)
        self.assertIn("[artistes] 2 fiche(s) dans Artistes/ (0 écrite(s), 2 inchangée(s))", sortie)
        self.assertIn("inchangé", sortie)
        self.assertEqual({p: (p.stat().st_mtime_ns, p.read_bytes()) for p in fichiers}, fichiers)

    def test_piste_modifiee_est_relue(self):
        self.lancer("--apply")
        piste(self.racine / "Daft Punk" / "Discovery", "04.flac", number=4, total=4, title="Un titre plus long qu'avant", mbid=MBID)
        _, sortie = self.lancer("--apply")
        self.assertIn("4 reprise(s) du catalogue, 1 à lire", sortie)
        self.assertIn("1 écrite(s)", sortie)

    def test_no_cache_rouvre_tout(self):
        self.lancer("--apply")
        _, sortie = self.lancer("--apply", "--no-cache")
        self.assertIn("0 reprise(s) du catalogue, 5 à lire", sortie)

    def test_catalogue_corrompu_est_ignore(self):
        self.lancer("--apply")
        (self.data / "catalog.json").write_text("{", encoding="utf-8")
        _, sortie = self.lancer("--apply")
        self.assertIn("0 reprise(s) du catalogue, 5 à lire", sortie)

    def test_fichier_illisible_code_1_et_journal(self):
        (self.racine / "Daft Punk" / "Discovery" / "03.flac").write_bytes(b"coupe")
        code, sortie = self.lancer("--apply")
        self.assertEqual(code, 1)
        self.assertIn("À CORRIGER : 1 fichier(s) illisible(s)", sortie)
        self.assertIn("[ILLISIBLE] Daft Punk/Discovery/03.flac", (self.data / "recap.log").read_text(encoding="utf-8"))
        self.assertTrue((self.data / "music.html").exists())

    def test_catalogue_sans_piste_illisible(self):
        (self.racine / "Daft Punk" / "Discovery" / "03.flac").write_bytes(b"coupe")
        self.lancer("--apply")
        catalogue = json.loads((self.data / "catalog.json").read_text(encoding="utf-8"))["tracks"]
        self.assertNotIn("Daft Punk/Discovery/03.flac", catalogue)

    def test_dossier_sans_musique(self):
        vide = self.racine / "Vide"
        vide.mkdir()
        with mock.patch.object(sys, "argv", ["Recap.py", "--dir", str(vide)]), redirect_stdout(io.StringIO()) as sortie:
            self.assertEqual(recap.main(), 0)
        self.assertIn("Aucun .flac ni .mp3", sortie.getvalue())

    def test_dossier_introuvable(self):
        with mock.patch.object(sys, "argv", ["Recap.py", "--dir", str(self.racine / "nulle part")]):
            with self.assertRaises(SystemExit):
                recap.main()

    def test_options_invalides(self):
        with mock.patch.object(sys, "argv", ["Recap.py", "--dir", str(self.racine), "--workers", "0"]), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                recap.main()

    def test_un_mp3_compte_comme_un_flac(self):
        dossier = self.racine / "Air" / "Moon Safari"
        dossier.mkdir(parents=True)
        trames = [test_mp3.trame("TIT2", test_mp3.texte(["La femme d'argent"])), test_mp3.trame("TALB", test_mp3.texte(["Moon Safari"])),
                  test_mp3.trame("TPE1", test_mp3.texte(["Air"])), test_mp3.trame("TRCK", test_mp3.texte(["1/10"])),
                  test_mp3.trame("TXXX", test_mp3.txxx("MusicBrainz Album Id", [MBID]))]
        (dossier / "01.mp3").write_bytes(test_mp3.fichier(trames))
        _, sortie = self.lancer("--apply")
        self.assertIn("4 album(s), 3 artiste(s), 6 piste(s), 5 étiquetée(s)", sortie)
        fiche = next((self.data / "Albums").glob("Air - Moon Safari-*.html")).read_text(encoding="utf-8")
        self.assertIn("MP3", fiche)
        self.assertIn("La femme d&#39;argent", fiche)
        self.assertIn("Manque : pistes 2–10", fiche)

    @unittest.skipUnless(thumbs.available(), "Pillow n'est pas installé")
    def test_pochette_reduite_et_reprise_de_la_page(self):
        chemin = self.racine / "Daft Punk" / "Discovery" / "01.flac"
        chemin.write_bytes(fichier(["TITLE=Titre 1", "ARTIST=Daft Punk", "ALBUM=Discovery", "TRACKNUMBER=1", "MUSICBRAINZ_ALBUMID=" + MBID],
                                   extra=[(flac.PICTURE, image(png(900, 900)))]))
        _, sortie = self.lancer("--apply")
        self.assertIn("1 pochette(s) extraite(s)", sortie)
        index = (self.data / "music.html").read_text(encoding="utf-8")
        self.assertIn("src='data:image/jpeg;base64,", index)
        self.assertEqual(len(re.findall(r"<img data-img=", index)), 1)
        # Deuxième passage : la page sert de cache, la pochette n'est pas rouverte.
        with mock.patch.object(recap.library, "read_cover", side_effect=AssertionError("pochette rouverte")):
            _, sortie = self.lancer("--apply")
        self.assertIn("0 pochette(s) extraite(s)", sortie)
        self.assertEqual((self.data / "music.html").read_text(encoding="utf-8"), index)

    def test_sans_pillow_image_generique(self):
        chemin = self.racine / "Daft Punk" / "Discovery" / "01.flac"
        chemin.write_bytes(fichier(["TITLE=Titre 1", "ARTIST=Daft Punk", "ALBUM=Discovery", "TRACKNUMBER=1"], extra=[(flac.PICTURE, image(png()))]))
        with mock.patch.object(thumbs, "Image", None):
            _, sortie = self.lancer("--apply")
        self.assertIn("Pillow absent", sortie)
        index = (self.data / "music.html").read_text(encoding="utf-8")
        self.assertNotIn("<img data-img=", index)
        self.assertIn("<div class='noimg'></div>", index)

    def test_pochette_illisible_n_arrete_pas_le_passage(self):
        chemin = self.racine / "Daft Punk" / "Discovery" / "01.flac"
        chemin.write_bytes(fichier(["TITLE=Titre 1", "ARTIST=Daft Punk", "ALBUM=Discovery", "TRACKNUMBER=1"], extra=[(flac.PICTURE, image(b"pas une image"))]))
        code, _ = self.lancer("--apply")
        self.assertEqual(code, 0)
        self.assertNotIn("<img data-img=", next((self.data / "Albums").glob("Daft Punk - Discovery-*.html")).read_text(encoding="utf-8"))

    def test_fiche_d_un_album_sorti_de_la_mediatheque_reste_sur_le_disque(self):
        self.lancer("--apply")
        shutil.rmtree(self.racine / "Kavinsky")
        self.lancer("--apply")
        self.assertEqual(len(list((self.data / "Albums").glob("*.html"))), 3)
        self.assertEqual(len(re.findall(r"href='Albums/", (self.data / "music.html").read_text(encoding="utf-8"))), 2)


if __name__ == "__main__":
    unittest.main()
