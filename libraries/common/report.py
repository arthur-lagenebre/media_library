"""Le bilan d'un passage : ce qui a été traité, et ce qui reste à corriger.

Commun aux scripts de toutes les médiathèques - films, séries, musique -, qui totalisent leurs éléments de la même façon et rendent le même code de sortie.
"""

from dataclasses import dataclass


@dataclass
class Report:
    """Ce qu'un traitement a donné. Additionnable pour totaliser une série.

    `diffs` et `failures` sont ce qui reste à corriger : ils décident du code de sortie, pour qu'un script sache si le passage s'est bien termine.
    """
    matched: int = 0        # éléments associés à une fiche (TMDB, MusicBrainz)
    total: int = 0          # fichiers vus
    diffs: int = 0          # fichiers non conformes (--verify)
    failures: int = 0       # écritures en échec
    skipped: int = 0        # laissés de côté : pistes ambiguës, décision humaine
    pending: int = 0        # associations restées à confirmer

    def __add__(self, other):
        return Report(self.matched + other.matched, self.total + other.total, self.diffs + other.diffs, self.failures + other.failures, self.skipped + other.skipped, self.pending + other.pending)

    @property
    def exit_code(self):
        return 1 if (self.diffs or self.failures or self.skipped or self.pending) else 0

    def epilogue(self):
        """Ligne finale à afficher quand quelque chose n'est pas passé."""
        restes = []
        if self.diffs:
            restes.append(f"{self.diffs} fichier(s) non conforme(s)")
        if self.skipped:
            restes.append(f"{self.skipped} non traite(s) pour pistes ambigues")
        if self.pending:
            restes.append(f"{self.pending} association(s) a confirmer")
        if self.failures:
            restes.append(f"{self.failures} ecriture(s) en echec")
        return " ; ".join(restes)
