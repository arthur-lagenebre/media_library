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
        for ident in ("seek", "cover", "song", "sub", "time", "shuffle", "prev", "play", "next", "repeat", "qbtn", "mute", "vol", "player"):
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
        self.assertIn("side.onclick=function(){var t=cur();if(t&&t.page)open(t.page)}", player.INDEX_SCRIPT)

    def test_chaque_titre_de_la_file_porte_son_album(self):
        # La file peut mêler des albums : l'artiste, l'album, la pochette et la fiche sont ceux du titre, pas d'une file entière.
        self.assertIn("function item(t,m){return{src:t.src,title:String(t.title||''),artist:m.artist,album:m.album,cover:m.cover,page:m.page}}", player.INDEX_SCRIPT)
        self.assertIsNone(re.search(r"(?<![\w.])meta[.=]", player.INDEX_SCRIPT))        # plus de meta commune à toute la file
        for champ in ("t.artist", "t.album", "t.cover", "t.page"):
            self.assertIn(champ, player.INDEX_SCRIPT)

    def test_le_panneau_de_la_file_d_attente(self):
        html = player.main_bar()
        for ident in ("queue", "qbody", "qclose"):
            self.assertIn(f"id='{ident}'", html, ident)
        self.assertIn("<aside id='queue' hidden", html)                 # fermé au départ
        self.assertGreater(html.index("<aside"), html.index("<audio"))   # hors de la barre : il s'ouvre au-dessus
        self.assertLess(html.index("<aside"), html.index("</aside>"))

    def test_le_panneau_passe_au_dessus_de_la_fiche_et_sous_la_barre(self):
        def z(selector):
            return int(re.findall(re.escape(selector) + r"\{[^}]*z-index:(\d+)", player.INDEX_CSS)[-1])
        self.assertGreater(z("#queue"), z("#frame"))
        self.assertGreater(z("#bar"), z("#queue"))
        self.assertIn("bottom:72px", re.search(r"#queue\{[^}]*\}", player.INDEX_CSS).group(0))        # la barre reste libre

    def test_le_volet_a_deux_onglets(self):
        html = player.main_bar()
        for ident in ("tabq", "tabp", "qclose", "qbody"):
            self.assertIn(f"id='{ident}'", html, ident)
        self.assertIn("role='tablist'", html)
        self.assertIn("id='tabq' class='on'", html)                       # la file d'abord
        script = player.INDEX_SCRIPT
        self.assertIn("$('tabp').onclick=function(){setView('lists')}", script)
        self.assertIn("if(qp.hidden||view!=='queue')return;", script)       # la file ne se dessine que sur son onglet

    def test_une_playlist_garde_le_chemin_relatif_et_pas_l_adresse_complete(self):
        # Le même fichier se lit en file://truenas et en https://nas… : seule la forme relative vaut pour les deux.
        script = player.INDEX_SCRIPT
        self.assertIn("catalog[new URL(t[0],location.href).href]={rel:t[0],title:t[1],meta:m}", script)
        self.assertIn("out.push({src:c.rel,title:c.title})", script)
        self.assertIn("catalog[absolute(t.src)]", script)

    def test_le_stockage_est_valide_et_peut_manquer(self):
        script = player.INDEX_SCRIPT
        self.assertIn("var KEY='media_library.music.playlists.v1'", script)
        self.assertIn("catch(e){return[]}", script)                         # contenu illisible : on repart de rien
        self.assertIn("refuse le stockage", script)                          # stockage refusé : la page le dit et marche sans
        self.assertIn("typeof p.id==='string'&&typeof p.name==='string'&&Array.isArray(p.tracks)", script)

    def test_un_ajout_a_une_playlist_ne_double_pas_un_titre(self):
        script = player.INDEX_SCRIPT
        self.assertIn("if(!have[t.src]){have[t.src]=1;pl.tracks.push({src:t.src,title:t.title});n++}", script)
        self.assertIn("(dup?' ('+dup+' déjà présent", script)               # et le dit

    def test_les_playlists_se_creent_se_renomment_se_lisent_se_suppriment(self):
        script = player.INDEX_SCRIPT
        for morceau in ("'＋ Nouvelle playlist'", "'Renommer'", "'Supprimer'", "'▶ Lire'", "'À la file'", "confirm('Supprimer la playlist"):
            self.assertIn(morceau, script)
        self.assertIn("function playList(pl,from)", script)
        self.assertIn("fresh(p.map(function(x){return x.item}),idx)", script)    # une playlist devient la file, comme un album

    def test_un_titre_introuvable_reste_visible_mais_ne_se_joue_pas(self):
        script = player.INDEX_SCRIPT
        self.assertIn("album:'Introuvable'", script)
        self.assertIn("' lost'", script)
        self.assertIn("introuvable", script)
        self.assertIn("var c=catalog[absolute(t.src)]", script)
        self.assertIn(".qrow.lost .qt{", player.INDEX_CSS)

    def test_enregistrer_la_file_en_playlist(self):
        script = player.INDEX_SCRIPT
        self.assertIn("'Enregistrer en playlist'", script)
        self.assertIn("relTracks(order.map(function(i){return queue[i]}))", script)      # toute la file, dans l'ordre de lecture

    def test_les_fiches_proposent_de_ranger_dans_une_playlist(self):
        script = player.PAGE_SCRIPT
        self.assertIn("label:'Ajouter à une playlist…'", script)
        self.assertIn("label:'Ajouter l’album à une playlist…'", script)
        self.assertIn("postMessage({t:'pick',tracks:list}", script)
        self.assertIn("d.t==='pick'&&valid(d.tracks)", player.INDEX_SCRIPT)
        # Comme « lire ensuite » : seulement dans music.html, qui seul a des playlists.
        self.assertLess(script.index("if(framed){trackActions"), script.index("label:'Ajouter à une playlist…'"))

    def test_la_fenetre_de_choix_passe_au_dessus_de_tout(self):
        def z(selector):
            return int(re.findall(re.escape(selector) + r"\{[^}]*z-index:(\d+)", player.INDEX_CSS)[-1])
        self.assertGreater(z("#pick"), z("#toast"))
        self.assertGreater(z("#pick"), z("#bar"))
        self.assertIn("ov.onclick=function(e){if(e.target===ov)closePick()}", player.INDEX_SCRIPT)   # un clic à côté la ferme

    def test_aucun_texte_de_titre_n_entre_comme_html(self):
        self.assertNotIn("innerHTML", player.INDEX_SCRIPT)

    def test_le_panneau_pousse_la_page_au_lieu_de_la_recouvrir(self):
        # Sinon il cache le bord droit des fiches - durées, menus ⋯ - justement là où on ajoute des titres.
        css = player.INDEX_CSS
        self.assertIn("body.qopen{padding-right:360px}", css)
        self.assertIn("body.qopen #frame{right:360px;width:calc(100% - 360px)}", css)     # une largeur donnée : une iframe n'est pas étirée par left/right
        self.assertEqual(re.search(r"#queue\{[^}]*width:(\d+)px", css).group(1), "360")      # la même largeur que le retrait
        self.assertIn("document.body.classList.toggle('qopen',!qp.hidden)", player.INDEX_SCRIPT)

    def test_sur_un_ecran_etroit_le_panneau_repasse_par_dessus(self):
        self.assertIn("@media(max-width:760px){body.qopen{padding-right:0}body.qopen #frame{right:0;width:100%}}", player.INDEX_CSS)

    def test_la_file_se_redessine_quand_elle_change_pas_a_chaque_pause(self):
        script = player.INDEX_SCRIPT
        self.assertIn("go();refresh();paint();drawQueue()}", script)            # un titre chargé
        self.assertIn("refresh();drawQueue()};", script)                         # aléatoire et répéter
        refresh = script[script.index("function refresh()"):script.index("function show()")]
        self.assertNotIn("drawQueue", refresh)

    def test_le_panneau_liste_le_titre_en_cours_puis_la_suite_dans_l_ordre_de_lecture(self):
        script = player.INDEX_SCRIPT
        self.assertIn("for(var i=pos+1;i<order.length;i++)", script)             # l'ordre de lecture, pas celui de l'album
        self.assertIn("queue[order[p]]", script)
        self.assertIn("load(p)", script)                                          # un clic saute sur le titre
        self.assertIn("textContent", script)
        self.assertNotIn("innerHTML", script)                                     # titres et artistes entrent comme texte

    def test_echap_ferme_d_abord_la_fenetre_de_choix_puis_le_panneau(self):
        script = player.INDEX_SCRIPT
        fin = script[script.index("if(e.key!=='Escape')return;"):]
        self.assertLess(fin.index("closePick()"), fin.index("toggleQueue()"))
        self.assertIn("if(!qp.hidden)toggleQueue()", fin)

    def test_la_barre_montre_l_artiste_et_la_pochette_envoyes_par_la_fiche(self):
        # Chaque fiche dit de qui est l'album et quelle est sa pochette, et la page ne garde que des images en data-URI.
        for script in (player.PAGE_SCRIPT, player.TILE_SCRIPT):
            self.assertIn("artist:", script)
            self.assertIn("cover:", script)
        self.assertIn("d.cover.indexOf('data:image/')===0", player.INDEX_SCRIPT)

    def test_le_curseur_de_volume_n_est_pas_celui_du_navigateur(self):
        # Le curseur natif est blanc : sur la barre sombre il se confondait avec le bord de la fenêtre.
        self.assertIn("#vol{-webkit-appearance:none;appearance:none", player.INDEX_CSS)
        self.assertIn("#3a3e4a", player.INDEX_CSS)                      # la piste, sombre
        self.assertIn("#7cc4ff var(--v,100%)", player.INDEX_CSS)        # la partie remplie, bleue
        self.assertNotIn("accent-color", player.INDEX_CSS)
        self.assertIn("vol.style.setProperty('--v',vol.value+'%')", player.INDEX_SCRIPT)

    def test_le_menu_d_une_piste_propose_de_la_lire_seule(self):
        self.assertIn("{label:'Lire ce titre seul',run:function(i){start(i,true)}}", player.PAGE_SCRIPT)
        self.assertIn("role','menu'", player.PAGE_SCRIPT)
        self.assertIn("e.stopPropagation()", player.PAGE_SCRIPT)                 # le clic sur « ⋯ » n'est pas pris pour un clic « ailleurs »
        self.assertIn("e.key==='Escape'", player.PAGE_SCRIPT)
        self.assertNotIn("innerHTML", player.PAGE_SCRIPT)

    def test_lire_ensuite_et_ajouter_a_la_fin_n_existent_que_dans_music_html(self):
        script = player.PAGE_SCRIPT
        self.assertIn("label:'Lire ensuite'", script)
        self.assertIn("label:'Ajouter à la fin'", script)
        self.assertIn("label:'Lire l’album ensuite'", script)
        self.assertIn("label:'Ajouter l’album à la fin'", script)
        # Ajoutés seulement si la fiche est dans l'iframe : une fiche ouverte seule n'a pas de file.
        self.assertIn("albumActions=[];if(framed){trackActions.push({label:'Lire ensuite'", script)
        self.assertIn("allmore.remove()", script)                                  # sans file, le menu de l'album disparaît

    def test_une_fiche_envoie_un_ajout_que_la_page_comprend(self):
        envoi = re.search(r"enqueue=function\(where,list\)\{.*?postMessage\(\{t:'enqueue',where:where,tracks:list,", player.PAGE_SCRIPT)
        self.assertIsNotNone(envoi)
        self.assertIn("d.t==='enqueue'&&(d.where==='next'||d.where==='end')&&valid(d.tracks)", player.INDEX_SCRIPT)

    def test_un_ajout_se_place_apres_le_titre_en_cours_et_ceux_deja_ajoutes_ainsi(self):
        script = player.INDEX_SCRIPT
        self.assertIn("function runAfter(arr,p){var k=p+1;while(k<arr.length&&queue[arr[k]].nx)k++;return k}", script)
        self.assertIn("if(where==='next')t.nx=true", script)                      # marqué : « lire ensuite » se range derrière les précédents
        self.assertIn("cur().nx=false", script)                                    # joué : la marque tombe
        self.assertIn("ao=where==='next'?runAfter(order,pos):order.length", script)

    def test_l_ordre_naturel_suit_les_ajouts_pour_que_la_fin_de_l_aleatoire_les_garde(self):
        script = player.INDEX_SCRIPT
        self.assertIn("natural.splice.apply(natural,[an,0].concat(idx))", script)
        self.assertIn("order=natural.slice();pos=ci>=0?order.indexOf(ci):-1", script)
        self.assertNotIn("order=queue.map", script)

    def test_rien_en_cours_un_ajout_lance_la_lecture(self):
        self.assertIn("if(pos<0||!queue.length){fresh(items,0);return}", player.INDEX_SCRIPT)

    def test_le_panneau_retire_et_vide(self):
        script = player.INDEX_SCRIPT
        self.assertIn("function removeAt(p)", script)
        self.assertIn("function clearRest()", script)
        self.assertIn("function(){removeAt(p)}", script)
        self.assertIn("'Vider'", script)
        self.assertIn("aria-label','Retirer de la file'", script)
        # Une ligne n'est pas un bouton qui en contient un autre : le bouton de retrait est à côté du bouton principal.
        self.assertIn("r.appendChild(b)", script)
        self.assertIn("r.appendChild(d)", script)

    def test_la_confirmation_d_un_ajout(self):
        self.assertIn("'Lecture ensuite : '", player.INDEX_SCRIPT)
        self.assertIn("'Ajouté à la fin : '", player.INDEX_SCRIPT)
        self.assertIn("#toast{position:fixed", player.INDEX_CSS)
        self.assertIn("pointer-events:none", re.search(r"#toast\{[^}]*\}", player.INDEX_CSS).group(0))
        def z(selector):
            return int(re.findall(re.escape(selector) + r"\{[^}]*z-index:(\d+)", player.INDEX_CSS)[-1])
        self.assertGreater(z("#toast"), z("#queue"))

    def test_un_titre_seul_n_envoie_que_lui_a_la_page(self):
        # Dans musique.html : la file de la page est ce que la fiche envoie, donc un seul titre, à la place 0.
        self.assertIn("tracks:solo?[tracks[i]]:tracks,index:solo?0:i", player.PAGE_SCRIPT)

    def test_un_titre_seul_ne_lance_pas_le_suivant_sur_une_fiche_ouverte_seule(self):
        script = player.PAGE_SCRIPT
        self.assertIn("only=!!solo", script)
        self.assertIn("if(only){update()}else{start(cur+1)}", script)           # fin du titre : on s'arrête
        self.assertIn("next.disabled=cur<0||only||", script)                      # pas de « suivant »
        self.assertIn("cur===0||only", script)                                    # « précédent » relance le titre

    def test_le_menu_est_range_a_sa_place_dans_la_fenetre(self):
        css = player.PLAYER_CSS
        self.assertIn("#menu{position:fixed;z-index:40", css)                    # au-dessus de la barre de la fiche (5)
        self.assertIn("@media(hover:none){.more{opacity:1}}", css)                # visible au doigt
        self.assertIn("innerHeight", player.PAGE_SCRIPT)                          # remonte s'il manque de la place en bas

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
