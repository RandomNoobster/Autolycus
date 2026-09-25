# Shared helpers for the ops scripts. Source after cd-ing into the repo.

compose() {
  docker compose --profile prod "$@"
}

# Serialise update.sh and heal.sh so the watchdog never recreates containers in
# the middle of a deploy. Lives in /tmp so manual (non-root) runs share it too.
OPS_LOCK_FILE="/tmp/autolycus-ops.lock"

ops_lock() {
  touch "$OPS_LOCK_FILE" 2>/dev/null || true
  exec 9<"$OPS_LOCK_FILE"
  flock "$@" 9
}

# Recreate every service Docker reports as unhealthy. Restart policies only
# react to exits, so an unhealthy container (including one whose process died
# without Docker noticing) otherwise stays down until something recreates it.
recreate_unhealthy() {
  local svc
  for svc in $(compose ps --format '{{.Service}} {{.Health}}' | awk '$2 == "unhealthy" { print $1 }'); do
    echo "Service ${svc} is unhealthy; recreating"
    compose up -d --no-deps --force-recreate "$svc"
  done
}
