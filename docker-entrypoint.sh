#!/bin/sh
set -e
# Bind mounts are often root-owned on first run; appuser must be able to write logs/data.
for d in /app/logs /app/data; do
  if [ -d "$d" ]; then
    chown -R appuser:appuser "$d" 2>/dev/null || true
  fi
done
exec gosu appuser "$@"
