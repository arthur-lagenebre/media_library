#!/usr/bin/env python3
r"""
Recap.py — Fiche HTML d'une médiathèque musicale, comme celle des films et des séries.

Les albums étiquetés par Metadata.py portent déjà tout ce qu'une fiche montre : titre, artiste, année, genres, label, numéros de piste et leurs totaux, identifiant MusicBrainz, pochette. Ce script les LIT - sans clé, sans rien écrire dans les fichiers - pour en faire une fiche de la médiathèque : un mur de pochettes groupé par artiste, une fiche par album et une par artiste. Seules ces dernières ont besoin du réseau, et seulement pour s'enrichir (voir plus bas).

Un album est un dossier qui contient des .flac ou des .mp3, lui ou ses dossiers de disque (CD1, CD2...) ; les dossiers d'artiste au-dessus ne font que ranger. Un artiste qui a plusieurs albums a sa section, les autres se rangent ensemble à la fin. Les dossiers dont le nom commence par "__", "#" ou "@" (__Data__, #recycle, @eaDir) sont ignorés.

Les fiches d'artiste, elles, complètent les tags avec ce que MusicBrainz et Wikipédia en disent : type, pays, dates, membres du groupe, liens officiels et un court résumé (en français, à défaut en anglais). Seuls les artistes dont les tags portent l'identifiant MusicBrainz (MUSICBRAINZ_ALBUMARTISTID, écrit par Metadata.py) sont concernés, à raison d'une requête par seconde - la règle de MusicBrainz. Les réponses sont gardées dans artists.json et redemandées au bout d'un mois : aux passages suivants, seuls les nouveaux artistes coûtent une requête. Sans réseau, le script abandonne après trois échecs d'affilée et garde ce qu'il avait ; --no-artist-info ne s'en sert jamais.

Les pistes qui manquent à un album viennent du total que les tags annoncent (TRACKTOTAL, DISCTOTAL), comparé aux numéros possédés : "Manque : pistes 3, 5-7 (sur 13)". Rien n'est dit d'un disque dont une piste n'a pas de numéro.

Tout est écrit dans --out (défaut : __Data__ à la racine de --dir, créé au besoin) :
  index.html     le sommaire : recherche (album, artiste, label, genre), filtre de genre, index A-Z
  Albums/        une fiche par album : pochette, artiste, année, label, genres, pistes et durées, pistes manquantes
  Artistes/      une fiche par artiste, où mène son nom : ses albums, et son lien MusicBrainz quand les tags en donnent l'identifiant
  artists.json   ce que MusicBrainz et Wikipédia ont dit des artistes : redemandé au bout d'un mois seulement
  catalog.json   ce qu'on a lu dans chaque fichier : au passage suivant, seules les pistes nouvelles ou modifiées sont rouvertes
  recap.log      le journal : les albums pas encore étiquetés, les pistes qui manquent, les fichiers illisibles

Usage :
  python Recap.py --dir "D:\Musique"                  # simulation : lit les fichiers, n'écrit que le journal si --out existe
  python Recap.py --dir "D:\Musique" --apply          # écrit la fiche dans D:\Musique\__Data__

Options : --apply --out --title --no-cache --no-artist-info --cover-width (défaut 480) --workers (défaut 8)

Aucune dépendance obligatoire, et aucune clé. Pillow (pip install pillow) réduit les pochettes ; sans lui, les pages montrent un monogramme à leur place. Le premier passage ouvre l'en-tête de chaque fichier ; les suivants ne rouvrent que ce qui a changé, et ne réécrivent pas une page déjà à jour : de quoi tourner chaque nuit sur le NAS sans réveiller les disques pour rien.
"""

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # pour importer libraries
from libraries.common import cli, layout, textfile, thumbs  # noqa: E402
from libraries.common.report import Report  # noqa: E402
from libraries.music import artistinfo, library, librarypage, player  # noqa: E402
from libraries.music.musicbrainz import MusicBrainz, MusicBrainzError  # noqa: E402
from libraries.music.tags import AudioError  # noqa: E402

DATA_DIR = "__Data__"
INDEX_NAME = "index.html"
CATALOG_NAME = "catalog.json"
ARTISTS_NAME = "artists.json"
LOG_NAME = "recap.log"
DEFAULT_TITLE = "Musique"
PROGRESS_EVERY = 500
PROGRESS_ARTISTS = 25
MAX_FAILURES = 3              # échecs d'affilée après lesquels on n'interroge plus : le réseau ne répond pas, pas la peine d'attendre chaque artiste
COVER_WIDTH = 480             # la fiche montre la pochette à 280 px : le double, pour un écran haute densité
INDEX_COVER_WIDTH = 200       # une pochette du sommaire en demande ~150 : le sommaire en porte des centaines
INDEX_COVER_QUALITY = 65


# ----------------------------------------------------------------------------
# 1. Lecture des tags
# ----------------------------------------------------------------------------
def read_infos(tracks, workers):
    """Lit les tags de chaque piste, en parallèle : sur un partage réseau, chaque en-tête paie son aller-retour."""
    if not tracks:
        return
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for _ in pool.map(library.read_info, tracks):
            done += 1
            if done % PROGRESS_EVERY == 0:
                print(f"  [lecture] {done}/{len(tracks)}")


# ----------------------------------------------------------------------------
# 2. Pages
# ----------------------------------------------------------------------------
def cover_uri(release, width):
    """Pochette réduite d'un album, en data-URI ; None s'il n'en a pas, qu'elle est illisible ou que Pillow manque."""
    track = release.cover_track
    if track is None:
        return None
    try:
        raw = library.read_cover(track)
    except AudioError:
        return None
    jpeg = thumbs.thumbnail(raw, width) if raw else None
    return thumbs.data_uri(jpeg) if jpeg else None


def media_base(folder, root):
    """Le chemin relatif d'une fiche d'album à la racine de la médiathèque, terminé par '/' : par là, la fiche joue les fichiers. None quand il n'y en a pas (autre lecteur Windows)."""
    try:
        return Path(os.path.relpath(root, folder)).as_posix().rstrip("/") + "/"
    except ValueError:
        return None


def write_release_page(release, folder, library_name, width, artists, base=None):
    """Écrit la fiche d'un album. Retourne (pochette, pochette extraite ?, page écrite ?). 'artists' = {id: Artist} de ceux qui auront leur fiche.

    La page précédente sert de cache : une pochette déjà dedans n'est pas rouverte. Une page déjà à jour n'est pas réécrite.
    """
    page = folder / librarypage.page_name(release)
    image = librarypage.read_embedded(page).get(release.key)
    fresh = False
    if image is None:
        image = cover_uri(release, width)
        fresh = bool(image)
    html = librarypage.build_release(release, image, f"../{INDEX_NAME}", library_name, artists.get(release.artist_id), base)
    written = not textfile.same(page, html)
    if written:
        textfile.write(page, html)
    return image, fresh, written


def pending(artists, entries, args):
    """Les identifiants MusicBrainz des artistes à interroger : ceux qu'on ne connaît pas encore, ou depuis plus d'un mois (tous, avec --no-cache)."""
    if args.no_artist_info:
        return []
    wanted = sorted({a.mbid for a in artists if a.mbid})
    return [m for m in wanted if args.no_cache or m not in entries or artistinfo.stale(entries[m])]


def update_artist_info(artists, path, args):
    """{mbid: {'fetched', 'info'}} de tous les artistes connus, après avoir demandé à MusicBrainz et à Wikipédia ceux qui manquent.

    Un artiste dont la fiche n'existe plus (404) est noté sans rien dire, pour ne pas être redemandé à chaque passage. Une panne ne perd rien : ce qu'on savait déjà reste, et le passage suivant reprendra où celui-ci s'est arrêté.
    """
    entries = artistinfo.load(path)
    todo = pending(artists.values(), entries, args)
    if not todo:
        return entries
    names = {a.mbid: a.name for a in artists.values() if a.mbid}
    print(f"  [artistes] {len(todo)} artiste(s) a demander a MusicBrainz et Wikipedia (environ {max(1, round(len(todo) * 1.5 / 60))} min)")
    client, failures, fetched = MusicBrainz(), 0, 0
    try:
        for done, mbid in enumerate(todo, 1):
            try:
                entries[mbid] = {"fetched": date.today().isoformat(), "info": artistinfo.fetch(client, mbid)}
                failures, fetched = 0, fetched + 1
            except MusicBrainzError as e:
                print(f"  [artistes] {names[mbid]} : {e}")
                if e.code == 404:
                    entries[mbid] = {"fetched": date.today().isoformat(), "info": {}}
                    failures = 0
                else:
                    failures += 1
                    if failures >= MAX_FAILURES:
                        print(f"  [artistes] {MAX_FAILURES} echecs d'affilee : abandon, le reste au prochain passage")
                        break
            if done % PROGRESS_ARTISTS == 0:
                print(f"  [artistes] {done}/{len(todo)}")
    finally:                                   # même interrompu (Ctrl-C), ce qu'on a obtenu est gardé
        text = artistinfo.dump(entries)
        if not textfile.same(path, text):
            textfile.write(path, text)
    print(f"  [artistes] {fetched} fiche(s) obtenue(s) sur {len(todo)}")
    return entries


def write_artist_pages(artists, entries, covers, pages, out, library_name):
    """Écrit la fiche de chaque artiste, d'après les pochettes déjà réduites des albums et ce qu'on sait de lui. Retourne ({id: Artist} de ceux dont la fiche existe, nombre de fiches écrites)."""
    folder = out / librarypage.ARTIST_DIR
    folder.mkdir(parents=True, exist_ok=True)
    done, written = {}, 0
    for artist in artists.values():
        page = folder / librarypage.artist_page_name(artist)
        html = librarypage.build_artist(artist, covers, f"../{INDEX_NAME}", library_name, pages, (entries.get(artist.mbid) or {}).get("info"))
        try:
            if not textfile.same(page, html):
                textfile.write(page, html)
                written += 1
        except OSError as e:
            print(f"  [artistes] {page.name} non ecrite : {e}")
            continue
        done[artist.id] = artist
    print(f"  [artistes] {len(done)} fiche(s) dans {folder.name}/ ({written} ecrite(s), {len(done) - written} inchangee(s))")
    return done, written


def write_shell(path, library_name):
    """Écrit la coque qui garde la lecture en vie d'une fiche à l'autre : le sommaire dans une iframe, au-dessus d'une barre de lecture."""
    html = player.build_shell(library_name, INDEX_NAME)
    if textfile.same(path, html):
        print(f"  [lecteur] {path} inchange")
    else:
        textfile.write(path, html)
        print(f"  [lecteur] {path} ecrit  (ouvrir celle-ci pour naviguer sans couper la musique)")


def write_pages(sections, out, root, args):
    """Écrit la fiche de chaque album, celle de chaque artiste, puis le sommaire. Retourne le nombre de fiches d'albums écrites.

    Une fiche qu'on n'a pas pu écrire n'est pas rendue au sommaire, pour qu'il ne mène pas à rien. Les fiches d'albums ou d'artistes sortis de la médiathèque restent sur le disque : plus rien n'y mène, et les effacer n'est pas à ce script de décider.
    """
    folder = out / librarypage.DIR
    folder.mkdir(parents=True, exist_ok=True)
    base = None if args.no_player else media_base(folder, root)
    index = out / INDEX_NAME
    library_name = args.title or textfile.title_of(index) or DEFAULT_TITLE
    if not thumbs.available():
        print("  [pochettes] Pillow absent : les pages montrent un monogramme a la place (pip install pillow)")

    every = [r for _, releases in sections for r in releases]
    # Les albums d'artiste inconnu n'ont rien en commun : ils n'ont pas de fiche à eux.
    artists = {a.id: a for a in library.artists(every) if a.name != library.UNKNOWN_ARTIST}
    entries = update_artist_info(artists, out / ARTISTS_NAME, args)
    # Les albums les plus fournis d'abord : sinon le dernier, seul sur un fil, fait attendre tous les autres.
    queue = sorted(every, key=lambda r: -len(r.tracks))

    def build(release):
        try:
            return release, write_release_page(release, folder, library_name, args.cover_width, artists, base)
        except OSError as e:
            print(f"  [pages] {librarypage.page_name(release)} non ecrite : {e}")
            return release, None

    covers, pages, written, fresh = {}, set(), 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for done, (release, result) in enumerate(pool.map(build, queue), 1):
            if result is not None:
                image, extracted, was_written = result
                pages.add(release.id)
                written += was_written
                fresh += extracted
                if image:
                    covers[release.id] = thumbs.shrink_uri(image, INDEX_COVER_WIDTH, INDEX_COVER_QUALITY) or image
            if done % 100 == 0:
                print(f"  [pages] {done}/{len(queue)}")
    print(f"  [pages] {len(pages)} fiche(s) dans {folder.name}/ ({written} ecrite(s), {len(pages) - written} inchangee(s)), {fresh} pochette(s) extraite(s)")

    artists, _ = write_artist_pages(artists, entries, covers, pages, out, library_name)

    html = librarypage.build_index(library_name, sections, covers, pages, artists)
    if textfile.same(index, html):
        print(f"  [sommaire] {index} inchange")
    else:
        textfile.write(index, html)
        print(f"  [sommaire] {index} ecrit  ({len(html) / 1_048_576:.1f} Mo, {len(covers)} pochette(s) integree(s))")
    if base is not None:
        write_shell(out / player.SHELL_NAME, library_name)
    return written


# ----------------------------------------------------------------------------
# 3. Bilan, journal
# ----------------------------------------------------------------------------
def summarize(releases):
    """Affiche le compte de la médiathèque et retourne le Report : pistes vues, pistes étiquetées par MusicBrainz, fichiers illisibles."""
    tracks = [t for r in releases for t in r.tracks]
    report = Report(matched=sum(1 for t in tracks if t.info.get("mbid")), total=len(tracks), failures=sum(1 for t in tracks if t.error))
    artists = {layout.fold(r.artist) for r in releases}
    print(f"  {len(releases)} album(s), {len(artists)} artiste(s), {len(tracks)} piste(s), {report.matched} etiquetee(s)" + (f", {report.failures} illisible(s)" if report.failures else ""))
    return report


def write_log(path, root, releases, args, report):
    """Écrit le journal : le bilan, puis les albums à regarder - pas encore étiquetés, pistes manquantes, fichiers illisibles, formats non pris en charge."""
    untagged = [r for r in releases if r.tagged < len(r.tracks)]
    gaps = [r for r in releases if r.missing()]
    broken = [t for r in releases for t in r.tracks if t.error]
    other = [r for r in releases if r.unsupported]
    lines = [f"# Music/Recap.py - {Path(root).resolve()}",
             f"# {datetime.now():%Y-%m-%d %H:%M} - {cli.mode_label(args)}",
             f"# {report.matched}/{report.total} piste(s) etiquetee(s) par MusicBrainz", ""]
    if untagged:
        lines.append(f"# --- {len(untagged)} album(s) pas (entierement) etiquete(s) : lance Metadata.py ---")
        lines += [f"[NON ETIQUETE] {r.rel or r.folder.name} ({r.tagged}/{len(r.tracks)})" for r in untagged]
        lines.append("")
    if gaps:
        lines.append(f"# --- {len(gaps)} album(s) auxquels il manque des pistes ---")
        for release in gaps:
            for disc, lacking, total in release.missing():
                lines.append(f"[MANQUE] {release.rel or release.folder.name} : disque {disc}, piste(s) {layout.ranges(lacking)} (sur {total})")
        lines.append("")
    if broken:
        lines.append(f"# --- {len(broken)} fichier(s) illisible(s) ---")
        lines += [f"[ILLISIBLE] {t.rel} : {t.error}" for t in broken]
        lines.append("")
    if other:
        lines.append(f"# --- {len(other)} album(s) avec des fichiers que seuls .flac et .mp3 couvrent ---")
        lines += [f"[NON PRIS EN CHARGE] {r.rel or r.folder.name} : {', '.join(r.unsupported[:3])}" + (" ..." if len(r.unsupported) > 3 else "") for r in other]
        lines.append("")
    try:
        textfile.write(path, "\n".join(lines) + "\n")
    except OSError as e:
        print(f"[log] {path.name} non ecrit : {e}")
        return
    print(f"[log] {path.name} ecrit")


# ----------------------------------------------------------------------------
# 4. Programme principal
# ----------------------------------------------------------------------------
def parse_args():
    ap = argparse.ArgumentParser(description="Fiche HTML d'une mediatheque musicale (albums .flac et .mp3 etiquetes).")
    ap.add_argument("--dir", required=True, help="Mediatheque : un dossier par album, ranges ou non par artiste")
    ap.add_argument("--out", help=f"Ou ecrire la fiche (defaut : {DATA_DIR} a la racine de --dir)")
    ap.add_argument("--title", help=f"Titre de la fiche (defaut : celui de la fiche existante, sinon '{DEFAULT_TITLE}')")
    ap.add_argument("--apply", action="store_true", help="Ecrit reellement la fiche (defaut : simulation)")
    ap.add_argument("--no-cache", action="store_true", help="Rouvre toutes les pistes, sans reprendre le catalogue, et redemande tous les artistes")
    ap.add_argument("--no-artist-info", action="store_true", help="N'interroge ni MusicBrainz ni Wikipedia : les fiches d'artiste n'ont que ce qu'on savait deja")
    ap.add_argument("--no-player", action="store_true", help="Les fiches d'album ne lisent pas les pistes (utile si elles sont copiees sans la musique)")
    ap.add_argument("--cover-width", type=int, default=COVER_WIDTH, help=f"Largeur des pochettes des fiches en pixels (defaut : {COVER_WIDTH})")
    ap.add_argument("--workers", type=int, default=8, help="Pistes lues en parallele (defaut : 8)")
    args = ap.parse_args()
    if args.workers < 1 or args.cover_width < 1:
        ap.error("--workers et --cover-width attendent un entier positif")
    return args


def main():
    args = parse_args()
    cli.setup_console()
    root = cli.check_dir(args.dir)
    out = Path(args.out) if args.out else root / DATA_DIR
    print(f"=== {cli.mode_label(args, 'rien ne sera ecrit que le journal ; ajoute --apply pour ecrire la fiche')} ===   sortie : {out}\n")

    releases = library.scan(root)
    tracks = [t for r in releases for t in r.tracks]
    if not tracks:
        print(f"Aucun .flac ni .mp3 trouve dans : {root}")
        return 0

    todo = tracks if args.no_cache else library.apply_catalog(tracks, library.load_catalog(out / CATALOG_NAME))
    print(f"{len(tracks)} piste(s), {len(tracks) - len(todo)} reprise(s) du catalogue, {len(todo)} a lire")
    read_infos(todo, args.workers)

    print()
    report = summarize(releases)
    print()

    sections = library.sections(releases)
    if args.apply:
        out.mkdir(parents=True, exist_ok=True)
        catalog = library.dump_catalog(tracks)
        if not textfile.same(out / CATALOG_NAME, catalog):
            textfile.write(out / CATALOG_NAME, catalog)
        write_pages(sections, out, root, args)
    else:
        print(f"  [fiche] ecrirait {out / INDEX_NAME}, une fiche par album dans {librarypage.DIR}/ et une par artiste dans {librarypage.ARTIST_DIR}/")
        asked = pending(library.artists(releases), artistinfo.load(out / ARTISTS_NAME), args)
        if asked:
            print(f"  [artistes] interrogerait MusicBrainz et Wikipedia sur {len(asked)} artiste(s)")
    if out.is_dir():
        write_log(out / LOG_NAME, root, releases, args, report)

    print(f"\nTOTAL : {report.matched}/{report.total} piste(s) etiquetee(s) par MusicBrainz.")
    if report.failures:
        print(f"\nA CORRIGER : {report.failures} fichier(s) illisible(s) (voir {LOG_NAME}).")
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
