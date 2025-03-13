#send_email.py  
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
SMTP_USERNAME = os.getenv('SMTP_USERNAME')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
EMAIL_FROM = os.getenv('EMAIL_FROM')

def send_email(to_email, subject, body, html=False):
    # Tworzymy wiadomość e-mail
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = EMAIL_FROM
    msg['To'] = to_email

    if html:
        # Dodajemy wersję HTML
        part = MIMEText(body, 'html')
    else:
        # Dodajemy wersję plain text
        part = MIMEText(body, 'plain')
    msg.attach(part)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(EMAIL_FROM, to_email, msg.as_string())
            print(f"Email wysłany do {to_email}")
    except Exception as e:
        print(f"Błąd przy wysyłce email do {to_email}: {e}")