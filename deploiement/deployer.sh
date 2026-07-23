#!/bin/bash
# ============================================================
#  Déploiement d'une NOUVELLE VERSION en conservant les données
#  À lancer sur le serveur après avoir poussé vos changements.
#  Les données (base + factures + images) ne sont JAMAIS touchées :
#  elles vivent dans backend/data/ et assets/uploads/, ignorés par git.
# ============================================================
set -euo pipefail

SITE=/opt/msolution/site

echo "==> 1/5  Sauvegarde de sécurité avant mise à jour"
"$SITE/deploiement/sauvegarde.sh"

echo "==> 2/5  Récupération de la nouvelle version du code"
cd "$SITE"
git pull --ff-only

echo "==> 3/5  Mise à jour des dépendances Python"
"$SITE/backend/venv/bin/pip" install -q -r "$SITE/backend/requirements.txt"

echo "==> 4/5  Redémarrage de l'application"
sudo systemctl restart msolution

echo "==> 5/5  Vérification"
sleep 2
if systemctl is-active --quiet msolution; then
    echo "✅  Nouvelle version EN LIGNE."
else
    echo "❌  Problème au démarrage. Voir les logs :"
    echo "    journalctl -u msolution -n 60 --no-pager"
    echo "    (En cas de souci grave, restaurez la sauvegarde — voir le guide, section Rollback.)"
    exit 1
fi

# NB : les changements de STRUCTURE de la base (nouvelles colonnes) sont
# appliqués AUTOMATIQUEMENT au démarrage (migration intégrée), sans perte
# de données. Aucune action manuelle sur la base n'est nécessaire.
