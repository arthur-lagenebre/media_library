"""Les briques des scripts du dépôt, rangées par domaine.

  common/   ce qui ne dépend d'aucun domaine : cache disque, ligne de commande, bilan d'un passage, noms de fichiers, renommage, écriture de fichiers texte
  video/    films et séries : TMDB, fichiers .mkv, analyse des noms
  music/    musique : MusicBrainz, fichiers .flac et .mp3, albums, catalogue
  books/    livres, BD, comics et mangas : lecture des .cbz et .epub, étagère

video/, music/ et books/ ne se connaissent pas : chacun n'emprunte qu'à common/. Ce qui serait utile aux deux va donc dans common/, jamais de l'un chez l'autre.

Aucune dépendance pip : uniquement la bibliothèque standard.
"""
