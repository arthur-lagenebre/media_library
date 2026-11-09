"""libraries/video/credits.py : --credits-only ne remplace que le casting d'un fichier déjà étiqueté, le reste des tags est recopié tel quel.

mkvextract et mkvpropedit sont simulés : on regarde le XML qui serait écrit et ce que le script en dit.
"""

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.video import credits, mkv, movietags

OPTS = mkv.Options(cover=False, date=True, audio_names=True, sub_names=True, flags=True, stats=True, image_size="w780")

# Un film déjà étiqueté avec l'ancien plafond : un seul acteur, un réalisateur, une saga, et des statistiques de piste qu'il faut garder.
FICHIER = (
    '<?xml version="1.0" encoding="UTF-8"?><Tags>'
    '<Tag><Targets><TargetTypeValue>70</TargetTypeValue></Targets><Simple><Name>TITLE</Name><String>Ma saga</String></Simple></Tag>'
    '<Tag><Targets/><Simple><Name>TITLE</Name><String>Film</String></Simple>'
    '<Simple><Name>TMDB</Name><String>movie/7</String></Simple>'
    '<Simple><Name>DIRECTOR</Name><String>Ancien</String><Simple><Name>TMDB</Name><String>person/1</String></Simple></Simple>'
    '<Simple><Name>ACTOR</Name><String>Vieux (Rôle)</String><Simple><Name>TMDB</Name><String>person/2</String></Simple></Simple>'
    '<Simple><Name>SYNOPSIS</Name><String>Un synopsis.</String></Simple></Tag>'
    '<Tag><Targets><TrackUID>42</TrackUID></Targets><Simple><Name>BPS</Name><String>640000</String></Simple></Tag></Tags>'
)


def fiche(n_acteurs):
    return {"id": 7, "title": "Film", "overview": "Un autre synopsis.", "credits": {
        "crew": [{"id": 9, "name": "Nouveau", "job": "Director", "department": "Directing"}],
        "cast": [{"id": i + 100, "name": f"Acteur{i}", "character": f"Role{i} (voice)"} for i in range(n_acteurs)]}}


def blocs(xml):
    return ElementTree.fromstring(xml).findall("Tag")


def valeurs(bloc, nom):
    return [s.findtext("String") for s in bloc.findall("Simple") if s.findtext("Name") == nom]


class TestRecredit(unittest.TestCase):
    def setUp(self):
        self.cible = movietags.movie_target(fiche(3), OPTS).tags_xml
        self.xml = credits.recredit(FICHIER, self.cible)

    def test_les_personnes_sont_remplacees_par_celles_de_la_fiche(self):
        film = blocs(self.xml)[1]
        self.assertEqual(valeurs(film, "DIRECTOR"), ["Nouveau"])
        self.assertEqual(valeurs(film, "ACTOR"), ["Acteur0 (Role0 (voice))", "Acteur1 (Role1 (voice))", "Acteur2 (Role2 (voice))"])
        self.assertEqual(credits.credit_tags(mkv.parse_tags(self.xml)), credits.credit_tags(mkv.parse_tags(self.cible)))

    def test_tout_le_reste_est_recopie(self):
        film = blocs(self.xml)[1]
        self.assertEqual(valeurs(film, "TITLE"), ["Film"])
        self.assertEqual(valeurs(film, "TMDB"), ["movie/7"])
        self.assertEqual(valeurs(film, "SYNOPSIS"), ["Un synopsis."])          # celui du fichier, pas celui de la fiche
        self.assertEqual(valeurs(blocs(self.xml)[0], "TITLE"), ["Ma saga"])    # la collection ne bouge pas
        piste = blocs(self.xml)[2]
        self.assertEqual(piste.findtext("Targets/TrackUID"), "42")             # les statistiques de piste non plus
        self.assertEqual(valeurs(piste, "BPS"), ["640000"])

    def test_les_personnes_gardent_la_place_de_l_ancienne(self):
        noms = [s.findtext("Name") for s in blocs(self.xml)[1].findall("Simple")]
        self.assertEqual(noms[:3], ["TITLE", "TMDB", "DIRECTOR"])
        self.assertEqual(noms[-1], "SYNOPSIS")

    def test_un_fichier_sans_personne_les_recoit_en_fin_de_bloc(self):
        xml = credits.recredit('<Tags><Tag><Targets/><Simple><Name>TITLE</Name><String>F</String></Simple></Tag></Tags>', self.cible)
        self.assertEqual(valeurs(blocs(xml)[0], "ACTOR")[0], "Acteur0 (Role0 (voice))")

    def test_xml_illisible_ou_sans_bloc_de_film(self):
        self.assertIsNone(credits.recredit("pas du xml", self.cible))
        self.assertIsNone(credits.recredit("", self.cible))
        self.assertIsNone(credits.recredit('<Tags><Tag><Targets><TargetTypeValue>70</TargetTypeValue></Targets></Tag></Tags>', self.cible))

    def test_deuxieme_passage_sans_effet(self):
        self.assertEqual(credits.recredit(self.xml, self.cible), self.xml)


class TestProcess(unittest.TestCase):
    TAGS = mkv.parse_tags(FICHIER)

    def traiter(self, movie=None, tags=None, verify=False, apply=False, ecriture=(0, ""), xml=FICHIER):
        self.ecrit = []
        sortie = io.StringIO()
        cible = movietags.movie_target(movie or fiche(3), OPTS)
        with mock.patch.object(credits.mkv, "read_tags_xml", lambda path: xml), \
                mock.patch.object(credits.mkv, "write_tags", lambda path, tags_xml: self.ecrit.append((Path(path).name, tags_xml)) or ecriture), redirect_stdout(sortie):
            resultat = credits.process(Path("film.mkv"), self.TAGS if tags is None else tags, cible, verify, apply)
        self.sortie = sortie.getvalue()
        return resultat

    def test_simulation_montre_l_ecart_sans_ecrire(self):
        self.assertEqual(self.traiter(), (0, 0))
        self.assertEqual(self.ecrit, [])
        self.assertIn("casting : 8 manquant(s), 4 en trop", self.sortie)       # chaque personne compte deux tuples (elle et son id) : 1 + 3 voulues, 1 + 1 présentes

    def test_verification_signale_et_n_ecrit_pas(self):
        self.assertEqual(self.traiter(verify=True, apply=True), (1, 0))
        self.assertEqual(self.ecrit, [])
        self.assertIn("[DIFF] casting", self.sortie)

    def test_application_n_ecrit_que_les_tags(self):
        self.assertEqual(self.traiter(apply=True), (0, 0))
        nom, xml = self.ecrit[0]
        self.assertEqual(nom, "film.mkv")
        self.assertEqual(valeurs(blocs(xml)[1], "DIRECTOR"), ["Nouveau"])
        self.assertIn("[OK]", self.sortie)

    def test_casting_deja_conforme(self):
        a_jour = credits.recredit(FICHIER, movietags.movie_target(fiche(3), OPTS).tags_xml)
        self.assertEqual(self.traiter(tags=mkv.parse_tags(a_jour), apply=True), (0, 0))
        self.assertEqual(self.ecrit, [])
        self.assertIn("[OK] casting déjà conforme", self.sortie)

    def test_fichier_jamais_etiquete_signale_et_laisse(self):
        self.assertEqual(self.traiter(tags=set(), apply=True), (1, 0))
        self.assertEqual(self.ecrit, [])
        self.assertIn("[SANS TAGS]", self.sortie)

    def test_fiche_sans_casting_ne_vide_pas_le_fichier(self):
        vide = {"id": 7, "title": "Film", "credits": {}}
        self.assertEqual(self.traiter(movie=vide, apply=True), (0, 0))
        self.assertEqual(self.ecrit, [])
        self.assertIn("[SANS CASTING]", self.sortie)

    def test_tags_illisibles_rien_n_est_ecrit(self):
        self.assertEqual(self.traiter(apply=True, xml=""), (0, 1))
        self.assertEqual(self.ecrit, [])
        self.assertIn("[ÉCHEC] tags illisibles", self.sortie)

    def test_echec_d_ecriture_compte(self):
        self.assertEqual(self.traiter(apply=True, ecriture=(2, "Erreur")), (0, 1))
        self.assertIn("[ÉCHEC] Erreur", self.sortie)

    def test_plus_de_vingt_acteurs_viennent_jusqu_a_cinquante(self):
        self.traiter(movie=fiche(60), apply=True)
        self.assertEqual(len(valeurs(blocs(self.ecrit[0][1])[1], "ACTOR")), mkv.MAX_ACTORS)


class TestEcritureDesTags(unittest.TestCase):
    def ecrire(self, tags_xml):
        vu = {}

        def run(cmd, **kwargs):
            vu["cmd"] = cmd
            if tags_xml:
                vu["xml"] = (Path(kwargs["cwd"]) / "tags.xml").read_text(encoding="utf-8")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(mkv, "run_tool", run):
            return mkv.write_tags("film.mkv", tags_xml), vu

    def test_seuls_les_tags_sont_ecrits(self):
        (code, _), vu = self.ecrire("<Tags/>")
        self.assertEqual(code, 0)
        self.assertEqual(vu["cmd"][2:], ["--tags", "all:tags.xml"])           # pas de --edit info : le titre du conteneur ne bouge pas
        self.assertEqual(vu["xml"], "<Tags/>")


if __name__ == "__main__":
    unittest.main()
