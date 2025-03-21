import sys
from datetime import datetime, date, timedelta
from InvoiceTracker.models import db, Invoice, Case, SyncStatus, NotificationSettings, NotificationLog
from InvoiceTracker.src.api.api_client import InFaktAPIClient
from dotenv import load_dotenv
import logging

load_dotenv()

def sync_new_invoices(start_offset=0, limit=100):
    """
    Pobiera nowe faktury z inFaktu, dla których termin płatności przypada za 2 dni,
    i tworzy dla nich nowe sprawy (Invoice oraz Case).
    Zwraca liczbę przetworzonych rekordów.
    """
    client = InFaktAPIClient()
    client.reset_api_counter()  # Reset API counter at start
    processed_count = 0
    cases_created_count = 0  # Counter for new cases
    today = date.today()
    new_case_due_date = today + timedelta(days=2)
    new_case_due_date_str = new_case_due_date.strftime("%Y-%m-%d")
    offset = start_offset
    start_time = datetime.utcnow()

    # Cache for client details to avoid repeated API calls
    client_details_cache = {}

    while True:
        params = {
            "offset": offset,
            "limit": limit,
            "fields": "id,uuid,number,invoice_date,gross_price,status,client_id,payment_date,paid_price,payment_method,client_nip,client_company_name",
            "order": "invoice_date desc",
            "q[payment_date_eq]": new_case_due_date_str
        }
        url = f"{client.base_url}/invoices.json"
        try:
            response = client._session.get(url, headers=client.headers, params=params)
            response.raise_for_status()
        except Exception as e:
            print(f"[sync_new_invoices] Błąd przy pobieraniu partii offset={offset}: {e}")
            break

        data = response.json()
        batch_invoices = data.get("entities", [])
        # Filtrujemy, aby zachować tylko faktury o statusie 'sent' lub 'printed'
        batch_invoices = [inv for inv in batch_invoices if inv.get('status') in ('sent', 'printed')]
        if not batch_invoices:
            break

        for inv_data in batch_invoices:
            # Sprawdzamy, czy faktura już istnieje w bazie – jeśli tak, pomijamy
            local_inv = Invoice.query.filter_by(id=inv_data['id']).first()
            if local_inv:
                continue

            # Konwersja daty wystawienia
            invoice_date = None
            d_str = inv_data.get('invoice_date')
            if d_str and d_str != 'N/A':
                try:
                    invoice_date = datetime.strptime(d_str, '%Y-%m-%d').date()
                except Exception as e:
                    print(f"[sync_new_invoices] Błąd konwersji invoice_date: {e}")

            # Konwersja terminu płatności
            payment_due = None
            pd_str = inv_data.get('payment_date')
            if pd_str and pd_str != 'N/A':
                try:
                    payment_due = datetime.strptime(pd_str, '%Y-%m-%d').date()
                except Exception as e:
                    print(f"[sync_new_invoices] Błąd konwersji payment_date: {e}")

            # Tworzymy nową fakturę
            new_inv = Invoice(id=inv_data['id'])
            new_inv.invoice_number = inv_data.get('number', '')
            new_inv.invoice_date = invoice_date
            new_inv.payment_due_date = payment_due
            new_inv.gross_price = inv_data.get('gross_price', 0)
            new_inv.status = inv_data.get('status', '')
            new_inv.paid_price = inv_data.get('paid_price', 0)
            new_inv.client_id = inv_data.get('client_id', '')
            new_inv.client_nip = inv_data.get('client_nip', '')
            new_inv.client_company_name = inv_data.get('client_company_name', '')
            paid = new_inv.paid_price if new_inv.paid_price is not None else 0
            new_inv.left_to_pay = new_inv.gross_price - paid

            # Set default values for client details
            new_inv.client_email = 'N/A'
            new_inv.client_address = ''

            # Get client details if client_id exists
            client_id = inv_data.get('client_id', '')
            if client_id:
                # Fetch client details if not already in cache
                if client_id not in client_details_cache:
                    try:
                        cdata = client.get_client_details(client_id)
                        if cdata:
                            client_details_cache[client_id] = cdata
                            print(f"[sync_new_invoices] Got client details for client_id {client_id}")
                        else:
                            print(f"[sync_new_invoices] No client details returned for client_id {client_id}")
                            client_details_cache[client_id] = None
                    except Exception as e:
                        print(f"[sync_new_invoices] Error fetching client details for {client_id}: {e}")
                        client_details_cache[client_id] = None
                
                # Use cached client details
                cdata = client_details_cache.get(client_id)
                if cdata:
                    # Set client email
                    new_inv.client_email = cdata.get('email', 'N/A')
                    
                    # Update NIP if not already set
                    if not new_inv.client_nip:
                        new_inv.client_nip = cdata.get('nip', '')
                    
                    # Build address string
                    parts = []
                    post_code = cdata.get('postal_code', '')
                    street = cdata.get('street', '')
                    street_no = cdata.get('street_number', '')
                    flat_no = cdata.get('flat_number', '')
                    city = cdata.get('city', '')
                    
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
                    
                    new_inv.client_address = ", ".join(parts)
                    print(f"[sync_new_invoices] Set client details for new invoice {new_inv.invoice_number}")

            db.session.add(new_inv)
            db.session.commit()

            # Tworzymy nową sprawę, jeśli faktura nie jest opłacona
            if new_inv.status.lower() != "paid":
                new_case = Case(
                    case_number=new_inv.invoice_number,
                    client_id=new_inv.client_id,
                    client_nip=new_inv.client_nip,
                    client_company_name=new_inv.client_company_name,
                    status="active"
                )
                db.session.add(new_case)
                db.session.commit()
                # Odświeżamy referencję do faktury
                new_inv = Invoice.query.get(new_inv.id)
                new_inv.case_id = new_case.id
                db.session.add(new_inv)
                db.session.commit()
                cases_created_count += 1  # Increment cases created counter
                logging.info(f"[sync_new_invoices] Utworzono nową sprawę {new_case.case_number}")

            processed_count += 1
        offset += limit

    duration = (datetime.utcnow() - start_time).total_seconds()
    api_calls = client.get_api_counter()
    sync_record = SyncStatus(
        sync_type="new", 
        processed=processed_count, 
        duration=duration,
        cases_created=cases_created_count,
        api_calls=api_calls
    )
    db.session.add(sync_record)
    db.session.commit()
    print(f"[sync_new_invoices] Przetworzono {processed_count} faktur, utworzono {cases_created_count} spraw, wykonano {api_calls} wywołań API w {duration:.2f}s")
    return processed_count

def update_existing_cases(start_offset=0, limit=100):
    """
    Aktualizuje dane dla istniejących spraw – pobiera fakturę z inFaktu i sprawdza,
    czy faktura została opłacona. Jeśli tak, to zamyka sprawę.
    Zwraca liczbę przetworzonych rekordów.
    """
    client = InFaktAPIClient()
    client.reset_api_counter()  # Reset API counter at start
    processed_count = 0
    cases_updated_count = 0  # Counter for updated cases
    cases_closed_count = 0    # Counter for closed cases
    today = date.today()
    tomorrow = today + timedelta(days=1)
    offset = start_offset
    start_time = datetime.utcnow()

    # Get notification settings
    all_settings = NotificationSettings.get_all_settings()
    notification_days = list(all_settings.values())

    # Prepare list of dates on which notifications will be sent tomorrow
    target_dates = [tomorrow - timedelta(days=offset_val) for offset_val in notification_days]

    # Pobieramy ustawienia powiadomień z bazy danych
    notification_settings = NotificationSettings.get_all_settings()
    
    # Przygotuj listę dni różnicy, dla których powiadomienia będą wysyłane jutro
    notification_days = list(notification_settings.values())
    
    # Identyfikujemy faktury, dla których jutro przypada powiadomienie
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
    
    print(f"[update_existing_cases] Zakwalifikowano {len(combined_invoices)} faktur do aktualizacji")
    
    if not combined_invoices:
        print("[update_existing_cases] Brak faktur do aktualizacji.")
        duration = (datetime.utcnow() - start_time).total_seconds()
        sync_record = SyncStatus(sync_type="update", processed=0, duration=duration)
        db.session.add(sync_record)
        db.session.commit()
        return 0

    # Pobieramy tylko faktury, które zostały zakwalifikowane do aktualizacji
    while True:
        params = {
            "offset": offset,
            "limit": limit,
            "fields": "id,uuid,number,invoice_date,gross_price,status,client_id,payment_date,paid_price,payment_method,client_nip,client_company_name",
            "order": "invoice_date desc"
        }
        url = f"{client.base_url}/invoices.json"
        try:
            response = client._session.get(url, headers=client.headers, params=params)
            response.raise_for_status()
        except Exception as e:
            print(f"[update_existing_cases] Błąd przy pobieraniu partii offset={offset}: {e}")
            break

        data = response.json()
        batch_invoices = data.get("entities", [])
        # Filtrujemy tylko te faktury, które chcemy aktualizować + status sent/printed/paid
        batch_invoices = [
            inv for inv in batch_invoices 
            if (inv.get('id') in update_ids or inv.get('status') in ('sent', 'printed', 'paid'))
        ]
        
        if not batch_invoices:
            break

        for inv_data in batch_invoices:
            local_inv = Invoice.query.filter_by(id=inv_data['id']).first()
            if not local_inv:
                # Jeśli faktura jeszcze nie istnieje, pomijamy ją (może być już utworzona przez sync_new)
                continue

            # Aktualizacja daty wystawienia
            d_str = inv_data.get('invoice_date')
            if d_str and d_str != 'N/A':
                try:
                    local_inv.invoice_date = datetime.strptime(d_str, '%Y-%m-%d').date()
                except Exception as e:
                    print(f"[update_existing_cases] Błąd konwersji invoice_date: {e}")

            # Aktualizacja terminu płatności
            pd_str = inv_data.get('payment_date')
            payment_due = None
            if pd_str and pd_str != 'N/A':
                try:
                    payment_due = datetime.strptime(pd_str, '%Y-%m-%d').date()
                except Exception as e:
                    print(f"[update_existing_cases] Błąd konwersji payment_date: {e}")
            local_inv.payment_due_date = payment_due

            local_inv.gross_price = inv_data.get('gross_price', 0)
            local_inv.status = inv_data.get('status', '')
            local_inv.paid_price = inv_data.get('paid_price', 0)
            paid = local_inv.paid_price if local_inv.paid_price is not None else 0
            local_inv.left_to_pay = local_inv.gross_price - paid

            # Check if payment status has changed to 'paid'
            if 'paid' in inv_data.get('status', '').lower():
                local_inv.status = inv_data.get('status')
                # Zamykamy sprawę, jeśli została opłacona
                if local_inv.case:
                    local_inv.case.status = "closed_oplacone"
                    db.session.add(local_inv.case)
                    cases_closed_count += 1
                    print(f"[update_existing_cases] Zamknięto sprawę {local_inv.case.case_number} (faktura została opłacona)")
            
            db.session.add(local_inv)
            db.session.commit()
            cases_updated_count += 1

            processed_count += 1
        offset += limit

    duration = (datetime.utcnow() - start_time).total_seconds()
    api_calls = client.get_api_counter()
    sync_record = SyncStatus(
        sync_type="update", 
        processed=processed_count, 
        duration=duration,
        cases_updated=cases_updated_count,
        cases_closed=cases_closed_count,
        api_calls=api_calls
    )
    db.session.add(sync_record)
    db.session.commit()
    print(f"[update_existing_cases] Zaktualizowano {processed_count} faktur, zmieniono {cases_updated_count} spraw, zamknięto {cases_closed_count} spraw, wykonano {api_calls} wywołań API w {duration:.2f}s")
    return processed_count

def run_full_sync():
    """
    Wywołuje oba procesy: synchronizację nowych faktur oraz aktualizację istniejących.
    Rejestruje łączny wynik w SyncStatus (typ "full").
    """
    start_time = datetime.utcnow()
    
    # Get the latest sync records for reference (to track metrics)
    latest_new_sync = SyncStatus.query.filter_by(sync_type="new").order_by(SyncStatus.id.desc()).first()
    latest_update_sync = SyncStatus.query.filter_by(sync_type="update").order_by(SyncStatus.id.desc()).first()
    
    # Run sync processes
    new_count = sync_new_invoices()
    update_count = update_existing_cases()
    
    # Get the new sync records to calculate metrics
    new_sync = SyncStatus.query.filter_by(sync_type="new").order_by(SyncStatus.id.desc()).first()
    update_sync = SyncStatus.query.filter_by(sync_type="update").order_by(SyncStatus.id.desc()).first()
    
    # Calculate combined metrics
    total = new_count + update_count
    cases_created = new_sync.cases_created if new_sync else 0
    cases_updated = update_sync.cases_updated if update_sync else 0
    cases_closed = update_sync.cases_closed if update_sync else 0
    api_calls = (new_sync.api_calls if new_sync else 0) + (update_sync.api_calls if update_sync else 0)
    
    duration = (datetime.utcnow() - start_time).total_seconds()
    sync_record = SyncStatus(
        sync_type="full", 
        processed=total, 
        duration=duration,
        cases_created=cases_created,
        cases_updated=cases_updated,
        cases_closed=cases_closed,
        api_calls=api_calls
    )
    db.session.add(sync_record)
    db.session.commit()
    print(f"[run_full_sync] Łącznie przetworzono {total} faktur (nowe: {new_count}, aktualizacje: {update_count})")
    print(f"[run_full_sync] Utworzono {cases_created} spraw, zaktualizowano {cases_updated}, zamknięto {cases_closed}, wykonano {api_calls} wywołań API w {duration:.2f}s")
    return total

if __name__ == "__main__":
    run_full_sync()