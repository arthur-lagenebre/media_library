#!/usr/bin/env python3
r"""
Metadata.py — Étiquette les .mkv d'une série à partir de TMDB (données en français).

Écrit DIRECTEMENT dans chaque .mkv (sans re-encodage ni remux, c'est quasi instantané) :
  - le titre et la DATE de sortie dans les informations de segment
  - le synopsis, les numéros saison/épisode, réalisateur(s), scénariste(s), casting (tags)
  - les tags de STATISTIQUES de piste (débit, durée, nb d'images)  [--no-stats pour désactiver]
  - la vignette de l'épisode comme jaquette (attachment "cover.jpg")
  - le nom des pistes AUDIO       -> codec + canaux + débit (ex. "E-AC-3 5.1 640 kb/s"), suivi de AD ou Commentary quand la piste porte le drapeau malvoyant ou commentaire
  - le nom des pistes SOUS-TITRES -> uniquement les drapeaux actifs (Forced, SDH...), ou "Full"
  - les DRAPEAUX 'par défaut'     -> une seule piste audio par défaut (la FR, jamais une audiodescription ni un commentaire), aucun sous-titre
  - les drapeaux FORCED et SDH    -> posés sur un sous-titre dont le NOM les annonce ("Français force", "English SDH") alors que le drapeau manque - sinon, le renommer d'après ses seuls drapeaux effacerait l'information. Une seule piste par langue, et rien dans une langue qui declare déjà le drapeau.  [--no-flags]

=> Fichier 100% autonome : toutes les métadonnées voyagent avec le .mkv.

Dépendances EXTERNES (à avoir dans le PATH) :
  - mkvpropedit, mkvmerge et mkvextract   -> paquet MKVToolNix
  - ffprobe                   -> paquet FFmpeg  (pour le débit audio + la vérif. des durées)

Aucune dépendance pip. Necessite un accès Internet (API TMDB + jaquettes). Le code partage avec les autres scripts du dépôt vit dans libraries/ (à la racine).

Installation des outils (Windows) :
  winget install MoritzBunkus.MKVToolNix
  winget install Gyan.FFmpeg

Clé TMDB gratuite : themoviedb.org -> Paramètres -> API. À mettre dans le fichier .env à la racine du dépôt, sur une ligne TMDB_KEY=... : c'est la seule source.

Usage — pointe --dir sur la RACINE de la série (dossiers "Saison N") :

  # Simulation (n'écrit rien) puis application :
  python Metadata.py --dir "...\Secret Level"
  python Metadata.py --dir "...\Secret Level" --apply

  # Vérification (lecture seule) : rapporte ce qui n'est pas encore conforme.
  python Metadata.py --dir "...\Secret Level" --verify

  # La série est identifiée par recherche sur le nom du dossier ; --tmdb-id ne
  # sert qu'a corriger une recherche qui se trompe ou ne trouve rien :
  python Metadata.py --dir "...\Secret Level" --tmdb-id 261579 --apply

Structure attendue : un sous-dossier "Saison N" par saison (les .mkv dedans), chaque .mkv préfixe par son numéro d'épisode ("01 - ...", "05 - ...").
Si --dir pointe directement sur un dossier de saison, seule celle-ci est traitée. Un dossier "Specials" vaut la saison 0.
L'identifiant TMDB peut être épinglé dans le nom du dossier de la série, sous la forme "Ma Série [tmdbid-1396]" : plus besoin de --tmdb-id aux passages suivants.

Options principales :
  --tmdb-id STR    identifiant TMDB (défaut : recherche sur le nom du dossier)
  --language STR   langue TMDB (défaut : fr-FR)
  --no-cache       ignore le cache des réponses TMDB (garde 7 jours) et le rafraîchit
  --series-name STR  force le nom de série (sinon auto depuis TMDB)
  --apply          applique réellement (défaut : simulation)
  --verify         vérifie seulement (aucune écriture)
  --skip-done      saute les fichiers déjà conformes
  --no-tag         ne modifie aucun épisode ; avec --artwork, écrit seulement folder.jpg
  --no-cover / --no-date / --no-audio-names / --no-sub-names / --no-flags / --no-stats
  --artwork        écrit folder.jpg (vignette de dossier) en anglais (série et chaque saison)
  --image-size STR taille TMDB jaquette / folder.jpg : w300 / w780 / original (défaut : w780)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # pour importer libraries
from libraries.common import cache, cli  # noqa: E402
from libraries.common.report import Report  # noqa: E402
from libraries.video import artwork, lookup, mkv, naming  # noqa: E402
from libraries.video.tmdb import Tmdb, TmdbAuthError, TmdbError                    # noqa: E402

# ----------------------------------------------------------------------------
# 1. État vise pour un épisode : tags Matroska + titre + date + jaquette
#    TargetTypeValue : 70 = COLLECTION (série), 60 = SEASON, 50 = ÉPISODE
# ----------------------------------------------------------------------------
def build_tags_xml(season, ep, series_name, max_actors=20):
    blocks = []
    if series_name:
        blocks.append(mkv.tag_block(70, [mkv.simple("TITLE", series_name)]))

    blocks.append(mkv.tag_block(60, [
        mkv.simple("PART_NUMBER", season.get("season_number", "")),
        mkv.simple("TITLE", season.get("name", "")),
        mkv.simple("TOTAL_PARTS", len(season.get("episodes", []))),
    ]))

    lines = [mkv.simple("TITLE", ep.get("name", "")), mkv.simple("PART_NUMBER", ep.get("episode_number", ""))]
    if ep.get("overview"):
        lines.append(mkv.simple("SYNOPSIS", ep["overview"]))
        lines.append(mkv.simple("SUMMARY", ep["overview"]))
    if ep.get("air_date"):
        lines.append(mkv.simple("DATE_RELEASED", ep["air_date"]))
    lines += mkv.credits_lines(ep.get("crew", []), ep.get("guest_stars", []), max_actors)
    if ep.get("vote_average"):
        lines.append(mkv.simple("COMMENT", f"TMDB {round(ep['vote_average'], 1)}/10 ({ep.get('vote_count', 0)} votes)"))
    blocks.append(mkv.tag_block(50, lines))
    return mkv.tags_document(blocks)


def episode_target(season, ep, series_name, opts):
    """Ce que le .mkv de cet épisode devrait contenir."""
    return mkv.Target(
        title=ep.get("name", ""),
        date=ep.get("air_date"),
        tags_xml=build_tags_xml(season, ep, series_name),
        poster=(ep.get("still_path") or season.get("poster_path")) if opts.cover else None,
    )


# ----------------------------------------------------------------------------
# 2. Traitement d'une saison
# ----------------------------------------------------------------------------
@dataclass
class SeasonRun:
    """Une saison traitée : son dossier, son numéro et ses données TMDB."""
    folder: Path
    number: int
    data: dict

    @property
    def episodes(self):
        return self.data.get("episodes", [])


def season_run(folder, number, data, args):
    return SeasonRun(Path(folder), number, data)


@dataclass
class Candidate:
    """Un .mkv du dossier, confronte aux données TMDB."""
    path: Path
    episode: dict | None = None
    method: str = ""
    notes: list = field(default_factory=list)   # remarques à afficher sous le fichier
    info: dict | None = None
    tags: set | None = None                     # tags déjà écrits, si on les à relus


def build_plan(mkv_dir, season, args, opts):
    """[Candidate, ...] pour les .mkv du dossier, dans l'ordre des noms.

    Les fichiers associes sont lus en parallèle : chacun coûte deux sous-processus qu'on ne fait qu'attendre.
    """
    episodes = season.get("episodes", [])
    by_num = {e.get("episode_number"): e for e in episodes}
    plan = []
    for f in sorted(Path(mkv_dir).glob("*.mkv")):
        f = f.resolve()
        ep, method = naming.match_episode(f.name, episodes, args.match_threshold, by_num)
        plan.append(Candidate(f, ep, method))

    # Les tags ne sont relus que si on doit les comparer : un processus de plus.
    besoin_tags = args.verify or args.skip_done
    lectures = mkv.inspect_all([c.path for c in plan if c.episode], args.probe, besoin_tags)
    for candidate in plan:
        lecture = lectures.get(candidate.path)
        if lecture is None:
            continue
        candidate.info, candidate.tags = lecture.info, lecture.tags
        if lecture.note:
            candidate.notes.append(lecture.note)
        dmin, runtime = lecture.probe.duration_min, candidate.episode.get("runtime")
        if dmin and runtime and abs(dmin - runtime) > 3:
            candidate.notes.append(f"durée {dmin:.0f}min vs {runtime}min attendues -> à vérifier")
    return plan


def process_season(mkv_dir, season, args, opts, tmdb):
    """Construit le plan d'une saison, l'affiche, et applique si --apply. Retourne le Report de la saison."""
    plan = build_plan(mkv_dir, season, args, opts)
    if not plan:
        print(f"  Aucun .mkv dans {mkv_dir}")
        return Report()

    report = Report(total=len(plan))
    for c in plan:
        if c.episode is None:
            print(f"  [NON ASSOCIÉ] {c.path.name}")
            continue
        report.matched += 1
        sn, en = season.get("season_number", 1), c.episode.get("episode_number", 0)
        print(f"  [S{sn:02d}E{en:02d}] {c.path.name}")
        print(f"            -> {c.episode.get('name', '')}   ({c.method})")
        for note in c.notes:
            print(f"            /!\\ {note}")
        target = episode_target(season, c.episode, args.series_name, opts)
        if args.verify:                     # mode vérification : état actuel vs vise
            diffs = [(lbl, det) for lbl, ok, det in mkv.verify(c.info, target, opts, c.tags) if not ok]
            for lbl, det in diffs:
                print(f"      [DIFF] {lbl} : actuel = {det!r}")
            if diffs:
                report.diffs += 1
            else:
                print("      [OK] déjà conforme")
            continue
        if opts.date and target.date:
            print(f"      date segment -> {target.date}")
        for line in mkv.track_preview_lines(c.info, opts):
            print(line)

    if args.apply and not args.verify:
        print("  --- écriture ---")
        for c in plan:
            if c.episode is None:
                continue
            target = episode_target(season, c.episode, args.series_name, opts)
            if args.skip_done and mkv.is_conform(c.info, target, opts, c.tags):
                print(f"  [SKIP] {c.path.name} (déjà à jour)")
                continue
            code, msg = mkv.write(c.path, c.info, target, opts, tmdb)
            if code:
                report.failures += 1
            print(f"  [{'OK' if code == 0 else 'ÉCHEC'}] {c.path.name}" + (f"  -> {msg}" if code else ""))

    print(f"  => {report.matched}/{report.total} associé(s).")
    return report


# ----------------------------------------------------------------------------
# 3. Annexes : affiches de dossier
# ----------------------------------------------------------------------------
def generate_sidecars(root_dir, series_name, show, processed, args, tmdb):
    """Écrit les affiches de dossier (folder.jpg, en anglais) si --artwork. processed = [SeasonRun, ...]."""
    if not args.artwork:
        return
    apply = args.apply and not args.verify
    print("--- annexes ---")
    for run in processed:
        poster = artwork.english_poster(lambda: tmdb.season(args.tmdb_id, run.number, artwork.ARTWORK_LANG), run.data.get("poster_path"))
        print(f"  [saison {run.number}] affiche (EN) : "
              f"{artwork.write_poster(poster, run.folder, apply, tmdb)}")
    poster = artwork.english_poster(lambda: tmdb.series(args.tmdb_id, artwork.ARTWORK_LANG), show.get("poster_path"))
    print(f"  [série] affiche (EN) : {artwork.write_poster(poster, root_dir, apply, tmdb)}")


# ----------------------------------------------------------------------------
# 4. Programme principal
# ----------------------------------------------------------------------------
def parse_args():
    ap = argparse.ArgumentParser(description="Étiquette des .mkv depuis TMDB (données en français via l'API).")
    ap.add_argument("--dir", required=True, help="Racine de la série (dossiers 'Saison N') OU un seul dossier de saison")
    # --- Source TMDB ---
    ap.add_argument("--tmdb-id", help="Identifiant TMDB de la série "
                    "(par défaut : recherche sur le nom du dossier)")
    ap.add_argument("--language", default="fr-FR", help="Langue TMDB (défaut : fr-FR)")
    ap.add_argument("--no-cache", action="store_true", help="Ignore le cache des réponses TMDB et le rafraîchit")
    ap.add_argument("--series-name", help="Force le nom de série (sinon récupère automatiquement de TMDB)")
    # --- Ce qu'on écrit ---
    ap.add_argument("--apply", action="store_true", help="Applique réellement (défaut : simulation)")
    ap.add_argument("--verify", action="store_true", help="Vérifie seulement l'état des fichiers (aucune écriture)")
    ap.add_argument("--skip-done", action="store_true", help="Saute les fichiers déjà conformes")
    ap.add_argument("--no-tag", action="store_true", help="Ne modifie aucun épisode ; avec --artwork, écrit seulement folder.jpg")
    ap.add_argument("--no-cover", action="store_true", help="N'embarque pas la jaquette")
    ap.add_argument("--no-date", action="store_true", help="Ne modifie pas la date du segment")
    ap.add_argument("--no-audio-names", action="store_true", help="Ne renomme pas les pistes audio")
    ap.add_argument("--no-sub-names", action="store_true", help="Ne renomme pas les pistes de sous-titres")
    ap.add_argument("--no-flags", action="store_true", help="Ne touche pas aux drapeaux 'par défaut'")
    ap.add_argument("--no-stats", action="store_true", help="N'ajoute pas les tags de statistiques de piste")
    # --- Générateurs annexes (option, écrivent des fichiers à côté des .mkv) ---
    ap.add_argument("--artwork", action="store_true", help="Écrit folder.jpg (vignette de dossier) en anglais")
    ap.add_argument("--image-size", default="w780", help="Taille TMDB de la jaquette embarquée / folder.jpg : w300 / w780 / original")
    ap.add_argument("--match-threshold", type=float, default=0.55, help="Score minimal pour une association par titre (0-1)")
    return ap.parse_args()


def main():
    args = parse_args()
    cli.setup_console()
    cli.check_dir(args.dir)
    args.probe = mkv.check_tools(needs_mkvtoolnix=not args.no_tag)
    opts = mkv.Options.from_args(args)
    tmdb = Tmdb(cli.resolve_tmdb_key(), args.language, user_agent="tag_mkv/1.0", cache=cache.Cache(read=not args.no_cache))

    # La bannière d'abord : la recherche de série s'affiche dessous, pas avant.
    print(f"=== {cli.mode_label(args)} ===")
    args.tmdb_id = lookup.resolve_show_id(tmdb, args.dir, args.tmdb_id)
    if args.tmdb_id is None:
        sys.exit("Série non identifiée : relance avec --tmdb-id.")

    # Détails de la série via TMDB (nom auto, + poster/synopsis pour les annexes)
    try:
        show = tmdb.series(args.tmdb_id)
    except TmdbError as e:
        sys.exit(f"Échec de l'appel TMDB (série) : {e}")
    args.series_name = args.series_name or show.get("name", "")

    print(f"    série : {args.series_name}   |   source : TMDB {args.language} (id {args.tmdb_id})\n")

    if args.no_tag and not args.artwork:
        print("Astuce : --no-tag sans --artwork ne produit rien. Ajoute --artwork.\n")

    seasons = naming.find_seasons(args.dir)
    if seasons:
        # --- Multi-saisons : --dir est la racine de la série ---
        report = Report()
        processed = []
        for sub, num in seasons:
            print(f"--- {sub.name}  (TMDB saison {num}) ---")
            try:
                data = tmdb.season(args.tmdb_id, num)
            except TmdbError as e:
                print(f"  échec TMDB saison {num} : {e} -> saison ignorée\n")
                report += Report(unresolved=1)
                continue
            if args.no_tag:
                print("  épisodes non modifiés (--no-tag)")
            else:
                report += process_season(sub, data, args, opts, tmdb)
            processed.append(season_run(sub, num, data, args))
            print()
        if not args.no_tag:
            print(f"TOTAL : {report.matched}/{report.total} fichier(s) associé(s) "
                  f"sur {len(seasons)} saison(s) détectée(s).")
        generate_sidecars(args.dir, args.series_name, show, processed, args, tmdb)
    else:
        # --- Saison unique : --dir contient directement les .mkv ---
        num = naming.season_number(Path(args.dir).name)
        num = 1 if num is None else num
        try:
            data = tmdb.season(args.tmdb_id, num)
        except TmdbError as e:
            sys.exit(f"Échec de l'appel TMDB (saison {num}) : {e}")
        report = Report()
        if args.no_tag:
            print("  épisodes non modifiés (--no-tag)")
        else:
            report = process_season(args.dir, data, args, opts, tmdb)
        generate_sidecars(args.dir, args.series_name, show, [season_run(Path(args.dir), num, data, args)], args, tmdb)

    reste = report.epilogue()
    if reste:
        print(f"\nÀ CORRIGER : {reste}.")
    return report.exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except TmdbAuthError as e:
        sys.exit(f"TMDB : {e}")
