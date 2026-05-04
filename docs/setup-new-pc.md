# WhisprBar Setup on a New PC

After a fresh clone or Nextcloud sync, run the installer once:

```bash
cd ~/WhisprBar    # or wherever the folder was synced/cloned
./install.sh
```

The installer:

- installs missing system packages
- creates the Python environment (`.venv`)
- installs the launcher and desktop entry
- configures API keys

For updates after `git pull` or a Nextcloud sync:

```bash
cd ~/WhisprBar
./update.sh
```
