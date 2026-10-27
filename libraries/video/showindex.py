"""Sommaire des séries d'une médiathèque, construit à partir de leurs fiches.

Chaque fiche de série (index.html dans le dossier de la série, autrefois recap.html) porte dans son en-tête de quoi la présenter : titre, année, saisons, et l'affiche encodée. Le sommaire n'est donc que la lecture de ces en-têtes - ni TMDB, ni réseau, ni dépendance -, assez léger pour tourner en tâche planifiée sur le NAS qui héberge la médiathèque : les fiches sont souvent écrites ailleurs, sur un disque local, puis transférées, et seul le NAS voit la médiathèque entière.

Le sommaire est rangé dans le dossier __Data__ de la médiathèque, sous le nom du titre qu'on lui donne (--title "Anime" l'écrit dans Anime.html), à défaut tv_shows.html : la médiathèque elle-même n'est pas touchée, et ses liens remontent d'un cran jusqu'aux fiches. Une page qui n'a pas été écrite par ce module n'est jamais remplacée.
"""

import hashlib
import re
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from urllib.parse import quote, urlencode
from xml.sax.saxutils import escape

from libraries.common import favicon, layout, textfile
from libraries.common.filenames import safe_name

DATA_DIR = "__Data__"                 # là où le sommaire est écrit, à la racine de la médiathèque
DEFAULT_INDEX = "tv_shows.html"       # son nom quand on ne lui donne pas de titre
LEGACY_INDEX = "index.html"           # là où les versions précédentes l'écrivaient, à la racine : lu pour son titre, jamais effacé
# La fiche de chaque série reste dans le dossier de la série, sous le nom qu'un navigateur ou un serveur ouvre de lui-même dans un dossier. recap.html est l'ancien nom, lu tant que la fiche n'a pas été régénérée.
PAGE_NAME = "index.html"
LEGACY_NAME = "recap.html"
DEFAULT_TITLE = "Séries"

# Signe qu'un index.html est bien le nôtre, et peut être réécrit sans demander.
GENERATOR = "media_library-index"
GENERATOR_META = f"<meta name='generator' content='{GENERATOR}'>"
# La marque d'avant le renommage du projet : un sommaire déjà écrit (sur le NAS, souvent) reste le nôtre, et sera réécrit avec la nouvelle au prochain passage.
LEGACY_GENERATORS = ("mkv_editors-index",)

# L'en-tête d'une fiche s'arrête au <style> : au-delà commencent les images, des dizaines de Mo qu'il est inutile de lire.
HEAD_END = "<style>"
CHUNK = 65536
META_RE = re.compile(r"<meta name='([\w-]+)' content='([^']*)'>")
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL)


def esc(value):
    return escape(str(value or ""), {"'": "&#39;"})


def recap_metas(show, tmdb_id, seasons_on_disk, poster=None):
    """Les <meta> qu'une fiche porte pour le sommaire : ce qui la présente, sans l'ouvrir.

    'poster' = (clé d'image, data-URI). La clé est gardée à côté : à la fiche suivante, l'affiche est reprise au lieu d'être retéléchargée (voir recap_poster).
    """
    key, uri = poster or (None, None)
    metas = {"tmdb-id": tmdb_id,
             "first-air-date": show.get("first_air_date"),
             "seasons": seasons_on_disk,
             "seasons-total": show.get("number_of_seasons"),
             "genres": layout.GENRE_SEP.join(g["name"] for g in show.get("genres") or [] if g.get("name")),
             "overview": show.get("overview"),
             "poster-key": key,
             "poster": uri}
    return "".join(f"<meta name='{nom}' content='{esc(valeur)}'>"
                   for nom, valeur in metas.items() if valeur not in (None, ""))


def read_head(path):
    """Texte d'une page jusqu'à son <style>, lu par morceaux ; '' si elle est illisible."""
    head = ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            while HEAD_END not in head:
                chunk = f.read(CHUNK)
                if not chunk:
                    break
                head += chunk
    except OSError:
        return ""
    return head.split(HEAD_END, 1)[0]


def _metas(head):
    return {nom: unescape(valeur) for nom, valeur in META_RE.findall(head)}


def recap_poster(recap):
    """{clé: data-URI} de l'affiche qu'une fiche existante porte déjà, pour le cache d'images."""
    metas = _metas(read_head(recap))
    key, uri = metas.get("poster-key"), metas.get("poster", "")
    return {key: uri} if key and uri.startswith("data:image/") else {}


def recap_tmdb_id(recap):
    """Identifiant TMDB qu'une fiche existante a retenu, ou None."""
    ident = _metas(read_head(recap)).get("tmdb-id", "")
    return ident if ident.isdigit() else None


@dataclass
class Entry:
    """Une série du sommaire, telle que sa fiche la décrit."""
    folder: str
    title: str
    year: str = ""
    seasons: int = 0
    seasons_total: int = 0
    poster: str = ""
    overview: str = ""
    page: str = PAGE_NAME
    genres: tuple = ()

    @property
    def href(self):
        """Lien relatif vers la fiche, encodé : les noms de séries ont des espaces, des accents, des #. Le sommaire est dans __Data__ : il remonte d'un cran."""
        return quote(f"../{self.folder}/{self.page}")

    @property
    def seasons_label(self):
        """'3 saisons', ou '2/5 saisons' quand TMDB en connaît plus que le disque n'en range."""
        if self.seasons and self.seasons_total and self.seasons < self.seasons_total:
            return f"{self.seasons}/{self.seasons_total} saisons"
        n = self.seasons or self.seasons_total
        return f"{n} saison{'s' if n > 1 else ''}" if n else ""


def _int(value):
    return int(value) if (value or "").isdigit() else 0


def read_entry(recap):
    """Entry décrite par une fiche, ou None si ce n'en est pas une.

    Une fiche écrite avant que les fiches portent ces <meta> n'a que son titre : elle figure quand même, sans affiche, jusqu'à ce qu'elle soit régénérée.
    """
    head = read_head(recap)
    title = TITLE_RE.search(head)
    if not title:
        return None
    metas = _metas(head)
    poster = metas.get("poster", "")
    return Entry(folder=Path(recap).parent.name, page=Path(recap).name, title=unescape(title.group(1)).strip(), year=metas.get("first-air-date", "")[:4], seasons=_int(metas.get("seasons")), seasons_total=_int(metas.get("seasons-total")), poster=poster if poster.startswith("data:image/") else "", overview=metas.get("overview", "").strip(), genres=tuple(g for g in metas.get("genres", "").split(layout.GENRE_SEP) if g))


def series_page(folder):
    """La fiche d'un dossier de série - index.html, à défaut l'ancien recap.html -, ou None s'il n'en a pas."""
    for name in (PAGE_NAME, LEGACY_NAME):
        page = Path(folder) / name
        if page.is_file():
            return page
    return None


def find_entries(root):
    """[Entry, ...] pour chaque sous-dossier de `root` qui contient une fiche."""
    entries = []
    try:
        subs = sorted(p for p in Path(root).iterdir() if p.is_dir() and not p.name.startswith(".") and p.name != DATA_DIR)
    except OSError:
        return []
    for sub in subs:
        recap = series_page(sub)
        if recap:
            entry = read_entry(recap)
            if entry:
                entries.append(entry)
    return entries


def anchor(folder):
    """Ancre de la vignette d'une série dans le sommaire, d'après le nom de son dossier : le retour depuis la fiche y ramène. Un condensé plutôt que le nom, plein d'espaces, d'accents et de #."""
    return "s" + hashlib.sha1(layout.fold(folder).encode("utf-8")).hexdigest()[:8]


def sort_key(title):
    """Clé de classement d'un titre : le titre tel qu'on le lit, article compris ("The Office" à T, "Les Motards de l'espace" à L), sans accents ni casse.

    Les articles ne sont pas retirés : un retrait par expression régulière prenait le "A" d'"Alien" pour un article, et rangeait Arcane après Reacher.
    """
    return layout.fold((title or "").strip())


def source_fragment(library_name, page):
    """Ce que le lien d'une vignette dit de son sommaire - son fichier et son titre - pour que la fiche sache où et comment revenir : « ← Anime » vers Anime.html, pas « ← Séries » vers tv_shows.html. Dans le lien plutôt que déduit de la page d'origine, que le navigateur ne donne pas toujours (file://)."""
    return "#" + urlencode({"i": page, "t": library_name}, quote_via=quote)


def build_html(library_name, entries, page=DEFAULT_INDEX):
    """Rend le sommaire (pur rendu : ni réseau ni disque). Classement par titre, article compris : "The Expanse" à T.

    Le résumé est coupé à trois lignes sous l'affiche : un résumé TMDB fait souvent plusieurs centaines de caractères, et en entier il rendrait la grille illisible. L'en-tête (titre, recherche, menu des genres, bouton de largeur, index A-Z) reste fixe en haut de page. `library_name` titre l'onglet et le h1 ; `page` est le nom du fichier du sommaire, que les fiches rappellent à leur retour."""
    cards = []
    source = source_fragment(library_name, page)
    genres = {}
    for entry in sorted(entries, key=lambda e: sort_key(e.title)):
        for genre in entry.genres:
            genres[genre] = genres.get(genre, 0) + 1
        img = (f"<img src='{entry.poster}' alt='' decoding='async' loading='lazy'>"
               if entry.poster else "<div class='noimg'></div>")
        meta = " · ".join(t for t in (entry.year, entry.seasons_label) if t)
        overview = f"<div class='o'>{esc(entry.overview)}</div>" if entry.overview else ""
        cards.append(f"<a id='{anchor(entry.folder)}' class='serie' href='{esc(entry.href + source)}' data-i='{layout.initial(sort_key(entry.title))}'{layout.genre_attr(entry.genres)}>"
                     f"<div class='aff'>{img}</div>"
                     f"<div class='t'>{esc(entry.title)}</div>"
                     f"<div class='y'>{esc(meta)}</div>{overview}</a>")

    return (
        "<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'>"
        f"{GENERATOR_META}{favicon.index_link()}"
        + layout.BOOT +
        f"<title>{esc(library_name)}</title>"
        "<style>"
        "body{font:16px/1.5 system-ui,sans-serif;margin:0;background:#14151a;color:#e8e8ea}"
        ".wrap{max-width:1180px;margin:0 auto;padding:32px}"
        "h1{margin:0 0 4px}.sub{color:#9aa0aa}"
        + layout.CSS +
        # Sept par ligne, comme les films ; sous 900 px, remplissage automatique, qui décide seul en pleine largeur.
        ".grid{display:grid;gap:18px;grid-template-columns:repeat(7,1fr)}"
        "@media(max-width:900px){.grid{grid-template-columns:repeat(auto-fill,minmax(120px,1fr))}}"
        ".wide .grid{grid-template-columns:repeat(auto-fill,minmax(148px,1fr))}"
        ".serie{display:block;color:inherit;text-decoration:none}"
        ".serie[hidden]{display:none}"
        ".serie .aff{aspect-ratio:2/3;border-radius:8px;overflow:hidden;"
        "background:#21232b;transition:transform .15s,box-shadow .15s}"
        ".serie:hover .aff,.serie:focus-visible .aff{transform:translateY(-3px);"
        "box-shadow:0 0 0 2px #7cc4ff}"
        ".serie:hover .t{color:#7cc4ff}"
        ".serie img,.serie .noimg{width:100%;height:100%;object-fit:cover;display:block}"
        ".serie .t{margin-top:8px;font-size:14px;font-weight:600;line-height:1.3}"
        ".serie .y{color:#9aa0aa;font-size:13px;font-variant-numeric:tabular-nums}"
        ".serie .o{margin-top:4px;color:#c7ccd4;font-size:12.5px;line-height:1.4;"
        "display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;line-clamp:3;"
        "overflow:hidden}"
        "</style></head><body>"
        + layout.header(
            f"<h1>{esc(library_name)}</h1>"
            f"<div class='sub'>{len(entries)} série(s)</div>"
            "<div class='bar'>"
            "<div class='line'>"
            "<input class='filter' type='search' placeholder='Filtrer…' aria-label='Filtrer les séries'>"
            + layout.genre_select(genres) + "</div>"
            + layout.mode_button() + "</div>"
            + layout.index_nav()) +
        f"<div class='grid'>{''.join(cards)}</div>"
        "<script>"
        "var f=document.querySelector('.filter');"
        "function n(s){return s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase()}"
        "f.oninput=function(){var q=n(f.value);"
        "document.querySelectorAll('.serie').forEach(function(c){"
        "c.hidden=(!!q&&n(c.querySelector('.t').textContent).indexOf(q)<0)||!gok(c)})};"
        + layout.genre_script() + layout.mode_script() + layout.index_script() +
        "</script></div></body></html>"
    )


def is_ours(path):
    """Vrai si `path` est un sommaire écrit par ce module."""
    head = read_head(path)
    return any(f"<meta name='generator' content='{name}'>" in head for name in (GENERATOR, *LEGACY_GENERATORS))


def index_name(title=None):
    """Nom du fichier du sommaire : le titre qu'on lui donne (« Anime » -> Anime.html), à défaut tv_shows.html."""
    return f"{safe_name(title) or Path(DEFAULT_INDEX).stem}.html" if title else DEFAULT_INDEX


def index_path(root, title=None):
    """Où écrire le sommaire : dans le dossier __Data__ de `root`."""
    return Path(root) / DATA_DIR / index_name(title)


def our_indexes(root):
    """Les sommaires que ce module a écrits dans le dossier __Data__ de `root`, quel que soit leur nom : un titre changé ou oublié n'en perd aucun."""
    try:
        return sorted(p for p in (Path(root) / DATA_DIR).glob("*.html") if p.is_file() and is_ours(p))
    except OSError:
        return []


def write(root, apply, title=None, out=None):
    """Réécrit le sommaire de `root` d'après les fiches présentes. Retourne le compte rendu à afficher.

    Il va dans __Data__, sous le nom de `title` (voir index_name) ou, avec `out`, sous ce chemin-là. Une page identique n'est pas réécrite : lancé toutes les heures sur un NAS, le sommaire ne doit ni réveiller les disques ni changer de date tant que la médiathèque ne bouge pas.

    Le titre est `title`, sinon celui du sommaire existant, sinon celui du sommaire que les versions précédentes écrivaient à la racine (index.html), sinon "Séries" - pas le nom du dossier, qui manque à la racine d'un partage réseau : la page n'avait alors aucun titre, et l'onglet affichait le nom du fichier.
    """
    out = Path(out) if out else index_path(root, title)
    entries = find_entries(root)
    legacy = Path(root) / LEGACY_INDEX
    previous = textfile.title_of(out) or (textfile.title_of(legacy) if is_ours(legacy) else None)
    html = build_html(title or previous or DEFAULT_TITLE, entries, out.name)
    if textfile.same(out, html):
        return f"{out.name} inchangé ({len(entries)} série(s))"
    if not apply:
        return f"écrirait {out.name} ({len(entries)} série(s))"
    out.parent.mkdir(exist_ok=True)
    textfile.write(out, html)
    missing = sum(1 for e in entries if not e.poster)
    return (f"{out.name} écrit ({len(entries)} série(s)"
            + (f", dont {missing} sans affiche : fiche à régénérer" if missing else "") + ")")
