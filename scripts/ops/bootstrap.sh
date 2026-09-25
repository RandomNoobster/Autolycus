#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SYSTEMD_DIR="/etc/systemd/system"

sudo install -m 0644 "$REPO_DIR/scripts/ops/autolycus.service" "$SYSTEMD_DIR/autolycus.service"
sudo install -m 0644 "$REPO_DIR/scripts/ops/autolycus-update.service" "$SYSTEMD_DIR/autolycus-update.service"
sudo install -m 0644 "$REPO_DIR/scripts/ops/autolycus-update.timer" "$SYSTEMD_DIR/autolycus-update.timer"
sudo install -m 0644 "$REPO_DIR/scripts/ops/autolycus-heal.service" "$SYSTEMD_DIR/autolycus-heal.service"
sudo install -m 0644 "$REPO_DIR/scripts/ops/autolycus-heal.timer" "$SYSTEMD_DIR/autolycus-heal.timer"

# systemd update unit runs as root; repo is often owned by a deploy user.
sudo git config --system --add safe.directory "$REPO_DIR" || true

sudo systemctl daemon-reload
sudo systemctl enable --now autolycus.service
sudo systemctl enable --now autolycus-update.timer
sudo systemctl enable --now autolycus-heal.timer

echo "Tip: force one update now with: sudo systemctl start autolycus-update.service"
