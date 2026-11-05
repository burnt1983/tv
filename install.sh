#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
SHARE="${HOME}/.local/share/lee-tv"
BIN="${HOME}/.local/bin"
mkdir -p "$SHARE" "$BIN"
install -m 0755 "$ROOT/lee_tv_widget.py" "$SHARE/lee_tv_widget.py"
install -m 0644 "$ROOT/desklet_geometry.py" "$SHARE/desklet_geometry.py"
ln -sfn "$SHARE/lee_tv_widget.py" "$BIN/tv"
ln -sfn "$SHARE/lee_tv_widget.py" "$BIN/lee-tv-widget"
echo "Installed TV."
echo "  Run: tv"
echo "  It does not start at login until you tick Open at login."
