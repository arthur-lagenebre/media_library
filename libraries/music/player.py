"""Le lecteur de la médiathèque musicale : une page, music.html, qui est à la fois le sommaire et le lecteur.

Chaque fiche (album, artiste) est un document à part : naviguer le décharge, et l'<audio> avec lui. Trois façons de lire :

- Une fiche ouverte seule joue elle-même, avec son propre <audio> dans une barre fixée en bas de page.
- Dans music.html, le sommaire et sa barre de lecture sont le même document : la musique ne s'arrête jamais. Un clic sur un nom d'artiste ou une pochette ouvre la fiche PAR-DESSUS, dans une iframe, au-dessus de la barre. Cette fiche ne joue plus rien : elle envoie sa liste de pistes à la page, qui seule a un <audio>, et la page lui dit en retour ce qui joue, pour qu'elle marque la bonne ligne. Fermer la fiche (« ← Musique ») retire l'iframe et ramène au groupe qu'on a quitté, le sommaire n'ayant pas bougé.
- Le bouton posé sur chaque pochette du sommaire lit l'album dans la même barre.

La page et ses fiches se parlent par postMessage, qui marche aussi en file:// (les origines y sont opaques, d'où le '*' : l'émetteur se reconnaît à la fenêtre d'où vient le message, pas à son origine). Rien ne passe par le DOM de l'autre page, que file:// interdit.

Tout est pur : ni réseau ni disque.
"""

from __future__ import annotations


# Le style de la barre, commun aux fiches et à la page music.html.
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

# La barre fixée en bas de page, et la place qu'elle prend une fois visible.
FIXED_BAR_CSS = (
    "#bar{position:fixed;left:0;right:0;bottom:0;z-index:5}"
    "body.playing .page{padding-bottom:70px}"
)

# Sur une fiche : les boutons de piste, "Tout lire", et la barre fixée en bas.
PLAYER_CSS = (
    BAR_CSS
    + ".trk .p{width:1%;padding-right:0}"
    ".play{width:30px;height:30px;border:0;border-radius:50%;background:#21232b;color:#c7ccd4;font-size:12px;cursor:pointer}"
    ".play:hover,.play:focus-visible,#all:hover{background:#7cc4ff;color:#14151a}"
    ".trk tr.now td{color:#7cc4ff}.trk tr.now .play{background:#7cc4ff;color:#14151a}"
    ".allbar{display:flex;align-items:center;gap:6px;margin-top:16px}"
    "#all{padding:9px 18px;border:0;border-radius:20px;background:#7cc4ff;color:#14151a;font:600 14px system-ui,sans-serif;cursor:pointer}"
    "#all:hover{background:#a6d8ff}"
    "#allmore{opacity:1}"
    # Le menu « ⋯ » de chaque piste : discret tant qu'on ne vise pas la ligne (toujours visible au doigt), et le menu lui-même, posé près du bouton.
    ".trk .m{width:1%;padding:4px 4px 4px 0}"
    ".more{width:30px;height:30px;border:0;border-radius:50%;background:none;color:#c7ccd4;font-size:18px;line-height:1;cursor:pointer;opacity:0}"
    ".trk tr:hover .more,.more:focus-visible,.more[aria-expanded=true]{opacity:1}"
    ".more:hover,.more[aria-expanded=true]{background:#252833;color:#fff}"
    "@media(hover:none){.more{opacity:1}}"
    "#menu{position:fixed;z-index:40;min-width:210px;padding:6px;background:#1a1c23;border:1px solid #2a2d37;border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.45)}"
    "#menu button{display:block;width:100%;padding:8px 12px;border:0;border-radius:6px;background:none;color:#e8e8ea;font:inherit;font-size:14px;text-align:left;cursor:pointer}"
    "#menu button:hover,#menu button:focus-visible{background:#252833;outline:0}"
    + FIXED_BAR_CSS
)

# Sur la fiche d'un artiste : le bouton posé au milieu de chaque pochette, et la barre fixée en bas. Le sommaire (music.html) a le même bouton, mais sa propre barre : voir INDEX_CSS. Le bouton n'est pas dans le lien de la pochette (un bouton dans un lien n'est pas valide) mais par-dessus, dans un calque qui laisse passer les clics : un clic sur le bouton lit l'album, un clic à côté, toujours sur la pochette, ouvre sa fiche.
OVERLAY_CSS = (
    ".al{position:relative}"
    ".ovl{position:absolute;top:0;left:0;right:0;aspect-ratio:1;display:flex;align-items:center;justify-content:center;pointer-events:none;transition:transform .15s}"
    ".ov{pointer-events:auto;width:56px;height:56px;padding:0 0 0 4px;border:0;border-radius:50%;background:rgba(20,21,26,.78);color:#fff;font-size:20px;cursor:pointer;opacity:0;transition:opacity .15s,background .15s,transform .15s}"
    ".ov.on{padding:0;opacity:1}"
    "a.cv:hover~.ovl .ov,a.cv:focus-visible~.ovl .ov,.ov:hover,.ov:focus-visible{opacity:1}"
    ".ov:hover,.ov:focus-visible{background:#7cc4ff;color:#14151a;transform:scale(1.08);outline:0}"
    # La pochette se soulève au survol, le bouton avec elle - et reste soulevée quand c'est lui qu'on survole.
    "a.cv:hover~.ovl,a.cv:focus-visible~.ovl,.ovl:has(.ov:hover),.ovl:has(.ov:focus-visible){transform:translateY(-3px)}"
    ".al:has(.ov:hover) .aff,.al:has(.ov:focus-visible) .aff{transform:translateY(-3px);box-shadow:0 0 0 2px #7cc4ff}"
    "@media(hover:none){.ov{opacity:1}}"
)
TILE_CSS = BAR_CSS + OVERLAY_CSS + FIXED_BAR_CSS

# Le script de la fiche d'un artiste. Les pistes de chaque album sont dans l'attribut data-t de son bouton, lues seulement au clic. Comme la fiche d'un album, il envoie l'album à music.html quand il est dans son iframe, et sinon joue lui-même dans la barre ; le bouton de l'album en cours devient une pause.
TILE_SCRIPT = (
    "(function(){"
    "var framed=window.parent!==window,curBtn=null,curSrcs=[],nowSrc='',nowPaused=true,queue=[],cur=-1,a,bar,song,prev,next;"
    "function shown(){if(!curBtn)return;var on=!nowPaused&&curSrcs.indexOf(nowSrc)>=0;"
    "curBtn.className=on?'ov on':'ov';curBtn.textContent=on?'❚❚':'▶'}"
    "function list(b){return JSON.parse(b.getAttribute('data-t')).map(function(t){return{src:new URL(t[0],location.href).href,title:t[1]}})}"
    "var start,toggle;"
    "if(framed){"
    "start=function(t,name,page,img){var h=document.querySelector('h1');window.parent.postMessage({t:'play',tracks:t,index:0,album:name,page:page,artist:h?h.textContent:'',cover:img},'*')};"
    "toggle=function(){window.parent.postMessage({t:'toggle'},'*')};"
    "window.addEventListener('message',function(e){var d=e.data;if(e.source!==window.parent||!d||d.t!=='state')return;"
    "nowSrc=d.src;nowPaused=d.paused;shown()});"
    "window.parent.postMessage({t:'hello'},'*');"
    "}else{"
    "a=document.getElementById('player');bar=document.getElementById('bar');song=document.getElementById('song');"
    "prev=document.getElementById('prev');next=document.getElementById('next');"
    "function update(){prev.disabled=cur<0;next.disabled=cur<0||cur>=queue.length-1;"
    "nowSrc=cur>=0?queue[cur].src:'';nowPaused=a.paused;shown()}"
    "function play(i){if(i<0||i>=queue.length){cur=-1;update();return}"
    "cur=i;a.src=queue[i].src;song.textContent=(i+1)+'/'+queue.length+' · '+queue[i].title;song.className='';"
    "bar.hidden=false;document.body.classList.add('playing');"
    "var p=a.play();if(p&&p.catch)p.catch(function(){});update()}"
    "start=function(t){queue=t;play(0)};"
    "toggle=function(){if(a.paused){a.play()}else{a.pause()}};"
    "prev.onclick=function(){if(a.currentTime>3||cur===0){a.currentTime=0}else{play(cur-1)}};"
    "next.onclick=function(){play(cur+1)};"
    "a.addEventListener('play',update);a.addEventListener('pause',update);"
    "a.addEventListener('ended',function(){play(cur+1)});"
    "a.addEventListener('error',function(){if(cur<0)return;song.className='bad';song.textContent='Lecture impossible : '+queue[cur].title});"
    "}"
    "document.addEventListener('click',function(ev){"
    "var b=ev.target.closest&&ev.target.closest('button.ov');if(!b)return;"
    "if(b===curBtn&&curSrcs.indexOf(nowSrc)>=0){toggle();return}"
    "var was=curBtn,al=b.closest('.al'),link=al.querySelector('a.cv'),t=list(b);"
    "curBtn=b;curSrcs=t.map(function(x){return x.src});nowSrc='';nowPaused=true;"
    "if(was&&was!==b){was.className='ov';was.textContent='▶'}"
    "var im=al.querySelector('img');start(t,al.querySelector('.t').textContent,link?link.href:'',im?im.src:'')})"
    "})();"
)

# « Tout lire », et le menu de l'album (lire ensuite, ajouter à la fin) : le script retire ce menu d'une fiche ouverte seule, qui n'a pas de file.
ALL_BUTTON = ("<div class='allbar'><button id='all' type='button'>▶ Tout lire</button>"
              "<button id='allmore' class='more' type='button' aria-haspopup='menu' aria-expanded='false' aria-label='Plus d&#39;actions pour l&#39;album'>⋯</button></div>")


def bar():
    """La barre d'une fiche ouverte seule : précédent, suivant, la piste en cours, et le lecteur du navigateur. Cachée jusqu'à la première lecture."""
    return ("<div id='bar' hidden><button id='prev' type='button' aria-label='Piste précédente'>⏮</button>"
            "<button id='next' type='button' aria-label='Piste suivante'>⏭</button>"
            "<span id='song'></span><audio id='player' controls preload='none'></audio></div>")


# Le script d'une fiche d'album. Il lit l'album dans l'ordre de la fiche, disques à la suite : "Tout lire" part de la première piste, une piste finie lance la suivante, et un fichier introuvable le dit dans la barre au lieu de se taire. 'start' et 'toggle' changent selon qu'on est dans music.html (la fiche s'ouvre alors dans son iframe) ou seul.
PAGE_SCRIPT = (
    "(function(){"
    "var btns=[].slice.call(document.querySelectorAll('button.play')),all=document.getElementById('all'),"
    "tracks=btns.map(function(b){return{src:new URL(b.getAttribute('data-src'),location.href).href,title:b.getAttribute('data-title')}}),"
    "framed=window.parent!==window,cur=-1,paused=true,only=false,start,toggle,enqueue,toList,"
    "mores=[].slice.call(document.querySelectorAll('.trk button.more')),allmore=document.getElementById('allmore'),mb=null,menu=document.createElement('div');"
    # De qui est l'album et quelle est sa pochette : la barre de musique.html les montre.
    "function side(){var ar=document.querySelector('.artist'),im=document.querySelector('.cov img');return{artist:ar?ar.textContent:'',cover:im?im.src:''}}"
    "function mark(){"
    "btns.forEach(function(b,k){var on=k===cur;b.parentNode.parentNode.className=on?'now':'';b.textContent=on&&!paused?'❚❚':'▶'});"
    "all.textContent=cur<0?'▶ Tout lire':paused?'▶ Reprendre':'❚❚ Pause'}"
    "btns.forEach(function(b,k){b.onclick=function(){if(k===cur){toggle()}else{start(k)}}});"
    "all.onclick=function(){if(cur<0){start(0)}else{toggle()}};"
    # Les menus : un seul pour la page, rempli au clic. Une action reçoit le rang de la piste (-1 pour l'album). Lire ensuite et ajouter à la fin n'existent que dans musique.html, qui seul a une file.
    "var trackActions=[{label:'Lire ce titre seul',run:function(i){start(i,true)}}],albumActions=[];"
    "if(framed){"
    "trackActions.push({label:'Lire ensuite',run:function(i){enqueue('next',[tracks[i]])}},{label:'Ajouter à la fin',run:function(i){enqueue('end',[tracks[i]])}},{label:'Ajouter à une playlist…',run:function(i){toList([tracks[i]])}});"
    "albumActions.push({label:'Lire l’album ensuite',run:function(){enqueue('next',tracks)}},{label:'Ajouter l’album à la fin',run:function(){enqueue('end',tracks)}},{label:'Ajouter l’album à une playlist…',run:function(){toList(tracks)}})}"
    "menu.id='menu';menu.hidden=true;menu.setAttribute('role','menu');document.body.appendChild(menu);"
    "function closeMenu(){if(mb)mb.setAttribute('aria-expanded','false');menu.hidden=true;mb=null}"
    "function openMenu(b,acts,arg){closeMenu();mb=b;menu.textContent='';"
    "acts.forEach(function(x){var e=document.createElement('button');e.type='button';e.setAttribute('role','menuitem');e.textContent=x.label;"
    "e.onclick=function(){closeMenu();x.run(arg)};menu.appendChild(e)});"
    "menu.hidden=false;b.setAttribute('aria-expanded','true');"
    "var r=b.getBoundingClientRect(),h=menu.offsetHeight,w=menu.offsetWidth;"
    "menu.style.top=(r.bottom+h+8>innerHeight?Math.max(4,r.top-h-4):r.bottom+4)+'px';"
    "menu.style.left=Math.max(4,Math.min(r.right-w,innerWidth-w-4))+'px';menu.firstChild.focus()}"
    "function toggleMenu(b,acts,arg){if(mb===b){closeMenu()}else{openMenu(b,acts,arg)}}"
    "mores.forEach(function(b,k){b.onclick=function(e){e.stopPropagation();toggleMenu(b,trackActions,k)}});"
    "if(allmore){if(albumActions.length){allmore.onclick=function(e){e.stopPropagation();toggleMenu(allmore,albumActions,-1)}}else{allmore.remove()}}"
    "document.addEventListener('click',closeMenu);"
    "document.addEventListener('keydown',function(e){if(e.key==='Escape')closeMenu()});"
    "if(framed){"
    # Un titre seul : la page n'envoie que lui, et sa file ne contient rien d'autre.
    "start=function(i,solo){var m=side();"
    "window.parent.postMessage({t:'play',tracks:solo?[tracks[i]]:tracks,index:solo?0:i,album:document.title,page:location.href,artist:m.artist,cover:m.cover},'*')};"
    "toList=function(list){window.parent.postMessage({t:'pick',tracks:list},'*')};"
    "enqueue=function(where,list){var m=side();"
    "window.parent.postMessage({t:'enqueue',where:where,tracks:list,album:document.title,page:location.href,artist:m.artist,cover:m.cover},'*')};"
    "toggle=function(){window.parent.postMessage({t:'toggle'},'*')};"
    "window.addEventListener('message',function(e){var d=e.data;if(e.source!==window.parent||!d||d.t!=='state')return;"
    "cur=-1;tracks.forEach(function(t,k){if(t.src===d.src)cur=k});paused=d.paused;mark()});"
    "window.parent.postMessage({t:'hello'},'*');"
    "}else{"
    "var a=document.getElementById('player'),bar=document.getElementById('bar'),song=document.getElementById('song'),"
    "prev=document.getElementById('prev'),next=document.getElementById('next');"
    "function update(){paused=a.paused;mark();prev.disabled=cur<0;next.disabled=cur<0||only||cur>=tracks.length-1}"
    "start=function(i,solo){if(i<0||i>=tracks.length){cur=-1;update();return}"
    "only=!!solo;cur=i;a.src=tracks[i].src;song.textContent=only?tracks[i].title:(i+1)+'/'+tracks.length+' · '+tracks[i].title;song.className='';"
    "bar.hidden=false;document.body.classList.add('playing');"
    "var p=a.play();if(p&&p.catch)p.catch(function(){});update()};"
    "toggle=function(){if(a.paused){a.play()}else{a.pause()}};"
    "prev.onclick=function(){if(a.currentTime>3||cur===0||only){a.currentTime=0}else{start(cur-1)}};"
    "next.onclick=function(){start(cur+1)};"
    "a.addEventListener('play',update);a.addEventListener('pause',update);"
    "a.addEventListener('ended',function(){if(only){update()}else{start(cur+1)}});"
    "a.addEventListener('error',function(){if(cur<0)return;song.className='bad';song.textContent='Lecture impossible : '+tracks[cur].title});"
    "}"
    "mark()})();"
)

ICONS = {
    "shuffle": "M10.59 9.17 5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z",
    "prev": "M6 6h2v12H6zm3.5 6 8.5 6V6z",
    "next": "M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z",
    "play": "M8 5v14l11-7z",
    "pause": "M6 19h4V5H6v14zm8-14v14h4V5h-4z",
    "repeat": "M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z",
    "repeat-one": "M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4zm-4-2V9h-1l-2 1v1h1.5v4H13z",
    "queue": "M15 6H3v2h12V6zm0 4H3v2h12v-2zM3 16h8v-2H3v2zM17 6v8.18c-.31-.11-.65-.18-1-.18-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3V8h3V6h-5z",
    "volume": "M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 7.97v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z",
    "muted": "M16.5 12A4.5 4.5 0 0 0 14 7.97v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51A8.8 8.8 0 0 0 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3 3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06a8.99 8.99 0 0 0 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4 9.91 6.09 12 8.18V4z",
}

# La barre de music.html, à la Qobuz : la piste à gauche, les commandes au centre, le volume à droite, et la progression en travers de son bord haut. Fixée en bas, elle passe au-dessus de la fiche qui s'ouvre par-dessus le sommaire (INDEX_CSS).
MAIN_BAR_CSS = (
    "#bar{position:fixed;left:0;right:0;bottom:0;z-index:30;display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:16px;height:72px;padding:0 20px;background:#1a1c23;border-top:1px solid #2a2d37}"
    "#bar button{display:flex;align-items:center;justify-content:center;width:36px;height:36px;padding:0;border:0;border-radius:50%;background:none;color:#c7ccd4;cursor:pointer}"
    "#bar button:hover:not(:disabled),#bar button:focus-visible{color:#fff}"
    "#bar button:disabled{opacity:.35;cursor:default}"
    "#bar button.on{color:#7cc4ff}"
    "#bar svg{width:22px;height:22px;fill:currentColor}"
    "#seek{position:absolute;left:0;right:0;top:-7px;height:12px;cursor:pointer;touch-action:none;outline:0}"
    "#seek::before,#fill{content:'';position:absolute;left:0;top:5px;height:2px;transition:top .1s,height .1s}"
    "#seek::before{right:0;background:#2a2d37}"
    "#fill{width:0;background:#7cc4ff}"
    "#seek:hover::before,#seek:hover #fill,#seek:focus-visible::before,#seek:focus-visible #fill{top:4px;height:4px}"
    ".side{display:flex;align-items:center;gap:12px;min-width:0}"
    ".side.go{cursor:pointer}"
    "#cover{flex:none;display:flex;align-items:center;justify-content:center;width:48px;height:48px;border-radius:4px;background:#21232b center/cover;color:#4a4e5a}"
    "#cover.has::after{content:none}"
    "#cover::after{content:'♪';font-size:20px}"
    ".txt{min-width:0}"
    "#song,#sub{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}"
    "#song{font-size:14px;font-weight:600}"
    "#song.bad{color:#ff9aa6}"
    "#sub{font-size:13px;color:#9aa0aa}"
    ".side.go:hover #sub{color:#7cc4ff;text-decoration:underline}"
    ".mid{display:flex;align-items:center;gap:6px}"
    "#time{min-width:96px;margin-right:14px;text-align:right;font-size:13px;color:#9aa0aa;font-variant-numeric:tabular-nums;white-space:nowrap}"
    "#bar #play{width:44px;height:44px}"
    "#play svg{width:32px;height:32px}"
    "#play .i-pause,#play.on .i-play{display:none}"
    "#play.on .i-pause{display:block}"
    "#repeat .i-one,#repeat.one .i-all{display:none}"
    "#repeat.one .i-one{display:block}"
    "#mute .i-muted,#mute.muted .i-vol{display:none}"
    "#mute.muted .i-muted{display:block}"
    ".end{display:flex;align-items:center;justify-content:flex-end;gap:6px}"
    # Le curseur est le nôtre : celui du navigateur est blanc, et se confond avec le bord de la fenêtre. La piste est sombre, la partie remplie bleue (--v, posée par le script), et la poignée claire.
    "#vol{-webkit-appearance:none;appearance:none;width:110px;height:4px;margin:0 4px 0 0;border-radius:2px;outline:0;cursor:pointer;"
    "background:linear-gradient(to right,#7cc4ff var(--v,100%),#3a3e4a var(--v,100%))}"
    "#vol::-webkit-slider-thumb{-webkit-appearance:none;width:12px;height:12px;border:0;border-radius:50%;background:#e8e8ea}"
    "#vol::-moz-range-thumb{width:12px;height:12px;border:0;border-radius:50%;background:#e8e8ea}"
    "#vol::-moz-range-track{background:transparent}"
    "#vol:hover::-webkit-slider-thumb,#vol:focus-visible::-webkit-slider-thumb{background:#fff;box-shadow:0 0 0 3px rgba(124,196,255,.35)}"
    "body.playing .page{padding-bottom:96px}"
    "@media(max-width:760px){#bar{grid-template-columns:1fr auto;padding:0 12px}.end,#time,#shuffle,#repeat{display:none}}"
)

# Le panneau de la file d'attente : un volet à droite, au-dessus de la fiche ouverte (z-index 20) et sous la barre (30), qu'il laisse libre. Ouvert, il ne recouvre pas la page : celle-ci et la fiche se rétrécissent de sa largeur (classe qopen sur le body), pour que les durées et les menus ⋯ du bord droit restent accessibles. Sur un écran étroit il n'y a pas la place : il passe par-dessus.
QUEUE_CSS = (
    "#queue{position:fixed;top:0;right:0;bottom:72px;z-index:25;display:flex;flex-direction:column;width:360px;max-width:100%;background:#1a1c23;border-left:1px solid #2a2d37}"
    "body.qopen{padding-right:360px}"
    # Une iframe n'est pas étirée par left/right (un élément remplacé garde sa largeur de 300 px) : sa largeur est donnée.
    "body.qopen #frame{right:360px;width:calc(100% - 360px)}"
    "@media(max-width:760px){body.qopen{padding-right:0}body.qopen #frame{right:0;width:100%}}"
    ".qh{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid #2a2d37}"
    ".qtabs{display:flex;gap:4px}"
    ".qtabs button{padding:6px 10px;border:0;border-radius:6px;background:none;color:#9aa0aa;font:inherit;font-size:14px;font-weight:600;cursor:pointer}"
    ".qtabs button:hover{color:#fff}"
    ".qtabs button.on{background:#252833;color:#fff}"
    ".qh button{padding:4px 9px;border:0;border-radius:6px;background:none;color:#c7ccd4;font-size:16px;cursor:pointer}"
    ".qh button:hover{background:#252833;color:#fff}"
    "#qbody{flex:1;min-height:0;overflow-y:auto;padding:4px 8px 16px}"
    ".qlabel{margin:16px 8px 6px;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#9aa0aa}"
    ".qnone{margin:6px 8px;font-size:14px;color:#9aa0aa}"
    ".qlabel{display:flex;align-items:center;justify-content:space-between;min-height:24px}"
    ".qbar{display:flex;gap:8px;padding:10px 8px 4px}"
    ".qnew,.qpb{padding:6px 14px;border:1px solid #2a2d37;border-radius:16px;background:#21232b;color:#e8e8ea;font:inherit;font-size:13px;cursor:pointer}"
    ".qnew:hover,.qpb:hover:not(:disabled){background:#2a2d37}"
    ".qpb:disabled{opacity:.4;cursor:default}"
    ".qpb.main{background:#7cc4ff;border-color:#7cc4ff;color:#14151a;font-weight:600}"
    ".qpb.main:hover:not(:disabled){background:#a6d8ff}"
    ".qback{padding:4px 8px 4px 0;border:0;background:none;color:#7cc4ff;font:inherit;font-size:13px;cursor:pointer}"
    ".qptitle{padding:6px 8px 2px}"
    ".qpn{font-size:18px;font-weight:700;overflow-wrap:anywhere}"
    ".qacts{display:flex;flex-wrap:wrap;gap:6px;padding:8px 8px 6px}"
    ".qask{display:flex;gap:6px;width:100%}"
    ".qask input{flex:1;min-width:0;padding:6px 10px;border:1px solid #2a2d37;border-radius:8px;background:#14151a;color:inherit;font:inherit;font-size:14px}"
    ".qask input:focus{outline:0;border-color:#7cc4ff}"
    ".qask button{padding:6px 12px;border:0;border-radius:8px;background:#21232b;color:#e8e8ea;font:inherit;font-size:13px;cursor:pointer}"
    ".qask button[type=submit]{background:#7cc4ff;color:#14151a;font-weight:600}"
    ".qrow.lost .qt{color:#9aa0aa;text-decoration:line-through}"
    "#pick{position:fixed;inset:0;z-index:50;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.55)}"
    ".pickbox{display:flex;flex-direction:column;width:360px;max-width:92%;max-height:80%;padding:16px;border:1px solid #2a2d37;border-radius:12px;background:#1a1c23;box-shadow:0 16px 48px rgba(0,0,0,.6)}"
    ".pickbox h3{margin:0 0 10px;font-size:16px}"
    ".pickbody{overflow-y:auto}"
    ".pickrow{display:flex;justify-content:space-between;gap:12px;width:100%;padding:9px 10px;border:0;border-radius:8px;background:none;color:inherit;font:inherit;font-size:14px;text-align:left;cursor:pointer}"
    ".pickrow:hover,.pickrow:focus-visible{background:#252833;outline:0}"
    ".pickrow .pc{flex:none;color:#9aa0aa;font-size:13px}"
    ".pickbox .qask{margin-top:8px}"
    ".qclear{padding:2px 6px;border:0;border-radius:6px;background:none;color:#7cc4ff;font:inherit;font-size:12px;letter-spacing:0;text-transform:none;cursor:pointer}"
    ".qclear:hover{background:#252833}"
    ".qrow{display:flex;align-items:center;border-radius:8px}"
    ".qrow:hover,.qrow:focus-within{background:#252833}"
    ".qmain{flex:1;min-width:0;display:flex;align-items:center;gap:12px;padding:6px 8px;border:0;border-radius:8px;background:none;color:inherit;font:inherit;text-align:left;cursor:pointer;outline:0}"
    ".qx{flex:none;width:28px;height:28px;margin-right:6px;border:0;border-radius:50%;background:none;color:#9aa0aa;font-size:13px;cursor:pointer;opacity:0}"
    ".qrow:hover .qx,.qx:focus-visible{opacity:1}"
    ".qx:hover{background:#2f3340;color:#fff}"
    "@media(hover:none){.qx{opacity:1}}"
    ".qrow.now .qt{color:#7cc4ff}"
    ".qcov{flex:none;display:flex;align-items:center;justify-content:center;width:44px;height:44px;border-radius:4px;background:#21232b center/cover;color:#4a4e5a}"
    ".qcov.has::after{content:none}"
    ".qcov::after{content:'♪';font-size:18px}"
    ".qtxt{min-width:0}"
    ".qt,.qs{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}"
    ".qt{font-size:14px;font-weight:600}"
    ".qs{font-size:13px;color:#9aa0aa}"
    # La confirmation d'un ajout, au-dessus de la barre : plus haut que la fiche (20) et le panneau (25), sans prendre les clics.
    "#toast{position:fixed;left:50%;bottom:88px;transform:translateX(-50%);z-index:35;max-width:80%;padding:9px 16px;border-radius:20px;background:#252833;color:#e8e8ea;font-size:14px;box-shadow:0 6px 20px rgba(0,0,0,.4);pointer-events:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}"
)

# Sur le sommaire : le bouton des pochettes, la barre, et la fiche qui s'ouvre par-dessus. L'iframe couvre toute la fenêtre sauf la barre (sa hauteur est posée par le script) ; elle passe au-dessus de l'en-tête fixe du sommaire (z-index 10), et la barre au-dessus d'elle.
INDEX_CSS = (
    OVERLAY_CSS
    + MAIN_BAR_CSS
    + QUEUE_CSS
    + "#frame{position:fixed;top:0;left:0;right:0;bottom:0;z-index:20;width:100%;height:100%;border:0;background:#14151a}"
)


def _icon(name, cls=""):
    return f"<svg class='{cls}' viewBox='0 0 24 24' aria-hidden='true'><path d='{ICONS[name]}'/></svg>"


def _button(ident, label, *icons):
    """Un bouton de la barre ; 'icons' = [(icône, classe)], que le CSS montre selon l'état du bouton."""
    return f"<button id='{ident}' type='button' aria-label='{label}'>{''.join(_icon(name, cls) for name, cls in icons)}</button>"


def main_bar():
    """La barre de music.html : pochette, titre et artiste, temps, aléatoire, précédent, lecture, suivant, répéter, volume, et la progression. Cachée jusqu'à la première lecture."""
    return (
        "<div id='bar' hidden>"
        "<div id='seek' role='slider' tabindex='0' aria-label='Position de lecture' aria-valuemin='0' aria-valuemax='100'><div id='fill'></div></div>"
        "<div class='side'><div id='cover'></div><div class='txt'><div id='song'></div><div id='sub'></div></div></div>"
        "<div class='mid'><span id='time'>00:00 - 00:00</span>"
        + _button("shuffle", "Lecture aléatoire", ("shuffle", ""))
        + _button("prev", "Piste précédente", ("prev", ""))
        + _button("play", "Lecture", ("play", "i-play"), ("pause", "i-pause"))
        + _button("next", "Piste suivante", ("next", ""))
        + _button("repeat", "Répéter", ("repeat", "i-all"), ("repeat-one", "i-one"))
        + "</div>"
        "<div class='end'>"
        + _button("qbtn", "File d'attente", ("queue", ""))
        + _button("mute", "Couper le son", ("volume", "i-vol"), ("muted", "i-muted"))
        + "<input id='vol' type='range' min='0' max='100' value='100' aria-label='Volume'></div>"
        "<audio id='player' preload='none'></audio></div>"
        # Le panneau est hors de la barre : il s'ouvre au-dessus d'elle, sur toute la hauteur.
        "<aside id='queue' hidden aria-label=\"File d'attente et playlists\"><div class='qh'>"
        "<div class='qtabs' role='tablist'><button id='tabq' class='on' type='button' role='tab' aria-selected='true'>File d'attente</button>"
        "<button id='tabp' type='button' role='tab' aria-selected='false'>Playlists</button></div>"
        "<button id='qclose' type='button' aria-label='Fermer le volet'>\u2715</button></div><div id='qbody'></div></aside>"
    )


# Le script du sommaire : la barre et sa file de lecture, les boutons des pochettes, et la fiche qui s'ouvre par-dessus. La file est l'album en cours : 'order' est l'ordre de lecture (celui de l'album, ou un tirage au hasard), 'pos' la place de la piste en cours dedans, et 'repeat' vaut 0 (rien), 1 (l'album) ou 2 (la piste). Les pistes de chaque album sont dans l'attribut data-t de son bouton, lues seulement au clic ; un clic sur un lien d'artiste ou de pochette ouvre sa fiche dans l'iframe (un clic avec une touche, ou un lien vers un autre onglet, reste normal). La page n'accepte que les messages de son iframe, et que des liens du même protocole qu'elle (file:// ici, http:// ailleurs) : une fiche qui sortirait de la médiathèque ne lui ferait lire rien d'étranger. Un 'hello' est la fiche qui vient de se charger et demande ce qui joue ; un 'close', le lien « ← Musique » de la fiche ; un 'play' porte aussi l'artiste et la pochette de l'album, que la barre montre. Ce script se place avant celui du retour au sommaire : un lien qu'il prend n'est pas vu de l'autre.
INDEX_SCRIPT = r"""(function(){
function $(id){return document.getElementById(id)}
var a=$('player'),bar=$('bar'),seek=$('seek'),fill=$('fill'),cover=$('cover'),song=$('song'),sub=$('sub'),time=$('time'),side=document.querySelector('.side'),
bShuffle=$('shuffle'),bPrev=$('prev'),bPlay=$('play'),bNext=$('next'),bRepeat=$('repeat'),bMute=$('mute'),vol=$('vol'),
head=document.querySelector('.top'),base=document.title,
qp=$('queue'),qb=$('qbody'),qbtn=$('qbtn'),
queue=[],natural=[],order=[],pos=-1,shuffled=false,repeat=0,drag=false,curBtn=null,curSrcs=[];
// Chaque titre de la file porte lui-même son artiste, son album, sa pochette et la fiche de son album : la file peut mêler des albums.
function item(t,m){return{src:t.src,title:String(t.title||''),artist:m.artist,album:m.album,cover:m.cover,page:m.page}}
function make(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
// Le catalogue : chaque titre que la page sait lire, retrouvé par son adresse complète - titre, artiste, album, pochette et fiche viennent de la pochette de son album, qui porte déjà la liste de ses pistes. 'rel' est son chemin tel que la page l'écrit (relatif à elle) : c'est lui qu'une playlist garde, et il vaut aussi bien en file:// qu'en http://.
var catalog={};
[].forEach.call(document.querySelectorAll('button.ov'),function(b){
var al=b.closest('.al'),sec=al.closest('section'),h=sec&&sec.querySelector('h2'),im=al.querySelector('img'),link=al.querySelector('a.cv'),
m={album:al.querySelector('.t').textContent,artist:h?h.firstChild.textContent:'',cover:im?im.src:'',page:link?link.href:''};
JSON.parse(b.getAttribute('data-t')).forEach(function(t){catalog[new URL(t[0],location.href).href]={rel:t[0],title:t[1],meta:m}})});
function absolute(rel){return new URL(rel,location.href).href}
function plural(n){return n+' titre'+(n>1?'s':'')}
// Les playlists : [{id, name, tracks:[{src: rel, title}]}], gardées dans le navigateur. Le stockage peut manquer (navigation privée, accès refusé) : on le dit, et la page marche sans.
var KEY='media_library.music.playlists.v1',view='queue',openId=null,lists=stored();
function stored(){
try{var d=JSON.parse(localStorage.getItem(KEY));
return Array.isArray(d)?d.filter(function(p){return p&&typeof p.id==='string'&&typeof p.name==='string'&&Array.isArray(p.tracks)}).map(function(p){
return{id:p.id,name:p.name,tracks:p.tracks.filter(function(t){return t&&typeof t.src==='string'}).map(function(t){return{src:t.src,title:String(t.title||'')}})}}):[]}
catch(e){return[]}}
function save(){try{localStorage.setItem(KEY,JSON.stringify(lists));return true}catch(e){toast('Playlists non enregistrées : le navigateur refuse le stockage.');return false}}
function uid(){return Date.now().toString(36)+Math.random().toString(36).slice(2,6)}
function listById(id){for(var i=0;i<lists.length;i++){if(lists[i].id===id)return lists[i]}return null}
function create(name,tracks){var pl={id:uid(),name:name,tracks:tracks||[]};lists.push(pl);save();return pl}
// Ajoute des titres ([{src: rel, title}]) sans doubler ceux que la playlist a déjà ; rend le nombre ajouté.
function addTo(pl,tracks){
var have={},n=0;pl.tracks.forEach(function(t){have[t.src]=1});
tracks.forEach(function(t){if(!have[t.src]){have[t.src]=1;pl.tracks.push({src:t.src,title:t.title});n++}});
save();return n}
// Des pistes comme les fiches les envoient (adresses complètes) : celles que le catalogue connaît, sous leur forme de playlist.
function relTracks(tracks){
var out=[];tracks.forEach(function(t){var c=catalog[t.src];if(c)out.push({src:c.rel,title:c.title})});return out}
// Les titres d'une playlist que la page peut lire, prêts à entrer dans la file ; 'k' est leur rang dans la playlist.
function playable(pl){
var out=[];pl.tracks.forEach(function(t,k){var c=catalog[absolute(t.src)];if(c)out.push({k:k,item:item({src:absolute(t.src),title:c.title},c.meta)})});return out}
function playList(pl,from){
var p=playable(pl);
if(!p.length){toast('Aucun titre de cette playlist n’est disponible.');return}
var idx=0;if(from!=null){for(var i=0;i<p.length;i++){if(p[i].k===from){idx=i;break}}}
fresh(p.map(function(x){return x.item}),idx)}
function frame(){return $('frame')}
function ours(u){try{return new URL(u).protocol===location.protocol}catch(e){return false}}
function cur(){return pos>=0?queue[order[pos]]:null}
function nowSrc(){var t=cur();return t?t.src:''}
function clock(s){s=Math.max(0,Math.floor(s||0));var m=Math.floor(s/60);return(m<10?'0':'')+m+':'+(s%60<10?'0':'')+s%60}
function length(){return isFinite(a.duration)&&a.duration>0?a.duration:0}
function paint(frac){
var end=length(),at=frac==null?a.currentTime:frac*end;
time.textContent=clock(at)+' - '+clock(end);
fill.style.width=(end?Math.min(100,at/end*100):0)+'%';
seek.setAttribute('aria-valuetext',time.textContent)}
function shown(){
if(!curBtn)return;
var on=!a.paused&&curSrcs.indexOf(nowSrc())>=0;
curBtn.className=on?'ov on':'ov';curBtn.textContent=on?'❚❚':'▶'}
// Les boutons, la pause ou la lecture de la pochette, et ce que la fiche ouverte par-dessus doit marquer.
function refresh(){
var t=cur(),playing=!a.paused&&!a.ended;
bPlay.classList.toggle('on',playing);
bPlay.setAttribute('aria-label',playing?'Pause':'Lecture');
bPrev.disabled=!t;
bNext.disabled=!t||(pos>=order.length-1&&repeat!==1);
shown();
var f=frame();if(f&&f.contentWindow)f.contentWindow.postMessage({t:'state',src:nowSrc(),paused:a.paused},'*')}
function show(){
var t=cur();
song.textContent=t?t.title:'';song.className='';
sub.textContent=t?(t.artist?t.artist+' \u2013 ':'')+t.album:'';
cover.style.backgroundImage=t&&t.cover?'url("'+t.cover+'")':'';
cover.className=t&&t.cover?'has':'';
side.className=t&&t.page?'side go':'side';side.title=t&&t.page?'Ouvrir la fiche de cet album':'';
document.title=t?t.title+(t.artist?' \u00b7 '+t.artist:''):base}
// La file d'attente : le titre en cours, puis ce qui suit dans l'ordre de lecture (celui de l'album, ou le tirage de l'aléatoire). Redessinée quand la file ou l'ordre change, pas à chaque pause : la liste ne doit pas sauter sous le doigt.
function qrow(t,cls,click,remove){
var r=make('div','qrow'+cls),b=make('button','qmain'),c=make('div','qcov'+(t.cover?' has':'')),x=make('div','qtxt');
b.type='button';if(t.cover)c.style.backgroundImage='url("'+t.cover+'")';
x.appendChild(make('div','qt',t.title));x.appendChild(make('div','qs',(t.artist?t.artist+' \u2013 ':'')+t.album));
b.appendChild(c);b.appendChild(x);b.onclick=click;r.appendChild(b);
if(remove){var d=make('button','qx','\u2715');d.type='button';d.setAttribute('aria-label','Retirer de la file');d.onclick=function(e){e.stopPropagation();remove()};r.appendChild(d)}
return r}
function drawQueue(){
if(qp.hidden||view!=='queue')return;
qb.textContent='';
var t=cur();
if(!t){qb.appendChild(make('div','qnone','Rien en cours de lecture.'));return}
var now=make('div','qlabel');now.appendChild(make('span',null,'En cours'));
var sv=make('button','qclear','Enregistrer en playlist');sv.type='button';
sv.onclick=function(){askName(now,'',function(name){
var tr=relTracks(order.map(function(i){return queue[i]})),pl=create(name,[]);addTo(pl,tr);
toast('Playlist « '+name+' » créée ('+plural(pl.tracks.length)+')');drawQueue()},drawQueue)};
now.appendChild(sv);qb.appendChild(now);
qb.appendChild(qrow(t,' now',function(){toggle()}));
var rest=order.length-pos-1,lab=make('div','qlabel');
lab.appendChild(make('span',null,'\u00c0 suivre'+(rest>0?' \u00b7 '+rest:'')));
if(rest>0){var cl=make('button','qclear','Vider');cl.type='button';cl.onclick=clearRest;lab.appendChild(cl)}
qb.appendChild(lab);
if(repeat===2){qb.appendChild(make('div','qnone','Le titre en cours se r\u00e9p\u00e8te.'))}
else if(rest<=0){qb.appendChild(make('div','qnone',repeat===1?'Rien d\u2019autre : la lecture reprend au d\u00e9but.':'Rien \u00e0 suivre.'))}
for(var i=pos+1;i<order.length;i++){(function(p){qb.appendChild(qrow(queue[order[p]],'',function(){load(p)},function(){removeAt(p)}))})(i)}}
function toggleQueue(){
qp.hidden=!qp.hidden;document.body.classList.toggle('qopen',!qp.hidden);qbtn.classList.toggle('on',!qp.hidden);qbtn.setAttribute('aria-pressed',!qp.hidden);redraw()}
// Le volet a deux onglets : la file, et les playlists (leur liste, puis le contenu de l'une d'elles).
function setView(v,id){view=v;openId=id||null;redraw()}
function redraw(){
if(qp.hidden)return;
var onq=view==='queue';
$('tabq').classList.toggle('on',onq);$('tabq').setAttribute('aria-selected',onq);
$('tabp').classList.toggle('on',!onq);$('tabp').setAttribute('aria-selected',!onq);
if(onq){drawQueue()}else if(view==='lists'){drawLists()}else{drawList()}}
// Une ligne de saisie à la place de 'host' : pour nommer une playlist.
function askName(host,initial,done,cancel){
host.textContent='';
var f=make('form','qask'),i=make('input'),ok=make('button',null,'OK'),no=make('button',null,'Annuler');
i.type='text';i.value=initial;i.maxLength=80;i.placeholder='Nom de la playlist';i.setAttribute('aria-label','Nom de la playlist');
ok.type='submit';no.type='button';f.appendChild(i);f.appendChild(ok);f.appendChild(no);host.appendChild(f);
f.onsubmit=function(e){e.preventDefault();var n=i.value.trim();if(n)done(n)};
no.onclick=cancel;i.focus();i.select()}
function drawLists(){
qb.textContent='';
var top=make('div','qbar'),nb=make('button','qnew','＋ Nouvelle playlist');nb.type='button';
nb.onclick=function(){askName(top,'',function(name){setView('list',create(name,[]).id)},drawLists)};
top.appendChild(nb);qb.appendChild(top);
if(!lists.length){qb.appendChild(make('div','qnone','Aucune playlist. Ajoutez-y des titres avec « Ajouter à une playlist… » dans le menu ⋯ d’un titre ou d’un album.'));return}
lists.forEach(function(pl){
var first=null;for(var k=0;k<pl.tracks.length&&!first;k++){first=catalog[absolute(pl.tracks[k].src)]||null}
var r=make('div','qrow'),b=make('button','qmain'),c=make('div','qcov'+(first&&first.meta.cover?' has':'')),x=make('div','qtxt');
b.type='button';if(first&&first.meta.cover)c.style.backgroundImage='url("'+first.meta.cover+'")';
x.appendChild(make('div','qt',pl.name));x.appendChild(make('div','qs',plural(pl.tracks.length)));
b.appendChild(c);b.appendChild(x);b.onclick=function(){setView('list',pl.id)};r.appendChild(b);
var pb=make('button','qx','▶');pb.type='button';pb.setAttribute('aria-label','Lire '+pl.name);pb.onclick=function(e){e.stopPropagation();playList(pl)};
r.appendChild(pb);qb.appendChild(r)})}
function drawList(){
var pl=listById(openId);
if(!pl){setView('lists');return}
qb.textContent='';
var back=make('div','qbar'),bb=make('button','qback','‹ Playlists');bb.type='button';bb.onclick=function(){setView('lists')};back.appendChild(bb);qb.appendChild(back);
var head=make('div','qptitle'),n=pl.tracks.length,known=playable(pl).length;
head.appendChild(make('div','qpn',pl.name));
head.appendChild(make('div','qs',plural(n)+(known<n?' · '+(n-known)+' introuvable'+(n-known>1?'s':''):'')));
qb.appendChild(head);
var acts=make('div','qacts'),play=make('button','qpb main','▶ Lire'),add=make('button','qpb','À la file'),ren=make('button','qpb','Renommer'),del=make('button','qpb','Supprimer');
[play,add,ren,del].forEach(function(b){b.type='button'});
play.disabled=add.disabled=!known;
play.onclick=function(){playList(pl)};
add.onclick=function(){var p=playable(pl);enqueue(p.map(function(x){return x.item}),'end',pl.name)};
ren.onclick=function(){askName(head,pl.name,function(name){pl.name=name;save();drawList()},drawList)};
del.onclick=function(){if(confirm('Supprimer la playlist « '+pl.name+' » ?')){lists.splice(lists.indexOf(pl),1);save();setView('lists')}};
[play,add,ren,del].forEach(function(b){acts.appendChild(b)});qb.appendChild(acts);
if(!n){qb.appendChild(make('div','qnone','Cette playlist est vide.'));return}
pl.tracks.forEach(function(t,k){
var c=catalog[absolute(t.src)],item=c?{title:c.title,artist:c.meta.artist,album:c.meta.album,cover:c.meta.cover}:{title:t.title,artist:'',album:'Introuvable',cover:''};
var row=qrow(item,c?'':' lost',function(){if(c)playList(pl,k)},function(){pl.tracks.splice(k,1);save();drawList()});
qb.appendChild(row)})}
// Choisir où ranger des titres : une fenêtre au-dessus de tout, avec les playlists et « Nouvelle playlist ».
function closePick(){var e=$('pick');if(e)e.remove()}
function pick(tracks){
closePick();
if(!tracks.length){toast('Ces titres ne sont pas dans la médiathèque.');return}
var ov=make('div'),box=make('div','pickbox'),body=make('div','pickbody'),host=make('div');
ov.id='pick';box.setAttribute('role','dialog');box.setAttribute('aria-label','Ajouter à une playlist');
box.appendChild(make('h3',null,'Ajouter à une playlist'));box.appendChild(body);box.appendChild(host);ov.appendChild(box);
function done(pl){
var n=addTo(pl,tracks),dup=tracks.length-n;closePick();
toast(n?'Ajouté à « '+pl.name+' »'+(dup?' ('+dup+' déjà présent'+(dup>1?'s':'')+')':''):'Déjà dans « '+pl.name+' »');redraw()}
function plus(){
host.textContent='';
var nb=make('button','pickrow','＋ Nouvelle playlist');nb.type='button';
nb.onclick=function(){askName(host,'',function(name){done(create(name,[]))},plus)};host.appendChild(nb)}
lists.forEach(function(pl){
var b=make('button','pickrow');b.type='button';b.appendChild(make('span',null,pl.name));b.appendChild(make('span','pc',plural(pl.tracks.length)));
b.onclick=function(){done(pl)};body.appendChild(b)});
plus();
ov.onclick=function(e){if(e.target===ov)closePick()};
document.body.appendChild(ov);
var f=body.querySelector('button')||host.querySelector('button');if(f)f.focus()}function fit(){var f=frame();if(f)f.style.bottom=bar.hidden?'0':bar.offsetHeight+'px'}
function go(){var r=a.play();if(r&&r.catch)r.catch(function(){})}
function load(p){
pos=p;cur().nx=false;a.src=cur().src;show();
bar.hidden=false;document.body.classList.add('playing');fit();
go();refresh();paint();drawQueue()}
function reshuffle(first){
for(var i=order.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1)),x=order[i];order[i]=order[j];order[j]=x}
if(first>=0){var k=order.indexOf(first);order[k]=order[0];order[0]=first}}
// Une file neuve : l'album, depuis la piste 'index' ; l'aléatoire, s'il est actif, la mélange en gardant cette piste en tête.
function fresh(items,index){
queue=items;natural=queue.map(function(_,i){return i});order=natural.slice();
if(index<0||index>=queue.length)index=0;
if(shuffled){reshuffle(index);load(0)}else{load(index)}}
function begin(tracks,index,m){fresh(tracks.map(function(t){return item(t,m)}),index)}
// Ajouter à la file : 'next' juste après le titre en cours - derrière ceux déjà ajoutés ainsi et pas encore joués (nx), pour qu'ils passent dans l'ordre où on les a demandés -, 'end' tout au bout. Le titre est inséré dans l'ordre de lecture, et dans l'ordre naturel que l'aléatoire désactivé retrouve. Rien en cours : l'ajout lance la lecture.
function runAfter(arr,p){var k=p+1;while(k<arr.length&&queue[arr[k]].nx)k++;return k}
function toast(text){
var e=$('toast');if(!e){e=make('div');e.id='toast';document.body.appendChild(e)}
e.textContent=text;e.hidden=false;clearTimeout(toast.t);toast.t=setTimeout(function(){e.hidden=true},2200)}
function enqueue(items,where,label){
if(pos<0||!queue.length){fresh(items,0);return}
var base=queue.length,idx=items.map(function(t,i){if(where==='next')t.nx=true;queue.push(t);return base+i}),
cq=order[pos],ao=where==='next'?runAfter(order,pos):order.length,an;
order.splice.apply(order,[ao,0].concat(idx));
an=where==='next'?runAfter(natural,natural.indexOf(cq)):natural.length;
natural.splice.apply(natural,[an,0].concat(idx));
refresh();drawQueue();
toast((where==='next'?'Lecture ensuite : ':'Ajouté à la fin : ')+label)}
function removeAt(p){var qi=order[p];order.splice(p,1);var n=natural.indexOf(qi);if(n>=0)natural.splice(n,1);refresh();drawQueue()}
function clearRest(){var gone=order.splice(pos+1);natural=natural.filter(function(i){return gone.indexOf(i)<0});refresh();drawQueue()}
function step(auto){
if(auto&&repeat===2){a.currentTime=0;go();return}
if(pos+1<order.length){load(pos+1)}
else if(repeat===1&&order.length){if(shuffled)reshuffle(-1);load(0)}
else refresh()}
function toggle(){if(a.paused||a.ended){go()}else{a.pause()}}
// Une iframe neuve à chaque fiche : sa première navigation n'ajoute rien à l'historique, et fermer la fiche la décharge.
function open(url){close('');var f=document.createElement('iframe');f.id='frame';f.title='Fiche';f.src=url;
document.body.insertBefore(f,bar);fit()}
function close(to){var f=frame();if(!f)return;f.remove();
var e=to&&$(to);
if(e)scrollTo(0,e.getBoundingClientRect().top+scrollY-head.offsetHeight-12)}
function valid(tracks){return Array.isArray(tracks)&&tracks.length>0&&tracks.every(function(t){return t&&ours(t.src)})}
function metaOf(d){return{album:String(d.album||''),artist:String(d.artist||''),page:ours(d.page)?d.page:'',
cover:typeof d.cover==='string'&&d.cover.indexOf('data:image/')===0?d.cover:''}}
window.addEventListener('message',function(e){var f=frame(),d=e.data;if(!f||e.source!==f.contentWindow||!d)return;
if(d.t==='hello'){refresh()}
else if(d.t==='toggle'){toggle()}
else if(d.t==='close'){close(String(d.to||''))}
else if(d.t==='play'&&valid(d.tracks)){begin(d.tracks,+d.index||0,metaOf(d))}
else if(d.t==='pick'&&valid(d.tracks)){pick(relTracks(d.tracks))}
else if(d.t==='enqueue'&&(d.where==='next'||d.where==='end')&&valid(d.tracks)){
var m=metaOf(d),items=d.tracks.map(function(t){return item(t,m)});
enqueue(items,d.where,items.length>1?m.album:items[0].title)}});
side.onclick=function(){var t=cur();if(t&&t.page)open(t.page)};
qbtn.onclick=toggleQueue;$('qclose').onclick=toggleQueue;
$('tabq').onclick=function(){setView('queue')};$('tabp').onclick=function(){setView('lists')};
document.addEventListener('keydown',function(e){
if(e.key!=='Escape')return;
if($('pick')){closePick();return}
if(!qp.hidden)toggleQueue()});
bPlay.onclick=function(){if(pos<0){return}toggle()};
bPrev.onclick=function(){if(a.currentTime>3||pos===0){a.currentTime=0}else{load(pos-1)}};
bNext.onclick=function(){step(false)};
bShuffle.onclick=function(){
var t=cur(),ci=t?order[pos]:-1;
shuffled=!shuffled;
if(shuffled){reshuffle(ci);pos=ci>=0?0:-1}
else{order=natural.slice();pos=ci>=0?order.indexOf(ci):-1}
bShuffle.classList.toggle('on',shuffled);bShuffle.setAttribute('aria-pressed',shuffled);refresh();drawQueue()};
bRepeat.onclick=function(){
repeat=(repeat+1)%3;
bRepeat.classList.toggle('on',repeat>0);bRepeat.classList.toggle('one',repeat===2);
bRepeat.setAttribute('aria-pressed',repeat>0);refresh();drawQueue()};
function at(e){var r=seek.getBoundingClientRect();return Math.min(1,Math.max(0,(e.clientX-r.left)/r.width))}
seek.addEventListener('pointerdown',function(e){
if(!cur()||!length())return;
drag=true;seek.setPointerCapture(e.pointerId);paint(at(e))});
seek.addEventListener('pointermove',function(e){if(drag)paint(at(e))});
seek.addEventListener('pointerup',function(e){
if(!drag)return;
drag=false;a.currentTime=at(e)*length();paint()});
seek.addEventListener('pointercancel',function(){drag=false;paint()});
seek.addEventListener('keydown',function(e){
var d=e.key==='ArrowRight'?5:e.key==='ArrowLeft'?-5:0;
if(d&&cur()){a.currentTime=Math.max(0,a.currentTime+d);e.preventDefault()}});
vol.oninput=function(){a.volume=vol.value/100;a.muted=false;vol.style.setProperty('--v',vol.value+'%')};
bMute.onclick=function(){a.muted=!a.muted};
a.addEventListener('volumechange',function(){bMute.classList.toggle('muted',a.muted||a.volume===0)});
a.addEventListener('play',refresh);a.addEventListener('pause',refresh);
a.addEventListener('ended',function(){refresh();step(true)});
a.addEventListener('timeupdate',function(){if(!drag)paint()});
a.addEventListener('durationchange',function(){if(!drag)paint()});
a.addEventListener('error',function(){
var t=cur();if(!t)return;
song.className='bad';song.textContent='Lecture impossible : '+t.title;refresh()});
function list(b){return JSON.parse(b.getAttribute('data-t')).map(function(t){return{src:new URL(t[0],location.href).href,title:t[1]}})}
document.addEventListener('click',function(ev){
var l=ev.target.closest&&ev.target.closest('a[href]');
if(l&&!l.target&&ev.button===0&&!ev.ctrlKey&&!ev.metaKey&&!ev.shiftKey&&!ev.altKey&&(l.closest('.al')||l.closest('h2'))){
ev.preventDefault();ev.stopImmediatePropagation();open(l.href);return}
var b=ev.target.closest&&ev.target.closest('button.ov');if(!b)return;
if(b===curBtn&&curSrcs.indexOf(nowSrc())>=0){toggle();return}
var was=curBtn,al=b.closest('.al'),link=al.querySelector('a.cv'),im=al.querySelector('img'),h=al.closest('section').querySelector('h2'),
tracks=list(b);
curBtn=b;curSrcs=tracks.map(function(x){return x.src});
if(was&&was!==b){was.className='ov';was.textContent='▶'}
begin(tracks,0,{album:al.querySelector('.t').textContent,artist:h?h.firstChild.textContent:'',page:link?link.href:'',cover:im?im.src:''})});
refresh();paint();
})();
"""
