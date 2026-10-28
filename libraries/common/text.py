"""Texte à classer : sans accents ni casse, et la lettre sous laquelle un titre se range.

Ce qui servait aux pages HTML et sert encore à quiconque lit la médiathèque (le serveur media_hub range ses titres de la même façon).
"""

import string
import unicodedata

# Les ligatures ne se décomposent pas : "Œil pour Œil" se range à O, pas à #.
LIGATURES = str.maketrans({"Œ": "O", "œ": "o", "Æ": "A", "æ": "a"})


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
