import sys
from datetime import datetime, date, timedelta
from InvoiceTracker.models import db, Invoice, Case, SyncStatus, NotificationSettings, NotificationLog
from InvoiceTracker.src.api.api_client import InFaktAPIClient
from dotenv import load_dotenv

load_dotenv()

def sync_new_invoices(start_offset=0, limit=100):
    """
    Pobiera nowe faktury z inFaktu, dla których termin płatności przypada za 2 dni,
    i tworzy dla nich nowe sprawy (Invoice oraz Case).
    Zwraca liczbę przetworzonych rekordów.
    """
    client = InFaktAPIClient()
    processed_count = 0
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
                new_inv.case_id = new_case.id
                db.session.add(new_inv)
                db.session.commit()

            processed_count += 1
        offset += limit

    duration = (datetime.utcnow() - start_time).total_seconds()
    # Zapisujemy wynik synchronizacji nowych faktur w tabeli SyncStatus
    sync_record = SyncStatus(sync_type="new", processed=processed_count, duration=duration)
    db.session.add(sync_record)
    db.session.commit()
    print(f"[sync_new_invoices] Przetworzono {processed_count} nowych faktur (offset={start_offset}) w {duration:.2f}s")
    return processed_count

def update_existing_cases(start_offset=0, limit=100):
    """
    Aktualizuje dane (status, kwoty) dla faktur już istniejących w bazie.
    Zoptymalizowana wersja, która aktualizuje tylko faktury, które:
    1. Są w aktywnych sprawach
    2. Mają zaplanowane powiadomienie na następny dzień
    3. Zostały niedawno dodane (w ciągu ostatnich 7 dni)
    4. Mają status, który może się zmienić na "paid"
    
    Jeśli faktura została opłacona, odpowiadająca jej sprawa zostaje zamknięta.
    Zwraca liczbę zaktualizowanych rekordów.
    """
    client = InFaktAPIClient()
    processed_count = 0
    start_time = datetime.utcnow()
    
    # Cache for client details to avoid repeated API calls
    client_details_cache = {}
    
    # 1. Determine which invoices need to be updated based on notification schedule
    today = date.today()
    tomorrow = today + timedelta(days=1)
    
    # Get notification settings from database
    notification_settings = NotificationSettings.get_all_settings()
    if not notification_settings:
        # Use default settings if none in database
        notification_settings = {
            "Przypomnienie o zbliżającym się terminie płatności": -1,
            "Powiadomienie o upływie terminu płatności": 7,
            "Wezwanie do zapłaty": 14,
            "Powiadomienie o zamiarze skierowania sprawy do windykatora zewnętrznego i publikacji na giełdzie wierzytelności": 21,
            "Przekazanie sprawy do windykatora zewnętrznego": 30,
        }
    
    # Get list of invoices that need to be updated
    cases_to_update = []
    
    # A. Cases with notifications scheduled for tomorrow
    for stage_name, offset_days in notification_settings.items():
        # Calculate the payment_due_date that corresponds to the notification's offset
        target_date = tomorrow - timedelta(days=offset_days)
        
        # Find active cases with payment_due_date matching the target date
        invoices = (Invoice.query
                  .join(Case, Invoice.case_id == Case.id)
                  .filter(Case.status == "active")
                  .filter(Invoice.payment_due_date == target_date)
                  .all())
        
        for invoice in invoices:
            # Check if this notification was already sent
            existing_log = NotificationLog.query.filter_by(
                invoice_number=invoice.invoice_number,
                stage=stage_name
            ).first()
            
            if not existing_log:
                # This invoice needs an update as it's due for notification
                cases_to_update.append(invoice)
                print(f"[update_existing_cases] Adding invoice {invoice.invoice_number} for scheduled notification {stage_name}")
    
    # B. Recently added cases (within last 7 days)
    recent_date = today - timedelta(days=7)
    recent_cases = (Invoice.query
                  .join(Case, Invoice.case_id == Case.id)
                  .filter(Case.status == "active")
                  .filter(Case.created_at >= recent_date)
                  .all())
    
    # Combine the lists, ensuring no duplicates
    for invoice in recent_cases:
        if invoice not in cases_to_update:
            cases_to_update.append(invoice)
    
    print(f"[update_existing_cases] Total number of cases to update: {len(cases_to_update)}")
    
    if not cases_to_update:
        duration = (datetime.utcnow() - start_time).total_seconds()
        sync_record = SyncStatus(sync_type="update", processed=0, duration=duration)
        db.session.add(sync_record)
        db.session.commit()
        print(f"[update_existing_cases] No cases need updating today.")
        return 0
    
    # 2. Update only the targeted invoices by getting their data from Infakt API
    invoice_ids_to_update = [invoice.id for invoice in cases_to_update]
    
    # Process in batches to respect API limits
    for i in range(0, len(invoice_ids_to_update), limit):
        batch_ids = invoice_ids_to_update[i:i+limit]
        
        # Get the invoice details from InFakt API
        for invoice_id in batch_ids:
            # Use the API to get fresh data for this invoice
            try:
                # Get invoice details by ID
                invoice_data = client.get_invoice_details(invoice_id)
                if not invoice_data:
                    print(f"[update_existing_cases] No data returned for invoice ID {invoice_id}")
                    continue
                
                # Update the local invoice record
                local_inv = Invoice.query.filter_by(id=invoice_id).first()
                if not local_inv:
                    print(f"[update_existing_cases] Local invoice not found for ID {invoice_id}")
                    continue
                
                # Update invoice data
                if 'invoice_date' in invoice_data and invoice_data['invoice_date'] and invoice_data['invoice_date'] != 'N/A':
                    try:
                        local_inv.invoice_date = datetime.strptime(invoice_data['invoice_date'], '%Y-%m-%d').date()
                    except Exception as e:
                        print(f"[update_existing_cases] Error converting invoice_date: {e}")
                
                if 'payment_date' in invoice_data and invoice_data['payment_date'] and invoice_data['payment_date'] != 'N/A':
                    try:
                        local_inv.payment_due_date = datetime.strptime(invoice_data['payment_date'], '%Y-%m-%d').date()
                    except Exception as e:
                        print(f"[update_existing_cases] Error converting payment_date: {e}")
                
                # Update other invoice fields
                local_inv.status = invoice_data.get('status', local_inv.status)
                local_inv.gross_price = invoice_data.get('gross_price', local_inv.gross_price)
                local_inv.paid_price = invoice_data.get('paid_price', local_inv.paid_price)
                
                # Calculate left_to_pay
                paid = local_inv.paid_price if local_inv.paid_price is not None else 0
                local_inv.left_to_pay = local_inv.gross_price - paid
                
                # Get client ID
                client_id = invoice_data.get('client_id', local_inv.client_id)
                if client_id:
                    # Update client NIP and company name if provided in invoice data
                    if 'client_nip' in invoice_data and invoice_data['client_nip']:
                        local_inv.client_nip = invoice_data['client_nip']
                    if 'client_company_name' in invoice_data and invoice_data['client_company_name']:
                        local_inv.client_company_name = invoice_data['client_company_name']
                    
                    # Fetch complete client details
                    if client_id not in client_details_cache:
                        try:
                            cdata = client.get_client_details(client_id)
                            if cdata:
                                client_details_cache[client_id] = cdata
                                print(f"[update_existing_cases] Got client details for client_id {client_id}")
                            else:
                                print(f"[update_existing_cases] No client details returned for client_id {client_id}")
                                client_details_cache[client_id] = None
                        except Exception as e:
                            print(f"[update_existing_cases] Error fetching client details for {client_id}: {e}")
                            client_details_cache[client_id] = None
                    
                    # Update with client details from cache
                    cdata = client_details_cache.get(client_id)
                    if cdata:
                        # Update email
                        local_inv.client_email = cdata.get('email', local_inv.client_email)
                        
                        # Update NIP if not already set
                        if not local_inv.client_nip and 'nip' in cdata:
                            local_inv.client_nip = cdata['nip']
                        
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
                        
                        local_inv.client_address = ", ".join(parts)
                        print(f"[update_existing_cases] Updated client details for invoice {local_inv.invoice_number}")
                
                db.session.add(local_inv)
                
                # Update the associated case
                case_obj = Case.query.filter_by(case_number=local_inv.invoice_number).first()
                if case_obj:
                    if local_inv.status.lower() == "paid" or local_inv.paid_price >= local_inv.gross_price:
                        case_obj.status = "closed_oplacone"
                        print(f"[update_existing_cases] Marked case {case_obj.case_number} as paid/closed")
                    
                    # Keep case client details in sync with invoice data
                    case_obj.client_id = local_inv.client_id
                    case_obj.client_nip = local_inv.client_nip
                    case_obj.client_company_name = local_inv.client_company_name
                    
                    db.session.add(case_obj)
                
                processed_count += 1
                
                # Commit every 5 records to avoid memory issues
                if processed_count % 5 == 0:
                    db.session.commit()
                    print(f"[update_existing_cases] Processed {processed_count} invoices so far...")
                
            except Exception as e:
                print(f"[update_existing_cases] Error processing invoice ID {invoice_id}: {e}")
                continue
    
    # Final commit
    db.session.commit()
    
    duration = (datetime.utcnow() - start_time).total_seconds()
    sync_record = SyncStatus(sync_type="update", processed=processed_count, duration=duration)
    db.session.add(sync_record)
    db.session.commit()
    print(f"[update_existing_cases] Updated {processed_count} invoices in {duration:.2f}s")
    return processed_count

def run_full_sync():
    """
    Wywołuje oba procesy: synchronizację nowych faktur oraz aktualizację istniejących.
    Rejestruje łączny wynik w SyncStatus (typ "full").
    """
    start_time = datetime.utcnow()
    
    # Run sync processes
    new_count = sync_new_invoices()
    update_count = update_existing_cases()
    
    total = new_count + update_count
    duration = (datetime.utcnow() - start_time).total_seconds()
    sync_record = SyncStatus(sync_type="full", processed=total, duration=duration)
    db.session.add(sync_record)
    db.session.commit()
    print(f"[run_full_sync] Łącznie przetworzono {total} faktur (nowe: {new_count}, aktualizacje: {update_count}) w {duration:.2f}s")
    return total

if __name__ == "__main__":
    run_full_sync()