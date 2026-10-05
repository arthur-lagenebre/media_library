#!/usr/bin/env python3
r"""
Metadata.py — Étiquette des films .mkv à partir de TMDB (données en français via l'API).

Même principe que TV_Shows/Metadata.py, mais pour les films : pas de saisons/épisodes, et l'association se fait par RECHERCHE TMDB sur le titre + l'année extraits du nom.

Écrit DIRECTEMENT dans chaque .mkv (sans re-encodage ni remux) :
  - le titre et la DATE de sortie dans les informations de segment (sortie du pays de --language : fr-FR -> sortie française, pas la sortie d'origine)
  - le synopsis, le réalisateur, les scénaristes, le casting, les genres (tags)
  - l'IDENTIFIANT TMDB (tag "TMDB", au format Matroska "movie/1234")
  - les tags de STATISTIQUES de piste (débit, durée, nb d'images)  [--no-stats]
  - l'affiche du film comme jaquette (attachment "cover.jpg")
  - le nom des pistes AUDIO       -> codec + canaux + débit (ex. "E-AC-3 5.1 640 kb/s"), suivi de AD ou Commentary quand la piste porte le drapeau malvoyant ou commentaire
  - le nom des pistes SOUS-TITRES -> uniquement les drapeaux actifs (Forced, SDH...), ou "Full"
  - les DRAPEAUX 'par défaut'     -> une seule piste audio par défaut (la FR, jamais une audiodescription ni un commentaire), aucun sous-titre
  - les drapeaux FORCED et SDH    -> posés sur un sous-titre dont le NOM les annonce ("Français force", "English SDH") alors que le drapeau manque - sinon, le renommer d'après ses seuls drapeaux effacerait l'information. Une seule piste par langue, et rien dans une langue qui declare déjà le drapeau.  [--no-flags]

Un film dont une piste est AMBIGUË n'est pas traité du tout - pas même ses autres fichiers : un nom qui dit "force" sans drapeau transposable, ou deux pistes de même langue qui porteraient le même nom (deux "Full" français, que plus rien ne distingue).
Rien n'est modifié, la raison est affichée sous [NON TRAITE], et le bilan les compte.

Deux situations que le script refuse de trancher seul, et qu'il met de côté pour poser la QUESTION À LA FIN du passage : plusieurs fiches écrivent le même titre autrement ("Les Quatre Fantastiques" et "Les 4 Fantastiques"), ou plusieurs fiches portent le MÊME titre ("Dracula" en rend trois, "Mortal Kombat" deux).
Dans les deux cas seules comptent les fiches assez votées pour être crédibles : presque tout titre à un homonyme obscur quelque part, et sans ce filtre un cinquième de la médiathèque poserait une question.
Dans le terminal : candidats numérotés, le plus vote en tête, Entrée le garde, il laisse le film de côté, q arrête les questions. Une suite ("Iron Man 2") n'est pas une variante et ne declenche rien.
Hors terminal (sortie redirigée, CI), les films restent de côté plutôt que de bloquer le passage ; --no-ask rétablit l'ancien comportement, le premier résultat sans rien demander.

Dépendances EXTERNES (dans le PATH) : mkvpropedit + mkvmerge + mkvextract (MKVToolNix), ffprobe (FFmpeg). Aucune dépendance pip. Necessite Internet (API TMDB + jaquettes).
Le code partage avec les autres scripts du dépôt vit dans libraries/ (à la racine).

Clé TMDB : ligne TMDB_KEY=... du fichier .env, à la racine du dépôt. C'est la seule source, et le même .env sert à tous les scripts : la clé n'est écrite qu'une fois.

Structure libre : --dir est parcouru RÉCURSIVEMENT, aussi profond qu'il y a des dossiers.
Seuls les .mkv sont des films - un dossier ne compte ni ne se traite jamais comme un film, il ne fait que ranger.
Un dossier qui ne contient qu'un film et rien en dessous lui prête son nom ("Inception (2010)/film.mkv") ; partout ailleurs c'est le nom du FICHIER qui parle, et le dossier IMMÉDIAT sert de renfort à la recherche : "Resident Evil/2 - Apocalypse.mkv" cherche "Apocalypse" (qui rend "Amour Apocalypse"...) puis "Resident Evil Apocalypse", et ne retient le renfort que si le titre trouvé contient à la fois le dossier et ce qu'on cherchait.
Lui seul : au-dessus vivent les dossiers de rangement d'une médiathèque ("_Marvel", "_DC"), qui ne sont pas des sagas.
Un film coupe en plusieurs fichiers (CD1/CD2) reçoit les mêmes métadonnées partout ; les bandes-annonces et making-of posés à côté sont reconnus À LEUR NOM et laissés de côté, comme les dossiers de bonus (Extras, Featurettes...).
Le poids des fichiers ne decide de rien : un dessin anime de 1 Go est un film autant qu'un remux de 28 Go.
Un préfixe d'ordre de saga "{n} - " est détecté et retire pour la recherche ("1 - Iron Man" -> recherche "Iron Man"), demi-numéros compris ("1.5 - Dark Fury") ; l'ordre est inscrit comme numéro dans la collection (tag PART_NUMBER).
À titre égal, TMDB classe par POPULARITÉ : une fiche portant EXACTEMENT le titre cherché passe donc devant ("Blade" doit rendre Blade, pas Blade II).

Un dossier de saga n'est pas une réunion de fichiers indépendants : c'est une COLLECTION TMDB, que l'API donne en entier.
Les dossiers qui contiennent plusieurs films sont donc réexaminés DE L'INTÉRIEUR : la saga est cherchée par le NOM du dossier (le seul signal qu'un film mal associe ne peut pas fausser), puis parmi celles vers lesquelles plusieurs films pointent déjà.
Les fichiers lui sont ensuite apparies un à un - le numéro d'ordre d'abord, la ressemblance du titre ensuite, et chaque film de la saga ne servant qu'une fois, les titres muets héritent de ce qui reste.
Un homonyme qui existe dans 900 000 films n'existe pas dans une saga de 26 : "Le défi" ne peut plus ramener Batman, ni "Vendetta" ramener V pour Vendetta.
La numérotation du dossier doit tenir dans la collection, faute de quoi un dossier de rangement (le MCU numéroté 35 films) se ferait passer pour une saga.  [--no-saga]
L'identifiant TMDB retenu est INSCRIT DANS LE FILM : au passage suivant, il est relu et plus rien n'est cherché - l'association survit donc au renommage, et ne peut plus se tromper deux fois de la même façon.
La relecture ne coûte un sous-processus de plus que sur les fichiers qui déclarent des tags : une médiathèque jamais étiquetée ne paie rien.
Une association suspecte (durée incohérente, fiche presque inconnue) est signalée à chaque passage. Pour la faire taire SANS épingler l'identifiant dans le nom du fichier, ajoute-le à "metadata.ok", à côté du journal : une ligne par film, l'identifiant seul ou son lien TMDB tel que le journal le donne, '#' pour un commentaire. Les doutes de ces films ne sont plus signalés ; rien d'autre ne change.
Ordre de priorité : --tmdb-id, puis l'identifiant épinglé dans le NOM, puis celui lu dans le FICHIER, puis la recherche.
Si un passage à inscrit le mauvais identifiant, corrige-le en épinglant le bon dans le nom - "Dune (2021) [tmdbid-438631]" ou "Dune {tmdb-438631}" - le passage suivant le réécrira dans le fichier.

Usage :
  python Metadata.py --dir "D:\Films"                         # simulation (n'écrit rien)
  python Metadata.py --dir "D:\Films" --apply                 # applique
  python Metadata.py --dir "D:\Films\Inception (2010)" --tmdb-id 27205 --apply   # force l'id (1 film)
  python Metadata.py --dir "D:\Films" --verify                # vérifie seulement

Options : --apply --verify --skip-done --artwork --recap --no-tag --no-cache --no-ask
          --no-saga
          --no-cover --no-date --no-audio-names --no-sub-names --no-flags --no-stats
          --tmdb-id (force, si un seul film) --language (défaut fr-FR) --image-size (w780)

À chaque passage, un JOURNAL est écrit à la racine de --dir : "metadata.log" donne le lien TMDB de chaque film trouve, et groupe en fin de fichier ceux qui n'en ont pas - non associes, ou laissés en attente d'une réponse.

--recap genere une fiche HTML de la médiathèque à la racine de --dir (ou là où --recap-out le dit, dossier ou fichier .html) : mur d'affiches groupe par saga, avec les films qui MANQUENT à chaque saga (TMDB en connaît la composition) - les films déjà sortis seulement, pas les suites annoncées.
Fichier unique, les affiches sont encodées dedans. --no-tag genere les annexes sans rien modifier dans les .mkv.
Une zone de recherche filtre les films par titre ; chaque film possédé mène à SA fiche (affiche, résumé, réalisateur, casting), un fichier par film dans le dossier Fiches, à côté de l'index (donc dans __Data__ avec --recap-out). Elle n'ajoute aucune requête TMDB : le casting est déjà dans la réponse, seules les images se téléchargent - une seule fois, la fiche précédente sert de cache. --cast-limit et --profile-size règlent le casting.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # pour importer libraries
from libraries.common import cache, cli, favicon, layout, textfile  # noqa: E402
from libraries.common.report import Report  # noqa: E402
from libraries.video import artwork, embed, filmpage, lookup, mkv, naming  # noqa: E402
from libraries.video import saga as saga_module  # noqa: E402
from libraries.video.tmdb import (Tmdb, TmdbAuthError, TmdbError,   # noqa: E402
                        movie_url, release_region)


# ----------------------------------------------------------------------------
# 1. État vise pour un film (TargetTypeValue 50 = film, 70 = collection/saga)
# ----------------------------------------------------------------------------
def build_movie_tags_xml(movie, max_actors=20):
    credits = movie.get("credits", {})
    blocks = []

    collection = (movie.get("belongs_to_collection") or {}).get("name")
    if collection:
        lines = [mkv.simple("TITLE", collection)]
        if movie.get("_order"):                       # ordre de la saga (préfixe "{n} - ")
            lines.append(mkv.simple("PART_NUMBER", movie["_order"]))
        blocks.append(mkv.tag_block(70, lines))

    lines = [mkv.simple("TITLE", movie.get("title", ""))]
    if movie.get("id"):
        # L'association elle-même, inscrite dans le film : au passage suivant, plus rien n'est cherché, donc plus rien ne peut se tromper.
        lines.append(mkv.simple(mkv.TMDB_TAG, mkv.tmdb_value(movie["id"])))
    if movie.get("overview"):
        lines.append(mkv.simple("SYNOPSIS", movie["overview"]))
        lines.append(mkv.simple("SUMMARY", movie["overview"]))
    if movie.get("release_date"):
        lines.append(mkv.simple("DATE_RELEASED", movie["release_date"]))
    lines += mkv.credits_lines(credits.get("crew", []), credits.get("cast", []), max_actors)
    genres = ", ".join(g.get("name", "") for g in movie.get("genres", []))
    if genres:
        lines.append(mkv.simple("GENRE", genres))
    blocks.append(mkv.tag_block(50, lines))
    return mkv.tags_document(blocks)


def movie_target(movie, opts):
    """Ce que le .mkv de ce film devrait contenir."""
    return mkv.Target(title=movie.get("title", ""), date=movie.get("release_date"), tags_xml=build_movie_tags_xml(movie), poster=movie.get("poster_path") if opts.cover else None,)


# ----------------------------------------------------------------------------
# 2. Traitement d'un film
# ----------------------------------------------------------------------------
def process_file(path, lecture, movie, args, opts, tmdb):
    """Traite UN fichier du film. Retourne (non_conforme, echec_ecriture), 0 ou 1 chacun."""
    info, tags = lecture.info, lecture.tags
    if lecture.note:
        print(f"      {lecture.note}")
    target = movie_target(movie, opts)

    if args.verify:
        diffs = [(lbl, det) for lbl, ok, det in mkv.verify(info, target, opts, tags) if not ok]
        for lbl, det in diffs:
            print(f"      [DIFF] {lbl} : actuel = {det!r}")
        if not diffs:
            print("      [OK] deja conforme")
        return (1 if diffs else 0), 0

    if opts.date and target.date:
        origine = (f" (sortie {movie['_date_region']})" if movie.get("_date_region") else " (sortie d'origine)")
        print(f"      date -> {target.date}{origine}")
    for line in mkv.track_preview_lines(info, opts):
        print(line)

    if not args.apply:
        return 0, 0
    if args.skip_done and mkv.is_conform(info, target, opts, tags):
        print("      [SKIP] deja a jour")
        return 0, 0
    code, msg = mkv.write(path, info, target, opts, tmdb)
    print(f"      [{'OK' if code == 0 else 'ECHEC'}]" + (f" {msg}" if code else ""))
    return 0, (1 if code else 0)


def report_conflicts(entry, lectures, opts):
    """Affiche ce qui bloque l'étiquetage du film, et dit si ça bloque.

    Un film dont une piste est ambiguë n'est pas traité DU TOUT - pas même ses autres fichiers : à moitié etiquete, il aurait l'air fait, et le souci passerait à la trappe au passage suivant.
    """
    soucis = [(path, mkv.track_conflicts(lectures[path].info, opts)) for path in entry.files]
    if not any(raisons for _, raisons in soucis):
        return False
    print("      [NON TRAITE] rien n'a ete modifie ; ces pistes demandent une decision :")
    for path, raisons in soucis:
        for raison in raisons:
            prefixe = f"{path.name} : " if len(entry.files) > 1 else ""
            print(f"         - {prefixe}{raison}")
    return True


def process_movie(entry, movie, lectures, args, opts, tmdb):
    """Traite tous les fichiers d'un film et retourne son Report.

    Un film peut occuper plusieurs fichiers : chacun reçoit les mêmes métadonnées, et son nom est rappelé pour qu'on sache lequel parle.
    """
    if report_conflicts(entry, lectures, opts):
        return Report(matched=1, total=1, skipped=1)

    report = Report(matched=1, total=1)
    for path in entry.files:
        if len(entry.files) > 1:
            print(f"      · {path.name}")
        diffs, failures = process_file(path, lectures[path], movie, args, opts, tmdb)
        report.diffs += diffs
        report.failures += failures

    return report


def write_artwork(entry, movie, args, tmdb):
    """Écrit folder.jpg à côté du film. Appele même sous --no-tag, qui ne doit empêcher que la modification des .mkv, pas la génération des annexes."""
    poster = artwork.english_poster(lambda: tmdb.movie(movie["id"], artwork.ARTWORK_LANG), movie.get("poster_path"))
    apply = args.apply and not args.verify
    print(f"      affiche (EN) : {artwork.write_poster(poster, entry.folder, apply, tmdb)}")


@dataclass
class Library:
    """Ce qui s'accumule au fil du passage, au-delà du Report."""
    resolved: list          # fiches TMDB retenues, pour la fiche récap
    seen: dict              # {id TMDB: film déjà vu} - détection des doublons
    lectures: dict          # {chemin: Reading}
    journal: list = field(default_factory=list)   # (nom affiche, id TMDB, statut)
    doubts: list = field(default_factory=list)    # (nom affiche, fiche TMDB, [raisons]) - associations suspectes
    approved: set = field(default_factory=set)    # identifiants TMDB validés dans metadata.ok

    def note(self, display, movie_id=None, statut=""):
        """Consigne le sort d'un film pour le journal de fin de passage."""
        self.journal.append((display, movie_id, statut))


def log_path(root_dir, args):
    """Où écrire le journal : à côté de la fiche quand --recap-out la range ailleurs (les annexes vivent ensemble), sinon à la racine de --dir."""
    if getattr(args, "recap", False) and getattr(args, "recap_out", None):
        return recap_path(root_dir, args.recap_out).parent / "metadata.log"
    return Path(root_dir) / "metadata.log"


APPROVED_NAME = "metadata.ok"
MOVIE_ID_RE = re.compile(r"/movie/(\d+)")
LEADING_ID_RE = re.compile(r"\s*(\d+)\b")


def approved_path(root_dir, args):
    """Le fichier des films validés, rangé avec le journal."""
    return log_path(root_dir, args).with_name(APPROVED_NAME)


def read_approved(path):
    """Identifiants TMDB des films dont tu as vérifié l'association : {id, ...}.

    Une ligne par film, '#' commence un commentaire. L'identifiant s'écrit seul ("1437733") ou en lien TMDB, tel que le journal le donne : on peut y recopier la ligne d'un film, ou son seul lien. Un fichier absent ou illisible ne valide rien.

    C'est ce qui permet de faire taire un doute sans épingler l'identifiant dans le NOM du fichier : le nom reste propre, et le fichier survit aux renommages.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return set()
    approved = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0]
        found = MOVIE_ID_RE.search(line) or LEADING_ID_RE.match(line)
        if found:
            approved.add(int(found.group(1)))
    return approved


def write_log(root_dir, library, args, report):
    """Écrit le journal du passage : un lien TMDB par film, les vides à la fin.

    Le terminal defile et se perd ; ce fichier reste. Les films sans lien sont groupés en fin de fichier : ce sont eux qui demandent quelque chose. Comme la fiche, il n'est pas réécrit quand seul son horodatage changerait.
    """
    out = log_path(root_dir, args)
    trouves = [(nom, mid, st) for nom, mid, st in library.journal if mid]
    vides = [(nom, st) for nom, mid, st in library.journal if not mid]
    largeur = min(max((len(nom) for nom, _, _ in library.journal), default=0), 70)

    lignes = [f"# Metadata.py - {Path(root_dir).resolve()}", f"# {datetime.now():%Y-%m-%d %H:%M} - {cli.mode_label(args)}", f"# {report.matched}/{report.total} film(s) associe(s)", ""]
    for nom, movie_id, statut in trouves:
        lignes.append(f"{nom:<{largeur}}  {movie_url(movie_id)}" + (f"  {statut}" if statut else ""))
    if vides:
        lignes += ["", f"# --- sans lien ({len(vides)}) ---"]
        lignes += [f"{nom:<{largeur}}  {statut}" for nom, statut in vides]

    text = "\n".join(lignes) + "\n"
    if textfile.same(out, text, skip_lines=2):
        print(f"[log] {out.name} inchange")
        return
    try:
        textfile.write(out, text)
    except OSError as e:
        print(f"[log] {out.name} non ecrit : {e}")
        return
    print(f"[log] {out.name} ecrit ({len(trouves)} lien(s), {len(vides)} sans lien)")


# Une durée qui sort de cette fourchette ne s'explique ni par une version longue (Kingdom of Heaven : 144 -> 189 min, x1.31) ni par l'accélération PAL (-4 %) : c'est un autre film. Les cinq erreurs relevées sur une vraie médiathèque en sortaient toutes - Microcosmos pris pour un court métrage de 3 min, Catwoman pour un DC Showcase de 15 min, Destruction finale (95 min) pour un film coréen de 128.
LENGTH_MIN, LENGTH_MAX = 0.75, 1.35
LENGTH_GAP = 10            # en dessous, un écart de minutes ne dit rien (courts métrages, génériques)
MIN_VOTES = 10              # une fiche que presque personne n'a notée : rarement le film qu'on possède


def file_minutes(entry, lectures):
    """Durée totale du film sur le disque, toutes parties (CD1, CD2...) comprises ; None si l'une manque."""
    total = 0.0
    for path in entry.files:
        m = mkv.minutes(lectures.get(path))
        if not m:
            return None
        total += m
    return total


def identity_doubts(entry, movie, lectures):
    """Raisons de douter que `movie` soit bien le film du fichier : [texte, ...].

    Un identifiant épinglé dans le nom est une décision de l'utilisateur, et n'est pas remis en cause : une version longue qu'on a épinglée ne doit pas revenir à chaque passage.
    """
    if naming.extract_tmdb_id(entry.rawname)[0]:
        return []
    doubts = []
    length, runtime = file_minutes(entry, lectures), movie.get("runtime")
    if length and runtime and abs(length - runtime) >= LENGTH_GAP and not (LENGTH_MIN <= length / runtime <= LENGTH_MAX):
        doubts.append(f"duree {length:.0f} min, la fiche TMDB en annonce {runtime}")
    votes = movie.get("vote_count")
    if votes is not None and votes < MIN_VOTES:
        doubts.append(f"fiche TMDB presque inconnue ({votes} vote(s))")
    return doubts


def handle_movie(entry, movie, library, args, opts, tmdb):
    """Traite un film dont l'association est arrêtée. Retourne son Report."""
    jumeau = library.seen.setdefault(movie.get("id"), entry.display)
    if jumeau != entry.display:
        # Deux dossiers pour un même film : les deux sont étiquetés (une VF et une 4K le méritent), mais le récap n'en montrera qu'une vignette.
        print(f"  [DOUBLON] meme film que '{jumeau}' -> les deux seront traites")
    library.resolved.append(movie)
    # Un film validé dans metadata.ok garde ses doutes pour lui : tu les as vus.
    doubts = [] if movie.get("id") in library.approved else identity_doubts(entry, movie, library.lectures)
    if doubts:
        print(f"  /!\\ {' ; '.join(doubts)} -> verifie l'association, ou epingle l'id dans le nom")
        library.doubts.append((entry.display, movie, doubts))
    if args.no_tag:
        print("      film non modifie (--no-tag)")
        report = Report(matched=1, total=1)
    else:
        report = process_movie(entry, movie, library.lectures, args, opts, tmdb)
    if args.artwork and entry.owns_folder:
        write_artwork(entry, movie, args, tmdb)
    status = "[NON TRAITE]" if report.skipped else ("[A VERIFIER] " + " ; ".join(doubts) if doubts else "")
    library.note(entry.display, movie.get("id"), status)
    return report


def resolve_pending(attente, library, args, opts, tmdb):
    """Pose les questions mises de côté, puis traite les films confirmés.

    Les questions attendent la fin pour ne pas hacher le passage : le script déroule d'abord tout ce qu'il sait faire seul, et n'arbitre qu'ensuite.
    """
    print(f"=== {len(attente)} association(s) a confirmer ===")
    if not cli.can_ask():
        print("  Terminal non interactif : ces films sont laisses de cote.")
        print("  Relance dans un terminal, epingle l'id dans le nom, ou passe")
        print("  --no-ask pour accepter le premier resultat sans demander.\n")
        for entry, doute in attente:
            print(f"  [A CONFIRMER] {entry.display} -> {lookup.describe(doute.candidates[0])}")
            library.note(entry.display, None, "[A CONFIRMER]")
        return Report(matched=len(attente), total=len(attente), pending=len(attente))

    print("  Entree = garder le 1er, i = laisser de cote, q = arreter les questions.\n")
    report, arrete = Report(), False
    for numero, (entry, doute) in enumerate(attente, 1):
        print(f"[{numero}/{len(attente)}] {entry.display}   (recherche : '{doute.query}')")
        for note in doute.notes:
            print(f"      /!\\ {note}")
        for rang, candidat in enumerate(doute.candidates, 1):
            print(f"      {rang}) {lookup.describe(candidat)}" + ("   (defaut)" if rang == 1 else ""))
        choix = cli.ASK_SKIP if arrete else cli.ask_choice(len(doute.candidates))
        if choix == cli.ASK_STOP:
            arrete, choix = True, cli.ASK_SKIP
        if choix == cli.ASK_SKIP:
            print("      [NON TRAITE] association non confirmee\n")
            report += Report(matched=1, total=1, pending=1)
            library.note(entry.display, None, "[A CONFIRMER]")
            continue
        candidat = doute.candidates[choix]
        movie = movie_details(candidat["id"], doute.order, args, tmdb)
        if movie is None:
            report += Report(total=1)
            continue
        print(f"      -> {lookup.describe(candidat)}")
        print(f"      pour ne plus avoir la question : ajoute "
              f"' [tmdbid-{candidat['id']}]' au nom")
        report += handle_movie(entry, movie, library, args, opts, tmdb)
        print()
    return report


def movie_details(movie_id, order, args, tmdb):
    """Fiche complète d'un film : crédits, genres, et date de sortie NATIONALE."""
    try:
        movie = tmdb.movie(movie_id)
    except TmdbError as e:
        print(f"  echec details TMDB : {e}\n")
        return None
    movie["_order"] = order

    # Sortie nationale (fr-FR -> FR) : sans ça, TMDB donne la sortie d'origine.
    region = release_region(args.language)
    local = (tmdb.local_release_date(movie_id, region) if region and not args.no_date else None)
    if local:
        movie["release_date"], movie["_date_region"] = local, region
    return movie


def folder_groups(movies):
    """{dossier: [films]} pour les dossiers qui en contiennent plusieurs."""
    groupes = {}
    for entry in movies:
        groupes.setdefault(entry.folder, []).append(entry)
    return {d: g for d, g in groupes.items() if len(g) > 1}


def saga_candidates(dossier, vues, tmdb):
    """[[films d'une collection], ...] à essayer pour ce dossier, la plus sure d'abord.

    Le NOM du dossier passe devant : c'est le seul signal qu'un film mal associé ne peut pas fausser, et un dossier dont tous les films sont faux ne désigne aucune saga - c'est pourtant celui qui a le plus besoin d'aide. Vient ensuite la saga vers laquelle plusieurs films pointent déjà, utile quand le dossier ne porte pas le nom de sa saga.

    Plusieurs pistes plutôt qu'une seule : un dossier chevauche parfois deux collections (les Tortues Ninja de 1990 et le reboot de 2014).

    Le contrôle de numérotation, lui, se fait au moment de l'appariement : il dépend des fichiers qui restent à placer.
    """
    pistes = []
    try:
        trouvees = tmdb.search_collection(dossier.name)
    except TmdbError:
        trouvees = []
    # La saga trouvée par le nom doit vraiment ressembler au dossier : une médiathèque nommée "films" ramène "MIRRORLIAR FILMS", et "_Marvel" ramène "Marvel Rising Collection" - ni l'une ni l'autre n'est une saga.
    for c in trouvees[:1]:
        if saga_module.close_to(dossier.name, c.get("name") or "") >= saga_module.MIN_SCORE:
            pistes.append(c["id"])
    commune = saga_module.most_common_collection(vues)
    if commune is not None and commune not in pistes:
        pistes.append(commune)

    sorties = []
    for ident in pistes:
        try:
            parts = tmdb.collection(ident).get("parts", [])
        except TmdbError:
            continue
        if parts:
            sorties.append(parts)
    return sorties


def saga_corrections(movies, lectures, args, tmdb):
    """{nom affiche: fiche TMDB} pour les films qu'une collection replace mieux.

    Passe silencieuse, avant tout le reste. Chaque film d'un dossier multiple est résolu comme d'habitude, puis le dossier est réexamine DE L'INTÉRIEUR : les fichiers sont appariés aux films de la saga, un à un. Un homonyme qui existe dans 900 000 films n'existe pas dans une saga de 26 - "Le défi" ne peut plus ramener Batman, ni "Vendetta" ramener V pour Vendetta.

    Les recherches sont rejouées ensuite par la boucle principale, mais le cache des réponses TMDB les rend gratuites.
    """
    corrections = {}
    for dossier, entrees in folder_groups(movies).items():
        fixes, fiches, vues, fichiers = set(), {}, [], []
        for entry in entrees:
            with contextlib.redirect_stdout(io.StringIO()):
                movie, doute = resolve_movie(entry.rawname, args, tmdb, single=False, contexts=entry.contexts, tag_id=tag_movie_id(entry, lectures))
                if movie is None and doute is not None:
                    movie = movie_details(doute.candidates[0]["id"], None, args, tmdb)
            if movie is None:
                continue
            fiches[entry.display] = movie
            vues.append((movie.get("belongs_to_collection") or {}).get("id"))
            # Un identifiant épinglé ou déjà inscrit dans le film ne se discute pas : il retient sa fiche, et personne d'autre ne peut l'avoir.
            if naming.extract_tmdb_id(entry.rawname)[0] or tag_movie_id(entry, lectures):
                fixes.add(movie.get("id"))
                continue
            _, nom = naming.extract_tmdb_id(entry.rawname)
            titre, _, ordre = naming.parse_title_year(nom)
            fichiers.append((entry.display, titre, ordre))

        if not fichiers:
            continue
        restants = list(fichiers)
        for parts in saga_candidates(dossier, vues, tmdb):
            if not restants or not saga_module.fits(restants, parts):
                continue
            libres = [p for p in parts if p.get("id") not in fixes]
            places = saga_module.assign(restants, libres)
            for cle, part in places:
                fixes.add(part.get("id"))
                if part.get("id") != fiches[cle].get("id"):
                    corrections[cle] = part
            posees = {cle for cle, _ in places}
            restants = [f for f in restants if f[0] not in posees]
    return corrections


def tag_movie_id(entry, lectures):
    """Identifiant TMDB déjà inscrit dans les fichiers du film, ou None."""
    for path in entry.files:
        lecture = lectures.get(path)
        ident = mkv.tmdb_id(lecture.tags) if lecture else None
        if ident:
            return ident
    return None


def resolve_movie(rawname, args, tmdb, single, contexts=(), tag_id=None, saga=None):
    """(film, doute) pour un nom de dossier/fichier. (None, None) si rien ne colle.

    `contexts` liste les dossiers au-dessus du film, du plus proche au plus lointain : ils servent de renfort à la recherche, pas de remplaçants.

    Un `doute` non nul veut dire que plusieurs fiches écrivent le même titre : le film n'est alors PAS charge, et la question est posée en fin de passage.
    """
    pinned, rawname = naming.extract_tmdb_id(rawname)
    title, year, order = naming.parse_title_year(rawname)
    if args.tmdb_id and single:
        return movie_details(args.tmdb_id, order, args, tmdb), None
    if pinned:
        movie = movie_details(pinned, order, args, tmdb)
        if movie:
            print(f"  id epingle dans le nom : {lookup.describe(movie)}")
        return movie, None
    if tag_id:
        # Le nom passe avant : c'est le seul moyen de corriger un identifiant qu'un passage précédent aurait inscrit de travers.
        movie = movie_details(tag_id, order, args, tmdb)
        if movie:
            print(f"  id lu dans le fichier : {lookup.describe(movie)}")
        return movie, None
    if saga is not None:
        movie = movie_details(saga["id"], order, args, tmdb)
        if movie:
            print(f"  place par sa saga : {lookup.describe(saga)}")
        return movie, None

    try:
        results, query = lookup.search_with_context(tmdb, title, year, contexts)
    except TmdbError as e:
        print(f"  echec recherche TMDB : {e}\n")
        return None, None
    if not results:
        print(f"  [NON ASSOCIE] recherche '{title}'" + (f" ({year})" if year else "") + " -> aucun resultat\n")
        return None, None
    best, notes = lookup.pick_result(results, query)
    print(f"  recherche : '{query}'" + (f" ({year})" if year else "") + (f" [ordre {order}]" if order else "") + f" -> {lookup.describe(best)}")
    for note in notes:
        print(f"  /!\\ {note}")

    # Deux façons de ne pas pouvoir trancher : le même titre écrit autrement ("Les 4 Fantastiques"), ou le même titre porte par deux films (un remake).
    doutes = lookup.rival_versions(query, results) + lookup.twin_versions(results, best)
    if doutes and not args.no_ask:
        return None, lookup.Doubt(query=query, notes=notes, order=order, candidates=lookup.choice_list(results, best, doutes))
    return movie_details(best["id"], order, args, tmdb), None


# ----------------------------------------------------------------------------
# 3. Fiche récap de la médiathèque
# ----------------------------------------------------------------------------
@dataclass
class Card:
    """Une vignette de la fiche : un film possède, ou un film qui manque à une saga."""
    title: str
    date: str = ""
    poster: str | None = None
    owned: bool = True
    runtime: int | None = None
    movie_id: int | None = None     # identifiant TMDB, de quoi retrouver sa fiche (voir filmpage)

    @property
    def year(self):
        return (self.date or "")[:4]


def _card(movie, owned=True):
    return Card(title=movie.get("title", ""), date=movie.get("release_date") or "", poster=movie.get("poster_path"), owned=owned, runtime=movie.get("runtime"), movie_id=movie.get("id"))


def fetch_collections(movies, tmdb):
    """{id de saga: composition TMDB} pour les sagas des films trouvés."""
    sagas = {}
    for movie in movies:
        info = movie.get("belongs_to_collection") or {}
        ident = info.get("id")
        if ident is None or ident in sagas:
            continue
        try:
            sagas[ident] = tmdb.collection(ident)
        except TmdbError as e:
            print(f"  [recap] saga '{info.get('name')}' ignoree : {e}")
    return sagas


def released(part, today):
    """Le film est-il déjà sorti ? Sans date, il n'est qu'annoncé."""
    return bool(part.get("release_date")) and part["release_date"] <= today


# Ce que TMDB ajoute au nom d'une saga : "Iron Man - Saga", "Saga Iron Man", "Iron Man Collection". Le titre de section n'a besoin que du nom ; "Saga" y est redit par la section elle-même, et par "Hors saga" en dessous.
SAGA_SUFFIX_RE = re.compile(r"\s*(?:[-–—:]\s*(?:saga|collection)|collection)\s*$", re.IGNORECASE)
SAGA_PREFIX_RE = re.compile(r"^(?:saga|collection)\s+(?:[-–—:]\s*)?", re.IGNORECASE)


# Un nom qui commencerait ou finirait sur l'un d'eux une fois "collection" retiré ("Star Wars : la collection" -> "Star Wars : la", "Collection of Hope" -> "of Hope") n'était pas habillé : le mot faisait partie de sa phrase.
DANGLING = {"la", "le", "les", "l'", "de", "du", "des", "d'", "un", "une", "the", "a", "an", "of"}


def saga_title(name):
    """'Iron Man - Saga' -> 'Iron Man'. Un nom qui n'est que "Saga" ou "Collection" reste tel quel.

    Seul un mot séparé par un tiret ou deux-points, ou prêt à lancer le nom, est retiré : "The Twilight Saga" est un nom entier, pas un habillage.
    """
    name = (name or "").strip()
    short = SAGA_PREFIX_RE.sub("", SAGA_SUFFIX_RE.sub("", name)).strip()
    if not short or {short.split()[0].casefold(), short.split()[-1].casefold()} & DANGLING:
        return name
    return short


def library_sections(movies, sagas, today=None):
    """[(titre de section, [Card, ...]), ...] : une section par saga, puis le reste.

    Une saga apparait avec TOUS ses films sortis - ceux qu'on possède et les autres - dans l'ordre de sortie : c'est ce qui rend visible ce qui manque à la collection. Un film pas encore sorti, ou seulement annoncé sans date, ne manque à personne : il n'apparaît pas, sauf si on l'a déjà.
    """
    today = today or date.today().isoformat()
    owned = {m.get("id"): m for m in movies}
    sections, classes = [], set()
    # Classées sur le nom court : "Saga Alien" ne doit pas finir à S.
    for ident, saga in sorted(sagas.items(), key=lambda kv: saga_title(kv[1].get("name")).casefold()):
        cards = []
        for part in sorted(saga.get("parts", []), key=lambda p: p.get("release_date") or "9999"):
            mine = owned.get(part.get("id"))
            if not mine and not released(part, today):
                continue
            cards.append(_card(mine, True) if mine else _card(part, False))
            if mine:
                classes.add(part.get("id"))
        if cards:
            sections.append((saga_title(saga.get("name")) or "Saga", cards))
    seuls = [m for m in movies if m.get("id") not in classes]
    if seuls:
        sections.append(("Hors saga", [_card(m) for m in sorted(seuls, key=lambda m: m.get("title", ""))]))
    return sections


def collect_posters(sections, size):
    """{clé: chemin TMDB} pour toutes les affiches de la fiche."""
    needed = {}
    for _, cards in sections:
        for card in cards:
            key = embed.image_key(card.poster, size)
            if key:
                needed[key] = card.poster
    return needed


def build_recap_html(library_name, sections, posters, size, pages=()):
    """Rend la fiche HTML (pur rendu : ni réseau ni disque).

    Les films manquants d'une saga sont grises et étiquetés, comme les épisodes absents dans la fiche d'une série.

    `pages` = identifiants des films dont la fiche existe (voir filmpage) : leur vignette mène à elle. Un film sans fiche - ou manquant, que TMDB décrit mais qu'on ne possède pas - reste une vignette inerte plutôt qu'un lien cassé.

    L'en-tête (titre, recherche, bouton de largeur) reste fixe en haut de page. La recherche filtre les vignettes sur leur titre, sans accents ni casse, et masque les sagas qui n'ont plus rien à montrer."""
    def esc(s):
        # L'apostrophe aussi : les attributs sont entre apostrophes, et un titre qui dit "l'Oeil" fermerait l'attribut en plein milieu.
        return escape(str(s or ""), {"'": "&#39;"})

    blocs = []
    total = manquants = 0
    for titre, cards in sections:
        possedes = sum(1 for c in cards if c.owned)
        total += possedes
        manquants += len(cards) - possedes
        compteur = (f"<span class='cnt'>{possedes}/{len(cards)}</span>" if len(cards) != possedes else "")
        vignettes = []
        for card in cards:
            key = embed.image_key(card.poster, size)
            uri = posters.get(key) if key else None
            img = embed.tag(key, uri) if uri else "<div class='noimg'></div>"
            duree = f" · {card.runtime} min" if card.runtime else ""
            manque = "<div class='miss'>manquant</div>" if not card.owned else ""
            lien = (f" href='{esc(filmpage.href(card.movie_id))}'" if card.owned and card.movie_id in pages else "")
            balise = "a" if lien else "div"
            # L'ancre : le retour depuis la fiche du film ramène à sa vignette.
            ancre = f" id='{filmpage.anchor(card.movie_id)}'" if lien else ""
            # L'index A-Z ne vise que ce qui est rangé par ordre alphabétique : les films seuls, pas ceux d'une saga (classés par date de sortie).
            lettre = f" data-i='{layout.initial(card.title)}'" if titre == "Hors saga" else ""
            vignettes.append(
                f"<{balise} class='film{'' if card.owned else ' absent'}'{ancre}{lien}{lettre}>"
                f"<div class='aff'>{img}{manque}</div>"
                f"<div class='t'>{esc(card.title)}</div>"
                f"<div class='y'>{esc(card.year)}{duree}</div>"
                f"</{balise}>")
        # Une saga se range sous la première lettre de son nom ; "Hors saga" n'est pas un nom, ses films le sont.
        lettre = f" data-i='{layout.initial(titre)}'" if titre != "Hors saga" else ""
        blocs.append(f"<section><h2{lettre}>{esc(titre)}{compteur}</h2>"
                     f"<div class='grid'>{''.join(vignettes)}</div></section>")

    sagas = sum(1 for titre, _ in sections if titre != "Hors saga")
    resume = f"{total} film(s)" + (f" · {sagas} saga(s)" if sagas else "")
    if manquants:
        resume += f" · {manquants} manquant(s) dans les sagas"

    return (
        "<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'>"
        + favicon.films_link()
        + layout.BOOT +
        f"<meta name='poster-size' content='{esc(size)}'>"
        f"<title>{esc(library_name)}</title>"
        "<style>"
        "body{font:16px/1.5 system-ui,sans-serif;margin:0;background:#14151a;color:#e8e8ea}"
        ".wrap{max-width:1180px;margin:0 auto;padding:32px}"
        "h1{margin:0 0 4px}.sub{color:#9aa0aa}"
        + layout.CSS +
        ".none{color:#9aa0aa;margin-top:30px}"
        "[hidden]{display:none!important}"
        "h2{font-size:17px;margin:30px 0 14px;padding-bottom:8px;"
        "border-bottom:1px solid #21232b}"
        ".cnt{margin-left:9px;font-size:13px;font-weight:400;color:#9aa0aa;"
        "font-variant-numeric:tabular-nums}"
        # Sept par ligne, pas "autant que la largeur en tient" : c'est ce qu'on regarde, et à 1180 px l'ancien calcul en donnait six. Sous 900 px sept affiches deviennent des timbres-poste : retour au remplissage automatique. En pleine largeur, le remplissage automatique seul décide.
        ".grid{display:grid;gap:18px;grid-template-columns:repeat(7,1fr)}"
        "@media(max-width:900px){.grid{grid-template-columns:repeat(auto-fill,minmax(120px,1fr))}}"
        ".wide .grid{grid-template-columns:repeat(auto-fill,minmax(148px,1fr))}"
        ".film{display:block;color:inherit;text-decoration:none}"
        ".film .aff{position:relative;aspect-ratio:2/3;border-radius:8px;overflow:hidden;"
        "background:#21232b;transition:transform .15s,box-shadow .15s}"
        "a.film:hover .aff,a.film:focus-visible .aff{transform:translateY(-3px);"
        "box-shadow:0 0 0 2px #7cc4ff}"
        "a.film:hover .t{color:#7cc4ff}"
        ".film img,.film .noimg{width:100%;height:100%;object-fit:cover;display:block}"
        ".film .t{margin-top:8px;font-size:14px;font-weight:600;line-height:1.3}"
        ".film .y{color:#9aa0aa;font-size:13px}"
        ".film.absent{opacity:.42}"
        ".miss{position:absolute;left:6px;bottom:6px;padding:2px 8px;border-radius:999px;"
        "font-size:11px;text-transform:uppercase;letter-spacing:.04em;"
        "background:#3a2a2e;color:#ff9aa6}"
        "</style></head><body>"
        + layout.header(
            f"<h1>{esc(library_name)}</h1>"
            f"<div class='sub'>{esc(resume)}</div>"
            "<div class='bar'>"
            "<input class='filter' type='search' placeholder='Rechercher un film…' aria-label='Rechercher un film'>"
            + layout.mode_button() + "</div>"
            + layout.index_nav()) +
        f"{''.join(blocs)}"
        "<p class='none' hidden>Aucun film ne correspond.</p>"
        "<script>"
        "var f=document.querySelector('.filter');"
        "function n(s){return s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase()}"
        "f.oninput=function(){var q=n(f.value.trim()),any=false;"
        "document.querySelectorAll('section').forEach(function(s){var seen=0;"
        "s.querySelectorAll('.film').forEach(function(c){"
        "var ok=!q||n(c.querySelector('.t').textContent).indexOf(q)>=0;c.hidden=!ok;if(ok)seen++});"
        "s.hidden=!seen;if(seen)any=true});"
        "document.querySelector('.none').hidden=any||!q};"
        # Le choix de présentation est gardé dans le navigateur. localStorage peut être refusé (page ouverte hors serveur, navigation privée) : la page marche alors sans, en 7 par ligne.
        + layout.mode_script() + layout.index_script() +
        "</script></div></body></html>"
    )


RECAP_NAME = "index.html"       # le nom qu'un navigateur ou un serveur ouvre de lui-même dans un dossier
LEGACY_NAME = "recap.html"      # l'ancien nom, repris au premier passage
DEFAULT_TITLE = "Films"


def recap_path(root_dir, recap_out=None):
    """Où écrire la fiche : à la racine de --dir, sinon là où --recap-out le dit (un dossier, ou le chemin du fichier)."""
    if not recap_out:
        return Path(root_dir) / RECAP_NAME
    out = Path(recap_out)
    return out if out.suffix.lower() in (".html", ".htm") else out / RECAP_NAME


def recap_title(args, previous):
    """--title, sinon le titre de la fiche précédente, sinon "Films".

    Pas le nom du dossier : à la racine d'un partage réseau, il n'y en a pas, la page n'avait aucun titre et l'onglet affichait le nom du fichier.
    """
    return getattr(args, "title", None) or textfile.title_of(previous) or DEFAULT_TITLE


def write_film_pages(out, library_name, movies, args, tmdb):
    """Écrit la fiche de chaque film (voir filmpage) à côté de l'index `out`. Retourne les identifiants des films qui en ont une.

    Une fiche déjà à jour n'est pas réécrite, et ses images sont reprises d'elle : chaque nuit, seul un film nouveau coûte des téléchargements. Une fiche qu'on n'a pas pu écrire n'est pas rendue, pour que l'index ne mène pas à rien. Les fiches de films sortis de la médiathèque restent sur le disque : plus rien n'y mène, et les effacer n'est pas à ce script de décider.
    """
    folder = out.parent / filmpage.DIR
    try:
        folder.mkdir(exist_ok=True)
    except OSError as e:
        print(f"  [fiches] dossier {folder} non cree : {e} -> pas de fiche par film")
        return set()
    limit = getattr(args, "cast_limit", filmpage.CAST_LIMIT)
    profile_size = getattr(args, "profile_size", filmpage.PROFILE_SIZE)
    back = f"../{out.name}"
    # Deux dossiers pour un même film n'ont qu'une fiche : elle porte l'identifiant, pas le dossier.
    unique = {m["id"]: m for m in movies if m.get("id")}
    pages, written = set(), 0
    for movie_id, movie in unique.items():
        page = folder / filmpage.name(movie_id)
        known = embed.read_embedded(page)
        images = {**embed.fetch(filmpage.poster_images(movie), known, filmpage.POSTER_SIZE, tmdb, label="affiche", quiet=True),
                  **embed.fetch(filmpage.profile_images(movie, limit, profile_size), known, profile_size, tmdb, label="portrait", quiet=True)}
        html = filmpage.build_html(movie, images, back, library_name, limit, profile_size)
        try:
            if not textfile.same(page, html):
                textfile.write(page, html)
                written += 1
        except OSError as e:
            print(f"  [fiches] {page.name} non ecrite : {e}")
            continue
        pages.add(movie_id)
    print(f"  [fiches] {len(pages)} fiche(s) dans {folder.name}/ ({written} ecrite(s), {len(pages) - written} inchangee(s))")
    return pages


def write_recap(root_dir, movies, args, tmdb):
    """Écrit la fiche (index.html à la racine de --dir, ou --recap-out) et celle de chaque film. Ne télécharge ni n'écrit rien en simulation.

    La fiche précédente, au même endroit, sert de cache d'affiches ; une fiche encore nommée recap.html est renommée plutôt que doublée."""
    apply = args.apply and not args.verify
    out = recap_path(root_dir, getattr(args, "recap_out", None))
    if not out.parent.is_dir():
        print(f"  [mediatheque] dossier introuvable pour la fiche : {out.parent} -> fiche non ecrite")
        return
    print("--- annexes ---")
    previous = textfile.adopt(out.with_name(LEGACY_NAME), out, apply) if out.name == RECAP_NAME else out
    sections = library_sections(movies, fetch_collections(movies, tmdb))
    needed = collect_posters(sections, args.poster_size)
    posters = (embed.fetch(needed, embed.read_embedded(previous), args.poster_size, tmdb, label="affiche") if apply else {})
    title = recap_title(args, previous)
    pages = write_film_pages(out, title, movies, args, tmdb) if apply else set()
    html = build_recap_html(title, sections, posters, args.poster_size, pages)
    if not apply:
        print(f"  [mediatheque] ecrirait {out} et une fiche par film dans {filmpage.DIR}/")
        return
    # Lancée chaque nuit sur un NAS, la fiche ne doit ni réveiller les disques ni changer de date tant que la médiathèque ne bouge pas.
    if textfile.same(out, html):
        print(f"  [mediatheque] {out} inchange")
        return
    textfile.write(out, html)
    print(f"  [mediatheque] {out} ecrit  "
          f"({len(html) / 1_048_576:.1f} Mo, {len(posters)} affiche(s) integree(s))")


# ----------------------------------------------------------------------------
# 4. Programme principal
# ----------------------------------------------------------------------------
def parse_args():
    ap = argparse.ArgumentParser(description="Etiquette des films .mkv depuis TMDB (en francais).")
    ap.add_argument("--dir", required=True, help="Dossier de films, parcouru recursivement (dossiers de saga compris)")
    ap.add_argument("--tmdb-id", help="Force l'id TMDB (utile si --dir ne contient qu'un seul film)")
    ap.add_argument("--language", default="fr-FR", help="Langue TMDB (defaut : fr-FR)")
    ap.add_argument("--no-cache", action="store_true", help="Ignore le cache des reponses TMDB et le rafraichit")
    ap.add_argument("--no-saga", action="store_true", help="N'utilise pas les collections TMDB pour replacer les films")
    ap.add_argument("--no-ask", action="store_true", help="Ne pose aucune question : garde le 1er resultat TMDB, comme avant")
    ap.add_argument("--apply", action="store_true", help="Applique reellement (defaut : simulation)")
    ap.add_argument("--verify", action="store_true", help="Verifie seulement (aucune ecriture)")
    ap.add_argument("--skip-done", action="store_true", help="Saute les films deja conformes")
    ap.add_argument("--no-cover", action="store_true", help="N'embarque pas la jaquette")
    ap.add_argument("--no-date", action="store_true", help="Ne modifie pas la date du segment")
    ap.add_argument("--no-audio-names", action="store_true", help="Ne renomme pas les pistes audio")
    ap.add_argument("--no-sub-names", action="store_true", help="Ne renomme pas les pistes de sous-titres")
    ap.add_argument("--no-flags", action="store_true", help="Ne touche pas aux drapeaux 'par defaut'")
    ap.add_argument("--no-stats", action="store_true", help="N'ajoute pas les tags de statistiques")
    ap.add_argument("--no-tag", action="store_true", help="Ne modifie aucun film ; genere seulement folder.jpg / recap")
    ap.add_argument("--artwork", action="store_true", help="Ecrit folder.jpg (affiche EN) par film")
    ap.add_argument("--recap", action="store_true", help="Genere une fiche recap HTML de la mediatheque (sagas et manquants)")
    ap.add_argument("--poster-size", default="w185", help="Taille TMDB des affiches du recap (defaut : w185)")
    ap.add_argument("--profile-size", default=filmpage.PROFILE_SIZE, help=f"Taille TMDB des portraits du casting, dans la fiche de chaque film (defaut : {filmpage.PROFILE_SIZE})")
    ap.add_argument("--cast-limit", type=int, default=filmpage.CAST_LIMIT, help=f"Acteurs montres dans la fiche de chaque film (defaut : {filmpage.CAST_LIMIT})")
    ap.add_argument("--recap-out", help="Ou ecrire la fiche recap : un dossier ou un chemin .html (defaut : index.html a la racine de --dir)")
    ap.add_argument("--title", help="Titre de la fiche recap (defaut : celui de la fiche existante, sinon 'Films')")
    ap.add_argument("--image-size", default="w780", help="Taille TMDB : w300 / w780 / original")
    return ap.parse_args()


def main():
    args = parse_args()
    cli.setup_console()
    cli.check_dir(args.dir)
    args.probe = mkv.check_tools(needs_mkvtoolnix=not args.no_tag)
    opts = mkv.Options.from_args(args)
    tmdb = Tmdb(cli.resolve_tmdb_key(), args.language, user_agent="movies_mkv/1.0", cache=cache.Cache(read=not args.no_cache))

    print(f"=== {cli.mode_label(args)} ===   source : TMDB {args.language}\n")

    movies = naming.find_movies(args.dir)
    if not movies:
        print(f"Aucun .mkv trouve dans : {args.dir}")
        return
    if args.tmdb_id and len(movies) > 1:
        print(f"Note : --tmdb-id ne s'applique qu'a un seul film ; {len(movies)} detectes "
              "-> id ignore, recherche par nom.\n")
    if args.no_tag and not (args.artwork or args.recap):
        print("Astuce : --no-tag sans --artwork ni --recap ne produit rien. "
              "Ajoute --artwork et/ou --recap.\n")
    if args.artwork and not any(e.owns_folder for e in movies):
        print("Note : --artwork sans effet ici : aucun dossier ne contient un seul film.\n")

    # Toutes les lectures d'un coup, en parallèle : chaque fichier coûte deux à trois sous-processus qu'on ne fait qu'attendre, et rien la-dedans ne dépend de TMDB. L'affichage, lui, garde son ordre.
    lectures = {}
    fichiers = [f for entry in movies for f in entry.files]
    if not args.no_tag:
        lectures = mkv.inspect_all(fichiers, args.probe, with_tags=args.verify or args.skip_done)
    else:
        # Sans étiquetage, on ne lit des fichiers que leurs tags et leur durée - pour l'identifiant TMDB qu'un passage précédent y a inscrit, et le contrôle de l'association. Sans lui, la fiche rechercherait chaque film par son nom et "Mortal Kombat" (1995) y redeviendrait celui de 2021. Lu en Python pur : ni MKVToolNix ni ffprobe, de quoi tourner sur un NAS.
        lectures = mkv.read_light_all(fichiers)

    corrections = {} if args.no_saga else saga_corrections(movies, lectures, args, tmdb)
    if corrections:
        print(f"{len(corrections)} film(s) replace(s) par leur saga TMDB.\n")

    report, library = Report(), Library([], {}, lectures, approved=read_approved(approved_path(args.dir, args)))
    if library.approved:
        print(f"{len(library.approved)} film(s) valide(s) dans {APPROVED_NAME} : leurs doutes ne sont pas signales.\n")
    attente = []
    for entry in movies:
        print(f"--- {entry.display} ---")
        movie, doute = resolve_movie(entry.rawname, args, tmdb, single=len(movies) == 1, contexts=entry.contexts, tag_id=tag_movie_id(entry, lectures), saga=corrections.get(entry.display))
        if doute is not None:
            print("      [A CONFIRMER] plusieurs versions portent ce titre "
                  "-> question en fin de passage")
            attente.append((entry, doute))
            print()
            continue
        if movie is None:
            report += Report(total=1)
            library.note(entry.display, None, "[NON ASSOCIE]")
            continue
        report += handle_movie(entry, movie, library, args, opts, tmdb)
        print()

    if attente:
        report += resolve_pending(attente, library, args, opts, tmdb)

    resolved = library.resolved
    print(f"TOTAL : {report.matched}/{report.total} film(s) associe(s).")
    if library.doubts:
        print(f"\nA VERIFIER : {len(library.doubts)} association(s) suspecte(s)")
        for name, movie, doubts in library.doubts:
            print(f"  {name} -> {lookup.describe(movie)} : {' ; '.join(doubts)}")
        print()
    if args.recap and resolved:
        write_recap(args.dir, resolved, args, tmdb)
    write_log(args.dir, library, args, report)
    reste = report.epilogue()
    if reste:
        print(f"\nA CORRIGER : {reste}.")
    return report.exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except TmdbAuthError as e:
        sys.exit(f"TMDB : {e}")
