"""Miniatures des couvertures, pour les pages HTML.

Une couverture de comics fait 4 Mo et 2700 pixels de large ; une vignette de page en demande 240. Réduire, c'est ce qui permet d'embarquer des milliers de couvertures dans des pages de quelques Mo. Pillow est la seule dépendance de ce dossier, et elle est facultative : sans lui, `thumbnail` rend None et les pages montrent un monogramme à la place.
"""

import io
import warnings

try:
    from PIL import Image
except ImportError:          # Pillow est facultatif
    Image = None

# Une couverture tronquée fait écrire un avertissement à Pillow, qui n'indique même pas de quel livre il s'agit : sur des milliers de couvertures, il noierait la sortie du script. Ce que Pillow n'arrive pas à lire rend None plus bas.
warnings.filterwarnings("ignore", module="PIL")

WIDTH = 240          # le double de la vignette affichée (~150 px) : nette sur un écran haute densité
QUALITY = 72
RESAMPLE = getattr(getattr(Image, "Resampling", Image), "LANCZOS", None) if Image else None


def available():
    return Image is not None


def thumbnail(data, width=WIDTH, quality=QUALITY):
    """JPEG de `width` pixels de large au plus (octets), ou None si Pillow manque ou que l'image est illisible."""
    if Image is None:
        return None
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format == "JPEG":
                # Le décodeur JPEG sait réduire par 2, 4 ou 8 en décodant : dix fois plus vite pour une page de comics que de la décoder en entier.
                image.draft("RGB", (width * 2, width * 3))
            image = image.convert("RGB")
            if image.width > width:
                image = image.resize((width, max(1, round(image.height * width / image.width))), RESAMPLE)
            out = io.BytesIO()
            image.save(out, "JPEG", quality=quality, optimize=True)
            return out.getvalue()
    except Exception:        # Pillow lève de tout (OSError, ValueError, SyntaxError, DecompressionBombError...) sur un fichier abîmé : une couverture illisible n'arrête pas un passage
        return None
