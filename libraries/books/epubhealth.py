"""Contrôler un .epub sans outil externe : l'archive, le conteneur, l'.opf et le XHTML.

Un .epub est un zip qui obéit à quelques règles que beaucoup de lecteurs font semblant d'ignorer, et qu'un seul refuse un jour : "mimetype" en première entrée, stocké sans compression, sans champ "extra" ; un conteneur qui désigne un .opf ; un manifeste dont chaque fichier existe ; un ordre de lecture (spine) qui ne cite que le manifeste ; du XHTML bien formé. `audit` les vérifie toutes, en bibliothèque standard.

Ce n'est pas EpubCheck : ni schéma EPUB 3, ni CSS, ni accessibilité. Seulement ce qui fait qu'un livre s'ouvre ou ne s'ouvre pas, et ce qu'un script peut réparer sans rien perdre (`Defect.fixable`, voir epubclean.py).

Rien n'est écrit.
"""

import posixpath
import re
import zipfile
from collections import Counter
from html.entities import name2codepoint
from typing import NamedTuple
from urllib.parse import unquote
from xml.etree import ElementTree

from . import epub
from .archive import BookError, ZIP_ERRORS, is_parasite, open_zip

MIMETYPE = b"application/epub+zip"
CONTAINER_PATH = "META-INF/container.xml"
XML_TYPES = ("application/xhtml+xml", "application/x-dtbncx+xml")
# Les éléments Dublin Core que l'on peut retirer quand ils sont vides : ni le titre, ni la langue, ni l'identifiant, que le livre doit avoir.
OPTIONAL_DC = ("contributor", "coverage", "creator", "date", "description", "format", "publisher", "relation", "rights", "source", "subject", "type")
XML_ENTITIES = {"amp", "lt", "gt", "quot", "apos"}
ENTITY_RE = re.compile(rb"&([A-Za-z][A-Za-z0-9]*);")
MAX_LISTED = 3          # noms cités dans un message qui en regroupe beaucoup


class Defect(NamedTuple):
    """Ce qui cloche dans un livre, et si epubclean.py sait le réparer sans rien perdre."""
    message: str
    fixable: bool = False


def _text(element):
    return (element.text or "").strip()


def _child(element, name):
    """Le fils OPF `name`, avec ou sans espace de noms (certains .opf l'oublient)."""
    found = element.find(epub.OPF + name)
    return found if found is not None else element.find(name)


def _metas(metadata):
    return metadata.findall(f"{epub.OPF}meta") + metadata.findall("meta")


def is_external(href):
    return "://" in href or href.startswith("data:")


def entry_name(opf_path, href):
    """Nom, dans l'archive, du fichier que l'.opf désigne par `href` : relatif à l'.opf, '%20' décodé, sans ancre."""
    return posixpath.normpath(posixpath.join(posixpath.dirname(opf_path), unquote(href.split("#", 1)[0])))


def manifest_items(root):
    manifest = _child(root, "manifest")
    return list(manifest) if manifest is not None else []


def listed_entries(root, opf_path):
    """Les noms d'entrées que le manifeste déclare : ce qu'un nettoyage ne doit jamais retirer."""
    return {entry_name(opf_path, i.get("href")) for i in manifest_items(root) if i.get("href") and not is_external(i.get("href"))}


# --------------------------------------------------------------------------
# L'archive
# --------------------------------------------------------------------------
def mimetype_problems(archive):
    """[Defect] du fichier "mimetype" : absent, mal placé, compressé, avec un champ "extra", au mauvais contenu. Réparables dès que le livre a son conteneur."""
    repairable = CONTAINER_PATH in archive.namelist()
    infos = archive.infolist()
    entries = [i for i in infos if i.filename == "mimetype"]
    if not entries:
        return [Defect("mimetype absent", repairable)]
    info, problems = entries[-1], []
    if infos[0].filename != "mimetype":
        problems.append("mimetype n'est pas la première entrée de l'archive")
    if info.compress_type != zipfile.ZIP_STORED:
        problems.append("mimetype est compressé (il doit être stocké tel quel)")
    if info.extra:
        problems.append("mimetype porte un champ « extra » (interdit)")
    try:
        content = archive.read(info)
    except ZIP_ERRORS as e:
        return [Defect(f"mimetype illisible : {e}")]
    if content != MIMETYPE:
        problems.append(f"mimetype contient {content[:40]!r} au lieu de application/epub+zip")
    return [Defect(p, repairable) for p in problems]


def duplicates(archive):
    """Les noms d'entrées présents plus d'une fois (un lecteur lit la première, un autre la dernière), dans l'ordre de l'archive."""
    counts = Counter(i.filename for i in archive.infolist())
    return [name for name, count in counts.items() if count > 1]


def residues(archive, listed=None):
    """Les entrées qui ne sont que des résidus (__MACOSX, .DS_Store...), hors celles que le manifeste déclare. `listed` : les noms déclarés, lus dans l'.opf quand on ne les donne pas."""
    if listed is None:
        try:
            listed = listed_entries(*epub.opf_root(archive))
        except BookError:
            listed = set()
    found = []
    for info in archive.infolist():
        if is_parasite(info.filename) and info.filename not in listed and info.filename not in found:
            found.append(info.filename)
    return found


def cited(names):
    shown = ", ".join(names[:MAX_LISTED])
    return shown + (", …" if len(names) > MAX_LISTED else "")


# --------------------------------------------------------------------------
# L'.opf
# --------------------------------------------------------------------------
def xml_problem(data):
    """Pourquoi ce document n'est pas du XML bien formé, ou "".

    Un XHTML qui porte un DOCTYPE peut employer les entités nommées de HTML (&nbsp;, &eacute;...) que sa DTD définit : l'analyseur n'ouvre pas la DTD, ces entités sont donc remplacées avant lui par leur code, faute de quoi tout livre en XHTML 1.1 passerait pour cassé.
    """
    if b"<!DOCTYPE" in data[:4096]:
        data = ENTITY_RE.sub(_html_entity, data)
    try:
        ElementTree.fromstring(data)
    except (ElementTree.ParseError, ValueError, LookupError) as e:
        return str(e)
    return ""


def _html_entity(match):
    name = match.group(1).decode("ascii")
    code = None if name in XML_ENTITIES else name2codepoint.get(name)
    return match.group(0) if code is None else b"&#%d;" % code


def _identifier_defects(root, metadata):
    identifiers = metadata.findall(epub.DC + "identifier")
    unique = root.get("unique-identifier")
    if not any(_text(e) for e in identifiers):
        return [Defect("dc:identifier absent ou vide")]
    if not unique:
        return [Defect("<package> sans unique-identifier")]
    if not any(e.get("id") == unique and _text(e) for e in identifiers):
        return [Defect(f"unique-identifier « {unique} » ne désigne aucun dc:identifier")]
    return []


def _metadata_defects(root, metadata, version):
    defects = []
    for tag in ("title", "language"):
        if not any(_text(e) for e in metadata.findall(epub.DC + tag)):
            defects.append(Defect(f"dc:{tag} absent ou vide"))
    defects += _identifier_defects(root, metadata)
    if version.startswith("3") and not any(m.get("property") == "dcterms:modified" and _text(m) for m in _metas(metadata)):
        defects.append(Defect("EPUB 3 sans dcterms:modified"))
    for element in metadata.findall(epub.DC + "date"):
        found = epub.DATE_RE.match(_text(element))
        if found and int(found.group(1)) < epub.MIN_YEAR:
            defects.append(Defect(f"date inconnue ({_text(element)}) : le « zéro » de Calibre", True))
    for tag in OPTIONAL_DC:
        if any(not _text(e) and len(e) == 0 for e in metadata.findall(epub.DC + tag)):
            defects.append(Defect(f"élément vide : dc:{tag}", True))
    return defects


def _manifest_defects(archive, opf_path, items):
    defects = []
    names = set(archive.namelist())
    if not items:
        defects.append(Defect("manifeste vide ou absent"))
    for ident, count in Counter(i.get("id") for i in items).items():
        if count > 1:
            defects.append(Defect(f"id en double dans le manifeste : {ident}"))
    for item in items:
        href = item.get("href") or ""
        if not href:
            defects.append(Defect("item du manifeste sans href"))
        elif not is_external(href):
            name = entry_name(opf_path, href)
            if name not in names:
                defects.append(Defect(f"fichier du manifeste absent de l'archive : {href}"))
            elif item.get("media-type") in XML_TYPES:
                defects += _xml_defect(archive, name, href)
    return defects


def _xml_defect(archive, name, href):
    try:
        data = archive.read(name)
    except ZIP_ERRORS as e:
        return [Defect(f"{href} illisible : {e}")]
    problem = xml_problem(data)
    return [Defect(f"XML mal formé : {href} ({problem})")] if problem else []


def _spine_defects(root, items, version):
    ids = {i.get("id") for i in items}
    spine = _child(root, "spine")
    refs = [r.get("idref") for r in spine] if spine is not None else []
    defects = [] if refs else [Defect("spine vide ou absent")]
    defects += [Defect(f"spine : « {ref} » n'est pas dans le manifeste") for ref in refs if ref not in ids]
    if version.startswith("3") and not any("nav" in (i.get("properties") or "").split() for i in items):
        defects.append(Defect("EPUB 3 sans document de navigation (properties=\"nav\")"))
    if version.startswith("2") and spine is not None:
        toc = spine.get("toc")
        if not toc:
            defects.append(Defect("EPUB 2 : le spine n'a pas d'attribut toc"))
        elif toc not in ids:
            defects.append(Defect(f"EPUB 2 : toc « {toc} » n'est pas dans le manifeste"))
    return defects


def package_defects(archive, root, opf_path):
    """[Defect] de l'.opf : fiche, manifeste, ordre de lecture, XHTML."""
    version = root.get("version") or ""
    defects = []
    if not version.startswith(("2", "3")):
        defects.append(Defect(f"version EPUB inconnue : « {version} »"))
    metadata = _child(root, "metadata")
    defects += _metadata_defects(root, metadata, version) if metadata is not None else [Defect("l'.opf n'a pas de <metadata>")]
    items = manifest_items(root)
    return defects + _manifest_defects(archive, opf_path, items) + _spine_defects(root, items, version)


# --------------------------------------------------------------------------
# Le livre
# --------------------------------------------------------------------------
def _archive_defects(archive):
    try:
        bad = archive.testzip()
    except ZIP_ERRORS as e:
        return [Defect(f"contenu de l'archive illisible : {e}")]
    defects = [Defect(f"entrée corrompue (CRC) : {bad}")] if bad else []
    defects += mimetype_problems(archive)
    defects += [Defect(f"entrée en double : {name}", True) for name in duplicates(archive)]
    defects += [Defect(f"nom d'entrée dangereux : {n}") for n in archive.namelist() if n.startswith("/") or ".." in n.split("/")]
    return defects


def audit(path):
    """[Defect] du livre, vide quand il est sain. Une archive illisible est un défaut parmi les autres : on ne lève pas."""
    try:
        archive = open_zip(path)
    except BookError as e:
        return [Defect(str(e))]
    with archive:
        defects = _archive_defects(archive)
        try:
            root, opf_path = epub.opf_root(archive)
        except BookError as e:
            return defects + [Defect(str(e))]
        defects += package_defects(archive, root, opf_path)
        found = residues(archive, listed_entries(root, opf_path))
        if found:
            defects.append(Defect(f"résidus à retirer ({len(found)}) : {cited(found)}", True))
        return defects
