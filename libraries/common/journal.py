"""Le journal d'un passage : ce que le script affiche, recopié dans le fichier donné par --log.

Les scripts qui n'ont pas de journal propre affichent déjà une ligne par élément traité : leur console est leur journal. `--log FICHIER` la garde ; sans `--log`, rien n'est écrit.

Le texte est gardé en mémoire et écrit à la fin du passage, pas au fil de l'eau : un fichier resté ouvert dans `--dir` empêcherait sous Windows de renommer ce dossier (`Rename_Movies` le fait quand le dossier ne contient qu'un film). Il est écrit aussi après une erreur, un Ctrl-C ou `sys.exit`, puisque c'est alors qu'on en a le plus besoin.

Les lignes de progression (`cli.progress`, `cli.clear_line`), réécrites sur place, commencent par "\\r" : elles restent à l'écran et hors du fichier.
"""

import sys
from contextlib import contextmanager
from pathlib import Path


def add_option(parser):
    """Déclare `--log FICHIER` (défaut : pas de journal)."""
    parser.add_argument("--log", metavar="FICHIER", help="recopie ce qui s'affiche dans ce fichier (défaut : pas de journal)")


class _Recopie:
    """Console qui écrit à l'écran et garde une copie ; tout le reste (`isatty`, `encoding`, `flush`...) est celui de la console."""

    def __init__(self, console):
        self._console = console
        self._copie = []

    def write(self, texte):
        if not texte.startswith("\r"):
            self._copie.append(texte)
        return self._console.write(texte)

    def text(self):
        return "".join(self._copie)

    def __getattr__(self, nom):
        return getattr(self._console, nom)


@contextmanager
def record(destination):
    """Recopie dans `destination` tout ce qui s'affiche dans le bloc ; ne fait rien si `destination` est None.

    Le fichier est écrit en UTF-8 à la sortie du bloc, quelle qu'elle soit. S'il ne peut pas l'être, le message le dit et le passage continue : un journal manqué ne change ni le résultat ni le code de sortie.
    """
    if destination is None:
        yield
        return
    destination = Path(destination)
    console = sys.stdout
    recopie = _Recopie(console)
    sys.stdout = recopie
    try:
        yield
    finally:
        sys.stdout = console
        try:
            destination.write_text(recopie.text(), encoding="utf-8")
            print(f"[log] {destination} écrit")
        except OSError as exc:
            print(f"[log] impossible d'écrire {destination} : {exc.strerror or exc}")
