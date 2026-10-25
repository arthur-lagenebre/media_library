#!/usr/bin/env python3
r"""
Wav_To_Flac.py - Encode les .wav en .flac, sans perte.

Un .wav ne sait presque rien porter : pas de pochette, pas d'identifiant MusicBrainz, des tags que la plupart des lecteurs ignorent, et une taille en général près du double de celle du même son en FLAC. Music/Metadata.py n'a donc nulle part où écrire tant qu'une piste reste dans ce conteneur. C'est la passe qui précède l'étiquetage : elle change le format, et rien d'autre.

FLAC plutôt que MP3 : c'est le seul des deux qui rende exactement le son d'origine. Un .wav sort d'un CD ou d'une captation et il n'existera plus qu'en une copie ; l'encoder en MP3 jetterait à jamais ce que l'oreille ne remarque pas aujourd'hui, et un .flac se transcode en MP3 le jour où il en faut un, pas l'inverse. Music/Metadata.py et Music/Recap.py lisent les deux de la même façon.

« Sans perte » est vérifié, pas supposé : le son décodé du .wav et celui du .flac produit sont comparés par empreinte (MD5 des échantillons), et le .flac n'existe qu'à cette condition. --delete-source n'efface l'original qu'ensuite. Seuls les .wav en entiers 16 ou 24 bits sont pris : un .wav en virgule flottante ou en 32 bits ressortirait arrondi, donc modifié, et il est laissé tel quel avec la raison.

Les tags du .wav (titre, artiste, album, année, numéro de piste...) suivent quand il en a. Le .flac s'écrit d'abord sous un nom provisoire (Piste.flac.part) : une coupure, un échec ou une empreinte différente ne laissent aucun .flac tronqué, que le passage suivant aurait pris pour une conversion déjà faite.

Usage :
  python Wav_To_Flac.py --dir "D:\Musique"                          # simulation
  python Wav_To_Flac.py --dir "D:\Musique" --apply                  # convertit
  python Wav_To_Flac.py --dir "D:\Musique" --apply --compression 12
  python Wav_To_Flac.py --dir "D:\Musique" --apply --delete-source  # + efface le .wav vérifié

Options : --apply --compression --output-dir --overwrite --delete-source --no-recursive --log (défaut : conversion_flac.log à la racine de --dir)

Dépendances EXTERNES : ffmpeg et ffprobe (FFmpeg). Aucune dépendance pip, aucun accès réseau : ce script ne parle qu'aux fichiers.
"""

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))   # pour importer libraries
from libraries.common import cli, filenames  # noqa: E402
from libraries.common.tools import partial_path, run_tool  # noqa: E402

# Les seuls codecs que FLAC garde à l'identique. ffmpeg arrondit tout le reste (virgule flottante, 32 bits, 8 bits) sans rien dire.
LOSSLESS_CODECS = {"pcm_s16le": "16 bits", "pcm_s24le": "24 bits"}
MAX_COMPRESSION = 12   # niveaux de ffmpeg : 0 = le plus rapide, 12 = le plus petit (le son décodé est le même)


def parse_args():
    p = argparse.ArgumentParser(description="Encode les .wav d'un dossier en .flac, sans perte (récursivement par défaut).")
    p.add_argument("--dir", required=True, help="dossier à convertir")
    p.add_argument("--apply", action="store_true", help="convertit réellement (défaut : simulation)")
    p.add_argument("--compression", type=int, choices=range(MAX_COMPRESSION + 1), metavar="0-12", default=8, help="niveau de compression : ne change que la taille et le temps de calcul, jamais le son (défaut : 8)")
    p.add_argument("--output-dir", default=None, help="dossier de sortie, où les fichiers sont posés à plat (défaut : à côté de la source)")
    p.add_argument("--overwrite", action="store_true", help="écrase un .flac déjà présent au lieu de passer son tour")
    p.add_argument("--delete-source", action="store_true", help="efface le .wav une fois le son du .flac vérifié")
    p.add_argument("--no-recursive", action="store_true", help="ne convertit que les .wav posés directement dans --dir, sans descendre dans les sous-dossiers")
    p.add_argument("--log", default=None, help="fichier journal (défaut : conversion_flac.log à la racine de --dir)")
    args = p.parse_args()
    if args.output_dir:
        args.output_dir = Path(args.output_dir)
    return args


def wav_files(root, recursive=True):
    """Les .wav sous root : ceux posés à la racine d'abord, puis dossier par dossier.

    Le même ordre que les convertisseurs de films, pour qu'un passage se relise pareil d'un script à l'autre. L'extension est comparée en minuscules plutôt que filtrée par glob : un ".WAV" de CD ripé à l'ancienne ne serait pas vu sous Linux.
    """
    found = root.rglob("*") if recursive else root.glob("*")
    files = (f for f in found if f.is_file() and f.suffix.lower() == ".wav")
    return sorted(files, key=lambda p: (p.parent != root, str(p.parent).lower(), p.name.lower()))


def build_command(wav, output, args):
    """La commande ffmpeg qui encode un .wav en .flac.

    `-f flac` est obligatoire : le fichier s'écrit sous un nom en .part, dont ffmpeg ne peut pas deviner le format. `-map 0:a:0` ne prend que le son, `-map_metadata 0` recopie les tags, et `-bitexact` empêche ffmpeg de signer le fichier de sa version, de sorte que deux passages donnent deux fichiers identiques.
    """
    return ["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-map", "0:a:0", "-map_metadata", "0",
            "-c:a", "flac", "-compression_level", str(args.compression), "-fflags", "+bitexact", "-f", "flac", str(output)]


def display_command(command):
    """La commande telle qu'on la retaperait, guillemets compris."""
    return " ".join(f'"{word}"' if " " in word else word for word in command)


def last_error(result):
    """Dernière ligne d'erreur de ffmpeg : avec `-v error` c'est elle qui dit pourquoi, les précédentes en sont les conséquences."""
    lines = [line.strip() for line in (result.stderr or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def audio_codec(path):
    """Codec de la première piste audio d'un fichier, ou None s'il est illisible."""
    result = run_tool(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "json", str(path)])
    if result.returncode != 0:
        return None
    try:
        streams = json.loads(result.stdout).get("streams", [])
    except ValueError:
        return None
    return streams[0].get("codec_name") if streams else None


def sound_hash(path):
    """Empreinte MD5 du son décodé d'un fichier, ou None si ffmpeg n'a pas pu le lire.

    L'empreinte porte sur les échantillons, pas sur les octets du fichier : un .wav et son .flac en ont forcément de différents, mais le même son. Tout est décodé en 32 bits pour que 16 et 24 bits se comparent sans qu'aucun ne soit tronqué au passage - le muxer md5 prendrait sinon du 16 bits.
    """
    result = run_tool(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-c:a", "pcm_s32le", "-f", "md5", "-"])
    line = (result.stdout or "").strip()
    return line if result.returncode == 0 and line.startswith("MD5=") else None


def convert(wav, args):
    """(statut, détail) : ce qu'on a fait du fichier, et ce qu'il y a à en dire.

    Rien n'est affiché ici : c'est l'appelant qui imprime, et le journal reprend mot pour mot ce que le terminal a montré.
    """
    final = (args.output_dir or wav.parent) / (wav.stem + ".flac")
    if final.exists() and not args.overwrite:
        return "ignoré", f"{final.name} existe déjà (--overwrite pour l'écraser)"

    codec = audio_codec(wav)
    if codec is None:
        return "erreur", "aucune piste audio lisible"
    if codec not in LOSSLESS_CODECS:
        return "erreur", f"{codec} : FLAC ne le garderait pas à l'identique (seuls les entiers 16 et 24 bits le sont)"

    partial = partial_path(final)
    command = build_command(wav, partial if args.apply else final, args)
    if not args.apply:
        return "simule", display_command(command)

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        partial.unlink(missing_ok=True)       # reste d'un passage interrompu : il ne doit pas passer pour la sortie de celui-ci
        result = run_tool(command)
        if result.returncode != 0 or not partial.exists():
            return "erreur", last_error(result) or "ffmpeg n'a rien pu écrire"

        source, produced = sound_hash(wav), sound_hash(partial)
        if source is None or produced is None:
            return "erreur", "le son n'a pas pu être relu pour être comparé : le .flac n'a pas été écrit"
        if source != produced:
            return "écart", f"le son décodé diffère de la source : {final.name} n'a pas été écrit, l'original est gardé"
        size_wav, size_flac = wav.stat().st_size, partial.stat().st_size
        try:
            os.replace(partial, final)
        except OSError as exc:
            return "erreur", f"{final.name} n'a pas pu être écrit : {exc.strerror or exc}"
    finally:
        partial.unlink(missing_ok=True)       # déjà renommé : rien à faire ; sinon (échec, écart, Ctrl-C) rien ne doit traîner

    note = f"son identique ({LOSSLESS_CODECS[codec]}), {size_flac / size_wav:.0%} de la taille d'origine" if size_wav else "son identique"
    if args.delete_source:
        try:
            wav.unlink()
            note += ", source effacée"
        except OSError as exc:
            note += f", source non effacée : {exc.strerror or exc}"
    return "converti", note


def write_log(destination, root, entries, args, summary):
    """Journal du passage : un fichier par ligne, avec ce qu'on en a fait."""
    lines = [
        f"Conversion du {datetime.now():%d/%m/%Y %H:%M} - {root}",
        cli.mode_label(args, "aucune conversion") + ("" if not args.no_recursive else ", sans les sous-dossiers"),
        f"{len(entries)} fichier(s) .wav - {summary}",
        "",
    ]
    for name, status, detail in entries:
        lines += [name, f"    {status} : {detail}", ""]
    failed = [name for name, status, _ in entries if status in ("erreur", "écart")]
    if failed:
        lines += ["", "NON CONVERTIS (originaux intacts) :"] + [f"  {name}" for name in failed]
    try:
        destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[log] {destination} écrit")
    except OSError as exc:
        print(f"[log] impossible d'écrire {destination} : {exc.strerror or exc}")


def main():
    cli.setup_console()
    args = parse_args()
    root = cli.check_dir(args.dir)
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        sys.exit(f"{' et '.join(missing)} {'est introuvable' if len(missing) == 1 else 'sont introuvables'} dans le PATH.\n"
                 "  Installe FFmpeg : winget install Gyan.FFmpeg")

    files = wav_files(root, recursive=not args.no_recursive)
    scope = "dans" if args.no_recursive else "sous"
    if not files:
        sys.exit(f"Aucun .wav {scope} {root}")
    print(f"=== {cli.mode_label(args, 'rien ne sera converti ; ajoute --apply')} ===")
    print(f"{len(files)} fichier(s) .wav {scope} {root}"
          + (" (sous-dossiers ignorés)" if args.no_recursive else ""))
    print("Encodage sans perte : le son décodé du .flac est comparé à celui du .wav avant que le .flac existe.\n")

    entries, start = [], time.time()
    for n, path in enumerate(files, 1):
        name = filenames.relative_name(path, root)
        print(f"  [{n}/{len(files)}] {name}")
        status, detail = convert(path, args)
        mark = f"[{status.upper()}] " if status in ("erreur", "écart") else ""
        print(f"          {mark}{detail}")
        entries.append((name, status, detail))

    counts = {}
    for _, status, _ in entries:
        counts[status] = counts.get(status, 0) + 1
    summary = ", ".join(f"{count} {status}" for status, count in sorted(counts.items()))
    elapsed = time.time() - start
    print(f"\nTOTAL : {len(entries)} fichier(s) en {elapsed / 60:.1f} min - {summary}.")
    if not args.apply:
        print("Simulation : rien n'a été écrit. Ajoute --apply pour convertir.")
    elif counts.get("converti") and not args.delete_source:
        print("Les .wav sont toujours à côté de leurs .flac : étiquette-les avec "
              "Music/Metadata.py, puis efface-les quand le résultat te convient.")

    write_log(Path(args.log) if args.log else root / "conversion_flac.log", root, entries, args, summary)
    return 1 if counts.get("erreur") or counts.get("écart") else 0


if __name__ == "__main__":
    sys.exit(main())
