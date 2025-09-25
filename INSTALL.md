# WhisprBar Installation

WhisprBar targets Linux desktops that provide a working system tray and clipboard integration. The instructions below were tested on Linux Mint (Cinnamon), GNOME, KDE Plasma, and XFCE.

## Quickstart with the Installer Script

```bash
chmod +x install.sh
./install.sh
```

The installer performs the following steps:
- Detects `apt`, `dnf`, or `pacman` and checks for required packages (Python, GTK/AppIndicator stack, clipboard/audio tools, `zenity` for GUI prompts).
- Offers to install missing packages automatically.
- Creates or updates `.venv` and installs Python dependencies from `requirements.txt`.
- Writes `~/.config/whisprbar.env` (including `WHISPRBAR_HOME`, optionally `OPENAI_API_KEY`).
- Installs the launcher (`~/.local/bin/whisprbar`) and desktop entry on request.

Helpful flags:
- `./install.sh --dry-run` – perform checks only, without changes.
- `./install.sh --auto` – run unattended and apply all suggested actions.
- `./install.sh --skip-system` – skip system package checks (only virtualenv + pip).

After a successful run, start WhisprBar from your applications menu or via:

```bash
~/.local/bin/whisprbar
```

On first launch a diagnostics dialog verifies the key dependencies (tray backend, auto-paste capability, audio input, API key). You can reopen the dialog later from the tray menu (`Diagnostics...`).

## System Packages & Desktop Notes

| Desktop | Default session | Required packages (examples) | Notes |
| --- | --- | --- | --- |
| Cinnamon / Mint | X11 | `python3-venv`, `python3-gi`, `gir1.2-appindicator3-0.1`, `libayatana-appindicator3-1`, `xdotool`, `xclip`, `libnotify-bin`, `alsa-utils` | Prefers AppIndicator; auto-paste works fully on X11. |
| GNOME Shell | Wayland | `wl-clipboard`, `gnome-shell-extension-appindicator`, `libnotify`, remaining packages same as Cinnamon | On Wayland the app degrades to copy-to-clipboard only; use an X11 session or the `type` fallback for auto-paste. |
| KDE Plasma | Wayland/X11 | `xdotool`, `wl-clipboard`, `libnotify`, AppIndicator package | Tray icons are sorted alphabetically; Wayland requires clipboard portals. |
| XFCE | X11 | Same as Cinnamon plus enable `xfce4-statusnotifier-plugin` | Wayland support is experimental; auto-paste behaves like X11. |

### Package Summary per Package Manager

- **apt (Debian/Ubuntu/Mint):** `python3`, `python3-venv`, `python3-pip`, `python3-gi`, `gir1.2-gtk-3.0`, `gir1.2-appindicator3-0.1`, `libayatana-appindicator3-1`, `xdotool`, `libnotify-bin`, `xclip`, `wl-clipboard`, `alsa-utils`, `zenity`, optional `gnome-shell-extension-appindicator`.
- **dnf (Fedora/RHEL):** `python3`, `python3-pip`, `python3-gobject`, `gtk3`, `libappindicator-gtk3`, `xdotool`, `libnotify`, `xclip`, `wl-clipboard`, `alsa-utils`, `zenity`, optional `gnome-shell-extension-appindicator`.
- **pacman (Arch/Manjaro):** `python`, `python-pip`, `python-gobject`, `gtk3`, `libappindicator-gtk3`, `xdotool`, `libnotify`, `xclip`, `wl-clipboard`, `alsa-utils`, `zenity`, optional `gnome-shell-extension-appindicator`.

## Manual Installation (Fallback)

Use this route if your distribution is unsupported or you prefer to manage everything manually:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Install the required system packages beforehand (see the tables above). After that, activate the virtualenv and install Python dependencies.

Create the configuration file `~/.config/whisprbar.env`:

```bash
cat <<'CFG' > ~/.config/whisprbar.env
OPENAI_API_KEY=sk-...your-key...
WHISPRBAR_HOME="/path/to/whisprbar"
CFG
chmod 600 ~/.config/whisprbar.env
```

Optional launcher/desktop integration:

```bash
install -Dm755 whisprbar-launcher.sh ~/.local/bin/whisprbar
install -Dm644 whisprbar.desktop ~/.local/share/applications/whisprbar.desktop
```

## Troubleshooting & Checks

- **Enable debug logs:** `WHISPRBAR_DEBUG=1 ~/.local/bin/whisprbar`.
- **Tray icon missing:** Ensure AppIndicator support is active (GNOME requires the extension). On Wayland, try an X11 session for comparison.
- **Auto-paste fails:** Verify `xdotool` (X11) or `wl-clipboard` (Wayland). Wayland mode currently supports copy-to-clipboard only.
- **Audio devices unavailable:** `python -m sounddevice` lists devices; adjust the device name inside `~/.config/whisprbar.json`.
- **OPENAI_API_KEY lost:** Edit `~/.config/whisprbar.env` or rerun the installer.
- **Run environment diagnostics:** `~/.local/bin/whisprbar --diagnose` prints the full check report in the terminal.

See `WORKLOG.md` and `DEPLOY_PLAN.md` (sections 1–3) for additional diagnostics and known limitations.
