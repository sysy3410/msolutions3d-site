"""
MSolution — backend de la plateforme.

Sert le site statique + l'API : portfolio public, comptes (admin/clients),
connexion sécurisée, réinitialisation de mot de passe, gestion des clients.
"""

import os
import json
import time
import secrets
from pathlib import Path
from datetime import datetime, timezone, timedelta, date

from fastapi import FastAPI, Request, HTTPException, Depends, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from db import (SessionLocal, init_db, get_db, User, Project, Order, Invoice,
                Message, FilamentSpool, Expense, Settings, DevProject, DevTask, now_utc)
from security import (
    hash_password, verify_password, make_token, make_reset_token,
    get_current_user, require_admin, password_error,
)
from emailer import send_email

BASE_DIR = Path(__file__).resolve().parent
SITE_ROOT = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = SITE_ROOT / "assets" / "uploads"        # images publiques (portfolio)
INVOICE_DIR = DATA_DIR / "invoices"                  # PDF privés (jamais servis en statique)
LEGACY_ADMIN = DATA_DIR / "admin.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
INVOICE_DIR.mkdir(parents=True, exist_ok=True)

VALID_TYPES = {"impression3d", "logiciel"}
# SVG/GIF exclus des téléversements : un SVG peut contenir du JavaScript (XSS si ouvert directement).
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PDF_BYTES = 15 * 1024 * 1024

# Étapes de suivi d'une commande (ordre = progression)
STATUS_STEPS = ["devis", "validee", "en_cours", "controle", "terminee"]
STATUS_LABELS = {
    "devis": "Devis", "validee": "Validée", "en_cours": "En cours",
    "controle": "Contrôle", "terminee": "Terminée", "annulee": "Annulée",
}
ORDER_CATEGORIES = {"impression3d", "dev", "autre"}
LOGIN_WINDOW = 300
LOGIN_MAX_ATTEMPTS = 10
RESET_TTL = timedelta(hours=2)
DEFAULT_ADMIN_EMAIL = os.environ.get("MSOLUTION_ADMIN_EMAIL", "martin.sylvain34@outlook.com")

# --------------------------------------------------------------------------
# Initialisation base + compte admin
# --------------------------------------------------------------------------
init_db()


def _seed_projects(db: Session) -> None:
    demo = [
        ("impression3d", "Carte 3D personnalisée : Monviso", "Particulier",
         "Reproduction en relief du massif du Monviso en PLA. Modélisation topographique précise, idéale comme souvenir ou décoration.",
         ["PLA", "Relief 3D", "Sur mesure"], "assets/carte-3d-monviso.jpg"),
        ("impression3d", "Support de fixation industriel", "Professionnel",
         "Pièce de remplacement pour châssis machine. Tolérance serrée, matériau résistant à la chaleur.",
         ["ABS", "±0,2 mm", "Sur plan"], ""),
        ("impression3d", "Boîtier électronique prototype", "Professionnel",
         "Coque pour carte PCB avec découpes USB, ventilation et rail DIN. Validation avant injection plastique.",
         ["PETG", "Prototype", "Fichier STEP"], ""),
        ("impression3d", "Engrenage de transmission", "Professionnel",
         "Pignon de remplacement pour mécanisme d'automatisme. Nylon PA pour résistance à l'usure et légèreté.",
         ["Nylon PA", "±0,1 mm", "Pièce technique"], ""),
        ("impression3d", "Clips de fixation : série de 50", "Professionnel",
         "Production de 50 clips identiques pour assemblage de panneaux. Cohérence dimensionnelle garantie entre toutes les pièces.",
         ["PETG", "×50 pièces", "Série"], ""),
        ("impression3d", "Vase architectural", "Particulier",
         "Objet décoratif à parois fines et géométrie organique. Modélisation paramétrique, finition sablée mat.",
         ["PLA", "Paroi 0,8 mm", "Design"], ""),
    ]
    for pos, (typ, title, cat, desc, tags, img) in enumerate(demo):
        db.add(Project(type=typ, title=title, category=cat, description=desc,
                       tags=json.dumps(tags, ensure_ascii=False), features="[]",
                       image=img, position=pos))
    db.commit()


def _ensure_admin_and_seed() -> None:
    db = SessionLocal()
    try:
        if db.query(Project).count() == 0:
            _seed_projects(db)

        if db.query(User).filter(User.role == "admin").first():
            return

        # Migration depuis l'ancien admin.json si présent (conserve le mot de passe).
        if LEGACY_ADMIN.exists():
            try:
                rec = json.loads(LEGACY_ADMIN.read_text(encoding="utf-8"))
                pw = f"pbkdf2${rec['iterations']}${rec['salt']}${rec['hash']}"
            except Exception:
                pw = hash_password(secrets.token_urlsafe(12))
        else:
            pw = hash_password(os.environ.get("MSOLUTION_ADMIN_PASSWORD") or secrets.token_urlsafe(12))

        admin = User(email=DEFAULT_ADMIN_EMAIL.lower(), password=pw,
                     role="admin", name="Administrateur")
        db.add(admin)
        db.commit()
        print("=" * 64)
        print(" MSolution — compte administrateur")
        print(f"   Identifiant (e-mail) : {DEFAULT_ADMIN_EMAIL.lower()}")
        if LEGACY_ADMIN.exists():
            print("   Mot de passe : inchangé (celui déjà défini).")
        print("   Modifier l'e-mail : variable MSOLUTION_ADMIN_EMAIL.")
        print("=" * 64)
    finally:
        db.close()


_ensure_admin_and_seed()

# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------
def project_dict(p: Project) -> dict:
    return {
        "id": p.id, "type": p.type, "title": p.title, "subtitle": p.subtitle,
        "category": p.category, "description": p.description,
        "tags": json.loads(p.tags or "[]"), "features": json.loads(p.features or "[]"),
        "image": p.image, "position": p.position,
    }


def user_dict(u: User) -> dict:
    return {
        "id": u.id, "email": u.email, "role": u.role, "name": u.name,
        "company": u.company, "phone": u.phone, "active": u.active,
    }


def euros(cents: int) -> str:
    """Formate des centimes en montant français : 1234567 -> '12 345,67 €'."""
    s = f"{(cents or 0) / 100:,.2f}"          # '12,345.67'
    s = s.replace(",", " ").replace(".", ",")  # '12 345,67'
    return s + " €"


def parse_euros(raw: str) -> int:
    """Convertit une saisie en euros ('240', '240,50', '1 200.00 €') en centimes."""
    s = (raw or "").strip().replace("€", "").replace(" ", "").replace(",", ".")
    if not s:
        return 0
    try:
        return round(float(s) * 100)
    except ValueError:
        return 0


def _parse_form_lines(raw: str):
    """Lignes saisies (unit_price en euros) -> [{designation, qty, unit_price_cents}] + total HT."""
    try:
        arr = json.loads(raw or "[]")
    except Exception:
        arr = []
    parsed, total = [], 0
    for li in arr if isinstance(arr, list) else []:
        desig = str(li.get("designation", "")).strip()
        if not desig:
            continue
        try:
            qty = float(str(li.get("qty", 1)).replace(",", ".") or 1)
        except ValueError:
            qty = 1
        pu = parse_euros(str(li.get("unit_price", "")))
        total += round(qty * pu)
        parsed.append({"designation": desig, "qty": qty, "unit_price_cents": pu})
    return parsed, total


def _lines_total(lines: list) -> int:
    total = 0
    for li in lines or []:
        try:
            qty = float(li.get("qty", 1))
        except (TypeError, ValueError):
            qty = 1
        total += round(qty * (li.get("unit_price_cents", 0) or 0))
    return total


ACTIVITY_LABELS = {"impression3d": "Impression 3D", "dev": "Développement",
                   "general": "Général", "autre": "Autre"}

_MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
              "août", "septembre", "octobre", "novembre", "décembre"]


def _to_date(value):
    """Convertit un datetime ou une chaîne ISO en objet date (ou None)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _period_match(d, period: str) -> bool:
    """Le date d tombe-t-il dans la période ('', 'YYYY', 'YYYY-MM', 'YYYY-Www') ?"""
    if not period:
        return True
    if d is None:
        return False
    if len(period) == 4 and period.isdigit():                 # année
        return d.year == int(period)
    if len(period) == 7 and period[4] == "-":                 # mois YYYY-MM
        return d.strftime("%Y-%m") == period
    if "-W" in period:                                        # semaine ISO YYYY-Www
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}" == period
    return True


def _period_label(period: str) -> str:
    if not period:
        return "toutes périodes"
    if len(period) == 4 and period.isdigit():
        return "année " + period
    if len(period) == 7 and period[4] == "-":
        y, m = period.split("-")
        return f"{_MONTHS_FR[int(m) - 1]} {y}"
    if "-W" in period:
        y, w = period.split("-W")
        return f"semaine {int(w)} · {y}"
    return period


def _client_label(db: Session, client_id: int) -> str:
    u = db.get(User, client_id)
    if not u:
        return "—"
    return u.name or u.company or u.email


def order_dict(o: Order, client_name: str | None = None) -> dict:
    step = STATUS_STEPS.index(o.status) if o.status in STATUS_STEPS else -1
    return {
        "id": o.id, "client_id": o.client_id, "client_name": client_name,
        "reference": o.reference, "title": o.title, "category": o.category,
        "description": o.description, "status": o.status,
        "status_label": STATUS_LABELS.get(o.status, o.status),
        "step": step, "steps_total": len(STATUS_STEPS),
        "steps": [{"key": s, "label": STATUS_LABELS[s]} for s in STATUS_STEPS],
        "amount_cents": o.amount_cents or 0, "amount": euros(o.amount_cents or 0),
        "lines": json.loads(o.lines or "[]"), "vat_rate": o.vat_rate or 0,
        "due_date": o.due_date,
        "created_at": o.created_at.isoformat() if o.created_at else "",
    }


def invoice_dict(inv: Invoice, client_name: str | None = None) -> dict:
    return {
        "id": inv.id, "client_id": inv.client_id, "client_name": client_name,
        "order_id": inv.order_id, "number": inv.number, "label": inv.label,
        "kind": inv.kind or "facture",
        "kind_label": "Devis" if inv.kind == "devis" else "Facture",
        "amount": inv.amount, "issued_date": inv.issued_date, "due_date": inv.due_date,
        "has_file": bool(inv.file), "generated": bool(inv.generated),
        "total_ttc": euros(inv.total_ttc_cents or 0),
        "paid": bool(inv.paid), "paid_at": inv.paid_at or "",
        "payment_label": "Payée" if inv.paid else "À payer",
        "created_at": inv.created_at.isoformat() if inv.created_at else "",
    }


def message_dict(m: Message) -> dict:
    return {
        "id": m.id, "sender": m.sender, "body": m.body,
        "created_at": m.created_at.isoformat() if m.created_at else "",
    }


def _clean_list(raw: str) -> str:
    try:
        arr = json.loads(raw or "[]")
        if not isinstance(arr, list):
            return "[]"
        return json.dumps([str(x).strip() for x in arr if str(x).strip()], ensure_ascii=False)
    except Exception:
        return "[]"


def _save_image(file: UploadFile) -> str:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, "Format d'image non autorisé (jpg, png, webp uniquement).")
    data = file.file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(400, "Image trop lourde (maximum 5 Mo).")
    name = f"{secrets.token_hex(8)}{ext}"
    (UPLOAD_DIR / name).write_bytes(data)
    return f"assets/uploads/{name}"


def _delete_image(path: str) -> None:
    if path and path.startswith("assets/uploads/"):
        try:
            (SITE_ROOT / path).unlink()
        except FileNotFoundError:
            pass


_login_attempts: dict[str, list[float]] = {}


def _check_rate(ip: str) -> None:
    now = time.time()
    attempts = [t for t in _login_attempts.get(ip, []) if now - t < LOGIN_WINDOW]
    _login_attempts[ip] = attempts
    if len(attempts) >= LOGIN_MAX_ATTEMPTS:
        raise HTTPException(429, "Trop de tentatives. Réessayez dans quelques minutes.")


def _record_attempt(ip: str) -> None:
    _login_attempts.setdefault(ip, []).append(time.time())


# Empreinte factice utilisée pour égaliser le temps de connexion (anti-énumération par timing).
_DUMMY_HASH = hash_password("x")


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------
app = FastAPI(title="MSolution — plateforme", docs_url=None, redoc_url=None)


# Origine du service de statistiques (Umami), autorisée dans la CSP si définie.
# Ex. "https://stats.msolutions3d.fr" (auto-hébergé) ou "https://cloud.umami.is" (cloud).
_ANALYTICS_ORIGIN = os.environ.get("MSOLUTION_ANALYTICS_ORIGIN", "").strip()


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Ajoute les en-têtes de sécurité HTTP à toutes les réponses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # N'a d'effet qu'en HTTPS (ignoré en HTTP) : prêt pour la mise en ligne.
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    extra = (" " + _ANALYTICS_ORIGIN) if _ANALYTICS_ORIGIN else ""
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline'; "
        f"script-src 'self' 'unsafe-inline'{extra}; "
        f"connect-src 'self'{extra}; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    )
    response.headers["Server"] = "MSolution"
    return response


# ===== API publique : portfolio =====
@app.get("/api/projects")
def list_projects(type: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Project)
    if type:
        q = q.filter(Project.type == type)
    rows = q.order_by(Project.position, Project.id).all()
    return [project_dict(p) for p in rows]


# ===== Authentification =====
@app.post("/api/auth/login")
def login(request: Request, email: str = Form(...), password: str = Form(...),
          db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "?"
    _check_rate(ip)
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if user and user.active:
        valid = verify_password(password, user.password)
    else:
        # Toujours exécuter un hachage même si le compte n'existe pas / est inactif,
        # pour que le temps de réponse ne révèle pas l'existence de l'e-mail (anti-énumération).
        verify_password(password, _DUMMY_HASH)
        valid = False
    if not valid:
        _record_attempt(ip)
        raise HTTPException(401, "E-mail ou mot de passe incorrect.")
    return {"token": make_token(user.id, user.role), "role": user.role, "name": user.name}


@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user)):
    return user_dict(user)


@app.post("/api/auth/password-reset/request")
def password_reset_request(request: Request, email: str = Form(...),
                           db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "?"
    _check_rate(ip)
    _record_attempt(ip)          # limite le nombre de demandes (anti-spam e-mail)
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if user:
        token = make_reset_token()
        user.reset_token = token
        user.reset_expires = now_utc() + RESET_TTL
        db.commit()
        base = str(request.base_url).rstrip("/")
        link = f"{base}/reinitialiser-mot-de-passe.html?token={token}"
        send_email(
            user.email,
            "MSolution — réinitialisation de votre mot de passe",
            f"Bonjour,\n\nPour définir un nouveau mot de passe, cliquez sur ce lien "
            f"(valable 2 heures) :\n{link}\n\nSi vous n'êtes pas à l'origine de cette "
            f"demande, ignorez cet e-mail.\n\nL'équipe MSolution",
        )
    # Réponse identique que l'e-mail existe ou non (anti-énumération).
    return {"ok": True}


@app.post("/api/auth/password-reset/confirm")
def password_reset_confirm(token: str = Form(...), password: str = Form(...),
                           db: Session = Depends(get_db)):
    err = password_error(password)
    if err:
        raise HTTPException(400, err)
    token = token.strip()
    if not token:
        raise HTTPException(400, "Lien invalide ou expiré.")
    user = db.query(User).filter(User.reset_token == token).first()
    if not user or not user.reset_expires:
        raise HTTPException(400, "Lien invalide ou expiré.")
    # reset_expires est relu naïf depuis SQLite : on compare en UTC naïf.
    now = datetime.now(timezone.utc)
    expires = user.reset_expires
    if expires.tzinfo is None:
        now = now.replace(tzinfo=None)
    if expires < now:
        raise HTTPException(400, "Lien invalide ou expiré.")
    user.password = hash_password(password)
    user.reset_token = ""
    user.reset_expires = None
    db.commit()
    return {"ok": True}


@app.post("/api/auth/change-password")
def change_password(current_password: str = Form(...), new_password: str = Form(...),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(current_password, user.password):
        raise HTTPException(400, "Mot de passe actuel incorrect.")
    err = password_error(new_password)
    if err:
        raise HTTPException(400, err)
    user.password = hash_password(new_password)
    db.commit()
    return {"ok": True}


# ===== Portfolio : administration =====
@app.post("/api/admin/projects")
def create_project(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    type: str = Form(...), title: str = Form(...), subtitle: str = Form(""),
    category: str = Form(""), description: str = Form(""),
    tags: str = Form("[]"), features: str = Form("[]"), position: int = Form(0),
    image: UploadFile | None = File(None),
):
    if type not in VALID_TYPES:
        raise HTTPException(400, "Type de projet invalide.")
    if not title.strip():
        raise HTTPException(400, "Le titre est obligatoire.")
    img = _save_image(image) if image and image.filename else ""
    p = Project(type=type, title=title.strip(), subtitle=subtitle.strip(),
                category=category.strip(), description=description.strip(),
                tags=_clean_list(tags), features=_clean_list(features),
                image=img, position=position)
    db.add(p)
    db.commit()
    db.refresh(p)
    return project_dict(p)


@app.put("/api/admin/projects/{pid}")
def update_project(
    pid: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db),
    type: str = Form(...), title: str = Form(...), subtitle: str = Form(""),
    category: str = Form(""), description: str = Form(""),
    tags: str = Form("[]"), features: str = Form("[]"), position: int = Form(0),
    remove_image: str = Form(""), image: UploadFile | None = File(None),
):
    if type not in VALID_TYPES:
        raise HTTPException(400, "Type de projet invalide.")
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "Projet introuvable.")
    if remove_image == "1":
        _delete_image(p.image)
        p.image = ""
    if image and image.filename:
        _delete_image(p.image)
        p.image = _save_image(image)
    p.type, p.title, p.subtitle = type, title.strip(), subtitle.strip()
    p.category, p.description = category.strip(), description.strip()
    p.tags, p.features, p.position = _clean_list(tags), _clean_list(features), position
    db.commit()
    db.refresh(p)
    return project_dict(p)


@app.delete("/api/admin/projects/{pid}")
def delete_project(pid: int, _admin: User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "Projet introuvable.")
    _delete_image(p.image)
    db.delete(p)
    db.commit()
    return {"ok": True}


# ===== Clients : administration =====
@app.get("/api/admin/clients")
def list_clients(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(User).filter(User.role == "client").order_by(User.name, User.id).all()
    return [user_dict(u) for u in rows]


@app.post("/api/admin/clients")
def create_client(
    request: Request, _admin: User = Depends(require_admin), db: Session = Depends(get_db),
    email: str = Form(...), name: str = Form(""), company: str = Form(""),
    phone: str = Form(""), password: str = Form(""), send_invite: str = Form(""),
):
    email = email.strip().lower()
    if "@" not in email:
        raise HTTPException(400, "E-mail invalide.")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "Un compte existe déjà avec cet e-mail.")

    if password.strip():
        err = password_error(password.strip())
        if err:
            raise HTTPException(400, err)
    # Sans mot de passe fourni : on en génère un fort et aléatoire (le client le redéfinira).
    pwd = password.strip() or (secrets.token_urlsafe(9) + "A1!")
    user = User(email=email, password=hash_password(pwd), role="client",
                name=name.strip(), company=company.strip(), phone=phone.strip())
    db.add(user)
    db.commit()
    db.refresh(user)

    invite_link = None
    if send_invite == "1":
        token = make_reset_token()
        user.reset_token = token
        user.reset_expires = now_utc() + timedelta(days=7)
        db.commit()
        base = str(request.base_url).rstrip("/")
        invite_link = f"{base}/reinitialiser-mot-de-passe.html?token={token}"
        send_email(
            user.email,
            "MSolution — votre espace client",
            f"Bonjour {user.name or ''},\n\nUn espace client a été créé pour vous sur "
            f"MSolution. Définissez votre mot de passe ici (lien valable 7 jours) :\n"
            f"{invite_link}\n\nÀ bientôt,\nL'équipe MSolution",
        )

    result = user_dict(user)
    # Mot de passe en clair renvoyé une seule fois si généré et pas d'invitation e-mail.
    if not password.strip() and send_invite != "1":
        result["generated_password"] = pwd
    if invite_link:
        result["invite_link"] = invite_link
    return result


@app.put("/api/admin/clients/{cid}")
def update_client(
    cid: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db),
    name: str = Form(""), company: str = Form(""), phone: str = Form(""),
    active: str = Form("1"),
):
    user = db.get(User, cid)
    if not user or user.role != "client":
        raise HTTPException(404, "Client introuvable.")
    user.name, user.company, user.phone = name.strip(), company.strip(), phone.strip()
    user.active = active == "1"
    db.commit()
    return user_dict(user)


@app.post("/api/admin/clients/{cid}/reset-link")
def client_reset_link(cid: int, request: Request, _admin: User = Depends(require_admin),
                      db: Session = Depends(get_db)):
    user = db.get(User, cid)
    if not user or user.role != "client":
        raise HTTPException(404, "Client introuvable.")
    token = make_reset_token()
    user.reset_token = token
    user.reset_expires = now_utc() + timedelta(days=7)
    db.commit()
    base = str(request.base_url).rstrip("/")
    return {"link": f"{base}/reinitialiser-mot-de-passe.html?token={token}"}


@app.delete("/api/admin/clients/{cid}")
def delete_client(cid: int, _admin: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    user = db.get(User, cid)
    if not user or user.role != "client":
        raise HTTPException(404, "Client introuvable.")
    db.delete(user)
    db.commit()
    return {"ok": True}


# ===== Commandes : administration =====
@app.get("/api/admin/orders")
def admin_list_orders(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(Order).order_by(Order.created_at.desc(), Order.id.desc()).all()
    names = {u.id: (u.name or u.company or u.email) for u in db.query(User).all()}
    return [order_dict(o, names.get(o.client_id, "—")) for o in rows]


@app.post("/api/admin/orders")
def admin_create_order(
    _admin: User = Depends(require_admin), db: Session = Depends(get_db),
    client_id: int = Form(...), title: str = Form(...), reference: str = Form(""),
    category: str = Form("autre"), description: str = Form(""),
    status: str = Form("devis"), amount: str = Form(""), due_date: str = Form(""),
    lines: str = Form("[]"), vat_rate: str = Form("0"),
):
    client = db.get(User, client_id)
    if not client or client.role != "client":
        raise HTTPException(400, "Client invalide.")
    if not title.strip():
        raise HTTPException(400, "Le titre est obligatoire.")
    parsed, total = _parse_form_lines(lines)
    amount_cents = total if parsed else parse_euros(amount)
    o = Order(
        client_id=client_id, title=title.strip(), reference=reference.strip(),
        category=category if category in ORDER_CATEGORIES else "autre",
        description=description.strip(),
        status=status if status in STATUS_LABELS else "devis",
        amount_cents=amount_cents, lines=json.dumps(parsed, ensure_ascii=False),
        vat_rate=_to_float(vat_rate, 0), due_date=due_date.strip(),
    )
    db.add(o); db.commit(); db.refresh(o)
    return order_dict(o, _client_label(db, o.client_id))


@app.put("/api/admin/orders/{oid}")
def admin_update_order(
    oid: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db),
    title: str = Form(...), reference: str = Form(""), category: str = Form("autre"),
    description: str = Form(""), status: str = Form("devis"),
    amount: str = Form(""), due_date: str = Form(""),
    lines: str = Form("[]"), vat_rate: str = Form("0"),
):
    o = db.get(Order, oid)
    if not o:
        raise HTTPException(404, "Commande introuvable.")
    if not title.strip():
        raise HTTPException(400, "Le titre est obligatoire.")
    parsed, total = _parse_form_lines(lines)
    o.title = title.strip()
    o.reference = reference.strip()
    o.category = category if category in ORDER_CATEGORIES else "autre"
    o.description = description.strip()
    o.status = status if status in STATUS_LABELS else o.status
    o.amount_cents = total if parsed else parse_euros(amount)
    o.lines = json.dumps(parsed, ensure_ascii=False)
    o.vat_rate = _to_float(vat_rate, 0)
    o.due_date = due_date.strip()
    db.commit(); db.refresh(o)
    return order_dict(o, _client_label(db, o.client_id))


@app.delete("/api/admin/orders/{oid}")
def admin_delete_order(oid: int, _admin: User = Depends(require_admin),
                       db: Session = Depends(get_db)):
    o = db.get(Order, oid)
    if not o:
        raise HTTPException(404, "Commande introuvable.")
    db.delete(o); db.commit()
    return {"ok": True}


# ===== Factures : administration =====
@app.get("/api/admin/invoices")
def admin_list_invoices(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(Invoice).filter(Invoice.kind == "facture") \
        .order_by(Invoice.created_at.desc(), Invoice.id.desc()).all()
    names = {u.id: (u.name or u.company or u.email) for u in db.query(User).all()}
    return [invoice_dict(i, names.get(i.client_id, "—")) for i in rows]


@app.post("/api/admin/invoices")
def admin_create_invoice(
    _admin: User = Depends(require_admin), db: Session = Depends(get_db),
    client_id: int = Form(...), order_id: str = Form(""), number: str = Form(""),
    label: str = Form(""), amount: str = Form(""), issued_date: str = Form(""),
    file: UploadFile | None = File(None),
):
    client = db.get(User, client_id)
    if not client or client.role != "client":
        raise HTTPException(400, "Client invalide.")
    fname = ""
    if file and file.filename:
        if Path(file.filename).suffix.lower() != ".pdf":
            raise HTTPException(400, "La facture doit être un fichier PDF.")
        data = file.file.read()
        if len(data) > MAX_PDF_BYTES:
            raise HTTPException(400, "PDF trop lourd (maximum 15 Mo).")
        fname = f"{secrets.token_hex(10)}.pdf"
        (INVOICE_DIR / fname).write_bytes(data)
    oid = int(order_id) if order_id.strip().isdigit() else None
    inv = Invoice(client_id=client_id, order_id=oid, number=number.strip(),
                  label=label.strip(), amount=amount.strip(),
                  issued_date=issued_date.strip(), file=fname)
    db.add(inv); db.commit(); db.refresh(inv)
    return invoice_dict(inv, _client_label(db, inv.client_id))


@app.delete("/api/admin/invoices/{iid}")
def admin_delete_invoice(iid: int, _admin: User = Depends(require_admin),
                         db: Session = Depends(get_db)):
    inv = db.get(Invoice, iid)
    if not inv:
        raise HTTPException(404, "Facture introuvable.")
    if inv.file:
        try:
            (INVOICE_DIR / inv.file).unlink()
        except FileNotFoundError:
            pass
    db.delete(inv); db.commit()
    return {"ok": True}


@app.put("/api/admin/invoices/{iid}/payment")
def admin_set_payment(iid: int, _admin: User = Depends(require_admin),
                      db: Session = Depends(get_db),
                      paid: str = Form("0"), paid_at: str = Form("")):
    inv = db.get(Invoice, iid)
    if not inv:
        raise HTTPException(404, "Facture introuvable.")
    inv.paid = paid == "1"
    inv.paid_at = paid_at.strip() if inv.paid else ""
    if inv.paid and not inv.paid_at:
        inv.paid_at = date.today().isoformat()
    db.commit(); db.refresh(inv)
    return invoice_dict(inv, _client_label(db, inv.client_id))


# ===== Espace client (données de l'utilisateur connecté) =====
@app.get("/api/client/orders")
def client_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Order).filter(Order.client_id == user.id) \
        .order_by(Order.created_at.desc(), Order.id.desc()).all()
    result = []
    for o in rows:
        d = order_dict(o)
        docs = db.query(Invoice).filter(Invoice.order_id == o.id) \
            .order_by(Invoice.created_at.desc()).all()
        d["documents"] = [invoice_dict(i) for i in docs]
        d["can_accept"] = o.status == "devis" and any(i.kind == "devis" and i.file for i in docs)
        result.append(d)
    return result


@app.get("/api/client/invoices")
def client_invoices(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Invoice).filter(Invoice.client_id == user.id, Invoice.kind == "facture") \
        .order_by(Invoice.created_at.desc(), Invoice.id.desc()).all()
    return [invoice_dict(i) for i in rows]


@app.get("/api/client/invoices/{iid}/download")
def client_invoice_download(iid: int, user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    inv = db.get(Invoice, iid)
    if not inv or inv.client_id != user.id:
        raise HTTPException(404, "Facture introuvable.")
    if not inv.file or not (INVOICE_DIR / inv.file).exists():
        raise HTTPException(404, "Fichier indisponible.")
    return FileResponse(INVOICE_DIR / inv.file, media_type="application/pdf",
                        filename=f"facture-{inv.number or inv.id}.pdf")


# ===== Messagerie : administration =====
@app.get("/api/admin/threads")
def admin_threads(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    result = []
    for c in db.query(User).filter(User.role == "client").all():
        msgs = db.query(Message).filter(Message.client_id == c.id) \
            .order_by(Message.created_at.desc()).all()
        last = msgs[0] if msgs else None
        unread = sum(1 for m in msgs if m.sender == "client" and not m.read_by_admin)
        result.append({
            "client_id": c.id, "client_name": c.name or c.company or c.email,
            "unread": unread, "total": len(msgs),
            "last_body": last.body if last else "",
            "last_sender": last.sender if last else "",
            "last_at": last.created_at.isoformat() if last and last.created_at else "",
        })
    result.sort(key=lambda t: t["last_at"], reverse=True)
    return result


@app.get("/api/admin/messages/{cid}")
def admin_get_thread(cid: int, _admin: User = Depends(require_admin),
                     db: Session = Depends(get_db)):
    c = db.get(User, cid)
    if not c or c.role != "client":
        raise HTTPException(404, "Client introuvable.")
    msgs = db.query(Message).filter(Message.client_id == cid).order_by(Message.created_at).all()
    for m in msgs:
        if m.sender == "client" and not m.read_by_admin:
            m.read_by_admin = True
    db.commit()
    return {"client_name": c.name or c.company or c.email,
            "messages": [message_dict(m) for m in msgs]}


@app.post("/api/admin/messages/{cid}")
def admin_send_message(cid: int, request: Request, body: str = Form(...),
                       _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.get(User, cid)
    if not c or c.role != "client":
        raise HTTPException(404, "Client introuvable.")
    if not body.strip():
        raise HTTPException(400, "Message vide.")
    m = Message(client_id=cid, sender="admin", body=body.strip(),
                read_by_admin=True, read_by_client=False)
    db.add(m); db.commit(); db.refresh(m)
    base = str(request.base_url).rstrip("/")
    send_email(
        c.email, "MSolution — nouveau message",
        f"Bonjour,\n\nVous avez reçu un nouveau message sur votre espace client :\n\n"
        f"{body.strip()}\n\nPour répondre, connectez-vous : {base}/espace-client.html\n\n"
        f"L'équipe MSolution",
    )
    return message_dict(m)


# ===== Messagerie : espace client =====
@app.get("/api/client/messages")
def client_messages(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    msgs = db.query(Message).filter(Message.client_id == user.id).order_by(Message.created_at).all()
    for m in msgs:
        if m.sender == "admin" and not m.read_by_client:
            m.read_by_client = True
    db.commit()
    return [message_dict(m) for m in msgs]


@app.post("/api/client/messages")
def client_send_message(request: Request, body: str = Form(...),
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not body.strip():
        raise HTTPException(400, "Message vide.")
    m = Message(client_id=user.id, sender="client", body=body.strip(),
                read_by_client=True, read_by_admin=False)
    db.add(m); db.commit(); db.refresh(m)
    admin = db.query(User).filter(User.role == "admin").first()
    if admin:
        base = str(request.base_url).rstrip("/")
        who = user.name or user.company or user.email
        send_email(
            admin.email, f"MSolution — nouveau message de {who}",
            f"{who} vous a écrit sur l'espace client :\n\n{body.strip()}\n\n"
            f"Pour répondre : {base}/admin.html (onglet Messages)",
        )
    return message_dict(m)


# ===== Stock de filament : administration =====
def spool_dict(s: FilamentSpool) -> dict:
    total = s.weight_total_g or 0
    remaining = s.weight_remaining_g or 0
    return {
        "id": s.id, "material": s.material, "color": s.color, "brand": s.brand,
        "weight_total_g": total, "weight_remaining_g": remaining,
        "low_threshold_g": s.low_threshold_g or 0,
        "low": remaining <= (s.low_threshold_g or 0),
        "percent": round(remaining / total * 100) if total else 0,
        "cost_cents": s.cost_cents or 0, "cost": euros(s.cost_cents or 0),
        "supplier": s.supplier, "purchase_date": s.purchase_date, "notes": s.notes,
    }


@app.get("/api/admin/filament")
def list_filament(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(FilamentSpool).order_by(FilamentSpool.material, FilamentSpool.id).all()
    return [spool_dict(s) for s in rows]


@app.post("/api/admin/filament")
def create_filament(
    _admin: User = Depends(require_admin), db: Session = Depends(get_db),
    material: str = Form(""), color: str = Form(""), brand: str = Form(""),
    weight_total_g: int = Form(1000), weight_remaining_g: str = Form(""),
    low_threshold_g: int = Form(150), cost: str = Form(""), supplier: str = Form(""),
    purchase_date: str = Form(""), notes: str = Form(""),
):
    remaining = int(weight_remaining_g) if weight_remaining_g.strip().isdigit() else weight_total_g
    s = FilamentSpool(
        material=material.strip(), color=color.strip(), brand=brand.strip(),
        weight_total_g=weight_total_g, weight_remaining_g=remaining,
        low_threshold_g=low_threshold_g, cost_cents=parse_euros(cost),
        supplier=supplier.strip(), purchase_date=purchase_date.strip(), notes=notes.strip(),
    )
    db.add(s); db.commit(); db.refresh(s)
    return spool_dict(s)


@app.put("/api/admin/filament/{sid}")
def update_filament(
    sid: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db),
    material: str = Form(""), color: str = Form(""), brand: str = Form(""),
    weight_total_g: int = Form(1000), weight_remaining_g: int = Form(0),
    low_threshold_g: int = Form(150), cost: str = Form(""), supplier: str = Form(""),
    purchase_date: str = Form(""), notes: str = Form(""),
):
    s = db.get(FilamentSpool, sid)
    if not s:
        raise HTTPException(404, "Bobine introuvable.")
    s.material, s.color, s.brand = material.strip(), color.strip(), brand.strip()
    s.weight_total_g, s.weight_remaining_g, s.low_threshold_g = weight_total_g, weight_remaining_g, low_threshold_g
    s.cost_cents = parse_euros(cost)
    s.supplier, s.purchase_date, s.notes = supplier.strip(), purchase_date.strip(), notes.strip()
    db.commit(); db.refresh(s)
    return spool_dict(s)


@app.delete("/api/admin/filament/{sid}")
def delete_filament(sid: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    s = db.get(FilamentSpool, sid)
    if not s:
        raise HTTPException(404, "Bobine introuvable.")
    db.delete(s); db.commit()
    return {"ok": True}


# ===== Dépenses : administration =====
def expense_dict(e: Expense) -> dict:
    return {
        "id": e.id, "label": e.label, "category": e.category,
        "category_label": ACTIVITY_LABELS.get(e.category, e.category),
        "amount_cents": e.amount_cents or 0, "amount": euros(e.amount_cents or 0),
        "date": e.date, "notes": e.notes,
    }


@app.get("/api/admin/expenses")
def list_expenses(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(Expense).order_by(Expense.date.desc(), Expense.id.desc()).all()
    return [expense_dict(e) for e in rows]


@app.post("/api/admin/expenses")
def create_expense(
    _admin: User = Depends(require_admin), db: Session = Depends(get_db),
    label: str = Form(...), category: str = Form("general"), amount: str = Form(""),
    date: str = Form(""), notes: str = Form(""),
):
    if not label.strip():
        raise HTTPException(400, "Le libellé est obligatoire.")
    e = Expense(label=label.strip(),
                category=category if category in ACTIVITY_LABELS else "general",
                amount_cents=parse_euros(amount), date=date.strip(), notes=notes.strip())
    db.add(e); db.commit(); db.refresh(e)
    return expense_dict(e)


@app.put("/api/admin/expenses/{eid}")
def update_expense(
    eid: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db),
    label: str = Form(...), category: str = Form("general"), amount: str = Form(""),
    date: str = Form(""), notes: str = Form(""),
):
    e = db.get(Expense, eid)
    if not e:
        raise HTTPException(404, "Dépense introuvable.")
    e.label = label.strip()
    e.category = category if category in ACTIVITY_LABELS else "general"
    e.amount_cents = parse_euros(amount)
    e.date, e.notes = date.strip(), notes.strip()
    db.commit(); db.refresh(e)
    return expense_dict(e)


@app.delete("/api/admin/expenses/{eid}")
def delete_expense(eid: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    e = db.get(Expense, eid)
    if not e:
        raise HTTPException(404, "Dépense introuvable.")
    db.delete(e); db.commit()
    return {"ok": True}


# ===== Contrôle de gestion / rentabilité =====
@app.get("/api/admin/accounting")
def accounting(period: str = "", _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    period = (period or "").strip()

    # Recettes : commandes acceptées (hors devis / annulée), ventilées par activité
    orders = [o for o in db.query(Order).filter(~Order.status.in_(["devis", "annulee"])).all()
              if _period_match(_to_date(o.created_at), period)]
    revenue = {"impression3d": 0, "dev": 0, "autre": 0}
    for o in orders:
        cat = o.category if o.category in revenue else "autre"
        revenue[cat] += o.amount_cents or 0

    # Coût du filament (attribué à l'impression 3D)
    spools = [s for s in db.query(FilamentSpool).all()
              if _period_match(_to_date(s.purchase_date), period)]
    filament_cost = sum(s.cost_cents or 0 for s in spools)

    # Dépenses ventilées par activité
    expenses = [e for e in db.query(Expense).all()
                if _period_match(_to_date(e.date), period)]
    exp = {"impression3d": 0, "dev": 0, "general": 0, "autre": 0}
    for e in expenses:
        cat = e.category if e.category in exp else "general"
        exp[cat] += e.amount_cents or 0

    cost = {
        "impression3d": filament_cost + exp["impression3d"],
        "dev": exp["dev"],
        "autre": exp["autre"],
    }
    activities = []
    for key in ("impression3d", "dev", "autre"):
        r, c = revenue[key], cost[key]
        activities.append({
            "key": key, "label": ACTIVITY_LABELS[key],
            "revenue_cents": r, "revenue": euros(r),
            "cost_cents": c, "cost": euros(c),
            "margin_cents": r - c, "margin": euros(r - c),
            "margin_pct": round((r - c) / r * 100) if r else None,
        })
    general = exp["general"]
    total_rev = sum(revenue.values())
    total_cost = sum(cost.values()) + general
    net = total_rev - total_cost

    years = sorted(
        {o.created_at.year for o in db.query(Order).all() if o.created_at}
        | {int((e.date or "")[:4]) for e in db.query(Expense).all() if (e.date or "")[:4].isdigit()}
        | {int((s.purchase_date or "")[:4]) for s in db.query(FilamentSpool).all() if (s.purchase_date or "")[:4].isdigit()},
        reverse=True,
    )
    low_stock = [spool_dict(s) for s in db.query(FilamentSpool).all()
                 if (s.weight_remaining_g or 0) <= (s.low_threshold_g or 0)]

    return {
        "period": period,
        "period_label": _period_label(period),
        "years": [str(y) for y in years],
        "activities": activities,
        "general_cents": general, "general": euros(general),
        "filament_cost_cents": filament_cost, "filament_cost": euros(filament_cost),
        "total_revenue_cents": total_rev, "total_revenue": euros(total_rev),
        "total_cost_cents": total_cost, "total_cost": euros(total_cost),
        "net_cents": net, "net": euros(net),
        "net_pct": round(net / total_rev * 100) if total_rev else None,
        "low_stock": low_stock,
    }


# ===== Paramètres de l'entreprise =====
def get_settings(db: Session) -> Settings:
    s = db.query(Settings).first()
    if not s:
        s = Settings()
        db.add(s); db.commit(); db.refresh(s)
    return s


def settings_dict(s: Settings) -> dict:
    return {
        "company_name": s.company_name, "legal_form": s.legal_form, "address": s.address,
        "postal_code": s.postal_code, "city": s.city, "siret": s.siret,
        "vat_number": s.vat_number, "ape_code": s.ape_code, "capital": s.capital,
        "rcs": s.rcs, "email": s.email, "phone": s.phone, "iban": s.iban, "bic": s.bic,
        "vat_applicable": s.vat_applicable, "default_vat_rate": s.default_vat_rate,
        "payment_terms": s.payment_terms, "late_penalty": s.late_penalty,
        "invoice_prefix": s.invoice_prefix, "next_invoice_number": s.next_invoice_number,
        "devis_prefix": s.devis_prefix, "next_devis_number": s.next_devis_number,
        "devis_validity_days": s.devis_validity_days,
        "calc_printer_power_w": s.calc_printer_power_w, "calc_elec_price": s.calc_elec_price,
        "calc_machine_cost": s.calc_machine_cost, "calc_labor_cost": s.calc_labor_cost,
        "calc_failure_pct": s.calc_failure_pct, "calc_margin_pct": s.calc_margin_pct,
    }


def _to_float(v, default):
    try:
        return float(str(v).replace(",", "."))
    except (ValueError, TypeError):
        return default


@app.put("/api/admin/settings/calc")
def write_calc_settings(
    _admin: User = Depends(require_admin), db: Session = Depends(get_db),
    printer_power_w: int = Form(250), elec_price: str = Form("0.25"),
    machine_cost: str = Form("0.80"), labor_cost: str = Form("35"),
    failure_pct: str = Form("5"), margin_pct: str = Form("50"),
):
    s = get_settings(db)
    s.calc_printer_power_w = max(0, printer_power_w)
    s.calc_elec_price = _to_float(elec_price, 0.25)
    s.calc_machine_cost = _to_float(machine_cost, 0.80)
    s.calc_labor_cost = _to_float(labor_cost, 35.0)
    s.calc_failure_pct = _to_float(failure_pct, 5.0)
    s.calc_margin_pct = _to_float(margin_pct, 50.0)
    db.commit()
    return settings_dict(s)


@app.get("/api/admin/settings")
def read_settings(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return settings_dict(get_settings(db))


@app.put("/api/admin/settings")
def write_settings(
    _admin: User = Depends(require_admin), db: Session = Depends(get_db),
    company_name: str = Form(""), legal_form: str = Form(""), address: str = Form(""),
    postal_code: str = Form(""), city: str = Form(""), siret: str = Form(""),
    vat_number: str = Form(""), ape_code: str = Form(""), capital: str = Form(""),
    rcs: str = Form(""), email: str = Form(""), phone: str = Form(""),
    iban: str = Form(""), bic: str = Form(""), vat_applicable: str = Form(""),
    default_vat_rate: str = Form("20"), payment_terms: str = Form(""),
    late_penalty: str = Form(""), invoice_prefix: str = Form("F-"),
    next_invoice_number: int = Form(1), devis_prefix: str = Form("D-"),
    next_devis_number: int = Form(1), devis_validity_days: int = Form(30),
):
    s = get_settings(db)
    s.company_name = company_name.strip() or "MSolution"
    s.legal_form, s.address = legal_form.strip(), address.strip()
    s.postal_code, s.city = postal_code.strip(), city.strip()
    s.siret, s.vat_number, s.ape_code = siret.strip(), vat_number.strip(), ape_code.strip()
    s.capital, s.rcs = capital.strip(), rcs.strip()
    s.email, s.phone = email.strip(), phone.strip()
    s.iban, s.bic = iban.strip(), bic.strip()
    s.vat_applicable = vat_applicable == "1"
    try:
        s.default_vat_rate = float(default_vat_rate.replace(",", ".")) if default_vat_rate.strip() else 20.0
    except ValueError:
        s.default_vat_rate = 20.0
    s.payment_terms, s.late_penalty = payment_terms.strip(), late_penalty.strip()
    s.invoice_prefix = invoice_prefix.strip()
    s.next_invoice_number = max(1, next_invoice_number)
    s.devis_prefix = devis_prefix.strip()
    s.next_devis_number = max(1, next_devis_number)
    s.devis_validity_days = max(1, devis_validity_days)
    db.commit()
    return settings_dict(s)


# ===== Génération de factures PDF conformes =====
def _pdf_money(cents: int) -> str:
    s = f"{(cents or 0) / 100:,.2f}".replace(",", " ").replace(".", ",")
    return s + " €"


_NEXT = dict(new_x=XPos.LMARGIN, new_y=YPos.NEXT)
_SAME = dict(new_x=XPos.RIGHT, new_y=YPos.TOP)


FONT_DIR = BASE_DIR / "fonts"
FONT = "DejaVu"
LOGO_PATH = SITE_ROOT / "assets" / "logo-msolution.png"

BRAND_BLUE = (13, 79, 122)
BRAND_TURQ = (20, 184, 166)
INK = (40, 50, 60)
GREY = (120, 130, 140)
LIGHT = (244, 248, 250)
HAIR = (225, 232, 238)


def _pdf_font(pdf: FPDF) -> None:
    pdf.add_font(FONT, "", str(FONT_DIR / "DejaVuSans.ttf"))
    pdf.add_font(FONT, "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))


def ensure_logo() -> None:
    """Génère (une fois) le logo « M » de la marque en PNG pour les factures."""
    if LOGO_PATH.exists():
        return
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return
    S = 256
    img = Image.new("RGB", (S, S))
    px = img.load()
    c1, c2 = BRAND_BLUE, BRAND_TURQ
    for yy in range(S):
        for xx in range(S):
            t = (xx + yy) / (2 * (S - 1))
            px[xx, yy] = (
                int(c1[0] + (c2[0] - c1[0]) * t),
                int(c1[1] + (c2[1] - c1[1]) * t),
                int(c1[2] + (c2[2] - c1[2]) * t),
            )
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    draw = ImageDraw.Draw(out)
    sc = S / 48.0
    pts = [(12, 34), (12, 15), (20, 26), (24, 20.5), (28, 26), (36, 15), (36, 34)]
    pts = [(x * sc, y * sc) for x, y in pts]
    lw = 3.4 * sc
    draw.line(pts, fill=(255, 255, 255, 255), width=int(lw), joint="curve")
    r = lw / 2
    for x, y in (pts[0], pts[-1]):
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 255))
    LOGO_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.save(LOGO_PATH)


def generate_invoice_pdf(inv: Invoice, client: User, s: Settings, kind: str = "facture") -> bytes:
    is_devis = kind == "devis"
    doc_title = "DEVIS" if is_devis else "FACTURE"
    issued_label = "Établi le" if is_devis else "Émise le"
    due_label = "Valable jusqu'au :" if is_devis else "Échéance :"
    try:
        ensure_logo()
    except Exception:
        pass

    pdf = FPDF(format="A4")
    _pdf_font(pdf)
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(18, 14, 18)
    pdf.add_page()
    LM, RM = 18, 192          # marges gauche / droite (x)
    PW = RM - LM              # largeur utile = 174

    # ---------- En-tête ----------
    logo_ok = LOGO_PATH.exists()
    if logo_ok:
        pdf.image(str(LOGO_PATH), x=LM, y=14, w=15, h=15)
    name_x = LM + 19 if logo_ok else LM
    pdf.set_xy(name_x, 15)
    pdf.set_text_color(*BRAND_BLUE)
    pdf.set_font(FONT, "B", 16)
    pdf.cell(90, 7, s.company_name or "MSolution", **_NEXT)
    pdf.set_font(FONT, "", 8)
    pdf.set_text_color(*GREY)
    emit = []
    if s.legal_form:
        emit.append(s.legal_form + (f" · capital {s.capital}" if s.capital else ""))
    if s.address:
        emit.append(s.address)
    cpv = " ".join(x for x in [s.postal_code, s.city] if x)
    if cpv:
        emit.append(cpv)
    if s.siret:
        emit.append(f"SIRET {s.siret}" + (f" · APE {s.ape_code}" if s.ape_code else ""))
    if s.vat_applicable and s.vat_number:
        emit.append(f"N° TVA {s.vat_number}")
    if s.rcs:
        emit.append(f"RCS {s.rcs}")
    ct = " · ".join(x for x in [s.email, s.phone] if x)
    if ct:
        emit.append(ct)
    for ln in emit:
        pdf.set_x(name_x)
        pdf.cell(100, 4.2, ln, **_NEXT)
    left_bottom = pdf.get_y()

    # Bloc FACTURE (à droite)
    pdf.set_xy(120, 15)
    pdf.set_text_color(*BRAND_BLUE)
    pdf.set_font(FONT, "B", 24)
    pdf.cell(72, 11, doc_title, align="R", **_NEXT)
    pdf.set_x(120)
    pdf.set_font(FONT, "B", 12)
    pdf.set_text_color(*INK)
    pdf.cell(72, 7, inv.number, align="R", **_NEXT)
    pdf.set_font(FONT, "", 9)
    pdf.set_text_color(*GREY)
    if inv.issued_date:
        pdf.set_x(120)
        pdf.cell(72, 5, f"{issued_label} {inv.issued_date}", align="R", **_NEXT)
    if inv.due_date:
        pdf.set_x(120)
        pdf.cell(72, 5, f"{due_label} {inv.due_date}", align="R", **_NEXT)
    right_bottom = pdf.get_y()

    y = max(left_bottom, right_bottom) + 4
    pdf.set_draw_color(*BRAND_TURQ)
    pdf.set_line_width(0.8)
    pdf.line(LM, y, RM, y)
    y += 8

    # ---------- Facturé à (encadré) ----------
    cl = [x for x in [client.name, client.company, client.email, client.phone] if x]
    box_h = 9 + 4.8 * max(1, len(cl))
    pdf.set_fill_color(*LIGHT)
    pdf.set_draw_color(*HAIR)
    pdf.set_line_width(0.2)
    pdf.rect(LM, y, 86, box_h, style="DF", round_corners=True, corner_radius=2)
    pdf.set_xy(LM + 4, y + 3)
    pdf.set_font(FONT, "B", 8)
    pdf.set_text_color(*GREY)
    pdf.cell(78, 4, "FACTURÉ À", **_NEXT)
    pdf.set_font(FONT, "", 10)
    pdf.set_text_color(*INK)
    for ln in cl:
        pdf.set_x(LM + 4)
        pdf.cell(78, 4.8, ln, **_NEXT)
    y = y + box_h + 8
    pdf.set_y(y)

    # ---------- Tableau des lignes ----------
    w = [92, 18, 32, 32]
    pdf.set_x(LM)
    pdf.set_font(FONT, "B", 9)
    pdf.set_text_color(255, 255, 255)
    pdf.set_fill_color(*BRAND_BLUE)
    pdf.cell(w[0], 8, "  Désignation", fill=True, **_SAME)
    pdf.cell(w[1], 8, "Qté", align="C", fill=True, **_SAME)
    pdf.cell(w[2], 8, "PU HT", align="R", fill=True, **_SAME)
    pdf.cell(w[3], 8, "Total HT  ", align="R", fill=True, **_NEXT)

    pdf.set_font(FONT, "", 9)
    pdf.set_text_color(*INK)
    lines = json.loads(inv.lines or "[]")
    zebra = False
    for li in lines:
        qty = li.get("qty", 1)
        pu = li.get("unit_price_cents", 0)
        line_total = round(qty * pu)
        qty_txt = str(int(qty)) if float(qty).is_integer() else str(qty)
        pdf.set_x(LM)
        pdf.set_fill_color(247, 250, 251) if zebra else pdf.set_fill_color(255, 255, 255)
        pdf.cell(w[0], 7, "  " + str(li.get("designation", ""))[:56], fill=True, **_SAME)
        pdf.cell(w[1], 7, qty_txt, align="C", fill=True, **_SAME)
        pdf.cell(w[2], 7, _pdf_money(pu), align="R", fill=True, **_SAME)
        pdf.cell(w[3], 7, _pdf_money(line_total) + "  ", align="R", fill=True, **_NEXT)
        zebra = not zebra
    pdf.set_draw_color(*HAIR)
    pdf.set_line_width(0.3)
    pdf.line(LM, pdf.get_y(), RM, pdf.get_y())

    # ---------- Totaux ----------
    pdf.ln(5)
    tx, tw_l, tw_v = 116, 46, 30
    pdf.set_font(FONT, "", 10)
    pdf.set_text_color(*INK)
    pdf.set_x(tx)
    pdf.cell(tw_l, 7, "Total HT", align="R", **_SAME)
    pdf.cell(tw_v, 7, _pdf_money(inv.total_ht_cents) + "  ", align="R", **_NEXT)
    if inv.total_vat_cents:
        pdf.set_x(tx)
        pdf.cell(tw_l, 7, f"TVA ({inv.vat_rate:g} %)", align="R", **_SAME)
        pdf.cell(tw_v, 7, _pdf_money(inv.total_vat_cents) + "  ", align="R", **_NEXT)
    ttc_y = pdf.get_y() + 1
    pdf.set_fill_color(*BRAND_BLUE)
    pdf.rect(tx, ttc_y, tw_l + tw_v, 9, style="F", round_corners=True, corner_radius=1.5)
    pdf.set_xy(tx, ttc_y)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(FONT, "B", 11)
    pdf.cell(tw_l, 9, "Total TTC", align="R", **_SAME)
    pdf.cell(tw_v, 9, _pdf_money(inv.total_ttc_cents) + "  ", align="R", **_NEXT)

    # ---------- Mentions légales ----------
    pdf.ln(16)
    pdf.set_draw_color(*HAIR)
    pdf.set_line_width(0.3)
    pdf.line(LM, pdf.get_y(), RM, pdf.get_y())
    pdf.ln(3)
    pdf.set_font(FONT, "", 8)
    pdf.set_text_color(*GREY)
    mentions = []
    if not s.vat_applicable:
        mentions.append("TVA non applicable, art. 293 B du CGI.")
    if s.payment_terms:
        mentions.append("Conditions de règlement : " + s.payment_terms)
    if s.iban:
        mentions.append(f"IBAN {s.iban}" + (f" · BIC {s.bic}" if s.bic else ""))
    if not is_devis and s.late_penalty:
        mentions.append(s.late_penalty)
    for m in mentions:
        pdf.set_x(LM)
        pdf.multi_cell(PW, 4, m)
        pdf.ln(0.5)

    if is_devis:
        pdf.ln(6)
        pdf.set_font(FONT, "B", 9)
        pdf.set_text_color(*INK)
        pdf.set_x(LM)
        pdf.cell(0, 6, "Bon pour accord (date et signature) :", **_NEXT)

    return bytes(pdf.output())


@app.post("/api/admin/invoices/generate")
def generate_invoice(
    _admin: User = Depends(require_admin), db: Session = Depends(get_db),
    client_id: int = Form(...), order_id: str = Form(""), issued_date: str = Form(""),
    due_date: str = Form(""), vat_rate: str = Form(""), label: str = Form(""),
    lines: str = Form("[]"),
):
    client = db.get(User, client_id)
    if not client or client.role != "client":
        raise HTTPException(400, "Client invalide.")
    s = get_settings(db)

    try:
        raw = json.loads(lines or "[]")
        if not isinstance(raw, list):
            raw = []
    except Exception:
        raw = []
    parsed, total_ht = [], 0
    for li in raw:
        desig = str(li.get("designation", "")).strip()
        if not desig:
            continue
        try:
            qty = float(str(li.get("qty", 1)).replace(",", ".") or 1)
        except ValueError:
            qty = 1
        pu = parse_euros(str(li.get("unit_price", "")))
        line_total = round(qty * pu)
        total_ht += line_total
        parsed.append({"designation": desig, "qty": qty, "unit_price_cents": pu})
    if not parsed:
        raise HTTPException(400, "Ajoutez au moins une ligne de facturation.")

    if s.vat_applicable:
        try:
            vrate = float(vat_rate.replace(",", ".")) if vat_rate.strip() else s.default_vat_rate
        except ValueError:
            vrate = s.default_vat_rate
    else:
        vrate = 0.0
    total_vat = round(total_ht * vrate / 100)
    total_ttc = total_ht + total_vat

    number = f"{s.invoice_prefix}{s.next_invoice_number:05d}"
    s.next_invoice_number += 1
    oid = int(order_id) if order_id.strip().isdigit() else None

    inv = Invoice(
        client_id=client_id, order_id=oid, number=number, label=label.strip(),
        amount=euros(total_ttc), issued_date=issued_date.strip() or date.today().isoformat(),
        due_date=due_date.strip(), lines=json.dumps(parsed, ensure_ascii=False),
        vat_rate=vrate, total_ht_cents=total_ht, total_vat_cents=total_vat,
        total_ttc_cents=total_ttc, generated=True,
    )
    db.add(inv); db.commit(); db.refresh(inv)

    fname = f"{secrets.token_hex(10)}.pdf"
    (INVOICE_DIR / fname).write_bytes(generate_invoice_pdf(inv, client, s))
    inv.file = fname
    db.commit(); db.refresh(inv)
    return invoice_dict(inv, _client_label(db, inv.client_id))


@app.get("/api/admin/invoices/{iid}/download")
def admin_invoice_download(iid: int, _admin: User = Depends(require_admin),
                          db: Session = Depends(get_db)):
    inv = db.get(Invoice, iid)
    if not inv or not inv.file or not (INVOICE_DIR / inv.file).exists():
        raise HTTPException(404, "Fichier indisponible.")
    return FileResponse(INVOICE_DIR / inv.file, media_type="application/pdf",
                        filename=f"facture-{inv.number or inv.id}.pdf")


# ===== Projets de développement (Gantt) =====
DEV_STATUS_LABELS = {"en_cours": "En cours", "en_pause": "En pause",
                     "termine": "Terminé", "annule": "Annulé"}
TASK_STATUS_LABELS = {"a_faire": "À faire", "en_cours": "En cours", "termine": "Terminé"}


def dev_task_dict(t: DevTask) -> dict:
    return {
        "id": t.id, "project_id": t.project_id, "name": t.name,
        "start_date": t.start_date, "end_date": t.end_date,
        "progress": t.progress or 0, "status": t.status,
        "status_label": TASK_STATUS_LABELS.get(t.status, t.status),
        "position": t.position,
    }


def dev_project_dict(p: DevProject, client_name=None, tasks=None) -> dict:
    prog = None
    if tasks:
        prog = round(sum(t.progress or 0 for t in tasks) / len(tasks))
    return {
        "id": p.id, "name": p.name, "client_id": p.client_id, "client_name": client_name,
        "description": p.description, "status": p.status,
        "status_label": DEV_STATUS_LABELS.get(p.status, p.status),
        "start_date": p.start_date, "end_date": p.end_date,
        "task_count": len(tasks) if tasks is not None else None, "progress": prog,
    }


@app.get("/api/admin/dev-projects")
def list_dev_projects(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    names = {u.id: (u.name or u.company or u.email) for u in db.query(User).all()}
    result = []
    for p in db.query(DevProject).order_by(DevProject.created_at.desc(), DevProject.id.desc()).all():
        tasks = db.query(DevTask).filter(DevTask.project_id == p.id).all()
        result.append(dev_project_dict(p, names.get(p.client_id), tasks))
    return result


@app.get("/api/admin/dev-projects/{pid}")
def get_dev_project(pid: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = db.get(DevProject, pid)
    if not p:
        raise HTTPException(404, "Projet introuvable.")
    tasks = db.query(DevTask).filter(DevTask.project_id == pid) \
        .order_by(DevTask.position, DevTask.id).all()
    name = None
    if p.client_id:
        u = db.get(User, p.client_id)
        name = (u.name or u.company or u.email) if u else None
    d = dev_project_dict(p, name, tasks)
    d["tasks"] = [dev_task_dict(t) for t in tasks]
    return d


@app.post("/api/admin/dev-projects")
def create_dev_project(
    _admin: User = Depends(require_admin), db: Session = Depends(get_db),
    name: str = Form(...), client_id: str = Form(""), description: str = Form(""),
    status: str = Form("en_cours"), start_date: str = Form(""), end_date: str = Form(""),
):
    if not name.strip():
        raise HTTPException(400, "Le nom du projet est obligatoire.")
    cid = int(client_id) if client_id.strip().isdigit() else None
    p = DevProject(
        name=name.strip(), client_id=cid, description=description.strip(),
        status=status if status in DEV_STATUS_LABELS else "en_cours",
        start_date=start_date.strip(), end_date=end_date.strip(),
    )
    db.add(p); db.commit(); db.refresh(p)
    return dev_project_dict(p, None, [])


@app.put("/api/admin/dev-projects/{pid}")
def update_dev_project(
    pid: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db),
    name: str = Form(...), client_id: str = Form(""), description: str = Form(""),
    status: str = Form("en_cours"), start_date: str = Form(""), end_date: str = Form(""),
):
    p = db.get(DevProject, pid)
    if not p:
        raise HTTPException(404, "Projet introuvable.")
    p.name = name.strip()
    p.client_id = int(client_id) if client_id.strip().isdigit() else None
    p.description = description.strip()
    p.status = status if status in DEV_STATUS_LABELS else p.status
    p.start_date, p.end_date = start_date.strip(), end_date.strip()
    db.commit(); db.refresh(p)
    return dev_project_dict(p, None, None)


@app.delete("/api/admin/dev-projects/{pid}")
def delete_dev_project(pid: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = db.get(DevProject, pid)
    if not p:
        raise HTTPException(404, "Projet introuvable.")
    db.query(DevTask).filter(DevTask.project_id == pid).delete()
    db.delete(p); db.commit()
    return {"ok": True}


@app.post("/api/admin/dev-projects/{pid}/tasks")
def create_dev_task(
    pid: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db),
    name: str = Form(...), start_date: str = Form(""), end_date: str = Form(""),
    progress: int = Form(0), status: str = Form("a_faire"), position: int = Form(0),
):
    if not db.get(DevProject, pid):
        raise HTTPException(404, "Projet introuvable.")
    if not name.strip():
        raise HTTPException(400, "Le nom de la tâche est obligatoire.")
    t = DevTask(
        project_id=pid, name=name.strip(), start_date=start_date.strip(),
        end_date=end_date.strip(), progress=max(0, min(100, progress)),
        status=status if status in TASK_STATUS_LABELS else "a_faire", position=position,
    )
    db.add(t); db.commit(); db.refresh(t)
    return dev_task_dict(t)


@app.put("/api/admin/dev-tasks/{tid}")
def update_dev_task(
    tid: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db),
    name: str = Form(...), start_date: str = Form(""), end_date: str = Form(""),
    progress: int = Form(0), status: str = Form("a_faire"), position: int = Form(0),
):
    t = db.get(DevTask, tid)
    if not t:
        raise HTTPException(404, "Tâche introuvable.")
    t.name = name.strip()
    t.start_date, t.end_date = start_date.strip(), end_date.strip()
    t.progress = max(0, min(100, progress))
    t.status = status if status in TASK_STATUS_LABELS else t.status
    t.position = position
    db.commit(); db.refresh(t)
    return dev_task_dict(t)


@app.delete("/api/admin/dev-tasks/{tid}")
def delete_dev_task(tid: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    t = db.get(DevTask, tid)
    if not t:
        raise HTTPException(404, "Tâche introuvable.")
    db.delete(t); db.commit()
    return {"ok": True}


# ===== Cycle de vie commande : devis, facture, envoi =====
def _next_doc_number(s: Settings, kind: str) -> str:
    if kind == "devis":
        n = f"{s.devis_prefix}{s.next_devis_number:05d}"
        s.next_devis_number += 1
    else:
        n = f"{s.invoice_prefix}{s.next_invoice_number:05d}"
        s.next_invoice_number += 1
    return n


def _build_document_from_order(db: Session, order: Order, kind: str) -> Invoice:
    client = db.get(User, order.client_id)
    if not client:
        raise HTTPException(400, "Client de la commande introuvable.")
    s = get_settings(db)
    lines = json.loads(order.lines or "[]")
    if not lines:
        raise HTTPException(400, "Ajoutez au moins une ligne à la commande avant de générer ce document.")
    total_ht = _lines_total(lines)
    vrate = (order.vat_rate or 0) if s.vat_applicable else 0
    total_vat = round(total_ht * vrate / 100)
    total_ttc = total_ht + total_vat
    number = _next_doc_number(s, kind)
    due = (date.today() + timedelta(days=s.devis_validity_days or 30)).isoformat() if kind == "devis" else (order.due_date or "")
    inv = Invoice(
        client_id=order.client_id, order_id=order.id, kind=kind, number=number,
        label=order.title, amount=euros(total_ttc),
        issued_date=date.today().isoformat(), due_date=due,
        lines=json.dumps(lines, ensure_ascii=False), vat_rate=vrate,
        total_ht_cents=total_ht, total_vat_cents=total_vat, total_ttc_cents=total_ttc,
        generated=True,
    )
    db.add(inv); db.commit(); db.refresh(inv)
    pdf = generate_invoice_pdf(inv, client, s, kind=kind)
    fname = f"{secrets.token_hex(10)}.pdf"
    (INVOICE_DIR / fname).write_bytes(pdf)
    inv.file = fname
    db.commit(); db.refresh(inv)
    return inv


@app.get("/api/admin/orders/{oid}")
def admin_get_order(oid: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    o = db.get(Order, oid)
    if not o:
        raise HTTPException(404, "Commande introuvable.")
    d = order_dict(o, _client_label(db, o.client_id))
    docs = db.query(Invoice).filter(Invoice.order_id == oid).order_by(Invoice.created_at.desc()).all()
    d["documents"] = [invoice_dict(i) for i in docs]
    return d


@app.post("/api/admin/orders/{oid}/devis")
def admin_order_devis(oid: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    o = db.get(Order, oid)
    if not o:
        raise HTTPException(404, "Commande introuvable.")
    return invoice_dict(_build_document_from_order(db, o, "devis"), _client_label(db, o.client_id))


@app.post("/api/admin/orders/{oid}/facture")
def admin_order_facture(oid: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    o = db.get(Order, oid)
    if not o:
        raise HTTPException(404, "Commande introuvable.")
    return invoice_dict(_build_document_from_order(db, o, "facture"), _client_label(db, o.client_id))


@app.post("/api/admin/invoices/{iid}/send")
def admin_send_document(iid: int, request: Request, _admin: User = Depends(require_admin),
                        db: Session = Depends(get_db)):
    inv = db.get(Invoice, iid)
    if not inv or not inv.file or not (INVOICE_DIR / inv.file).exists():
        raise HTTPException(404, "Document introuvable.")
    client = db.get(User, inv.client_id)
    if not client:
        raise HTTPException(400, "Client introuvable.")
    base = str(request.base_url).rstrip("/")
    is_devis = inv.kind == "devis"
    label = "devis" if is_devis else "facture"
    subject = f"MSolution — {'Devis' if is_devis else 'Facture'} {inv.number}"
    body = (
        f"Bonjour {client.name or ''},\n\n"
        f"Veuillez trouver ci-joint votre {label} {inv.number}"
        f"{' (montant : ' + inv.amount + ')' if inv.amount else ''}.\n\n"
        + ("Vous pouvez le consulter et l'accepter depuis votre espace client : "
           if is_devis else "Vous pouvez le retrouver dans votre espace client : ")
        + f"{base}/espace-client.html\n\nCordialement,\nL'équipe MSolution"
    )
    data = (INVOICE_DIR / inv.file).read_bytes()
    send_email(client.email, subject, body, attachment=(f"{label}-{inv.number or inv.id}.pdf", data))
    return {"ok": True}


@app.post("/api/client/orders/{oid}/accept")
def client_accept_devis(oid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    o = db.get(Order, oid)
    if not o or o.client_id != user.id:
        raise HTTPException(404, "Commande introuvable.")
    if o.status != "devis":
        raise HTTPException(400, "Cette commande n'est pas en attente d'acceptation.")
    if not db.query(Invoice).filter(Invoice.order_id == oid, Invoice.kind == "devis").first():
        raise HTTPException(400, "Aucun devis à accepter pour cette commande.")
    o.status = "validee"
    db.commit()
    admin = db.query(User).filter(User.role == "admin").first()
    if admin:
        who = user.name or user.company or user.email
        send_email(admin.email, f"MSolution — devis accepté par {who}",
                   f"{who} a accepté le devis de la commande « {o.title} » "
                   f"(réf. {o.reference or o.id}). La commande est passée en « Validée ».")
    return order_dict(o)


# ===== Site statique (monté en dernier) =====
app.mount("/", StaticFiles(directory=str(SITE_ROOT), html=True), name="site")
