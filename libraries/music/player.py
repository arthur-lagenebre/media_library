"""Le lecteur des fiches d'album, et la page "coque" qui le garde en vie d'une page à l'autre.

Chaque fiche est un document à part : naviguer le décharge, et l'<audio> avec lui. Deux façons de lire :

- Une fiche ouverte seule joue elle-même, avec son propre <audio> dans une barre fixée en bas de page.
- Dans la coque (lecteur.html), les fiches sont affichées dans une iframe et ne jouent plus rien : elles envoient leur liste de pistes à la coque, qui seule a un <audio> et ne change jamais. Naviguer dans l'iframe ne la touche pas, la musique continue. La coque dit en retour à la fiche ce qui joue, pour qu'elle marque la bonne ligne.

Les deux se parlent par postMessage, qui marche aussi en file:// (les origines y sont opaques, d'où le '*' : l'émetteur se reconnaît à la fenêtre d'où vient le message, pas à son origine). Rien ne passe par le DOM de l'autre page, que file:// interdit.

Tout est pur : ni réseau ni disque.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from libraries.common import favicon

SHELL_NAME = "lecteur.html"

# Le style de la barre, commun à la fiche et à la coque.
BAR_CSS = (
    "#bar{display:flex;align-items:center;gap:10px;padding:10px 20px;background:#1a1c23;border-top:1px solid #2a2d37}"
    "#bar button{flex:none;width:34px;height:34px;border:0;border-radius:50%;background:#21232b;color:#c7ccd4;font-size:13px;cursor:pointer}"
    "#bar button:hover:not(:disabled){background:#7cc4ff;color:#14151a}"
    "#bar button:disabled{opacity:.35;cursor:default}"
    "#bar #song{flex:none;max-width:35%;margin:0 4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px}"
    "#bar #song.bad{color:#ff9aa6}"
    "#bar #alb{flex:none;max-width:25%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px;color:#9aa0aa;cursor:pointer}"
    "#bar #alb:hover{color:#7cc4ff;text-decoration:underline}"
    "#bar audio{flex:1;min-width:0;height:36px}"
)

# Sur une fiche : les boutons de piste, "Tout lire", et la barre fixée en bas.
PLAYER_CSS = (
    BAR_CSS
    + ".trk .p{width:1%;padding-right:0}"
    ".play{width:30px;height:30px;border:0;border-radius:50%;background:#21232b;color:#c7ccd4;font-size:12px;cursor:pointer}"
    ".play:hover,.play:focus-visible,#all:hover{background:#7cc4ff;color:#14151a}"
    ".trk tr.now td{color:#7cc4ff}.trk tr.now .play{background:#7cc4ff;color:#14151a}"
    "#all{margin-top:16px;padding:9px 18px;border:0;border-radius:20px;background:#7cc4ff;color:#14151a;font:600 14px system-ui,sans-serif;cursor:pointer}"
    "#all:hover{background:#a6d8ff}"
    "#bar{position:fixed;left:0;right:0;bottom:0;z-index:5}"
    "body.playing .page{padding-bottom:70px}"
)

ALL_BUTTON = "<div><button id='all' type='button'>▶ Tout lire</button></div>"


def bar(extra=""):
    """La barre : précédent, suivant, la piste en cours, 'extra', et le lecteur. Cachée jusqu'à la première lecture."""
    return ("<div id='bar' hidden><button id='prev' type='button' aria-label='Piste précédente'>⏮</button>"
            "<button id='next' type='button' aria-label='Piste suivante'>⏭</button>"
            f"<span id='song'></span>{extra}<audio id='player' controls preload='none'></audio></div>")


# Le script d'une fiche. Il lit l'album dans l'ordre de la fiche, disques à la suite : "Tout lire" part de la première piste, une piste finie lance la suivante, et un fichier introuvable le dit dans la barre au lieu de se taire. 'start' et 'toggle' changent selon qu'on est dans la coque ou seul.
PAGE_SCRIPT = (
    "(function(){"
    "var btns=[].slice.call(document.querySelectorAll('button.play')),all=document.getElementById('all'),"
    "tracks=btns.map(function(b){return{src:new URL(b.getAttribute('data-src'),location.href).href,title:b.getAttribute('data-title')}}),"
    "framed=window.parent!==window,cur=-1,paused=true,start,toggle;"
    "function mark(){"
    "btns.forEach(function(b,k){var on=k===cur;b.parentNode.parentNode.className=on?'now':'';b.textContent=on&&!paused?'❚❚':'▶'});"
    "all.textContent=cur<0?'▶ Tout lire':paused?'▶ Reprendre':'❚❚ Pause'}"
    "btns.forEach(function(b,k){b.onclick=function(){if(k===cur){toggle()}else{start(k)}}});"
    "all.onclick=function(){if(cur<0){start(0)}else{toggle()}};"
    "if(framed){"
    "start=function(i){window.parent.postMessage({t:'play',tracks:tracks,index:i,album:document.title,page:location.href},'*')};"
    "toggle=function(){window.parent.postMessage({t:'toggle'},'*')};"
    "window.addEventListener('message',function(e){var d=e.data;if(e.source!==window.parent||!d||d.t!=='state')return;"
    "cur=-1;tracks.forEach(function(t,k){if(t.src===d.src)cur=k});paused=d.paused;mark()});"
    "window.parent.postMessage({t:'hello'},'*');"
    "}else{"
    "var a=document.getElementById('player'),bar=document.getElementById('bar'),song=document.getElementById('song'),"
    "prev=document.getElementById('prev'),next=document.getElementById('next');"
    "function update(){paused=a.paused;mark();prev.disabled=cur<0;next.disabled=cur<0||cur>=tracks.length-1}"
    "start=function(i){if(i<0||i>=tracks.length){cur=-1;update();return}"
    "cur=i;a.src=tracks[i].src;song.textContent=(i+1)+'/'+tracks.length+' · '+tracks[i].title;song.className='';"
    "bar.hidden=false;document.body.classList.add('playing');"
    "var p=a.play();if(p&&p.catch)p.catch(function(){});update()};"
    "toggle=function(){if(a.paused){a.play()}else{a.pause()}};"
    "prev.onclick=function(){if(a.currentTime>3||cur===0){a.currentTime=0}else{start(cur-1)}};"
    "next.onclick=function(){start(cur+1)};"
    "a.addEventListener('play',update);a.addEventListener('pause',update);"
    "a.addEventListener('ended',function(){start(cur+1)});"
    "a.addEventListener('error',function(){if(cur<0)return;song.className='bad';song.textContent='Lecture impossible : '+tracks[cur].title});"
    "}"
    "mark()})();"
)

SHELL_CSS = (
    "[hidden]{display:none!important}"
    "html,body{height:100%}"
    "body{margin:0;display:flex;flex-direction:column;font:16px/1.5 system-ui,sans-serif;background:#14151a;color:#e8e8ea}"
    "iframe{flex:1;min-height:0;width:100%;border:0;background:#14151a}"
    + BAR_CSS
)

# La coque. Elle n'accepte que les messages de son iframe, et que des liens du même protocole qu'elle (file:// ici, http:// ailleurs) : une page qui sortirait de la médiathèque dans l'iframe ne lui ferait lire rien d'étranger. Un 'hello' est la fiche qui vient de se charger et demande ce qui joue.
SHELL_SCRIPT = (
    "(function(){"
    "var f=document.getElementById('frame'),a=document.getElementById('player'),bar=document.getElementById('bar'),"
    "song=document.getElementById('song'),alb=document.getElementById('alb'),prev=document.getElementById('prev'),next=document.getElementById('next'),"
    "queue=[],cur=-1,page='';"
    "function ours(u){try{return new URL(u).protocol===location.protocol}catch(e){return false}}"
    "function state(){if(f.contentWindow)f.contentWindow.postMessage({t:'state',src:cur>=0?queue[cur].src:'',paused:a.paused},'*')}"
    "function update(){prev.disabled=cur<0;next.disabled=cur<0||cur>=queue.length-1;state()}"
    "function play(i){if(i<0||i>=queue.length){cur=-1;update();return}"
    "cur=i;a.src=queue[i].src;song.textContent=(i+1)+'/'+queue.length+' · '+queue[i].title;song.className='';"
    "bar.hidden=false;var p=a.play();if(p&&p.catch)p.catch(function(){});update()}"
    "window.addEventListener('message',function(e){var d=e.data;if(e.source!==f.contentWindow||!d)return;"
    "if(d.t==='hello'){state()}"
    "else if(d.t==='toggle'){if(a.paused){a.play()}else{a.pause()}}"
    "else if(d.t==='play'&&Array.isArray(d.tracks)&&d.tracks.length&&d.tracks.every(function(t){return t&&ours(t.src)})){"
    "queue=d.tracks.map(function(t){return{src:t.src,title:String(t.title||'')}});"
    "page=ours(d.page)?d.page:'';alb.textContent=String(d.album||'');alb.title=page?'Revenir à cet album':'';"
    "play(+d.index||0)}});"
    "alb.onclick=function(){if(page)f.src=page};"
    "prev.onclick=function(){if(a.currentTime>3||cur===0){a.currentTime=0}else{play(cur-1)}};"
    "next.onclick=function(){play(cur+1)};"
    "a.addEventListener('play',update);a.addEventListener('pause',update);"
    "a.addEventListener('ended',function(){play(cur+1)});"
    "a.addEventListener('error',function(){if(cur<0)return;song.className='bad';song.textContent='Lecture impossible : '+queue[cur].title});"
    "})();"
)


def _attr(text):
    return escape(str(text), {"'": "&#39;"})


def build_shell(library_name, index_name):
    """La page coque : le sommaire dans une iframe, au-dessus d'une barre de lecture qui ne change jamais. 'index_name' = le sommaire, à côté d'elle."""
    return (
        "<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"{favicon.music_link()}"        # celle du sommaire qu'elle contient : un onglet, une icône
        f"<title>{escape(library_name)}</title>"
        f"<style>{SHELL_CSS}</style></head><body>"
        f"<iframe id='frame' src='{_attr(index_name)}' title='{_attr(library_name)}'></iframe>"
        + bar("<span id='alb'></span>")
        + f"<script>{SHELL_SCRIPT}</script></body></html>"
    )
