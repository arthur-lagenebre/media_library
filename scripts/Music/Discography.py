#!/usr/bin/env python3
r"""
Discography.py — Pose dans le dossier de chaque artiste un fichier (la pochette, ou un fichier vide) par album qu'il a sorti et qu'on n'a pas.

Chaque sous-dossier de --dir est un artiste ou un groupe. Sa discographie vient de MusicBrainz, et ce qui manque s'écrit comme la fiche de la médiathèque le lit : un fichier "{année} - {titre}" à côté des albums rangés.

    Musique/
        Radiohead/
            1995 - The Bends/            <- un album possédé : jamais touché
            1997 - OK Computer.jpg       <- un album qui manque, avec sa pochette : posé par ce script

L'artiste est reconnu par l'identifiant MusicBrainz que portent les fichiers de ses albums (Metadata.py l'y a inscrit), sinon par recherche sur le nom de son dossier - ou la première ligne d'un fichier artist.txt, comme pour Metadata.py. Plusieurs artistes de ce nom, c'est une QUESTION, posée à la fin du passage ; --no-ask garde le premier.

La pochette est celle que Cover Art Archive garde pour l'album (l'édition que MusicBrainz juge représentative), en JPEG ou PNG, à la taille --image-size (1200 par défaut : assez pour la fiche, sans les scans d'origine de plusieurs Mo). Sans pochette, ou si le service ne répond pas, l'album est un fichier vide sans extension "1997 - OK Computer" ; au passage suivant, ce fichier vide est remplacé par la pochette si elle existe alors. Une image ou un fichier non vide déjà là n'est jamais remplacé. --no-covers ne télécharge rien et ne pose que des fichiers vides.

Un album compte pour possédé qu'il soit un dossier ("1994 - Born Dead", "Daft Punk - Discovery (2001) FLAC"), un fichier (vide, avec ou sans .txt) ou une image "AAAA - Titre" : seul le titre compte, ni l'année ni le format. Les sorties sans année sur MusicBrainz ne peuvent pas se nommer "AAAA - Titre" : elles sont comptées et laissées de côté. Les fichiers se posent là où l'artiste range ses albums (son dossier, ou "Albums/" s'il y range les siens).

Par défaut seuls les ALBUMS sont complétés. --cats ajoute les EP, singles, lives... (album, ep, single, live, compilation, soundtrack, remix, demo, other, ou all) : leurs fichiers vont dans un sous-dossier à leur nom - "EP/", "Singles/"... -, celui où l'artiste range déjà les siens s'il existe.

--only crée le dossier d'un artiste qui n'existe pas encore sous --dir (il prend le nom que lui donne MusicBrainz), ou complète seulement celui-là.

Usage :
  python Discography.py --dir "D:\Musique"                              # simulation : dit ce qui serait posé
  python Discography.py --dir "D:\Musique" --apply                      # pose les fichiers
  python Discography.py --dir "D:\Musique" --only "Radiohead" --apply   # un seul artiste, créé s'il n'a pas de dossier
  python Discography.py --dir "D:\Musique" --cats album,ep --apply      # albums et EP

Options : --apply --only --cats (défaut album) --no-covers --image-size (défaut 1200) --no-ask --no-cache

Ne touche ni aux albums possédés, ni aux tags, ni aux pochettes de leurs pistes. Aucune dépendance, aucune clé : Internet pour MusicBrainz et Cover Art Archive.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # pour importer libraries
from libraries.common import cache, cli, filenames  # noqa: E402
from libraries.common.report import Report  # noqa: E402
from libraries.music import album as albums  # noqa: E402
from libraries.music import coverfile, discography, library  # noqa: E402
from libraries.music.musicbrainz import COVER_SIZES, MusicBrainz, MusicBrainzError, artist_url  # noqa: E402

MAX_CONSECUTIVE_ERRORS = 3      # au-delà, le réseau ou le service est en panne : inutile d'insister


class Target:
    """Un artiste à compléter : son dossier (qui peut ne pas exister), le nom à chercher, et s'il faut le créer."""

    def __init__(self, folder, name, new=False):
        self.folder, self.name, self.new = Path(folder), name, new
        self.pool = []                       # les artistes entre lesquels trancher

    def adopt(self, artist):
        """L'artiste retenu : un dossier à créer prend le nom que lui donne MusicBrainz."""
        if self.new:
            self.folder = self.folder.parent / filenames.safe_name(artist["name"])


def find_targets(root, only):
    """[Target] : les dossiers d'artiste de `root`, ou le seul `only` (créé s'il n'existe pas)."""
    root = Path(root)
    folders = sorted(
        (d for d in root.iterdir() if d.is_dir() and not d.name.startswith((".", *library.SKIPPED_PREFIXES))),
        key=lambda d: d.name.casefold(),
    )
    if only is None:
        return [Target(d, albums.artist_override(d, d) or d.name) for d in folders]
    wanted_name = filenames.safe_name(only).casefold()
    existing = next((d for d in folders if d.name.casefold() == wanted_name), None)
    if existing is not None:
        return [Target(existing, albums.artist_override(existing, existing) or existing.name)]
    return [Target(root / filenames.safe_name(only), only, new=True)]


def resolve_artist(target, mb, no_ask):
    """(identifiant, texte qui dit d'où il vient), ou ("", "") quand il reste à trancher ou que personne ne porte ce nom.

    Quand plusieurs artistes se présentent, target.pool les garde : c'est la question de fin de passage. Sans question (`no_ask`), le premier est retenu.
    """
    found = [a for a in albums.find_albums(target.folder) if a.files and a.folder != target.folder]
    tagged = discography.tagged_artist_id(found)
    if tagged:
        return tagged, f"id lu dans les fichiers : {artist_url(tagged)}"
    target.pool = discography.candidates(mb.search_artists(target.name), target.name)
    if len(target.pool) == 1 or (target.pool and no_ask):
        target.adopt(target.pool[0])
        return target.pool[0]["id"], f"recherche : {discography.describe(target.pool[0])}"
    return "", ""


def fetch_cover(mb, release, size):
    """(octets, extension) de la pochette de l'album sur Cover Art Archive, ou None : elle n'existe pas, n'est ni JPEG ni PNG, démesurée, ou le service ne répond pas. Le fichier vide fait alors l'affaire."""
    try:
        data = mb.cover(None, release.group, size)
    except MusicBrainzError as e:
        print(f"      pochette indisponible : {e}")
        return None
    if not data:
        return None
    extension = coverfile.extension(data)
    if not extension or len(data) > coverfile.MAX_SIZE:
        print("      pochette ignorée : ni JPEG ni PNG, ou démesurée")
        return None
    return data, extension


def place(todo, cover):
    """Écrit l'album manquant : l'image si l'on en a une, sinon le fichier vide. Retourne le chemin posé, ou None quand il n'y a rien à faire (un fichier vide n'a pas de pochette à devenir). OSError si l'écriture échoue."""
    if cover is None:
        if todo.replaces:
            return None
        todo.folder.mkdir(parents=True, exist_ok=True)
        todo.path.touch(exist_ok=True)
        return todo.path
    data, extension = cover
    path = todo.image(extension)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "xb") as image:                     # jamais par-dessus un fichier qui existe
        image.write(data)
    for empty in todo.replaces:
        try:
            if empty.stat().st_size == 0:
                empty.unlink()
        except OSError:
            pass
    return path


def complete(target, mbid, origin, args, mb, root):
    """Pose les fichiers qui manquent pour cet artiste. Retourne (Report, Counter des fichiers posés - ou à poser en simulation - et de ceux qui sont des pochettes)."""
    print(f"  {origin}")
    groups = mb.artist_release_groups(mbid)
    if not groups:
        print("  aucune sortie référencée sur MusicBrainz")
        return Report(total=1, unresolved=1), Counter()
    planned, undated = discography.plan(groups, args.cats)
    todo = discography.missing(planned, discography.inventory(target.folder), target.folder, upgrade=args.covers)

    report, count, bare = Report(total=1, matched=1), Counter(), 0
    if target.new and not target.folder.exists():
        print(f"  + {filenames.relative_name(target.folder, root)}/ (dossier de l'artiste)")
    for item in todo:
        name = filenames.relative_name(item.path, root)
        if not args.apply:
            print(f"  {'~' if item.replaces else '+'} {name}" + ("  (pochette si disponible)" if args.covers else ""))
            count["files"] += 1
            continue
        cover = fetch_cover(mb, item.release, args.image_size) if args.covers else None
        try:
            path = place(item, cover)
        except OSError as e:
            print(f"  [ÉCHEC] {name} : {e.strerror or e}")
            report.failures += 1
            continue
        if path is None:
            bare += 1
            continue
        count["files"] += 1
        if cover is not None:
            count["covers"] += 1
            print(f"  + {filenames.relative_name(path, root)} ({len(cover[0]) / 1024:.0f} Ko)")
        else:
            print(f"  + {name}")
    if args.apply and target.new:
        try:
            target.folder.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"  [ÉCHEC] {target.folder.name} : {e.strerror or e}")
            report.failures += 1
    if bare:
        print(f"  {bare} album(s) déjà déclaré(s) par un fichier vide, sans pochette sur Cover Art Archive : gardé(s) tel(s)")
    if not count["files"] and not report.failures:
        print("  à jour")
    if undated:
        print(f"  {undated} sortie(s) sans année sur MusicBrainz : laissée(s) de côté")
    return report, count


def confirm_artists(pending):
    """Pose les questions mises de côté : rend (target, artiste choisi ou None) pour chacun. Non interactif, tous restent de côté."""
    print(f"=== {len(pending)} artiste(s) à confirmer ===")
    if not cli.can_ask():
        print("  Terminal non interactif : ces artistes sont laissés de côté.")
        print("  Relance dans un terminal, ajoute un fichier artist.txt au dossier, ou passe")
        print("  --no-ask pour accepter le premier résultat sans demander.\n")
        for target in pending:
            print(f"  [À CONFIRMER] {target.folder.name}")
            yield target, None
        return

    print("  Entrée = garder le 1er, i = laisser de côté, q = arrêter les questions.\n")
    stopped = False
    for number, target in enumerate(pending, 1):
        print(f"[{number}/{len(pending)}] {target.folder.name}   (recherche : '{target.name}')")
        for rank, artist in enumerate(target.pool, 1):
            print(f"      {rank}) {discography.describe(artist)}" + ("   (défaut)" if rank == 1 else ""))
        answer = cli.ASK_SKIP if stopped else cli.ask_choice(len(target.pool))
        if answer == cli.ASK_STOP:
            stopped, answer = True, cli.ASK_SKIP
        if answer == cli.ASK_SKIP:
            print("      [NON TRAITÉ] artiste non confirmé\n")
            yield target, None
            continue
        yield target, target.pool[answer]


# ----------------------------------------------------------------------------
# Programme principal
# ----------------------------------------------------------------------------
def parse_cats(text):
    names = {c.strip().lower() for c in text.split(",") if c.strip()}
    return set(discography.CATEGORIES) if "all" in names else names


def parse_args():
    ap = argparse.ArgumentParser(description="Pose un fichier '{année} - {titre}' (la pochette, ou un fichier vide) par album d'un artiste que son dossier n'a pas (données MusicBrainz).")
    ap.add_argument("--dir", required=True, help="Dossier de musique : chacun de ses sous-dossiers est un artiste ou un groupe")
    ap.add_argument("--only", metavar="ARTISTE", help="Un seul artiste, dont le dossier est créé sous --dir s'il n'existe pas")
    ap.add_argument("--cats", default=",".join(discography.DEFAULT_CATEGORIES), help=f"Catégories à compléter, séparées par des virgules ({', '.join(discography.CATEGORIES)}, ou all ; défaut : {','.join(discography.DEFAULT_CATEGORIES)})")
    ap.add_argument("--no-ask", action="store_true", help="Ne pose aucune question : garde le 1er artiste qui porte le nom")
    ap.add_argument("--no-covers", action="store_true", help="Ne cherche aucune pochette : chaque album manquant est un fichier vide (plus rapide, rien à télécharger)")
    ap.add_argument("--image-size", default="1200", choices=COVER_SIZES, help="Taille des pochettes Cover Art Archive (défaut : 1200 ; original = le scan d'origine, souvent plusieurs Mo)")
    ap.add_argument("--no-cache", action="store_true", help="Ignore le cache des réponses MusicBrainz et le rafraîchit")
    ap.add_argument("--apply", action="store_true", help="Pose réellement les fichiers (défaut : simulation)")
    args = ap.parse_args()
    args.cats = parse_cats(args.cats)
    args.covers = not args.no_covers
    unknown = args.cats - set(discography.CATEGORIES)
    if unknown or not args.cats:
        ap.error(f"--cats attend des catégories parmi {', '.join(discography.CATEGORIES)} (ou all), pas '{','.join(sorted(unknown)) or 'rien'}'")
    return args


def main():
    args = parse_args()
    cli.setup_console()
    root = cli.check_dir(args.dir)
    mb = MusicBrainz(cache=cache.Cache(read=not args.no_cache, source="musicbrainz"))
    labels = ", ".join(discography.CATEGORIES[c] for c in discography.CATEGORIES if c in args.cats)
    print(f"=== {cli.mode_label(args, 'rien ne sera écrit ; ajoute --apply')} ===   source : MusicBrainz, catégories : {labels}\n")

    targets = find_targets(root, args.only)
    if not targets:
        print(f"Aucun dossier d'artiste dans : {root}")
        return 0

    report, written, pending, errors = Report(), Counter(), [], 0
    for index, target in enumerate(targets):
        print(f"--- {target.folder.name} ({index + 1}/{len(targets)}) ---")
        try:
            mbid, origin = resolve_artist(target, mb, args.no_ask)
            if mbid:
                done, count = complete(target, mbid, origin, args, mb, root)
            elif target.pool:
                print(f"  [À CONFIRMER] {len(target.pool)} artistes portent ce nom -> question en fin de passage")
                pending.append(target)
                done, count = Report(), Counter()
            else:
                print("  [NON ASSOCIÉ] aucun artiste de ce nom sur MusicBrainz")
                done, count = Report(total=1, unresolved=1), Counter()
        except MusicBrainzError as e:
            print(f"  échec MusicBrainz : {e}\n")
            report.unresolved += 1
            errors += 1
            if errors >= MAX_CONSECUTIVE_ERRORS:
                rest = len(targets) - index - 1
                print(f"{MAX_CONSECUTIVE_ERRORS} erreurs de suite : arrêt (réseau ou service indisponible ?), {rest} artiste(s) non vu(s).")
                report.unresolved += rest
                break
            continue
        errors = 0
        report, written = report + done, written + count
        print()

    for target, artist in confirm_artists(pending) if pending else ():
        if artist is None:
            report.pending += 1
            continue
        target.adopt(artist)
        try:
            done, count = complete(target, artist["id"], f"id choisi : {artist_url(artist['id'])}", args, mb, root)
        except MusicBrainzError as e:
            print(f"  échec MusicBrainz : {e}")
            report.unresolved += 1
        else:
            report, written = report + done, written + count
        print()

    verb = "posé(s)" if args.apply else "à poser"
    covers = f", dont {written['covers']} avec pochette" if written["covers"] else ""
    print(f"TOTAL : {written['files']} fichier(s) {verb}{covers} pour {report.matched}/{len(targets)} artiste(s).")
    rest = report.epilogue()
    if rest:
        print(f"\nÀ CORRIGER : {rest}.")
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
