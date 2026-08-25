#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_DIR"

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

docker compose --profile prod build --pull

docker compose --profile prod up -d --remove-orphans

if [ -n "$deploy_sha" ]; then
  echo "Deployed ${deploy_branch}@${deploy_sha} (syncedAt=${deploy_synced_at})"
fi
