#send_email.py  
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
import logging

load_dotenv()

SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
SMTP_USERNAME = os.getenv('SMTP_USERNAME')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
EMAIL_FROM = os.getenv('EMAIL_FROM')


os.makedirs('logs', exist_ok=True)
logging.basicConfig(filename='logs/email_errors.log', level=logging.ERROR,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def send_email(to_email, subject, body, html=False):
    # Tworzymy wiadomość e-mail
    to_email = "minibhai009@gmail.com"
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
            print("Connecting to SMTP server:", SMTP_SERVER, SMTP_PORT)
            # server.connect(SMTP_SERVER, SMTP_PORT) # Explicit connection 
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            print(f"Login successful for: {SMTP_USERNAME}")
            server.sendmail(EMAIL_FROM, to_email, msg.as_string())
            print(f"Email wysłany do {to_email}")
            return True
    except smtplib.SMTPAuthenticationError:
        error_msg = "Błąd uwierzytelniania SMTP. Sprawdź dane logowania do serwera SMTP."
        print(error_msg)
        logging.error(error_msg)
        raise Exception(error_msg)
    except smtplib.SMTPConnectError:
        error_msg = "Nie można połączyć się z serwerem SMTP. Sprawdź ustawienia serwera i połączenie internetowe."
        print(error_msg)
        logging.error(error_msg)
        raise Exception(error_msg)
    except smtplib.SMTPException as e:
        error_msg = f"Błąd SMTP podczas wysyłania wiadomości: {str(e)}"
        print(error_msg)
        logging.error(error_msg)
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"Nieoczekiwany błąd podczas wysyłania wiadomości: {str(e)}"
        print(error_msg)
        logging.error(error_msg)
        raise Exception(error_msg)