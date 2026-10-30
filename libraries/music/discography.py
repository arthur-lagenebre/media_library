"""La discographie d'un artiste, et ce qu'il en manque dans son dossier.

MusicBrainz sait tout ce qu'un artiste a sorti ; le dossier de l'artiste sait ce qu'on en possède. L'écart entre les deux s'écrit comme wanted.py le lit : un fichier vide, sans extension, "1997 - OK Computer" posé à côté des albums rangés.

    Musique/
        Radiohead/
            1995 - The Bends/            <- un album possédé
            1997 - OK Computer           <- un album qui manque (un fichier vide, sans extension)

Chaque fichier est une image quand Cover Art Archive a la pochette de l'album - "1997 - OK Computer.jpg", que wanted.py montre sur la fiche -, et reste un fichier vide sinon ; un fichier vide posé plus tôt est remplacé par la pochette dès qu'elle existe.

Seuls les albums sont complétés par défaut ; les EP, singles, lives... le sont sur demande, dans un sous-dossier à leur nom ("EP/", "Singles/") - celui où l'on range déjà les siens s'il existe. Rien de ce qui est déjà là n'est touché : un album compte pour possédé qu'il soit un dossier, un .txt ou une image de ce titre.

Tout est pur, sauf inventory et tagged_artist_id qui lisent le disque.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from libraries.common import filenames
from libraries.common.text import fold

from . import album as albums
from . import audio
from . import coverfile
from . import wanted

# Clé interne -> nom du sous-dossier où se rangent ces sorties.
CATEGORIES = {
    "album": "Albums",
    "ep": "EP",
    "single": "Singles",
    "live": "Live",
    "compilation": "Compilations",
    "soundtrack": "Bandes originales",
    "remix": "Remixes",
    "demo": "Démos",
    "other": "Autres",
}
DEFAULT_CATEGORIES = ("album",)

# Types secondaires MusicBrainz -> catégorie, testés dans cet ordre : un album live reste un live.
SECONDARY_MAP = (
    ("Live", "live"),
    ("Compilation", "compilation"),
    ("Soundtrack", "soundtrack"),
    ("Remix", "remix"),
    ("DJ-mix", "remix"),
    ("Mixtape/Street", "compilation"),
    ("Demo", "demo"),
    ("Spokenword", "other"),
    ("Interview", "other"),
    ("Audiobook", "other"),
    ("Audio drama", "other"),
    ("Field recording", "other"),
)
PRIMARY_MAP = {"Album": "album", "EP": "ep", "Single": "single"}

MIN_SCORE = 80           # en dessous, MusicBrainz parle d'un autre artiste
MAX_CHOICES = 8          # artistes proposés quand plusieurs portent le nom
SAMPLE_ALBUMS = 5        # albums dont on lit un fichier pour trouver l'identifiant de l'artiste


def categorize(group):
    """Catégorie d'un release group : son type secondaire (live, compilation...) d'abord, sinon son type."""
    secondary = group.get("secondary-types") or []
    for mb_type, category in SECONDARY_MAP:
        if mb_type in secondary:
            return category
    return PRIMARY_MAP.get(group.get("primary-type") or "", "other")


def release_year(group):
    """Année de première sortie ("1997"), ou "" quand MusicBrainz n'en donne pas."""
    found = re.match(r"(?:19|20)\d{2}", group.get("first-release-date") or "")
    return found.group(0) if found else ""


class Release(NamedTuple):
    """Une sortie à compléter : son année, son titre, et l'identifiant MusicBrainz de son release group (de quoi retrouver sa pochette)."""
    year: str
    title: str
    group: str = ""


def stem(year, title):
    """"1997 - OK Computer" : le nom d'un album manquant sans extension ; "/" devient "-" comme dans Rename_Tracks, les autres signes interdits sous Windows disparaissent. "" quand rien ne reste du titre."""
    clean = filenames.safe_name((title or "").replace("/", "-"))
    return f"{year} - {clean}" if clean else ""


def file_name(year, title):
    """Le nom du fichier vide d'un album manquant : son stem, sans extension.

    Un titre dont la fin ressemble à une extension ("Vol.2", "Mr.Scruff") en prend une vraie, ".txt" : sans elle, wanted.py y lirait l'extension d'un autre fichier."""
    name = stem(year, title)
    return name + ".txt" if name and wanted.EXTENSION_RE.fullmatch(Path(name).suffix.lower()) else name


def title_key(text):
    """Un titre réduit à ses lettres et chiffres, sans accents ni casse : "OK Computer", "ok-computer" et "Ok Computér" ne font qu'un."""
    return re.sub(r"[\W_]+", "", fold(text))


def plan(groups, cats):
    """{catégorie: [Release, ...]} des sorties retenues, par année puis par titre. Les sorties sans année ne peuvent pas se nommer "AAAA - Titre" : elles sont écartées, et comptées à part dans le second retour."""
    planned, undated, seen = {}, 0, set()
    for group in sorted(groups, key=lambda g: (release_year(g), fold(g.get("title") or ""))):
        category = categorize(group)
        if category not in cats:
            continue
        year, title = release_year(group), (group.get("title") or "").strip()
        if not year:
            undated += 1
            continue
        if not title_key(title) or (category, year, title_key(title)) in seen:
            continue
        seen.add((category, year, title_key(title)))
        planned.setdefault(category, []).append(Release(year, title, group.get("id") or ""))
    return planned, undated


# --------------------------------------------------------------------------
# L'artiste
# --------------------------------------------------------------------------
def describe(artist):
    """"Radiohead (rock band) - Group, GB, depuis 1985" : de quoi départager deux artistes du même nom."""
    parts = [artist.get("name") or ""]
    if artist.get("disambiguation"):
        parts.append(f"({artist['disambiguation']})")
    meta = [m for m in (artist.get("type"), artist.get("country")) if m]
    begin = (artist.get("life-span") or {}).get("begin")
    if begin:
        meta.append(f"depuis {begin[:4]}")
    if meta:
        parts.append("- " + ", ".join(meta))
    return " ".join(parts)


def candidates(results, name):
    """Les artistes de la recherche qui peuvent être `name` : ceux qui portent exactement ce nom, sinon tous les assez pertinents. Plusieurs : une question."""
    good = [a for a in results if a.get("score", 0) >= MIN_SCORE]
    exact = [a for a in good if (a.get("name") or "").casefold() == (name or "").casefold()]
    return (exact or good)[:MAX_CHOICES]


def tagged_artist_id(found):
    """Identifiant MusicBrainz de l'artiste que portent les fichiers des albums `found` (un par album, les premiers seulement), ou "". Celui que la plupart des albums déclarent ; un album aux artistes multiples (feat.) ne dit rien."""
    ids = Counter()
    for album in found[:SAMPLE_ALBUMS]:
        for path in album.files[:1]:
            try:
                meta = audio.read(path)
            except audio.AudioError:
                continue
            values = {albums.parse_mbid(v) for v in meta.values("MUSICBRAINZ_ALBUMARTISTID") if v.strip()}
            if len(values) == 1 and None not in values:
                ids.update(values)
    return ids.most_common(1)[0][0] if ids else ""


# --------------------------------------------------------------------------
# Le dossier de l'artiste
# --------------------------------------------------------------------------
@dataclass
class Inventory:
    """Ce que le dossier d'un artiste possède déjà."""
    have: set = field(default_factory=set)               # title_key de chaque album : rangé, ou déjà déclaré en fichier vide / image
    held: set = field(default_factory=set)               # ceux de ces titres que rien ne remplacera : un album rangé, une image, un fichier qui n'est pas vide
    empty: dict = field(default_factory=dict)            # title_key -> fichiers vides posés pour ce titre : ceux qu'une pochette peut remplacer
    shelves: Counter = field(default_factory=Counter)    # dossier -> albums qu'il range : où poser les fichiers


def inventory(artist_dir):
    """L'inventaire du dossier d'un artiste, qui peut ne pas exister encore (il est alors vide).

    Les titres se lisent comme partout : le nom du dossier d'un album ("1994 - Born Dead", "Daft Punk - Discovery (2001) FLAC"), et le nom des .txt ou images "AAAA - Titre" posées dans le dossier de l'artiste et dans ceux qui rangent ses albums.
    """
    artist_dir, found = Path(artist_dir), Inventory()
    for album in albums.find_albums(artist_dir):
        if album.folder == artist_dir:                   # de l'audio vrac dans le dossier de l'artiste : aucun titre à en tirer
            continue
        found.held.add(title_key(albums.folder_hints(album.folder).title))
        found.shelves[album.folder.parent] += 1
    try:
        for folder in {artist_dir, *found.shelves}:
            for path in folder.iterdir():
                declared = wanted.parse(path.name) if path.is_file() else None
                if declared is None:
                    continue
                key = title_key(declared.title)
                if path.suffix.lower() in coverfile.EXTS or path.stat().st_size:
                    found.held.add(key)
                else:
                    found.empty.setdefault(key, []).append(path)
    except OSError:
        pass
    found.have = found.held | set(found.empty)
    return found


def target_folder(category, artist_dir, shelves):
    """Où poser les fichiers d'une catégorie. Les albums : là où l'artiste range les siens, sinon son dossier. Les autres : le dossier à leur nom s'il en range déjà, sinon un sous-dossier à créer."""
    artist_dir = Path(artist_dir)
    rows = [folder for folder, _ in shelves.most_common()]
    if category == "album":
        return rows[0] if rows else artist_dir
    label = CATEGORIES[category]
    return next((f for f in rows if f.name.casefold() == label.casefold()), artist_dir / label)


class Todo(NamedTuple):
    """Un album à poser : dans quel dossier, quelle sortie, et les fichiers vides qu'une pochette remplacerait."""
    folder: Path
    release: Release
    replaces: tuple = ()

    @property
    def path(self):
        """Le fichier vide de l'album."""
        return self.folder / file_name(self.release.year, self.release.title)

    def image(self, extension):
        """L'image de l'album, d'extension ".jpg" ou ".png"."""
        return self.folder / (stem(self.release.year, self.release.title) + extension)


def missing(planned, inventory_, artist_dir, upgrade=False):
    """[Todo, ...] : ce que `planned` compte de plus que l'inventaire, dans l'ordre des catégories puis des années.

    Avec `upgrade`, un album déjà déclaré par un fichier vide en fait partie aussi : c'est le moment de lui chercher sa pochette."""
    todo = []
    for category in CATEGORIES:
        folder = target_folder(category, artist_dir, inventory_.shelves)
        for release in planned.get(category, []):
            if not file_name(release.year, release.title):
                continue
            key = title_key(release.title)
            if key in inventory_.held:
                continue
            if key not in inventory_.empty:
                todo.append(Todo(folder, release))
            elif upgrade:
                empty = tuple(inventory_.empty[key])
                todo.append(Todo(empty[0].parent, release, empty))
    return todo
