-- a restored copy must never push backups to (or prune) production storage
UPDATE db_backup
   SET method = 'local',
       fs_storage_id = NULL
 WHERE method = 'fs_storage';
