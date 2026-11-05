"""Nettoyer un .epub : retirer ses résidus, réparer son archive, assainir la fiche de son .opf.

Trois familles de corrections, chacune sûre parce qu'elle ne touche à aucun contenu du livre :
  residues   les entrées qui ne sont que des résidus (__MACOSX/, .DS_Store, Thumbs.db, la position de lecture de Calibre...) et que le manifeste ne déclare pas
  archive    "mimetype" remis en première entrée, stocké, au contenu exact ; les entrées en double ne gardent que la dernière, celle que lit un lecteur de zip
  metadata   dans l'.opf, la date « zéro » de Calibre (0101-01-01) et les éléments Dublin Core vides ; ni le titre, ni la langue, ni l'identifiant ne sont touchés, ni les champs "calibre:" que les étagères lisent (série, numéro)

Le livre est réécrit sous un nom provisoire, contrôlé, puis échangé contre l'original, qui reste à côté en ".bak" tant qu'on ne demande pas de le supprimer : `plan` dit ce qui changera, `apply` le fait, et refuse (BookError) tout résultat qu'il n'a pas pu prouver identique au reste près.
"""

import re
import zipfile
from typing import NamedTuple

from ..common.tools import partial_path
from . import epub, epubhealth
from .archive import BookError, open_zip, read_member

FIXES = ("residues", "archive", "metadata")
FICHE_DATE_FIELDS = ("Year", "Month", "Day")      # la fiche lue peut gagner une date quand le « zéro » qui masquait la vraie disparaît

DC_NAMESPACE = rb"http://purl\.org/dc/elements/1\.1/"
DC_PREFIX_RE = re.compile(rb"xmlns:([\w.\-]+)\s*=\s*[\"']" + DC_NAMESPACE + rb"[\"']")
ENCODING_RE = re.compile(rb"^(?:\xef\xbb\xbf)?\s*<\?xml[^>]*?encoding\s*=\s*[\"']([\w.\-]+)[\"']")


class Plan(NamedTuple):
    """Ce qu'un nettoyage ferait à un livre."""
    residues: tuple = ()        # noms d'entrées à retirer
    archive: tuple = ()         # ce qui se répare dans l'archive, en phrases
    metadata: tuple = ()        # ce qui se corrige dans l'.opf, en phrases
    opf_path: str = ""          # où est l'.opf dans l'archive

    @property
    def empty(self):
        return not (self.residues or self.archive or self.metadata)

    def lines(self):
        """Le plan en phrases, une par correction."""
        found = []
        if self.residues:
            found.append(f"retirer {len(self.residues)} résidu(s) : {epubhealth.cited(list(self.residues))}")
        found += list(self.archive)
        found += [f"{self.opf_path} : {note}" for note in self.metadata]
        return found


def backup_path(path):
    """Où l'original se met de côté : `Livre.epub.bak`, ou `.bak2`, `.bak3`... Jamais par-dessus une sauvegarde qui existe."""
    candidate = path.with_name(path.name + ".bak")
    number = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.bak{number}")
        number += 1
    return candidate


# --------------------------------------------------------------------------
# L'.opf, réécrit comme du texte
# --------------------------------------------------------------------------
# Les éléments retirés le sont à l'identique du reste : réécrire l'arbre XML changerait les préfixes, l'ordre des attributs et la déclaration, et rendrait la fiche illisible pour qui compare octet à octet. Le texte est donc modifié en place, et le résultat est reparsé par l'appelant.
def fix_opf(data):
    """(octets de l'.opf corrigé, [ce qui a été corrigé]). Octets identiques et liste vide quand il n'y a rien à faire, ou quand le fichier ne se laisse pas lire sans risque (encodage inconnu, préfixe Dublin Core introuvable)."""
    declared = ENCODING_RE.match(data)
    encoding = declared.group(1).decode("ascii") if declared else "utf-8"
    prefix = DC_PREFIX_RE.search(data)
    if prefix is None:
        return data, []
    try:
        text = data.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return data, []
    tag = re.escape(prefix.group(1).decode("ascii"))
    notes = []

    placeholder = re.compile(rf"[ \t]*<{tag}:date(?:\s[^<>]*)?>\s*0\d{{3}}(?:-\d{{2}}){{0,2}}[^<]*</{tag}:date>[ \t]*(?:\r?\n)?")
    text, count = placeholder.subn("", text)
    if count:
        notes.append(f"{count} date inconnue (« zéro » de Calibre) retirée(s)")

    names = "|".join(epubhealth.OPTIONAL_DC)
    empty = re.compile(rf"[ \t]*<{tag}:(?P<name>{names})(?:\s[^<>]*)?(?:/>|>\s*</{tag}:(?P=name)>)[ \t]*(?:\r?\n)?")
    removed = [m.group("name") for m in empty.finditer(text)]
    if removed:
        text = empty.sub("", text)
        notes.append("élément(s) vide(s) retiré(s) : " + ", ".join(f"dc:{name}" for name in dict.fromkeys(removed)))
    return (text.encode(encoding), notes) if notes else (data, [])


# --------------------------------------------------------------------------
# Le plan
# --------------------------------------------------------------------------
def archive_repairs(archive):
    """Ce que le nettoyage de l'archive réparerait, en phrases."""
    found = [d.message for d in epubhealth.mimetype_problems(archive) if d.fixable]
    found += [f"entrée en double (la dernière est gardée) : {name}" for name in epubhealth.duplicates(archive)]
    return tuple(found)


def plan(path, fixes=FIXES):
    """Le Plan du livre pour ces corrections. BookError quand l'archive est illisible : on n'y touche pas."""
    with open_zip(path) as archive:
        try:
            root, opf_path = epub.opf_root(archive)
        except BookError:
            root, opf_path = None, ""
        residues = ()
        if "residues" in fixes:
            listed = epubhealth.listed_entries(root, opf_path) if root is not None else set()
            residues = tuple(epubhealth.residues(archive, listed))
        repairs = archive_repairs(archive) if "archive" in fixes else ()
        notes = ()
        if "metadata" in fixes and root is not None:
            notes = tuple(fix_opf(read_member(archive, opf_path, ".opf"))[1])
    return Plan(residues, repairs, notes, opf_path)


# --------------------------------------------------------------------------
# La réécriture
# --------------------------------------------------------------------------
def _copy_entry(out, info, data):
    """L'entrée recopiée telle quelle - nom, date, droits, compression - sans le champ "extra" ni le commentaire."""
    copy = zipfile.ZipInfo(info.filename, info.date_time)
    copy.external_attr = info.external_attr
    copy.compress_type = info.compress_type if info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) else zipfile.ZIP_DEFLATED
    out.writestr(copy, data)


def rewrite(path, destination, wanted):
    """Écrit dans `destination` le livre `path` corrigé selon le Plan `wanted`. Le livre d'origine n'est pas touché."""
    with open_zip(path) as source, zipfile.ZipFile(destination, "w") as out:
        infos = source.infolist()
        names = [i.filename for i in infos]
        last = {name: n for n, name in enumerate(names)}
        dropped = set(wanted.residues)
        repair = bool(wanted.archive)
        if repair and ("mimetype" in names or epubhealth.CONTAINER_PATH in names):
            old = next((i for i in infos if i.filename == "mimetype"), None)
            first = zipfile.ZipInfo("mimetype", old.date_time if old else (1980, 1, 1, 0, 0, 0))
            first.compress_type = zipfile.ZIP_STORED
            out.writestr(first, epubhealth.MIMETYPE)
        for n, info in enumerate(infos):
            name = info.filename
            if name in dropped or (repair and (name == "mimetype" or last[name] != n)):
                continue
            data = read_member(source, info, name)
            if name == wanted.opf_path and wanted.metadata:
                data = fix_opf(data)[0]
            _copy_entry(out, info, data)


def _fiche(archive):
    """La fiche lue dans l'.opf, sans les champs de date."""
    info = epub.parse_opf(epub.opf_root(archive)[0])
    return {k: v for k, v in info.items() if k not in FICHE_DATE_FIELDS}


def verify_rewrite(path, rewritten, wanted):
    """BookError sauf si `rewritten` est `path` moins exactement ce que `wanted` annonce : mêmes entrées à ce près, mêmes octets partout ailleurs, même fiche, et aucun défaut qu'il n'avait pas."""
    with open_zip(path) as before, open_zip(rewritten) as after:
        expected = set(before.namelist()) - set(wanted.residues)
        if wanted.archive:
            expected.add("mimetype")                      # le seul fichier que la réparation de l'archive a le droit d'ajouter
        if set(after.namelist()) != expected:
            raise BookError("le contenu réécrit n'est pas celui qui était prévu")
        for name in sorted(expected):
            if name == "mimetype" and wanted.archive:
                continue                                  # contrôlé par l'audit : c'est lui qu'on répare
            if name == wanted.opf_path and wanted.metadata:
                continue
            if read_member(before, name, name) != read_member(after, name, name):
                raise BookError(f"{name} a changé à la réécriture")
        if wanted.metadata and _fiche(before) != _fiche(after):
            raise BookError("la fiche de l'.opf a changé à la réécriture")
    known = {d.message for d in epubhealth.audit(path)}
    appeared = [d.message for d in epubhealth.audit(rewritten) if d.message not in known]
    if appeared:
        raise BookError(f"la réécriture introduit un défaut : {appeared[0]}")


def apply(path, wanted, keep_backup=True):
    """Réécrit le livre selon le Plan. Retourne le chemin de la sauvegarde de l'original, ou None s'il n'en reste pas.

    L'original ne bouge qu'une fois le résultat contrôlé : BookError et rien n'a changé si le contrôle refuse, OSError si l'écriture ou l'échange échoue (l'original est alors remis à sa place).
    """
    partial = partial_path(path)
    try:
        rewrite(path, partial, wanted)
        verify_rewrite(path, partial, wanted)
        backup = backup_path(path)
        path.rename(backup)
        try:
            partial.rename(path)
        except OSError:
            backup.rename(path)
            raise
    finally:
        try:
            partial.unlink()
        except OSError:
            pass
    if keep_backup:
        return backup
    try:
        backup.unlink()
    except OSError:
        return backup
    return None
