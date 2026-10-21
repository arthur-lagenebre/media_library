"""ebml.py face aux fichiers abîmés ou inhabituels : chaque test fabrique, octet par octet, le défaut qu'il veut voir.

Complète test_ebml.py, qui couvre un film sain et les dégâts les plus courants (troncature, index qui ment, queue rompue).
"""

import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.video import ebml
from tests.test_ebml import element, index, octets_id, simple_tag, table_cues, taille_vint, verifier, with_metadata

ENTETE = element(ebml.ENTETE_EBML, element(0x4282, b"matroska"))
INFO = element(ebml.INFO, element(ebml.TIMESTAMP_SCALE, (1000000).to_bytes(4, "big")))
VOID = element(0xEC, bytes(3))
CLUSTER = element(ebml.CLUSTER, element(0xE7, b"\x01"))
LONGUEUR_INDEX = len(index([(ebml.CUES, 0)]))           # les positions tiennent sur 8 octets fixes : un index à une entrée a toujours cette longueur


def mkv(contenu, taille_declaree=None):
    """Un fichier dont le Segment annonce exactement son contenu, sauf avis contraire."""
    taille = len(contenu) if taille_declaree is None else taille_declaree
    return ENTETE + octets_id(ebml.SEGMENT) + taille_vint(taille) + contenu


def defaut(donnees, complet=False):
    resultat = verifier(donnees, complet=complet)
    return None if resultat is None else str(resultat)


class TestEntetesIllisibles(unittest.TestCase):
    def test_en_tete_sans_taille_lisible(self):
        self.assertIn("n'annonce pas de taille lisible", defaut(octets_id(ebml.ENTETE_EBML) + b"\x00"))

    def test_segment_absent_apres_l_en_tete(self):
        self.assertIn("aucun Segment après l'en-tête EBML", defaut(ENTETE + INFO))

    def test_segment_de_taille_inconnue_est_legitime(self):
        # Un flux sans taille annoncée : la chaîne se suit jusqu'à la fin du fichier.
        donnees = ENTETE + octets_id(ebml.SEGMENT) + b"\xff" + INFO + CLUSTER
        self.assertIsNone(defaut(donnees, complet=True))

    def test_octets_manquants_avant_la_fin(self):
        self.assertIn("manquants avant la fin", defaut(mkv(INFO + CLUSTER, taille_declaree=len(INFO + CLUSTER) + 9)))

    def test_octets_en_trop_apres_la_fin(self):
        self.assertIn("en trop après la fin", defaut(mkv(INFO + CLUSTER) + b"\x00" * 5))


class TestChaineDesElements(unittest.TestCase):
    """Contrôle complet : chaque élément de niveau 1 doit tomber là où le précédent finit."""

    def complet(self, contenu):
        return defaut(mkv(contenu), complet=True)

    def test_segment_sain(self):
        self.assertIsNone(self.complet(INFO + VOID + CLUSTER))

    def test_element_illisible(self):
        self.assertIn("élément illisible", self.complet(INFO + b"\x00\x00\x00"))

    def test_identifiant_inconnu_a_ce_niveau(self):
        # 0xE7 (Timestamp) est un enfant de cluster : il n'a rien à faire ici.
        self.assertIn("inconnu à ce niveau", self.complet(INFO + element(0xE7, b"x")))

    def test_taille_illisible(self):
        self.assertIn("Cluster n'annonce pas de taille lisible", self.complet(INFO + octets_id(ebml.CLUSTER) + b"\x00"))

    def test_taille_inconnue(self):
        self.assertIn("Cluster n'annonce pas sa taille", self.complet(INFO + octets_id(ebml.CLUSTER) + b"\xff" + b"x" * 4))

    def test_element_qui_deborde_de_la_fin(self):
        defaut_vu = self.complet(INFO + octets_id(ebml.CLUSTER) + taille_vint(1000) + b"x" * 10)
        self.assertIn("Cluster déborde de la fin du fichier", defaut_vu)

    def test_bloc_de_cluster_sans_taille(self):
        cluster = element(ebml.CLUSTER, element(0xE7, b"\x01") + b"\xa3\x00")
        self.assertIn("bloc sans taille lisible", self.complet(INFO + cluster))

    def test_le_defaut_porte_sa_position(self):
        self.assertRegex(self.complet(INFO + element(0xE7, b"x")), r"\(octet \d+\)")


class TestIndexEtTableCues(unittest.TestCase):
    """Contrôle rapide : on vérifie ce que l'index annonce, sans parcourir les clusters."""

    def rapide(self, contenu):
        return defaut(mkv(contenu))

    def avec_cues(self, cues):
        """Index -> Cues, avec Info et un cluster entre les deux (positions relatives au Segment)."""
        position = LONGUEUR_INDEX + len(INFO) + len(CLUSTER)
        return index([(ebml.CUES, position)]) + INFO + CLUSTER + cues, LONGUEUR_INDEX + len(INFO)

    def test_fichier_sain_avec_un_vide_devant_l_index(self):
        # D'autres muxeurs glissent un Void avant l'index : il ne doit pas passer pour un défaut.
        position_cluster = len(VOID) + LONGUEUR_INDEX + len(INFO)
        position_cues = position_cluster + len(CLUSTER)
        contenu = VOID + index([(ebml.CUES, position_cues)]) + INFO + CLUSTER + table_cues([position_cluster])
        self.assertIsNone(self.rapide(contenu))

    def test_segment_qui_ne_commence_pas_par_un_element_connu(self):
        self.assertIn("ne commence pas par un élément connu", self.rapide(element(0xE7, b"x") + INFO))

    def test_tete_de_segment_illisible(self):
        self.assertIn("élément illisible en tête du Segment", self.rapide(b"\x00" * 20))

    def test_pas_d_index_dans_les_premiers_elements(self):
        # Sans index, la queue reste hors de portée : rien à juger, donc rien à signaler.
        self.assertIsNone(self.rapide(VOID * 4))

    def test_index_qui_cite_un_element_hors_du_fichier(self):
        self.assertIn("l'index annonce Cues hors du fichier", self.rapide(index([(ebml.CUES, 10 ** 6)]) + INFO))

    def test_repere_vers_un_element_qu_on_ne_juge_pas(self):
        self.assertIsNone(self.rapide(index([(0x7F7F, 3)]) + INFO + CLUSTER))

    def test_index_sans_cues(self):
        self.assertIsNone(self.rapide(index([(ebml.INFO, LONGUEUR_INDEX)]) + INFO + CLUSTER))

    def test_table_cues_sans_taille_lisible(self):
        position = LONGUEUR_INDEX + len(INFO)
        contenu = index([(ebml.CUES, position)]) + INFO + octets_id(ebml.CUES) + b"\x00"
        self.assertIn("table Cues illisible", self.rapide(contenu))

    def test_table_cues_vide(self):
        contenu, _ = self.avec_cues(element(ebml.CUES, b""))
        self.assertIsNone(self.rapide(contenu))

    def test_cues_qui_cite_un_cluster_hors_du_fichier(self):
        contenu, _ = self.avec_cues(table_cues([10 ** 6]))
        self.assertIn("la table Cues annonce un cluster hors du fichier", self.rapide(contenu))

    def test_cues_qui_cite_un_cluster_qui_n_y_est_pas(self):
        contenu, position_info = self.avec_cues(table_cues([LONGUEUR_INDEX]))      # c'est Info qui est là
        self.assertIn("annonce un cluster qui n'y est pas", self.rapide(contenu))


class TestPrimitives(unittest.TestCase):
    def test_entier_de_taille_invraisemblable(self):
        self.assertIsNone(ebml._entier(b"\x01\x02", 0, 0))
        self.assertIsNone(ebml._entier(bytes(9), 0, 9))
        self.assertEqual(ebml._entier(b"\x01\x02", 0, 2), 258)

    def test_entier_au_dela_du_maximum_demande(self):
        self.assertIsNone(ebml._entier(bytes(6), 0, 5, maximum=4))

    def test_enumeration_arretee_sans_bruit_sur_un_bloc_abime(self):
        self.assertEqual(list(ebml._elements(b"\x00\x00")), [])
        self.assertEqual(list(ebml._elements(element(0x81, b"abc")[:-1])), [])      # contenu tronqué
        self.assertEqual(list(ebml._elements(b"\x81\xff")), [])                        # taille inconnue : on ne devine pas

    def test_enumeration_garde_les_elements_lisibles_avant_l_accident(self):
        bloc = element(0x81, b"a") + element(0x82, b"b") + b"\x00"
        self.assertEqual([i for i, _, _ in ebml._elements(bloc)], [0x81, 0x82])

    def test_entree_d_index_sans_position_ignoree(self):
        sans_position = element(ebml.SEEK, element(ebml.SEEK_ID, octets_id(ebml.CUES)))
        sans_identifiant = element(ebml.SEEK, element(ebml.SEEK_POSITION, (5).to_bytes(8, "big")))
        complete = element(ebml.SEEK, element(ebml.SEEK_ID, octets_id(ebml.CUES)) + element(ebml.SEEK_POSITION, (5).to_bytes(8, "big")))
        self.assertEqual(ebml.reperes_seekhead(sans_position + sans_identifiant + complete, 100), [(ebml.CUES, 105)])

    def test_element_etranger_dans_un_index_ignore(self):
        etranger = element(0xEC, b"\x00\x00")
        self.assertEqual(ebml.reperes_seekhead(etranger, 0), [])

    def test_cues_en_dehors_de_la_structure_attendue_ignorees(self):
        autre = element(ebml.CUE_POINT, element(0xB3, b"\x01") + element(ebml.CUE_TRACK_POSITIONS, element(0xF7, b"\x01")))
        position_vide = element(ebml.CUE_POINT, element(ebml.CUE_TRACK_POSITIONS, element(ebml.CUE_CLUSTER_POSITION, b"")))
        etranger = element(0xEC, b"")
        bonne = element(ebml.CUE_POINT, element(ebml.CUE_TRACK_POSITIONS, element(ebml.CUE_CLUSTER_POSITION, (7).to_bytes(8, "big"))))
        self.assertEqual(ebml.clusters_de_cues(etranger + autre + position_vide + bonne, 10), [17])

    def test_lecture_exacte_se_contente_de_ce_qui_existe(self):
        import io
        self.assertEqual(ebml.lire_exact(io.BytesIO(b"abc"), 10), b"abc")
        self.assertEqual(ebml.lire_exact(io.BytesIO(b"abc"), 0), b"")

    def test_defaut_sans_position(self):
        self.assertEqual(str(ebml.Defaut("fichier vide")), "fichier vide")
        self.assertEqual(str(ebml.Defaut("coupé", 12)), "coupé (octet 12)")

    def test_fichier_vide_et_chemin_absent(self):
        self.assertEqual(defaut(b""), "fichier vide")
        with tempfile.TemporaryDirectory() as dossier:
            self.assertIn("fichier illisible", str(ebml.verifier(Path(dossier) / "absent.mkv")))


class TestFlottantsEtTextes(unittest.TestCase):
    def test_flottants_de_quatre_et_huit_octets(self):
        self.assertAlmostEqual(ebml._float(struct.pack(">f", 1.5), 0, 4), 1.5)
        self.assertAlmostEqual(ebml._float(struct.pack(">d", 2.25), 0, 8), 2.25)

    def test_flottant_d_une_autre_taille(self):
        self.assertIsNone(ebml._float(bytes(3), 0, 3))

    def test_texte_sans_ses_octets_nuls_et_tolerant_aux_octets_invalides(self):
        self.assertEqual(ebml._text(b"Dune\x00\x00", 0, 6), "Dune")
        self.assertEqual(ebml._text(b"\xff\xfeok", 0, 4), "��ok")


class TestDureeDuSegment(unittest.TestCase):
    def duree(self, *enfants):
        return ebml.parse_info(b"".join(enfants))

    def test_echelle_par_defaut_quand_info_ne_la_precise_pas(self):
        # 6 000 000 unités de 1 ms = 100 minutes.
        self.assertAlmostEqual(self.duree(element(ebml.DURATION, struct.pack(">d", 6_000_000.0))), 100.0)

    def test_echelle_precisee(self):
        # Unités de 1 µs.
        enfants = (element(ebml.TIMESTAMP_SCALE, (1000).to_bytes(2, "big")), element(ebml.DURATION, struct.pack(">f", 6e9)))
        self.assertAlmostEqual(self.duree(*enfants), 100.0, places=2)

    def test_echelle_nulle_retombe_sur_la_valeur_par_defaut(self):
        enfants = (element(ebml.TIMESTAMP_SCALE, b"\x00"), element(ebml.DURATION, struct.pack(">d", 6_000_000.0)))
        self.assertAlmostEqual(self.duree(*enfants), 100.0)

    def test_duree_absente_nulle_ou_negative(self):
        self.assertIsNone(self.duree())
        self.assertIsNone(self.duree(element(ebml.DURATION, struct.pack(">d", 0.0))))
        self.assertIsNone(self.duree(element(ebml.DURATION, struct.pack(">d", -5.0))))

    def test_duree_d_une_taille_incomprehensible(self):
        self.assertIsNone(self.duree(element(ebml.DURATION, bytes(3))))


class TestTagsDuSegment(unittest.TestCase):
    def tags(self, *blocs):
        return ebml.parse_tags(b"".join(element(ebml.TAG, b) for b in blocs))

    def test_niveau_par_defaut_sans_cible(self):
        self.assertEqual(self.tags(simple_tag("TITLE", "Dune")), {(50, "TITLE", "Dune")})

    def test_niveau_nul_vaut_le_niveau_par_defaut(self):
        cible = element(ebml.TARGETS, element(ebml.TARGET_TYPE_VALUE, b"\x00"))
        self.assertEqual(self.tags(cible + simple_tag("TITLE", "Dune")), {(50, "TITLE", "Dune")})

    def test_niveau_de_collection(self):
        cible = element(ebml.TARGETS, element(ebml.TARGET_TYPE_VALUE, b"\x46"))
        self.assertEqual(self.tags(cible + simple_tag("TITLE", "Saga")), {(70, "TITLE", "Saga")})

    def test_tag_sans_valeur(self):
        simple = element(ebml.SIMPLE_TAG, element(ebml.TAG_NAME, b"EMPTY"))
        self.assertEqual(self.tags(simple), {(50, "EMPTY", "")})

    def test_element_etranger_dans_les_tags_ignore(self):
        self.assertEqual(ebml.parse_tags(element(0xEC, b"\x00") + element(ebml.TAG, simple_tag("A", "b"))), {(50, "A", "b")})

    def test_bloc_vide(self):
        self.assertEqual(ebml.parse_tags(b""), set())


class TestRecherchePuisLecture(unittest.TestCase):
    def lire(self, donnees):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "film.mkv"
            chemin.write_bytes(donnees)
            return ebml.read_metadata(chemin)

    def test_second_index_suivi_depuis_le_premier(self):
        # mkvmerge pose parfois un second index plus loin, que le premier cite : les Tags n'y sont atteints que par ce détour.
        tags = element(ebml.TAGS, element(ebml.TAG, simple_tag("TMDB", "movie/9312")))
        taille_index = len(index([(ebml.INFO, 0), (ebml.SEEK_HEAD, 0)]))
        seconde = taille_index + len(INFO) + len(CLUSTER)
        premier = index([(ebml.INFO, taille_index), (ebml.SEEK_HEAD, seconde)])
        contenu = premier + INFO + CLUSTER + index([(ebml.TAGS, seconde + len(index([(ebml.TAGS, 0)])))]) + tags
        etiquettes, _ = self.lire(mkv(contenu))
        self.assertEqual(etiquettes, {(50, "TMDB", "movie/9312")})

    def test_index_qui_se_cite_lui_meme_ne_boucle_pas(self):
        boucle = index([(ebml.SEEK_HEAD, 0)])
        etiquettes, minutes = self.lire(mkv(boucle + INFO + CLUSTER))
        self.assertEqual(etiquettes, set())

    def test_taille_aberrante_pour_info_ignoree_sans_lire(self):
        enorme = octets_id(ebml.INFO) + taille_vint(ebml.MAX_METADATA + 1, 4)
        etiquettes, minutes = self.lire(mkv(enorme + b"x" * 8))
        self.assertEqual((etiquettes, minutes), (set(), None))

    def test_octets_en_trop_n_empechent_pas_la_lecture(self):
        # Le défaut de structure est l'affaire de Verify_Files : la fiche lit ce qu'elle peut.
        etiquettes, minutes = self.lire(with_metadata() + b"\x00" * 7)
        self.assertIn((50, "TMDB", "movie/9312"), etiquettes)
        self.assertAlmostEqual(minutes, 95.5, places=3)

    def test_fichier_absent(self):
        with tempfile.TemporaryDirectory() as dossier:
            self.assertEqual(ebml.read_metadata(Path(dossier) / "absent.mkv"), (None, None))

    def test_fichier_vide(self):
        self.assertEqual(self.lire(b""), (None, None))


if __name__ == "__main__":
    unittest.main()
