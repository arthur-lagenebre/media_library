"""Briques des scripts de livres : romans, BD, comics, mangas.

Un livre est un fichier - .cbz pour les bandes dessinées, .epub et .pdf pour le reste - qui porte souvent sa propre fiche : ComicInfo.xml dans un .cbz, le .opf d'un .epub (Calibre, le plus souvent). Les scripts de Books/ ne gardent que leur déroulé ; la lecture de ces fiches, le parcours de l'étagère et les pages HTML vivent ici. Ce qui n'est propre à aucun domaine - ligne de commande, bilan d'un passage, pages écrites à l'identique, icônes d'onglet - vient de libraries/common/ ; ce dossier ne dépend jamais de libraries/video/ ni de libraries/music/.

Aucune dépendance obligatoire : uniquement la bibliothèque standard. Pillow, s'il est installé, réduit les couvertures ; sans lui les pages montrent un monogramme à leur place.
"""
