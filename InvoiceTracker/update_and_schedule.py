# update_and_schedule.py

import sys
from datetime import datetime, timedelta, date
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

from .src.api.api_client import InFaktAPIClient
from .models import db, NotificationLog, Invoice, Case, NotificationSettings
from .send_email import send_email
from .mail_templates import MAIL_TEMPLATES
from .update_db import update_invoices_in_db_batch as update_database

load_dotenv()

def run_daily_notifications():
    """
    Najpierw aktualizujemy dane faktur z API,
    a następnie dla każdej aktywnej sprawy (Case) wysyłamy powiadomienia,
    jeśli dzisiejsza data równa się (payment_due_date + offset) dla danego etapu.
    """
    try:
        # Przykładowa synchronizacja – możesz dostosować offset i limit
        update_database(0, 100)
    except Exception as e:
        print(f"Błąd aktualizacji bazy przed wysyłką powiadomień: {e}")

    today = date.today()
    active_invoices = Invoice.query.join(Case, Invoice.case_id == Case.id)\
                                   .filter(Case.status == "active")\
                                   .all()
    
    # Get notification settings from database
    notification_settings = NotificationSettings.get_all_settings()
    
    for invoice in active_invoices:
        if not invoice.payment_due_date:
            continue

        logs = NotificationLog.query.filter_by(
            invoice_number=invoice.invoice_number,
            client_id=invoice.client_id
        ).all()
        sent_stages = [int(log.stage) for log in logs if log.stage.isdigit()]
        next_stage = 1 if not sent_stages else max(sent_stages) + 1
        if next_stage > 5:
            continue

        stage_mapping = {
            1: ("Przypomnienie o zbliżającym się terminie płatności", "stage_1"),
            2: ("Powiadomienie o upływie terminu płatności", "stage_2"),
            3: ("Wezwanie do zapłaty", "stage_3"),
            4: ("Powiadomienie o zamiarze skierowania sprawy do windykatora zewnętrznego i publikacji na giełdzie wierzytelności", "stage_4"),
            5: ("Przekazanie sprawy do windykatora zewnętrznego", "stage_5"),
        }
        stage_text, template_key = stage_mapping.get(next_stage, (None, None))
        if stage_text is None:
            continue

        offset_value = notification_settings.get(stage_text)
        if offset_value is None:
            continue

        scheduled_date = invoice.payment_due_date + timedelta(days=offset_value)
        if scheduled_date == today:
            template = MAIL_TEMPLATES.get(template_key)
            if not template:
                continue

            subject = template["subject"].format(case_number=invoice.invoice_number)
            
            # Get the offset value for stage 4 from notification settings
            stage_4_offset = notification_settings.get("Powiadomienie o zamiarze skierowania sprawy do windykatora zewnętrznego i publikacji na giełdzie wierzytelności", 21)
            stage_4_date = (invoice.payment_due_date + timedelta(days=stage_4_offset)).strftime('%Y-%m-%d')
            
            body_html = template["body_html"].format(
                company_name=invoice.client_company_name,
                due_date=invoice.payment_due_date.strftime('%Y-%m-%d'),
                case_number=invoice.invoice_number,
                street_address=invoice.client_address,
                postal_code="",
                city="",
                nip=invoice.client_nip,
                debt_amount="%.2f" % (invoice.gross_price / 100 if invoice.gross_price else 0),
                stage_4_date=stage_4_date
            )
            recipient = invoice.client_email
            if recipient and recipient != "N/A":
                send_email(recipient, subject, body_html, html=True)
                log = NotificationLog(
                    client_id=invoice.client_id,
                    invoice_number=invoice.invoice_number,
                    email_to=recipient,
                    subject=subject,
                    body=body_html,
                    stage=str(next_stage),
                    mode="automatyczny",
                    scheduled_date=datetime.combine(scheduled_date, datetime.min.time())
                )
                db.session.add(log)
                db.session.commit()
                print(f"Automatyczne powiadomienie etapu {next_stage}/5 wysłane dla faktury {invoice.invoice_number}")
            else:
                print(f"Brak prawidłowego adresu email dla faktury {invoice.invoice_number}")

def start_daily_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_daily_notifications, 'cron', hour=12, minute=0)
    scheduler.start()
    print("Scheduler powiadomień automatycznych uruchomiony. Sprawdzanie następuje codziennie o 12:00.")
    try:
        while True:
            pass
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("Scheduler został zatrzymany.")

if __name__ == "__main__":
    start_daily_scheduler()