# shipping_settings.py

NOTIFICATION_OFFSETS = {
    "Przypomnienie o zbliżającym się terminie płatności": -1,
    "Powiadomienie o upływie terminu płatności": 7,
    "Wezwanie do zapłaty": 14,
    "Powiadomienie o zamiarze skierowania sprawy do windykatora zewnętrznego i publikacji na giełdzie wierzytelności": 21,
    "Przekazanie sprawy do windykatora zewnętrznego": 30,
}

# REFRESH_THRESHOLDS określa przedziały dni, w których odświeżamy szczegóły faktury.
# Możesz je dowolnie modyfikować, by ograniczyć lub poszerzyć zakres synchronizacji.
REFRESH_THRESHOLDS = [-2, 6, 13, 20, 29]

# Konfiguracja synchronizacji – używana przez endpoint /manual_sync
SYNC_CONFIG = {
    "sync_offset": 0,
    "sync_limit": 100
}