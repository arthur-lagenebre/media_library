"""Pages et journaux écrits à l'identique, et réécrits seulement quand ils changent.

Lancées chaque nuit sur un NAS, les fiches ne doivent ni réveiller les disques ni changer de date tant que la médiathèque ne bouge pas : il faut pouvoir dire qu'un fichier contient déjà ce qu'on s'apprête à y écrire. Ça suppose de relire exactement ce qu'on a écrit. Or Python traduit les fins de ligne dans les deux sens - "\\n" devient "\\r\\n" à l'écriture sous Windows, et un "\\r" isolé devient "\\n" à la lecture partout -, et des synopsis TMDB portent de tels "\\r" : relue, la page ne ressemblait jamais à elle-même. Ici, rien n'est traduit, ni à l'écriture ni à la lecture.

S'y ajoute un service des pages elles-mêmes : relire leur titre.
"""

import re
from html import unescape
from pathlib import Path


def same(path, text, skip_lines=0):
    """Vrai si `path` contient déjà `text`, ses `skip_lines` premières lignes mises à part (un horodatage)."""
    try:
        with open(path, encoding="utf-8", newline="") as f:
            current = f.read()
    except (OSError, UnicodeDecodeError):
        return False
    return current.split("\n")[skip_lines:] == text.split("\n")[skip_lines:]


def write(path, text):
    """Écrit `text` tel quel, sans traduire les fins de ligne."""
    with open(Path(path), "w", encoding="utf-8", newline="") as f:
        f.write(text)


TITLE_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL)
HEAD_SIZE = 65536           # le <title> est en tête : inutile de lire les images qui suivent


def title_of(path):
    """Titre d'une page déjà écrite, ou None : un titre choisi une fois (--title) doit survivre aux passages suivants, ceux d'une tâche planifiée compris."""
    try:
        with open(path, encoding="utf-8", errors="replace", newline="") as f:
            found = TITLE_RE.search(f.read(HEAD_SIZE))
    except OSError:
        return None
    return unescape(found.group(1)).strip() or None if found else None
