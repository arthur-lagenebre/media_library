"""Ouvrir une archive zip (.cbz, .epub) et en trier le contenu.

Un .cbz comme un .epub est un zip : ce qui est commun à leur lecture - l'ouverture qui rend une erreur claire, l'ordre des pages - est ici.
"""

import re
import zipfile
import zlib

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


class BookError(Exception):
    """Livre illisible : l'appelant le signale et passe au suivant."""


# Tout ce qu'un zip abîmé peut lever : l'index tronqué (BadZipFile, EOFError), un nom d'entrée mal encodé (UnicodeDecodeError - vu sur un .cbz réel), une compression inconnue (NotImplementedError), un mot de passe (RuntimeError), un flux corrompu (zlib.error), un partage qui lâche (OSError), une entrée absente (KeyError).
ZIP_ERRORS = (KeyError, zipfile.BadZipFile, zipfile.LargeZipFile, UnicodeDecodeError, NotImplementedError, ValueError,
              RuntimeError, EOFError, zlib.error, OSError)


def open_zip(path):
    """ZipFile du fichier, ou BookError. Un .cbz tronqué par un transfert interrompu est le cas courant."""
    try:
        return zipfile.ZipFile(path)
    except ZIP_ERRORS as e:
        raise BookError(f"archive illisible : {e}") from e


def read_member(archive, member, what):
    """Octets d'une entrée de l'archive (son nom ou son ZipInfo), ou BookError qui dit ce qu'on cherchait à lire."""
    try:
        return archive.read(member)
    except ZIP_ERRORS as e:
        raise BookError(f"{what} illisible : {e}") from e


def natural_key(text):
    """Clé de tri "naturel" : 'Tome 2' avant 'Tome 10', sans tenir compte de la casse."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", (text or "").casefold())]


def image_names(archive):
    """Noms des pages d'une archive, dans l'ordre de lecture.

    Les dossiers, les fichiers cachés et les résidus de macOS (__MACOSX) ne sont pas des pages.
    """
    names = []
    for item in archive.infolist():
        name = item.filename
        base = name.rsplit("/", 1)[-1]
        if item.is_dir() or name.startswith("__MACOSX/") or base.startswith("."):
            continue
        if name.lower().endswith(IMAGE_EXTENSIONS):
            names.append(name)
    return sorted(names, key=natural_key)
