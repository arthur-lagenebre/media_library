"""Le lecteur : la page coque qui garde la lecture en vie, et le script des fiches qui lui parle."""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common import favicon
from libraries.music import player


class TestCoque(unittest.TestCase):
    def test_le_sommaire_est_dans_une_iframe_et_la_barre_a_cote(self):
        html = player.build_shell("Musique", "index.html")
        self.assertIn("<iframe id='frame' src='index.html'", html)
        self.assertEqual(html.count("<audio"), 1)
        self.assertLess(html.index("<iframe"), html.index("<audio"))

    def test_meme_icone_que_le_sommaire(self):
        self.assertIn(favicon.music_link(), player.build_shell("Musique", "index.html"))

    def test_la_barre_precede_le_script_qui_la_cherche(self):
        html = player.build_shell("Musique", "index.html")
        script = html.index("<script>")
        for ident in ("id='player'", "id='frame'", "id='alb'", "id='song'", "id='prev'", "id='next'"):
            self.assertLess(html.index(ident), script, ident)

    def test_titre_et_sommaire_echappes(self):
        html = player.build_shell("L'Oeil <b>", "a'b.html")
        self.assertIn("<title>L'Oeil &lt;b&gt;</title>", html)
        self.assertIn("src='a&#39;b.html'", html)
        self.assertNotIn("<b>", html)

    def test_la_coque_ne_se_fie_qu_a_son_iframe_et_a_son_protocole(self):
        # Ce qui retient un message d'une autre fenêtre, ou un lien vers autre chose que la médiathèque.
        self.assertIn("e.source!==f.contentWindow", player.SHELL_SCRIPT)
        self.assertIn("protocol===location.protocol", player.SHELL_SCRIPT)

    def test_la_fiche_n_ecoute_que_son_parent(self):
        self.assertIn("e.source!==window.parent", player.PAGE_SCRIPT)

    def test_les_deux_cotes_parlent_le_meme_langage(self):
        # Chaque message envoyé par la fiche est compris par la coque, et inversement.
        envoyes = set(re.findall(r"postMessage\(\{t:'(\w+)'", player.PAGE_SCRIPT))
        compris = set(re.findall(r"d\.t==='(\w+)'", player.SHELL_SCRIPT))
        self.assertEqual(envoyes, compris)
        recus = set(re.findall(r"d\.t!=='(\w+)'", player.PAGE_SCRIPT))
        emis = set(re.findall(r"postMessage\(\{t:'(\w+)'", player.SHELL_SCRIPT))
        self.assertEqual(recus, emis)


if __name__ == "__main__":
    unittest.main()
