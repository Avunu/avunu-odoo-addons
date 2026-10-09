# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "Auto Backup - FS Storage",
    "summary": "Push scheduled database backups to any fs.storage (S3, ...), "
    "with credentials read from environment variables.",
    "version": "18.0.1.0.0",
    "category": "Technical",
    "author": "Avunu LLC",
    "website": "https://avu.nu",
    "license": "AGPL-3",
    "depends": [
        "auto_backup",  # db.backup model, cron and retention logic being extended
        "fs_storage",  # fs.storage records: S3/SFTP/... via fsspec
    ],
    "data": [
        "data/fs_storage.xml",
        "views/db_backup_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
}
