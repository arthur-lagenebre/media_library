"""Mise en page commune des pages HTML : en-tête fixe, zone de recherche, bouton de largeur.

Les trois sommaires (films, séries, livres) et leurs fiches se présentent de la même façon : un en-tête qui reste en haut quand on fait défiler, et un bouton qui bascule entre deux largeurs. Sur un sommaire, "pleine largeur" ou "7 par ligne" ; sur une fiche, "pleine largeur" ou "centrée". Le choix est un seul réglage, gardé dans le navigateur : il suit d'une page à l'autre.

Tout est pur : ce module ne rend que des morceaux de page, que chacune assemble.
"""

import string
import unicodedata
from xml.sax.saxutils import escape

# Appliqué dans le <head>, avant le <style> : sinon la page s'afficherait dans l'autre largeur avant de basculer. localStorage peut être refusé (page ouverte hors serveur, navigation privée) : la page marche alors sans, centrée.
BOOT = "<script>try{if(localStorage.getItem('wide')==='1')document.documentElement.classList.add('wide')}catch(e){}</script>"

# Deux boutons de largeur : sur un sommaire (vignettes) et sur une fiche (texte).
INDEX_LABELS = ("Pleine largeur", "7 par ligne")
SHEET_LABELS = ("Pleine largeur", "Centrée")

CSS = (
    ".top{position:sticky;top:0;z-index:10;background:#14151a;border-bottom:1px solid #21232b}"
    ".top .wrap{padding-top:12px;padding-bottom:12px}.top h1{font-size:26px;line-height:1.25}"
    ".wrap.page{padding-top:12px}"
    ".row{display:flex;align-items:center;justify-content:space-between;gap:12px}"
    ".bar{display:flex;flex-direction:column;align-items:flex-start;gap:8px;margin-top:8px}"
    ".mode{cursor:pointer;border:1px solid #2a2c34;background:#1c1e26;color:#c7ccd4;padding:7px 16px;border-radius:999px;font:inherit;font-size:14px;flex:none}"
    ".mode:hover,.totop:hover{background:#252833}"
    ".ctl{display:flex;gap:8px;flex:none}"
    ".totop{cursor:pointer;border:1px solid #2a2c34;background:#1c1e26;color:#c7ccd4;padding:7px 14px;border-radius:999px;font:inherit;font-size:14px}"
    ".filter{width:100%;max-width:320px;margin:0;padding:8px 14px;font:inherit;font-size:14px;color:#e8e8ea;background:#1c1e26;border:1px solid #2a2c34;border-radius:999px;outline:none;box-sizing:border-box}"
    ".filter:focus,.genre:focus{border-color:#7cc4ff}"
    ".genre{max-width:220px;padding:8px 14px;font:inherit;font-size:14px;color:#e8e8ea;background:#1c1e26;border:1px solid #2a2c34;border-radius:999px;outline:none;cursor:pointer}"
    ".wide .wrap{max-width:none}"
    ".line{display:flex;flex-wrap:wrap;align-items:center;gap:8px}"
    ".chip{cursor:pointer;border:1px solid #2a2c34;background:transparent;color:#9aa0aa;padding:5px 12px;border-radius:999px;font:inherit;font-size:13px}"
    ".chip:hover{background:#252833;color:#e8e8ea}"
    ".az{display:flex;flex-wrap:wrap;gap:2px;margin-top:8px}"
    ".az button{cursor:pointer;min-width:26px;padding:3px 0;border:0;border-radius:6px;background:transparent;color:#7cc4ff;font:inherit;font-size:13px;font-weight:600}"
    ".az button:hover:not(:disabled){background:#252833}"
    ".az button:disabled{color:#4a4d57;cursor:default}"
    # Le retour depuis une fiche ramène à une vignette par son ancre : sans cette marge, l'en-tête fixe la recouvrirait.
    "html{scroll-padding-top:230px}"
)


def header(inner):
    """L'en-tête fixe. Son contenu est calé sur la même largeur que la page (.wrap), pleine ou centrée."""
    return f"<header class='top'><div class='wrap'>{inner}</div></header><div class='wrap page'>"


def mode_button(labels=INDEX_LABELS):
    """Le bouton de largeur ; son texte est celui du mode qu'il fait prendre. Le retour en haut l'accompagne : l'en-tête est fixe, il est donc toujours sous la main."""
    return (f"<span class='ctl'><button class='mode' type='button' aria-pressed='false'>{labels[0]}</button>"
            "<button class='totop' type='button' aria-label='Retour en haut' onclick=\"window.scrollTo({top:0,behavior:'smooth'})\">↑ Haut</button></span>")


def mode_script(labels=INDEX_LABELS):
    """Le script du bouton : bascule la classe 'wide' de la page et retient le choix."""
    return (
        "var m=document.querySelector('.mode'),root=document.documentElement;"
        "function wide(on){root.classList.toggle('wide',on);"
        f"m.textContent=on?'{labels[1]}':'{labels[0]}';m.setAttribute('aria-pressed',on)}}"
        "wide(root.classList.contains('wide'));"
        "m.onclick=function(){var on=!root.classList.contains('wide');wide(on);"
        "try{localStorage.setItem('wide',on?'1':'0')}catch(e){}};"
    )


# ----------------------------------------------------------------------------
# Genres
# ----------------------------------------------------------------------------
GENRE_SEP = "|"


def genre_attr(genres):
    """L'attribut data-g d'une vignette : ses genres, séparés par GENRE_SEP. Vide, il est omis : la vignette n'a alors aucun genre à montrer."""
    names = [g for g in genres if g]
    return f" data-g='{escape(GENRE_SEP.join(names), {chr(39): '&#39;'})}'" if names else ""


def genre_select(counts):
    """La liste des genres, du plus fréquent au moins fréquent (puis par nom), avec leur compte. 'counts' = {genre: nombre de vignettes} ; sans aucun genre, rien n'est rendu : un menu vide ne filtrerait rien."""
    if not counts:
        return ""
    options = "".join(
        f"<option value='{escape(g, {chr(39): '&#39;'})}'>{escape(g)} ({n})</option>"
        for g, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].casefold())))
    return f"<select class='genre' aria-label='Filtrer par genre'><option value=''>Tous les genres</option>{options}</select>"


def genre_script():
    """Le script du menu : `gok(vignette)` dit si une vignette passe le genre choisi, `picked()` s'il y en a un. À placer avant le filtre de la page, qui s'en sert et relance son propre filtre quand le choix change (`f.oninput`, relu à chaque fois : l'index A-Z l'enveloppe plus tard)."""
    return (
        "var g=document.querySelector('.genre');"
        "function picked(){return !!(g&&g.value)}"
        f"function gok(c){{return !picked()||(c.getAttribute('data-g')||'').split('{GENRE_SEP}').indexOf(g.value)>=0}}"
        "if(g)g.onchange=function(){f.oninput()};"
    )


# ----------------------------------------------------------------------------
# Index alphabétique
# ----------------------------------------------------------------------------
LETTERS = list(string.ascii_uppercase) + ["#"]


# Les ligatures ne se décomposent pas : "Œil pour Œil" se range à O, pas à #.
LIGATURES = str.maketrans({"Œ": "O", "œ": "o", "Æ": "A", "æ": "a"})


def initial(text):
    """Lettre sous laquelle un titre se range : 'É' -> 'E', 'Le robot' -> 'L' (la page classe sans retirer les articles), un chiffre ou autre chose -> '#'."""
    for c in unicodedata.normalize("NFD", (text or "").translate(LIGATURES)):
        if unicodedata.combining(c):
            continue
        if c.isalnum():
            c = c.upper()
            return c if c in string.ascii_uppercase else "#"
    return "#"


def index_nav():
    """La barre A-Z de l'en-tête. Chaque lettre mène à l'élément suivant qui porte data-i="<lettre>" ; le script grise celles qui n'en ont aucun."""
    return ("<nav class='az' aria-label='Index alphabétique'>"
            + "".join(f"<button type='button' data-l='{c}'>{c}</button>" for c in LETTERS) + "</nav>")


def index_script():
    """Le script de la barre A-Z (et des raccourcis .chip[data-t=<id d'une section>]).

    Une lettre mène à la première occurrence APRÈS la position courante, et revient au début passé la dernière : la même lettre, pressée de nouveau, parcourt tous ses éléments - ceux d'une saga puis ceux des films seuls, d'une section puis de la suivante. Tant qu'on enchaîne (sans défiler à la main), la lettre part de la ligne du dernier élément visé et non de la position de la page : en bas de page, la cible ne peut pas monter jusqu'en haut, et la position seule la reviserait sans fin. Les éléments masqués par la recherche sont ignorés, et leurs lettres grisées."""
    return (
        "var bar=document.querySelector('.top'),last=null;"
        "function seen(e){return e.offsetParent!==null}"
        "function go(e){window.scrollTo({top:e.getBoundingClientRect().top+window.scrollY-bar.offsetHeight-12,behavior:'smooth'})}"
        "function az(){var have={};"
        "document.querySelectorAll('[data-i]').forEach(function(e){if(seen(e))have[e.getAttribute('data-i')]=1});"
        "document.querySelectorAll('.az button').forEach(function(b){b.disabled=!have[b.getAttribute('data-l')]});"
        "document.querySelectorAll('.chip').forEach(function(b){b.hidden=!seen(document.getElementById(b.getAttribute('data-t')))})}"
        "document.querySelectorAll('.az button').forEach(function(b){b.onclick=function(){"
        "var here=window.scrollY+bar.offsetHeight+16,"
        "list=[].filter.call(document.querySelectorAll('[data-i]'),function(e){return e.getAttribute('data-i')===b.getAttribute('data-l')&&seen(e)}),"
        "from=last&&list.indexOf(last)>=0?last.getBoundingClientRect().top+window.scrollY+5:here,"
        "after=list.filter(function(e){return e.getBoundingClientRect().top+window.scrollY>from}),"
        "next=after[0]||list[0];"
        "last=next;if(next)go(next)}});"
        "['wheel','touchmove','keydown'].forEach(function(t){addEventListener(t,function(){last=null},{passive:true})});"
        "document.querySelectorAll('.chip').forEach(function(b){b.onclick=function(){go(document.getElementById(b.getAttribute('data-t')))}});"
        "var typed=f.oninput;f.oninput=function(){typed();az()};az();"
    )
