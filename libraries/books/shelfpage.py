"""Pages HTML de l'étagère : un sommaire de toutes les séries, et une page par série.

Le sommaire montre une vignette par série (la couverture de son premier volume), groupées par section, avec une zone de recherche qui cherche aussi dans les auteurs, éditeurs et genres. Chaque vignette mène à la page de sa série : couverture, résumé, auteurs, volumes avec leur couverture, et les numéros qui manquent d'après les fiches.

Comme les fiches des films, chaque page est un fichier unique - les couvertures y sont encodées - et la page précédente sert de cache : régénérer ne relit que les livres nouveaux ou modifiés.

Tout est pur : ni réseau ni disque, l'appelant fournit les couvertures déjà réduites.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

from libraries.common import favicon, layout
from libraries.common.filenames import safe_name

from . import shelf

DIR = "Series"                 # le dossier des pages, rangé À CÔTÉ du sommaire
MIME = "image/jpeg"

# Retrouve les couvertures déjà encodées dans une page précédente.
EMBEDDED_RE = re.compile(r"<img data-img='([^']+)' src='(data:[^']+)'")


def esc(value):
    # L'apostrophe aussi : les attributs sont entre apostrophes, et un nom qui dit "l'Oeil" fermerait l'attribut en plein milieu.
    return escape(str(value or ""), {"'": "&#39;"})


def page_name(series):
    """Nom du fichier de la page : le nom de la série, lisible dans une liste de fichiers, et son identifiant pour que deux séries du même nom (dans deux sections) n'en partagent pas une."""
    return f"{safe_name(series.name)[:60] or 'serie'}-{series.id}.html"


def href(series):
    """Lien, relatif au sommaire, vers la page d'une série."""
    return f"{DIR}/{quote(page_name(series))}"


def anchor(series):
    """Ancre de la vignette d'une série dans le sommaire : le retour depuis sa page y ramène."""
    return f"s{series.id}"


def data_uri(jpeg):
    return f"data:{MIME};base64," + base64.b64encode(jpeg).decode("ascii")


def read_embedded(page_path):
    """{clé: data-URI} des couvertures déjà présentes dans une page existante."""
    try:
        html = Path(page_path).read_text(encoding="utf-8")
    except OSError:
        return {}
    return dict(EMBEDDED_RE.findall(html))


def _cover(key, uri, name):
    """La couverture, ou à défaut un monogramme dans la couleur du titre : un carré vide ressemble à une image qui n'a pas chargé."""
    if uri:
        return f"<img data-img='{esc(key)}' src='{uri}' alt='' decoding='async' loading='lazy'>"
    return (f"<div class='noimg mono' style='background:{favicon.color(name)}'>"
            f"{esc(favicon.initials(name))}</div>")


def ranges(numbers):
    """'3, 5–7, 12' : les numéros qui se suivent tiennent en une plage."""
    parts, start, previous = [], None, None
    for n in list(numbers) + [None]:
        if start is not None and (n is None or n != previous + 1):
            parts.append(str(start) if start == previous else f"{start}–{previous}" if previous - start > 1 else f"{start}, {previous}")
            start = None
        if n is not None and start is None:
            start = n
        previous = n
    return ", ".join(parts)


def progress(series):
    """(possédés, attendus) quand le dossier est UNE série dont les fiches donnent le total, et qu'il en manque ; sinon None.

    Un dossier de plusieurs cycles n'a pas de total unique : "1/3" y compterait un seul cycle pour tout le dossier.
    """
    gaps = series.missing()
    if len(gaps) != 1 or len(series.tag_groups()) != 1:
        return None
    _, lacking, total = gaps[0]
    return total - len(lacking), total


def _count_label(series):
    got = progress(series)
    if got:
        return f"{got[0]}/{got[1]} {shelf.UNITS.get(series.section, shelf.DEFAULT_UNIT)[1]}"
    return shelf.unit(series.section, len(series.volumes))


def _search_text(series):
    return " ".join([series.name, *series.authors, series.publisher, *series.genres])


def _years(series):
    years = series.years
    if not years:
        return ""
    return str(years[0]) if years[0] == years[1] else f"{years[0]}–{years[1]}"


# ----------------------------------------------------------------------------
# Feuille de style commune
# ----------------------------------------------------------------------------
CSS_BASE = (
    "body{font:16px/1.5 system-ui,sans-serif;margin:0;background:#14151a;color:#e8e8ea}"
    "h1{margin:0 0 4px}"
    "[hidden]{display:none!important}"
    "h2{font-size:17px;margin:30px 0 14px;padding-bottom:8px;border-bottom:1px solid #21232b}"
    ".cnt{margin-left:9px;font-size:13px;font-weight:400;color:#9aa0aa;font-variant-numeric:tabular-nums}"
    ".bk{display:block;color:inherit;text-decoration:none}"
    ".bk .aff{position:relative;aspect-ratio:2/3;border-radius:8px;overflow:hidden;background:#21232b;transition:transform .15s,box-shadow .15s}"
    "a.bk:hover .aff,a.bk:focus-visible .aff{transform:translateY(-3px);box-shadow:0 0 0 2px #7cc4ff}"
    "a.bk:hover .t{color:#7cc4ff}"
    ".bk img,.bk .noimg{width:100%;height:100%;object-fit:cover;display:block}"
    ".mono{display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:34px}"
    ".bk .t{margin-top:8px;font-size:14px;font-weight:600;line-height:1.3;overflow-wrap:anywhere}"
    ".bk .y{color:#9aa0aa;font-size:13px}"
    ".bk .y.warn{color:#ffb86b}"
    ".bk.bad .aff{box-shadow:0 0 0 2px #ff9aa6}"
)


# ----------------------------------------------------------------------------
# Sommaire
# ----------------------------------------------------------------------------
def build_index(library_name, sections, covers, pages=()):
    """Rend le sommaire. 'sections' = [(nom, [Series])] ; 'covers' = {id de série: data-URI} ; 'pages' = ids des séries dont la page existe (les autres vignettes restent inertes plutôt que de mener à un lien cassé)."""
    blocks, chips = [], []
    n_series = n_volumes = 0
    genre_counts = {}
    for number, (name, series_list) in enumerate(sections):
        n_series += len(series_list)
        count = sum(len(s.volumes) for s in series_list)
        section = series_list[0].section             # "Comics · DC" compte ses tomes comme "Comics"
        n_volumes += count
        tiles = []
        for series in series_list:
            link = f" href='{esc(href(series))}' id='{anchor(series)}'" if series.id in pages else ""
            tag = "a" if link else "div"
            warn = " warn" if progress(series) else ""
            for genre in series.genres:
                genre_counts[genre] = genre_counts.get(genre, 0) + 1
            tiles.append(
                f"<{tag} class='bk'{link} data-s='{esc(_search_text(series))}' data-i='{layout.initial(series.name)}'{layout.genre_attr(series.genres)}>"
                f"<div class='aff'>{_cover(series.cover_volume.key, covers.get(series.id), series.name)}</div>"
                f"<div class='t'>{esc(series.name)}</div>"
                f"<div class='y{warn}'>{esc(_count_label(series))}</div>"
                f"</{tag}>")
        chips.append(f"<button class='chip' type='button' data-t='sec{number}'>{esc(name)}</button>")
        blocks.append(f"<section id='sec{number}'><h2>{esc(name)}<span class='cnt'>{len(series_list)} · {esc(shelf.unit(section, count))}</span></h2>"
                      f"<div class='grid'>{''.join(tiles)}</div></section>")

    summary = f"{n_series} séries · {n_volumes} volumes"
    return (
        "<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'>"
        + favicon.shelf_link()
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
            "<input class='filter' type='search' placeholder='Rechercher une série, un auteur…' aria-label='Rechercher une série ou un auteur'>"
            + layout.genre_select(genre_counts) + "</div>"
            + f"{layout.mode_button()}<div class='line'>{''.join(chips)}</div></div>"
            + layout.index_nav()) +
        f"{''.join(blocks)}"
        "<p class='none' hidden>Aucune série ne correspond.</p>"
        "<script>"
        "var f=document.querySelector('.filter');"
        "function n(s){return s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase()}"
        "f.oninput=function(){var q=n(f.value.trim()),any=false;"
        "document.querySelectorAll('section').forEach(function(s){var seen=0;"
        "s.querySelectorAll('.bk').forEach(function(c){"
        "var ok=(!q||n(c.getAttribute('data-s')).indexOf(q)>=0)&&gok(c);c.hidden=!ok;if(ok)seen++});"
        "s.hidden=!seen;if(seen)any=true});"
        "document.querySelector('.none').hidden=any||!(q||picked())};"
        + layout.genre_script() + layout.mode_script() + layout.index_script() +
        "</script></div></body></html>"
    )


# ----------------------------------------------------------------------------
# Page d'une série
# ----------------------------------------------------------------------------
def _facts(series):
    parts = (series.label, series.publisher, _years(series), shelf.unit(series.section, len(series.volumes)))
    return " · ".join(p for p in parts if p)


def _volume_meta(volume):
    fields = volume.fields
    parts = [str(fields["Year"]) if fields.get("Year") else "",
             f"{fields['PageCount']} p." if fields.get("PageCount") else "",
             volume.kind.upper() if volume.kind not in ("cbz", "epub") else ""]
    return " · ".join(p for p in parts if p)


def _volume_card(volume, images):
    uri = images.get(volume.key)
    bad = " bad" if volume.error else ""
    meta = f"illisible : {volume.error}" if volume.error else _volume_meta(volume)
    return (f"<div class='bk{bad}'>"
            f"<div class='aff'>{_cover(volume.key, uri, volume.title)}</div>"
            f"<div class='t'>{esc(volume.title)}</div>"
            f"<div class='y'>{esc(meta)}</div></div>")


def build_series(series, images, back_href, library_name):
    """Rend la page d'une série. 'images' = {clé de volume: data-URI} ; 'back_href' = lien vers le sommaire."""
    back_href = f"{back_href}#{anchor(series)}"
    cover = series.cover_volume
    text, source = series.summary
    by = ", ".join(series.authors)
    gaps = series.missing()
    named = len(series.tag_groups()) > 1            # plusieurs cycles : un manque sans son cycle ne dirait pas où chercher
    gap_lines = "".join(
        f"<div class='gap'>Manque : {esc((label + ' : ') if named and label else '')}{esc(ranges(lacking))} "
        f"<span>(sur {total}, d'après les fiches)</span></div>" for label, lacking, total in gaps)

    groups = []                        # [(sous-dossier, [volumes])], dans l'ordre de la série
    for volume in series.volumes:
        if not groups or groups[-1][0] != volume.sub:
            groups.append((volume.sub, []))
        groups[-1][1].append(volume)
    shown = []
    for sub, volumes in groups:
        heading = f"<h2>{esc(sub)}<span class='cnt'>{len(volumes)}</span></h2>" if sub else ("<h2>Volumes</h2>" if len(groups) > 1 else "")
        shown.append(heading + "<div class='grid'>" + "".join(_volume_card(v, images) for v in volumes) + "</div>")

    return (
        "<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'>"
        f"{favicon.monogram_link(series.name)}"
        + layout.BOOT +
        f"<title>{esc(series.name)}</title>"
        "<style>"
        + CSS_BASE +
        ".wrap{max-width:1000px;margin:0 auto;padding:32px}"
        + layout.CSS +
        ".back{color:#7cc4ff;text-decoration:none;font-size:14px}"
        ".back:hover{text-decoration:underline}"
        ".head{display:flex;gap:28px;flex-wrap:wrap;margin-bottom:34px}"
        ".head .cov{flex:none;width:240px}"
        ".info{flex:1;min-width:260px}"
        ".facts{color:#9aa0aa;margin-bottom:6px}"
        ".by{color:#c7ccd4;font-size:14px;margin-bottom:6px}"
        ".genres{color:#9aa0aa;font-size:14px;margin-bottom:14px}"
        ".o{color:#e8e8ea;font-size:15.5px;line-height:1.6;white-space:pre-line}"
        ".src{color:#9aa0aa;font-size:13px;margin-top:6px}"
        ".gap{color:#ffb86b;margin-top:14px;font-size:14.5px}.gap span{color:#9aa0aa}"
        ".grid{display:grid;gap:18px;grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}"
        "</style></head><body>"
        + layout.header(f"<div class='row'><a class='back' href='{esc(back_href)}'>← {esc(library_name)}</a>"
                        + layout.mode_button(layout.SHEET_LABELS) + "</div>") +
        f"<div class='head'><div class='cov'><div class='bk'><div class='aff'>{_cover(cover.key, images.get(cover.key), series.name)}</div></div></div>"
        "<div class='info'>"
        f"<h1>{esc(series.name)}</h1>"
        f"<div class='facts'>{esc(_facts(series))}</div>"
        + (f"<div class='by'>{esc(by)}</div>" if by else "")
        + (f"<div class='genres'>{esc(', '.join(series.genres))}</div>" if series.genres else "")
        + (f"<div class='o'>{esc(text)}</div>"
           + (f"<div class='src'>Résumé de « {esc(source.title)} »</div>" if source else "") if text else "")
        + gap_lines
        + "</div></div>"
        + "".join(shown)
        + "<script>"
        "var b=document.querySelector('.back');"
        "b.onclick=function(e){"
        "var from=document.referrer.split(/[?#]/)[0],"
        "index=new URL(b.getAttribute('href').split('#')[0],location.href).href;"
        "if(history.length>1&&from===index){e.preventDefault();history.back()}};"
        + layout.mode_script(layout.SHEET_LABELS) +
        "</script></div></body></html>"
    )
