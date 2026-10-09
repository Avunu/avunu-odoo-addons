# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import SUPERUSER_ID, api


def post_init_hook(env_or_cr, registry=None):
    """Create a default database-only backup job on the odoo_backup storage."""
    env = (
        env_or_cr
        if isinstance(env_or_cr, api.Environment)
        else api.Environment(env_or_cr, SUPERUSER_ID, {})
    )
    storage = env.ref("auto_backup_fs_storage.odoo_backup", raise_if_not_found=False)
    if not storage or env["db.backup"].search_count([("fs_storage_id", "=", storage.id)]):
        return
    env["db.backup"].create(
        {
            "method": "fs_storage",
            "fs_storage_id": storage.id,
            "folder": env.cr.dbname,
            # Attachments live in the object store (fs_attachment), so a
            # database-only dump is the complete backup.
            "backup_format": "dump",
            "days_to_keep": 30,
        }
    )
