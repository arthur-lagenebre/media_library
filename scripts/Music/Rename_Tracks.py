#!/usr/bin/env python3
r"""
Rename_Tracks.py — Renomme les pistes des albums .flac et .mp3 avec les titres MusicBrainz.

Format appliqué :  "{numéro} - {titre}.flac" (ou .mp3, l'extension ne change pas)
  - Le numéro est zéro-paddé pour avoir le MÊME nombre de chiffres dans tout l'album (largeur = nb de chiffres du plus long disque, minimum 2).  ex : 01, 02, ... 14
  - Un album en plusieurs disques rangés dans le même dossier préfixe le numéro du disque : "2-01 - Alive 1997.flac". Rangés dans CD1, CD2..., chaque dossier de disque repart de 01.
  - Un "/" dans un titre devient "-" : "Robot Rock / Oh Yeah" -> "01 - Robot Rock - Oh Yeah.flac". Windows l'interdit, et le supprimer collerait les morceaux d'un medley.
  - Les PAROLES posées à côté (.lrc) suivent leur piste : "01 Prelude.lrc" -> "01 - Prelude.lrc".
  - Ne touche qu'au NOM : ni les tags, ni le son, ni les dossiers. Aucun outil externe, juste Internet pour MusicBrainz.

C'est le pendant de TV_Shows/Rename_Episodes.py pour la musique. L'album est reconnu exactement comme par Metadata.py : --mbid, puis l'identifiant épinglé dans le nom du dossier, puis celui que TOUS les fichiers déclarent, puis la recherche sur les tags ALBUM et ALBUMARTIST et sur le nom du dossier. Passé après Metadata.py, il ne cherche donc plus rien : l'identifiant est dans les fichiers, et la fiche dans le cache.
Chaque fichier est placé sur sa piste comme pour l'étiquetage : par son numéro (tags, dossier de disque, nom), puis par son titre. Un seul fichier sans piste et l'album n'est PAS renommé : à moitié renommé, il aurait l'air fait.
Deux albums différents du même titre qui tiennent tous les deux sont une QUESTION, posée à la fin du passage ; --no-ask garde le premier.

Usage :
  python Rename_Tracks.py --dir "D:\Musique"                 # simulation
  python Rename_Tracks.py --dir "D:\Musique" --apply         # renomme
  python Rename_Tracks.py --dir "D:\Musique\Kavinsky\2013 - Outrun" --mbid 4e5d9f0c-09b6-42bf-b495-e2d7cc288bf6 --apply

Options : --apply --no-cache --no-ask --mbid --country (défaut FR)

Seuls les .flac et les .mp3 sont renommés, comme seuls ils sont étiquetés : ce sont leurs tags qui reconnaissent l'album et placent chaque fichier. Un dossier de .m4a, .ogg... est signalé et laissé tel quel.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # pour importer libraries
from libraries.common import cache, cli, filenames, rename  # noqa: E402
from libraries.music import album as albums  # noqa: E402
from libraries.music import lookup  # noqa: E402
from libraries.music.musicbrainz import MusicBrainz, MusicBrainzError, release_url  # noqa: E402


def track_stem(medium, track, width, with_disc=False):
    """Nom visé pour une piste, sans extension : "03 - Protovision", ou "2-01 - Alive 1997" quand le disque doit s'y lire."""
    position = track.get("position") or 0
    number = f"{medium.get('position')}-{position:0{width}d}" if with_disc else f"{position:0{width}d}"
    title = track.get("title") or (track.get("recording") or {}).get("title") or ""
    return f"{number} - {filenames.safe_name(title.replace('/', '-'))}"


def plan_album(found, release):
    """Prévoit les renommages d'un album dont l'édition est arrêtée. Retourne (planned, tally).

    `planned` = [(source, destination), ...], pistes et paroles mélangées. Chaque fichier étant placé sur une piste distincte, deux fichiers d'un même dossier ne visent jamais le même nom : pas de doublon à guetter, contrairement aux épisodes.
    """
    album, metas = found.album, found.metas
    entries = [albums.entry_for(path, metas[path], album.disc_folder(path)) for path in album.files]
    placed, reason = albums.match_tracks(entries, release)
    tally = rename.Tally()
    if reason:
        tally.unresolved = 1
        print(f"  [NON TRAITÉ] rien ne sera renommé : {reason}")
        print(f"      si l'édition n'est pas la bonne, épingle la bonne : ' [mbid-...]' dans le nom du dossier ({release_url(release.get('id'))})")
        return [], tally

    several_discs = len(release.get("media") or []) > 1
    width = max(2, len(str(max(albums.track_counts(release), default=0))))
    planned = []
    for entry in sorted(entries, key=lambda e: (placed[e.path][0].get("position") or 0, placed[e.path][1].get("position") or 0)):
        medium, track = placed[entry.path]
        # Rangé dans CD2, le dossier dit déjà de quel disque il s'agit ; à plat, seul le nom peut le dire.
        stem = track_stem(medium, track, width, with_disc=several_discs and album.disc_folder(entry.path) is None)
        target = entry.path.with_name(stem + entry.path.suffix.lower())
        lyrics = [(src, dst) for src, dst in rename.sidecar_renames(entry.path, stem, albums.LYRICS_EXTS) if dst != src]
        notes = albums.entry_notes(entry, track)
        moves = target.name != entry.path.name

        if moves or lyrics or notes:
            print(f"  {filenames.relative_name(entry.path, album.folder)}")
        if moves:
            planned.append((entry.path, target))
            print(f"       -> {target.name}")
        else:
            tally.named += 1
        for note in notes:
            print(f"       /!\\ {note}")
        for src, dst in lyrics:
            planned.append((src, dst))
            tally.subtitles += 1
            print(f"       + {src.name}  ->  {dst.name}")
    if not planned:
        print("  toutes les pistes sont déjà au bon nom")
    return planned, tally


def rename_album(found, release, args):
    """Affiche le plan d'un album et l'applique si --apply. Retourne son Tally, sans le total : main le compte d'avance."""
    planned, tally = plan_album(found, release)
    if args.apply:
        renamed = rename.apply_renames(planned)
        tracks = {src for src, _ in planned if src.suffix.lower() in albums.AUDIO_EXTS}
        tally.named += len(tracks & renamed)
        tally.subtitles = len(renamed - tracks)   # ce qui a vraiment bougé
    return tally


def rename_pending(pending, args, mb):
    """Pose les questions mises de côté, puis renomme les albums confirmés. Retourne leur Tally."""
    tally = rename.Tally()
    for found, chosen in lookup.confirm(pending):
        if chosen is None:
            tally.unresolved += 1
            continue
        try:
            release, _ = lookup.fetch_release(chosen["id"], mb, with_genres=False)
        except MusicBrainzError as e:
            print(f"      échec MusicBrainz : {e}\n")
            tally.unresolved += 1
            continue
        tally += rename_album(found, release, args)
        print()
    return tally


# ----------------------------------------------------------------------------
# Programme principal
# ----------------------------------------------------------------------------
def parse_args():
    ap = argparse.ArgumentParser(description="Renomme les pistes des albums .flac et .mp3 au format '{numéro} - {titre}.flac' (données MusicBrainz).")
    ap.add_argument("--dir", required=True, help="Dossier de musique, parcouru récursivement (dossiers d'artiste et de disque compris)")
    ap.add_argument("--mbid", help="Force l'identifiant MusicBrainz de l'édition (si --dir ne contient qu'un album)")
    ap.add_argument("--country", default="FR", help="Pays préféré parmi les éditions d'un album, code à deux lettres (défaut : FR)")
    ap.add_argument("--no-cache", action="store_true", help="Ignore le cache des réponses MusicBrainz et le rafraîchit")
    ap.add_argument("--no-ask", action="store_true", help="Ne pose aucune question : garde le 1er album qui tient")
    ap.add_argument("--apply", action="store_true", help="Renomme réellement (défaut : simulation)")
    args = ap.parse_args()
    args.country = args.country.upper()
    if args.mbid:
        mbid = albums.parse_mbid(args.mbid)
        if mbid is None:
            ap.error(f"--mbid attend un identifiant MusicBrainz (8-4-4-4-12 hexadécimaux), pas '{args.mbid}'")
        args.mbid = mbid
    return args


def main():
    args = parse_args()
    cli.setup_console()
    cli.check_dir(args.dir)
    mb = MusicBrainz(cache=cache.Cache(read=not args.no_cache, source="musicbrainz"))
    mode = cli.mode_label(args, "rien ne sera renommé ; ajoute --apply")
    print(f"=== {mode} ===   source : MusicBrainz, éditions {args.country} de préférence\n")

    found_albums = albums.find_albums(args.dir)
    if not found_albums:
        print(f"Aucun album trouvé dans : {args.dir}")
        return 0
    writable = [a for a in found_albums if a.files]
    if args.mbid and len(writable) > 1:
        print(f"Note : --mbid ne s'applique qu'à un seul album ; {len(writable)} détectés -> id ignoré, recherche par nom.\n")

    # Le total est compté d'avance : les pistes d'un album non reconnu restent comptées comme mal nommées, sans que chaque échec ait à y penser.
    tally, pending = rename.Tally(total=sum(len(a.files) for a in writable)), []
    for album in found_albums:
        print(f"--- {album.display} ---")
        if not album.files:
            kinds = ", ".join(sorted({p.suffix.lower() for p in album.unsupported}))
            print(f"  [NON PRIS EN CHARGE] {len(album.unsupported)} fichier(s) {kinds} : seuls les .flac et .mp3 sont renommés\n")
            continue
        if album.unsupported:
            print(f"  /!\\ {len(album.unsupported)} fichier(s) d'un autre format ignoré(s) : l'album est compté sans eux")
        metas, errors = lookup.read_album(album)
        if errors:
            print("  [NON TRAITÉ] fichier(s) illisible(s) :")
            for error in errors:
                print(f"      - {error}")
            print()
            tally.unresolved += 1
            continue

        found = lookup.Found(album, metas)
        try:
            release, _ = lookup.resolve(found, mb, forced=args.mbid if len(writable) == 1 else None, country=args.country, ask=not args.no_ask, with_genres=False)
        except MusicBrainzError as e:
            print(f"  échec MusicBrainz : {e}\n")
            tally.unresolved += 1
            continue
        if found.choice is not None:
            pending.append(found)
        elif release is None:
            tally.unresolved += 1
        else:
            tally += rename_album(found, release, args)
        print()

    if pending:
        tally += rename_pending(pending, args, mb)

    lyrics = (f", {tally.subtitles} fichier(s) de paroles " + ("renommé(s)" if args.apply else "à renommer")) if tally.subtitles else ""
    print(f"TOTAL : {tally.named}/{tally.total} piste(s) au bon nom{lyrics}.")
    if tally.unresolved:
        print(f"\nÀ CORRIGER : {tally.unresolved} album(s) non traité(s) (non reconnu(s), illisible(s), à confirmer ou MusicBrainz injoignable).")
    return 1 if tally.unresolved else 0


if __name__ == "__main__":
    sys.exit(main())
