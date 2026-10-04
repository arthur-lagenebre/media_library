"""Icônes d'onglet des fiches HTML, écrites dans la page elle-même.

Une icône en SVG tient dans un attribut (data-URI) : la fiche reste un fichier unique, sans favicon.ico à transférer à côté, et rien n'est à télécharger ni à dessiner avec une bibliothèque d'images.

Une fiche de série prend un monogramme : ses initiales sur une couleur tirée de son titre. À 16 pixels, une affiche réduite n'est plus qu'une tache ; deux lettres restent lisibles, et la couleur suffit souvent à retrouver un onglet parmi d'autres.
"""

import colorsys
import hashlib
import re
from urllib.parse import quote
from xml.sax.saxutils import escape

# Mots qui ne donnent pas d'initiale : "Game of Thrones" s'écrit GT, "The Expanse" E.
SMALL_WORDS = {"the", "a", "an", "of", "and", "le", "la", "les", "l", "un", "une",
               "de", "du", "des", "d", "et", "en", "au", "aux"}
WORD_RE = re.compile(r"\w+")
WIDE_LETTERS = set("MWÆŒ")

# Le sommaire : un téléviseur dans les couleurs des fiches (fond sombre, accent bleu).
INDEX_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
    "<rect width='64' height='64' rx='14' fill='#1c1e26'/>"
    "<path d='M23 9l9 9 9-9' fill='none' stroke='#7cc4ff' stroke-width='4' "
    "stroke-linecap='round' stroke-linejoin='round'/>"
    "<rect x='8' y='19' width='48' height='35' rx='7' fill='#7cc4ff'/>"
    "<path d='M28 29v15l13-7.5z' fill='#1c1e26'/>"
    "</svg>")

# La fiche des films : un clap, dans les mêmes couleurs. Le haut du clap est incliné, comme ouvert, pour se lire comme tel même à 16 pixels.
FILMS_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
    "<rect width='64' height='64' rx='14' fill='#1c1e26'/>"
    "<rect x='9' y='28' width='46' height='27' rx='4' fill='#7cc4ff'/>"
    "<path d='M9 22l43-11 2.6 9.5L11.6 31.5z' fill='#7cc4ff'/>"
    "<path d='M19 19.4l6 9.3M31 16.3l6 9.3M43 13.2l6 9.3' stroke='#1c1e26' stroke-width='4'/>"
    "</svg>")

# Les livres : trois dos sur une étagère, dans les mêmes couleurs ; le dernier est penché pour qu'on y lise des livres, pas des barres, même à 16 pixels.
SHELF_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
    "<rect width='64' height='64' rx='14' fill='#1c1e26'/>"
    "<rect x='11' y='13' width='11' height='36' rx='2' fill='#7cc4ff'/>"
    "<rect x='26' y='9' width='11' height='40' rx='2' fill='#7cc4ff'/>"
    "<path d='M41 19l10-3 6 31-10 3z' fill='#7cc4ff'/>"
    "<rect x='8' y='52' width='48' height='4' rx='2' fill='#7cc4ff'/>"
    "</svg>")


def initials(title):
    """'BB' pour Breaking Bad, 'D' pour Dark, '24' pour 24 ; '?' pour un titre vide.

    Les petits mots sont sautés, sauf s'il n'y a qu'eux ("Les" donne L, pas "?"). Un nombre reste entier : "9-1-1" donne 9, mais "24" ne devient pas "2".
    """
    words = WORD_RE.findall(title or "")
    kept = [w for w in words if w.casefold() not in SMALL_WORDS] or words
    if not kept:
        return "?"
    if len(kept) == 1 or kept[0].isdigit():
        first = kept[0]
        return first[:2] if first.isdigit() else first[0].upper()
    return (kept[0][0] + kept[1][0]).upper()


def color(title):
    """Couleur propre à un titre, stable d'un passage à l'autre.

    hash() de Python change à chaque lancement : la couleur d'une série changerait à chaque régénération. Seule la teinte varie ; la luminosité reste assez basse pour qu'un texte blanc se lise sur toutes, jaunes comprises.
    """
    hue = int(hashlib.md5((title or "").casefold().encode("utf-8")).hexdigest()[:4], 16) / 0xFFFF
    r, g, b = colorsys.hls_to_rgb(hue, 0.38, 0.55)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def monogram_svg(title):
    letters = initials(title)
    # Un W ou un M est presque deux fois plus large qu'un I : "WW" à la taille de "BB" déborderait du carré.
    wide = sum(1 for c in letters if c in WIDE_LETTERS)
    size = (34 if len(letters) > 1 else 42) - 5 * wide
    return (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
        f"<rect width='64' height='64' rx='14' fill='{color(title)}'/>"
        f"<text x='32' y='33' text-anchor='middle' dominant-baseline='central' fill='#fff' "
        f"font-family='system-ui,Segoe UI,sans-serif' font-weight='700' font-size='{size}'>"
        f"{escape(letters)}</text></svg>")


def link(svg):
    """Balise <link rel='icon'> portant le SVG encodé dans la page."""
    return f"<link rel='icon' type='image/svg+xml' href='data:image/svg+xml,{quote(svg, safe='')}'>"


def monogram_link(title):
    return link(monogram_svg(title))


def index_link():
    return link(INDEX_SVG)


def films_link():
    return link(FILMS_SVG)


def shelf_link():
    return link(SHELF_SVG)
