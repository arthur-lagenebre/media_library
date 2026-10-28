#!/usr/bin/env python3
r"""
Cover.py — Embarque dans les pistes la pochette posée dans le dossier de chaque album, et rien d'autre.

Un fichier "cover.jpg" (ou .jpeg, .png ; aussi "folder", "front", "album", "albumart", casse libre) dans le dossier d'un album est LA pochette de cet album : elle l'emporte sur celle que portent déjà les pistes - un scan recto-verso, une image mal cadrée - comme sur celle de Cover Art Archive. La fiche de la médiathèque (Recap.py) la lit directement. Ce script, lui, la recopie dans chaque .flac et .mp3 de l'album, pour que l'Explorateur de Windows, les lecteurs et les téléphones l'affichent aussi.

Il ne touche à aucun tag : ni titre, ni genre, ni identifiant. Il n'a pas besoin d'Internet : MusicBrainz n'est pas interrogé. Une piste qui porte déjà exactement cette image n'est pas réécrite, une autre image de face est remplacée, et les images d'un autre type (dos, livret...) sont gardées.

Un album sans fichier cover est listé à la fin, pour savoir où en poser un. Le fichier cover d'un album en plusieurs disques se pose à la racine de l'album, à côté de CD1, CD2... Seuls le JPEG et le PNG s'embarquent ; un .webp, .gif ou .bmp sert à la fiche mais pas aux pistes (signalé). L'Explorateur de Windows ne lit rien d'un en-tête .flac de plus de 4 Mio : une image qui le fait dépasser est signalée.

--extract fait le chemin inverse, pour les albums déjà étiquetés dont les pistes portent une pochette mais dont le dossier n'a pas de fichier : il écrit cette pochette en cover.jpg (ou cover.png, selon l'image) dans le dossier de l'album. Un fichier cover existant n'est jamais remplacé, et les pistes ne sont pas touchées. C'est le point de départ pour corriger : extraire, ouvrir les cover.jpg, remplacer à la main les mauvaises (recto-verso, mal cadrées), puis embarquer avec --apply.

Usage :
  python Cover.py --dir "D:\Musique" --extract --apply   # un cover.jpg par album, d'après les pochettes déjà embarquées
  python Cover.py --dir "D:\Musique"                  # simulation : dit ce qui serait embarqué
  python Cover.py --dir "D:\Musique" --apply          # embarque
  python Cover.py --dir "D:\Musique" --verify         # vérifie seulement (code 1 s'il reste un écart)
  python Cover.py --dir "D:\Musique\Eminem\1996 - Infinite" --apply     # un seul album

Options : --apply --verify --extract

Aucune dépendance, aucun outil externe, aucune clé. Pour ajouter la pochette de Cover Art Archive aux albums qui n'ont ni fichier ni image, c'est Metadata.py .
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # pour importer libraries
from libraries.common import cli, filenames  # noqa: E402
from libraries.common.report import Report  # noqa: E402
from libraries.music import album as albums  # noqa: E402
from libraries.music import audio, coverfile, flac, lookup  # noqa: E402


def process_album(album, args):
    """Embarque la pochette du dossier dans chaque piste. Retourne (Report, fichier cover ou None) : le fichier est None quand l'album n'en a pas."""
    path = coverfile.find(album.folder)
    if path is None:
        return Report(), None
    try:
        wanted = coverfile.picture(path)
    except audio.AudioError as e:
        print(f"  [NON TRAITÉ] {e}")
        return Report(total=len(album.files), skipped=1), path

    metas, errors = lookup.read_album(album)
    if errors:
        print("  [NON TRAITÉ] fichier(s) illisible(s) :")
        for error in errors:
            print(f"      - {error}")
        return Report(total=len(album.files), skipped=1), path

    report = Report(total=len(album.files))
    print(f"  pochette : {path.name} ({len(wanted.data) / 1024:.0f} Ko, {wanted.width}x{wanted.height})")
    if len(wanted.data) > flac.WINDOWS_HEADER_LIMIT:
        print("      /!\\ plus de 4 Mio : l'Explorateur de Windows ne lira rien des pistes qui la portent (réduis l'image)")
    for track, meta in metas.items():
        name = filenames.relative_name(track, album.folder)
        if coverfile.same_front(meta, wanted):
            print(f"  {name} : déjà conforme")
            continue
        if args.verify:
            print(f"  [DIFF] {name} : pochette " + ("différente" if meta.has_front_cover else "absente"))
            report.diffs += 1
            continue
        print(f"  {name} : " + ("pochette remplacée" if meta.has_front_cover else "pochette ajoutée") + ("" if args.apply else " (simulation)"))
        if not args.apply:
            continue
        pictures = [wanted] + [p for p in meta.pictures if p.kind != audio.FRONT_COVER]
        try:
            mode = audio.write(track, meta, meta.comments, pictures)
            print(f"      [OK] {mode}")
        except audio.AudioError as e:
            print(f"      [ÉCHEC] {e}")
            report.failures += 1
    return report, path


def readable(album):
    """Les métadonnées des pistes de l'album, une à une et au fil de la lecture : un fichier illisible est sauté, et l'on s'arrête à la première piste qui sert."""
    for track in album.files:
        try:
            yield audio.read(track)
        except audio.AudioError:
            continue


def extract_album(album, args):
    """Écrit la pochette embarquée de l'album en cover.jpg / cover.png dans son dossier. Retourne (Report, "extrait" | "existe" | "aucune") : "existe" quand le dossier a déjà un fichier cover, qu'on ne remplace jamais ; "aucune" quand aucune piste ne porte d'image exploitable."""
    existing = coverfile.find(album.folder)
    if existing is not None:
        print(f"  {existing.name} existe déjà : rien à extraire")
        return Report(), "existe"
    picture, is_front = coverfile.embedded(readable(album))
    if picture is None or not coverfile.extension(picture.data):
        print("  aucune pochette JPEG ou PNG embarquée dans les pistes")
        return Report(), "aucune"
    name = f"cover{coverfile.extension(picture.data)}"
    print(f"  pochette embarquée : {len(picture.data) / 1024:.0f} Ko, {picture.width}x{picture.height}")
    if not is_front:
        print("      /!\\ elle n'est pas typée « face » : c'est peut-être un dos ou un livret, à vérifier")
    if not args.apply:
        print(f"  {name} serait écrit (simulation)")
        return Report(), "extrait"
    try:
        path = coverfile.write(album.folder, picture)
    except OSError as e:
        print(f"  [ÉCHEC] {name} : {e.strerror or e}")
        return Report(failures=1), "échec"
    print(f"  [OK] {path.name} écrit")
    return Report(), "extrait"


def extract_albums(found, args):
    """--extract : un cover.jpg par album qui n'en a pas, d'après la pochette que ses pistes portent déjà. Retourne le code de sortie."""
    report, counts, bare = Report(), {}, []
    for album in found:
        print(f"--- {album.display} ---")
        done, status = extract_album(album, args)
        report += done
        counts[status] = counts.get(status, 0) + 1
        if status == "aucune":
            bare.append(album)
        print()
    print(f"TOTAL : {counts.get('extrait', 0)} cover à écrire ou écrits, {counts.get('existe', 0)} album(s) en avaient déjà un, {counts.get('aucune', 0)} sans pochette embarquée.")
    if bare:
        print(f"\nSans pochette à extraire ({len(bare)}) : pose un cover.jpg à la main, ou passe Metadata.py.")
        for album in bare:
            print(f"  - {album.display}")
    rest = report.epilogue()
    if rest:
        print(f"\nÀ CORRIGER : {rest}.")
    return report.exit_code


def main():
    args = parse_args()
    cli.setup_console()
    cli.check_dir(args.dir)
    what = "la pochette embarquée dans les pistes de chaque album" if args.extract else "le fichier cover de chaque dossier d'album"
    print(f"=== {cli.mode_label(args)} ===   source : {what}\n")

    found = [a for a in albums.find_albums(args.dir) if a.files]
    if not found:
        print(f"Aucun album trouvé dans : {args.dir}")
        return 0
    if args.extract:
        return extract_albums(found, args)

    report, without, with_file = Report(), [], 0
    for album in found:
        print(f"--- {album.display} ---")
        done, path = process_album(album, args)
        if path is None:
            print("  aucun fichier cover : rien à embarquer")
            without.append(album)
        else:
            with_file += 1
        report += done
        print()

    print(f"TOTAL : {with_file}/{len(found)} album(s) ont un fichier cover.")
    if without:
        print(f"\nSans fichier cover ({len(without)}) : pose un cover.jpg dans le dossier de chacun.")
        for album in without:
            print(f"  - {album.display}")
    rest = report.epilogue()
    if rest:
        print(f"\nÀ CORRIGER : {rest}.")
    return report.exit_code


def parse_args():
    ap = argparse.ArgumentParser(description="Embarque dans les pistes le fichier cover du dossier de chaque album, sans toucher aux tags.")
    ap.add_argument("--dir", required=True, help="Dossier de musique, parcouru récursivement (un album, ou toute la médiathèque)")
    ap.add_argument("--apply", action="store_true", help="Applique réellement (défaut : simulation)")
    ap.add_argument("--verify", action="store_true", help="Vérifie seulement (aucune écriture)")
    ap.add_argument("--extract", action="store_true", help="Fait l'inverse : écrit en cover.jpg / cover.png, dans le dossier de chaque album qui n'en a pas, la pochette que ses pistes portent déjà")
    args = ap.parse_args()
    if args.extract and args.verify:
        ap.error("--extract et --verify ne vont pas ensemble : --extract sans --apply est déjà une simulation")
    return args


if __name__ == "__main__":
    sys.exit(main())
