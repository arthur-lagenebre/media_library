"""La pochette posée dans le dossier de l'album : "cover.jpg", "folder.png"...

C'est la pochette que l'on choisit soi-même, et elle l'emporte sur toute autre : celle d'un fichier audio (souvent un scan recto-verso ou mal cadré), comme celle de Cover Art Archive. Elle s'écrit à côté des pistes, dans le dossier de l'album, et celle de l'album sert à tous ses disques (CD1, CD2...). Seul Cover.py (et Metadata.py) connaît aussi le fichier posé dans un dossier de disque, à défaut de celui de l'album : la fiche de la médiathèque, elle, ne lit que celui de l'album.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from libraries.common import filenames
from libraries.common.tools import partial_path, read_timeout, run_tool
from .tags import FRONT_COVER, AudioError, Picture, front_cover, image_dimensions

CANDIDATES_DIR = "_covers"                                     # où Cover.py --candidates dépose les pochettes entre lesquelles choisir
MAX_DIMENSION = 1500                                           # la pochette embarquée tient dans 1500x1500 : au-delà, des pistes lourdes pour rien (un scan de 3000x3000 pèse plusieurs Mo par piste)
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


def steps(picture):
    """Ce qu'il faut faire à la pochette avant de l'embarquer : "réduire à 1500x1500 au plus" si un côté dépasse, "convertir en JPEG" si ce n'est pas du JPEG. Liste vide quand elle est déjà conforme - elle n'est alors jamais recompressée, d'où un second passage qui ne change rien. C'est le contenu qui dit le format, pas l'extension du fichier."""
    todo = []
    if max(picture.width, picture.height) > MAX_DIMENSION:
        todo.append(f"réduire à {MAX_DIMENSION}x{MAX_DIMENSION} au plus")
    if extension(picture.data) != ".jpg":
        todo.append("convertir en JPEG")
    return todo


def ffmpeg_missing():
    """Vrai quand ffmpeg, qui réduit et convertit l'image, n'est pas dans le PATH."""
    return shutil.which("ffmpeg") is None


def convert_command(source, target):
    """La commande ffmpeg qui écrit `source` en JPEG dans `target`, réduite pour tenir dans 1500x1500 (les proportions sont gardées, une image plus petite n'est jamais agrandie). La transparence d'un PNG est perdue : le JPEG n'en a pas."""
    fit = f"scale='min({MAX_DIMENSION},iw)':'min({MAX_DIMENSION},ih)':force_original_aspect_ratio=decrease"
    return ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source), "-frames:v", "1", "-vf", fit,
            "-c:v", "mjpeg", "-q:v", "2", "-f", "image2", "-update", "1", str(target)]   # -f : le nom provisoire (.part) ne dit pas le format


def convert(path):
    """Remplace le fichier cover par sa version JPEG tenant dans 1500x1500 et retourne le chemin du JPEG : le même fichier s'il l'était déjà, "cover.jpg" à côté d'un "cover.png" (qui est alors supprimé). AudioError si ça échoue, auquel cas rien n'a bougé.

    L'image s'écrit d'abord sous un nom provisoire, contrôlée (un JPEG lisible dans la limite de taille) avant de prendre la place de l'original : un échec ou un Ctrl-C ne laissent pas une pochette tronquée. Un autre fichier déjà nommé comme le résultat n'est jamais écrasé.
    """
    path = Path(path)
    final = path.with_suffix(".jpg")
    partial = partial_path(final)
    try:
        if final.exists() and not os.path.samefile(path, final):
            raise AudioError(f"{final.name} existe déjà à côté de {path.name} : à supprimer ou renommer à la main")
        try:
            result = run_tool(convert_command(path, partial), timeout=read_timeout(path))
        except FileNotFoundError:
            raise AudioError("ffmpeg est introuvable dans le PATH (winget install Gyan.FFmpeg)")
        except subprocess.TimeoutExpired:
            raise AudioError(f"{path.name} : lecture sans fin, le partage ne répond plus ?")
        data = read(partial) if result.returncode == 0 and partial.exists() else None
        if not data or extension(data) != ".jpg" or not 0 < max(image_dimensions(data)[:2]) <= MAX_DIMENSION:
            error = next((line.strip() for line in (result.stderr or "").splitlines() if line.strip()), "")
            raise AudioError(f"{path.name} : ffmpeg n'a pas produit de JPEG exploitable" + (f" ({error})" if error else ""))
        try:
            os.replace(partial, final)
        except OSError as e:
            raise AudioError(f"{final.name} n'a pas pu être écrit : {e.strerror or e}")
    finally:
        partial.unlink(missing_ok=True)
    if not os.path.samefile(path, final):      # "cover.png" -> "cover.jpg" : l'original n'a plus lieu d'être (sur Windows, "Cover.JPG" et "Cover.jpg" sont le même fichier : jamais supprimé)
        try:
            path.unlink()
        except OSError as e:
            raise AudioError(f"{path.name} n'a pas pu être supprimé après conversion : {e.strerror or e}")
    return final


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


def by_date(editions):
    """Les éditions d'un album, les plus anciennes d'abord (celles sans date à la fin)."""
    return sorted(editions, key=lambda r: r.get("date") or "9999")


def candidate_sources(editions, mb):
    """[(édition, image)] : les pochettes de face de ces éditions, dans l'ordre donné. Ne demande à Cover Art Archive que les éditions qui déclarent une pochette de face. Les erreurs de `mb` (MusicBrainzError) se propagent."""
    sources = []
    for edition in editions:
        if not (edition.get("cover-art-archive") or {}).get("front"):
            continue
        sources += [(edition, image) for image in mb.cover_images(edition["id"])]
    return sources


def write_candidate(folder, name, data, album=""):
    """Dépose une pochette candidate dans _covers/ (créé au besoin), ou dans _covers/<album>/ quand `album` est donné, sans jamais écraser un fichier. Retourne le chemin écrit. OSError si l'écriture échoue, FileExistsError si le fichier est déjà là."""
    place = Path(folder) / CANDIDATES_DIR / album
    place.mkdir(parents=True, exist_ok=True)
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
