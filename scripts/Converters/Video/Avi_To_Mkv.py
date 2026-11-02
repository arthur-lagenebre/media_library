#!/usr/bin/env python3
r"""
Avi_To_Mkv.py - Remultiplexe les .avi en .mkv, sans réencodage, sous-titres compris.

Un .avi ne sait rien porter : ni jaquette, ni synopsis, ni identifiant TMDB. Tant qu'un film reste dans ce conteneur, Metadata.py n'a nulle part où écrire, et le fichier ne peut pas être autonome. C'est donc la passe qui précède l'étiquetage : elle change le conteneur, et rien d'autre.

Rien n'est réencodé - les pistes sont recopiées telles quelles, à la vitesse du disque - donc l'image et le son ressortent identiques. Ce qui change, c'est ce que le fichier saura raconter ensuite.

Les sous-titres posés à côté sont embarqués au passage, et leur encodage est mesuré fichier par fichier : mkvmerge suppose de l'UTF-8, alors qu'un .srt d'époque est en général en windows-1252, et le malentendu ne se voit qu'aux accents cassés, souvent une fois l'original effacé. La langue est lue dans le suffixe du nom ("Film.fr.srt"), et un .sub est laissé à son .idx, qui l'embarque déjà.

La durée du .mkv produit est comparée à celle de la source : c'est ce qui attrape un index AVI qui ment ou un flux mal recopié, que mkvmerge ne signale pas toujours. --delete-source n'efface l'original qu'après ce contrôle, et réclame donc ffprobe.

Usage :
  python Avi_To_Mkv.py --dir "D:\Films"                          # simulation
  python Avi_To_Mkv.py --dir "D:\Films" --apply                  # convertit
  python Avi_To_Mkv.py --dir "D:\Films" --apply --lang eng --sub-lang fre
  python Avi_To_Mkv.py --dir "D:\Films" --apply --delete-source  # + efface l'.avi verifie

Options : --apply --lang --sub-lang --subs --sub-charset --default-audio --default-sub --title --output-dir --overwrite --tolerance --delete-source --no-recursive --log (défaut : conversion.log à la racine de --dir)

Dépendances EXTERNES : mkvmerge (MKVToolNix), et ffprobe (FFmpeg) pour le contrôle des durées. Aucune dépendance pip, aucun accès réseau : ce script ne parle qu'aux fichiers.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))   # pour importer libraries
from libraries.common import cli  # noqa: E402
from libraries.video import remux  # noqa: E402


def parse_args():
    p = argparse.ArgumentParser(description="Remultiplexe les .avi d'un dossier en .mkv, sans réencodage (récursivement par défaut).")
    p.add_argument("--dir", required=True, help="dossier à convertir")
    p.add_argument("--apply", action="store_true", help="convertit réellement (défaut : simulation)")
    p.add_argument("--lang", default="fre", help="langue des pistes audio, code ISO 639-2 à trois lettres (défaut : fre)")
    p.add_argument("--sub-lang", default=None, help="langue d'un sous-titre dont le nom ne dit rien (défaut : celle de --lang)")
    p.add_argument("--subs", choices=("auto", "none", "require"), default="auto", help="auto : embarque les sous-titres posés à côté ; none : les ignore ; require : ne convertit que les films qui en ont (défaut : auto)")
    p.add_argument("--sub-charset", default="windows-1252", help="encodage de repli des sous-titres texte qui ne sont pas en UTF-8 (défaut : windows-1252)")
    p.add_argument("--default-audio", action="store_true", help="marque la première piste audio comme piste par défaut")
    p.add_argument("--default-sub", action="store_true", help="marque le premier sous-titre comme piste par défaut")
    p.add_argument("--title", action="store_true", help="inscrit le nom du fichier comme titre du segment")
    p.add_argument("--output-dir", default=None, help="dossier de sortie, où les fichiers sont posés à plat (défaut : à côté de la source)")
    p.add_argument("--overwrite", action="store_true", help="écrase un .mkv déjà présent au lieu de passer son tour")
    p.add_argument("--tolerance", type=float, default=2.0, help="écart de durée toléré entre la source et le résultat, en secondes (défaut : 2.0)")
    p.add_argument("--delete-source", action="store_true", help="efface l'.avi une fois la durée du .mkv vérifiée (demande ffprobe)")
    p.add_argument("--no-recursive", action="store_true", help="ne convertit que les .avi posés directement dans --dir, sans descendre dans les sous-dossiers")
    p.add_argument("--log", default=None, help="fichier journal (défaut : conversion.log à la racine de --dir)")
    args = p.parse_args()
    if args.sub_lang is None:
        args.sub_lang = args.lang
    if args.output_dir:
        args.output_dir = Path(args.output_dir)
    if len(args.lang) != 3 or len(args.sub_lang) != 3:
        print("Attention : mkvmerge attend un code ISO 639-2 à trois lettres (fre, eng, ger...) ; "
              f"'{args.lang}' / '{args.sub_lang}' risque d'être refusé.\n")
    return args


def build_command(video, output, info, subs, args):
    """(commande mkvmerge, [(nom, langue, encodage)]) pour un fichier.

    Les identifiants de piste sont ceux de 'mkvmerge -J', et non ceux de ffprobe, qui numérote autrement. Un .avi ne dit jamais la langue de ses pistes : --lang les donne toutes.
    """
    command = ["mkvmerge", "--output", str(output)]

    audio_ids = [t["id"] for t in info.get("tracks", []) if t.get("type") == "audio"]
    for track_id in audio_ids:
        command += ["--language", f"{track_id}:{args.lang}"]
    if audio_ids and args.default_audio:
        command += ["--default-track-flag", f"{audio_ids[0]}:yes"]
    if args.title:
        command += ["--title", video.stem]
    command.append(str(video))

    attached = remux.attach_subtitles(command, video, subs, args)
    return command, attached


def plan(video, output, info, subs, args):
    command, attached = build_command(video, output, info, subs, args)
    return command, attached, ""


CONTAINER = remux.Container(
    extension=".avi",
    log_name="conversion.log",
    no_subtitles="aucun sous-titre à côté (--subs require)",
    plan=plan,
)


def main():
    cli.setup_console()
    return remux.run(parse_args(), CONTAINER)


if __name__ == "__main__":
    sys.exit(main())
