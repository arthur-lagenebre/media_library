"""La casse d'un titre français : TMDB l'écrit à l'anglaise, un nom de fichier à la française.

TMDB rend "28 Ans plus tard : Le Temple des morts" ; le fichier s'appelle "28 ans plus tard - Le temple des morts". Aucune règle ne dit lequel est juste : "American History X" doit garder ses majuscules, "Le voyage de Chihiro" son nom propre, et mettre tout en minuscules sans dictionnaire les ferait sauter. Seul celui qui a écrit le nom de fichier le sait.

Ce module repère le cas - le titre TMDB et le nom du fichier ne diffèrent que par la casse - et propose la version du fichier ; c'est le script qui pose la question et mémorise la réponse.
"""

import re

from libraries.common import cli

WORD_RE = re.compile(r"[^\W_]+")
HINT = "      (Entrée = défaut ; t = défaut pour toutes les suivantes ; i = laisser ; q = arrêter les questions)"
# Des mots que seul du français contient : ils décident de la réponse proposée par défaut, jamais d'une écriture.
FRENCH_WORDS = {"le", "la", "les", "des", "du", "un", "une", "au", "aux", "et", "pour", "dans", "sur", "avec", "sans", "plus", "ans", "jours"}


def recased(title, disk_name):
    """`title` écrit avec la casse de `disk_name`, ou None quand il n'y a rien à demander.

    Le nom du fichier doit être ce titre à la casse près, ou n'en être qu'un morceau contigu ("La naissance d'un empire" dans "300 : La Naissance d'un Empire") : la ponctuation ne compte pas, les accents si. Le premier mot du morceau garde la casse de TMDB - c'est une majuscule de début de phrase, que le fichier ne dit pas toujours. Seuls les mots suivants prennent celle du fichier ; s'ils sont déjà pareils, il n'y a pas de question.
    """
    found = list(WORD_RE.finditer(title))
    theirs = WORD_RE.findall(disk_name)
    n = len(theirs)
    if n < 2 or n > len(found):
        return None
    wanted = [w.lower() for w in theirs]
    start = next((i for i in range(len(found) - n + 1) if [m.group().lower() for m in found[i:i + n]] == wanted), None)
    if start is None:
        return None
    out = title
    for match, word in reversed(list(zip(found[start + 1:start + n], theirs[1:]))):
        out = out[:match.start()] + word + out[match.end():]
    return out if out != title else None


def looks_french(title):
    """Vrai si le titre contient un mot que seul le français emploie : la réponse proposée par défaut."""
    return any(word.lower() in FRENCH_WORDS for word in WORD_RE.findall(title))


def default_choice(title, candidate):
    """Le titre que proposerait ask() par défaut : la casse du fichier pour un titre français, celle de TMDB sinon."""
    return candidate if looks_french(title) else title


def ask(title, candidate, what="titre"):
    """Pose la question et rend le titre choisi, ou cli.ASK_SKIP / cli.ASK_STOP / cli.ASK_ALL (le défaut, pour celle-ci et toutes les suivantes).

    Un titre français est proposé par défaut avec la casse du fichier, un titre anglais avec celle de TMDB : "American History X" ne devient pas "American history X" parce qu'on a répondu Entrée.
    """
    default = 0 if looks_french(title) else 1
    print(f"      {what} : TMDB écrit '{title}', ton fichier '{candidate}'")
    for rang, (texte, origine) in enumerate(((candidate, "casse de ton fichier"), (title, "casse de TMDB")), 1):
        print(f"      {rang}) {texte}   ({origine})" + ("   (défaut)" if rang - 1 == default else ""))
    print(HINT)
    choice = cli.ask_choice(2, default, True)
    return choice if choice in (cli.ASK_SKIP, cli.ASK_STOP, cli.ASK_ALL) else (candidate, title)[choice]
