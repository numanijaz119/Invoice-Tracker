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
      - cases_created: liczba utworzonych nowych spraw
      - cases_updated: liczba zaktualizowanych spraw
      - cases_closed: liczba zamkniętych spraw
      - api_calls: liczba wywołań API podczas synchronizacji
    """
    id = db.Column(db.Integer, primary_key=True)
    sync_type = db.Column(db.String(50))
    processed = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    duration = db.Column(db.Float)
    cases_created = db.Column(db.Integer, default=0)
    cases_updated = db.Column(db.Integer, default=0)
    cases_closed = db.Column(db.Integer, default=0)
    api_calls = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'<SyncStatus {self.sync_type}: {self.processed} faktur, {self.duration:.2f}s>'
    
    
class NotificationSettings(db.Model):
    """
    Model NotificationSettings – przechowuje ustawienia powiadomień w bazie danych.
    """
    id = db.Column(db.Integer, primary_key=True)
    stage_name = db.Column(db.String(255), unique=True, nullable=False)
    offset_days = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<NotificationSettings {self.stage_name}: {self.offset_days} days>'

    @classmethod
    def get_all_settings(cls):
        """Returns all settings as a dictionary"""
        settings = cls.query.all()
        return {setting.stage_name: setting.offset_days for setting in settings}

    @classmethod
    def update_settings(cls, settings_dict):
        """Updates all settings from a dictionary"""
        for stage_name, offset_days in settings_dict.items():
            setting = cls.query.filter_by(stage_name=stage_name).first()
            if setting:
                setting.offset_days = offset_days
            else:
                new_setting = cls(stage_name=stage_name, offset_days=offset_days)
                db.session.add(new_setting)
        db.session.commit()

    @classmethod
    def initialize_default_settings(cls):
        """Initializes default settings if none exist"""
        if not cls.query.first():
            default_settings = {
                "Przypomnienie o zbliżającym się terminie płatności": -1,
                "Powiadomienie o upływie terminu płatności": 7,
                "Wezwanie do zapłaty": 14,
                "Powiadomienie o zamiarze skierowania sprawy do windykatora zewnętrznego i publikacji na giełdzie wierzytelności": 21,
                "Przekazanie sprawy do windykatora zewnętrznego": 30,
            }
            for stage_name, offset_days in default_settings.items():
                new_setting = cls(stage_name=stage_name, offset_days=offset_days)
                db.session.add(new_setting)
            db.session.commit()