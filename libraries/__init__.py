"""Les briques des scripts du dépôt, rangées par domaine.

  common/   ce qui ne dépend d'aucun domaine : cache disque, ligne de commande, bilan d'un passage, noms de fichiers, renommage, écriture des pages
  video/    films et séries : TMDB, fichiers .mkv, analyse des noms, fiches HTML
  music/    musique : MusicBrainz, fichiers .flac, albums

video/ et music/ ne se connaissent pas : chacun n'emprunte qu'à common/. Ce qui serait utile aux deux va donc dans common/, jamais de l'un chez l'autre.

Aucune dépendance pip : uniquement la bibliothèque standard.
"""
