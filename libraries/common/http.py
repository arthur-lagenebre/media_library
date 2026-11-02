"""GET HTTP avec réessais, commun aux clients TMDB et MusicBrainz.

Les deux APIs se comportent pareil quand elles sont sollicitées : un 429 ou une panne serveur passent en quelques secondes, une connexion coupée aussi. Ce qui diffère - quelle erreur lever, quel code est définitif, combien attendre - reste dans chaque client ; ici, la boucle.
"""

import random
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MAX_RETRY_WAIT = 30        # secondes : plafond du Retry-After renvoyé par le serveur


def retry_after(headers):
    """Délai demandé par le serveur dans l'en-tête Retry-After, si exploitable."""
    value = (headers or {}).get("Retry-After")
    if value and str(value).strip().isdigit():
        return min(int(value), MAX_RETRY_WAIT)
    return None


def backoff(attempt, base):
    """Attente exponentielle + bruit : des requêtes parallèles sans bruit reviendraient toutes taper au même instant. `base` = 1 : 1 s, 2 s, 4 s... ; 2 : 2 s, 4 s..."""
    return base * 2 ** (attempt - 1) + random.uniform(0, 0.5)


def fetch(url, headers, timeout, attempts, fail, refuse, base=1, before_attempt=None):
    """GET brut avec réessais. Retourne (octets, en-têtes).

    `refuse(erreur_http)` rend l'exception à lever tout de suite pour un échec définitif (404, clé refusée...) ; elle n'est consultée que pour les codes qui ne se réessaient pas, car 429 et pannes serveur (5xx) le sont toujours. `fail(message)` rend l'exception à lever quand les tentatives sont épuisées. `before_attempt()` est appelée avant chaque tentative : MusicBrainz y espace ses requêtes.
    """
    for attempt in range(1, attempts + 1):
        if before_attempt:
            before_attempt()
        wait = None
        try:
            with urlopen(Request(url, headers=headers), timeout=timeout) as r:
                return r.read(), r.headers
        except HTTPError as e:            # sous-classe d'URLError : à rattraper avant
            if e.fp is not None:          # sans corps, Python 3.8 lève KeyError à la fermeture
                e.close()                 # le corps d'une erreur ne sert à rien : sa connexion ne reste pas ouverte pendant l'attente
            if e.code != 429 and e.code < 500:
                raise refuse(e) from e
            failure, wait = e, retry_after(e.headers)
        except (URLError, OSError, HTTPException) as e:   # réseau, DNS, timeout, réponse coupée en route (IncompleteRead n'est pas un OSError)
            failure = e
        if attempt == attempts:
            raise fail(str(failure)) from failure
        time.sleep(wait if wait is not None else backoff(attempt, base))
