# mail_templates.py

MAIL_TEMPLATES = {
    "stage_1": {
        "subject": "Przypomnienie o zbliżającym się terminie płatności dla {case_number}",
        "body_html": """<p><strong>{company_name},</strong><br><br>
Informujemy, iż z dniem <strong>{due_date}</strong> mija termin zapłaty dla faktury <strong>{case_number}</strong>. 
Prosimy o terminowe uregulowanie płatności wobec <strong>AQUATEST LABORATORIUM BADAWCZE SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ</strong>.<br><br>
W przypadku kiedy należność została opłacona, proszę o zignorowanie poniższej wiadomości.</p>

<p><strong>Specyfikacja należności:</strong><br>
<strong>{company_name}</strong><br>
<strong>{street_address}</strong><br>
<strong>{postal_code}</strong>, <strong>{city}</strong><br>
<strong>NIP: {nip}</strong><br>
Nr sprawy: <strong>{case_number}</strong><br>
Kwota zadłużenia: <strong>{debt_amount} zł</strong><br>
Rachunek do spłaty: 27 1140 1124 0000 3980 6300 1001</p>

<p><strong>Kontakt do wierzyciela w celu wyjaśnienia sprawy:</strong><br>
Telefon: 451089077<br>
E-mail: rozliczenia@aquatest.pl</p>
"""
    },

    "stage_2": {
        "subject": "Przypomnienie o upływie terminu płatności dla {case_number}",
        "body_html": """<p><strong>{company_name},</strong><br><br>
Informujemy, iż z dniem <strong>{due_date}</strong> minął termin płatności dla faktury <strong>{case_number}</strong>. 
Prosimy o jak najszybsze uregulowanie należności wobec <strong>AQUATEST LABORATORIUM BADAWCZE SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ</strong>.<br><br>
W przypadku kiedy należność została opłacona, proszę o zignorowanie poniższej wiadomości.</p>

<p><strong>Specyfikacja należności:</strong><br>
<strong>{company_name}</strong><br>
<strong>{street_address}</strong><br>
<strong>{postal_code}</strong>, <strong>{city}</strong><br>
<strong>NIP: {nip}</strong><br>
Nr sprawy: <strong>{case_number}</strong><br>
Kwota zadłużenia: <strong>{debt_amount} zł</strong><br>
Rachunek do spłaty: 27 1140 1124 0000 3980 6300 1001</p>

<p><strong>Kontakt do wierzyciela w celu wyjaśnienia sprawy:</strong><br>
Telefon: 451089077<br>
E-mail: rozliczenia@aquatest.pl</p>

<p><strong>Harmonogram działań w przypadku braku płatności:</strong><br>
{stage_3_date} - Ostateczne wezwanie do zapłaty.<br>
{stage_4_date} - Powiadomienie o zamiarze skierowania sprawy do windykatora zewnętrznego i publikacji na giełdzie wierzytelności.<br>
{stage_5_date} - Przekazanie sprawy do windykatora zewnętrznego</p>

<p><strong>Pamiętaj, aby zapobiec wpisowi na giełdę wierzytelności należy spłacić należność.</strong></p>
"""
    },

    "stage_3": {
        "subject": "Wezwanie do zapłaty {case_number}",
        "body_html": """<p><strong>{company_name},</strong><br><br>
Informujemy, że Państwa wierzyciel – <strong>AQUATEST LABORATORIUM BADAWCZE SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ</strong> w dniu <strong>{stage_4_date}</strong> 
upubliczni poniższe dane wraz z wysokością zadłużenia w sprawie <strong>{case_number}</strong>.<br><br>
W przypadku kiedy należność została opłacona, proszę o zignorowanie poniższej wiadomości.</p>

<p><strong>Specyfikacja należności:</strong><br>
<strong>{company_name}</strong><br>
<strong>{street_address}</strong><br>
<strong>{postal_code}</strong>, <strong>{city}</strong><br>
<strong>NIP: {nip}</strong><br>
Nr sprawy: <strong>{case_number}</strong><br>
Kwota zadłużenia: <strong>{debt_amount} zł</strong><br>
Rachunek do spłaty: 27 1140 1124 0000 3980 6300 1001</p>

<p><strong>Kontakt do wierzyciela w celu wyjaśnienia sprawy:</strong><br>
Telefon: 451089077<br>
E-mail: rozliczenia@aquatest.pl</p>

<p><strong>Harmonogram działań w przypadku braku płatności:</strong><br>
{stage_4_date} - Powiadomienie o zamiarze skierowania sprawy do windykatora zewnętrznego i publikacji na giełdzie wierzytelności.<br>
{stage_5_date} - Przekazanie sprawy do windykatora zewnętrznego</p>

<p><strong>Pamiętaj, aby zapobiec wpisowi na giełdę wierzytelności należy spłacić należność.</strong></p>
"""
    },

    "stage_4": {
        "subject": "Powiadomienie o zamiarze skierowania sprawy {case_number} do windykatora zewnętrznego i publikacji na giełdzie wierzytelności",
        "body_html": """<p><strong>{company_name},</strong><br><br>
Informujemy, że w systemie Vindicat.pl zostały upublicznione Państwa dane wraz z wysokością zadłużenia w sprawie <strong>{case_number}</strong>. 
Aby uregulować zaległość należy skontaktować się z wierzycielem: 
<strong>AQUATEST LABORATORIUM BADAWCZE SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ</strong>.<br><br>
W przypadku kiedy należność została opłacona, proszę o zignorowanie poniższej wiadomości.</p>

<p><strong>Specyfikacja należności:</strong><br>
<strong>{company_name}</strong><br>
<strong>{street_address}</strong><br>
<strong>{postal_code}</strong>, <strong>{city}</strong><br>
<strong>NIP: {nip}</strong><br>
Nr sprawy: <strong>{case_number}</strong><br>
Kwota zadłużenia: <strong>{debt_amount} zł</strong><br>
Rachunek do spłaty: 27 1140 1124 0000 3980 6300 1001</p>

<p><strong>Kontakt do wierzyciela w celu wyjaśnienia sprawy:</strong><br>
Telefon: 451089077<br>
E-mail: rozliczenia@aquatest.pl</p>

<p><strong>Harmonogram działań w przypadku braku płatności:</strong><br>
{stage_5_date} - Skierowanie sprawy do windykatora zewnętrznego</p>

<p><strong>Pamiętaj, aby zapobiec wpisowi na giełdę wierzytelności należy spłacić należność.</strong></p>
"""
    },

    "stage_5": {
        "subject": "Przekazanie sprawy {case_number} do windykatora zewnętrznego",
        "body_html": """<p><strong>{company_name},</strong><br><br>
Informujemy, że Państwa sprawa o zapłatę kwoty <strong>{debt_amount} zł</strong> wobec 
<strong>AQUATEST LABORATORIUM BADAWCZE SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ</strong> 
została skierowana do windykatora zewnętrznego. Istnieje możliwość wycofania sprawy i zawarcia porozumienia. 
Aby uregulować zaległość należy skontaktować się z wierzycielem: 
<strong>AQUATEST LABORATORIUM BADAWCZE SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ</strong>.<br><br>
W przypadku kiedy należność została opłacona, proszę o zignorowanie poniższej wiadomości.</p>

<p><strong>Specyfikacja należności:</strong><br>
<strong>{company_name}</strong><br>
<strong>{street_address}</strong><br>
<strong>{postal_code}</strong>, <strong>{city}</strong><br>
<strong>NIP: {nip}</strong><br>
Nr sprawy: <strong>{case_number}</strong><br>
Kwota zadłużenia: <strong>{debt_amount} zł</strong><br>
Rachunek do spłaty: 27 1140 1124 0000 3980 6300 1001</p>

<p><strong>Kontakt do wierzyciela w celu wyjaśnienia sprawy:</strong><br>
Telefon: 451089077<br>
E-mail: rozliczenia@aquatest.pl</p>

<p><strong>Aby zapobiec realizacji tego etapu, prosimy o uregulowanie należności.</strong></p>
"""
    }
}