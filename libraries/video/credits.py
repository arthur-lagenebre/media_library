"""--credits-only : ne remettre à jour que le casting (DIRECTOR, WRITTEN_BY, ACTOR et l'id TMDB de chacun) d'un fichier déjà étiqueté.

Les tags sont relus tels que mkvextract les rend et réécrits à l'identique, les personnes exceptées : titre, synopsis, identifiant TMDB, statistiques de pistes, noms de pistes, drapeaux, date et jaquette ne bougent pas. Sert aux films comme aux épisodes : la fiche TMDB change, le reste du fichier non.
"""

from xml.etree import ElementTree

from . import mkv

PERSON_TAGS = ("DIRECTOR", "WRITTEN_BY", "ACTOR")


def credit_tags(tags):
    """Les tuples de personnes (niveau 50) d'un ensemble rendu par parse_tags : DIRECTOR, WRITTEN_BY, ACTOR et leurs fils (ACTOR/TMDB)."""
    return {tag for tag in tags or () if tag[0] == 50 and tag[1].split("/")[0] in PERSON_TAGS}


def _level_50_blocks(root):
    """Les blocs <Tag> de niveau film ou épisode : ni les statistiques de piste, ni les autres niveaux. Un bloc sans TargetTypeValue vaut 50, comme dans parse_tags."""
    blocks = []
    for bloc in root.findall("Tag"):
        targets = bloc.find("Targets")
        if targets is not None and targets.find("TrackUID") is not None:
            continue
        level = targets.find("TargetTypeValue") if targets is not None else None
        if (int(level.text) if (level is not None and level.text) else 50) == 50:
            blocks.append(bloc)
    return blocks


def recredit(xml, wanted_xml):
    """Le XML `xml` dont les personnes sont remplacées par celles de `wanted_xml`, ou None s'il ne se lit pas ou n'a aucun bloc de niveau 50.

    Tout le reste est recopié tel que mkvextract l'a rendu. Les personnes prennent la place de la première qui s'y trouvait, à défaut la fin du bloc.
    """
    try:
        root = ElementTree.fromstring(xml.lstrip("﻿"))
        wanted = ElementTree.fromstring(wanted_xml.lstrip("﻿"))
    except (ElementTree.ParseError, AttributeError):
        return None
    blocks = _level_50_blocks(root)
    if not blocks:
        return None
    new = [s for bloc in _level_50_blocks(wanted) for s in bloc.findall("Simple") if s.findtext("Name") in PERSON_TAGS]
    place = None
    for bloc in blocks:
        for simple in bloc.findall("Simple"):
            if simple.findtext("Name") in PERSON_TAGS:
                if place is None:
                    place = (bloc, list(bloc).index(simple))
                bloc.remove(simple)
    bloc, index = place or (blocks[0], len(blocks[0]))
    for offset, simple in enumerate(new):
        bloc.insert(index + offset, simple)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ElementTree.tostring(root, encoding="unicode")


def process(path, tags, target, verify, apply, indent="      "):
    """Compare le casting du fichier à celui de la fiche et, sous `apply`, le réécrit seul. Retourne (non_conforme, echec_ecriture), 0 ou 1 chacun.

    Un fichier sans tag TITLE n'a pas été étiqueté : le laisser à moitié étiqueté serait pire que de ne rien faire, il est signalé. Une fiche sans aucune personne ne vide pas un casting déjà écrit : rien n'est perdu.
    """
    if not any(level == 50 and name == "TITLE" for level, name, _ in tags or ()):
        print(f"{indent}[SANS TAGS] pas encore étiqueté : relance sans --credits-only")
        return 1, 0
    current, wanted = credit_tags(tags), credit_tags(mkv.parse_tags(target.tags_xml))
    if not wanted and current:
        print(f"{indent}[SANS CASTING] la fiche TMDB n'en donne aucun : casting laissé tel quel")
        return 0, 0
    missing, extra = wanted - current, current - wanted
    if not (missing or extra):
        print(f"{indent}[OK] casting déjà conforme")
        return 0, 0
    detail = f"{len(missing)} manquant(s), {len(extra)} en trop"
    print(f"{indent}[DIFF] casting : {detail}" if verify else f"{indent}casting : {detail}")
    if verify:
        return 1, 0
    if not apply:
        return 0, 0
    xml = recredit(mkv.read_tags_xml(path), target.tags_xml)
    if xml is None:
        print(f"{indent}[ÉCHEC] tags illisibles : rien n'a été modifié")
        return 0, 1
    code, msg = mkv.write_tags(path, xml)
    print(f"{indent}[{'OK' if code == 0 else 'ÉCHEC'}]" + (f" {msg}" if code else ""))
    return 0, (1 if code else 0)
