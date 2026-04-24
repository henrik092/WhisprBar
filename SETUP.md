# WhisprBar Setup (neuer PC)

Nach dem Nextcloud-Sync einmalig ausführen:

```bash
cd ~/WhisprBar    # oder wo Nextcloud den Ordner hinsynct
./install.sh
```

Das wars. Das Script:
- Installiert fehlende System-Pakete
- Erstellt die Python-Umgebung (.venv)
- Richtet den Launcher ein (Startmenü)
- Konfiguriert API-Keys

Bei Updates (nach git pull oder Nextcloud-Sync):

```bash
cd ~/WhisprBar
./update.sh
```
