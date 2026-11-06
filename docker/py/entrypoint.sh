#!/bin/sh
# Shortcuts so attendees can type `docker compose run --rm app check`.
set -e
case "$1" in
  check)    shift; exec python -m tools.check "$@" ;;
  smoke)    shift; exec python -m pytest -q tests "$@" ;;
  mcp-http)
    export WATCHFILES_FORCE_POLLING=1
    # Polling reloader: inotify events don't cross the Windows/WSL file
    # boundary or some Docker Desktop mounts, so poll instead.
    exec watchfiles --filter python --sigint-timeout 2 \
      "python -m edgar_mcp --http" /workspace/edgar_mcp ;;
  *) exec "$@" ;;
esac
