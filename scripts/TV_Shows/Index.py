#!/usr/bin/env python3
r"""
Index.py — Sommaire HTML de toutes les séries d'une médiathèque.

Écrit un sommaire dans le dossier __Data__ de --dir (créé au besoin) : un mur d'affiches, une par série, chacune menant à sa fiche, dans __Data__/Fiches (ou à l'ancien index.html / recap.html du dossier de la série, tant que la fiche n'a pas été régénérée). Tout est lu dans les fiches elles-mêmes (titre, année, saisons, affiche) : ni clé TMDB ni réseau.

Fait pour tourner en TÂCHE PLANIFIÉE sur le NAS qui héberge la médiathèque : les fiches sont écrites sur un disque local puis transférées, et seul le NAS voit toutes les séries. Le script n'a besoin que de Python 3 et de libraries/ - aucun outil, aucune clé, aucun réseau - et ne réécrit le sommaire que si son contenu change.

Le sommaire porte le nom du titre : --title "Anime" l'écrit dans __Data__/Anime.html (et lui donne ce titre), sans --title c'est __Data__/tv_shows.html. L'ancien index.html, à la racine, n'est ni réécrit ni effacé : on en reprend le titre, et on peut le supprimer.

Une fiche écrite avant que les fiches portent ces informations figure sans affiche ni année : régénérer sa fiche les ajoute.

Les liens sont relatifs : la médiathèque peut être déplacée ou ouverte depuis un autre poste, ils restent bons.

Usage :
  python Index.py --dir "D:\Séries"            # simulation
  python Index.py --dir "D:\Séries" --apply                  # écrit D:\Séries\__Data__\tv_shows.html
  python Index.py --dir "D:\Séries" --apply --title "Anime"  # écrit D:\Séries\__Data__\Anime.html

  # TrueNAS SCALE : System > Advanced Settings > Cron Jobs, toutes les heures, en tant que
  # l'utilisateur propriétaire du partage (pas root : le fichier doit rester modifiable par SMB).
  # Mise en place détaillée dans le README.
  python3 /mnt/<pool>/<outils>/media_library/scripts/TV_Shows/Index.py --dir /mnt/<pool>/<series> --apply
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # pour importer libraries
from libraries.common import cli  # noqa: E402
from libraries.video import showindex  # noqa: E402


def parse_args():
    ap = argparse.ArgumentParser(description="Sommaire HTML de toutes les séries d'une médiathèque, avec un lien vers la fiche de chacune.")
    ap.add_argument("--dir", required=True, help="Racine de la médiathèque : un sous-dossier par série")
    ap.add_argument("--apply", action="store_true", help="Écrit réellement le sommaire (défaut : simulation)")
    ap.add_argument("--title", help="Titre du sommaire, onglet et page, et nom de son fichier : --title Anime écrit Anime.html (défaut : tv_shows.html, titré comme le sommaire existant, sinon 'Séries')")
    return ap.parse_args()


def main():
    args = parse_args()
    cli.setup_console()
    root = cli.check_dir(args.dir)
    print(f"=== {cli.mode_label(args)} ===")

    out = showindex.index_path(root, args.title)
    if out.exists() and not showindex.is_ours(out):
        sys.exit(f"{out} existe et n'a pas été écrit par ce script : il n'est pas remplacé.")
    entries = showindex.find_entries(root)
    if not entries:
        sys.exit(f"Aucune fiche dans {root} : lance d'abord Metadata.py --recap sur chaque série.")
    for entry in sorted(entries, key=lambda e: showindex.sort_key(e.title)):
        print(f"  {entry.title}" + (f" ({entry.year})" if entry.year else "")
              + ("" if entry.poster else "  [sans affiche : fiche à régénérer]"))
    print(f"\n{showindex.write(root, args.apply, args.title)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
