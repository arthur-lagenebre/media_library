"""Décoder une piste avec ffmpeg pour savoir si elle passe : ce que le contrôle de structure (integrity.py) ne peut pas voir.

Un .flac abîmé au milieu a une structure saine : seul le CRC de chaque trame, ou l'empreinte MD5 du son, le dit. Cela demande de lire le fichier en entier et de le décoder.
"""

import re
import subprocess

from libraries.common.tools import read_timeout, run_tool

# Fait échouer le décodage à la première trame qui ne passe pas son CRC ou sa syntaxe : sans lui ffmpeg se contente de l'ignorer et sort en code 0, même sur un FLAC dont un octet a changé.
STRICT = "+crccheck+bitstream+buffer+explode"
ADDRESS_RE = re.compile(r"^\[[^\]]*@ (?:0x)?[0-9a-fA-F]+\]\s*")   # « [flac @ 0000029c0c36a380] » : une adresse mémoire, qui change à chaque passage


def command(path, bits=None):
    """La commande ffmpeg qui décode la première piste audio d'un fichier.

    Avec `bits`, le son est rendu en entiers de cette largeur et résumé par une empreinte MD5 : c'est la forme exacte dans laquelle FLAC calcule la sienne. Sans, il est décodé pour rien (`-f null`) : seules les erreurs comptent.
    """
    commande = ["ffmpeg", "-v", "error", "-err_detect", STRICT, "-i", str(path), "-map", "0:a:0"]
    return commande + (["-c:a", f"pcm_s{bits}le", "-f", "md5", "-"] if bits else ["-f", "null", "-"])


def first_error(result):
    """Première ligne d'erreur de ffmpeg, débarrassée de l'adresse mémoire qui la précède : avec `-err_detect explode`, c'est elle qui dit pourquoi, les suivantes en sont les conséquences."""
    for line in (result.stderr or "").splitlines():
        line = ADDRESS_RE.sub("", line.strip())
        if line:
            return line
    return ""


def check(path, digest=None):
    """Ce que le décodage complet reproche au fichier, ou "" s'il passe. `digest` est (bits, MD5) : l'empreinte que le son décodé doit avoir."""
    try:
        result = run_tool(command(path, digest[0] if digest else None), timeout=read_timeout(path))
    except subprocess.TimeoutExpired:
        return "lecture sans fin : le partage ne répond plus ?"
    error = first_error(result)
    if error:
        return f"ffmpeg : {error}"
    if result.returncode != 0:
        return f"ffmpeg a échoué (code {result.returncode})"
    if digest:
        found = (result.stdout or "").strip().replace("MD5=", "").lower()
        if found != digest[1]:
            return f"le son décodé n'a pas l'empreinte MD5 que STREAMINFO annonce ({found or 'aucune'} au lieu de {digest[1]})"
    return ""
