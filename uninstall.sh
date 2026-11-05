#!/usr/bin/env bash
set -euo pipefail
rm -f \
  "${HOME}/.local/bin/tv" \
  "${HOME}/.local/bin/lee-tv-widget" \
  "${HOME}/.local/share/applications/lee-tv.desktop"
rm -rf "${HOME}/.local/share/lee-tv"
echo "Removed TV. The saved place in ~/.config/lee-tv was left in place."
