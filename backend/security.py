"""
MSolutions3D — sécurité : hachage de mots de passe, jetons de session
signés (HMAC, avec rôle et expiration) et dépendances d'authentification.
"""

import re
import json
import time
import hmac
import base64
import hashlib
import secrets
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from db import get_db, User

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SECRET_PATH = DATA_DIR / ".secret_key"
TOKEN_TTL = 8 * 3600          # 8 heures


def _get_secret() -> bytes:
    if SECRET_PATH.exists():
        return SECRET_PATH.read_bytes()
    key = secrets.token_bytes(32)
    SECRET_PATH.write_bytes(key)
    return key


SECRET = _get_secret()


# --------------------------------------------------------------------------
# Mots de passe (PBKDF2-HMAC-SHA256, format "pbkdf2$iterations$salt$hash")
# --------------------------------------------------------------------------
def hash_password(password: str, iterations: int = 200_000) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2${iterations}${salt.hex()}${dk.hex()}"


PASSWORD_POLICY = ("Le mot de passe doit contenir au moins 8 caractères, avec au moins "
                   "une minuscule, une majuscule, un chiffre et un caractère spécial.")


def password_error(password: str):
    """Renvoie un message d'erreur si le mot de passe ne respecte pas la politique, sinon None."""
    if len(password or "") < 8:
        return "Le mot de passe doit contenir au moins 8 caractères."
    if not re.search(r"[a-z]", password):
        return "Le mot de passe doit contenir au moins une lettre minuscule."
    if not re.search(r"[A-Z]", password):
        return "Le mot de passe doit contenir au moins une lettre majuscule."
    if not re.search(r"[0-9]", password):
        return "Le mot de passe doit contenir au moins un chiffre."
    if not re.search(r"[^A-Za-z0-9]", password):
        return "Le mot de passe doit contenir au moins un caractère spécial (!?@#$…)."
    return None


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# --------------------------------------------------------------------------
# Jetons de session
# --------------------------------------------------------------------------
def make_token(uid: int, role: str) -> str:
    payload = {"uid": uid, "role": role, "exp": int(time.time()) + TOKEN_TTL}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    sig = hmac.new(SECRET, b.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b}.{sig}"


def decode_token(token: str):
    try:
        b, sig = token.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(SECRET, b.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        pad = "=" * (-len(b) % 4)
        payload = json.loads(base64.urlsafe_b64decode(b + pad))
    except Exception:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload


# --------------------------------------------------------------------------
# Jetons de réinitialisation de mot de passe (indépendants de la session)
# --------------------------------------------------------------------------
def make_reset_token() -> str:
    return secrets.token_urlsafe(32)


# --------------------------------------------------------------------------
# Dépendances d'authentification
# --------------------------------------------------------------------------
def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Authentification requise.")
    payload = decode_token(auth[7:])
    if not payload:
        raise HTTPException(401, "Session expirée ou invalide.")
    user = db.get(User, int(payload.get("uid", 0)))
    if not user or not user.active:
        raise HTTPException(401, "Compte introuvable ou désactivé.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Accès réservé à l'administrateur.")
    return user
