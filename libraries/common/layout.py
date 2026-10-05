"""Mise en page commune des pages HTML : en-tête fixe, zone de recherche, bouton de largeur.

Les trois sommaires (films, séries, livres) et leurs fiches se présentent de la même façon : un en-tête qui reste en haut quand on fait défiler, et un bouton qui bascule entre deux largeurs. Sur un sommaire, "pleine largeur" ou "7 par ligne" ; sur une fiche, "pleine largeur" ou "centrée". Le choix est un seul réglage, gardé dans le navigateur : il suit d'une page à l'autre.

Tout est pur : ce module ne rend que des morceaux de page, que chacune assemble.
"""

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
    ".mode:hover{background:#252833}"
    ".filter{width:100%;max-width:320px;margin:0;padding:8px 14px;font:inherit;font-size:14px;color:#e8e8ea;background:#1c1e26;border:1px solid #2a2c34;border-radius:999px;outline:none;box-sizing:border-box}"
    ".filter:focus{border-color:#7cc4ff}"
    ".wide .wrap{max-width:none}"
    # Le retour depuis une fiche ramène à une vignette par son ancre : sans cette marge, l'en-tête fixe la recouvrirait.
    "html{scroll-padding-top:190px}"
)


def header(inner):
    """L'en-tête fixe. Son contenu est calé sur la même largeur que la page (.wrap), pleine ou centrée."""
    return f"<header class='top'><div class='wrap'>{inner}</div></header><div class='wrap page'>"


def mode_button(labels=INDEX_LABELS):
    """Le bouton de largeur ; son texte est celui du mode qu'il fait prendre."""
    return f"<button class='mode' type='button' aria-pressed='false'>{labels[0]}</button>"


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
