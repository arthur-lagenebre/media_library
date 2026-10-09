"""Un seul point d'entrée pour lire et écrire un fichier audio, quel que soit son format.

Les scripts ne savent pas si une piste est un .flac ou un .mp3 : ils lisent, comparent des tags sous leurs noms Vorbis, et écrivent. Ce module choisit le bon lecteur d'après l'extension, et le bon écrivain d'après ce qui a été lu.
"""

from pathlib import Path

from . import flac, mp3
from .tags import FRONT_COVER, AudioError, front_cover  # noqa: F401  (réexportés : audio.AudioError, audio.FRONT_COVER, audio.front_cover)


def read(path):
    """Metadata d'une piste, du module qui sait lire son format."""
    return (mp3 if Path(path).suffix.lower() == ".mp3" else flac).read(path)


def write(path, meta, comments, pictures):
    """Remplace les tags et les images d'une piste. Retourne "sur place" ou "recopie"."""
    return (mp3 if isinstance(meta, mp3.Metadata) else flac).write(path, meta, comments, pictures)
