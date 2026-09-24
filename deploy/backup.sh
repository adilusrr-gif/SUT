#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
set -a; source .env; set +a
stamp=$(date +%Y%m%d_%H%M%S)
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "backups/sut_${stamp}.sql.gz"
echo "backup: backups/sut_${stamp}.sql.gz"
