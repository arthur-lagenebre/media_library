#!/usr/bin/env python3
r"""
Flac_To_Mp3.py - Copie MP3 (320 kb/s ou V0) d'une bibliothèque FLAC, dans un dossier à part.

Le FLAC reste la copie de référence : c'est le seul format qui rende exactement le son d'origine. Mais un téléphone, un autoradio ou une clé USB n'en veulent pas toujours, et un album FLAC pèse trois fois son équivalent MP3. Ce script fabrique cette copie de poche sans toucher à l'original : les .mp3 sont écrits sous --output-dir, dans la même arborescence (Artiste\Album\01 - Titre.mp3), et rien n'est jamais écrit, renommé ni effacé sous --dir.

320 kb/s à débit constant par défaut (LAME, par ffmpeg) : le plus haut débit du MP3, lu par tous les appareils, y compris ceux que le débit variable trouble. --quality v0 choisit le meilleur réglage à débit variable de LAME (autour de 245 kb/s) : le même son à l'oreille, pour un quart de place en moins.

Tags et images suivent : ffmpeg n'encode que le son, puis tous les tags du .flac (identifiants MusicBrainz compris) et ses images sont écrits en ID3v2.4 par libraries/music/mp3.py, comme Music/Metadata.py et Picard les écrivent - un .mp3 produit ici se relit à l'identique dans l'un comme dans l'autre. Le son d'un .flac en haute résolution est ramené à 48 kHz (ou 44,1 kHz pour les multiples de 44,1), le plus haut que le MP3 connaisse.

Le .mp3 s'écrit d'abord sous un nom provisoire (Piste.mp3.part) et ne prend son nom qu'une fois contrôlé : chaîne de trames saine de bout en bout (le contrôle de Verify_Mp3.py) et durée égale à celle du .flac. Une coupure, un échec ou un fichier suspect ne laissent aucun .mp3 tronqué, que le passage suivant aurait pris pour une conversion déjà faite. Un .mp3 déjà présent est laissé tel quel : un second passage ne convertit que les nouveautés.

Usage :
  python Flac_To_Mp3.py --dir "D:\Musique" --output-dir "E:\Musique MP3"            # simulation
  python Flac_To_Mp3.py --dir "D:\Musique" --output-dir "E:\Musique MP3" --apply    # convertit
  python Flac_To_Mp3.py --dir "D:\Musique" --output-dir "E:\Musique MP3" --apply --quality v0
  python Flac_To_Mp3.py --dir "D:\Musique\Radiohead" --output-dir "E:\Musique MP3\Radiohead" --apply

Options : --apply --quality 320|v0 --overwrite --no-recursive --log FICHIER (journal du passage ; défaut : aucun)

Dépendance EXTERNE : ffmpeg (FFmpeg, avec l'encodeur libmp3lame, présent dans les versions de winget). Aucune dépendance pip, aucun accès réseau : ce script ne parle qu'aux fichiers.
"""

import argparse
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # pour importer libraries
from libraries.common import cli, filenames, journal  # noqa: E402
from libraries.common.report import Report  # noqa: E402
from libraries.common.tools import display_command, partial_path, run_tool  # noqa: E402
from libraries.music import flac, integrity, mp3  # noqa: E402
from libraries.music.tags import AudioError  # noqa: E402

# --quality -> (réglage de LAME, libellé). V0 est le meilleur réglage à débit variable de LAME : à l'oreille, le même son que 320 constant, pour un quart de place en moins.
QUALITIES = {
    "320": (["-b:a", "320k"], "MP3 320 kb/s constant"),
    "v0": (["-q:a", "0"], "MP3 V0 (débit variable, ≈ 245 kb/s)"),
}
MAX_RATE = 48000              # le MP3 ne connaît rien au-delà
DURATION_TOLERANCE = 0.5      # secondes : LAME ajoute moins d'une trame de silence au début et à la fin ; un fichier coupé perd bien plus
DROPPED_TAGS = {"ENCODER"}    # dit quel logiciel a encodé le .flac : faux une fois recopié dans un .mp3


def parse_args():
    p = argparse.ArgumentParser(description="Convertit les .flac d'un dossier en .mp3 (320 kb/s ou V0), dans un autre dossier qui reprend la même arborescence (récursivement par défaut).")
    p.add_argument("--dir", required=True, help="dossier des .flac, jamais modifié")
    p.add_argument("--output-dir", required=True, help="dossier où écrire les .mp3, dans la même arborescence que --dir (créé au besoin)")
    p.add_argument("--apply", action="store_true", help="convertit réellement (défaut : simulation)")
    p.add_argument("--quality", choices=sorted(QUALITIES), default="320", help="320 : 320 kb/s constant, lu partout (défaut) ; v0 : débit variable autour de 245 kb/s, un quart plus léger")
    p.add_argument("--overwrite", action="store_true", help="réencode un .mp3 déjà présent au lieu de passer son tour")
    p.add_argument("--no-recursive", action="store_true", help="ne convertit que les .flac posés directement dans --dir, sans descendre dans les sous-dossiers")
    journal.add_option(p)
    args = p.parse_args()
    args.output_dir = Path(args.output_dir)
    return args


def check_output_dir(root, output_dir):
    """Refuse un dossier de sortie qui serait --dir lui-même ou l'un de ses sous-dossiers : les .mp3 se mêleraient aux .flac qu'ils copient."""
    source, target = root.resolve(), output_dir.resolve()
    if target == source or source in target.parents:
        sys.exit(f"--output-dir doit être hors de --dir : {output_dir} est dans {root}")


def flac_files(root, recursive=True):
    """Les .flac sous root : ceux posés à la racine d'abord, puis dossier par dossier - le même ordre que Wav_To_Flac.py."""
    found = root.rglob("*") if recursive else root.glob("*")
    files = (f for f in found if f.is_file() and f.suffix.lower() == ".flac")
    return sorted(files, key=lambda p: (p.parent != root, str(p.parent).lower(), p.name.lower()))


def target_path(source, root, output_dir):
    """Où va le .mp3 d'un .flac : le même chemin relatif, sous output_dir."""
    return output_dir / source.relative_to(root).with_suffix(".mp3")


def output_rate(sample_rate):
    """Fréquence à imposer à l'encodeur, ou None quand celle du .flac convient : 96 kHz donne 48 kHz, 88,2 ou 176,4 kHz donnent 44,1 kHz."""
    if sample_rate <= MAX_RATE:
        return None
    return MAX_RATE if sample_rate % MAX_RATE == 0 else 44100


def build_command(source, output, sample_rate, quality="320"):
    """La commande ffmpeg qui encode le son d'un .flac en MP3, au réglage de LAME que donne `quality` (une clé de QUALITIES).

    Le son seul : `-map 0:a:0` laisse l'image de côté, `-map_metadata -1` et `-id3v2_version 0` empêchent ffmpeg d'écrire ses propres tags - c'est mp3.py qui les écrit ensuite, à la manière de Picard. `-f mp3` est obligatoire, ffmpeg ne devinerait pas le format d'un nom en .part ; `-bitexact` l'empêche de signer le fichier de sa version.
    """
    command = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source), "-map", "0:a:0", "-map_metadata", "-1",
               "-c:a", "libmp3lame", *QUALITIES[quality][0]]
    rate = output_rate(sample_rate)
    if rate:
        command += ["-ar", str(rate)]
    return command + ["-id3v2_version", "0", "-fflags", "+bitexact", "-f", "mp3", str(output)]


def last_error(result):
    """Dernière ligne d'erreur de ffmpeg : avec `-v error` c'est elle qui dit pourquoi."""
    lines = [line.strip() for line in (result.stderr or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def copied_tags(meta):
    """Les tags du .flac à écrire dans le .mp3 : tous, hors ceux qui décrivent le .flac lui-même."""
    return [(key, value) for key, value in meta.comments if key.upper() not in DROPPED_TAGS]


def _encode(command, partial):
    """Lance ffmpeg, qui écrit sous le nom provisoire. L'échec est un message, None quand il a écrit."""
    partial.unlink(missing_ok=True)           # reste d'un passage interrompu : il ne doit pas passer pour la sortie de celui-ci
    result = run_tool(command)
    if result.returncode != 0 or not partial.exists():
        return last_error(result) or "ffmpeg n'a rien pu écrire"
    return None


def _tag(partial, meta):
    """Écrit dans le .mp3 les tags et les images du .flac. L'échec est un message, None quand c'est fait."""
    try:
        mp3.write(partial, mp3.read(partial), copied_tags(meta), meta.pictures)
    except AudioError as exc:
        return f"tags non écrits : {exc}"
    return None


def _check(partial, meta):
    """Le .mp3 produit, relu avant de prendre son nom : trames saines, durée du .flac. L'échec est un message, None quand il est bon."""
    defect = integrity.mp3_defect(partial)
    if defect:
        return f"le .mp3 produit est défectueux ({defect}) : il n'a pas été gardé"
    try:
        produced = mp3.read(partial).duration
    except AudioError as exc:
        return f"le .mp3 produit ne se relit pas ({exc}) : il n'a pas été gardé"
    expected = meta.duration
    if expected is not None and (produced is None or abs(produced - expected) > DURATION_TOLERANCE):
        shown = "inconnue" if produced is None else f"{produced:.1f} s"
        return f"durée du .mp3 {shown} au lieu de {expected:.1f} s : il n'a pas été gardé"
    return None


def convert(source, root, args):
    """(statut, détail) : ce qu'on a fait du .flac, et ce qu'il y a à en dire. Rien n'est affiché ici."""
    final = target_path(source, root, args.output_dir)
    if final.exists() and not args.overwrite:
        return "ignoré", f"{final.name} existe déjà (--overwrite pour le réencoder)"
    try:
        meta = flac.read(source)
    except AudioError as exc:
        return "erreur", f"illisible : {exc}"

    partial = partial_path(final)
    command = build_command(source, partial if args.apply else final, meta.sample_rate, args.quality)
    if not args.apply:
        return "simule", display_command(command)

    try:
        final.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return "erreur", f"{final.parent} n'a pas pu être créé : {exc.strerror or exc}"
    try:
        failure = _encode(command, partial) or _tag(partial, meta) or _check(partial, meta)
        if failure:
            return "erreur", failure
        size_flac, size_mp3 = source.stat().st_size, partial.stat().st_size
        try:
            os.replace(partial, final)
        except OSError as exc:
            return "erreur", f"{final.name} n'a pas pu être écrit : {exc.strerror or exc}"
    finally:
        partial.unlink(missing_ok=True)       # déjà renommé : rien à faire ; sinon (échec, Ctrl-C) rien ne doit traîner
    note = f"{len(copied_tags(meta))} tag(s), {len(meta.pictures)} image(s)"
    if size_flac:
        note += f", {size_mp3 / size_flac:.0%} de la taille du .flac"
    return "converti", note


def main():
    cli.setup_console()
    args = parse_args()
    with journal.record(args.log):
        return run(args)


def run(args):
    root = cli.check_dir(args.dir)
    check_output_dir(root, args.output_dir)
    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg est introuvable dans le PATH.\n"
                 "  Installe FFmpeg : winget install Gyan.FFmpeg")

    files = flac_files(root, recursive=not args.no_recursive)
    scope = "dans" if args.no_recursive else "sous"
    if not files:
        sys.exit(f"Aucun .flac {scope} {root}")
    print(f"=== {cli.mode_label(args, 'rien ne sera converti ; ajoute --apply')} ===")
    print(f"{len(files)} fichier(s) .flac {scope} {root}" + (" (sous-dossiers ignorés)" if args.no_recursive else ""))
    print(f"{QUALITIES[args.quality][1]}, écrits sous {args.output_dir} ; les .flac ne sont pas touchés.\n")

    counts, start = {}, time.time()
    for n, path in enumerate(files, 1):
        print(f"  [{n}/{len(files)}] {filenames.relative_name(path, root)}")
        status, detail = convert(path, root, args)
        print(f"          {'[ERREUR] ' if status == 'erreur' else ''}{detail}")
        counts[status] = counts.get(status, 0) + 1

    report = Report(total=len(files), failures=counts.get("erreur", 0))
    summary = ", ".join(f"{count} {status}" for status, count in sorted(counts.items()))
    print(f"\nTOTAL : {len(files)} fichier(s) en {cli.readable_time(time.time() - start)} - {summary}.")
    if not args.apply:
        print("Simulation : rien n'a été écrit. Ajoute --apply pour convertir.")
    if report.exit_code:
        print(f"À corriger : {report.epilogue()} (aucun .mp3 partiel n'a été laissé).")
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
