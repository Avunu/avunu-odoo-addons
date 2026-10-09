# Auto Backup - FS Storage

Adds an **FS Storage** method to OCA's `auto_backup`: scheduled database dumps are written to any `fs.storage` (S3 and other fsspec protocols), with the same retention (`days_to_keep`) as the built-in local and SFTP methods.

## Credentials

Installing the module creates an `odoo_backup` storage (`noupdate`) that never stores secrets: its options are `$VAR` references resolved from the server's environment (`eval_options_from_env`):

| Variable | Meaning |
| --- | --- |
| `BACKUPS_URL` | S3 endpoint |
| `BACKUPS_ACCESS_KEY`, `BACKUPS_SECRET_KEY` | Credentials |
| `BACKUPS_BUCKET` | Bucket |
| `BACKUPS_PREFIX` | Optional prefix |

With odoo-nix these come from an agenix-encrypted env-file (see its "Backups & restore" docs). The module also expands `$VARs` in `directory_path`, which `fs_storage` itself does not.

A default job (`dump` format, 30 days) is created on install. Use `dump`: if attachments live in object storage (`fs_attachment`), the filestore is not in the database dump anyway.

## Neutralization

`data/neutralize.sql` switches fs-storage backup jobs to `local` in a neutralized copy, so a restored development database cannot push to or prune production backups.

## Tests

```sh
python odoo/odoo-bin -c odoo.conf -d <testdb> -i auto_backup_fs_storage \
  --test-enable --test-tags /auto_backup_fs_storage --stop-after-init
```
