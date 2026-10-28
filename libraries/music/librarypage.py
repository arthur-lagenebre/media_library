"""Pages HTML de la médiathèque musicale : music.html - un sommaire de tous les albums, qui est aussi le lecteur -, une fiche par album et une fiche par artiste.

Le sommaire est un mur de pochettes groupé par artiste - chacun a sa section, même avec un seul album -, avec une zone de recherche, un filtre de genre et un index A-Z, comme celui des films. Chaque pochette mène à la fiche de son album : pochette, artiste, année, label, genres, pistes avec leur durée, et celles qui manquent d'après les tags. Le nom de l'artiste, sur le sommaire comme sur la fiche d'un album, mène à sa fiche : ses albums, et son lien MusicBrainz quand les tags en donnent l'identifiant.

Comme les fiches des films et des livres, chaque page est un fichier unique - les pochettes y sont encodées - et la page précédente sert de cache : régénérer ne rouvre que les pochettes nouvelles.

Le sommaire porte sa barre de lecture (voir player.py) : un bouton sur chaque pochette lit l'album, et les fiches s'ouvrent par-dessus dans une iframe, sans couper la musique. Une fiche ouverte seule peut aussi lire ses pistes : chacune porte un bouton qui joue le fichier lui-même, par un lien relatif, dans un lecteur fixé en bas de page qui enchaîne les pistes. Rien n'est copié ni encodé dans la page - elle ne marche donc que là où les fichiers sont joignables depuis elle (disque local, partage réseau, serveur web du NAS).

Tout est pur : ni réseau ni disque, l'appelant fournit les pochettes déjà réduites.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

from libraries.common import favicon, layout
from libraries.common.filenames import safe_name

from . import artistinfo, library, player
from .musicbrainz import artist_url, release_url

DIR = "Albums"                 # le dossier des fiches, rangé À CÔTÉ du sommaire
ARTIST_DIR = "Artistes"        # celui des fiches d'artiste

# Retrouve les pochettes déjà encodées dans une page précédente.
EMBEDDED_RE = re.compile(r"<img data-img='([^']+)' src='(data:[^']+)'")


def esc(value):
    # L'apostrophe aussi : les attributs sont entre apostrophes, et un titre qui dit "l'Oeil" fermerait l'attribut en plein milieu.
    return escape(str(value or ""), {"'": "&#39;"})


def page_name(release):
    """Nom du fichier de la fiche : l'artiste et le titre, lisibles dans une liste de fichiers, et l'identifiant du dossier pour que deux éditions du même album n'en partagent pas une."""
    return f"{safe_name(f'{release.artist} - {release.title}')[:70] or 'album'}-{release.id}.html"


def href(release, base=""):
    """Lien vers la fiche d'un album, relatif au sommaire ; 'base' = '../' depuis une fiche."""
    return f"{base}{DIR}/{quote(page_name(release))}"


def artist_page_name(artist):
    """Nom du fichier de la fiche d'un artiste : son nom, lisible, et l'identifiant qui le distingue d'un homonyme à la graphie voisine."""
    return f"{safe_name(artist.name)[:70] or 'artiste'}-{artist.id}.html"


def artist_href(artist, base=""):
    """Lien vers la fiche d'un artiste, relatif au sommaire ; 'base' = '../' depuis une fiche."""
    return f"{base}{ARTIST_DIR}/{quote(artist_page_name(artist))}"


def artist_anchor(artist):
    """Où le sommaire range un artiste : le titre de sa section."""
    return f"s{artist.id}"


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


# L'image des albums sans pochette : une note sur le gris des pochettes, la même partout. C'est un fond de CSS, écrit une fois par page : un album sans pochette ne coûte que sa <div>.
NO_COVER_SVG = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><path fill='#4a4e5a' "
                "d='M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z'/></svg>")
NO_COVER = "data:image/svg+xml," + quote(NO_COVER_SVG, safe="")


def _cover(key, uri):
    """La pochette, ou à défaut l'image générique : un carré vide ressemble à une image qui n'a pas chargé."""
    if uri:
        return f"<img data-img='{esc(key)}' src='{uri}' alt='' decoding='async' loading='lazy'>"
    return "<div class='noimg'></div>"


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
    ".al .cv{display:block;color:inherit;text-decoration:none}"
    ".al .aff{position:relative;aspect-ratio:1;border-radius:8px;overflow:hidden;background:#21232b;transition:transform .15s,box-shadow .15s}"
    "a.cv:hover .aff,a.cv:focus-visible .aff{transform:translateY(-3px);box-shadow:0 0 0 2px #7cc4ff}"
    "a.cv:hover .t{color:#7cc4ff}"
    ".al img,.al .noimg{width:100%;height:100%;object-fit:cover;display:block}"
    f".noimg{{background:#21232b url({NO_COVER}) center/45% no-repeat}}"
    ".al .t{margin-top:8px;font-size:14px;font-weight:600;line-height:1.3;overflow-wrap:anywhere}"
    ".artist a:hover,h2 a:hover{color:#7cc4ff;text-decoration:underline}"
    "h2 a{color:inherit;text-decoration:none}"
    ".al .y{color:#9aa0aa;font-size:13px}"
    ".al .y.warn{color:#ffb86b}"
    ".al.bad .aff{box-shadow:0 0 0 2px #ff9aa6}"
)


def _order(number, i):
    """Où se range une piste sur une fiche : son numéro, et à la suite celles qui n'en ont pas."""
    return number if number is not None else 10 ** 6 + i


def _playlist(release, media_base):
    """[[adresse, titre]] des pistes lisibles d'un album, dans l'ordre de sa fiche (disques à la suite) ; vide quand la page ne lit rien (media_base = None)."""
    if media_base is None:
        return []
    found = []
    for _, tracks in release.discs:
        ordered = sorted(enumerate(tracks), key=lambda p: _order(p[1].number, p[0]))
        found += [[media_base + quote(t.rel), t.title] for _, t in ordered if not t.error]
    return found


def _play_overlay(release, media_base):
    """Le bouton de lecture posé au milieu de la pochette ; rien pour un album sans piste lisible. Il est à côté du lien de la pochette, pas dedans : voir player.TILE_CSS."""
    tracks = _playlist(release, media_base)
    if not tracks:
        return ""
    return (f"<span class='ovl'><button class='ov' type='button' aria-label='Lire {esc(release.title)}' "
            f"data-t='{esc(json.dumps(tracks, ensure_ascii=False, separators=(',', ':')))}'>▶</button></span>")


def _tile(release, uri, link, attrs="", media_base=None):
    """Une pochette avec son titre. 'link' = adresse de la fiche de l'album, ou '' ; 'attrs' = les attributs de la vignette ; 'media_base' = le chemin relatif de la page à la racine de la médiathèque, terminé par '/' : avec lui, un bouton lit l'album depuis la pochette."""
    warn = " warn" if release.progress() else ""
    facts = " · ".join(p for p in (release.year, _count_label(release)) if p)
    tag, target = ("a", f" href='{esc(link)}'") if link else ("div", "")
    return (f"<div class='al'{attrs}>"
            f"<{tag} class='cv'{target}>"
            f"<div class='aff'>{_cover(release.key, uri)}</div>"
            f"<div class='t'>{esc(release.title)}</div>"
            f"</{tag}>"
            f"{_play_overlay(release, media_base)}"
            f"<div class='y{warn}'>{esc(facts)}</div>"
            "</div>")


def _wanted_tile(wanted, uri=None):
    """La vignette d'un album qu'on n'a pas : grisée, sans lien ni lecture, l'année et « manquant » à la place du nombre de pistes. 'uri' = sa pochette en data-URI, si on en a une."""
    return ("<div class='al gone'><div class='cv'>"
            f"<div class='aff'>{_cover(wanted.key, uri)}</div>"
            f"<div class='t'>{esc(wanted.title)}</div></div>"
            f"<div class='y'>{esc(wanted.year)} · <span class='lack'>manquant</span></div></div>")


def _group(release, artists):
    """Où revenir sur le sommaire après la fiche d'un album : le nom de son groupe, pas sa pochette - sous un en-tête fixe, c'est le titre de la section qu'on veut voir en premier. Rien pour l'artiste sans fiche : on revient à la pochette."""
    artist = artists.get(release.artist_id)
    return f" data-b='{artist_anchor(artist)}'" if artist is not None else ""


# ----------------------------------------------------------------------------
# Sommaire
# ----------------------------------------------------------------------------
def build_index(library_name, sections, covers, pages=(), artists=None, media_base=None):
    """Rend le sommaire. 'sections' = [(nom, [Release])] (voir library.sections) ; 'covers' = {id d'album: data-URI} ; 'pages' = ids des albums dont la fiche existe (les autres pochettes restent inertes plutôt que de mener à un lien cassé) ; 'artists' = {id d'artiste: Artist} de ceux dont la fiche existe, de même ; 'media_base' = le chemin relatif du sommaire à la racine de la médiathèque, terminé par '/' (chaque pochette porte alors un bouton qui lit l'album), ou None pour un sommaire qui ne lit rien."""
    artists = artists or {}
    playable = False
    blocks = []
    n_albums = n_tracks = 0
    seconds = 0
    names = set()
    genre_counts = {}
    for name, releases in sections:
        tiles = []
        for release in releases:
            n_albums += 1
            n_tracks += len(release.tracks)
            seconds += release.duration
            names.add(layout.fold(release.artist))
            for genre in release.genres:
                genre_counts[genre] = genre_counts.get(genre, 0) + 1
            tiles.append(_tile(
                release, covers.get(release.id), href(release) if release.id in pages else "",
                f" id='{anchor(release)}'{_group(release, artists)} data-s='{esc(_search_text(release))}'{layout.genre_attr(release.genres)}",
                media_base))
            playable = playable or bool(_playlist(release, media_base))
        # C'est le titre de la section que vise l'index A-Z : la pochette ne dit pas de qui elle est.
        shown, ident = esc(name), ""
        letter = f" data-i='{layout.initial(name)}'"
        artist = artists.get(releases[0].artist_id)
        if artist is not None:
            ident = f" id='{artist_anchor(artist)}'"
            shown = f"<a href='{esc(artist_href(artist))}'>{shown}</a>"
        blocks.append(f"<section><h2{ident}{letter}>{shown}<span class='cnt'>{len(releases)} album{'s' if len(releases) != 1 else ''}</span></h2>"
                      f"<div class='grid'>{''.join(tiles)}</div></section>")

    summary = " · ".join(p for p in (f"{n_albums} album{'s' if n_albums != 1 else ''}", f"{len(names)} artiste{'s' if len(names) != 1 else ''}", tracks_label(n_tracks), length(seconds)) if p)
    return (
        "<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'>"
        + favicon.music_link()
        + layout.BOOT +
        f"<title>{esc(library_name)}</title>"
        "<style>"
        + CSS_BASE +
        ".wrap{max-width:1180px;margin:0 auto;padding:32px}"
        ".sub{color:#9aa0aa}"
        + layout.CSS + (player.INDEX_CSS if playable else "") +
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
        # La barre précède le script : il la cherche à son exécution.
        "</div>" + (player.main_bar() if playable else "") +
        "<script>"
        "var f=document.querySelector('.filter');"
        "function n(s){return s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase()}"
        "f.oninput=function(){var q=n(f.value.trim()),any=false;"
        "document.querySelectorAll('section').forEach(function(s){var seen=0;"
        "s.querySelectorAll('.al').forEach(function(c){"
        "var ok=(!q||n(c.getAttribute('data-s')).indexOf(q)>=0)&&gok(c);c.hidden=!ok;if(ok)seen++});"
        "s.hidden=!seen;if(seen)any=true});"
        "document.querySelector('.none').hidden=any||!(q||picked())};"
        + layout.genre_script() + layout.mode_script() + layout.index_script() + (player.INDEX_SCRIPT if playable else "") + RETURN_SCRIPT +
        "</script></body></html>"
    )


# ----------------------------------------------------------------------------
# Fiche d'un album
# ----------------------------------------------------------------------------
# Le retour au sommaire : quand on en vient, c'est l'historique qui revient - le sommaire retrouve sa position -, sinon le lien mène à la vignette.
# Le retour sur le sommaire : le navigateur y remet la page là où elle était, et c'est presque toujours en travers d'une rangée de pochettes, coupée par l'en-tête fixe. On retient donc, dans l'entrée d'historique du sommaire, le groupe de l'album qu'on ouvre ; au retour - retour du navigateur ou lien « Musique » -, la page se cale sous l'en-tête sur le nom de ce groupe. Sans cette entrée (page rechargée, ouverte directement), rien ne change.
RETURN_SCRIPT = (
    "(function(){"
    "var top=document.querySelector('.top');"
    "function put(id){var e=document.getElementById(id);if(e)scrollTo(0,e.getBoundingClientRect().top+scrollY-top.offsetHeight-12)}"
    "document.addEventListener('click',function(ev){"
    "var a=ev.target.closest&&ev.target.closest('a[href]');if(!a||a.target==='_blank')return;"
    "var al=a.closest('.al'),h=a.closest('h2'),id=al?al.getAttribute('data-b')||al.id:h?h.id:'';"
    "if(id){try{history.replaceState({back:id},'')}catch(e){}}});"
    "function restore(){var s=history.state;if(s&&s.back){put(s.back);try{history.replaceState(null,'')}catch(e){}}}"
    "if(history.state&&history.state.back){try{history.scrollRestoration='manual'}catch(e){}}"
    "restore();"
    "addEventListener('pageshow',function(e){if(e.persisted)restore()});"
    "})();"
)

# Le lien de retour : dans music.html, la fiche est dans une iframe, et il la fait fermer ; sinon c'est l'historique qui revient quand on vient du sommaire, et le lien mène à sa vignette dans les autres cas.
BACK_SCRIPT = (
    "var b=document.querySelector('.back');"
    "b.onclick=function(e){"
    "if(window.parent!==window){e.preventDefault();window.parent.postMessage({t:'close',to:b.getAttribute('href').split('#')[1]||''},'*');return}"
    "var from=document.referrer.split(/[?#]/)[0],"
    "index=new URL(b.getAttribute('href').split('#')[0],location.href).href;"
    "if(history.length>1&&from===index){e.preventDefault();history.back()}};"
)


def _facts(release):
    label = " ".join(p for p in (release.label, f"({release.catalog})" if release.catalog else "") if p)
    parts = (release.year, label, tracks_label(len(release.tracks)), length(release.duration), " + ".join(release.formats))
    return " · ".join(p for p in parts if p)


def _name(name, artist):
    """Un nom d'artiste sur une fiche d'album : un lien vers la fiche de l'artiste quand il en a une."""
    if artist is None:
        return esc(name)
    return f"<a href='{esc(artist_href(artist, '../'))}'>{esc(name)}</a>"


def _play_cell(track, media_base):
    """La cellule du bouton de lecture : vide pour une piste illisible ou absente, et absente de la table quand la fiche ne lit rien (media_base = None)."""
    if media_base is None:
        return ""
    if track is None or track.error:
        return "<td class='p'></td>"
    return (f"<td class='p'><button class='play' type='button' aria-label='Lire {esc(track.title)}' "
            f"data-src='{esc(media_base + quote(track.rel))}' data-title='{esc(track.title)}'>▶</button></td>")


def _more_cell(track, media_base):
    """La cellule du menu « ⋯ » d'une piste : comme celle de lecture, vide pour une piste illisible ou absente, et absente de la table quand la fiche ne lit rien (media_base = None)."""
    if media_base is None:
        return ""
    if track is None or track.error:
        return "<td class='m'></td>"
    return (f"<td class='m'><button class='more' type='button' aria-haspopup='menu' aria-expanded='false' "
            f"aria-label='Plus d&#39;actions pour {esc(track.title)}'>⋯</button></td>")


FEAT_RE = re.compile(r"\s+(?:feat\.?|ft\.?|featuring)\s+.*$", re.IGNORECASE)


def _main_artist(name):
    """'Ultra Vomit feat. Mouss de Mass' -> 'Ultra Vomit' : l'invité ne fait pas un autre artiste."""
    return layout.fold(FEAT_RE.sub("", name or ""))


def _row(track, album_artist, media_base=None):
    by = track.info.get("artist") or ""
    shown = f"<div class='by'>{esc(by)}</div>" if by and _main_artist(by) != _main_artist(album_artist) else ""
    bad = f"<div class='err'>illisible : {esc(track.error)}</div>" if track.error else ""
    return (f"<tr>{_play_cell(track, media_base)}<td class='n'>{esc(track.number if track.number is not None else '')}</td>"
            f"<td>{esc(track.title)}{shown}{bad}</td><td class='d'>{esc(clock(track.duration))}</td>{_more_cell(track, media_base)}</tr>")


def _absent(number, media_base=None):
    return f"<tr class='absent'>{_play_cell(None, media_base)}<td class='n'>{number}</td><td>piste manquante</td><td class='d'></td>{_more_cell(None, media_base)}</tr>"


def _disc_table(tracks, lacking, album_artist, media_base=None):
    """Les pistes d'un disque dans l'ordre, les manquantes grisées à leur place."""
    rows = [(_order(t.number, i), _row(t, album_artist, media_base)) for i, t in enumerate(tracks)]
    rows += [(n, _absent(n, media_base)) for n in lacking]
    return "<table class='trk'>" + "".join(html for _, html in sorted(rows, key=lambda r: r[0])) + "</table>"


def build_release(release, image, back_href, library_name, artist=None, media_base=None):
    """Rend la fiche d'un album. 'image' = data-URI de la pochette, ou None ; 'back_href' = lien vers le sommaire ; 'artist' = l'Artist dont la fiche existe, ou None ; 'media_base' = le chemin relatif de la fiche à la racine de la médiathèque, terminé par '/' (les pistes se lisent par là), ou None pour une fiche qui ne lit rien."""
    back_href = f"{back_href}#{artist_anchor(artist) if artist is not None else anchor(release)}"
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

    playable = media_base is not None and any(not t.error for t in release.tracks)

    tables = "".join(
        (f"<h2>Disque {number}<span class='cnt'>{tracks_label(len(tracks))}</span></h2>" if many else "")
        + _disc_table(tracks, gaps.get(number, []), release.artist, media_base)
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
        ".artist a{color:inherit;text-decoration:none}"
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
        + layout.PATH_CSS + (player.PLAYER_CSS if playable else "") +
        "</style></head><body>"
        + layout.header(f"<div class='row'><a class='back' href='{esc(back_href)}'>← {esc(library_name)}</a>"
                        + layout.mode_button(layout.SHEET_LABELS) + "</div>") +
        f"<div class='head'><div class='cov'><div class='al'><div class='aff'>{_cover(release.key, image)}</div></div></div>"
        "<div class='info'>"
        f"<h1>{esc(release.title)}</h1>"
        f"<div class='artist'>{_name(release.artist, artist)}</div>"
        f"<div class='facts'>{esc(_facts(release))}</div>"
        + (f"<div class='genres'>{esc(', '.join(release.genres))}</div>" if release.genres else "")
        + mb + gap_lines + unsupported + (player.ALL_BUTTON if playable else "")
        + "</div></div>"
        + tables
        + layout.paths_block([where])
        # La barre précède le script : il la cherche à son exécution, et le navigateur n'a lu que ce qui le précède.
        + "</div>" + (player.bar() if playable else "")
        + "<script>" + BACK_SCRIPT + layout.mode_script(layout.SHEET_LABELS) + (player.PAGE_SCRIPT if playable else "") +
        "</script></body></html>"
    )


# ----------------------------------------------------------------------------
# Fiche d'un artiste
# ----------------------------------------------------------------------------
def _artist_facts(artist):
    first, last = artist.years
    span = first if first == last else f"{first}–{last}"
    count = len(artist.releases)
    lacking = f"{len(artist.wanted)} manquant{'s' if len(artist.wanted) != 1 else ''}" if artist.wanted else ""
    parts = (f"{count} album{'s' if count != 1 else ''}", lacking, span, tracks_label(artist.tracks), length(artist.duration))
    return " · ".join(p for p in parts if p)


def _bio(info):
    """Le résumé Wikipédia et sa source ; rien sans article."""
    wiki = info.get("wiki")
    if not wiki:
        return ""
    return (f"<div class='bio'><p>{esc(wiki['extract'])}</p>"
            f"<a class='src' href='{esc(wiki['url'])}' target='_blank' rel='noopener'>Source : Wikipédia ({esc(wiki['lang'])}) ↗</a></div>")


def _members(info):
    """La liste des membres d'un groupe : les actuels, puis les anciens, chacun lié à sa fiche MusicBrainz. Chaque liste est repliée : on vient pour les albums, et un orchestre en compte des dizaines."""
    rows = []
    for member in info.get("members") or []:
        detail = " · ".join(p for p in (", ".join(member.get("roles") or []), artistinfo.period(member)) if p)
        rows.append((member.get("ended"), f"<li><a href='{esc(artist_url(member['mbid']))}' target='_blank' rel='noopener'>{esc(member['name'])}</a>"
                     + (f"<span>{esc(detail)}</span>" if detail else "") + "</li>"))
    out = ""
    for ended, title in ((False, "Membres"), (True, "Anciens membres")):
        part = [html for flag, html in rows if bool(flag) == ended]
        if part:
            out += f"<details class='mem'><summary>{title}<span class='cnt'>{len(part)}</span></summary><ul class='members'>{''.join(part)}</ul></details>"
    return out


def _links(artist, info):
    """Les liens de l'artiste : sa fiche MusicBrainz, puis ceux qu'il tient lui-même."""
    found = [("Voir sur MusicBrainz", artist_url(artist.mbid))] if artist.mbid else []
    found += [(link["label"], link["url"]) for link in info.get("links") or []]
    if not found:
        return ""
    return "<div class='links'>" + "".join(
        f"<a class='mb' href='{esc(url)}' target='_blank' rel='noopener'>{esc(label)} ↗</a>" for label, url in found) + "</div>"


def build_artist(artist, covers, back_href, library_name, pages=(), info=None, media_base=None, wanted_covers=None):
    """Rend la fiche d'un artiste : ce que MusicBrainz et Wikipédia en disent (voir artistinfo), ses albums, et son lien MusicBrainz. 'covers' = {id d'album: data-URI} ; 'pages' = ids des albums dont la fiche existe ; 'back_href' = lien vers le sommaire ; 'info' = le dictionnaire d'artistinfo, ou None ; 'media_base' = le chemin relatif de la fiche à la racine de la médiathèque, terminé par '/' (les pochettes lisent leur album), ou None ; 'wanted_covers' = {Wanted.key: data-URI} des albums manquants qui ont une image."""
    info = info or {}
    wanted_covers = wanted_covers or {}
    back_href = f"{back_href}#{artist_anchor(artist)}"
    # Les albums qui manquent se rangent parmi ceux qu'on a, par année : c'est la discographie, à quoi on voit ce qui y est.
    shown = [(library.order(release), _tile(release, covers.get(release.id), href(release, "../") if release.id in pages else "", media_base=media_base))
             for release in artist.releases]
    shown += [(wanted.order, _wanted_tile(wanted, wanted_covers.get(wanted.key))) for wanted in artist.wanted]
    tiles = "".join(tile for _, tile in sorted(shown, key=lambda pair: pair[0]))
    count = f"{len(artist.releases)}/{len(artist.releases) + len(artist.wanted)}" if artist.wanted else str(len(artist.releases))
    playable = any(_playlist(release, media_base) for release in artist.releases)
    return (
        "<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'>"
        f"{favicon.monogram_link(artist.name)}"
        + layout.BOOT +
        f"<title>{esc(artist.name)}</title>"
        "<style>"
        + CSS_BASE +
        ".wrap{max-width:1000px;margin:0 auto;padding:32px}"
        + layout.CSS +
        ".back{color:#7cc4ff;text-decoration:none;font-size:14px}"
        ".back:hover{text-decoration:underline}"
        ".head{margin-bottom:10px}"
        ".kind{color:#c7ccd4;font-size:18px;margin-bottom:6px}"
        ".dis{color:#9aa0aa;font-size:14px;font-style:italic;margin-bottom:6px}"
        ".bio{max-width:760px;margin:14px 0 8px}.bio p{margin:0 0 6px}"
        ".src{color:#9aa0aa;font-size:12.5px;text-decoration:none}.src:hover{color:#7cc4ff;text-decoration:underline}"
        ".links{display:flex;flex-wrap:wrap;gap:6px 18px}"
        ".mem{margin-top:30px}.mem+.mem{margin-top:18px}"
        ".mem summary{cursor:pointer;list-style:none;font-size:17px;font-weight:700;padding-bottom:8px;border-bottom:1px solid #21232b}"
        ".mem summary::-webkit-details-marker{display:none}"
        ".mem summary::before{content:'▸';display:inline-block;width:1.1em;color:#9aa0aa}"
        ".mem[open] summary::before{content:'▾'}"
        ".mem summary:hover{color:#7cc4ff}"
        ".mem .grid{margin-top:14px}"
        ".members{list-style:none;margin:14px 0 0;padding:0;columns:2 260px;column-gap:28px}"
        ".members li{break-inside:avoid;padding:4px 0}"
        ".members a{color:inherit;text-decoration:none}.members a:hover{color:#7cc4ff;text-decoration:underline}"
        ".members span{display:block;color:#9aa0aa;font-size:13px}"
        ".facts{color:#9aa0aa;margin-bottom:6px}"
        ".genres{color:#9aa0aa;font-size:14px;margin-bottom:10px}"
        ".links{margin-top:6px}"
        ".mb{color:#7cc4ff;font-size:13px;text-decoration:none;white-space:nowrap}.mb:hover{text-decoration:underline}"
        ".grid{display:grid;gap:18px;grid-template-columns:repeat(auto-fill,minmax(160px,1fr))}"
        # Un album qui manque : même vignette, en retrait, avec un simple liseré à la place de la pochette qu'il n'a pas.
        ".al.gone{opacity:.55}.al.gone .aff{box-shadow:inset 0 0 0 1px #3a3d48}.al.gone .t{font-weight:400}"
        ".al .lack{color:#ff9aa6}"
        + (player.TILE_CSS if playable else "") +
        "</style></head><body>"
        + layout.header(f"<div class='row'><a class='back' href='{esc(back_href)}'>← {esc(library_name)}</a>"
                        + layout.mode_button(layout.SHEET_LABELS) + "</div>") +
        "<div class='head'>"
        f"<h1>{esc(artist.name)}</h1>"
        + (f"<div class='dis'>{esc(info['disambiguation'])}</div>" if info.get("disambiguation") else "")
        + (f"<div class='kind'>{esc(artistinfo.facts(info))}</div>" if artistinfo.facts(info) else "")
        + f"<div class='facts'>{esc(_artist_facts(artist))}</div>"
        + (f"<div class='genres'>{esc(', '.join(artist.genres))}</div>" if artist.genres else "")
        + _links(artist, info)
        + _bio(info)
        + "</div>"
        + _members(info)
        + f"<details class='mem' open><summary>Albums<span class='cnt'>{count}</span></summary>"
        f"<div class='grid'>{tiles}</div></details>"
        "</div>" + (player.bar() if playable else "") +
        "<script>" + BACK_SCRIPT + layout.mode_script(layout.SHEET_LABELS) + (player.TILE_SCRIPT if playable else "") +
        "</script></body></html>"
    )
