#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)
VENV_DIR="$PROJECT_ROOT/.venv"

log() { printf '[whisprbar-update] %s\n' "$1"; }
err() { printf '[whisprbar-update][error] %s\n' "$1" >&2; exit 1; }

if [[ ! -d "$VENV_DIR" ]]; then
  log "No venv found — running full install instead"
  exec "$PROJECT_ROOT/install.sh" "$@"
fi

log "Upgrading pip"
"$VENV_DIR/bin/python" -m pip install --upgrade pip -q

log "Updating Python dependencies"
"$VENV_DIR/bin/pip" install -r "$PROJECT_ROOT/requirements.txt" -q

log "Done. Restart WhisprBar to use the new version."
