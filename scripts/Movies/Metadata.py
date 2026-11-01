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
Le titre de COLLECTION inscrit dans le film ne garde pas le suffixe " - Saga" que TMDB ajoute en français : il est retiré d'office. Le " Collection" final ("Iron Man Collection") n'est retiré qu'avec ton accord, car il peut faire partie du nom ("The Criterion Collection") : la question est posée une fois par collection, dans le terminal, et la réponse est mémorisée dans "metadata.collections", à côté du journal ("nom TMDB => titre inscrit", une ligne par collection, modifiable à la main). Hors terminal, sous --no-ask ou en vérification, rien n'est demandé et le nom est gardé tel quel.
Ordre de priorité : --tmdb-id, puis l'identifiant épinglé dans le NOM, puis celui lu dans le FICHIER, puis la recherche.
Si un passage à inscrit le mauvais identifiant, corrige-le en épinglant le bon dans le nom - "Dune (2021) [tmdbid-438631]" ou "Dune {tmdb-438631}" - le passage suivant le réécrira dans le fichier.

Usage :
  python Metadata.py --dir "D:\Films"                         # simulation (n'écrit rien)
  python Metadata.py --dir "D:\Films" --apply                 # applique
  python Metadata.py --dir "D:\Films\Inception (2010)" --tmdb-id 27205 --apply   # force l'id (1 film)
  python Metadata.py --dir "D:\Films" --verify                # vérifie seulement

Options : --apply --verify --skip-done --artwork --no-tag --no-cache --no-ask
          --no-saga --log-dir
          --no-cover --no-date --no-audio-names --no-sub-names --no-flags --no-stats
          --tmdb-id (force, si un seul film) --language (défaut fr-FR) --image-size (w780)

À chaque passage, un JOURNAL est écrit à la racine de --dir (ou dans --log-dir, qui accueille alors aussi metadata.ok et metadata.collections - utile quand la médiathèque est en lecture seule) : "metadata.log" donne le lien TMDB de chaque film trouve, et groupe en fin de fichier ceux qui n'en ont pas - non associes, ou laissés en attente d'une réponse.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # pour importer libraries
from libraries.common import cache, cli, textfile  # noqa: E402
from libraries.common.report import Report  # noqa: E402
from libraries.video import artwork, lookup, mkv, naming  # noqa: E402
from libraries.video import saga as saga_module  # noqa: E402
from libraries.video.tmdb import (Tmdb, TmdbAuthError, TmdbError,   # noqa: E402
                        movie_url, release_region)


# ----------------------------------------------------------------------------
# 1. État vise pour un film (TargetTypeValue 50 = film, 70 = collection/saga)
# ----------------------------------------------------------------------------
SAGA_SUFFIX_RE = re.compile(r"\s+-\s+saga\s*$", re.IGNORECASE)
COLLECTION_SUFFIX_RE = re.compile(r"(?:\s+-)?\s+collection\s*$", re.IGNORECASE)


def collection_title(name):
    """Le nom de la collection sans le " - Saga" que TMDB ajoute en français ("Iron Man - Saga" -> "Iron Man").

    Ce suffixe est un invariant : il part toujours. Le " Collection" anglais, lui, peut faire partie du nom ("The Criterion Collection") : voir `collection_proposal`, qui ne le retire qu'avec l'accord de l'utilisateur.
    """
    name = (name or "").strip()
    return SAGA_SUFFIX_RE.sub("", name).strip() or name


def collection_proposal(name):
    """Le nom sans son " Collection" final, ou None quand il n'y a rien à proposer."""
    name = collection_title(name)
    proposal = COLLECTION_SUFFIX_RE.sub("", name).strip()
    return proposal if proposal and proposal != name else None


def build_movie_tags_xml(movie, max_actors=20):
    credits = movie.get("credits", {})
    blocks = []

    # `_collection_title` : le titre arrêté avec l'utilisateur (voir `settle_collection`) ; à défaut, seul l'invariant " - Saga" est appliqué.
    collection = movie.get("_collection_title") or collection_title((movie.get("belongs_to_collection") or {}).get("name"))
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
            print("      [OK] déjà conforme")
        return (1 if diffs else 0), 0

    if opts.date and target.date:
        origine = (f" (sortie {movie['_date_region']})" if movie.get("_date_region") else " (sortie d'origine)")
        print(f"      date -> {target.date}{origine}")
    for line in mkv.track_preview_lines(info, opts):
        print(line)

    if not args.apply:
        return 0, 0
    if args.skip_done and mkv.is_conform(info, target, opts, tags):
        print("      [SKIP] déjà à jour")
        return 0, 0
    code, msg = mkv.write(path, info, target, opts, tmdb)
    print(f"      [{'OK' if code == 0 else 'ÉCHEC'}]" + (f" {msg}" if code else ""))
    return 0, (1 if code else 0)


def report_conflicts(entry, lectures, opts):
    """Affiche ce qui bloque l'étiquetage du film, et dit si ça bloque.

    Un film dont une piste est ambiguë n'est pas traité DU TOUT - pas même ses autres fichiers : à moitié etiquete, il aurait l'air fait, et le souci passerait à la trappe au passage suivant.
    """
    soucis = [(path, mkv.track_conflicts(lectures[path].info, opts)) for path in entry.files]
    if not any(raisons for _, raisons in soucis):
        return False
    print("      [NON TRAITÉ] rien n'a été modifié ; ces pistes demandent une décision :")
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
    resolved: list          # fiches TMDB retenues
    seen: dict              # {id TMDB: film déjà vu} - détection des doublons
    lectures: dict          # {chemin: Reading}
    journal: list = field(default_factory=list)   # (nom affiche, id TMDB, statut)
    doubts: list = field(default_factory=list)    # (nom affiche, fiche TMDB, [raisons]) - associations suspectes
    approved: set = field(default_factory=set)    # identifiants TMDB validés dans metadata.ok
    titles: dict = field(default_factory=dict)    # {nom TMDB de collection: titre à écrire}, lu dans metadata.collections
    titles_file: object = None                    # où consigner une réponse (None : on ne mémorise rien)
    asking: bool = True                           # faux dès que l'entrée se ferme : inutile d'insister
    waiting: set = field(default_factory=set)     # collections laissées sans réponse, signalées une seule fois

    def note(self, display, movie_id=None, statut=""):
        """Consigne le sort d'un film pour le journal de fin de passage."""
        self.journal.append((display, movie_id, statut))


def log_path(root_dir, args):
    """Où écrire le journal : à la racine de --dir, où on le cherche, ou dans --log-dir.

    metadata.ok et metadata.collections sont rangés avec lui : ils suivent donc --log-dir.
    """
    log_dir = getattr(args, "log_dir", None)
    return (Path(log_dir) if log_dir else Path(root_dir)) / "metadata.log"


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


COLLECTIONS_NAME = "metadata.collections"
COLLECTIONS_HEADER = ("# Titres de collection arrêtés avec toi : 'nom TMDB => titre inscrit dans le film'.\n"
                      "# Une ligne par collection ; '#' en début de ligne = commentaire. Modifie le titre à ta guise,\n"
                      "# ou supprime la ligne pour que la question soit reposée.\n")


def collections_path(root_dir, args):
    """Le fichier des titres de collection, rangé avec le journal."""
    return log_path(root_dir, args).with_name(COLLECTIONS_NAME)


def read_collections(path):
    """{nom TMDB de collection: titre à inscrire} lu dans metadata.collections ; un fichier absent ou illisible ne décide rien."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    titles = {}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        name, sep, title = line.partition("=>")
        if sep and name.strip() and title.strip():
            titles[name.strip()] = title.strip()
    return titles


def remember_collection(path, name, title):
    """Consigne une réponse tout de suite : une interruption plus loin ne doit pas la perdre."""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        new = not Path(path).exists()
        with open(path, "a", encoding="utf-8", newline="") as f:
            f.write((COLLECTIONS_HEADER if new else "") + f"{name} => {title}\n")
    except OSError as e:
        print(f"      [{COLLECTIONS_NAME}] non écrit : {e}")


def settle_collection(movie, library, args):
    """Arrête le titre de collection à inscrire dans `movie` (clé `_collection_title`).

    " - Saga" est retiré d'office (voir `collection_title`). Un " Collection" final, lui, n'est retiré qu'avec l'accord de l'utilisateur : "The Criterion Collection" ne doit pas devenir "The Criterion" sans qu'on le lui ait demandé. La réponse vaut pour toute la collection, et est mémorisée dans metadata.collections.

    Sans terminal, sous --no-ask, en vérification ou sans étiquetage, rien n'est demandé et le nom est gardé tel quel.
    """
    name = ((movie.get("belongs_to_collection") or {}).get("name") or "").strip()
    proposal = collection_proposal(name)
    if not proposal:
        return
    if name in library.titles:
        movie["_collection_title"] = library.titles[name]
        return
    if args.verify or args.no_tag:
        return
    if args.no_ask or not library.asking or not cli.can_ask():
        if name not in library.waiting:
            library.waiting.add(name)
            print(f"      [COLLECTION] '{collection_title(name)}' gardé tel quel (non validé) ; "
                  f"à décider dans {COLLECTIONS_NAME}, ou relance dans un terminal")
        return
    print(f"      collection TMDB : '{collection_title(name)}' -> retirer ' Collection' pour inscrire '{proposal}' ?")
    answer = cli.ask_yes_no(True)
    if answer is None:
        library.asking = False
        return
    title = proposal if answer else collection_title(name)
    library.titles[name] = title
    movie["_collection_title"] = title
    if library.titles_file:
        remember_collection(library.titles_file, name, title)


def write_log(root_dir, library, args, report):
    """Écrit le journal du passage : un lien TMDB par film, les vides à la fin.

    Le terminal defile et se perd ; ce fichier reste. Les films sans lien sont groupés en fin de fichier : ce sont eux qui demandent quelque chose. Comme la fiche, il n'est pas réécrit quand seul son horodatage changerait.
    """
    out = log_path(root_dir, args)
    trouves = [(nom, mid, st) for nom, mid, st in library.journal if mid]
    vides = [(nom, st) for nom, mid, st in library.journal if not mid]
    largeur = min(max((len(nom) for nom, _, _ in library.journal), default=0), 70)

    lignes = [f"# Metadata.py - {Path(root_dir).resolve()}", f"# {datetime.now():%Y-%m-%d %H:%M} - {cli.mode_label(args)}", f"# {report.matched}/{report.total} film(s) associé(s)", ""]
    for nom, movie_id, statut in trouves:
        lignes.append(f"{nom:<{largeur}}  {movie_url(movie_id)}" + (f"  {statut}" if statut else ""))
    if vides:
        lignes += ["", f"# --- sans lien ({len(vides)}) ---"]
        lignes += [f"{nom:<{largeur}}  {statut}" for nom, statut in vides]

    text = "\n".join(lignes) + "\n"
    if textfile.same(out, text, skip_lines=2):
        print(f"[log] {out.name} inchangé")
        return
    try:
        if getattr(args, "log_dir", None):
            out.parent.mkdir(parents=True, exist_ok=True)
        textfile.write(out, text)
    except OSError as e:
        print(f"[log] {out.name} non écrit : {e}")
        return
    print(f"[log] {out.name} écrit ({len(trouves)} lien(s), {len(vides)} sans lien)")


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
        doubts.append(f"durée {length:.0f} min, la fiche TMDB en annonce {runtime}")
    votes = movie.get("vote_count")
    if votes is not None and votes < MIN_VOTES:
        doubts.append(f"fiche TMDB presque inconnue ({votes} vote(s))")
    return doubts


def handle_movie(entry, movie, library, args, opts, tmdb):
    """Traite un film dont l'association est arrêtée. Retourne son Report."""
    jumeau = library.seen.setdefault(movie.get("id"), entry.display)
    if jumeau != entry.display:
        # Deux dossiers pour un même film : les deux sont étiquetés (une VF et une 4K le méritent).
        print(f"  [DOUBLON] même film que '{jumeau}' -> les deux seront traités")
    library.resolved.append(movie)
    settle_collection(movie, library, args)
    # Un film validé dans metadata.ok garde ses doutes pour lui : tu les as vus.
    doubts = [] if movie.get("id") in library.approved else identity_doubts(entry, movie, library.lectures)
    if doubts:
        print(f"  /!\\ {' ; '.join(doubts)} -> vérifie l'association, ou épingle l'id dans le nom")
        library.doubts.append((entry.display, movie, doubts))
    if args.no_tag:
        print("      film non modifié (--no-tag)")
        report = Report(matched=1, total=1)
    else:
        report = process_movie(entry, movie, library.lectures, args, opts, tmdb)
    if args.artwork and entry.owns_folder:
        write_artwork(entry, movie, args, tmdb)
    status = "[NON TRAITÉ]" if report.skipped else ("[À VÉRIFIER] " + " ; ".join(doubts) if doubts else "")
    library.note(entry.display, movie.get("id"), status)
    return report


def resolve_pending(attente, library, args, opts, tmdb):
    """Pose les questions mises de côté, puis traite les films confirmés.

    Les questions attendent la fin pour ne pas hacher le passage : le script déroule d'abord tout ce qu'il sait faire seul, et n'arbitre qu'ensuite.
    """
    print(f"=== {len(attente)} association(s) à confirmer ===")
    if not cli.can_ask():
        print("  Terminal non interactif : ces films sont laissés de côté.")
        print("  Relance dans un terminal, épingle l'id dans le nom, ou passe")
        print("  --no-ask pour accepter le premier résultat sans demander.\n")
        for entry, doute in attente:
            print(f"  [À CONFIRMER] {entry.display} -> {lookup.describe(doute.candidates[0])}")
            library.note(entry.display, None, "[À CONFIRMER]")
        return Report(matched=len(attente), total=len(attente), pending=len(attente))

    print("  Entrée = garder le 1er, i = laisser de côté, q = arrêter les questions.\n")
    report, arrete = Report(), False
    for numero, (entry, doute) in enumerate(attente, 1):
        print(f"[{numero}/{len(attente)}] {entry.display}   (recherche : '{doute.query}')")
        for note in doute.notes:
            print(f"      /!\\ {note}")
        for rang, candidat in enumerate(doute.candidates, 1):
            print(f"      {rang}) {lookup.describe(candidat)}" + ("   (défaut)" if rang == 1 else ""))
        choix = cli.ASK_SKIP if arrete else cli.ask_choice(len(doute.candidates))
        if choix == cli.ASK_STOP:
            arrete, choix = True, cli.ASK_SKIP
        if choix == cli.ASK_SKIP:
            print("      [NON TRAITÉ] association non confirmée\n")
            report += Report(matched=1, total=1, pending=1)
            library.note(entry.display, None, "[À CONFIRMER]")
            continue
        candidat = doute.candidates[choix]
        movie = movie_details(candidat["id"], doute.order, args, tmdb)
        if movie is None:
            report += Report(total=1, unresolved=1)
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
        print(f"  échec détails TMDB : {e}\n")
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
            print(f"  id épinglé dans le nom : {lookup.describe(movie)}")
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
            print(f"  placé par sa saga : {lookup.describe(saga)}")
        return movie, None

    try:
        results, query = lookup.search_with_context(tmdb, title, year, contexts)
    except TmdbError as e:
        print(f"  échec recherche TMDB : {e}\n")
        return None, None
    if not results:
        print(f"  [NON ASSOCIÉ] recherche '{title}'" + (f" ({year})" if year else "") + " -> aucun résultat\n")
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
# 3. Programme principal
# ----------------------------------------------------------------------------
def parse_args():
    ap = argparse.ArgumentParser(description="Étiquette des films .mkv depuis TMDB (en français).")
    ap.add_argument("--dir", required=True, help="Dossier de films, parcouru récursivement (dossiers de saga compris)")
    ap.add_argument("--log-dir", help="Dossier où ranger metadata.log, metadata.ok et metadata.collections (défaut : la racine de --dir ; créé au besoin)")
    ap.add_argument("--tmdb-id", help="Force l'id TMDB (utile si --dir ne contient qu'un seul film)")
    ap.add_argument("--language", default="fr-FR", help="Langue TMDB (défaut : fr-FR)")
    ap.add_argument("--no-cache", action="store_true", help="Ignore le cache des réponses TMDB et le rafraîchit")
    ap.add_argument("--no-saga", action="store_true", help="N'utilise pas les collections TMDB pour replacer les films")
    ap.add_argument("--no-ask", action="store_true", help="Ne pose aucune question : garde le 1er résultat TMDB, comme avant")
    ap.add_argument("--apply", action="store_true", help="Applique réellement (défaut : simulation)")
    ap.add_argument("--verify", action="store_true", help="Vérifie seulement (aucune écriture)")
    ap.add_argument("--skip-done", action="store_true", help="Saute les films déjà conformes")
    ap.add_argument("--no-cover", action="store_true", help="N'embarque pas la jaquette")
    ap.add_argument("--no-date", action="store_true", help="Ne modifie pas la date du segment")
    ap.add_argument("--no-audio-names", action="store_true", help="Ne renomme pas les pistes audio")
    ap.add_argument("--no-sub-names", action="store_true", help="Ne renomme pas les pistes de sous-titres")
    ap.add_argument("--no-flags", action="store_true", help="Ne touche pas aux drapeaux 'par défaut'")
    ap.add_argument("--no-stats", action="store_true", help="N'ajoute pas les tags de statistiques")
    ap.add_argument("--no-tag", action="store_true", help="Ne modifie aucun film ; avec --artwork, écrit seulement folder.jpg")
    ap.add_argument("--artwork", action="store_true", help="Écrit folder.jpg (affiche EN) par film")
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
        print(f"Aucun .mkv trouvé dans : {args.dir}")
        return
    if args.tmdb_id and len(movies) > 1:
        print(f"Note : --tmdb-id ne s'applique qu'à un seul film ; {len(movies)} détectés "
              "-> id ignoré, recherche par nom.\n")
    if args.no_tag and not args.artwork:
        print("Astuce : --no-tag sans --artwork ne produit rien. Ajoute --artwork.\n")
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
        print(f"{len(corrections)} film(s) replacé(s) par leur saga TMDB.\n")

    titles_file = collections_path(args.dir, args)
    report, library = Report(), Library([], {}, lectures, approved=read_approved(approved_path(args.dir, args)), titles=read_collections(titles_file), titles_file=titles_file)
    if library.titles:
        print(f"{len(library.titles)} titre(s) de collection arrêté(s) dans {COLLECTIONS_NAME}.\n")
    if library.approved:
        print(f"{len(library.approved)} film(s) validé(s) dans {APPROVED_NAME} : leurs doutes ne sont pas signalés.\n")
    attente = []
    for entry in movies:
        print(f"--- {entry.display} ---")
        movie, doute = resolve_movie(entry.rawname, args, tmdb, single=len(movies) == 1, contexts=entry.contexts, tag_id=tag_movie_id(entry, lectures), saga=corrections.get(entry.display))
        if doute is not None:
            print("      [À CONFIRMER] plusieurs versions portent ce titre "
                  "-> question en fin de passage")
            attente.append((entry, doute))
            print()
            continue
        if movie is None:
            report += Report(total=1, unresolved=1)
            library.note(entry.display, None, "[NON ASSOCIÉ]")
            continue
        report += handle_movie(entry, movie, library, args, opts, tmdb)
        print()

    if attente:
        report += resolve_pending(attente, library, args, opts, tmdb)

    print(f"TOTAL : {report.matched}/{report.total} film(s) associé(s).")
    if library.doubts:
        print(f"\nÀ VÉRIFIER : {len(library.doubts)} association(s) suspecte(s)")
        for name, movie, doubts in library.doubts:
            print(f"  {name} -> {lookup.describe(movie)} : {' ; '.join(doubts)}")
        print()
    write_log(args.dir, library, args, report)
    reste = report.epilogue()
    if reste:
        print(f"\nÀ CORRIGER : {reste}.")
    return report.exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except TmdbAuthError as e:
        sys.exit(f"TMDB : {e}")
