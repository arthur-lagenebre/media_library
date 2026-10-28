"""TV_Shows/Metadata.py : le plan d'une saison, la vérification, l'écriture, et le déroulé complet avec étiquetage.

Les lectures de fichiers (mkvmerge, ffprobe) et l'écriture (mkvpropedit) sont simulées : on regarde ce que le script décide d'écrire, fichier par fichier, et ce qu'il en dit.
"""

import io
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.video import mkv
from scripts.TV_Shows import Metadata as series
from tests.test_codes_de_sortie_video import ProgrammeTestCase
from tests.test_flux import FauxTmdbSerie

OPTS = mkv.Options(cover=False, date=True, audio_names=True, sub_names=True, flags=True, stats=True, image_size="w780")
INFO = {"tracks": [{"id": 0, "type": "video"}, {"id": 1, "type": "audio", "codec": "AC-3", "properties": {"language": "fre", "audio_channels": 2}}]}
SAISON = {"season_number": 1, "name": "Saison 1", "episodes": [
    {"episode_number": 1, "name": "Pilote", "air_date": "2024-01-02", "runtime": 45},
    {"episode_number": 2, "name": "Suite", "air_date": "2024-01-09", "runtime": 45},
]}


def lecture(duree=45.0, note="", tags=None):
    return mkv.Reading(info=INFO, probe=mkv.Probe(duree), tags=tags, note=note)


def arguments(**changes):
    args = dict(probe=False, verify=False, apply=False, skip_done=False, match_threshold=0.55, series_name="Ma Serie", dir="")
    args.update(changes)
    return types.SimpleNamespace(**args)


class SaisonTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dossier = Path(self._tmp.name)
        for nom in ("01 - brut.mkv", "02 - brut.mkv"):
            (self.dossier / nom).write_text("x", encoding="utf-8")
        self.ecritures = []

    def lectures(self, **par_nom):
        """Un inspect_all simulé : {chemin: lecture}, la lecture de chaque fichier se choisissant par son nom."""
        def inspect_all(paths, with_probe=True, with_tags=False, **kwargs):
            return {p: par_nom.get(Path(p).name[:2], lecture()) for p in paths}
        return inspect_all

    def traiter(self, args=None, lectures=None, verify_rend=None, ecriture=(0, ""), conforme=False):
        args = args or arguments()

        def write(path, info, target, opts, tmdb):
            self.ecritures.append((Path(path).name, target.title, target.tags_xml))
            return ecriture

        sortie = io.StringIO()
        with mock.patch.object(series.mkv, "inspect_all", lectures or self.lectures()), \
                mock.patch.object(series.mkv, "write", write), \
                mock.patch.object(series.mkv, "verify", lambda info, target, opts, tags: verify_rend or []), \
                mock.patch.object(series.mkv, "is_conform", lambda *a: conforme), \
                redirect_stdout(sortie):
            report = series.process_season(self.dossier, SAISON, args, OPTS, None)
        self.sortie = sortie.getvalue()
        return report


class TestPlanEtRemarques(SaisonTestCase):
    def plan(self, **lectures):
        with mock.patch.object(series.mkv, "inspect_all", self.lectures(**lectures)):
            return series.build_plan(self.dossier, SAISON, arguments(), OPTS)

    def test_chaque_fichier_est_confronte_a_son_episode(self):
        plan = self.plan()
        self.assertEqual([c.episode["name"] for c in plan], ["Pilote", "Suite"])

    def test_duree_trop_courte_signalee(self):
        plan = self.plan(**{"01": lecture(duree=30.0)})
        self.assertEqual(plan[0].notes, ["durée 30min vs 45min attendues -> à vérifier"])
        self.assertEqual(plan[1].notes, [])

    def test_ecart_de_duree_toleré(self):
        # TMDB arrondit ; une marge de trois minutes évite de crier pour rien.
        self.assertEqual(self.plan(**{"01": lecture(duree=47.5)})[0].notes, [])

    def test_remarque_de_lecture_reprise(self):
        plan = self.plan(**{"02": lecture(note="lecture impossible par mkvmerge (code 2)")})
        self.assertEqual(plan[1].notes, ["lecture impossible par mkvmerge (code 2)"])

    def test_fichier_non_lu_garde_son_episode_sans_remarque(self):
        with mock.patch.object(series.mkv, "inspect_all", lambda paths, *a, **k: {}):
            plan = series.build_plan(self.dossier, SAISON, arguments(), OPTS)
        self.assertEqual([(c.episode["name"], c.notes, c.info) for c in plan], [("Pilote", [], None), ("Suite", [], None)])

    def test_fichier_sans_episode_correspondant(self):
        (self.dossier / "ZZ sans numero.mkv").write_text("x", encoding="utf-8")
        plan = self.plan()
        self.assertIsNone(next(c for c in plan if c.path.name.startswith("ZZ")).episode)

    def test_les_tags_ne_sont_relus_que_pour_les_comparer(self):
        demandes = []

        def inspect_all(paths, with_probe=True, with_tags=False, **kwargs):
            demandes.append(with_tags)
            return {}

        for options, attendu in (({}, False), ({"verify": True}, True), ({"skip_done": True}, True)):
            with mock.patch.object(series.mkv, "inspect_all", inspect_all):
                series.build_plan(self.dossier, SAISON, arguments(**options), OPTS)
        self.assertEqual(demandes, [False, True, True])


class TestSimulation(SaisonTestCase):
    def test_apercu_sans_rien_ecrire(self):
        report = self.traiter()
        self.assertEqual((report.matched, report.total, report.failures), (2, 2, 0))
        self.assertEqual(self.ecritures, [])
        self.assertIn("[S01E01] 01 - brut.mkv", self.sortie)
        self.assertIn("-> Pilote", self.sortie)
        self.assertIn("date segment -> 2024-01-02", self.sortie)
        self.assertIn("audio a1 [fre]", self.sortie)
        self.assertIn("=> 2/2 associé(s).", self.sortie)

    def test_remarques_affichees_sous_le_fichier(self):
        self.traiter(lectures=self.lectures(**{"01": lecture(duree=30.0)}))
        self.assertIn("/!\\ durée 30min vs 45min attendues", self.sortie)

    def test_fichier_sans_episode(self):
        (self.dossier / "ZZ sans numero.mkv").write_text("x", encoding="utf-8")
        report = self.traiter(arguments(apply=True))
        self.assertIn("[NON ASSOCIÉ] ZZ sans numero.mkv", self.sortie)
        self.assertEqual((report.matched, report.total), (2, 3))
        self.assertNotIn("ZZ sans numero.mkv", [nom for nom, _, _ in self.ecritures])
        self.assertEqual(len(self.ecritures), 2)


class TestVerification(SaisonTestCase):
    def test_ecarts_comptes_par_fichier(self):
        report = self.traiter(arguments(verify=True), verify_rend=[("titre", False, "ancien"), ("tags", False, "2 manquant(s)"), ("date", True, "ok")])
        self.assertEqual(report.diffs, 2)                # deux fichiers, chacun non conforme
        self.assertIn("[DIFF] titre : actuel = 'ancien'", self.sortie)
        self.assertIn("[DIFF] tags : actuel = '2 manquant(s)'", self.sortie)
        self.assertNotIn("[DIFF] date", self.sortie)
        self.assertEqual(report.exit_code, 1)

    def test_fichier_conforme(self):
        report = self.traiter(arguments(verify=True), verify_rend=[("titre", True, "ok")])
        self.assertEqual(report.diffs, 0)
        self.assertEqual(self.sortie.count("[OK] déjà conforme"), 2)
        self.assertEqual(report.exit_code, 0)

    def test_la_verification_n_ecrit_jamais(self):
        self.traiter(arguments(verify=True, apply=True), verify_rend=[("titre", False, "x")])
        self.assertEqual(self.ecritures, [])
        self.assertNotIn("--- écriture ---", self.sortie)


class TestEcriture(SaisonTestCase):
    def test_chaque_episode_est_ecrit_avec_son_titre(self):
        report = self.traiter(arguments(apply=True))
        self.assertEqual([(nom, titre) for nom, titre, _ in self.ecritures], [("01 - brut.mkv", "Pilote"), ("02 - brut.mkv", "Suite")])
        self.assertIn("Ma Serie", self.ecritures[0][2])             # le nom de la série est dans les tags
        self.assertEqual(report.failures, 0)
        self.assertEqual(self.sortie.count("[OK] "), 2)

    def test_echec_d_ecriture_compte_et_n_arrete_pas_les_suivants(self):
        report = self.traiter(arguments(apply=True), ecriture=(2, "Erreur : fichier verrouillé"))
        self.assertEqual(report.failures, 2)
        self.assertEqual(len(self.ecritures), 2)
        self.assertIn("[ÉCHEC] 01 - brut.mkv  -> Erreur : fichier verrouillé", self.sortie)
        self.assertEqual(report.exit_code, 1)

    def test_skip_done_saute_ce_qui_est_deja_a_jour(self):
        report = self.traiter(arguments(apply=True, skip_done=True), conforme=True)
        self.assertEqual(self.ecritures, [])
        self.assertEqual(self.sortie.count("(déjà à jour)"), 2)
        self.assertEqual(report.failures, 0)

    def test_skip_done_n_ecrit_que_le_reste(self):
        conformes = iter([True, False])
        sortie = io.StringIO()
        with mock.patch.object(series.mkv, "inspect_all", self.lectures()), mock.patch.object(series.mkv, "is_conform", lambda *a: next(conformes)), \
                mock.patch.object(series.mkv, "write", lambda path, *a: self.ecritures.append(Path(path).name) or (0, "")), redirect_stdout(sortie):
            series.process_season(self.dossier, SAISON, arguments(apply=True, skip_done=True), OPTS, None)
        self.assertEqual(self.ecritures, ["02 - brut.mkv"])

    def test_simulation_n_ecrit_pas(self):
        self.traiter(arguments(apply=False))
        self.assertEqual(self.ecritures, [])


# ----------------------------------------------------------------------------
# main() avec étiquetage
# ----------------------------------------------------------------------------
class TestSeriesDeBoutEnBout(ProgrammeTestCase):
    def setUp(self):
        super().setUp()
        self.bib = self.racine                      # la médiathèque : la fiche de la série va dans son __Data__
        self.racine = self.bib / "Ma Serie"
        self.racine.mkdir()
        for numero in (1, 2):
            saison = self.racine / f"Saison {numero}"
            saison.mkdir()
            (saison / "01 - brut.mkv").write_text("x", encoding="utf-8")
        self.ecritures = []

    def metadata(self, tmdb=None, *options, **patches):
        def write(path, info, target, opts, tmdb_):
            self.ecritures.append((Path(path).parent.name, target.title, target.tags_xml))
            return 0, ""

        defauts = {"mkv.inspect_all": lambda paths, *a, **k: {p: lecture() for p in paths}, "mkv.write": write}
        defauts.update(patches)
        return self.lancer(series, tmdb or FauxTmdbSerie(), "--tmdb-id", "42", *options, **defauts)

    def test_etiquetage_de_toutes_les_saisons(self):
        code, texte = self.metadata(None, "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(sorted((dossier, titre) for dossier, titre, _ in self.ecritures), [("Saison 1", "Pilote"), ("Saison 2", "Pilote")])
        self.assertIn("TOTAL : 2/2 fichier(s) associé(s) sur 2 saison(s) détectée(s).", texte)

    def test_le_nom_de_la_serie_vient_de_tmdb_sauf_avis_contraire(self):
        _, texte = self.metadata(None, "--apply", "--series-name", "Mon Titre")
        self.assertIn("série : Mon Titre", texte)
        self.assertIn("Mon Titre", self.ecritures[0][2])
        self.assertNotIn("Ma Serie", self.ecritures[0][2])

    def test_saison_unique_etiquetee(self):
        for saison in ("Saison 1", "Saison 2"):
            (self.racine / saison / "01 - brut.mkv").unlink()
            (self.racine / saison).rmdir()
        (self.racine / "01 - brut.mkv").write_text("x", encoding="utf-8")
        code, texte = self.metadata(None, "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.ecritures), 1)
        self.assertIn("=> 1/1 associé(s).", texte)

    def test_ecriture_en_echec_donne_le_code_1(self):
        code, texte = self.metadata(None, "--apply", **{"mkv.write": lambda *a: (2, "Erreur")})
        self.assertEqual(code, 1)
        self.assertIn("À CORRIGER : 2 écriture(s) en échec", texte)

    def test_serie_non_identifiee(self):
        with mock.patch.object(series.lookup, "resolve_show_id", lambda *a: None):
            code, _ = self.lancer(series, FauxTmdbSerie(), "--tmdb-id", "42")
        self.assertIn("Série non identifiée", code)

    def test_fiche_de_la_serie_introuvable(self):
        class SansSerie(FauxTmdbSerie):
            def series(self, show_id, language=None):
                from libraries.video.tmdb import TmdbError
                raise TmdbError("HTTP 503")

        code, _ = self.lancer(series, SansSerie(), "--tmdb-id", "42", "--no-tag")
        self.assertIn("Échec de l'appel TMDB (série)", code)

    def test_astuce_quand_no_tag_ne_produit_rien(self):
        _, texte = self.lancer(series, FauxTmdbSerie(), "--tmdb-id", "42", "--no-tag")
        self.assertIn("--no-tag sans --artwork ni --recap ne produit rien", texte)

    def test_affiches_de_dossier_pour_chaque_saison_et_la_serie(self):
        tmdb = FauxTmdbSerie()
        tmdb.season_en = []
        original = tmdb.season

        def season(show_id, numero, language=None):
            if language:
                tmdb.season_en.append(numero)
                return {"poster_path": f"/saison{numero}.jpg"}
            return original(show_id, numero)

        tmdb.season = season
        tmdb.series = lambda show_id, language=None: {"id": show_id, "name": "Ma Serie", "overview": "R", "poster_path": "/serie.jpg"}
        code, texte = self.lancer(series, tmdb, "--tmdb-id", "42", "--no-tag", "--artwork", "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(sorted(tmdb.season_en), [1, 2])
        for chemin in (self.racine / "Saison 1", self.racine / "Saison 2", self.racine):
            self.assertTrue((chemin / "folder.jpg").is_file(), chemin)
        self.assertIn("[saison 2] affiche (EN) : folder.jpg écrit", texte)
        self.assertIn("[série] affiche (EN) : folder.jpg écrit", texte)

    def test_simulation_des_affiches(self):
        code, texte = self.lancer(series, FauxTmdbSerie(), "--tmdb-id", "42", "--no-tag", "--artwork")
        self.assertIn("écrirait folder.jpg", texte)
        self.assertFalse((self.racine / "folder.jpg").exists())

    def test_ancien_dossier_assets_signale(self):
        (self.racine / "assets").mkdir()
        _, texte = self.lancer(series, FauxTmdbSerie(), "--tmdb-id", "42", "--no-tag", "--recap", "--apply")
        self.assertIn("le dossier 'assets' n'est plus utilisé", texte)

    def test_recap_ecrit_pendant_un_etiquetage_normal(self):
        code, _ = self.metadata(None, "--apply", "--recap")
        self.assertEqual(code, 0)
        self.assertTrue((self.bib / "__Data__" / "Fiches" / "Ma Serie.html").is_file())


if __name__ == "__main__":
    unittest.main()
