# ✅ Checklist — Jour de la commande du VPS OVH

À suivre le jour où vous commandez le serveur. Cochez au fur et à mesure.
Une fois terminé, on enchaîne sur le **GUIDE-HEBERGEMENT-OVH.md** (Partie A), ensemble.

---

## 1. Avant de commander (5 min de préparation)

- [ ] Avoir un **moyen de paiement** (CB) pour le compte OVH.
- [ ] Décider du **nom de domaine** souhaité (ex. `msolutions3d.fr`) — à commander en même temps si vous ne l'avez pas déjà.
- [ ] Avoir une **adresse e-mail** pour créer/associer le compte OVH.
- [ ] *(Recommandé)* Créer une **clé SSH** sur votre PC — dans PowerShell :
      `ssh-keygen -t ed25519` (appuyez sur Entrée pour tout accepter).
      Ça sécurisera la connexion au serveur (détaillé dans le guide, A.3).

## 2. Pendant la commande (les 6 choix à faire)

Sur **ovhcloud.com → VPS** :

- [ ] **Modèle : VPS-1** (2 vCores, 4 Go RAM, 40 Go NVMe)
- [ ] **Système d'exploitation : Ubuntu 24.04 LTS**
- [ ] **Datacenter : France** (Gravelines ou Roubaix)
- [ ] **Sauvegarde automatique : activée** (option — double sécurité pour vos factures/données)
- [ ] **Engagement : mensuel** (flexible) — ou annuel si vous êtes sûr (moins cher)
- [ ] **Panneau de gestion : AUCUN** (ni Plesk ni cPanel — on installe à la main, plus léger et plus sûr)

*(Trafic illimité et anti-DDoS sont déjà inclus, rien à cocher.)*

## 3. Après la commande — à noter et garder précieusement 🔐

OVH vous envoie un e-mail avec les accès. Notez-les dans un endroit sûr :

- [ ] **Adresse IP** du VPS (ex. `1.2.3.4`)
- [ ] **Identifiant + mot de passe root** initial (on créera un compte plus sûr ensuite)
- [ ] Confirmation que le **système installé est bien Ubuntu 24.04**

## 4. À préparer en parallèle pour l'installation

- [ ] **Accès à la Zone DNS** de votre domaine (dans l'espace OVH) — pour le faire pointer vers le VPS.
- [ ] **Compte Brevo** (gratuit, sur brevo.com) — pour l'envoi d'e-mails. On le branchera à la fin.
- [ ] **E-mail administrateur** choisi (ex. `contact@msolutions3d.fr`) = votre identifiant de connexion à `/admin.html`.
- [ ] *(Si méthode Git)* un **compte GitHub** (gratuit) avec un **dépôt privé** pour y déposer le code.
      *(Sinon, on transférera les fichiers par rsync — voir le guide A.6.)*
- [ ] Votre **PC prêt** avec un terminal (PowerShell suffit pour le SSH).

## 5. Prochaine étape

- [ ] Me prévenir dès que le VPS est livré (IP reçue) → on déroule le
      **GUIDE-HEBERGEMENT-OVH.md, Partie A**, étape par étape, ensemble.

---

## ⚠️ Rappel sécurité (à ne pas oublier pendant l'installation)
- [ ] **Changer le mot de passe administrateur** de l'application (`MSolution2026` est connu) → via `set_password.py` (guide, A.10).
- [ ] Vérifier après coup que le site s'ouvre bien en **https://** (cadenas).

---

**Budget à prévoir :** ~**4,57 € TTC/mois** (VPS-1) + le **nom de domaine** (~7-10 €/an) + **0 €** pour les e-mails (offre gratuite Brevo). Total : moins de **6 €/mois**.
