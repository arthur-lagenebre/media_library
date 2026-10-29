"""La pochette posée dans le dossier de l'album : "cover.jpg", "folder.png"...

C'est la pochette que l'on choisit soi-même, et elle l'emporte sur toute autre : celle d'un fichier audio (souvent un scan recto-verso ou mal cadré), comme celle de Cover Art Archive. Elle s'écrit à côté des pistes, dans le dossier de l'album - jamais dans celui d'un disque (CD1, CD2...), qui partage celle de l'album.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from libraries.common import filenames
from .tags import FRONT_COVER, AudioError, Picture, front_cover, image_dimensions

CANDIDATES_DIR = "_covers"                                     # où Cover.py --candidates dépose les pochettes entre lesquelles choisir
NAMES = ("cover", "folder", "front", "album", "albumart")      # dans cet ordre : "cover" l'emporte sur "folder"
EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")      # dans cet ordre : un .jpg l'emporte sur un .png
# Un .flac ou un .mp3 ne porte que du JPEG ou du PNG, que tous les lecteurs savent afficher : les autres formats servent à la fiche, pas à l'embarquement.
EMBEDDABLE = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
MAX_SIZE = 20 * 1024 * 1024                                     # au-delà, ce n'est pas une pochette


def find(folder):
    """Le fichier cover du dossier de l'album, ou None. Le nom se lit sans tenir compte de la casse ("Cover.JPG")."""
    try:
        found = {p.name.casefold(): p for p in Path(folder).iterdir() if p.is_file()}
    except OSError:
        return None
    for name in NAMES:
        for ext in EXTS:
            if (path := found.get(name + ext)) is not None:
                return path
    return None


def stamp(path):
    """Ce qui change quand le fichier change (taille, date) : l'identifiant de la pochette de la fiche en dépend, pour qu'une image remplacée ne laisse pas la page précédente en servir une périmée."""
    try:
        stat = Path(path).stat()
    except OSError:
        return ""
    return f"{stat.st_size}-{int(stat.st_mtime)}"


def read(path):
    """Les octets du fichier cover, ou None s'il est illisible, vide ou démesuré."""
    try:
        if not 0 < Path(path).stat().st_size <= MAX_SIZE:
            return None
        return Path(path).read_bytes()
    except OSError:
        return None


def picture(path):
    """La pochette de face à embarquer dans une piste. AudioError quand le fichier ne peut pas l'être : illisible, ou d'un format que ni le FLAC ni l'ID3 ne portent par convention."""
    mime = EMBEDDABLE.get(Path(path).suffix.lower())
    if mime is None:
        raise AudioError(f"{Path(path).name} : seuls le JPEG et le PNG s'embarquent dans une piste")
    data = read(path)
    if not data:
        raise AudioError(f"{Path(path).name} : illisible, vide ou trop lourd")
    return front_cover(data, mime)


def extension(data):
    """".jpg" ou ".png" d'après les premiers octets de l'image, "" pour tout autre format : c'est le contenu qui dit ce qu'est l'image, pas le type que le tag déclare."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    return ".jpg" if data[:2] == b"\xff\xd8" else ""


def embedded(metas):
    """(image, de face ?) : la pochette embarquée dans la première piste qui en porte une - celle de face, à défaut sa première image, comme la fiche. (None, False) si aucune piste n'en porte."""
    for meta in metas:
        front = next((p for p in meta.pictures if p.kind == FRONT_COVER), None)
        if front is not None:
            return front, True
        if meta.pictures:
            return meta.pictures[0], False
    return None, False


def write(folder, picture):
    """Écrit l'image en "cover.jpg" (ou .png) dans le dossier de l'album, sans jamais écraser un fichier. Retourne le chemin écrit. OSError si l'écriture échoue, FileExistsError si le fichier existe déjà."""
    path = Path(folder) / f"cover{extension(picture.data)}"
    with open(path, "xb") as f:
        f.write(picture.data)
    return path


def candidate_name(rank, release, data):
    """Nom d'une pochette candidate : "01_FR-2013-CD_1200x1200.jpg" - l'ordre, puis ce qui distingue l'édition et l'image, pour choisir sans rien ouvrir de plus."""
    media = release.get("media") or []
    label = [release.get("country"), (release.get("date") or "")[:4], next((m["format"] for m in media if m.get("format")), "")]
    width, height, _ = image_dimensions(data)
    parts = [f"{rank:02d}", filenames.safe_name("-".join(x for x in label if x)), f"{width}x{height}" if width else ""]
    return "_".join(p for p in parts if p) + extension(data)


def write_candidate(folder, name, data):
    """Dépose une pochette candidate dans _covers/ (créé au besoin), sans jamais écraser un fichier. Retourne le chemin écrit. OSError si l'écriture échoue, FileExistsError si le fichier est déjà là."""
    place = Path(folder) / CANDIDATES_DIR
    place.mkdir(exist_ok=True)
    with open(place / name, "xb") as f:
        f.write(data)
    return place / name


def candidates_present(folder):
    """Vrai quand le dossier de l'album a ses pochettes candidates."""
    path = Path(folder) / CANDIDATES_DIR
    return path.is_dir() and not path.is_symlink()


def remove_candidates(folder):
    """Supprime _covers/ et ce qu'il contient. OSError si la suppression échoue."""
    if candidates_present(folder):
        shutil.rmtree(Path(folder) / CANDIDATES_DIR)


def same_front(meta, wanted: Picture):
    """Vrai quand la seule pochette de face de la piste est déjà exactement celle-ci."""
    fronts = [p for p in meta.pictures if p.kind == wanted.kind]
    return len(fronts) == 1 and fronts[0].data == wanted.data
