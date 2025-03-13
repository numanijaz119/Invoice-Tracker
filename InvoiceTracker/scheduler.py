# scheduler.py
from datetime import datetime, timedelta, date
import time
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

# Usunięto import do update_database:
# from .update_db import update_database

from .models import db, Invoice, NotificationLog, Case
from .shipping_settings import NOTIFICATION_OFFSETS
from .mail_templates import MAIL_TEMPLATES
from .send_email import send_email
from .mail_utils import generate_email

load_dotenv()

def stage_to_number(text):
    mapping = {
        "Przypomnienie o zbliżającym się terminie płatności": 1,
        "Powiadomienie o upływie terminu płatności": 2,
        "Wezwanie do zapłaty": 3,
        "Powiadomienie o zamiarze skierowania sprawy do windykatora zewnętrznego i publikacji na giełdzie wierzytelności": 4,
        "Przekazanie sprawy do windykatora zewnętrznego": 5
    }
    return mapping.get(text, 0)

def run_sync_with_context(app):
    """
    Usuwamy starą funkcję update_database, więc nic tu nie robimy,
    albo usuwamy tę funkcję całkowicie z harmonogramu.
    """
    with app.app_context():
        print("[scheduler] run_sync_with_context() – brak starej logiki")

def run_mail_with_context(app):
    """
    Automatyczna wysyłka powiadomień e-mail w kontekście aplikacji,
    w partiach (batch_size).
    """
    with app.app_context():
        print("[scheduler] Rozpoczynam automatyczną wysyłkę maili (z app context)")
        today = date.today()
        batch_size = 100
        offset = 0

        while True:
            active_invoices = (Invoice.query.join(Case, Invoice.case_id == Case.id)
                               .filter(Case.status == "active")
                               .order_by(Invoice.invoice_date.desc())
                               .offset(offset)
                               .limit(batch_size)
                               .all())
            if not active_invoices:
                break

            for inv in active_invoices:
                if not inv.payment_due_date:
                    continue
                days_diff = (today - inv.payment_due_date).days

                for stage_name, offset_value in NOTIFICATION_OFFSETS.items():
                    if days_diff == offset_value:
                        existing_log = NotificationLog.query.filter_by(
                            invoice_number=inv.invoice_number,
                            stage=stage_name
                        ).first()
                        if existing_log:
                            continue

                        subject, body_html = generate_email(stage_name, inv)
                        if not subject or not body_html:
                            print(f"[scheduler] Brak szablonu dla {stage_name}, pomijam.")
                            continue

                        emails = [email.strip() for email in inv.client_email.split(',') if email.strip()]
                        for email in emails:
                            retries = 3
                            for attempt in range(retries):
                                try:
                                    send_email(email, subject, body_html, html=True)
                                    break
                                except Exception as e:
                                    print(f"[scheduler] Błąd wysyłki maila do {email} (próba {attempt+1}): {e}")
                                    time.sleep(5)

                        new_log = NotificationLog(
                            client_id=inv.client_id,
                            invoice_number=inv.invoice_number,
                            email_to=inv.client_email,
                            subject=subject,
                            body=body_html,
                            stage=stage_name,
                            mode="Automatyczne"
                        )
                        db.session.add(new_log)
                        db.session.commit()
                        print(f"[scheduler] Wysłano mail dla {inv.invoice_number}, etap={stage_name}")

                # Jeśli wysłano etap 5 => zamykamy sprawę
                logs = NotificationLog.query.filter_by(invoice_number=inv.invoice_number).all()
                stage5_sent = any(log.stage == "Przekazanie sprawy do windykatora zewnętrznego" for log in logs)
                if stage5_sent:
                    case_obj = Case.query.filter_by(case_number=inv.invoice_number).first()
                    if case_obj and case_obj.status != "closed_oplacone":
                        case_obj.status = "closed_oplacone"
                        db.session.add(case_obj)
                        db.session.commit()
                        print(f"[scheduler] Zamknięto sprawę {inv.invoice_number} (wysłano etap 5)")

            offset += batch_size

        print("[scheduler] Zakończono automatyczną wysyłkę maili")

def start_scheduler(app):
    """
    Inicjuje scheduler.
    - run_sync_with_context() jest teraz pusty albo do usunięcia, 
      bo nie mamy update_database.
    - run_mail_with_context() wysyła powiadomienia.
    """
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: run_sync_with_context(app), 'cron', hour=16, minute=55)
    scheduler.add_job(lambda: run_mail_with_context(app), 'cron', hour=17, minute=0)
    scheduler.start()
    print("[scheduler] Scheduler uruchomiony (z app context).")