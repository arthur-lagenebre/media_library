"""Lire un .epub : la fiche de son .opf et sa couverture.

Un .epub est un zip dont container.xml désigne le fichier .opf, qui porte la fiche (Dublin Core, plus les champs "calibre:" quand Calibre est passé par là) et la liste des fichiers du livre. La fiche est rendue avec les noms de ComicInfo (voir comicinfo.py) : Title, Writer, Publisher, Year, Summary...

Rien n'est écrit, et seuls l'.opf et la couverture sont lus.
"""

import posixpath
import re
from html import unescape
from urllib.parse import unquote
from xml.etree import ElementTree

from .archive import BookError, IMAGE_EXTENSIONS, open_zip, read_member

DC = "{http://purl.org/dc/elements/1.1/}"
OPF = "{http://www.idpf.org/2007/opf}"
CONTAINER = "{urn:oasis:names:tc:opendocument:xmlns:container}"

TAG_RE = re.compile(r"<[^>]*>")
BREAK_RE = re.compile(r"(?i)<br\s*/?>|</p>|</div>")
DATE_RE = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?")
MIN_YEAR = 1000      # Calibre écrit 0101-01-01 quand il ne sait pas : ce n'est pas une année


def plain_text(html):
    """Le texte d'une description : les balises sautées, les entités décodées, les paragraphes gardés."""
    text = unescape(TAG_RE.sub("", BREAK_RE.sub("\n", html or "")))
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _opf_root(archive):
    """(arbre de l'.opf, son chemin dans l'archive)."""
    try:
        container = ElementTree.fromstring(read_member(archive, "META-INF/container.xml", "container.xml"))
        path = container.find(f".//{CONTAINER}rootfile").get("full-path")
        return ElementTree.fromstring(read_member(archive, path, ".opf")), path
    except (BookError, AttributeError, ElementTree.ParseError) as e:
        raise BookError(f"epub sans .opf lisible : {e}") from e


def _texts(metadata, tag):
    return [(e.text or "").strip() for e in metadata.findall(DC + tag) if (e.text or "").strip()]


def _meta(metadata, name):
    for element in metadata.findall(f"{OPF}meta") + metadata.findall("meta"):
        if element.get("name") == name and element.get("content"):
            return element.get("content").strip()
    return None


def parse_opf(root):
    """Fiche d'un .opf déjà analysé, aux noms de ComicInfo."""
    metadata = root.find(f"{OPF}metadata")
    if metadata is None:
        metadata = root.find("metadata")
    if metadata is None:
        return {}
    info = {}
    title = _texts(metadata, "title")
    if title:
        info["Title"] = title[0]
    # Les auteurs : ceux qu'un rôle désigne comme tels, ou sans rôle. Les traducteurs, illustrateurs et le "bkp" de Calibre n'écrivent pas le livre.
    authors = [(e.text or "").strip() for e in metadata.findall(DC + "creator")
               if (e.text or "").strip() and e.get(f"{OPF}role") in (None, "aut")]
    if authors:
        info["Writer"] = ", ".join(authors)
    for field, tag in (("Publisher", "publisher"), ("LanguageISO", "language")):
        found = _texts(metadata, tag)
        if found:
            info[field] = found[0]
    subjects = _texts(metadata, "subject")
    if subjects:
        info["Genre"] = ", ".join(subjects)
    summary = plain_text((_texts(metadata, "description") or [""])[0])
    if summary:
        info["Summary"] = summary
    date = DATE_RE.match((_texts(metadata, "date") or [""])[0])
    if date and int(date.group(1)) >= MIN_YEAR:
        info["Year"] = int(date.group(1))
        for field, part in (("Month", date.group(2)), ("Day", date.group(3))):
            if part and 1 <= int(part) <= 31:
                info[field] = int(part)
    series = _meta(metadata, "calibre:series")
    if series:
        info["Series"] = series
        index = _meta(metadata, "calibre:series_index")
        if index:
            info["Number"] = index[:-2] if index.endswith(".0") else index
    return info


def read_info(path):
    """Fiche d'un .epub, ou BookError s'il est illisible."""
    with open_zip(path) as archive:
        return parse_opf(_opf_root(archive)[0])


def cover_href(root):
    """Chemin (relatif à l'.opf) du fichier image de la couverture, ou None.

    Dans l'ordre : ce que l'.opf déclare (EPUB 3 "cover-image", Calibre "cover"), puis une image du manifeste nommée cover. Une référence "guide" mène souvent à une page de texte plutôt qu'à l'image : elle n'est pas suivie.
    """
    manifest = root.find(f"{OPF}manifest")
    items = list(manifest) if manifest is not None else []
    by_id = {i.get("id"): i for i in items}
    candidates = [i for i in items if "cover-image" in (i.get("properties") or "").split()]
    metadata = root.find(f"{OPF}metadata")
    declared = _meta(metadata, "cover") if metadata is not None else None
    if declared and declared in by_id:
        candidates.append(by_id[declared])
    candidates += [i for i in items if (i.get("id") or "").lower() in ("cover", "cover-image", "coverimage")]
    for item in candidates:
        href = item.get("href") or ""
        if href.lower().endswith(IMAGE_EXTENSIONS):
            return href
    return None


def cover(path):
    """Octets de la couverture d'un .epub, ou None s'il n'en déclare pas."""
    with open_zip(path) as archive:
        root, opf_path = _opf_root(archive)
        href = cover_href(root)
        if href is None:
            return None
        name = posixpath.normpath(posixpath.join(posixpath.dirname(opf_path), unquote(href)))
        if name not in archive.namelist():
            return None
        return read_member(archive, name, "couverture")
