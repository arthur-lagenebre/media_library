#!/usr/bin/env python3
r"""
Verify_Mp3.py - Contrôle les .mp3 d'un dossier, en lecture seule.

Une piste abîmée se lit presque toujours jusqu'au bout : le lecteur saute ce qu'il ne comprend pas, et le défaut ne se remarque qu'à l'écoute. Un .mp3 n'a cependant aucune somme de contrôle : on ne peut juger que sa forme. C'est une chaîne de trames dont chaque en-tête donne la longueur - la suivante commence juste derrière - et ce que l'en-tête Xing/Info annonce.

Deux profondeurs, comme pour les films (Video/Verify_Mkv.py) :
  (défaut)   sans outil externe. Toute la chaîne de trames, de l'étiquette ID3 à la fin : une trame coupée, un trou (avec combien d'octets avant que le son reprenne), du bruit au milieu ou à la fin, et le nombre de trames que l'en-tête Xing/Info annonce. Il faut lire chaque fichier en entier, mais ils sont petits.
  --full     décode tout avec ffmpeg et signale toute erreur de décodage, en plus de la structure. Mesuré, il ne voit rien de plus que le contrôle rapide sur des fichiers coupés ou troués : il sert surtout à confirmer qu'un fichier que le contrôle rapide juge sain se décode bien.

Ce que ni l'un ni l'autre ne voit : UN OCTET ALTÉRÉ DANS LE SON. Aucun format MP3 n'a de somme de contrôle (hors un CRC optionnel que presque aucun encodeur ne pose), et le décodeur accepte n'importe quel octet sans protester. Seul un .flac se vérifie à l'octet près (Verify_Flac.py).

Rien n'est réparé ni déplacé : une piste abîmée ne se répare pas, elle se remplace (nouveau rip, sauvegarde). Le script la nomme, et sort en code 1.

Usage :
  python Verify_Mp3.py --dir "D:\Musique"                       # contrôle rapide
  python Verify_Mp3.py --dir "D:\Musique\Radiohead" --full      # + décodage ffmpeg
  python Verify_Mp3.py --dir "D:\Musique" --no-recursive        # cet étage seul

Options : --full --no-recursive --log (défaut : verification_mp3.log à la racine de --dir)

Dépendance EXTERNE : ffmpeg (FFmpeg), pour --full seulement. Aucune dépendance pip, aucun accès réseau : ce script ne parle qu'aux fichiers.
"""

import argparse
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))   # pour importer libraries
from libraries.common import cli, verify  # noqa: E402
from libraries.common.report import Report  # noqa: E402
from libraries.music import decode, integrity  # noqa: E402

EXTENSIONS = (".mp3",)
RAPIDE = "chaîne de trames, de l'étiquette ID3 à la fin"
COMPLET = "décodage de chaque piste, en plus de la chaîne de trames"
REMEDE = "Une piste abîmée ne se répare pas : remplace-la (nouveau rip, sauvegarde)."
NOTE = "Un octet altéré dans le son d'un .mp3 reste invisible, même avec --full : le format n'a pas de somme de contrôle."
NOTE_COMPLET = "Un octet altéré dans le son d'un .mp3 reste invisible : le format n'a pas de somme de contrôle."


def parse_args():
    p = argparse.ArgumentParser(description="Contrôle les .mp3 d'un dossier, en lecture seule (récursivement par défaut).")
    p.add_argument("--dir", required=True, help="dossier à contrôler")
    p.add_argument("--full", action="store_true", help="décode aussi tout avec ffmpeg et signale toute erreur de décodage : lit chaque fichier en entier")
    p.add_argument("--no-recursive", action="store_true", help="ne contrôle que les pistes posées directement dans --dir, sans descendre dans les sous-dossiers")
    p.add_argument("--log", default=None, help="fichier journal (défaut : verification_mp3.log à la racine de --dir)")
    return p.parse_args()


def check(chemin, complet):
    """Ce qui cloche dans la piste, ou "" si elle est saine.

    La chaîne de trames d'abord, parce qu'elle se lit sans sous-processus et qu'un fichier coupé explique tout le reste ; le décodage ensuite.
    """
    return integrity.mp3_defect(chemin) or (decode.check(chemin) if complet else "")


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

    verify.summarize(rapport, time.time() - debut, args, "piste", REMEDE, NOTE, NOTE_COMPLET)
    verify.write_log(Path(args.log) if args.log else racine / "verification_mp3.log", racine, len(fichiers), defauts, "piste",
                     "rapide (chaîne de trames)", "complet (décodage)", not args.no_recursive, args.full)
    return rapport.exit_code


if __name__ == "__main__":
    sys.exit(main())
