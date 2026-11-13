#!/usr/bin/env python3
r"""
Clean_Epub.py - Nettoie les .epub d'un dossier : retire leurs résidus, répare leur archive, assainit la fiche de leur .opf.

Trois corrections, chacune sûre parce qu'elle ne touche à aucun contenu du livre (texte, images, styles) :
  residues   les entrées qui ne sont que des résidus et que le livre ne déclare pas : __MACOSX/, les "._" d'AppleDouble, .DS_Store, Thumbs.db, desktop.ini, iTunesMetadata.plist, iTunesArtwork, calibre_bookmarks.txt (la position de lecture de Calibre)
  archive    "mimetype" remis en première entrée, stocké sans compression, sans champ "extra", au contenu exact (beaucoup de liseuses refusent le livre sinon) ; les entrées en double ne gardent que la dernière, celle que lit un lecteur de zip
  metadata   dans l'.opf, la date « zéro » de Calibre (0101-01-01) et les éléments Dublin Core vides (<dc:publisher/>...). Ni le titre, ni la langue, ni l'identifiant ne sont touchés, ni les champs "calibre:" que l'étagère lit (série, numéro) ; l'.opf n'est modifié que dans ces lignes, le reste reste identique à l'octet

Rien n'est perdu en route. Le livre est réécrit sous un nom provisoire (.epub.part), puis CONTRÔLÉ : mêmes entrées à ce qui est retiré près, mêmes octets partout ailleurs, même fiche, et aucun défaut qu'il n'avait pas (le contrôle de Verify_Epub.py). Si un seul point échoue, rien n'est remplacé. Sinon l'original est mis de côté en "Livre.epub.bak" (".bak2", ".bak3"... jamais par-dessus une sauvegarde) et le livre propre prend sa place ; --no-backup supprime cette sauvegarde, une fois le contrôle passé.

Un livre sans rien à nettoyer n'est pas réécrit : un second passage ne change rien. Une archive illisible n'est pas touchée et fait sortir en code 1. Ce qui ne se répare pas sans perte (fichiers du manifeste absents, liens ou images cassés, XML cassé, fichiers hors manifeste) n'est pas l'affaire de ce script : Verify_Epub.py le nomme.

Usage :
  python Clean_Epub.py --dir "D:\Livres"                           # simulation : dit ce qui serait nettoyé
  python Clean_Epub.py --dir "D:\Livres" --apply                   # nettoie, en gardant les originaux en .bak
  python Clean_Epub.py --dir "D:\Livres" --apply --no-backup       # nettoie, sans garder les originaux
  python Clean_Epub.py --dir "D:\Livres" --fix residues --apply    # seulement les résidus
  python Clean_Epub.py --dir "D:\Livres\Romans" --no-recursive     # cet étage seul

Options : --apply --fix (residues, archive, metadata ; défaut : les trois) --no-backup --no-recursive --log FICHIER

Aucune dépendance externe, aucune dépendance pip, aucun accès réseau : ce script ne parle qu'aux fichiers.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # pour importer libraries
from libraries.books import epubclean  # noqa: E402
from libraries.books.archive import BookError  # noqa: E402
from libraries.common import cli, filenames, journal, verify  # noqa: E402
from libraries.common.report import Report  # noqa: E402

EXTENSIONS = (".epub",)


def parse_args():
    p = argparse.ArgumentParser(description="Nettoie les .epub d'un dossier : résidus, archive, fiche de l'.opf (simulation par défaut ; l'original est gardé en .bak).")
    p.add_argument("--dir", required=True, help="dossier à nettoyer")
    p.add_argument("--apply", action="store_true", help="réécrit réellement les livres (défaut : simulation)")
    p.add_argument("--fix", default=",".join(epubclean.FIXES), help=f"corrections à faire, séparées par des virgules ({', '.join(epubclean.FIXES)} ; défaut : les trois)")
    p.add_argument("--no-backup", action="store_true", help="ne garde pas l'original en .bak une fois le livre nettoyé contrôlé")
    p.add_argument("--no-recursive", action="store_true", help="ne traite que les livres posés directement dans --dir, sans descendre dans les sous-dossiers")
    journal.add_option(p)
    args = p.parse_args()
    args.fix = [name.strip() for name in args.fix.split(",") if name.strip()]
    unknown = sorted(set(args.fix) - set(epubclean.FIXES))
    if unknown or not args.fix:
        p.error(f"--fix attend des corrections parmi {', '.join(epubclean.FIXES)}, pas '{','.join(unknown) or 'rien'}'")
    return args


def clean_book(chemin, racine, args, report):
    """Nettoie un livre. Retourne "propre" (rien à faire), "à nettoyer" (simulation), "nettoyé" ou "échec"."""
    name = filenames.relative_name(chemin, racine)
    try:
        plan = epubclean.plan(chemin, args.fix)
    except BookError as e:
        cli.clear_line()
        print(f"  [NON TRAITÉ] {name} : {e}")
        report.skipped += 1
        return "échec"
    if plan.empty:
        return "propre"
    cli.clear_line()
    print(f"  {name}")
    for line in plan.lines():
        print(f"      - {line}")
    if not args.apply:
        return "à nettoyer"
    try:
        backup = epubclean.apply(chemin, plan, keep_backup=not args.no_backup)
    except (BookError, OSError) as e:
        print(f"      [ÉCHEC] {getattr(e, 'strerror', None) or e} (le livre n'a pas été modifié)")
        report.failures += 1
        return "échec"
    print("      [OK] nettoyé" + (f", original gardé : {backup.name}" if backup else ""))
    return "nettoyé"


def main():
    cli.setup_console()
    args = parse_args()
    with journal.record(args.log):
        return run(args)


def run(args):
    """Le passage entier, une fois les options lues. Rend le code de sortie."""
    racine, fichiers = verify.locate(args, EXTENSIONS)
    print(f"=== {cli.mode_label(args)} ===   corrections : {', '.join(args.fix)}\n")
    print(f"{len(fichiers)} livre(s) sous {racine}\n" if not args.no_recursive else f"{len(fichiers)} livre(s) dans {racine} (sous-dossiers ignorés)\n")

    report, counts = Report(total=len(fichiers)), {}
    for n, chemin in enumerate(fichiers, 1):
        cli.progress(n, len(fichiers), filenames.relative_name(chemin, racine))
        status = clean_book(chemin, racine, args, report)
        counts[status] = counts.get(status, 0) + 1
    cli.clear_line()

    done = counts.get("nettoyé", 0)
    backups = done if not args.no_backup else 0
    if args.apply:
        print(f"\nTOTAL : {report.total} livre(s) vus, {done} nettoyé(s), {counts.get('propre', 0)} déjà propre(s).")
    else:
        print(f"\nTOTAL : {report.total} livre(s) vus, {counts.get('à nettoyer', 0)} à nettoyer, {counts.get('propre', 0)} déjà propre(s).")
    if backups:
        print(f"{backups} original(aux) gardé(s) en .bak : supprime-les une fois les livres vérifiés (ou passe --no-backup la prochaine fois).")
    if done or counts.get("à nettoyer"):
        print("Pour voir ce que ce script ne répare pas : Verify_Epub.py.")
    rest = [f"{n} {what}" for n, what in ((report.skipped, "livre(s) illisible(s), non touché(s)"), (report.failures, "réécriture(s) en échec")) if n]
    if rest:
        print(f"\nÀ CORRIGER : {' ; '.join(rest)}.")
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
