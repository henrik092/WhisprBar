#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REQUIREMENTS_FILE="$PROJECT_ROOT/requirements.txt"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
ENV_FILE="$CONFIG_DIR/whisprbar.env"
VENV_DIR="$PROJECT_ROOT/.venv"
LAUNCHER_PATH="$HOME/.local/bin/whisprbar"
DESKTOP_ENTRY_PATH="$HOME/.local/share/applications/whisprbar.desktop"
AUTO_MODE=0
DRY_RUN=0
SKIP_SYSTEM=0

log() {
  printf '[whisprbar-install] %s\n' "$1"
}

warn() {
  printf '[whisprbar-install][warn] %s\n' "$1" >&2
}

err() {
  printf '[whisprbar-install][error] %s\n' "$1" >&2
  exit 1
}

usage() {
  cat <<'USAGE'
Usage: ./install.sh [options]

Options:
  --auto        run without interactive confirmations (installs missing packages, overwrites defaults)
  --dry-run     only perform checks, do not install packages or modify files
  --skip-system skip system package checks and installations (virtualenv + pip only)
  -h, --help    show this help message
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --auto)
      AUTO_MODE=1
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    --skip-system)
      SKIP_SYSTEM=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      err "Unknown option: $1"
      ;;
  esac
  shift
done

INSTALL_TITLE="WhisprBar Installer"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Required command '$1' not found. Install it first."
  fi
}

trim() {
  local value="$1"
  value="${value#${value%%[![:space:]]*}}"
  value="${value%${value##*[![:space:]]}}"
  printf '%s' "$value"
}

detect_package_manager() {
  if command -v apt-get >/dev/null 2>&1; then
    echo "apt"
  elif command -v dnf >/dev/null 2>&1; then
    echo "dnf"
  elif command -v pacman >/dev/null 2>&1; then
    echo "pacman"
  else
    echo "unknown"
  fi
}

is_pkg_installed() {
  local manager="$1"
  local pkg="$2"
  case "$manager" in
    apt)
      dpkg -s "$pkg" >/dev/null 2>&1
      ;;
    dnf)
      rpm -q "$pkg" >/dev/null 2>&1
      ;;
    pacman)
      pacman -Qi "$pkg" >/dev/null 2>&1
      ;;
    *)
      return 1
      ;;
  esac
}

collect_packages() {
  local manager="$1"
  local -n _result="$2"
  local -a base=()
  case "$manager" in
    apt)
      base=(python3 python3-venv python3-pip python3-gi gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 libayatana-appindicator3-1 xdotool libnotify-bin xclip wl-clipboard alsa-utils zenity)
      ;;
    dnf)
      base=(python3 python3-pip python3-gobject gtk3 libappindicator-gtk3 xdotool libnotify xclip wl-clipboard alsa-utils zenity)
      ;;
    pacman)
      base=(python python-pip python-gobject gtk3 libappindicator-gtk3 xdotool libnotify xclip wl-clipboard alsa-utils zenity)
      ;;
    *)
      base=()
      ;;
  esac

  local desktop="$(trim "${XDG_CURRENT_DESKTOP:-${DESKTOP_SESSION:-}}")"
  local session="$(trim "${XDG_SESSION_TYPE:-}")"
  desktop=$(echo "$desktop" | tr '[:upper:]' '[:lower:]')
  session=$(echo "$session" | tr '[:upper:]' '[:lower:]')

  if [[ "$desktop" == *gnome* ]]; then
    case "$manager" in
      apt|dnf|pacman)
        base+=(gnome-shell-extension-appindicator)
        ;;
    esac
  fi

  if [[ "$session" == "wayland" ]]; then
    case "$manager" in
      dnf|pacman)
        if [[ " ${base[*]} " != *" wl-clipboard "* ]]; then
          base+=(wl-clipboard)
        fi
        ;;
    esac
  fi

  _result=(${base[@]})
}

print_missing_packages() {
  local -a missing=()
  local manager="$1"
  shift
  local -a pkg_list=("$@")
  for pkg in "${pkg_list[@]}"; do
    if ! is_pkg_installed "$manager" "$pkg"; then
      missing+=("$pkg")
    fi
  done
  if (( ${#missing[@]} > 0 )); then
    printf '%s\n' "${missing[*]}"
  fi
}

install_packages() {
  local manager="$1"
  shift
  local -a pkgs=("$@")
  if (( ${#pkgs[@]} == 0 )); then
    return
  fi
  case "$manager" in
    apt)
      sudo apt-get update
      sudo apt-get install -y "${pkgs[@]}"
      ;;
    dnf)
      sudo dnf install -y "${pkgs[@]}"
      ;;
    pacman)
      sudo pacman -S --noconfirm --needed "${pkgs[@]}"
      ;;
    *)
      warn "Cannot auto-install packages on unsupported manager."
      ;;
  esac
}

ensure_virtualenv() {
  require_command python3
  if [[ -d "$VENV_DIR" ]]; then
    log "Reusing existing virtualenv at $VENV_DIR"
  else
    log "Creating virtualenv at $VENV_DIR"
    python3 -m venv "$VENV_DIR"
  fi
  log "Upgrading pip"
  "$VENV_DIR/bin/python" -m pip install --upgrade pip
  if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
    err "requirements.txt not found at $REQUIREMENTS_FILE"
  fi
  log "Installing Python dependencies"
  "$VENV_DIR/bin/pip" install -r "$REQUIREMENTS_FILE"
}

configure_env_file() {
  mkdir -p "$CONFIG_DIR"
  local existing_key=""
  if [[ -f "$ENV_FILE" ]]; then
    existing_key=$(grep -E '^OPENAI_API_KEY=' "$ENV_FILE" | tail -n1 | cut -d'=' -f2-)
    existing_key=$(trim "${existing_key:-}")
    if [[ -z "$existing_key" ]]; then
      local legacy_key
      legacy_key=$(grep -E '^[[:alnum:]_-]{10,}$' "$ENV_FILE" | head -n1 || true)
      legacy_key=$(trim "${legacy_key:-}")
      if [[ -n "$legacy_key" ]]; then
        existing_key="$legacy_key"
        log "Recovered OPENAI_API_KEY from legacy format in $ENV_FILE"
      fi
    fi
    log "Found existing $ENV_FILE"
  else
    log "Creating $ENV_FILE"
    : > "$ENV_FILE"
  fi

  if [[ $DRY_RUN -eq 1 ]]; then
    warn "Dry run: skipping changes to $ENV_FILE"
    return
  fi

  chmod 600 "$ENV_FILE"

  local new_key=""
  if [[ -z "$existing_key" ]]; then
    new_key=$(prompt_api_key "Enter OPENAI_API_KEY (leave blank to skip): ")
  else
    if [[ $AUTO_MODE -eq 0 ]]; then
      read -rp "Existing OPENAI_API_KEY detected. Replace it? [y/N]: " answer
      answer=$(trim "$answer")
      if [[ "$answer" =~ ^[Yy]$ ]]; then
        new_key=$(prompt_api_key "Enter new OPENAI_API_KEY: ")
      fi
    else
      log "Keeping existing OPENAI_API_KEY"
    fi
  fi

  local final_key="$existing_key"
  if [[ -n "$new_key" ]]; then
    final_key="$new_key"
  fi

  if [[ -z "$final_key" ]]; then
    warn "No OPENAI_API_KEY stored. You must edit $ENV_FILE later."
  fi

  write_env_file "$final_key" "$PROJECT_ROOT"
}

prompt_yes() {
  local prompt="$1"
  if [[ $AUTO_MODE -eq 1 ]]; then
    return 0
  fi
  read -rp "$prompt" answer
  answer=$(trim "$answer")
  [[ "$answer" =~ ^[Yy]$ ]]
}

prompt_api_key() {
  local prompt="$1"
  local key=""
  if [[ -t 0 ]]; then
    read -rp "$prompt" key || key=""
  else
    if command -v zenity >/dev/null 2>&1; then
      key=$(zenity --entry --title="$INSTALL_TITLE" --text="$prompt" --hide-text 2>/dev/null || true)
    elif command -v kdialog >/dev/null 2>&1; then
      key=$(kdialog --title "$INSTALL_TITLE" --password "$prompt" 2>/dev/null || true)
    else
      warn "No terminal available and neither zenity nor kdialog found – unable to prompt for OPENAI_API_KEY. Edit $ENV_FILE manually later."
      key=""
    fi
  fi
  key=$(trim "$key")
  printf '%s' "$key"
}

write_env_file() {
  local api_key="$1"
  local home_path="$2"
  local tmp
  tmp=$(mktemp)

  if [[ -n "$api_key" ]]; then
    printf 'OPENAI_API_KEY=%s\n' "$api_key" >> "$tmp"
  else
    printf 'OPENAI_API_KEY=\n' >> "$tmp"
  fi
  printf 'WHISPRBAR_HOME="%s"\n' "$home_path" >> "$tmp"

  if [[ -f "$ENV_FILE" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      case "$line" in
        OPENAI_API_KEY=*|WHISPRBAR_HOME=*)
          continue
          ;;
        '')
          printf '\n' >> "$tmp"
          ;;
        \#*)
          printf '%s\n' "$line" >> "$tmp"
          ;;
        *=*)
          printf '%s\n' "$line" >> "$tmp"
          ;;
        *)
          continue
          ;;
      esac
    done < "$ENV_FILE"
  fi

  chmod 600 "$tmp"
  mv "$tmp" "$ENV_FILE"
}

install_launcher_assets() {
  if [[ $DRY_RUN -eq 1 ]]; then
    warn "Dry run: skipping launcher/desktop installation"
    return
  fi

  if prompt_yes "Install launcher to $LAUNCHER_PATH? [y/N]: "; then
    mkdir -p "$(dirname "$LAUNCHER_PATH")"
    install -m 755 "$PROJECT_ROOT/whisprbar-launcher.sh" "$LAUNCHER_PATH"
    log "Launcher installed to $LAUNCHER_PATH"
  fi

  if prompt_yes "Install desktop entry to $DESKTOP_ENTRY_PATH? [y/N]: "; then
    mkdir -p "$(dirname "$DESKTOP_ENTRY_PATH")"
    install -m 644 "$PROJECT_ROOT/whisprbar.desktop" "$DESKTOP_ENTRY_PATH"
    if command -v desktop-file-edit >/dev/null 2>&1; then
      desktop-file-edit --set-key=Exec --set-value="$LAUNCHER_PATH" "$DESKTOP_ENTRY_PATH" || warn "desktop-file-edit failed to update Exec"
    else
      sed -i "s|^Exec=.*|Exec=$LAUNCHER_PATH|" "$DESKTOP_ENTRY_PATH"
    fi
    if command -v update-desktop-database >/dev/null 2>&1; then
      update-desktop-database "$(dirname "$DESKTOP_ENTRY_PATH")" || warn "update-desktop-database failed"
    fi
    if command -v xdg-desktop-menu >/dev/null 2>&1; then
      xdg-desktop-menu forceupdate >/dev/null 2>&1 || true
    fi
    log "Desktop entry installed"
  fi
}

print_summary() {
  cat <<SUMMARY

Installation summary
--------------------
Project root:      ${PROJECT_ROOT}
Virtualenv:        ${VENV_DIR}
Env file:          ${ENV_FILE}
Launcher:          ${LAUNCHER_PATH} (installed on request)
Desktop entry:     ${DESKTOP_ENTRY_PATH} (installed on request)

Start the app:
  ${LAUNCHER_PATH}
or run:
  ${VENV_DIR}/bin/python ${PROJECT_ROOT}/whisprbar.py

Troubleshooting:
  export WHISPRBAR_DEBUG=1
  ${LAUNCHER_PATH}
SUMMARY
}

start_whisprbar() {
  local runner=""
  if [[ -x "$LAUNCHER_PATH" ]]; then
    runner="$LAUNCHER_PATH"
  elif [[ -x "$PROJECT_ROOT/whisprbar-launcher.sh" ]]; then
    runner="$PROJECT_ROOT/whisprbar-launcher.sh"
  else
    warn "No executable launcher found for first run."
    return 1
  fi

  log "Starting WhisprBar via $runner"
  "$runner" >/dev/null 2>&1 &
  local pid=$!
  # Give the process a moment; if it exits immediately, treat it as failure.
  sleep 1
  if kill -0 "$pid" >/dev/null 2>&1; then
    # Detach background process from the installer session.
    disown "$pid" 2>/dev/null || true
    log "WhisprBar launched (PID $pid)"
    return 0
  fi

  wait "$pid" || true
  warn "Failed to launch WhisprBar."
  return 1
}

offer_first_run() {
  if [[ $DRY_RUN -eq 1 ]]; then
    warn "Dry run: skipping first run prompt"
    return
  fi

  if [[ $AUTO_MODE -eq 1 ]]; then
    log "Auto mode: skipping interactive first run prompt"
    return
  fi

  if prompt_yes "Start WhisprBar now? [y/N]: "; then
    if ! start_whisprbar; then
      warn "Manual start required (see summary)."
    fi
  fi
}

main() {
  if [[ $AUTO_MODE -eq 0 && ! -t 0 ]]; then
    log "No interactive terminal detected - enabling auto mode."
    AUTO_MODE=1
  fi

  if [[ $DRY_RUN -eq 1 ]]; then
    log "Running in dry-run mode"
  fi

  if [[ $SKIP_SYSTEM -eq 0 ]]; then
    local manager
    manager=$(detect_package_manager)
    if [[ "$manager" == "unknown" ]]; then
      warn "Unsupported package manager. Please install runtime dependencies manually."
    else
      log "Detected package manager: $manager"
      local packages=()
      collect_packages "$manager" packages
      if (( ${#packages[@]} == 0 )); then
        warn "No package list defined for $manager"
      else
        local missing
        missing=$(print_missing_packages "$manager" "${packages[@]}" || true)
        if [[ -n "$missing" ]]; then
          log "Missing packages: $missing"
          if [[ $DRY_RUN -eq 1 ]]; then
            warn "Dry run: not installing packages"
          else
            if [[ $AUTO_MODE -eq 1 ]]; then
              install_packages "$manager" $missing
            elif prompt_yes "Install missing packages now? [y/N]: "; then
              install_packages "$manager" $missing
            else
              warn "Skipping package installation. Ensure dependencies are installed before running WhisprBar."
            fi
          fi
        else
          log "All required system packages are present"
        fi
      fi
    fi
  else
    log "Skipping system package checks"
  fi

  if [[ $DRY_RUN -eq 1 ]]; then
    log "Dry run complete"
    return
  fi

  ensure_virtualenv
  configure_env_file
  install_launcher_assets
  print_summary
  offer_first_run
}

main "$@"
