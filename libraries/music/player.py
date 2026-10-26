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
    "#all{margin-top:16px;padding:9px 18px;border:0;border-radius:20px;background:#7cc4ff;color:#14151a;font:600 14px system-ui,sans-serif;cursor:pointer}"
    "#all:hover{background:#a6d8ff}"
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

ALL_BUTTON = "<div><button id='all' type='button'>▶ Tout lire</button></div>"


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
    "framed=window.parent!==window,cur=-1,paused=true,start,toggle;"
    "function mark(){"
    "btns.forEach(function(b,k){var on=k===cur;b.parentNode.parentNode.className=on?'now':'';b.textContent=on&&!paused?'❚❚':'▶'});"
    "all.textContent=cur<0?'▶ Tout lire':paused?'▶ Reprendre':'❚❚ Pause'}"
    "btns.forEach(function(b,k){b.onclick=function(){if(k===cur){toggle()}else{start(k)}}});"
    "all.onclick=function(){if(cur<0){start(0)}else{toggle()}};"
    "if(framed){"
    "start=function(i){var ar=document.querySelector('.artist'),im=document.querySelector('.cov img');"
    "window.parent.postMessage({t:'play',tracks:tracks,index:i,album:document.title,page:location.href,artist:ar?ar.textContent:'',cover:im?im.src:''},'*')};"
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

ICONS = {
    "shuffle": "M10.59 9.17 5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z",
    "prev": "M6 6h2v12H6zm3.5 6 8.5 6V6z",
    "next": "M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z",
    "play": "M8 5v14l11-7z",
    "pause": "M6 19h4V5H6v14zm8-14v14h4V5h-4z",
    "repeat": "M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z",
    "repeat-one": "M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4zm-4-2V9h-1l-2 1v1h1.5v4H13z",
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
    "#vol{width:110px;accent-color:#7cc4ff;cursor:pointer}"
    "body.playing .page{padding-bottom:96px}"
    "@media(max-width:760px){#bar{grid-template-columns:1fr auto;padding:0 12px}.end,#time,#shuffle,#repeat{display:none}}"
)

# Sur le sommaire : le bouton des pochettes, la barre, et la fiche qui s'ouvre par-dessus. L'iframe couvre toute la fenêtre sauf la barre (sa hauteur est posée par le script) ; elle passe au-dessus de l'en-tête fixe du sommaire (z-index 10), et la barre au-dessus d'elle.
INDEX_CSS = (
    OVERLAY_CSS
    + MAIN_BAR_CSS
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
        + _button("mute", "Couper le son", ("volume", "i-vol"), ("muted", "i-muted"))
        + "<input id='vol' type='range' min='0' max='100' value='100' aria-label='Volume'></div>"
        "<audio id='player' preload='none'></audio></div>"
    )


# Le script du sommaire : la barre et sa file de lecture, les boutons des pochettes, et la fiche qui s'ouvre par-dessus. La file est l'album en cours : 'order' est l'ordre de lecture (celui de l'album, ou un tirage au hasard), 'pos' la place de la piste en cours dedans, et 'repeat' vaut 0 (rien), 1 (l'album) ou 2 (la piste). Les pistes de chaque album sont dans l'attribut data-t de son bouton, lues seulement au clic ; un clic sur un lien d'artiste ou de pochette ouvre sa fiche dans l'iframe (un clic avec une touche, ou un lien vers un autre onglet, reste normal). La page n'accepte que les messages de son iframe, et que des liens du même protocole qu'elle (file:// ici, http:// ailleurs) : une fiche qui sortirait de la médiathèque ne lui ferait lire rien d'étranger. Un 'hello' est la fiche qui vient de se charger et demande ce qui joue ; un 'close', le lien « ← Musique » de la fiche ; un 'play' porte aussi l'artiste et la pochette de l'album, que la barre montre. Ce script se place avant celui du retour au sommaire : un lien qu'il prend n'est pas vu de l'autre.
INDEX_SCRIPT = r"""(function(){
function $(id){return document.getElementById(id)}
var a=$('player'),bar=$('bar'),seek=$('seek'),fill=$('fill'),cover=$('cover'),song=$('song'),sub=$('sub'),time=$('time'),side=document.querySelector('.side'),
bShuffle=$('shuffle'),bPrev=$('prev'),bPlay=$('play'),bNext=$('next'),bRepeat=$('repeat'),bMute=$('mute'),vol=$('vol'),
head=document.querySelector('.top'),base=document.title,
queue=[],order=[],pos=-1,shuffled=false,repeat=0,drag=false,meta={album:'',artist:'',cover:'',page:''},curBtn=null,curSrcs=[];
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
sub.textContent=t?(meta.artist?meta.artist+' – ':'')+meta.album:'';
cover.style.backgroundImage=t&&meta.cover?'url("'+meta.cover+'")':'';
cover.className=t&&meta.cover?'has':'';
side.className=meta.page?'side go':'side';side.title=meta.page?'Ouvrir la fiche de cet album':'';
document.title=t?t.title+(meta.artist?' · '+meta.artist:''):base}
function fit(){var f=frame();if(f)f.style.bottom=bar.hidden?'0':bar.offsetHeight+'px'}
function go(){var r=a.play();if(r&&r.catch)r.catch(function(){})}
function load(p){
pos=p;a.src=cur().src;show();
bar.hidden=false;document.body.classList.add('playing');fit();
go();refresh();paint()}
function reshuffle(first){
for(var i=order.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1)),x=order[i];order[i]=order[j];order[j]=x}
if(first>=0){var k=order.indexOf(first);order[k]=order[0];order[0]=first}}
// Une file neuve : l'album, depuis la piste 'index' ; l'aléatoire, s'il est actif, la mélange en gardant cette piste en tête.
function begin(tracks,index,m){
queue=tracks;meta=m;order=queue.map(function(_,i){return i});
if(index<0||index>=queue.length)index=0;
if(shuffled){reshuffle(index);load(0)}else{load(index)}}
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
window.addEventListener('message',function(e){var f=frame(),d=e.data;if(!f||e.source!==f.contentWindow||!d)return;
if(d.t==='hello'){refresh()}
else if(d.t==='toggle'){toggle()}
else if(d.t==='close'){close(String(d.to||''))}
else if(d.t==='play'&&Array.isArray(d.tracks)&&d.tracks.length&&d.tracks.every(function(t){return t&&ours(t.src)})){
begin(d.tracks.map(function(t){return{src:t.src,title:String(t.title||'')}}),+d.index||0,
{album:String(d.album||''),artist:String(d.artist||''),page:ours(d.page)?d.page:'',
cover:typeof d.cover==='string'&&d.cover.indexOf('data:image/')===0?d.cover:''})}});
side.onclick=function(){if(meta.page)open(meta.page)};
bPlay.onclick=function(){if(pos<0){return}toggle()};
bPrev.onclick=function(){if(a.currentTime>3||pos===0){a.currentTime=0}else{load(pos-1)}};
bNext.onclick=function(){step(false)};
bShuffle.onclick=function(){
var t=cur(),ci=t?order[pos]:-1;
shuffled=!shuffled;
if(shuffled){reshuffle(ci);pos=ci>=0?0:-1}
else{order=queue.map(function(_,i){return i});pos=ci}
bShuffle.classList.toggle('on',shuffled);bShuffle.setAttribute('aria-pressed',shuffled);refresh()};
bRepeat.onclick=function(){
repeat=(repeat+1)%3;
bRepeat.classList.toggle('on',repeat>0);bRepeat.classList.toggle('one',repeat===2);
bRepeat.setAttribute('aria-pressed',repeat>0);refresh()};
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
vol.oninput=function(){a.volume=vol.value/100;a.muted=false};
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
