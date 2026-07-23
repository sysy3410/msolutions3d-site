"""
MSolutions3D — couche de données (SQLAlchemy).

Base SQLite unique partagée par le site public, l'espace client et le
logiciel de gestion. On démarre avec create_all ; les migrations Alembic
seront introduites quand le schéma devra évoluer sur des données réelles.
"""

from pathlib import Path
from datetime import datetime, timezone

from sqlalchemy import create_engine, Column, Integer, Float, String, Text, Boolean, DateTime, ForeignKey, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "msolution.db"

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password = Column(String, nullable=False)          # "pbkdf2$iterations$salt$hash"
    role = Column(String, nullable=False, default="client")   # "admin" | "client"
    name = Column(String, default="")
    company = Column(String, default="")
    phone = Column(String, default="")
    active = Column(Boolean, default=True, nullable=False)
    reset_token = Column(String, default="")
    reset_expires = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now_utc)


class Project(Base):
    """Réalisations impression 3D et projets logiciels du portfolio public."""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    type = Column(String, nullable=False)              # "impression3d" | "logiciel"
    title = Column(String, nullable=False)
    subtitle = Column(String, default="")
    category = Column(String, default="")
    description = Column(Text, default="")
    tags = Column(Text, default="[]")                  # liste JSON
    features = Column(Text, default="[]")              # liste JSON
    image = Column(String, default="")
    position = Column(Integer, default=0)
    created_at = Column(String, default=lambda: now_utc().isoformat())


class Order(Base):
    """Commande d'un client (impression 3D, développement, autre)."""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reference = Column(String, default="")
    title = Column(String, nullable=False)
    category = Column(String, default="")          # "impression3d" | "dev" | "autre"
    description = Column(Text, default="")
    status = Column(String, default="devis")       # voir STATUS_STEPS dans app.py
    amount = Column(String, default="")            # (ancien champ texte, conservé)
    amount_cents = Column(Integer, default=0)      # total HT en centimes (= somme des lignes)
    lines = Column(Text, default="[]")             # [{designation, qty, unit_price_cents}]
    vat_rate = Column(Float, default=0)            # taux TVA pour devis/facture
    due_date = Column(String, default="")          # date ISO ou ""
    created_at = Column(DateTime, default=now_utc)
    updated_at = Column(DateTime, default=now_utc, onupdate=now_utc)


class Invoice(Base):
    """Facture rattachée à un client (et éventuellement à une commande)."""
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    kind = Column(String, default="facture")       # "facture" | "devis"
    number = Column(String, default="")
    label = Column(String, default="")
    amount = Column(String, default="")            # TTC formaté (affichage liste)
    issued_date = Column(String, default="")
    due_date = Column(String, default="")
    file = Column(String, default="")              # nom de fichier privé dans data/invoices/
    # Champs des factures générées :
    lines = Column(Text, default="[]")             # [{designation, qty, unit_price_cents}]
    vat_rate = Column(Float, default=0)
    total_ht_cents = Column(Integer, default=0)
    total_vat_cents = Column(Integer, default=0)
    total_ttc_cents = Column(Integer, default=0)
    generated = Column(Boolean, default=False)
    paid = Column(Boolean, default=False)          # statut de paiement (factures)
    paid_at = Column(String, default="")           # date de règlement (ISO)
    created_at = Column(DateTime, default=now_utc)


class Settings(Base):
    """Paramètres de l'entreprise (ligne unique) pour les factures."""
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)
    company_name = Column(String, default="MSolutions3D")
    legal_form = Column(String, default="")
    address = Column(String, default="")
    postal_code = Column(String, default="")
    city = Column(String, default="")
    siret = Column(String, default="")
    vat_number = Column(String, default="")
    ape_code = Column(String, default="")
    capital = Column(String, default="")
    rcs = Column(String, default="")
    email = Column(String, default="")
    phone = Column(String, default="")
    iban = Column(String, default="")
    bic = Column(String, default="")
    vat_applicable = Column(Boolean, default=False)
    default_vat_rate = Column(Float, default=20.0)
    payment_terms = Column(String, default="Paiement à réception de la facture.")
    late_penalty = Column(Text, default=(
        "En cas de retard de paiement, application d'une pénalité égale à 3 fois "
        "le taux d'intérêt légal, ainsi qu'une indemnité forfaitaire de 40 € pour "
        "frais de recouvrement (art. L441-10 et D441-5 du Code de commerce)."))
    invoice_prefix = Column(String, default="F-")
    next_invoice_number = Column(Integer, default=1)
    devis_prefix = Column(String, default="D-")
    next_devis_number = Column(Integer, default=1)
    devis_validity_days = Column(Integer, default=30)
    # Paramètres du calculateur de coût de production 3D
    calc_printer_power_w = Column(Integer, default=250)
    calc_elec_price = Column(Float, default=0.25)      # €/kWh
    calc_machine_cost = Column(Float, default=0.80)    # €/h (amortissement + usure)
    calc_labor_cost = Column(Float, default=35.0)      # €/h (main d'œuvre)
    calc_failure_pct = Column(Float, default=5.0)      # % provision échec
    calc_margin_pct = Column(Float, default=50.0)      # % marge commerciale
    created_at = Column(DateTime, default=now_utc)


class FilamentSpool(Base):
    """Bobine de filament 3D en stock."""
    __tablename__ = "filament_spools"

    id = Column(Integer, primary_key=True)
    material = Column(String, default="")          # PLA, PETG, ABS, TPU, Nylon…
    color = Column(String, default="")
    brand = Column(String, default="")
    weight_total_g = Column(Integer, default=1000)
    weight_remaining_g = Column(Integer, default=1000)
    low_threshold_g = Column(Integer, default=150)
    cost_cents = Column(Integer, default=0)        # prix d'achat de la bobine
    supplier = Column(String, default="")
    purchase_date = Column(String, default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=now_utc)


class Expense(Base):
    """Dépense / charge (matières hors filament, matériel, abonnements…)."""
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True)
    label = Column(String, nullable=False)
    category = Column(String, default="general")   # impression3d | dev | general | autre
    amount_cents = Column(Integer, default=0)
    date = Column(String, default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=now_utc)


class Message(Base):
    """Message de la messagerie client ↔ administrateur (un fil par client)."""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    sender = Column(String, nullable=False)        # "client" | "admin"
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=now_utc)
    read_by_admin = Column(Boolean, default=False, nullable=False)
    read_by_client = Column(Boolean, default=False, nullable=False)


class DevProject(Base):
    """Projet de développement informatique (suivi en Gantt)."""
    __tablename__ = "dev_projects"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    description = Column(Text, default="")
    status = Column(String, default="en_cours")     # en_cours | en_pause | termine | annule
    start_date = Column(String, default="")
    end_date = Column(String, default="")
    created_at = Column(DateTime, default=now_utc)


class DevTask(Base):
    """Tâche d'un projet de développement (barre du Gantt)."""
    __tablename__ = "dev_tasks"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("dev_projects.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    start_date = Column(String, default="")
    end_date = Column(String, default="")
    progress = Column(Integer, default=0)           # 0-100
    status = Column(String, default="a_faire")      # a_faire | en_cours | termine
    position = Column(Integer, default=0)
    created_at = Column(DateTime, default=now_utc)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _column_default_sql(col) -> str:
    d = col.default
    if d is None or not hasattr(d, "arg"):
        return ""
    arg = d.arg
    if callable(arg):
        return ""
    if isinstance(arg, bool):
        return f" DEFAULT {1 if arg else 0}"
    if isinstance(arg, (int, float)):
        return f" DEFAULT {arg}"
    if isinstance(arg, str):
        return " DEFAULT '" + arg.replace("'", "''") + "'"
    return ""


def _auto_migrate() -> None:
    """Ajoute les colonnes manquantes aux tables existantes (SQLite ALTER TABLE)."""
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                coltype = col.type.compile(engine.dialect)
                conn.execute(text(
                    f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype}{_column_default_sql(col)}'
                ))


def init_db() -> None:
    """Crée les tables manquantes puis ajoute les colonnes manquantes."""
    Base.metadata.create_all(engine)
    _auto_migrate()
