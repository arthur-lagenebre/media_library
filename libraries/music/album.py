"""Albums sur le disque : reconnaissance des dossiers, rapprochement avec une sortie MusicBrainz, et tags visés.

Un album n'a pas la forme d'un film. Son nom de dossier varie d'une source à l'autre - "1994 - Born Dead", "Daft Punk - Discovery (2001) FLAC [16bit 44.1kHz]-CML34" - mais ses fichiers portent presque toujours des tags ALBUM et ARTIST, lisibles en quelques octets. Ce sont eux qui parlent d'abord ; le nom du dossier ne sert qu'à défaut.

Et un album a une forme que le disque permet de vérifier : un nombre de pistes. Parmi les éditions d'un même titre - le CD de 17 pistes, le pressage australien de 16, la réédition de 18 - seules celles qui ont exactement autant de pistes que le dossier a de fichiers sont des candidates. C'est le garde-fou que les films n'ont pas.

Tout est pur, sauf find_albums et artist_override qui lisent le disque.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from libraries.common import filenames

AUDIO_EXTS = {".flac", ".mp3"}            # les formats qu'on sait écrire
OTHER_AUDIO_EXTS = {".m4a", ".aac", ".ogg", ".opus", ".wma", ".ape", ".wv", ".wav", ".aif", ".aiff", ".dsf"}
LYRICS_EXTS = {".lrc"}                     # paroles posées à côté d'une piste : elles suivent son nom
ARTIST_FILE = "artist.txt"                 # le nom d'artiste à garder à la place de celui de MusicBrainz, pour tout ce que le dossier range

# Dossier de disque d'un album en plusieurs CD : "CD1", "CD 2", "Disc 2 - Bonus", "Disque 1".
DISC_DIR_RE = re.compile(r"^(?:cd|dis[ck]|disque)[\s._-]*0*(\d{1,2})(?:\s*[-–—:]\s+.+)?$", re.IGNORECASE)
# Le disque nommé d'après son titre sur MusicBrainz : "1 - La fête est finie", "2 - Épilogue". Trop banal pour valoir seul (un dossier "1 - Album" peut être un album) : voir disc_dirs.
NUMBERED_DISC_DIR_RE = re.compile(r"^0*(\d{1,2})\s+[-–—]\s+\S.*$")
# "1994 - Born Dead" : l'année devant, l'artiste dans le dossier parent.
YEAR_PREFIX_RE = re.compile(r"^\s*((?:19|20)\d{2})\s*[-–—]\s+(.+)$")
YEAR_PAREN_RE = re.compile(r"[\(\[]\s*((?:19|20)\d{2})\s*[\)\]]")
# Ce qu'une "release" ajoute après le titre : format, résolution, groupe.
RELEASE_TAIL_RE = re.compile(r"\s*\b(?:flac|mp3|web(?:-?dl)?|lossless|hi-?res|\d{2}\s*bit)\b.*$", re.IGNORECASE)
# Identifiant MusicBrainz épinglé dans un nom de dossier, sur le modèle de "[tmdbid-27205]".
MBID_RE = re.compile(r"[\[{]\s*mbid[-=\s]\s*([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\s*[\]}]", re.IGNORECASE)


@dataclass
class Album:
    """Un album sur le disque : ses .flac et .mp3 (dossiers de disque compris), et ce qu'on ne sait pas écrire."""
    folder: Path
    files: list
    display: str
    unsupported: list = field(default_factory=list)

    def disc_folder(self, path):
        """Numéro du dossier de disque ("CD2" -> 2) qui contient ce fichier, ou None s'il est à la racine de l'album."""
        if Path(path).parent == self.folder:
            return None
        return disc_number(Path(path).parent.name)

    @property
    def disc_count(self):
        """Disques que le dossier range à part (CD1, CD2...), 1 s'il n'en range aucun."""
        return len({self.disc_folder(f) for f in self.files} - {None}) or 1


def disc_number(name):
    """Numéro de disque d'un nom de dossier ("CD2", "Disc 2 - Bonus", "2 - Épilogue"), ou None."""
    found = DISC_DIR_RE.match(name) or NUMBERED_DISC_DIR_RE.match(name)
    return int(found.group(1)) if found else None


def disc_dirs(subs):
    """Ceux des dossiers `subs` qui rangent un disque de l'album.

    "CD1", "Disc 2"... le disent seuls. "1 - La fête est finie" ressemble autant à un album numéroté : il n'est un disque que s'ils se suivent, de 1 à n, au moins deux.
    """
    named = [s for s in subs if DISC_DIR_RE.match(s.name)]
    numbered = [s for s in subs if s not in named and NUMBERED_DISC_DIR_RE.match(s.name)]
    if len(numbered) >= 2 and sorted(disc_number(s.name) for s in numbered) == list(range(1, len(numbered) + 1)):
        named += numbered
    return sorted(named)


def _subdirs(folder):
    try:
        return sorted(p for p in Path(folder).iterdir() if p.is_dir() and not p.name.startswith("."))
    except OSError:
        return []


def find_albums(root):
    """[Album, ...] sous `root`, en profondeur.

    Un album est un dossier qui contient de l'audio, lui ou ses dossiers de disque. Au-dessus, les dossiers d'artiste ne font que ranger : ils ne comptent pas.
    """
    root = Path(root)
    albums = []

    def scan(folder):
        subs = _subdirs(folder)
        discs = disc_dirs(subs)
        places = [folder] + discs
        files = [f for place in places for f in filenames.files_with_ext(place, AUDIO_EXTS)]
        others = [f for place in places for f in filenames.files_with_ext(place, OTHER_AUDIO_EXTS)]
        if files or others:
            display = filenames.relative_name(folder, root) if folder != root else folder.name
            albums.append(Album(folder, files, display, others))
        for sub in subs:
            if sub not in discs:
                scan(sub)

    if root.is_dir():
        scan(root)
    return albums


def artist_override(folder, root, forced=""):
    """Nom d'artiste imposé à un album, ou "".

    `forced` (--artist) d'abord ; sinon le fichier artist.txt le plus proche, de l'album jusqu'à `root` compris - le dossier d'artiste, typiquement. Sa première ligne non vide est le nom : MusicBrainz écrit parfois le même artiste de plusieurs façons d'un album à l'autre, et c'est celle-ci qui est gardée.
    """
    if forced and forced.strip():
        return forced.strip()
    folder, root = Path(folder), Path(root)
    chain = [folder, *folder.parents]
    for place in chain[:chain.index(root) + 1] if root in chain else [folder]:
        try:
            lines = (place / ARTIST_FILE).read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        name = next((line.strip() for line in lines if line.strip()), "")
        if name:
            return name
    return ""


# --------------------------------------------------------------------------
# Ce que disent le dossier et les tags
# --------------------------------------------------------------------------
@dataclass
class Hints:
    """De quoi chercher un album : artiste, titre, année, et identifiants déjà connus."""
    artist: str = ""
    title: str = ""
    year: str = ""
    pinned: str | None = None          # MBID épinglé dans le nom du dossier
    tagged: str | None = None          # MBID que TOUS les fichiers déclarent


def parse_mbid(text):
    """Identifiant MusicBrainz passé en option, en minuscules ; None si `text` n'en est pas un."""
    found = MBID_RE.search(f"[mbid-{(text or '').strip()}]")
    return found.group(1).lower() if found else None


def folder_hints(folder):
    """Hints lus dans le nom du dossier (et de son parent pour l'artiste)."""
    folder = Path(folder)
    name = folder.name
    found = MBID_RE.search(name)
    pinned = found.group(1).lower() if found else None
    if found:
        name = " ".join((name[:found.start()] + " " + name[found.end():]).split())

    prefixed = YEAR_PREFIX_RE.match(name)
    if prefixed:
        return Hints(folder.parent.name, prefixed.group(2).strip(), prefixed.group(1), pinned)

    year = ""
    paren = YEAR_PAREN_RE.search(name)
    if paren:
        year, name = paren.group(1), name[:paren.start()]
    name = RELEASE_TAIL_RE.sub("", name).strip(" -_.")
    if " - " in name:                  # "Daft Punk - Discovery" : l'artiste est dans le nom
        artist, title = name.split(" - ", 1)
        return Hints(artist.strip(), title.strip(), year, pinned)
    return Hints(folder.parent.name, name, year, pinned)


def _most_common(values):
    values = [v.strip() for v in values if v and v.strip()]
    return Counter(values).most_common(1)[0][0] if values else ""


def tag_hints(metas):
    """Hints lus dans les tags des fichiers d'un album (liste de flac.Metadata ou mp3.Metadata).

    La valeur la plus répandue l'emporte : un morceau bonus rangé avec l'album ne doit pas en changer le titre. L'identifiant MusicBrainz, lui, ne vaut que si TOUS les fichiers le déclarent - un album à moitié étiqueté par Picard n'est pas encore un album étiqueté.
    """
    artist = _most_common(m.first("ALBUMARTIST") or m.first("ALBUM ARTIST") or m.first("ARTIST") for m in metas)
    title = _most_common(m.first("ALBUM") for m in metas)
    years = [re.match(r"\d{4}", m.first("DATE") or m.first("YEAR") or "") for m in metas]
    year = _most_common(y.group(0) for y in years if y)
    ids = {m.first("MUSICBRAINZ_ALBUMID").strip().lower() for m in metas}
    tagged = ids.pop() if (len(ids) == 1 and metas) else None
    return Hints(artist, title, year, None, tagged or None)


# --------------------------------------------------------------------------
# Choix de la sortie
# --------------------------------------------------------------------------
MIN_TITLE = 0.6                          # en dessous, la sortie trouvée parle d'autre chose
COVER_FORMATS = {"CD", "Digital Media"}  # d'où viennent les .flac et les .mp3 : un vinyle a d'autres faces, parfois d'autres pistes


def normalize(text):
    """"TRON: Legacy (OST)" et "tron legacy ost" s'écrivent pareil : seuls les mots comptent."""
    return " ".join(re.sub(r"[^\w]+", " ", (text or "").lower()).split())


def similarity(a, b):
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def track_counts(release):
    """[pistes par disque] d'une sortie, qu'elle vienne d'une recherche ou d'une fiche complète."""
    return [m.get("track-count") or len(m.get("tracks") or []) for m in release.get("media") or []]


def group_id(release):
    return (release.get("release-group") or {}).get("id")


def describe(release):
    """'OutRun (2013-02-25, FR, CD:13) [id 4e5d9f0c]' - comment on montre une sortie."""
    media = "+".join(f"{m.get('format') or '?'}:{m.get('track-count') or len(m.get('tracks') or [])}" for m in release.get("media") or [])
    details = ", ".join(x for x in (release.get("date"), release.get("country"), media) if x)
    return f"{release.get('title')} ({details}) [id {(release.get('id') or '')[:8]}]"


def edition_rank(release, year, country, discs=1):
    """Clé de tri des éditions d'un même album : la plus vraisemblable d'abord.

    Officielle ; en autant de disques que le dossier en range ; sur un support d'où sortent des .flac ; de l'année annoncée (pas la réédition de 2021) ; du pays demandé, à défaut européenne puis mondiale ; la plus ancienne à égalité.

    La FORME passe avant le pays : le vinyle français de "Human After All" a bien dix pistes, mais en deux faces de cinq - retenu, il aurait écrit "disque 2, piste 1" sur la sixième.
    """
    countries = [country, "XE", "XW"]
    media = release.get("media") or []
    formats = {m.get("format") for m in media}
    date = release.get("date") or ""
    return (release.get("status") != "Official", len(media) != discs, not formats & COVER_FORMATS, bool(year) and date[:4] != year, countries.index(release.get("country")) if release.get("country") in countries else len(countries), date or "9999")


@dataclass
class Choice:
    """Sortie retenue pour un album, ou la raison de n'en retenir aucune."""
    release: dict | None = None
    rivals: list = field(default_factory=list)   # autres albums du même titre qui tiennent aussi : une question
    reason: str = ""


def choose_release(results, file_count, hints, country="FR", discs=1):
    """Choice parmi les résultats d'une recherche de sorties.

    Seules comptent les éditions qui ont autant de pistes que le dossier a de fichiers. Parmi elles, un album par release group, celui au titre exact d'abord ; deux albums DIFFÉRENTS au même titre qui tiennent tous les deux sont une question, pas une déduction.
    """
    if not results:
        return Choice(reason="aucun résultat")
    close = [r for r in results if not hints.title or similarity(r.get("title"), hints.title) >= MIN_TITLE]
    fitting = [r for r in close if sum(track_counts(r)) == file_count]
    if not fitting:
        seen = sorted({sum(track_counts(r)) for r in close})
        if not seen:
            return Choice(reason=f"titres trouvés trop éloignés de '{hints.title}' (ex. {describe(results[0])})")
        return Choice(reason=f"aucune édition de {file_count} piste(s) ; trouvé : {', '.join(map(str, seen))} piste(s)")

    heads = {}
    for release in sorted(fitting, key=lambda r: edition_rank(r, hints.year, country, discs)):
        heads.setdefault(group_id(release), release)
    exact = [r for r in heads.values() if normalize(r.get("title")) == normalize(hints.title)]
    candidates = exact or sorted(heads.values(), key=lambda r: -similarity(r.get("title"), hints.title))
    return Choice(candidates[0], candidates[1:] if exact else [])


# --------------------------------------------------------------------------
# Fichiers et pistes
# --------------------------------------------------------------------------
NUMBER_RE = re.compile(r"^\s*0*(\d{1,3})")                      # "03", "3/12"
DISC_TRACK_NAME_RE = re.compile(r"(?<!\d)(\d{1,2})-(\d{2,3})(?=\s)")   # "... - 01-01 One More Time"
LEAD_NUMBER_RE = re.compile(r"^\s*(\d{1,3})(?=[\s._-])")         # "01 Titre", "01. Titre", "01-titre"
MAX_DURATION_GAP = 5                                            # secondes d'écart tolérées avec la durée de la piste


@dataclass
class Entry:
    """Un fichier de l'album, avec ce qu'il dit de sa place."""
    path: Path
    disc: int | None = None
    track: int | None = None
    title: str = ""
    duration: float | None = None
    titled: bool = False               # le titre vient d'un tag, pas du nom du fichier


def _number(text):
    found = NUMBER_RE.match(text or "")
    return int(found.group(1)) if found else None


def entry_for(path, meta, disc_folder=None):
    """Entry d'un fichier : tags d'abord, puis dossier de disque, puis nom.

    Le dossier de disque prime sur le tag DISCNUMBER : "CD2/01.flac" est rangé là par quelqu'un, alors que les tags d'un CD bonus disent volontiers "disque 1".
    """
    path = Path(path)
    disc = _number(meta.first("DISCNUMBER")) if meta else None
    track = _number(meta.first("TRACKNUMBER")) if meta else None
    if disc_folder is not None:
        disc = disc_folder
    if track is None:
        paired = DISC_TRACK_NAME_RE.search(path.stem)
        lead = LEAD_NUMBER_RE.match(path.stem)
        if paired:
            disc, track = (disc if disc is not None else int(paired.group(1))), int(paired.group(2))
        elif lead:
            track = int(lead.group(1))
    title = (meta.first("TITLE") if meta else "") or path.stem
    return Entry(path, disc, track, title, meta.duration if meta else None, bool(meta and meta.first("TITLE")))


def match_tracks(entries, release):
    """({chemin: (disque, piste)}, raison) : chaque fichier sur une piste distincte de la sortie.

    Le numéro d'abord - disque et piste, ou numérotation continue sur tout l'album - puis la ressemblance des titres pour ce qui reste, les meilleures correspondances d'abord et chaque piste une seule fois. Un seul fichier sans piste et l'album entier est refusé : à moitié étiqueté, il aurait l'air fait.
    """
    media = release.get("media") or []
    slots = [(m, t) for m in media for t in m.get("tracks") or []]
    by_position = {(m.get("position"), t.get("position")): (m, t) for m, t in slots}
    placed, taken = {}, set()

    for entry in entries:
        if entry.track is None:
            continue
        continuous = None
        if 1 <= entry.track <= len(slots):              # numérotation continue d'un album à plusieurs disques
            medium, track = slots[entry.track - 1]
            continuous = (medium.get("position"), track.get("position"))
        if len(media) == 1:
            key = (media[0].get("position"), entry.track)
        elif entry.disc is not None and (entry.disc, entry.track) in by_position:
            key = (entry.disc, entry.track)
        else:                                           # "CD 2/10 - Distortion" : les tags d'une édition en 16 pistes d'un seul tenant
            key = continuous
        if key is None:
            continue
        if key in by_position and key not in taken:
            placed[entry.path] = key
            taken.add(key)

    # Un numéro qui tombe sur une piste au titre sans rapport avec celui du fichier est peut-être celui d'une autre édition ("12 - San" quand San est la piste 1) : sa place est remise en jeu, et il la retrouve si aucun titre ne le réclame mieux.
    by_path = {e.path: e for e in entries}
    doubtful = {path: key for path, key in placed.items() if by_path[path].titled and similarity(by_path[path].title, by_position[key][1].get("title")) < MIN_TITLE / 2}
    for path, key in doubtful.items():
        del placed[path]
        taken.discard(key)

    rest = [e for e in entries if e.path not in placed]
    scores = sorted(((similarity(e.title, t.get("title")), str(e.path), e, (m.get("position"), t.get("position"))) for e in rest for m, t in slots if (m.get("position"), t.get("position")) not in taken), key=lambda x: (-x[0], x[1], x[3]))
    for score, _, entry, key in scores:
        if score < MIN_TITLE or entry.path in placed or key in taken:
            continue
        placed[entry.path] = key
        taken.add(key)
    for path, key in doubtful.items():
        if path not in placed and key not in taken:
            placed[path] = key
            taken.add(key)

    missing = [e.path.name for e in entries if e.path not in placed]
    if missing:
        return {}, f"{len(missing)} fichier(s) sans piste correspondante : " + ", ".join(missing[:3]) + (" ..." if len(missing) > 3 else "")
    return {path: by_position[key] for path, key in placed.items()}, ""


def entry_notes(entry, track):
    """Remarques sur un fichier placé : un titre ou une durée qui ne collent pas méritent un coup d'œil."""
    notes = []
    if similarity(entry.title, track.get("title")) < MIN_TITLE / 2:
        notes.append(f"titre du fichier éloigné : {entry.title!r}")
    length = track.get("length") or (track.get("recording") or {}).get("length")
    if entry.duration and length and abs(entry.duration - length / 1000) > MAX_DURATION_GAP:
        notes.append(f"durée {entry.duration:.0f} s contre {length / 1000:.0f} s attendues")
    return notes


# --------------------------------------------------------------------------
# Tags visés
# --------------------------------------------------------------------------
# Les clés propres à une ÉDITION : toujours gérées, même quand MusicBrainz n'en donne pas - une valeur restée d'une autre édition mentirait. Les autres ne le sont que si la sortie leur donne une valeur : un genre écrit à la main ne disparaît pas parce que la base n'en connaît aucun.
EDITION_KEYS = {"LABEL", "CATALOGNUMBER", "BARCODE", "RELEASECOUNTRY", "RELEASESTATUS", "RELEASETYPE", "MEDIA", "MUSICBRAINZ_ALBUMID", "MUSICBRAINZ_RELEASEGROUPID", "MUSICBRAINZ_ALBUMARTISTID", "MUSICBRAINZ_ARTISTID", "MUSICBRAINZ_TRACKID", "MUSICBRAINZ_RELEASETRACKID"}
# Doublons de clés gérées, que certains lecteurs lisent avant elles : laissés en place, ils contrediraient ce qu'on écrit.
OBSOLETE_KEYS = {"YEAR", "ALBUM ARTIST"}
MAX_GENRES = 3


def unique(values):
    out = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out


def names_artist(credit, name):
    """Vrai si ce crédit désigne l'artiste `name`, quelle que soit la façon dont MusicBrainz l'y écrit.

    Le nom crédité, le nom de la fiche et son nom de tri sont comparés : "H.F. Thiéfaine", "Thiéfaine" et "Hubert Félix Thiéfaine" sont tous la fiche "Hubert-Félix Thiéfaine". Un nom qui contient tous les mots de l'autre suffit ; "Mairet" ne ressemble pas à Thiéfaine.
    """
    wanted = set(normalize(name).split())
    artist = credit.get("artist") or {}
    for known in (credit.get("name"), artist.get("name"), artist.get("sort-name")):
        words = set(normalize(known).split())
        if words and wanted and (words <= wanted or wanted <= words or similarity(known, name) >= MIN_TITLE):
            return True
    return False


FEAT_JOIN_RE = re.compile(r"\b(?:feat|ft|featuring)\b", re.IGNORECASE)


def guest_start(credits, artist):
    """Indice du premier invité quand l'artiste imposé est crédité "feat." d'autres, sinon None."""
    if artist:
        for i, credit in enumerate(credits[:-1]):
            if names_artist(credit, artist) and FEAT_JOIN_RE.search(credit.get("joinphrase") or ""):
                return i + 1
    return None


def guest_ids(credits, artist):
    """Les identifiants des invités que `artist` porte en "feat." sur ce crédit."""
    start = guest_start(credits, artist)
    return {(c.get("artist") or {}).get("id") for c in credits[start:]} - {None} if start else set()


def without_guests(credits, artist, hidden):
    """Les crédits sans les invités de `hidden`, quand l'artiste imposé est crédité "feat." d'eux.

    MusicBrainz peut mettre tout un disque en "Ultra Vomit feat. A, B, C" : l'artiste imposé est là pour que ce soit "Ultra Vomit", comme les autres albums. Les invités d'une seule piste, eux, restent.
    """
    start = guest_start(credits, artist)
    if not start:
        return credits
    kept = credits[:start] + [c for c in credits[start:] if (c.get("artist") or {}).get("id") not in hidden]
    return kept[:-1] + [dict(kept[-1], joinphrase="")]


def credit_name(credits, sort=False, artist=""):
    """'Daft Punk', 'Kavinsky feat. Havoc' : les noms crédités, liaisons comprises.

    `artist` impose son écriture au crédit qui le désigne, les autres crédits gardent la leur : "Thiéfaine / Mairet" devient "Hubert-Félix Thiéfaine / Mairet". Le nom de tri ne bouge pas, c'est celui de la même fiche.
    """
    parts = []
    for credit in credits:
        known = credit.get("artist") or {}
        name = (known.get("sort-name") if sort else None) or credit.get("name") or known.get("name") or ""
        if artist and not sort and names_artist(credit, artist):
            name = artist
        parts.append(name + (credit.get("joinphrase") or ""))
    return "".join(parts)


def genres(group, release, limit=MAX_GENRES):
    """Genres votés, les plus votés d'abord : ceux du release group, sinon ceux de la sortie."""
    voted = (group or {}).get("genres") or release.get("genres") or []
    ranked = sorted((g for g in voted if g.get("name")), key=lambda g: (-(g.get("count") or 0), g["name"]))
    return [g["name"][:1].upper() + g["name"][1:] for g in ranked[:limit]]


def target_tags(release, group, medium, track, with_genres=True, artist=""):
    """[(clé, valeur)] visés pour une piste.

    Les noms de clés sont ceux de Picard : un fichier étiqueté ici doit se relire à l'identique dans Picard ou dans un lecteur, et un fichier déjà passé par Picard ne doit pas paraître différent. `artist` remplace l'écriture que MusicBrainz donne de l'artiste (voir artist_override).
    """
    rg = group or release.get("release-group") or {}
    recording = track.get("recording") or {}
    album_credit = release.get("artist-credit") or []
    track_credit = track.get("artist-credit") or recording.get("artist-credit") or album_credit
    hidden = guest_ids(album_credit, artist)
    album_credit, track_credit = without_guests(album_credit, artist, hidden), without_guests(track_credit, artist, hidden)
    media = release.get("media") or []
    labels = release.get("label-info") or []
    first = rg.get("first-release-date") or ""
    count = str(medium.get("track-count") or len(medium.get("tracks") or []))
    tags = [("TITLE", track.get("title") or recording.get("title")), ("ARTIST", credit_name(track_credit, artist=artist)), ("ARTISTSORT", credit_name(track_credit, sort=True)), ("ALBUM", release.get("title")), ("ALBUMARTIST", credit_name(album_credit, artist=artist)), ("ALBUMARTISTSORT", credit_name(album_credit, sort=True)), ("TRACKNUMBER", str(track.get("position") or "")), ("TRACKTOTAL", count), ("TOTALTRACKS", count), ("DISCNUMBER", str(medium.get("position") or "")), ("DISCTOTAL", str(len(media))), ("TOTALDISCS", str(len(media))), ("DATE", release.get("date")), ("ORIGINALDATE", first), ("ORIGINALYEAR", first[:4])]
    tags += [("GENRE", g) for g in (genres(rg, release) if with_genres else [])]
    tags += [("RELEASETYPE", t.lower()) for t in unique([rg.get("primary-type")] + list(rg.get("secondary-types") or []))]
    tags += [("RELEASESTATUS", (release.get("status") or "").lower()), ("RELEASECOUNTRY", release.get("country")), ("MEDIA", medium.get("format")), ("BARCODE", release.get("barcode"))]
    tags += [("LABEL", name) for name in unique((i.get("label") or {}).get("name") for i in labels)]
    tags += [("CATALOGNUMBER", number) for number in unique(i.get("catalog-number") for i in labels)]
    tags += [("MUSICBRAINZ_ALBUMID", release.get("id")), ("MUSICBRAINZ_RELEASEGROUPID", rg.get("id"))]
    tags += [("MUSICBRAINZ_ALBUMARTISTID", a) for a in unique((c.get("artist") or {}).get("id") for c in album_credit)]
    tags += [("MUSICBRAINZ_ARTISTID", a) for a in unique((c.get("artist") or {}).get("id") for c in track_credit)]
    tags += [("MUSICBRAINZ_TRACKID", recording.get("id")), ("MUSICBRAINZ_RELEASETRACKID", track.get("id"))]
    return [(key, str(value)) for key, value in tags if value]


def managed_keys(target):
    return EDITION_KEYS | OBSOLETE_KEYS | {key for key, _ in target}


def merge(comments, target):
    """Tags à écrire : les visés d'abord, puis tout ce qu'on ne gère pas, tel quel.

    ReplayGain, paroles, notes, ISRC : rien de tout ça ne vient de MusicBrainz, et un étiquetage qui l'effacerait détruirait ce qu'aucune base ne peut rendre.
    """
    managed = managed_keys(target)
    return list(target) + [(key, value) for key, value in comments if key.upper() not in managed]


def differences(comments, target):
    """[(clé, valeurs actuelles, valeurs visées)] pour les clés gérées qui diffèrent. L'ordre des valeurs multiples ne compte pas, la casse des clés non plus."""
    managed = managed_keys(target)
    current, wanted = {}, {}
    for key, value in comments:
        if key.upper() in managed:
            current.setdefault(key.upper(), []).append(value)
    for key, value in target:
        wanted.setdefault(key, []).append(value)
    keys = list(wanted) + [k for k in current if k not in wanted]
    return [(key, current.get(key, []), wanted.get(key, [])) for key in keys if sorted(current.get(key, [])) != sorted(wanted.get(key, []))]
