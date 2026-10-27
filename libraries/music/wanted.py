"""Les albums qu'un artiste a sortis et qu'on n'a pas, tels que le disque les dit.

Dans le dossier d'un artiste, un fichier vide nommé comme un album rangé - "1997 - OK Computer.txt" - dit qu'il existe et manque à la médiathèque :

    Musique/
        Radiohead/
            1995 - The Bends/            <- un album possédé
            1997 - OK Computer.txt       <- un album qui manque : seul son nom compte, le contenu n'est pas lu

La fiche de l'artiste montre ces albums à leur place, grisés. Rien n'est cherché en ligne ni écrit sur le disque : on lit des noms de fichiers.

Un album qui figure à la fois en dossier et en .txt (acquis depuis, le .txt oublié) n'est pas déclaré manquant.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from libraries.common import layout

from . import album as albums


@dataclass(frozen=True)
class Wanted:
    """Un album qui manque : l'année et le titre que dit le nom du fichier."""
    year: str
    title: str

    @property
    def order(self):
        """Où il se range parmi les albums possédés : par année, puis par titre (voir library.order)."""
        return (self.year, layout.fold(self.title))


def parse(name):
    """Wanted d'un nom de fichier "1997 - OK Computer.txt", ou None si ce n'en est pas un (artist.txt, notes.txt...)."""
    path = Path(name)
    if path.suffix.lower() != ".txt":
        return None
    found = albums.YEAR_PREFIX_RE.match(path.stem)
    title = found.group(2).strip() if found else ""
    return Wanted(found.group(1), title) if title else None


def _in_folder(folder):
    try:
        return [w for w in (parse(p.name) for p in Path(folder).iterdir() if p.is_file()) if w]
    except OSError:
        return []


def owned(release, wanted):
    """Vrai si `release` est l'album que `wanted` dit manquer : même titre, et même année quand les deux la donnent. Les signes comptent pour rien : un nom de fichier ne peut pas porter "?" ou ":"."""
    names = {albums.normalize(release.title), albums.normalize(release.hints.title)} - {""}
    if albums.normalize(wanted.title) not in names:
        return False
    years = {y for y in (release.year, release.hints.year) if y}
    return not years or wanted.year in years


def find(root, releases):
    """{id d'artiste: [Wanted, ...]} d'après les .txt des dossiers qui rangent ses albums, de son dossier à celui de la médiathèque (exclu : ce n'est pas un artiste).

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
