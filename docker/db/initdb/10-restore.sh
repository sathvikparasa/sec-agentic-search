#!/bin/bash
# Restore the workshop dataset on first start. GRANTs to mcp_reader come from the dump.
set -euo pipefail
echo "edgar: restoring dataset..."
start=$(date +%s)
pg_restore --no-owner --exit-on-error -j 4 -U "$POSTGRES_USER" -d "$POSTGRES_DB" /opt/edgar/edgar.dump
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO mcp_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO mcp_reader;
ANALYZE;
SQL
echo "edgar: restore done in $(( $(date +%s) - start ))s"
