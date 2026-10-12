"""La médiathèque musicale : lecture des tags d'une piste, albums, pistes manquantes, rangement par artiste, catalogue."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.music import flac, library
from tests.test_flac import fichier, image


def piste(dossier, nom, *, title="Titre", number=1, total=None, artist="Daft Punk", albumartist=None, album="Discovery",
          date="2001-03-12", disc=None, disctotal=None, genres=("Electronic",), mbid="", label="Virgin", cover=False, extra=()):
    """Écrit un .flac étiqueté sous `dossier`, avec les clés de Picard."""
    lignes = [f"TITLE={title}", f"ARTIST={artist}", f"ALBUM={album}", f"TRACKNUMBER={number}"]
    if albumartist is not False:
        lignes.append(f"ALBUMARTIST={albumartist or artist}")
    if total:
        lignes.append(f"TRACKTOTAL={total}")
    if date:
        lignes.append(f"DATE={date}")
    if disc:
        lignes.append(f"DISCNUMBER={disc}")
    if disctotal:
        lignes.append(f"DISCTOTAL={disctotal}")
    lignes += [f"GENRE={g}" for g in genres]
    if label:
        lignes.append(f"LABEL={label}")
    if mbid:
        lignes.append(f"MUSICBRAINZ_ALBUMID={mbid}")
    lignes += list(extra)
    blocs = [(flac.PICTURE, image(b"JPEGDATA"))] if cover else []
    chemin = Path(dossier) / nom
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(fichier(lignes, extra=blocs))
    return chemin


MBID = "4e5d9f0c-09b6-42bf-b495-e2d7cc288bf6"


class MediathequeTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.racine = Path(self._tmp.name)

    def lire(self):
        albums = library.scan(self.racine)
        for release in albums:
            for track in release.tracks:
                library.read_info(track)
        return albums


class TestLectureDUnePiste(MediathequeTestCase):
    def test_tags_retenus(self):
        piste(self.racine / "Discovery", "01 - One More Time.flac", title="One More Time", number=1, total=14, mbid=MBID, cover=True)
        track = self.lire()[0].tracks[0]
        self.assertEqual((track.title, track.number, track.disc), ("One More Time", 1, 1))
        self.assertEqual(track.info["albumartist"], "Daft Punk")
        self.assertEqual(track.info["year"], "2001")
        self.assertEqual(track.info["tracktotal"], 14)
        self.assertEqual(track.info["mbid"], MBID)
        self.assertEqual(track.info["genres"], ["Electronic"])
        self.assertEqual(track.info["duration"], 10.0)
        self.assertTrue(track.info["cover"])

    def test_total_colle_au_numero(self):
        piste(self.racine / "A", "01.flac", number="3/12")
        self.assertEqual(self.lire()[0].tracks[0].info["tracktotal"], 12)

    def test_piste_jamais_etiquetee_garde_sa_place(self):
        chemin = self.racine / "Vrac" / "07 - Sans tags.flac"
        chemin.parent.mkdir()
        chemin.write_bytes(fichier(lignes=()))
        track = self.lire()[0].tracks[0]
        self.assertEqual((track.title, track.number), ("07 - Sans tags", 7))
        self.assertFalse(track.info["mbid"])

    def test_genres_separes_par_des_points_virgules(self):
        piste(self.racine / "A", "01.flac", genres=("Hip-Hop; Rap",))
        self.assertEqual(self.lire()[0].tracks[0].info["genres"], ["Hip-Hop", "Rap"])

    def test_fichier_illisible_garde_son_erreur(self):
        chemin = self.racine / "A" / "01.flac"
        chemin.parent.mkdir()
        chemin.write_bytes(b"pas un flac")
        track = self.lire()[0].tracks[0]
        self.assertTrue(track.error)
        self.assertEqual(track.info, {})

    def test_pochette_de_face_avant_les_autres(self):
        chemin = piste(self.racine / "A", "01.flac")
        chemin.write_bytes(fichier(["TITLE=x"], extra=[(flac.PICTURE, image(b"BACK", kind=4)), (flac.PICTURE, image(b"FRONT", kind=3))]))
        track = self.lire()[0].tracks[0]
        self.assertEqual(library.read_cover(track), b"FRONT")


ARTISTE = "056e4f3e-765f-4e34-b4ce-4c2d3ce6f1d6"
AUTRE_ARTISTE = "a3a5f1f9-3b3e-4e0c-8f3a-0d6a0c6e2b11"


class TestArtiste(MediathequeTestCase):
    def test_identifiant_musicbrainz_de_l_artiste(self):
        piste(self.racine / "A", "01.flac", extra=(f"MUSICBRAINZ_ALBUMARTISTID={ARTISTE.upper()}",))
        release = self.lire()[0]
        self.assertEqual(release.tracks[0].info["artistid"], ARTISTE)
        self.assertEqual(release.artist_mbid, ARTISTE)

    def test_plusieurs_artistes_credites_aucun_identifiant(self):
        piste(self.racine / "A", "01.flac", extra=(f"MUSICBRAINZ_ALBUMARTISTID={ARTISTE}", f"MUSICBRAINZ_ALBUMARTISTID={AUTRE_ARTISTE}"))
        self.assertEqual(self.lire()[0].artist_mbid, "")

    def test_identifiant_invalide_ignore(self):
        piste(self.racine / "A", "01.flac", extra=("MUSICBRAINZ_ALBUMARTISTID=pas-un-uuid",))
        self.assertEqual(self.lire()[0].artist_mbid, "")

    def test_sans_tag_pas_d_identifiant(self):
        piste(self.racine / "A", "01.flac")
        self.assertEqual(self.lire()[0].artist_mbid, "")

    def test_albums_d_un_meme_artiste_malgre_casse_et_accents(self):
        piste(self.racine / "x" / "A", "01.flac", artist="Beyoncé", album="Lemonade", date="2016", extra=(f"MUSICBRAINZ_ALBUMARTISTID={ARTISTE}",))
        piste(self.racine / "x" / "B", "01.flac", artist="BEYONCE", album="Renaissance", date="2022")
        albums = self.lire()
        self.assertEqual(albums[0].artist_id, albums[1].artist_id)
        artiste, = library.artists(albums)
        self.assertEqual((artiste.id, artiste.mbid, artiste.years), (albums[0].artist_id, ARTISTE, ("2016", "2022")))
        self.assertEqual([r.title for r in artiste.releases], ["Lemonade", "Renaissance"])

    def test_artistes_classes_sans_accents_ni_casse(self):
        for nom in ("Zebda", "Étienne Daho", "air"):
            piste(self.racine / nom, "01.flac", artist=nom, album=nom)
        self.assertEqual([a.name for a in library.artists(self.lire())], ["air", "Étienne Daho", "Zebda"])


class TestAlbum(MediathequeTestCase):
    def test_titre_artiste_annee_label(self):
        for n in (1, 2):
            piste(self.racine / "Daft Punk" / "2001 - Discovery", f"{n:02d}.flac", number=n)
        album = self.lire()[0]
        self.assertEqual((album.title, album.artist, album.year, album.label), ("Discovery", "Daft Punk", "2001", "Virgin"))
        self.assertEqual(album.duration, 20.0)
        self.assertEqual(album.formats, ["FLAC"])

    def test_marqueurs_de_musicbrainz_ne_sont_ni_label_ni_catalogue(self):
        piste(self.racine / "A", "01.flac", label="[no label]", extra=("CATALOGNUMBER=[none]",))
        album = self.lire()[0]
        self.assertEqual((album.label, album.catalog), ("", ""))

    def test_la_valeur_la_plus_repandue_l_emporte(self):
        for n in (1, 2, 3):
            piste(self.racine / "A", f"{n:02d}.flac", number=n)
        piste(self.racine / "A", "04.flac", number=4, album="Discovery (bonus)")
        self.assertEqual(self.lire()[0].title, "Discovery")

    def test_artiste_de_l_album_avant_celui_de_la_piste(self):
        piste(self.racine / "A", "01.flac", artist="Kavinsky feat. Havoc", albumartist="Kavinsky")
        self.assertEqual(self.lire()[0].artist, "Kavinsky")

    def test_sans_tags_le_nom_du_dossier_parle(self):
        for n in (1, 2):
            (self.racine / "Kavinsky" / "2013 - Outrun").mkdir(parents=True, exist_ok=True)
            (self.racine / "Kavinsky" / "2013 - Outrun" / f"{n:02d}.flac").write_bytes(fichier(lignes=()))
        album = self.lire()[0]
        self.assertEqual((album.title, album.artist), ("Outrun", "Kavinsky"))

    def test_le_dossier_de_la_mediatheque_n_est_pas_un_artiste(self):
        (self.racine / "Vrac").mkdir()
        (self.racine / "Vrac" / "01.flac").write_bytes(fichier(lignes=()))
        self.assertEqual(self.lire()[0].artist, library.UNKNOWN_ARTIST)

    def test_identifiant_musicbrainz_seulement_si_tous_les_fichiers_le_disent(self):
        piste(self.racine / "A", "01.flac", number=1, mbid=MBID)
        piste(self.racine / "A", "02.flac", number=2)
        album = self.lire()[0]
        self.assertEqual(album.mbid, "")
        self.assertEqual(album.tagged, 1)
        piste(self.racine / "A", "02.flac", number=2, mbid=MBID)
        self.assertEqual(self.lire()[0].mbid, MBID)

    def test_genres_les_plus_presents_d_abord(self):
        piste(self.racine / "A", "01.flac", number=1, genres=("Rock", "Pop"))
        piste(self.racine / "A", "02.flac", number=2, genres=("Pop",))
        self.assertEqual(self.lire()[0].genres, ["Pop", "Rock"])

    def test_dossiers_de_disque(self):
        piste(self.racine / "A" / "CD1", "01.flac", number=1)
        piste(self.racine / "A" / "CD2", "01.flac", number=1)
        album = self.lire()[0]
        self.assertEqual([n for n, _ in album.discs], [1, 2])
        self.assertEqual(len(album.tracks), 2)

    def test_dossiers_ignores(self):
        piste(self.racine / "A", "01.flac")
        for nom in ("__Data__", "#recycle", "@eaDir", ".cache"):
            piste(self.racine / nom / "Perdu", "01.flac")
        self.assertEqual([r.rel for r in self.lire()], ["A"])

    def test_formats_non_pris_en_charge_signales(self):
        piste(self.racine / "A", "01.flac")
        (self.racine / "A" / "02.m4a").write_bytes(b"x")
        self.assertEqual(self.lire()[0].unsupported, ["02.m4a"])

    def test_dossier_sans_flac_ni_mp3_n_est_pas_un_album(self):
        (self.racine / "A").mkdir()
        (self.racine / "A" / "01.m4a").write_bytes(b"x")
        self.assertEqual(library.scan(self.racine), [])

    def test_pistes_dans_l_ordre_des_numeros(self):
        for n in (10, 2, 1):
            piste(self.racine / "A", f"{n}.flac", number=n, title=f"T{n}")
        self.assertEqual([t.title for _, tracks in self.lire()[0].discs for t in tracks], ["T1", "T2", "T10"])

    def test_cle_de_pochette_change_avec_le_fichier(self):
        piste(self.racine / "A", "01.flac", cover=True)
        avant = self.lire()[0].key
        piste(self.racine / "A", "01.flac", cover=True, title="Autre titre plus long pour changer la taille")
        self.assertNotEqual(self.lire()[0].key, avant)

    def test_sans_pochette(self):
        piste(self.racine / "A", "01.flac")
        album = self.lire()[0]
        self.assertIsNone(album.cover_track)
        self.assertTrue(album.key.endswith("-nocover"))


class TestPistesManquantes(MediathequeTestCase):
    def poser(self, numeros, total=6, **kw):
        for n in numeros:
            piste(self.racine / "A", f"{n:02d}.flac", number=n, total=total, **kw)
        return self.lire()[0]

    def test_numeros_manquants_d_apres_le_total(self):
        album = self.poser((1, 2, 5))
        self.assertEqual(album.missing(), [(1, [3, 4, 6], 6)])
        self.assertEqual(album.progress(), (3, 6))

    def test_album_complet(self):
        album = self.poser(range(1, 7))
        self.assertEqual(album.missing(), [])
        self.assertIsNone(album.progress())

    def test_sans_total_rien_n_est_dit(self):
        self.assertEqual(self.poser((1, 2), total=None).missing(), [])

    def test_piste_sans_numero_rien_n_est_dit(self):
        piste(self.racine / "A", "bonus.flac", number=0, total=6)
        piste(self.racine / "A", "01.flac", number=1, total=6)
        (self.racine / "A" / "bonus.flac").write_bytes(fichier(["TITLE=Bonus", "TRACKTOTAL=6", "ALBUM=Discovery"]))
        self.assertEqual(self.lire()[0].missing(), [])

    def test_total_absurde_ignore(self):
        self.assertEqual(self.poser((1,), total=9999).missing(), [])

    def test_un_seul_titre_annonce_n_est_pas_un_album_a_completer(self):
        self.assertEqual(self.poser((1,), total=1).missing(), [])

    def test_disque_par_disque(self):
        for disc in (1, 2):
            for n in (1, 3):
                piste(self.racine / "A", f"{disc}-{n}.flac", number=n, total=3, disc=disc, disctotal=2)
        album = self.lire()[0]
        self.assertEqual(album.missing(), [(1, [2], 3), (2, [2], 3)])
        self.assertEqual(album.missing_discs(), [])

    def test_disque_absent(self):
        for n in (1, 2):
            piste(self.racine / "A", f"{n:02d}.flac", number=n, total=2, disc=1, disctotal=3)
        self.assertEqual(self.lire()[0].missing_discs(), [2, 3])


class TestRangement(MediathequeTestCase):
    def album(self, artiste, titre, annee="2001"):
        piste(self.racine / artiste / titre, "01.flac", artist=artiste, album=titre, date=annee)

    def test_chaque_artiste_a_sa_section_meme_avec_un_seul_album(self):
        self.album("Daft Punk", "Homework", "1997")
        self.album("Daft Punk", "Discovery", "2001")
        self.album("Kavinsky", "Outrun", "2013")
        noms = [(nom, [r.title for r in releases]) for nom, releases in library.sections(self.lire())]
        self.assertEqual(noms, [("Daft Punk", ["Homework", "Discovery"]), ("Kavinsky", ["Outrun"])])

    def test_les_sections_sont_classees_par_artiste(self):
        self.album("Zebda", "Essence ordinaire")
        self.album("Étienne Daho", "Éden")
        self.album("Air", "Moon Safari")
        self.assertEqual([nom for nom, _ in library.sections(self.lire())], ["Air", "Étienne Daho", "Zebda"])

    def test_casse_et_accents_ne_separent_pas_un_artiste(self):
        self.album("Beyoncé", "Lemonade", "2016")
        piste(self.racine / "x" / "B", "01.flac", artist="BEYONCE", album="Renaissance", date="2022")
        sections = library.sections(self.lire())
        self.assertEqual(len(sections), 1)
        self.assertEqual(len(sections[0][1]), 2)

    def test_albums_d_un_artiste_par_annee(self):
        self.album("A", "Zéro", "1990")
        self.album("A", "Alpha", "2000")
        self.album("A", "Bêta", "1990")
        (_, releases), = library.sections(self.lire())
        self.assertEqual([r.title for r in releases], ["Bêta", "Zéro", "Alpha"])

    def test_aucun_album_aucune_section(self):
        self.assertEqual(library.sections([]), [])


class TestCatalogue(MediathequeTestCase):
    def test_aller_retour(self):
        piste(self.racine / "A", "01.flac", mbid=MBID)
        tracks = [t for r in self.lire() for t in r.tracks]
        chemin = self.racine / "catalog.json"
        chemin.write_text(library.dump_catalog(tracks), encoding="utf-8")
        frais = [t for r in library.scan(self.racine) for t in r.tracks]
        self.assertEqual(library.apply_catalog(frais, library.load_catalog(chemin)), [])
        self.assertEqual(frais[0].info, tracks[0].info)

    def test_fichier_modifie_est_relu(self):
        piste(self.racine / "A", "01.flac")
        tracks = [t for r in self.lire() for t in r.tracks]
        catalogue = json.loads(library.dump_catalog(tracks))["tracks"]
        piste(self.racine / "A", "01.flac", title="Un titre beaucoup plus long que le précédent")
        frais = [t for r in library.scan(self.racine) for t in r.tracks]
        self.assertEqual(library.apply_catalog(frais, catalogue), frais)

    def test_piste_illisible_absente_du_catalogue(self):
        chemin = self.racine / "A" / "01.flac"
        chemin.parent.mkdir()
        chemin.write_bytes(b"pas un flac")
        tracks = [t for r in self.lire() for t in r.tracks]
        self.assertEqual(json.loads(library.dump_catalog(tracks))["tracks"], {})

    def test_catalogue_absent_ou_d_une_autre_version(self):
        self.assertEqual(library.load_catalog(self.racine / "rien.json"), {})
        autre = self.racine / "vieux.json"
        autre.write_text(json.dumps({"version": 0, "tracks": {"x": {}}}), encoding="utf-8")
        self.assertEqual(library.load_catalog(autre), {})
        autre.write_text("pas du json", encoding="utf-8")
        self.assertEqual(library.load_catalog(autre), {})


if __name__ == "__main__":
    unittest.main()
