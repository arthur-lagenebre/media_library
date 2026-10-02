"""Pages et journaux écrits à l'identique, et réécrits seulement quand ils changent.

Lancées chaque nuit sur un NAS, les fiches ne doivent ni réveiller les disques ni changer de date tant que la médiathèque ne bouge pas : il faut pouvoir dire qu'un fichier contient déjà ce qu'on s'apprête à y écrire. Ça suppose de relire exactement ce qu'on a écrit. Or Python traduit les fins de ligne dans les deux sens - "\\n" devient "\\r\\n" à l'écriture sous Windows, et un "\\r" isolé devient "\\n" à la lecture partout -, et des synopsis TMDB portent de tels "\\r" : relue, la page ne ressemblait jamais à elle-même. Ici, rien n'est traduit, ni à l'écriture ni à la lecture.
"""

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
