# sync_database.py
import sys
import asyncio
import csv
from datetime import datetime, date
import aiohttp

from .models import db, Invoice, Case
from .src.api.api_client import InFaktAPIClient
from dotenv import load_dotenv

load_dotenv()

def export_invoices_to_csv(invoices, filename='/tmp/sync_database_export.csv'):
    """
    Eksportuje dane faktur do pliku CSV w celu weryfikacji.
    """
    headers = [
        'ID', 'UUID', 'Numer', 'Data Wystawienia', 'Termin Płatności',
        'Kwota (zł)', 'Status', 'NIP', 'Nazwa Klienta', 'Email', 'Adres'
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
                'Termin Płatności': inv.get('payment_date', 'N/A'),  # inFakt -> "payment_date"
                'Kwota (zł)': inv.get('gross_price', 0) / 100,
                'Status': inv.get('status', ''),
                'NIP': inv.get('client_nip', ''),
                'Nazwa Klienta': inv.get('client_company_name', ''),
                'Email': inv.get('client_email', ''),
                'Adres': inv.get('client_address', '')
            })
    print(f"[sync_database] Dane faktur zapisane w pliku {filename}")

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
                print(f"[sync_database] Błąd pobierania faktury UUID={invoice_uuid}, HTTP={response.status}")
                return None
    except Exception as e:
        print(f"[sync_database] Błąd przy pobieraniu faktury UUID={invoice_uuid}: {e}")
        return None

async def fetch_all_details(client, invoices):
    """
    Asynchronicznie pobiera szczegóły (payment_date, currency, paid_price, left_to_pay) dla listy faktur.
    """
    async with aiohttp.ClientSession() as session:
        tasks = []
        for inv in invoices:
            uuid_val = inv.get('uuid')
            if uuid_val:
                tasks.append(fetch_invoice_detail(session, client, uuid_val))
        details = await asyncio.gather(*tasks)
        return [d for d in details if d is not None]

def sync_database():
    """
    Przykładowa funkcja do synchronizacji bazy – pobiera tylko faktury o statusie 'sent' i 'printed'
    (pomijamy 'paid'), następnie zapisuje/aktualizuje je w bazie.
    """
    client = InFaktAPIClient()

    # Pobieramy wszystkie faktury (paginacja w razie potrzeby)
    all_invoices = []
    offset = 0
    limit = 100
    while True:
        data_batch = client.list_invoices(offset=offset, limit=limit, fields=["id","uuid","number","invoice_date","gross_price","status","client_id"], order="invoice_date desc")
        if not data_batch:
            break
        if len(data_batch) == 0:
            break
        # Pomijamy 'paid'
        filtered = [inv for inv in data_batch if inv.get('status') in ('sent','printed')]
        all_invoices.extend(filtered)
        offset += limit

    if not all_invoices:
        print("[sync_database] Brak faktur do przetworzenia (status sent/printed).")
        return

    # Pobieramy szczegóły asynchronicznie
    details = asyncio.run(fetch_all_details(client, all_invoices))
    details_map = {d['uuid']: d for d in details}

    processed_invoices = []
    for inv_data in all_invoices:
        inv_uuid = inv_data.get('uuid')
        if not inv_uuid:
            continue
        inv_data['payment_due_date'] = 'N/A'
        inv_data['currency'] = 'PLN'
        inv_data['paid_price'] = 0
        inv_data['left_to_pay'] = 0
        if inv_uuid in details_map:
            det = details_map[inv_uuid]
            inv_data['payment_due_date'] = det.get('payment_date','N/A')
            inv_data['currency'] = det.get('currency','PLN')
            inv_data['paid_price'] = det.get('paid_price',0)
            inv_data['left_to_pay'] = det.get('left_to_pay',0)
            inv_data['client_nip'] = det.get('client_tax_code','')
            inv_data['client_company_name'] = det.get('client_company_name','')

        # Klient
        client_id = inv_data.get('client_id')
        inv_data['client_address'] = ''
        inv_data['client_email'] = 'N/A'
        if client_id:
            cdata = client.get_client_details(client_id)
            if cdata:
                inv_data['client_email'] = cdata.get('email','N/A')
                parts = []
                post_code = cdata.get('postal_code','')
                street = cdata.get('street','')
                street_no = cdata.get('street_number','')
                flat_no = cdata.get('flat_number','')
                city = cdata.get('city','')
                if post_code:
                    parts.append(post_code)
                if street:
                    s = street
                    if street_no:
                        s+=f" {street_no}"
                    if flat_no:
                        s+=f"/{flat_no}"
                    parts.append(s)
                if city:
                    parts.append(city)
                inv_data['client_address'] = ", ".join(parts)
        processed_invoices.append(inv_data)

    # Zapis do bazy
    for inv in processed_invoices:
        local_inv = Invoice.query.filter_by(id=inv['id']).first()
        if not local_inv:
            local_inv = Invoice(id=inv['id'])
        local_inv.invoice_number = inv.get('number','')
        try:
            if inv.get('invoice_date','N/A')!='N/A':
                local_inv.invoice_date = datetime.strptime(inv['invoice_date'],'%Y-%m-%d').date()
        except:
            pass
        try:
            if inv.get('payment_due_date','N/A')!='N/A':
                local_inv.payment_due_date = datetime.strptime(inv['payment_due_date'],'%Y-%m-%d').date()
        except:
            pass
        local_inv.gross_price = inv.get('gross_price',0)
        local_inv.status = inv.get('status','')
        local_inv.paid_price = inv.get('paid_price',0)
        local_inv.client_id = inv.get('client_id','')
        local_inv.client_nip = inv.get('client_nip','')
        local_inv.client_company_name = inv.get('client_company_name','')
        local_inv.client_email = inv.get('client_email','N/A')
        local_inv.client_address = inv.get('client_address','')
        local_inv.currency = inv.get('currency','PLN')
        local_inv.left_to_pay = inv.get('left_to_pay',0)
        db.session.add(local_inv)
    db.session.commit()

    export_invoices_to_csv(processed_invoices, '/tmp/sync_database_export.csv')
    print("[sync_database] Synchronizacja zakończona.")

if __name__=="__main__":
    from .app import create_app
    app = create_app()
    with app.app_context():
        sync_database()