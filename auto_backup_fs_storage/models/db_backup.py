# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import os
import shutil
from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.service import db


class DbBackup(models.Model):
    _inherit = "db.backup"

    method = fields.Selection(
        selection_add=[("fs_storage", "FS Storage (S3, ...)")],
        ondelete={"fs_storage": "set default"},
    )
    fs_storage_id = fields.Many2one(
        "fs.storage",
        string="Storage",
        help="Backups are written under the storage's directory path, in "
        "the sub-folder given by 'Backup Directory'.",
    )

    @api.depends("fs_storage_id")
    def _compute_name(self):
        super()._compute_name()
        for rec in self.filtered(lambda r: r.method == "fs_storage"):
            code = rec.fs_storage_id.code or "?"
            rec.name = f"{code}://{rec.folder}"

    def _fs_backup_dir(self):
        """Folder inside the storage, without a leading slash."""
        self.ensure_one()
        return self.folder.strip("/")

    def action_backup(self):
        fs_recs = self.filtered(lambda r: r.method == "fs_storage")
        successful = self.browse()
        for rec in fs_recs:
            filename = self.filename(datetime.now(), ext=rec.backup_format)
            ok = False
            with rec.backup_log():
                fs = rec.fs_storage_id.fs
                folder = rec._fs_backup_dir()
                fs.makedirs(folder, exist_ok=True)
                cached = db.dump_db(
                    self.env.cr.dbname, None, backup_format=rec.backup_format
                )
                with cached, fs.open(os.path.join(folder, filename), "wb") as dest:
                    shutil.copyfileobj(cached, dest)
                ok = True
            if ok:
                successful |= rec
        successful.cleanup()
        return super(DbBackup, self - fs_recs).action_backup()

    def cleanup(self):
        now = datetime.now()
        fs_recs = self.filtered(lambda r: r.method == "fs_storage" and r.days_to_keep)
        for rec in fs_recs:
            with rec.cleanup_log():
                fmt = rec.backup_format
                suffix = "dump.zip" if fmt == "zip" else fmt
                oldest = self.filename(now - timedelta(days=rec.days_to_keep), fmt)
                fs = rec.fs_storage_id.fs
                folder = rec._fs_backup_dir()
                if not fs.exists(folder):
                    continue
                for name in fs.ls(folder, detail=False):
                    base = os.path.basename(name)
                    if base.endswith(f".{suffix}") and base < oldest:
                        fs.rm_file(os.path.join(folder, base))
        return super(DbBackup, self - fs_recs).cleanup()
