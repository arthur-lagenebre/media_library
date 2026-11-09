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
Le titre de COLLECTION inscrit dans le film ne garde pas le suffixe " - Saga" que TMDB ajoute en français : il est retiré d'office. Le reste se CHOISIT : le nom TMDB, ce nom sans son " Collection" final ("Iron Man Collection" ; il peut faire partie du nom : "The Criterion Collection"), le nom de ton dossier de saga quand il en diffère, ou un titre que tu tapes ("autre"). La question est posée une fois par collection, dans le terminal - Entrée prend la proposition marquée "(défaut)", t prend le défaut pour toutes les suivantes (casse des titres comprise) - et la réponse est mémorisée dans "metadata.collections", à côté du journal ("nom TMDB => titre inscrit", une ligne par collection, modifiable à la main ; supprime la ligne pour que la question soit reposée). Une seule proposition, et il n'y a rien à choisir. Hors terminal, sous --no-ask ou en vérification, rien n'est demandé et le nom TMDB est gardé tel quel.
La CASSE du titre se décide avec toi quand TMDB et ton fichier ne diffèrent que par elle : TMDB écrit ses titres français à l'anglaise ("28 Ans plus tard : Le Temple des morts"), ton fichier à la française ("28 ans plus tard - Le temple des morts"). Rien ne dit lequel est juste ("American History X" doit garder ses majuscules), donc la question est posée une fois par titre, dans le terminal - Entrée prend la casse du fichier pour un titre français, celle de TMDB pour un titre anglais -, et la réponse est mémorisée dans "metadata.titles", à côté du journal ("titre TMDB => titre inscrit", modifiable à la main). Hors terminal, sous --no-ask ou en vérification, rien n'est demandé et le titre TMDB est gardé tel quel.
--title-only ne change QUE les titres d'un film déjà étiqueté : le titre du conteneur et les tags TITLE (film, et collection si le fichier en porte un). Les tags sont relus tels quels et réécrits à l'identique, le TITLE excepté : synopsis, casting, genres, identifiant TMDB, statistiques de pistes, noms de pistes, drapeaux, date et jaquette ne bougent pas. Utile après avoir arrêté une casse ou un titre de collection (metadata.titles, metadata.collections) sans réécrire toute la médiathèque. Un fichier sans tag TITLE n'a pas été étiqueté : il est signalé [SANS TAGS] et laissé tel quel (code de sortie 1). Avec --verify, seuls les titres sont comparés ; incompatible avec --no-tag.
--credits-only ne change QUE le casting d'un film déjà étiqueté : DIRECTOR, WRITTEN_BY et ACTOR, chacun avec son id TMDB. Même principe que --title-only : les tags sont relus tels quels et réécrits à l'identique, les personnes exceptées ; titre, synopsis, genres, statistiques de pistes, noms de pistes, drapeaux, date et jaquette ne bougent pas, et le titre du conteneur non plus. Utile après avoir relevé le plafond du casting (50 acteurs) sans réécrire toute la médiathèque. Un fichier sans tag TITLE est signalé [SANS TAGS] et laissé tel quel (code de sortie 1) ; une fiche TMDB sans aucune personne ne vide pas un casting déjà écrit. Avec --verify, seul le casting est comparé ; incompatible avec --no-tag et --title-only.
Ordre de priorité : --tmdb-id, puis l'identifiant épinglé dans le NOM, puis celui lu dans le FICHIER, puis la recherche.
Si un passage à inscrit le mauvais identifiant, corrige-le en épinglant le bon dans le nom - "Dune (2021) [tmdbid-438631]" ou "Dune {tmdb-438631}" - le passage suivant le réécrira dans le fichier.

Usage :
  python Metadata.py --dir "D:\Films"                         # simulation (n'écrit rien)
  python Metadata.py --dir "D:\Films" --apply                 # applique
  python Metadata.py --dir "D:\Films\Inception (2010)" --tmdb-id 27205 --apply   # force l'id (1 film)
  python Metadata.py --dir "D:\Films" --verify                # vérifie seulement

Options : --apply --verify --skip-done --title-only --credits-only --artwork --no-tag --no-cache --no-ask
          --no-saga --log-dir
          --no-cover --no-date --no-audio-names --no-sub-names --no-flags --no-stats
          --tmdb-id (force, si un seul film) --language (défaut fr-FR) --image-size (w780)

À chaque passage, un JOURNAL est écrit à la racine de --dir (ou dans --log-dir, qui accueille alors aussi metadata.ok, metadata.collections et metadata.titles - utile quand la médiathèque est en lecture seule) : "metadata.log" donne le lien TMDB de chaque film trouve, et groupe en fin de fichier ceux qui n'en ont pas - non associes, ou laissés en attente d'une réponse.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))   # pour importer libraries
from libraries.common import cache, cli  # noqa: E402
from libraries.common.report import Report  # noqa: E402
from libraries.video import artwork, casing, credits, lookup, mkv, naming  # noqa: E402
from libraries.video.doubts import identity_doubts  # noqa: E402
from libraries.video.movietags import collection_choices, collection_title, movie_target  # noqa: E402
from libraries.video.resolve import movie_details, resolve_movie, saga_corrections, tag_movie_id  # noqa: E402
from libraries.video.passfiles import (APPROVED_NAME, COLLECTIONS_NAME, TITLES_NAME, approved_path, collections_path,   # noqa: E402
                                      read_approved, read_collections, read_titles, remember_collection, remember_title,
                                      titles_path, write_log)
from libraries.video.tmdb import Tmdb, TmdbAuthError  # noqa: E402


# ----------------------------------------------------------------------------
# 1. Traitement d'un film
# ----------------------------------------------------------------------------
def title_diffs(info, tags, target):
    """[(libellé, actuel, visé)] : ce qui sépare les titres du fichier de ceux de la fiche. Un tag TITLE absent du fichier n'est pas un écart : --title-only ne crée rien."""
    wanted, current = mkv.title_tags(mkv.parse_tags(target.tags_xml)), mkv.title_tags(tags)
    container = ((info or {}).get("container") or {}).get("properties", {}).get("title")
    diffs = [("titre du conteneur", container or "(absent)", target.title)] if container != target.title else []
    for level, label in ((50, "tag TITLE du film"), (70, "tag TITLE de la collection")):
        if level in wanted and level in current and current[level] != wanted[level]:
            diffs.append((label, current[level], wanted[level]))
    return diffs


def process_title_only(path, lecture, movie, args, opts):
    """--title-only : ne change que le titre du conteneur et les tags TITLE d'un film déjà étiqueté. Retourne (non_conforme, echec_ecriture).

    Les tags sont relus tels que mkvextract les rend et réécrits à l'identique, le TITLE excepté : synopsis, casting, identifiant TMDB, statistiques de pistes, tout reste. Un fichier sans aucun TITLE n'a pas été étiqueté : le laisser à moitié étiqueté serait pire que de ne rien faire, il est signalé.
    """
    target = movie_target(movie, opts)
    if not mkv.title_tags(lecture.tags):
        print("      [SANS TAGS] pas encore étiqueté : relance sans --title-only")
        return 1, 0
    diffs = title_diffs(lecture.info, lecture.tags, target)
    if not diffs:
        print("      [OK] titres déjà conformes")
        return 0, 0
    for label, current, wanted in diffs:
        print(f"      [DIFF] {label} : actuel = {current!r}" if args.verify else f"      {label} : {current!r} -> {wanted!r}")
    if args.verify:
        return 1, 0
    if not args.apply:
        return 0, 0
    wanted = mkv.title_tags(mkv.parse_tags(target.tags_xml))
    tags_xml, changes = mkv.retitle(mkv.read_tags_xml(path), wanted)
    if len(changes) != sum(label != "titre du conteneur" for label, _, _ in diffs):
        print("      [ÉCHEC] tags illisibles : rien n'a été modifié")
        return 0, 1
    code, msg = mkv.write_titles(path, target.title, tags_xml if changes else "")
    print(f"      [{'OK' if code == 0 else 'ÉCHEC'}]" + (f" {msg}" if code else ""))
    return 0, (1 if code else 0)


def process_file(path, lecture, movie, args, opts, tmdb):
    """Traite UN fichier du film. Retourne (non_conforme, echec_ecriture), 0 ou 1 chacun."""
    info, tags = lecture.info, lecture.tags
    if lecture.note:
        print(f"      {lecture.note}")
    if getattr(args, "title_only", False):
        return process_title_only(path, lecture, movie, args, opts)
    target = movie_target(movie, opts)
    if getattr(args, "credits_only", False):
        return credits.process(path, tags, target, args.verify, args.apply)

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
    casings: dict = field(default_factory=dict)   # {titre TMDB: titre à écrire}, lu dans metadata.titles
    casings_file: object = None                   # où consigner une réponse sur la casse (None : on ne mémorise rien)
    waiting_casings: set = field(default_factory=set)   # titres laissés sans réponse, signalés une seule fois
    take_defaults: bool = False                   # vrai dès que l'utilisateur répond "t" : la proposition par défaut vaut pour toutes les questions suivantes

    def note(self, display, movie_id=None, statut=""):
        """Consigne le sort d'un film pour le journal de fin de passage."""
        self.journal.append((display, movie_id, statut))


def collection_folder(entry):
    """Nom du dossier de saga qui range ce film : le plus proche, quand le film ne vit pas dans son propre dossier ; "" sinon."""
    return entry.contexts[0] if entry is not None and not entry.owns_folder and entry.contexts else ""


def ask_collection(name, choices, default):
    """Pose la question et rend le titre choisi - une des propositions, ou un titre tapé -, ou cli.ASK_SKIP / cli.ASK_STOP."""
    print(f"      collection TMDB : '{name}'")
    for rang, (title, origin) in enumerate(choices, 1):
        print(f"      {rang}) {title}   ({origin})" + ("   (défaut)" if rang - 1 == default else ""))
    print(f"      {len(choices) + 1}) autre : je tape le titre")
    print(casing.HINT)
    choice = cli.ask_choice(len(choices) + 1, default, True)
    if choice in (cli.ASK_SKIP, cli.ASK_STOP, cli.ASK_ALL):
        return choice
    if choice < len(choices):
        return choices[choice][0]
    typed = cli.ask_text()
    return cli.ASK_STOP if typed is None else (typed or cli.ASK_SKIP)


def settle_collection(movie, library, args, entry=None):
    """Arrête le titre de collection à inscrire dans `movie` (clé `_collection_title`).

    " - Saga" est retiré d'office (voir `collection_title`). Le reste se choisit : le nom TMDB, ce nom sans son " Collection" final (qui peut faire partie du nom : "The Criterion Collection" ne doit pas devenir "The Criterion" sans qu'on l'ait demandé), le nom de ton dossier de saga, ou un titre tapé. Une seule proposition, et il n'y a rien à choisir. La réponse vaut pour toute la collection, et est mémorisée dans metadata.collections.

    Sans terminal, sous --no-ask, en vérification ou sans étiquetage, rien n'est demandé et le nom est gardé tel quel.
    """
    name = ((movie.get("belongs_to_collection") or {}).get("name") or "").strip()
    if not name:
        return
    if name in library.titles:
        movie["_collection_title"] = library.titles[name]
        return
    choices, default = collection_choices(name, collection_folder(entry))
    if len(choices) < 2 or args.verify or args.no_tag:
        return
    if args.no_ask or not library.asking or not cli.can_ask():
        if name not in library.waiting:
            library.waiting.add(name)
            print(f"      [COLLECTION] '{collection_title(name)}' gardé tel quel (non validé) ; "
                  f"à décider dans {COLLECTIONS_NAME}, ou relance dans un terminal")
        return
    if library.take_defaults:
        title = choices[default][0]
        print(f"      collection : '{name}' -> '{title}' (défaut)")
    else:
        title = ask_collection(name, choices, default)
        if title == cli.ASK_ALL:
            library.take_defaults, title = True, choices[default][0]
    if title == cli.ASK_STOP:
        library.asking = False
        return
    if title == cli.ASK_SKIP:
        return
    library.titles[name] = title
    movie["_collection_title"] = title
    if library.titles_file:
        remember_collection(library.titles_file, name, title)


def settle_title(entry, movie, library, args):
    """Arrête la casse du titre à inscrire dans `movie` (clé `title`).

    TMDB écrit ses titres français à l'anglaise ("28 Ans plus tard"), et le fichier s'appelle "28 ans plus tard". Quand les deux ne diffèrent que par la casse, la question est posée une fois ; la réponse vaut pour tous les films de ce titre, et est mémorisée dans metadata.titles. Voir casing.py.

    Sans terminal, sous --no-ask, en vérification ou sans étiquetage, rien n'est demandé et le titre TMDB est gardé tel quel.
    """
    title = movie.get("title") or ""
    if title in library.casings:
        movie["title"] = library.casings[title]
        return
    candidate = casing.recased(title, naming.parse_title_year(naming.extract_tmdb_id(entry.rawname)[1])[0])
    if not candidate or args.verify or args.no_tag:
        return
    if args.no_ask or not library.asking or not cli.can_ask():
        if title not in library.waiting_casings:
            library.waiting_casings.add(title)
            print(f"      [CASSE] '{title}' gardé tel quel (TMDB) ; ton fichier dit '{candidate}' : "
                  f"à décider dans {TITLES_NAME}, ou relance dans un terminal")
        return
    if library.take_defaults:
        answer = casing.default_choice(title, candidate)
        print(f"      casse : '{title}' -> '{answer}' (défaut)")
    else:
        answer = casing.ask(title, candidate)
        if answer == cli.ASK_ALL:
            library.take_defaults, answer = True, casing.default_choice(title, candidate)
    if answer == cli.ASK_STOP:
        library.asking = False
        return
    if answer == cli.ASK_SKIP:
        return
    library.casings[title] = answer
    movie["title"] = answer
    if library.casings_file:
        remember_title(library.casings_file, title, answer)


def handle_movie(entry, movie, library, args, opts, tmdb):
    """Traite un film dont l'association est arrêtée. Retourne son Report."""
    jumeau = library.seen.setdefault(movie.get("id"), entry.display)
    if jumeau != entry.display:
        # Deux dossiers pour un même film : les deux sont étiquetés (une VF et une 4K le méritent).
        print(f"  [DOUBLON] même film que '{jumeau}' -> les deux seront traités")
    library.resolved.append(movie)
    settle_collection(movie, library, args, entry)
    settle_title(entry, movie, library, args)
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


# ----------------------------------------------------------------------------
# 2. Programme principal
# ----------------------------------------------------------------------------
def parse_args():
    ap = argparse.ArgumentParser(description="Étiquette des films .mkv depuis TMDB (en français).")
    ap.add_argument("--dir", required=True, help="Dossier de films, parcouru récursivement (dossiers de saga compris)")
    ap.add_argument("--log-dir", help="Dossier où ranger metadata.log, metadata.ok, metadata.collections et metadata.titles (défaut : la racine de --dir ; créé au besoin)")
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
    ap.add_argument("--title-only", action="store_true", help="Ne change que le titre : celui du conteneur et les tags TITLE (film, collection) d'un film déjà étiqueté ; synopsis, casting, pistes, date et jaquette ne bougent pas")
    ap.add_argument("--credits-only", action="store_true", help="Ne change que le casting : réalisateurs, scénaristes et acteurs (avec leur id TMDB) d'un film déjà étiqueté ; titre, synopsis, pistes, date et jaquette ne bougent pas")
    ap.add_argument("--artwork", action="store_true", help="Écrit folder.jpg (affiche EN) par film")
    ap.add_argument("--image-size", default="w780", help="Taille TMDB : w300 / w780 / original")
    args = ap.parse_args()
    if args.title_only and args.no_tag:
        ap.error("--title-only et --no-tag se contredisent : l'un ne change que les titres, l'autre rien")
    if args.credits_only and args.no_tag:
        ap.error("--credits-only et --no-tag se contredisent : l'un ne change que le casting, l'autre rien")
    if args.credits_only and args.title_only:
        ap.error("--credits-only et --title-only ne se combinent pas : une seule catégorie à la fois")
    return args


def print_notes(movies, args):
    """Les options qui ne feront rien, ou pas ce qu'on croit, avec ce qu'on a trouvé."""
    if args.tmdb_id and len(movies) > 1:
        print(f"Note : --tmdb-id ne s'applique qu'à un seul film ; {len(movies)} détectés "
              "-> id ignoré, recherche par nom.\n")
    if args.no_tag and not args.artwork:
        print("Astuce : --no-tag sans --artwork ne produit rien. Ajoute --artwork.\n")
    if args.artwork and not any(e.owns_folder for e in movies):
        print("Note : --artwork sans effet ici : aucun dossier ne contient un seul film.\n")


def read_files(movies, args):
    """{chemin: Reading} de tous les fichiers, lus d'un coup, en parallèle : chaque fichier coûte deux à trois sous-processus qu'on ne fait qu'attendre, et rien là-dedans ne dépend de TMDB. L'affichage, lui, garde son ordre."""
    fichiers = [f for entry in movies for f in entry.files]
    if not args.no_tag:
        return mkv.inspect_all(fichiers, args.probe, with_tags=args.verify or args.skip_done or args.title_only or args.credits_only)
    # Sans étiquetage, on ne lit des fichiers que leurs tags et leur durée - pour l'identifiant TMDB qu'un passage précédent y a inscrit, et le contrôle de l'association. Sans lui, la fiche rechercherait chaque film par son nom et "Mortal Kombat" (1995) y redeviendrait celui de 2021. Lu en Python pur : ni MKVToolNix ni ffprobe, de quoi tourner sur un NAS.
    return mkv.read_light_all(fichiers)


def open_library(lectures, args):
    """La Library du passage, avec les films validés (metadata.ok) et les titres de collection arrêtés (metadata.collections)."""
    titles_file, casings_file = collections_path(args.dir, args), titles_path(args.dir, args)
    library = Library([], {}, lectures, approved=read_approved(approved_path(args.dir, args)), titles=read_collections(titles_file), titles_file=titles_file,
                      casings=read_titles(casings_file), casings_file=casings_file)
    if library.titles:
        print(f"{len(library.titles)} titre(s) de collection arrêté(s) dans {COLLECTIONS_NAME}.\n")
    if library.casings:
        print(f"{len(library.casings)} casse(s) de titre arrêtée(s) dans {TITLES_NAME}.\n")
    if library.approved:
        print(f"{len(library.approved)} film(s) validé(s) dans {APPROVED_NAME} : leurs doutes ne sont pas signalés.\n")
    return library


def process_library(movies, library, corrections, args, opts, tmdb):
    """Associe et traite chaque film, puis pose les questions mises de côté. Retourne le Report du passage."""
    report, attente = Report(), []
    for entry in movies:
        print(f"--- {entry.display} ---")
        movie, doute = resolve_movie(entry.rawname, args, tmdb, single=len(movies) == 1, contexts=entry.contexts, tag_id=tag_movie_id(entry, library.lectures), saga=corrections.get(entry.display))
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
    return report


def print_summary(report, library):
    """Le bilan du passage, et les associations suspectes."""
    print(f"TOTAL : {report.matched}/{report.total} film(s) associé(s).")
    if library.doubts:
        print(f"\nÀ VÉRIFIER : {len(library.doubts)} association(s) suspecte(s)")
        for name, movie, doubts in library.doubts:
            print(f"  {name} -> {lookup.describe(movie)} : {' ; '.join(doubts)}")
        print()


def main():
    args = parse_args()
    cli.setup_console()
    cli.check_dir(args.dir)
    args.probe = mkv.check_tools(needs_mkvtoolnix=not args.no_tag)
    opts = mkv.Options.from_args(args)
    tmdb = Tmdb(cli.resolve_tmdb_key(), args.language, user_agent="movies_mkv/1.0", cache=cache.Cache(read=not args.no_cache))

    print(f"=== {cli.mode_label(args)} ===   source : TMDB {args.language}\n")
    if args.title_only:
        print("Titres seulement : le titre du conteneur et les tags TITLE sont seuls modifiés ; le reste du fichier ne bouge pas.\n")
    if args.credits_only:
        print("Casting seulement : les réalisateurs, scénaristes et acteurs sont seuls modifiés ; le reste du fichier ne bouge pas.\n")

    movies = naming.find_movies(args.dir)
    if not movies:
        print(f"Aucun .mkv trouvé dans : {args.dir}")
        return
    print_notes(movies, args)

    lectures = read_files(movies, args)
    corrections = {} if args.no_saga else saga_corrections(movies, lectures, args, tmdb)
    if corrections:
        print(f"{len(corrections)} film(s) replacé(s) par leur saga TMDB.\n")

    library = open_library(lectures, args)
    report = process_library(movies, library, corrections, args, opts, tmdb)
    print_summary(report, library)
    write_log(args.dir, library.journal, args, report)
    reste = report.epilogue()
    if reste:
        print(f"\nÀ CORRIGER : {reste}.")
    return report.exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except TmdbAuthError as e:
        sys.exit(f"TMDB : {e}")
