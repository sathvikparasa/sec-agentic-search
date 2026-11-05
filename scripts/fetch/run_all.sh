#!/usr/bin/env bash
# Instructor-only: rebuild the dataset from EDGAR and write docker/db/edgar.dump.
#   export SEC_USER_AGENT="Your Name you@example.edu"   # for the fetch stage
#   export VOYAGE_API_KEY=...                            # for the embed_chunks stage (Atlas model API key)
#   scripts/fetch/run_all.sh            # all stages
#   scripts/fetch/run_all.sh extract    # from a given stage onward
# Raw responses are cached in data/raw, so reruns don't hit the SEC again.
set -euo pipefail
cd "$(dirname "$0")/../.."
IMAGE=${BUILD_IMAGE:-edgar-py:dev}
STAGES=(fetch facts extract chunk embed_chunks load dump report)
START=${1:-fetch}

docker network create edgar-build >/dev/null 2>&1 || true
run() {  # run a python module inside the app image, with the repo mounted
  docker run --rm --network edgar-build -u "$(id -u):$(id -g)" -e HOME=/tmp -e SEC_USER_AGENT -e VOYAGE_API_KEY \
    -e BUILD_DSN=postgresql://postgres:postgres@edgar-build-db:5432/edgar \
    -v "$PWD":/workspace -w /workspace "$IMAGE" python -m "$@"
}
start_db() {
  docker rm -f edgar-build-db >/dev/null 2>&1 || true
  docker run -d --name edgar-build-db --network edgar-build -e POSTGRES_PASSWORD=postgres \
    -e POSTGRES_DB=edgar pgvector/pgvector:0.8.1-pg16 >/dev/null
  until docker exec edgar-build-db pg_isready -h 127.0.0.1 -U postgres >/dev/null 2>&1; do sleep 1; done
}

go=false
for s in "${STAGES[@]}"; do
  [[ $s == "$START" ]] && go=true
  $go || continue
  echo "=== $s"
  case $s in
    load)   start_db; run scripts.fetch.load ;;
    dump)   docker exec edgar-build-db pg_dump -U postgres -d edgar -Fc --no-owner -Z 6 > docker/db/edgar.dump
            ls -lh docker/db/edgar.dump ;;
    report) run scripts.fetch.report ;;
    fetch)  : "${SEC_USER_AGENT:?SEC_USER_AGENT must be set, e.g. Your Name you@example.edu}"; run scripts.fetch.fetch ;;
    embed_chunks) : "${VOYAGE_API_KEY:?VOYAGE_API_KEY must be set (Atlas model API key)}"; run scripts.fetch.embed_chunks ;;
    *)      run "scripts.fetch.$s" ;;
  esac
done
