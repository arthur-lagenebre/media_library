"""Métadonnées d'un .mp3 (aucun outil externe requis).

Les fichiers d'essai sont fabriqués octet par octet, sans passer par le module testé : un écrivain qui se trompe et un lecteur qui se trompe de la même façon se donneraient raison l'un l'autre.
"""

import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.music import album as albums
from libraries.music import mp3, tags
from tests.test_album import OUTRUN

TRAME_AUDIO = b"\xff\xfb\x90\x00" + bytes(413)         # MPEG 1, couche III, 128 kbit/s, 44,1 kHz, stéréo : 417 octets
SON = TRAME_AUDIO * 40                                 # 40 trames, 1,0425 s ; seul compte que le son ne bouge pas
MBID = "4e5d9f0c-09b6-42bf-b495-e2d7cc288bf6"


def synchrosur(n):
    return bytes((n >> shift) & 0x7F for shift in (21, 14, 7, 0))


def texte(valeurs, codage=3):
    """Corps d'une trame de texte : le codage, puis les valeurs séparées par un terminateur."""
    if codage == 1:
        return bytes([1]) + b"\x00\x00".join(b"\xff\xfe" + v.encode("utf-16-le") for v in valeurs)
    return bytes([codage]) + b"\x00".join(v.encode("utf-8" if codage == 3 else "latin-1") for v in valeurs)


def txxx(description, valeurs, codage=3):
    return texte([description], codage) + (b"\x00\x00" if codage == 1 else b"\x00") + texte(valeurs, codage)[1:]


def image(donnees, genre=3, mime=b"image/jpeg"):
    return b"\x00" + mime + b"\x00" + bytes([genre]) + b"\x00" + donnees


def trame(identifiant, corps, version=4, indicateurs=(0, 0)):
    taille = synchrosur(len(corps)) if version == 4 else len(corps).to_bytes(4, "big")
    return identifiant.encode() + taille + bytes(indicateurs) + corps


def etiquette(trames, version=4, padding=100, indicateurs=0):
    corps = b"".join(trames) + bytes(padding)
    return b"ID3" + bytes([version, 0, indicateurs]) + synchrosur(len(corps)) + corps


def fichier(trames=(), version=4, padding=100, son=SON):
    """Octets d'un .mp3 : étiquette ID3 (absente sans trames ni padding), puis le son."""
    return (etiquette(list(trames), version, padding) if (trames or padding) else b"") + son


def xing(nombre_de_trames):
    """Première trame d'un VBR : un en-tête audio dont le corps porte "Xing" et le nombre de trames."""
    corps = bytearray(413)
    corps[32:36] = b"Xing"                              # 4 octets d'en-tête + 32 d'infos stéréo, moins l'en-tête déjà compté
    corps[36:40] = (1).to_bytes(4, "big")
    corps[40:44] = nombre_de_trames.to_bytes(4, "big")
    return b"\xff\xfb\x90\x00" + bytes(corps)


class Mp3TestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dossier = Path(self._tmp.name)

    def poser(self, donnees, nom="01 - Nightcall.mp3"):
        chemin = self.dossier / nom
        chemin.write_bytes(donnees)
        return chemin


class TestLecture(Mp3TestCase):
    def test_tags_en_utf8(self):
        meta = mp3.read(self.poser(fichier([trame("TIT2", texte(["Nightcall é"])), trame("TPE1", texte(["AC/DC"]))])))
        self.assertEqual(meta.comments, [("TITLE", "Nightcall é"), ("ARTIST", "AC/DC")])        # un "/" ne coupe rien
        self.assertEqual((meta.version, meta.padding), (4, 100))

    def test_id3v23_en_utf16_et_latin1(self):
        meta = mp3.read(self.poser(fichier([trame("TIT2", texte(["Été"], 1), 3), trame("TALB", texte(["Été"], 0), 3)], version=3)))
        self.assertEqual(meta.comments, [("TITLE", "Été"), ("ALBUM", "Été")])
        self.assertEqual(meta.version, 3)

    def test_valeurs_multiples_separees_par_un_octet_nul(self):
        meta = mp3.read(self.poser(fichier([trame("TCON", texte(["Synthwave", "Electronic"]))])))
        self.assertEqual(meta.values("GENRE"), ["Synthwave", "Electronic"])

    def test_valeurs_multiples_en_utf16(self):
        meta = mp3.read(self.poser(fichier([trame("TCON", texte(["Synthwave", "Electronic"], 1))])))
        self.assertEqual(meta.values("GENRE"), ["Synthwave", "Electronic"])

    def test_numero_et_total_de_piste_et_de_disque(self):
        meta = mp3.read(self.poser(fichier([trame("TRCK", texte(["3/13"])), trame("TPOS", texte(["2/2"]))])))
        self.assertEqual(meta.first("TRACKNUMBER"), "3")
        self.assertEqual((meta.first("TRACKTOTAL"), meta.first("TOTALTRACKS")), ("13", "13"))
        self.assertEqual((meta.first("DISCNUMBER"), meta.first("DISCTOTAL"), meta.first("TOTALDISCS")), ("2", "2", "2"))

    def test_numero_seul(self):
        meta = mp3.read(self.poser(fichier([trame("TRCK", texte(["3"]))])))
        self.assertEqual(meta.comments, [("TRACKNUMBER", "3")])

    def test_trames_txxx_sous_leur_nom_vorbis(self):
        meta = mp3.read(self.poser(fichier([trame("TXXX", txxx("MusicBrainz Album Id", [MBID])), trame("TXXX", txxx("REPLAYGAIN_TRACK_GAIN", ["-9.5 dB"])), trame("TXXX", txxx("MusicBrainz Artist Id", ["a", "b"]))])))
        self.assertEqual(meta.first("MUSICBRAINZ_ALBUMID"), MBID)
        self.assertEqual(meta.first("REPLAYGAIN_TRACK_GAIN"), "-9.5 dB")
        self.assertEqual(meta.values("MUSICBRAINZ_ARTISTID"), ["a", "b"])

    def test_identifiant_de_l_enregistrement(self):
        meta = mp3.read(self.poser(fichier([trame("UFID", b"http://musicbrainz.org\x00" + b"1111-2222"), trame("UFID", b"http://autre.org\x00zzz")])))
        self.assertEqual(meta.comments, [("MUSICBRAINZ_TRACKID", "1111-2222")])

    def test_date_d_id3v23(self):
        meta = mp3.read(self.poser(fichier([trame("TYER", texte(["2013"], 0), 3), trame("TDAT", texte(["2502"], 0), 3), trame("TORY", texte(["2012"], 0), 3)], version=3)))
        self.assertEqual((meta.first("DATE"), meta.first("ORIGINALYEAR")), ("2013-02-25", "2012"))

    def test_annee_seule_d_id3v23(self):
        meta = mp3.read(self.poser(fichier([trame("TYER", texte(["2013"], 0), 3)], version=3)))
        self.assertEqual(meta.first("DATE"), "2013")

    def test_date_d_id3v24(self):
        meta = mp3.read(self.poser(fichier([trame("TDRC", texte(["2013-02-25"])), trame("TDOR", texte(["2012"]))])))
        self.assertEqual((meta.first("DATE"), meta.first("ORIGINALDATE")), ("2013-02-25", "2012"))

    def test_genre_en_reference_id3v1(self):
        meta = mp3.read(self.poser(fichier([trame("TCON", texte(["(17)Rock"]))])))
        self.assertEqual(meta.values("GENRE"), ["Rock"])

    def test_image_de_face(self):
        meta = mp3.read(self.poser(fichier([trame("APIC", image(b"JPEG"))])))
        self.assertTrue(meta.has_front_cover)
        self.assertEqual((meta.pictures[0].data, meta.pictures[0].mime), (b"JPEG", "image/jpeg"))

    def test_verso_n_est_pas_une_couverture(self):
        meta = mp3.read(self.poser(fichier([trame("APIC", image(b"JPEG", genre=4))])))
        self.assertFalse(meta.has_front_cover)

    def test_debut_du_son(self):
        donnees = fichier([trame("TIT2", texte(["Nightcall"]))])
        meta = mp3.read(self.poser(donnees))
        self.assertEqual(donnees[meta.audio_offset:], SON)

    def test_fichier_sans_etiquette(self):
        meta = mp3.read(self.poser(SON))
        self.assertEqual((meta.version, meta.audio_offset, meta.comments, meta.padding), (0, 0, [], 0))

    def test_duree_d_un_debit_constant(self):
        # 40 trames de 1152 échantillons à 44,1 kHz.
        self.assertAlmostEqual(mp3.read(self.poser(fichier([trame("TIT2", texte(["x"]))]))).duration, 1.0449, places=2)

    def test_duree_lue_dans_l_en_tete_xing(self):
        meta = mp3.read(self.poser(fichier([trame("TIT2", texte(["x"]))], son=xing(1000) + SON)))
        self.assertAlmostEqual(meta.duration, 1000 * 1152 / 44100, places=3)

    def test_id3v1_de_fin_ignore_dans_la_duree(self):
        sans = mp3.read(self.poser(fichier(son=SON), "a.mp3")).duration
        avec = mp3.read(self.poser(fichier(son=SON + b"TAG" + bytes(125)), "b.mp3")).duration
        self.assertAlmostEqual(sans, avec, places=3)

    def test_etiquette_desynchronisee_id3v23(self):
        # Chaque "FF" suivi d'un octet "synchro" y reçoit un "00" : la taille des trames compte l'octet ajouté.
        corps = trame("TIT2", texte(["x"], 0), 3) + trame("APIC", image(b"\xff\xd8\xff\xe0"), 3)
        brut = corps.replace(b"\xff", b"\xff\x00")
        donnees = b"ID3\x03\x00\x80" + synchrosur(len(brut)) + brut + SON
        meta = mp3.read(self.poser(donnees))
        self.assertEqual((meta.first("TITLE"), meta.pictures[0].data), ("x", b"\xff\xd8\xff\xe0"))

    def test_trame_compressee_d_id3v23(self):
        corps = len(texte(["Nightcall"], 0)).to_bytes(4, "big") + zlib.compress(texte(["Nightcall"], 0))
        meta = mp3.read(self.poser(fichier([trame("TIT2", corps, 3, (0, 0x80))], version=3)))
        self.assertEqual(meta.first("TITLE"), "Nightcall")

    def test_trame_chiffree_ecartee(self):
        meta = mp3.read(self.poser(fichier([trame("TIT2", b"\x01" + texte(["x"]), 3, (0, 0x40))], version=3)))
        self.assertEqual(meta.comments, [])

    def test_en_tete_etendu_saute(self):
        corps = (6).to_bytes(4, "big") + bytes(6) + trame("TIT2", texte(["x"]), 3)
        meta = mp3.read(self.poser(b"ID3\x03\x00\x40" + synchrosur(len(corps)) + corps + SON))
        self.assertEqual(meta.first("TITLE"), "x")

    def test_id3v22_refuse(self):
        with self.assertRaisesRegex(mp3.Mp3Error, "2.2"):
            mp3.read(self.poser(b"ID3\x02\x00\x00" + synchrosur(20) + bytes(20) + SON))

    def test_pas_un_mp3(self):
        with self.assertRaisesRegex(mp3.Mp3Error, "pas un fichier MP3"):
            mp3.read(self.poser(b"fLaC" + bytes(2000)))

    def test_etiquette_tronquee(self):
        with self.assertRaisesRegex(mp3.Mp3Error, "tronquee"):
            mp3.read(self.poser(fichier([trame("TIT2", texte(["x"]))])[:20]))

    def test_trame_invalide(self):
        with self.assertRaisesRegex(mp3.Mp3Error, "abimee"):
            mp3.read(self.poser(fichier([b"t\xe9te" + bytes(20)])))

    def test_chemin_absent(self):
        with self.assertRaisesRegex(mp3.Mp3Error, "lecture impossible"):
            mp3.read(self.dossier / "absent.mp3")


class TestEcriture(Mp3TestCase):
    def ecrire(self, donnees, comments, images=(), nom="01 - Nightcall.mp3"):
        chemin = self.poser(donnees, nom)
        mode = mp3.write(chemin, mp3.read(chemin), comments, list(images))
        return chemin, mode, mp3.read(chemin)

    def test_sur_place_quand_le_padding_suffit(self):
        donnees = fichier([trame("TIT2", texte(["x"]))], padding=500)
        chemin, mode, relu = self.ecrire(donnees, [("TITLE", "Nightcall"), ("ARTIST", "Kavinsky")])
        self.assertEqual(mode, "sur place")
        self.assertEqual(len(chemin.read_bytes()), len(donnees))                        # même taille : le padding a absorbé
        self.assertEqual(chemin.read_bytes()[relu.audio_offset:], SON)
        self.assertEqual(relu.comments, [("TITLE", "Nightcall"), ("ARTIST", "Kavinsky")])

    def test_recopie_quand_ca_ne_tient_pas(self):
        donnees = fichier([trame("TIT2", texte(["x"]))], padding=0)
        chemin, mode, relu = self.ecrire(donnees, [("TITLE", "Nightcall"), ("ARTIST", "Kavinsky")])
        self.assertEqual(mode, "recopie")
        self.assertEqual(chemin.read_bytes()[relu.audio_offset:], SON)
        self.assertEqual(relu.padding, mp3.DEFAULT_PADDING)
        self.assertEqual([p.name for p in self.dossier.iterdir()], ["01 - Nightcall.mp3"])      # aucun fichier temporaire

    def test_fichier_sans_etiquette(self):
        chemin, mode, relu = self.ecrire(SON, [("TITLE", "Nightcall")])
        self.assertEqual(mode, "recopie")
        self.assertEqual((chemin.read_bytes()[relu.audio_offset:], relu.version), (SON, 4))

    def test_second_ecriture_sur_place(self):
        chemin, _, relu = self.ecrire(SON, [("TITLE", "Nightcall")])
        avant = chemin.read_bytes()
        mode = mp3.write(chemin, relu, relu.comments, relu.pictures)
        self.assertEqual((mode, chemin.read_bytes()), ("sur place", avant))

    def test_pochette_ecrite_et_relue(self):
        chemin, _, relu = self.ecrire(SON, [("TITLE", "x")], [tags.front_cover(b"\xff\xd8JPEG")])
        self.assertTrue(relu.has_front_cover)
        self.assertEqual(relu.pictures[0].data, b"\xff\xd8JPEG")

    def test_tags_relus_a_l_identique(self):
        comments = [("TITLE", "Nightcall é"), ("ARTIST", "AC/DC"), ("TRACKNUMBER", "3"), ("TRACKTOTAL", "13"), ("TOTALTRACKS", "13"), ("DISCNUMBER", "1"), ("DISCTOTAL", "1"), ("TOTALDISCS", "1"), ("DATE", "2013-02-25"), ("ORIGINALDATE", "2012"), ("ORIGINALYEAR", "2012"), ("GENRE", "Synthwave"), ("GENRE", "Electronic"), ("LABEL", "Record Makers"), ("MEDIA", "CD"), ("RELEASETYPE", "album"), ("RELEASETYPE", "soundtrack"), ("RELEASESTATUS", "official"), ("RELEASECOUNTRY", "FR"), ("BARCODE", "123"), ("CATALOGNUMBER", "RM1"), ("MUSICBRAINZ_ALBUMID", MBID), ("MUSICBRAINZ_ARTISTID", "a"), ("MUSICBRAINZ_ARTISTID", "b"), ("MUSICBRAINZ_TRACKID", "1111"), ("REPLAYGAIN_TRACK_GAIN", "-9.5 dB")]
        _, _, relu = self.ecrire(SON, comments)
        self.assertEqual(sorted(relu.comments), sorted(comments))

    def test_les_tags_vises_par_musicbrainz_ne_different_plus_une_fois_ecrits(self):
        release, medium = OUTRUN, OUTRUN["media"][0]
        cible = albums.target_tags(release, {"id": "rg-1", "primary-type": "Album", "genres": [{"name": "synthwave", "count": 5}]}, medium, medium["tracks"][2])
        _, _, relu = self.ecrire(SON, albums.merge([], cible))
        self.assertEqual(albums.differences(relu.comments, cible), [])

    def test_tags_non_geres_conserves(self):
        # ReplayGain, paroles, commentaires, notes : rien de tout ça ne vient de MusicBrainz.
        paroles, commentaire, note, gain = trame("USLT", b"\x03eng\x00" + b"la la la"), trame("COMM", b"\x03eng\x00\x00" + b"super"), trame("POPM", b"a@b.c\x00\xc4\x00\x00\x00\x01"), trame("TXXX", txxx("REPLAYGAIN_TRACK_GAIN", ["-9.5 dB"]))
        donnees = fichier([trame("TIT2", texte(["x"])), paroles, commentaire, note, gain, trame("TCOM", texte(["Vincent Belorgey"]))], padding=0)
        _, _, relu = self.ecrire(donnees, [("TITLE", "Nightcall"), ("REPLAYGAIN_TRACK_GAIN", "-9.5 dB")])
        kept = {f.id: f.body for f in relu.frames}
        self.assertEqual((kept["USLT"], kept["COMM"], kept["POPM"]), (paroles[10:], commentaire[10:], note[10:]))
        self.assertEqual(kept["TCOM"], texte(["Vincent Belorgey"]))
        self.assertEqual(relu.first("REPLAYGAIN_TRACK_GAIN"), "-9.5 dB")

    def test_id3v23_converti_en_2_4(self):
        anciennes = [trame("TIT2", texte(["Old"], 1), 3), trame("TYER", texte(["2010"], 0), 3), trame("TDAT", texte(["0102"], 0), 3), trame("IPLS", texte(["producer", "Kavinsky"], 0), 3), trame("TRDA", texte(["x"], 0), 3), trame("TSIZ", texte(["1"], 0), 3), trame("COMM", b"\x00eng\x00\x00" + b"hello", 3)]
        _, _, relu = self.ecrire(fichier(anciennes, version=3), [("TITLE", "Nightcall"), ("DATE", "2013-02-25")])
        ids = [f.id for f in relu.frames]
        self.assertEqual(relu.version, 4)
        self.assertIn("TIPL", ids)
        self.assertIn("COMM", ids)
        for abandonnee in ("TYER", "TDAT", "IPLS", "TRDA", "TSIZ"):
            self.assertNotIn(abandonnee, ids)
        self.assertEqual(relu.first("DATE"), "2013-02-25")

    def test_ancien_identifiant_remplace_pas_dedouble(self):
        donnees = fichier([trame("TXXX", txxx("MusicBrainz Album Id", ["ancien"])), trame("UFID", b"http://musicbrainz.org\x00ancien")])
        _, _, relu = self.ecrire(donnees, [("MUSICBRAINZ_ALBUMID", MBID), ("MUSICBRAINZ_TRACKID", "nouveau")])
        self.assertEqual((relu.values("MUSICBRAINZ_ALBUMID"), relu.values("MUSICBRAINZ_TRACKID")), ([MBID], ["nouveau"]))

    def test_etiquette_id3v1_de_fin_intacte(self):
        fin = b"TAG" + b"Ancien titre".ljust(30, b"\x00") + bytes(95)
        chemin, _, relu = self.ecrire(fichier([trame("TIT2", texte(["x"]))], padding=0, son=SON + fin), [("TITLE", "Nightcall")])
        self.assertEqual(chemin.read_bytes()[relu.audio_offset:], SON + fin)

    def test_valeur_vide_ecartee(self):
        _, _, relu = self.ecrire(SON, [("TITLE", "x"), ("ARTIST", "")])
        self.assertEqual(relu.comments, [("TITLE", "x")])

    def test_echec_d_ecriture_laisse_l_original(self):
        chemin = self.poser(SON)
        meta = mp3.read(chemin)
        with self.assertRaises(mp3.Mp3Error):
            mp3.write(chemin, meta, [("TITLE", "x")], [tags.Picture(3, "image/jpeg", bytes(mp3.MAX_TAG + 1))])
        self.assertEqual(chemin.read_bytes(), SON)


class TestFormatsDistingues(Mp3TestCase):
    def test_aucune_limite_flac_pour_un_mp3(self):
        meta = mp3.read(self.poser(fichier([trame("TIT2", texte(["x"]))])))
        self.assertEqual((meta.bloated, meta.heavy_header), (False, False))


if __name__ == "__main__":
    unittest.main()
