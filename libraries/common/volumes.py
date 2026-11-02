"""Sur quel genre de volume vit un fichier : un disque local, ou un partage réseau (NAS).

La différence compte pour les lectures : un disque local répond ou tombe en panne tout de suite, un partage réseau peut rester suspendu des minutes (NAS qui se réveille, réseau qui lâche) sans jamais rendre d'erreur. Savoir où l'on lit permet de ne mettre un délai qu'aux lectures qui en ont besoin.

Réponse "disque local" en cas de doute : un système qu'on ne sait pas interroger se comporte comme avant.
"""

import functools
import os
import re

# Systèmes de fichiers réseau, tels que les nomme /proc/mounts.
NETWORK_FSTYPES = {"nfs", "nfs4", "cifs", "smb", "smb3", "smbfs", "afs", "ceph", "glusterfs", "9p", "davfs", "fuse.sshfs", "fuse.rclone", "fuse.glusterfs"}
DRIVE_REMOTE = 4          # GetDriveTypeW : lecteur réseau
MOUNTS = "/proc/self/mounts"


def is_unc(path):
    r"""Vrai pour un chemin réseau Windows : \\serveur\partage, ou \\?\UNC\serveur\partage."""
    text = str(path)
    if text.upper().startswith("\\\\?\\UNC\\"):
        return True
    return text.startswith("\\\\") and not text.startswith(("\\\\?\\", "\\\\.\\"))


def parse_mounts(text):
    """[(point de montage, système de fichiers)] d'après le contenu de /proc/mounts. Les espaces des points de montage y sont écrits en octal (\\040)."""
    mounts = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 3:
            point = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), fields[1])
            mounts.append((point, fields[2]))
    return mounts


def filesystem_of(path, mounts):
    """Système de fichiers qui porte `path` : celui du point de montage le plus profond qui le contient, ou None."""
    best = None
    for point, fstype in mounts:
        inside = point == "/" or path == point or path.startswith(point.rstrip("/") + "/")
        if inside and (best is None or len(point) >= len(best[0])):
            best = (point, fstype)
    return best[1] if best else None


def is_network_filesystem(fstype):
    return bool(fstype) and (fstype in NETWORK_FSTYPES or fstype.startswith(("nfs", "cifs", "smb")))


def _windows_drive_type(root):
    import ctypes
    return ctypes.windll.kernel32.GetDriveTypeW(root)


@functools.lru_cache(maxsize=512)
def _is_network_folder(folder):
    try:
        if os.name == "nt":
            if is_unc(folder):
                return True
            drive = os.path.splitdrive(folder)[0]
            return bool(drive) and _windows_drive_type(drive + "\\") == DRIVE_REMOTE
        with open(MOUNTS, encoding="utf-8", errors="replace") as f:
            mounts = parse_mounts(f.read())
        return is_network_filesystem(filesystem_of(os.path.realpath(folder), mounts))
    except (OSError, AttributeError, ValueError):       # pas de /proc (macOS...), pas de ctypes.windll : on ne sait pas
        return False


def is_network_path(path):
    """Vrai quand `path` est sur un partage réseau (chemin UNC, lecteur réseau mappé, montage NFS ou SMB). Faux pour un disque local, et en cas de doute."""
    return _is_network_folder(os.path.dirname(os.path.abspath(str(path))))
