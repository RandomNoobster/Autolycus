#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_DIR"

# Deploy host: discard local dirt (e.g. chmod +x) and sync to remote.
# Do not use this pattern on a machine with work you care about keeping.
if [ -d .git ]; then
  git fetch --prune origin
  branch="$(git rev-parse --abbrev-ref HEAD)"
  git reset --hard "origin/${branch}"
  git clean -fd
  git lfs pull --include "data/city_builds.db" || true
fi

docker compose --profile prod build --pull

docker compose --profile prod up -d --remove-orphans
