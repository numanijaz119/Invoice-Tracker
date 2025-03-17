import os
import threading
from datetime import date, datetime, timedelta
from flask import Flask, render_template, redirect, url_for, request, flash, session
from dotenv import load_dotenv
import logging

# Modele bazy danych
from .models import db, Invoice, NotificationLog, Case, SyncStatus

# Inne moduły
from .send_email import send_email
from .shipping_settings import NOTIFICATION_OFFSETS, SYNC_CONFIG
from .mail_templates import MAIL_TEMPLATES
from .scheduler import start_scheduler  # Scheduler uruchamiany w tle
from .mail_utils import generate_email  # Funkcja generująca treść wiadomości
from .update_db import run_full_sync, sync_new_invoices, update_existing_cases

load_dotenv()

def map_stage(stage):
    """
    Mapa skrótów używanych w endpointach np. '/send_manual/<case>/<stage>'
    na pełne nazwy, które są używane w mail_templates (np. "przeds" -> "Przypomnienie o...")
    """
    mapping = {
        "przeds": "Przypomnienie o zbliżającym się terminie płatności",
        "7dni": "Powiadomienie o upływie terminu płatności",
        "14dni": "Wezwanie do zapłaty",
        "21dni": "Powiadomienie o zamiarze skierowania sprawy do windykatora zewnętrznego i publikacji na giełdzie wierzytelności",
        "30dni": "Przekazanie sprawy do windykatora zewnętrznego"
    }
    return mapping.get(stage, stage)

STAGE_LABELS = {
    "Przypomnienie o zbliżającym się terminie płatności": "Przypomnienie o zbliżającym się terminie płatności",
    "Powiadomienie o upływie terminu płatności": "Powiadomienie o upływie terminu płatności",
    "Wezwanie do zapłaty": "Wezwanie do zapłaty",
    "Powiadomienie o zamiarze skierowania sprawy do windykatora zewnętrznego i publikacji na giełdzie wierzytelności":
        "Powiadomienie o zamiarze skierowania sprawy do windykatora zewnętrznego i publikacji na giełdzie wierzytelności",
    "Przekazanie sprawy do windykatora zewnętrznego": "Przekazanie sprawy do windykatora zewnętrznego"
}

def create_app():
    app = Flask(__name__)
    app.secret_key = os.getenv('SECRET_KEY', 'secret')

    # Konfiguracja bazy Postgres (Cloud SQL)
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASSWORD')
    db_name = os.getenv('DB_NAME')

    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5432')

    instance_connection_name = os.getenv('INSTANCE_CONNECTION_NAME')
    # app.config['SQLALCHEMY_DATABASE_URI'] = (
    #     f"postgresql+psycopg2://{db_user}:{db_password}@/{db_name}?host=/cloudsql/{instance_connection_name}"
    # )
    
# Local PostgreSQL URI
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    )

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    # Tworzenie tabel bazy przy pierwszym uruchomieniu
    @app.before_first_request
    def create_tables():
        db.create_all()

    # Wymaganie zalogowania (z wyjątkiem login, static)
    @app.before_request
    def require_login():
        if request.endpoint not in ('login', 'static'):
            if not session.get('logged_in'):
                return redirect(url_for('login'))

    # Widok spraw aktywnych ("/")
    @app.route('/')
    def active_cases():
        search_query = request.args.get('search', '').strip().lower()
        sort_by = request.args.get('sort_by', 'case_number')
        sort_order = request.args.get('sort_order', 'asc')

        cases_query = Case.query.filter_by(status="active").all()
        cases_list = []
        for case_obj in cases_query:
            inv = Invoice.query.filter_by(case_id=case_obj.id).first()
            if inv:
                # Pozostała kwota do zapłaty
                left = inv.left_to_pay if inv.left_to_pay is not None else (inv.gross_price - (inv.paid_price or 0))
                # days_diff -> ile dni po terminie (jeśli payment_due_date jest ustawiona)
                day_diff = (date.today() - inv.payment_due_date).days if inv.payment_due_date else None

                # Obliczanie etapu z logów NotificationLog
                def stage_from_log_text(text):
                    mapping = {
                        "Przypomnienie o zbliżającym się terminie płatności": 1,
                        "Powiadomienie o upływie terminu płatności": 2,
                        "Wezwanie do zapłaty": 3,
                        "Powiadomienie o zamiarze skierowania sprawy do windykatora zewnętrznego i publikacji na giełdzie wierzytelności": 4,
                        "Przekazanie sprawy do windykatora zewnętrznego": 5
                    }
                    return mapping.get(text, 0)

                logs = NotificationLog.query.filter_by(invoice_number=inv.invoice_number).all()
                max_stage = 0
                for lg in logs:
                    st = stage_from_log_text(lg.stage)
                    if st > max_stage:
                        max_stage = st
                progress_val = int((max_stage / 5) * 100)

                email_val = inv.client_email if inv.client_email else "Brak"
                cases_list.append({
                    'case_number': case_obj.case_number,
                    'client_id': case_obj.client_id,
                    'client_company_name': case_obj.client_company_name,
                    'client_nip': case_obj.client_nip,
                    'client_email': email_val,
                    'total_debt': (left / 100.0) if left else 0.0,
                    'days_diff': day_diff,
                    'progress_percent': progress_val,
                    'status': case_obj.status
                })

        # Sortowanie
        if cases_list and sort_by in cases_list[0]:
            try:
                if isinstance(cases_list[0][sort_by], (int, float)):
                    cases_list = sorted(
                        cases_list,
                        key=lambda x: x.get(sort_by, 0),
                        reverse=(sort_order == "desc")
                    )
                else:
                    cases_list = sorted(
                        cases_list,
                        key=lambda x: (x.get(sort_by) or "").lower(),
                        reverse=(sort_order == "desc")
                    )
            except Exception as e:
                print("Sortowanie error:", e)

        total_debt_all = sum(c['total_debt'] for c in cases_list)
        active_count = len(cases_list)

        return render_template('cases.html',
                               cases=cases_list,
                               search_query=search_query,
                               sort_by=sort_by,
                               sort_order=sort_order,
                               total_debt_all=total_debt_all,
                               active_count=active_count)

    # Widok spraw zakończonych ("/completed")
    @app.route('/completed')
    def completed_cases():
        search_query = request.args.get('search', '').strip().lower()
        sort_by = request.args.get('sort_by', 'case_number')
        sort_order = request.args.get('sort_order', 'asc')

        cases_query = Case.query.filter(Case.status != "active").all()
        cases_list = []
        for case_obj in cases_query:
            inv = Invoice.query.filter_by(case_id=case_obj.id).first()
            if inv:
                left = inv.left_to_pay if inv.left_to_pay is not None else (inv.gross_price - (inv.paid_price or 0))
                day_diff = (date.today() - inv.payment_due_date).days if inv.payment_due_date else None

                def stage_from_log_text(text):
                    mapping = {
                        "Przypomnienie o zbliżającym się terminie płatności": 1,
                        "Powiadomienie o upływie terminu płatności": 2,
                        "Wezwanie do zapłaty": 3,
                        "Powiadomienie o zamiarze skierowania sprawy do windykatora zewnętrznego i publikacji na giełdzie wierzytelności": 4,
                        "Przekazanie sprawy do windykatora zewnętrznego": 5
                    }
                    return mapping.get(text, 0)
                logs = NotificationLog.query.filter_by(invoice_number=inv.invoice_number).all()
                max_stage = 0
                for lg in logs:
                    st = stage_from_log_text(lg.stage)
                    if st > max_stage:
                        max_stage = st
                progress_val = int((max_stage / 5) * 100)
                email_val = inv.client_email if inv.client_email else "Brak"

                cases_list.append({
                    'case_number': case_obj.case_number,
                    'client_id': case_obj.client_id,
                    'client_company_name': case_obj.client_company_name,
                    'client_nip': case_obj.client_nip,
                    'client_email': email_val,
                    'total_debt': (left / 100.0) if left else 0.0,
                    'days_diff': day_diff,
                    'progress_percent': progress_val,
                    'status': case_obj.status
                })

        if search_query:
            cases_list = [
                c for c in cases_list
                if search_query in (c.get('client_id') or '').lower()
                or search_query in (c.get('client_nip') or '').lower()
                or search_query in (c.get('client_company_name') or '').lower()
                or search_query in (c.get('case_number') or '').lower()
                or search_query in (c.get('client_email') or '').lower()
            ]

        if cases_list and 'case_number' in cases_list[0]:
            try:
                if isinstance(cases_list[0].get(sort_by), (int, float)):
                    cases_list = sorted(
                        cases_list,
                        key=lambda x: x.get(sort_by, 0),
                        reverse=(sort_order == "desc")
                    )
                else:
                    cases_list = sorted(
                        cases_list,
                        key=lambda x: (x.get(sort_by) or "").lower(),
                        reverse=(sort_order == "desc")
                    )
            except Exception as e:
                print("Sortowanie error:", e)

        completed_count = len(cases_list)
        stage_counts = {i: 0 for i in range(1, 6)}
        # Ewentualnie logika zliczania na jakim etapie sprawa zakończona

        return render_template('completed.html',
                               cases=cases_list,
                               search_query=search_query,
                               completed_count=completed_count,
                               stage_counts=stage_counts)

    # Widok szczegółów sprawy ("/case/<case_number>")
    @app.route('/case/<path:case_number>')
    def case_detail(case_number):
        case_obj = Case.query.filter_by(case_number=case_number).first_or_404()
        inv = Invoice.query.filter_by(case_id=case_obj.id).first_or_404()

        left = inv.left_to_pay if inv.left_to_pay is not None else (inv.gross_price - (inv.paid_price or 0))
        day_diff = (date.today() - inv.payment_due_date).days if inv.payment_due_date else None

        def stage_from_log_text(text):
            mapping = {
                "Przypomnienie o zbliżającym się terminie płatności": 1,
                "Powiadomienie o upływie terminu płatności": 2,
                "Wezwanie do zapłaty": 3,
                "Powiadomienie o zamiarze skierowania sprawy do windykatora zewnętrznego i publikacji na giełdzie wierzytelności": 4,
                "Przekazanie sprawy do windykatora zewnętrznego": 5
            }
            return mapping.get(text, 0)

        logs = NotificationLog.query.filter_by(invoice_number=inv.invoice_number)\
                                    .order_by(NotificationLog.sent_at.desc()).all()
        modified_logs = []
        for log in logs:
            modified_logs.append({
                "sent_at": log.sent_at,
                "stage": f"{log.stage} ({log.mode})",
                "subject": log.subject,
                "body": log.body
            })

        progress_val = 0
        if modified_logs:
            max_stage = max([stage_from_log_text(log["stage"].split(" (")[0]) for log in modified_logs])
            progress_val = int((max_stage / 5) * 100)

        return render_template('case_detail.html',
                               case=case_obj,
                               invoice=inv,
                               left_to_pay=left,
                               days_display=day_diff,
                               progress_percent=progress_val,
                               notifications=modified_logs)

    # Widok spraw klienta ("/client/<client_id>")
    @app.route('/client/<client_id>')
    def client_cases(client_id):
        current_date = date.today()
        active_objs = Case.query.filter_by(client_id=client_id, status="active").all()
        completed_objs = Case.query.filter(Case.client_id == client_id, Case.status != "active").all()
        active_cases_list = []
        completed_cases_list = []
        total_debt_all = 0.0

        def build_case_dict(case_obj):
            inv = case_obj.invoice
            if not inv:
                return None
            left = inv.left_to_pay if inv.left_to_pay is not None else (inv.gross_price - (inv.paid_price or 0))
            total_debt = left / 100.0
            days_diff = (current_date - inv.payment_due_date).days if inv.payment_due_date else None

            logs = NotificationLog.query.filter_by(invoice_number=inv.invoice_number).all()
            stage_mapping = {
                "Przypomnienie o zbliżającym się terminie płatności": 1,
                "Powiadomienie o upływie terminu płatności": 2,
                "Wezwanie do zapłaty": 3,
                "Powiadomienie o zamiarze skierowania sprawy do windykatora zewnętrznego i publikacji na giełdzie wierzytelności": 4,
                "Przekazanie sprawy do windykatora zewnętrznego": 5
            }
            max_stage = 0
            for lg in logs:
                s = stage_mapping.get(lg.stage, 0)
                if s > max_stage:
                    max_stage = s
            progress_val = int((max_stage / 5) * 100)

            return {
                'case_number': case_obj.case_number,
                'client_id': case_obj.client_id,
                'client_company_name': case_obj.client_company_name,
                'client_nip': case_obj.client_nip,
                'client_email': inv.client_email if inv.client_email else "Brak",
                'total_debt': total_debt,
                'days_diff': days_diff,
                'progress_percent': progress_val,
                'status': case_obj.status
            }

        for c in active_objs:
            res = build_case_dict(c)
            if res:
                total_debt_all += res['total_debt']
                active_cases_list.append(res)
        for c in completed_objs:
            res = build_case_dict(c)
            if res:
                completed_cases_list.append(res)

        active_count = len(active_cases_list)
        client_details = {}
        if active_cases_list:
            first = active_cases_list[0]
            client_details = {
                'client_company_name': first['client_company_name'],
                'client_nip': first['client_nip'],
                'client_email': first['client_email'],
                'client_address': ''  # można dodać, jeśli Invoice trzyma adres
            }
        elif completed_cases_list:
            first = completed_cases_list[0]
            client_details = {
                'client_company_name': first['client_company_name'],
                'client_nip': first['client_nip'],
                'client_email': first['client_email'],
                'client_address': ''
            }

        return render_template('client_cases.html',
                               active_cases=active_cases_list,
                               completed_cases=completed_cases_list,
                               client_id=client_id,
                               client_details=client_details,
                               total_debt_all=total_debt_all,
                               active_count=active_count,
                               current_date=current_date)

    # Oznaczenie faktury jako opłaconej
    @app.route('/mark_paid/<int:invoice_id>')
    def mark_invoice_paid(invoice_id):
        inv = Invoice.query.get_or_404(invoice_id)
        inv.status = "opłacona"
        inv.paid_date = datetime.utcnow().date()
        inv.left_to_pay = 0
        db.session.add(inv)

        case_obj = Case.query.get(inv.case_id)
        if case_obj:
            case_obj.status = "closed_oplacone"
            db.session.add(case_obj)

        db.session.commit()
        flash("Faktura została oznaczona jako opłacona, a sprawa zamknięta.", "success")
        return redirect(url_for('case_detail', case_number=inv.invoice_number))

    # Ręczne wysyłanie powiadomienia ("/send_manual/<case_number>/<stage>")
    @app.route('/send_manual/<path:case_number>/<stage>')
    def send_manual(case_number, stage):
        try:
            case_obj = Case.query.filter_by(case_number=case_number).first_or_404()
            inv = Invoice.query.filter_by(case_id=case_obj.id).first()
            if not inv:
                flash("Faktura nie znaleziona.", "danger")
                return redirect(url_for('active_cases'))

            mapped = map_stage(stage)
            subject, body_html = generate_email(mapped, inv)
            if not subject or not body_html:
                flash("Błąd w generowaniu szablonu wiadomości.", "danger")
                return redirect(url_for('case_detail', case_number=case_number))

            emails = [email.strip() for email in inv.client_email.split(',') if email.strip()]
            for email in emails:
                send_email(email, subject, body_html, html=True)

            inv.debt_status = mapped
            db.session.add(inv)

            new_log = NotificationLog(
                client_id=inv.client_id,
                invoice_number=inv.invoice_number,
                email_to=inv.client_email,
                subject=subject,
                body=body_html,
                stage=mapped,
                mode="Manualne"
            )
            db.session.add(new_log)
            db.session.commit()

            # Sprawdzamy, czy osiągnięto etap 5
            logs = NotificationLog.query.filter_by(invoice_number=inv.invoice_number).all()
            max_stage = 0
            def stage_from_log_text(t):
                mapping = {
                    "Przypomnienie o zbliżającym się terminie płatności": 1,
                    "Powiadomienie o upływie terminu płatności": 2,
                    "Wezwanie do zapłaty": 3,
                    "Powiadomienie o zamiarze skierowania sprawy do windykatora zewnętrznego i publikacji na giełdzie wierzytelności": 4,
                    "Przekazanie sprawy do windykatora zewnętrznego": 5
                }
                return mapping.get(t, 0)
            for log in logs:
                st = stage_from_log_text(log.stage)
                if st > max_stage:
                    max_stage = st

            if max_stage >= 5:
                case_obj.status = "closed_oplacone"
                db.session.add(case_obj)
                db.session.commit()

            flash("Powiadomienie zostało wysłane.", "success")
        except Exception as e:
            logging.error(f"Error in manual email sending: {e}")
            flash("Wystąpił błąd przy wysyłaniu powiadomienia. Sprawdź logi.", "danger")

        return redirect(url_for('case_detail', case_number=inv.invoice_number if inv else case_number))

    # Funkcja pomocnicza do uruchamiania synchronizacji w tle
    def background_sync(app):
        with app.app_context():
            try:
                start_time = datetime.utcnow()
                new_processed = sync_new_invoices()
                updated_processed = update_existing_cases()
                total = new_processed + updated_processed
                duration = (datetime.utcnow() - start_time).total_seconds()
                # Zapis informacji w SyncStatus
                record = SyncStatus(sync_type="full", processed=total, duration=duration)
                db.session.add(record)
                db.session.commit()
            except Exception as e:
                logging.error(f"Background sync error: {e}")

    # Ręczna synchronizacja – uruchamiana w tle, aby uniknąć timeoutu
    @app.route('/manual_sync', methods=['GET'])
    def manual_sync():
        # Uruchamiamy nowy wątek z kontekstem aplikacji
        t = threading.Thread(target=background_sync, args=(app,))
        t.start()
        flash("Synchronizacja została uruchomiona w tle. Sprawdź panel statusu synchronizacji.", "info")
        return redirect(url_for('active_cases'))

    # Panel statusu synchronizacji
    @app.route('/sync_status')
    def sync_status():
        statuses = SyncStatus.query.order_by(SyncStatus.timestamp.desc()).limit(20).all()
        return render_template('sync_status.html', statuses=statuses)

    # Ustawienia wysyłki ("/shipping_settings")
    @app.route('/shipping_settings', methods=['GET', 'POST'], endpoint='shipping_settings_view')
    def shipping_settings_view():
        from .shipping_settings import NOTIFICATION_OFFSETS
        current_settings = dict(NOTIFICATION_OFFSETS)
        if request.method == 'POST':
            for key in current_settings.keys():
                try:
                    new_value = int(request.form.get(key, current_settings[key]))
                    current_settings[key] = new_value
                except ValueError:
                    pass
            try:
                flash("Ustawienia zostały zaktualizowane i zapisane.", "success")
            except Exception as e:
                flash(f"Nie udało się zapisać ustawień: {e}", "danger")
            return redirect(url_for('shipping_settings_view'))
        return render_template('shipping_settings.html', settings=current_settings)

    # Logowanie
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            if username == 'admin' and password == 'admin':
                session['logged_in'] = True
                flash("Zalogowano pomyślnie.", "success")
                return redirect(url_for('active_cases'))
            else:
                flash("Nieprawidłowe dane logowania.", "danger")
        return render_template('login.html')

    # Wylogowanie
    @app.route('/logout')
    def logout():
        session.pop('logged_in', None)
        flash("Wylogowano.", "success")
        return redirect(url_for('login'))

    # Scheduler w tle
    with app.app_context():
        start_scheduler(app)

    return app

if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=8080, debug=True)