#!/usr/bin/env bash
set -euo pipefail

log(){
  printf '[WhisprBar] %s\n' "$1" >&2
}

notify_error(){
  local message="$1"
  if command -v notify-send >/dev/null 2>&1; then
    notify-send --app-name=WhisprBar --icon=dialog-error "WhisprBar" "$message" || true
  elif command -v zenity >/dev/null 2>&1; then
    (zenity --error --title="WhisprBar" --text="$message" >/dev/null 2>&1 &) || true
  fi
}

fail(){
  local message="$1"
  echo "[WhisprBar] $message" >&2
  notify_error "$message"
  exit 1
}

SCRIPT_DIR=$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ENV_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/whisprbar.env"

if [[ -f "$ENV_FILE" ]]; then
  log "Loading config from $ENV_FILE"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

export PYTHONPATH="/usr/lib/python3/dist-packages:/usr/lib/python3.12/dist-packages:${PYTHONPATH:-}"

APP_DIR="${WHISPRBAR_HOME:-$SCRIPT_DIR}"
VENV_DIR="$APP_DIR/.venv"
PYTHON="$VENV_DIR/bin/python"
APP_SCRIPT="$APP_DIR/whisprbar.py"

log "App directory: $APP_DIR"
log "Virtualenv: $PYTHON"

if [[ ! -x "$PYTHON" ]]; then
  fail "Virtualenv missing. Run 'python3 -m venv .venv' and install dependencies."
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  fail "OPENAI_API_KEY not set. Edit $ENV_FILE and add 'OPENAI_API_KEY=…'"
fi

log "Starting WhisprBar..."
exec "$PYTHON" "$APP_SCRIPT" "$@"
