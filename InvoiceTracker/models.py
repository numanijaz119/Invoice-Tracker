from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Case(db.Model):
    """
    Model Case – reprezentuje sprawę windykacyjną pojedynczej faktury.
    Numer sprawy to numer faktury.
    Status może być: "active", "closed_oplacone", "closed_nieoplacone".
    """
    id = db.Column(db.Integer, primary_key=True)
    case_number = db.Column(db.String(50), unique=True, nullable=False)
    client_id = db.Column(db.String(50), nullable=False)
    client_nip = db.Column(db.String(50), nullable=True)
    client_company_name = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(50), default="active")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacja 1:1 – każda sprawa odpowiada jednej fakturze
    invoice = db.relationship('Invoice', backref='case', uselist=False)
    
    def __repr__(self):
        return f'<Case {self.case_number} for client {self.client_id}>'

class Invoice(db.Model):
    """
    Model Invoice – przechowuje dane faktury pobrane z API inFakt
    oraz dane klienta. Jest powiązany (1:1) ze sprawą windykacyjną (Case).
    """
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50))
    invoice_date = db.Column(db.Date)
    payment_due_date = db.Column(db.Date)
    gross_price = db.Column(db.Integer)  # wartość brutto w groszach
    status = db.Column(db.String(50))    # np. "sent", "printed", "paid"
    debt_status = db.Column(db.String(200))
    client_id = db.Column(db.String(50))
    client_company_name = db.Column(db.String(200))
    client_email = db.Column(db.String(100))
    client_nip = db.Column(db.String(50))
    client_address = db.Column(db.String(255))
    currency = db.Column(db.String(10))
    paid_price = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)
    payment_method = db.Column(db.String(50))
    sale_date = db.Column(db.Date)
    paid_date = db.Column(db.Date)
    net_price = db.Column(db.Integer)
    tax_price = db.Column(db.Integer)
    left_to_pay = db.Column(db.Integer)
    case_id = db.Column(db.Integer, db.ForeignKey('case.id'), nullable=True)

    def __repr__(self):
        return f'<Invoice {self.invoice_number} for client {self.client_id}>'

class NotificationLog(db.Model):
    """
    Model NotificationLog – zapisuje historię wysłanych powiadomień (e-maili).
    """
    id = db.Column(db.Integer, primary_key=True)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    client_id = db.Column(db.String(50))
    invoice_number = db.Column(db.String(50))
    email_to = db.Column(db.String(100))
    subject = db.Column(db.String(200))
    body = db.Column(db.Text)
    stage = db.Column(db.String(255))
    mode = db.Column(db.String(20))
    scheduled_date = db.Column(db.DateTime)

    def __repr__(self):
        return f'<NotificationLog {self.subject} to {self.email_to} at {self.sent_at}>'

class SyncStatus(db.Model):
    """
    Model SyncStatus – rejestruje informacje o przebiegu synchronizacji:
      - sync_type: typ synchronizacji ("new", "update", "full")
      - processed: liczba przetworzonych faktur
      - timestamp: data wykonania synchronizacji
      - duration: czas trwania operacji (w sekundach)
    """
    id = db.Column(db.Integer, primary_key=True)
    sync_type = db.Column(db.String(50))
    processed = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    duration = db.Column(db.Float)

    def __repr__(self):
        return f'<SyncStatus {self.sync_type}: {self.processed} faktur, {self.duration:.2f}s>'