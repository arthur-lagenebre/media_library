"""Ce que tous les formats audio partagent : l'erreur, l'image embarquée, la pochette de face.

flac.py et mp3.py écrivent chacun à leur manière, mais présentent la même chose aux scripts : des tags sous des noms de clé Vorbis ("TITLE", "MUSICBRAINZ_ALBUMID"...), des images, et une durée.
"""

from dataclasses import dataclass

FRONT_COVER = 3               # type d'image "couverture (recto)", le même dans la spécification FLAC et dans celle d'ID3


class AudioError(Exception):
    """Fichier illisible ou écriture impossible : l'appelant passe au suivant."""


@dataclass
class Picture:
    """Une image embarquée (bloc PICTURE d'un .flac, trame APIC d'un .mp3)."""
    kind: int
    mime: str
    data: bytes
    description: str = ""
    width: int = 0
    height: int = 0
    depth: int = 0
    colors: int = 0


def image_dimensions(data):
    """(largeur, hauteur, bits par pixel) d'un JPEG ou d'un PNG, zéros si on ne sait pas.

    La spécification FLAC demande ces valeurs ; certains lecteurs s'en servent pour choisir l'image à afficher.
    """
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 26:
        channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(data[25], 1)
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big"), data[24] * channels
    if data[:2] == b"\xff\xd8":
        position = 2
        while position + 9 < len(data):
            if data[position] != 0xFF:
                break
            marker = data[position + 1]
            if marker == 0xFF:                     # octet de bourrage entre deux marqueurs
                position += 1
                continue
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):   # SOF : là où la taille est écrite
                height = int.from_bytes(data[position + 5:position + 7], "big")
                width = int.from_bytes(data[position + 7:position + 9], "big")
                return width, height, data[position + 4] * data[position + 9]
            position += 2 + int.from_bytes(data[position + 2:position + 4], "big")
    return 0, 0, 0


def front_cover(data, mime="image/jpeg"):
    """Picture de couverture pour ces octets, dimensions comprises."""
    width, height, depth = image_dimensions(data)
    return Picture(FRONT_COVER, mime, data, "", width, height, depth, 0)
