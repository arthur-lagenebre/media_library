"""ComicInfo.xml : la fiche que les lecteurs de bandes dessinées (Komga, Kavita, ComicRack...) lisent dans un .cbz.

Ses noms de champs - Series, Number, Writer, Publisher... - servent aussi de vocabulaire commun aux .epub (voir epub.py) : une fiche de livre est un dictionnaire de ces noms, quelle que soit son origine.

Tout est pur : on analyse des octets, on ne lit aucun fichier.
"""

import re
from xml.etree import ElementTree

NAME = "ComicInfo.xml"
INT_FIELDS = ("Year", "Month", "Day", "Count", "PageCount")
PEOPLE = ("Writer", "Penciller", "Inker", "Colorist", "Letterer", "CoverArtist")

NUMBER_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*$")


def parse(data):
    """Dictionnaire des champs renseignés ; les nombres sont des entiers, sauf Number qui reste un texte ("0.5", "HS").

    'FrontCover' est le rang de la page marquée comme couverture, quand il y en a une. Un XML illisible ou qui n'est pas un ComicInfo donne {} : un livre sans fiche, pas une erreur.
    """
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return {}
    if root.tag.rsplit("}", 1)[-1] != "ComicInfo":
        return {}
    info = {}
    for child in root:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "Pages":
            for page in child:
                if page.get("Type") == "FrontCover" and (page.get("Image") or "").isdigit():
                    info["FrontCover"] = int(page.get("Image"))
                    break
            continue
        text = (child.text or "").strip()
        if not text:
            continue
        if tag in INT_FIELDS:
            if text.isdigit():
                info[tag] = int(text)
        else:
            info[tag] = text
    return info


def number_value(text):
    """Valeur numérique d'un Number ("28" -> 28.0, "0,5" -> 0.5), ou None pour ce qui n'est pas un nombre ("HS", "Intégrale")."""
    found = NUMBER_RE.match(text or "")
    return float(found.group(1).replace(",", ".")) if found else None
