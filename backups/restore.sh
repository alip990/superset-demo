#!/bin/bash
# Runs once on first start of the backup-db container (empty volume).
# Restores the pg_dumpall cluster dump, skipping the `postgres` role lines:
# the role already exists, and the dump's ALTER ROLE would reset its password
# to the original (unknown) one.
set -euo pipefail
grep -vE '^(CREATE|ALTER) ROLE postgres[ ;]' /backups/1may-backup.sql \
  | psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d postgres
