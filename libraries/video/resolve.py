"""Associer un fichier de film à sa fiche TMDB, et replacer par leur saga ceux qu'un homonyme aurait détournés.

Dans l'ordre de ce qui fait foi : l'identifiant donné en ligne de commande (un seul film), celui épinglé dans le nom, celui inscrit dans le fichier par un passage précédent, la saga qui a replacé le film, et enfin la recherche par le titre. Quand plusieurs fiches écrivent le même titre, le film n'est pas chargé : un `Doubt` est rendu, et la question est posée en fin de passage.

Ces fonctions parlent à TMDB et affichent ce qu'elles trouvent ; aucune n'écrit dans un fichier.
"""

import contextlib
import io

from . import lookup, mkv, naming
from . import saga as saga_module
from .tmdb import TmdbError, release_region


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
