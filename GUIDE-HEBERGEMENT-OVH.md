# Guide d'hébergement & de gestion — MSolution sur un VPS OVHcloud

Ce document explique **de A à Z** : comment mettre le site en ligne sur un serveur OVH,
comment le gérer au quotidien, comment mettre à jour le système, et surtout **comment
publier une nouvelle version de l'application sans jamais perdre vos données**.

> Les fichiers de configuration mentionnés sont fournis dans le dossier `deploiement/`.
> Remplacez partout `msolutions3d.fr` par **votre vrai domaine**, et `1.2.3.4` par
> **l'adresse IP de votre VPS**.

---

## 0. Vue d'ensemble

```
Votre domaine (msolutions3d.fr) ──DNS──▶  VPS OVHcloud (Ubuntu 24.04)
                                          │
                                          ├─ Caddy        → HTTPS auto + reçoit le trafic
                                          │                 et le transmet à l'application
                                          │
                                          └─ uvicorn (app FastAPI)  [service systemd]
                                               ├─ base SQLite + fichiers (disque du VPS)
                                               └─ sauvegarde quotidienne (cron)

                    Brevo (SMTP)  ◀── e-mails (réinit. mot de passe, notifications, devis…)
```

**Ce que vous ne toucherez presque jamais après l'installation :** Caddy (HTTPS auto),
le service (redémarrage auto), les sauvegardes (cron), les mises à jour de sécurité (auto).

---

## Partie A — Installation initiale (à faire UNE fois)

### A.1 — Commander le domaine et le VPS

1. Sur **ovhcloud.com**, commandez un **VPS** (le modèle d'entrée « VPS-1 » suffit :
   ~2 vCores, 2–4 Go de RAM). Choisissez **Ubuntu 24.04 LTS** comme système, et un
   **datacenter en France** (Gravelines ou Strasbourg).
2. Commandez (ou transférez) votre **nom de domaine** `msolutions3d.fr` (OVH est aussi
   registrar — pratique, tout au même endroit).
3. OVH vous envoie par e-mail **l'adresse IP** du VPS et un mot de passe root initial.

### A.2 — Faire pointer le domaine vers le VPS (DNS)

Dans l'espace OVH → **Noms de domaine → Zone DNS**, créez / vérifiez :

| Type | Sous-domaine | Cible |
|------|--------------|-------|
| A    | (vide / `@`) | `1.2.3.4` (IP du VPS) |
| A    | `www`        | `1.2.3.4` |

⏳ La propagation DNS peut prendre de quelques minutes à quelques heures.

### A.3 — Première connexion et création d'un utilisateur dédié

Depuis votre PC (PowerShell fait très bien l'affaire), connectez-vous en SSH :

```bash
ssh root@1.2.3.4
```

Mettez à jour le système et créez un utilisateur non-root `msolution` :

```bash
apt update && apt upgrade -y
adduser msolution                 # choisissez un mot de passe fort
usermod -aG sudo msolution        # droits d'administration
```

**Sécuriser la connexion SSH par clé** (fortement recommandé). Sur **votre PC** :

```bash
ssh-keygen -t ed25519             # crée une clé (Entrée pour tout accepter)
ssh-copy-id msolution@1.2.3.4     # installe votre clé sur le serveur
```

Puis reconnectez-vous en tant que `msolution` : `ssh msolution@1.2.3.4`.

### A.4 — Durcissement de la sécurité (le « kit sécurité »)

```bash
# Pare-feu : on n'ouvre QUE le web (80/443) et SSH (22)
sudo apt install -y ufw
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

# Anti-force-brute sur SSH
sudo apt install -y fail2ban
sudo systemctl enable --now fail2ban

# Mises à jour de sécurité AUTOMATIQUES (le point le plus important)
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades   # répondre "Oui"
```

*(Optionnel mais conseillé)* désactiver la connexion SSH par mot de passe une fois la clé
en place : dans `/etc/ssh/sshd_config`, mettre `PasswordAuthentication no`, puis
`sudo systemctl restart ssh`.

### A.5 — Installer les logiciels nécessaires

```bash
sudo apt install -y python3 python3-venv python3-pip git sqlite3

# Caddy (serveur web + HTTPS automatique)
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

### A.6 — Déposer le code de l'application

**Méthode recommandée : Git** (permet les retours en arrière). Créez un dépôt **privé**
sur GitHub, poussez-y le contenu du dossier `Site internet` (le `.gitignore` fourni
exclut déjà les données et l'environnement). Puis, sur le serveur :

```bash
sudo mkdir -p /opt/msolution
sudo chown msolution:msolution /opt/msolution
cd /opt/msolution
git clone https://github.com/VOTRE-COMPTE/VOTRE-DEPOT.git site
```

> *Alternative sans Git :* depuis votre PC, `rsync` en excluant les données :
> `rsync -av --exclude 'backend/venv' --exclude 'backend/data' --exclude 'assets/uploads' "C:/Users/sylvain/Desktop/MSolution/Site internet/" msolution@1.2.3.4:/opt/msolution/site/`

### A.7 — Créer l'environnement Python et installer les dépendances

```bash
cd /opt/msolution/site/backend
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt
```

### A.8 — Configurer les variables (e-mail admin + Brevo)

```bash
cd /opt/msolution/site/deploiement
cp msolution.env.example msolution.env
nano msolution.env          # remplissez ADMIN_EMAIL et, plus tard, les infos Brevo
chmod 600 msolution.env     # lisible uniquement par vous
```

### A.9 — Installer le service (démarrage automatique)

```bash
sudo cp /opt/msolution/site/deploiement/msolution.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now msolution
sudo systemctl status msolution        # doit afficher "active (running)"
```

### A.10 — Définir votre mot de passe administrateur

Au 1er démarrage, un compte admin est créé avec l'e-mail défini dans `msolution.env`.
Définissez son mot de passe (politique : 8 car. min., majuscule + minuscule + chiffre +
caractère spécial) :

```bash
cd /opt/msolution/site/backend
venv/bin/python set_password.py
```

### A.11 — Activer Caddy (HTTPS)

```bash
sudo cp /opt/msolution/site/deploiement/Caddyfile /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile          # mettez VOTRE domaine
sudo mkdir -p /var/log/caddy && sudo chown caddy:caddy /var/log/caddy
sudo systemctl reload caddy
```

🎉 Ouvrez **https://msolutions3d.fr** : le site est en ligne, en HTTPS.
L'admin est sur **https://msolutions3d.fr/admin.html**.

### A.12 — Programmer les sauvegardes automatiques

```bash
chmod +x /opt/msolution/site/deploiement/sauvegarde.sh
sudo mkdir -p /opt/msolution/backups && sudo chown msolution:msolution /opt/msolution/backups
crontab -e
```
Ajoutez cette ligne (sauvegarde tous les jours à 3 h du matin) :
```
0 3 * * * /opt/msolution/site/deploiement/sauvegarde.sh >> /var/log/msolution-backup.log 2>&1
```

### A.13 — Brancher l'envoi d'e-mails (Brevo)

1. Créez un compte gratuit sur **brevo.com**.
2. **Authentifiez votre domaine** (menu *Expéditeurs & domaines*) : Brevo vous donne des
   enregistrements **SPF** et **DKIM** à ajouter dans la **Zone DNS OVH**. Indispensable
   pour ne pas tomber en spam.
3. Récupérez vos identifiants **SMTP** (*SMTP & API → SMTP*).
4. Renseignez-les dans `deploiement/msolution.env` (voir A.8), puis :
   ```bash
   sudo systemctl restart msolution
   ```
   Les e-mails partent désormais réellement.

---

## Partie B — Gestion du serveur au quotidien

Tout se fait en SSH (`ssh msolution@1.2.3.4`). Commandes essentielles :

| Objectif | Commande |
|----------|----------|
| Voir si l'app tourne | `sudo systemctl status msolution` |
| Redémarrer l'app | `sudo systemctl restart msolution` |
| Voir les logs de l'app (temps réel) | `journalctl -u msolution -f` |
| 50 dernières lignes de log | `journalctl -u msolution -n 50 --no-pager` |
| État de Caddy (HTTPS) | `sudo systemctl status caddy` |
| Espace disque | `df -h` |
| Vérifier une sauvegarde | `ls -lh /opt/msolution/backups` |

**Rythme conseillé :** une petite vérification **~1 fois par mois** (l'app tourne,
les sauvegardes se créent, l'espace disque est OK). Rien de quotidien.

---

## Partie C — Mises à jour du système d'exploitation

### C.1 — Automatique (déjà en place)
Grâce à `unattended-upgrades` (étape A.4), les **correctifs de sécurité** s'installent
**tout seuls**. C'est le plus important — vous n'avez rien à faire.

### C.2 — Manuel (de temps en temps, ex. tous les 1–2 mois)
Pour appliquer aussi les mises à jour non critiques :
```bash
sudo apt update && sudo apt upgrade -y
```
Si une mise à jour l'exige (message *reboot required* ou mise à jour du noyau) :
```bash
sudo reboot
```
Grâce aux services `systemd`, **l'application et Caddy redémarrent tout seuls** après le
redémarrage du serveur. Reconnectez-vous après ~1 minute et vérifiez avec
`sudo systemctl status msolution`.

### C.3 — Grosse mise à niveau (rare, ~tous les 2 ans)
Passage à la version LTS suivante d'Ubuntu : `sudo do-release-upgrade`. À faire après une
sauvegarde, sans précipitation. On s'en occupera ensemble le moment venu.

---

## Partie D — Modifier l'application et publier une nouvelle version (SANS perdre les données)

C'est le point clé. Le principe qui protège vos données :

> **Le code** (fichiers `.py`, `.html`, `.css`, `.js`) est remplacé à chaque mise à jour.
> **Les données** (base `msolution.db`, factures PDF, images téléversées, clé secrète)
> vivent dans `backend/data/` et `assets/uploads/`, qui sont **ignorés par Git**
> (`.gitignore`). Une mise à jour du code **ne les touche donc jamais**.

### D.1 — Le cycle de travail (développement → production)

```
1. Sur votre PC : on modifie/ajoute des fonctionnalités (avec moi) et on TESTE en local.
2. On enregistre les changements dans Git :
        git add -A
        git commit -m "Description de la nouveauté"
        git push
3. Sur le serveur : on récupère et on publie la nouvelle version :
        ssh msolution@1.2.3.4
        /opt/msolution/site/deploiement/deployer.sh
```

Le script `deployer.sh` fait automatiquement, dans l'ordre :
1. une **sauvegarde de sécurité**,
2. `git pull` (récupère le nouveau code — sans toucher aux données),
3. la mise à jour des **dépendances** si `requirements.txt` a changé,
4. le **redémarrage** de l'application,
5. une **vérification** que tout est reparti.

### D.2 — Et les changements de structure de la base ? (nouvelles colonnes)

Quand une nouveauté ajoute des champs en base (ex. le statut de paiement des factures),
l'application applique la modification **automatiquement au démarrage** (migration
intégrée : elle ajoute les colonnes manquantes sans effacer l'existant). **Vous n'avez
aucune manipulation de base de données à faire.**

> ⚠️ Seul cas particulier : une transformation de données complexe (renommer/supprimer
> des colonnes, migrer vers PostgreSQL…). Là, on prépare ensemble un script de migration
> dédié avant de déployer. Ça n'arrive que pour de gros changements — je vous préviendrai.

### D.3 — Ajouter une dépendance / un service externe

Si une nouvelle fonctionnalité nécessite une bibliothèque Python, elle sera ajoutée à
`backend/requirements.txt` (côté développement). Le `deployer.sh` l'installe tout seul au
déploiement (étape `pip install -r requirements.txt`). Rien de plus à faire de votre côté.

Si c'est un service externe (ex. un fournisseur de paiement), il apportera en général des
**clés/identifiants** : on les ajoutera dans `deploiement/msolution.env` (comme pour
Brevo), puis `sudo systemctl restart msolution`.

---

## Partie E — En cas de problème : retour arrière (rollback)

### E.1 — Revenir à la version de code précédente
```bash
cd /opt/msolution/site
git log --oneline -5          # repère l'identifiant de la version qui marchait
git reset --hard <identifiant>
sudo systemctl restart msolution
```

### E.2 — Restaurer une sauvegarde de données
```bash
sudo systemctl stop msolution
# Base :
cp /opt/msolution/backups/db-AAAA-MM-JJ_HHMM.sqlite /opt/msolution/site/backend/data/msolution.db
# Fichiers :
tar -xzf /opt/msolution/backups/fichiers-AAAA-MM-JJ_HHMM.tar.gz -C /opt/msolution/site/backend/data --strip-components=0
sudo systemctl start msolution
```
*(Adaptez les chemins/dates ; au moindre doute, on le fait ensemble.)*

---

## Partie F — Statistiques de visites (Umami)

**Umami** compte les visites de votre site **sans cookie** (donc **aucun bandeau de
consentement** nécessaire), en respectant le RGPD. L'intégration est déjà prête dans le
code : il suffit de renseigner **2 valeurs** dans `js/main.js` et **1 variable** côté
serveur, puis de redéployer.

Deux façons d'obtenir Umami — choisissez-en **une** :

### Option A — Umami Cloud (le plus simple, recommandé pour démarrer)
Hébergé en Europe, offre gratuite suffisante, **zéro maintenance**.
1. Créez un compte sur **cloud.umami.is** (ou umami.is).
2. Ajoutez votre site → Umami vous donne un **identifiant de site** (website ID) et un
   script (`https://cloud.umami.is/script.js`).
3. Dans `js/main.js`, renseignez :
   ```js
   const UMAMI_SRC = "https://cloud.umami.is/script.js";
   const UMAMI_WEBSITE_ID = "votre-website-id";
   ```
4. Dans `deploiement/msolution.env`, mettez :
   ```
   MSOLUTION_ANALYTICS_ORIGIN=https://cloud.umami.is
   ```
5. Redéployez (`deployer.sh`) puis `sudo systemctl restart msolution`.

→ Consultez vos statistiques depuis le tableau de bord Umami.

### Option B — Umami auto-hébergé sur votre VPS (données 100 % chez vous)
Un peu plus à installer, mais tout reste sur votre serveur.
```bash
# 1) Installer Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker msolution      # déconnexion/reconnexion ensuite

# 2) Lancer Umami + sa base (dans un dossier dédié)
mkdir -p ~/umami && cd ~/umami
# Récupérez le docker-compose officiel :
curl -o docker-compose.yml https://raw.githubusercontent.com/umami-software/umami/master/docker-compose.yml
# (Éditez le mot de passe de base de données dans le fichier, puis :)
docker compose up -d
```
3. **Sous-domaine + HTTPS** : ajoutez dans `/etc/caddy/Caddyfile` :
   ```
   stats.msolutions3d.fr {
       reverse_proxy 127.0.0.1:3000
   }
   ```
   Créez l'enregistrement DNS `A` pour `stats` → IP du VPS, puis `sudo systemctl reload caddy`.
4. Ouvrez `https://stats.msolutions3d.fr`, connectez-vous (admin/umami par défaut →
   **changez le mot de passe**), ajoutez votre site → récupérez le **website ID**.
5. Dans `js/main.js` :
   ```js
   const UMAMI_SRC = "https://stats.msolutions3d.fr/script.js";
   const UMAMI_WEBSITE_ID = "votre-website-id";
   ```
6. Dans `deploiement/msolution.env` :
   ```
   MSOLUTION_ANALYTICS_ORIGIN=https://stats.msolutions3d.fr
   ```
7. Redéployez + `sudo systemctl restart msolution`.

> Le suivi ne concerne que les **pages publiques** (accueil, impression 3D, logiciels,
> réalisations) — jamais l'espace client ni l'admin. Tant que les 2 valeurs de `main.js`
> sont vides, **aucun suivi n'est actif** (utile en local).

---

## Annexe — Aide-mémoire

| Situation | Que faire |
|-----------|-----------|
| Le site ne répond pas | `sudo systemctl status msolution` puis `sudo systemctl status caddy` |
| Erreur après un déploiement | `journalctl -u msolution -n 60 --no-pager` (lire l'erreur) → rollback E.1 |
| Certificat HTTPS en erreur | Vérifier que le DNS pointe bien vers le VPS et que les ports 80/443 sont ouverts (`sudo ufw status`) |
| E-mails non reçus | Vérifier SPF/DKIM chez Brevo + les variables SMTP dans `msolution.env` |
| Changer le mot de passe admin | `cd /opt/msolution/site/backend && venv/bin/python set_password.py` |
| Créer un compte client | Depuis l'interface `/admin.html`, onglet **Clients** |

---

**En résumé** : après l'installation (Partie A), votre implication se limite à :
**publier vos nouveautés** avec `deployer.sh` (Partie D) et **jeter un œil une fois par
mois**. Les mises à jour de sécurité, l'HTTPS et les sauvegardes sont automatiques, et
**vos données sont préservées à chaque mise à jour**.
