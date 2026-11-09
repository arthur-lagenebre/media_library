"""L'état visé pour un film : les tags Matroska qu'il doit porter et ce que son .mkv devrait contenir.

Tout est pur : un film TMDB (et l'avis de l'utilisateur sur le titre de sa collection) en entrée, du XML de tags et une cible en sortie. TargetTypeValue 50 = film, 70 = collection/saga.
"""

import re

from . import mkv


SAGA_SUFFIX_RE = re.compile(r"\s+-\s+saga\s*$", re.IGNORECASE)
COLLECTION_SUFFIX_RE = re.compile(r"(?:\s+-)?\s+collection\s*$", re.IGNORECASE)


def collection_title(name):
    """Le nom de la collection sans le " - Saga" que TMDB ajoute en français ("Iron Man - Saga" -> "Iron Man").

    Ce suffixe est un invariant : il part toujours. Le " Collection" anglais, lui, peut faire partie du nom ("The Criterion Collection") : voir `collection_proposal`, qui ne le retire qu'avec l'accord de l'utilisateur.
    """
    name = (name or "").strip()
    return SAGA_SUFFIX_RE.sub("", name).strip() or name


def collection_proposal(name):
    """Le nom sans son " Collection" final, ou None quand il n'y a rien à proposer."""
    name = collection_title(name)
    proposal = COLLECTION_SUFFIX_RE.sub("", name).strip()
    return proposal if proposal and proposal != name else None


def collection_choices(name, folder=""):
    """([(titre, origine), ...], indice proposé par défaut) : les titres entre lesquels choisir pour cette collection.

    Le nom TMDB sans son " - Saga" ; le même sans son " Collection" final, qui est la proposition par défaut quand il y en a une ; le nom du dossier de saga sur le disque, quand il en diffère. Une seule entrée = rien à choisir.
    """
    choices = [(collection_title(name), "TMDB")]
    proposal = collection_proposal(name)
    if proposal:
        choices.append((proposal, "sans \" Collection\""))
    if folder.strip():
        choices.append((folder.strip(), "nom de ton dossier de saga"))
    seen, unique = set(), []
    for title, origin in choices:
        if title not in seen:
            seen.add(title)
            unique.append((title, origin))
    default = next((i for i, (title, _) in enumerate(unique) if title == proposal), 0)
    return unique, default


def build_movie_tags_xml(movie):
    credits = movie.get("credits", {})
    blocks = []

    # `_collection_title` : le titre arrêté avec l'utilisateur (voir `settle_collection`) ; à défaut, seul l'invariant " - Saga" est appliqué.
    collection = movie.get("_collection_title") or collection_title((movie.get("belongs_to_collection") or {}).get("name"))
    if collection:
        lines = [mkv.simple("TITLE", collection)]
        if movie.get("_order"):                       # ordre de la saga (préfixe "{n} - ")
            lines.append(mkv.simple("PART_NUMBER", movie["_order"]))
        blocks.append(mkv.tag_block(70, lines))

    lines = [mkv.simple("TITLE", movie.get("title", ""))]
    if movie.get("id"):
        # L'association elle-même, inscrite dans le film : au passage suivant, plus rien n'est cherché, donc plus rien ne peut se tromper.
        lines.append(mkv.simple(mkv.TMDB_TAG, mkv.tmdb_value(movie["id"])))
    if movie.get("overview"):
        lines.append(mkv.simple("SYNOPSIS", movie["overview"]))
        lines.append(mkv.simple("SUMMARY", movie["overview"]))
    if movie.get("release_date"):
        lines.append(mkv.simple("DATE_RELEASED", movie["release_date"]))
    lines += mkv.credits_lines(credits.get("crew", []), credits.get("cast", []))
    genres = ", ".join(g.get("name", "") for g in movie.get("genres", []))
    if genres:
        lines.append(mkv.simple("GENRE", genres))
    blocks.append(mkv.tag_block(50, lines))
    return mkv.tags_document(blocks)


def movie_target(movie, opts):
    """Ce que le .mkv de ce film devrait contenir."""
    return mkv.Target(title=movie.get("title", ""), date=movie.get("release_date"), tags_xml=build_movie_tags_xml(movie), poster=movie.get("poster_path") if opts.cover else None,)
