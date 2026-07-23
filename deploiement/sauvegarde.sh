#!/bin/bash
# ============================================================
#  Sauvegarde quotidienne : base de données + fichiers privés
#  (factures PDF) + images téléversées.
#  Lancé automatiquement par cron (voir le guide).
# ============================================================
set -euo pipefail

SITE=/opt/msolution/site
DEST=/opt/msolution/backups
DATE=$(date +%Y-%m-%d_%H%M)

mkdir -p "$DEST"

# 1) Base SQLite : snapshot cohérent même si l'app tourne (.backup)
sqlite3 "$SITE/backend/data/msolution.db" ".backup '$DEST/db-$DATE.sqlite'"

# 2) Fichiers : factures privées + images téléversées + clé secrète
tar -czf "$DEST/fichiers-$DATE.tar.gz" \
    -C "$SITE/backend/data" invoices .secret_key \
    -C "$SITE" assets/uploads 2>/dev/null || true

# 3) Rétention : on ne garde que les 14 derniers jours
find "$DEST" -type f -mtime +14 -delete

echo "[$(date)] Sauvegarde OK -> $DEST (db-$DATE.sqlite, fichiers-$DATE.tar.gz)"

# CONSEIL : pour une vraie sécurité, copiez aussi ces sauvegardes HORS du
# serveur (ex. vers un stockage objet OVH/Scaleway avec 'rclone', ou par scp
# vers votre PC). Un serveur perdu = sauvegardes perdues si elles sont dessus.
