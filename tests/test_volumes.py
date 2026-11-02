"""libraries/common/volumes.py : disque local ou partage réseau, et le délai qu'on en déduit pour les lectures."""

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libraries.common import tools, volumes

MOUNTS = """\
/dev/md0 / ext4 rw,relatime 0 0
tmpfs /run tmpfs rw 0 0
/dev/md2 /volume1 btrfs rw 0 0
192.168.1.10:/export/films /mnt/films nfs4 rw 0 0
//asgard/musique /mnt/ma\\040musique cifs rw 0 0
/dev/sdb1 /mnt/films/local ext4 rw 0 0
"""


class TestChemins(unittest.TestCase):
    def test_chemin_unc(self):
        for chemin in ("\\\\Asgard\\films\\a.mkv", "\\\\?\\UNC\\Asgard\\films\\a.mkv"):
            with self.subTest(chemin=chemin):
                self.assertTrue(volumes.is_unc(chemin))

    def test_chemin_local_n_est_pas_unc(self):
        for chemin in ("D:\\Films\\a.mkv", "\\\\?\\D:\\Films\\a.mkv", "/volume1/films/a.mkv", "a.mkv"):
            with self.subTest(chemin=chemin):
                self.assertFalse(volumes.is_unc(chemin))


class TestMontages(unittest.TestCase):
    def setUp(self):
        self.montages = volumes.parse_mounts(MOUNTS)

    def test_espace_ecrit_en_octal(self):
        self.assertIn(("/mnt/ma musique", "cifs"), self.montages)

    def test_le_montage_le_plus_profond_l_emporte(self):
        self.assertEqual(volumes.filesystem_of("/mnt/films/a.mkv", self.montages), "nfs4")
        self.assertEqual(volumes.filesystem_of("/mnt/films/local/a.mkv", self.montages), "ext4")
        self.assertEqual(volumes.filesystem_of("/volume1/films/a.mkv", self.montages), "btrfs")
        self.assertEqual(volumes.filesystem_of("/home/moi/a.mkv", self.montages), "ext4")

    def test_un_dossier_au_nom_voisin_n_est_pas_dans_le_montage(self):
        self.assertEqual(volumes.filesystem_of("/mnt/films2/a.mkv", self.montages), "ext4")

    def test_systemes_de_fichiers_reseau(self):
        for fstype in ("nfs", "nfs4", "cifs", "smb3", "fuse.sshfs"):
            with self.subTest(fstype=fstype):
                self.assertTrue(volumes.is_network_filesystem(fstype))
        for fstype in ("ext4", "btrfs", "ntfs", "tmpfs", "", None):
            with self.subTest(fstype=fstype):
                self.assertFalse(volumes.is_network_filesystem(fstype))


class TestDetection(unittest.TestCase):
    def setUp(self):
        volumes._is_network_folder.cache_clear()
        self.addCleanup(volumes._is_network_folder.cache_clear)

    def test_windows_unc(self):
        with mock.patch.object(volumes.os, "name", "nt"):
            self.assertTrue(volumes._is_network_folder("\\\\Asgard\\films"))

    def test_windows_lecteur_mappe_ou_local(self):
        with mock.patch.object(volumes.os, "name", "nt"), mock.patch.object(volumes.os.path, "splitdrive", lambda p: (p[:2], p[2:])), \
                mock.patch.object(volumes, "_windows_drive_type", side_effect=lambda root: volumes.DRIVE_REMOTE if root == "Z:\\" else 3):
            self.assertTrue(volumes._is_network_folder("Z:\\Films"))
            self.assertFalse(volumes._is_network_folder("D:\\Films"))

    def test_linux_d_apres_les_montages(self):
        ouvrir = mock.mock_open(read_data=MOUNTS)
        with mock.patch.object(volumes.os, "name", "posix"), mock.patch("builtins.open", ouvrir), \
                mock.patch.object(volumes.os.path, "realpath", lambda p: p):
            self.assertTrue(volumes._is_network_folder("/mnt/films"))
            self.assertFalse(volumes._is_network_folder("/volume1/films"))

    def test_on_ne_sait_pas_alors_c_est_local(self):
        with mock.patch.object(volumes.os, "name", "posix"), mock.patch("builtins.open", side_effect=FileNotFoundError):
            self.assertFalse(volumes._is_network_folder("/mnt/films"))

    def test_la_vraie_interrogation_ne_leve_rien(self):
        self.assertIsInstance(volumes.is_network_path(Path(__file__)), bool)


class TestDelaiDeLecture(unittest.TestCase):
    def test_partage_reseau_delai_disque_local_aucun(self):
        with mock.patch.object(tools.volumes, "is_network_path", side_effect=lambda p: str(p).startswith("\\\\")):
            self.assertEqual(tools.read_timeout("\\\\Asgard\\films\\a.mkv"), tools.READ_TIMEOUT)
            self.assertIsNone(tools.read_timeout("D:\\Films\\a.mkv"))

    def test_outil_suspendu_interrompu_par_run_tool(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            tools.run_tool([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5)


if __name__ == "__main__":
    unittest.main()
