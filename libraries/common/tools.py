"""Lancer un outil externe, et nommer le fichier qu'il écrit en attendant qu'il soit jugé sain (mkvmerge, ffmpeg)."""

import subprocess


def run_tool(cmd, **kwargs):
    """Lance un outil externe et récupère sa sortie, décodée en UTF-8.

    Préciser l'encodage n'est pas un détail : mkvmerge et ffprobe écrivent leur JSON en UTF-8, alors que Python décoderait avec l'encodage local (cp1252 sous Windows). Il suffit d'un caractère absent de cp1252 dans un synopsis - le trait d'union typographique de "est-ce" en fournit un - pour que le décodage echoue dans un thread interne de subprocess : la sortie revient alors à None, sans erreur ni code de retour anormal, et le fichier devient illisible juste après avoir été étiqueté.
    """
    return subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", **kwargs)


PARTIAL_SUFFIX = ".part"


def partial_path(path):
    """Nom sous lequel un fichier converti s'écrit avant d'avoir été contrôlé : `Film.mkv` -> `Film.mkv.part`.

    mkvmerge et ffmpeg écrivent directement là où on le leur dit : une coupure, un échec ou un résultat suspect laisseraient un `Film.mkv` tronqué que les passages suivants prendraient pour un film (ou pour une conversion déjà faite). Sous ce nom-là aucun script ne le voit ; le fichier ne prend son vrai nom qu'une fois jugé sain.
    """
    return path.with_name(path.name + PARTIAL_SUFFIX)
