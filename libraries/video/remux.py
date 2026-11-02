"""Remultiplexer un conteneur vidéo en .mkv sans réencodage : ce que Avi_To_Mkv.py et Mp4_To_Mkv.py ont en commun.

Les deux passes sont la même : trouver les fichiers, les identifier, construire une commande mkvmerge, l'écrire sous un nom provisoire, comparer la durée du résultat à celle de la source, et seulement alors lui donner son nom et, si on l'a demandé, effacer l'original. Ce qui les sépare tient dans un `Container` : l'extension, la commande (les langues de pistes n'y sont pas traitées pareil) et les sous-titres que le fichier porte déjà.

Une seule copie de ce chemin, parce que c'est lui qui décide si un original survit : une correction faite d'un côté seulement laisserait l'autre côté exposé.
"""

import os
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from libraries.common import cli, filenames
from libraries.common.tools import display_command
from libraries.video.mkv import first_error, identify, partial_path, probe, run_tool

TEXT_SUB_EXT = {".srt", ".ass", ".ssa"}   # sous-titres texte : eux seuls ont un encodage
SUB_EXT = TEXT_SUB_EXT | {".idx"}         # un .sub n'est pas cité : mkvmerge le prend avec son .idx
MKVMERGE_WARNING = 1                      # mkvmerge : 1 = il a écrit malgré une remarque, 2+ = il n'a rien produit

# Suffixe de nom de fichier -> code ISO 639-2/B, le seul que mkvmerge accepte en --language.
LANG_HINTS = {
    "fr": "fre", "fre": "fre", "fra": "fre", "french": "fre", "vf": "fre", "vff": "fre", "vfq": "fre", "fr-fr": "fre", "en": "eng", "eng": "eng", "english": "eng", "vo": "eng", "vost": "eng",
    "es": "spa", "spa": "spa", "de": "ger", "ger": "ger", "deu": "ger", "it": "ita", "ita": "ita", "nl": "dut", "dut": "dut", "ja": "jpn", "jpn": "jpn", "pt": "por", "por": "por"
}


@dataclass(frozen=True)
class Container:
    """Ce qui distingue un conteneur à remultiplexer d'un autre."""
    extension: str                  # ".avi"
    log_name: str                   # journal par défaut, à la racine de --dir
    no_subtitles: str               # message de --subs require quand rien n'est à embarquer
    # (vidéo, sortie, info mkvmerge, sous-titres posés à côté, args) -> (commande, [(nom, langue, encodage)], remarque ajoutée au détail)
    plan: Callable
    embedded_subtitles: Callable = lambda info: 0            # info mkvmerge -> nombre de sous-titres que le fichier porte déjà
    intro: Callable = lambda args: []                        # args -> lignes ajoutées à la bannière


def source_files(root, extension, recursive=True):
    """Les fichiers de cette extension sous root : ceux posés à la racine d'abord, puis dossier par dossier.

    Le même ordre que Verify_Files, pour qu'un passage se relise pareil d'un script à l'autre. L'extension est comparée en minuscules plutôt que filtrée par glob : les rips d'époque écrivent volontiers ".AVI", et sous Linux le glob ne les verrait pas.
    """
    found = root.rglob("*") if recursive else root.glob("*")
    files = (f for f in found if f.is_file() and f.suffix.lower() == extension)
    return sorted(files, key=lambda p: (p.parent != root, str(p.parent).lower(), p.name.lower()))


def detect_charset(path, fallback):
    """Encodage d'un sous-titre texte : UTF-8 s'il l'est vraiment, sinon `fallback`.

    mkvmerge suppose de l'UTF-8 et n'a aucun moyen de se tromper bruyamment : un .srt en windows-1252 passe quand même, avec des accents remplacés par des losanges qu'on ne découvre qu'à la lecture du film. Le test est donc fait ici, en strict - un texte réellement UTF-8 ne peut pas échouer, un texte latin-1 accentué ne peut pas réussir.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return fallback
    if raw.startswith(b"\xef\xbb\xbf"):
        return "UTF-8"
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "UTF-16"
    try:
        raw.decode("utf-8", errors="strict")
        return "UTF-8"
    except UnicodeDecodeError:
        return fallback


def guess_sub_language(sub, video, default):
    """Langue déduite du suffixe du nom : 'Film.fr.srt' -> fre, 'Film.srt' -> défaut."""
    suffix = sub.stem[len(video.stem):].strip(". _-").lower()
    return LANG_HINTS.get(suffix, default)


def find_subtitles(video):
    """Les sous-titres posés à côté de la vidéo, qui portent son nom.

    Un .sub est ignoré volontairement : en VobSub, c'est le .idx qui décrit les deux, et mkvmerge va chercher le .sub tout seul. Le citer aurait fait entrer la même piste deux fois.
    """
    return [f for f in filenames.files_with_ext(video.parent, SUB_EXT)
            if f.stem == video.stem or f.stem.startswith(video.stem + ".")]


def attach_subtitles(command, video, subs, args):
    """Ajoute à `command` les sous-titres posés à côté, et rend [(nom, langue, encodage)].

    Une option mkvmerge s'applique au fichier qui la SUIT : chaque bloc de langue et d'encodage doit donc précéder son sous-titre. Côté sous-titres posés à côté il n'y a qu'une piste par fichier, donc toujours 0.
    """
    attached = []
    for index, sub in enumerate(subs):
        language = guess_sub_language(sub, video, args.sub_lang)
        command += ["--language", f"0:{language}"]
        charset = None
        if sub.suffix.lower() in TEXT_SUB_EXT:
            charset = detect_charset(sub, args.sub_charset)
            command += ["--sub-charset", f"0:{charset}"]
        command += ["--default-track-flag", "0:yes" if (index == 0 and args.default_sub) else "0:no"]
        command.append(str(sub))
        attached.append((sub.name, language, charset))
    return attached


def convert(video, args, check_duration, container):
    """(statut, détail) : ce qu'on a fait du fichier, et ce qu'il y a à en dire.

    Rien n'est affiché ici : c'est l'appelant qui imprime, et le journal reprend mot pour mot ce que le terminal a montré.
    """
    final = (args.output_dir or video.parent) / (video.stem + ".mkv")
    if final.exists() and not args.overwrite:
        return "ignoré", f"{final.name} existe déjà (--overwrite pour l'écraser)"

    info, problem = identify(video)
    if info is None:
        return "erreur", problem
    if not any(track.get("type") == "video" for track in info.get("tracks", [])):
        return "erreur", "aucune piste vidéo"

    subs = find_subtitles(video) if args.subs != "none" else []
    if args.subs == "require" and not subs and not container.embedded_subtitles(info):
        return "ignoré", container.no_subtitles

    # mkvmerge écrit sous un nom provisoire : le .mkv ne prend son nom qu'une fois jugé sain.
    partial = partial_path(final)
    command, attached, remark = container.plan(video, partial if args.apply else final, info, subs, args)
    note = "".join(f", {name} en {language}" + (f" ({charset})" if charset else "")
                   for name, language, charset in attached) + remark
    if not args.apply:
        return "simule", display_command(command)

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        partial.unlink(missing_ok=True)       # reste d'un passage interrompu : il ne doit pas passer pour la sortie de celui-ci
        result = run_tool(command)
        if result.returncode > MKVMERGE_WARNING or not partial.exists():
            return "erreur", first_error(result) or "mkvmerge n'a rien pu écrire"
        if result.returncode == MKVMERGE_WARNING:
            note += ", avertissement mkvmerge"

        # Un conteneur décrit sa durée dans un index ou un moov que les copies successives ont pu abîmer, ou qu'une copie coupée n'a jamais reçu :
        # mkvmerge recopie alors moins de film qu'il n'y en a, sans forcément le dire.
        unverified = "" if check_duration else "durée non contrôlée (ffprobe absent)"
        if check_duration:
            source, produced = probe(video).duration_min, probe(partial).duration_min
            if source is None or produced is None:
                unverified = "durée indéterminable"
            else:
                gap = abs(source - produced) * 60
                if gap > args.tolerance:
                    return "écart", f"{gap:.1f} s de différence avec la source : {final.name} n'a pas été écrit, l'original est gardé"
        try:
            os.replace(partial, final)
        except OSError as exc:
            return "erreur", f"{final.name} n'a pas pu être écrit : {exc.strerror or exc}"
    finally:
        partial.unlink(missing_ok=True)       # déjà renommé : rien à faire ; sinon (échec, écart, Ctrl-C) rien ne doit traîner

    if unverified:
        return "non vérifié", f"converti, {unverified}{note}"
    if args.delete_source:
        try:
            video.unlink()
            note += ", source effacée"
        except OSError as exc:
            note += f", source non effacée : {exc.strerror or exc}"
    return "converti", f"écart {gap:.2f} s{note}"


def write_log(destination, root, entries, args, summary, container):
    """Journal du passage : un fichier par ligne, avec ce qu'on en a fait."""
    lines = [
        f"Conversion du {datetime.now():%d/%m/%Y %H:%M} - {root}",
        cli.mode_label(args, "aucune conversion") + ("" if not args.no_recursive else ", sans les sous-dossiers"),
        f"{len(entries)} fichier(s) {container.extension} - {summary}",
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


def run(args, container):
    """Le passage entier, de la vérification des outils au journal. Rend le code de sortie."""
    root = cli.check_dir(args.dir)
    if shutil.which("mkvmerge") is None:
        sys.exit("mkvmerge est introuvable dans le PATH.\n"
                 "  Installe MKVToolNix : winget install MoritzBunkus.MKVToolNix")
    check_duration = shutil.which("ffprobe") is not None
    if args.delete_source and not check_duration:
        sys.exit(f"--delete-source n'efface un {container.extension} qu'après avoir comparé la durée du .mkv à la sienne,\n"
                 "et ffprobe est introuvable dans le PATH : installe FFmpeg (winget install Gyan.FFmpeg)\n"
                 "ou relance sans --delete-source.")
    if not check_duration:
        print("ffprobe absent -> la durée des fichiers produits ne sera pas contrôlée "
              "(winget install Gyan.FFmpeg)\n")

    files = source_files(root, container.extension, recursive=not args.no_recursive)
    scope = "dans" if args.no_recursive else "sous"
    if not files:
        sys.exit(f"Aucun {container.extension} {scope} {root}")
    print(f"=== {cli.mode_label(args, 'rien ne sera converti ; ajoute --apply')} ===")
    print(f"{len(files)} fichier(s) {container.extension} {scope} {root}"
          + (" (sous-dossiers ignorés)" if args.no_recursive else ""))
    print("Remultiplexage sans réencodage : l'image et le son sont recopiés tels quels.")
    for line in container.intro(args):
        print(line)
    print()

    entries, start = [], time.time()
    for n, path in enumerate(files, 1):
        name = filenames.relative_name(path, root)
        print(f"  [{n}/{len(files)}] {name}")
        status, detail = convert(path, args, check_duration, container)
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
        print(f"Les {container.extension} sont toujours à côté de leurs .mkv : étiquette-les avec "
              "Movies/Metadata.py, puis efface-les quand le résultat te convient.")

    write_log(Path(args.log) if args.log else root / container.log_name, root, entries, args, summary, container)
    return 1 if counts.get("erreur") or counts.get("écart") else 0
