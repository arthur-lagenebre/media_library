#!/usr/bin/env python3
r"""
Discography.py — Pose dans le dossier de chaque artiste un fichier (la pochette, ou un fichier vide) par album qu'il a sorti et qu'on n'a pas.

Chaque sous-dossier de --dir est un artiste ou un groupe. Sa discographie vient de MusicBrainz, et ce qui manque s'écrit comme la fiche de la médiathèque le lit : un fichier "{année} - {titre}" à côté des albums rangés.

    Musique/
        Radiohead/
            1995 - The Bends/            <- un album possédé : jamais touché
            1997 - OK Computer.jpg       <- un album qui manque, avec sa pochette : posé par ce script

L'artiste est reconnu par l'identifiant MusicBrainz que portent les fichiers de ses albums (Metadata.py l'y a inscrit), sinon par recherche sur le nom de son dossier - ou la première ligne d'un fichier artist.txt, comme pour Metadata.py. Plusieurs artistes de ce nom, c'est une QUESTION, posée à la fin du passage ; --no-ask garde le premier.

La pochette est celle que Cover Art Archive garde pour l'album (l'édition que MusicBrainz juge représentative), en JPEG ou PNG, à sa taille d'origine, sauf si --image-size en demande une autre (250, 500 ou 1200). Au-delà de 20 Mio, ce n'est pas une pochette : l'album reste alors un fichier vide. Sans pochette, ou si le service ne répond pas, l'album est un fichier vide sans extension "1997 - OK Computer" ; au passage suivant, ce fichier vide est remplacé par la pochette si elle existe alors. Une image ou un fichier non vide déjà là n'est jamais remplacé. --no-covers ne télécharge rien et ne pose que des fichiers vides.

Un album compte pour possédé qu'il soit un dossier ("1994 - Born Dead", "Daft Punk - Discovery (2001) FLAC"), un fichier (vide, avec ou sans .txt) ou une image "AAAA - Titre" : seul le titre compte, ni l'année ni le format. Les sorties sans année sur MusicBrainz ne peuvent pas se nommer "AAAA - Titre" : elles sont comptées et laissées de côté. Les fichiers se posent là où l'artiste range ses albums (son dossier, ou "Albums/" s'il y range les siens).

Par défaut seuls les ALBUMS sont complétés. --cats ajoute les EP, singles, lives... (album, ep, single, live, compilation, soundtrack, remix, demo, other, ou all) : leurs fichiers vont dans un sous-dossier à leur nom - "EP/", "Singles/"... -, celui où l'artiste range déjà les siens s'il existe.

--candidates sert à CHOISIR la meilleure pochette : pour chaque album que l'artiste n'a pas (même déclaré par un fichier ou une image déjà posés), il télécharge dans un dossier _covers/<album>/ de l'artiste toutes les pochettes de face que Cover Art Archive garde pour TOUTES les éditions de cet album, sans limite de nombre, en taille d'origine sauf si --image-size en demande une autre. Chaque fichier dit d'où il vient : "01_FR-2013-CD_3000x3000.jpg" - le 01 est l'édition la plus ancienne. Les images identiques ne sont déposées qu'une fois. Rien d'autre n'est posé ni touché : ni les fichiers des albums, ni leurs pochettes. Pour choisir : ouvrir _covers/ dans l'Explorateur, copier la bonne image à côté des albums sous le nom de l'album ("1997 - OK Computer.jpg"), en remplaçant la pochette posée (si le format change, .jpg contre .png, supprimer l'ancienne). --clean-candidates supprime ensuite les dossiers _covers/. Ni l'un ni l'autre ne va avec --no-covers.

--only crée le dossier d'un artiste qui n'existe pas encore sous --dir (il prend le nom que lui donne MusicBrainz), ou complète seulement celui-là.

Usage :
  python Discography.py --dir "D:\Musique"                              # simulation : dit ce qui serait posé
  python Discography.py --dir "D:\Musique" --apply                      # pose les fichiers
  python Discography.py --dir "D:\Musique" --only "Radiohead" --apply   # un seul artiste, créé s'il n'a pas de dossier
  python Discography.py --dir "D:\Musique" --cats album,ep --apply      # albums et EP
  python Discography.py --dir "D:\Musique" --only "Radiohead" --candidates --apply   # dépose les pochettes entre lesquelles choisir
  python Discography.py --dir "D:\Musique" --clean-candidates --apply   # supprime les dossiers _covers

Options : --apply --only --cats (défaut album) --no-covers --candidates --clean-candidates --image-size (défaut original) --no-ask --no-cache

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
        """L'artiste retenu : un dossier à créer prend le nom que lui donne MusicBrainz. Un nom qui ne laisse rien une fois nettoyé ("???") garde celui qu'on a demandé : sans quoi le « dossier » serait --dir lui-même."""
        name = filenames.safe_name(artist["name"])
        if self.new and name:
            self.folder = self.folder.parent / name


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


def preview_item(item, root, args, count):
    """Simulation : dit ce qui serait posé."""
    name = filenames.relative_name(item.path, root)
    print(f"  {'~' if item.replaces else '+'} {name}" + ("  (pochette si disponible)" if args.covers else ""))
    count["files"] += 1


def lay_item(item, root, args, mb, report, count):
    """Pose le fichier d'un album manquant, avec sa pochette si on en trouve une. Vrai quand l'album est déjà déclaré par un fichier vide et reste tel quel, faute de pochette."""
    name = filenames.relative_name(item.path, root)
    cover = fetch_cover(mb, item.release, args.image_size) if args.covers else None
    try:
        path = place(item, cover)
    except OSError as e:
        print(f"  [ÉCHEC] {name} : {e.strerror or e}")
        report.failures += 1
        return False
    if path is None:
        return True
    count["files"] += 1
    if cover is not None:
        count["covers"] += 1
        print(f"  + {filenames.relative_name(path, root)} ({len(cover[0]) / 1024:.0f} Ko)")
    else:
        print(f"  + {name}")
    return False


def candidate_sources(release, mb):
    """[(édition, image)] : les pochettes de face de toutes les éditions du release group de l'album, les plus anciennes d'abord. [] quand MusicBrainz n'a pas d'identifiant de release group pour lui."""
    editions = coverfile.by_date(mb.group_releases(release.group)) if release.group else []
    return coverfile.candidate_sources(editions, mb)


def deposit_candidates(item, artist_dir, args, mb, report):
    """Dépose dans _covers/<album>/ les pochettes entre lesquelles choisir. Retourne (nombre de pochettes déposées - ou à déposer en simulation, vrai si MusicBrainz ne répond pas)."""
    try:
        sources = candidate_sources(item.release, mb)
    except MusicBrainzError as e:
        print(f"  [ÉCHEC] {item.name} : {e}")
        report.failures += 1
        return 0, True
    if not sources:
        print(f"  {item.name} : aucune pochette de face sur Cover Art Archive")
        return 0, False
    print(f"  {item.name} : {len(sources)} pochette(s) de face chez {len({edition['id'] for edition, _ in sources})} édition(s)" + ("" if args.apply else " (simulation)"))
    if not args.apply:
        return len(sources), False

    written, seen, down = 0, set(), False
    for edition, image in sources:
        label = albums.describe(edition)
        try:
            data = mb.cover_image(image, args.image_size)
        except MusicBrainzError as e:
            print(f"      [ÉCHEC] {label} : {e}")
            report.failures += 1
            down = True
            continue
        down = False
        if not data or data in seen:
            continue
        seen.add(data)
        if not coverfile.extension(data):
            print(f"      {label} : ni JPEG ni PNG, ignorée")
            continue
        name = coverfile.candidate_name(written + 1, edition, data)
        written += 1
        try:
            coverfile.write_candidate(artist_dir, name, data, album=item.name)
        except FileExistsError:
            print(f"      {coverfile.CANDIDATES_DIR}/{item.name}/{name} : déjà là")
        except OSError as e:
            print(f"      [ÉCHEC] {name} : {e.strerror or e}")
            report.failures += 1
            written -= 1
            break
        else:
            print(f"      {coverfile.CANDIDATES_DIR}/{item.name}/{name} ({len(data) / 1024:.0f} Ko)  <- {label}")
    return written, down


def candidate_artist(target, todo, args, mb):
    """--candidates : les pochettes de chaque album que le dossier de l'artiste n'a pas, dans son _covers/. Retourne (Report, Counter des pochettes - "files" - et des albums qui en ont - "albums")."""
    report, count, errors = Report(total=1, matched=1), Counter(), 0
    for item in todo:
        written, down = deposit_candidates(item, target.folder, args, mb, report)
        count["files"] += written
        count["albums"] += bool(written)
        errors = errors + 1 if down else 0
        if errors >= MAX_CONSECUTIVE_ERRORS:
            print(f"  {MAX_CONSECUTIVE_ERRORS} échecs de suite : arrêt pour cet artiste (réseau ou service indisponible ?)")
            break
    if not todo:
        print("  à jour")
    return report, count


def clean_candidates(targets, args):
    """--clean-candidates : supprime le dossier _covers/ de chaque artiste qui en a un. Retourne le code de sortie."""
    report, removed = Report(), 0
    for target in targets:
        if not coverfile.candidates_present(target.folder):
            continue
        print(f"--- {target.folder.name} ---")
        if not args.apply:
            print(f"  {coverfile.CANDIDATES_DIR} serait supprimé (simulation)\n")
            removed += 1
            continue
        try:
            coverfile.remove_candidates(target.folder)
        except OSError as e:
            print(f"  [ÉCHEC] {coverfile.CANDIDATES_DIR} : {e.strerror or e}\n")
            report.failures += 1
            continue
        print(f"  [OK] {coverfile.CANDIDATES_DIR} supprimé\n")
        removed += 1
    print(f"TOTAL : {removed} dossier(s) {coverfile.CANDIDATES_DIR} " + ("supprimé(s)." if args.apply else "à supprimer."))
    rest = report.epilogue()
    if rest:
        print(f"\nÀ CORRIGER : {rest}.")
    return report.exit_code


def create_folder(target, report):
    """Crée le dossier d'un artiste nouveau, même quand aucun album ne s'y pose."""
    try:
        target.folder.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"  [ÉCHEC] {target.folder.name} : {e.strerror or e}")
        report.failures += 1


def print_closing(report, count, bare, undated):
    """Ce qui reste à dire d'un artiste : albums gardés tels quels, « à jour », sorties sans année."""
    if bare:
        print(f"  {bare} album(s) déjà déclaré(s) par un fichier vide, sans pochette sur Cover Art Archive : gardé(s) tel(s)")
    if not count["files"] and not report.failures:
        print("  à jour")
    if undated:
        print(f"  {undated} sortie(s) sans année sur MusicBrainz : laissée(s) de côté")


def complete(target, mbid, origin, args, mb, root):
    """Pose les fichiers qui manquent pour cet artiste. Retourne (Report, Counter des fichiers posés - ou à poser en simulation - et de ceux qui sont des pochettes)."""
    print(f"  {origin}")
    groups = mb.artist_release_groups(mbid)
    if not groups:
        print("  aucune sortie référencée sur MusicBrainz")
        return Report(total=1, unresolved=1), Counter()
    planned, undated = discography.plan(groups, args.cats)
    try:
        owned = discography.inventory(target.folder)
    except OSError as e:
        print(f"  [ÉCHEC] inventaire impossible, rien n'est posé pour cet artiste : {e}")
        return Report(total=1, matched=1, failures=1), Counter()
    if args.candidates:
        report, count = candidate_artist(target, discography.unowned(planned, owned, target.folder), args, mb)
        if undated:
            print(f"  {undated} sortie(s) sans année sur MusicBrainz : laissée(s) de côté")
        return report, count
    todo = discography.missing(planned, owned, target.folder, upgrade=args.covers)

    report, count, bare = Report(total=1, matched=1), Counter(), 0
    if target.new and not target.folder.exists():
        print(f"  + {filenames.relative_name(target.folder, root)}/ (dossier de l'artiste)")
    for item in todo:
        if args.apply:
            bare += lay_item(item, root, args, mb, report, count)
        else:
            preview_item(item, root, args, count)
    if args.apply and target.new:
        create_folder(target, report)
    print_closing(report, count, bare, undated)
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
    ap.add_argument("--image-size", default="original", choices=COVER_SIZES, help="Taille des pochettes Cover Art Archive (défaut : original, le scan d'origine, souvent plusieurs Mo ; 250, 500 ou 1200 pour des miniatures)")
    ap.add_argument("--candidates", action="store_true", help="Dépose dans _covers/<album>/, dans le dossier de chaque artiste, toutes les pochettes de face de Cover Art Archive (toutes les éditions de chaque album qu'il n'a pas) : on y choisit la meilleure et on la copie sous le nom de l'album. Ne pose aucun autre fichier")
    ap.add_argument("--clean-candidates", action="store_true", help="Supprime les dossiers _covers/ déposés par --candidates")
    ap.add_argument("--no-cache", action="store_true", help="Ignore le cache des réponses MusicBrainz et le rafraîchit")
    ap.add_argument("--apply", action="store_true", help="Pose réellement les fichiers (défaut : simulation)")
    args = ap.parse_args()
    if args.candidates + args.clean_candidates + args.no_covers > 1:
        ap.error("--candidates, --clean-candidates et --no-covers s'excluent : un seul à la fois")
    args.cats = parse_cats(args.cats)
    if args.only is not None and not filenames.safe_name(args.only):
        ap.error(f"--only attend un nom d'artiste dont il reste quelque chose une fois les signes interdits dans un nom de dossier retirés, pas '{args.only}'")
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
    if args.clean_candidates:
        return clean_candidates(targets, args)

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

    if args.candidates:
        verb = "déposée(s)" if args.apply else "à déposer"
        print(f"TOTAL : {written['files']} pochette(s) {verb} pour {written['albums']} album(s), {report.matched}/{len(targets)} artiste(s).")
        if written["files"] and args.apply:
            print(f"\nPour choisir : ouvre {coverfile.CANDIDATES_DIR}/<album>/ dans le dossier de l'artiste, copie la meilleure image à côté des albums, sous le nom de l'album (\"1997 - OK Computer.jpg\"), en remplaçant la pochette posée.\nPour supprimer les dossiers {coverfile.CANDIDATES_DIR}/ ensuite : Discography.py --clean-candidates --apply.")
    else:
        verb = "posé(s)" if args.apply else "à poser"
        covers = f", dont {written['covers']} avec pochette" if written["covers"] else ""
        print(f"TOTAL : {written['files']} fichier(s) {verb}{covers} pour {report.matched}/{len(targets)} artiste(s).")
    rest = report.epilogue()
    if rest:
        print(f"\nÀ CORRIGER : {rest}.")
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
