"""Lecture et écriture des tags d'un .mp3 (ID3v2), sans outil externe.

Un .mp3 n'a pas d'en-tête propre : ses tags sont une étiquette ID3v2 collée DEVANT les trames audio. Elle commence par "ID3", une version, la taille de ce qui suit, puis une suite de trames "identifiant de 4 lettres + taille + contenu", puis du padding (des zéros) qui réserve de la place pour retoucher les tags plus tard. Comme pour un .flac, tant que les nouvelles trames tiennent dans l'espace déjà occupé on réécrit l'étiquette sur place et le son ne bouge pas d'un octet ; sinon - une pochette ajoutée, ou un fichier qui n'a aucune étiquette - le fichier est recopié à côté puis substitué à l'original.

Pour les scripts, ce module se présente comme flac.py : des tags sous les noms de clé Vorbis ("TITLE", "MUSICBRAINZ_ALBUMID"...) et des Picture. La correspondance avec les trames suit celle de Picard : un fichier étiqueté ici se relit à l'identique dans Picard, et un fichier déjà passé par Picard ne paraît pas différent.

Lit les ID3v2.3 et 2.4, écrit de l'ID3v2.4 : plusieurs valeurs dans une trame (genres, labels, artistes) s'y séparent par un octet nul, sans convention de "/" qui casserait "AC/DC". Les ID3v2.2 (rares, d'avant 1999) sont refusés plutôt que réécrits à moitié. L'étiquette ID3v1 de fin de fichier n'est pas touchée.

Tout ce qui n'est pas un tag géré - ReplayGain, paroles (USLT), commentaires (COMM), notes (POPM), compositeur... - est recopié tel quel.
"""

from __future__ import annotations

import os
import re
import shutil
import struct
import tempfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from .tags import FRONT_COVER, AudioError, Picture, front_cover, image_dimensions  # noqa: F401  (réexportés, comme dans flac.py)

DEFAULT_PADDING = 2048        # de quoi retoucher les tags plus tard sans tout recopier
MAX_TAG = (1 << 28) - 1       # la taille de l'étiquette comme celle d'une trame tient sur 4 x 7 bits
UTF8, UTF16 = 3, 1            # codages de texte d'ID3v2 ; 0 = latin-1 et 2 = UTF-16BE ne sont que lus
TEXT_ENCODING = UTF8
MB_OWNER = b"http://musicbrainz.org"   # propriétaire de la trame UFID qui porte l'identifiant de l'enregistrement
SCAN_BYTES = 65536            # où chercher la première trame audio derrière l'étiquette

# Clé Vorbis <-> trame de texte.
TEXT_FRAMES = {"TITLE": "TIT2", "ARTIST": "TPE1", "ARTISTSORT": "TSOP", "ALBUM": "TALB", "ALBUMARTIST": "TPE2", "ALBUMARTISTSORT": "TSO2", "GENRE": "TCON", "LABEL": "TPUB", "MEDIA": "TMED", "DATE": "TDRC", "ORIGINALDATE": "TDOR"}
KEYS_BY_FRAME = {frame: key for key, frame in TEXT_FRAMES.items()}
# Clé Vorbis <-> description de la trame TXXX, telle que Picard l'écrit. Toute autre TXXX garde sa description pour clé (REPLAYGAIN_TRACK_GAIN...).
TXXX_DESCRIPTIONS = {"MUSICBRAINZ_ALBUMID": "MusicBrainz Album Id", "MUSICBRAINZ_RELEASEGROUPID": "MusicBrainz Release Group Id", "MUSICBRAINZ_ALBUMARTISTID": "MusicBrainz Album Artist Id", "MUSICBRAINZ_ARTISTID": "MusicBrainz Artist Id", "MUSICBRAINZ_RELEASETRACKID": "MusicBrainz Release Track Id", "RELEASETYPE": "MusicBrainz Album Type", "RELEASESTATUS": "MusicBrainz Album Status", "RELEASECOUNTRY": "MusicBrainz Album Release Country", "BARCODE": "BARCODE", "CATALOGNUMBER": "CATALOGNUMBER", "ORIGINALYEAR": "originalyear"}
KEYS_BY_DESCRIPTION = {description.upper(): key for key, description in TXXX_DESCRIPTIONS.items()}
# TRCK et TPOS portent "numéro/total" : le total se lit, et s'écrit, sous les deux noms qu'on lui donne en Vorbis.
NUMBER_FRAMES = {"TRCK": ("TRACKNUMBER", ("TRACKTOTAL", "TOTALTRACKS")), "TPOS": ("DISCNUMBER", ("DISCTOTAL", "TOTALDISCS"))}
FRAME_BY_NUMBER_KEY = {key: frame_id for frame_id, (number, totals) in NUMBER_FRAMES.items() for key in (number, *totals)}
# Trames dont les tags sont relus et réécrits à partir des clés : tout le reste est recopié tel quel. Les dernières sont celles d'ID3v2.3, devenues dates et années.
MANAGED_IDS = set(TEXT_FRAMES.values()) | set(NUMBER_FRAMES) | {"TXXX", "APIC", "TYER", "TDAT", "TIME", "TORY"}
# Trames d'ID3v2.3 que la 2.4 a retirées et que rien ne saurait lire : abandonnées plutôt que recopiées en trames invalides.
OBSOLETE_IDS = {"RVAD", "EQUA", "TRDA", "TSIZ"}
GENRE_REFERENCE_RE = re.compile(r"^\((?:\d+|RX|CR)\)(.+)$")      # "(17)Rock" : le numéro d'ID3v1, suivi du nom
FRAME_ID_RE = re.compile(rb"^[A-Z0-9]{4}$")


class Mp3Error(AudioError):
    """Fichier illisible ou écriture impossible : l'appelant passe au suivant."""


@dataclass
class Frame:
    """Une trame lue : son identifiant et son contenu, débarrassé de ce qui n'est qu'emballage (désynchronisation, compression, longueur)."""
    id: str
    body: bytes
    status: int = 0          # indicateurs "tag alter / file alter / read only", à leur place d'ID3v2.4


@dataclass
class Metadata:
    """Ce que l'étiquette d'un .mp3 contient, tel qu'on l'a lu."""
    frames: list                                   # [Frame] dans l'ordre du fichier
    audio_offset: int                              # octet où commencent les trames audio ; 0 sans étiquette
    version: int = 0                               # 3 ou 4 ; 0 sans étiquette
    comments: list = field(default_factory=list)   # [(clé Vorbis, valeur)]
    pictures: list = field(default_factory=list)   # [Picture]
    padding: int = 0                               # octets de padding de l'étiquette
    seconds: float | None = None

    @property
    def duration(self):
        """Durée en secondes (exacte avec un en-tête Xing, estimée sinon), None si on ne l'a pas trouvée."""
        return self.seconds

    def values(self, key):
        key = key.upper()
        return [value for name, value in self.comments if name.upper() == key]

    def first(self, key):
        values = self.values(key)
        return values[0] if values else ""

    @property
    def has_front_cover(self):
        return any(p.kind == FRONT_COVER for p in self.pictures)

    # Les deux contrôles propres aux .flac (en-tête que Windows ne lit plus) ne s'appliquent pas ici.
    bloated = False
    heavy_header = False


# --------------------------------------------------------------------------
# Lecture
# --------------------------------------------------------------------------
def syncsafe(data):
    """Entier codé sur 7 bits par octet, comme la taille d'une étiquette."""
    value = 0
    for byte in data:
        value = (value << 7) | (byte & 0x7F)
    return value


def to_syncsafe(value):
    return bytes((value >> shift) & 0x7F for shift in (21, 14, 7, 0))


def _terminator(encoding):
    return b"\x00\x00" if encoding in (1, 2) else b"\x00"


def _decode(encoding, data, order=None):
    """(texte, ordre des octets) : l'ordre lu dans la marque BOM d'un texte UTF-16 vaut pour les suivants."""
    if encoding == 1:
        if data[:2] == b"\xff\xfe":
            order, data = "le", data[2:]
        elif data[:2] == b"\xfe\xff":
            order, data = "be", data[2:]
        return data.decode("utf-16-" + (order or "le"), "replace"), order
    if encoding == 2:
        return data.decode("utf-16-be", "replace"), order
    if encoding == 3:
        return data.decode("utf-8", "replace"), order
    return data.decode("latin-1"), order


def _split(encoding, data):
    """[octets de chaque texte] : les valeurs d'une trame sont séparées par un terminateur, de deux octets alignés en UTF-16."""
    if encoding not in (1, 2):
        return data.split(b"\x00")
    parts, start = [], 0
    for i in range(0, len(data) - 1, 2):
        if data[i] == 0 and data[i + 1] == 0:
            parts.append(data[start:i])
            start = i + 2
    parts.append(data[start:])
    return parts


def _texts(body):
    """[valeurs] d'une trame de texte ; les valeurs vides, dont celle qu'un terminateur final laisse, sont écartées."""
    if not body:
        return []
    order, values = None, []
    for part in _split(body[0], body[1:]):
        text, order = _decode(body[0], part, order)
        values.append(text)
    return [v for v in values if v]


def _take(encoding, data):
    """(texte, reste) : le texte qui précède le premier terminateur - description d'une TXXX ou d'une APIC."""
    stop = _terminator(encoding)
    step = len(stop)
    for i in range(0, len(data) - step + 1, step):
        if data[i:i + step] == stop:
            return _decode(encoding, data[:i])[0], data[i + step:]
    return _decode(encoding, data)[0], b""


def parse_picture(body):
    """Picture d'une trame APIC : codage, type MIME, type d'image, description, image."""
    if len(body) < 4:
        raise Mp3Error("image tronquee")
    encoding = body[0]
    end = body.find(b"\x00", 1)
    if end < 0 or end + 1 >= len(body):
        raise Mp3Error("image tronquee")
    mime = body[1:end].decode("latin-1") or "image/jpeg"
    kind = body[end + 1]
    description, data = _take(encoding, body[end + 2:])
    width, height, depth = image_dimensions(data)
    return Picture(kind, mime, data, description, width, height, depth, 0)


def _frames(data, version):
    """([Frame], octets de padding) d'un corps d'étiquette. Une trame illisible rend l'étiquette entière suspecte : on s'arrête là."""
    frames, position = [], 0
    while position + 10 <= len(data):
        raw_id = data[position:position + 4]
        if raw_id[0] == 0:                          # le padding commence
            break
        if not FRAME_ID_RE.match(raw_id):
            raise Mp3Error(f"etiquette ID3 abimee : trame '{raw_id.decode('latin-1', 'replace')}' invalide")
        size = int.from_bytes(data[position + 4:position + 8], "big") if version == 3 else syncsafe(data[position + 4:position + 8])
        flag1, flag2 = data[position + 8], data[position + 9]
        body = data[position + 10:position + 10 + size]
        if len(body) < size:
            raise Mp3Error(f"trame {raw_id.decode()} deborde de l'etiquette")
        position += 10 + size
        frame = _unwrap(raw_id.decode(), body, version, flag1, flag2)
        if frame is not None:
            frames.append(frame)
    return frames, len(data) - position


def _unwrap(frame_id, body, version, flag1, flag2):
    """Frame sans son emballage, ou None quand elle est chiffrée (illisible) ou obsolète."""
    if version == 3:
        status = (flag1 & 0xE0) >> 1                # 0x80/0x40/0x20 -> 0x40/0x20/0x10
        compressed, encrypted, grouped, unsynchronised, sized = flag2 & 0x80, flag2 & 0x40, flag2 & 0x20, False, False
        skip = (4 if compressed else 0) + (1 if encrypted else 0) + (1 if grouped else 0)
        payload = body[skip:]
    else:
        status = flag1 & 0x70
        compressed, encrypted, grouped, unsynchronised, sized = flag2 & 0x08, flag2 & 0x04, flag2 & 0x40, flag2 & 0x02, flag2 & 0x01
        skip = (1 if grouped else 0) + (1 if encrypted else 0) + (4 if sized else 0)
        payload = body[skip:]
    if encrypted or frame_id in OBSOLETE_IDS:
        return None
    if unsynchronised:
        payload = payload.replace(b"\xff\x00", b"\xff")
    if compressed:
        try:
            payload = zlib.decompress(payload)
        except zlib.error:
            return None
    if frame_id == "IPLS":                          # la liste des personnes d'ID3v2.3 est la TIPL de la 2.4, au même format
        frame_id = "TIPL"
    return Frame(frame_id, payload, status)


def _number_comments(frame_id, body):
    number, totals = NUMBER_FRAMES[frame_id]
    values = _texts(body)
    if not values:
        return []
    count, _, total = values[0].partition("/")
    comments = [(number, count.strip())] if count.strip() else []
    return comments + ([(key, total.strip()) for key in totals] if total.strip() else [])


def _comments(frames, version):
    """([(clé, valeur)], [Picture]) : les trames gérées, sous leurs noms de clé Vorbis."""
    comments, pictures, years, days, original = [], [], None, None, None
    for frame in frames:
        if frame.id == "APIC":
            try:
                pictures.append(parse_picture(frame.body))
            except Mp3Error:
                continue
        elif frame.id in KEYS_BY_FRAME:
            for value in _texts(frame.body):
                if frame.id == "TCON":
                    found = GENRE_REFERENCE_RE.match(value)
                    value = found.group(1) if found else value
                comments.append((KEYS_BY_FRAME[frame.id], value))
        elif frame.id in NUMBER_FRAMES:
            comments += _number_comments(frame.id, frame.body)
        elif frame.id == "TXXX" and frame.body:
            description, rest = _take(frame.body[0], frame.body[1:])
            key = KEYS_BY_DESCRIPTION.get(description.upper(), description)
            comments += [(key, value) for value in _texts(frame.body[:1] + rest)]
        elif frame.id == "UFID":
            owner, _, identifier = frame.body.partition(b"\x00")
            if owner == MB_OWNER and identifier:
                comments.append(("MUSICBRAINZ_TRACKID", identifier.decode("ascii", "replace")))
        elif frame.id == "TYER":
            years = (_texts(frame.body) or [None])[0]
        elif frame.id == "TDAT":
            days = (_texts(frame.body) or [None])[0]
        elif frame.id == "TORY":
            original = (_texts(frame.body) or [None])[0]
    # ID3v2.3 n'a pas de date complète : l'année (TYER) et "JJMM" (TDAT) sont deux trames.
    if years and not any(key == "DATE" for key, _ in comments):
        comments.append(("DATE", years + (f"-{days[2:]}-{days[:2]}" if days and re.fullmatch(r"\d{4}", days) and re.fullmatch(r"\d{4}", years) else "")))
    if original and not any(key == "ORIGINALYEAR" for key, _ in comments):
        comments.append(("ORIGINALYEAR", original))
    return comments, pictures


# Débits (kbit/s) selon [version MPEG][couche] ; l'indice 0 (libre) et 15 (invalide) ne servent pas.
BITRATES = {
    (1, 1): [0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448, 0],
    (1, 2): [0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384, 0],
    (1, 3): [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0],
    (2, 1): [0, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256, 0],
    (2, 2): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0],
}
BITRATES[(2, 3)] = BITRATES[(2, 2)]
SAMPLE_RATES = {1: [44100, 48000, 32000], 2: [22050, 24000, 16000], 3: [11025, 12000, 8000]}   # MPEG 1, 2 et 2.5


def _frame_header(head):
    """(version MPEG, couche, débit en kbit/s, fréquence, padding, mono, CRC) d'un en-tête de trame audio, ou None s'il n'en est pas un."""
    if len(head) < 4 or head[0] != 0xFF or head[1] & 0xE0 != 0xE0:
        return None
    version_bits, layer_bits = (head[1] >> 3) & 3, (head[1] >> 1) & 3
    bitrate_index, rate_index = head[2] >> 4, (head[2] >> 2) & 3
    if version_bits == 1 or layer_bits == 0 or bitrate_index in (0, 15) or rate_index == 3:
        return None
    version, layer = {3: 1, 2: 2, 0: 3}[version_bits], 4 - layer_bits       # 3 = MPEG 1, 2 = MPEG 2, 0 = MPEG 2.5
    bitrate = BITRATES[(1 if version == 1 else 2, layer)][bitrate_index]
    return version, layer, bitrate, SAMPLE_RATES[version][rate_index], (head[2] >> 1) & 1, (head[3] >> 6) == 3, not head[1] & 1


def _samples(version, layer):
    return 384 if layer == 1 else (1152 if version == 1 or layer == 2 else 576)


def _frame_length(version, layer, bitrate, rate, padding):
    if layer == 1:
        return (12 * bitrate * 1000 // rate + padding) * 4
    return (_samples(version, layer) // 8) * bitrate * 1000 // rate + padding


def _duration(f, offset, size):
    """Secondes de son derrière `offset` : le nombre de trames du premier en-tête Xing/VBRI s'il y en a un, sinon la taille sur le débit de la première trame (exacte pour un CBR). None si aucune trame n'est trouvée."""
    f.seek(offset)
    chunk = f.read(SCAN_BYTES)
    for i in range(len(chunk) - 4):
        header = _frame_header(chunk[i:i + 4])
        if header is None:
            continue
        version, layer, bitrate, rate, padding, mono, crc = header
        following = i + _frame_length(version, layer, bitrate, rate, padding)
        if following + 2 <= len(chunk) and not _frame_header(chunk[following:following + 4]):
            continue                                # un faux départ : la trame suivante ne commence pas là
        side_info = (17 if mono else 32) if version == 1 else (9 if mono else 17)
        xing = i + 4 + (2 if crc else 0) + side_info
        if chunk[xing:xing + 4] in (b"Xing", b"Info") and len(chunk) >= xing + 12 and chunk[xing + 7] & 1:
            return int.from_bytes(chunk[xing + 8:xing + 12], "big") * _samples(version, layer) / rate
        if chunk[i + 36:i + 40] == b"VBRI" and len(chunk) >= i + 54:      # l'équivalent de Xing chez Fraunhofer : le compte de trames est 10 octets plus loin
            return int.from_bytes(chunk[i + 50:i + 54], "big") * _samples(version, layer) / rate
        f.seek(max(size - 128, 0))
        end = size - 128 if f.read(3) == b"TAG" else size
        return (end - offset - i) * 8 / (bitrate * 1000)
    return None


def read(path):
    """Metadata d'un .mp3. Le son n'est pas lu, hors la recherche de sa première trame."""
    try:
        with open(path, "rb") as f:
            head = f.read(10)
            version, frames, padding, offset = 0, [], 0, 0
            if head[:3] == b"ID3":
                version = head[3]
                if version not in (3, 4):
                    raise Mp3Error(f"ID3v2.{version} non pris en charge (seuls 2.3 et 2.4)")
                flags, size = head[5], syncsafe(head[6:10])
                data = f.read(size)
                if len(data) < size or len(head) < 10:
                    raise Mp3Error("etiquette ID3 tronquee")
                offset = 10 + size + (10 if version == 4 and flags & 0x10 else 0)
                if version == 3 and flags & 0x80:                # désynchronisation de toute l'étiquette
                    data = data.replace(b"\xff\x00", b"\xff")
                if flags & 0x40:                                  # en-tête étendu : sans intérêt, on saute
                    skip = (int.from_bytes(data[:4], "big") + 4) if version == 3 else syncsafe(data[:4])
                    data = data[skip:]
                frames, padding = _frames(data, version)
            f.seek(0, os.SEEK_END)
            seconds = _duration(f, offset, f.tell())
    except OSError as e:
        raise Mp3Error(f"lecture impossible : {e.strerror or e}") from e
    if not version and seconds is None:
        raise Mp3Error("ce n'est pas un fichier MP3 (ni etiquette ID3, ni trame audio)")
    comments, pictures = _comments(frames, version)
    return Metadata(frames, offset, version, comments, pictures, padding, seconds)


# --------------------------------------------------------------------------
# Écriture
# --------------------------------------------------------------------------
def _encode(values):
    """Octets des valeurs d'une trame de texte, séparées par un terminateur, précédés de leur codage."""
    stop = _terminator(TEXT_ENCODING)
    return bytes([TEXT_ENCODING]) + stop.join(_encode_one(v) for v in values)


def _encode_one(text):
    return b"\xff\xfe" + text.encode("utf-16-le") if TEXT_ENCODING == UTF16 else text.encode("utf-8")


def _text_frame(frame_id, values):
    return Frame(frame_id, _encode(values))


def _number_frame(frame_id, groups):
    number, totals = NUMBER_FRAMES[frame_id]
    values = groups.get(number, (number, []))[1]
    if not values:
        return None
    count, _, total = values[0].partition("/")
    total = next((groups[t][1][0] for t in totals if t in groups), total)
    return _text_frame(frame_id, [f"{count.strip()}/{total.strip()}" if total.strip() else count.strip()])


def build_frames(comments, pictures):
    """[Frame] pour ces tags et ces images : l'inverse de _comments."""
    groups = {}
    for key, value in comments:
        if value != "":
            groups.setdefault(key.upper(), (key, []))[1].append(value)
    frames, done = [], set()
    for upper, (name, values) in groups.items():
        if upper in TEXT_FRAMES:
            frames.append(_text_frame(TEXT_FRAMES[upper], values))
        elif upper == "MUSICBRAINZ_TRACKID":
            frames.append(Frame("UFID", MB_OWNER + b"\x00" + values[0].encode("ascii", "replace")))
        elif upper in FRAME_BY_NUMBER_KEY:
            frame_id = FRAME_BY_NUMBER_KEY[upper]
            if frame_id not in done:
                done.add(frame_id)
                frame = _number_frame(frame_id, groups)
                if frame:
                    frames.append(frame)
        else:
            description = TXXX_DESCRIPTIONS.get(upper, name)
            frames.append(Frame("TXXX", _encode([description]) + _terminator(TEXT_ENCODING) + _encode(values)[1:]))
    for picture in pictures:
        mime, stop = picture.mime.encode("latin-1", "replace"), _terminator(TEXT_ENCODING)
        description = _encode_one(picture.description) if picture.description else b""
        frames.append(Frame("APIC", bytes([TEXT_ENCODING]) + mime + b"\x00" + bytes([picture.kind]) + description + stop + picture.data))
    return frames


def _kept(meta):
    """Les trames qu'on ne gère pas, à recopier telles quelles."""
    return [f for f in meta.frames if f.id not in MANAGED_IDS and not (f.id == "UFID" and f.body.startswith(MB_OWNER + b"\x00"))]


def render(meta, comments, pictures, padding):
    """L'étiquette complète : les trames gérées d'abord, celles qu'on recopie ensuite, puis `padding` octets de zéros."""
    out = []
    for frame in build_frames(comments, pictures) + _kept(meta):
        if len(frame.body) > MAX_TAG:
            raise Mp3Error(f"trame {frame.id} de {len(frame.body)} octets : trop grosse pour ID3")
        out.append(frame.id.encode("ascii") + to_syncsafe(len(frame.body)) + bytes([frame.status, 0]) + frame.body)
    body = b"".join(out) + bytes(padding)
    if len(body) > MAX_TAG:
        raise Mp3Error("etiquette ID3 trop grosse")
    return b"ID3\x04\x00\x00" + to_syncsafe(len(body)) + body


def write(path, meta, comments, pictures):
    """Remplace les tags et les images d'un .mp3. Retourne "sur place" ou "recopie".

    `meta` doit être la lecture du fichier tel qu'il est : c'est elle qui dit où commence le son. Sur place, seule l'étiquette est réécrite, à taille identique - le padding absorbe la différence. Sinon le fichier est recopié à côté avec un padding neuf, sa taille contrôlée, et il ne remplace l'original qu'une fois complet : une coupure en route laisse l'original intact.
    """
    path = Path(path)
    bare = len(render(meta, comments, pictures, 0))
    if bare <= meta.audio_offset:
        header = render(meta, comments, pictures, meta.audio_offset - bare)
        try:
            with open(path, "r+b") as f:
                f.write(header)
        except OSError as e:
            raise Mp3Error(f"ecriture impossible : {e.strerror or e}") from e
        return "sur place"

    header = render(meta, comments, pictures, DEFAULT_PADDING)
    temporary = None
    try:
        size = path.stat().st_size
        with open(path, "rb") as source, tempfile.NamedTemporaryFile(dir=path.parent, prefix=".", suffix=".mp3.tmp", delete=False) as target:
            temporary = Path(target.name)
            target.write(header)
            source.seek(meta.audio_offset)
            shutil.copyfileobj(source, target, 1 << 20)
            target.flush()
            os.fsync(target.fileno())
        if temporary.stat().st_size != len(header) + size - meta.audio_offset:
            raise Mp3Error("copie incomplete : l'original est garde")
        os.replace(temporary, path)
        temporary = None
    except OSError as e:
        raise Mp3Error(f"ecriture impossible : {e.strerror or e}") from e
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return "recopie"
