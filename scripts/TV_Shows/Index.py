#!/usr/bin/env python3
r"""
Index.py — Sommaire HTML de toutes les séries d'une médiathèque.

Écrit un index.html à la racine de --dir : un mur d'affiches, une par série, chacune menant à la fiche index.html de son dossier (ou à l'ancien recap.html, tant que la fiche n'a pas été régénérée). Tout est lu dans les fiches elles-mêmes (titre, année, saisons, affiche) : ni clé TMDB ni réseau.

Fait pour tourner en TÂCHE PLANIFIÉE sur le NAS qui héberge la médiathèque : les fiches sont écrites sur un disque local puis transférées, et seul le NAS voit toutes les séries. Le script n'a besoin que de Python 3 et de mkvlib/ - aucun outil, aucune clé, aucun réseau - et ne réécrit index.html que si son contenu change.

Une fiche écrite avant que les fiches portent ces informations figure sans affiche ni année : régénérer sa fiche les ajoute.

Les liens sont relatifs : la médiathèque peut être déplacée ou ouverte depuis un autre poste, ils restent bons.

Usage :
  python Index.py --dir "D:\Séries"            # simulation
  python Index.py --dir "D:\Séries" --apply    # écrit index.html

  # TrueNAS SCALE : System > Advanced Settings > Cron Jobs, toutes les heures, en tant que
  # l'utilisateur propriétaire du partage (pas root : le fichier doit rester modifiable par SMB).
  # Mise en place détaillée dans le README.
  python3 /mnt/<pool>/<outils>/mkv_editors/scripts/TV_Shows/Index.py --dir /mnt/<pool>/<series> --apply
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # pour importer mkvlib
from mkvlib import cli, showindex                               # noqa: E402


def parse_args():
    ap = argparse.ArgumentParser(description="Sommaire HTML de toutes les series d'une mediatheque, avec un lien vers la fiche de chacune.")
    ap.add_argument("--dir", required=True, help="Racine de la mediatheque : un sous-dossier par serie")
    ap.add_argument("--apply", action="store_true", help="Ecrit reellement index.html (defaut : simulation)")
    ap.add_argument("--title", help="Titre du sommaire (defaut : celui du sommaire existant, sinon 'Series')")
    return ap.parse_args()


def main():
    args = parse_args()
    cli.setup_console()
    root = cli.check_dir(args.dir)
    print(f"=== {cli.mode_label(args)} ===")

    out = root / showindex.INDEX_NAME
    if out.exists() and not showindex.is_ours(out):
        sys.exit(f"{out} existe et n'a pas ete ecrit par ce script : il n'est pas remplace.")
    entries = showindex.find_entries(root)
    if not entries:
        sys.exit(f"Aucune fiche dans {root} : lance d'abord Metadata.py --recap sur chaque serie.")
    for entry in sorted(entries, key=lambda e: showindex.sort_key(e.title)):
        print(f"  {entry.title}" + (f" ({entry.year})" if entry.year else "")
              + ("" if entry.poster else "  [sans affiche : fiche a regenerer]"))
    print(f"\n{showindex.write(root, args.apply, args.title)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
