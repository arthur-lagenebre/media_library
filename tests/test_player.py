"""Le lecteur : la page music.html (sommaire et barre en un seul document) et les scripts des fiches qui lui parlent."""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.music import librarypage, player


class TestUnSeulFichier(unittest.TestCase):
    def test_plus_de_coque(self):
        # Le sommaire porte lui-même sa barre : il n'y a plus de page à part qui l'affiche dans une iframe.
        for name in ("build_shell", "SHELL_NAME", "SHELL_SCRIPT", "SHELL_CSS"):
            self.assertFalse(hasattr(player, name), name)

    def test_la_fiche_s_ouvre_dans_une_iframe_creee_par_le_script(self):
        # Pas d'iframe dans la page elle-même : sans fiche ouverte, rien ne couvre le sommaire.
        self.assertIn("createElement('iframe')", player.INDEX_SCRIPT)
        self.assertIn("f.id='frame'", player.INDEX_SCRIPT)

    def test_la_fiche_passe_au_dessus_de_l_en_tete_et_sous_la_barre(self):
        def z(selector):
            return int(re.findall(re.escape(selector) + r"\{[^}]*z-index:(\d+)", player.INDEX_CSS)[-1])       # la dernière règle l'emporte
        self.assertGreater(z("#frame"), 10)                  # l'en-tête fixe du sommaire (layout.CSS) est à 10
        self.assertGreater(z("#bar"), z("#frame"))

    def test_la_page_ne_se_fie_qu_a_son_iframe_et_a_son_protocole(self):
        # Ce qui retient un message d'une autre fenêtre, ou un lien vers autre chose que la médiathèque.
        self.assertIn("e.source!==f.contentWindow", player.INDEX_SCRIPT)
        self.assertIn("protocol===location.protocol", player.INDEX_SCRIPT)

    def test_la_fiche_n_ecoute_que_son_parent(self):
        self.assertIn("e.source!==window.parent", player.PAGE_SCRIPT)
        self.assertIn("e.source!==window.parent", player.TILE_SCRIPT)

    def test_les_deux_cotes_parlent_le_meme_langage(self):
        # Chaque message envoyé par une fiche (lecture, pause, retour) est compris par la page, et inversement.
        fiches = player.PAGE_SCRIPT + player.TILE_SCRIPT + librarypage.BACK_SCRIPT
        envoyes = set(re.findall(r"postMessage\(\{t:'(\w+)'", fiches))
        compris = set(re.findall(r"d\.t===?'(\w+)'", player.INDEX_SCRIPT))
        self.assertEqual(envoyes, compris)
        recus = set(re.findall(r"d\.t!=='(\w+)'", fiches))
        emis = set(re.findall(r"postMessage\(\{t:'(\w+)'", player.INDEX_SCRIPT))
        self.assertEqual(recus, emis)

    def test_les_liens_pris_par_la_page_ne_sont_pas_vus_du_retour_au_sommaire(self):
        # Le script de la page se place avant celui du retour, et arrête la propagation du clic qu'il prend.
        self.assertIn("stopImmediatePropagation", player.INDEX_SCRIPT)
        self.assertIn("(l.closest('.al')||l.closest('h2'))", player.INDEX_SCRIPT)

    def test_un_clic_avec_une_touche_ou_vers_un_autre_onglet_reste_normal(self):
        for garde in ("!l.target", "ev.button===0", "!ev.ctrlKey", "!ev.metaKey", "!ev.shiftKey"):
            self.assertIn(garde, player.INDEX_SCRIPT)

    def test_la_barre_du_sommaire_a_toutes_ses_commandes(self):
        html = player.main_bar()
        for ident in ("seek", "cover", "song", "sub", "time", "shuffle", "prev", "play", "next", "repeat", "mute", "vol", "player"):
            self.assertIn(f"id='{ident}'", html, ident)
        self.assertEqual(html.count("<audio"), 1)
        self.assertNotIn("controls", html)                  # la barre est la nôtre, pas celle du navigateur
        self.assertIn("hidden", html.split(">")[0])         # cachée jusqu'à la première lecture

    def test_la_barre_des_fiches_ouvertes_seules_ne_change_pas(self):
        html = player.bar()
        self.assertIn("<audio id='player' controls", html)
        for absent in ("id='seek'", "id='shuffle'", "id='vol'"):
            self.assertNotIn(absent, html)

    def test_cliquer_la_piste_ouvre_la_fiche_de_l_album(self):
        self.assertIn("side.onclick=function(){if(meta.page)open(meta.page)}", player.INDEX_SCRIPT)

    def test_la_barre_montre_l_artiste_et_la_pochette_envoyes_par_la_fiche(self):
        # Chaque fiche dit de qui est l'album et quelle est sa pochette, et la page ne garde que des images en data-URI.
        for script in (player.PAGE_SCRIPT, player.TILE_SCRIPT):
            self.assertIn("artist:", script)
            self.assertIn("cover:", script)
        self.assertIn("d.cover.indexOf('data:image/')===0", player.INDEX_SCRIPT)

    def test_aucun_play_sans_promesse_rattrapee(self):
        # Un fichier introuvable fait rejeter play() : sans catch, la console s'emplit d'erreurs « Uncaught (in promise) ».
        self.assertEqual(player.INDEX_SCRIPT.count(".play()"), 1)
        self.assertIn("r.catch(", player.INDEX_SCRIPT)

    def test_les_fiches_n_ont_plus_la_barre_du_sommaire_dans_leur_style(self):
        self.assertNotIn("#seek", player.TILE_CSS)
        self.assertNotIn("#seek", player.PLAYER_CSS)
        self.assertIn("#seek", player.INDEX_CSS)
        self.assertIn(".ovl", player.INDEX_CSS)             # mais le bouton des pochettes y est


if __name__ == "__main__":
    unittest.main()
