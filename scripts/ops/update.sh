#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_DIR"

# shellcheck source=scripts/ops/common.sh
. "$REPO_DIR/scripts/ops/common.sh"

# Wait for a running heal.sh to finish, then keep it out until we're done.
ops_lock

# Prefer per-command safe.directory so root-run systemd updates work even when
# /opt/autolycus is owned by a non-root user (git "dubious ownership").
git_safe() {
  git -c "safe.directory=$REPO_DIR" "$@"
}

# Deploy host: discard local dirt (e.g. chmod +x) and sync to remote.
# Do not use this pattern on a machine with work you care about keeping.
deploy_sha=""
deploy_branch=""
deploy_synced_at=""
if [ -d .git ]; then
  git_safe fetch --prune origin
  deploy_branch="$(git_safe rev-parse --abbrev-ref HEAD)"
  git_safe reset --hard "origin/${deploy_branch}"
  git_safe clean -fd
  git_safe lfs pull --include "data/city_builds.db" || true
  deploy_sha="$(git_safe rev-parse HEAD)"
  deploy_synced_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
fi

mkdir -p data
if [ -n "$deploy_sha" ]; then
  cat > data/deploy.json <<EOF
{
  "commit": "${deploy_sha}",
  "branch": "${deploy_branch}",
  "syncedAt": "${deploy_synced_at}",
  "source": "scripts/ops/update.sh"
}
EOF
fi

# Rebuild only when the deployed commit changes (or FORCE_BUILD=1). Building is
# memory-hungry on a small VM, and running `build --pull` every time rebuilt and
# restarted the stack whenever a base image was republished. The marker is
# written only after a successful build, so a failed build is retried next run.
build_marker="data/.last-build-commit"
last_built=""
if [ -f "$build_marker" ]; then
  last_built="$(cat "$build_marker")"
fi
if [ "${FORCE_BUILD:-0}" = "1" ] || [ -z "$deploy_sha" ] || [ "$deploy_sha" != "$last_built" ]; then
  compose build --pull
  if [ -n "$deploy_sha" ]; then
    echo "$deploy_sha" > "$build_marker"
  fi
  # Old layers otherwise pile up with every rebuild.
  docker builder prune -f --filter until=168h >/dev/null || true
  docker image prune -f >/dev/null || true
else
  echo "Commit ${deploy_sha} is already built; skipping image build"
fi

# `up` fails when a dependency (the API) is unhealthy, and an unhealthy
# container is not recreated unless its image changed. Recreate and retry once.
if ! compose up -d --remove-orphans; then
  echo "compose up failed; recreating unhealthy services and retrying" >&2
  recreate_unhealthy
  compose up -d --remove-orphans
fi

# Fail the unit (visible in `systemctl status`) if anything is left down.
not_running="$(compose ps -a --format '{{.Service}} {{.State}}' | awk '$2 != "running" { print $1 }')"
if [ -n "$not_running" ]; then
  echo "Services not running after deploy: ${not_running//$'\n'/ }" >&2
  exit 1
fi

if [ -n "$deploy_sha" ]; then
  echo "Deployed ${deploy_branch}@${deploy_sha} (syncedAt=${deploy_synced_at})"
fi
