# fetch_invoices.py
import sys
import asyncio
import csv
from datetime import datetime, date, timedelta
import aiohttp
import os
from flask import Flask

from .models import db, Invoice, NotificationLog, Case, NotificationSettings
from .send_email import send_email
from .sync_database import sync_database
from .src.api.api_client import InFaktAPIClient
from dotenv import load_dotenv

load_dotenv()

def create_test_app():
    """Creates a simple Flask app just for database operations"""
    app = Flask(__name__)
    
    # Konfiguracja bazy Postgres
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASSWORD')
    db_name = os.getenv('DB_NAME')
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5432')
    
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app

def export_invoices_to_csv(invoices, filename='invoices_with_due_dates.csv'):
    """
    Zapisuje listę faktur do pliku CSV, aby móc zweryfikować pobrane dane.
    """
    headers = [
        'ID', 'UUID', 'Numer', 'Data Wystawienia', 'Termin Płatności',
        'Kwota (zł)', 'Status', 'NIP', 'Nazwa Klienta', 'Email', 'Status Windykacji', 'Adres'
    ]
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=headers)
        writer.writeheader()
        for inv in invoices:
            writer.writerow({
                'ID': inv.get('id', ''),
                'UUID': inv.get('uuid', ''),
                'Numer': inv.get('number', ''),
                'Data Wystawienia': inv.get('invoice_date', ''),
                'Termin Płatności': inv.get('payment_due_date', 'N/A'),
                'Kwota (zł)': inv.get('gross_price', 0) / 100,
                'Status': inv.get('status', ''),
                'NIP': inv.get('client_nip', ''),
                'Nazwa Klienta': inv.get('client_company_name', ''),
                'Email': inv.get('client_email', ''),
                'Status Windykacji': inv.get('debt_status', ''),
                'Adres': inv.get('client_address', '')
            })
    print(f"[fetch_invoices] Faktury zapisane w pliku {filename}")

async def fetch_invoice_detail(session, client, invoice_uuid):
    """
    Asynchronicznie pobiera szczegóły pojedynczej faktury.
    """
    url = f"{client.base_url}/invoices/{invoice_uuid}.json"
    headers = client.headers
    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                data['uuid'] = invoice_uuid
                return data
            else:
                print(f"[fetch_invoices] Błąd pobierania faktury UUID={invoice_uuid}, kod HTTP={response.status}")
                return None
    except Exception as e:
        print(f"[fetch_invoices] Błąd przy pobieraniu faktury UUID={invoice_uuid}: {e}")
        return None

async def fetch_all_details(client, invoices):
    """
    Asynchronicznie pobiera szczegóły dla listy faktur.
    """
    async with aiohttp.ClientSession() as session:
        tasks = []
        for inv in invoices:
            uuid_val = inv.get('uuid')
            if uuid_val:
                tasks.append(fetch_invoice_detail(session, client, uuid_val))
        details = await asyncio.gather(*tasks)
        return [d for d in details if d]

def update_invoices_in_db():
    """
    Optymalizacja pobierania danych z API:
    1. Pobieramy tylko faktury o statusie 'sent' lub 'printed'
    2. Selektywnie aktualizujemy tylko faktury, które będą przetwarzane w najbliższym czasie
    3. Optymalizujemy aby szanować limity API InFakt i usprawnić działanie przy dużej liczbie spraw
    """
    client = InFaktAPIClient()
    app = create_test_app()
    
    with app.app_context():
        # Najpierw ustalamy, które faktury należy zaktualizować
        today = date.today()
        tomorrow = today + timedelta(days=1)
        
        # Get notification settings from database
        notification_settings = NotificationSettings.get_all_settings()
        
        # Przygotuj listę dni różnicy, dla których powiadomienia będą wysyłane jutro
        notification_days = list(notification_settings.values())
        
        # Pobierz aktywne faktury, dla których jutro przypada powiadomienie
        target_invoices = []
        for offset_value in notification_days:
            target_date = tomorrow - timedelta(days=offset_value)
            invoices = (Invoice.query
                        .join(Case, Invoice.case_id == Case.id)
                        .filter(Case.status == "active")
                        .filter(Invoice.payment_due_date == target_date)
                        .all())
            target_invoices.extend(invoices)
        
        # Dodatkowo pobieramy świeże faktury (z ostatnich 30 dni)
        fresh_date = today - timedelta(days=30)
        fresh_invoices = (Invoice.query
                          .join(Case, Invoice.case_id == Case.id)
                          .filter(Case.status == "active")
                          .filter(Invoice.invoice_date >= fresh_date)
                          .all())
        
        # Połącz listy i unikalne faktury po ID
        update_ids = set()
        combined_invoices = []
        
        for inv in target_invoices + fresh_invoices:
            if inv.id not in update_ids:
                update_ids.add(inv.id)
                combined_invoices.append(inv)
        
        print(f"[fetch_invoices] Zakwalifikowano {len(combined_invoices)} faktur do aktualizacji")
        
        if not combined_invoices:
            print("[fetch_invoices] Brak faktur do aktualizacji.")
            return
        
        # Pobieramy listę faktur z API (paginacja po 100 rekordów)
        invoices_list = []
        offset = 0
        limit = 100
        
        while True:
            try:
                data_batch = client.list_invoices(
                    offset=offset, 
                    limit=limit, 
                    fields=["id", "uuid", "number", "invoice_date", "gross_price", "status", "client_id"], 
                    order="invoice_date desc"
                )
                
                if not data_batch or len(data_batch) == 0:
                    break
                
                # Filtrujemy tylko te faktury, które chcemy aktualizować + status sent/printed
                data_filtered = [
                    inv for inv in data_batch 
                    if inv.get('id') in update_ids or inv.get('status') in ('sent', 'printed')
                ]
                
                invoices_list.extend(data_filtered)
                offset += limit
                
                # Zatrzymujemy się, gdy pobraliśmy już wszystkie potrzebne faktury
                if len(invoices_list) >= len(update_ids) and offset > 1000:
                    break
                
            except Exception as e:
                print(f"[fetch_invoices] Błąd podczas pobierania listy faktur: {e}")
                break

    if not invoices_list:
        print("[fetch_invoices] Nie znaleziono faktur do aktualizacji.")
        return

    # Pobieramy szczegóły asynchronicznie
    details = asyncio.run(fetch_all_details(client, invoices_list))
    details_map = {d['uuid']: d for d in details if 'uuid' in d}

    updated_invoices = []
    for inv in invoices_list:
        inv_uuid = inv.get('uuid', '')
        inv['payment_due_date'] = 'N/A'
        inv['debt_status'] = ''
        if inv_uuid in details_map:
            det = details_map[inv_uuid]
            inv['payment_due_date'] = det.get('payment_date', 'N/A')
            inv['currency'] = det.get('currency', 'PLN')
            inv['paid_price'] = det.get('paid_price', 0)
            inv['left_to_pay'] = det.get('left_to_pay', 0)
            inv['client_nip'] = det.get('client_tax_code', '')
            inv['client_company_name'] = det.get('client_company_name', '')

        # Pobieramy dane klienta (adres, email)
        client_id = inv.get('client_id', '')
        address_str = ''
        email_str = 'N/A'
        if client_id:
            try:
                cdata = client.get_client_details(client_id)
                if cdata:
                    email_str = cdata.get('email', 'N/A')
                    street = cdata.get('street', '')
                    street_no = cdata.get('street_number', '')
                    flat_no = cdata.get('flat_number', '')
                    city = cdata.get('city', '')
                    post_code = cdata.get('postal_code', '')
                    parts = []
                    if post_code:
                        parts.append(post_code)
                    if street:
                        s = street
                        if street_no:
                            s += f" {street_no}"
                        if flat_no:
                            s += f"/{flat_no}"
                        parts.append(s)
                    if city:
                        parts.append(city)
                    address_str = ", ".join(parts)
            except Exception as e:
                print(f"[fetch_invoices] Błąd podczas pobierania danych klienta {client_id}: {e}")
                
        inv['client_address'] = address_str
        inv['client_email'] = email_str
        updated_invoices.append(inv)

    # Zapis do bazy
    with create_test_app().app_context():
        updated_count = 0
        for inv in updated_invoices:
            local_inv = Invoice.query.filter_by(id=inv['id']).first()
            if not local_inv:
                local_inv = Invoice(id=inv['id'])

            local_inv.invoice_number = inv.get('number', '')
            d_str = inv.get('invoice_date')
            local_inv.invoice_date = None
            if d_str and d_str != 'N/A':
                try:
                    local_inv.invoice_date = datetime.strptime(d_str, '%Y-%m-%d').date()
                except Exception:
                    pass

            pd_str = inv.get('payment_due_date')
            if pd_str == 'N/A':
                local_inv.payment_due_date = None
            else:
                try:
                    local_inv.payment_due_date = datetime.strptime(pd_str, '%Y-%m-%d').date()
                except Exception:
                    local_inv.payment_due_date = None

            local_inv.gross_price = inv.get('gross_price', 0)
            local_inv.status = inv.get('status', '')
            local_inv.debt_status = inv.get('debt_status', '')
            local_inv.client_id = inv.get('client_id', '')
            local_inv.client_nip = inv.get('client_nip', '')
            local_inv.client_company_name = inv.get('client_company_name', '')
            local_inv.client_email = inv.get('client_email', 'N/A')
            local_inv.client_address = inv.get('client_address', '')
            local_inv.currency = inv.get('currency', 'PLN')
            local_inv.paid_price = inv.get('paid_price', 0)
            local_inv.left_to_pay = inv.get('left_to_pay', 0)

            db.session.add(local_inv)
            updated_count += 1
            
            # Mark as paid if needed
            if local_inv.left_to_pay == 0 and local_inv.gross_price > 0:
                case = Case.query.filter_by(case_number=local_inv.invoice_number).first()
                if case and case.status == "active":
                    case.status = "closed_oplacone"
                    db.session.add(case)
        
        db.session.commit()

    print(f"[fetch_invoices] Zakończono aktualizację {updated_count} faktur w bazie.")
    return updated_count

def main():
    update_invoices_in_db()

if __name__ == "__main__":
    main()