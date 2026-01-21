#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_DIR"

if [ -d .git ]; then
  git pull --rebase
fi

docker compose build --pull

docker compose up -d --remove-orphans
