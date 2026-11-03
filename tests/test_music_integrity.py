"""Contrôle d'un .flac et d'un .mp3 sans décodage (aucun outil externe requis).

Les fichiers d'essai sont fabriqués octet par octet : des trames FLAC au corps arbitraire mais au CRC-8 et au CRC-16 calculés ici, bit à bit, par une autre méthode que celle du module testé - un calcul qui se tromperait de la même façon des deux côtés se donnerait raison.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.music import integrity
from tests.test_flac import bloc, streaminfo as streaminfo_flac
from tests.test_mp3 import TRAME_AUDIO, etiquette, fichier as fichier_mp3, xing

BLOC = 4096
FREQUENCE = 44100


def crc_bit_a_bit(donnees, largeur, polynome):
    """CRC sans table ni reflet, départ 0 : la définition elle-même."""
    crc, haut = 0, 1 << (largeur - 1)
    for octet in donnees:
        crc ^= octet << (largeur - 8)
        for _ in range(8):
            crc = ((crc << 1) ^ polynome if crc & haut else crc << 1) & ((1 << largeur) - 1)
    return crc


def trame_flac(numero, taille=BLOC, variable=False, corps=bytes(range(200)) * 3, premier_echantillon=0):
    """Une trame FLAC complète : en-tête (CRC-8), corps quelconque, CRC-16. Le corps n'est pas du son, et n'a pas à l'être : seuls les CRC et l'en-tête sont lus."""
    code = {4096: 12, 192: 1, 576: 2, 1152: 3, 4608: 5}.get(taille)
    en_tete = bytes([0xFF, 0xF9 if variable else 0xF8, ((code or 7) << 4) | 9, (1 << 4) | (4 << 1)])
    en_tete += bytes([premier_echantillon if variable else numero])           # < 128 : un seul octet de numéro suffit à ces essais
    if code is None:
        en_tete += (taille - 1).to_bytes(2, "big")
    en_tete += bytes([crc_bit_a_bit(en_tete, 8, 0x07)])
    reste = en_tete + corps
    return reste + crc_bit_a_bit(reste, 16, 0x8005).to_bytes(2, "big")


def flac(trames, total, md5=bytes(16), bits=16, canaux=2, metadonnees_en_plus=b""):
    """Octets d'un .flac : STREAMINFO annonçant `total` échantillons, puis ces trames."""
    info = bytearray(streaminfo_flac(FREQUENCE, total))
    info[2:4] = BLOC.to_bytes(2, "big")
    info[12] = (info[12] & 0xF1) | ((canaux - 1) << 1) | ((bits - 1) >> 4)
    info[13] = (((bits - 1) & 0x0F) << 4) | (info[13] & 0x0F)
    info[18:34] = md5
    return b"fLaC" + bloc(0, bytes(info), last=True) + metadonnees_en_plus + b"".join(trames)


def flac_sain(nombre=10, reste=1000):
    """`nombre` trames de 4096 échantillons, puis une dernière plus courte."""
    trames = [trame_flac(n) for n in range(nombre)] + [trame_flac(nombre, reste)]
    return trames, nombre * BLOC + reste


class IntegriteTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dossier = Path(self._tmp.name)

    def poser(self, donnees, nom="01 - Piste.flac"):
        chemin = self.dossier / nom
        chemin.write_bytes(donnees)
        return chemin


class TestCrc(unittest.TestCase):
    def test_crc_8_et_16_suivent_la_definition(self):
        for donnees in (b"", b"\xff\xf8\xc9\x18\x00", bytes(range(256)) * 5, b"\x00" * 50):
            with self.subTest(len(donnees)):
                self.assertEqual(integrity.crc8(donnees), crc_bit_a_bit(donnees, 8, 0x07))
                self.assertEqual(integrity.crc16(donnees), crc_bit_a_bit(donnees, 16, 0x8005))

    def test_une_trame_entiere_a_un_crc_16_nul(self):
        self.assertEqual(integrity.crc16(trame_flac(3)), 0)


class TestFlacSain(IntegriteTestCase):
    def test_fichier_complet(self):
        trames, total = flac_sain()
        self.assertEqual(integrity.flac_defect(self.poser(flac(trames, total))), "")

    def test_taille_de_bloc_variable_numerotee_en_echantillons(self):
        # Un flux à taille variable numérote ses trames par leur premier échantillon, pas par leur rang.
        trames = [trame_flac(0, 192, variable=True, premier_echantillon=0), trame_flac(0, 192, variable=True, premier_echantillon=100)]
        self.assertEqual(integrity.flac_defect(self.poser(flac(trames, 100 + 192))), "")

    def test_nombre_d_echantillons_inconnu(self):
        # STREAMINFO à zéro : le flux ne sait pas sa longueur, il n'y a rien à comparer.
        trames, _ = flac_sain()
        self.assertEqual(integrity.flac_defect(self.poser(flac(trames, 0))), "")

    def test_fichier_plus_court_que_la_fenetre_de_lecture(self):
        trames, total = flac_sain(nombre=0, reste=192)
        self.assertEqual(integrity.flac_defect(self.poser(flac(trames, total))), "")

    def test_un_faux_depart_de_trame_dans_le_son_n_inquiete_pas(self):
        # Les octets FF F8 apparaissent dans le son : sans CRC-8 valable derrière, ce n'est pas une trame.
        faux = bytes([0xFF, 0xF8, 0xC9, 0x18, 0x05, 0x00])
        trames, total = flac_sain()
        trames[-1] = trame_flac(10, 1000, corps=faux + bytes(300))
        self.assertEqual(integrity.flac_defect(self.poser(flac(trames, total))), "")


class TestFlacAbime(IntegriteTestCase):
    def test_coupe_au_milieu_d_une_trame(self):
        trames, total = flac_sain()
        donnees = flac(trames, total)
        message = integrity.flac_defect(self.poser(donnees[:-300]))
        self.assertIn("incomplète", message)

    def test_coupe_entre_deux_trames_est_vu_au_nombre_d_echantillons(self):
        # Le cas que le CRC ne voit pas : la dernière trame est intacte, c'est la suivante qui manque.
        trames, total = flac_sain()
        message = integrity.flac_defect(self.poser(flac(trames[:-2], total)))
        self.assertIn("s'arrête à l'échantillon", message)
        self.assertIn(f"sur {total} annoncés", message)
        self.assertIn("il manque", message)

    def test_echantillons_en_trop(self):
        trames, total = flac_sain()
        self.assertIn("de trop", integrity.flac_defect(self.poser(flac(trames, total - 2000))))

    def test_octets_ajoutes_apres_le_son(self):
        trames, total = flac_sain()
        message = integrity.flac_defect(self.poser(flac(trames, total) + b"\x12\x34\x56" * 20))
        self.assertIn("octets étrangers", message)

    def test_remplissage_nul_apres_le_son_passe_inapercu(self):
        # Le CRC-16 de FLAC part de zéro : des zéros derrière une trame entière ne le changent pas. Inoffensif, et indiscernable.
        trames, total = flac_sain()
        self.assertEqual(integrity.flac_defect(self.poser(flac(trames, total) + b"\x00" * 50)), "")

    def test_aucune_trame_apres_les_metadonnees(self):
        self.assertIn("aucune trame audio", integrity.flac_defect(self.poser(flac([], 1000))))

    def test_fichier_qui_n_est_pas_un_flac(self):
        self.assertIn("pas un fichier FLAC", integrity.flac_defect(self.poser(b"RIFF" + bytes(100))))

    def test_etiquette_id3_devant_un_flac(self):
        message = integrity.flac_defect(self.poser(etiquette([]) + flac(*flac_sain())))
        self.assertIn("étiquette ID3", message)

    def test_frequence_nulle(self):
        trames, total = flac_sain()
        donnees = bytearray(flac(trames, total))
        donnees[4 + 4 + 10:4 + 4 + 13] = bytes([0, 0, donnees[4 + 4 + 12] & 0x0F])
        self.assertIn("fréquence", integrity.flac_defect(self.poser(bytes(donnees))))

    def test_fichier_absent(self):
        self.assertIn("lecture impossible", integrity.flac_defect(self.dossier / "absent.flac"))


class TestEmpreinteFlac(IntegriteTestCase):
    def digest(self, **options):
        trames, total = flac_sain()
        return integrity.flac_digest(self.poser(flac(trames, total, **options)))

    def test_16_bits_stereo(self):
        self.assertEqual(self.digest(md5=bytes(range(1, 17))), (16, bytes(range(1, 17)).hex()))

    def test_24_bits_mono(self):
        self.assertEqual(self.digest(md5=b"\x07" * 16, bits=24, canaux=1), (24, "07" * 16))

    def test_sans_empreinte_l_encodeur_ne_l_a_pas_calculee(self):
        self.assertIsNone(self.digest(md5=bytes(16)))

    def test_largeurs_et_canaux_hors_du_connu(self):
        for options in ({"bits": 20}, {"bits": 32}, {"bits": 8}, {"canaux": 6}):
            with self.subTest(options):
                self.assertIsNone(self.digest(md5=b"\x01" * 16, **options))

    def test_fichier_illisible(self):
        self.assertIsNone(integrity.flac_digest(self.poser(b"pas un flac")))


class TestMp3Sain(IntegriteTestCase):
    def test_etiquette_et_trames(self):
        self.assertEqual(integrity.mp3_defect(self.poser(fichier_mp3(), "a.mp3")), "")

    def test_sans_etiquette(self):
        self.assertEqual(integrity.mp3_defect(self.poser(fichier_mp3(padding=0), "a.mp3")), "")

    def test_nombre_de_trames_annonce_et_trouve(self):
        # L'annonce ne compte pas la trame Xing elle-même.
        donnees = fichier_mp3(son=xing(39) + TRAME_AUDIO * 39)
        self.assertEqual(integrity.mp3_defect(self.poser(donnees, "a.mp3")), "")

    def test_etiquette_de_fin_et_remplissage_ne_sont_pas_des_defauts(self):
        for suite in (b"TAG" + bytes(125), bytes(512), b"APETAGEX" + bytes(40)):
            with self.subTest(suite[:8]):
                self.assertEqual(integrity.mp3_defect(self.poser(fichier_mp3(son=TRAME_AUDIO * 40 + suite), "a.mp3")), "")


class TestMp3Abime(IntegriteTestCase):
    def test_coupe_au_milieu_d_une_trame(self):
        message = integrity.mp3_defect(self.poser(fichier_mp3(son=(TRAME_AUDIO * 40)[:-100]), "a.mp3"))
        self.assertIn("dernière trame incomplète", message)
        self.assertIn("après 39 trames", message)
        self.assertIn("il manque 100 octets", message)

    def test_trou_au_milieu_puis_le_son_reprend(self):
        son = TRAME_AUDIO * 10 + bytes(200) + TRAME_AUDIO * 30
        message = integrity.mp3_defect(self.poser(fichier_mp3(son=son), "a.mp3"))
        self.assertIn("synchro perdue", message)
        self.assertIn("après 10 trames", message)
        self.assertIn("le son reprend 200 octets plus loin", message)

    def test_bruit_jusqu_a_la_fin(self):
        son = TRAME_AUDIO * 10 + b"\x12\x34\x56" * 200
        message = integrity.mp3_defect(self.poser(fichier_mp3(son=son), "a.mp3"))
        self.assertIn("ne revient pas", message)

    def test_coupe_pile_entre_deux_trames_est_vu_au_nombre_annonce(self):
        # La chaîne est intacte, c'est l'en-tête Xing qui sait qu'il en manque.
        message = integrity.mp3_defect(self.poser(fichier_mp3(son=xing(39) + TRAME_AUDIO * 30), "a.mp3"))
        self.assertIn("annonce 39 trames", message)

    def test_etiquette_sans_son(self):
        self.assertIn("aucune trame audio", integrity.mp3_defect(self.poser(fichier_mp3(son=b""), "a.mp3")))

    def test_fichier_qui_n_est_pas_un_mp3(self):
        self.assertIn("pas un fichier MP3", integrity.mp3_defect(self.poser(b"RIFF" + bytes(500), "a.mp3")))

    def test_fichier_absent(self):
        self.assertIn("lecture impossible", integrity.mp3_defect(self.dossier / "absent.mp3"))


if __name__ == "__main__":
    unittest.main()
