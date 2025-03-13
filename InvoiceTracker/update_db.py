import sys
from datetime import datetime, date, timedelta
from InvoiceTracker.models import db, Invoice, Case, SyncStatus
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
    Jeśli faktura została opłacona, odpowiadająca jej sprawa zostaje zamknięta.
    Zwraca liczbę zaktualizowanych rekordów.
    """
    client = InFaktAPIClient()
    processed_count = 0
    offset = start_offset
    start_time = datetime.utcnow()

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
        # Pobieramy faktury o statusie 'sent', 'printed' lub 'paid'
        batch_invoices = [inv for inv in batch_invoices if inv.get('status') in ('sent', 'printed', 'paid')]
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

            db.session.add(local_inv)
            db.session.commit()

            # Aktualizacja statusu sprawy odpowiadającej fakturze
            case_obj = Case.query.filter_by(case_number=local_inv.invoice_number).first()
            if case_obj:
                if local_inv.status.lower() == "paid" or local_inv.paid_price >= local_inv.gross_price:
                    case_obj.status = "closed_oplacone"
                else:
                    case_obj.status = "active"
                db.session.add(case_obj)
                db.session.commit()
            processed_count += 1
        offset += limit

    duration = (datetime.utcnow() - start_time).total_seconds()
    sync_record = SyncStatus(sync_type="update", processed=processed_count, duration=duration)
    db.session.add(sync_record)
    db.session.commit()
    print(f"[update_existing_cases] Zaktualizowano {processed_count} faktur (offset={start_offset}) w {duration:.2f}s")
    return processed_count

def run_full_sync():
    """
    Wywołuje oba procesy: synchronizację nowych faktur oraz aktualizację istniejących.
    Rejestruje łączny wynik w SyncStatus (typ "full").
    """
    start_time = datetime.utcnow()
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