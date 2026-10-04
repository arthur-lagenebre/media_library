"""Lire un .cbz : sa fiche ComicInfo.xml et sa couverture.

Un .cbz pèse souvent plusieurs centaines de Mo, sur un partage réseau : on n'en lit que ce qu'il faut - l'index du zip, puis le seul fichier voulu -, jamais l'archive entière. Rien n'est écrit.
"""

from . import comicinfo
from .archive import image_names, open_zip, read_member


def read_info(path):
    """Fiche ComicInfo.xml d'un .cbz ({} s'il n'en a pas), ou BookError si l'archive est illisible."""
    with open_zip(path) as archive:
        for item in archive.infolist():
            if item.filename.lower() == comicinfo.NAME.lower():
                return comicinfo.parse(read_member(archive, item, comicinfo.NAME))
    return {}


def cover(path, front_cover=None):
    """Octets de la couverture : la page que la fiche désigne (rang `front_cover`), sinon la première. None si l'archive n'a aucune image."""
    with open_zip(path) as archive:
        names = image_names(archive)
        if not names:
            return None
        name = names[front_cover] if front_cover is not None and 0 <= front_cover < len(names) else names[0]
        return read_member(archive, name, "couverture")
