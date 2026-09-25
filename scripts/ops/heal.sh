#!/usr/bin/env bash
set -euo pipefail

# Watchdog run by autolycus-heal.timer: recreates containers Docker marks as
# unhealthy (e.g. an API that died after an out-of-memory kill but that Docker
# still believes is running).

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_DIR"

# shellcheck source=scripts/ops/common.sh
. "$REPO_DIR/scripts/ops/common.sh"

# An update is in progress; it recreates unhealthy services itself.
ops_lock -n || exit 0

recreate_unhealthy
