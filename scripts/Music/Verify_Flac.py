#!/usr/bin/env python3
r"""
Verify_Flac.py - Contrôle les .flac d'un dossier, en lecture seule.

Une piste abîmée se lit presque toujours jusqu'au bout : le lecteur saute ce qu'il ne comprend pas, et le défaut ne se remarque qu'à l'écoute - un claquement, un morceau qui s'arrête trois secondes trop tôt. Une copie interrompue sur le NAS, un disque qui flanche, et la piste est perdue sans que rien ne le dise. FLAC est le seul format audio de la médiathèque qui se vérifie à l'octet près : chaque trame porte son CRC-16, et STREAMINFO l'empreinte MD5 de tout le son.

Deux profondeurs, comme pour les films (Video/Verify_Mkv.py) :
  (défaut)   sans outil externe. L'en-tête, puis la queue du fichier : la dernière trame doit être complète (son CRC-16 est bon) et s'arrêter à l'échantillon exact que STREAMINFO annonce. Cela voit un fichier coupé où que la coupure tombe, même juste entre deux trames, en ne lisant que quelques centaines de Ko par piste.
  --full     décode tout avec ffmpeg : le CRC de CHAQUE trame est vérifié, puis l'empreinte MD5 du son décodé est comparée à celle de STREAMINFO (16 et 24 bits, mono ou stéréo) - c'est ce que fait `flac -t`. Il faut lire chaque fichier en entier et le décoder, donc à réserver à un dossier plutôt qu'à toute une médiathèque. Seul ce mode voit une trame abîmée au milieu d'un fichier.

Un .flac que son encodeur a écrit sans empreinte (seize octets nuls dans STREAMINFO) n'est contrôlé que par ses CRC, comme un son en 20 ou 32 bits ou en multicanal, où l'ordre des échantillons pourrait différer sans que le fichier soit abîmé.

Rien n'est réparé ni déplacé : une piste abîmée ne se répare pas, elle se remplace (nouveau rip, sauvegarde). Le script la nomme, et sort en code 1.

Usage :
  python Verify_Flac.py --dir "D:\Musique"                       # contrôle rapide
  python Verify_Flac.py --dir "D:\Musique\Radiohead" --full      # décodage intégral
  python Verify_Flac.py --dir "D:\Musique" --no-recursive        # cet étage seul

Options : --full --no-recursive --log (défaut : verification_flac.log à la racine de --dir)

Dépendance EXTERNE : ffmpeg (FFmpeg), pour --full seulement. Aucune dépendance pip, aucun accès réseau : ce script ne parle qu'aux fichiers.
"""

import argparse
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # pour importer libraries
from libraries.common import cli, verify  # noqa: E402
from libraries.common.report import Report  # noqa: E402
from libraries.music import decode, integrity  # noqa: E402

EXTENSIONS = (".flac",)
RAPIDE = "fin du fichier : la dernière trame, complète, à l'échantillon annoncé"
COMPLET = "décodage de chaque piste (CRC des trames, empreinte MD5)"
REMEDE = "Une piste abîmée ne se répare pas : remplace-la (nouveau rip, sauvegarde)."
NOTE = "Le contrôle rapide ne voit qu'un fichier coupé : --full décode chaque piste et voit une trame abîmée au milieu."


def parse_args():
    p = argparse.ArgumentParser(description="Contrôle les .flac d'un dossier, en lecture seule (récursivement par défaut).")
    p.add_argument("--dir", required=True, help="dossier à contrôler")
    p.add_argument("--full", action="store_true", help="décode tout avec ffmpeg (CRC de chaque trame, empreinte MD5) : lit chaque fichier en entier")
    p.add_argument("--no-recursive", action="store_true", help="ne contrôle que les pistes posées directement dans --dir, sans descendre dans les sous-dossiers")
    p.add_argument("--log", default=None, help="fichier journal (défaut : verification_flac.log à la racine de --dir)")
    return p.parse_args()


def check(chemin, complet):
    """Ce qui cloche dans la piste, ou "" si elle est saine.

    La structure d'abord, parce qu'elle se lit sans sous-processus et qu'un fichier coupé explique tout le reste ; le décodage ensuite, qui seul voit une trame abîmée au milieu.
    """
    return integrity.flac_defect(chemin) or (decode.check(chemin, integrity.flac_digest(chemin)) if complet else "")


def main():
    cli.setup_console()
    args = parse_args()
    if args.full and shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg est introuvable dans le PATH.\n"
                 "  Installe FFmpeg : winget install Gyan.FFmpeg")
    racine, fichiers = verify.locate(args, EXTENSIONS)
    verify.announce(racine, fichiers, args, "piste", RAPIDE, COMPLET)

    debut = time.time()
    defauts = verify.check_all(fichiers, racine, check, args.full)
    rapport = Report(total=len(fichiers), diffs=len(defauts))

    verify.summarize(rapport, time.time() - debut, args, "piste", REMEDE, NOTE)
    verify.write_log(Path(args.log) if args.log else racine / "verification_flac.log", racine, len(fichiers), defauts, "piste",
                     "rapide (fin du fichier)", "complet (décodage)", not args.no_recursive, args.full)
    return rapport.exit_code


if __name__ == "__main__":
    sys.exit(main())
