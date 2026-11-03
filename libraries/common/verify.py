"""Ce que les scripts de contrôle de fichiers partagent : lister les fichiers, les passer un à un, tenir le journal et le bilan.

Ce qu'un script juge d'un fichier lui appartient (une fonction `check(chemin, complet)` qui rend le défaut ou ""), le reste est ici pour que chaque format ne le réécrive pas.
"""

import sys
from datetime import datetime

from . import cli, filenames


def files(racine, extensions, recursif=True):
    """Les fichiers de ces extensions sous racine : ceux posés à la racine d'abord, puis dossier par dossier.

    L'extension est comparée en minuscules plutôt que filtrée par glob : un ".MP3" ripé à l'ancienne ne serait pas vu sous Linux. Les résidus de copie depuis macOS (`._Piste.mp3`) ne sont pas des fichiers audio.
    """
    trouves = racine.rglob("*") if recursif else racine.glob("*")
    fichiers = (f for f in trouves if f.is_file() and f.suffix.lower() in extensions and not f.name.startswith("._"))
    return sorted(fichiers, key=lambda p: (p.parent != racine, str(p.parent).lower(), p.name.lower()))


def locate(args, extensions):
    """(racine, fichiers) à contrôler, ou la sortie du programme avec ce qui manque."""
    racine = cli.check_dir(args.dir)
    fichiers = files(racine, extensions, recursif=not args.no_recursive)
    if not fichiers:
        sys.exit(f"Aucun {' ni '.join(extensions)} {'dans' if args.no_recursive else 'sous'} {racine}")
    return racine, fichiers


def announce(racine, fichiers, args, nom, rapide, complet):
    """Ce qu'on va contrôler, et à quelle profondeur."""
    portee = "dans" if args.no_recursive else "sous"
    octets = sum(f.stat().st_size for f in fichiers)
    print(f"{len(fichiers)} {nom}(s), {cli.readable_size(octets)} {portee} {racine}" + (" (sous-dossiers ignorés)" if args.no_recursive else ""))
    print("Contrôle " + (f"complet : {complet}" if args.full else f"rapide : {rapide}"))


def check_all(fichiers, racine, check, complet):
    """[(chemin, message)] des fichiers en défaut, signalés au fur et à mesure."""
    defauts = []
    for n, chemin in enumerate(fichiers, 1):
        cli.progress(n, len(fichiers), filenames.relative_name(chemin, racine))
        message = check(chemin, complet)
        if message:
            cli.clear_line()
            print(f"  [DÉFAUT] {filenames.relative_name(chemin, racine)}")
            print(f"           {message}")
            defauts.append((chemin, message))
    cli.clear_line()
    return defauts


def summarize(rapport, duree, args, nom, remede, note, note_complet=""):
    """Le bilan du passage : combien en défaut, ce qu'il reste à faire, et ce que le contrôle ne voit pas (`note` en rapide, `note_complet` avec --full)."""
    print(f"\nTOTAL : {rapport.total} {nom}(s) contrôlée(s) en {cli.readable_time(duree)}, {rapport.diffs} en défaut.")
    if rapport.diffs:
        print(remede)
    elif note_complet if args.full else note:
        print(note_complet if args.full else note)


def write_log(destination, racine, total, defauts, nom, rapide, complet, recursif, mode_complet):
    """Journal du passage : ce qui cloche."""
    lignes = [
        f"Vérification du {datetime.now():%d/%m/%Y %H:%M} - {racine}",
        f"Contrôle {complet if mode_complet else rapide}{'' if recursif else ', sans les sous-dossiers'}",
        f"{total} {nom}(s) contrôlée(s), {len(defauts)} en défaut.",
        "",
    ]
    if not defauts:
        lignes.append("Aucun défaut.")
    for chemin, message in defauts:
        lignes += [filenames.relative_name(chemin, racine), f"    {message}", ""]
    try:
        destination.write_text("\n".join(lignes) + "\n", encoding="utf-8")
        print(f"[log] {destination} écrit")
    except OSError as exc:
        print(f"[log] impossible d'écrire {destination} : {exc.strerror or exc}")

