"""Noms de fichiers : les gestes communs à toutes les médiathèques.

Nettoyer un titre pour en faire un nom valide sous Windows, lister les fichiers d'un dossier par extension, afficher un chemin sans son préfixe commun. Ce qui lit le contenu d'un nom - saison, épisode, titre et année d'un film - dépend du domaine et reste dans libraries/video/naming.py.
"""

import re
from pathlib import Path


def safe_name(s):
    """Nettoie un titre pour en faire un nom de fichier valide sous Windows."""
    s = re.sub(r'[<>:"/\\|?*]', "", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s.rstrip(". ")


def files_with_ext(folder, extensions):
    """Fichiers d'un dossier dont l'extension figure dans `extensions`, triés.

    Un dossier illisible rend une liste vide : l'existence de --dir est vérifiée une fois pour toutes au démarrage, le reste n'a pas à s'en soucier.
    """
    try:
        return sorted(f for f in Path(folder).iterdir() if f.is_file() and f.suffix.lower() in extensions)
    except OSError:
        return []


def relative_name(path, root):
    """Chemin affichable : ce qui distingue le fichier, sans le préfixe commun."""
    try:
        return str(Path(path).relative_to(root))
    except ValueError:                               # hors de la racine (lien, montage)
        return str(path)
