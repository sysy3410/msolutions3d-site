"""
MSolution — envoi d'e-mails.

En production : configurez ces variables d'environnement (SMTP de votre
service, ex. Brevo/Mailjet, ou boîte OVH/Outlook) :
    MSOLUTION_SMTP_HOST, MSOLUTION_SMTP_PORT (587), MSOLUTION_SMTP_USER,
    MSOLUTION_SMTP_PASSWORD, MSOLUTION_SMTP_FROM

En développement (aucun SMTP configuré) : les e-mails ne sont pas envoyés
mais journalisés dans data/emails_dev.log et affichés dans la console.
"""

import os
import ssl
import smtplib
from email.message import EmailMessage
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).resolve().parent / "data"
DEV_MAIL_LOG = DATA_DIR / "emails_dev.log"


def send_email(to: str, subject: str, body: str, attachment: tuple | None = None) -> None:
    """attachment = (nom_fichier, contenu_bytes) — PDF joint facultatif."""
    host = os.environ.get("MSOLUTION_SMTP_HOST")

    if not host:
        # Mode développement : pas d'envoi réel.
        att = f"\n[Pièce jointe : {attachment[0]} ({len(attachment[1])} octets)]" if attachment else ""
        entry = (
            f"\n{'=' * 60}\n{datetime.now().isoformat()}\n"
            f"À      : {to}\nSujet  : {subject}\n\n{body}\n{att}\n"
        )
        try:
            with open(DEV_MAIL_LOG, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception:
            pass
        print(f"[EMAIL — mode dev] Destinataire {to} | {subject}"
              + (f" | PJ {attachment[0]}" if attachment else ""))
        print("   (contenu enregistré dans backend/data/emails_dev.log)")
        return

    port = int(os.environ.get("MSOLUTION_SMTP_PORT", "587"))
    user = os.environ.get("MSOLUTION_SMTP_USER", "")
    password = os.environ.get("MSOLUTION_SMTP_PASSWORD", "")
    sender = os.environ.get("MSOLUTION_SMTP_FROM", user)

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if attachment:
        fname, data = attachment
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=fname)

    with smtplib.SMTP(host, port, timeout=20) as server:
        server.starttls(context=ssl.create_default_context())
        if user:
            server.login(user, password)
        server.send_message(msg)
