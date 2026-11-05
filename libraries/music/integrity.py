"""Contrôle d'un .flac ou d'un .mp3 sans rien décoder : ce que le fichier dit de lui-même, et ce que sa queue en dit.

Un fichier audio abîmé se lit presque toujours jusqu'au bout : un lecteur saute la trame qu'il ne comprend pas et passe à la suivante. Le défaut ne se voit qu'à la comparaison avec ce que le fichier annonce.

FLAC : STREAMINFO annonce le nombre exact d'échantillons, et chaque trame se termine par un CRC-16 qui couvre toute la trame. La dernière trame doit donc être complète - son CRC-16 est bon - et s'arrêter à l'échantillon annoncé. Cela voit un fichier coupé, où que la coupure tombe (au milieu d'une trame, ou juste entre deux), en ne lisant que la queue du fichier. Une trame abîmée plus tôt, elle, ne se voit qu'en décodant tout (voir scripts/Music/Verify_Flac.py --full).

MP3 : aucune somme de contrôle globale, mais une chaîne de trames dont chaque en-tête donne la longueur - la suivante commence juste derrière. Le fichier est suivi d'un bout à l'autre : une trame coupée, un trou, du bruit au milieu ou à la fin se voient. Le nombre de trames que l'en-tête Xing/Info annonce est comparé à celui qu'on a compté. Un octet qui change dans le son, lui, ne laisse aucune trace : aucun format MP3 ne permet de le voir, même en décodant.

Tout est en lecture seule, sans outil externe.
"""

import os

from . import flac, mp3
from .tags import AudioError

FLAC_TAIL = 256 * 1024         # où chercher la dernière trame d'un .flac : de quoi couvrir quelques trames de stéréo 16 bits
FLAC_TAIL_CANDIDATES = 8       # combien de départs de trame essayer en remontant : un début qui n'en est pas un (CRC-8 chanceux) ne doit pas faire déclarer coupé un fichier sain
MP3_RESYNC = 1 << 20           # jusqu'où chercher le son qui reprend derrière un passage illisible
MP3_BUFFER = 1 << 20           # lecture par gros blocs : un partage réseau répond mal aux petites lectures
MP3_FOOTERS = (b"TAG", b"APETAGEX", b"LYRICSBEGIN")   # ce qui peut légitimement suivre la dernière trame : ID3v1, APEv2, Lyrics3
ID3V1_SIZE = 128
FLAC_BLOCK_SIZES = {1: 192, 2: 576, 3: 1152, 4: 2304, 5: 4608, 8: 256, 9: 512, 10: 1024, 11: 2048, 12: 4096, 13: 8192, 14: 16384, 15: 32768}


def _table(width, poly):
    mask, top = (1 << width) - 1, 1 << (width - 1)
    table = []
    for byte in range(256):
        crc = byte << (width - 8)
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & mask if crc & top else (crc << 1) & mask
        table.append(crc)
    return table


CRC8_TABLE, CRC16_TABLE = _table(8, 0x07), _table(16, 0x8005)


def crc8(data):
    """CRC-8 (polynôme 0x07) de l'en-tête d'une trame FLAC."""
    crc = 0
    for byte in data:
        crc = CRC8_TABLE[crc ^ byte]
    return crc


def crc16(data):
    """CRC-16 (polynôme 0x8005, départ 0) d'une trame FLAC : vaut 0 sur une trame entière, CRC compris."""
    crc = 0
    for byte in data:
        crc = ((crc << 8) & 0xFFFF) ^ CRC16_TABLE[(crc >> 8) ^ byte]
    return crc


# --------------------------------------------------------------------------
# FLAC
# --------------------------------------------------------------------------
def streaminfo(meta):
    """(taille de bloc, taille de trame maximale, canaux, bits par échantillon, empreinte MD5 en hexa) lus dans STREAMINFO ; l'empreinte est None quand l'encodeur ne l'a pas calculée (seize octets nuls)."""
    body = meta.blocks[0][1]
    if len(body) < 34:
        raise flac.FlacError("STREAMINFO tronqué")
    block = int.from_bytes(body[2:4], "big")
    max_frame = int.from_bytes(body[7:10], "big")
    channels = ((body[12] >> 1) & 7) + 1
    bits = (((body[12] & 1) << 4) | (body[13] >> 4)) + 1
    digest = body[18:34]
    return block, max_frame, channels, bits, digest.hex() if any(digest) else None


def _utf8_number(data, i):
    """(valeur, longueur) du numéro codé en UTF-8 étendu (jusqu'à 7 octets) qui suit l'en-tête d'une trame FLAC, ou None."""
    first = data[i]
    if first < 0x80:
        return first, 1
    if first == 0xFF:
        return None
    length = 0
    while length < 7 and first & (0x80 >> length):
        length += 1
    if length < 2 or length > 7:
        return None
    value = first & (0x7F >> length)
    for byte in data[i + 1:i + length]:
        if byte & 0xC0 != 0x80:
            return None
        value = (value << 6) | (byte & 0x3F)
    return (value, length) if len(data[i:i + length]) == length else None


def frame_header(data, i, stream_block):
    """(premier échantillon, taille de bloc) de la trame FLAC qui commence en `data[i]`, ou None si ce n'est pas un en-tête valide (code de synchro, champs réservés, CRC-8)."""
    try:
        if data[i] != 0xFF or data[i + 1] not in (0xF8, 0xF9):
            return None
        block_code, rate_code, channel_code, size_code = data[i + 2] >> 4, data[i + 2] & 15, data[i + 3] >> 4, (data[i + 3] >> 1) & 7
        if block_code == 0 or rate_code == 15 or channel_code > 10 or size_code == 3 or data[i + 3] & 1:
            return None
        number = _utf8_number(data, i + 4)
        if number is None:
            return None
        value, length = number
        end = i + 4 + length
        if block_code == 6:
            block, end = data[end] + 1, end + 1
        elif block_code == 7:
            block, end = int.from_bytes(data[end:end + 2], "big") + 1, end + 2
        else:
            block = FLAC_BLOCK_SIZES[block_code]
        end += 1 if rate_code == 12 else 2 if rate_code in (13, 14) else 0
        if crc8(data[i:end]) != data[end]:
            return None
    except IndexError:
        return None
    # Un flux à taille de bloc fixe numérote ses trames ; un flux à taille variable, ses échantillons.
    return (value * stream_block if data[i + 1] == 0xF8 else value), block


def _read_tail(path, size):
    """(position du premier octet lu, octets lus) : la queue du fichier."""
    start = max(size - FLAC_TAIL, 0)
    with open(path, "rb") as f:
        f.seek(start)
        return start, f.read()


def _last_frame(tail, stream_block):
    """(premier échantillon, taille de bloc) de la trame complète qui termine `tail`, ou None : on remonte les départs de trame plausibles, le premier dont le CRC-16 couvre exactement jusqu'au bout est la dernière trame."""
    candidates = [i for i in range(len(tail) - 1, -1, -1) if tail[i] == 0xFF and tail[i + 1:i + 2] in (b"\xf8", b"\xf9")]
    tried = 0
    for i in candidates:
        header = frame_header(tail, i, stream_block)
        if header is None:
            continue
        tried += 1
        if crc16(tail[i:]) == 0:
            return header
        if tried >= FLAC_TAIL_CANDIDATES:
            break
    return None


def _duration(samples, rate):
    """Durée lisible d'un nombre d'échantillons : « 3 min 12 s » ou « 4,2 s »."""
    seconds = samples / rate if rate else 0
    return f"{int(seconds) // 60} min {int(seconds) % 60:02d} s" if seconds >= 60 else f"{seconds:.1f} s".replace(".", ",")


def flac_defect(path):
    """Ce qui cloche dans un .flac d'après son en-tête et sa queue, ou "" s'il est sain."""
    try:
        meta = flac.read(path)
        block, max_frame, _, _, _ = streaminfo(meta)
        if not meta.sample_rate:
            return "STREAMINFO invalide : fréquence d'échantillonnage nulle"
        size = os.path.getsize(path)
        if size <= meta.audio_offset:
            return "aucune trame audio derrière l'en-tête : fichier coupé après ses métadonnées"
        start, tail = _read_tail(path, size)
    except AudioError as exc:
        return str(exc)
    except OSError as exc:
        return f"lecture impossible : {exc.strerror or exc}"
    if start < meta.audio_offset:                    # un fichier plus court que la fenêtre : l'en-tête ne doit pas passer pour des trames
        tail = tail[meta.audio_offset - start:]
    last = _last_frame(tail, block)
    if last is None:
        return "la dernière trame audio est incomplète ou suivie d'octets étrangers : fichier coupé ?"
    first, length = last
    if meta.total_samples and first + length != meta.total_samples:
        gap = meta.total_samples - (first + length)
        return (f"le son s'arrête à l'échantillon {first + length} sur {meta.total_samples} annoncés : "
                + (f"il manque {_duration(gap, meta.sample_rate)}" if gap > 0 else f"{_duration(-gap, meta.sample_rate)} de trop"))
    return ""


# --------------------------------------------------------------------------
# MP3
# --------------------------------------------------------------------------
def _clock(seconds):
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def _header_at(f, position):
    """(en-tête décodé, longueur de la trame) à `position`, ou None si ce n'est pas un début de trame."""
    f.seek(position)
    header = mp3._frame_header(f.read(4))
    if header is None:
        return None
    version, layer, bitrate, rate, padding, _, _ = header
    return header, mp3._frame_length(version, layer, bitrate, rate, padding)


def _chained(f, position, end):
    """Vrai si une trame commence à `position` et qu'une deuxième (ou la fin des données) suit juste derrière : un seul en-tête plausible ne prouve rien, deux à la suite si."""
    found = _header_at(f, position)
    if found is None:
        return False
    following = position + found[1]
    return following == end or _header_at(f, following) is not None


def _resync(f, position, end):
    """Position du premier début de trame sûr (deux trames à la suite) à partir de `position`, ou None dans les MP3_RESYNC octets suivants."""
    f.seek(position)
    chunk = f.read(min(MP3_RESYNC, end - position))
    i = chunk.find(b"\xff")
    while i != -1:
        if _chained(f, position + i, end):
            return position + i
        i = chunk.find(b"\xff", i + 1)
    return None


def _declared_frames(f, position, header):
    """Nombre de trames annoncé par l'en-tête Xing/Info ou VBRI de la première trame, ou None s'il n'y en a pas."""
    version, layer, _, _, _, mono, crc = header
    f.seek(position)
    data = f.read(200)
    side_info = (17 if mono else 32) if version == 1 else (9 if mono else 17)
    xing = 4 + (2 if crc else 0) + side_info
    if data[xing:xing + 4] in (b"Xing", b"Info") and len(data) >= xing + 12 and data[xing + 7] & 1:
        return int.from_bytes(data[xing + 8:xing + 12], "big")
    if data[36:40] == b"VBRI" and len(data) >= 54:
        return int.from_bytes(data[50:54], "big")
    return None


def _audio_end(f, size):
    """Où finissent les trames : avant l'étiquette ID3v1 de fin de fichier, s'il y en a une."""
    if size >= ID3V1_SIZE:
        f.seek(size - ID3V1_SIZE)
        if f.read(3) == b"TAG":
            return size - ID3V1_SIZE
    return size


def _first_frame(f, start, end):
    """Position de la première trame, cherchée dans les SCAN_BYTES octets derrière l'étiquette ID3v2, ou None."""
    f.seek(start)
    chunk = f.read(min(mp3.SCAN_BYTES, end - start))
    i = chunk.find(b"\xff")
    while i != -1:
        if _chained(f, start + i, end):
            return start + i
        i = chunk.find(b"\xff", i + 1)
    return None


def _tail_is_harmless(f, position, end):
    """Vrai si ce qui reste derrière la dernière trame n'est que du remplissage nul ou une étiquette de fin connue."""
    f.seek(position)
    rest = f.read(end - position)
    return not rest.strip(b"\x00") or rest.startswith(MP3_FOOTERS)


def mp3_defect(path):
    """Ce qui cloche dans un .mp3 d'après sa chaîne de trames, ou "" s'il est sain."""
    try:
        meta = mp3.read(path)
        size = os.path.getsize(path)
        with open(path, "rb", buffering=MP3_BUFFER) as f:
            end = _audio_end(f, size)
            position = _first_frame(f, meta.audio_offset, end)
            if position is None:
                return "aucune trame audio derrière l'étiquette : fichier coupé après ses métadonnées ?"
            return _walk(f, position, end)
    except AudioError as exc:
        return str(exc)
    except OSError as exc:
        return f"lecture impossible : {exc.strerror or exc}"


def _walk(f, position, end):
    """Suit la chaîne de trames de `position` à `end` et rend le premier défaut, ou "" ."""
    first = position
    frames, seconds, declared = 0, 0.0, None
    while position < end:
        found = _header_at(f, position)
        if found is None:
            if _tail_is_harmless(f, position, end):
                break
            where = f"à l'octet {position} (après {frames} trames, {_clock(seconds)})"
            again = _resync(f, position, end)
            return (f"synchro perdue {where}, le son reprend {again - position} octets plus loin" if again is not None
                    else f"synchro perdue {where} et ne revient pas : fichier abîmé ou octets étrangers jusqu'à la fin")
        header, length = found
        if frames == 0:
            declared = _declared_frames(f, position, header)
        if position + length > end:
            return f"dernière trame incomplète à l'octet {position} (après {frames} trames, {_clock(seconds)}) : il manque {position + length - end} octets, fichier coupé"
        frames += 1
        seconds += mp3._samples(header[0], header[1]) / header[3]
        position += length
    if declared is not None and frames not in (declared, declared + 1):     # l'annonce compte les trames hors la trame Xing elle-même
        return f"l'en-tête annonce {declared} trames, le fichier en contient {frames} : fichier coupé ou allongé après coup"
    return ""


def flac_digest(path):
    """(bits par échantillon, empreinte MD5) à comparer au son décodé d'un .flac, ou None quand la comparaison ne serait pas fiable.

    L'empreinte de STREAMINFO porte sur les échantillons entrelacés en petit-boutiste, sur autant d'octets que le fichier a de bits. ffmpeg sait les rendre à l'identique en 16 et 24 bits, mono ou stéréo ; au-delà (multicanal, 20 bits, 32 bits) l'ordre ou la largeur des échantillons pourrait différer sans que le fichier soit abîmé, et le contrôle s'en tient aux CRC. Aucune empreinte non plus quand l'encodeur ne l'a pas calculée.
    """
    try:
        _, _, channels, bits, digest = streaminfo(flac.read(path))
    except AudioError:
        return None
    return (bits, digest) if digest and bits in (16, 24) and channels <= 2 else None

