"""Les albums qu'un artiste a sortis et qu'on n'a pas, tels que le disque les dit.

Dans le dossier d'un artiste, une image nommée comme un album rangé - "1997 - OK Computer.jpg", ou .png, .webp... - dit qu'il existe et manque à la médiathèque : c'est sa pochette.

    Musique/
        Radiohead/
            1995 - The Bends/            <- un album possédé
            1997 - OK Computer.jpg       <- un album qui manque, avec sa pochette

La fiche de l'artiste montre ces albums à leur place, grisés, avec cette pochette. Un fichier vide "1997 - OK Computer.txt" dit la même chose, sans pochette (l'ancienne façon, toujours lue) ; avec une image de même nom, c'est elle qui sert. Rien n'est cherché en ligne ni écrit sur le disque : on lit des noms de fichiers.

Un album qui figure à la fois en dossier et en image (acquis depuis, l'image oubliée) n'est pas déclaré manquant.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

from libraries.common.text import fold

from . import album as albums
from . import coverfile


@dataclass(frozen=True)
class Wanted:
    """Un album qui manque : l'année et le titre que dit le nom du fichier, et son image s'il en a une (elle ne compte pas pour l'égalité : l'image et le .txt du même album n'en font qu'un)."""
    year: str
    title: str
    cover: Path | None = field(default=None, compare=False)
    stamp: str = field(default="", compare=False)       # taille et date de l'image

    @property
    def order(self):
        """Où il se range parmi les albums possédés : par année, puis par titre (voir library.order)."""
        return (self.year, fold(self.title))

    @property
    def key(self):
        """Identifiant de sa pochette sur la fiche : change avec l'image, pour que la page précédente ne serve pas une pochette périmée."""
        digest = hashlib.sha1("|".join(self.order).encode("utf-8")).hexdigest()[:8]
        return f"{digest}-wanted-{self.stamp}"


def parse(name):
    """Wanted d'un nom de fichier "1997 - OK Computer.jpg" (ou .txt), ou None si ce n'en est pas un (artist.txt, cover.jpg, notes.txt...). `cover` reste vide : voir _in_folder."""
    path = Path(name)
    if path.suffix.lower() not in (".txt", *coverfile.EXTS):
        return None
    found = albums.YEAR_PREFIX_RE.match(path.stem)
    title = found.group(2).strip() if found else ""
    return Wanted(found.group(1), title) if title else None


def _in_folder(folder):
    try:
        files = [p for p in Path(folder).iterdir() if p.is_file()]
    except OSError:
        return []
    found = {}          # Wanted -> son image, ou None
    for path in sorted(files, key=lambda p: p.name):
        wanted = parse(path.name)
        if wanted is None:
            continue
        cover = path if path.suffix.lower() in coverfile.EXTS else None
        best = found.get(wanted)
        # Un .jpg l'emporte sur un .png, comme pour cover.
        if cover is not None and (best is None or coverfile.EXTS.index(cover.suffix.lower()) < coverfile.EXTS.index(best.suffix.lower())):
            best = cover
        found[wanted] = best
    return [replace(w, cover=c, stamp=coverfile.stamp(c)) if c else w for w, c in found.items()]


def owned(release, wanted):
    """Vrai si `release` est l'album que `wanted` dit manquer : même titre, et même année quand les deux la donnent. Les signes comptent pour rien : un nom de fichier ne peut pas porter "?" ou ":"."""
    names = {albums.normalize(release.title), albums.normalize(release.hints.title)} - {""}
    if albums.normalize(wanted.title) not in names:
        return False
    years = {y for y in (release.year, release.hints.year) if y}
    return not years or wanted.year in years


def find(root, releases):
    """{id d'artiste: [Wanted, ...]} d'après les images (et .txt) des dossiers qui rangent ses albums, de son dossier à celui de la médiathèque (exclu : ce n'est pas un artiste).

    Un dossier qui range des albums de plusieurs artistes (un compte-rendu de collaborations, un genre) donne ses fichiers à celui qui y a le plus d'albums.
    """
    root = Path(root)
    below = {}
    for release in releases:
        for parent in release.folder.parents:
            if parent == root or root not in parent.parents:
                break
            below.setdefault(parent, []).append(release)
    by_artist = {}
    for release in releases:
        by_artist.setdefault(release.artist_id, []).append(release)
    found = {}
    for folder, inside in below.items():
        names = _in_folder(folder)
        if not names:
            continue
        artist = Counter(r.artist_id for r in inside).most_common(1)[0][0]
        found.setdefault(artist, set()).update(w for w in names if not any(owned(r, w) for r in by_artist[artist]))
    return {artist: sorted(wanted, key=lambda w: w.order) for artist, wanted in found.items() if wanted}
