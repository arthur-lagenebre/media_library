"""Les raisons de douter qu'une fiche TMDB soit bien le film du fichier.

Une association fausse ne se voit pas : le fichier est étiqueté comme un autre film, avec assurance. Deux signaux la trahissent - une durée qui ne correspond à aucune version du film, une fiche que presque personne n'a notée - et ils se signalent sans rien imposer.
"""

from . import mkv, naming

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
