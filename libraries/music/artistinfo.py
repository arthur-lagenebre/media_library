"""Ce que MusicBrainz et Wikipédia savent d'un artiste : type, pays, dates, membres du groupe, liens officiels, résumé.

Une seule fiche MusicBrainz suffit pour tout sauf le résumé : le type, le pays, les dates, les membres (relations d'artiste) et les liens (relations d'URL). Le résumé vient de Wikipédia, que MusicBrainz ne fait que désigner - par un identifiant Wikidata, qui dit en quelles langues l'article existe : on prend le français, à défaut l'anglais.

Ce qu'on garde est un petit dictionnaire JSON prêt à être montré : la médiathèque le range à côté de ses pages (artists.json) et n'y revient qu'une fois par mois.

Tout est pur, sauf `fetch` qui interroge le réseau par le client qu'on lui donne.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from .musicbrainz import MusicBrainzError

VERSION = 1
STALE_DAYS = 30                 # un groupe se reforme moins vite : au-delà, on redemande
MAX_MEMBERS = 40                # un orchestre en compte des centaines, la fiche n'est pas un annuaire
MAX_LINKS = 8
MAX_EXTRACT = 900               # caractères du résumé : de quoi situer l'artiste, pas son article entier
LANGS = ("fr", "en")            # les langues du résumé, par préférence

WIKIDATA_URL = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"
WIKIPEDIA_URL = "https://{}.wikipedia.org/api/rest_v1/page/summary/{}"
WIKIDATA_ID_RE = re.compile(r"/(Q\d+)$")
WIKIPEDIA_PAGE_RE = re.compile(r"^https?://([a-z-]+)\.wikipedia\.org/wiki/([^?#]+)")

TYPES = {"Group": "Groupe", "Person": "Artiste solo", "Orchestra": "Orchestre", "Choir": "Chœur", "Character": "Personnage"}
GROUPS = {"Group", "Orchestra", "Choir"}      # ceux qui ont des membres
NOT_A_ROLE = {"original"}                     # "membre d'origine" : MusicBrainz le note comme un instrument, ce n'en est pas un

# Les relations d'URL qu'on montre : les liens que l'artiste tient lui-même, ni les bases de données ni les boutiques. Le premier de la liste passe en premier sur la fiche.
LINK_TYPES = ("official homepage", "bandcamp", "social network", "youtube", "soundcloud", "streaming", "free streaming")
LINK_LABELS = {"official homepage": "Site officiel", "bandcamp": "Bandcamp", "youtube": "YouTube", "soundcloud": "SoundCloud"}
HOST_LABELS = {"facebook.com": "Facebook", "instagram.com": "Instagram", "twitter.com": "Twitter", "x.com": "X", "tiktok.com": "TikTok",
               "spotify.com": "Spotify", "deezer.com": "Deezer", "music.apple.com": "Apple Music", "bandcamp.com": "Bandcamp",
               "youtube.com": "YouTube", "soundcloud.com": "SoundCloud", "twitch.tv": "Twitch", "mastodon.social": "Mastodon"}


# ----------------------------------------------------------------------------
# Lecture d'une fiche MusicBrainz
# ----------------------------------------------------------------------------
def year(text):
    """'1993-05-02' -> '1993' ; '' si la date n'en dit pas."""
    found = re.match(r"\d{4}", text or "")
    return found.group(0) if found else ""


def _span(begin, end, ended):
    """(début, fin) en années, tels que MusicBrainz les donne pour une relation ou une vie."""
    return year(begin), year(end), bool(ended)


def host_label(url):
    """'Facebook' pour facebook.com, le nom de domaine à défaut."""
    host = (urlparse(url).hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host        # str.removeprefix n'existe qu'à partir de Python 3.9
    for known, label in HOST_LABELS.items():
        if host == known or host.endswith("." + known):
            return label
    return host


def _web(url):
    """L'adresse, si c'est bien un lien web : ce qu'une base ouverte contient ne doit jamais devenir un href 'javascript:'."""
    return url if urlparse(url or "").scheme in ("http", "https") and urlparse(url).hostname else ""


def links(data):
    """[{'label', 'url'}] : les liens que l'artiste tient lui-même, le site officiel d'abord."""
    found = []
    for rel in data.get("relations") or []:
        kind = rel.get("type")
        url = _web((rel.get("url") or {}).get("resource"))
        if kind in LINK_TYPES and url and all(url != f["url"] for f in found):
            found.append({"label": LINK_LABELS.get(kind) or host_label(url), "url": url, "rank": LINK_TYPES.index(kind)})
    found.sort(key=lambda f: f["rank"])
    return [{"label": f["label"], "url": f["url"]} for f in found[:MAX_LINKS]]


def members(data):
    """[{'name', 'mbid', 'begin', 'end', 'ended', 'roles'}] : les membres d'un groupe, les actuels d'abord.

    Un musicien qui a quitté le groupe puis l'a rejoint a deux relations : il n'a qu'une ligne, de sa première entrée à sa dernière sortie.
    """
    found = {}
    for rel in data.get("relations") or []:
        who = rel.get("artist") or {}
        if rel.get("type") != "member of band" or rel.get("direction") != "backward" or not who.get("id"):
            continue
        begin, end, ended = _span(rel.get("begin"), rel.get("end"), rel.get("ended"))
        roles = [a for a in rel.get("attributes") or [] if a and a not in NOT_A_ROLE]
        entry = found.get(who["id"])
        if entry is None:
            found[who["id"]] = {"name": who.get("name") or "", "mbid": who["id"], "begin": begin, "end": end, "ended": ended, "roles": roles}
            continue
        entry["begin"] = min(filter(None, (entry["begin"], begin)), default="")
        entry["ended"] = entry["ended"] and ended
        entry["end"] = "" if not entry["ended"] else max(entry["end"], end)
        entry["roles"] += [r for r in roles if r not in entry["roles"]]
    ranked = sorted(found.values(), key=lambda m: (m["ended"], m["begin"] or "9999", m["name"].casefold()))
    return ranked[:MAX_MEMBERS]


def parse(data):
    """Ce qu'une fiche MusicBrainz apprend de l'artiste, sans le résumé."""
    life = data.get("life-span") or {}
    begin, end, ended = _span(life.get("begin"), life.get("end"), life.get("ended"))
    kind = data.get("type") or ""
    return {
        "type": kind, "area": (data.get("area") or {}).get("name") or "",
        "begin": begin, "end": end, "ended": ended,
        "disambiguation": data.get("disambiguation") or "",
        "members": members(data) if kind in GROUPS else [],
        "links": links(data),
        "wiki": None,
    }


# ----------------------------------------------------------------------------
# Présentation
# ----------------------------------------------------------------------------
def lifespan(info):
    """'1993 – 2021', 'depuis 1993', 'né en 1970' : la vie de l'artiste en une expression, ou ''."""
    begin, end, ended = info.get("begin"), info.get("end"), info.get("ended")
    if begin and end:
        return f"{begin} – {end}"
    if begin and ended:
        return f"{begin} – ?"
    if begin:
        return f"né en {begin}" if info.get("type") == "Person" else f"depuis {begin}"
    return f"jusqu'en {end}" if end else ""


def facts(info):
    """'Groupe · France · 1993 – 2021'."""
    parts = (TYPES.get(info.get("type"), ""), info.get("area"), lifespan(info))
    return " · ".join(p for p in parts if p)


def period(member):
    """'1993 – 2001', 'depuis 1993' pour un membre ; '' sans date."""
    begin, end = member.get("begin"), member.get("end")
    if begin and end:
        return begin if begin == end else f"{begin} – {end}"
    if begin:
        return f"{begin} – ?" if member.get("ended") else f"depuis {begin}"
    return f"jusqu'en {end}" if end else ""


def shorten(text, limit=MAX_EXTRACT):
    """Le résumé coupé à la fin d'une phrase quand il dépasse `limit`."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[:end + 1] if end > limit // 2 else cut.rstrip() + "…"


# ----------------------------------------------------------------------------
# Wikipédia
# ----------------------------------------------------------------------------
def wiki_sources(data):
    """(identifiant Wikidata, (langue, titre) d'un article désigné directement) d'après les relations d'URL ; '' et None à défaut."""
    qid, direct = "", None
    for rel in data.get("relations") or []:
        url = (rel.get("url") or {}).get("resource") or ""
        if rel.get("type") == "wikidata" and WIKIDATA_ID_RE.search(url):
            qid = WIKIDATA_ID_RE.search(url).group(1)
        elif rel.get("type") == "wikipedia" and WIKIPEDIA_PAGE_RE.match(url):
            lang, title = WIKIPEDIA_PAGE_RE.match(url).groups()
            direct = (lang, unquote(title).replace("_", " "))
    return qid, direct


def _articles(client, qid, direct):
    """[(langue, titre)] des articles possibles, le français d'abord : ceux que Wikidata connaît, puis celui que MusicBrainz désigne."""
    found = []
    if qid:
        try:
            entities = client.external(WIKIDATA_URL.format(qid)).get("entities") or {}
        except MusicBrainzError as e:
            if e.code != 404:
                raise
            entities = {}
        sitelinks = next(iter(entities.values()), {}).get("sitelinks") or {}
        found = [(lang, sitelinks[f"{lang}wiki"]["title"]) for lang in LANGS if (sitelinks.get(f"{lang}wiki") or {}).get("title")]
    if direct and direct[0] not in [lang for lang, _ in found]:
        found.append(direct)
    return found


def summary(client, lang, title):
    """{'lang', 'title', 'url', 'extract'} d'un article, ou None s'il n'existe pas, renvoie à une page d'homonymes ou n'a pas de texte."""
    try:
        data = client.external(WIKIPEDIA_URL.format(lang, quote(title.replace(" ", "_"), safe="")))
    except MusicBrainzError as e:
        if e.code != 404:
            raise
        return None
    extract = shorten(data.get("extract"))
    if not extract or data.get("type") == "disambiguation":
        return None
    page = ((data.get("content_urls") or {}).get("desktop") or {}).get("page")
    url = _web(page) or f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'), safe='')}"
    return {"lang": lang, "title": data.get("title") or title, "url": url, "extract": extract}


def fetch(client, mbid):
    """Tout ce qu'on sait d'un artiste : sa fiche MusicBrainz, puis son résumé Wikipédia. MusicBrainzError si le réseau ou le serveur ne répond pas ; un artiste sans article n'en est pas une."""
    data = client.artist(mbid)
    info = parse(data)
    for lang, title in _articles(client, *wiki_sources(data)):
        info["wiki"] = summary(client, lang, title)
        if info["wiki"]:
            break
    return info


# ----------------------------------------------------------------------------
# Ce qu'on garde d'un passage à l'autre
# ----------------------------------------------------------------------------
def load(path):
    """{mbid: {'fetched': 'AAAA-MM-JJ', 'info': {...}}} du passage précédent, ou {}."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("version") != VERSION:
        return {}
    entries = data.get("artists")
    return {k: v for k, v in entries.items() if isinstance(v, dict) and isinstance(v.get("info"), dict)} if isinstance(entries, dict) else {}


def dump(entries):
    return json.dumps({"version": VERSION, "artists": entries}, ensure_ascii=False, indent=1, sort_keys=True)


def stale(entry, today=None):
    """Vrai si l'entrée date de plus de STALE_DAYS jours (ou n'a pas de date lisible)."""
    try:
        age = (today or date.today()) - date.fromisoformat(entry.get("fetched") or "")
    except (ValueError, TypeError):
        return True
    return age.days > STALE_DAYS
