"""Pages de la médiathèque musicale : ce que montrent le sommaire et la fiche d'un album, et leur relecture comme cache de pochettes."""

import re
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common.filenames import safe_name
from libraries.music import artistinfo, library, librarypage
from tests.test_artistinfo import groupe, resume
from tests.test_library import ARTISTE, MBID, piste

URI = "data:image/jpeg;base64,QUJD"


class PageTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.racine = Path(self._tmp.name)

    def albums(self):
        found = library.scan(self.racine)
        for release in found:
            for track in release.tracks:
                library.read_info(track)
        return found

    def album(self, artiste="Daft Punk", titre="Discovery", pistes=(1, 2, 3), total=3, annee="2001", **kw):
        for n in pistes:
            piste(self.racine / safe_name(artiste) / safe_name(titre), f"{n:02d}.flac", number=n, title=f"Piste {n}", total=total, artist=artiste, album=titre, date=annee, **kw)

    def un(self, **kw):
        self.album(**kw)
        return self.albums()[0]


class TestFormats(unittest.TestCase):
    def test_horloge(self):
        for secondes, attendu in ((0, ""), (None, ""), (5, "0:05"), (222, "3:42"), (3723, "1:02:03"), (59.6, "1:00")):
            with self.subTest(secondes=secondes):
                self.assertEqual(librarypage.clock(secondes), attendu)

    def test_duree(self):
        for secondes, attendu in ((10, ""), (2880, "48 min"), (3600, "1 h"), (4320, "1 h 12 min"), (36000, "10 h")):
            with self.subTest(secondes=secondes):
                self.assertEqual(librarypage.length(secondes), attendu)

    def test_pistes(self):
        self.assertEqual((librarypage.tracks_label(1), librarypage.tracks_label(13)), ("1 piste", "13 pistes"))


class TestNomsDePage(PageTestCase):
    def test_nom_lisible_et_identifiant(self):
        album = self.un()
        self.assertEqual(librarypage.page_name(album), f"Daft Punk - Discovery-{album.id}.html")

    def test_caracteres_interdits_retires(self):
        album = self.un(artiste="AC/DC", titre='Who Made Who? "Live"')
        self.assertTrue(librarypage.page_name(album).startswith("ACDC - Who Made Who Live-"))

    def test_lien_encode_et_relatif(self):
        album = self.un(titre="Un titre & des espaces")
        lien = librarypage.href(album)
        self.assertTrue(lien.startswith("Albums/"))
        self.assertNotIn(" ", lien)
        self.assertEqual(unquote(lien), f"Albums/{librarypage.page_name(album)}")


class TestSommaire(PageTestCase):
    def sommaire(self, **kw):
        sections = library.sections(self.albums())
        pages = {r.id for _, releases in sections for r in releases}
        return librarypage.build_index("Musique", sections, {}, pages if kw.get("pages", True) else set())

    def test_une_section_par_artiste_meme_avec_un_seul_album(self):
        self.album("Daft Punk", "Homework", annee="1997")
        self.album("Daft Punk", "Discovery")
        self.album("Kavinsky", "Outrun", annee="2013")
        html = self.sommaire()
        self.assertEqual(re.findall(r"<h2[^>]*>(.*?)<span", html), ["Daft Punk", "Kavinsky"])
        self.assertLess(html.index("Homework"), html.index("Discovery"))
        self.assertNotIn("Autres artistes", html)

    def test_resume(self):
        self.album("Daft Punk", "Homework", annee="1997")
        self.album("Kavinsky", "Outrun")
        self.assertIn("2 albums · 2 artistes · 6 pistes", self.sommaire())

    def test_la_pochette_mene_a_la_fiche(self):
        album = self.un()
        html = self.sommaire()
        self.assertIn(f"id='{librarypage.anchor(album)}'", html)
        self.assertIn(f"href='{librarypage.href(album)}'", html)

    def test_sans_fiche_la_pochette_reste_inerte(self):
        self.album()
        html = self.sommaire(pages=False)
        self.assertNotIn("href='Albums/", html)
        self.assertNotIn("<a class='al'", html)

    def test_monogramme_sans_pochette(self):
        self.album(titre="Discovery")
        self.assertIn("class='noimg mono'", self.sommaire())

    def test_pochette_encodee_dans_la_page(self):
        album = self.un()
        html = librarypage.build_index("Musique", library.sections([album]), {album.id: URI}, {album.id})
        self.assertIn(f"<img data-img='{album.key}' src='{URI}'", html)

    def test_pistes_manquantes_en_orange(self):
        self.album(pistes=(1, 2), total=6)
        html = self.sommaire()
        self.assertIn("<div class='y warn'>2001 · 2/6 pistes</div>", html)

    def test_l_index_alphabetique_vise_le_titre_de_la_section(self):
        self.album("Kavinsky", "Outrun")
        self.album("Daft Punk", "Discovery")
        html = self.sommaire()
        self.assertEqual(re.findall(r"<h2[^>]*data-i='(\w)'", html), ["D", "K"])
        self.assertEqual(html.count("data-i="), 2)          # les pochettes n'en portent pas

    def test_recherche_dans_artiste_label_et_genre(self):
        self.album("Daft Punk", "Discovery", genres=("Electronic", "House"), label="Virgin")
        texte = re.search(r"data-s='([^']*)'", self.sommaire()).group(1)
        for mot in ("Discovery", "Daft Punk", "Virgin", "House"):
            self.assertIn(mot, texte)

    def test_genres_filtrables(self):
        self.album("Daft Punk", "Discovery", genres=("Electronic",))
        html = self.sommaire()
        self.assertIn("class='genre'", html)
        self.assertIn("Electronic (1)", html)
        self.assertIn("data-g='Electronic'", html)

    def test_titre_et_icone(self):
        self.album()
        html = self.sommaire()
        self.assertIn("<title>Musique</title>", html)
        self.assertIn("rel='icon'", html)

    def test_apostrophe_dans_un_titre_n_ouvre_pas_l_attribut(self):
        self.album("Air", "L'Oeil du cyclone")
        html = self.sommaire()
        self.assertIn("L&#39;Oeil du cyclone", html)
        self.assertNotIn("data-s='L'Oeil", html)


class TestSommaireArtistes(PageTestCase):
    def sommaire(self, avec_fiches=True):
        sections = library.sections(self.albums())
        pages = {r.id for _, releases in sections for r in releases}
        artistes = {a.id: a for a in library.artists(self.albums())} if avec_fiches else {}
        return librarypage.build_index("Musique", sections, {}, pages, artistes)

    def test_le_nom_de_la_section_mene_a_l_artiste(self):
        self.album("Daft Punk", "Homework", annee="1997")
        self.album("Daft Punk", "Discovery")
        artiste, = library.artists(self.albums())
        html = self.sommaire()
        self.assertIn(f"<h2 id='s{artiste.id}' data-i='D'><a href='{librarypage.artist_href(artiste)}'>Daft Punk</a>", html)

    def test_le_nom_d_un_artiste_d_un_seul_album_mene_a_sa_fiche(self):
        self.album("Kavinsky", "Outrun")
        artiste, = library.artists(self.albums())
        self.assertIn(f"<h2 id='s{artiste.id}' data-i='K'><a href='{librarypage.artist_href(artiste)}'>Kavinsky</a>", self.sommaire())

    def test_les_pochettes_d_un_groupe_reviennent_a_son_nom(self):
        self.album("Daft Punk", "Homework", annee="1997")
        self.album("Daft Punk", "Discovery")
        self.album("Kavinsky", "Outrun", annee="2013")
        html = self.sommaire()
        daft_punk, = [a for a in library.artists(self.albums()) if a.name == "Daft Punk"]
        ancre = librarypage.artist_anchor(daft_punk)
        self.assertIn(f"<h2 id='{ancre}'", html)
        self.assertEqual(html.count(f"data-b='{ancre}'"), 2)

    def test_un_artiste_d_un_seul_album_revient_aussi_a_son_nom(self):
        self.album("Kavinsky", "Outrun", annee="2013")
        artiste, = library.artists(self.albums())
        self.assertIn(f"data-b='{librarypage.artist_anchor(artiste)}'", self.sommaire())

    def test_sans_fiche_d_artiste_la_pochette_est_la_cible_du_retour(self):
        self.album("Kavinsky", "Outrun", annee="2013")
        self.assertNotIn("data-b=", self.sommaire(avec_fiches=False))

    def test_le_sommaire_se_cale_au_retour(self):
        self.album("Kavinsky", "Outrun", annee="2013")
        self.assertIn("history.replaceState({back:id}", self.sommaire())

    def test_sans_fiche_d_artiste_le_nom_reste_du_texte(self):
        self.album("Daft Punk", "Homework", annee="1997")
        self.album("Daft Punk", "Discovery")
        self.album("Kavinsky", "Outrun")
        html = self.sommaire(avec_fiches=False)
        self.assertNotIn("href='Artistes/", html)
        self.assertEqual(re.findall(r"<h2[^>]*>(.*?)<span", html), ["Daft Punk", "Kavinsky"])


class TestFiche(PageTestCase):
    def fiche(self, album, image=None, artiste=None):
        return librarypage.build_release(album, image, "../index.html", "Musique", artiste)

    def test_le_nom_de_l_artiste_mene_a_sa_fiche(self):
        album = self.un()
        artiste, = library.artists([album])
        html = self.fiche(album, artiste=artiste)
        self.assertIn(f"<div class='artist'><a href='{librarypage.artist_href(artiste, '../')}'>Daft Punk</a></div>", html)

    def test_sans_fiche_d_artiste_le_nom_reste_du_texte(self):
        self.assertNotIn("Artistes/", self.fiche(self.un()))

    def test_titre_artiste_faits(self):
        html = self.fiche(self.un(mbid=MBID))
        self.assertIn("<h1>Discovery</h1>", html)
        self.assertIn("<div class='artist'>Daft Punk</div>", html)
        self.assertIn("2001 · Virgin · 3 pistes · FLAC", html)

    def test_label_sans_numero_de_catalogue(self):
        html = self.fiche(self.un(label="Craft Recordings", extra=("CATALOGNUMBER=[none]",)))
        self.assertIn("2001 · Craft Recordings · 3 pistes", html)
        self.assertNotIn("[none]", html)

    def test_label_et_numero_de_catalogue(self):
        self.assertIn("Craft Recordings (CR00123)", self.fiche(self.un(label="Craft Recordings", extra=("CATALOGNUMBER=CR00123",))))

    def test_retour_au_sommaire_sur_la_vignette_sans_fiche_d_artiste(self):
        album = self.un()
        self.assertIn(f"href='../index.html#{librarypage.anchor(album)}'", self.fiche(album))

    def test_retour_au_sommaire_sur_le_nom_du_groupe(self):
        self.album("Daft Punk", "Homework", annee="1997")
        self.album("Daft Punk", "Discovery")
        album = self.albums()[0]
        artiste, = library.artists(self.albums())
        self.assertIn(f"href='../index.html#{librarypage.artist_anchor(artiste)}'", self.fiche(album, artiste=artiste))

    def test_pistes_dans_l_ordre_avec_leur_duree(self):
        html = self.fiche(self.un())
        lignes = re.findall(r"<td class='n'>(\d+)</td><td>(.*?)</td><td class='d'>(.*?)</td>", html)
        self.assertEqual(lignes, [("1", "Piste 1", "0:10"), ("2", "Piste 2", "0:10"), ("3", "Piste 3", "0:10")])

    def test_pistes_manquantes_grisees_a_leur_place(self):
        html = self.fiche(self.un(pistes=(1, 2, 5), total=6))
        self.assertEqual(re.findall(r"<tr class='absent'><td class='n'>(\d+)</td>", html), ["3", "4", "6"])
        self.assertLess(html.index("Piste 2"), html.index("<tr class='absent'><td class='n'>3"))
        self.assertLess(html.index("<tr class='absent'><td class='n'>4"), html.index("Piste 5"))
        self.assertIn("Manque : pistes 3, 4, 6 <span>(sur 6, d'après les tags)</span>", html)

    def test_une_seule_piste_manquante_au_singulier(self):
        self.assertIn("Manque : piste 3 <", self.fiche(self.un(pistes=(1, 2, 4), total=4)))

    def test_album_complet_sans_manque(self):
        html = self.fiche(self.un())
        self.assertNotIn("Manque", html)
        self.assertNotIn("absent", html.split("<style>")[1].split("</style>")[1])

    def test_plusieurs_disques(self):
        for disc in (1, 2):
            piste(self.racine / "A" / f"CD{disc}", "01.flac", number=1, total=1, disc=disc, disctotal=2, title=f"D{disc}")
        html = self.fiche(self.albums()[0])
        self.assertEqual(re.findall(r"<h2>(Disque \d)", html), ["Disque 1", "Disque 2"])

    def test_disque_absent_signale(self):
        piste(self.racine / "A", "01.flac", number=1, total=1, disc=1, disctotal=2)
        self.assertIn("Manque : disque 2 ", self.fiche(self.albums()[0]))

    def test_artiste_de_piste_montre_quand_il_differe(self):
        piste(self.racine / "A", "01.flac", number=1, artist="Kavinsky", albumartist="Various Artists", title="Nightcall")
        piste(self.racine / "A", "02.flac", number=2, artist="Various Artists", albumartist="Various Artists", title="Autre")
        html = self.fiche(self.albums()[0])
        self.assertEqual(re.findall(r"<div class='by'>(.*?)</div>", html), ["Kavinsky"])

    def test_artiste_de_piste_masque_quand_seul_l_invite_change(self):
        piste(self.racine / "A", "01.flac", number=1, artist="Kavinsky feat. Havoc", albumartist="Kavinsky", title="Protovision")
        piste(self.racine / "A", "02.flac", number=2, artist="Kavinsky", albumartist="Kavinsky", title="Autre")
        html = self.fiche(self.albums()[0])
        self.assertEqual(re.findall(r"<div class='by'>(.*?)</div>", html), [])

    def test_sans_racine_la_fiche_ne_lit_rien(self):
        html = self.fiche(self.un())
        for absent in ("<audio", "class='play'", "class='p'", "#bar", "id='all'"):
            self.assertNotIn(absent, html)

    def lisible(self, album, base="../../"):
        return librarypage.build_release(album, None, "../index.html", "Musique", None, base)

    def test_un_bouton_par_piste_vers_le_fichier(self):
        album = self.un()
        html = self.lisible(album)
        self.assertEqual(re.findall(r"data-src='([^']+)'", html), ["../../Daft%20Punk/Discovery/01.flac", "../../Daft%20Punk/Discovery/02.flac", "../../Daft%20Punk/Discovery/03.flac"])
        self.assertEqual(html.count("<audio"), 1)
        self.assertEqual(re.findall(r"data-title='([^']+)'", html), ["Piste 1", "Piste 2", "Piste 3"])

    def test_tout_lire_et_pistes_precedente_suivante(self):
        html = self.lisible(self.un())
        for present in ("id='all'", "id='prev'", "id='next'"):
            self.assertIn(present, html)
        self.assertLess(html.index("id='all'"), html.index("<table class='trk'>"))

    def test_album_sans_piste_lisible_sans_lecteur(self):
        album = self.un()
        for track in album.tracks:
            track.error = "en-tete invalide"
        html = self.lisible(album)
        for absent in ("id='all'", "<audio", "document.getElementById('player')"):
            self.assertNotIn(absent, html)

    def test_la_barre_precede_le_script_qui_la_cherche(self):
        # Un script ne voit que ce qui le précède dans la page : la barre après lui, il cherchait un <audio> qui n'existait pas encore.
        html = self.lisible(self.un())
        self.assertLess(html.index("<audio id='player'"), html.index("document.getElementById('player')"))

    def test_chemin_de_piste_encode_et_apostrophe_echappee(self):
        piste(self.racine / "Artiste" / "L'Oeil #1", "01 - Ça va 100%.flac", number=1, total=1, title="Ça va 100%")
        html = self.lisible(self.albums()[0], "../")
        self.assertIn("data-src='../Artiste/L%27Oeil%20%231/01%20-%20%C3%87a%20va%20100%25.flac'", html)

    def test_piste_manquante_et_piste_illisible_sans_bouton(self):
        html = self.lisible(self.un(pistes=(1, 3), total=3))
        self.assertEqual(html.count("class='play'"), 2)
        self.assertIn("<tr class='absent'><td class='p'></td><td class='n'>2</td>", html)

    def test_piste_illisible_ne_se_joue_pas(self):
        album = self.un()
        album.tracks[1].error = "en-tete invalide"
        self.assertEqual(self.lisible(album).count("class='play'"), 2)

    def test_lien_musicbrainz_seulement_avec_l_identifiant(self):
        self.assertIn(f"https://musicbrainz.org/release/{MBID}", self.fiche(self.un(mbid=MBID)))

    def test_sans_identifiant_pas_de_lien(self):
        self.assertNotIn("musicbrainz", self.fiche(self.un()))

    def test_chemin_de_l_album(self):
        self.assertIn("<div class='path'>Daft Punk/Discovery</div>", self.fiche(self.un()))

    def test_pochette_ou_monogramme(self):
        album = self.un()
        self.assertIn(f"<img data-img='{album.key}' src='{URI}'", self.fiche(album, URI))
        self.assertIn("class='noimg mono'", self.fiche(album))

    def test_fichier_illisible_signale_sur_la_fiche(self):
        album = self.un()
        album.tracks[0].error = "bloc tronque"
        self.assertIn("illisible : bloc tronque", self.fiche(album))

    def test_formats_non_pris_en_charge(self):
        album = self.un()
        album.unsupported = ["04.m4a"]
        self.assertIn("Non pris en charge : 04.m4a", self.fiche(album))


class TestFicheArtiste(PageTestCase):
    def fiche(self, mbid=None, **kw):
        self.album("Daft Punk", "Homework", annee="1997", extra=(f"MUSICBRAINZ_ALBUMARTISTID={mbid}",) if mbid else ())
        self.album("Daft Punk", "Discovery", genres=("Electronic", "House"))
        albums = self.albums()
        artiste, = library.artists(albums)
        return artiste, albums, librarypage.build_artist(artiste, kw.get("covers", {}), "../index.html", "Musique", {r.id for r in albums})

    def test_nom_et_faits(self):
        _, _, html = self.fiche()
        self.assertIn("<title>Daft Punk</title>", html)
        self.assertIn("<h1>Daft Punk</h1>", html)
        self.assertIn("2 albums · 1997–2001 · 6 pistes", html)
        self.assertIn("Electronic, House", html)

    def test_albums_dans_l_ordre_et_menant_a_leur_fiche(self):
        artiste, albums, html = self.fiche()
        liens = re.findall(r"<a class='cv' href='([^']*)'", html)
        self.assertEqual([unquote(x) for x in liens], [f"../Albums/{librarypage.page_name(r)}" for r in artiste.releases])
        self.assertLess(html.index("Homework"), html.index("Discovery"))

    def test_pochette_du_sommaire_reprise(self):
        artiste, albums, html = self.fiche(covers={})
        album = artiste.releases[0]
        html = librarypage.build_artist(artiste, {album.id: URI}, "../index.html", "Musique", {album.id})
        self.assertIn(f"<img data-img='{album.key}' src='{URI}'", html)

    def test_lien_musicbrainz_de_l_artiste(self):
        _, _, html = self.fiche(mbid=ARTISTE)
        self.assertIn(f"href='https://musicbrainz.org/artist/{ARTISTE}'", html)
        self.assertIn("Voir sur MusicBrainz", html)

    def test_sans_identifiant_pas_de_lien(self):
        _, _, html = self.fiche()
        self.assertNotIn("musicbrainz.org", html)

    def test_retour_a_la_section_de_l_artiste(self):
        artiste, _, html = self.fiche()
        self.assertIn(f"href='../index.html#s{artiste.id}'", html)

    def test_retour_au_nom_d_un_artiste_d_un_seul_album(self):
        self.album("Kavinsky", "Outrun")
        album = self.albums()[0]
        artiste, = library.artists([album])
        html = librarypage.build_artist(artiste, {}, "../index.html", "Musique", {album.id})
        self.assertIn(f"href='../index.html#s{artiste.id}'", html)

    def test_album_sans_fiche_reste_inerte(self):
        artiste, albums, _ = self.fiche()
        html = librarypage.build_artist(artiste, {}, "../index.html", "Musique", set())
        self.assertNotIn("../Albums/", html)

    def test_apostrophe_dans_un_nom(self):
        self.album("Guns N' Roses", "Appetite")
        album = self.albums()[0]
        artiste, = library.artists([album])
        html = librarypage.build_artist(artiste, {}, "../index.html", "Musique", {album.id})
        self.assertIn("<h1>Guns N&#39; Roses</h1>", html)

    def info(self, **kw):
        info = artistinfo.parse(groupe(**kw))
        info["wiki"] = {"lang": "fr", "title": "Daft Punk", "url": "https://fr.wikipedia.org/wiki/Daft_Punk", "extract": "Daft Punk est un duo français."}
        return info

    def avec_info(self, info, mbid=ARTISTE):
        self.album("Daft Punk", "Homework", annee="1997", extra=(f"MUSICBRAINZ_ALBUMARTISTID={mbid}",))
        albums = self.albums()
        artiste, = library.artists(albums)
        return librarypage.build_artist(artiste, {}, "../index.html", "Musique", {r.id for r in albums}, info)

    def test_type_pays_dates_et_desambiguation(self):
        html = self.avec_info(self.info())
        self.assertIn("<div class='kind'>Groupe · France · depuis 1993</div>", html)
        self.assertIn("<div class='dis'>French electronic duo</div>", html)

    def test_resume_wikipedia_et_sa_source(self):
        html = self.avec_info(self.info())
        self.assertIn("<div class='bio'><p>Daft Punk est un duo français.</p>", html)
        self.assertIn("href='https://fr.wikipedia.org/wiki/Daft_Punk' target='_blank' rel='noopener'>Source : Wikipédia (fr) ↗", html)

    def test_membres_actuels_puis_anciens_avec_leurs_roles(self):
        html = self.avec_info(self.info())
        self.assertEqual(re.findall(r"<summary>(Membres|Anciens membres)<span class='cnt'>(\d+)</span>", html), [("Membres", "1"), ("Anciens membres", "1")])
        self.assertIn("synthesizer · depuis 1993", html)
        self.assertIn("1993 – 2021", html)
        self.assertIn("https://musicbrainz.org/artist/0e6a5d0a-1f2b-4c3d-8e4f-5a6b7c8d9e01", html)

    def test_listes_de_membres_repliees_par_defaut(self):
        html = self.avec_info(self.info())
        self.assertEqual(re.findall(r"<details class='mem'( open)?><summary>([^<]+)<", html),
                         [("", "Membres"), ("", "Anciens membres"), (" open", "Albums")])

    def test_albums_deplies_par_defaut(self):
        html = self.avec_info(self.info())
        self.assertIn("<details class='mem' open><summary>Albums<span class='cnt'>1</span></summary><div class='grid'>", html)
        self.assertEqual(len(re.findall(r"<details class='mem' open>", html)), 1)

    def test_albums_repliables_meme_sans_info(self):
        self.assertIn("<details class='mem' open><summary>Albums<", self.avec_info(None))

    def test_liens_de_l_artiste_apres_celui_de_musicbrainz(self):
        html = self.avec_info(self.info())
        self.assertLess(html.index("Voir sur MusicBrainz ↗"), html.index("Site officiel ↗"))
        self.assertIn("href='https://www.daftpunk.com/'", html)

    def test_liens_sans_identifiant_musicbrainz(self):
        html = self.avec_info(self.info(), mbid="")
        self.assertNotIn("Voir sur MusicBrainz", html)
        self.assertIn("Site officiel ↗", html)

    def test_sans_info_rien_de_plus(self):
        html = self.avec_info(None)
        for absent in ("class='kind'", "class='dis'", "class='bio'", "Membres"):
            self.assertNotIn(absent, html.split("</style>")[1])

    def test_texte_de_wikipedia_echappe(self):
        info = self.info()
        info["wiki"]["extract"] = "<script>alert('x')</script>"
        html = self.avec_info(info).split("</style>")[1]
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;alert(&#39;x&#39;)", html)

    def test_nom_de_fichier(self):
        artiste, _, _ = self.fiche()
        self.assertEqual(librarypage.artist_page_name(artiste), f"Daft Punk-{artiste.id}.html")


class TestCache(PageTestCase):
    def test_pochettes_relues_dans_une_page_ecrite(self):
        album = self.un()
        page = self.racine / "fiche.html"
        page.write_text(librarypage.build_release(album, URI, "../index.html", "Musique"), encoding="utf-8")
        self.assertEqual(librarypage.read_embedded(page), {album.key: URI})

    def test_page_absente(self):
        self.assertEqual(librarypage.read_embedded(self.racine / "rien.html"), {})

    def test_monogramme_ne_laisse_aucune_pochette(self):
        album = self.un()
        page = self.racine / "fiche.html"
        page.write_text(librarypage.build_release(album, None, "../index.html", "Musique"), encoding="utf-8")
        self.assertEqual(librarypage.read_embedded(page), {})


if __name__ == "__main__":
    unittest.main()
