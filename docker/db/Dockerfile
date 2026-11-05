# Postgres 16 + pgvector with the workshop dataset. The dump is restored into a
# fresh data directory on first start (docker-entrypoint-initdb.d), so no network
# is ever needed. Rebuild with: scripts/fetch/run_all.sh, then docker compose build db.
FROM pgvector/pgvector:0.8.1-pg16

ENV POSTGRES_DB=edgar \
    POSTGRES_USER=postgres \
    POSTGRES_PASSWORD=postgres

COPY docker/db/edgar.dump /opt/edgar/edgar.dump
COPY docker/db/initdb/ /docker-entrypoint-initdb.d/
