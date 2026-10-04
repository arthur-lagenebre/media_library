#!/usr/bin/env python3
r"""
Recap_All.py — Régénère la fiche (index.html) de toutes les séries d'une médiathèque.

Pour chaque série de --dir, lance Metadata.py --no-tag --recap : les épisodes ne sont JAMAIS modifiés, seule la fiche est réécrite. Utile quand la fiche évolue (affiche et année pour le sommaire, icône d'onglet...) : une seule commande remet toute la médiathèque à niveau.

Est une série tout sous-dossier de --dir qui contient des dossiers "Saison N" (ou "Specials"), ou déjà une fiche (index.html, ou l'ancien recap.html, renommé au passage).

L'identifiant TMDB inscrit dans la fiche existante est repris : une série identifiée autrefois avec --tmdb-id reste la même, sans nouvelle recherche qui pourrait tomber sur un homonyme. Un identifiant épinglé dans le nom du dossier ("Ma Série [tmdbid-1396]") passe devant.

Chaque série tourne dans son propre processus : une série en échec est signalée au bilan, et les suivantes sont traitées quand même. Les images déjà dans une fiche sont reprises, seules les nouvelles sont téléchargées.

Si la médiathèque a un sommaire index.html (Index.py), il est réécrit à la fin.

Usage :
  python Recap_All.py --dir "D:\Séries"                       # simulation
  python Recap_All.py --dir "D:\Séries" --apply               # régénère toutes les fiches
  python Recap_All.py --dir "D:\Séries" --apply --only "Dark"  # seulement les séries dont le nom contient "Dark"

Toute autre option est transmise telle quelle à Metadata.py (--no-cache, --still-size, --cast-limit, --artwork...).
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # pour importer libraries
from libraries.common import cli  # noqa: E402
from libraries.video import lookup, naming, showindex  # noqa: E402

METADATA = Path(__file__).resolve().with_name("Metadata.py")


def find_series(root):
    """Dossiers de série de `root`, dans l'ordre du disque."""
    return [sub for sub in naming.subdirs(Path(root))
            if naming.find_seasons(sub) or showindex.series_page(sub)]


def series_command(folder, apply, extra):
    """Ligne de commande de Metadata.py pour régénérer la fiche d'une série."""
    cmd = [sys.executable, str(METADATA), "--dir", str(folder), "--no-tag", "--recap"]
    if not lookup.pinned_show_id(folder):
        page = showindex.series_page(folder)
        ident = showindex.recap_tmdb_id(page) if page else None
        if ident:
            cmd += ["--tmdb-id", ident]
    if apply:
        cmd.append("--apply")
    return cmd + list(extra)


def parse_args():
    ap = argparse.ArgumentParser(description="Regenere la fiche index.html de toutes les series d'une mediatheque (episodes non modifies).",
                                 epilog="Toute autre option est transmise a Metadata.py.")
    ap.add_argument("--dir", required=True, help="Racine de la mediatheque : un sous-dossier par serie")
    ap.add_argument("--apply", action="store_true", help="Ecrit reellement les fiches (defaut : simulation)")
    ap.add_argument("--only", help="Ne traite que les series dont le nom de dossier contient ce texte")
    return ap.parse_known_args()


def main():
    args, extra = parse_args()
    cli.setup_console()
    root = cli.check_dir(args.dir)
    print(f"=== {cli.mode_label(args)} ===")

    series = find_series(root)
    if args.only:
        series = [s for s in series if args.only.casefold() in s.name.casefold()]
    if not series:
        sys.exit(f"Aucune serie dans {root}" + (f" dont le nom contient '{args.only}'" if args.only else "")
                 + " : il faut un sous-dossier par serie, avec ses dossiers 'Saison N'.")

    failed = []
    for i, folder in enumerate(series, 1):
        print(f"\n##### [{i}/{len(series)}] {folder.name}", flush=True)
        if subprocess.run(series_command(folder, args.apply, extra)).returncode != 0:
            failed.append(folder.name)

    print(f"\n{len(series) - len(failed)}/{len(series)} fiche(s) "
          + ("regeneree(s)." if args.apply else "a regenerer (simulation)."))
    index = root / showindex.INDEX_NAME
    if showindex.is_ours(index):
        print(showindex.write(root, args.apply))
    if failed:
        print("EN ECHEC : " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
