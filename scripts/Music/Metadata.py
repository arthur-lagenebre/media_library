#!/usr/bin/env python3
r"""
Metadata.py — Étiquette des albums .flac et .mp3 à partir de MusicBrainz.

Même principe que Movies/Metadata.py, pour la musique : la base de référence est MusicBrainz (ouverte, sans clé), les pochettes viennent de Cover Art Archive, et tout est écrit DIRECTEMENT dans chaque .flac (commentaires Vorbis) ou .mp3 (étiquette ID3v2.4), sans outil externe.

Écrit, pour chaque piste, les tags sous les noms qu'emploie Picard :
  - titre, artiste(s) crédité(s), album, artiste de l'album, noms de tri
  - numéro de piste et de disque, et leurs totaux
  - date de l'édition, date de première sortie de l'album, genres votés  [--no-genres]
  - label, numéro de catalogue, code-barres, pays, type et statut de la sortie, support
  - les IDENTIFIANTS MusicBrainz (album, release group, artistes, enregistrement, piste)
  - la pochette (recto) quand le fichier n'en a pas  [--no-cover, --replace-cover]

Tout ce qui ne vient pas de MusicBrainz reste en place : ReplayGain, paroles, notes, ISRC... Une clé n'est gérée que si la base lui donne une valeur - un genre écrit à la main survit à un album sans genre - sauf celles qui décrivent l'édition (label, code-barres, identifiants), qui mentiraient si elles restaient d'une autre.
L'écriture se fait sur place tant que les tags tiennent dans le padding du fichier (ou de l'étiquette ID3) ; sinon (une pochette ajoutée, typiquement) le fichier est recopié à côté puis substitué, le son intact.

Un album est un dossier qui contient des .flac ou des .mp3, lui ou ses dossiers de disque (CD1, CD2...). --dir est parcouru récursivement : les dossiers d'artiste au-dessus ne font que ranger.
L'album est cherché d'après les tags ALBUM et ALBUMARTIST de ses fichiers, puis d'après le nom du dossier ("1994 - Born Dead", "Daft Punk - Discovery (2001) FLAC [...]").
Seules comptent les éditions qui ont exactement autant de pistes que le dossier a de fichiers : c'est ce qui départage l'album du single, le CD de 17 pistes du pressage de 16. Parmi elles, l'édition officielle de l'année du dossier, du pays --country (défaut FR), puis européenne, puis mondiale.
Chaque fichier est placé sur sa piste par son numéro (tags, dossier de disque, nom), puis par son titre. Un seul fichier sans piste et l'album n'est PAS traité : à moitié étiqueté, il aurait l'air fait.
Deux albums différents du même titre qui tiennent tous les deux sont une QUESTION, posée à la fin du passage, comme pour les films ; --no-ask garde le premier.

L'identifiant de l'édition retenue (MUSICBRAINZ_ALBUMID) est inscrit dans chaque fichier : au passage suivant il est relu, plus rien n'est cherché.
Ordre de priorité : --mbid, puis l'identifiant épinglé dans le NOM du dossier ("2013 - Outrun [mbid-4e5d9f0c-09b6-42bf-b495-e2d7cc288bf6]"), puis celui que TOUS les fichiers déclarent, puis la recherche.

MusicBrainz écrit parfois le même artiste de plusieurs façons d'un album à l'autre ("H.F. Thiéfaine", "Thiéfaine", "Hubert-Félix Thiéfaine"), ce qui éparpille ses albums. Pour imposer l'écriture : un fichier "artist.txt" dans le dossier d'artiste (sa première ligne est le nom ; le plus proche de l'album l'emporte), ou --artist "Nom" pour tout ce que --dir contient. Seul le crédit qui désigne cet artiste est réécrit - "Thiéfaine / Mairet" devient "Hubert-Félix Thiéfaine / Mairet" - dans ARTIST et ALBUMARTIST ; les identifiants et les noms de tri restent ceux de MusicBrainz.

Usage :
  python Metadata.py --dir "D:\Musique"                  # simulation (n'écrit rien)
  python Metadata.py --dir "D:\Musique" --apply          # applique
  python Metadata.py --dir "D:\Musique" --verify         # vérifie seulement
  python Metadata.py --dir "D:\Musique\Kavinsky\2013 - Outrun" --mbid 4e5d9f0c-09b6-42bf-b495-e2d7cc288bf6 --apply

Options : --apply --verify --no-cache --no-ask --no-cover --replace-cover --no-genres --mbid --artist --country (défaut FR) --image-size (défaut 1200)

Aucune dépendance pip, aucun outil externe. Nécessite Internet (MusicBrainz + Cover Art Archive), à raison d'une requête par seconde - la règle de MusicBrainz - que le cache (7 jours) épargne aux passages suivants.
Seuls les .flac et les .mp3 sont écrits : un dossier de .m4a, .ogg... est signalé et laissé tel quel. Dans un .mp3, les tags portent les noms de trames de Picard (TXXX "MusicBrainz Album Id"...), les ID3v2.3 sont réécrits en 2.4, et l'étiquette ID3v1 de fin de fichier n'est pas touchée.
À chaque passage, un JOURNAL "metadata.log" est écrit à la racine de --dir : le lien MusicBrainz de chaque album, ceux qui n'en ont pas à la fin.
"""

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # pour importer libraries
from libraries.common import cache, cli  # noqa: E402
from libraries.common.report import Report  # noqa: E402
from libraries.common import filenames  # noqa: E402
from libraries.music import album as albums  # noqa: E402
from libraries.music import audio, lookup  # noqa: E402
from libraries.music.musicbrainz import COVER_SIZES, MusicBrainz, MusicBrainzError, release_url  # noqa: E402


# ----------------------------------------------------------------------------
# 1. Écriture d'un album
# ----------------------------------------------------------------------------
class CoverCache:
    """La pochette d'un album, téléchargée une fois pour toutes ses pistes, et seulement s'il en faut une.

    Quand l'édition retenue n'a pas d'image, celle du release group fait l'affaire : c'est la même pochette d'album. Mesuré sur "Bloodlust" : le CD européen n'en a aucune, le release group si. La fiche de la sortie dit si elle a la sienne, ce qui épargne une requête vouée au 404.
    """

    def __init__(self, release, mb, size):
        self.release, self.mb, self.size = release, mb, size
        self.own = bool((release.get("cover-art-archive") or {}).get("front"))
        self.group = (release.get("release-group") or {}).get("id")
        self.picture, self.tried = None, False

    @property
    def possible(self):
        return self.own or bool(self.group)

    @property
    def label(self):
        return "pochette" if self.own else "pochette du release group (si elle existe)"

    def get(self):
        if not self.tried:
            self.tried = True
            try:
                data = self.mb.cover(self.release.get("id") if self.own else None, self.group, self.size)
                if data is None:
                    print("      aucune pochette sur Cover Art Archive pour cet album")
            except MusicBrainzError as e:
                print(f"      pochette ignorée ({e})")
                data = None
            self.picture = audio.front_cover(data) if data else None
        return self.picture


def process_album(found, release, group, args, mb):
    """Place chaque fichier sur sa piste, compare, et écrit si --apply. Retourne le Report de l'album."""
    album, metas = found.album, found.metas
    entries = [albums.entry_for(path, metas[path], album.disc_folder(path)) for path in album.files]
    placed, reason = albums.match_tracks(entries, release)
    if reason:
        print(f"  [NON TRAITÉ] rien n'a été modifié : {reason}")
        print(f"      si l'édition n'est pas la bonne, épingle la bonne : ' [mbid-...]' dans le nom du dossier ({release_url(release.get('id'))})")
        return Report(matched=1, total=1, skipped=1)

    report = Report(matched=1, total=1)
    if found.artist_name:
        print(f"  artiste imposé : {found.artist_name}")
        if not any(albums.names_artist(c, found.artist_name) for c in release.get("artist-credit") or []):
            print(f"      /!\\ aucun artiste crédité de l'album ne ressemble à '{found.artist_name}' : les noms de MusicBrainz sont gardés")
    covers = CoverCache(release, mb, args.image_size)
    for entry in sorted(entries, key=lambda e: (placed[e.path][0].get("position") or 0, placed[e.path][1].get("position") or 0)):
        medium, track = placed[entry.path]
        meta = metas[entry.path]
        target = albums.target_tags(release, group, medium, track, with_genres=not args.no_genres, artist=found.artist_name)
        diffs =albums.differences(meta.comments, target)
        wants_cover = not args.no_cover and covers.possible and (args.replace_cover or not meta.has_front_cover)
        # --verify n'exige que la pochette que la sortie déclare : celle du release group n'existe peut-être pas, et l'exiger signalerait un écart que rien ne comble.
        missing_cover = not args.no_cover and covers.own and not meta.has_front_cover
        # L'Explorateur de Windows ne lit rien d'un en-tête de plus de 4 Mio : quand c'est le padding qui l'enfle, recopier le fichier suffit à le rendre lisible.
        shrink = meta.bloated

        name = filenames.relative_name(entry.path, album.folder)       # CD1/ et CD2/ se distinguent
        print(f"  [{medium.get('position')}-{track.get('position'):02d}] {name} -> {track.get('title')}")
        for note in albums.entry_notes(entry, track):
            print(f"      /!\\ {note}")
        if meta.heavy_header:
            print(f"      /!\\ en-tête de {(meta.audio_offset - meta.padding) / 1048576:.1f} Mo sans le padding : l'Explorateur Windows n'en lit rien (--replace-cover remplace la pochette)")
        if args.verify:
            for key, current, wanted in diffs:
                print(f"      [DIFF] {key} : {', '.join(current) or '(absent)'} -> {', '.join(wanted) or '(retire)'}")
            if missing_cover:
                print("      [DIFF] pochette : absente")
            if shrink:
                print(f"      [DIFF] en-tête : {meta.audio_offset / 1048576:.1f} Mo dont {meta.padding / 1048576:.1f} Mo de padding, illisible pour l'Explorateur Windows")
            if diffs or missing_cover or shrink:
                report.diffs += 1
            else:
                print("      [OK] déjà conforme")
            continue

        changes = ([f"{len(diffs)} tag(s) : " + ", ".join(k for k, _, _ in diffs[:6]) + (" ..." if len(diffs) > 6 else "")] if diffs else []) + ([covers.label] if wants_cover else []) + (["padding à retirer (en-tête illisible par Windows)"] if shrink else [])
        if not changes:
            print("      déjà conforme")
            continue
        print(f"      à écrire : {' + '.join(changes)}")
        if not args.apply:
            continue

        pictures = meta.pictures
        if wants_cover:
            cover = covers.get()
            if cover is not None:
                pictures = [cover] + [p for p in meta.pictures if p.kind != audio.FRONT_COVER]
            elif not diffs and not shrink:
                continue
        try:
            mode = audio.write(entry.path, meta, albums.merge(meta.comments, target), pictures)
            print(f"      [OK] {mode}")
        except audio.AudioError as e:
            print(f"      [ÉCHEC] {e}")
            report.failures += 1
    return report


# ----------------------------------------------------------------------------
# 2. Questions de fin de passage, journal
# ----------------------------------------------------------------------------
@dataclass
class Journal:
    """Le sort de chaque album, pour le journal de fin de passage."""
    entries: list = field(default_factory=list)   # (nom affiché, MBID, statut)

    def note(self, display, mbid=None, status=""):
        self.entries.append((display, mbid, status))


def handle(found, release, group, journal, args, mb):
    """Traite un album dont l'édition est arrêtée, et le consigne. Retourne son Report."""
    report = process_album(found, release, group, args, mb)
    journal.note(found.album.display, release.get("id"), "[NON TRAITÉ]" if report.skipped else "")
    return report


def resolve_pending(pending, journal, args, mb):
    """Pose les questions mises de côté, puis traite les albums confirmés. Retourne leur Report."""
    report = Report()
    for found, chosen in lookup.confirm(pending):
        if chosen is None:
            report += Report(matched=1, total=1, pending=1)
            journal.note(found.album.display, None, "[À CONFIRMER]")
            continue
        try:
            release, group = lookup.fetch_release(chosen["id"], mb, with_genres=not args.no_genres)
        except MusicBrainzError as e:
            print(f"      échec MusicBrainz : {e}\n")
            report += Report(total=1)
            journal.note(found.album.display, None, "[ÉCHEC MUSICBRAINZ]")
            continue
        report += handle(found, release, group, journal, args, mb)
        print()
    return report


def write_log(root, journal, args, report):
    """Écrit le journal du passage : un lien MusicBrainz par album, les vides à la fin."""
    out = Path(root) / "metadata.log"
    linked = [(name, mbid, status) for name, mbid, status in journal.entries if mbid]
    empty = [(name, status) for name, mbid, status in journal.entries if not mbid]
    width = min(max((len(name) for name, _, _ in journal.entries), default=0), 70)

    lines = [f"# Music/Metadata.py - {Path(root).resolve()}", f"# {datetime.now():%Y-%m-%d %H:%M} - {cli.mode_label(args)}", f"# {report.matched}/{report.total} album(s) associé(s)", ""]
    lines += [f"{name:<{width}}  {release_url(mbid)}" + (f"  {status}" if status else "") for name, mbid, status in linked]
    if empty:
        lines += ["", f"# --- sans lien ({len(empty)}) ---"] + [f"{name:<{width}}  {status}" for name, status in empty]
    try:
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as e:
        print(f"[log] {out.name} non écrit : {e}")
        return
    print(f"[log] {out.name} écrit ({len(linked)} lien(s), {len(empty)} sans lien)")


# ----------------------------------------------------------------------------
# 3. Programme principal
# ----------------------------------------------------------------------------
def parse_args():
    ap = argparse.ArgumentParser(description="Étiquette des albums .flac et .mp3 depuis MusicBrainz.")
    ap.add_argument("--dir", required=True, help="Dossier de musique, parcouru récursivement (dossiers d'artiste et de disque compris)")
    ap.add_argument("--mbid", help="Force l'identifiant MusicBrainz de l'édition (si --dir ne contient qu'un album)")
    ap.add_argument("--artist", help="Nom d'artiste à écrire à la place de celui de MusicBrainz, pour tous les albums de --dir (un fichier artist.txt dans un dossier d'artiste le fait pour ce dossier seul)")
    ap.add_argument("--country", default="FR", help="Pays préféré parmi les éditions d'un album, code à deux lettres (défaut : FR)")
    ap.add_argument("--no-cache", action="store_true", help="Ignore le cache des réponses MusicBrainz et le rafraîchit")
    ap.add_argument("--no-ask", action="store_true", help="Ne pose aucune question : garde le 1er album qui tient")
    ap.add_argument("--apply", action="store_true", help="Applique réellement (défaut : simulation)")
    ap.add_argument("--verify", action="store_true", help="Vérifie seulement (aucune écriture)")
    ap.add_argument("--no-cover", action="store_true", help="N'embarque aucune pochette")
    ap.add_argument("--replace-cover", action="store_true", help="Remplace aussi les pochettes déjà embarquées par celle de Cover Art Archive")
    ap.add_argument("--no-genres", action="store_true", help="N'écrit pas les genres, et laisse ceux des fichiers")
    ap.add_argument("--image-size", default="1200", choices=COVER_SIZES, help="Taille des pochettes Cover Art Archive (défaut : 1200)")
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
    print(f"=== {cli.mode_label(args)} ===   source : MusicBrainz, éditions {args.country} de préférence\n")

    found_albums = albums.find_albums(args.dir)
    if not found_albums:
        print(f"Aucun album trouvé dans : {args.dir}")
        return 0
    writable = [a for a in found_albums if a.files]
    if args.mbid and len(writable) > 1:
        print(f"Note : --mbid ne s'applique qu'à un seul album ; {len(writable)} détectés -> id ignoré, recherche par nom.\n")

    report, journal, pending = Report(), Journal(), []
    for album in found_albums:
        print(f"--- {album.display} ---")
        if not album.files:
            kinds = ", ".join(sorted({p.suffix.lower() for p in album.unsupported}))
            print(f"  [NON PRIS EN CHARGE] {len(album.unsupported)} fichier(s) {kinds} : seuls les .flac et .mp3 sont étiquetés\n")
            journal.note(album.display, None, "[NON PRIS EN CHARGE]")
            continue
        if album.unsupported:
            print(f"  /!\\ {len(album.unsupported)} fichier(s) d'un autre format ignoré(s) : l'album est compté sans eux")
        metas, errors = lookup.read_album(album)
        if errors:
            print("  [NON TRAITÉ] fichier(s) illisible(s) :")
            for error in errors:
                print(f"      - {error}")
            report += Report(total=1, skipped=1)
            journal.note(album.display, None, "[ILLISIBLE]")
            print()
            continue

        found = lookup.Found(album, metas, artist_name=albums.artist_override(album.folder, args.dir, args.artist))
        try:
            release, group = lookup.resolve(found, mb, forced=args.mbid if len(writable) == 1 else None, country=args.country, ask=not args.no_ask, with_genres=not args.no_genres)
        except MusicBrainzError as e:
            print(f"  échec MusicBrainz : {e}\n")
            report += Report(total=1)
            journal.note(album.display, None, "[ÉCHEC MUSICBRAINZ]")
            continue
        if found.choice is not None:
            pending.append(found)
        elif release is None:
            report += Report(total=1)
            journal.note(album.display, None, "[NON ASSOCIÉ]")
        else:
            report += handle(found, release, group, journal, args, mb)
        print()

    if pending:
        report += resolve_pending(pending, journal, args, mb)

    print(f"TOTAL : {report.matched}/{report.total} album(s) associé(s).")
    write_log(args.dir, journal, args, report)
    rest = report.epilogue()
    if rest:
        print(f"\nÀ CORRIGER : {rest}.")
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
