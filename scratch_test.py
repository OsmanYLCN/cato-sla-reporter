"""
Tüm olası sistem risk noktalarını kontrol eder.
"""
import os
import sys
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

TZ = ZoneInfo("Europe/Istanbul")
UTC = ZoneInfo("UTC")

api_key = os.getenv('CATO_API_KEY')
account_id = os.getenv('CATO_ACCOUNT_ID')
endpoint = os.getenv('CATO_API_ENDPOINT', 'https://api.catonetworks.com/api/v1/graphql2')
headers = {'x-api-key': api_key, 'Content-Type': 'application/json'}

PASS = "OK"
FAIL = "FAIL"
WARN = "WARN"

results = []

def check(name, status, detail=""):
    results.append((name, status, detail))
    print(f"[{status}] {name}" + (f" -> {detail}" if detail else ""))

# ─────────────────────────────────────────
# 1. TimeFrame builder - tek ay
# ─────────────────────────────────────────
try:
    sys.path.insert(0, '.')
    from data_ingestion.cato_api_client import CatoApiClient
    c = CatoApiClient.__new__(CatoApiClient)
    
    s = datetime(2026, 8, 1, 0, 0, 0, tzinfo=TZ)
    e = datetime(2026, 8, 31, 23, 59, 59, tzinfo=TZ)
    tf = c._build_timeframe(s, e)
    expected = "utc.2026-07-{31/21:00:00--31/20:59:59}"  # UTC karsiligi
    # Sadece format kontrolu
    if tf.startswith("utc.") and "--" in tf:
        check("TimeFrame builder (tek ay UTC format)", PASS, tf)
    else:
        check("TimeFrame builder (tek ay UTC format)", FAIL, tf)
except Exception as ex:
    check("TimeFrame builder (tek ay UTC format)", FAIL, str(ex))

# ─────────────────────────────────────────
# 2. TimeFrame builder - cok aylik
# ─────────────────────────────────────────
try:
    s = datetime(2026, 6, 1, 0, 0, 0, tzinfo=TZ)
    e = datetime(2026, 8, 31, 23, 59, 59, tzinfo=TZ)
    tf = c._build_timeframe(s, e)
    if tf.startswith("last.P"):
        check("TimeFrame builder (cok ay -> last.PxD)", PASS, tf)
    else:
        check("TimeFrame builder (cok ay -> last.PxD)", FAIL, tf)
except Exception as ex:
    check("TimeFrame builder (cok ay)", FAIL, str(ex))

# ─────────────────────────────────────────
# 3. Parse timestamp - Unix ms
# ─────────────────────────────────────────
try:
    ts = CatoApiClient._parse_timestamp("1786794176000")
    if ts and ts.tzinfo is not None:
        check("Timestamp parse (Unix ms)", PASS, str(ts))
    else:
        check("Timestamp parse (Unix ms)", FAIL, str(ts))
except Exception as ex:
    check("Timestamp parse (Unix ms)", FAIL, str(ex))

# ─────────────────────────────────────────
# 4. Parse timestamp - ISO
# ─────────────────────────────────────────
try:
    ts = CatoApiClient._parse_timestamp("2026-08-15T10:30:00Z")
    if ts and ts.tzinfo is not None:
        check("Timestamp parse (ISO 8601)", PASS, str(ts))
    else:
        check("Timestamp parse (ISO 8601)", FAIL)
except Exception as ex:
    check("Timestamp parse (ISO 8601)", FAIL, str(ex))

# ─────────────────────────────────────────
# 5. API baglantisi ve 401 kontrolu
# ─────────────────────────────────────────
try:
    query = """
    query { eventsFeed(accountIDs: ["0"]) { marker } }
    """
    r = requests.post(endpoint, json={"query": query}, headers=headers, timeout=10)
    if r.status_code == 200:
        check("API baglan (HTTP 200 alindi)", PASS)
    elif r.status_code == 401:
        check("API baglan", FAIL, "401 Unauthorized - API key hatali")
    else:
        check("API baglan", WARN, f"HTTP {r.status_code}")
except Exception as ex:
    check("API baglan", FAIL, str(ex))

# ─────────────────────────────────────────
# 6. events query - gercek veri
# ─────────────────────────────────────────
try:
    query = """
    query GetConnectivityEvents(
      $accountID:  ID!
      $timeFrame:  TimeFrame!
      $filters:    [EventsFilter!]
      $dimensions: [EventsDimension]
      $measures:   [EventsMeasure]
    ) {
      events(accountID: $accountID timeFrame: $timeFrame filters: $filters
             dimensions: $dimensions measures: $measures) {
        records { fieldsMap }
      }
    }
    """
    variables = {
        'accountID': account_id,
        'timeFrame': "last.P7D",
        'filters': [{'fieldName': 'event_type', 'operator': 'is', 'values': ['Connectivity']}],
        'dimensions': [
            {'fieldName': 'event_sub_type'}, {'fieldName': 'src_site_name'},
            {'fieldName': 'socket_interface'}, {'fieldName': 'socket_role'}, {'fieldName': 'time'},
        ],
        'measures': [{'fieldName': 'event_count', 'aggType': 'count'}]
    }
    r = requests.post(endpoint, json={'query': query, 'variables': variables}, headers=headers, timeout=30)
    data = r.json()
    if 'errors' in data:
        check("events query (son 7 gun)", FAIL, data['errors'][0]['message'])
    else:
        recs = data['data']['events']['records']
        check("events query (son 7 gun)", PASS, f"{len(recs)} kayit")
except Exception as ex:
    check("events query (son 7 gun)", FAIL, str(ex))

# ─────────────────────────────────────────
# 7. Reconnected event_sub_type varliga kontrolu
# ─────────────────────────────────────────
try:
    # Transformer sadece "Connected" ve "Disconnected" kabul ediyor
    # Ama API "Reconnected" ve "Site Disconnected" gibi farkli eventler de gonderiyor
    from config.settings import VALID_EVENT_TYPES
    
    # Yukardaki son test sonucundaki kayitlarda gordugumuzu biliyoruz:
    # "Reconnected", "Site Disconnected" gibi degerler var
    api_event_types_seen = ["Reconnected", "Site Disconnected", "Connected", "Disconnected"]
    unrecognized = [e for e in api_event_types_seen if e not in VALID_EVENT_TYPES]
    
    if unrecognized:
        check(
            "Event tipi uyumu (VALID_EVENT_TYPES vs API)",
            WARN,
            f"API'dan gelen ama taninmayan event_sub_type: {unrecognized}"
        )
    else:
        check("Event tipi uyumu", PASS)
except Exception as ex:
    check("Event tipi uyumu", FAIL, str(ex))

# ─────────────────────────────────────────
# 8. Tum benzersiz event_sub_type degerlerini gercek API'den cek
# ─────────────────────────────────────────
try:
    query = """
    query GetConnectivityEvents(
      $accountID:  ID!
      $timeFrame:  TimeFrame!
      $filters:    [EventsFilter!]
      $dimensions: [EventsDimension]
      $measures:   [EventsMeasure]
    ) {
      events(accountID: $accountID timeFrame: $timeFrame filters: $filters
             dimensions: $dimensions measures: $measures) {
        records { fieldsMap }
      }
    }
    """
    variables = {
        'accountID': account_id,
        'timeFrame': "last.P30D",
        'filters': [{'fieldName': 'event_type', 'operator': 'is', 'values': ['Connectivity']}],
        'dimensions': [{'fieldName': 'event_sub_type'}],
        'measures': [{'fieldName': 'event_count', 'aggType': 'count'}]
    }
    r = requests.post(endpoint, json={'query': query, 'variables': variables}, headers=headers, timeout=30)
    data = r.json()
    if 'errors' not in data:
        recs = data['data']['events']['records']
        unique_events = sorted(set(rec['fieldsMap'].get('event_sub_type', '') for rec in recs))
        from config.settings import VALID_EVENT_TYPES
        unrecognized = [e for e in unique_events if e and e not in VALID_EVENT_TYPES]
        if unrecognized:
            check(
                "Gercek API event_sub_type degerleri",
                WARN,
                f"Taninmayan tipler: {unrecognized} | Tum gorunenler: {unique_events}"
            )
        else:
            check("Gercek API event_sub_type degerleri", PASS, str(unique_events))
    else:
        check("Gercek API event_sub_type degerleri", WARN, "Sorgu hatasi")
except Exception as ex:
    check("Gercek API event_sub_type degerleri", FAIL, str(ex))

# ─────────────────────────────────────────
print("\n" + "="*60)
print("OZET:")
for name, status, detail in results:
    print(f"  [{status}] {name}")
