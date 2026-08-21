#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SYSTEMD_DIR="/etc/systemd/system"

sudo install -m 0644 "$REPO_DIR/scripts/ops/autolycus.service" "$SYSTEMD_DIR/autolycus.service"
sudo install -m 0644 "$REPO_DIR/scripts/ops/autolycus-update.service" "$SYSTEMD_DIR/autolycus-update.service"
sudo install -m 0644 "$REPO_DIR/scripts/ops/autolycus-update.timer" "$SYSTEMD_DIR/autolycus-update.timer"

sudo systemctl daemon-reload
sudo systemctl enable --now autolycus.service
sudo systemctl enable --now autolycus-update.timer
