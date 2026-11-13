#!/usr/bin/env python3
r"""
Mp4_To_Mkv.py - Remultiplexe les .mp4 en .mkv, sans réencodage, sous-titres compris.

Un .mp4 sait porter une jaquette et quelques tags, mais à la mode iTunes : Metadata.py écrit des tags Matroska, et n'a donc nulle part où les poser tant que le film reste dans ce conteneur. C'est la passe qui précède l'étiquetage : elle change le conteneur, et rien d'autre.

Rien n'est réencodé - les pistes sont recopiées telles quelles, à la vitesse du disque - donc l'image et le son ressortent identiques. Les chapitres suivent ; la jaquette et les tags iTunes, non : Metadata.py les réécrit ensuite, depuis TMDB.

Ce qui distingue ce passage de celui des .avi tient en une chose : un .mp4 déclare souvent la langue de ses pistes. Elle est alors gardée, et --lang ne sert qu'à celles qui n'en ont pas ("und") ; --force-lang réétiquette tout, pour un fichier qui se trompe. Un .avi, lui, ne dit jamais rien de ses langues, et il faut bien les lui donner.

Les sous-titres posés à côté sont embarqués au passage, et leur encodage est mesuré fichier par fichier : mkvmerge suppose de l'UTF-8, alors qu'un .srt d'époque est en général en windows-1252, et le malentendu ne se voit qu'aux accents cassés, souvent une fois l'original effacé. La langue est lue dans le suffixe du nom ("Film.fr.srt"), et un .sub est laissé à son .idx, qui l'embarque déjà. Ceux qui sont déjà DANS le mp4 (tx3g) sont recopiés sans qu'on ait rien à demander, et comptent pour --subs require.

La durée du .mkv produit est comparée à celle de la source : le moov d'un .mp4 ne ment pas comme un index AVI, mais il peut manquer, ou n'avoir jamais été écrit sur un fichier coupé en cours de copie - mkvmerge remultiplexe alors ce qu'il trouve, sans toujours s'en plaindre. --delete-source n'efface l'original qu'après ce contrôle, et réclame donc ffprobe.

Usage :
  python Mp4_To_Mkv.py --dir "D:\Films"                          # simulation
  python Mp4_To_Mkv.py --dir "D:\Films" --apply                  # convertit
  python Mp4_To_Mkv.py --dir "D:\Films" --apply --lang eng --sub-lang fre
  python Mp4_To_Mkv.py --dir "D:\Films" --apply --delete-source  # + efface le .mp4 verifie

Options : --apply --lang --force-lang --sub-lang --subs --sub-charset --default-audio --default-sub --title --output-dir --overwrite --tolerance --delete-source --no-recursive --log FICHIER (journal du passage ; défaut : aucun)

Dépendances EXTERNES : mkvmerge (MKVToolNix), et ffprobe (FFmpeg) pour le contrôle des durées. Aucune dépendance pip, aucun accès réseau : ce script ne parle qu'aux fichiers.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # pour importer libraries
from libraries.common import cli  # noqa: E402
from libraries.video import remux  # noqa: E402

NO_LANGUAGE = {"", "und"}                 # ce que mkvmerge répond d'une piste qui ne dit pas sa langue


def parse_args():
    p = argparse.ArgumentParser(description="Remultiplexe les .mp4 d'un dossier en .mkv, sans réencodage (récursivement par défaut).")
    p.add_argument("--dir", required=True, help="dossier à convertir")
    p.add_argument("--apply", action="store_true", help="convertit réellement (défaut : simulation)")
    p.add_argument("--lang", default="fre", help="langue des pistes audio qui n'en déclarent aucune, code ISO 639-2 à trois lettres (défaut : fre)")
    p.add_argument("--force-lang", action="store_true", help="impose --lang à toutes les pistes audio, y compris celles qui déclarent déjà une langue")
    p.add_argument("--sub-lang", default=None, help="langue d'un sous-titre dont le nom ne dit rien (défaut : celle de --lang)")
    p.add_argument("--subs", choices=("auto", "none", "require"), default="auto", help="auto : embarque les sous-titres posés à côté ; none : les ignore ; require : ne convertit que les films qui en ont, dedans ou à côté (défaut : auto)")
    p.add_argument("--sub-charset", default="windows-1252", help="encodage de repli des sous-titres texte qui ne sont pas en UTF-8 (défaut : windows-1252)")
    p.add_argument("--default-audio", action="store_true", help="marque la première piste audio comme piste par défaut")
    p.add_argument("--default-sub", action="store_true", help="marque le premier sous-titre posé à côté comme piste par défaut")
    p.add_argument("--title", action="store_true", help="inscrit le nom du fichier comme titre du segment")
    p.add_argument("--output-dir", default=None, help="dossier de sortie, où les fichiers sont posés à plat (défaut : à côté de la source)")
    p.add_argument("--overwrite", action="store_true", help="écrase un .mkv déjà présent au lieu de passer son tour")
    p.add_argument("--tolerance", type=float, default=2.0, help="écart de durée toléré entre la source et le résultat, en secondes (défaut : 2.0)")
    p.add_argument("--delete-source", action="store_true", help="efface le .mp4 une fois la durée du .mkv vérifiée (demande ffprobe)")
    p.add_argument("--no-recursive", action="store_true", help="ne convertit que les .mp4 posés directement dans --dir, sans descendre dans les sous-dossiers")
    p.add_argument("--log", metavar="FICHIER", help="fichier journal (défaut : pas de journal)")
    args = p.parse_args()
    if args.sub_lang is None:
        args.sub_lang = args.lang
    if args.output_dir:
        args.output_dir = Path(args.output_dir)
    if len(args.lang) != 3 or len(args.sub_lang) != 3:
        print("Attention : mkvmerge attend un code ISO 639-2 à trois lettres (fre, eng, ger...) ; "
              f"'{args.lang}' / '{args.sub_lang}' risque d'être refusé.\n")
    return args


def tracks_of(info, kind):
    """Les pistes d'un type donné, dans l'ordre où mkvmerge les a lues."""
    return [t for t in (info or {}).get("tracks", []) if t.get("type") == kind]


def track_language(track):
    """Langue déclarée par une piste, ou "" quand elle n'en déclare pas.

    mkvmerge répond "und" pour une piste muette sur ce point, ce qui revient au même qu'un champ absent : les deux sont rendus ici comme une absence, pour qu'un seul test suffise ensuite.
    """
    language = (track.get("properties") or {}).get("language") or ""
    return "" if language in NO_LANGUAGE else language


def audio_languages(info, args):
    """([(id, langue à écrire)], [langues gardées]) pour les pistes audio.

    C'est là que ce script se sépare de son voisin Avi_To_Mkv : un .mp4 déclare souvent la langue de ses pistes, et un rip anglais correctement étiqueté ressortirait en français si on écrasait tout au passage. On n'écrit donc que sur les pistes qui ne disent rien - à moins que --force-lang ne tranche, pour un fichier qui se trompe.
    """
    to_write, kept = [], []
    for track in tracks_of(info, "audio"):
        language = track_language(track)
        if language and not args.force_lang:
            kept.append(language)
        else:
            to_write.append((track["id"], args.lang))
    return to_write, kept


def build_command(video, output, info, subs, args):
    """(commande mkvmerge, [(nom, langue, encodage)], [langues gardées]) pour un fichier.

    Les identifiants de piste sont ceux de 'mkvmerge -J', et non ceux de ffprobe, qui numérote autrement.
    """
    command = ["mkvmerge", "--output", str(output)]

    to_write, kept = audio_languages(info, args)
    for track_id, language in to_write:
        command += ["--language", f"{track_id}:{language}"]
    audio_ids = [t["id"] for t in tracks_of(info, "audio")]
    if audio_ids and args.default_audio:
        command += ["--default-track-flag", f"{audio_ids[0]}:yes"]
    if args.title:
        command += ["--title", video.stem]
    command.append(str(video))

    attached = remux.attach_subtitles(command, video, subs, args)
    return command, attached, kept


def plan(video, output, info, subs, args):
    command, attached, kept = build_command(video, output, info, subs, args)
    remark = ""
    embedded = len(tracks_of(info, "subtitles"))
    if embedded:
        remark += f", {embedded} sous-titre(s) déjà dans le mp4"
    if kept:
        remark += ", langue(s) d'origine gardée(s) : " + ", ".join(sorted(set(kept)))
    return command, attached, remark


def intro(args):
    return ["Les pistes qui déclarent déjà leur langue la gardent"
            + (" - sauf ici, où --force-lang l'impose." if args.force_lang else " (--force-lang pour l'imposer).")]


CONTAINER = remux.Container(
    extension=".mp4",
    no_subtitles="aucun sous-titre, ni dedans ni à côté (--subs require)",
    plan=plan,
    embedded_subtitles=lambda info: len(tracks_of(info, "subtitles")),
    intro=intro,
)


def main():
    cli.setup_console()
    return remux.run(parse_args(), CONTAINER)


if __name__ == "__main__":
    sys.exit(main())
