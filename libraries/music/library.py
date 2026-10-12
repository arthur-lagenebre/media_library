"""La médiathèque musicale telle que ses fichiers la décrivent : des albums, leurs pistes, leurs tags.

Les albums étiquetés par Metadata.py portent tout ce qu'une fiche montre - titre, artiste, année, genres, label, numéros de piste et leurs totaux, identifiant MusicBrainz, pochette. Il n'y a donc rien à chercher en ligne : comme pour les livres, on LIT les fichiers, et rien n'y est écrit.

    Musique/
        Daft Punk/                    <- un dossier d'artiste : il range, il ne compte pas
            2001 - Discovery/         <- un album : un dossier qui contient de l'audio, lui ou ses CD1, CD2...
                01 - One More Time.flac

Le catalogue garde ce qu'on a lu dans chaque fichier : sur un partage réseau, chaque en-tête paie son aller-retour, et ne sert qu'une fois tant que le fichier ne bouge pas (même taille, même date).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from libraries.common import layout

from . import album as albums
from . import audio
from .tags import FRONT_COVER, AudioError

SKIPPED_PREFIXES = ("__", "#", "@")      # __Data__ (nos pages), #recycle, @eaDir (vignettes DSM) : ce n'est pas de la musique rangée. Les dossiers cachés sont déjà écartés par find_albums.
UNKNOWN_ARTIST = "Artiste inconnu"
MAX_TRACKS = 500                         # un total de pistes au-delà est une faute de frappe, pas un album à compléter
MAX_GENRES = 6

# Ce que MusicBrainz écrit quand une édition n'a ni label ni numéro de catalogue : un marqueur, pas une valeur à montrer.
PLACEHOLDERS = {"[none]", "[no label]", "[unknown]"}

YEAR_RE = re.compile(r"(?:19|20)\d{2}")
TOTAL_RE = re.compile(r"/\s*(\d{1,3})\s*$")          # "3/12" : le total, quand il est collé au numéro
UUID_RE = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
CATALOG_VERSION = 2                                  # 2 : l'identifiant MusicBrainz de l'artiste de l'album


def _int(text):
    found = re.match(r"\s*0*(\d{1,4})", text or "")
    return int(found.group(1)) if found else None


def _total(meta, *keys, joined=""):
    """Un total de pistes ou de disques : sa propre clé, sinon la partie après le "/" du numéro ("3/12")."""
    for key in keys:
        value = _int(meta.first(key))
        if value:
            return value
    found = TOTAL_RE.search(meta.first(joined)) if joined else None
    return int(found.group(1)) if found else None


def _artist_mbid(meta):
    """L'identifiant MusicBrainz de l'artiste de l'album, quand les tags en donnent un seul : "Kavinsky feat. Havoc" en porte deux, et aucun ne dit à lui seul qui est l'artiste."""
    found = {v.strip().lower() for v in meta.values("MUSICBRAINZ_ALBUMARTISTID") if v.strip()}
    only = found.pop() if len(found) == 1 else ""
    return only if UUID_RE.fullmatch(only) else ""


def track_info(path, meta, disc_folder=None):
    """Ce qu'une fiche retient d'une piste, lu dans ses tags : un dictionnaire JSON, gardé dans le catalogue.

    Disque, numéro et titre suivent la règle de l'étiquetage - tags, puis dossier de disque, puis nom du fichier : une piste jamais étiquetée a quand même sa place.
    """
    entry = albums.entry_for(path, meta, disc_folder)
    genres = [g.strip() for value in meta.values("GENRE") for g in value.split(";") if g.strip()]
    year = YEAR_RE.search(meta.first("DATE") or meta.first("YEAR") or meta.first("ORIGINALYEAR"))
    return {
        "title": entry.title, "disc": entry.disc, "number": entry.track,
        "artist": meta.first("ARTIST"),
        "albumartist": meta.first("ALBUMARTIST") or meta.first("ALBUM ARTIST"),
        "album": meta.first("ALBUM"),
        "artistid": _artist_mbid(meta),
        "year": year.group(0) if year else "",
        "genres": genres,
        "label": meta.first("LABEL"), "catalog": meta.first("CATALOGNUMBER"),
        "tracktotal": _total(meta, "TRACKTOTAL", "TOTALTRACKS", joined="TRACKNUMBER"),
        "disctotal": _total(meta, "DISCTOTAL", "TOTALDISCS", joined="DISCNUMBER"),
        "mbid": meta.first("MUSICBRAINZ_ALBUMID").strip().lower(),
        "duration": round(meta.duration, 2) if meta.duration else None,
        "cover": bool(meta.pictures),
    }


@dataclass
class Track:
    path: Path
    rel: str                  # chemin relatif à la médiathèque, séparé par "/" : l'identité de la piste
    size: int
    mtime: int
    kind: str                 # "flac" ou "mp3"
    disc_folder: int | None = None
    info: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def title(self):
        return self.info.get("title") or self.path.stem

    @property
    def number(self):
        return self.info.get("number")

    @property
    def disc(self):
        return self.info.get("disc") or 1

    @property
    def duration(self):
        return self.info.get("duration") or 0

    @property
    def key(self):
        """Identifiant d'une pochette : change dès que le fichier qui la porte change, pour que la page précédente ne serve pas une pochette périmée."""
        digest = hashlib.sha1(self.rel.encode("utf-8")).hexdigest()[:12]
        return f"{digest}-{self.size}-{self.mtime}"

    @property
    def order(self):
        return (self.number is None, self.number or 0, layout.fold(self.path.stem))


def _most_common(values):
    values = [v for v in values if v]
    return Counter(values).most_common(1)[0][0] if values else ""


@dataclass
class Release:
    """Un album de la médiathèque, tel que le disque le range."""
    folder: Path
    rel: str                  # dossier relatif à la médiathèque, "" à la racine
    tracks: list
    unsupported: list = field(default_factory=list)
    hints: albums.Hints = field(default_factory=albums.Hints)      # ce que dit le nom du dossier, à défaut de tags

    @property
    def id(self):
        """Identifiant stable : il ne change que si le dossier est déplacé ou renommé."""
        return hashlib.sha1(self.rel.encode("utf-8")).hexdigest()[:8]

    def _tagged(self, name):
        return _most_common(t.info.get(name) for t in self.tracks)

    def _shown(self, name):
        value = self._tagged(name)
        return "" if value.casefold() in PLACEHOLDERS else value

    @property
    def title(self):
        return self._tagged("album") or self.hints.title or self.folder.name

    @property
    def artist(self):
        return self._tagged("albumartist") or self._tagged("artist") or self.hints.artist or UNKNOWN_ARTIST

    @property
    def artist_id(self):
        """Identifiant de la page de l'artiste : ses albums, qui s'écrivent à la casse et aux accents près, partagent la même."""
        return artist_id(self.artist)

    @property
    def artist_mbid(self):
        return self._tagged("artistid")

    @property
    def year(self):
        return self._tagged("year")

    @property
    def label(self):
        return self._shown("label")

    @property
    def catalog(self):
        return self._shown("catalog")

    @property
    def mbid(self):
        """L'édition MusicBrainz, quand tous les fichiers la déclarent : à moitié étiqueté, l'album n'a pas encore de fiche à montrer."""
        ids = {t.info.get("mbid") for t in self.tracks}
        found = ids.pop() if len(ids) == 1 else ""
        return found or ""

    @property
    def genres(self):
        found = Counter(g for t in self.tracks for g in t.info.get("genres") or [])
        return [name for name, _ in found.most_common(MAX_GENRES)]

    @property
    def duration(self):
        return sum(t.duration for t in self.tracks)

    @property
    def formats(self):
        return sorted({t.kind.upper() for t in self.tracks})

    @property
    def cover_track(self):
        """La première piste qui porte une pochette, ou None."""
        return next((t for t in self.tracks if t.info.get("cover")), None)

    @property
    def key(self):
        track = self.cover_track
        return track.key if track else f"{self.id}-nocover"

    @property
    def discs(self):
        """[(numéro de disque, [pistes dans l'ordre])]."""
        grouped = {}
        for track in self.tracks:
            grouped.setdefault(track.disc, []).append(track)
        return [(n, sorted(tracks, key=lambda t: t.order)) for n, tracks in sorted(grouped.items())]

    @property
    def tagged(self):
        """Pistes étiquetées par Metadata.py (elles portent l'identifiant de leur édition)."""
        return sum(1 for t in self.tracks if t.info.get("mbid"))

    def missing(self):
        """[(disque, [numéros manquants], total attendu)] d'après le total de pistes que les tags annoncent.

        On ne dit rien d'un disque dont une piste n'a pas de numéro (c'est peut-être elle qui manque) ni d'un total qui n'a pas de sens.
        """
        result = []
        for number, tracks in self.discs:
            totals = [t.info["tracktotal"] for t in tracks if t.info.get("tracktotal")]
            numbers = [t.number for t in tracks]
            if not totals or None in numbers:
                continue
            total = max(totals)
            if not 1 < total <= MAX_TRACKS:
                continue
            lacking = [n for n in range(1, total + 1) if n not in set(numbers)]
            if lacking:
                result.append((number, lacking, total))
        return result

    def missing_discs(self):
        """Numéros des disques que les tags annoncent (DISCTOTAL) et que le dossier ne range pas."""
        totals = [t.info["disctotal"] for t in self.tracks if t.info.get("disctotal")]
        if not totals or not 1 < max(totals) <= 20:
            return []
        seen = {n for n, _ in self.discs}
        return [n for n in range(1, max(totals) + 1) if n not in seen]

    def progress(self):
        """(possédées, attendues) quand les tags disent qu'il manque des pistes ; sinon None."""
        gaps = self.missing()
        if not gaps:
            return None
        return len(self.tracks), len(self.tracks) + sum(len(lacking) for _, lacking, _ in gaps)


def artist_id(name):
    return hashlib.sha1(layout.fold(name).encode("utf-8")).hexdigest()[:8]


@dataclass
class Artist:
    """Un artiste de la médiathèque : tous les albums qui s'écrivent à son nom."""
    releases: list

    @property
    def name(self):
        return _most_common(r.artist for r in self.releases)

    @property
    def id(self):
        return artist_id(self.releases[0].artist)

    @property
    def mbid(self):
        return _most_common(r.artist_mbid for r in self.releases)

    @property
    def genres(self):
        found = Counter(g for r in self.releases for g in r.genres)
        return [name for name, _ in found.most_common(MAX_GENRES)]

    @property
    def tracks(self):
        return sum(len(r.tracks) for r in self.releases)

    @property
    def duration(self):
        return sum(r.duration for r in self.releases)

    @property
    def years(self):
        """(première, dernière) année de ses albums ; ("", "") si aucun n'en a."""
        found = sorted(r.year for r in self.releases if r.year)
        return (found[0], found[-1]) if found else ("", "")


def _skipped(rel):
    return any(part.startswith(SKIPPED_PREFIXES) for part in rel.split("/"))


def scan(root):
    """Les albums sous `root`, dans l'ordre du disque. Ne lit le contenu d'aucun fichier : seuls noms, tailles et dates sont vus (voir `read_info`)."""
    root = Path(root)
    found = []
    for item in albums.find_albums(root):
        rel = "" if item.folder == root else item.folder.relative_to(root).as_posix()
        if _skipped(rel):
            continue
        tracks = []
        for path in item.files:
            try:
                stat = path.stat()
            except OSError:
                continue
            tracks.append(Track(path, path.relative_to(root).as_posix(), stat.st_size, int(stat.st_mtime), path.suffix.lower().lstrip("."), item.disc_folder(path)))
        if tracks:
            hints = albums.folder_hints(item.folder)
            if item.folder.parent == root or item.folder == root:      # le nom du dossier de la médiathèque n'est pas un artiste
                hints.artist = ""
            found.append(Release(item.folder, rel, tracks, [p.name for p in item.unsupported], hints))
    return found


def read_info(track):
    """Lit les tags d'une piste et les range dans `track.info` ; un fichier illisible garde son erreur dans `track.error`."""
    track.info, track.error = {}, None
    try:
        track.info = track_info(track.path, audio.read(track.path), track.disc_folder)
    except AudioError as e:
        track.error = str(e)


def read_cover(track):
    """Octets de la pochette de face d'une piste (à défaut, de sa première image), ou None. AudioError si le fichier est illisible."""
    pictures = audio.read(track.path).pictures
    front = next((p for p in pictures if p.kind == FRONT_COVER), pictures[0] if pictures else None)
    return front.data if front else None


# ----------------------------------------------------------------------------
# Rangement
# ----------------------------------------------------------------------------
def order(release):
    return (release.year or "9999", layout.fold(release.title))


def artists(releases):
    """[Artist], rangés sans accents ni casse ; les albums de chacun par année, puis par titre."""
    by_artist = {}
    for release in releases:
        by_artist.setdefault(layout.fold(release.artist), []).append(release)
    return [Artist(sorted(by_artist[key], key=order)) for key in sorted(by_artist)]


def sections(releases):
    """[(nom de la section, [Release])] : une section par artiste, même s'il n'a qu'un album.

    Les artistes se rangent sans accents ni casse ; leurs albums par année, puis par titre.
    """
    return [(artist.name, artist.releases) for artist in artists(releases)]


# ----------------------------------------------------------------------------
# Catalogue
# ----------------------------------------------------------------------------
def load_catalog(path):
    """{chemin relatif: {'size', 'mtime', 'info'}} du catalogue écrit au passage précédent, ou {}."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("version") != CATALOG_VERSION:
        return {}
    return data.get("tracks") or {}


def apply_catalog(tracks, catalog):
    """Reprend du catalogue les tags des pistes qui n'ont pas bougé. Retourne celles qu'il reste à lire."""
    todo = []
    for track in tracks:
        kept = catalog.get(track.rel)
        if kept and kept.get("size") == track.size and kept.get("mtime") == track.mtime and isinstance(kept.get("info"), dict) and kept["info"]:
            track.info = kept["info"]
        else:
            todo.append(track)
    return todo


def dump_catalog(tracks):
    """Le catalogue en JSON, tel qu'on l'écrit : une piste illisible n'y figure pas, elle sera relue au prochain passage."""
    entries = {t.rel: {"size": t.size, "mtime": t.mtime, "info": t.info} for t in tracks if not t.error}
    return json.dumps({"version": CATALOG_VERSION, "tracks": entries}, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
