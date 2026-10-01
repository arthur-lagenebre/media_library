"""Sommaire des séries d'une médiathèque, construit à partir de leurs fiches.

Chaque fiche recap.html porte dans son en-tête de quoi la présenter : titre, année, saisons, et l'affiche encodée. Le sommaire n'est donc que la lecture de ces en-têtes - ni TMDB, ni réseau, ni dépendance -, assez léger pour tourner en tâche planifiée sur le NAS qui héberge la médiathèque : les fiches sont souvent écrites ailleurs, sur un disque local, puis transférées, et seul le NAS voit la médiathèque entière.

Un index.html qui n'a pas été écrit par ce module n'est jamais remplacé.
"""

import re
import unicodedata
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

from . import favicon

INDEX_NAME = "index.html"
RECAP_NAME = "recap.html"

# Signe qu'un index.html est bien le nôtre, et peut être réécrit sans demander.
GENERATOR = "mkv_editors-index"
GENERATOR_META = f"<meta name='generator' content='{GENERATOR}'>"

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

    @property
    def href(self):
        """Lien relatif vers la fiche, encodé : les noms de séries ont des espaces, des accents, des #."""
        return quote(f"{self.folder}/{RECAP_NAME}")

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
    return Entry(folder=Path(recap).parent.name, title=unescape(title.group(1)).strip(), year=metas.get("first-air-date", "")[:4], seasons=_int(metas.get("seasons")), seasons_total=_int(metas.get("seasons-total")), poster=poster if poster.startswith("data:image/") else "", overview=metas.get("overview", "").strip())


def find_entries(root):
    """[Entry, ...] pour chaque sous-dossier de `root` qui contient une fiche."""
    entries = []
    try:
        subs = sorted(p for p in Path(root).iterdir() if p.is_dir() and not p.name.startswith("."))
    except OSError:
        return []
    for sub in subs:
        recap = sub / RECAP_NAME
        if recap.is_file():
            entry = read_entry(recap)
            if entry:
                entries.append(entry)
    return entries


# Articles ignorés au classement, comme sur une étagère.
ARTICLE_RE = re.compile(r"^(?:the|a|an|le|la|les|l')\s*(?=\w)", re.IGNORECASE)


def sort_key(title):
    """Clé de classement d'un titre : sans article en tête, sans accents, sans casse."""
    plain = unicodedata.normalize("NFD", title or "")
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return ARTICLE_RE.sub("", plain.strip()).casefold()


def build_html(library_name, entries):
    """Rend le sommaire (pur rendu : ni réseau ni disque). Classement par titre, "The Expanse" à E.

    Le résumé est coupé à trois lignes sous l'affiche, et donné en entier au survol : un résumé TMDB fait souvent plusieurs centaines de caractères, et en entier il rendrait la grille illisible."""
    cards = []
    for entry in sorted(entries, key=lambda e: sort_key(e.title)):
        img = (f"<img src='{entry.poster}' alt='' decoding='async' loading='lazy'>"
               if entry.poster else "<div class='noimg'></div>")
        meta = " · ".join(t for t in (entry.year, entry.seasons_label) if t)
        resume = f"<div class='o'>{esc(entry.overview)}</div>" if entry.overview else ""
        survol = f" title='{esc(entry.overview)}'" if entry.overview else ""
        cards.append(f"<a class='serie' href='{esc(entry.href)}'{survol}>"
                     f"<div class='aff'>{img}</div>"
                     f"<div class='t'>{esc(entry.title)}</div>"
                     f"<div class='y'>{esc(meta)}</div>{resume}</a>")

    return (
        "<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'>"
        f"{GENERATOR_META}{favicon.index_link()}"
        f"<title>{esc(library_name)}</title>"
        "<style>"
        "body{font:16px/1.5 system-ui,sans-serif;margin:0;background:#14151a;color:#e8e8ea}"
        ".wrap{max-width:1180px;margin:0 auto;padding:32px}"
        "h1{margin:0 0 4px}.sub{color:#9aa0aa;margin-bottom:12px}"
        ".filter{width:100%;max-width:320px;margin:10px 0 26px;padding:8px 14px;font:inherit;"
        "font-size:14px;color:#e8e8ea;background:#1c1e26;border:1px solid #2a2c34;"
        "border-radius:999px;outline:none;box-sizing:border-box}"
        ".filter:focus{border-color:#7cc4ff}"
        ".grid{display:grid;gap:18px;grid-template-columns:repeat(auto-fill,minmax(172px,1fr))}"
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
        "</style></head><body><div class='wrap'>"
        f"<h1>{esc(library_name)}</h1>"
        f"<div class='sub'>{len(entries)} série(s)</div>"
        "<input class='filter' type='search' placeholder='Filtrer…' aria-label='Filtrer les séries'>"
        f"<div class='grid'>{''.join(cards)}</div>"
        "<script>"
        "var f=document.querySelector('.filter');"
        "function n(s){return s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase()}"
        "f.oninput=function(){var q=n(f.value);"
        "document.querySelectorAll('.serie').forEach(function(c){"
        "c.hidden=!!q&&n(c.querySelector('.t').textContent).indexOf(q)<0})};"
        "</script></div></body></html>"
    )


def is_ours(path):
    """Vrai si `path` est un sommaire écrit par ce module."""
    return GENERATOR_META in read_head(path)


def write(root, apply):
    """Réécrit le sommaire de `root` d'après les fiches présentes. Retourne le compte rendu à afficher.

    Une page identique n'est pas réécrite : lancé toutes les heures sur un NAS, le sommaire ne doit ni réveiller les disques ni changer de date tant que la médiathèque ne bouge pas.
    """
    out = Path(root) / INDEX_NAME
    entries = find_entries(root)
    html = build_html(Path(root).resolve().name, entries)
    try:
        unchanged = out.read_text(encoding="utf-8") == html
    except (OSError, UnicodeDecodeError):
        unchanged = False
    if unchanged:
        return f"{out.name} inchange ({len(entries)} serie(s))"
    if not apply:
        return f"ecrirait {out.name} ({len(entries)} serie(s))"
    out.write_text(html, encoding="utf-8")
    sans = sum(1 for e in entries if not e.poster)
    return (f"{out.name} ecrit ({len(entries)} serie(s)"
            + (f", dont {sans} sans affiche : fiche a regenerer" if sans else "") + ")")
