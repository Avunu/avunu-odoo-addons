# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import io
import os
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDbBackupFsStorage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.storage = cls.env["fs.storage"].create(
            {
                "name": "Test backups",
                "code": "test_backup_mem",
                "protocol": "memory",
                "directory_path": "/bk",
            }
        )
        cls.backup = cls.env["db.backup"].create(
            {
                "method": "fs_storage",
                "fs_storage_id": cls.storage.id,
                "folder": "mydb",
                "backup_format": "dump",
                "days_to_keep": 2,
            }
        )

    def setUp(self):
        super().setUp()
        # fsspec's memory filesystem is process-global: start and end clean.
        self.addCleanup(self._wipe)
        self._wipe()

    def _wipe(self):
        fs = self.storage.fs
        if fs.exists("mydb"):
            fs.rm("mydb", recursive=True)

    def _dump(self, *args, **kwargs):
        return io.BytesIO(b"PGDMP-fake")

    def test_backup_written(self):
        with patch("odoo.service.db.dump_db", self._dump):
            self.backup.action_backup()
        files = self.storage.fs.ls("mydb", detail=False)
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].endswith(".dump"))
        with self.storage.fs.open(files[0], "rb") as f:
            self.assertEqual(f.read(), b"PGDMP-fake")

    def test_retention(self):
        fs = self.storage.fs
        fs.makedirs("mydb", exist_ok=True)
        now = datetime.now()
        old = self.env["db.backup"].filename(now - timedelta(days=5), "dump")
        recent = self.env["db.backup"].filename(now - timedelta(days=1), "dump")
        for name in (old, recent, "notes.txt"):
            fs.pipe_file(os.path.join("mydb", name), b"x")
        self.backup.cleanup()
        names = {os.path.basename(p) for p in fs.ls("mydb", detail=False)}
        self.assertNotIn(old, names)
        self.assertIn(recent, names)
        self.assertIn("notes.txt", names)

    def test_directory_path_env(self):
        self.storage.eval_options_from_env = True
        self.storage.directory_path = "$TEST_BK_BUCKET/$TEST_BK_PREFIX"
        with patch.dict(os.environ, {"TEST_BK_BUCKET": "b", "TEST_BK_PREFIX": "p"}):
            self.assertEqual(self.storage.get_directory_path(), "b/p")

    def test_name(self):
        self.assertEqual(self.backup.name, "test_backup_mem://mydb")
