"""Utilitaires de ligne de commande : console, fichier .env, clé TMDB."""

import sys
from pathlib import Path


def setup_console():
    """Force stdout/stderr en UTF-8 tolérant.

    Sous Windows la console est en cp1252 : afficher un titre TMDB japonais ou cyrillique y leve UnicodeEncodeError et interrompt le script en plein travail (un renommage à moitié applique, par exemple). Avec errors=replace le caractère s'affiche mal, mais le traitement va au bout.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):        # flux redirige, non reconfigurable
            pass


def read_dotenv(filename=".env"):
    """Valeurs d'un fichier .env (lignes CLÉ=valeur), en dictionnaire.

    Le fichier est cherché en remontant depuis le dossier de ce module, puis depuis le dossier courant ; on s'arrête au premier trouvé. Rien n'est écrit dans les variables d'environnement : le .env est la seule source de la clé, et mieux vaut que ça se voie ici plutôt que de se deviner ailleurs.
    """
    for start in (Path(__file__).resolve().parent, Path.cwd().resolve()):
        for folder in (start, *start.parents):
            path = folder / filename
            if not path.is_file():
                continue
            valeurs = {}
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if line.startswith("export "):
                    line = line[7:].lstrip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                name, value = name.strip(), value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                if name:
                    valeurs.setdefault(name, value)      # la première ligne l'emporte
            return valeurs
    return {}


NO_KEY_MESSAGE = ("Aucune clé TMDB. Renseigne la ligne TMDB_KEY=... du fichier .env "
                  "à la racine du dépôt (voir .env.example).")


def resolve_tmdb_key():
    """Clé TMDB lue dans le fichier .env, seule source acceptee.

    Quitte avec un message explicite si le fichier manque ou ne la donne pas.
    """
    key = read_dotenv().get("TMDB_KEY", "").strip()
    if not key:
        sys.exit(NO_KEY_MESSAGE)
    return key


def check_dir(path):
    """Vérifie que --dir désigne un dossier existant, et s'arrête clairement sinon.

    Une faute de frappe dans le chemin est l'erreur la plus courante : sans ce contrôle, elle ressort soit en pile d'appels, soit - pire - en "aucun fichier trouve", qui ressemble à une médiathèque vide.
    """
    dossier = Path(path)
    if not dossier.exists():
        sys.exit(f"Dossier introuvable : {dossier}")
    if not dossier.is_dir():
        sys.exit(f"--dir attend un dossier, pas un fichier : {dossier}")
    return dossier


ASK_SKIP, ASK_STOP, ASK_ALL = "ignorer", "arreter", "tout"


def can_ask():
    """Vrai si une question à une chance d'obtenir une réponse.

    Sortie redirigée vers un fichier, exécution dans un CI, entrée fermée : la question ne serait vue par personne et le script attendrait indéfiniment. Mieux vaut alors laisser le cas de côté que de bloquer un passage entier.
    """
    try:
        return bool(sys.stdin and sys.stdin.isatty() and sys.stdout.isatty())
    except (AttributeError, ValueError):         # flux ferme ou remplace
        return False


def ask_choice(nombre, defaut=0, tout=False):
    """Indice choisi parmi `nombre` propositions, ou ASK_SKIP / ASK_STOP.

    Entrée vide = le défaut. Une réponse incomprise repose la question plutôt que de décider à la place de quelqu'un - c'est tout l'intérêt de demander. Avec `tout`, "t" rend ASK_ALL : le défaut pour cette question et pour toutes celles qui suivent, quand elles sont nombreuses et que le défaut est presque toujours le bon.
    """
    while True:
        try:
            reponse = input(f"      choix [{defaut + 1}] : ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return ASK_STOP
        if not reponse:
            return defaut
        if reponse in ("i", "ignorer"):
            return ASK_SKIP
        if reponse in ("q", "quitter", "arreter"):
            return ASK_STOP
        if tout and reponse in ("t", "tout"):
            return ASK_ALL
        if reponse.isdigit() and 1 <= int(reponse) <= nombre:
            return int(reponse) - 1
        print(f"      réponse non comprise : un numéro de 1 à {nombre}, "
              + ("t pour le défaut à toutes les suivantes, " if tout else "")
              + "i pour laisser de côté, q pour arrêter les questions.")


def ask_text(invite="      titre : "):
    """Le texte tapé, sans ses espaces de bord ; "" si rien n'est tapé, None si l'entrée se ferme ou si Ctrl-C interrompt.

    Pour la réponse que aucune proposition ne couvre : une réponse vide ne décide rien, c'est à l'appelant de laisser la question sans réponse.
    """
    try:
        return input(invite).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def ask_yes_no(defaut=True):
    """True (oui) ou False (non), None si l'entrée se ferme ou si Ctrl-C interrompt.

    Entrée vide = le défaut. Une réponse incomprise repose la question plutôt que de décider à la place de quelqu'un.
    """
    while True:
        try:
            reponse = input(f"      [{'O/n' if defaut else 'o/N'}] : ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not reponse:
            return defaut
        if reponse in ("o", "oui", "y", "yes"):
            return True
        if reponse in ("n", "non", "no"):
            return False
        print("      réponse non comprise : o pour oui, n pour non.")


def mode_label(args, simulation="rien ne sera écrit ; ajoute --apply pour appliquer"):
    """Libellé du mode courant, pour la bannière affichee au démarrage."""
    if getattr(args, "verify", False):
        return "VÉRIFICATION (aucune écriture)"
    return "APPLICATION" if args.apply else f"SIMULATION ({simulation})"


PROGRESS_WIDTH = 100     # ligne de progression : de quoi tenir dans un terminal étroit


def readable_size(octets):
    """Taille lisible : on ne parle pas en téraoctets d'un dossier de trois films."""
    for unite, seuil in (("To", 1e12), ("Go", 1e9), ("Mo", 1e6)):
        if octets >= seuil:
            return f"{octets / seuil:.2f} {unite}"
    return f"{octets / 1e3:.0f} ko"


def readable_time(secondes):
    """Durée lisible, de la seconde à l'heure."""
    if secondes < 60:
        return f"{secondes:.0f} s"
    if secondes < 3600:
        return f"{secondes / 60:.1f} min"
    return f"{secondes / 3600:.1f} h"


def progress(fait, total, nom):
    """Ligne réécrite sur place. Muette hors terminal : redirigée, elle salirait.

    Le nom du fichier en cours compte autant que le compteur : un contrôle rapide passe une demi-seconde par fichier, mais un contrôle complet peut rester dix minutes sur le même, et il faut voir lequel.
    """
    try:
        if not sys.stdout.isatty():
            return
    except (AttributeError, ValueError):            # flux ferme ou remplace
        return
    ligne = f"  {fait}/{total}  {nom}"
    print(f"\r{ligne[:PROGRESS_WIDTH]:<{PROGRESS_WIDTH}}", end="", flush=True)


def clear_line():
    """Rend la ligne de progression au message qui va s'afficher à sa place."""
    try:
        if sys.stdout.isatty():
            print(f"\r{'':<{PROGRESS_WIDTH}}\r", end="")
    except (AttributeError, ValueError):
        pass
