"""L'état visé pour un épisode : les tags Matroska qu'il doit porter et ce que son .mkv devrait contenir.

Tout est pur : une saison et un épisode TMDB en entrée, du XML de tags et une cible en sortie. TargetTypeValue : 70 = COLLECTION (série), 60 = SEASON, 50 = ÉPISODE.
"""

from . import mkv


def build_tags_xml(season, ep, series_name, max_actors=20):
    blocks = []
    if series_name:
        blocks.append(mkv.tag_block(70, [mkv.simple("TITLE", series_name)]))

    blocks.append(mkv.tag_block(60, [
        mkv.simple("PART_NUMBER", season.get("season_number", "")),
        mkv.simple("TITLE", season.get("name", "")),
        mkv.simple("TOTAL_PARTS", len(season.get("episodes", []))),
    ]))

    lines = [mkv.simple("TITLE", ep.get("name", "")), mkv.simple("PART_NUMBER", ep.get("episode_number", ""))]
    if ep.get("overview"):
        lines.append(mkv.simple("SYNOPSIS", ep["overview"]))
        lines.append(mkv.simple("SUMMARY", ep["overview"]))
    if ep.get("air_date"):
        lines.append(mkv.simple("DATE_RELEASED", ep["air_date"]))
    lines += mkv.credits_lines(ep.get("crew", []), ep.get("guest_stars", []), max_actors)
    if ep.get("vote_average"):
        lines.append(mkv.simple("COMMENT", f"TMDB {round(ep['vote_average'], 1)}/10 ({ep.get('vote_count', 0)} votes)"))
    blocks.append(mkv.tag_block(50, lines))
    return mkv.tags_document(blocks)


def episode_target(season, ep, series_name, opts):
    """Ce que le .mkv de cet épisode devrait contenir."""
    return mkv.Target(
        title=ep.get("name", ""),
        date=ep.get("air_date"),
        tags_xml=build_tags_xml(season, ep, series_name),
        poster=(ep.get("still_path") or season.get("poster_path")) if opts.cover else None,
    )
