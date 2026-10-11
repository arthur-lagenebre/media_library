"""Pages HTML de la médiathèque musicale : un sommaire de tous les albums, et une fiche par album.

Le sommaire est un mur de pochettes groupé par artiste - ceux qui ont plusieurs albums ont leur section, les autres se rangent ensemble à la fin -, avec une zone de recherche, un filtre de genre et un index A-Z, comme celui des films. Chaque pochette mène à la fiche de son album : pochette, artiste, année, label, genres, pistes avec leur durée, et celles qui manquent d'après les tags.

Comme les fiches des films et des livres, chaque page est un fichier unique - les pochettes y sont encodées - et la page précédente sert de cache : régénérer ne rouvre que les pochettes nouvelles.

Tout est pur : ni réseau ni disque, l'appelant fournit les pochettes déjà réduites.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

from libraries.common import favicon, layout
from libraries.common.filenames import safe_name

from . import library
from .musicbrainz import release_url

DIR = "Albums"                 # le dossier des fiches, rangé À CÔTÉ du sommaire

# Retrouve les pochettes déjà encodées dans une page précédente.
EMBEDDED_RE = re.compile(r"<img data-img='([^']+)' src='(data:[^']+)'")


def esc(value):
    # L'apostrophe aussi : les attributs sont entre apostrophes, et un titre qui dit "l'Oeil" fermerait l'attribut en plein milieu.
    return escape(str(value or ""), {"'": "&#39;"})


def page_name(release):
    """Nom du fichier de la fiche : l'artiste et le titre, lisibles dans une liste de fichiers, et l'identifiant du dossier pour que deux éditions du même album n'en partagent pas une."""
    return f"{safe_name(f'{release.artist} - {release.title}')[:70] or 'album'}-{release.id}.html"


def href(release):
    """Lien, relatif au sommaire, vers la fiche d'un album."""
    return f"{DIR}/{quote(page_name(release))}"


def anchor(release):
    """Ancre de la pochette d'un album dans le sommaire : le retour depuis sa fiche y ramène."""
    return f"a{release.id}"


def read_embedded(page_path):
    """{clé: data-URI} des pochettes déjà présentes dans une page existante."""
    try:
        html = Path(page_path).read_text(encoding="utf-8")
    except OSError:
        return {}
    return dict(EMBEDDED_RE.findall(html))


def _cover(key, uri, name):
    """La pochette, ou à défaut un monogramme dans la couleur du titre : un carré vide ressemble à une image qui n'a pas chargé."""
    if uri:
        return f"<img data-img='{esc(key)}' src='{uri}' alt='' decoding='async' loading='lazy'>"
    return (f"<div class='noimg mono' style='background:{favicon.color(name)}'>"
            f"{esc(favicon.initials(name))}</div>")


def tracks_label(n):
    return f"{n} piste{'s' if n != 1 else ''}"


def clock(seconds):
    """'3:42', ou '1:02:03' au-delà d'une heure ; rien sans durée."""
    if not seconds:
        return ""
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def length(seconds):
    """'48 min', '1 h 12 min' : la durée d'un album ou d'une médiathèque, sans les secondes."""
    minutes = int(round(seconds / 60))
    if minutes < 60:
        return f"{minutes} min" if minutes else ""
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min" if minutes else f"{hours} h"


def _count_label(release):
    got = release.progress()
    return f"{got[0]}/{got[1]} pistes" if got else tracks_label(len(release.tracks))


def _search_text(release):
    return " ".join([release.title, release.artist, release.label, *release.genres])


# ----------------------------------------------------------------------------
# Feuille de style commune
# ----------------------------------------------------------------------------
CSS_BASE = (
    "body{font:16px/1.5 system-ui,sans-serif;margin:0;background:#14151a;color:#e8e8ea}"
    "h1{margin:0 0 4px}"
    "[hidden]{display:none!important}"
    "h2{font-size:17px;margin:30px 0 14px;padding-bottom:8px;border-bottom:1px solid #21232b}"
    ".cnt{margin-left:9px;font-size:13px;font-weight:400;color:#9aa0aa;font-variant-numeric:tabular-nums}"
    ".al{display:block;color:inherit;text-decoration:none}"
    ".al .aff{position:relative;aspect-ratio:1;border-radius:8px;overflow:hidden;background:#21232b;transition:transform .15s,box-shadow .15s}"
    "a.al:hover .aff,a.al:focus-visible .aff{transform:translateY(-3px);box-shadow:0 0 0 2px #7cc4ff}"
    "a.al:hover .t{color:#7cc4ff}"
    ".al img,.al .noimg{width:100%;height:100%;object-fit:cover;display:block}"
    ".mono{display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:34px}"
    ".al .t{margin-top:8px;font-size:14px;font-weight:600;line-height:1.3;overflow-wrap:anywhere}"
    ".al .a{color:#c7ccd4;font-size:13px;line-height:1.3;overflow-wrap:anywhere}"
    ".al .y{color:#9aa0aa;font-size:13px}"
    ".al .y.warn{color:#ffb86b}"
    ".al.bad .aff{box-shadow:0 0 0 2px #ff9aa6}"
)


# ----------------------------------------------------------------------------
# Sommaire
# ----------------------------------------------------------------------------
def build_index(library_name, sections, covers, pages=()):
    """Rend le sommaire. 'sections' = [(nom, [Release])] (voir library.sections) ; 'covers' = {id d'album: data-URI} ; 'pages' = ids des albums dont la fiche existe (les autres pochettes restent inertes plutôt que de mener à un lien cassé)."""
    blocks = []
    n_albums = n_tracks = 0
    seconds = 0
    artists = set()
    genre_counts = {}
    for name, releases in sections:
        single = name == library.SINGLES            # ses albums se rangent par artiste : c'est eux que l'index A-Z vise, et la pochette dit de qui ils sont
        tiles = []
        for release in releases:
            n_albums += 1
            n_tracks += len(release.tracks)
            seconds += release.duration
            artists.add(layout.fold(release.artist))
            link = f" href='{esc(href(release))}' id='{anchor(release)}'" if release.id in pages else ""
            tag = "a" if link else "div"
            warn = " warn" if release.progress() else ""
            for genre in release.genres:
                genre_counts[genre] = genre_counts.get(genre, 0) + 1
            facts = " · ".join(p for p in (release.year, _count_label(release)) if p)
            letter = f" data-i='{layout.initial(release.artist)}'" if single else ""
            tiles.append(
                f"<{tag} class='al'{link} data-s='{esc(_search_text(release))}'{letter}{layout.genre_attr(release.genres)}>"
                f"<div class='aff'>{_cover(release.key, covers.get(release.id), release.title)}</div>"
                f"<div class='t'>{esc(release.title)}</div>"
                + (f"<div class='a'>{esc(release.artist)}</div>" if single else "")
                + f"<div class='y{warn}'>{esc(facts)}</div>"
                f"</{tag}>")
        letter = "" if single else f" data-i='{layout.initial(name)}'"
        blocks.append(f"<section><h2{letter}>{esc(name)}<span class='cnt'>{len(releases)} album{'s' if len(releases) != 1 else ''}</span></h2>"
                      f"<div class='grid'>{''.join(tiles)}</div></section>")

    summary = " · ".join(p for p in (f"{n_albums} album{'s' if n_albums != 1 else ''}", f"{len(artists)} artiste{'s' if len(artists) != 1 else ''}", tracks_label(n_tracks), length(seconds)) if p)
    return (
        "<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'>"
        + favicon.music_link()
        + layout.BOOT +
        f"<title>{esc(library_name)}</title>"
        "<style>"
        + CSS_BASE +
        ".wrap{max-width:1180px;margin:0 auto;padding:32px}"
        ".sub{color:#9aa0aa}"
        + layout.CSS +
        ".none{color:#9aa0aa;margin-top:30px}"
        # Sept par ligne, comme les films ; sous 900 px, remplissage automatique.
        ".grid{display:grid;gap:18px;grid-template-columns:repeat(7,1fr)}"
        "@media(max-width:900px){.grid{grid-template-columns:repeat(auto-fill,minmax(120px,1fr))}}"
        ".wide .grid{grid-template-columns:repeat(auto-fill,minmax(148px,1fr))}"
        "</style></head><body>"
        + layout.header(
            f"<h1>{esc(library_name)}</h1>"
            f"<div class='sub'>{esc(summary)}</div>"
            "<div class='bar'>"
            "<div class='line'>"
            "<input class='filter' type='search' placeholder='Rechercher un album, un artiste…' aria-label='Rechercher un album ou un artiste'>"
            + layout.genre_select(genre_counts) + "</div>"
            + layout.mode_button() + "</div>"
            + layout.index_nav()) +
        f"{''.join(blocks)}"
        "<p class='none' hidden>Aucun album ne correspond.</p>"
        "<script>"
        "var f=document.querySelector('.filter');"
        "function n(s){return s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase()}"
        "f.oninput=function(){var q=n(f.value.trim()),any=false;"
        "document.querySelectorAll('section').forEach(function(s){var seen=0;"
        "s.querySelectorAll('.al').forEach(function(c){"
        "var ok=(!q||n(c.getAttribute('data-s')).indexOf(q)>=0)&&gok(c);c.hidden=!ok;if(ok)seen++});"
        "s.hidden=!seen;if(seen)any=true});"
        "document.querySelector('.none').hidden=any||!(q||picked())};"
        + layout.genre_script() + layout.mode_script() + layout.index_script() +
        "</script></div></body></html>"
    )


# ----------------------------------------------------------------------------
# Fiche d'un album
# ----------------------------------------------------------------------------
def _facts(release):
    label = " ".join(p for p in (release.label, f"({release.catalog})" if release.catalog else "") if p)
    parts = (release.year, label, tracks_label(len(release.tracks)), length(release.duration), " + ".join(release.formats))
    return " · ".join(p for p in parts if p)


def _row(track, album_artist):
    by = track.info.get("artist") or ""
    shown = f"<div class='by'>{esc(by)}</div>" if by and layout.fold(by) != layout.fold(album_artist) else ""
    bad = f"<div class='err'>illisible : {esc(track.error)}</div>" if track.error else ""
    return (f"<tr><td class='n'>{esc(track.number if track.number is not None else '')}</td>"
            f"<td>{esc(track.title)}{shown}{bad}</td><td class='d'>{esc(clock(track.duration))}</td></tr>")


def _absent(number):
    return f"<tr class='absent'><td class='n'>{number}</td><td>piste manquante</td><td class='d'></td></tr>"


def _disc_table(tracks, lacking, album_artist):
    """Les pistes d'un disque dans l'ordre, les manquantes grisées à leur place."""
    rows = [(t.number if t.number is not None else 10 ** 6 + i, _row(t, album_artist)) for i, t in enumerate(tracks)]
    rows += [(n, _absent(n)) for n in lacking]
    return "<table class='trk'>" + "".join(html for _, html in sorted(rows, key=lambda r: r[0])) + "</table>"


def build_release(release, image, back_href, library_name):
    """Rend la fiche d'un album. 'image' = data-URI de la pochette, ou None ; 'back_href' = lien vers le sommaire."""
    back_href = f"{back_href}#{anchor(release)}"
    gaps = {number: lacking for number, lacking, _ in release.missing()}
    totals = {number: total for number, _, total in release.missing()}
    discs = release.discs
    many = len(discs) > 1 or bool(release.missing_discs())

    gap_lines = "".join(
        f"<div class='gap'>Manque : {esc(('disque ' + str(number) + ' : ') if many else '')}piste{'s' if len(lacking) > 1 else ''} {esc(layout.ranges(lacking))} "
        f"<span>(sur {totals[number]}, d'après les tags)</span></div>" for number, lacking in sorted(gaps.items()))
    absent_discs = release.missing_discs()
    if absent_discs:
        gap_lines += (f"<div class='gap'>Manque : disque{'s' if len(absent_discs) > 1 else ''} {esc(layout.ranges(absent_discs))} "
                      "<span>(d'après les tags)</span></div>")

    tables = "".join(
        (f"<h2>Disque {number}<span class='cnt'>{tracks_label(len(tracks))}</span></h2>" if many else "")
        + _disc_table(tracks, gaps.get(number, []), release.artist)
        for number, tracks in discs)
    mb = (f"<div class='links'><a class='mb' href='{esc(release_url(release.mbid))}' target='_blank' rel='noopener'>Voir sur MusicBrainz ↗</a></div>"
          if release.mbid else "")
    where = release.rel or release.folder.name
    unsupported = (f"<div class='gap'>Non pris en charge : {esc(', '.join(release.unsupported[:5]))}{' …' if len(release.unsupported) > 5 else ''}</div>"
                   if release.unsupported else "")

    return (
        "<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'>"
        f"{favicon.monogram_link(release.title)}"
        + layout.BOOT +
        f"<title>{esc(release.title)}</title>"
        "<style>"
        + CSS_BASE +
        ".wrap{max-width:1000px;margin:0 auto;padding:32px}"
        + layout.CSS +
        ".back{color:#7cc4ff;text-decoration:none;font-size:14px}"
        ".back:hover{text-decoration:underline}"
        ".head{display:flex;gap:28px;flex-wrap:wrap;margin-bottom:34px}"
        ".head .cov{flex:none;width:280px;max-width:100%}"
        ".info{flex:1;min-width:260px}"
        ".artist{color:#c7ccd4;font-size:18px;margin-bottom:6px}"
        ".facts{color:#9aa0aa;margin-bottom:6px}"
        ".genres{color:#9aa0aa;font-size:14px;margin-bottom:10px}"
        ".links{margin-top:6px}"
        ".mb{color:#7cc4ff;font-size:13px;text-decoration:none;white-space:nowrap}.mb:hover{text-decoration:underline}"
        ".gap{color:#ffb86b;margin-top:14px;font-size:14.5px}.gap span{color:#9aa0aa}"
        ".trk{width:100%;border-collapse:collapse;font-size:15px}"
        ".trk td{padding:8px 10px;border-bottom:1px solid #21232b;vertical-align:top}"
        ".trk .n,.trk .d{width:1%;white-space:nowrap;text-align:right;color:#9aa0aa;font-variant-numeric:tabular-nums}"
        ".trk .by{color:#9aa0aa;font-size:13px}"
        ".trk .err{color:#ff9aa6;font-size:13px}"
        ".trk tr.absent td{color:#ffb86b;opacity:.55;font-style:italic}"
        + layout.PATH_CSS +
        "</style></head><body>"
        + layout.header(f"<div class='row'><a class='back' href='{esc(back_href)}'>← {esc(library_name)}</a>"
                        + layout.mode_button(layout.SHEET_LABELS) + "</div>") +
        f"<div class='head'><div class='cov'><div class='al'><div class='aff'>{_cover(release.key, image, release.title)}</div></div></div>"
        "<div class='info'>"
        f"<h1>{esc(release.title)}</h1>"
        f"<div class='artist'>{esc(release.artist)}</div>"
        f"<div class='facts'>{esc(_facts(release))}</div>"
        + (f"<div class='genres'>{esc(', '.join(release.genres))}</div>" if release.genres else "")
        + mb + gap_lines + unsupported
        + "</div></div>"
        + tables
        + layout.paths_block([where])
        + "<script>"
        "var b=document.querySelector('.back');"
        "b.onclick=function(e){"
        "var from=document.referrer.split(/[?#]/)[0],"
        "index=new URL(b.getAttribute('href').split('#')[0],location.href).href;"
        "if(history.length>1&&from===index){e.preventDefault();history.back()}};"
        + layout.mode_script(layout.SHEET_LABELS) +
        "</script></div></body></html>"
    )
