"""Briques des scripts de musique : MusicBrainz, fichiers .flac, albums.

Les scripts de Music/ ne gardent que leur déroulé : l'accès à MusicBrainz et à Cover Art Archive, la lecture et l'écriture des .flac, la reconnaissance des albums et le choix de leur édition vivent ici. Ce qui n'est propre à aucun domaine - cache, ligne de commande, bilan d'un passage, noms de fichiers - vient de libraries/common/ ; ce dossier ne dépend jamais de libraries/video/.

Aucune dépendance pip : uniquement la bibliothèque standard.
"""
