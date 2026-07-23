"""
Définit (ou réinitialise) le mot de passe du compte ADMINISTRATEUR.

Usage :
    venv\\Scripts\\python.exe set_password.py            (demande le mot de passe)
    venv\\Scripts\\python.exe set_password.py MonMotDePasse

Le mot de passe est haché puis enregistré dans la base (table users).
La prise en compte est immédiate (pas besoin de redémarrer le serveur).
Identifiant de connexion = l'e-mail du compte admin (affiché à la fin).
"""

import sys
import getpass

from db import SessionLocal, User, init_db
from security import hash_password, password_error


def main() -> None:
    if len(sys.argv) > 1:
        password = sys.argv[1]
    else:
        password = getpass.getpass("Nouveau mot de passe administrateur : ")
        confirm = getpass.getpass("Confirmez le mot de passe          : ")
        if password != confirm:
            print("Les mots de passe ne correspondent pas. Aucune modification.")
            sys.exit(1)

    err = password_error(password)
    if err:
        print(err + " Aucune modification.")
        print("(8 caractères min., avec minuscule, majuscule, chiffre et caractère spécial.)")
        sys.exit(1)

    init_db()
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.role == "admin").first()
        if not admin:
            print("Aucun compte administrateur en base.")
            print("Démarrez le serveur une première fois (Demarrer-site.bat) puis réessayez.")
            sys.exit(1)
        admin.password = hash_password(password)
        db.commit()
        print("Mot de passe administrateur enregistre.")
        print(f"Connexion sur /admin.html avec :  {admin.email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
