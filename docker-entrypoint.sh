#!/bin/sh
set -e
# Ensure bind mount targets exist and are writable by appuser (UID 1000).
# chown can fail on rootless Docker, NFS root_squash, etc.; then widen perms.
mkdir -p /app/logs /app/data

if chown -R appuser:appuser /app/logs /app/data; then
  :
else
  echo "docker-entrypoint: chown failed; applying world-writable fallback on /app/logs and /app/data" >&2
  chmod -R a+rwx /app/logs /app/data || true
fi

exec gosu appuser "$@"
