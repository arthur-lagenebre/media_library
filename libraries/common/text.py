"""Texte à classer : sans accents ni casse, et la lettre sous laquelle un titre se range.

Ce qui servait aux pages HTML et sert encore à quiconque lit la médiathèque (le serveur media_hub range ses titres de la même façon).
"""

import string
import unicodedata

# Les ligatures ne se décomposent pas : "Œil pour Œil" se range à O, pas à #.
LIGATURES = str.maketrans({"Œ": "O", "œ": "o", "Æ": "A", "æ": "a"})


# Les apostrophes typographiques (U+2019, et la lettre modificatrice U+02BC que certains claviers produisent à sa place) et les guillemets doubles courbes (U+201C, U+201D, U+201E, U+201F), que MusicBrainz et TMDB écrivent souvent. Les « » du français sont une typographie, pas une variante : ils restent.
DOUBLE_QUOTES = str.maketrans({chr(code): chr(0x22) for code in (0x201C, 0x201D, 0x201E, 0x201F)})
ALL_QUOTES = str.maketrans({**{chr(code): chr(0x22) for code in (0x201C, 0x201D, 0x201E, 0x201F)}, chr(0x2019): chr(0x27), chr(0x02BC): chr(0x27)})
OPENING_QUOTE = chr(0x2018)


def straight_quotes(text):
    """L'apostrophe et le guillemet double droits, partout : une seule écriture dans la médiathèque, la seule que tous les claviers, tous les lecteurs et toutes les recherches reconnaissent.

    Un texte qui contient un guillemet simple ouvrant (‘mot’) garde ses apostrophes courbes : fermer en apostrophe droite laisserait une paire dépareillée. Ses guillemets doubles, eux, sont redressés.
    """
    return text.translate(DOUBLE_QUOTES if OPENING_QUOTE in text else ALL_QUOTES)


def fold(text):
    """Texte pour classer : sans accents ni casse ('Éden' se range entre 'Dune' et 'Fargo', pas après 'Zorro')."""
    plain = "".join(c for c in unicodedata.normalize("NFD", (text or "").translate(LIGATURES)) if not unicodedata.combining(c))
    return plain.casefold()


def initial(text):
    """Lettre sous laquelle un titre se range : 'É' -> 'E', 'Le robot' -> 'L' (on ne retire pas les articles), un chiffre ou autre chose -> '#'."""
    for c in unicodedata.normalize("NFD", (text or "").translate(LIGATURES)):
        if unicodedata.combining(c):
            continue
        if c.isalnum():
            c = c.upper()
            return c if c in string.ascii_uppercase else "#"
    return "#"
