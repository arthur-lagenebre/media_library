"""Albums : dossiers reconnus, choix de l'édition MusicBrainz, fichiers placés sur leurs pistes, tags visés et fusion avec l'existant."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.music import album, flac
def meta(*lignes, duree=None):
    """flac.Metadata réduit à ses tags (et à sa durée si on la donne)."""
    m = flac.Metadata(blocks=[], audio_offset=0, comments=[tuple(l.split("=", 1)) for l in lignes])
    if duree:
        m.sample_rate, m.total_samples = 1000, int(duree * 1000)
    return m


def sortie(ident, titre, pistes, date="2013-02-25", pays="FR", groupe="rg-1", statut="Official", support="CD"):
    """Résultat de recherche de sortie, tel que MusicBrainz le rend."""
    pistes = pistes if isinstance(pistes, list) else [pistes]
    return {"id": ident, "title": titre, "date": date, "country": pays, "status": statut, "release-group": {"id": groupe}, "media": [{"format": support, "track-count": n} for n in pistes]}


KAVINSKY = {"name": "Kavinsky", "joinphrase": "", "artist": {"id": "art-1", "name": "Kavinsky", "sort-name": "Kavinsky"}}


def piste(position, titre, **extra):
    return dict({"id": f"t{position}", "position": position, "title": titre, "length": 200000, "recording": {"id": f"r{position}", "title": titre, "length": 200000}}, **extra)


OUTRUN = {"id": "rel-1", "title": "OutRun", "date": "2013-02-25", "country": "FR", "status": "Official", "barcode": "602537320233", "artist-credit": [KAVINSKY],
          "label-info": [{"catalog-number": "00602537320233", "label": {"name": "Record Makers"}}, {"catalog-number": "00602537320233", "label": {"name": "Vertigo"}}],
          "release-group": {"id": "rg-1", "primary-type": "Album", "secondary-types": ["Live"], "first-release-date": "2013-02-22"},
          "media": [{"position": 1, "format": "CD", "track-count": 3, "tracks": [piste(1, "Prelude"), piste(2, "Blizzard"), piste(3, "Protovision", **{"artist-credit": [dict(KAVINSKY, joinphrase=" feat. "), {"name": "Havoc", "joinphrase": "", "artist": {"id": "art-2", "name": "Havoc", "sort-name": "Havoc"}}]})]}]}

DOUBLE = {"id": "rel-2", "title": "Alive", "media": [{"position": 1, "format": "CD", "tracks": [piste(1, "Robot Rock"), piste(2, "Touch It")]}, {"position": 2, "format": "CD", "tracks": [piste(1, "Alive 1997")]}]}


class TestDossiers(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.racine = Path(self._tmp.name)

    def poser(self, *chemins):
        for chemin in chemins:
            fichier = self.racine / chemin
            fichier.parent.mkdir(parents=True, exist_ok=True)
            fichier.write_bytes(b"")

    def test_le_dossier_d_artiste_ne_compte_pas(self):
        self.poser("Kavinsky/2013 - Outrun/01 - Prelude.flac", "Kavinsky/2022 - Reborn/01 - Pulsar.flac")
        self.assertEqual([a.display for a in album.find_albums(self.racine)], [str(Path("Kavinsky/2013 - Outrun")), str(Path("Kavinsky/2022 - Reborn"))])

    def test_artist_txt_du_dossier_d_artiste(self):
        self.poser("Thiéfaine/2005 - Scandale/01.flac")
        (self.racine / "Thiéfaine" / "artist.txt").write_text("\ufeff\n  Hubert-Félix Thiéfaine \n", encoding="utf-8")
        self.assertEqual(album.artist_override(self.racine / "Thiéfaine" / "2005 - Scandale", self.racine), "Hubert-Félix Thiéfaine")

    def test_artist_txt_le_plus_proche_et_jamais_au_dessus_de_la_racine(self):
        self.poser("Thiéfaine/2005 - Scandale/01.flac")
        (self.racine / "artist.txt").write_text("Racine", encoding="utf-8")
        (self.racine / "Thiéfaine" / "2005 - Scandale" / "artist.txt").write_text("Album", encoding="utf-8")
        self.assertEqual(album.artist_override(self.racine / "Thiéfaine" / "2005 - Scandale", self.racine), "Album")
        self.assertEqual(album.artist_override(self.racine / "Thiéfaine", self.racine), "Racine")
        self.assertEqual(album.artist_override(self.racine / "Thiéfaine", self.racine / "Thiéfaine"), "")

    def test_option_artist_prime_sur_le_fichier(self):
        self.poser("Thiéfaine/2005 - Scandale/01.flac")
        (self.racine / "Thiéfaine" / "artist.txt").write_text("Fichier", encoding="utf-8")
        self.assertEqual(album.artist_override(self.racine / "Thiéfaine" / "2005 - Scandale", self.racine, " Option "), "Option")

    def test_aucun_artist_txt(self):
        self.poser("Kavinsky/2013 - Outrun/01.flac")
        self.assertEqual(album.artist_override(self.racine / "Kavinsky" / "2013 - Outrun", self.racine), "")

    def test_dossiers_de_disque_reunis(self):
        self.poser("Daft Punk/Alive/CD1/01.flac", "Daft Punk/Alive/CD1/02.flac", "Daft Punk/Alive/CD 2/01.flac")
        (seul,) = album.find_albums(self.racine)
        self.assertEqual((seul.folder.name, len(seul.files)), ("Alive", 3))
        self.assertEqual(sorted(seul.disc_folder(f) for f in seul.files), [1, 1, 2])
        self.assertEqual(seul.disc_count, 2)

    def test_disques_nommes_d_apres_leur_titre(self):
        # "La fête est finie - Épilogue" : MusicBrainz titre ses deux CD, et les dossiers portent ces titres.
        self.poser("Orelsan/La fete/1 - La fete est finie/01 - San.mp3", "Orelsan/La fete/2 - Epilogue/01 - Fantomes.mp3", "Orelsan/La fete/2 - Epilogue/02 - Dis-moi.mp3")
        (seul,) = album.find_albums(self.racine)
        self.assertEqual((seul.folder.name, len(seul.files), seul.disc_count), ("La fete", 3, 2))
        self.assertEqual(sorted(seul.disc_folder(f) for f in seul.files), [1, 2, 2])

    def test_cd_avec_un_titre(self):
        self.poser("A/CD1 - Live/01.flac", "A/Disc 2 - Bonus/01.flac")
        (seul,) = album.find_albums(self.racine)
        self.assertEqual(sorted(seul.disc_folder(f) for f in seul.files), [1, 2])

    def test_albums_numerotes_ne_sont_pas_des_disques(self):
        # Un seul "1 - Album", ou des numéros qui ne se suivent pas depuis 1 : ce sont des albums.
        self.poser("A/1 - Premier/01.flac", "A/3 - Troisieme/01.flac", "B/2 - Seul/01.flac")
        self.assertEqual(len(album.find_albums(self.racine)), 3)

    def test_un_disque_sans_dossier_de_disque(self):
        self.poser("A/01.flac", "A/02.flac")
        self.assertEqual(album.find_albums(self.racine)[0].disc_count, 1)

    def test_fichier_a_la_racine_de_l_album_sans_disque(self):
        self.poser("A/01.flac")
        (seul,) = album.find_albums(self.racine)
        self.assertIsNone(seul.disc_folder(seul.files[0]))

    def test_formats_non_ecrits_signales(self):
        self.poser("E-Life/01.m4a", "E-Life/02.m4a")
        (seul,) = album.find_albums(self.racine)
        self.assertEqual((seul.files, len(seul.unsupported)), ([], 2))

    def test_dir_pointe_sur_l_album(self):
        self.poser("01 - Nightcall.flac")
        (seul,) = album.find_albums(self.racine)
        self.assertEqual(seul.display, self.racine.name)


class TestIndicesDuDossier(unittest.TestCase):
    def test_annee_devant_artiste_au_dessus(self):
        h = album.folder_hints(Path("Body Count/1994 - Born Dead"))
        self.assertEqual((h.artist, h.title, h.year), ("Body Count", "Born Dead", "1994"))

    def test_nom_de_release(self):
        h = album.folder_hints(Path("Daft Punk/Daft Punk - Discovery (2001) FLAC [16bit 44.1kHz]-CML34"))
        self.assertEqual((h.artist, h.title, h.year), ("Daft Punk", "Discovery", "2001"))

    def test_titre_nu(self):
        h = album.folder_hints(Path("Kavinsky/Nightcall"))
        self.assertEqual((h.artist, h.title, h.year), ("Kavinsky", "Nightcall", ""))

    def test_identifiant_epingle(self):
        h = album.folder_hints(Path("Kavinsky/2013 - Outrun [mbid-4E5D9F0C-09b6-42bf-b495-e2d7cc288bf6]"))
        self.assertEqual((h.title, h.pinned), ("Outrun", "4e5d9f0c-09b6-42bf-b495-e2d7cc288bf6"))

    def test_identifiant_passe_en_option(self):
        self.assertEqual(album.parse_mbid(" 4E5D9F0C-09b6-42bf-b495-e2d7cc288bf6 "), "4e5d9f0c-09b6-42bf-b495-e2d7cc288bf6")
        self.assertIsNone(album.parse_mbid("4e5d9f0c"))


class TestIndicesDesTags(unittest.TestCase):
    def test_valeur_la_plus_repandue(self):
        # Le CD bonus d'Alive 2007 se dit "Alive 1997" : il ne doit pas renommer l'album.
        h = album.tag_hints([meta("ALBUM=Alive 2007", "ARTIST=Daft Punk", "DATE=2007"), meta("ALBUM=Alive 2007"), meta("ALBUM=Alive 1997")])
        self.assertEqual((h.title, h.artist, h.year), ("Alive 2007", "Daft Punk", "2007"))

    def test_artiste_de_l_album_avant_celui_de_la_piste(self):
        h = album.tag_hints([meta("ARTIST=Kavinsky feat. Havoc", "ALBUMARTIST=Kavinsky")])
        self.assertEqual(h.artist, "Kavinsky")

    def test_identifiant_si_tous_le_declarent(self):
        ident = "MUSICBRAINZ_ALBUMID=4e5d9f0c-09b6-42bf-b495-e2d7cc288bf6"
        self.assertEqual(album.tag_hints([meta(ident), meta(ident)]).tagged, "4e5d9f0c-09b6-42bf-b495-e2d7cc288bf6")

    def test_identifiant_partiel_ignore(self):
        # Un album à moitié étiqueté par Picard n'est pas encore un album étiqueté.
        self.assertIsNone(album.tag_hints([meta("MUSICBRAINZ_ALBUMID=abc"), meta("TITLE=x")]).tagged)


class TestChoixDeLEdition(unittest.TestCase):
    def choisir(self, resultats, fichiers, titre="Merciless", annee=""):
        return album.choose_release(resultats, fichiers, album.Hints("Body Count", titre, annee))

    def test_le_nombre_de_pistes_ecarte_le_single(self):
        choix = self.choisir([sortie("single", "Merciless", 1, groupe="rg-s"), sortie("cd", "Merciless", 12, groupe="rg-a")], 12)
        self.assertEqual((choix.release["id"], choix.rivals), ("cd", []))

    def test_aucune_edition_au_bon_compte(self):
        choix = self.choisir([sortie("a", "Merciless", 1), sortie("b", "Merciless", 13)], 12)
        self.assertIsNone(choix.release)
        self.assertIn("aucune édition de 12 piste(s) ; trouvé : 1, 13", choix.reason)

    def test_disques_additionnes(self):
        self.assertEqual(self.choisir([sortie("x", "Merciless", [12, 1])], 13).release["id"], "x")

    def test_l_annee_du_dossier_ecarte_la_reedition(self):
        resultats = [sortie("2021", "Discovery", 14, date="2021"), sortie("2001", "Discovery", 14, date="2001-03-12")]
        self.assertEqual(self.choisir(resultats, 14, "Discovery", "2001").release["id"], "2001")

    def test_pays_demande_puis_europe(self):
        resultats = [sortie("dz", "Homework", 16, pays="DZ"), sortie("xe", "Homework", 16, pays="XE"), sortie("fr", "Homework", 16, pays="FR")]
        self.assertEqual(self.choisir(resultats, 16, "Homework").release["id"], "fr")
        self.assertEqual(self.choisir(resultats[:2], 16, "Homework").release["id"], "xe")

    def test_le_vinyle_en_deux_faces_ne_passe_pas_devant_le_cd(self):
        # Mesuré sur "Human After All" : le vinyle français (5+5) passait devant le CD européen, et la 6e piste devenait "disque 2, piste 1".
        resultats = [sortie("vinyle", "Human After All", [5, 5], date="2005-03-14", support='12" Vinyl'), sortie("cd", "Human After All", 10, date="2005-03-11", pays="XE")]
        self.assertEqual(self.choisir(resultats, 10, "Human After All", "2005").release["id"], "cd")

    def test_dossiers_de_disque_preferent_l_edition_en_autant_de_disques(self):
        resultats = [sortie("un", "Alive 2007", 13, pays="XW", support="Digital Media"), sortie("deux", "Alive 2007", [12, 1])]
        hints = album.Hints("Daft Punk", "Alive 2007", "")
        self.assertEqual(album.choose_release(resultats, 13, hints, discs=2).release["id"], "deux")
        self.assertEqual(album.choose_release(resultats, 13, hints, discs=1).release["id"], "un")

    def test_officielle_avant_tout(self):
        resultats = [sortie("retiree", "Body Count", 17, statut="Withdrawn"), sortie("officielle", "Body Count", 17, pays="AU")]
        self.assertEqual(self.choisir(resultats, 17, "Body Count").release["id"], "officielle")

    def test_titre_exact_sans_question(self):
        # "Bloodlust (instrumental)" a aussi 11 pistes, mais ce n'est pas l'album cherché.
        resultats = [sortie("instru", "Bloodlust (instrumental)", 11, groupe="rg-i"), sortie("album", "Bloodlust", 11, groupe="rg-a")]
        choix = self.choisir(resultats, 11, "Bloodlust")
        self.assertEqual((choix.release["id"], choix.rivals), ("album", []))

    def test_deux_albums_du_meme_titre_posent_la_question(self):
        resultats = [sortie("a", "Body Count", 17, groupe="rg-1"), sortie("b", "Body Count", 17, groupe="rg-2")]
        choix = self.choisir(resultats, 17, "Body Count")
        self.assertEqual([r["id"] for r in choix.rivals], ["b"])

    def test_titres_trop_eloignes(self):
        choix = self.choisir([sortie("x", "Tout autre chose", 12)], 12, "Merciless")
        self.assertIsNone(choix.release)
        self.assertIn("trop éloignés", choix.reason)

    def test_aucun_resultat(self):
        self.assertEqual(self.choisir([], 12).reason, "aucun résultat")


class TestAppariement(unittest.TestCase):
    def test_numeros_des_tags(self):
        entrees = [album.entry_for(Path(f"{n}.flac"), meta(f"TRACKNUMBER={n}/3")) for n in (3, 1, 2)]
        places, raison = album.match_tracks(entrees, OUTRUN)
        self.assertEqual(raison, "")
        self.assertEqual(places[Path("3.flac")][1]["title"], "Protovision")

    def test_dossier_de_disque_prime_sur_le_tag(self):
        # Le CD bonus se dit "disque 1" dans ses tags ; rangé dans CD2, c'est le disque 2.
        entrees = [album.entry_for(Path("CD1/01.flac"), meta("TRACKNUMBER=1", "DISCNUMBER=1"), 1), album.entry_for(Path("CD1/02.flac"), meta("TRACKNUMBER=2"), 1), album.entry_for(Path("CD2/01.flac"), meta("TRACKNUMBER=1", "DISCNUMBER=1"), 2)]
        places, _ = album.match_tracks(entrees, DOUBLE)
        self.assertEqual(places[Path("CD2/01.flac")][1]["title"], "Alive 1997")

    def test_numerotation_continue(self):
        entrees = [album.entry_for(Path(f"0{n} - x.flac"), meta()) for n in (1, 2, 3)]
        places, _ = album.match_tracks(entrees, DOUBLE)
        self.assertEqual(places[Path("03 - x.flac")][1]["title"], "Alive 1997")

    def test_disque_et_piste_dans_le_nom(self):
        entree = album.entry_for(Path("Daft Punk - Alive - 02-01 Alive 1997.flac"), meta())
        self.assertEqual((entree.disc, entree.track), (2, 1))

    def test_titre_quand_le_numero_manque(self):
        entrees = [album.entry_for(Path("Blizzard.flac"), meta("TITLE=Blizzard")), album.entry_for(Path("a.flac"), meta("TRACKNUMBER=1"))]
        places, raison = album.match_tracks(entrees, OUTRUN)
        self.assertEqual((raison, places[Path("Blizzard.flac")][1]["title"]), ("", "Blizzard"))

    def test_numero_en_double_departage_par_le_titre(self):
        entrees = [album.entry_for(Path("a.flac"), meta("TRACKNUMBER=1", "TITLE=Prelude")), album.entry_for(Path("b.flac"), meta("TRACKNUMBER=1", "TITLE=Protovision"))]
        places, _ = album.match_tracks(entrees, OUTRUN)
        self.assertEqual(places[Path("b.flac")][1]["title"], "Protovision")

    def test_numero_d_une_autre_edition_cede_au_titre(self):
        # Mesuré sur "La fête est finie" : des fichiers numérotés 2-12... par une édition à 25 pistes. Le numéro 3 tomberait sur "Protovision" ; le titre dit "Prelude".
        entrees = [album.entry_for(Path("a.flac"), meta("TRACKNUMBER=3", "TITLE=Prelude")), album.entry_for(Path("b.flac"), meta("TRACKNUMBER=9", "TITLE=Blizzard")), album.entry_for(Path("c.flac"), meta("TRACKNUMBER=1", "TITLE=Protovision"))]
        places, raison = album.match_tracks(entrees, OUTRUN)
        self.assertEqual(raison, "")
        self.assertEqual([places[Path(f"{n}.flac")][1]["title"] for n in "abc"], ["Prelude", "Blizzard", "Protovision"])

    def test_titre_different_au_bon_numero_garde_sa_place(self):
        entrees = [album.entry_for(Path("a.flac"), meta("TRACKNUMBER=1", "TITLE=Intro")), album.entry_for(Path("b.flac"), meta("TRACKNUMBER=2", "TITLE=Blizzard")), album.entry_for(Path("c.flac"), meta("TRACKNUMBER=3", "TITLE=Protovision"))]
        places, raison = album.match_tracks(entrees, OUTRUN)
        self.assertEqual((raison, places[Path("a.flac")][1]["title"]), ("", "Prelude"))

    def test_un_fichier_sans_piste_refuse_l_album(self):
        entrees = [album.entry_for(Path("a.flac"), meta("TRACKNUMBER=1")), album.entry_for(Path("zz.flac"), meta("TITLE=Rien a voir"))]
        places, raison = album.match_tracks(entrees, OUTRUN)
        self.assertEqual(places, {})
        self.assertIn("zz.flac", raison)

    def test_duree_qui_ne_colle_pas(self):
        entree = album.entry_for(Path("a.flac"), meta("TITLE=Prelude", duree=120))
        self.assertIn("durée 120 s contre 200 s", album.entry_notes(entree, piste(1, "Prelude"))[0])

    def test_rien_a_dire(self):
        entree = album.entry_for(Path("a.flac"), meta("TITLE=Prelude", duree=201))
        self.assertEqual(album.entry_notes(entree, piste(1, "Prelude")), [])


class TestTagsVises(unittest.TestCase):
    def tags(self, position=1, groupe=None, **options):
        medium = OUTRUN["media"][0]
        return album.target_tags(OUTRUN, groupe, medium, medium["tracks"][position - 1], **options)

    def valeurs(self, tags, cle):
        return [v for k, v in tags if k == cle]

    def test_piste_et_album(self):
        tags = dict(self.tags())
        self.assertEqual((tags["TITLE"], tags["ALBUM"], tags["TRACKNUMBER"], tags["TRACKTOTAL"], tags["DISCTOTAL"]), ("Prelude", "OutRun", "1", "3", "1"))
        self.assertEqual((tags["DATE"], tags["ORIGINALDATE"], tags["ORIGINALYEAR"]), ("2013-02-25", "2013-02-22", "2013"))
        self.assertEqual((tags["MUSICBRAINZ_ALBUMID"], tags["MUSICBRAINZ_TRACKID"], tags["MUSICBRAINZ_RELEASETRACKID"]), ("rel-1", "r1", "t1"))

    def test_artistes_credites_avec_liaison(self):
        tags = self.tags(3)
        self.assertEqual(self.valeurs(tags, "ARTIST"), ["Kavinsky feat. Havoc"])
        self.assertEqual(self.valeurs(tags, "ALBUMARTIST"), ["Kavinsky"])
        self.assertEqual(self.valeurs(tags, "MUSICBRAINZ_ARTISTID"), ["art-1", "art-2"])

    def test_artiste_impose_remplace_le_credit_qui_le_designe(self):
        tags = self.tags(3, artist="Kavinsky (officiel)")
        self.assertEqual(self.valeurs(tags, "ARTIST"), ["Kavinsky (officiel) feat. Havoc"])
        self.assertEqual(self.valeurs(tags, "ALBUMARTIST"), ["Kavinsky (officiel)"])
        self.assertEqual(self.valeurs(tags, "ARTISTSORT"), ["Kavinsky feat. Havoc"])
        self.assertEqual(self.valeurs(tags, "MUSICBRAINZ_ARTISTID"), ["art-1", "art-2"])

    def test_artiste_impose_retire_les_invites_de_tout_l_album(self):
        def credit(ident, nom, liaison):
            return {"name": nom, "joinphrase": liaison, "artist": {"id": ident, "name": nom, "sort-name": nom}}
        tous = [credit("uv", "Ultra Vomit", " feat. "), credit("a", "Andréas", ", "), credit("b", "Rico", "")]
        sortie = dict(OUTRUN, **{"artist-credit": tous})
        sortie["media"] = [{"position": 1, "format": "CD", "track-count": 2, "tracks": [
            piste(1, "Kings", **{"artist-credit": tous}),
            piste(2, "Mouss", **{"artist-credit": tous[:2] + [credit("b", "Rico", ", "), credit("m", "Mouss de Mass", "")]})]}]
        def etiquettes(i):
            return album.target_tags(sortie, None, sortie["media"][0], sortie["media"][0]["tracks"][i], artist="Ultra Vomit")
        self.assertEqual(self.valeurs(etiquettes(0), "ARTIST"), ["Ultra Vomit"])
        self.assertEqual(self.valeurs(etiquettes(0), "ALBUMARTIST"), ["Ultra Vomit"])
        self.assertEqual(self.valeurs(etiquettes(0), "MUSICBRAINZ_ALBUMARTISTID"), ["uv"])
        self.assertEqual(self.valeurs(etiquettes(1), "ARTIST"), ["Ultra Vomit feat. Mouss de Mass"])
        self.assertEqual(self.valeurs(etiquettes(1), "MUSICBRAINZ_ARTISTID"), ["uv", "m"])
        sans = album.target_tags(sortie, None, sortie["media"][0], sortie["media"][0]["tracks"][0])
        self.assertEqual(self.valeurs(sans, "ARTIST"), ["Ultra Vomit feat. Andréas, Rico"])

    def test_artiste_impose_sans_ressemblance_ne_change_rien(self):
        self.assertEqual(self.tags(3, artist="Daft Punk"), self.tags(3))

    def test_variantes_d_ecriture_d_un_meme_artiste(self):
        def credit(nom):
            return {"name": nom, "joinphrase": "", "artist": {"id": "x", "name": "Hubert-Félix Thiéfaine", "sort-name": "Thiéfaine, Hubert-Félix"}}
        for ecrit in ("H.F. Thiéfaine", "Thiéfaine", "Hubert F Thiéfaine"):
            self.assertEqual(album.credit_name([credit(ecrit)], artist="Hubert-Félix Thiéfaine"), "Hubert-Félix Thiéfaine")
        duo = [dict(credit("Thiéfaine"), joinphrase=" / "), {"name": "Mairet", "joinphrase": "", "artist": {"id": "y", "name": "Mairet", "sort-name": "Mairet"}}]
        self.assertEqual(album.credit_name(duo, artist="Hubert-Félix Thiéfaine"), "Hubert-Félix Thiéfaine / Mairet")

    def test_valeurs_multiples_sans_doublon(self):
        tags = self.tags()
        self.assertEqual(self.valeurs(tags, "LABEL"), ["Record Makers", "Vertigo"])
        self.assertEqual(self.valeurs(tags, "CATALOGNUMBER"), ["00602537320233"])
        self.assertEqual(self.valeurs(tags, "RELEASETYPE"), ["album", "live"])

    def test_genres_les_plus_votes(self):
        groupe = dict(OUTRUN["release-group"], genres=[{"name": "synthwave", "count": 9}, {"name": "electronic", "count": 3}, {"name": "house", "count": 1}, {"name": "french house", "count": 2}])
        self.assertEqual(self.valeurs(self.tags(groupe=groupe), "GENRE"), ["Synthwave", "Electronic", "French house"])
        self.assertEqual(self.valeurs(self.tags(groupe=groupe, with_genres=False), "GENRE"), [])

    def test_aucune_valeur_vide(self):
        self.assertTrue(all(v for _, v in self.tags()))


class TestFusion(unittest.TestCase):
    VISES = [("TITLE", "Prelude"), ("ALBUM", "OutRun"), ("MUSICBRAINZ_ALBUMID", "rel-1")]

    def test_ce_qui_ne_vient_pas_de_musicbrainz_reste(self):
        existant = [("Title", "prelude"), ("REPLAYGAIN_TRACK_GAIN", "-9.5 dB"), ("LYRICS", "..."), ("ISRC", "FRS711200240")]
        fusion = album.merge(existant, self.VISES)
        self.assertEqual(fusion, self.VISES + [("REPLAYGAIN_TRACK_GAIN", "-9.5 dB"), ("LYRICS", "..."), ("ISRC", "FRS711200240")])

    def test_cles_d_edition_perimees_retirees(self):
        # Un code-barres resté d'une autre édition mentirait.
        fusion = album.merge([("BARCODE", "123"), ("MUSICBRAINZ_TRACKID", "vieux"), ("YEAR", "2005")], self.VISES)
        self.assertEqual(fusion, self.VISES)

    def test_genre_ecrit_a_la_main_garde_si_la_base_n_en_donne_pas(self):
        self.assertIn(("GENRE", "Crossover thrash"), album.merge([("GENRE", "Crossover thrash")], self.VISES))
        self.assertNotIn(("GENRE", "Crossover thrash"), album.merge([("GENRE", "Crossover thrash")], self.VISES + [("GENRE", "Rap metal")]))

    def test_differences(self):
        diffs = album.differences([("title", "Prelude"), ("ALBUM", "Outrun"), ("YEAR", "2013")], self.VISES)
        self.assertEqual(diffs, [("ALBUM", ["Outrun"], ["OutRun"]), ("MUSICBRAINZ_ALBUMID", [], ["rel-1"]), ("YEAR", ["2013"], [])])

    def test_ordre_des_valeurs_multiples_indifferent(self):
        vises = [("LABEL", "Vertigo"), ("LABEL", "Record Makers")]
        self.assertEqual(album.differences([("LABEL", "Record Makers"), ("LABEL", "Vertigo")], vises), [])

    def test_conforme_apres_fusion(self):
        existant = [("TITLE", "x"), ("BARCODE", "1"), ("REPLAYGAIN_ALBUM_GAIN", "-1 dB")]
        self.assertEqual(album.differences(album.merge(existant, self.VISES), self.VISES), [])


if __name__ == "__main__":
    unittest.main()
