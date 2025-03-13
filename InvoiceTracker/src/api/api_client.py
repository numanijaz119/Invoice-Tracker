# src/api/api_client.py
import os
import requests
import logging
from dotenv import load_dotenv

# Wczytanie zmiennych środowiskowych z pliku .env
load_dotenv()

class InFaktAPIClient:
    def __init__(self):
        self.api_key = os.getenv('INFAKT_API_KEY')
        self.base_url = "https://api.infakt.pl/api/v3"
        if not self.api_key or self.api_key == "YOUR_INFAKT_API_KEY":
            raise ValueError("Klucz API inFakt nie został ustawiony. Sprawdź plik .env!")
        self.headers = {
            'X-inFakt-ApiKey': self.api_key,
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        # Utwórz obiekt Session do ponownego użycia połączeń HTTP
        self._session = requests.Session()
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s:%(levelname)s:%(message)s'
        )

    def test(self):
        print("InFaktAPIClient jest poprawnie skonfigurowany!")

    def list_invoices(self, offset=0, limit=10, fields=None, order=None):
        """
        Pobiera faktury bez dodatkowego filtrowania.
        """
        url = f"{self.base_url}/invoices.json"
        params = {"offset": offset, "limit": limit}
        if fields:
            params['fields'] = ','.join(fields)
        if order:
            params['order'] = order
        try:
            response = self._session.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            logging.info(f"Pobrano listę faktur: offset={offset}, limit={limit}")
            return data.get('entities', [])
        except requests.exceptions.HTTPError as http_err:
            logging.error(f"HTTP error przy pobieraniu faktur: {http_err} - {response.text}")
        except Exception as err:
            logging.error(f"Inny błąd przy pobieraniu faktur: {err}")
        return None

    def list_active_invoices(self, offset=0, limit=10, order=None):
        """
        Pobiera tylko faktury, których status to 'sent' lub 'printed'.
        Dzięki temu nie pobieramy faktur opłaconych (status 'paid').
        """
        url = f"{self.base_url}/invoices.json"
        params = {
            "offset": offset,
            "limit": limit,
            # Filtrowanie po statusie: korzystamy z modyfikatora _eq, aby pobrać tylko faktury o statusie 'sent' lub 'printed'
            "q[status_eq]": "sent",  # Pierwszy etap – możemy też później wykonać drugie zapytanie dla 'printed'
            "order": order or "invoice_date desc"
        }
        try:
            response = self._session.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            logging.info(f"Pobrano aktywne faktury: offset={offset}, limit={limit}")
            invoices_sent = data.get('entities', [])
            # Dodatkowo pobieramy faktury o statusie 'printed'
            params["q[status_eq]"] = "printed"
            response_printed = self._session.get(url, headers=self.headers, params=params)
            response_printed.raise_for_status()
            data_printed = response_printed.json()
            invoices_printed = data_printed.get('entities', [])
            return invoices_sent + invoices_printed
        except requests.exceptions.HTTPError as http_err:
            logging.error(f"HTTP error przy pobieraniu aktywnych faktur: {http_err} - {response.text}")
        except Exception as err:
            logging.error(f"Inny błąd przy pobieraniu aktywnych faktur: {err}")
        return None

    def list_clients(self, offset=0, limit=100):
        url = f"{self.base_url}/clients.json"
        params = {"offset": offset, "limit": limit}
        try:
            response = self._session.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            logging.info(f"Pobrano listę klientów: offset={offset}, limit={limit}")
            return data.get("entities", [])
        except requests.exceptions.HTTPError as http_err:
            logging.error(f"HTTP error przy pobieraniu klientów: {http_err}")
        except Exception as err:
            logging.error(f"Inny błąd przy pobieraniu klientów: {err}")
        return None

    def get_client_details(self, client_id):
        url = f"{self.base_url}/clients/{client_id}.json"
        try:
            response = self._session.get(url, headers=self.headers)
            response.raise_for_status()
            client = response.json()
            logging.info(f"Pobrano szczegóły klienta: {client_id}")
            return client
        except requests.exceptions.HTTPError as http_err:
            logging.error(f"HTTP error przy pobieraniu danych klienta {client_id}: {http_err}")
        except Exception as err:
            logging.error(f"Inny błąd przy pobieraniu danych klienta {client_id}: {err}")
        return None