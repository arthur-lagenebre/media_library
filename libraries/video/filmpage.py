"""Fiche d'un film de la médiathèque : affiche, résumé, casting.

Chaque film possédé a sa propre page, rangée dans un dossier à côté de l'index (voir DIR) : l'index reste léger - il embarque une affiche par film, pas vingt portraits -, et la fiche n'est ouverte que pour le film qu'on clique.

Tout vient de la réponse TMDB du film (/movie?append_to_response=credits), déjà lue pour étiqueter ou classer le film : une fiche ne coûte aucune requête de plus, seulement les images. Comme l'index, la page est un fichier unique (images encodées dedans) et la version précédente sert de cache.

Tout est pur : ni réseau ni disque, l'appelant fournit les images déjà téléchargées.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from libraries.common import favicon, layout
from . import cast, embed

# Le dossier des fiches, rangé À CÔTÉ de l'index : avec --recap-out __Data__ (voir le README), il vit donc dans __Data__ avec le reste de ce que le script écrit, et la médiathèque elle-même n'est pas touchée.
DIR = "Fiches"

POSTER_SIZE = "w342"      # la fiche montre l'affiche en grand : celle de l'index (w185) y serait floue
PROFILE_SIZE = "w185"     # la taille TMDB faite pour un visage
CAST_LIMIT = 20           # comme les fiches de série ; passé les premiers, ce sont des silhouettes


def esc(value):
    return escape(str(value or ""), {"'": "&#39;"})


def name(movie_id):
    """Nom du fichier de la fiche : l'identifiant TMDB, stable même si le film est renommé ou son titre corrigé."""
    return f"{movie_id}.html"


def href(movie_id):
    """Lien, relatif à l'index, vers la fiche d'un film."""
    return f"{DIR}/{name(movie_id)}"


def anchor(movie_id):
    """Ancre de la vignette d'un film dans l'index : le retour depuis sa fiche y ramène."""
    return f"f{movie_id}"


def directors(movie):
    """Réalisateurs, sans doublon, dans l'ordre TMDB."""
    names = [c.get("name") for c in (movie.get("credits") or {}).get("crew", []) if c.get("job") == "Director"]
    return list(dict.fromkeys(n for n in names if n))


def actors(movie, limit=CAST_LIMIT):
    """Les premiers rôles, au rang du générique : [{'name', 'character', 'profile_path'}, ...]."""
    return [a for a in (movie.get("credits") or {}).get("cast", []) if a.get("name")][:limit]


def poster_images(movie):
    """{clé: chemin TMDB} de l'affiche de la fiche."""
    key = embed.image_key(movie.get("poster_path"), POSTER_SIZE)
    return {key: movie["poster_path"]} if key else {}


def profile_images(movie, limit=CAST_LIMIT, size=PROFILE_SIZE):
    """{clé: chemin TMDB} des portraits du casting."""
    needed = {}
    for actor in actors(movie, limit):
        key = embed.image_key(actor.get("profile_path"), size)
        if key:
            needed[key] = actor["profile_path"]
    return needed


def _facts(movie):
    """'2010 · 148 min · Science-Fiction, Action' : ce qui présente le film, sans les trous."""
    runtime = movie.get("runtime")
    genres = ", ".join(g.get("name", "") for g in movie.get("genres") or [] if g.get("name"))
    parts = ((movie.get("release_date") or "")[:4], f"{runtime} min" if runtime else "", genres)
    return " · ".join(p for p in parts if p)


def page_title(movie):
    """'Inception (2010)' : l'onglet doit distinguer deux films du même titre."""
    year = (movie.get("release_date") or "")[:4]
    return f"{movie.get('title') or ''} ({year})" if year else (movie.get("title") or "")


def build_html(movie, images, back_href, library_name, limit=CAST_LIMIT, profile_size=PROFILE_SIZE):
    """Rend la fiche d'un film. 'images' = {clé: data-URI}, affiche et portraits mêlés ; 'back_href' = lien vers l'index."""
    key = embed.image_key(movie.get("poster_path"), POSTER_SIZE)
    uri = images.get(key) if key else None
    poster = embed.tag(key, uri) if uri else "<div class='noimg'></div>"

    faces = []
    for actor in actors(movie, limit):
        pkey = embed.image_key(actor.get("profile_path"), profile_size)
        puri = images.get(pkey) if pkey else None
        face = embed.tag(pkey, puri) if puri else "<div class='noimg'></div>"
        faces.append(f"<div class='actor'><div class='ph'>{face}</div>"
                     f"<div class='n'>{esc(actor.get('name'))}</div>"
                     f"<div class='c'>{esc(actor.get('character'))}</div></div>")

    by = directors(movie)
    tagline = movie.get("tagline")
    # Le retour ramène à la vignette du film, pas en haut de l'index. L'ancre est le repli sûr (elle marche partout, en file:// comme sur un NAS) ; quand on vient bien de l'index, un vrai retour en arrière vaut mieux - le navigateur y rend aussi la recherche en cours, que l'ancre ne retrouve pas (la vignette serait masquée).
    if movie.get("id"):
        back_href = f"{back_href}#{anchor(movie['id'])}"
    return (
        "<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'>"
        f"{favicon.monogram_link(movie.get('title'))}"
        + layout.BOOT +
        f"<meta name='poster-size' content='{esc(POSTER_SIZE)}'>"
        f"<meta name='profile-size' content='{esc(profile_size)}'>"
        f"<title>{esc(page_title(movie))}</title>"
        "<style>"
        "body{font:16px/1.5 system-ui,sans-serif;margin:0;background:#14151a;color:#e8e8ea}"
        ".wrap{max-width:1000px;margin:0 auto;padding:32px}"
        + layout.CSS +
        ".back{color:#7cc4ff;text-decoration:none;font-size:14px}"
        ".back:hover{text-decoration:underline}"
        ".head{display:flex;gap:28px;flex-wrap:wrap}"
        ".head .aff{flex:none;width:240px;aspect-ratio:2/3;border-radius:10px;overflow:hidden;background:#21232b}"
        ".head img,.head .noimg,.actor img,.actor .noimg{width:100%;height:100%;object-fit:cover;display:block}"
        ".info{flex:1;min-width:260px}"
        "h1{margin:0 0 4px}"
        ".facts{color:#9aa0aa;margin-bottom:6px}"
        ".tag{color:#9aa0aa;font-style:italic;margin-bottom:6px}"
        ".by{color:#c7ccd4;font-size:14px;margin-bottom:14px}"
        ".o{color:#e8e8ea;font-size:15.5px;line-height:1.6}"
        "h2{font-size:17px;margin:34px 0 14px;padding-bottom:8px;border-bottom:1px solid #21232b}"
        ".grid{display:grid;gap:18px;grid-template-columns:repeat(auto-fill,minmax(124px,1fr))}"
        ".actor .ph{aspect-ratio:2/3;border-radius:8px;overflow:hidden;background:#21232b}"
        ".actor .n{margin-top:8px;font-size:14px;font-weight:600;line-height:1.3}"
        ".actor .c{color:#c7ccd4;font-size:13px;line-height:1.35}"
        + cast.noface_rule() +
        "</style></head><body>"
        + layout.header(f"<div class='row'><a class='back' href='{esc(back_href)}'>← {esc(library_name)}</a>"
                        + layout.mode_button(layout.SHEET_LABELS) + "</div>") +
        ""
        f"<div class='head'><div class='aff'>{poster}</div><div class='info'>"
        f"<h1>{esc(movie.get('title'))}</h1>"
        f"<div class='facts'>{esc(_facts(movie))}</div>"
        + (f"<div class='tag'>{esc(tagline)}</div>" if tagline else "")
        + (f"<div class='by'>De {esc(', '.join(by))}</div>" if by else "")
        + f"<div class='o'>{esc(movie.get('overview') or 'Pas de résumé.')}</div>"
        "</div></div>"
        + (f"<h2>Casting</h2><div class='grid'>{''.join(faces)}</div>" if faces else "")
        + "<script>"
        "var b=document.querySelector('.back');"
        "b.onclick=function(e){"
        "var from=document.referrer.split(/[?#]/)[0],"
        "index=new URL(b.getAttribute('href').split('#')[0],location.href).href;"
        "if(history.length>1&&from===index){e.preventDefault();history.back()}};"
        + layout.mode_script(layout.SHEET_LABELS) +
        "</script></div></body></html>"
    )
