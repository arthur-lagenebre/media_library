#!/usr/bin/env python3
r"""
Recap.py — Fiche HTML d'une bibliothèque de livres, BD, comics et mangas.

Les livres portent déjà leur fiche : ComicInfo.xml dans un .cbz, le .opf d'un .epub (Calibre). Ce script la LIT - sans réseau, sans clé, sans rien écrire dans les livres - pour en faire une fiche de la bibliothèque, comme celle des films : un sommaire par section (Manga, BD, Comics, Romans...), une vignette par série, et une page par série avec ses couvertures, son résumé, ses auteurs et les tomes qui manquent.

Une série est un dossier de section : Manga/20th Century Boys/, BD/Megalex/. Pour les romans c'est l'auteur. Un fichier posé seul dans une section (Manuels/Un guide.epub) est sa propre série, et ceux de la racine forment la section "Autres". Les sous-dossiers d'une série (cycles, intégrales) en groupent les volumes à l'affichage.

Les tomes manquants viennent du champ Count des fiches ("37" : la série compte 37 tomes) comparé aux numéros possédés. Rien n'est dit d'une série dont un volume n'a pas de numéro.

Les .pdf sont ignorés : ils n'ont ni fiche ni couverture à lire. --include-pdf les ajoute, avec un monogramme et le titre de leur nom de fichier.

Tout est écrit dans --out (défaut : __Data__ à la racine de --dir, créé au besoin) :
  index.html     le sommaire, avec une zone de recherche (titre, auteur, éditeur, genre)
  Series/        une page par série
  catalog.json   ce qu'on a lu dans chaque livre : au passage suivant, seuls les livres nouveaux ou modifiés sont rouverts
  recap.log      le journal : les livres sans fiche et les fichiers illisibles

Usage :
  python Recap.py --dir "\\TRUENAS\Livres"                   # simulation : lit les livres, n'écrit que le journal si --out existe
  python Recap.py --dir "\\TRUENAS\Livres" --apply           # écrit la fiche dans \\TRUENAS\Livres\__Data__

Options : --apply --out --title --include-pdf --no-cache --cover-width (défaut 240) --workers (défaut 8)

Aucune dépendance obligatoire. Pillow (pip install pillow) réduit les couvertures ; sans lui, les pages montrent un monogramme à leur place. Le premier passage ouvre chaque archive - un quart d'heure pour 9000 .cbz sur un partage réseau - ; les suivants ne rouvrent que ce qui a changé, et ne réécrivent pas une page déjà à jour : de quoi tourner chaque nuit sur le NAS sans réveiller les disques pour rien.
"""

import argparse
import base64
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # pour importer libraries
from libraries.common import cli, textfile  # noqa: E402
from libraries.common.report import Report  # noqa: E402
from libraries.books import shelf, shelfpage, thumbs  # noqa: E402
from libraries.books.archive import BookError  # noqa: E402

DATA_DIR = "__Data__"
INDEX_NAME = "index.html"
CATALOG_NAME = "catalog.json"
LOG_NAME = "recap.log"
DEFAULT_TITLE = "Livres"
PROGRESS_EVERY = 500
INDEX_COVER_WIDTH = 180       # une vignette du sommaire en demande ~150 : le sommaire en porte mille cinq cents, et pesait 34 Mo avec les couvertures des pages
INDEX_COVER_QUALITY = 65


# ----------------------------------------------------------------------------
# 1. Lecture des fiches
# ----------------------------------------------------------------------------
def read_infos(volumes, workers):
    """Lit la fiche de chaque volume, en parallèle : sur un partage réseau, chaque archive paie son aller-retour."""
    if not volumes:
        return
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for _ in pool.map(shelf.read_info, volumes):
            done += 1
            if done % PROGRESS_EVERY == 0:
                print(f"  [lecture] {done}/{len(volumes)}")


# ----------------------------------------------------------------------------
# 2. Pages
# ----------------------------------------------------------------------------
def cover_uri(volume, width):
    """Couverture réduite d'un volume, en data-URI ; None si le format n'en a pas, qu'elle est illisible ou que Pillow manque."""
    try:
        raw = shelf.read_cover(volume)
    except BookError:
        return None
    jpeg = thumbs.thumbnail(raw, width) if raw else None
    return shelfpage.data_uri(jpeg) if jpeg else None


def index_cover(uri):
    """Version réduite, pour le sommaire, de la couverture d'une page (data-URI). Sans Pillow, ou si elle est illisible, la couverture de la page fait l'affaire."""
    try:
        small = thumbs.thumbnail(base64.b64decode(uri.split(",", 1)[1]), INDEX_COVER_WIDTH, INDEX_COVER_QUALITY)
    except (ValueError, IndexError):
        small = None
    return shelfpage.data_uri(small) if small else uri


def write_series_page(series, folder, library_name, width):
    """Écrit la page d'une série. Retourne (couverture de la série, couvertures extraites, page écrite ?).

    La page précédente sert de cache : une couverture déjà dedans n'est pas rouverte. Une page déjà à jour n'est pas réécrite.
    """
    page = folder / shelfpage.page_name(series)
    known = shelfpage.read_embedded(page)
    images, fresh = {}, 0
    for volume in series.volumes:
        if volume.key in known:
            images[volume.key] = known[volume.key]
            continue
        uri = cover_uri(volume, width)
        if uri:
            images[volume.key] = uri
            fresh += 1
    html = shelfpage.build_series(series, images, f"../{INDEX_NAME}", library_name)
    written = not textfile.same(page, html)
    if written:
        textfile.write(page, html)
    return images.get(series.cover_volume.key), fresh, written


def write_pages(sections, out, args):
    """Écrit la page de chaque série puis le sommaire. Retourne le nombre de pages écrites.

    Une page qu'on n'a pas pu écrire n'est pas rendue au sommaire, pour qu'il ne mène pas à rien. Les pages de séries sorties de la bibliothèque restent sur le disque : plus rien n'y mène, et les effacer n'est pas à ce script de décider.
    """
    folder = out / shelfpage.DIR
    folder.mkdir(parents=True, exist_ok=True)
    index = out / INDEX_NAME
    library_name = args.title or textfile.title_of(index) or DEFAULT_TITLE
    if not thumbs.available():
        print("  [couvertures] Pillow absent : les pages montrent un monogramme a la place (pip install pillow)")

    every = [s for _, series_list in sections for s in series_list]
    # Les séries les plus fournies d'abord : sinon la dernière, seule sur un fil, fait attendre tous les autres.
    queue = sorted(every, key=lambda s: -len(s.volumes))

    def build(series):
        try:
            return series, write_series_page(series, folder, library_name, args.cover_width)
        except OSError as e:
            print(f"  [pages] {shelfpage.page_name(series)} non ecrite : {e}")
            return series, None

    covers, pages, written, fresh = {}, set(), 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for done, (series, result) in enumerate(pool.map(build, queue), 1):
            if result is not None:
                cover, extracted, was_written = result
                pages.add(series.id)
                written += was_written
                fresh += extracted
                if cover:
                    covers[series.id] = index_cover(cover)
            if done % 100 == 0:
                print(f"  [pages] {done}/{len(queue)}")
    print(f"  [pages] {len(pages)} page(s) dans {folder.name}/ ({written} ecrite(s), {len(pages) - written} inchangee(s)), {fresh} couverture(s) extraite(s)")

    html = shelfpage.build_index(library_name, sections, covers, pages)
    if textfile.same(index, html):
        print(f"  [sommaire] {index} inchange")
    else:
        textfile.write(index, html)
        print(f"  [sommaire] {index} ecrit  ({len(html) / 1_048_576:.1f} Mo, {len(covers)} couverture(s) integree(s))")
    return written


# ----------------------------------------------------------------------------
# 3. Bilan, journal
# ----------------------------------------------------------------------------
def summarize(sections):
    """Affiche le compte de chaque section et retourne le Report : volumes vus, volumes avec fiche, fichiers illisibles."""
    report = Report()
    for name, series_list in sections:
        volumes = [v for s in series_list for v in s.volumes]
        tagged = sum(1 for v in volumes if v.info)
        broken = sum(1 for v in volumes if v.error)
        report += Report(matched=tagged, total=len(volumes), failures=broken)
        print(f"  {name:<28} {len(series_list):>5} serie(s) {len(volumes):>6} volume(s) {tagged:>6} avec fiche" + (f"  {broken} illisible(s)" if broken else ""))
    return report


def write_log(path, root, sections, args, report):
    """Écrit le journal : le bilan, puis par section les livres sans fiche et les fichiers illisibles."""
    lines = [f"# Books/Recap.py - {Path(root).resolve()}",
             f"# {datetime.now():%Y-%m-%d %H:%M} - {cli.mode_label(args)}",
             f"# {report.matched}/{report.total} livre(s) avec fiche", ""]
    for name, series_list in sections:
        volumes = [v for s in series_list for v in s.volumes]
        bare = [v for v in volumes if not v.info and not v.error]
        broken = [v for v in volumes if v.error]
        if not bare and not broken:
            continue
        lines.append(f"# --- {name} : {len(bare)} sans fiche, {len(broken)} illisible(s) ---")
        lines += [f"[SANS FICHE] {v.rel}" for v in bare]
        lines += [f"[ILLISIBLE] {v.rel} : {v.error}" for v in broken]
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
    ap = argparse.ArgumentParser(description="Fiche HTML d'une bibliotheque de livres, BD, comics et mangas.")
    ap.add_argument("--dir", required=True, help="Bibliotheque : un dossier par section (Manga, BD, Romans...)")
    ap.add_argument("--out", help=f"Ou ecrire la fiche (defaut : {DATA_DIR} a la racine de --dir)")
    ap.add_argument("--title", help=f"Titre de la fiche (defaut : celui de la fiche existante, sinon '{DEFAULT_TITLE}')")
    ap.add_argument("--apply", action="store_true", help="Ecrit reellement la fiche (defaut : simulation)")
    ap.add_argument("--include-pdf", action="store_true", help="Compte aussi les .pdf (ignores par defaut : ni fiche ni couverture)")
    ap.add_argument("--no-cache", action="store_true", help="Rouvre tous les livres, sans reprendre le catalogue")
    ap.add_argument("--cover-width", type=int, default=thumbs.WIDTH, help=f"Largeur des couvertures en pixels (defaut : {thumbs.WIDTH})")
    ap.add_argument("--workers", type=int, default=8, help="Livres lus en parallele (defaut : 8)")
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

    sections = shelf.scan(root, include_pdf=args.include_pdf)
    volumes = [v for _, series_list in sections for s in series_list for v in s.volumes]
    if not volumes:
        print(f"Aucun livre trouve dans : {root}")
        return 0

    todo = volumes if args.no_cache else shelf.apply_catalog(volumes, shelf.load_catalog(out / CATALOG_NAME))
    print(f"{len(volumes)} livre(s), {len(volumes) - len(todo)} repris du catalogue, {len(todo)} a lire")
    read_infos(todo, args.workers)

    print()
    report = summarize(sections)
    print()

    if args.apply:
        out.mkdir(parents=True, exist_ok=True)
        catalog = shelf.dump_catalog(volumes)
        if not textfile.same(out / CATALOG_NAME, catalog):
            textfile.write(out / CATALOG_NAME, catalog)
        write_pages(sections, out, args)
    else:
        print(f"  [fiche] ecrirait {out / INDEX_NAME} et une page par serie dans {shelfpage.DIR}/")
    if out.is_dir():
        write_log(out / LOG_NAME, root, sections, args, report)

    print(f"\nTOTAL : {report.matched}/{report.total} livre(s) avec fiche.")
    if report.failures:
        print(f"\nA CORRIGER : {report.failures} fichier(s) illisible(s) (voir {LOG_NAME}).")
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
