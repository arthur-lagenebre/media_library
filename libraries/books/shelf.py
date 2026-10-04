"""L'étagère : ce qu'une bibliothèque de livres contient, rangé en sections, séries et volumes.

    Livres/                     <- la bibliothèque
        Manga/                  <- une section
            20th Century Boys/  <- une série (un dossier) ; pour les romans, c'est l'auteur
                Tome 01.cbz     <- un volume
        Manuels/Un guide.epub   <- un fichier seul dans sa section est sa propre série
        Comics/_DC/Batman/      <- un dossier "_Univers" regroupe des séries : c'est une collection, "Comics · DC"

Les dossiers qui suivent le nom de la série ("Sambre/Sambre/2 - Troisième génération/") ne changent pas la série : ses volumes sont tous ceux qu'elle contient, à n'importe quelle profondeur, groupés par sous-dossier à l'affichage.

Le catalogue garde ce qu'on a lu dans chaque fichier : ouvrir 9000 archives sur un partage réseau prend un quart d'heure, et ne sert qu'une fois tant que le fichier ne bouge pas (même taille, même date).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import cbz, comicinfo, epub
from .archive import BookError, natural_key

KINDS = {".cbz": "cbz", ".cbr": "cbr", ".epub": "epub", ".pdf": "pdf", ".mobi": "mobi", ".azw3": "azw3"}
OPTIONAL_KINDS = (".pdf",)                    # ignorés sauf demande (include_pdf) : ni fiche ni couverture à en tirer, ils n'apportent que du bruit
SKIPPED_PREFIXES = ("__", "#", "@", ".")      # "__" : ce qui n'est pas rangé - __Data__ (nos pages), __En cours (travaux en cours) ; #recycle, @eaDir (vignettes DSM), dossiers cachés
LOOSE_SECTION = "Autres"                      # les fichiers posés à la racine de la bibliothèque

# Les sections dans l'ordre où on les range sur l'étagère : ce qu'on feuillette en premier. Les autres suivent par ordre alphabétique, et "Autres" ferme la marche.
SECTION_ORDER = ("Manga", "BD", "Comics", "Artbook", "Romans", "Livre dont vous êtes héros", "Magazines", "Manuels")

# Ce qu'une section compte : des tomes, sauf là où le mot sonnerait faux.
UNITS = {"Romans": ("livre", "livres"), "Livre dont vous êtes héros": ("livre", "livres"),
         "Manuels": ("livre", "livres"), "Autres": ("livre", "livres"), "Magazines": ("numéro", "numéros")}
DEFAULT_UNIT = ("tome", "tomes")

NUMBER_RE = re.compile(r"^(?:tome|t|n°|no|#|vol\.?|volume)?\s*0*(\d+(?:[.,]\d+)?)\b", re.IGNORECASE)
DATE_RE = re.compile(r"\((\d{4})-(\d{2})\)")
MAX_COUNT = 1000          # un "Count" au-delà est une faute de frappe, pas une série à compléter


def unit(section, n):
    """'12 tomes', '1 livre', '3 numéros'."""
    one, many = UNITS.get(section, DEFAULT_UNIT)
    return f"{n} {one if n == 1 else many}"


def sort_text(text):
    """Texte pour trier : sans accents ni casse, chiffres en nombres."""
    plain = "".join(c for c in unicodedata.normalize("NFD", text or "") if not unicodedata.combining(c))
    return natural_key(plain)


def name_hints(stem):
    """Ce que le nom d'un fichier laisse deviner quand il n'a pas de fiche : {'Number', 'Year', 'Month'}.

    'Tome 01' -> 1 ; '1 - L'anomalie' -> 1 ; '28.La rue maudite' -> 28 ; 'Tome 001 (1975-01)' -> 1, janvier 1975. Un nom qui commence par un nombre collé à du texte ('21st Century Boys') n'en donne pas.
    """
    hints = {}
    number = NUMBER_RE.match(stem.strip())
    if number:
        value = number.group(1).replace(",", ".")
        hints["Number"] = value[:-2] if value.endswith(".0") else value
    date = DATE_RE.search(stem)
    if date and 1 <= int(date.group(2)) <= 12:
        hints["Year"], hints["Month"] = int(date.group(1)), int(date.group(2))
    return hints


@dataclass
class Volume:
    path: Path
    rel: str                  # chemin relatif à la bibliothèque, séparé par "/" : l'identité du volume
    section: str
    group: str                # nom de la série
    sub: str                  # sous-dossier à l'intérieur de la série ("" si le volume est à sa racine)
    size: int
    mtime: int
    kind: str
    info: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def stem(self):
        return self.path.stem

    @property
    def title(self):
        return self.info.get("Title") or self.stem

    @property
    def fields(self):
        """La fiche du fichier, complétée par ce que son nom dit (numéro, date) pour ce qu'elle ne renseigne pas."""
        return {**name_hints(self.stem), **self.info}

    @property
    def number(self):
        """Numéro du volume (texte), ou None."""
        return self.fields.get("Number")

    @property
    def key(self):
        """Identifiant d'une miniature : change dès que le fichier change, pour que la page précédente ne serve pas une couverture périmée."""
        digest = hashlib.sha1(self.rel.encode("utf-8")).hexdigest()[:12]
        return f"{digest}-{self.size}-{self.mtime}"

    @property
    def order(self):
        """Rang dans la série : par sous-dossier, puis les volumes numérotés par numéro, puis les autres par nom."""
        value = comicinfo.number_value(self.number)
        return (natural_key(self.sub), 0 if value is not None else 1, value or 0.0, sort_text(self.stem))


@dataclass
class Series:
    section: str
    name: str
    volumes: list = field(default_factory=list)
    collection: str = ""      # l'univers qui la regroupe ("DC" pour Comics/_DC/Batman), ou ""

    def sort(self):
        self.volumes.sort(key=lambda v: v.order)

    @property
    def id(self):
        """Identifiant stable : il ne change que si la série change de section, de collection ou de nom."""
        return hashlib.sha1(f"{self.section}/{self.collection}/{self.name}".encode("utf-8")).hexdigest()[:8]

    @property
    def label(self):
        """Le nom de sa section d'affichage : "Comics", ou "Comics · DC" quand elle appartient à une collection."""
        return f"{self.section} · {self.collection}" if self.collection else self.section

    @property
    def cover_volume(self):
        return self.volumes[0]

    def _count(self, field_name):
        return Counter(v.fields[field_name] for v in self.volumes if v.fields.get(field_name))

    def _people(self):
        found = Counter()
        for volume in self.volumes:
            for role in ("Writer", "Penciller"):
                for person in (volume.fields.get(role) or "").split(","):
                    if person.strip():
                        found[person.strip()] += 1
        return found

    @property
    def authors(self):
        """Les auteurs les plus présents dans la série, scénaristes et dessinateurs confondus, sans doublon."""
        return [name for name, _ in self._people().most_common(6)]

    @property
    def publisher(self):
        counted = self._count("Publisher").most_common(1)
        return counted[0][0] if counted else ""

    @property
    def genres(self):
        found = Counter()
        for volume in self.volumes:
            for genre in (volume.fields.get("Genre") or "").split(","):
                if genre.strip():
                    found[genre.strip()] += 1
        return [name for name, _ in found.most_common(6)]

    @property
    def years(self):
        """(première, dernière) année de parution, ou None."""
        years = [v.fields["Year"] for v in self.volumes if v.fields.get("Year")]
        return (min(years), max(years)) if years else None

    @property
    def summary(self):
        """(texte, volume) : le résumé du premier volume qui en a un. Les fiches décrivent un volume, pas la série : c'est celui du tome 1 qui la présente le mieux."""
        for volume in self.volumes:
            if volume.fields.get("Summary"):
                return volume.fields["Summary"], volume
        return "", None

    @property
    def tagged(self):
        return sum(1 for v in self.volumes if v.info)

    def tag_groups(self):
        """{Series de la fiche: [volumes]} : un dossier peut réunir plusieurs séries au sens des fiches, comme les cycles de "Sambre"."""
        groups = {}
        for volume in self.volumes:
            groups.setdefault(volume.fields.get("Series") or "", []).append(volume)
        return groups

    def missing(self):
        """[(libellé, [numéros manquants], total attendu)] d'après le "Count" des fiches.

        Un dossier qui réunit plusieurs séries se compte série par série. On ne dit rien d'un groupe dont un volume n'a pas de numéro (il pourrait être celui qui manque) ni d'un total qui n'a pas de sens.
        """
        result = []
        for label, volumes in sorted(self.tag_groups().items()):
            counts = [v.fields["Count"] for v in volumes if v.fields.get("Count")]
            values = [comicinfo.number_value(v.number) for v in volumes]
            if not counts or None in values:
                continue
            total = max(counts)
            if not 1 < total <= MAX_COUNT:
                continue
            owned = {int(x) for x in values if x == int(x)}
            lacking = [n for n in range(1, total + 1) if n not in owned]
            if lacking:
                result.append((label, lacking, total))
        return result


# ----------------------------------------------------------------------------
# Parcours
# ----------------------------------------------------------------------------
def _skipped(name):
    return name.startswith(SKIPPED_PREFIXES)


def _walk(folder, kinds):
    """(chemin, taille, date) des livres d'un dossier, à toute profondeur, dans l'ordre. `kinds` : les extensions retenues."""
    found = []
    try:
        entries = sorted(os.scandir(folder), key=lambda e: e.name)
    except OSError:
        return found
    for entry in entries:
        if _skipped(entry.name):
            continue
        try:
            if entry.is_dir():
                found += _walk(entry.path, kinds)
            elif Path(entry.name).suffix.lower() in kinds:
                stat = entry.stat()
                found.append((Path(entry.path), stat.st_size, int(stat.st_mtime)))
        except OSError:
            continue
    return found


def _is_container(name):
    """Un dossier "_DC", "_Marvel" : il regroupe des séries au lieu d'en être une. Le "__" des dossiers pas encore rangés est écarté avant."""
    return name.startswith("_")


def scan(root, include_pdf=False):
    """Les séries de la bibliothèque, par section : [(nom de la section, [Series])], séries triées par nom.

    Une collection ("_DC" dans "Comics") est sa propre section d'affichage - "Comics · DC" -, rangée juste après sa section. Ne lit le contenu d'aucun fichier : seuls les noms, tailles et dates sont vus (voir `read_info`). Les .pdf sont ignorés, sauf `include_pdf`.
    """
    root = Path(root)
    kinds = {ext: kind for ext, kind in KINDS.items() if include_pdf or ext not in OPTIONAL_KINDS}
    sections = {}

    def add(section, collection, group, sub, path, size, mtime):
        volume = Volume(path, path.relative_to(root).as_posix(), section, group, sub, size, mtime, kinds[path.suffix.lower()])
        series = sections.setdefault((section, collection), {}).setdefault(group, Series(section, group, collection=collection))
        series.volumes.append(volume)

    def add_children(section, collection, folder):
        """Les séries d'une section - ou d'une collection - : un dossier par série, un fichier seul étant la sienne."""
        try:
            children = sorted(os.scandir(folder), key=lambda e: e.name)
        except OSError:
            return
        for child in children:
            if _skipped(child.name):
                continue
            path = Path(child.path)
            try:
                if child.is_dir():
                    if not collection and section != LOOSE_SECTION and _is_container(child.name):
                        add_children(section, child.name.lstrip("_").strip(), child.path)
                        continue
                    for file, size, mtime in _walk(child.path, kinds):
                        sub = file.parent.relative_to(path).as_posix()
                        add(section, collection, child.name, "" if sub == "." else sub, file, size, mtime)
                elif path.suffix.lower() in kinds:
                    stat = child.stat()
                    add(section, collection, path.stem, "", path, stat.st_size, int(stat.st_mtime))
            except OSError:
                continue

    try:
        top = sorted(os.scandir(root), key=lambda e: e.name)
    except OSError:
        return []
    for entry in top:
        if _skipped(entry.name):
            continue
        path = Path(entry.path)
        try:
            if entry.is_dir():
                add_children(entry.name, "", entry.path)
            elif path.suffix.lower() in kinds:
                stat = entry.stat()
                add(LOOSE_SECTION, "", path.stem, "", path, stat.st_size, int(stat.st_mtime))
        except OSError:
            continue

    def rank(key):
        section, collection = key
        if section == LOOSE_SECTION:
            return (2, 0, [], [])
        if section in SECTION_ORDER:
            return (0, SECTION_ORDER.index(section), [], sort_text(collection))
        return (1, 0, sort_text(section), sort_text(collection))

    result = []
    for key in sorted(sections, key=rank):
        series = sorted(sections[key].values(), key=lambda s: sort_text(s.name))
        for one in series:
            one.sort()
        result.append((series[0].label, series))
    return result


# ----------------------------------------------------------------------------
# Lecture des fiches, catalogue
# ----------------------------------------------------------------------------
def read_info(volume):
    """Lit la fiche d'un volume et la range dans `volume.info` ; un fichier illisible garde son erreur dans `volume.error`.

    Seuls les .cbz (ComicInfo.xml) et les .epub (.opf) portent une fiche : les autres formats n'ont que leur nom.
    """
    volume.info, volume.error = {}, None
    try:
        if volume.kind == "cbz":
            volume.info = cbz.read_info(volume.path)
        elif volume.kind == "epub":
            volume.info = epub.read_info(volume.path)
    except BookError as e:
        volume.error = str(e)


def read_cover(volume):
    """Octets de la couverture d'un volume, ou None (format sans image lisible, pas de couverture). BookError si le fichier est illisible."""
    if volume.kind == "cbz":
        return cbz.cover(volume.path, volume.info.get("FrontCover"))
    if volume.kind == "epub":
        return epub.cover(volume.path)
    return None


CATALOG_VERSION = 1


def load_catalog(path):
    """{chemin relatif: {'size', 'mtime', 'info'}} du catalogue écrit au passage précédent, ou {}."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("version") != CATALOG_VERSION:
        return {}
    return data.get("volumes") or {}


def apply_catalog(volumes, catalog):
    """Reprend du catalogue la fiche des volumes qui n'ont pas bougé. Retourne ceux qu'il reste à lire."""
    todo = []
    for volume in volumes:
        kept = catalog.get(volume.rel)
        if kept and kept.get("size") == volume.size and kept.get("mtime") == volume.mtime and isinstance(kept.get("info"), dict):
            volume.info = kept["info"]
        else:
            todo.append(volume)
    return todo


def dump_catalog(volumes):
    """Le catalogue en JSON, tel qu'on l'écrit : un volume illisible n'y figure pas, il sera relu au prochain passage."""
    entries = {v.rel: {"size": v.size, "mtime": v.mtime, "info": v.info} for v in volumes if not v.error}
    return json.dumps({"version": CATALOG_VERSION, "volumes": entries}, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
