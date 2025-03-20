# Current optimization:
- Uses pagination (limit=100)
- Filters by payment date in API query: "q[payment_date_eq]": new_case_due_date_str
- Caches client details: client_details_cache = {}
- Only processes 'sent' or 'printed' invoices
- Skips existing invoices

# Areas for improvement:
1. The client details fetching could be optimized:
```python
# Current approach:
if client_id not in client_details_cache:
    cdata = client.get_client_details(client_id)

# Could be improved to:
if client_id and client_id not in client_details_cache:
    # Batch fetch client details
    client_ids = [inv.get('client_id') for inv in batch_invoices if inv.get('client_id')]
    client_details = client.get_multiple_client_details(client_ids)  # New API method needed
    client_details_cache.update(client_details)
```

2. **update_existing_cases Optimization**:
```python
# Current optimization:
- Uses pagination (limit=100)
- Smart filtering of invoices to update:
  - Only invoices with notifications tomorrow
  - Only invoices from last 30 days
- Early exit if no updates needed
- Filters by invoice IDs in memory
- Stops after 1000 records

# Areas for improvement:
1. The API query could be more specific:
```python
# Current approach:
params = {
    "offset": offset,
    "limit": limit,
    "fields": "id,uuid,number,invoice_date,gross_price,status,client_id,payment_date,paid_price,payment_method,client_nip,client_company_name",
    "order": "invoice_date desc"
}

# Could be improved to:
params = {
    "offset": offset,
    "limit": limit,
    "fields": "id,uuid,number,invoice_date,gross_price,status,client_id,payment_date,paid_price,payment_method,client_nip,client_company_name",
    "order": "invoice_date desc",
    "q[status_in]": "sent,printed,paid",  # Filter at API level
    "q[invoice_date_gteq]": fresh_date.strftime("%Y-%m-%d")  # Filter at API level
}
```

2. Batch processing could be improved:
```python
# Current approach:
for inv_data in batch_invoices:
    local_inv = Invoice.query.filter_by(id=inv_data['id']).first()

# Could be improved to:
invoice_ids = [inv['id'] for inv in batch_invoices]
local_invoices = {inv.id: inv for inv in Invoice.query.filter(Invoice.id.in_(invoice_ids)).all()}
```

Here's a proposed optimized version of both functions:

```python
def sync_new_invoices(start_offset=0, limit=100):
    client = InFaktAPIClient()
    processed_count = 0
    today = date.today()
    new_case_due_date = today + timedelta(days=2)
    new_case_due_date_str = new_case_due_date.strftime("%Y-%m-%d")
    offset = start_offset
    start_time = datetime.utcnow()
    
    # Cache for client details
    client_details_cache = {}
    
    while True:
        # Optimize API query
        params = {
            "offset": offset,
            "limit": limit,
            "fields": "id,uuid,number,invoice_date,gross_price,status,client_id,payment_date,paid_price,payment_method,client_nip,client_company_name",
            "order": "invoice_date desc",
            "q[payment_date_eq]": new_case_due_date_str,
            "q[status_in]": "sent,printed"  # Filter at API level
        }
        
        try:
            response = client._session.get(f"{client.base_url}/invoices.json", 
                                         headers=client.headers, 
                                         params=params)
            response.raise_for_status()
        except Exception as e:
            print(f"[sync_new_invoices] Błąd przy pobieraniu partii offset={offset}: {e}")
            break

        data = response.json()
        batch_invoices = data.get("entities", [])
        if not batch_invoices:
            break

        # Batch fetch existing invoices
        invoice_ids = [inv['id'] for inv in batch_invoices]
        existing_invoices = {
            inv.id: inv for inv in Invoice.query.filter(Invoice.id.in_(invoice_ids)).all()
        }

        # Batch fetch client details
        client_ids = [inv.get('client_id') for inv in batch_invoices if inv.get('client_id')]
        client_details = client.get_multiple_client_details(client_ids)
        client_details_cache.update(client_details)

        for inv_data in batch_invoices:
            if inv_data['id'] in existing_invoices:
                continue

            # Process new invoice...
            # (rest of the invoice processing code)

        offset += limit
        if len(batch_invoices) < limit:
            break

    return processed_count

def update_existing_cases(start_offset=0, limit=100):
    client = InFaktAPIClient()
    processed_count = 0
    offset = start_offset
    start_time = datetime.utcnow()
    
    # Smart invoice selection (existing code)
    today = date.today()
    tomorrow = today + timedelta(days=1)
    notification_settings = NotificationSettings.get_all_settings()
    notification_days = list(notification_settings.values())
    
    # Get target invoices (existing code)
    target_invoices = []
    for offset_value in notification_days:
        target_date = tomorrow - timedelta(days=offset_value)
        invoices = (Invoice.query
                    .join(Case, Invoice.case_id == Case.id)
                    .filter(Case.status == "active")
                    .filter(Invoice.payment_due_date == target_date)
                    .all())
        target_invoices.extend(invoices)
    
    # Get fresh invoices (existing code)
    fresh_date = today - timedelta(days=30)
    fresh_invoices = (Invoice.query
                      .join(Case, Invoice.case_id == Case.id)
                      .filter(Case.status == "active")
                      .filter(Invoice.invoice_date >= fresh_date)
                      .all())
    
    # Optimize invoice selection
    update_ids = {inv.id for inv in target_invoices + fresh_invoices}
    if not update_ids:
        return 0

    while True:
        # Optimize API query
        params = {
            "offset": offset,
            "limit": limit,
            "fields": "id,uuid,number,invoice_date,gross_price,status,client_id,payment_date,paid_price,payment_method,client_nip,client_company_name",
            "order": "invoice_date desc",
            "q[status_in]": "sent,printed,paid",
            "q[invoice_date_gteq]": fresh_date.strftime("%Y-%m-%d")
        }
        
        try:
            response = client._session.get(f"{client.base_url}/invoices.json", 
                                         headers=client.headers, 
                                         params=params)
            response.raise_for_status()
        except Exception as e:
            print(f"[update_existing_cases] Błąd przy pobieraniu partii offset={offset}: {e}")
            break

        data = response.json()
        batch_invoices = data.get("entities", [])
        
        # Filter invoices at API level
        batch_invoices = [
            inv for inv in batch_invoices 
            if inv.get('id') in update_ids or inv.get('status') in ('sent', 'printed', 'paid')
        ]
        
        if not batch_invoices:
            break

        # Batch fetch existing invoices
        invoice_ids = [inv['id'] for inv in batch_invoices]
        existing_invoices = {
            inv.id: inv for inv in Invoice.query.filter(Invoice.id.in_(invoice_ids)).all()
        }

        # Process invoices in batch
        for inv_data in batch_invoices:
            local_inv = existing_invoices.get(inv_data['id'])
            if not local_inv:
                continue

            # Update invoice data...
            # (rest of the update code)

        offset += limit
        if len(batch_invoices) < limit or offset > 1000:
            break

    return processed_count