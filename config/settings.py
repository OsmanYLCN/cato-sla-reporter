import os
from pathlib import Path
from zoneinfo import ZoneInfo

# .env dosyasını yukle (varsa; sunucuda env var olarak da verilebilir)
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass  # python-dotenv yuklu degilse env var'lari sistem environment'tan okunur

# Genel sistem parametreleri ve saat dilimi
TIMEZONE: str = "Europe/Istanbul"
TZ: ZoneInfo = ZoneInfo(TIMEZONE)

# SLA hedef eşiği (%)
SLA_THRESHOLD_PCT: float = 99.90
SLA_STATUS_PASSED: str = "Passed"
SLA_STATUS_FAILED: str = "Failed"

# Rapor dönemlerinin toplam dakika karşılıkları
PERIOD_MINUTES: dict[int, int] = {
    0: 0,        # Özel tarih aralığı
    1: 43_200,   # 30 gün
    3: 129_600,  # 90 gün
}

PERIOD_LABELS: dict[int, str] = {
    0: "Custom Range",
    1: "Last 1 Month",
    3: "Last 3 Months",
}

# Anlık bağlantı dalgalanmalarını tolere etme süresi (saniye)
CORRELATION_WINDOW_SECONDS: int = 30

# Log veri yapısı ve sütun eşlemeleri
REQUIRED_COLUMNS: list[str] = [
    "src_site_name",
    "time",
    "event_sub_type",
    "socket_interface",
    "socket_role",
]

COL_SITE: str = "src_site_name"
COL_TIME: str = "time"
COL_EVENT: str = "event_sub_type"
COL_IFACE: str = "socket_interface"
COL_ROLE: str = "socket_role"

VALID_EVENT_TYPES: set[str] = {"Connected", "Disconnected"}

# Cato API'sinin gonderdigi tum event_sub_type degerlerinin kanonik karsiligi.
# "Connected" veya "Disconnected" olarak normalize edilir.
# Bu sayede transformer ve state machine tutarli calisir.
EVENT_TYPE_ALIASES: dict[str, str] = {
    # Baglanti tipleri -> Connected
    "Connected":                     "Connected",
    "Reconnected":                   "Connected",   # yeniden baglandi = baglandi
    "Site Connected":                "Connected",
    # Kopus tipleri -> Disconnected
    "Disconnected":                  "Disconnected",
    "Site Disconnected":             "Disconnected",
    # Failover durumu: bir bacak devralinca digeri kopuk sayilir
    "Socket Fail-Over":              "Disconnected",
}

# Dosya ve dizin yolları
OUTPUT_DIR: str = "output"
LOG_DIR: str = "logs"

# Excel çıktı biçimlendirme ayarları
EXCEL_SHEET_SUMMARY: str = "SLA Summary"
EXCEL_SHEET_DETAILS: str = "Outage Details"
EXCEL_SHEET_OVERALL: str = "Overall Summary"

COLOR_PASSED_BG: str = "FF92D050"
COLOR_PASSED_FONT: str = "FF375623"
COLOR_FAILED_BG: str = "FFFF0000"
COLOR_FAILED_FONT: str = "FF7B0000"
COLOR_HEADER_BG: str = "FF203864"
COLOR_HEADER_FONT: str = "FFFFFFFF"
COLOR_ROW_ALT: str = "FFD9E1F2"

# Log yapılandırması
LOG_LEVEL: str = "DEBUG"
LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# ---------------------------------------------------------------------------
# Cato Networks API Yapılandırması (v1.1.0)
# Değerler .env dosyasından veya sistem environment variable'larından okunur.
# ASLA bu dosyaya doğrudan yazılmaz — .env.example şablonuna bakın.
# ---------------------------------------------------------------------------
CATO_API_ENDPOINT: str = os.getenv(
    "CATO_API_ENDPOINT",
    "https://api.catonetworks.com/api/v1/graphql2",
)
CATO_ACCOUNT_ID: str = os.getenv("CATO_ACCOUNT_ID", "")
CATO_API_KEY: str = os.getenv("CATO_API_KEY", "")

# API istek ayarları
CATO_API_TIMEOUT_SECONDS: int = 60        # tek istek için maksimum bekleme
CATO_API_MAX_RETRIES: int = 3             # başarısız istekte yeniden deneme sayısı
CATO_API_RETRY_DELAY_SECONDS: int = 5     # yeniden denemeler arası bekleme (saniye)
CATO_API_PAGE_SIZE: int = 1_000          # her sayfada istenen maksimum kayıt sayısı

